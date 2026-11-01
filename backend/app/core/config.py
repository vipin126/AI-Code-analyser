"""Application configuration via pydantic-settings.

All settings are loaded from environment variables (or a .env file).
Defaults are provided for local development; override in production.
"""

from functools import lru_cache
from typing import Any, Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed, validated application settings."""

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────
    app_name: str = "ai-code-analyzer"
    app_env: str = "development"
    debug: bool = True
    log_level: str = "INFO"

    # ── Backend ──────────────────────────────────────────────
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    backend_cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ]

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> list[str]:
        """Support JSON string, comma-separated string, or list."""
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                import json
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        if isinstance(v, list):
            return v
        return []

    # ── PostgreSQL ───────────────────────────────────────────
    postgres_user: str = "analyzer"
    postgres_password: str = "changeme_in_production"
    postgres_db: str = "code_analyzer"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    database_url: str = ""  # Set directly or built from parts above

    @model_validator(mode="after")
    def assemble_database_url(self) -> Self:
        """Build DATABASE_URL from individual parts if not set directly."""
        if self.database_url:
            # Cloud providers (Neon, Supabase) often use postgres:// or postgresql://
            # SQLAlchemy needs the +psycopg2 driver prefix
            if self.database_url.startswith("postgres://"):
                self.database_url = self.database_url.replace(
                    "postgres://", "postgresql+psycopg2://", 1
                )
            elif self.database_url.startswith("postgresql://") and "+psycopg2" not in self.database_url:
                self.database_url = self.database_url.replace(
                    "postgresql://", "postgresql+psycopg2://", 1
                )
        else:
            self.database_url = (
                f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            )
        return self

    # ── Redis ────────────────────────────────────────────────
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_url: str = ""  # Set directly or built from host/port

    @model_validator(mode="after")
    def assemble_redis_url(self) -> Self:
        """Build REDIS_URL from host/port if not set directly."""
        if not self.redis_url:
            self.redis_url = f"redis://{self.redis_host}:{self.redis_port}/0"
        return self

    # ── Celery ───────────────────────────────────────────────
    celery_broker_url: str = ""
    celery_result_backend: str = ""

    @model_validator(mode="after")
    def assemble_celery_urls(self) -> Self:
        """Default Celery broker/backend to REDIS_URL if not set."""
        if not self.celery_broker_url:
            self.celery_broker_url = self.redis_url
        if not self.celery_result_backend:
            self.celery_result_backend = self.redis_url
        return self

    # ── Qdrant (Vector DB) ───────────────────────────────────
    qdrant_url: str | None = None  # Cloud URL (e.g. https://xyz.cloud.qdrant.io:6333)
    qdrant_host: str = "localhost"  # Local host (ignored if qdrant_url is set)
    qdrant_port: int = 6333
    qdrant_grpc_port: int = 6334
    qdrant_api_key: str | None = None  # Cloud API key
    openrouter_qdrant_collection_name: str = "code_chunks_openrouter"

    # ── OpenRouter ──────────────────────────────────────────
    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemma-4-26b-a4b-it:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # ── Auth (Future) ────────────────────────────────────────
    jwt_secret_key: str = "change-this-to-a-random-secret"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (singleton)."""
    return Settings()
