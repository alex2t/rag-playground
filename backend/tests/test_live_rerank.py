"""Step 6 check of the reranker model itself (OpenRouter, under $0.001).
Run with `uv run pytest -m live tests/test_live_rerank.py`."""

import pytest

from rag_playground.datasets.schema import KB_DIR, load_tests
from rag_playground.rag.rerank import rerank
from rag_playground.stacks.hits import Hit

pytestmark = pytest.mark.live

PRICE = next(t for t in load_tests() if t.id == "numerical-004")  # price of Agentforce Agent Design -> 46,250 USD
GOLD = "services/agentforce-agent-design.md"  # the only document that states the price
DISTRACTORS = ["company/overview.md", "services/data-cloud-foundations.md"]  # a similar service page is the hard one


def kb_hit(path: str) -> Hit:
    return Hit(f"{path}#0", path, 1.0, (KB_DIR / path).read_text(encoding="utf-8"))


def test_the_reranker_moves_the_gold_document_from_last_to_first():
    hits = [kb_hit(path) for path in [*DISTRACTORS, GOLD]]
    out = rerank(PRICE.question, hits, k=3)
    assert out.hits[0].source == GOLD
    assert sorted(h.source for h in out.hits) == sorted([*DISTRACTORS, GOLD])
    assert not out.repaired
    assert out.result.temperature_controlled
    assert out.result.cost_usd > 0
