"""Health endpoint for backend connectivity and dependency diagnostics."""

from __future__ import annotations

import pyreadstat
from fastapi import APIRouter

from app.config import get_settings
from app.schemas import HealthResponse
from app.services.project_store import get_project_store

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Return service status, schema version, and pyreadstat availability."""
    settings = get_settings()
    store = get_project_store()
    return HealthResponse(
        status="ok",
        schema_version=settings.schema_version,
        pyreadstat_version=getattr(pyreadstat, "__version__", "unknown"),
        active_projects=len(store.list_projects()),
    )
