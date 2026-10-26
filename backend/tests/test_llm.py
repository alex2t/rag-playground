"""Unit tests for model metadata and the OpenRouter result mapping (no network)."""

from openai.types.chat import ChatCompletion

from rag_playground.llm.models import parse_model
from rag_playground.llm.openrouter import sampling_params, to_result

RAW_MODEL = {
    "id": "openai/gpt-4.1-nano",
    "canonical_slug": "openai/gpt-4.1-nano-2025-04-14",
    "supported_parameters": ["temperature", "structured_outputs"],
    "pricing": {"prompt": "0.0000001", "completion": "0.0000004"},
}


def test_parse_model_reads_slug_parameters_and_prices():
    info = parse_model(RAW_MODEL)
    assert info.canonical_slug == "openai/gpt-4.1-nano-2025-04-14"
    assert info.supports_temperature
    assert info.prompt_usd_per_token == 1e-7
    assert info.completion_usd_per_token == 4e-7


def test_temperature_zero_sent_only_when_supported():
    assert sampling_params(parse_model(RAW_MODEL)) == {"temperature": 0}
    no_temp = parse_model({**RAW_MODEL, "supported_parameters": ["structured_outputs"]})
    assert not no_temp.supports_temperature
    assert sampling_params(no_temp) == {}


def test_model_without_supported_parameters_is_not_temperature_controlled():
    raw = {k: v for k, v in RAW_MODEL.items() if k != "supported_parameters"}
    assert sampling_params(parse_model(raw)) == {}


def completion(details: dict | None) -> ChatCompletion:
    usage = {"prompt_tokens": 12, "completion_tokens": 30, "total_tokens": 42, "cost": 0.0000132}
    if details is not None:
        usage["completion_tokens_details"] = details
    return ChatCompletion.model_validate({
        "id": "gen-1", "object": "chat.completion", "created": 0, "model": "openai/gpt-4.1-nano",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "Paris"}}],
        "usage": usage,
    })


def test_to_result_reads_text_tokens_cost_and_metadata():
    result = to_result(completion({"reasoning_tokens": 7}), parse_model(RAW_MODEL))
    assert result.text == "Paris"
    assert (result.prompt_tokens, result.completion_tokens, result.reasoning_tokens) == (12, 30, 7)
    assert result.cost_usd == 0.0000132
    assert result.canonical_slug == "openai/gpt-4.1-nano-2025-04-14"
    assert result.temperature_controlled


def test_to_result_counts_zero_reasoning_tokens_when_details_missing():
    assert to_result(completion(None), parse_model(RAW_MODEL)).reasoning_tokens == 0
