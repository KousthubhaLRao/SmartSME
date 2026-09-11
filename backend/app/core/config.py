from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from the environment (and a local .env)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # ---- Database -----------------------------------------------------------
    # Postgres is required; there is no embedded fallback.
    database_url: str = "postgresql+psycopg://smartsme:smartsme@localhost:5432/smartsme"

    # ---- Auth ---------------------------------------------------------------
    auth_secret: str = "smartsme-dev-insecure-secret-change-me"
    session_cookie: str = "smartsme_session"
    session_days: int = 30
    # Set true when serving the API over HTTPS from a different site than the SPA.
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    # ---- Frontend / CORS ----------------------------------------------------
    # Comma-separated list of allowed browser origins.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ---- Event worker -------------------------------------------------------
    # Disable the background poller (e.g. on serverless, where writes drain
    # the queue synchronously instead).
    disable_worker: bool = False
    worker_poll_seconds: float = 1.0

    # ---- Demo data ----------------------------------------------------------
    seed_demo_data: bool = True

    # ---- AI provider --------------------------------------------------------
    # Set one key. When several are set the first below wins, unless ai_provider
    # forces a choice.
    ai_provider: str = ""

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"

    google_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
