"""Project listing, Variable View schema, and virtualized SPSS Data View endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.config import get_settings
from app.schemas import CasesPageResponse, ProjectListResponse, ProjectSchema
from app.services.fixture_store import get_fixture_store

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=ProjectListResponse)
def list_projects() -> ProjectListResponse:
    """List projects and current scanner watch status."""
    settings = get_settings()
    store = get_fixture_store()
    return ProjectListResponse(
        projects=store.list_projects(),
        scanner_watch_active=False,
        watch_folder=settings.watch_folder,
    )


@router.get("/{project_id}", response_model=ProjectSchema)
def get_project(project_id: str) -> ProjectSchema:
    """Return project metadata and SPSS Variable View schema."""
    store = get_fixture_store()
    project = store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return project


@router.get("/{project_id}/cases", response_model=CasesPageResponse)
def get_project_cases(
    project_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    search: str | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_dir: Literal["asc", "desc"] = Query(default="asc"),
) -> CasesPageResponse:
    """Return paginated/virtualized SPSS Data View rows with raw codes and Value Labels."""
    store = get_fixture_store()
    page = store.get_cases_page(
        project_id=project_id,
        offset=offset,
        limit=limit,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    if page is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return page
