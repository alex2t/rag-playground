"""Background jobs in the API process (D07): one worker thread runs one job at a time, the UI polls its status.

One worker keeps runs in sequence, which the budget guard assumes (T44). Jobs do not survive a restart: at startup,
jobs and runs left unfinished are marked failed."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from rag_playground import store
from rag_playground.datasets.schema import TestCase
from rag_playground.rag import pipeline, runs
from rag_playground.rag.runs import insert
from rag_playground.stacks import indexes

INTERRUPTED = "interrupted: the app restarted"


def new_executor() -> ThreadPoolExecutor:
    """One worker thread, so jobs run one at a time."""
    return ThreadPoolExecutor(max_workers=1, thread_name_prefix="job")


executor = new_executor()


@dataclass(frozen=True)
class Job:
    id: int
    kind: str
    status: str
    run_id: int
    progress: float
    message: str
    error: str | None


def set_status(conn: sqlite3.Connection, job_id: int, status: str, error: str | None = None) -> None:
    finished = "datetime('now')" if status in ("done", "failed") else "NULL"
    with conn:
        conn.execute(f"UPDATE jobs SET status = ?, error = ?, finished_at = {finished} WHERE id = ?",
                     (status, error, job_id))


def submit_evaluation(conn: sqlite3.Connection, choices: pipeline.Choices, tests: list[TestCase]) -> int:
    """Create the run and its job, and queue it; return the job id. A run that would be refused (not indexed,
    over budget, a held-out prompt not evaluated on dev) raises here, before any run or job is stored."""
    if indexes.lookup(conn, choices.stack, choices.chunk_set_id) is None:
        raise KeyError(f"{choices.chunk_set_id} is not indexed on Stack {choices.stack}")
    run_id = pipeline.start_run(conn, choices, tests)
    job_id = insert(conn, "jobs", {"kind": "evaluate", "run_id": run_id})
    executor.submit(evaluate, job_id, run_id)
    return job_id


def evaluate(job_id: int, run_id: int) -> None:
    """Run one evaluation in the worker thread, with the thread's own connection, so every paid call made here is
    recorded (the spend listener is set inside `execute`, in this thread)."""
    conn = store.connect()
    try:
        set_status(conn, job_id, "running")
        pipeline.execute(conn, run_id, indexes.retriever(conn, runs.get_run(conn, run_id).meta))
        set_status(conn, job_id, "done")
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        if runs.get_run(conn, run_id).status == "running":
            runs.finish_run(conn, run_id, error=error)
        set_status(conn, job_id, "failed", error)
    finally:
        conn.close()


def get_job(conn: sqlite3.Connection, job_id: int) -> Job:
    """The job with its run's progress; KeyError if it does not exist."""
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise KeyError(job_id)
    run = runs.run_row(conn, row["run_id"])
    total = len(json.loads(run["test_ids"]))
    return Job(id=row["id"], kind=row["kind"], status=row["status"], run_id=row["run_id"],
               progress=run["done"] / total, message=f"{run['done']} of {total} questions", error=row["error"])


def recover_interrupted(conn: sqlite3.Connection) -> int:
    """Mark jobs and runs a previous process left unfinished as failed; return how many jobs were marked."""
    left = conn.execute("SELECT id, run_id FROM jobs WHERE status IN ('queued', 'running')").fetchall()
    for job_id, run_id in left:
        if runs.get_run(conn, run_id).status == "running":
            runs.finish_run(conn, run_id, error=INTERRUPTED)
        set_status(conn, job_id, "failed", INTERRUPTED)
    return len(left)
