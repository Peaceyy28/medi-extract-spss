"""Native SPSS (.sav), syntax (.sps), Excel, CSV, and Stata export endpoints."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse

from app.config import get_settings
from app.schemas import ExportFormat, ExportRequest, ExportResponse
from app.services.project_store import get_project_store
from app.services.spss_engine import (
    generate_sps_syntax,
    write_csv_file,
    write_dta_file,
    write_sav_file,
    write_xlsx_with_codebook,
)

router = APIRouter(prefix="/projects", tags=["exports"])

_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _sanitize_project_id(project_id: str) -> str:
    if not _SAFE_NAME_RE.match(project_id) or ".." in project_id:
        raise HTTPException(status_code=400, detail="Invalid project identifier")
    return project_id


def _sanitize_filename(filename: str) -> str:
    if not _SAFE_NAME_RE.match(filename) or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid export filename")
    return filename


def _export_dir_for(project_id: str) -> Path:
    settings = get_settings()
    settings.ensure_data_dirs()
    safe_pid = _sanitize_project_id(project_id)
    target = (settings.data_dir / "exports" / safe_pid).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return target


@router.get("/{project_id}/export/sav")
def download_sav_export(
    project_id: str,
    anonymize: bool = Query(default=False),
) -> FileResponse:
    """Generate and stream a genuine IBM SPSS (.sav) binary dataset."""
    store = get_project_store()
    loaded = store.get_dataframe_and_schema(project_id)
    if loaded is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    df, variables = loaded
    suffix = "_anonymized" if anonymize else ""
    filename = f"{project_id}{suffix}.sav"
    out_path = _export_dir_for(project_id) / filename
    write_sav_file(df, variables, out_path, anonymize=anonymize)

    return FileResponse(
        path=str(out_path),
        media_type="application/octet-stream",
        filename=filename,
    )


@router.get("/{project_id}/export/sps", response_class=PlainTextResponse)
def download_sps_export(
    project_id: str,
    include_autorecode: bool = Query(default=False),
) -> PlainTextResponse:
    """Generate and download reproducible IBM SPSS (.sps) syntax."""
    store = get_project_store()
    loaded = store.get_dataframe_and_schema(project_id)
    if loaded is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    _, variables = loaded
    syntax = generate_sps_syntax(
        variables=variables,
        sav_filename=f"{project_id}.sav",
        include_autorecode=include_autorecode,
    )
    return PlainTextResponse(
        content=syntax,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{project_id}.sps"'},
    )


@router.post("/{project_id}/export", response_model=ExportResponse)
def create_export(project_id: str, payload: ExportRequest) -> ExportResponse:
    """Generate an export file (.sav, .sps, .xlsx, .csv, .dta) and return its download URL."""
    store = get_project_store()
    loaded = store.get_dataframe_and_schema(project_id)
    if loaded is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    df, variables = loaded
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    anon_tag = "_anon" if payload.anonymize else ""
    filename = f"{project_id}{anon_tag}_{stamp}.{payload.format.value}"
    out_path = _export_dir_for(project_id) / filename

    if payload.format == ExportFormat.SAV:
        write_sav_file(df, variables, out_path, anonymize=payload.anonymize)
    elif payload.format == ExportFormat.SPS:
        syntax = generate_sps_syntax(variables, sav_filename=f"{project_id}.sav")
        out_path.write_text(syntax, encoding="utf-8")
    elif payload.format == ExportFormat.XLSX:
        write_xlsx_with_codebook(df, variables, out_path, anonymize=payload.anonymize)
    elif payload.format == ExportFormat.CSV:
        write_csv_file(df, variables, out_path, anonymize=payload.anonymize)
    elif payload.format == ExportFormat.DTA:
        write_dta_file(df, variables, out_path, anonymize=payload.anonymize)

    return ExportResponse(
        ok=True,
        project_id=project_id,
        format=payload.format,
        filename=filename,
        size_bytes=out_path.stat().st_size,
        anonymized=payload.anonymize,
        download_url=f"/api/v1/projects/{project_id}/exports/{filename}",
    )


@router.get("/{project_id}/exports/{filename}")
def fetch_generated_export(project_id: str, filename: str) -> FileResponse:
    """Download a previously generated export deliverable by filename."""
    safe_name = _sanitize_filename(filename)
    export_dir = _export_dir_for(project_id)
    file_path = (export_dir / safe_name).resolve()

    if file_path.parent != export_dir or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Export file not found")

    return FileResponse(
        path=str(file_path),
        media_type="application/octet-stream",
        filename=safe_name,
    )
