"""Application configuration via environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from ``.env``."""

    # ── Database ──────────────────────────────────────────────────────
    DATABASE_URL: str = ""

    # ── LLM Provider Keys (server-side defaults / fallbacks) ─────────
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    MISTRAL_API_KEY: str = ""
    GROQ_API_KEY: str = ""

    # ── Default provider / model ─────────────────────────────────────
    DEFAULT_PROVIDER: str = "google"
    DEFAULT_MODEL: str = "gemini-2.5-pro"

    # ── Encryption (for BYOK key storage) ────────────────────────────
    ENCRYPTION_SECRET: str = "change-me-in-production"

    # ── Runtime ──────────────────────────────────────────────────────
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    BROWSER_HEADLESS: bool = True
    VIEWPORT_WIDTH: int = 1280
    VIEWPORT_HEIGHT: int = 720

    # ── Gemini-specific (kept for backwards compatibility) ───────────
    GEMINI_MODEL: str = "gemini-2.5-pro"
    GEMINI_LIVE_MODEL: str = "gemini-2.5-flash-native-audio-preview"

    # ── Auth / Sessions ──────────────────────────────────────────────
    SESSION_SECRET: str = ""
    SESSION_TTL_SECONDS: int = 60 * 60 * 24 * 7
    COOKIE_SECURE: bool = False
    ADMIN_EMAILS: str = ""
    PUBLIC_BASE_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:5173"
    CORS_ORIGINS: str = ""  # comma-separated extra origins (e.g. "https://mohex.org,https://app.netlify.app")

    # ── OAuth providers ──────────────────────────────────────────────
    GOOGLE_OAUTH_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLIENT_SECRET: str = ""
    GITHUB_OAUTH_CLIENT_ID: str = ""
    GITHUB_OAUTH_CLIENT_SECRET: str = ""
    SSO_OIDC_METADATA_URL: str = ""
    SSO_CLIENT_ID: str = ""
    SSO_CLIENT_SECRET: str = ""
    SSO_SCOPE: str = "openid email profile"

    # ── Email / SMTP ─────────────────────────────────────────────────
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_SENDER: str = ""
    SMTP_USE_TLS: bool = True

    # ── Railway / Deployment ─────────────────────────────────────────
    RAILWAY_ENVIRONMENT: str = ""
    RAILWAY_PUBLIC_DOMAIN: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
