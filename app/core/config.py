from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Directory where uploaded profile photos are persisted (next to media/).
UPLOADS_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "MediScribe AI"
    debug: bool = False

    # Database (PostgreSQL via Supabase in prod; SQLite allowed for offline demo)
    database_url: str

    # JWT
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Supabase
    supabase_url: str | None = None
    supabase_service_key: str | None = None
    supabase_anon_key: str | None = None

    # AI / External APIs
    mistral_api_key: str | None = None
    gemini_api_key: str | None = None

    # Demo seeding
    admin_email: str | None = None
    admin_password: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
