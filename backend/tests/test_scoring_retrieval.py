"""Step 5 checks for the retrieval metrics, with hand-built inputs and hand-computed values."""

import math

import pytest

from rag_playground.chunking.chunk_sets import Chunk
from rag_playground.datasets import schema
from rag_playground.scoring import retrieval as r
from rag_playground.stacks.hits import Hit

G1, G2, X = "clients/g1.md", "services/g2.md", "other.md"


@pytest.mark.parametrize("sources, expected", [([G1, X, X], 1.0), ([X, G1, X], 0.5), ([X, X, X], 0.0)])
def test_mrr_is_one_over_the_rank_of_the_first_gold_chunk(sources, expected):
    assert r.reciprocal_rank(sources, [G1]) == expected


def test_mrr_counts_only_the_first_gold_document_found():
    """Two gold documents first found at ranks 2 and 4: MRR is 1/2, not their average."""
    assert r.reciprocal_rank([X, G1, X, G2], [G1, G2]) == 0.5


def test_recall_is_half_when_one_of_two_gold_documents_is_retrieved():
    assert r.recall([G1, X, G1], [G1, G2]) == 0.5


def test_hit_is_one_if_any_gold_document_is_retrieved():
    assert r.hit([X, G2], [G1, G2]) == 1.0
    assert r.hit([X, X], [G1, G2]) == 0.0


def test_ndcg_is_one_with_relevant_chunks_on_top():
    assert r.ndcg([G1, G1, X], [G1], k=3, relevant_in_index=2) == 1.0


def test_ndcg_matches_the_worked_example_in_the_evaluation_doc():
    """Relevant chunks at positions 2, 3, 4 of 5, three relevant chunks in the index: 1.5616 / 2.1309."""
    expected = (1 / math.log2(3) + 1 / math.log2(4) + 1 / math.log2(5)) / (1 + 1 / math.log2(3) + 1 / math.log2(4))
    assert r.ndcg([X, G1, G1, G2, X], [G1, G2], k=5, relevant_in_index=3) == pytest.approx(expected)
    assert expected == pytest.approx(0.7328, abs=1e-4)


def test_ndcg_ideal_is_capped_at_k():
    """Ten relevant chunks in the index, K = 2, both retrieved chunks relevant: a perfect score."""
    assert r.ndcg([G1, G1], [G1], k=2, relevant_in_index=10) == 1.0


def test_ndcg_is_below_one_when_more_relevant_chunks_exist_than_were_retrieved():
    """One relevant chunk on top, K = 2, two relevant in the index: 1 / (1 + 1/log2(3))."""
    assert r.ndcg([G1, X], [G1], k=2, relevant_in_index=2) == pytest.approx(1 / (1 + 1 / math.log2(3)))


def test_keyword_recall_ignores_case_and_counts_each_keyword_once():
    assert r.keyword_recall(["Started on 2015-03-09", "the SF CLI"], ["2015-03-09", "sf cli", "absent"]) == 2 / 3


def chunk(source: str, i: int) -> Chunk:
    return Chunk(chunk_id=f"{source}#{i}", source=source, doc_type="x", index=i, text="t", tokens=1, start=0, end=1)


def test_relevant_in_index_counts_chunks_from_gold_documents():
    chunks = [chunk(G1, 0), chunk(G1, 1), chunk(G2, 0), chunk(X, 0)]
    assert r.relevant_in_index(chunks, [G1, G2]) == 3


def case(test_id: str, category: str, gold: list[str]) -> schema.TestCase:
    return schema.TestCase(id=test_id, question="q", reference_answer="a", category=category, source_docs=gold,
                           keywords=["t"], split="dev")


def hits(*sources: str) -> list[Hit]:
    return [Hit(f"{s}#0", s, 0.5, "t") for s in sources]


def test_unanswerable_tests_are_excluded_from_retrieval_means():
    chunks = [chunk(G1, 0), chunk(X, 0)]
    tests = [case("a", "direct_fact", [G1]), case("b", "direct_fact", [G1]), case("u", "unanswerable", [])]
    hits_by_test = {"a": hits(G1, X), "b": hits(X, X), "u": hits(X, X)}
    means = r.score_run(tests, hits_by_test, 2, chunks)
    assert means["mrr"] == 0.5 and means["hit"] == 0.5 and means["recall"] == 0.5
    assert means["ndcg"] == 0.5 and means["keyword_recall"] == 1.0


def test_ndcg_ideal_uses_the_requested_k_when_fewer_chunks_are_returned():
    """K = 5 asked, a score threshold let 1 chunk through, 3 relevant in the index: 1 / (1 + 1/log2(3) + 1/2)."""
    assert r.ndcg([G1], [G1], k=5, relevant_in_index=3) == pytest.approx(1 / (1 + 1 / math.log2(3) + 0.5))


def test_no_returned_chunks_score_zero_on_every_metric():
    scores = r.score_question(case("a", "direct_fact", [G1]), [], 5, [chunk(G1, 0)])
    assert scores == r.RetrievalScores(mrr=0.0, recall=0.0, ndcg=0.0, hit=0.0, keyword_recall=0.0)
