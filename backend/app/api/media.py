"""Media serving endpoints for deskewed page scans and WebP provenance crops."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import get_settings

router = APIRouter(tags=["media"])

_SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _resolve_media_file(root_subdir: str, batch_id: str, filename: str) -> Path:
    if (
        not _SAFE_SEGMENT_RE.match(batch_id)
        or not _SAFE_SEGMENT_RE.match(filename)
        or ".." in batch_id
        or ".." in filename
    ):
        raise HTTPException(status_code=400, detail="Invalid media path segment")

    settings = get_settings()
    batch_dir = (settings.data_dir / root_subdir / batch_id).resolve()
    target = (batch_dir / filename).resolve()
    if target.parent != batch_dir or not target.is_file():
        raise HTTPException(status_code=404, detail="Media asset not found")
    return target


@router.get("/crops/{batch_id}/{filename}")
def get_field_crop_image(batch_id: str, filename: str) -> FileResponse:
    """Stream cropped WebP field snippet for paper provenance."""
    path = _resolve_media_file("crops", batch_id, filename)
    return FileResponse(path=str(path), media_type="image/webp", filename=filename)


@router.get("/scans/{batch_id}/{filename}")
def get_full_scan_page_image(batch_id: str, filename: str) -> FileResponse:
    """Stream deskewed, contrast-enhanced full-page WebP scan."""
    path = _resolve_media_file("scans", batch_id, filename)
    return FileResponse(path=str(path), media_type="image/webp", filename=filename)
