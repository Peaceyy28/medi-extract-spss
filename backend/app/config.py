"""Application configuration with environment-overridable local data and model paths."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent


class Settings(BaseSettings):
    """Runtime settings for MediExtract SPSS FastAPI backend."""

    model_config = SettingsConfigDict(
        env_prefix="MEDIEXTRACT_",
        env_file=str(_BACKEND_DIR / ".env"),
        extra="ignore",
    )

    app_env: str = "development"
    schema_version: str = "1.0.0"
    data_dir: Path = _BACKEND_DIR / "data"
    fixtures_dir: Path = _REPO_ROOT / "fixtures"
    watch_folder: str = r"C:\EncounterForms\ScanQueue"
    cors_origins: list[str] = ["*"]

    # Vision HTR & Narrative provider chain (local Ollama primary; HF / Groq for hosted demos)
    vision_provider_chain: str = "ollama,huggingface,groq"
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_vision_model: str = "qwen2.5vl:3b"
    ollama_narrative_model: str = "llama3.2:3b"
    hf_base_url: str = "https://router.huggingface.co/v1"
    hf_token: str = ""
    hf_vision_model: str = "Qwen/Qwen2.5-VL-7B-Instruct"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_api_key: str = ""
    groq_vision_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"

    # Medical Auto-Coder embedding settings
    embedding_backend: str = "fastembed"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    fastembed_cache_path: str = ""
    confidence_threshold: float = 0.90

    def resolved_fastembed_cache_path(self) -> str | None:
        """Return explicit cache directory for FastEmbed ONNX weights if configured."""
        candidate = self.fastembed_cache_path.strip() or os.environ.get(
            "FASTEMBED_CACHE_PATH", ""
        ).strip()
        return candidate or None

    def ensure_data_dirs(self) -> None:
        """Create required local storage directories on demand."""
        for subdir in ("", "projects", "exports", "uploads", "crops", "scans"):
            target = self.data_dir / subdir if subdir else self.data_dir
            target.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings instance."""
    settings = Settings()
    settings.ensure_data_dirs()
    return settings


def reset_settings_cache() -> None:
    """Clear settings cache (used in test fixtures)."""
    get_settings.cache_clear()
