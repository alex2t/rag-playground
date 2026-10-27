"""Step 5 checks of the judge model itself (OpenRouter, about $0.01). Run with `uv run pytest -m live -k judge`."""

import pytest

from rag_playground.datasets.schema import KB_DIR, load_tests
from rag_playground.scoring.judging import judge

pytestmark = pytest.mark.live


def case(test_id: str):
    return next(t for t in load_tests() if t.id == test_id)


def kb(path: str) -> list[str]:
    return [(KB_DIR / path).read_text(encoding="utf-8")]


PRICE = case("numerical-004")  # "What is the price of the Agentforce Agent Design service?" -> 46,250 USD
PRICE_CONTEXT = kb("services/agentforce-agent-design.md")
MUMBAI = case("unanswerable-001")  # "How many people work in the Mumbai office?" -> not in the KB
MUMBAI_CONTEXT = kb("company/overview.md")  # lists Austin, Dublin and Toronto only


def test_the_reference_answer_scores_at_least_4_5_on_average():
    j, _ = judge(PRICE, PRICE_CONTEXT, PRICE.reference_answer)
    assert (j.accuracy + j.completeness + j.relevance + j.faithfulness) / 4 >= 4.5
    assert not j.refused


def test_a_wrong_answer_gets_accuracy_1():
    j, _ = judge(PRICE, PRICE_CONTEXT, "Agentforce Agent Design costs 52,500 USD.")
    assert j.accuracy == 1


def test_an_invented_fact_pulls_faithfulness_below_the_gate():
    """The price is in the context, the discount is invented. The rubric (T41) gives 3 for a supported main
    claim with an unsupported extra claim, so the check is "below 4", the faithfulness gate (T08)."""
    answer = "Agentforce Agent Design costs 46,250 USD, with a 20% discount for nonprofit clients."
    j, _ = judge(PRICE, PRICE_CONTEXT, answer)
    assert j.faithfulness < 4


def test_a_correct_answer_unsupported_by_the_context_is_accurate_but_not_faithful():
    """The 'lucky guess' of docs/evaluation.md: the right price, but the retrieved context never states it.
    Fails if the judge grades faithfulness against the reference answer instead of the context."""
    j, _ = judge(PRICE, MUMBAI_CONTEXT, PRICE.reference_answer)
    assert j.accuracy >= 4
    assert j.faithfulness <= 2


def test_a_refusal_on_an_unanswerable_question_gets_accuracy_5_and_is_flagged():
    j, results = judge(MUMBAI, MUMBAI_CONTEXT, "The knowledge base does not say how many people work in Mumbai.")
    assert j.accuracy == 5 and j.refused
    assert len(results) == 2 and all(r.cost_usd > 0 for r in results)
    print("judge tokens in/out per call:", [(r.prompt_tokens, r.completion_tokens) for r in results],
          "cost USD:", sum(r.cost_usd for r in results))
