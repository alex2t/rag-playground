"""Thin client for the OpenAI Vector Store used by Stack A."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import cache

from openai import OpenAI

from rag_playground.chunking.chunk_sets import Chunk
from rag_playground.settings import settings

# T01: our splitter makes the chunks; one file per chunk, so OpenAI must not split again.
NO_RESPLIT = {"type": "static", "static": {"max_chunk_size_tokens": 4096, "chunk_overlap_tokens": 0}}
BATCH_SIZE = 500
UPLOAD_WORKERS = 8


@dataclass(frozen=True)
class Hit:
    """One search result; `attributes` holds the chunk ids set at upload."""

    filename: str
    score: float
    text: str
    attributes: dict | None = None


@cache
def client() -> OpenAI:
    """OpenAI SDK client for the OpenAI API itself."""
    return OpenAI(api_key=settings.openai_api_key)


def create_store(name: str) -> str:
    """Create an empty vector store and return its id."""
    return client().vector_stores.create(name=name, chunking_strategy=NO_RESPLIT).id


def upload_texts(store_id: str, texts: dict[str, str]) -> None:
    """Upload each text as its own file and wait until all are indexed."""
    files = [(name, text.encode()) for name, text in texts.items()]
    batch = client().vector_stores.file_batches.upload_and_poll(store_id, files=files, chunking_strategy=NO_RESPLIT)
    if batch.file_counts.completed != len(files):
        raise RuntimeError(f"vector store batch {batch.id}: {batch.file_counts}")


def upload_file(chunk: Chunk) -> str:
    """Upload one chunk's text as a file named after its chunk id."""
    name = chunk.chunk_id.replace("/", "__").replace("#", "__") + ".md"
    return client().files.create(file=(name, chunk.text.encode()), purpose="assistants").id


def chunk_attributes(chunk: Chunk) -> dict:
    return {"chunk_id": chunk.chunk_id, "source": chunk.source, "doc_type": chunk.doc_type}


def upload_chunks(store_id: str, chunks: list[Chunk]) -> int:
    """Upload each chunk as its own file with its ids as attributes; return the number of files indexed."""
    with ThreadPoolExecutor(UPLOAD_WORKERS) as pool:
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


def search(store_id: str, query: str, k: int, ranking_options: dict | None = None) -> list[Hit]:
    """Return the top-k hits for a query, with query rewriting off. `ranking_options` is sent as is, because
    the SDK types lack `hybrid_search` although the API accepts it (checked live on 2026-10-27)."""
    extra = {"ranking_options": ranking_options} if ranking_options else None
    page = client().vector_stores.search(store_id, query=query, max_num_results=k, rewrite_query=False,
                                         extra_body=extra)
    return [Hit(r.filename, r.score, "".join(c.text for c in r.content), r.attributes) for r in page.data]


def delete_store(store_id: str) -> None:
    """Delete the store and its files (deleting a store alone keeps the files)."""
    for f in client().vector_stores.files.list(store_id):
        client().files.delete(f.id)
    client().vector_stores.delete(store_id)
