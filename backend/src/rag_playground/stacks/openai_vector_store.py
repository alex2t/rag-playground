"""Thin client for the OpenAI Vector Store used by Stack A."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import cache
from typing import Literal

from openai import OpenAI
from openai.types import VectorStoreSearchResponse

from rag_playground.chunking.chunk_sets import Chunk
from rag_playground.settings import settings
from rag_playground.stacks.hits import Hit

# T01: our splitter makes the chunks; one file per chunk, so OpenAI must not split again.
NO_RESPLIT = {"type": "static", "static": {"max_chunk_size_tokens": 4096, "chunk_overlap_tokens": 0}}
BATCH_SIZE = 500
WORKERS = 8


@dataclass(frozen=True)
class Ranking:
    """OpenAI search ranking, always chosen by the user (T12, T40). With ranker "auto" the weights have no
    measurable effect; with "none" the semantic and keyword lists are fused by RRF with these weights."""

    ranker: Literal["none", "auto"]
    embedding_weight: float
    text_weight: float
    score_threshold: float


@cache
def client() -> OpenAI:
    """OpenAI SDK client for the OpenAI API itself."""
    return OpenAI(api_key=settings.openai_api_key)


def create_store(name: str) -> str:
    """Create an empty vector store and return its id."""
    return client().vector_stores.create(name=name, chunking_strategy=NO_RESPLIT).id


def file_name(chunk: Chunk) -> str:
    """A neutral name, so the document path cannot act as a keyword match (Stack B indexes text only)."""
    return f"chunk_{uuid.uuid5(uuid.NAMESPACE_URL, chunk.chunk_id).hex}.md"


def upload_file(chunk: Chunk) -> str:
    """Upload the text search should read as its own file and return the file id."""
    return client().files.create(file=(file_name(chunk), chunk.indexed_text.encode()), purpose="assistants").id


def chunk_attributes(chunk: Chunk) -> dict:
    return {"chunk_id": chunk.chunk_id, "source": chunk.source, "doc_type": chunk.doc_type}


def upload_chunks(store_id: str, chunks: list[Chunk]) -> int:
    """Upload each chunk as its own file with its ids as attributes; return the number of files indexed."""
    with ThreadPoolExecutor(WORKERS) as pool:
        file_ids = list(pool.map(upload_file, chunks))
    completed = 0
    for i in range(0, len(chunks), BATCH_SIZE):
        files = [{"file_id": f, "attributes": chunk_attributes(c), "chunking_strategy": NO_RESPLIT}
                 for f, c in zip(file_ids[i:i + BATCH_SIZE], chunks[i:i + BATCH_SIZE])]
        batch = client().vector_stores.file_batches.create_and_poll(store_id, files=files)
        if batch.file_counts.completed != len(files):
            raise RuntimeError(f"vector store batch {batch.id}: {batch.file_counts}")
        completed += batch.file_counts.completed
    return completed


def ranking_body(ranking: Ranking) -> dict:
    """The `ranking_options` request body. Sent raw, because the SDK types lack `"none"` and `hybrid_search`
    although the API accepts both (checked live on 2026-10-27)."""
    return {"ranker": ranking.ranker, "score_threshold": ranking.score_threshold,
            "hybrid_search": {"embedding_weight": ranking.embedding_weight, "text_weight": ranking.text_weight}}


def to_hit(result: VectorStoreSearchResponse) -> Hit:
    return Hit(result.attributes["chunk_id"], result.attributes["source"], result.score,
               "".join(c.text for c in result.content))


def search(store_id: str, query: str, k: int, ranking: Ranking) -> list[Hit]:
    """Return the top-k chunks for a query, with query rewriting off."""
    page = client().vector_stores.search(store_id, query=query, max_num_results=k, rewrite_query=False,
                                         extra_body={"ranking_options": ranking_body(ranking)})
    return [to_hit(r) for r in page.data]


def delete_store(store_id: str) -> None:
    """Delete the store and its files (deleting a store alone keeps the files)."""
    file_ids = [f.id for f in client().vector_stores.files.list(store_id, limit=100)]
    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(client().files.delete, file_ids))
    client().vector_stores.delete(store_id)
