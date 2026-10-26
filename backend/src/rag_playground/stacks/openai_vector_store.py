"""Thin client for the OpenAI Vector Store used by Stack A."""

from dataclasses import dataclass
from functools import cache

from openai import OpenAI

from rag_playground.settings import settings

# T01: our splitter makes the chunks; one file per chunk, so OpenAI must not split again.
NO_RESPLIT = {"type": "static", "static": {"max_chunk_size_tokens": 4096, "chunk_overlap_tokens": 0}}


@dataclass(frozen=True)
class Hit:
    """One search result."""

    filename: str
    score: float
    text: str


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


def search(store_id: str, query: str, k: int) -> list[Hit]:
    """Return the top-k hits for a query."""
    page = client().vector_stores.search(store_id, query=query, max_num_results=k)
    return [Hit(r.filename, r.score, "".join(c.text for c in r.content)) for r in page.data]


def delete_store(store_id: str) -> None:
    """Delete the store and its files (deleting a store alone keeps the files)."""
    for f in client().vector_stores.files.list(store_id):
        client().files.delete(f.id)
    client().vector_stores.delete(store_id)
