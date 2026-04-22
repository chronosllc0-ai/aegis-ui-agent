"""Application configuration via environment variables."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from ``.env``."""

    # ── Database ──────────────────────────────────────────────────────
    DATABASE_URL: str = ""

    # ── LLM Provider Keys (server-side defaults / fallbacks) ─────────
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    XAI_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    FIREWORKS_API_KEY: str = ""
    BRAVE_SEARCH_API_KEY: str = ""  # Brave Search API key for the built-in web_search tool
    VIRUSTOTAL_API_KEY: str = ""

    # ── Platform-level agent instruction (admin-only) ─────────────────
    # Injected at the top of every agent system prompt on every session.
    # Users cannot see or override it. Prefer the DB-backed setting
    # (editable live in Admin > Agent Config) — this env var is a
    # deploy-time fallback when the DB row has not been set yet.
    AEGIS_GLOBAL_SYSTEM_INSTRUCTION: str = ""
    WORKSPACE_PROMPT_MODE: str = "v1"
    FEATURE_FLAG_WORKSPACE_PROMPT_MODE: bool = False
    FEATURE_FLAG_SESSIONS_V2: bool = False
    FEATURE_FLAG_OBSERVABILITY_EVENT_LOG: bool = True
    SESSIONS_V2_DUAL_WRITE: bool = True
    SESSIONS_V2_LEGACY_FALLBACK: bool = False
    MEMORY_MODE: str = "hybrid"
    MEMORY_LONG_TERM_MAIN_SESSION_ONLY: bool = True

    # ── Default provider / model ─────────────────────────────────────
    DEFAULT_PROVIDER: str = "chronos"
    DEFAULT_MODEL: str = "nvidia/nemotron-3-super-120b-a12b:free"

    # ── Encryption (for BYOK key storage) ────────────────────────────
    ENCRYPTION_SECRET: str = "change-me-in-production"

    # ── Runtime ──────────────────────────────────────────────────────
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    BROWSER_HEADLESS: bool = True
    VIEWPORT_WIDTH: int = 1280
    VIEWPORT_HEIGHT: int = 720
    NAVIGATION_TASK_TIMEOUT_SECONDS: int = 180
    NAVIGATION_MAX_TOOL_CALLS: int = 100
    NAVIGATION_ACK_TIMEOUT_SECONDS: int = 5
    NAVIGATION_HANDOFF_TIMEOUT_SECONDS: int = 600
    CHANNEL_TOOLS_TELEGRAM_ADVANCED_ENABLED: bool = True
    CHANNEL_TOOLS_SLACK_ADVANCED_ENABLED: bool = True
    CHANNEL_TOOLS_DISCORD_ADVANCED_ENABLED: bool = True
    HEARTBEAT_SESSION_INTERVAL_SECONDS: int = 180

    # ── Gemini-specific (kept for backwards compatibility) ───────────
    GEMINI_MODEL: str = "gemini-2.5-pro"
    GEMINI_LIVE_MODEL: str = "gemini-3.1-flash-live-preview"

    # ── Auth / Sessions ──────────────────────────────────────────────
    SESSION_SECRET: str = ""
    SESSION_TTL_SECONDS: int = 60 * 60 * 24 * 7
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    COOKIE_DOMAIN: str = ""
    ADMIN_EMAILS: str = ""  # comma-separated email list for auto-admin assignment
    SUPERADMIN_EMAIL: str = ""  # auto-seed a password-based superadmin on startup
    SUPERADMIN_PASSWORD: str = ""  # password for the auto-seeded superadmin
    SUPERADMIN_NAME: str = "Super Admin"
    PUBLIC_BASE_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:5173"
    CORS_ORIGINS: str = ""  # comma-separated extra origins (e.g. "https://mohex.org,https://app.netlify.app")

    # ── OAuth providers (authentication) ────────────────────────────
    GOOGLE_OAUTH_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLIENT_SECRET: str = ""
    GITHUB_OAUTH_CLIENT_ID: str = ""
    GITHUB_OAUTH_CLIENT_SECRET: str = ""
    SSO_OIDC_METADATA_URL: str = ""
    SSO_CLIENT_ID: str = ""
    SSO_CLIENT_SECRET: str = ""
    SSO_SCOPE: str = "openid email profile"

    # ── Connector OAuth2 (user integrations) ─────────────────────────
    # Separate client IDs for connectors — these request broader scopes
    # (e.g. Gmail read/send, Drive access) than the auth-only clients.
    GOOGLE_CONNECTOR_CLIENT_ID: str = ""
    GOOGLE_CONNECTOR_CLIENT_SECRET: str = ""
    GITHUB_CONNECTOR_CLIENT_ID: str = ""
    GITHUB_CONNECTOR_CLIENT_SECRET: str = ""
    SLACK_CONNECTOR_CLIENT_ID: str = ""
    SLACK_CONNECTOR_CLIENT_SECRET: str = ""
    NOTION_CONNECTOR_CLIENT_ID: str = ""
    NOTION_CONNECTOR_CLIENT_SECRET: str = ""
    LINEAR_CONNECTOR_CLIENT_ID: str = ""
    LINEAR_CONNECTOR_CLIENT_SECRET: str = ""

    # ── Resend email API ─────────────────────────────────────────────
    RESEND_API_KEY: str = ""

    # ── Email / SMTP ─────────────────────────────────────────────────
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_SENDER: str = ""
    SMTP_USE_TLS: bool = True

    # ── Payments ─────────────────────────────────────────────────────
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    COINBASE_COMMERCE_API_KEY: str = ""
    COINBASE_COMMERCE_WEBHOOK_SECRET: str = ""

    # ── Railway / Deployment ─────────────────────────────────────────
    RAILWAY_ENVIRONMENT: str = ""
    RAILWAY_PUBLIC_DOMAIN: str = ""
    VIRUSTOTAL_TIMEOUT_SECONDS: int = 30
    VIRUSTOTAL_ENABLED: bool = False
    VIRUSTOTAL_MAX_FILE_BYTES: int = 1048576
    VIRUSTOTAL_POLL_INTERVAL_SECONDS: int = 5
    VIRUSTOTAL_MAX_POLLS: int = 12
    VIRUSTOTAL_REQUEST_MAX_RETRIES: int = 2
    VIRUSTOTAL_RETRY_BASE_DELAY_SECONDS: float = 0.5
    VIRUSTOTAL_REQUIRED: bool = False
    VIRUSTOTAL_FALLBACK_POLICY: str = "warn_allow"
    SKILLS_MAX_TOKENS: int = 10_000
    SKILLS_MIN_PRIORITY: int | None = None
    # Backward-compatible singular alias requested in some deployments.
    SKILLS_MAX_TOKEN: int = Field(default=10_000, validation_alias="SKILLS_MAX_TOKEN")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def resolved_public_base_url(self) -> str:
        """Return the canonical backend base URL for callbacks and docs."""
        if self.PUBLIC_BASE_URL.strip():
            return self.PUBLIC_BASE_URL.rstrip("/")
        if self.RAILWAY_PUBLIC_DOMAIN.strip():
            return f"https://{self.RAILWAY_PUBLIC_DOMAIN.strip()}".rstrip("/")
        return f"http://localhost:{self.PORT}"

    @property
    def resolved_frontend_url(self) -> str:
        """Return the canonical frontend URL for redirects."""
        if self.FRONTEND_URL.strip():
            return self.FRONTEND_URL.rstrip("/")
        return "http://localhost:5173"

    @property
    def normalized_cookie_samesite(self) -> str:
        """Return a browser-compatible SameSite cookie policy."""
        value = self.COOKIE_SAMESITE.strip().lower()
        if value not in {"lax", "strict", "none"}:
            return "lax"
        return value

    @property
    def resolved_cookie_domain(self) -> str | None:
        """Return the cookie domain when explicitly configured."""
        value = self.COOKIE_DOMAIN.strip()
        return value or None


settings = Settings()
