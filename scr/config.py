from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://mpesa:mpesa@localhost:5432/mpesa"
    api_key: str = "change-me"  # simple protection for /api endpoints
    max_upload_mb: int = 10

    class Config:
        env_prefix = ""
        env_file = ".env"


settings = Settings()