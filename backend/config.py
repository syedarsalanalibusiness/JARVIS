from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration is loaded from the project .env file, never from source code."""

    gemini_api_key: str = ""
    gemini_live_model: str = "gemini-2.5-flash-native-audio-preview-12-2025"
    gemini_text_model: str = "gemini-3.1-flash-lite"
    ollama_enabled: bool = True
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b"
    jarvis_host: str = "127.0.0.1"
    jarvis_port: int = 8000
    database_path: str = "data/jarvis.db"
    search_max_results: int = 5
    weather_default_city: str = "Karachi"
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def db_path(self) -> Path:
        path = Path(self.database_path)
        return path if path.is_absolute() else Path(__file__).resolve().parents[1] / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
