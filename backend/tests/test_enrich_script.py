"""Offline rehearsal of scripts/enrich.py, which the user runs for real: the real KB and chunk splitter, with fake
prices, LLM and stacks, a fresh database and chunk-set folder (no network, no cost)."""

import importlib.util

import pytest

from rag_playground import store
from rag_playground.chunking import chunk_sets, enrichment
from rag_playground.llm.models import ModelInfo
from rag_playground.llm.openrouter import ChatResult, paid
from rag_playground.rag import enrich_run, estimate, pipeline, spend
from rag_playground.settings import ENRICH_MODEL, REPO_ROOT, settings
from rag_playground.stacks import openai_vector_store, qdrant_store

spec = importlib.util.spec_from_file_location("enrich", REPO_ROOT / "backend" / "scripts" / "enrich.py")
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)

SIZE, OVERLAP = 2048, 0
BASE_ID, SET_ID = "fixed__c2048__o0", "llm_enriched__c2048__o0"


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Fresh var/ folder, budget $5, the enrichment model's tokens at $1 per million and any other model's at ten times
    that, one saved chunk set, a fake LLM whose calls cost `world["cost"]` each, and fake stacks that record what they
    index."""
    monkeypatch.setattr(settings, "var_dir", tmp_path)
    monkeypatch.setattr(settings, "budget_usd", 5.0)

    def info(model):
        price = 1e-6 if model == ENRICH_MODEL else 1e-5
        return ModelInfo(model, f"{model}-1", frozenset({"temperature"}), price, price)

    monkeypatch.setattr(estimate, "model_info", info)
    state = {"calls": 0, "cost": 0.0001, "indexed": []}

    def fake_llm(model, messages, schema):
        state["calls"] += 1
        return schema(headline="A headline", summary="A summary."), paid(ChatResult(
            text="{}", model=model, canonical_slug=f"{model}-1", temperature_controlled=True, prompt_tokens=100,
            completion_tokens=50, reasoning_tokens=0, cost_usd=state["cost"]))

    monkeypatch.setattr(enrichment, "chat_structured", fake_llm)
    monkeypatch.setattr(openai_vector_store, "create_store", lambda name: "vs_1")
    monkeypatch.setattr(openai_vector_store, "upload_chunks", lambda sid, chunks: state["indexed"].append(("A", chunks)))
    monkeypatch.setattr(qdrant_store, "client", lambda: "qdrant")
    monkeypatch.setattr(qdrant_store, "index_chunks", lambda q, name, chunks: state["indexed"].append(("B", chunks))
                        or len(chunks))
    chunk_sets.load_or_build(SIZE, OVERLAP)
    return state


@pytest.fixture
def conn(world):
    connection = store.connect()
    yield connection
    connection.close()


def test_the_estimate_is_each_chunks_real_input_plus_the_assumed_output(conn):
    documents = chunk_sets.kb_documents()
    expected = sum(estimate.count(enrichment.messages(c, documents[c.source])) + enrich_run.OUTPUT_TOKENS
                   for c in chunk_sets.load(BASE_ID)) * 1e-6
    assert enrich_run.remaining_cost(BASE_ID) == pytest.approx(expected)


def test_the_estimate_counts_only_chunks_not_paid_for_yet(conn, world):
    full = enrich_run.remaining_cost(BASE_ID)
    enrich_run.enrich_set(conn, BASE_ID)
    assert full > 0 and enrich_run.remaining_cost(BASE_ID) == 0


def test_a_build_over_the_budget_is_refused_before_any_paid_call(conn, world, monkeypatch):
    monkeypatch.setattr(settings, "budget_usd", enrich_run.remaining_cost(BASE_ID) * 0.99)
    with pytest.raises(pipeline.BudgetExceeded, match="BUDGET_USD"):
        enrich_run.enrich_set(conn, BASE_ID)
    assert world["calls"] == 0 and spend.total(conn) == 0
    assert not chunk_sets.saved_path(SET_ID).exists()


def test_every_paid_call_is_recorded_outside_any_run(conn, world):
    enriched = enrich_run.enrich_set(conn, BASE_ID)
    rows = conn.execute("SELECT run_id, model, cost_usd FROM spend").fetchall()
    assert [tuple(row) for row in rows] == [(None, ENRICH_MODEL, world["cost"])] * len(enriched)


def test_a_build_stops_at_the_cap_keeps_what_was_paid_for_and_resumes_with_more_budget(conn, world, monkeypatch):
    """Dearer calls than estimated: the budget is used up after 3 of them, and the 4th is never sent."""
    budget = enrich_run.remaining_cost(BASE_ID) * 1.5
    monkeypatch.setattr(settings, "budget_usd", budget)
    world["cost"] = budget / 3
    with pytest.raises(pipeline.BudgetExceeded, match="Budget reached"):
        enrich_run.enrich_set(conn, BASE_ID)
    assert world["calls"] == 3
    assert len(chunk_sets.load(SET_ID)) == 3
    monkeypatch.setattr(settings, "budget_usd", 5.0)
    world["cost"] = 0.0001
    world["calls"] = 0
    enriched = enrich_run.enrich_set(conn, BASE_ID)
    assert len(enriched) == len(chunk_sets.load(BASE_ID))
    assert world["calls"] == len(enriched) - 3


def test_the_script_enriches_and_indexes_both_stacks_with_the_enriched_chunks(conn, world, capsys):
    script.main(SIZE, OVERLAP, "both")
    enriched = enrichment.load_complete(SET_ID)
    assert [stack for stack, _ in world["indexed"]] == ["A", "B"]
    assert all(chunks == enriched for _, chunks in world["indexed"])
    out = capsys.readouterr().out
    assert f"{len(enriched)} chunks" in out and f"recorded spend ${world['cost'] * len(enriched):.4f}" in out


@pytest.mark.parametrize("which, stacks", [("A", ["A"]), ("B", ["B"])])
def test_the_script_indexes_only_the_stack_asked_for(conn, world, which, stacks):
    script.main(SIZE, OVERLAP, which)
    assert [stack for stack, _ in world["indexed"]] == stacks


def test_a_second_script_run_pays_nothing_and_does_not_index_again(conn, world):
    script.main(SIZE, OVERLAP, "both")
    calls, indexed = world["calls"], len(world["indexed"])
    script.main(SIZE, OVERLAP, "both")
    assert (world["calls"], len(world["indexed"])) == (calls, indexed)


def test_the_script_builds_a_base_set_that_is_missing(conn, world):
    chunk_sets.saved_path(BASE_ID).unlink()
    script.main(SIZE, OVERLAP, "B")
    assert world["indexed"][0][1] == enrichment.load_complete(SET_ID)


def test_the_script_reports_this_builds_spend_not_all_spend(conn, world, capsys):
    """Money spent earlier stays in the budget but is not part of this build."""
    spend.record(conn, None, ChatResult(text="", model="m", canonical_slug="m-1", temperature_controlled=True,
                                        prompt_tokens=1, completion_tokens=1, reasoning_tokens=0, cost_usd=1.5))
    script.main(SIZE, OVERLAP, "B")
    enriched = enrichment.load_complete(SET_ID)
    out = capsys.readouterr().out
    assert f"recorded spend ${world['cost'] * len(enriched):.4f}" in out and "$3.5000 left" in out


def test_a_stopped_build_is_not_indexed(conn, world, monkeypatch):
    monkeypatch.setattr(settings, "budget_usd", 0.0)
    with pytest.raises(pipeline.BudgetExceeded):
        script.main(SIZE, OVERLAP, "both")
    assert world["indexed"] == []
