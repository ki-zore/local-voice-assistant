"""Configuration settings for LLM receptionist agent."""

from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class VoiceConfig(BaseSettings):
    """Runtime configuration for voice/receptionist agent."""

    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="qwen2.5:7b-instruct", alias="OLLAMA_MODEL")
    ollama_keep_alive: str = Field(default="30m", alias="OLLAMA_KEEP_ALIVE")
    temperature: float = Field(default=0.2, alias="OLLAMA_TEMPERATURE")
    backend_url: str = Field(default="http://127.0.0.1:8000", alias="BACKEND_URL")
    default_business_id: str = Field(default="cafe_demo_001", alias="DEFAULT_BUSINESS_ID")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_voice_config() -> VoiceConfig:
    """Return cached VoiceConfig singleton."""
    return VoiceConfig()
