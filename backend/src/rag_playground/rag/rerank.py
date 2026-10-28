"""LLM reranker (decision.md T21): `gpt-4.1-nano` reorders the retrieved candidates and the top K are kept.

A listwise ranking as in RankGPT (Sun et al., 2023). An invalid ranking is completed the way RankGPT's
`receive_permutation` does it: duplicates and unknown numbers are dropped, missing passages are appended in
their retrieved order. Every completed ranking is flagged, so a model that often fails cannot hide it."""

from dataclasses import dataclass

from pydantic import BaseModel

from rag_playground.llm.openrouter import ChatResult, chat_structured
from rag_playground.scoring.judging import numbered
from rag_playground.settings import RERANK_MODEL
from rag_playground.stacks.hits import Hit

INSTRUCTIONS = """You rank passages by how useful they are for answering a question.
You receive a question and numbered passages.
Return every passage number exactly once, ordered from the most useful passage to the least useful."""


class Ranking(BaseModel):
    """Passage numbers, most useful first."""

    ranking: list[int]


@dataclass(frozen=True)
class Reranked:
    """The top K chunks in their new order, the call's usage (None if no call was needed), and whether the
    ranking had to be completed."""

    hits: list[Hit]
    result: ChatResult | None
    repaired: bool


def rerank_messages(question: str, hits: list[Hit]) -> list[dict]:
    """The question and the chunk texts numbered in retrieved order (no source paths, as for the answer)."""
    return [
        {"role": "system", "content": INSTRUCTIONS},
        {"role": "user", "content": f"QUESTION:\n{question}\n\nPASSAGES:\n{numbered([hit.text for hit in hits])}"},
    ]


def complete_ranking(ranking: list[int], count: int) -> list[int]:
    """A full 1-based order of `count` passages: valid first mentions, then the missing ones in retrieved order."""
    order = list(dict.fromkeys(n for n in ranking if 1 <= n <= count))
    return order + [n for n in range(1, count + 1) if n not in order]


def rerank(question: str, hits: list[Hit], k: int) -> Reranked:
    """Reorder the candidates with the reranker model and keep the top `k`. Zero or one candidate has only one
    order, so no call is made (a score threshold, T40, can leave that few)."""
    if len(hits) <= 1:
        return Reranked(hits[:k], None, repaired=False)
    ranking, result = chat_structured(RERANK_MODEL, rerank_messages(question, hits), Ranking)
    order = complete_ranking(ranking.ranking, len(hits))
    return Reranked([hits[n - 1] for n in order][:k], result, repaired=order != ranking.ranking)
