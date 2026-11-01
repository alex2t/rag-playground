"""What the Compare page reads (T57): two finished runs on the same questions, side by side."""

import sqlite3

from rag_playground.datasets.schema import load_tests
from rag_playground.rag import best_run, evaluation, heldout, runs
from rag_playground.settings import PASS_ACCURACY


def verdict(change: dict) -> str:
    """A paired change (T09), read both ways: its whole interval above 0, below 0, or holding 0."""
    return "better" if change["low"] > 0 else "worse" if change["high"] < 0 else "no real difference"


def check_comparable(before: dict, after: dict) -> None:
    """Raise ValueError unless both runs asked every question of the same split: a paired test needs the same questions."""
    if before["id"] == after["id"]:
        raise ValueError("Pick two different runs")
    for run in (before, after):
        if not run["full"]:
            raise ValueError(f"Run {run['id']} is a sample of {run['questions']} questions: Compare takes full runs")
    if before["split"] != after["split"]:
        raise ValueError("A dev run and a held-out run ask different questions, so they cannot be compared")


def question_changes(conn: sqlite3.Connection, before_id: int, after_id: int) -> dict:
    """The questions that crossed the pass mark (T20) between two runs, and how many stayed on one side."""
    tests = {test.id: test for test in load_tests()}
    after = {result.test_id: result.judgement.accuracy for result in runs.get_results(conn, after_id)}
    moved = {"fixed": [], "broken": [], "both_pass": 0, "both_fail": 0}
    for result in runs.get_results(conn, before_id):
        old, new = result.judgement.accuracy, after[result.test_id]
        if (old >= PASS_ACCURACY) == (new >= PASS_ACCURACY):
            moved["both_pass" if old >= PASS_ACCURACY else "both_fail"] += 1
            continue
        test = tests[result.test_id]
        moved["fixed" if new >= PASS_ACCURACY else "broken"].append(
            {"test_id": test.id, "category": test.category.value, "question": test.question, "before": old, "after": new})
    return moved


def compare(conn: sqlite3.Connection, before_id: int, after_id: int) -> dict:
    """Both reports, the paired changes of accuracy and MRR, and the questions fixed or broken. KeyError if a run does
    not exist, ValueError if the two cannot be compared. Held-out runs compare overall only (T18, T56)."""
    check_comparable(evaluation.summary(conn, before_id), evaluation.summary(conn, after_id))
    before, after = evaluation.report(conn, before_id), evaluation.report(conn, after_id)
    tests ={test.id: test for test in load_tests()}
    candidates = [best_run.candidate(conn, runs.get_run(conn, run_id), tests) for run_id in (before_id, after_id)]
    changes = {name: change | {"verdict": verdict(change)} for name, change in heldout.gain(*candidates).items()}
    return {"before": before, "after": after, "change": changes,
            "questions": None if before["split"] == "heldout" else question_changes(conn, before_id, after_id)}
