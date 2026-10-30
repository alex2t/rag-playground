"""Enrich one chunk set with the LLM and index it (ladder step S4, T47). Builds the base chunk set if it is missing,
prints the estimate, enriches the chunks not paid for yet, prints the recorded spend, then indexes each stack that does
not have the set yet. Run it again after a stop: it resumes and pays only for what is left.

Paid: OpenRouter (about $0.04 to $0.27 per chunk set), and on Stack A the OpenAI index build. Run by the user.
Usage: uv run python scripts/enrich.py <chunk size> <overlap in tokens> A|B|both
"""

import sys

from rag_playground import store
from rag_playground.chunking.chunk_sets import chunk_set_id, load_or_build
from rag_playground.chunking.enrichment import enriched_set_id
from rag_playground.rag import enrich_run, pipeline, spend
from rag_playground.settings import ENRICH_MODEL, settings
from rag_playground.stacks import indexes


def main(size: int, overlap: int, which: str) -> None:
    stacks = {"A": ["A"], "B": ["B"], "both": ["A", "B"]}[which]
    conn = store.connect()
    load_or_build(size, overlap)
    base_id = chunk_set_id(size, overlap)
    print(f"BUDGET_USD ${settings.budget_usd:.2f}, ${pipeline.remaining(conn):.4f} left; {ENRICH_MODEL}; "
          f"estimate for what is left of {base_id}: ${enrich_run.remaining_cost(base_id):.4f}", flush=True)
    before = spend.total(conn)
    enriched = enrich_run.enrich_set(conn, base_id)
    print(f"{len(enriched)} chunks enriched; recorded spend ${spend.total(conn) - before:.4f}", flush=True)
    set_id = enriched_set_id(base_id)
    for stack in stacks:
        if indexes.lookup(conn, stack, set_id) is None:
            print(f"Stack {stack}: indexing {set_id} ...", flush=True)
            indexes.build(conn, stack, set_id)
        print(f"Stack {stack}: {set_id} is indexed", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3])
