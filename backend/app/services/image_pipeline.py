"""OpenCV pre-processor, multi-page splitter, deterministic checkbox OMR, and WebP field cropper."""

from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pymupdf
from PIL import Image, ImageSequence

from app.schemas import (
    CroppedFieldArtifact,
    FieldProvenance,
    OmrFieldResult,
    ValidationStatus,
)

DEFAULT_OMR_GROUPS: list[dict[str, Any]] = [
    {
        "variable_name": "Sex",
        "options": [
            {"code": 1.0, "label": "Male", "bbox": [0.16, 0.28, 0.035, 0.025]},
            {"code": 2.0, "label": "Female", "bbox": [0.28, 0.28, 0.035, 0.025]},
        ],
    },
    {
        "variable_name": "Referral",
        "options": [
            {"code": 1.0, "label": "No", "bbox": [0.64, 0.28, 0.035, 0.025]},
            {"code": 2.0, "label": "Yes", "bbox": [0.76, 0.28, 0.035, 0.025]},
        ],
    },
]

DEFAULT_FIELD_BOXES: dict[str, list[float]] = {
    "FacilityPHC": [0.12, 0.12, 0.55, 0.045],
    "OYSHIA_ID": [0.68, 0.12, 0.24, 0.045],
    "Name": [0.12, 0.20, 0.52, 0.045],
    "Age": [0.68, 0.20, 0.20, 0.045],
    "Sex": [0.15, 0.27, 0.22, 0.045],
    "Referral": [0.63, 0.27, 0.22, 0.045],
    "Diagnosis1": [0.12, 0.42, 0.42, 0.06],
    "Treatment1": [0.56, 0.42, 0.36, 0.06],
}


def detect_scan_file_type(data: bytes) -> str | None:
    """Detect scanned document MIME type from leading magic bytes."""
    if len(data) < 4:
        return None
    if data[:5] == b"%PDF-":
        return "application/pdf"
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    return None


def split_document_to_pages(
    data: bytes, mime_type: str, dpi: int = 150
) -> list[np.ndarray]:
    """Split a PDF, multi-page TIFF, PNG, or JPEG payload into BGR NumPy page images."""
    pages: list[np.ndarray] = []

    if mime_type == "application/pdf":
        doc = pymupdf.open(stream=data, filetype="pdf")
        try:
            scale = dpi / 72.0
            mat = pymupdf.Matrix(scale, scale)
            for page in doc:
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                    pix.height, pix.width, pix.n
                )
                if pix.n == 3:
                    bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
                elif pix.n == 4:
                    bgr = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
                else:
                    bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
                pages.append(bgr)
        finally:
            doc.close()
        return pages

    if mime_type == "image/tiff":
        with Image.open(io.BytesIO(data)) as tif:
            for frame in ImageSequence.Iterator(tif):
                rgb = np.array(frame.convert("RGB"), dtype=np.uint8)
                pages.append(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        return pages

    arr = np.frombuffer(data, dtype=np.uint8)
    decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if decoded is None:
        raise ValueError(f"Failed to decode image payload ({mime_type}).")
    pages.append(decoded)
    return pages


def _estimate_skew_angle(gray: np.ndarray) -> float:
    """Estimate document tilt angle in degrees using Hough line segments (fallback minAreaRect)."""
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blurred, 50, 150, apertureSize=3)
    h, w = gray.shape[:2]
    min_len = max(40, int(w * 0.12))
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 720.0,
        threshold=60,
        minLineLength=min_len,
        maxLineGap=20,
    )

    angles: list[float] = []
    weights: list[float] = []
    if lines is not None:
        for line in np.asarray(lines).reshape(-1, 4):
            x1, y1, x2, y2 = int(line[0]), int(line[1]), int(line[2]), int(line[3])
            if x2 < x1:
                x1, y1, x2, y2 = x2, y2, x1, y1
            dx = x2 - x1
            dy = y2 - y1
            length = math.hypot(dx, dy)
            if length < min_len:
                continue
            phi = math.degrees(math.atan2(dy, dx))
            if abs(phi) <= 22.0:
                angles.append(phi)
                weights.append(length)

    if angles:
        order = np.argsort(angles)
        sorted_angles = np.array(angles)[order]
        sorted_weights = np.array(weights)[order]
        cum_w = np.cumsum(sorted_weights)
        cutoff = cum_w[-1] / 2.0
        idx = int(np.searchsorted(cum_w, cutoff))
        return float(sorted_angles[min(idx, len(sorted_angles) - 1)])

    # Fallback: foreground pixel minimum-area bounding box
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(thresh > 0))
    if len(coords) < 50:
        return 0.0
    rect_angle = float(cv2.minAreaRect(coords[:, ::-1])[-1])
    if rect_angle > 45.0:
        rect_angle -= 90.0
    elif rect_angle < -45.0:
        rect_angle += 90.0
    return rect_angle if abs(rect_angle) <= 22.0 else 0.0


def deskew_page(image: np.ndarray) -> tuple[np.ndarray, float]:
    """Straighten a tilted scan page and return (deskewed_image, applied_angle_deg)."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    theta = _estimate_skew_angle(gray)
    if abs(theta) < 0.5 or abs(theta) > 25.0:
        return image.copy(), 0.0

    h, w = image.shape[:2]
    center = (w / 2.0, h / 2.0)
    rot_matrix = cv2.getRotationMatrix2D(center, theta, 1.0)
    rotated = cv2.warpAffine(
        image,
        rot_matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    return rotated, round(theta, 2)


def enhance_contrast_and_binarize(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Enhance faint ballpoint ink via CLAHE and compute inverted binary ink mask."""
    bgr = image if image.ndim == 3 else cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    l_chan, a_chan, b_chan = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    l_enhanced = clahe.apply(l_chan)
    enhanced_bgr = cv2.cvtColor(cv2.merge([l_enhanced, a_chan, b_chan]), cv2.COLOR_LAB2BGR)

    gray = cv2.cvtColor(enhanced_bgr, cv2.COLOR_BGR2GRAY)
    binarized_ink_mask = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        25,
        10,
    )
    return enhanced_bgr, binarized_ink_mask


def _union_bbox(boxes: list[list[float]]) -> list[float]:
    x1 = min(b[0] for b in boxes)
    y1 = min(b[1] for b in boxes)
    x2 = max(b[0] + b[2] for b in boxes)
    y2 = max(b[1] + b[3] for b in boxes)
    return [round(x1, 4), round(y1, 4), round(x2 - x1, 4), round(y2 - y1, 4)]


def evaluate_omr_checkbox_groups(
    binarized_ink_mask: np.ndarray,
    page_number: int,
    batch_id: str,
    case_index: int,
    omr_groups: list[dict[str, Any]] | None = None,
) -> list[OmrFieldResult]:
    """Run deterministic interior-inset pixel-density OMR on checkbox/radio groups."""
    groups = omr_groups if omr_groups is not None else DEFAULT_OMR_GROUPS
    h, w = binarized_ink_mask.shape[:2]

    tick_threshold = 0.14
    margin_threshold = 0.08
    results: list[OmrFieldResult] = []

    for group in groups:
        var_name = str(group["variable_name"])
        options: list[dict[str, Any]] = list(group["options"])
        fill_ratios: dict[str, float] = {}
        scored_options: list[tuple[float, float, str]] = []

        for opt in options:
            bx, by, bw, bh = opt["bbox"]
            px1 = max(0, int(round(bx * w)))
            py1 = max(0, int(round(by * h)))
            px2 = min(w, int(round((bx + bw) * w)))
            py2 = min(h, int(round((by + bh) * h)))

            # Inset interior by 18% so printed square borders do not register as ticks
            box_w = max(1, px2 - px1)
            box_h = max(1, py2 - py1)
            inset_x = max(1, int(round(box_w * 0.18)))
            inset_y = max(1, int(round(box_h * 0.18)))

            ix1 = min(px2, px1 + inset_x)
            iy1 = min(py2, py1 + inset_y)
            ix2 = max(ix1 + 1, px2 - inset_x)
            iy2 = max(iy1 + 1, py2 - inset_y)

            roi = binarized_ink_mask[iy1:iy2, ix1:ix2]
            ratio = float(np.count_nonzero(roi)) / max(int(roi.size), 1)
            ratio_rounded = round(ratio, 4)

            label = str(opt["label"])
            code = float(opt["code"])
            fill_ratios[label] = ratio_rounded
            scored_options.append((ratio, code, label))

        scored_options.sort(key=lambda item: item[0], reverse=True)
        best_ratio, best_code, best_label = scored_options[0]
        second_ratio = scored_options[1][0] if len(scored_options) > 1 else 0.0
        above_threshold = [item for item in scored_options if item[0] >= tick_threshold]

        if len(above_threshold) == 1 and (best_ratio - second_ratio) >= margin_threshold:
            selected_code: float | None = best_code
            selected_label: str | None = best_label
            confidence = min(0.99, round(0.86 + 0.45 * (best_ratio - second_ratio), 4))
            status = (
                ValidationStatus.AUTO_VERIFIED
                if confidence >= 0.90
                else ValidationStatus.NEEDS_REVIEW
            )
            raw_text = best_label
        else:
            selected_code = None
            selected_label = None
            confidence = round(max(0.15, 0.45 - abs(best_ratio - second_ratio)), 4)
            status = ValidationStatus.NEEDS_REVIEW
            raw_text = "AMBIGUOUS_MULTI_TICK" if len(above_threshold) > 1 else "UNMARKED"

        group_bbox = _union_bbox([list(o["bbox"]) for o in options])
        crop_uri = f"/api/v1/crops/{batch_id}/case_{case_index:02d}_{var_name}.webp"

        results.append(
            OmrFieldResult(
                variable_name=var_name,
                selected_code=selected_code,
                selected_label=selected_label,
                fill_ratios=fill_ratios,
                confidence=confidence,
                status=status,
                provenance=FieldProvenance(
                    page_number=page_number,
                    bbox=group_bbox,
                    crop_image_uri=crop_uri,
                    raw_ocr_text=raw_text,
                    confidence=confidence,
                ),
            )
        )

    return results


def save_page_and_field_crops(
    enhanced_bgr: np.ndarray,
    batch_id: str,
    page_number: int,
    case_index: int,
    scans_dir: Path,
    crops_dir: Path,
    field_boxes: dict[str, list[float]] | None = None,
) -> tuple[str, list[CroppedFieldArtifact]]:
    """Persist deskewed full-page WebP and per-field WebP provenance crops."""
    boxes = field_boxes if field_boxes is not None else DEFAULT_FIELD_BOXES
    h, w = enhanced_bgr.shape[:2]

    batch_scans = scans_dir / batch_id
    batch_crops = crops_dir / batch_id
    batch_scans.mkdir(parents=True, exist_ok=True)
    batch_crops.mkdir(parents=True, exist_ok=True)

    page_filename = f"page_{page_number:02d}.webp"
    page_path = batch_scans / page_filename
    cv2.imwrite(str(page_path), enhanced_bgr, [cv2.IMWRITE_WEBP_QUALITY, 82])
    full_page_url = f"/api/v1/scans/{batch_id}/{page_filename}"

    crops: list[CroppedFieldArtifact] = []
    for var_name, bbox in boxes.items():
        bx, by, bw, bh = bbox
        x1 = max(0, int(round(bx * w)) - 4)
        y1 = max(0, int(round(by * h)) - 4)
        x2 = min(w, int(round((bx + bw) * w)) + 4)
        y2 = min(h, int(round((by + bh) * h)) + 4)
        if x2 <= x1:
            x2 = min(w, x1 + 8)
        if y2 <= y1:
            y2 = min(h, y1 + 8)

        crop_img = enhanced_bgr[y1:y2, x1:x2]
        crop_filename = f"case_{case_index:02d}_{var_name}.webp"
        crop_path = batch_crops / crop_filename
        cv2.imwrite(str(crop_path), crop_img, [cv2.IMWRITE_WEBP_QUALITY, 85])

        crops.append(
            CroppedFieldArtifact(
                variable_name=var_name,
                page_number=page_number,
                bbox=bbox,
                crop_image_uri=f"/api/v1/crops/{batch_id}/{crop_filename}",
            )
        )

    return full_page_url, crops
