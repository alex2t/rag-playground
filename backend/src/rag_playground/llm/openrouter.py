"""Chat and structured output through OpenRouter (D03, D19)."""

from dataclasses import dataclass
from functools import cache

from openai import OpenAI
from openai.types.chat import ChatCompletion
from pydantic import BaseModel

from rag_playground.llm.models import ModelInfo, model_info
from rag_playground.settings import OPENROUTER_BASE_URL, settings


@dataclass(frozen=True)
class ChatResult:
    """One completion with the usage and metadata stored for reproducibility."""

    text: str
    model: str
    canonical_slug: str
    temperature_controlled: bool
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    cost_usd: float


@cache
def client() -> OpenAI:
    """OpenAI SDK client pointed at OpenRouter."""
    return OpenAI(base_url=OPENROUTER_BASE_URL, api_key=settings.openrouter_api_key)


def sampling_params(info: ModelInfo) -> dict:
    """Temperature 0, sent only when the model accepts it (D11, T14)."""
    return {"temperature": 0} if info.supports_temperature else {}


def to_result(completion: ChatCompletion, info: ModelInfo) -> ChatResult:
    """Extract text, tokens and OpenRouter's `usage.cost` from a completion."""
    usage = completion.usage
    details = usage.completion_tokens_details
    return ChatResult(
        text=completion.choices[0].message.content or "",
        model=info.id,
        canonical_slug=info.canonical_slug,
        temperature_controlled=info.supports_temperature,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        reasoning_tokens=(details.reasoning_tokens or 0) if details else 0,
        cost_usd=float(usage.model_extra["cost"]),
    )


def chat(model: str, messages: list[dict]) -> ChatResult:
    """Send one chat request and return the answer with usage."""
    info = model_info(model)
    completion = client().chat.completions.create(model=model, messages=messages, **sampling_params(info))
    return to_result(completion, info)


def chat_structured[T: BaseModel](model: str, messages: list[dict], schema: type[T]) -> tuple[T, ChatResult]:
    """Send one chat request that must return JSON matching `schema`."""
    info = model_info(model)
    completion = client().chat.completions.parse(
        model=model, messages=messages, response_format=schema, **sampling_params(info)
    )
    return completion.choices[0].message.parsed, to_result(completion, info)
