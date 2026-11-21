"""Multi-Clerk SPSS Harmonizer & Master Merger API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.schemas import MergeExecuteRequest, MergeExecuteResponse, MergeInspectResponse
from app.services.project_store import get_project_store
from app.services.spss_merger import execute_merge, inspect_merge_files

router = APIRouter(prefix="/projects", tags=["merge"])


@router.post("/{project_id}/merge/inspect", response_model=MergeInspectResponse)
async def inspect_clerk_sav_files(
    project_id: str,
    files: list[UploadFile] = File(...),
) -> MergeInspectResponse:
    """Inspect 2+ clerk .sav files for variable drift, codebook collisions, and type coercions."""
    store = get_project_store()
    uploaded: list[tuple[str, bytes]] = []
    for f in files:
        content = await f.read()
        uploaded.append((f.filename or "clerk.sav", content))

    try:
        return inspect_merge_files(store=store, project_id=project_id, uploaded_files=uploaded)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/merge/execute", response_model=MergeExecuteResponse)
def execute_master_merge(
    project_id: str,
    payload: MergeExecuteRequest,
) -> MergeExecuteResponse:
    """Harmonize, recode, deduplicate, and consolidate clerk .sav files into MASTER_MERGED.sav."""
    store = get_project_store()
    try:
        return execute_merge(store=store, project_id=project_id, request=payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
