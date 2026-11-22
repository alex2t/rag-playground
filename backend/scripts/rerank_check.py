"""Reranker diagnosis (fix.md, 2026-11-22): re-rank a few dev questions on Stack B and print the model's raw ranking
beside the positions of the gold-document chunks, to tell a weak model from a bug in how its ranking is applied.

Same set-up as run 37: Stack B, chunk set fixed__c400__o78, plain vector search, 20 candidates, top 2 kept.
Paid: one reranker call per question (gpt-4.1-nano, well under $0.01 in all), not counted in `spend`. Run by the user.
Usage: uv run python scripts/rerank_check.py <test id> [<test id> ...]
"""

import sys

from rag_playground import store
from rag_playground.datasets.schema import load_tests
from rag_playground.llm.openrouter import chat_structured
from rag_playground.rag.rerank import Ranking, complete_ranking, rerank_messages
from rag_playground.settings import RERANK_CANDIDATES, RERANK_MODEL
from rag_playground.stacks import indexes, qdrant_store

CHUNK_SET = "fixed__c400__o78"
TOP_K = 2


def check(test, ref: str) -> float:
    """Print one question's diagnosis and return the call's cost."""
    hits = qdrant_store.search(qdrant_store.client(), ref, test.question, RERANK_CANDIDATES)
    gold = [n for n, hit in enumerate(hits, 1) if hit.source in test.source_docs]
    ranking, result = chat_structured(RERANK_MODEL, rerank_messages(test.question, hits), Ranking)
    order = complete_ranking(ranking.ranking, len(hits))
    kept = order[:TOP_K]
    print(f"{test.id}: {test.question}")
    print(f"  candidates {len(hits)}; gold chunks at retrieved positions {gold}")
    print(f"  model ranking ({len(ranking.ranking)} numbers): {ranking.ranking}")
    print(f"  completed order: {order}")
    print(f"  kept {kept}; gold kept: {any(n in gold for n in kept)}; cost ${result.cost_usd:.5f}")
    return result.cost_usd


def main(test_ids: list[str]) -> None:
    tests = {t.id: t for t in load_tests()}
    ref = indexes.require(store.connect(), "B", CHUNK_SET)
    total = sum(check(tests[test_id], ref) for test_id in test_ids)
    print(f"total cost ${total:.5f}")


if __name__ == "__main__":
    main(sys.argv[1:])
