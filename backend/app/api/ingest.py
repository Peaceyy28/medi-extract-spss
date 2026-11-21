"""Dual-mode batch ingestion API (manual upload, local filesystem paths, batch ledger)."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.schemas import BatchRecord, LocalPathIngestRequest
from app.services.ingestion import ingest_files, ingest_local_paths
from app.services.project_store import get_project_store

router = APIRouter(prefix="/projects", tags=["ingestion"])


async def _handle_upload(
    project_id: str,
    files: list[UploadFile],
    facility: str,
    reporting_period: str,
    description: str,
    duplicate_policy: str,
) -> BatchRecord:
    store = get_project_store()
    payloads: list[tuple[str, bytes]] = []
    for f in files:
        content = await f.read()
        payloads.append((f.filename or "scan.pdf", content))

    dup_mode = "allow" if duplicate_policy == "allow" else "skip"
    try:
        return ingest_files(
            store=store,
            project_id=project_id,
            files=payloads,
            source="manual_upload",
            facility=facility,
            reporting_period=reporting_period,
            description=description,
            duplicate_policy=dup_mode,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/ingest", response_model=BatchRecord, status_code=status.HTTP_201_CREATED)
async def ingest_uploaded_scans(
    project_id: str,
    files: list[UploadFile] = File(...),
    facility: str = Form(default=""),
    reporting_period: str = Form(default=""),
    description: str = Form(default=""),
    duplicate_policy: str = Form(default="skip"),
) -> BatchRecord:
    """Ingest uploaded PDF/TIFF/PNG/JPEG encounter form scans."""
    return await _handle_upload(
        project_id, files, facility, reporting_period, description, duplicate_policy
    )


@router.post("/{project_id}/upload", response_model=BatchRecord, status_code=status.HTTP_201_CREATED)
async def upload_alias_scans(
    project_id: str,
    files: list[UploadFile] = File(...),
    facility: str = Form(default=""),
    reporting_period: str = Form(default=""),
    description: str = Form(default=""),
    duplicate_policy: str = Form(default="skip"),
) -> BatchRecord:
    """Alias route matching Receiving Desk user story (/upload)."""
    return await _handle_upload(
        project_id, files, facility, reporting_period, description, duplicate_policy
    )


@router.post(
    "/{project_id}/ingest/paths",
    response_model=BatchRecord,
    status_code=status.HTTP_201_CREATED,
)
def ingest_scans_from_paths(
    project_id: str, payload: LocalPathIngestRequest
) -> BatchRecord:
    """Ingest scanned PDF/image files directly from local filesystem paths."""
    store = get_project_store()
    try:
        return ingest_local_paths(store=store, project_id=project_id, request=payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{project_id}/batches", response_model=list[BatchRecord])
def list_project_batches(project_id: str) -> list[BatchRecord]:
    """List ingested batches for a project."""
    store = get_project_store()
    if store.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return store.list_batches(project_id)


@router.get("/{project_id}/batches/{batch_id}", response_model=BatchRecord)
def get_project_batch(project_id: str, batch_id: str) -> BatchRecord:
    """Fetch full details and page/OMR/crop records for a single batch."""
    store = get_project_store()
    batch = store.get_batch(project_id, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found")
    return batch
