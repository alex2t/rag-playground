"""Offline rehearsal of scripts/first_run.py, which the user runs for real: fake stacks, models and prices, a fresh
database and chunk-set folder (no network, no cost)."""

import importlib.util

import pytest

from rag_playground import store
from rag_playground.datasets.schema import load_tests
from rag_playground.datasets.splits import round_robin
from rag_playground.llm.models import ModelInfo
from rag_playground.llm.openrouter import ChatResult, paid
from rag_playground.rag import estimate, pipeline, runs, spend
from rag_playground.scoring.judging import Judgement
from rag_playground.settings import REPO_ROOT, S0, settings
from rag_playground.stacks import openai_vector_store, qdrant_store
from rag_playground.stacks.hits import Hit

spec = importlib.util.spec_from_file_location("first_run", REPO_ROOT / "backend" / "scripts" / "first_run.py")
first_run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(first_run)

VERDICT = Judgement(refused=False, accuracy=5, completeness=5, relevance=5, faithfulness=5, feedback="ok",
                    faithfulness_feedback="ok")


def call(cost: float) -> ChatResult:
    return ChatResult(text="An answer.", model="m", canonical_slug="m-1", temperature_controlled=True,
                      prompt_tokens=100, completion_tokens=10, reasoning_tokens=0, cost_usd=cost)


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Fresh var/ folder, budget $5, every token priced at $1 per million, fake stacks and models."""
    seen = {"created": [], "searched": []}
    monkeypatch.setattr(settings, "var_dir", tmp_path)
    monkeypatch.setattr(settings, "budget_usd", 5.0)
    info = lambda m: ModelInfo(m, f"{m}-1", frozenset({"temperature"}), 1e-6, 1e-6)
    monkeypatch.setattr(pipeline, "model_info", info)
    monkeypatch.setattr(estimate, "model_info", info)
    monkeypatch.setattr(openai_vector_store, "create_store", lambda name: seen["created"].append(name) or "vs_1")
    monkeypatch.setattr(openai_vector_store, "upload_chunks", lambda sid, chunks: len(chunks))
    monkeypatch.setattr(qdrant_store, "client", lambda: "qdrant")
    monkeypatch.setattr(qdrant_store, "index_chunks", lambda q, name, chunks: seen["created"].append(name) or len(chunks))

    def hits(k):
        return [Hit(f"c{i}", f"doc{i}.md", 1.0, "text") for i in range(k)]

    monkeypatch.setattr(openai_vector_store, "search",
                        lambda sid, question, k, ranking: seen["searched"].append(("A", sid, k, ranking)) or hits(k))
    monkeypatch.setattr(qdrant_store, "search",
                        lambda q, name, question, k, hybrid: seen["searched"].append(("B", name, k, hybrid)) or hits(k))
    monkeypatch.setattr(pipeline, "answer", lambda model, prompt, question, h: paid(call(0.0002)))
    monkeypatch.setattr(pipeline, "judge", lambda test, context, text: (VERDICT, [paid(call(0.0001)), paid(call(0.0001))]))
    return seen


def test_s0_choices_are_the_baseline_with_each_stack_s_own_default_search():
    """Shared S0 settings; Stack A uses OpenAI's default search (T12: hybrid with the "auto" ranker), Stack B
    plain vector search (T40 revision 2026-10-29)."""
    a, b = first_run.s0_choices("A"), first_run.s0_choices("B")
    shared = ("fixed__c1024__o200", 2, False, "openai/gpt-4.1-nano", "default")
    for choices in (a, b):
        assert (choices.chunk_set_id, choices.top_k, choices.rerank, choices.answer_model,
                choices.prompt_name) == shared
    assert (a.hybrid, a.openai_ranking) == (True, {"ranker": "auto", "embedding_weight": 1.0, "text_weight": 1.0,
                                                   "score_threshold": 0.0})
    assert (b.hybrid, b.openai_ranking) == (False, None)


def test_batches_of_10_follow_the_round_robin_order_without_overlap():
    first, second = first_run.batch_questions(1), first_run.batch_questions(2)
    dev = [t for t in load_tests() if t.split == "dev"]
    assert first + second == round_robin(dev, 20)
    assert len(first) == len(second) == 10 and not {t.id for t in first} & {t.id for t in second}


def test_both_stacks_index_s0_once_and_answer_the_same_10_questions(world, capsys):
    first_run.main("both")
    conn = store.connect()
    done = [runs.get_run(conn, run_id) for run_id in (1, 2)]
    assert [(r.meta.stack, r.status) for r in done] == [("A", "done"), ("B", "done")]
    assert done[0].meta.test_ids == done[1].meta.test_ids and len(done[0].meta.test_ids) == 10
    assert world["created"] == ["rag-playground-dev-fixed__c1024__o200", "fixed__c1024__o200"]
    ranking = openai_vector_store.Ranking(**S0["search"]["A"]["openai_ranking"])
    assert world["searched"] == [("A", "vs_1", 2, ranking)] * 10 + [("B", "fixed__c1024__o200", 2, False)] * 10
    assert spend.total(conn) == pytest.approx(2 * 10 * 0.0004)
    out = capsys.readouterr().out
    assert out.count("recorded spend $0.0040; actual / estimate = ") == 2


def test_a_second_run_reuses_the_recorded_indexes(world):
    first_run.main("both")
    first_run.main("B")
    assert world["created"] == ["rag-playground-dev-fixed__c1024__o200", "fixed__c1024__o200"]
    assert len(runs.get_results(store.connect(), 3)) == 10
