"""Step 1 checks against the real APIs. Run with `uv run pytest -m live`."""

import math

import openai
import pytest
from pydantic import BaseModel

from rag_playground.chunking.chunk_sets import Chunk
from rag_playground.llm.models import model_info
from rag_playground.llm.openrouter import chat, chat_structured
from rag_playground.settings import ANSWER_MODELS, EMBED_DIM, JUDGE_MODEL
from rag_playground.stacks import nomic, openai_vector_store as store

pytestmark = pytest.mark.live

PING = [{"role": "user", "content": "Reply with the single word OK."}]


@pytest.mark.parametrize("model", [*ANSWER_MODELS, JUDGE_MODEL])
def test_model_replies_with_usage_and_cost(model):
    result = chat(model, PING)
    assert "ok" in result.text.lower()
    assert result.prompt_tokens > 0 and result.completion_tokens > 0
    assert result.cost_usd > 0
    assert result.canonical_slug == model_info(model).canonical_slug
    assert result.temperature_controlled == model_info(model).supports_temperature


def test_gpt_6_1_sol_is_flagged_temperature_not_controlled():
    assert not model_info("openai/gpt-6.1-sol").supports_temperature


class Capital(BaseModel):
    country: str
    capital: str


def test_judge_returns_structured_output():
    messages = [{"role": "user", "content": "Give the capital of France."}]
    parsed, result = chat_structured(JUDGE_MODEL, messages, Capital)
    assert parsed.capital.lower() == "paris"
    assert result.cost_usd > 0


def test_vector_store_round_trip():
    texts = ["Customers can request a refund within 30 days of purchase.",
             "Standard shipping takes five business days.",
             "Hardware carries a two-year limited warranty."]
    chunks = [Chunk(chunk_id=f"policy.md#{i}", source="policy.md", doc_type="company", index=i, text=t,
                    tokens=10, start=0, end=len(t)) for i, t in enumerate(texts)]
    ranking = store.Ranking(ranker="auto", embedding_weight=1.0, text_weight=1.0, score_threshold=0.0)
    store_id = store.create_store("rag-playground-step1-test")
    try:
        assert store.upload_chunks(store_id, chunks) == 3
        hits = store.search(store_id, "How long do I have to get my money back?", 3, ranking)
        assert len(hits) == 3
        assert hits[0].chunk_id == "policy.md#0" and hits[0].source == "policy.md"
        assert hits[0].text == texts[0]
    finally:
        store.delete_store(store_id)
    with pytest.raises(openai.NotFoundError):
        store.client().vector_stores.retrieve(store_id)


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def test_nomic_returns_768_dims_and_ranks_relevant_document_first():
    docs = nomic.embed_documents(["Refunds are accepted within 30 days.", "The office is closed on Sundays."])
    query = nomic.embed_query("Can I get my money back?")
    assert len(query) == EMBED_DIM and all(len(d) == EMBED_DIM for d in docs)
    assert cosine(query, docs[0]) > cosine(query, docs[1])


def test_nomic_query_and_document_prefixes_change_the_vector():
    assert nomic.embed_query("refund policy") != nomic.embed_documents(["refund policy"])[0]
