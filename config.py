"""Configuration for Brain Mode Tuner."""

import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

# Model constants
# Gemini 3 Flash with Agentic Vision - uses Think→Act→Observe loop
# Model draws bounding boxes via code execution, grounding answers in visual evidence
BRAIN_MODE_MODEL = "gemini-3-flash-preview"
THINKING_LEVEL = "high"  # "minimal", "low", "medium", "high" - high = Flash Thinking


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    gemini_api_key: str | None = None
    data_path: str = r"D:\MOCK DATA\Chick-fil-A Love Field FSU 03904 -CPS"
    db_path: str = "brain_mode.db"
    cache_path: str = "cache"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
