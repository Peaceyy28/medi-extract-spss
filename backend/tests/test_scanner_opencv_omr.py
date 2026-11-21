"""Tests for Milestone D3: Dual ingestion, OpenCV pre-processing, OMR, WebP crops, and watchdog."""

from __future__ import annotations

import io
import time
from pathlib import Path

import cv2
import numpy as np
import pymupdf
from fastapi.testclient import TestClient
from PIL import Image

from app.schemas import IngestFileStatus, ValidationStatus
from app.services.image_pipeline import (
    DEFAULT_OMR_GROUPS,
    deskew_page,
    enhance_contrast_and_binarize,
    evaluate_omr_checkbox_groups,
    split_document_to_pages,
)


def _draw_synthetic_form_image(
    width: int = 1000,
    height: int = 1400,
    tick_sex: str | None = "Female",
    tick_referral: str | None = "Yes",
    double_tick_sex: bool = False,
) -> np.ndarray:
    """Render a crisp synthetic clinical encounter sheet with bordered checkboxes."""
    img = np.full((height, width, 3), 255, dtype=np.uint8)

    # Header rule and horizontal field lines so deskew has realistic page structure
    cv2.rectangle(img, (80, 60), (920, 1340), (40, 40, 40), 2)
    for y_line in (130, 230, 320, 480, 620, 800, 1000):
        cv2.line(img, (100, y_line), (900, y_line), (50, 50, 50), 2)

    # Draw printed checkbox borders for DEFAULT_OMR_GROUPS
    for group in DEFAULT_OMR_GROUPS:
        var = group["variable_name"]
        for opt in group["options"]:
            bx, by, bw, bh = opt["bbox"]
            x1 = int(round(bx * width))
            y1 = int(round(by * height))
            x2 = int(round((bx + bw) * width))
            y2 = int(round((by + bh) * height))
            cv2.rectangle(img, (x1, y1), (x2, y2), (30, 30, 30), 2)

            label = opt["label"]
            should_tick = False
            if var == "Sex":
                if double_tick_sex:
                    should_tick = True
                elif tick_sex == label:
                    should_tick = True
            elif var == "Referral" and tick_referral == label:
                should_tick = True

            if should_tick:
                # Draw thick interior checkmark / cross inside border inset
                pad = 6
                cv2.line(img, (x1 + pad, y1 + pad), (x2 - pad, y2 - pad), (20, 20, 20), 4)
                cv2.line(img, (x2 - pad, y1 + pad), (x1 + pad, y2 - pad), (20, 20, 20), 4)

    return img


def _encode_png(img_bgr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", img_bgr)
    assert ok
    return buf.tobytes()


def test_opencv_deskew_straightens_tilted_form() -> None:
    base = _draw_synthetic_form_image()
    h, w = base.shape[:2]
    # Rotate clockwise by 7.5 deg (-7.5 in OpenCV positive-CCW convention)
    rot_m = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), -7.5, 1.0)
    tilted = cv2.warpAffine(
        base, rot_m, (w, h), borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255)
    )

    deskewed, applied_angle = deskew_page(tilted)
    assert abs(applied_angle - 7.5) <= 1.5

    # Second pass should show minimal residual tilt
    _, residual = deskew_page(deskewed)
    assert abs(residual) <= 1.0


def test_clahe_enhances_faint_blue_ink() -> None:
    # Off-white paper with faint blue ballpoint ink stroke
    img = np.full((300, 600, 3), (240, 245, 248), dtype=np.uint8)
    cv2.putText(
        img,
        "Malaria + HTN",
        (40, 160),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.5,
        (230, 195, 185),  # faint blue in BGR
        3,
    )
    enhanced_bgr, ink_mask = enhance_contrast_and_binarize(img)
    assert enhanced_bgr.shape == img.shape
    ink_pixels = int(np.count_nonzero(ink_mask))
    assert ink_pixels > 500


def test_multipage_pdf_and_tiff_splitting() -> None:
    # 3-page PDF
    doc = pymupdf.open()
    for p in range(3):
        page = doc.new_page()
        page.insert_text((60, 80), f"Synthetic Form Page {p + 1}", fontsize=14)
    pdf_bytes = doc.tobytes()
    doc.close()

    pdf_pages = split_document_to_pages(pdf_bytes, "application/pdf")
    assert len(pdf_pages) == 3

    # 2-page TIFF
    frames = [
        Image.fromarray(cv2.cvtColor(_draw_synthetic_form_image(), cv2.COLOR_BGR2RGB)),
        Image.fromarray(cv2.cvtColor(_draw_synthetic_form_image(tick_sex="Male"), cv2.COLOR_BGR2RGB)),
    ]
    tif_buf = io.BytesIO()
    frames[0].save(tif_buf, format="TIFF", save_all=True, append_images=frames[1:])
    tiff_pages = split_document_to_pages(tif_buf.getvalue(), "image/tiff")
    assert len(tiff_pages) == 2


def test_deterministic_omr_clear_ambiguous_and_blank() -> None:
    # 1. Clear single ticks -> AUTO_VERIFIED
    clear_img = _draw_synthetic_form_image(tick_sex="Female", tick_referral="Yes")
    _, clear_mask = enhance_contrast_and_binarize(clear_img)
    clear_res = {
        r.variable_name: r
        for r in evaluate_omr_checkbox_groups(clear_mask, page_number=1, batch_id="B1", case_index=1)
    }
    assert clear_res["Sex"].selected_code == 2.0
    assert clear_res["Sex"].selected_label == "Female"
    assert clear_res["Sex"].confidence >= 0.90
    assert clear_res["Sex"].status == ValidationStatus.AUTO_VERIFIED

    assert clear_res["Referral"].selected_code == 2.0
    assert clear_res["Referral"].selected_label == "Yes"
    assert clear_res["Referral"].status == ValidationStatus.AUTO_VERIFIED

    # 2. Ambiguous double-tick -> NEEDS_REVIEW
    dbl_img = _draw_synthetic_form_image(double_tick_sex=True, tick_referral="No")
    _, dbl_mask = enhance_contrast_and_binarize(dbl_img)
    dbl_res = {
        r.variable_name: r
        for r in evaluate_omr_checkbox_groups(dbl_mask, page_number=1, batch_id="B1", case_index=2)
    }
    assert dbl_res["Sex"].selected_code is None
    assert dbl_res["Sex"].status == ValidationStatus.NEEDS_REVIEW
    assert dbl_res["Referral"].selected_code == 1.0

    # 3. Blank boxes (borders only) -> NEEDS_REVIEW (borders must not trigger false positive)
    blank_img = _draw_synthetic_form_image(tick_sex=None, tick_referral=None)
    _, blank_mask = enhance_contrast_and_binarize(blank_img)
    blank_res = {
        r.variable_name: r
        for r in evaluate_omr_checkbox_groups(blank_mask, page_number=1, batch_id="B1", case_index=3)
    }
    assert blank_res["Sex"].selected_code is None
    assert blank_res["Sex"].status == ValidationStatus.NEEDS_REVIEW
    assert blank_res["Referral"].selected_code is None
    assert blank_res["Referral"].status == ValidationStatus.NEEDS_REVIEW


def test_manual_ingest_crops_media_and_duplicate_detection(
    client: TestClient, tmp_path: Path
) -> None:
    # Build 2-page PDF embedding our synthetic PNG forms
    p1 = _encode_png(_draw_synthetic_form_image(tick_sex="Male", tick_referral="No"))
    p2 = _encode_png(_draw_synthetic_form_image(tick_sex="Female", tick_referral="Yes"))

    doc = pymupdf.open()
    for png_bytes in (p1, p2):
        page = doc.new_page(width=595, height=842)
        page.insert_image(page.rect, stream=png_bytes)
    pdf_bytes = doc.tobytes()
    doc.close()

    res = client.post(
        "/api/v1/projects/proj_oyshia_2025/ingest",
        data={"facility": "Adeoyo Maternity Hospital", "reporting_period": "2025-11"},
        files=[("files", ("batch_forms.pdf", pdf_bytes, "application/pdf"))],
    )
    assert res.status_code == 201
    batch = res.json()
    bid = batch["batch_id"]
    assert bid.startswith("BATCH-")
    assert batch["page_count"] == 2
    assert batch["documents"][0]["status"] == IngestFileStatus.INGESTED.value

    # Verify full scan and field crop WebP media endpoints
    full_url = batch["documents"][0]["pages"][0]["full_page_url"]
    crop_url = batch["documents"][0]["pages"][0]["crops"][0]["crop_image_uri"]

    scan_res = client.get(full_url)
    assert scan_res.status_code == 200
    assert scan_res.content[:4] == b"RIFF"
    assert scan_res.content[8:12] == b"WEBP"

    crop_res = client.get(crop_url)
    assert crop_res.status_code == 200
    assert crop_res.content[:4] == b"RIFF"
    assert crop_res.content[8:12] == b"WEBP"

    # Path traversal rejected
    assert client.get(f"/api/v1/crops/{bid}/..%2Fsecret.webp").status_code in {400, 404}

    # Re-upload exact duplicate -> DUPLICATE_SKIPPED
    dup_res = client.post(
        "/api/v1/projects/proj_oyshia_2025/ingest",
        files=[("files", ("batch_forms.pdf", pdf_bytes, "application/pdf"))],
    )
    assert dup_res.status_code == 201
    assert dup_res.json()["documents"][0]["status"] == IngestFileStatus.DUPLICATE_SKIPPED.value
    assert dup_res.json()["documents"][0]["duplicate_of_batch_id"] == bid

    # Local path ingestion
    local_png = tmp_path / "local_encounter.png"
    local_png.write_bytes(_encode_png(_draw_synthetic_form_image(tick_sex="Female")))
    path_res = client.post(
        "/api/v1/projects/proj_oyshia_2025/ingest/paths",
        json={"file_paths": [str(local_png)], "facility": "General Hospital, Igboho"},
    )
    assert path_res.status_code == 201
    assert path_res.json()["source"] == "local_path"
    assert path_res.json()["page_count"] == 1

    # Invalid magic-byte file rejected
    bad_res = client.post(
        "/api/v1/projects/proj_oyshia_2025/ingest",
        files=[("files", ("bad.pdf", b"not-a-scan", "application/pdf"))],
    )
    assert bad_res.status_code == 400


def test_hot_folder_watchdog_live_debounce(client: TestClient, tmp_path: Path) -> None:
    watch_dir = tmp_path / "ScanQueue"
    watch_dir.mkdir(parents=True, exist_ok=True)

    start_res = client.post(
        "/api/v1/scanner/start",
        json={
            "project_id": "proj_oyshia_2025",
            "watch_folder": str(watch_dir),
            "debounce_ms": 100,
        },
    )
    assert start_res.status_code == 200
    assert start_res.json()["active"] is True

    proj_list = client.get("/api/v1/projects").json()
    assert proj_list["scanner_watch_active"] is True

    # Simulate physical scanner writing a PNG file in two chunks
    png_bytes = _encode_png(_draw_synthetic_form_image(tick_sex="Male", tick_referral="Yes"))
    mid = len(png_bytes) // 2
    drop_file = watch_dir / "scanner_sheet_001.png"
    with drop_file.open("wb") as fh:
        fh.write(png_bytes[:mid])
        fh.flush()
        time.sleep(0.05)
        fh.write(png_bytes[mid:])
        fh.flush()

    deadline = time.monotonic() + 6.0
    processed = 0
    while time.monotonic() < deadline:
        st = client.get("/api/v1/scanner/status").json()
        processed = st["files_processed_count"]
        if processed >= 1:
            break
        time.sleep(0.1)

    assert processed >= 1
    assert (watch_dir / "_processed" / "scanner_sheet_001.png").is_file()

    batches = client.get("/api/v1/projects/proj_oyshia_2025/batches").json()
    assert any(b["source"] == "hot_folder" and b["page_count"] == 1 for b in batches)

    stop_res = client.post("/api/v1/scanner/stop")
    assert stop_res.status_code == 200
    assert stop_res.json()["active"] is False
