"""What the Evaluate page reads (T56): an estimate that stores nothing, the run list, and a finished run's scores, checked
against hand-worked numbers. Same fakes as test_jobs.py (no network, no cost)."""

import math

import pytest
from fastapi.testclient import TestClient
from test_api_runs import A, B, counts, stack_a, start  # noqa: F401  (stack_a is a fixture)
from test_jobs import CHOICES, CHUNK, world  # noqa: F401  (world is a fixture)

from rag_playground import jobs, main
from rag_playground.datasets.schema import Category, load_tests
from rag_playground.rag import evaluation, pipeline, prompts, runs
from rag_playground.rag.runs import Result
from rag_playground.scoring.judging import Judgement
from rag_playground.settings import SECONDS_PER_QUESTION, settings
from rag_playground.stacks.hits import Hit

client = TestClient(main.app)
TESTS = load_tests()
ANSWERABLE = [t for t in TESTS if t.category != Category.UNANSWERABLE and len(t.source_docs) == 1]
FACT = next(t for t in ANSWERABLE if t.split == "dev" and t.category == Category.DIRECT_FACT)
OTHER = next(t for t in ANSWERABLE if t.split == "dev" and t.category == Category.NUMERICAL)
NONE = next(t for t in TESTS if t.split == "dev" and t.category == Category.UNANSWERABLE)
HELD = [next(t for t in ANSWERABLE if t.split == "heldout"),
        next(t for t in TESTS if t.split == "heldout" and t.category == Category.UNANSWERABLE)]


def verdict(score, refused=False):
    return Judgement(refused=refused, accuracy=score, completeness=score, relevance=score, faithfulness=score,
                     feedback="fine", faithfulness_feedback="fine")


def hit(source, text="text"):
    return Hit("c", source, 1.0, text)


def result(test, hits, score, refused=False, cost=0.002, latency=1.0):
    return Result(test.id, hits, None, "An answer.", verdict(score, refused), cost, latency)


def stored(conn, results, tests, choices=CHOICES, finish=True):
    run_id = runs.create_run(conn, pipeline.build_meta(choices, prompts.get(conn, "default"), tests))
    for item in results:
        runs.add_result(conn, run_id, item)
    if finish:
        runs.finish_run(conn, run_id)
    return run_id


@pytest.fixture(autouse=True)
def every_document_has_a_chunk(monkeypatch):
    sources = sorted({source for test in TESTS for source in test.source_docs})
    monkeypatch.setattr(evaluation, "load_chunk_set", lambda set_id: [CHUNK.model_copy(update={"source": s}) for s in sources for _ in range(2)])


@pytest.fixture
def scored(world):
    """Three dev questions: FACT finds its document second, OTHER first and wrongly refuses, NONE correctly refuses."""
    results = [result(FACT, [hit("no.md"), hit(FACT.source_docs[0], " ".join(FACT.keywords))], 5, latency=1.0),
               result(OTHER, [hit(OTHER.source_docs[0]), hit("no.md")], 2, refused=True, latency=2.0),
               result(NONE, [hit("no.md"), hit("no.md")], 3, refused=True, latency=3.0)]
    world["run"] = stored(world["conn"], results, [FACT, OTHER, NONE])
    return world


def report(run_id):
    return client.get(f"/api/runs/{run_id}/report")


def test_an_estimate_gives_questions_cost_time_and_what_is_left_and_stores_nothing(world):
    before = counts(world["conn"])
    response = client.post("/api/runs/estimate", json=B)
    assert response.status_code == 200
    body = response.json()
    assert body["questions"] == 20
    assert body["seconds"] == 20 * SECONDS_PER_QUESTION["B"]
    assert body["budget_left_usd"] == 1.0
    assert body["estimate_usd"] > 0
    assert counts(world["conn"]) == before


def test_the_estimate_is_what_the_run_itself_checks(world, monkeypatch):
    estimated = client.post("/api/runs/estimate", json=B).json()["estimate_usd"]
    monkeypatch.setattr(settings, "budget_usd", estimated * 0.99)
    assert client.post("/api/runs", json=B).status_code == 409
    monkeypatch.setattr(settings, "budget_usd", estimated * 1.01)
    monkeypatch.setattr(jobs.executor, "submit", lambda *args: None)
    assert client.post("/api/runs", json=B).status_code == 202


def test_stack_a_is_timed_and_charged_as_stack_a(world, stack_a):
    a = client.post("/api/runs/estimate", json=A).json()
    b = client.post("/api/runs/estimate", json=B).json()
    assert a["seconds"] == 20 * SECONDS_PER_QUESTION["A"]
    assert a["estimate_usd"] == pytest.approx(b["estimate_usd"] + 20 * 0.0025)


def test_over_budget_is_shown_not_refused_by_the_estimate(world, monkeypatch):
    monkeypatch.setattr(settings, "budget_usd", 0.0)
    body = client.post("/api/runs/estimate", json=B).json()
    assert body["budget_left_usd"] == 0 and body["estimate_usd"] > 0


@pytest.mark.parametrize("change, status, reason", [
    ({"chunk_size": 512, "overlap": 0}, 404, "Not found: fixed__c512__o0 is not indexed on Stack B"),
    ({"prompt_name": "gone"}, 404, "Not found: gone"),
])
def test_the_estimate_refuses_what_the_run_would_refuse(world, change, status, reason):
    response = client.post("/api/runs/estimate", json={**B, **change})
    assert (response.status_code, response.json()["detail"]) == (status, reason)


def test_a_heldout_estimate_refuses_a_prompt_with_no_dev_run(world):
    prompts.save(world["conn"], "mine", "Text.")
    response = client.post("/api/runs/estimate", json={**B, "questions": "heldout", "prompt_name": "mine"})
    assert response.status_code == 422 and "no finished dev run" in response.json()["detail"]


def test_the_run_list_is_newest_first_with_settings_progress_and_no_scores(scored):
    conn = scored["conn"]
    second = stored(conn, [], [FACT], finish=False)
    listed = client.get("/api/runs").json()
    assert [run["id"] for run in listed] == [second, scored["run"]]
    newest, oldest = listed
    assert (newest["status"], newest["done"], newest["questions"], newest["full"]) == ("running", 0, 1, False)
    assert (oldest["status"], oldest["done"], oldest["questions"], oldest["split"]) == ("done", 3, 3, "dev")
    assert oldest["settings"] == {"chunk_set_id": "fixed__c1024__o200", "top_k": 2, "hybrid": False, "openai_ranking": None,
                                  "rerank": False, "answer_model": "openai/gpt-4.1-nano", "prompt_name": "default",
                                  "temperature_controlled": True}
    assert "scores" not in oldest and "accuracy" not in str(oldest)


def test_the_list_names_the_job_still_working_on_a_run(world, monkeypatch):
    monkeypatch.setattr(jobs.executor, "submit", lambda *args: None)
    job_id = client.post("/api/runs", json=B).json()["job_id"]
    assert client.get("/api/runs").json()[0]["job_id"] == job_id
    jobs.set_status(world["conn"], job_id, "running")
    assert client.get("/api/runs").json()[0]["job_id"] == job_id
    jobs.set_status(world["conn"], job_id, "done")
    assert client.get("/api/runs").json()[0]["job_id"] is None


def test_a_whole_split_counts_as_full(world, monkeypatch):
    monkeypatch.setattr(jobs.executor, "submit", lambda *args: None)
    monkeypatch.setattr(settings, "budget_usd", 5.0)
    client.post("/api/runs", json={**B, "questions": "smoke"})
    client.post("/api/runs", json={**B, "questions": "dev"})
    client.post("/api/runs", json={**B, "questions": "heldout"})
    assert [(r["split"], r["questions"], r["full"]) for r in client.get("/api/runs").json()] == [
        ("heldout", 48, True), ("dev", 192, True), ("dev", 20, False)]


def test_the_report_holds_the_scores_worked_out_by_hand(scored):
    response = report(scored["run"])
    assert response.status_code == 200
    body = response.json()
    expected = {"mrr": (0.5 + 1) / 2, "recall": 1.0, "hit": 1.0, "keyword_recall": 0.5, "accuracy": 10 / 3, "completeness": 10 / 3,
                "relevance": 10 / 3, "faithfulness": 10 / 3, "correct_refusal_rate": 1.0, "false_refusal_rate": 0.5}
    for name, value in expected.items():
        assert body["scores"][name] == pytest.approx(value), name
    ideal = 1 + 1 / math.log2(3)  # K=2, and each document has two chunks, so both top places could be relevant
    assert body["scores"]["ndcg"] == pytest.approx(((1 / math.log2(3)) / ideal + 1 / ideal) / 2)
    assert body["latency_s"] == pytest.approx(2.0)
    assert body["cost_per_question"] == pytest.approx(0.002)


def test_a_stack_a_report_includes_the_search_fee(world, scored):
    run_id = stored(world["conn"], [result(FACT, [hit(FACT.source_docs[0])], 5), result(NONE, [], 5, refused=True)], [FACT, NONE],
                    pipeline.Choices(**{**CHOICES.__dict__, "stack": "A", "openai_ranking": {"ranker": "auto"}}))
    assert report(run_id).json()["cost_per_question"] == pytest.approx(0.002 + 0.0025)


def test_categories_hold_each_categorys_own_means(scored):
    assert report(scored["run"]).json()["categories"] == [
        {"category": "direct_fact", "questions": 1, "accuracy": 5, "completeness": 5, "relevance": 5, "faithfulness": 5},
        {"category": "numerical", "questions": 1, "accuracy": 2, "completeness": 2, "relevance": 2, "faithfulness": 2},
        {"category": "unanswerable", "questions": 1, "accuracy": 3, "completeness": 3, "relevance": 3, "faithfulness": 3}]


def test_failed_gates_are_named(scored):
    assert report(scored["run"]).json()["failed_gates"] == ["faithfulness"]


def test_a_gate_passed_is_not_named(world, scored):
    run_id = stored(world["conn"], [result(FACT, [hit(FACT.source_docs[0])], 5), result(NONE, [], 5, refused=True)], [FACT, NONE])
    assert report(run_id).json()["failed_gates"] == []


def test_a_heldout_run_reports_overall_scores_and_nothing_per_question_or_category(world):
    run_id = stored(world["conn"], [result(HELD[0], [hit(HELD[0].source_docs[0])], 4), result(HELD[1], [], 4, refused=True)], HELD)
    body = report(run_id).json()
    assert body["scores"]["accuracy"] == 4
    assert body["categories"] is None
    assert HELD[0].question not in str(body) and HELD[0].id not in str(body)
    assert client.get(f"/api/runs/{run_id}/answers").status_code == 422


def test_a_run_not_finished_has_no_report(world):
    running = stored(world["conn"], [], [FACT], finish=False)
    response = report(running)
    assert (response.status_code, response.json()["detail"]) == (422, f"Run {running} has no report: it is running")
    failed = stored(world["conn"], [result(FACT, [hit(FACT.source_docs[0])], 5)], [FACT, NONE], finish=False)
    runs.finish_run(world["conn"], failed, error="stopped")
    response = report(failed)
    assert (response.status_code, response.json()["detail"]) == (422, f"Run {failed} has no report: it is failed")


def test_a_run_from_another_dataset_version_says_so_and_is_not_called_missing(scored, monkeypatch):
    monkeypatch.setattr(evaluation, "dataset_sha256", lambda: "another")
    response = report(scored["run"])
    assert (response.status_code, response.json()["detail"]) == (
        422, f"Run {scored['run']} has no report: it used another version of the dataset")


def test_a_run_that_does_not_exist_has_no_report(world):
    assert report(999).status_code == 404


def test_a_real_job_ends_in_a_report(world):
    """Through the worker thread: what the job stored is what the report reads."""
    job = client.get(f"/api/jobs/{start(B).json()['job_id']}").json()
    body = report(job["run_id"]).json()
    assert (body["status"], body["questions"], body["full"]) == ("done", 20, False)
    assert body["scores"]["accuracy"] == 5
    assert sum(item["questions"] for item in body["categories"]) == 20
