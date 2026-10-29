"""Evaluation runs and their per-question results, with the reproducibility metadata (plan.md, T36, T40)."""

import json
import sqlite3
from dataclasses import asdict, dataclass, fields

from rag_playground.scoring.judging import Judgement
from rag_playground.stacks.hits import Hit


@dataclass(frozen=True)
class RunMeta:
    """Every setting and version a run needs to be reproduced, including the exact questions it asks, in order.
    Unused options are None (Stack B has no OpenAI ranking; a run without reranking has no reranker)."""

    stack: str
    split: str
    test_ids: list[str]
    chunk_set_id: str
    top_k: int
    hybrid: bool
    openai_ranking: dict | None
    answer_model: str
    answer_slug: str
    judge_model: str
    judge_slug: str
    rerank_model: str | None
    rerank_slug: str | None
    rerank_candidates: int | None
    temperature_controlled: bool
    prompt_name: str
    prompt_sha256: str
    dataset_sha256: str
    app_version: str


@dataclass(frozen=True)
class Run:
    """A stored run: its id, date (UTC), status, error if it failed, and metadata."""

    id: int
    created_at: str
    status: str
    error: str | None
    meta: RunMeta


@dataclass(frozen=True)
class Result:
    """One answered and judged question: the chunks the answer model read, the verdict, cost and time."""

    test_id: str
    hits: list[Hit]
    rerank_repaired: bool | None
    answer: str
    judgement: Judgement
    cost_usd: float
    latency_s: float


def insert(conn: sqlite3.Connection, table: str, row: dict) -> int:
    """Insert one row and return its rowid."""
    sql = f"INSERT INTO {table} ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})"
    with conn:
        return conn.execute(sql, list(row.values())).lastrowid


def create_run(conn: sqlite3.Connection, meta: RunMeta) -> int:
    """Store a new run as "running" and return its id."""
    ranking = None if meta.openai_ranking is None else json.dumps(meta.openai_ranking)
    return insert(conn, "runs", asdict(meta) | {"openai_ranking": ranking, "test_ids": json.dumps(meta.test_ids)})


def add_result(conn: sqlite3.Connection, run_id: int, result: Result) -> None:
    """Store one question's result; only a question the run declared, and only once."""
    row = {"run_id": run_id} | asdict(result) | asdict(result.judgement)
    del row["judgement"]
    insert(conn, "results", row | {"hits": json.dumps([asdict(hit) for hit in result.hits])})


def finish_run(conn: sqlite3.Connection, run_id: int, error: str | None = None) -> None:
    """Mark a running run "done" (only with every result stored), or "failed" with the error message; KeyError if
    the run does not exist."""
    with conn:
        updated = conn.execute("UPDATE runs SET status = ?, error = ? WHERE id = ?",
                               ("failed" if error else "done", error, run_id)).rowcount
    if not updated:
        raise KeyError(run_id)


def run_row(conn: sqlite3.Connection, run_id: int) -> sqlite3.Row:
    """The run's row with its count of stored results; KeyError if the run does not exist."""
    row = conn.execute("SELECT *, (SELECT count(*) FROM results WHERE run_id = runs.id) AS done "
                       "FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise KeyError(run_id)
    return row


def progress(conn: sqlite3.Connection, run_id: int) -> float:
    """Share of the run's questions with a stored result, from 0.0 to 1.0."""
    row = run_row(conn, run_id)
    return row["done"] / len(json.loads(row["test_ids"]))


def get_run(conn: sqlite3.Connection, run_id: int) -> Run:
    """The stored run with its metadata; KeyError if it does not exist."""
    row = run_row(conn, run_id)
    ranking = row["openai_ranking"]
    meta = RunMeta(**{f.name: row[f.name] for f in fields(RunMeta)} | {
        "hybrid": bool(row["hybrid"]), "temperature_controlled": bool(row["temperature_controlled"]),
        "openai_ranking": None if ranking is None else json.loads(ranking), "test_ids": json.loads(row["test_ids"])})
    return Run(id=row["id"], created_at=row["created_at"], status=row["status"], error=row["error"], meta=meta)


def get_results(conn: sqlite3.Connection, run_id: int) -> list[Result]:
    """The run's results in the order they were stored."""
    rows = conn.execute("SELECT * FROM results WHERE run_id = ? ORDER BY rowid", (run_id,)).fetchall()
    return [to_result(row) for row in rows]


def to_result(row: sqlite3.Row) -> Result:
    """Rebuild a Result from its row (SQLite stores booleans as 0/1 and the chunks as JSON)."""
    judgement = Judgement(**{f.name: row[f.name] for f in fields(Judgement)} | {"refused": bool(row["refused"])})
    repaired = row["rerank_repaired"]
    return Result(test_id=row["test_id"], hits=[Hit(**h) for h in json.loads(row["hits"])],
                  rerank_repaired=None if repaired is None else bool(repaired), answer=row["answer"],
                  judgement=judgement, cost_usd=row["cost_usd"], latency_s=row["latency_s"])
