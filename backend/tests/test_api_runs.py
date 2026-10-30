"""Step 6 checks of POST /api/runs: the dashboard's request starts an evaluation job with exactly its settings,
and a request that would be refused stores nothing. Same fakes as test_jobs.py (no network, no cost)."""

import pytest
from fastapi.testclient import TestClient
from test_jobs import wait_for_jobs, world  # noqa: F401  (world is a fixture)

from rag_playground import jobs, main
from rag_playground.datasets.schema import load_tests
from rag_playground.datasets.splits import round_robin
from rag_playground.rag import prompts, runs
from rag_playground.rag.runs import insert
from rag_playground.settings import settings
from rag_playground.stacks import openai_vector_store
from rag_playground.stacks.hits import Hit

DEV = [t for t in load_tests() if t.split == "dev"]
B = {"stack": "B", "chunking_method": "fixed", "chunk_size": 1024, "overlap": 200, "top_k": 2, "hybrid": False,
     "rerank": False, "answer_model": "openai/gpt-4.1-nano", "prompt_name": "default", "questions": "smoke"}
AUTO = {"ranker": "auto", "embedding_weight": 1.0, "text_weight": 1.0, "score_threshold": 0.0}
A = {**{k: v for k, v in B.items() if k != "hybrid"}, "stack": "A", "openai_ranking": AUTO}

client = TestClient(main.app)


@pytest.fixture
def stack_a(world, monkeypatch):
    """S0 also indexed on Stack A, whose search records the ranking it receives."""
    insert(world["conn"], "indexes", {"stack": "A", "chunk_set_id": "fixed__c1024__o200", "ref": "vs_1",
                                      "chunk_count": 1})
    searched = []
    monkeypatch.setattr(openai_vector_store, "search", lambda sid, question, k, ranking:
                        searched.append((sid, k, ranking)) or [Hit(f"c{i}", "d.md", 1.0, "text") for i in range(k)])
    return searched


def counts(conn):
    return tuple(conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("runs", "jobs"))


def start(body):
    response = client.post("/api/runs", json=body)
    wait_for_jobs()
    return response


def test_a_stack_b_smoke_run_starts_a_job_with_exactly_the_requested_settings(world):
    response = start(B)
    assert response.status_code == 202
    job = client.get(f"/api/jobs/{response.json()['job_id']}").json()
    assert (job["status"], job["message"]) == ("done", "20 of 20 questions")
    meta = runs.get_run(world["conn"], job["run_id"]).meta
    assert (meta.stack, meta.chunk_set_id, meta.top_k, meta.hybrid, meta.openai_ranking, meta.rerank_model,
            meta.answer_model, meta.prompt_name, meta.split) == (
        "B", "fixed__c1024__o200", 2, False, None, None, "openai/gpt-4.1-nano", "default", "dev")
    assert meta.test_ids == [t.id for t in round_robin(DEV, 20)]


@pytest.mark.parametrize("text_weight, hybrid", [(1.0, True), (0.0, False)])
def test_a_stack_a_run_searches_with_its_own_ranking_and_records_whether_keywords_take_part(
        world, stack_a, text_weight, hybrid):
    ranking = {**AUTO, "text_weight": text_weight}
    job = client.get(f"/api/jobs/{start({**A, 'openai_ranking': ranking}).json()['job_id']}").json()
    meta = runs.get_run(world["conn"], job["run_id"]).meta
    assert (meta.openai_ranking, meta.hybrid) == (ranking, hybrid)
    assert stack_a[0] == ("vs_1", 2, openai_vector_store.Ranking(**ranking)) and len(stack_a) == 20


@pytest.mark.parametrize("questions, split, count", [("dev", "dev", 192), ("heldout", "heldout", 48)])
def test_dev_and_heldout_runs_ask_every_question_of_their_split(world, monkeypatch, questions, split, count):
    """The run and its questions are stored before the job starts, so the job is not run here."""
    monkeypatch.setattr(settings, "budget_usd", 5.0)
    monkeypatch.setattr(jobs.executor, "submit", lambda *args: None)
    job = client.get(f"/api/jobs/{start({**B, 'questions': questions}).json()['job_id']}").json()
    meta = runs.get_run(world["conn"], job["run_id"]).meta
    assert (meta.split, len(meta.test_ids), job["status"]) == (split, count, "queued")
    assert meta.test_ids == [t.id for t in load_tests() if t.split == split]


@pytest.mark.parametrize("change", [
    {"rerank": None}, {"top_k": None}, {"questions": None}, {"chunking_method": None},  # every setting is required (T40)
    {"top_k": 0}, {"top_k": 9}, {"chunk_size": 5000}, {"overlap": 600},  # T35, T45 ranges
    {"answer_model": "openai/gpt-5"}, {"questions": "all"}, {"temperature": 0.5},  # unknown values, extra fields
    {"chunking_method": "semantic"}, {"chunking_method": 1},
    {"openai_ranking": AUTO},  # Stack B takes hybrid only
    {"hybrid": None},
], ids=["no-rerank", "no-k", "no-questions", "no-method", "k0", "k9", "size", "overlap", "model", "questions", "extra",
        "method", "method-int", "b-ranking", "b-no-hybrid"])
def test_an_invalid_request_is_rejected_and_stores_nothing(world, change):
    body = {k: v for k, v in {**B, **change}.items() if v is not None}
    assert client.post("/api/runs", json=body).status_code == 422
    assert counts(world["conn"]) == (0, 0)


@pytest.mark.parametrize("change", [{"openai_ranking": None}, {"hybrid": True},
                                    {"openai_ranking": {**AUTO, "ranker": "semantic"}},
                                    {"openai_ranking": {**AUTO, "text_weight": -1.0}}],
                         ids=["no-ranking", "hybrid", "ranker", "weight"])
def test_a_stack_a_request_takes_its_own_ranking_only(world, stack_a, change):
    body = {k: v for k, v in {**A, **change}.items() if v is not None}
    assert client.post("/api/runs", json=body).status_code == 422
    assert counts(world["conn"]) == (0, 0)


@pytest.mark.parametrize("change", [
    {"top_k": "2"}, {"top_k": 2.0}, {"top_k": True}, {"chunk_size": "1024"}, {"overlap": "200"},
    {"rerank": "yes"}, {"rerank": 0}, {"hybrid": 0}, {"hybrid": "false"},
], ids=["k-text", "k-float", "k-bool", "size-text", "overlap-text", "rerank-text", "rerank-int", "hybrid-int",
        "hybrid-text"])
def test_a_value_of_the_wrong_type_is_refused_not_converted(world, change):
    """D27: the stored settings come from exact values only."""
    assert client.post("/api/runs", json={**B, **change}).status_code == 422
    assert counts(world["conn"]) == (0, 0)


@pytest.mark.parametrize("field, value", [("embedding_weight", "1.0"), ("text_weight", True),
                                          ("score_threshold", "0")])
def test_a_ranking_value_of_the_wrong_type_is_refused_not_converted(world, stack_a, field, value):
    body = {**A, "openai_ranking": {**AUTO, field: value}}
    assert client.post("/api/runs", json=body).status_code == 422
    assert counts(world["conn"]) == (0, 0)


def test_whole_numbers_are_valid_weights(world, stack_a):
    """JSON has one number type: a dashboard sending 1 for a weight means 1.0, so strict types must accept it."""
    ranking = {**AUTO, "embedding_weight": 1, "text_weight": 0, "score_threshold": 0}
    job = client.get(f"/api/jobs/{start({**A, 'openai_ranking': ranking}).json()['job_id']}").json()
    assert runs.get_run(world["conn"], job["run_id"]).meta.openai_ranking == {
        **AUTO, "embedding_weight": 1.0, "text_weight": 0.0, "score_threshold": 0.0}


@pytest.mark.parametrize("change, status, detail", [
    ({"chunk_size": 512, "overlap": 0}, 404, "fixed__c512__o0 is not indexed on Stack B"),
    ({"prompt_name": "never-saved"}, 404, "Not found: never-saved"),
    ({"questions": "heldout", "prompt_name": "strict"}, 422, "'strict' has no finished dev run"),
])
def test_a_run_that_would_be_refused_is_refused_with_its_reason(world, change, status, detail):
    prompts.save(world["conn"], "strict", "Only answer from the context.")
    response = client.post("/api/runs", json={**B, **change})
    assert response.status_code == status
    assert detail in response.json()["detail"]
    assert counts(world["conn"]) == (0, 0)


ENRICHED = {**B, "chunking_method": "llm_enriched"}
ENRICHED_ID = "llm_enriched__c1024__o200"


def test_an_enriched_run_uses_the_enriched_chunk_set_with_every_other_setting_unchanged(world):
    insert(world["conn"], "indexes", {"stack": "B", "chunk_set_id": ENRICHED_ID, "ref": ENRICHED_ID, "chunk_count": 1})
    job = client.get(f"/api/jobs/{start(ENRICHED).json()['job_id']}").json()
    assert job["status"] == "done"
    meta = runs.get_run(world["conn"], job["run_id"]).meta
    assert (meta.chunk_set_id, meta.top_k, meta.hybrid) == (ENRICHED_ID, 2, False)


def test_a_fixed_run_never_uses_an_enriched_set(world):
    insert(world["conn"], "indexes", {"stack": "B", "chunk_set_id": ENRICHED_ID, "ref": ENRICHED_ID, "chunk_count": 1})
    job = client.get(f"/api/jobs/{start(B).json()['job_id']}").json()
    assert runs.get_run(world["conn"], job["run_id"]).meta.chunk_set_id == "fixed__c1024__o200"


def test_an_enriched_set_not_indexed_is_refused_with_its_name_even_if_the_fixed_set_is(world):
    """A set still being enriched has no index, so it is refused here too."""
    response = client.post("/api/runs", json=ENRICHED)
    assert response.status_code == 404
    assert f"{ENRICHED_ID} is not indexed on Stack B" in response.json()["detail"]
    assert counts(world["conn"]) == (0, 0)


def test_a_run_over_the_budget_is_refused_with_409(world, monkeypatch):
    monkeypatch.setattr(settings, "budget_usd", 0.0)
    response = client.post("/api/runs", json=B)
    assert response.status_code == 409 and "BUDGET_USD" in response.json()["detail"]
    assert counts(world["conn"]) == (0, 0)
