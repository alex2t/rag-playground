"""Step 6 checks of the cost estimate (T43), with hand-set prices (no network, no cost).

Each test prices one part only (one model, input or output), so each share of the estimate is checked alone."""

import json

import pytest
from llama_index.core.utils import get_tokenizer

from rag_playground.chunking.chunk_sets import Chunk
from rag_playground.datasets.schema import load_tests
from rag_playground.llm.models import ModelInfo
from rag_playground.rag import estimate
from rag_playground.rag.answer import answer_messages
from rag_playground.rag.prompts import DEFAULT_NAME, DEFAULT_TEXT, PromptVersion, sha256
from rag_playground.rag.rerank import rerank_messages
from rag_playground.scoring.judging import answer_messages as grade_messages
from rag_playground.scoring.judging import faithfulness_messages
from rag_playground.settings import JUDGE_MODEL, MAX_TOP_K, RERANK_CANDIDATES, RERANK_MODEL
from rag_playground.stacks.hits import Hit

TESTS = load_tests()[:3]
TEST = TESTS[0]
PROMPT = PromptVersion(DEFAULT_NAME, DEFAULT_TEXT, sha256(DEFAULT_TEXT))
ANSWER_MODEL = "openai/gpt-4.1-mini"  # not the reranker model, so the two can be priced apart
CHUNK_TOKENS = 200
MESSAGE_OVERHEAD = 4  # per chat message, OpenAI cookbook "How to count tokens with tiktoken"


def tokens(text: str) -> int:
    return len(get_tokenizer()(text))


def real_chunk(i: int) -> str:
    """A chunk text of exactly CHUNK_TOKENS tokens, different from the estimate's filler."""
    return f" chunk{i}" + " policy" * (CHUNK_TOKENS - 2)


def real_hits(k: int) -> list[Hit]:
    hits = [Hit(f"c{i}", f"doc{i}.md", 1.0, real_chunk(i)) for i in range(k)]
    assert all(tokens(h.text) == CHUNK_TOKENS for h in hits)
    return hits


def real_count(messages: list[dict]) -> int:
    return sum(tokens(m["content"]) + MESSAGE_OVERHEAD for m in messages)


@pytest.fixture
def prices(monkeypatch):
    """Set per-token prices: {(model, "in" | "out"): dollars}; every other price is 0."""
    table = {}

    def info(model_id):
        return ModelInfo(model_id, model_id, frozenset(), table.get((model_id, "in"), 0.0),
                         table.get((model_id, "out"), 0.0))

    monkeypatch.setattr(estimate, "model_info", info)
    return table


def cost(top_k: int = 3, rerank: bool = False, test=TEST) -> float:
    return estimate.question_cost(test, PROMPT, ANSWER_MODEL, top_k, rerank, CHUNK_TOKENS)


def test_the_filler_has_exactly_the_requested_tokens():
    assert [tokens(estimate.filler(n)) for n in (1, 37, 500)] == [1, 37, 500]


def test_answer_input_matches_a_real_request_with_chunks_of_the_average_length(prices):
    prices[ANSWER_MODEL, "in"] = 1.0
    expected = real_count(answer_messages(PROMPT, TEST.question, real_hits(3)))
    assert cost(top_k=3) == expected


def test_answer_input_grows_with_k(prices):
    prices[ANSWER_MODEL, "in"] = 1.0
    for k in (1, 5, MAX_TOP_K):
        assert cost(top_k=k) == real_count(answer_messages(PROMPT, TEST.question, real_hits(k)))


def test_the_answer_prompt_version_is_counted(prices):
    prices[ANSWER_MODEL, "in"] = 1.0
    longer = PromptVersion("long", DEFAULT_TEXT + " the" * 1000, "x")
    assert estimate.question_cost(TEST, longer, ANSWER_MODEL, 3, False, CHUNK_TOKENS) - cost() == 1000


def test_answer_output_is_the_assumed_150_tokens(prices):
    prices[ANSWER_MODEL, "out"] = 1.0
    assert cost() == 150


def test_judge_input_is_the_reference_call_plus_the_faithfulness_call_with_the_k_chunks(prices):
    prices[JUDGE_MODEL, "in"] = 1.0
    answer = estimate.filler(estimate.ANSWER_TOKENS)
    expected = (real_count(grade_messages(TEST, answer))
                + real_count(faithfulness_messages(TEST, [h.text for h in real_hits(3)], answer)))
    assert cost(top_k=3) == expected


def test_judge_output_is_200_tokens_for_each_of_its_two_calls(prices):
    prices[JUDGE_MODEL, "out"] = 1.0
    assert cost() == 400


def test_the_reranker_is_paid_only_when_reranking_is_on(prices):
    prices[RERANK_MODEL, "in"] = prices[RERANK_MODEL, "out"] = 1.0
    assert cost(rerank=False) == 0
    assert cost(rerank=True) > 0


def test_reranker_input_holds_all_candidates_not_k(prices):
    prices[RERANK_MODEL, "in"] = 1.0
    expected = real_count(rerank_messages(TEST.question, real_hits(RERANK_CANDIDATES)))
    assert cost(top_k=3, rerank=True) == expected


def test_reranker_output_is_the_full_list_of_candidate_numbers(prices):
    prices[RERANK_MODEL, "out"] = 1.0
    reply = json.dumps({"ranking": list(range(RERANK_CANDIDATES, 0, -1))})
    assert cost(rerank=True) == tokens(reply)


def test_reranking_still_answers_and_judges_only_k_chunks(prices):
    prices[ANSWER_MODEL, "in"] = prices[JUDGE_MODEL, "in"] = 1.0
    assert cost(top_k=3, rerank=True) == cost(top_k=3, rerank=False)


def test_prices_are_applied_per_token(prices):
    prices[ANSWER_MODEL, "out"] = 2e-6
    prices[JUDGE_MODEL, "out"] = 5e-7
    assert cost() == pytest.approx(150 * 2e-6 + 400 * 5e-7)


def chunk(tokens_: int) -> Chunk:
    return Chunk(chunk_id="c", source="d.md", doc_type="t", index=0, text="x", tokens=tokens_, start=0, end=1)


def test_a_run_costs_the_sum_of_its_questions_at_the_mean_chunk_length(prices):
    prices[ANSWER_MODEL, "in"] = prices[JUDGE_MODEL, "in"] = prices[JUDGE_MODEL, "out"] = 1.0
    total = estimate.run_cost(TESTS, PROMPT, ANSWER_MODEL, 3, False, [chunk(100), chunk(300)])
    assert total == sum(cost(test=t) for t in TESTS)
    assert total != estimate.run_cost(TESTS, PROMPT, ANSWER_MODEL, 3, False, [chunk(100), chunk(100)])


def test_the_mean_chunk_length_is_rounded_to_the_nearest_token(prices):
    prices[ANSWER_MODEL, "in"] = 1.0
    chunks = [chunk(100), chunk(101), chunk(101)]  # mean 100.67
    nearest = estimate.question_cost(TEST, PROMPT, ANSWER_MODEL, 3, False, 101)
    assert estimate.run_cost([TEST], PROMPT, ANSWER_MODEL, 3, False, chunks) == nearest
