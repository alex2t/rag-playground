"""Spend recorded per paid OpenRouter call (T44); the budget (D15) is checked against its total."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from rag_playground.llm.openrouter import ChatResult, cost_listener
from rag_playground.rag.runs import insert


def record(conn: sqlite3.Connection, run_id: int | None, result: ChatResult) -> None:
    """Store one paid call with its tokens and cost."""
    insert(conn, "spend", {"run_id": run_id, "model": result.model, "prompt_tokens": result.prompt_tokens,
                           "completion_tokens": result.completion_tokens,
                           "reasoning_tokens": result.reasoning_tokens, "cost_usd": result.cost_usd})


@contextmanager
def recording(conn: sqlite3.Connection, run_id: int | None) -> Iterator[None]:
    """Record every paid call made inside the block, each as soon as it returns."""
    token = cost_listener.set(lambda result: record(conn, run_id, result))
    try:
        yield
    finally:
        cost_listener.reset(token)


def total(conn: sqlite3.Connection, run_id: int | None = None) -> float:
    """Dollars spent, by one run or (run_id None) in total."""
    if run_id is None:
        return conn.execute("SELECT coalesce(sum(cost_usd), 0) FROM spend").fetchone()[0]
    return conn.execute("SELECT coalesce(sum(cost_usd), 0) FROM spend WHERE run_id = ?", (run_id,)).fetchone()[0]
