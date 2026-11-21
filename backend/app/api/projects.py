"""Multi-Project Workspace endpoints, Variable View schema, and virtualized Data View."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status

from app.config import get_settings
from app.schemas import CasesPageResponse, ProjectListResponse, ProjectSchema, VariableSchema
from app.services.pdf_schema_discovery import validate_pdf_magic_bytes
from app.services.project_store import get_project_store
from app.services.spss_engine import validate_sav_magic_bytes

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=ProjectListResponse)
def list_projects() -> ProjectListResponse:
    """List isolated project workspaces and current scanner watch status."""
    settings = get_settings()
    store = get_project_store()
    return ProjectListResponse(
        projects=store.list_projects(),
        scanner_watch_active=False,
        watch_folder=settings.watch_folder,
    )


@router.post("", response_model=ProjectSchema, status_code=status.HTTP_201_CREATED)
async def create_project(
    name: str = Form(...),
    mode: str | None = Form(default=None),
    watch_folder: str | None = Form(default=None),
    import_cases: bool = Form(default=False),
    file: UploadFile | None = File(default=None),
) -> ProjectSchema:
    """Create an isolated project workspace from a .sav template, blank PDF, or empty schema."""
    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Project name must not be empty.")

    store = get_project_store()
    norm_mode = mode.strip().lower() if mode else None

    if file is None:
        if norm_mode in {None, "", "blank", "empty"}:
            return store.create_project_empty(name=clean_name, watch_folder=watch_folder)
        raise HTTPException(
            status_code=400,
            detail="A template file (.sav or .pdf) is required for the selected mode.",
        )

    payload = await file.read()
    filename = file.filename or "template"
    lower_name = filename.lower()

    if norm_mode in {"sav", "sav_template"} or (
        norm_mode is None and (lower_name.endswith(".sav") or validate_sav_magic_bytes(payload))
    ):
        try:
            return store.create_project_from_sav(
                name=clean_name,
                sav_bytes=payload,
                filename=filename,
                watch_folder=watch_folder,
                import_cases=import_cases,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if norm_mode in {"pdf", "blank_pdf"} or (
        norm_mode is None and (lower_name.endswith(".pdf") or validate_pdf_magic_bytes(payload))
    ):
        try:
            return store.create_project_from_blank_pdf(
                name=clean_name,
                pdf_bytes=payload,
                filename=filename,
                watch_folder=watch_folder,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    raise HTTPException(
        status_code=400,
        detail="Unsupported template file type. Upload a valid IBM SPSS (.sav) or blank questionnaire (.pdf).",
    )


@router.get("/{project_id}", response_model=ProjectSchema)
def get_project(project_id: str) -> ProjectSchema:
    """Return project metadata and SPSS Variable View schema."""
    store = get_project_store()
    project = store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return project


@router.delete("/{project_id}")
def delete_project(project_id: str) -> dict[str, object]:
    """Delete a project workspace and its persisted dataset."""
    store = get_project_store()
    if not store.delete_project(project_id):
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return {"ok": True, "project_id": project_id}


@router.get("/{project_id}/variables", response_model=list[VariableSchema])
def get_project_variables(project_id: str) -> list[VariableSchema]:
    """Return only the SPSS Variable View definitions for a project."""
    store = get_project_store()
    project = store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return project.variables


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
    store = get_project_store()
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
