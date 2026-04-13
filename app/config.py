"""Application configuration via environment variables / .env file."""

from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Optional
import secrets


class Settings(BaseSettings):
    # ── Web Auth ─────────────────────────────────────────────────────────────
    SECRET_KEY: str = secrets.token_hex(32)
    WEB_USERNAME: str = "admin"
    WEB_PASSWORD: str = "changeme"
    SESSION_TIMEOUT_MINUTES: int = 60  # 15 | 60 | 1440 | 10080

    # ── Google OAuth ─────────────────────────────────────────────────────────
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8080/api/google/callback"
    GOOGLE_TOKEN_FILE: str = "/app/credentials/google_token.json"

    # ── Storage ───────────────────────────────────────────────────────────────
    DESTINATION_PATH: str = "/data/photos"
    DATABASE_PATH: str = "/data/gpd.db"
    LOG_PATH: str = "/data/logs"
    THUMBNAIL_CACHE_PATH: str = "/data/thumbs"

    # ── Sync ──────────────────────────────────────────────────────────────────
    SPEED_LIMIT_MBPS: float = 0.0   # 0 = unlimited
    SYNC_INTERVAL_MINUTES: int = 60
    MAX_RETRIES: int = 3
    CHUNK_SIZE: int = 65536          # 64 KB per download chunk

    # ── Server ────────────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8080
    DEBUG: bool = False

    @field_validator("SESSION_TIMEOUT_MINUTES")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        allowed = {15, 60, 1440, 10080}
        if v not in allowed:
            raise ValueError(f"SESSION_TIMEOUT_MINUTES must be one of {allowed}")
        return v

    model_config = {
        "env_file": "env/.env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
