"""Which index holds each chunk set on each stack, and the search function a run uses (plan.md section 5)."""

import sqlite3
from collections.abc import Callable

from rag_playground.chunking.chunk_sets import Chunk, load as load_chunk_set
from rag_playground.rag.runs import RunMeta, insert
from rag_playground.settings import settings
from rag_playground.stacks import openai_vector_store, qdrant_store
from rag_playground.stacks.hits import Hit

Retrieve = Callable[[str, int], list[Hit]]


def build_stack_a(chunk_set_id: str, chunks: list[Chunk]) -> str:
    """A new vector store holding every chunk; deleted again if the upload fails, so no paid store is left over."""
    store_id = openai_vector_store.create_store(f"rag-playground-{settings.app_env}-{chunk_set_id}")
    try:
        openai_vector_store.upload_chunks(store_id, chunks)
    except Exception:
        openai_vector_store.delete_store(store_id)
        raise
    return store_id


def build_stack_b(chunk_set_id: str, chunks: list[Chunk]) -> str:
    """A Qdrant collection named after the chunk set, holding every chunk."""
    stored = qdrant_store.index_chunks(qdrant_store.client(), chunk_set_id, chunks)
    if stored != len(chunks):
        raise RuntimeError(f"Qdrant stored {stored} of {len(chunks)} chunks of {chunk_set_id}")
    return chunk_set_id


def build(conn: sqlite3.Connection, stack: str, chunk_set_id: str) -> str:
    """Index a saved chunk set on one stack and record where; an index that already exists is refused."""
    if lookup(conn, stack, chunk_set_id):
        raise ValueError(f"{chunk_set_id} is already indexed on Stack {stack}")
    chunks = load_chunk_set(chunk_set_id)
    ref = (build_stack_a if stack == "A" else build_stack_b)(chunk_set_id, chunks)
    insert(conn, "indexes", {"stack": stack, "chunk_set_id": chunk_set_id, "ref": ref, "chunk_count": len(chunks)})
    return ref


def lookup(conn: sqlite3.Connection, stack: str, chunk_set_id: str) -> str | None:
    """The index reference of a chunk set on a stack, or None if it was never indexed there."""
    row = conn.execute("SELECT ref FROM indexes WHERE stack = ? AND chunk_set_id = ?", (stack, chunk_set_id)).fetchone()
    return row[0] if row else None


def retriever(conn: sqlite3.Connection, meta: RunMeta) -> Retrieve:
    """Search the run's own index with its stored settings; KeyError if its chunk set is not indexed."""
    ref = lookup(conn, meta.stack, meta.chunk_set_id)
    if ref is None:
        raise KeyError(f"{meta.chunk_set_id} is not indexed on Stack {meta.stack}")
    if meta.stack == "A":
        ranking = openai_vector_store.Ranking(**meta.openai_ranking)
        return lambda question, k: openai_vector_store.search(ref, question, k, ranking)
    return lambda question, k: qdrant_store.search(qdrant_store.client(), ref, question, k, meta.hybrid)
