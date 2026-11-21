"""Real-time clinical validation and filtered Data Analyst Audit Report API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.config import get_settings
from app.schemas import ValidationReportFilter, ValidationReportResponse
from app.services.project_store import get_project_store
from app.services.report_exporter import (
    export_validation_report_pdf,
    export_validation_report_xlsx,
)
from app.services.validation_engine import run_validation_report

router = APIRouter(prefix="/projects", tags=["reports"])


def _generate_report_for_project(
    project_id: str, filters: ValidationReportFilter | None
) -> tuple[str, ValidationReportResponse]:
    store = get_project_store()
    project = store.get_project(project_id)
    loaded = store.get_dataframe_and_schema(project_id)
    if project is None or loaded is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    df, variables = loaded
    settings = get_settings()
    report = run_validation_report(
        project_id=project_id,
        df=df,
        variables=variables,
        filter_req=filters,
        schema_version=settings.schema_version,
    )
    return project.name, report


def _report_export_path(project_id: str, ext: str) -> tuple[Path, str]:
    settings = get_settings()
    settings.ensure_data_dirs()
    export_dir = (settings.data_dir / "exports" / project_id).resolve()
    export_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{project_id}_validation_audit_{stamp}.{ext}"
    return export_dir / filename, filename


@router.post("/{project_id}/reports/validation", response_model=ValidationReportResponse)
def generate_validation_report(
    project_id: str,
    payload: ValidationReportFilter | None = None,
) -> ValidationReportResponse:
    """Run single-pass O(N) clinical & statistical validation with optional filters."""
    _, report = _generate_report_for_project(project_id, payload)
    return report


@router.post("/{project_id}/validate", response_model=ValidationReportResponse)
def run_quality_validation(
    project_id: str,
    payload: ValidationReportFilter | None = None,
) -> ValidationReportResponse:
    """Alias for Quality Observatory validation trigger (/validate)."""
    _, report = _generate_report_for_project(project_id, payload)
    return report


@router.post("/{project_id}/reports/validation/pdf")
def download_validation_report_pdf(
    project_id: str,
    payload: ValidationReportFilter | None = None,
) -> FileResponse:
    """Generate and stream Data Analyst Validation Audit Report as PDF."""
    project_name, report = _generate_report_for_project(project_id, payload)
    out_path, filename = _report_export_path(project_id, "pdf")
    export_validation_report_pdf(report, project_name, out_path)
    return FileResponse(
        path=str(out_path),
        media_type="application/pdf",
        filename=filename,
    )


@router.post("/{project_id}/reports/validation/xlsx")
def download_validation_report_xlsx(
    project_id: str,
    payload: ValidationReportFilter | None = None,
) -> FileResponse:
    """Generate and stream Data Analyst Validation Audit Report as Excel (.xlsx)."""
    project_name, report = _generate_report_for_project(project_id, payload)
    out_path, filename = _report_export_path(project_id, "xlsx")
    export_validation_report_xlsx(report, project_name, out_path)
    return FileResponse(
        path=str(out_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )


@router.post("/{project_id}/reports/validation/export")
def export_validation_report_file(
    project_id: str,
    format: Literal["pdf", "xlsx"] = Query(default="pdf"),
    payload: ValidationReportFilter | None = None,
) -> dict[str, object]:
    """Generate validation audit report file and return download URL."""
    project_name, report = _generate_report_for_project(project_id, payload)
    out_path, filename = _report_export_path(project_id, format)
    if format == "pdf":
        export_validation_report_pdf(report, project_name, out_path)
    else:
        export_validation_report_xlsx(report, project_name, out_path)

    return {
        "ok": True,
        "project_id": project_id,
        "format": format,
        "filename": filename,
        "size_bytes": out_path.stat().st_size,
        "download_url": f"/api/v1/projects/{project_id}/exports/{filename}",
    }
