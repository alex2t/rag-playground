"""nomic-embed-text-v1.5 through fastembed for Stack B (D02)."""

from functools import cache

from fastembed import TextEmbedding

from rag_playground.settings import EMBED_MODEL

# nomic is trained with task prefixes; fastembed does not add them.
DOCUMENT_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "
# fastembed's default batch of 256 put a whole chunk set in one batch and needed ~15 GB (fix.md, 2026-10-27).
# 4 chunks of ~1,100 tokens peak at ~2 GB.
BATCH_SIZE = 4


@cache
def model() -> TextEmbedding:
    """Load the ONNX model once per process (downloads on first use)."""
    return TextEmbedding(EMBED_MODEL)


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed chunks with the document prefix."""
    return [v.tolist() for v in model().embed([DOCUMENT_PREFIX + t for t in texts], batch_size=BATCH_SIZE)]


def embed_query(text: str) -> list[float]:
    """Embed one query with the query prefix."""
    return next(iter(model().embed([QUERY_PREFIX + text]))).tolist()
