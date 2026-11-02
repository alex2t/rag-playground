"""D29: building a chunk set on a stack from the Build page. Real splitting of the knowledge base, a real worker thread
and database; enrichment, OpenAI and Qdrant are faked (no network, no cost)."""

import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from rag_playground import jobs, main, store
from rag_playground.chunking.chunk_sets import load
from rag_playground.rag import builds, enrich_run, prompts
from rag_playground.rag.pipeline import Choices
from rag_playground.rag.enrich_run import enrich_set as real_enrich_set
from rag_playground.rag.runs import insert
from rag_playground.settings import settings
from rag_playground.stacks import indexes

FIXED = {"chunking_method": "fixed", "chunk_size": 800, "overlap": 100}
ENRICHED = {**FIXED, "chunking_method": "llm_enriched"}


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Fresh var/ folder, $1 budget, one worker thread. `state` records what the fakes were asked to do."""
    state = SimpleNamespace(built=[], enriched=[], enrich_cost=0.0, gate=None, fail=None)
    monkeypatch.setattr(settings, "var_dir", tmp_path)
    monkeypatch.setattr(settings, "budget_usd", 1.0)
    monkeypatch.setattr(jobs, "executor", jobs.new_executor())
    monkeypatch.setattr(enrich_run, "remaining_cost", lambda base_id: state.enrich_cost)
    monkeypatch.setattr(enrich_run, "enrich_set", lambda conn, base_id: state.enriched.append(base_id))
    monkeypatch.setattr(indexes.enrichment, "load_complete", lambda set_id: load(set_id.replace("llm_enriched", "fixed")))

    def fake_build(stack):
        def build(set_id, chunks):
            if state.gate is not None:
                state.gate.wait(5)
            if state.fail:
                raise RuntimeError(state.fail)
            state.built.append((stack, set_id, len(chunks)))
            return f"ref-{stack}-{set_id}"
        return build

    monkeypatch.setattr(indexes, "build_stack_a", fake_build("A"))
    monkeypatch.setattr(indexes, "build_stack_b", fake_build("B"))
    state.conn = store.connect()
    state.client = TestClient(main.app)
    yield state
    if state.gate is not None:
        state.gate.set()
    jobs.executor.shutdown(wait=True)
    state.conn.close()


def finish() -> None:
    """Wait for the queued jobs."""
    jobs.executor.submit(lambda: None).result(30)


def start(world, stack: str, body: dict = FIXED):
    return world.client.post("/api/builds", json={**body, "stack": stack})


def job_count(world) -> int:
    return world.conn.execute("SELECT count(*) FROM jobs").fetchone()[0]


def test_an_estimate_names_the_set_counts_its_real_chunks_and_saves_only_the_free_split(world):
    reply = world.client.post("/api/builds/estimate", json=FIXED)
    assert reply.status_code == 200
    assert reply.json() == {"chunk_set_id": "fixed__c800__o100", "chunks": len(load("fixed__c800__o100")),
                            "enrichment_usd": 0.0, "built": [], "budget_left_usd": 1.0}
    assert (world.built, world.enriched, job_count(world)) == ([], [], 0)


def test_an_enriched_estimate_prices_what_is_left_of_its_base_set_and_names_the_enriched_set(world, monkeypatch):
    asked = []
    monkeypatch.setattr(enrich_run, "remaining_cost", lambda base_id: asked.append(base_id) or 0.123)
    reply = world.client.post("/api/builds/estimate", json=ENRICHED).json()
    assert (reply["chunk_set_id"], reply["enrichment_usd"], asked) == ("llm_enriched__c800__o100", 0.123, ["fixed__c800__o100"])
    assert world.enriched == []


def test_an_estimate_says_which_stacks_have_the_set_already(world):
    insert(world.conn, "indexes", {"stack": "B", "chunk_set_id": "fixed__c800__o100", "ref": "x", "chunk_count": 1})
    assert world.client.post("/api/builds/estimate", json=FIXED).json()["built"] == ["B"]
    assert world.client.post("/api/builds/estimate", json=ENRICHED).json()["built"] == []


def test_a_build_indexes_every_chunk_on_its_own_stack_only_and_its_job_ends_done(world):
    reply = start(world, "B")
    assert reply.status_code == 202
    finish()
    chunks = len(load("fixed__c800__o100"))
    assert world.built == [("B", "fixed__c800__o100", chunks)]
    assert indexes.lookup(world.conn, "B", "fixed__c800__o100") == "ref-B-fixed__c800__o100"
    assert indexes.lookup(world.conn, "A", "fixed__c800__o100") is None
    job = world.client.get(f"/api/jobs/{reply.json()['job_id']}").json()
    assert job | {"id": 0} == {"id": 0, "kind": "build", "status": "done", "run_id": None, "progress": 1.0,
                               "message": "fixed__c800__o100 on Stack B: built", "error": None}


def test_an_enriched_build_is_enriched_from_its_base_set_before_it_is_indexed(world, monkeypatch):
    order = []
    monkeypatch.setattr(enrich_run, "enrich_set", lambda conn, base_id: order.append(("enrich", base_id)))
    real = indexes.build
    monkeypatch.setattr(indexes, "build", lambda conn, stack, set_id: order.append(("index", set_id)) or real(conn, stack, set_id))
    start(world, "A", ENRICHED)
    finish()
    assert order == [("enrich", "fixed__c800__o100"), ("index", "llm_enriched__c800__o100")]
    assert indexes.lookup(world.conn, "A", "llm_enriched__c800__o100") is not None


def test_a_fixed_build_is_never_enriched(world):
    start(world, "A")
    finish()
    assert world.enriched == []


def test_a_set_built_already_is_refused_and_nothing_is_stored(world):
    start(world, "B")
    finish()
    before = job_count(world)
    reply = start(world, "B")
    assert (reply.status_code, reply.json()["detail"]) == (409, "fixed__c800__o100 is already built on Stack B")
    assert job_count(world) == before


def test_a_build_waiting_or_running_is_not_queued_twice_but_the_other_stack_may_build_the_same_set(world):
    world.gate = threading.Event()
    assert start(world, "B").status_code == 202
    second = start(world, "B")
    assert (second.status_code, second.json()["detail"]) == (409, "fixed__c800__o100 is already being built on Stack B")
    assert start(world, "A").status_code == 202
    world.gate.set()
    finish()
    assert sorted(stack for stack, _, _ in world.built) == ["A", "B"]


def test_an_enrichment_over_the_budget_is_refused_before_any_job_or_payment(world):
    world.enrich_cost = 1.5
    reply = start(world, "B", ENRICHED)
    assert (reply.status_code, reply.json()["detail"]) == (409, "Enrichment is estimated at $1.5000, but only $1.0000 of the budget is left")
    assert (job_count(world), world.enriched) == (0, [])


def test_an_enrichment_exactly_at_the_budget_is_accepted(world):
    world.enrich_cost = 1.0
    assert start(world, "B", ENRICHED).status_code == 202


def test_a_fixed_build_costs_nothing_and_is_accepted_with_no_budget_left(world, monkeypatch):
    monkeypatch.setattr(settings, "budget_usd", 0.0)
    world.enrich_cost = 5.0
    assert start(world, "B").status_code == 202


def overspend(world) -> None:
    """Spend past the $1 budget, as on the dev database ($6.96 spent of $5)."""
    insert(world.conn, "spend", {"model": "m", "prompt_tokens": 1, "completion_tokens": 1, "reasoning_tokens": 0, "cost_usd": 2.0})


def test_a_free_build_is_accepted_and_runs_when_spend_has_passed_the_budget(world):
    overspend(world)
    assert world.client.post("/api/builds/estimate", json=FIXED).json()["budget_left_usd"] == -1.0
    assert start(world, "B").status_code == 202
    finish()
    assert indexes.lookup(world.conn, "B", "fixed__c800__o100") is not None


def test_a_set_already_enriched_is_indexed_on_another_stack_when_spend_has_passed_the_budget(world, monkeypatch):
    """The real enrich_set, with nothing left to pay: no refusal, no paid call."""
    paid = []
    monkeypatch.setattr(enrich_run, "enrich_set", real_enrich_set)
    monkeypatch.setattr(enrich_run.enrichment, "load_or_enrich", lambda base_id, before_call: paid.append(base_id) or [])
    overspend(world)
    assert start(world, "A", ENRICHED).status_code == 202
    finish()
    assert indexes.lookup(world.conn, "A", "llm_enriched__c800__o100") is not None
    assert paid == ["fixed__c800__o100"]


def test_an_enrichment_with_something_left_to_pay_is_refused_when_spend_has_passed_the_budget(world, monkeypatch):
    monkeypatch.setattr(enrich_run, "enrich_set", real_enrich_set)
    overspend(world)
    world.enrich_cost = 0.0001
    assert start(world, "B", ENRICHED).status_code == 409
    with pytest.raises(enrich_run.pipeline.BudgetExceeded):
        real_enrich_set(world.conn, "fixed__c800__o100")


def test_a_failed_build_says_why_records_no_index_and_can_be_tried_again(world):
    world.fail = "Qdrant is not running"
    job_id = start(world, "B").json()["job_id"]
    finish()
    job = world.client.get(f"/api/jobs/{job_id}").json()
    assert (job["status"], job["error"], job["progress"]) == ("failed", "RuntimeError: Qdrant is not running", 0.0)
    assert indexes.lookup(world.conn, "B", "fixed__c800__o100") is None
    world.fail = None
    start(world, "B")
    finish()
    assert indexes.lookup(world.conn, "B", "fixed__c800__o100") is not None


def test_a_queued_build_says_it_waits_and_a_running_one_says_it_builds(world):
    world.gate = threading.Event()
    first = start(world, "B").json()["job_id"]
    second = start(world, "A").json()["job_id"]
    status = lambda job_id: world.client.get(f"/api/jobs/{job_id}").json()
    for _ in range(100):
        if status(first)["status"] == "running":
            break
        threading.Event().wait(0.05)
    assert status(first)["message"] == "fixed__c800__o100 on Stack B: building"
    assert status(second)["message"] == "fixed__c800__o100 on Stack A: waiting for the job before it"
    world.gate.set()


def test_the_list_shows_what_is_built_with_its_settings_and_every_build_job_newest_first(world):
    world.fail = "boom"
    start(world, "A")
    finish()
    world.fail = None
    start(world, "B", ENRICHED)
    finish()
    listing = world.client.get("/api/builds").json()
    assert [(row["stack"], row["chunk_set_id"], row["chunking_method"], row["chunk_size"], row["overlap"])
            for row in listing["built"]] == [("B", "llm_enriched__c800__o100", "llm_enriched", 800, 100)]
    assert listing["built"][0]["chunk_count"] == len(load("fixed__c800__o100"))
    assert [(job["stack"], job["chunk_set_id"], job["status"], job["error"]) for job in listing["jobs"]] == [
        ("B", "llm_enriched__c800__o100", "done", None), ("A", "fixed__c800__o100", "failed", "RuntimeError: boom")]
    assert [(job["chunking_method"], job["chunk_size"], job["overlap"]) for job in listing["jobs"]] == [
        ("llm_enriched", 800, 100), ("fixed", 800, 100)]


def test_built_sets_are_listed_newest_first(world):
    for stack, set_id, when in [("A", "fixed__c400__o0", "2026-10-30 10:00:00"), ("B", "fixed__c800__o0", "2026-10-31 10:00:00")]:
        insert(world.conn, "indexes", {"stack": stack, "chunk_set_id": set_id, "ref": "r", "chunk_count": 3, "created_at": when})
    assert [row["chunk_set_id"] for row in builds.built(world.conn)] == ["fixed__c800__o0", "fixed__c400__o0"]


def test_a_build_left_unfinished_by_a_restart_is_marked_failed(world):
    job_id = insert(world.conn, "jobs", {"kind": "build", "stack": "A", "chunk_set_id": "fixed__c800__o100"})
    assert jobs.recover_interrupted(world.conn) == 1
    assert jobs.get_job(world.conn, job_id).error == jobs.INTERRUPTED


@pytest.mark.parametrize("body", [
    {**FIXED, "overlap": 401},
    {**FIXED, "chunk_size": 63},
    {**FIXED, "chunk_size": 2049, "overlap": 0},
    {**FIXED, "chunk_size": "800"},
    {**FIXED, "chunking_method": "semantic"},
    {**FIXED, "extra": 1},
    {"chunking_method": "fixed", "chunk_size": 800},
])
def test_invalid_settings_are_refused_by_both_routes(world, body):
    assert world.client.post("/api/builds/estimate", json=body).status_code == 422
    assert world.client.post("/api/builds", json={**body, "stack": "B"}).status_code == 422
    assert job_count(world) == 0


@pytest.mark.parametrize("stack", ["C", None, "a"])
def test_a_build_names_one_real_stack(world, stack):
    body = {**FIXED, "stack": stack} if stack else FIXED
    assert world.client.post("/api/builds", json=body).status_code == 422


def test_the_limits_are_accepted_at_their_exact_edges(world):
    assert world.client.post("/api/builds/estimate", json={**FIXED, "chunk_size": 64, "overlap": 32}).status_code == 200
    assert world.client.post("/api/builds/estimate", json={**FIXED, "chunk_size": 2048, "overlap": 1024}).status_code == 200


def test_a_run_is_priced_on_the_original_split_of_its_own_chunk_set_and_its_own_settings(world, monkeypatch):
    """An enriched set is priced on its base split: answers read the original chunks (T47)."""
    asked = []
    monkeypatch.setattr(builds, "load_or_build", lambda size, overlap: asked.append((size, overlap)) or ["chunks"])
    monkeypatch.setattr(builds.pricing, "run_cost", lambda *args: asked.append(args) or 0.3)
    prompts.ensure_default(world.conn)
    choices = Choices(stack="A", chunk_set_id="llm_enriched__c800__o100", top_k=6, hybrid=False, openai_ranking={},
                      rerank=True, answer_model="openai/gpt-4.1-nano", prompt_name="default")
    assert builds.run_cost(world.conn, choices, ["t1", "t2"]) == 0.3
    tests, prompt, model, top_k, rerank, chunks, stack = asked[1]
    assert asked[0] == (800, 100)
    assert (tests, prompt.name, model, top_k, rerank, chunks, stack) == (["t1", "t2"], "default", "openai/gpt-4.1-nano", 6, True, ["chunks"], "A")
