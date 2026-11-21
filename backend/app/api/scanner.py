"""Scanner Hot-Folder watcher control and live status endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas import ScannerWatchStartRequest, ScannerWatchStatus
from app.services.hot_folder import get_hot_folder_watcher
from app.services.project_store import get_project_store

router = APIRouter(prefix="/scanner", tags=["scanner"])


@router.get("/status", response_model=ScannerWatchStatus)
def get_scanner_status() -> ScannerWatchStatus:
    """Return live Hot-Folder watcher status and processed count."""
    return get_hot_folder_watcher().status()


@router.post("/start", response_model=ScannerWatchStatus)
def start_scanner_watcher(payload: ScannerWatchStartRequest) -> ScannerWatchStatus:
    """Start watching a scanner Hot Folder for a target project."""
    store = get_project_store()
    project = store.get_project(payload.project_id)
    if project is None:
        raise HTTPException(
            status_code=404, detail=f"Project '{payload.project_id}' not found"
        )
    target_folder = payload.watch_folder or project.watch_folder
    return get_hot_folder_watcher().start(
        project_id=payload.project_id,
        watch_folder=target_folder,
        debounce_ms=payload.debounce_ms,
    )


@router.post("/stop", response_model=ScannerWatchStatus)
def stop_scanner_watcher() -> ScannerWatchStatus:
    """Stop the active Hot-Folder watcher cleanly."""
    return get_hot_folder_watcher().stop()
