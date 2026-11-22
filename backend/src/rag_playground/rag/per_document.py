"""At most a few chunks per document (decision.md T59): the top K are taken from a longer candidate list, so that
a question needing two documents is not answered from one document's chunks only."""

from rag_playground.stacks.hits import Hit


def limit_per_document(hits: list[Hit], k: int, limit: int) -> list[Hit]:
    """The first `k` hits in rank order, skipping a hit once its document already has `limit` hits kept."""
    kept, counts = [], {}
    for hit in hits:
        if counts.get(hit.source, 0) < limit:
            kept.append(hit)
            counts[hit.source] = counts.get(hit.source, 0) + 1
        if len(kept) == k:
            break
    return kept
