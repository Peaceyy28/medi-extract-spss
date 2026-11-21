"""Shared pytest fixtures for MediExtract SPSS backend tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import reset_settings_cache
from app.main import create_app
from app.services.fixture_store import reset_fixture_store_cache


@pytest.fixture()
def test_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point MEDIEXTRACT_DATA_DIR to a temporary directory for isolated tests."""
    data_dir = tmp_path / "data"
    monkeypatch.setenv("MEDIEXTRACT_DATA_DIR", str(data_dir))
    reset_settings_cache()
    reset_fixture_store_cache()
    yield data_dir
    reset_settings_cache()
    reset_fixture_store_cache()


@pytest.fixture()
def client(test_env: Path) -> TestClient:
    """Provide an isolated FastAPI TestClient."""
    app = create_app()
    with TestClient(app) as tc:
        yield tc
