"""Step 4 checks for Stack A on the S0 chunk set, against the real OpenAI vector store (about $0.001).
Run with `uv run pytest -m live -k stack_a`. The Stack B counterparts are in `test_qdrant_store.py`."""

import pytest

from rag_playground.chunking.chunk_sets import load_or_build
from rag_playground.datasets.schema import load_tests
from rag_playground.stacks import openai_vector_store as store

pytestmark = pytest.mark.live

SIZE, OVERLAP = 1024, 200
# No built-in ranker, so Stack A is compared on the same terms as Stack B (T12).
RANKING = store.Ranking(ranker="none", embedding_weight=1.0, text_weight=1.0, score_threshold=0.0)


@pytest.fixture(scope="module")
def chunks():
    return load_or_build(SIZE, OVERLAP)


@pytest.fixture(scope="module")
def store_id(chunks):
    sid = store.create_store("rag-playground-step4-stack-a")
    try:
        store.upload_chunks(sid, chunks)
        yield sid
    finally:
        store.delete_store(sid)


def test_stack_a_stores_one_file_per_chunk(store_id, chunks):
    counts = store.client().vector_stores.retrieve(store_id).file_counts
    assert counts.completed == len(chunks) and counts.failed == 0


def gold_test():
    return next(t for t in load_tests() if t.id == "exact_term-001")


def test_stack_a_returns_the_known_question_gold_document_in_top_5(store_id):
    hits = store.search(store_id, gold_test().question, 5, RANKING)
    assert len(hits) == 5
    assert gold_test().source_docs[0] in [h.source for h in hits]


def test_stack_a_hybrid_returns_the_one_chunk_holding_the_exact_string(store_id, chunks):
    """`sf org login jwt` occurs in exactly one chunk of this set (same check as Stack B)."""
    holders = [c.chunk_id for c in chunks if "sf org login jwt" in c.text]
    assert len(holders) == 1
    hits = store.search(store_id, gold_test().question, 5, RANKING)
    assert holders[0] in [h.chunk_id for h in hits]


def test_stack_a_returns_the_stored_chunk_text(store_id, chunks):
    by_id = {c.chunk_id: c.text for c in chunks}
    hits = store.search(store_id, "How do I roll back a production deployment?", 5, RANKING)
    assert len(hits) == 5
    assert all(h.text == by_id[h.chunk_id] for h in hits)
