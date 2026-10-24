"""Configuration settings for LLM receptionist agent."""

from functools import lru_cache
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class VoiceConfig(BaseSettings):
    """Runtime configuration for voice/receptionist agent and pipeline."""

    ollama_base_url: str = Field(default="http://localhost:11434", validation_alias=AliasChoices("OLLAMA_BASE_URL", "ollama_base_url"))
    ollama_model: str = Field(default="qwen2.5:7b-instruct", validation_alias=AliasChoices("OLLAMA_MODEL", "ollama_model"))
    ollama_keep_alive: str = Field(default="30m", validation_alias=AliasChoices("OLLAMA_KEEP_ALIVE", "ollama_keep_alive"))
    temperature: float = Field(default=0.2, validation_alias=AliasChoices("OLLAMA_TEMPERATURE", "temperature"))
    backend_url: str = Field(default="http://127.0.0.1:8000", validation_alias=AliasChoices("BACKEND_URL", "backend_url"))
    default_business_id: str = Field(default="cafe_demo_001", validation_alias=AliasChoices("DEFAULT_BUSINESS_ID", "default_business_id"))

    # Voice pipeline settings
    whisper_model: str = Field(default="base.en", validation_alias=AliasChoices("WHISPER_MODEL", "STT_MODEL_SIZE", "whisper_model"))
    whisper_device: str = Field(default="cpu", validation_alias=AliasChoices("WHISPER_DEVICE", "STT_DEVICE", "whisper_device"))
    whisper_compute_type: str = Field(default="int8", validation_alias=AliasChoices("WHISPER_COMPUTE_TYPE", "STT_COMPUTE_TYPE", "whisper_compute_type"))
    piper_voice: str = Field(default="en_US-lessac-medium", validation_alias=AliasChoices("PIPER_VOICE", "PIPER_VOICE_NAME", "piper_voice"))
    piper_download_dir: str = Field(default="voice/models", validation_alias=AliasChoices("PIPER_DOWNLOAD_DIR", "piper_download_dir"))
    vad_stop_secs: float = Field(default=0.5, validation_alias=AliasChoices("VAD_STOP_SECS", "vad_stop_secs"))
    audio_sample_rate: int = Field(default=16000, validation_alias=AliasChoices("AUDIO_SAMPLE_RATE", "audio_sample_rate"))

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_voice_config() -> VoiceConfig:
    """Return cached VoiceConfig singleton."""
    return VoiceConfig()
