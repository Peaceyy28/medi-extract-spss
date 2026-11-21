"""Verify Pydantic schemas against docs/shared/02-api-contracts.md and JSON fixtures."""

from __future__ import annotations

import json
from pathlib import Path

from app.schemas import (
    CasesPageResponse,
    MergeInspectResponse,
    ProjectSchema,
    ReviewItem,
    ValidationReportResponse,
)

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"


def test_contract_project_schema_payload() -> None:
    payload = {
        "project_id": "proj_oyshia_2025",
        "name": "OYSHIA Encounter Forms 2025",
        "created_at": "2026-11-13T12:00:00Z",
        "watch_folder": r"C:\EncounterForms\ScanQueue",
        "total_cases": 10981,
        "pending_reviews": 3,
        "variables": [
            {
                "index": 1,
                "name": "Year",
                "type": "numeric",
                "width": 8,
                "decimals": 0,
                "label": "Encounter Calendar Year",
                "value_labels": {},
                "missing_values": [],
                "measure": "scale",
            },
            {
                "index": 7,
                "name": "Sex",
                "type": "numeric",
                "width": 8,
                "decimals": 0,
                "label": "Biological Sex of Enrollee",
                "value_labels": {"1.0": "Male", "2.0": "Female"},
                "missing_values": [],
                "measure": "nominal",
            },
        ],
    }
    model = ProjectSchema.model_validate(payload)
    assert model.project_id == "proj_oyshia_2025"
    assert model.variables[1].value_labels["1.0"] == "Male"


def test_contract_review_validation_and_merge_payloads() -> None:
    review_payload = {
        "review_id": "rev_84_04_diag2",
        "project_id": "proj_oyshia_2025",
        "batch_id": "BATCH-2025-084",
        "case_index": 10982,
        "patient_summary": "Adeleke Taofeeq O. (Male, Age 48) — General Hospital, Igboho",
        "variable_name": "Diagnosis2",
        "variable_label": "Secondary Clinical Diagnosis",
        "status": "NEEDS_REVIEW",
        "raw_handwriting_text": "Mss wrist pain (?trauma)",
        "confidence": 0.68,
        "crop_image_url": "/api/v1/crops/BATCH-2025-084/case_04_Diagnosis2.webp",
        "full_page_url": "/api/v1/scans/BATCH-2025-084/page_04.webp",
        "suggested_candidates": [
            {"code": 1.0, "label": "MSS OF THE WRIST", "similarity": 0.91},
        ],
    }
    review = ReviewItem.model_validate(review_payload)
    assert review.suggested_candidates[0].code == 1.0

    report_payload = {
        "schema_version": "1.0.0",
        "project_id": "proj_oyshia_2025",
        "filters_applied": {"lga_code": "26", "month": 10, "year": 2025},
        "summary": {
            "total_cases_evaluated": 10981,
            "clean_cases_count": 10829,
            "clean_rate_pct": 98.62,
            "flagged_cases_count": 152,
            "duplicates_prevented": 6,
        },
        "missingness_audit": [
            {"variable": "OYSHIA_ID", "missing_count": 14, "missing_pct": 0.13, "severity": "WARNING"}
        ],
        "demographics_audit": {
            "age_mean": 46.4,
            "age_median": 47.0,
            "age_min": 1.0,
            "age_max": 98.0,
            "age_outliers_count": 2,
            "digit_preference_whipple_index": 108.2,
            "sex_distribution": {"Male": 4173, "Female": 6808},
        },
        "clinical_audit": {
            "top_diagnoses": [{"code": 2.0, "label": "Hypertention", "count": 3412, "pct": 31.07}],
            "mean_drugs_per_encounter": 2.84,
            "contradictions_found": [
                {
                    "case_index": 4102,
                    "rule_id": "VR-02",
                    "description": "Male patient (Sex=1) coded with Diagnosis=43 (FIBROID)",
                }
            ],
        },
        "facility_ranking": [
            {"facility": "General Hospital, Igboho", "cases": 1420, "clean_rate_pct": 99.2}
        ],
    }
    report = ValidationReportResponse.model_validate(report_payload)
    assert report.summary.clean_rate_pct == 98.62


def test_generated_json_fixtures_match_contracts() -> None:
    proj = ProjectSchema.model_validate_json(
        (FIXTURES_DIR / "oyshia_project_schema.json").read_text(encoding="utf-8")
    )
    assert len(proj.variables) == 32

    cases = CasesPageResponse.model_validate_json(
        (FIXTURES_DIR / "oyshia_cases_sample.json").read_text(encoding="utf-8")
    )
    assert len(cases.rows) == 25

    reviews_raw = json.loads(
        (FIXTURES_DIR / "oyshia_reviews_sample.json").read_text(encoding="utf-8")
    )
    reviews = [ReviewItem.model_validate(item) for item in reviews_raw]
    assert len(reviews) == 5

    report = ValidationReportResponse.model_validate_json(
        (FIXTURES_DIR / "oyshia_validation_report_sample.json").read_text(encoding="utf-8")
    )
    assert report.summary.total_cases_evaluated == 100

    merge = MergeInspectResponse.model_validate_json(
        (FIXTURES_DIR / "oyshia_merge_inspect_sample.json").read_text(encoding="utf-8")
    )
    assert merge.files_uploaded == 4
