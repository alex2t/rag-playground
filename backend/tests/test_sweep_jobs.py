"""T58: running a sweep. The ladder tests' world: a real worker thread and database, fake models, chunks and stacks, and
3 dev questions per run (no network, no cost)."""

import json
import threading

import pytest
from fastapi.testclient import TestClient

from rag_playground import jobs, main
from rag_playground.rag import pipeline, prompts, runs, sweeps
from rag_playground.settings import settings
from rag_playground.sweep_requests import SweepRequest
from test_ladder_step import DEV, finish, world  # noqa: F401  (world is a fixture)

BASE = {"stack": "B", "chunking_method": "fixed", "chunk_size": 1024, "overlap": 200, "top_k": 2, "hybrid": False,
        "rerank": False, "answer_model": "openai/gpt-4.1-nano", "prompt_name": "default"}


@pytest.fixture
def sweep_world(world, monkeypatch):
    monkeypatch.setattr(sweeps, "dev_tests", lambda: DEV)
    prompts.ensure_default(world.conn)
    world.client = TestClient(main.app)
    return world


def sweep(variable: str, values: list, base: dict = BASE) -> SweepRequest:
    return SweepRequest.model_validate({"base": base, "variable": variable, "values": values})


def made(world) -> list[runs.Run]:
    return [runs.get_run(world.conn, row["id"]) for row in world.conn.execute("SELECT id FROM runs ORDER BY id")]


def test_a_sweep_runs_each_missing_value_in_order_on_all_its_questions(sweep_world):
    job_id = jobs.submit_sweep(sweep_world.conn, sweep("top_k", [4, 6]))
    finish(sweep_world)
    job = jobs.get_job(sweep_world.conn, job_id)
    assert (job.kind, job.status, job.progress, job.error) == ("sweep", "done", 1.0, None)
    assert [(r.meta.top_k, r.status, sorted(r.meta.test_ids)) for r in made(sweep_world)] == [
        (k, "done", sorted(t.id for t in DEV)) for k in (2, 4, 6)]


def test_a_second_sweep_pays_only_for_values_not_run_yet(sweep_world):
    jobs.submit_sweep(sweep_world.conn, sweep("top_k", [4]))
    finish(sweep_world)
    job_id = jobs.submit_sweep(sweep_world.conn, sweep("top_k", [4, 8]))
    finish(sweep_world)
    assert [r.meta.top_k for r in made(sweep_world)] == [2, 4, 8]
    assert sweep_world.conn.execute("SELECT runs_total FROM jobs WHERE id = ?", (job_id,)).fetchone()[0] == 1


def test_missing_chunks_are_built_before_their_value_runs(sweep_world):
    jobs.submit_sweep(sweep_world.conn, sweep("overlap", [0]))
    finish(sweep_world)
    assert sweep_world.built == [("B", "fixed__c1024__o200"), ("B", "fixed__c1024__o0")]
    assert [r.meta.chunk_set_id for r in made(sweep_world)] == ["fixed__c1024__o200", "fixed__c1024__o0"]


def test_a_sweep_with_nothing_left_to_run_is_refused_and_stores_nothing(sweep_world):
    jobs.submit_sweep(sweep_world.conn, sweep("top_k", [4]))
    finish(sweep_world)
    before = sweep_world.conn.execute("SELECT count(*) FROM jobs").fetchone()[0]
    reply = sweep_world.client.post("/api/sweeps", json={"base": BASE, "variable": "top_k", "values": [4]})
    assert (reply.status_code, reply.json()["detail"]) == (409, "Every value has a run already: nothing to run")
    assert sweep_world.conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == before


def test_one_sweep_at_a_time_per_stack_while_the_other_stack_may_sweep(sweep_world, monkeypatch):
    monkeypatch.setattr(jobs.indexes.openai_vector_store, "search", lambda *a, **k: [])
    sweep_world.gate = threading.Event()
    assert sweep_world.client.post("/api/sweeps", json={"base": BASE, "variable": "top_k", "values": [4]}).status_code == 202
    second = sweep_world.client.post("/api/sweeps", json={"base": BASE, "variable": "top_k", "values": [6]})
    assert (second.status_code, second.json()["detail"]) == (409, "A sweep is already running on Stack B")
    base_a = {**{k: v for k, v in BASE.items() if k != "hybrid"}, "stack": "A",
              "openai_ranking": {"ranker": "auto", "embedding_weight": 1.0, "text_weight": 1.0, "score_threshold": 0.0}}
    assert sweep_world.client.post("/api/sweeps", json={"base": base_a, "variable": "top_k", "values": [4]}).status_code == 202
    sweep_world.gate.set()
    finish(sweep_world)


def test_a_sweep_over_the_budget_counts_its_enrichment_and_stores_nothing(sweep_world):
    sweep_world.enrich_cost = 2.0
    reply = sweep_world.client.post("/api/sweeps", json={"base": BASE, "variable": "chunking_method", "values": ["llm_enriched"]})
    assert reply.status_code == 409 and reply.json()["detail"].startswith("The sweep is estimated at $2.")
    assert sweep_world.conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
    assert sweep_world.enriched == []


def test_a_failure_stops_the_rest_keeps_finished_runs_and_closes_the_failed_one(sweep_world):
    sweep_world.fail_at = len(DEV) + 1  # first question of the second value
    job_id = jobs.submit_sweep(sweep_world.conn, sweep("top_k", [4, 6]))
    finish(sweep_world)
    job = jobs.get_job(sweep_world.conn, job_id)
    assert job.status == "failed" and "rate limited" in job.error
    assert [(r.meta.top_k, r.status) for r in made(sweep_world)] == [(2, "done"), (4, "failed")]


def test_a_running_sweep_reports_its_run_and_questions_and_the_latest_route_shows_it(sweep_world):
    sweep_world.gate = threading.Event()
    job_id = sweep_world.client.post("/api/sweeps", json={"base": BASE, "variable": "top_k", "values": [4]}).json()["job_id"]
    for _ in range(200):
        if jobs.get_job(sweep_world.conn, job_id).run_id:
            break
        threading.Event().wait(0.02)
    assert jobs.get_job(sweep_world.conn, job_id).message.startswith("Sweep on Stack B: run 1 of 2, ")
    shown = sweep_world.client.get("/api/sweeps/latest/B").json()
    assert (shown["id"], shown["kind"], shown["status"]) == (job_id, "sweep", "running")
    sweep_world.gate.set()
    finish(sweep_world)
    done = sweep_world.client.post("/api/sweeps/plan", json={"base": BASE, "variable": "top_k", "values": [4]}).json()
    assert sweep_world.client.get("/api/sweeps/latest/B").json()["status"] == "done"
    assert [i["run"]["run_id"] is not None for i in done["items"]] == [True, True]


def test_the_latest_route_shows_the_newest_sweep_of_the_stack_only(sweep_world):
    sweep_world.fail_at = 1
    failed = jobs.submit_sweep(sweep_world.conn, sweep("top_k", [4]))
    finish(sweep_world)
    sweep_world.fail_at = None
    latest = jobs.submit_sweep(sweep_world.conn, sweep("top_k", [6]))
    finish(sweep_world)
    shown = sweep_world.client.get("/api/sweeps/latest/B").json()
    assert (failed, shown["id"], shown["status"]) == (latest - 1, latest, "done")
    assert sweep_world.client.get("/api/sweeps/latest/A").json() is None


def test_the_latest_route_shows_nothing_on_a_stack_never_swept_and_refuses_an_unknown_stack(sweep_world):
    assert sweep_world.client.get("/api/sweeps/latest/B").json() is None
    assert sweep_world.client.get("/api/sweeps/latest/C").status_code == 422


def test_a_sweep_left_unfinished_by_a_restart_is_marked_failed_with_its_run(sweep_world):
    """As the app starts: a sweep job left running, with its current run left running."""
    run_id = pipeline.start_run(sweep_world.conn, sweep("top_k", [4]).base.choices(), DEV)
    job_id = jobs.insert(sweep_world.conn, "jobs", {"kind": "sweep", "stack": "B", "runs_total": 2, "run_id": run_id})
    waiting = jobs.insert(sweep_world.conn, "jobs", {"kind": "sweep", "stack": "A", "runs_total": 1})
    jobs.set_status(sweep_world.conn, job_id, "running")
    assert jobs.recover_interrupted(sweep_world.conn) == 2
    assert [jobs.get_job(sweep_world.conn, i).error for i in (job_id, waiting)] == [jobs.INTERRUPTED] * 2
    assert runs.get_run(sweep_world.conn, run_id).status == "failed"


def test_the_estimate_refusal_matches_the_plan_total(sweep_world, monkeypatch):
    monkeypatch.setattr(pipeline, "remaining", lambda conn: 0.0)
    reply = sweep_world.client.post("/api/sweeps", json={"base": BASE, "variable": "top_k", "values": [4]})
    plan = sweep_world.client.post("/api/sweeps/plan", json={"base": BASE, "variable": "top_k", "values": [4]}).json()
    assert reply.status_code == 409
    assert reply.json()["detail"] == f"The sweep is estimated at ${plan['estimate_usd']:.4f}, but only $0.0000 of the budget is left"


def test_a_failed_sweep_writes_its_trace_to_the_error_file(sweep_world):
    sweep_world.fail_at = 1
    job_id = jobs.submit_sweep(sweep_world.conn, sweep("top_k", [4]))
    finish(sweep_world)
    [line] = [json.loads(row) for row in (settings.var_dir / "errors.log").read_text(encoding="utf-8").splitlines()]
    assert (line["logger"], line["message"], line["job_id"]) == ("rag_playground.jobs", "job failed", job_id)
    assert "rate limited" in line["exception"]
