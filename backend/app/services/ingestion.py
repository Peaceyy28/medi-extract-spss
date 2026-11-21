"""Dual-mode document ingestion orchestrator (manual uploads, local paths, hot folder)."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.config import get_settings
from app.schemas import (
    BatchRecord,
    IngestedDocumentRecord,
    IngestedPageRecord,
    IngestFileStatus,
    LocalPathIngestRequest,
)
from app.services.image_pipeline import (
    deskew_page,
    detect_scan_file_type,
    enhance_contrast_and_binarize,
    evaluate_omr_checkbox_groups,
    save_page_and_field_crops,
    split_document_to_pages,
)
from app.services.project_store import ProjectWorkspaceManager


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_filename(name: str, fallback_idx: int) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name).strip("._")
    return cleaned or f"scan_{fallback_idx}"


def ingest_files(
    store: ProjectWorkspaceManager,
    project_id: str,
    files: list[tuple[str, bytes]],
    source: Literal["manual_upload", "local_path", "hot_folder"] = "manual_upload",
    facility: str = "",
    reporting_period: str = "",
    description: str = "",
    duplicate_policy: Literal["skip", "allow"] = "skip",
    omr_groups: list[dict[str, Any]] | None = None,
    field_boxes: dict[str, list[float]] | None = None,
) -> BatchRecord:
    """Validate, deduplicate, pre-process, OMR-evaluate, and crop a batch of form scans."""
    project = store.get_project(project_id)
    if project is None:
        raise KeyError(f"Project '{project_id}' not found")

    if not files:
        raise ValueError("At least one scanned document file is required.")

    settings = get_settings()
    settings.ensure_data_dirs()

    batch_id = store.next_batch_id()
    uploads_dir = settings.data_dir / "uploads" / project_id / batch_id
    scans_dir = settings.data_dir / "scans"
    crops_dir = settings.data_dir / "crops"

    documents: list[IngestedDocumentRecord] = []
    batch_page_counter = 0
    valid_or_dup_seen = 0
    seen_hashes_in_batch: dict[str, str] = {}

    for idx, (raw_name, payload) in enumerate(files, start=1):
        safe_name = _safe_filename(raw_name, idx)
        sha256 = hashlib.sha256(payload).hexdigest()
        doc_id = f"doc_{uuid.uuid4().hex[:10]}"
        mime_type = detect_scan_file_type(payload)

        if mime_type is None:
            documents.append(
                IngestedDocumentRecord(
                    document_id=doc_id,
                    filename=safe_name,
                    mime_type="application/octet-stream",
                    sha256=sha256,
                    size_bytes=len(payload),
                    status=IngestFileStatus.REJECTED_INVALID_FORMAT,
                    error="Unsupported or invalid file magic bytes (expected PDF, TIFF, PNG, or JPEG).",
                )
            )
            continue

        valid_or_dup_seen += 1

        if duplicate_policy == "skip":
            prior = store.find_duplicate_document(project_id, sha256)
            if prior is not None or sha256 in seen_hashes_in_batch:
                dup_batch = (
                    prior["batch_id"] if prior is not None else seen_hashes_in_batch[sha256]
                )
                documents.append(
                    IngestedDocumentRecord(
                        document_id=doc_id,
                        filename=safe_name,
                        mime_type=mime_type,
                        sha256=sha256,
                        size_bytes=len(payload),
                        status=IngestFileStatus.DUPLICATE_SKIPPED,
                        duplicate_of_batch_id=dup_batch,
                    )
                )
                continue

        seen_hashes_in_batch[sha256] = batch_id
        uploads_dir.mkdir(parents=True, exist_ok=True)
        (uploads_dir / safe_name).write_bytes(payload)

        raw_pages = split_document_to_pages(payload, mime_type)
        ingested_pages: list[IngestedPageRecord] = []
        for raw_img in raw_pages:
            batch_page_counter += 1
            deskewed, angle_deg = deskew_page(raw_img)
            enhanced_bgr, ink_mask = enhance_contrast_and_binarize(deskewed)
            h, w = enhanced_bgr.shape[:2]

            full_page_url, crops = save_page_and_field_crops(
                enhanced_bgr=enhanced_bgr,
                batch_id=batch_id,
                page_number=batch_page_counter,
                case_index=batch_page_counter,
                scans_dir=scans_dir,
                crops_dir=crops_dir,
                field_boxes=field_boxes,
            )
            omr_results = evaluate_omr_checkbox_groups(
                binarized_ink_mask=ink_mask,
                page_number=batch_page_counter,
                batch_id=batch_id,
                case_index=batch_page_counter,
                omr_groups=omr_groups,
            )
            ingested_pages.append(
                IngestedPageRecord(
                    page_number=batch_page_counter,
                    case_index=batch_page_counter,
                    width=w,
                    height=h,
                    deskew_angle_deg=angle_deg,
                    full_page_url=full_page_url,
                    crops=crops,
                    omr_results=omr_results,
                )
            )

        documents.append(
            IngestedDocumentRecord(
                document_id=doc_id,
                filename=safe_name,
                mime_type=mime_type,
                sha256=sha256,
                size_bytes=len(payload),
                status=IngestFileStatus.INGESTED,
                page_count=len(ingested_pages),
                pages=ingested_pages,
            )
        )

    if valid_or_dup_seen == 0:
        raise ValueError(
            "All uploaded files failed magic-byte validation (expected PDF, TIFF, PNG, or JPEG)."
        )

    batch = BatchRecord(
        batch_id=batch_id,
        project_id=project_id,
        source=source,
        facility=facility,
        reporting_period=reporting_period,
        description=description,
        created_at=_utc_now_iso(),
        document_count=len(documents),
        page_count=batch_page_counter,
        documents=documents,
    )
    store.save_batch(batch)
    return batch


def ingest_local_paths(
    store: ProjectWorkspaceManager,
    project_id: str,
    request: LocalPathIngestRequest,
) -> BatchRecord:
    """Read local filesystem paths and ingest them as a batch."""
    loaded_files: list[tuple[str, bytes]] = []
    for raw_path in request.file_paths:
        p = Path(raw_path).expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(f"Local file not found: {raw_path}")
        loaded_files.append((p.name, p.read_bytes()))

    return ingest_files(
        store=store,
        project_id=project_id,
        files=loaded_files,
        source="local_path",
        facility=request.facility,
        reporting_period=request.reporting_period,
        description=request.description,
        duplicate_policy=request.duplicate_policy,
    )
