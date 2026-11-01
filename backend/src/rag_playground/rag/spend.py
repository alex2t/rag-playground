"""Spend: paid OpenRouter calls recorded one by one (T44) plus Stack A's search fees (T53); the budget (D15) is checked
against the total."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from threading import Lock

from rag_playground.llm.openrouter import ChatResult, cost_listener
from rag_playground.rag.runs import insert
from rag_playground.settings import STACK_A_SEARCH_USD

SEARCH_ROW = "openai/vector-store-search"  # the `model` of a spend row holding a search fee, not an LLM call (T54)


def record(conn: sqlite3.Connection, run_id: int | None, result: ChatResult) -> None:
    """Store one paid call with its tokens and cost."""
    insert(conn, "spend", {"run_id": run_id, "model": result.model, "prompt_tokens": result.prompt_tokens,
                           "completion_tokens": result.completion_tokens,
                           "reasoning_tokens": result.reasoning_tokens, "cost_usd": result.cost_usd})


def search_fee(stack: str) -> float:
    """OpenAI's fee for one question's search (T53); one search per question, with or without the reranker."""
    return STACK_A_SEARCH_USD if stack == "A" else 0.0


def record_search(conn: sqlite3.Connection, stack: str) -> None:
    """Store the fee of a search outside any run (T54); inside a run, stored results count it, so never call this
    there. A stack with no fee stores nothing."""
    if search_fee(stack):
        insert(conn, "spend", {"run_id": None, "model": SEARCH_ROW, "prompt_tokens": 0, "completion_tokens": 0,
                               "reasoning_tokens": 0, "cost_usd": search_fee(stack)})


@contextmanager
def recording(conn: sqlite3.Connection, run_id: int | None) -> Iterator[None]:
    """Record every paid call made inside the block, each as soon as it returns. Questions in parallel share the
    connection, so one write at a time."""
    lock = Lock()

    def listen(result: ChatResult) -> None:
        with lock:
            record(conn, run_id, result)

    token = cost_listener.set(listen)
    try:
        yield
    finally:
        cost_listener.reset(token)


def total(conn: sqlite3.Connection, run_id: int | None = None) -> float:
    """Dollars spent, by one run or (run_id None) in total, Stack A's search fees included."""
    if run_id is None:
        calls = conn.execute("SELECT coalesce(sum(cost_usd), 0) FROM spend").fetchone()[0]
        searches = conn.execute("SELECT count(*) FROM results JOIN runs ON runs.id = run_id WHERE stack = 'A'").fetchone()[0]
    else:
        calls = conn.execute("SELECT coalesce(sum(cost_usd), 0) FROM spend WHERE run_id = ?", (run_id,)).fetchone()[0]
        searches = conn.execute("SELECT count(*) FROM results JOIN runs ON runs.id = run_id "
                                "WHERE stack = 'A' AND run_id = ?", (run_id,)).fetchone()[0]
    return calls + searches * STACK_A_SEARCH_USD
