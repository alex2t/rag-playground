"""Step 6 checks of the answer step with real models (OpenRouter, about $0.001; the refusal test also calls the judge).
Run with `uv run pytest -m live tests/test_live_answer.py`."""

import pytest

from rag_playground.datasets.schema import KB_DIR, load_tests
from rag_playground.llm.models import model_info
from rag_playground.rag.answer import answer
from rag_playground.rag.prompts import DEFAULT_NAME, DEFAULT_TEXT, PromptVersion, sha256
from rag_playground.scoring.judging import judge
from rag_playground.stacks.hits import Hit

pytestmark = pytest.mark.live

DEFAULT = PromptVersion(DEFAULT_NAME, DEFAULT_TEXT, sha256(DEFAULT_TEXT))
NANO = "openai/gpt-4.1-nano"


def case(test_id: str):
    return next(t for t in load_tests() if t.id == test_id)


def kb_hit(path: str) -> list[Hit]:
    return [Hit(f"{path}#0", path, 1.0, (KB_DIR / path).read_text(encoding="utf-8"))]


PRICE = case("numerical-004")  # "What is the price of the Agentforce Agent Design service?" -> 46,250 USD
MUMBAI = case("unanswerable-001")  # "How many people work in the Mumbai office?" -> not in the KB


def test_the_answer_states_the_price_found_in_the_context():
    result = answer(NANO, DEFAULT, PRICE.question, kb_hit("services/agentforce-agent-design.md"))
    assert "46,250" in result.text
    assert result.temperature_controlled
    assert result.canonical_slug.startswith(NANO)
    assert result.cost_usd > 0


def test_the_answer_refuses_when_the_context_lacks_it():
    """The overview lists the Austin, Dublin and Toronto offices only. Refusal is decided by the judge, the same
    way the refusal metrics are (T19): a phrase check would pass an invented answer that mentions the knowledge base."""
    hits = kb_hit("company/overview.md")
    result = answer(NANO, DEFAULT, MUMBAI.question, hits)
    verdict, _ = judge(MUMBAI, [hit.text for hit in hits], result.text)
    assert verdict.refused, result.text
    assert verdict.accuracy == 5, result.text


def test_gpt_6_1_sol_runs_are_flagged_temperature_not_controlled():
    """Reads OpenRouter's public model list only: no completion is bought."""
    assert not model_info("openai/gpt-6.1-sol").supports_temperature
