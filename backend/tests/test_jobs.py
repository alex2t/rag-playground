"""Step 6 checks of the background job runner (D07): a real worker thread, fake models and stacks, a fresh
database folder (no network, no cost)."""

import sqlite3
import threading

import pytest
from fastapi.testclient import TestClient

from rag_playground import jobs, main, store
from rag_playground.chunking.chunk_sets import Chunk
from rag_playground.datasets.schema import load_tests
from rag_playground.llm.models import ModelInfo
from rag_playground.llm.openrouter import ChatResult, paid
from rag_playground.rag import estimate, pipeline, prompts, runs, spend
from rag_playground.rag.runs import insert
from rag_playground.scoring.judging import Judgement
from rag_playground.settings import settings
from rag_playground.stacks import qdrant_store
from rag_playground.stacks.hits import Hit

DEV = [t for t in load_tests() if t.split == "dev"][:3]
CHOICES = pipeline.Choices(stack="B", chunk_set_id="fixed__c1024__o200", top_k=2, hybrid=False, openai_ranking=None,
                           rerank=False, answer_model="openai/gpt-4.1-nano", prompt_name="default")
CHUNK = Chunk(chunk_id="d.md#0", source="d.md", doc_type="d", index=0, text="x", tokens=100, start=0, end=1)
VERDICT = Judgement(refused=False, accuracy=5, completeness=5, relevance=5, faithfulness=5, feedback="ok",
                    faithfulness_feedback="ok")


def call(cost: float) -> ChatResult:
    return ChatResult(text="An answer.", model="m", canonical_slug="m-1", temperature_controlled=True,
                      prompt_tokens=1, completion_tokens=1, reasoning_tokens=0, cost_usd=cost)


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Fresh var/ folder with the S0 chunk set indexed on Stack B, budget $1, a fresh one-thread executor, and
    fake models. `state["gate"]` can hold the answer model back; `state["threads"]` records where it ran."""
    state = {"threads": [], "gate": None, "fail": None}
    monkeypatch.setattr(settings, "var_dir", tmp_path)
    monkeypatch.setattr(settings, "budget_usd", 1.0)
    monkeypatch.setattr(jobs, "executor", jobs.new_executor())
    info = lambda m: ModelInfo(m, f"{m}-1", frozenset({"temperature"}), 1e-6, 1e-6)
    monkeypatch.setattr(pipeline, "model_info", info)
    monkeypatch.setattr(estimate, "model_info", info)
    monkeypatch.setattr(pipeline, "load_chunk_set", lambda set_id: [CHUNK])
    monkeypatch.setattr(qdrant_store, "client", lambda: "qdrant")
    monkeypatch.setattr(qdrant_store, "search", lambda q, name, question, k, hybrid:
                        [Hit(f"c{i}", "d.md", 1.0, "text") for i in range(k)])

    def answer(model, prompt, question, hits):
        state["threads"].append(threading.current_thread().name)
        if state["gate"] is not None and len(state["threads"]) == 2:
            state["gate"].wait(5)
        if state["fail"] == len(state["threads"]):
            raise RuntimeError("rate limited")
        return paid(call(0.001))

    monkeypatch.setattr(pipeline, "answer", answer)
    monkeypatch.setattr(pipeline, "judge", lambda test, context, text: (VERDICT, [paid(call(0.0005))]))
    conn = store.connect()
    prompts.ensure_default(conn)
    insert(conn, "indexes", {"stack": "B", "chunk_set_id": CHOICES.chunk_set_id, "ref": CHOICES.chunk_set_id,
                             "chunk_count": 1})
    state["conn"] = conn
    yield state
    jobs.executor.shutdown(wait=True)
    conn.close()


def wait_for_jobs():
    jobs.executor.shutdown(wait=True)


def counts(conn):
    return tuple(conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("runs", "jobs"))


def test_a_job_runs_its_run_in_the_worker_thread_and_records_every_paid_call(world):
    conn = world["conn"]
    job_id = jobs.submit_evaluation(conn, CHOICES, DEV)
    wait_for_jobs()
    job = jobs.get_job(conn, job_id)
    assert (job.status, job.progress, job.message, job.error) == ("done", 1.0, "3 of 3 questions", None)
    assert runs.get_run(conn, job.run_id).status == "done"
    assert all(name.startswith("job") for name in world["threads"]) and len(world["threads"]) == 3
    assert threading.current_thread().name not in world["threads"]
    assert spend.total(conn, job.run_id) == pytest.approx(3 * 0.0015)
    assert conn.execute("SELECT count(*) FROM spend WHERE run_id = ?", (job.run_id,)).fetchone()[0] == 6


def test_progress_can_be_read_while_the_job_runs(world):
    """The answer model is held back on question 2, so question 1 is stored and the job is still running."""
    conn = world["conn"]
    world["gate"] = threading.Event()
    job_id = jobs.submit_evaluation(conn, CHOICES, DEV)
    for _ in range(200):
        if len(world["threads"]) == 2:
            break
        threading.Event().wait(0.01)
    job = jobs.get_job(conn, job_id)
    assert (job.status, job.message) == ("running", "1 of 3 questions")
    assert job.progress == pytest.approx(1 / 3)
    world["gate"].set()
    wait_for_jobs()
    assert jobs.get_job(conn, job_id).status == "done"


def test_one_job_runs_at_a_time_and_the_next_waits_queued(world):
    conn = world["conn"]
    world["gate"] = threading.Event()
    first = jobs.submit_evaluation(conn, CHOICES, DEV)
    second = jobs.submit_evaluation(conn, CHOICES, DEV)
    for _ in range(200):
        if len(world["threads"]) == 2:
            break
        threading.Event().wait(0.01)
    assert (jobs.get_job(conn, first).status, jobs.get_job(conn, second).status) == ("running", "queued")
    world["gate"].set()
    wait_for_jobs()
    assert (jobs.get_job(conn, first).status, jobs.get_job(conn, second).status) == ("done", "done")


def test_a_failing_question_fails_the_job_and_its_run_with_the_error(world):
    conn = world["conn"]
    world["fail"] = 2
    job_id = jobs.submit_evaluation(conn, CHOICES, DEV)
    wait_for_jobs()
    job = jobs.get_job(conn, job_id)
    assert (job.status, job.error, job.message) == ("failed", "RuntimeError: rate limited", "1 of 3 questions")
    assert runs.get_run(conn, job.run_id).error == "RuntimeError: rate limited"


def test_a_failure_before_the_first_question_still_finishes_the_run(world, monkeypatch):
    """Otherwise the run would stay "running" for ever."""
    conn = world["conn"]
    monkeypatch.setattr(jobs.indexes, "retriever", lambda conn, meta: (_ for _ in ()).throw(KeyError("gone")))
    job_id = jobs.submit_evaluation(conn, CHOICES, DEV)
    wait_for_jobs()
    job = jobs.get_job(conn, job_id)
    assert (job.status, job.error) == ("failed", "KeyError: 'gone'")
    assert (runs.get_run(conn, job.run_id).status, runs.get_run(conn, job.run_id).error) == ("failed", "KeyError: 'gone'")


def test_a_chunk_set_not_indexed_is_refused_before_any_run_or_job(world):
    conn = world["conn"]
    with pytest.raises(KeyError, match="not indexed on Stack A"):
        jobs.submit_evaluation(conn, pipeline.Choices(**{**CHOICES.__dict__, "stack": "A", "openai_ranking": {
            "ranker": "auto", "embedding_weight": 1.0, "text_weight": 1.0, "score_threshold": 0.0}}), DEV)
    assert counts(conn) == (0, 0)


def test_a_run_over_the_budget_is_refused_before_any_run_or_job(world, monkeypatch):
    conn = world["conn"]
    monkeypatch.setattr(settings, "budget_usd", 0.0)
    with pytest.raises(pipeline.BudgetExceeded):
        jobs.submit_evaluation(conn, CHOICES, DEV)
    assert counts(conn) == (0, 0)


def test_unknown_job_raises_key_error(world):
    with pytest.raises(KeyError):
        jobs.get_job(world["conn"], 999)


def unfinished(conn, status):
    """A job and its run as a previous process would have left them."""
    run_id = pipeline.start_run(conn, CHOICES, DEV)
    job_id = insert(conn, "jobs", {"kind": "evaluate", "run_id": run_id})
    if status == "running":
        jobs.set_status(conn, job_id, "running")
    return job_id, run_id


def test_restart_recovery_fails_unfinished_jobs_and_their_runs_only(world):
    conn = world["conn"]
    left = [unfinished(conn, "queued"), unfinished(conn, "running")]
    done_job = jobs.submit_evaluation(conn, CHOICES, DEV)
    wait_for_jobs()
    assert jobs.recover_interrupted(conn) == 2
    for job_id, run_id in left:
        assert (jobs.get_job(conn, job_id).status, jobs.get_job(conn, job_id).error) == ("failed", jobs.INTERRUPTED)
        assert (runs.get_run(conn, run_id).status, runs.get_run(conn, run_id).error) == ("failed", jobs.INTERRUPTED)
    assert jobs.get_job(conn, done_job).status == "done"
    assert jobs.recover_interrupted(conn) == 0


@pytest.mark.parametrize("before, after", [("queued", "done"), ("done", "running"), ("failed", "running"),
                                           ("running", "queued")])
def test_a_job_moves_forward_only(world, before, after):
    conn = world["conn"]
    job_id, _ = unfinished(conn, "running" if before != "queued" else "queued")
    if before in ("done", "failed"):
        jobs.set_status(conn, job_id, before, "boom" if before == "failed" else None)
    with pytest.raises(sqlite3.IntegrityError, match="forward only"):
        jobs.set_status(conn, job_id, after, "boom" if after == "failed" else None)


@pytest.mark.parametrize("status, error", [("failed", None), ("done", "boom"), ("running", "boom")])
def test_an_error_goes_with_failed_and_only_with_failed(world, status, error):
    conn = world["conn"]
    job_id, _ = unfinished(conn, "running" if status != "running" else "queued")
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        jobs.set_status(conn, job_id, status, error)


def test_the_api_reports_a_job_and_404_for_an_unknown_one(world):
    conn = world["conn"]
    job_id = jobs.submit_evaluation(conn, CHOICES, DEV)
    wait_for_jobs()
    client = TestClient(main.app)
    body = client.get(f"/api/jobs/{job_id}").json()
    assert body == {"id": job_id, "kind": "evaluate", "status": "done", "run_id": 1, "progress": 1.0,
                    "message": "3 of 3 questions", "error": None}
    assert client.get("/api/jobs/999").status_code == 404


def test_the_app_marks_unfinished_jobs_failed_when_it_starts(world):
    job_id, _ = unfinished(world["conn"], "running")
    with TestClient(main.app) as client:
        assert client.get(f"/api/jobs/{job_id}").json()["error"] == jobs.INTERRUPTED
