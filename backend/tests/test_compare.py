"""GET /api/compare (T57): two full runs on the same questions, with hand-worked changes. Same fakes as test_jobs.py (no
network, no cost)."""

import pytest
from fastapi.testclient import TestClient
from test_evaluation import TESTS, every_document_has_a_chunk, hit, result, stored  # noqa: F401  (a fixture)
from test_jobs import CHOICES, world  # noqa: F401  (world is a fixture)

from rag_playground import main
from rag_playground.rag import best_run, compare, evaluation, pipeline, runs

client = TestClient(main.app)
DEV = [t for t in TESTS if t.split == "dev"]
HELD = [t for t in TESTS if t.split == "heldout"]


@pytest.fixture(autouse=True)
def same_chunks_for_the_candidates(monkeypatch):
    monkeypatch.setattr(best_run, "load_chunk_set", lambda set_id: evaluation.load_chunk_set(set_id))


def full_run(conn, tests, score, choices=CHOICES):
    """A finished run on `tests`. `score` gives each question's accuracy from its position."""
    hits = lambda t: [hit(t.source_docs[0]), hit("no.md")] if t.source_docs else [hit("no.md")]
    return stored(conn, [result(t, hits(t), score(i), refused=not t.source_docs) for i, t in enumerate(tests)], tests, choices)


def get(before, after):
    return client.get("/api/compare", params={"before": before, "after": after})


def test_a_run_better_on_every_question_is_better_by_exactly_that_much(world):
    conn = world["conn"]
    response = get(full_run(conn, DEV, lambda i: 3), full_run(conn, DEV, lambda i: 4))
    assert response.status_code == 200
    change = response.json()["change"]["accuracy"]
    assert change == {"low": 1.0, "high": 1.0, "real": True, "verdict": "better"}


def test_a_run_worse_on_every_question_is_worse_not_merely_unproved(world):
    conn = world["conn"]
    change = get(full_run(conn, DEV, lambda i: 4), full_run(conn, DEV, lambda i: 3)).json()["change"]["accuracy"]
    assert change == {"low": -1.0, "high": -1.0, "real": False, "verdict": "worse"}


def test_a_change_in_both_directions_is_no_real_difference(world):
    conn = world["conn"]
    change = get(full_run(conn, DEV, lambda i: 3), full_run(conn, DEV, lambda i: 3 + (1 if i % 2 else -1))).json()["change"]["accuracy"]
    assert change["low"] < 0 < change["high"]
    assert change["verdict"] == "no real difference"


def test_mrr_has_its_own_change(world):
    conn = world["conn"]
    choices = pipeline.Choices(**{**CHOICES.__dict__, "top_k": 2})
    first = full_run(conn, DEV, lambda i: 3, choices)
    swapped = lambda t: [hit("no.md"), hit(t.source_docs[0])] if t.source_docs else [hit("no.md")]
    second = stored(conn, [result(t, swapped(t), 3, refused=not t.source_docs) for t in DEV], DEV, choices)
    change = get(first, second).json()["change"]
    assert change["mrr"] == {"low": -0.5, "high": -0.5, "real": False, "verdict": "worse"}
    assert change["accuracy"]["verdict"] == "no real difference"


def test_questions_are_sorted_by_which_side_of_the_pass_mark_they_crossed(world):
    """Pass is accuracy 4 or more: 3 to 4 is fixed, 4 to 3 broken; 4 to 5 and 1 to 3 stay on their side."""
    conn = world["conn"]
    old = {0: 3, 1: 4, 2: 4, 3: 1}
    new = {0: 4, 1: 3, 2: 5, 3: 3}
    body = get(full_run(conn, DEV, lambda i: old.get(i, 5)), full_run(conn, DEV, lambda i: new.get(i, 5))).json()["questions"]
    assert body["fixed"] == [{"test_id": DEV[0].id, "category": DEV[0].category.value, "question": DEV[0].question, "before": 3, "after": 4}]
    assert body["broken"] == [{"test_id": DEV[1].id, "category": DEV[1].category.value, "question": DEV[1].question, "before": 4, "after": 3}]
    assert (body["both_pass"], body["both_fail"]) == (189, 1)


def test_the_two_directions_mirror_each_other(world):
    conn = world["conn"]
    a, b = full_run(conn, DEV, lambda i: 3 if i < 10 else 5), full_run(conn, DEV, lambda i: 5)
    forward, back = get(a, b).json()["questions"], get(b, a).json()["questions"]
    assert [q["test_id"] for q in forward["fixed"]] == [q["test_id"] for q in back["broken"]]
    assert (len(forward["fixed"]), forward["broken"], back["fixed"]) == (10, [], [])


def test_both_stacks_can_be_compared_and_each_keeps_its_own_settings_and_cost(world):
    conn = world["conn"]
    ranking = {"ranker": "auto", "embedding_weight": 1.0, "text_weight": 1.0, "score_threshold": 0.0}
    a = full_run(conn, DEV, lambda i: 4, pipeline.Choices(**{**CHOICES.__dict__, "stack": "A", "openai_ranking": ranking}))
    body = get(a, full_run(conn, DEV, lambda i: 4)).json()
    assert (body["before"]["stack"], body["after"]["stack"]) == ("A", "B")
    assert body["before"]["settings"]["openai_ranking"] == ranking
    assert body["after"]["settings"]["openai_ranking"] is None
    assert body["before"]["cost_per_question"] == pytest.approx(body["after"]["cost_per_question"] + 0.0025)


def test_two_heldout_runs_compare_overall_and_reveal_no_question(world):
    conn = world["conn"]
    a, b = full_run(conn, HELD, lambda i: 3), full_run(conn, HELD, lambda i: 4)
    response = get(a, b)
    body = response.json()
    assert body["change"]["accuracy"]["verdict"] == "better"
    assert body["questions"] is None
    assert (body["before"]["categories"], body["after"]["categories"]) == (None, None)
    assert not any(t.id in response.text or t.question in response.text for t in HELD)


def test_a_dev_run_and_a_heldout_run_cannot_be_compared(world):
    conn = world["conn"]
    response = get(full_run(conn, DEV, lambda i: 4), full_run(conn, HELD, lambda i: 4))
    assert (response.status_code, response.json()["detail"]) == (
        422, "A dev run and a held-out run ask different questions, so they cannot be compared")


def test_a_sample_stays_out_of_compare(world):
    conn = world["conn"]
    sample = full_run(conn, DEV[:20], lambda i: 4)
    full = full_run(conn, DEV, lambda i: 4)
    for response in (get(full, sample), get(sample, full)):
        assert (response.status_code, response.json()["detail"]) == (
            422, f"Run {sample} is a sample of 20 questions: Compare takes full runs")


def test_a_run_is_not_compared_with_itself(world):
    run = full_run(world["conn"], DEV, lambda i: 4)
    response = get(run, run)
    assert (response.status_code, response.json()["detail"]) == (422, "Pick two different runs")


def test_an_unfinished_run_is_refused_with_its_reason(world):
    conn = world["conn"]
    running = stored(conn, [], DEV, finish=False)
    response = get(full_run(conn, DEV, lambda i: 4), running)
    assert (response.status_code, response.json()["detail"]) == (422, f"Run {running} has no report: it is running")


def test_a_run_that_does_not_exist_is_named(world):
    run = full_run(world["conn"], DEV, lambda i: 4)
    response = get(run, 999)
    assert (response.status_code, response.json()["detail"]) == (404, "No run 999")


def test_a_run_from_another_dataset_version_is_refused(world, monkeypatch):
    conn = world["conn"]
    a, b = full_run(conn, DEV, lambda i: 4), full_run(conn, DEV, lambda i: 4)
    monkeypatch.setattr(evaluation, "dataset_sha256", lambda: "another")
    response = get(a, b)
    assert (response.status_code, response.json()["detail"]) == (
        422, f"Run {a} has no report: it used another version of the dataset")


@pytest.mark.parametrize("change, verdict", [({"low": 0.01, "high": 1}, "better"), ({"low": 0, "high": 1}, "no real difference"),
                                             ({"low": -1, "high": 0}, "no real difference"), ({"low": -1, "high": -0.01}, "worse")])
def test_the_verdict_needs_the_whole_interval_on_one_side(change, verdict):
    assert compare.verdict(change) == verdict


def test_runs_stay_as_they_were(world):
    conn = world["conn"]
    a, b = full_run(conn, DEV, lambda i: 3), full_run(conn, DEV, lambda i: 4)
    before = conn.execute("SELECT count(*) FROM results").fetchone()[0]
    get(a, b)
    assert conn.execute("SELECT count(*) FROM results").fetchone()[0] == before
    assert runs.get_run(conn, a).status == "done"
