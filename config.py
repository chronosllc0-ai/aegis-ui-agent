"""Application configuration via environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from ``.env``."""

    GEMINI_API_KEY: str = ""
    GOOGLE_CLOUD_PROJECT: str = ""
    PORT: int = 8080
    LOG_LEVEL: str = "INFO"
    BROWSER_HEADLESS: bool = True
    VIEWPORT_WIDTH: int = 1280
    VIEWPORT_HEIGHT: int = 720
    GEMINI_MODEL: str = "gemini-2.5-pro"
    INTEGRATIONS_ENCRYPTION_KEY: str = "change-me"
    CODE_EXECUTION_ENABLED: bool = False
    CODE_EXECUTION_TIMEOUT_SECONDS: int = 5
    CODE_EXECUTION_OUTPUT_CAP: int = 8000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
