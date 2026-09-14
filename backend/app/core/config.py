from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from the environment (and a local .env)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # ---- Database -----------------------------------------------------------
    # Postgres is required; there is no embedded fallback.
    database_url: str = "postgresql+psycopg://smartsme:smartsme@localhost:5432/smartsme"

    # ---- Connection pool ----------------------------------------------------
    # SQLAlchemy's defaults (5 + 10) are sized for a script, not a server: every
    # concurrent request holds one connection for its whole life, so 15 of them
    # is the ceiling on concurrency no matter how many workers are running.
    db_pool_size: int = 20
    db_max_overflow: int = 40
    #: Fail fast rather than leaving a caller hanging for half a minute. A
    #: request that cannot get a connection in this long is one the user has
    #: already given up on.
    db_pool_timeout: float = 10.0
    #: Recycle before a proxy or Postgres drops an idle connection underneath us.
    db_pool_recycle: int = 1800

    #: Threads for the sync endpoint pool. One request occupies one thread *and*
    #: one connection, so this is kept in step with the pool ceiling; making it
    #: larger only queues work deeper inside the process.
    server_threads: int = 60

    # ---- Auth ---------------------------------------------------------------
    auth_secret: str = "smartsme-dev-insecure-secret-change-me"
    session_cookie: str = "smartsme_session"
    session_days: int = 30
    # Set true when serving the API over HTTPS from a different site than the SPA.
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    # ---- Sign-in throttling -------------------------------------------------
    #: Failures before an account is locked (employees are exempt).
    login_max_attempts: int = 5
    #: Minutes the first lock lasts; each further block of failures doubles it.
    login_lock_minutes: int = 15
    #: Sliding window for the per-IP limit.
    login_window_minutes: int = 15
    #: Failed attempts one IP may make across all accounts in that window.
    login_max_ip_attempts: int = 20

    # ---- Frontend / CORS ----------------------------------------------------
    # Comma-separated list of allowed browser origins.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ---- Inbound orders -----------------------------------------------------
    #: Collect orders from a mailbox. Off by default: an inbox that nobody has
    #: configured should not be polled every minute.
    email_ingest_enabled: bool = False
    #: "pop3" suits Mailpit (the local dev inbox); "imap" suits a real mailbox.
    email_protocol: Literal["pop3", "imap"] = "pop3"
    email_host: str = "localhost"
    email_port: int = 1110
    email_user: str = "smartsme"
    email_password: str = "smartsme"
    email_ssl: bool = False
    email_folder: str = "INBOX"
    #: Most messages to take in one sweep, so a backlog cannot stall the worker.
    email_batch: int = 25

    #: A bot token from Telegram's @BotFather. Free, instant, no card.
    telegram_bot_token: str = ""

    #: Seconds between inbound sweeps.
    inbound_poll_seconds: float = 30.0

    # ---- Event dispatch -----------------------------------------------------
    #: How a published event reaches the workflow engine.
    #:   "inline" — drained inside the request, so effects are visible the moment
    #:              the write returns. The default, and what the SPA expects.
    #:   "celery" — handed to Redis and applied by a Celery worker. Higher
    #:              throughput; the write returns before effects are applied.
    event_dispatch: Literal["inline", "celery"] = "inline"
    redis_url: str = "redis://localhost:6379/0"
    #: Seconds between outbox sweeps. The sweep is the safety net that catches
    #: events whose enqueue was lost (Redis restarting, say).
    celery_sweep_seconds: float = 5.0
    #: An event older than this that is still pending is considered stranded and
    #: is re-enqueued by the sweep.
    celery_stranded_seconds: float = 30.0

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
