"""Environment settings. The model catalogue, sizes, ladder and gates are added here in later steps."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Values read from environment variables or a `.env` file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    app_version: str = "dev"
    qdrant_url: str = "http://localhost:6333"
    static_dir: Path = Path(__file__).resolve().parents[3] / "frontend" / "dist"


settings = Settings()
