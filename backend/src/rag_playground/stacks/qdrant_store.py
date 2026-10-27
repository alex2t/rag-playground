"""Stack B: nomic dense vectors and BM25 sparse vectors in one Qdrant collection per chunk set (D02, T37)."""

import uuid
from functools import cache

from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient, models

from rag_playground.chunking.chunk_sets import Chunk
from rag_playground.settings import BM25_MODEL, EMBED_DIM, settings
from rag_playground.stacks import nomic
from rag_playground.stacks.hits import Hit

DENSE, SPARSE = "dense", "bm25"
# Candidates each list contributes to RRF in hybrid search (custom choice, see decision.md T37).
HYBRID_PREFETCH = 50


@cache
def client() -> QdrantClient:
    """Qdrant client for this environment, built on first use rather than at import."""
    return QdrantClient(url=settings.qdrant_url)


@cache
def bm25() -> SparseTextEmbedding:
    """Load the BM25 model once per process (downloads on first use)."""
    return SparseTextEmbedding(BM25_MODEL)


def point_id(chunk_id: str) -> str:
    """A stable Qdrant id derived from the chunk id, so re-indexing overwrites instead of duplicating."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def sparse(embedding) -> models.SparseVector:
    return models.SparseVector(indices=embedding.indices.tolist(), values=embedding.values.tolist())


def create_collection(q: QdrantClient, name: str) -> None:
    """Dense cosine vectors plus BM25 sparse vectors; Qdrant applies IDF at query time."""
    q.create_collection(name, vectors_config={DENSE: models.VectorParams(size=EMBED_DIM, distance=models.Distance.COSINE)},
                        sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)})


def index_chunks(q: QdrantClient, name: str, chunks: list[Chunk]) -> int:
    """Create the collection, store every chunk with both vectors, and return the stored count."""
    create_collection(q, name)
    texts = [c.text for c in chunks]
    dense = nomic.embed_documents(texts)
    points = [models.PointStruct(id=point_id(c.chunk_id), vector={DENSE: d, SPARSE: sparse(s)}, payload=c.model_dump())
              for c, d, s in zip(chunks, dense, bm25().embed(texts))]
    q.upload_points(name, points, wait=True)
    return q.count(name, exact=True).count


def to_hit(point: models.ScoredPoint) -> Hit:
    return Hit(point.payload["chunk_id"], point.payload["source"], point.score, point.payload["text"])


def search(q: QdrantClient, name: str, query: str, k: int, hybrid: bool = False) -> list[Hit]:
    """Top-k chunks by cosine similarity, or by RRF over the dense and BM25 rankings when `hybrid` is on."""
    dense = nomic.embed_query(query)
    if not hybrid:
        return [to_hit(p) for p in q.query_points(name, query=dense, using=DENSE, limit=k).points]
    prefetch = [models.Prefetch(query=dense, using=DENSE, limit=HYBRID_PREFETCH),
                models.Prefetch(query=sparse(next(iter(bm25().query_embed(query)))), using=SPARSE, limit=HYBRID_PREFETCH)]
    points = q.query_points(name, prefetch=prefetch, query=models.FusionQuery(fusion=models.Fusion.RRF), limit=k).points
    return [to_hit(p) for p in points]
