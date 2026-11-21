"""Application configuration with environment-overridable local data paths."""

from __future__ import annotations

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
    vision_provider_chain: str = "ollama"

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
