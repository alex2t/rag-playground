"""Model metadata from OpenRouter's public model list."""

from dataclasses import dataclass
from functools import cache

import httpx

from rag_playground.settings import OPENROUTER_BASE_URL


@dataclass(frozen=True)
class ModelInfo:
    """What a run needs to know about one model."""

    id: str
    canonical_slug: str
    supported_parameters: frozenset[str]
    prompt_usd_per_token: float
    completion_usd_per_token: float

    @property
    def supports_temperature(self) -> bool:
        return "temperature" in self.supported_parameters


def parse_model(raw: dict) -> ModelInfo:
    """Build a ModelInfo from one entry of /api/v1/models."""
    return ModelInfo(
        id=raw["id"],
        canonical_slug=raw["canonical_slug"],
        supported_parameters=frozenset(raw.get("supported_parameters", [])),
        prompt_usd_per_token=float(raw["pricing"]["prompt"]),
        completion_usd_per_token=float(raw["pricing"]["completion"]),
    )


@cache
def model_catalog() -> dict[str, ModelInfo]:
    """Fetch every OpenRouter model once per process."""
    response = httpx.get(f"{OPENROUTER_BASE_URL}/models", timeout=30)
    response.raise_for_status()
    return {m["id"]: parse_model(m) for m in response.json()["data"]}


def model_info(model_id: str) -> ModelInfo:
    """Return metadata for one model; KeyError if OpenRouter does not list it."""
    return model_catalog()[model_id]
