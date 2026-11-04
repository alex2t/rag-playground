"""D30: what the Ops page shows, from hand-made jobs, runs, results and spend with exact expected numbers."""

import json
from dataclasses import asdict, replace

import pytest
from fastapi.testclient import TestClient

from rag_playground import jobs, main, store
from rag_playground.rag import ops, prompts, runs
from rag_playground.rag.runs import insert
from rag_playground.settings import STACK_A_SEARCH_USD, settings
from test_runs import STACK_A, STACK_B, result

@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "var_dir", tmp_path)
    monkeypatch.setattr(settings, "budget_usd", 5.0)
    connection = store.connect()
    prompts.ensure_default(connection)
    yield connection
    connection.close()


def days_ago(conn, days: float) -> str:
    return conn.execute(f"SELECT datetime('now', '-{days} days')").fetchone()[0]


def run_with(conn, meta, seconds: list[float], days: float = 1) -> int:
    """A run started `days` ago, with one result per time in `seconds`."""
    meta = replace(meta, test_ids=[f"q{i}" for i in range(len(seconds))])
    run_id = insert(conn, "runs", asdict(meta) | {"openai_ranking": meta.openai_ranking and json.dumps(meta.openai_ranking),
                                                  "test_ids": json.dumps(meta.test_ids), "created_at": days_ago(conn, days)})
    for i, latency in enumerate(seconds):
        runs.add_result(conn, run_id, replace(result(f"q{i}"), latency_s=latency, cost_usd=0.0))
    return run_id


def job(conn, kind: str, status: str, error: str | None = None, days: float = 1) -> int:
    shape = {"evaluate": {}, "ladder_step": {"stack": "B", "step": "S1", "runs_total": 1},
             "build": {"stack": "A", "chunk_set_id": "fixed__c800__o100"}, "sweep": {"stack": "B", "runs_total": 2}}[kind]
    if kind == "evaluate":
        shape = {"run_id": run_with(conn, STACK_B, [1.0], days)}
    finished = days_ago(conn, days) if status in ("done", "failed") else None
    return insert(conn, "jobs", {"kind": kind, **shape, "status": status, "error": error, "finished_at": finished,
                                 "created_at": days_ago(conn, days)})


def spend_row(conn, cost: float, run_id: int | None) -> None:
    insert(conn, "spend", {"run_id": run_id, "model": "m", "prompt_tokens": 1, "completion_tokens": 1, "reasoning_tokens": 0, "cost_usd": cost})


def test_spend_is_counted_as_the_budget_guard_counts_it_and_split_into_runs_and_the_rest(conn):
    run_id = run_with(conn, STACK_A, [1.0, 2.0])
    spend_row(conn, 0.3, run_id)
    spend_row(conn, 0.2, None)
    shown = ops.budget(conn)
    spent = 0.5 + 2 * STACK_A_SEARCH_USD
    assert shown == pytest.approx({"budget_usd": 5.0, "spent_usd": spent, "left_usd": 5.0 - spent,
                                   "in_runs_usd": 0.3 + 2 * STACK_A_SEARCH_USD, "outside_runs_usd": 0.2})


@pytest.mark.parametrize("error, why", [
    ("BudgetExceeded: Budget reached: $5.0000 spent of BUDGET_USD $5.00", "budget"),
    ("BudgetExceeded: Enrichment is estimated at $0.0600, but only $0.0100 of the budget is left", "budget"),
    (jobs.INTERRUPTED, "restart"),
    ("RuntimeError: rate limited", "fault"),
    ("ResponseHandlingException: connection refused", "fault"),
    (f"{jobs.INTERRUPTED} twice", "fault"),
    ("budgetexceeded: lower case is no budget stop", "fault"),
    ("ValueError: the Budget page has no data", "fault"),
])
def test_a_failure_is_a_budget_stop_a_restart_or_a_fault(error, why):
    assert ops.cause(error) == why


def test_the_error_rate_is_faults_over_jobs_finished_in_the_window(conn):
    job(conn, "evaluate", "done")
    fault = job(conn, "build", "failed", "RuntimeError: Qdrant is not running")
    stop = job(conn, "sweep", "failed", "BudgetExceeded: Budget reached: x")
    restart = job(conn, "ladder_step", "failed", jobs.INTERRUPTED, days=2)
    job(conn, "ladder_step", "queued", days=0.5)
    job(conn, "build", "failed", "RuntimeError: old", days=8)
    shown = ops.failures(conn)
    assert {k: shown[k] for k in ("finished", "active", "faults", "budget_stops", "restarts", "error_rate")} == {
        "finished": 4, "active": 1, "faults": 1, "budget_stops": 1, "restarts": 1, "error_rate": 0.25}
    assert [(f["id"], f["kind"], f["cause"]) for f in shown["failed"]] == [
        (restart, "ladder_step", "restart"), (stop, "sweep", "budget"), (fault, "build", "fault")]
    assert shown["failed"][2]["error"] == "RuntimeError: Qdrant is not running"


def test_the_window_counts_when_a_job_finished_not_when_it_was_created(conn):
    """D30: jobs finished in the window. A job created before it but finished inside counts; one still waiting counts
    as active however old it is; one created and finished before the window is left out."""
    late = insert(conn, "jobs", {"kind": "build", "stack": "A", "chunk_set_id": "fixed__c800__o100", "status": "failed",
                                 "error": "RuntimeError: late", "created_at": days_ago(conn, 8), "finished_at": days_ago(conn, 6)})
    insert(conn, "jobs", {"kind": "sweep", "stack": "B", "runs_total": 2, "status": "queued", "created_at": days_ago(conn, 9)})
    job(conn, "build", "failed", "RuntimeError: old", days=8)
    shown = ops.failures(conn)
    assert (shown["finished"], shown["active"], shown["faults"]) == (1, 1, 1)
    assert [f["id"] for f in shown["failed"]] == [late]


def test_with_no_finished_job_in_the_window_there_is_no_rate(conn):
    job(conn, "sweep", "running")
    job(conn, "build", "failed", "RuntimeError: old", days=8)
    shown = ops.failures(conn)
    assert (shown["finished"], shown["active"], shown["error_rate"], shown["failed"]) == (0, 1, None, [])


def test_answer_times_are_p50_and_p95_per_stack_over_runs_started_in_the_window(conn):
    run_with(conn, STACK_A, [float(s) for s in range(1, 21)])
    run_with(conn, STACK_B, [9.0])
    run_with(conn, STACK_B, [100.0, 100.0], days=8)
    assert ops.latency(conn) == [{"stack": "A", "questions": 20, "p50_s": pytest.approx(10.5), "p95_s": pytest.approx(19.05)},
                                 {"stack": "B", "questions": 1, "p50_s": 9.0, "p95_s": 9.0}]


def test_two_questions_interpolate_and_a_stack_with_none_is_left_out(conn):
    run_with(conn, STACK_B, [2.0, 4.0])
    assert ops.latency(conn) == [{"stack": "B", "questions": 2, "p50_s": pytest.approx(3.0), "p95_s": pytest.approx(3.9)}]


def test_the_route_adds_the_version_and_qdrant(conn, monkeypatch):
    monkeypatch.setattr(settings, "app_version", "abc1234")
    monkeypatch.setattr(main, "qdrant_status", lambda: "error: ConnectError")
    body = TestClient(main.app).get("/api/ops").json()
    assert (body["version"], body["qdrant"], body["window_days"]) == ("abc1234", "error: ConnectError", 7)
    assert body["jobs"]["error_rate"] is None and body["latency"] == []
