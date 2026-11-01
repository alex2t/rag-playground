"""What the Evaluate page reads (T56): a run's estimate before it starts, the stored runs, and a finished run's scores."""

import sqlite3
from statistics import fmean

from rag_playground.chunking.chunk_sets import chunk_settings
from rag_playground.chunking.chunk_sets import load as load_chunk_set
from rag_playground.datasets.schema import TestCase, dataset_sha256, load_tests
from rag_playground.rag import pipeline, runs, spend
from rag_playground.scoring import retrieval, selection, trust
from rag_playground.settings import SECONDS_PER_QUESTION
from rag_playground.stacks import indexes

JUDGED = ("accuracy", "completeness", "relevance", "faithfulness")


def estimate_run(conn: sqlite3.Connection, choices: pipeline.Choices, tests: list[TestCase]) -> dict:
    """Questions, cost and time of a run, storing nothing. It is refused like the run itself, except over budget: the
    page shows what is left, and the start refuses it."""
    indexes.require(conn, choices.stack, choices.chunk_set_id)
    _, cost = pipeline.plan_run(conn, choices, tests)
    return {"questions": len(tests), "estimate_usd": cost, "seconds": len(tests) * SECONDS_PER_QUESTION[choices.stack],
            "budget_left_usd": pipeline.remaining(conn)}


def settings_of(meta: runs.RunMeta) -> dict:
    """The settings a result must state (T12, T14). No scores: this also describes held-out runs."""
    return {**chunk_settings(meta.chunk_set_id), "chunk_set_id": meta.chunk_set_id, "top_k": meta.top_k, "hybrid": meta.hybrid,
            "openai_ranking": meta.openai_ranking, "rerank": meta.rerank_model is not None,
            "answer_model": meta.answer_model, "prompt_name": meta.prompt_name,
            "temperature_controlled": meta.temperature_controlled}


def summary(conn: sqlite3.Connection, run_id: int) -> dict:
    """One line of the run list. `job_id` and `job_status` are the job still working on it. `full` says it asked its whole split, so a
    smoke test or a sample is never read as a full run."""
    run = runs.get_run(conn, run_id)
    split_size = sum(test.split == run.meta.split for test in load_tests())
    job = conn.execute("SELECT id, status FROM jobs WHERE run_id = ? AND status IN ('queued', 'running')", (run_id,)).fetchone()
    return {"id": run.id, "created_at": run.created_at, "status": run.status, "error": run.error,
            "stack": run.meta.stack, "split": run.meta.split, "questions": len(run.meta.test_ids),
            "full": len(run.meta.test_ids) == split_size, "done": runs.run_row(conn, run_id)["done"],
            "job_id": job and job["id"], "job_status": job and job["status"], "settings": settings_of(run.meta)}


def listing(conn: sqlite3.Connection) -> list[dict]:
    """Every stored run, newest first."""
    return [summary(conn, row["id"]) for row in conn.execute("SELECT id FROM runs ORDER BY id DESC").fetchall()]


def judged_means(results: list[runs.Result]) -> dict[str, float]:
    return {name: fmean(getattr(result.judgement, name) for result in results) for name in JUDGED}


def by_category(results: list[runs.Result], tests: dict[str, TestCase]) -> list[dict]:
    """The judge's scores per question category, in alphabetical order. Retrieval scores are left out: unanswerable
    questions have none."""
    groups: dict[str, list[runs.Result]] = {}
    for result in results:
        groups.setdefault(tests[result.test_id].category.value, []).append(result)
    return [{"category": category, "questions": len(group), **judged_means(group)} for category, group in sorted(groups.items())]


def report(conn: sqlite3.Connection, run_id: int) -> dict:
    """A finished run's scores. KeyError if it does not exist, ValueError if it is not done or used another version of
    the dataset, whose questions may have changed (best_run leaves such runs out too). A held-out run reports its
    overall scores only: per-category scores could steer later choices (T18, T56)."""
    head = summary(conn, run_id)
    if head["status"] != "done":
        raise ValueError(f"Run {run_id} has no report: it is {head['status']}")
    run = runs.get_run(conn, run_id)
    if run.meta.dataset_sha256 != dataset_sha256():
        raise ValueError(f"Run {run_id} has no report: it used another version of the dataset")
    results = runs.get_results(conn, run_id)
    tests = {test.id: test for test in load_tests()}
    asked = [tests[result.test_id] for result in results]
    found = retrieval.score_run(asked, {r.test_id: r.hits for r in results}, run.meta.top_k,
                                load_chunk_set(run.meta.chunk_set_id))
    refused = {r.test_id: r.judgement.refused for r in results}
    scores = found | judged_means(results) | {"correct_refusal_rate": trust.correct_refusal_rate(asked, refused),
                                              "false_refusal_rate": trust.false_refusal_rate(asked, refused)}
    fee = spend.search_fee(run.meta.stack)
    return head | {"scores": scores, "failed_gates": selection.failed_gates(scores),
                   "cost_per_question": fmean(r.cost_usd + fee for r in results),
                   "latency_s": fmean(r.latency_s for r in results),
                   "categories": None if run.meta.split == "heldout" else by_category(results, tests)}
