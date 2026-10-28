"""Step 6 checks of the reranker (no network). `test_live_rerank.py` checks the real model."""

import pytest

from rag_playground.rag import rerank
from rag_playground.settings import RERANK_MODEL
from rag_playground.stacks.hits import Hit

HITS = [Hit(f"doc{i}.md#0", f"doc{i}.md", 1 - i / 10, f"Passage {i}.") for i in range(1, 5)]


def fake_model(monkeypatch, ranking: list[int]) -> list:
    """Make the reranker model return `ranking`; collect the calls it receives."""
    calls = []

    def chat_structured(model, messages, schema):
        calls.append((model, messages, schema))
        return rerank.Ranking(ranking=ranking), "usage"

    monkeypatch.setattr(rerank, "chat_structured", chat_structured)
    return calls


def test_the_reranker_returns_the_same_chunks_in_the_models_order(monkeypatch):
    calls = fake_model(monkeypatch, [3, 1, 4, 2])
    out = rerank.rerank("Q?", HITS, k=4)
    assert out.hits == [HITS[2], HITS[0], HITS[3], HITS[1]]
    assert sorted(h.chunk_id for h in out.hits) == sorted(h.chunk_id for h in HITS)
    assert out.result == "usage"
    assert not out.repaired
    assert calls == [(RERANK_MODEL, rerank.rerank_messages("Q?", HITS), rerank.Ranking)]


def test_only_the_top_k_of_the_new_order_are_kept(monkeypatch):
    fake_model(monkeypatch, [4, 2, 1, 3])
    assert rerank.rerank("Q?", HITS, k=2).hits == [HITS[3], HITS[1]]


def test_k_larger_than_the_candidates_keeps_them_all(monkeypatch):
    """A score threshold (T40) can return fewer candidates than K."""
    fake_model(monkeypatch, [2, 1, 4, 3])
    assert rerank.rerank("Q?", HITS, k=10).hits == [HITS[1], HITS[0], HITS[3], HITS[2]]


@pytest.mark.parametrize("hits", [[], HITS[:1]])
def test_zero_or_one_candidate_is_returned_without_calling_the_model(monkeypatch, hits):
    """There is nothing to order, so no cost and no repair can be recorded."""
    calls = fake_model(monkeypatch, [1])
    assert rerank.rerank("Q?", hits, k=5) == rerank.Reranked(hits, None, repaired=False)
    assert calls == []


@pytest.mark.parametrize("ranking, expected", [
    ([3, 3, 1, 4, 2], [3, 1, 4, 2]),  # duplicate dropped
    ([3, 9, 0, -1, 1, 4, 2], [3, 1, 4, 2]),  # unknown numbers dropped
    ([4, 2], [4, 2, 1, 3]),  # missing passages appended in retrieved order
    ([], [1, 2, 3, 4]),  # nothing usable: retrieved order kept
])
def test_an_invalid_ranking_is_completed_as_in_rankgpt_and_flagged(monkeypatch, ranking, expected):
    fake_model(monkeypatch, ranking)
    out = rerank.rerank("Q?", HITS, k=4)
    assert out.hits == [HITS[n - 1] for n in expected]
    assert out.repaired


def test_messages_hold_the_question_and_numbered_texts_but_no_source_paths():
    system, user = rerank.rerank_messages("What is the price?", HITS[:2])
    assert system == {"role": "system", "content": rerank.INSTRUCTIONS}
    assert user["content"] == "QUESTION:\nWhat is the price?\n\nPASSAGES:\n[1] Passage 1.\n\n[2] Passage 2."
    assert "doc1.md" not in user["content"]
