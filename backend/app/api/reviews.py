"""Guided Verification Station, Batch Extraction, and Semantic Auto-Coder API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas import (
    AutoCodeRequest,
    AutoCodeResponse,
    BatchExtractionResponse,
    ReviewAuditEntry,
    ReviewConfirmRequest,
    ReviewConfirmResponse,
    ReviewItem,
)
from app.services.autocoder import MedicalAutoCoder
from app.services.project_store import get_project_store
from app.services.review_service import (
    confirm_review_and_commit,
    extract_batch_into_project,
)

router = APIRouter(prefix="/projects", tags=["reviews"])


@router.get("/{project_id}/reviews", response_model=list[ReviewItem])
def get_project_reviews(
    project_id: str,
    status: str | None = Query(default=None),
    batch_id: str | None = Query(default=None),
) -> list[ReviewItem]:
    """Fetch Guided Verification Queue items for a project."""
    store = get_project_store()
    if store.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return store.list_reviews(project_id=project_id, status=status, batch_id=batch_id)


@router.post("/{project_id}/reviews/{review_id}/confirm", response_model=ReviewConfirmResponse)
def confirm_review_item(
    project_id: str,
    review_id: str,
    payload: ReviewConfirmRequest,
) -> ReviewConfirmResponse:
    """Confirm, edit, flag, or mark N/A a verification item with immutable audit trail."""
    store = get_project_store()
    try:
        return confirm_review_and_commit(
            store=store, project_id=project_id, review_id=review_id, request=payload
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{project_id}/reviews/{review_id}/audit", response_model=list[ReviewAuditEntry])
def get_review_audit_history(project_id: str, review_id: str) -> list[ReviewAuditEntry]:
    """Return immutable reviewer audit trail for a verification item."""
    store = get_project_store()
    if store.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return store.list_review_audit(project_id=project_id, review_id=review_id)


@router.post("/{project_id}/batches/{batch_id}/extract", response_model=BatchExtractionResponse)
def extract_ingested_batch(project_id: str, batch_id: str) -> BatchExtractionResponse:
    """Run Vision HTR + Semantic Auto-Coder + Confidence Gate on an ingested batch."""
    store = get_project_store()
    try:
        return extract_batch_into_project(
            store=store, project_id=project_id, batch_id=batch_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/{project_id}/autocode", response_model=AutoCodeResponse)
def autocode_clinical_term(project_id: str, payload: AutoCodeRequest) -> AutoCodeResponse:
    """Map a clinical note or prescription string onto a project variable's SPSS codebook."""
    store = get_project_store()
    project = store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    coder = MedicalAutoCoder(variables=project.variables)
    return coder.code_term(
        variable_name=payload.variable_name,
        raw_text=payload.raw_text,
        top_k=payload.top_k,
    )
