"""Environment settings and the model catalogue. Sizes, ladder and gates are added in later steps."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# OpenRouter model IDs, checked against /api/v1/models on 2026-10-26.
ANSWER_MODELS = ["openai/gpt-4.1-nano", "openai/gpt-4.1-mini", "openai/gpt-6.1-sol"]
JUDGE_MODEL = "google/gemini-3.5-flash-lite"
RERANK_MODEL = "openai/gpt-4.1-nano"
GENERATOR_MODEL = "anthropic/claude-sonnet-5.5"
AUDIT_MODEL = "openai/gpt-6.1-sol"

EMBED_MODEL = "nomic-ai/nomic-embed-text-v1.5"
EMBED_DIM = 768
BM25_MODEL = "Qdrant/bm25"


class Settings(BaseSettings):
    """Values read from environment variables or the repo-root `.env` file."""

    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    app_env: str = "dev"
    app_version: str = "dev"
    qdrant_url: str = "http://localhost:6333"
    static_dir: Path = REPO_ROOT / "frontend" / "dist"
    var_dir: Path = REPO_ROOT / "var"
    openai_api_key: str = ""
    openrouter_api_key: str = ""


settings = Settings()
