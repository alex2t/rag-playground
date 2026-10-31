"""Environment settings, the model catalogue and the selection gates. Sizes and ladder are added later."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# OpenRouter model IDs, checked against /api/v1/models on 2026-10-26.
ANSWER_MODELS = ["openai/gpt-4.1-nano", "openai/gpt-4.1-mini", "openai/gpt-6.1-sol"]
JUDGE_MODEL = "google/gemini-3.5-flash-lite"
RERANK_MODEL = "openai/gpt-4.1-nano"
RERANK_CANDIDATES = 20  # chunks retrieved for the reranker, which keeps the top K (T21)
ENRICH_MODEL = "openai/gpt-4.1-mini"  # writes each chunk's headline and summary, once per chunk set (T47)
MAX_TOP_K = 8  # the KB is small (48 documents), so more chunks would hand the model a large share of it (T45)
# S0 baseline: LlamaIndex out-of-the-box defaults plus our cheapest answer model (T27 revision). Each stack
# searches with its own out-of-the-box search (T40 revision 2026-10-29): Qdrant plain vector search; OpenAI's
# default, which T12 measured as hybrid search with its "auto" ranker (weights have no effect with "auto").
S0 = {"chunk_size": 1024, "overlap": 200, "top_k": 2, "rerank": False, "answer_model": "openai/gpt-4.1-nano",
      "search": {"A": {"hybrid": True, "openai_ranking": {"ranker": "auto", "embedding_weight": 1.0,
                                                          "text_weight": 1.0, "score_threshold": 0.0}},
                 "B": {"hybrid": False, "openai_ranking": None}}}
GENERATOR_MODEL = "anthropic/claude-sonnet-5.5"
AUDIT_MODEL = "openai/gpt-6.1-sol"

EMBED_MODEL = "nomic-ai/nomic-embed-text-v1.5"
EMBED_DIM = 768
BM25_MODEL = "Qdrant/bm25"

# Minimum scores a run needs before it can be "best" (T08): custom values, confirmed 2026-10-27,
# to be reviewed after the first real runs. Each gate passes when the score is >= its value.
GATES = {"mrr": 0.75, "recall": 0.80, "faithfulness": 4.0, "correct_refusal_rate": 0.80}
BOOTSTRAP_RESAMPLES = 1000
BOOTSTRAP_SEED = 42

# Judge calibration (T20, T48): answers sampled from each S0 run, and the agreement target.
CALIBRATION_PER_RUN = 15
CALIBRATION_SEED = 44
CALIBRATION_TARGET = 0.80
PASS_ACCURACY = 4  # an answer passes at this accuracy score or above


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
    budget_usd: float = 0.0  # cap on all recorded evaluation spend (D15); unset means nothing paid can run


settings = Settings()
