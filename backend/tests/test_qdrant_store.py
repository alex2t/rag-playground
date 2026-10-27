"""Step 4 checks for Stack B on the S0 chunk set, in Qdrant's in-process mode (no server, no paid API)."""

import pytest
from qdrant_client import QdrantClient

from rag_playground.chunking.chunk_sets import chunk_set_id, load_or_build
from rag_playground.datasets.schema import load_tests
from rag_playground.stacks import qdrant_store

SIZE, OVERLAP = 1024, 200
NAME = chunk_set_id(SIZE, OVERLAP)


@pytest.fixture(scope="module")
def chunks():
    return load_or_build(SIZE, OVERLAP)


@pytest.fixture(scope="module")
def q(chunks):
    client = QdrantClient(":memory:")
    qdrant_store.index_chunks(client, NAME, chunks)
    return client


def gold_test(test_id: str):
    return next(t for t in load_tests() if t.id == test_id)


def test_stores_one_point_per_chunk(q, chunks):
    assert q.count(NAME, exact=True).count == len(chunks)


def test_point_id_is_stable_and_distinct():
    assert qdrant_store.point_id("a.md#0") == qdrant_store.point_id("a.md#0")
    assert qdrant_store.point_id("a.md#0") != qdrant_store.point_id("a.md#1")


def test_returned_text_is_the_stored_chunk_text(q, chunks):
    by_id = {c.chunk_id: c.text for c in chunks}
    hits = qdrant_store.search(q, NAME, "How do I roll back a production deployment?", k=5)
    assert len(hits) == 5
    assert all(h.text == by_id[h.chunk_id] for h in hits)


@pytest.mark.parametrize("hybrid", [False, True])
def test_known_question_returns_its_gold_document_in_top_5(q, hybrid):
    t = gold_test("exact_term-001")
    hits = qdrant_store.search(q, NAME, t.question, k=5, hybrid=hybrid)
    assert t.source_docs[0] in [h.source for h in hits]


def test_hybrid_returns_the_one_chunk_holding_the_exact_string(q, chunks):
    """`sf org login jwt` occurs in exactly one chunk of this set."""
    holders = [c.chunk_id for c in chunks if "sf org login jwt" in c.text]
    assert len(holders) == 1
    hits = qdrant_store.search(q, NAME, gold_test("exact_term-001").question, k=5, hybrid=True)
    assert holders[0] in [h.chunk_id for h in hits]


def test_hybrid_ranks_a_rare_code_first_where_only_bm25_can_see_it():
    """BM25 matches a made-up code exactly, so hybrid search ranks the one chunk holding it first."""
    client = QdrantClient(":memory:")
    texts = ["Deployment failed with error code QX7Z-4471 in the sandbox.",
             "Deployment failed with a permissions error in the sandbox.",
             "Deployment failed with a timeout error in the sandbox."]
    chunks = [load_or_build(SIZE, OVERLAP)[0].model_copy(update={"chunk_id": f"t.md#{i}", "text": t})
              for i, t in enumerate(texts)]
    qdrant_store.index_chunks(client, "t", chunks)
    assert qdrant_store.search(client, "t", "QX7Z-4471", k=1, hybrid=True)[0].chunk_id == "t.md#0"
