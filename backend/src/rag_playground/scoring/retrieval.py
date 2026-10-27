"""Retrieval metrics on gold source documents (T06, T17). `sources` are the retrieved chunks' source
documents in rank order. K is the run setting, not len(sources): Stack A can return fewer than K chunks
when the user sets a score threshold (T40). A chunk is relevant if its source is a gold document."""

import math
from dataclasses import dataclass
from statistics import mean

from rag_playground.chunking.chunk_sets import Chunk
from rag_playground.datasets.schema import Category, TestCase
from rag_playground.stacks.hits import Hit


@dataclass(frozen=True)
class RetrievalScores:
    """One question's retrieval scores."""

    mrr: float
    recall: float
    ndcg: float
    hit: float
    keyword_recall: float


def reciprocal_rank(sources: list[str], gold: list[str]) -> float:
    """1 / rank of the first chunk from any gold document; 0 if none is retrieved (Voorhees, 1999)."""
    return next((1 / rank for rank, s in enumerate(sources, 1) if s in gold), 0.0)


def recall(sources: list[str], gold: list[str]) -> float:
    """Gold documents found / gold documents."""
    return len(set(gold) & set(sources)) / len(gold)


def hit(sources: list[str], gold: list[str]) -> float:
    return float(any(s in gold for s in sources))


def dcg(relevance: list[int]) -> float:
    return sum(rel / math.log2(rank + 1) for rank, rel in enumerate(relevance, 1))


def ndcg(sources: list[str], gold: list[str], k: int, relevant_in_index: int) -> float:
    """DCG / ideal DCG with binary chunk relevance (Jarvelin & Kekalainen, 2002). The ideal ranking puts
    the index's relevant chunks first, so it holds min(k, relevant_in_index) relevant chunks."""
    ideal = dcg([1] * min(k, relevant_in_index))
    return dcg([int(s in gold) for s in sources]) / ideal


def keyword_recall(texts: list[str], keywords: list[str]) -> float:
    """Keywords found in the retrieved text / keywords, ignoring case (secondary cross-check)."""
    joined = "\n".join(texts).lower()
    return sum(k.lower() in joined for k in keywords) / len(keywords)


def relevant_in_index(chunks: list[Chunk], gold: list[str]) -> int:
    """Number of chunks in the chunk set that come from a gold document."""
    return sum(c.source in gold for c in chunks)


def score_question(test: TestCase, hits: list[Hit], k: int, chunks: list[Chunk]) -> RetrievalScores:
    """Retrieval scores of one answerable question."""
    sources, gold = [h.source for h in hits], test.source_docs
    return RetrievalScores(mrr=reciprocal_rank(sources, gold), recall=recall(sources, gold),
                           ndcg=ndcg(sources, gold, k, relevant_in_index(chunks, gold)), hit=hit(sources, gold),
                           keyword_recall=keyword_recall([h.text for h in hits], test.keywords))


def score_run(tests: list[TestCase], hits_by_test: dict[str, list[Hit]], k: int,
              chunks: list[Chunk]) -> dict[str, float]:
    """Mean retrieval scores over the answerable questions; unanswerable ones have no gold documents."""
    scores = [score_question(t, hits_by_test[t.id], k, chunks) for t in tests if t.category != Category.UNANSWERABLE]
    return {name: mean(getattr(s, name) for s in scores) for name in RetrievalScores.__dataclass_fields__}
