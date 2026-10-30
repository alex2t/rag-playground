"""Step 8 checks of blind grading (T48): the sample is fixed once drawn, and the grader never sees the judge or the
stack."""

import sqlite3
from dataclasses import fields, replace
from types import SimpleNamespace

import pytest

from rag_playground import store
from rag_playground.chunking.chunk_sets import chunk_set_id
from rag_playground.datasets.schema import TestCase
from rag_playground.rag import grading, prompts, runs
from rag_playground.scoring.judging import Judgement
from rag_playground.settings import S0

DATASET = "d" * 64
JUDGE_SLUG = "judge-v1"
TESTS = [TestCase(id=f"q{i}", question=f"Question {i}?", reference_answer=f"Reference {i}.", category="direct_fact",
                  source_docs=["gold.md"], keywords=["x"], split="dev") for i in range(40)]
DEV_IDS = [t.id for t in TESTS]
META_A = runs.RunMeta(
    stack="A", split="dev", test_ids=DEV_IDS, chunk_set_id=chunk_set_id(S0["chunk_size"], S0["overlap"]),
    top_k=S0["top_k"], hybrid=True, openai_ranking=S0["search"]["A"]["openai_ranking"],
    answer_model=S0["answer_model"], answer_slug="answer-v1", judge_model="judge", judge_slug=JUDGE_SLUG,
    rerank_model=None, rerank_slug=None, rerank_candidates=None, temperature_controlled=True, prompt_name="default",
    prompt_sha256=prompts.sha256(prompts.DEFAULT_TEXT), dataset_sha256=DATASET, app_version="test")
META_B = replace(META_A, stack="B", hybrid=False, openai_ranking=None)


def score_of(test_id: str) -> int:
    """Judge accuracy of a question: eight answers at each score."""
    return int(test_id[1:]) % 5 + 1


def make_run(conn, meta: runs.RunMeta, finish: bool = True) -> int:
    run_id = runs.create_run(conn, meta)
    for test_id in meta.test_ids:
        judgement = Judgement(refused=False, accuracy=score_of(test_id), completeness=4, relevance=4, faithfulness=4,
                              feedback="f", faithfulness_feedback="g")
        runs.add_result(conn, run_id, runs.Result(test_id=test_id, hits=[], rerank_repaired=None,
                                                  answer=f"{meta.stack} answers {test_id}", judgement=judgement,
                                                  cost_usd=0.001, latency_s=1.0))
    if finish:
        runs.finish_run(conn, run_id)
    return run_id


@pytest.fixture
def conn(tmp_path, monkeypatch):
    connection = store.connect(tmp_path / "test.db")
    prompts.ensure_default(connection)
    monkeypatch.setattr(grading, "load_tests", lambda: TESTS)
    monkeypatch.setattr(grading, "dataset_sha256", lambda: DATASET)
    monkeypatch.setattr(grading, "model_info", lambda model: SimpleNamespace(canonical_slug=JUDGE_SLUG))
    yield connection
    connection.close()


@pytest.fixture
def calibration_id(conn):
    return grading.open_calibration(conn, make_run(conn, META_A), make_run(conn, META_B))


def items(conn, calibration_id: int) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM calibration_items WHERE calibration_id = ? ORDER BY position",
                        (calibration_id,)).fetchall()


def grade_all(conn, calibration_id: int, grade_for) -> None:
    """Grade every answer in order; `grade_for` gets the judge's score of each."""
    for row in items(conn, calibration_id):
        grading.save_grade(conn, calibration_id, row["position"], grade_for(score_of(row["test_id"])))


def test_the_sample_has_three_per_score_from_each_stack(conn, calibration_id):
    rows = items(conn, calibration_id)
    assert [row["position"] for row in rows] == list(range(1, 31))
    for run_id in {row["run_id"] for row in rows}:
        picked = [score_of(row["test_id"]) for row in rows if row["run_id"] == run_id]
        assert sorted(picked) == sorted([1, 2, 3, 4, 5] * 3)


def test_the_order_mixes_the_stacks(conn, calibration_id):
    """T48: the order must not reveal the stack, so the stack changes often. A fair shuffle of 15 and 15 changes it
    about 15 times; the order is fixed by the seed, so this cannot fail by chance."""
    in_order = [row["run_id"] for row in items(conn, calibration_id)]
    assert sum(first != second for first, second in zip(in_order, in_order[1:])) >= 10


def test_two_runs_with_the_same_scores_do_not_pick_the_same_questions(conn, calibration_id):
    rows = items(conn, calibration_id)
    run_ids = sorted({row["run_id"] for row in rows})
    first, second = ({row["test_id"] for row in rows if row["run_id"] == run_id} for run_id in run_ids)
    assert first != second


def test_opening_again_returns_the_same_sample(conn, calibration_id):
    before = [tuple(row) for row in items(conn, calibration_id)]
    run_a, run_b = conn.execute("SELECT run_a, run_b FROM calibrations").fetchone()
    assert grading.open_calibration(conn, run_a, run_b) == calibration_id
    assert [tuple(row) for row in items(conn, calibration_id)] == before


def test_the_same_runs_always_draw_the_same_sample(conn):
    run_a, run_b = make_run(conn, META_A), make_run(conn, META_B)
    assert grading.draw_items(conn, run_a, run_b) == grading.draw_items(conn, run_a, run_b)


@pytest.mark.parametrize("wrong_a, reason", [
    (replace(META_A, test_ids=DEV_IDS[:30]), "questions"),
    (replace(META_A, top_k=4), "top-K"),
    (replace(META_A, chunk_set_id="fixed__c512__o50"), "chunk set"),
    (replace(META_A, answer_model="other"), "answer model"),
    (replace(META_A, hybrid=False), "hybrid"),
    (replace(META_A, openai_ranking={"ranker": "none"}), "ranking"),
    (replace(META_A, rerank_model="r", rerank_slug="r", rerank_candidates=20), "reranker"),
    (replace(META_A, dataset_sha256="e" * 64), "dataset"),
    (replace(META_A, judge_slug="judge-old"), "judge"),
    (replace(META_A, split="heldout"), "split"),
    (META_B, "stack"),
])
def test_only_the_full_s0_run_of_each_stack_qualifies(conn, wrong_a, reason):
    run_a, run_b = make_run(conn, wrong_a), make_run(conn, META_B)
    with pytest.raises(ValueError, match=reason):
        grading.open_calibration(conn, run_a, run_b)
    assert conn.execute("SELECT count(*) FROM calibrations").fetchone()[0] == 0


def test_an_unfinished_run_does_not_qualify(conn):
    with pytest.raises(ValueError, match="status"):
        grading.open_calibration(conn, make_run(conn, META_A, finish=False), make_run(conn, META_B))


def test_a_run_that_does_not_exist_is_refused(conn):
    with pytest.raises(KeyError):
        grading.open_calibration(conn, 998, 999)


def test_the_item_shows_only_what_the_grader_may_see(conn, calibration_id):
    assert [field.name for field in fields(grading.Item)] == ["position", "question", "reference_answer", "answer"]
    item = grading.next_item(conn, calibration_id)
    row = items(conn, calibration_id)[0]
    number = row["test_id"][1:]
    assert item.position == 1
    assert (item.question, item.reference_answer) == (f"Question {number}?", f"Reference {number}.")
    stored = conn.execute("SELECT answer FROM results WHERE run_id = ? AND test_id = ?",
                          (row["run_id"], row["test_id"])).fetchone()
    assert item.answer == stored["answer"]


def test_grading_resumes_at_the_first_ungraded_answer(conn, tmp_path, calibration_id):
    grading.save_grade(conn, calibration_id, 1, 4)
    grading.save_grade(conn, calibration_id, 3, 2)
    reopened = store.connect(tmp_path / "test.db")
    assert grading.next_item(reopened, calibration_id).position == 2
    assert grading.progress(reopened, calibration_id) == (2, 30)
    reopened.close()


def test_no_item_is_left_when_all_are_graded(conn, calibration_id):
    grade_all(conn, calibration_id, lambda judge: judge)
    assert grading.next_item(conn, calibration_id) is None
    assert grading.progress(conn, calibration_id) == (30, 30)


def test_a_grade_is_given_once(conn, calibration_id):
    grading.save_grade(conn, calibration_id, 1, 4)
    with pytest.raises(sqlite3.IntegrityError, match="given once"):
        grading.save_grade(conn, calibration_id, 1, 5)
    assert items(conn, calibration_id)[0]["grade"] == 4


@pytest.mark.parametrize("grade", [0, 6, 4.5])
def test_a_grade_is_a_whole_score_from_1_to_5(conn, calibration_id, grade):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        grading.save_grade(conn, calibration_id, 1, grade)


def test_grading_an_answer_outside_the_sample_is_refused(conn, calibration_id):
    with pytest.raises(KeyError):
        grading.save_grade(conn, calibration_id, 31, 4)


def test_agreement_waits_for_the_last_grade(conn, calibration_id):
    for position in range(1, 30):
        grading.save_grade(conn, calibration_id, position, 4)
    with pytest.raises(ValueError, match="29 of 30"):
        grading.agreement(conn, calibration_id)


def test_full_agreement(conn, calibration_id):
    grade_all(conn, calibration_id, lambda judge: judge)
    result = grading.agreement(conn, calibration_id)
    assert (result.pass_fail, result.within_one, result.graded) == (1.0, 1.0, 30)


def test_agreement_compares_the_user_with_the_judge_on_the_same_answers(conn, calibration_id):
    """12 of the 30 answers are judged 4 or 5. A user giving 4 to all agrees on those 12 and on none of the 18 others;
    within one point covers judge scores 3, 4 and 5, so 18 of the 30."""
    grade_all(conn, calibration_id, lambda judge: 4)
    result = grading.agreement(conn, calibration_id)
    assert result.pass_fail == pytest.approx(12 / 30)
    assert result.within_one == pytest.approx(18 / 30)


def test_progress_of_an_unknown_calibration(conn):
    with pytest.raises(KeyError):
        grading.progress(conn, 99)


def test_a_calibration_cannot_be_deleted_even_without_foreign_keys(conn, calibration_id):
    conn.execute("PRAGMA foreign_keys = OFF")
    with pytest.raises(sqlite3.IntegrityError, match="permanent"):
        conn.execute("DELETE FROM calibrations")


@pytest.mark.parametrize("sql", [
    "UPDATE calibrations SET seed = 1",
    "INSERT OR REPLACE INTO calibrations (id, run_a, run_b, per_score, seed, size) SELECT id, run_a, run_b, 1, 1, 1 "
    "FROM calibrations",
    "DELETE FROM calibration_items",
    "UPDATE calibration_items SET test_id = 'q0'",
    "UPDATE calibration_items SET position = position + 100",
    "UPDATE calibration_items SET run_id = 1",
    "INSERT OR REPLACE INTO calibration_items (calibration_id, position, run_id, test_id) "
    "SELECT calibration_id, position, run_id, test_id FROM calibration_items LIMIT 1",
    "INSERT INTO calibration_items (calibration_id, position, run_id, test_id) VALUES (1, 31, 1, 'q0')",
])
def test_the_sample_is_fixed_in_the_database(conn, calibration_id, sql):
    before = [tuple(row) for row in items(conn, calibration_id)]
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql)
    conn.rollback()
    assert [tuple(row) for row in items(conn, calibration_id)] == before


def test_an_item_must_be_a_stored_answer(conn, calibration_id):
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        conn.execute("INSERT INTO calibrations (run_a, run_b, per_score, seed, size) VALUES (1, 1, 3, 42, 1)")
        conn.execute("INSERT INTO calibration_items (calibration_id, position, run_id, test_id) VALUES (2, 1, 1, 'nope')")
    conn.rollback()


def test_an_item_cannot_arrive_already_graded(conn, calibration_id):
    with pytest.raises(sqlite3.IntegrityError, match="fixed once drawn"):
        conn.execute("INSERT INTO calibrations (run_a, run_b, per_score, seed, size) VALUES (1, 1, 3, 42, 1)")
        conn.execute("INSERT INTO calibration_items (calibration_id, position, run_id, test_id, grade) "
                     "VALUES (2, 1, 1, 'q0', 5)")
    conn.rollback()
