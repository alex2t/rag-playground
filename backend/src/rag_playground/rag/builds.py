"""Preparing a chunk set on a stack (D29): what a build would cost, the work itself, and what is built. The Build
page and the ladder build the same way."""

import sqlite3

from rag_playground.chunking.chunk_sets import METHOD as FIXED_METHOD
from rag_playground.chunking.chunk_sets import chunk_set_id, chunk_settings, load_or_build
from rag_playground.chunking.enrichment import set_id_for
from rag_playground.datasets.schema import TestCase
from rag_playground.rag import enrich_run, pipeline, prompts
from rag_playground.rag import estimate as pricing
from rag_playground.stacks import indexes


def enrichment_cost(method: str, size: int, overlap: int) -> float:
    """What is left to pay to enrich a chunk set; both stacks share the enriched set, so it is paid once (T47)."""
    if method == FIXED_METHOD:
        return 0.0
    load_or_build(size, overlap)
    return enrich_run.remaining_cost(chunk_set_id(size, overlap))


def estimate(conn: sqlite3.Connection, method: str, size: int, overlap: int) -> dict:
    """A build's chunk set, its chunk count, what enriching it would still cost, where it is built already, and what
    is left of the budget. Splitting is local and free, so the base chunk set is saved here. Stack A's index build is
    not counted (T44)."""
    chunks = load_or_build(size, overlap)
    set_id = set_id_for(method, size, overlap)
    return {"chunk_set_id": set_id, "chunks": len(chunks), "enrichment_usd": enrichment_cost(method, size, overlap),
            "built": [stack for stack in ("A", "B") if indexes.lookup(conn, stack, set_id)],
            "budget_left_usd": pipeline.remaining(conn)}


def run_cost(conn: sqlite3.Connection, choices: pipeline.Choices, tests: list[TestCase]) -> float:
    """A run's estimate (T43) before its chunks exist: answers read the original chunks, enriched or not (T47), so the
    base split prices it. Shared by the ladder and sweeps."""
    settings = chunk_settings(choices.chunk_set_id)
    chunks = load_or_build(settings["chunk_size"], settings["overlap"])
    return pricing.run_cost(tests, prompts.get(conn, choices.prompt_name), choices.answer_model, choices.top_k,
                            choices.rerank, chunks, choices.stack)


def check_budget(conn: sqlite3.Connection, method: str, size: int, overlap: int) -> None:
    """Refuse a build whose enrichment is estimated over what is left of BUDGET_USD, before anything is paid. A build
    with nothing to pay is never refused, even when spend has passed the budget."""
    cost, left = enrichment_cost(method, size, overlap), pipeline.remaining(conn)
    if cost > 0 and cost > left:
        raise pipeline.BudgetExceeded(f"Enrichment is estimated at ${cost:.4f}, but only ${left:.4f} of the budget is left")


def prepare(conn: sqlite3.Connection, stack: str, method: str, size: int, overlap: int) -> str:
    """Build what a stack needs and does not have yet: the chunk set, its paid enrichment, the index. Return the set id."""
    load_or_build(size, overlap)
    if method != FIXED_METHOD:
        enrich_run.enrich_set(conn, chunk_set_id(size, overlap))
    set_id = set_id_for(method, size, overlap)
    if indexes.lookup(conn, stack, set_id) is None:
        indexes.build(conn, stack, set_id)
    return set_id


def built(conn: sqlite3.Connection) -> list[dict]:
    """Every chunk set built on a stack, newest first, with its settings."""
    rows = conn.execute("SELECT stack, chunk_set_id, chunk_count, created_at FROM indexes "
                        "ORDER BY created_at DESC, chunk_set_id, stack").fetchall()
    return [dict(row) | chunk_settings(row["chunk_set_id"]) for row in rows]
