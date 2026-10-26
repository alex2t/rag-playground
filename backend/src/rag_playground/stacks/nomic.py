"""nomic-embed-text-v1.5 through fastembed for Stack B (D02)."""

from functools import cache

from fastembed import TextEmbedding

from rag_playground.settings import EMBED_MODEL

# nomic is trained with task prefixes; fastembed does not add them.
DOCUMENT_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "


@cache
def model() -> TextEmbedding:
    """Load the ONNX model once per process (downloads on first use)."""
    return TextEmbedding(EMBED_MODEL)


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed chunks with the document prefix."""
    return [v.tolist() for v in model().embed([DOCUMENT_PREFIX + t for t in texts])]


def embed_query(text: str) -> list[float]:
    """Embed one query with the query prefix."""
    return next(iter(model().embed([QUERY_PREFIX + text]))).tolist()
