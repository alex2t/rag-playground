"""Blind grading for the judge calibration (T48): draw the fixed sample from the two full S0 runs, hand out one answer at
a time without the judge's score or the stack, and compute agreement only when every answer is graded."""

import random
import sqlite3
from dataclasses import dataclass

from rag_playground.chunking.chunk_sets import chunk_set_id
from rag_playground.datasets.schema import dataset_sha256, load_tests
from rag_playground.llm.models import model_info
from rag_playground.rag import prompts, runs
from rag_playground.scoring import calibration
from rag_playground.settings import CALIBRATION_PER_RUN, CALIBRATION_SEED, JUDGE_MODEL, S0


@dataclass(frozen=True)
class Item:
    """What the grader sees of one answer. It must never carry the judge's score, or anything naming the stack."""

    position: int
    question: str
    reference_answer: str
    answer: str


def problems(run: runs.Run, stack: str, dev_ids: list[str]) -> list[str]:
    """Why a stored run is not the full S0 baseline of `stack`, on the current dataset and judge."""
    meta, search = run.meta, S0["search"][stack]
    expected = {"status": (run.status, "done"), "stack": (meta.stack, stack), "split": (meta.split, "dev"),
                "questions": (sorted(meta.test_ids), dev_ids),
                "chunk set": (meta.chunk_set_id, chunk_set_id(S0["chunk_size"], S0["overlap"])),
                "top-K": (meta.top_k, S0["top_k"]), "reranker": (meta.rerank_model, None),
                "answer model": (meta.answer_model, S0["answer_model"]), "hybrid": (meta.hybrid, search["hybrid"]),
                "ranking": (meta.openai_ranking, search["openai_ranking"]),
                "prompt": (meta.prompt_name, prompts.DEFAULT_NAME), "dataset": (meta.dataset_sha256, dataset_sha256()),
                "judge": (meta.judge_slug, model_info(JUDGE_MODEL).canonical_slug)}
    return [name for name, (actual, wanted) in expected.items() if actual != wanted]


def draw_items(conn: sqlite3.Connection, run_a: int, run_b: int) -> list[tuple[int, str]]:
    """The (run id, test id) sample of both runs in one shuffled order. Each run has its own seed: with one shared seed,
    two runs with similar scores would pick the same questions."""
    items = []
    for offset, run_id in enumerate((run_a, run_b)):
        scores = {r.test_id: r.judgement.accuracy for r in runs.get_results(conn, run_id)}
        items += [(run_id, test_id)
                  for test_id in calibration.sample(scores, CALIBRATION_PER_RUN, CALIBRATION_SEED + offset)]
    random.Random(CALIBRATION_SEED).shuffle(items)
    return items


def open_calibration(conn: sqlite3.Connection, run_a: int, run_b: int) -> int:
    """The calibration of these two S0 runs, drawing its sample the first time; ValueError if a run does not qualify."""
    row = conn.execute("SELECT id FROM calibrations WHERE run_a = ? AND run_b = ?", (run_a, run_b)).fetchone()
    if row:
        return row["id"]
    dev_ids = sorted(t.id for t in load_tests() if t.split == "dev")
    for run_id, stack in ((run_a, "A"), (run_b, "B")):
        wrong = problems(runs.get_run(conn, run_id), stack, dev_ids)
        if wrong:
            raise ValueError(f"Run {run_id} is not the full S0 run of Stack {stack}: {', '.join(wrong)}")
    items = draw_items(conn, run_a, run_b)
    with conn:
        calibration_id = conn.execute(
            "INSERT INTO calibrations (run_a, run_b, per_run, seed, size) VALUES (?, ?, ?, ?, ?)",
            (run_a, run_b, CALIBRATION_PER_RUN, CALIBRATION_SEED, len(items))).lastrowid
        conn.executemany("INSERT INTO calibration_items (calibration_id, position, run_id, test_id) VALUES (?, ?, ?, ?)",
                         [(calibration_id, position, *item) for position, item in enumerate(items, start=1)])
    return calibration_id


def next_item(conn: sqlite3.Connection, calibration_id: int) -> Item | None:
    """The first ungraded answer, or None when every answer is graded."""
    row = conn.execute("SELECT i.position, i.test_id, r.answer FROM calibration_items i "
                       "JOIN results r ON r.run_id = i.run_id AND r.test_id = i.test_id "
                       "WHERE i.calibration_id = ? AND i.grade IS NULL ORDER BY i.position LIMIT 1",
                       (calibration_id,)).fetchone()
    if row is None:
        return None
    test = next(t for t in load_tests() if t.id == row["test_id"])
    return Item(row["position"], test.question, test.reference_answer, row["answer"])


def save_grade(conn: sqlite3.Connection, calibration_id: int, position: int, grade: int) -> None:
    """Store the user's accuracy score for one answer, once; KeyError if there is no such answer."""
    with conn:
        updated = conn.execute("UPDATE calibration_items SET grade = ? WHERE calibration_id = ? AND position = ?",
                               (grade, calibration_id, position)).rowcount
    if not updated:
        raise KeyError(position)


def progress(conn: sqlite3.Connection, calibration_id: int) -> tuple[int, int]:
    """(answers graded, sample size); KeyError if the calibration does not exist."""
    row = conn.execute("SELECT size, (SELECT count(grade) FROM calibration_items WHERE calibration_id = c.id) AS graded "
                       "FROM calibrations c WHERE id = ?", (calibration_id,)).fetchone()
    if row is None:
        raise KeyError(calibration_id)
    return row["graded"], row["size"]


def agreement(conn: sqlite3.Connection, calibration_id: int) -> calibration.Agreement:
    """Judge against user. Only when every answer is graded: a partial figure would hint at the judge's scores."""
    graded, size = progress(conn, calibration_id)
    if graded < size:
        raise ValueError(f"Only {graded} of {size} answers are graded")
    rows = conn.execute("SELECT r.accuracy, i.grade FROM calibration_items i "
                        "JOIN results r ON r.run_id = i.run_id AND r.test_id = i.test_id "
                        "WHERE i.calibration_id = ?", (calibration_id,)).fetchall()
    return calibration.agreement([(row["accuracy"], row["grade"]) for row in rows])
