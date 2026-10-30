"""Paid enrichment of a chunk set under BUDGET_USD (T47): the estimate, the refusal before it starts, the stop at the
cap, and one spend row per call (T44), outside any run."""

import sqlite3

from rag_playground.chunking import enrichment
from rag_playground.chunking.chunk_sets import Chunk
from rag_playground.rag import estimate, pipeline, spend
from rag_playground.settings import ENRICH_MODEL, settings

OUTPUT_TOKENS = 80  # assumed reply length, not measured yet (T47)


def chunk_cost(chunk: Chunk, document: str) -> float:
    """Estimated dollars for one chunk: its real input tokens and the assumed reply length."""
    return estimate.price(ENRICH_MODEL, estimate.count(enrichment.messages(chunk, document)), OUTPUT_TOKENS)


def remaining_cost(base_id: str) -> float:
    """Estimated dollars for the chunks not paid for yet."""
    return sum(chunk_cost(chunk, document) for chunk, document in enrichment.progress(base_id)[1])


def enrich_set(conn: sqlite3.Connection, base_id: str) -> list[enrichment.EnrichedChunk]:
    """Enrich a saved chunk set. A build estimated over what is left of BUDGET_USD is refused before any paid call;
    during the build, the next chunk is sent only if it fits. A stop keeps every chunk already paid for."""
    cost = remaining_cost(base_id)
    if cost > pipeline.remaining(conn):
        raise pipeline.BudgetExceeded(f"Enrichment is estimated at ${cost:.4f}, but only "
                                      f"${pipeline.remaining(conn):.4f} of BUDGET_USD ${settings.budget_usd:.2f} is left")
    with spend.recording(conn, None):
        return enrichment.load_or_enrich(
            base_id, lambda chunk, document: pipeline.check_budget(conn, chunk_cost(chunk, document)))
