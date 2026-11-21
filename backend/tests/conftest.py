"""Shared pytest fixtures for MediExtract SPSS backend tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import reset_settings_cache
from app.main import create_app
from app.services.autocoder import reset_autocoder_cache, reset_embedder_cache
from app.services.fixture_store import reset_fixture_store_cache
from app.services.hot_folder import reset_hot_folder_watcher
from app.services.project_store import reset_project_store_cache


@pytest.fixture()
def test_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Configure isolated temp directory & zero-download stub AI providers for tests."""
    data_dir = tmp_path / "data"
    monkeypatch.setenv("MEDIEXTRACT_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MEDIEXTRACT_EMBEDDING_BACKEND", "stub")
    monkeypatch.setenv("MEDIEXTRACT_VISION_PROVIDER_CHAIN", "stub")
    reset_hot_folder_watcher()
    reset_autocoder_cache()
    reset_embedder_cache()
    reset_settings_cache()
    reset_fixture_store_cache()
    reset_project_store_cache()
    yield data_dir
    reset_hot_folder_watcher()
    reset_autocoder_cache()
    reset_embedder_cache()
    reset_settings_cache()
    reset_fixture_store_cache()
    reset_project_store_cache()


@pytest.fixture()
def client(test_env: Path) -> TestClient:
    """Provide an isolated FastAPI TestClient."""
    app = create_app()
    with TestClient(app) as tc:
        yield tc
