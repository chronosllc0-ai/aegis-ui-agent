"""Application configuration."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    GEMINI_API_KEY: str = ""
    GOOGLE_CLOUD_PROJECT: str = ""
    PORT: int = 8080
    LOG_LEVEL: str = "INFO"
    BROWSER_HEADLESS: bool = True
    VIEWPORT_WIDTH: int = 1280
    VIEWPORT_HEIGHT: int = 720

    class Config:
        env_file = ".env"


settings = Settings()
