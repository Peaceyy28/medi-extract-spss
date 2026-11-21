"""D4 Batch Extraction Orchestrator & Guided Verification Commit Service."""

from __future__ import annotations

import uuid
from typing import Any

import numpy as np
import pandas as pd

from app.config import get_settings
from app.schemas import (
    BatchExtractionResponse,
    FieldProvenance,
    IngestFileStatus,
    ReviewConfirmRequest,
    ReviewConfirmResponse,
    ReviewItem,
    SuggestedCandidate,
    ValidationStatus,
    VariableSchema,
    VariableType,
)
from app.services.autocoder import Embedder, get_project_autocoder
from app.services.image_pipeline import DEFAULT_FIELD_BOXES
from app.services.project_store import ProjectWorkspaceManager
from app.services.vision_htr import (
    VisionHTRClient,
    compute_total_confidence,
    evaluate_confidence_gate,
)


def _coerce_value_for_var(raw: Any, var: VariableSchema | None) -> Any:
    if raw is None:
        return np.nan if (var and var.type != VariableType.STRING) else ""
    if var is None:
        return raw
    if var.type == VariableType.STRING:
        return str(raw)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return np.nan


def extract_batch_into_project(
    store: ProjectWorkspaceManager,
    project_id: str,
    batch_id: str,
    vision_client: VisionHTRClient | None = None,
    embedder: Embedder | None = None,
) -> BatchExtractionResponse:
    """Run Vision HTR + OMR merge + Semantic Auto-Coder + Confidence Gate on a batch."""
    loaded = store.get_dataframe_and_schema(project_id)
    if loaded is None:
        raise KeyError(f"Project '{project_id}' not found")

    batch = store.get_batch(project_id, batch_id)
    if batch is None:
        raise KeyError(f"Batch '{batch_id}' not found")

    df, variables = loaded
    var_map = {v.name: v for v in variables}
    settings = get_settings()
    threshold = settings.confidence_threshold

    client = vision_client or VisionHTRClient(settings=settings)
    autocoder = get_project_autocoder(
        project_id=project_id, variables=variables, embedder=embedder
    )
    provenance_map = store.load_provenance(project_id)

    new_rows: list[dict[str, Any]] = []
    quarantined_terms: list[str] = []
    queued_reviews: list[ReviewItem] = []
    auto_verified_count = 0
    pages_processed = 0
    provider_used = ""
    model_used = ""

    target_fields = [v.name for v in variables]

    for doc in batch.documents:
        if doc.status != IngestFileStatus.INGESTED:
            continue

        for page in doc.pages:
            pages_processed += 1
            new_case_index = len(df) + len(new_rows) + 1

            page_filename = f"page_{page.page_number:02d}.webp"
            page_path = settings.data_dir / "scans" / batch_id / page_filename
            if not page_path.is_file():
                raise FileNotFoundError(f"Missing pre-processed scan image: {page_path}")

            htr_out = client.extract_page(
                image_bytes=page_path.read_bytes(),
                target_fields=target_fields,
                page_number=page.page_number,
            )
            provider_used = htr_out.provider_used
            model_used = htr_out.model_used

            row_dict: dict[str, Any] = {
                v.name: ("" if v.type == VariableType.STRING else np.nan)
                for v in variables
            }
            case_prov: dict[str, dict[str, Any]] = {}

            crop_by_var = {c.variable_name: c for c in page.crops}

            # 1) Apply deterministic D3 OMR checkbox results
            omr_vars_handled: set[str] = set()
            for omr in page.omr_results:
                omr_vars_handled.add(omr.variable_name)
                case_prov[omr.variable_name] = omr.provenance.model_dump()
                if omr.status == ValidationStatus.AUTO_VERIFIED and omr.selected_code is not None:
                    row_dict[omr.variable_name] = float(omr.selected_code)
                    auto_verified_count += 1
                else:
                    var_schema = var_map.get(omr.variable_name)
                    cands: list[SuggestedCandidate] = []
                    if var_schema:
                        for k, lbl in var_schema.value_labels.items():
                            try:
                                cands.append(
                                    SuggestedCandidate(
                                        code=float(k),
                                        label=lbl,
                                        similarity=omr.fill_ratios.get(lbl, 0.0),
                                    )
                                )
                            except (TypeError, ValueError):
                                continue
                    rev = ReviewItem(
                        review_id=f"rev_{batch_id}_{new_case_index}_{omr.variable_name}_{uuid.uuid4().hex[:6]}",
                        project_id=project_id,
                        batch_id=batch_id,
                        case_index=new_case_index,
                        patient_summary=f"Case #{new_case_index} ({batch.facility or doc.filename})",
                        variable_name=omr.variable_name,
                        variable_label=var_schema.label if var_schema else omr.variable_name,
                        status=ValidationStatus.NEEDS_REVIEW,
                        raw_handwriting_text=omr.provenance.raw_ocr_text,
                        confidence=omr.confidence,
                        crop_image_url=omr.provenance.crop_image_uri,
                        full_page_url=page.full_page_url,
                        suggested_candidates=cands,
                    )
                    queued_reviews.append(rev)

            # 2) Process Vision HTR fields + Medical Auto-Coder + Confidence Gate
            patient_name = htr_out.fields.get("Name")
            patient_age = htr_out.fields.get("Age")
            patient_fac = htr_out.fields.get("FacilityPHC")
            summary_name = patient_name.raw_text if patient_name else f"Case #{new_case_index}"
            summary_age = f", Age {patient_age.raw_text}" if patient_age else ""
            summary_fac = f" — {patient_fac.raw_text}" if patient_fac else ""
            patient_summary = f"{summary_name} ({summary_age.lstrip(', ')}{summary_fac})".replace("()", "").strip()

            for var_name, pred in htr_out.fields.items():
                if var_name in omr_vars_handled or var_name not in var_map:
                    continue

                var_schema = var_map[var_name]
                crop_art = crop_by_var.get(var_name)
                bbox = crop_art.bbox if crop_art else DEFAULT_FIELD_BOXES.get(var_name, [0.1, 0.1, 0.8, 0.08])
                crop_uri = crop_art.crop_image_uri if crop_art else page.full_page_url

                if var_schema.value_labels:
                    coded = autocoder.code_term(var_name, pred.raw_text)
                    total_conf = compute_total_confidence(
                        pred.ocr_confidence, coded.similarity if not coded.quarantined else 0.0
                    )
                    gate_status = (
                        ValidationStatus.NEEDS_REVIEW
                        if coded.quarantined
                        else evaluate_confidence_gate(total_conf, threshold=threshold)
                    )
                    if coded.quarantined:
                        quarantined_terms.append(pred.raw_text)

                    prov = FieldProvenance(
                        page_number=page.page_number,
                        bbox=bbox,
                        crop_image_uri=crop_uri,
                        raw_ocr_text=pred.raw_text,
                        confidence=total_conf,
                    )
                    case_prov[var_name] = prov.model_dump()

                    if gate_status == ValidationStatus.AUTO_VERIFIED and coded.matched_code is not None:
                        row_dict[var_name] = float(coded.matched_code)
                        auto_verified_count += 1
                    else:
                        rev = ReviewItem(
                            review_id=f"rev_{batch_id}_{new_case_index}_{var_name}_{uuid.uuid4().hex[:6]}",
                            project_id=project_id,
                            batch_id=batch_id,
                            case_index=new_case_index,
                            patient_summary=patient_summary,
                            variable_name=var_name,
                            variable_label=var_schema.label or var_name,
                            status=ValidationStatus.NEEDS_REVIEW,
                            raw_handwriting_text=pred.raw_text,
                            confidence=total_conf,
                            crop_image_url=crop_uri,
                            full_page_url=page.full_page_url,
                            suggested_candidates=coded.candidates,
                        )
                        queued_reviews.append(rev)
                else:
                    total_conf = compute_total_confidence(pred.ocr_confidence, None)
                    gate_status = evaluate_confidence_gate(total_conf, threshold=threshold)
                    prov = FieldProvenance(
                        page_number=page.page_number,
                        bbox=bbox,
                        crop_image_uri=crop_uri,
                        raw_ocr_text=pred.raw_text,
                        confidence=total_conf,
                    )
                    case_prov[var_name] = prov.model_dump()

                    if gate_status == ValidationStatus.AUTO_VERIFIED:
                        row_dict[var_name] = _coerce_value_for_var(pred.raw_text, var_schema)
                        auto_verified_count += 1
                    else:
                        rev = ReviewItem(
                            review_id=f"rev_{batch_id}_{new_case_index}_{var_name}_{uuid.uuid4().hex[:6]}",
                            project_id=project_id,
                            batch_id=batch_id,
                            case_index=new_case_index,
                            patient_summary=patient_summary,
                            variable_name=var_name,
                            variable_label=var_schema.label or var_name,
                            status=ValidationStatus.NEEDS_REVIEW,
                            raw_handwriting_text=pred.raw_text,
                            confidence=total_conf,
                            crop_image_url=crop_uri,
                            full_page_url=page.full_page_url,
                            suggested_candidates=[],
                        )
                        queued_reviews.append(rev)

            provenance_map[str(new_case_index)] = case_prov
            new_rows.append(row_dict)

    if new_rows:
        add_df = pd.DataFrame(new_rows)
        updated_df = pd.concat([df, add_df], ignore_index=True) if len(df) > 0 else add_df
        store.save_provenance(project_id, provenance_map)
        pending_total = store.upsert_reviews_bulk(project_id, queued_reviews)
        store.save_project_dataset(
            project_id, updated_df, variables, pending_reviews=pending_total
        )

    return BatchExtractionResponse(
        ok=True,
        project_id=project_id,
        batch_id=batch_id,
        provider_used=provider_used or "none",
        model_used=model_used or "none",
        pages_processed=pages_processed,
        cases_added=len(new_rows),
        auto_verified_fields=auto_verified_count,
        reviews_queued=len(queued_reviews),
        quarantined_terms=quarantined_terms,
    )


def confirm_review_and_commit(
    store: ProjectWorkspaceManager,
    project_id: str,
    review_id: str,
    request: ReviewConfirmRequest,
) -> ReviewConfirmResponse:
    """Confirm, edit, flag, or mark N/A a review item with immutable audit log & SPSS commit."""
    loaded = store.get_dataframe_and_schema(project_id)
    if loaded is None:
        raise KeyError(f"Project '{project_id}' not found")

    review = store.get_review(project_id, review_id)
    if review is None:
        raise KeyError(f"Review item '{review_id}' not found")

    df, variables = loaded
    var_map = {v.name: v for v in variables}
    var_schema = var_map.get(review.variable_name)

    final_val = request.selected_code
    if request.action == "confirm" and final_val is None:
        if review.suggested_candidates:
            final_val = review.suggested_candidates[0].code
        else:
            final_val = review.raw_handwriting_text
    elif request.action == "edit" and final_val is None:
        final_val = request.corrected_text
    elif request.action == "na":
        final_val = None

    row_idx = review.case_index - 1
    if request.action in {"confirm", "edit", "na"} and 0 <= row_idx < len(df):
        if review.variable_name in df.columns:
            coerced = _coerce_value_for_var(final_val, var_schema)
            df.at[row_idx, review.variable_name] = coerced
            store.save_project_dataset(project_id, df, variables)

    new_status = (
        ValidationStatus.NEEDS_REVIEW
        if request.action == "flag"
        else ValidationStatus.AUTO_VERIFIED
    )

    updated_review, audit_entry, pending_remaining = store.resolve_review(
        project_id=project_id,
        review_id=review_id,
        new_status=new_status,
        action=request.action,
        selected_code=final_val,
        corrected_text=request.corrected_text,
        reviewer=request.reviewer,
        reason=request.reason,
    )
    return ReviewConfirmResponse(
        ok=True,
        review=updated_review,
        audit_entry=audit_entry,
        pending_reviews_remaining=pending_remaining,
    )
