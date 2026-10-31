"""Choose the best stored run (T08). Only runs that can fairly be compared compete: finished, on the full dev questions
of the current dataset, graded by the current judge. Smoke runs and held-out runs never do."""

import sqlite3
from statistics import fmean

from rag_playground.chunking.chunk_sets import load as load_chunk_set
from rag_playground.datasets.schema import dataset_sha256, load_tests
from rag_playground.llm.models import model_info
from rag_playground.rag import runs
from rag_playground.scoring import retrieval, selection, trust
from rag_playground.settings import JUDGE_MODEL


def candidate(conn: sqlite3.Connection, run: runs.Run, by_id: dict) -> selection.Candidate:
    """Score one stored run. Retrieval scores use answerable questions only; the others are means over all."""
    results = runs.get_results(conn, run.id)
    tests = [by_id[result.test_id] for result in results]
    found = retrieval.score_run(tests, {r.test_id: r.hits for r in results}, run.meta.top_k,
                                load_chunk_set(run.meta.chunk_set_id))
    refused = {r.test_id: r.judgement.refused for r in results}
    scores = {"mrr": found["mrr"], "recall": found["recall"],
              "faithfulness": fmean(r.judgement.faithfulness for r in results),
              "correct_refusal_rate": trust.correct_refusal_rate(tests, refused)}
    mrr = {r.test_id: retrieval.reciprocal_rank([h.source for h in r.hits], by_id[r.test_id].source_docs)
           for r in results if by_id[r.test_id].source_docs}
    return selection.Candidate(run.id, scores, {r.test_id: r.judgement.accuracy for r in results},
                               fmean(r.cost_usd for r in results), mrr)


def candidates(conn: sqlite3.Connection) -> list[selection.Candidate]:
    """Every stored run that may compete, oldest first."""
    tests = load_tests()
    dev_ids = sorted(t.id for t in tests if t.split == "dev")
    rows = conn.execute("SELECT id FROM runs WHERE status = 'done' AND split = 'dev' AND dataset_sha256 = ? "
                        "AND judge_slug = ? ORDER BY id",
                        (dataset_sha256(), model_info(JUDGE_MODEL).canonical_slug)).fetchall()
    stored = [runs.get_run(conn, row["id"]) for row in rows]
    by_id = {t.id: t for t in tests}
    return [candidate(conn, run, by_id) for run in stored if sorted(run.meta.test_ids) == dev_ids]


def best_run(conn: sqlite3.Connection) -> selection.Candidate | None:
    """The best stored run, or None if no comparable run passes every gate."""
    return selection.pick_best(candidates(conn))
