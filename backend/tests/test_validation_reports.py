"""Tests for Milestone D5: Clinical Validation, VR-04-RX Prescription Audit & Reports."""

from __future__ import annotations

import time
from pathlib import Path

import openpyxl
import pandas as pd
import pymupdf
from fastapi.testclient import TestClient

from app.schemas import ValidationReportFilter
from app.services.project_store import get_project_store
from app.services.validation_engine import compute_whipple_index, run_validation_report


def test_validation_detects_all_planted_oyshia_anomalies(client: TestClient) -> None:
    res = client.post("/api/v1/projects/proj_oyshia_2025/reports/validation", json={})
    assert res.status_code == 200
    report = res.json()

    # Also test /validate alias used by Screen 05 Quality Observatory
    res_alias = client.post("/api/v1/projects/proj_oyshia_2025/validate", json={})
    assert res_alias.status_code == 200
    assert res_alias.json()["summary"] == report["summary"]

    summary = report["summary"]
    assert summary["total_cases_evaluated"] == 100
    assert summary["clean_cases_count"] == 95
    assert summary["flagged_cases_count"] == 5
    assert summary["clean_rate_pct"] == 95.0
    assert summary["duplicates_prevented"] == 1

    miss_by_var = {m["variable"]: m for m in report["missingness_audit"]}
    assert miss_by_var["OYSHIA_ID"]["missing_count"] == 1

    demo = report["demographics_audit"]
    assert demo["age_outliers_count"] == 1
    assert demo["age_max"] == 140.0
    assert demo["digit_preference_whipple_index"] is not None
    assert sum(demo["sex_distribution"].values()) == 100

    contradictions = report["clinical_audit"]["contradictions_found"]
    rules_by_case = {(c["case_index"], c["rule_id"]) for c in contradictions}
    assert (11, "VR-00") in rules_by_case  # Missing OYSHIA_ID
    assert (12, "VR-01") in rules_by_case  # Age = 140
    assert (13, "VR-02") in rules_by_case  # Male + FIBROID (43)
    assert (14, "VR-04-RX") in rules_by_case  # Malaria + Metformin & Amlodipine
    assert (15, "VR-05") in rules_by_case  # Duplicate encounter

    assert len(report["clinical_audit"]["top_diagnoses"]) > 0
    assert report["clinical_audit"]["mean_drugs_per_encounter"] > 1.0
    assert len(report["facility_ranking"]) >= 5


def test_validation_custom_filters_and_issue_type(client: TestClient) -> None:
    # Filter by facility & LGA 26 (General Hospital, Igboho)
    res_fac = client.post(
        "/api/v1/projects/proj_oyshia_2025/reports/validation",
        json={"facility_phc": "General Hospital, Igboho", "lga_code": "26", "year": 2025},
    )
    assert res_fac.status_code == 200
    body = res_fac.json()
    assert 10 <= body["summary"]["total_cases_evaluated"] <= 20
    assert body["filters_applied"]["lga_code"] == "26"
    assert len(body["facility_ranking"]) == 1
    assert body["facility_ranking"][0]["facility"] == "General Hospital, Igboho"

    # Filter contradictions strictly to VR-04-RX
    res_rx = client.post(
        "/api/v1/projects/proj_oyshia_2025/reports/validation",
        json={"issue_type": "VR-04-RX"},
    )
    assert res_rx.status_code == 200
    rx_items = res_rx.json()["clinical_audit"]["contradictions_found"]
    assert len(rx_items) >= 1
    assert all(item["rule_id"] == "VR-04-RX" for item in rx_items)
    assert any(item["case_index"] == 14 for item in rx_items)


def test_whipple_index_and_codebook_membership_rule(client: TestClient) -> None:
    assert compute_whipple_index(pd.Series([25, 30, 35, 40, 45, 50])) == 500.0
    assert compute_whipple_index(pd.Series(list(range(23, 63)))) == 100.0
    assert compute_whipple_index(pd.Series([5, 10, 70])) is None

    store = get_project_store()
    df, variables = store.get_dataframe_and_schema("proj_oyshia_2025")  # type: ignore[misc]
    df_bad = df.copy()
    df_bad.loc[0, "Diagnosis1"] = 9999.0  # Invalid codebook code
    rep = run_validation_report("proj_oyshia_2025", df_bad, variables)
    assert any(
        c.case_index == 1 and c.rule_id == "VR-03"
        for c in rep.clinical_audit.contradictions_found
    )


def test_validation_report_pdf_and_xlsx_exports(
    client: TestClient, tmp_path: Path
) -> None:
    # Direct PDF stream
    pdf_res = client.post(
        "/api/v1/projects/proj_oyshia_2025/reports/validation/pdf", json={}
    )
    assert pdf_res.status_code == 200
    assert pdf_res.content[:5] == b"%PDF-"

    pdf_doc = pymupdf.open(stream=pdf_res.content, filetype="pdf")
    full_text = "\n".join(page.get_text("text") for page in pdf_doc)
    pdf_doc.close()
    assert "VR-04-RX" in full_text
    assert "Whipple" in full_text
    assert "95.0%" in full_text

    # Direct Excel stream
    xlsx_res = client.post(
        "/api/v1/projects/proj_oyshia_2025/reports/validation/xlsx", json={}
    )
    assert xlsx_res.status_code == 200
    xlsx_path = tmp_path / "audit.xlsx"
    xlsx_path.write_bytes(xlsx_res.content)
    wb = openpyxl.load_workbook(xlsx_path)
    assert wb.sheetnames == [
        "Summary",
        "Missingness",
        "Top_Diagnoses",
        "Contradictions_Audit",
        "Facility_Ranking",
    ]
    assert wb["Contradictions_Audit"].max_row >= 6

    # JSON export metadata + download endpoint
    meta_res = client.post(
        "/api/v1/projects/proj_oyshia_2025/reports/validation/export?format=pdf",
        json={"issue_type": "VR-04-RX"},
    )
    assert meta_res.status_code == 200
    dl = client.get(meta_res.json()["download_url"])
    assert dl.status_code == 200
    assert dl.content[:5] == b"%PDF-"


def test_single_pass_vectorized_scale_performance(client: TestClient) -> None:
    store = get_project_store()
    df, variables = store.get_dataframe_and_schema("proj_oyshia_2025")  # type: ignore[misc]
    df_5k = pd.concat([df] * 50, ignore_index=True)
    df_5k["OYSHIA_ID"] = [f"SYN-5K-{i:05d}" for i in range(len(df_5k))]

    t0 = time.perf_counter()
    report = run_validation_report("proj_oyshia_2025", df_5k, variables, ValidationReportFilter())
    elapsed = time.perf_counter() - t0

    assert report.summary.total_cases_evaluated == 5000
    assert elapsed < 1.5


def test_validation_narrative_and_dataset_cache_invalidation(
    client: TestClient,
) -> None:
    res = client.post(
        "/api/v1/projects/proj_oyshia_2025/reports/validation",
        json={"include_narrative": True},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["narrative_summary"]
    assert "95.0%" in body["narrative_summary"]

    # PDF includes narrative when include_narrative=True
    pdf_res = client.post(
        "/api/v1/projects/proj_oyshia_2025/reports/validation/pdf",
        json={"include_narrative": True},
    )
    assert pdf_res.status_code == 200
    pdf_doc = pymupdf.open(stream=pdf_res.content, filetype="pdf")
    full_text = "\n".join(page.get_text("text") for page in pdf_doc)
    pdf_doc.close()
    assert "clean-data rate" in full_text

    # Dataset mtime cache invalidates immediately when autorecode mutates dataset.sav
    store = get_project_store()
    df_before, _ = store.get_dataframe_and_schema("proj_oyshia_2025")  # type: ignore[misc]
    assert "Age_Group" not in df_before.columns

    rec_res = client.post("/api/v1/projects/proj_oyshia_2025/transform/autorecode", json={})
    assert rec_res.status_code == 200
    df_after, _ = store.get_dataframe_and_schema("proj_oyshia_2025")  # type: ignore[misc]
    assert "Age_Group" in df_after.columns


def test_narrative_strips_preamble_and_uses_compact_json(client: TestClient) -> None:
    from types import SimpleNamespace

    from app.config import Settings
    from app.services.narrative_writer import generate_report_narrative

    store = get_project_store()
    df, variables = store.get_dataframe_and_schema("proj_oyshia_2025")  # type: ignore[misc]
    report = run_validation_report("proj_oyshia_2025", df, variables, ValidationReportFilter())

    captured_prompts: list[str] = []

    class FakeCompletions:
        def create(self, **kwargs: object) -> object:
            messages = kwargs["messages"]  # type: ignore[index]
            captured_prompts.append(messages[1]["content"])  # type: ignore[index]
            msg = SimpleNamespace(content="Here is a summary:\nClean rate is 95.0% across 100 cases.")
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    class FakeClient:
        def __init__(self) -> None:
            self.chat = SimpleNamespace(completions=FakeCompletions())

    text, provider_used = generate_report_narrative(
        report,
        "OYSHIA 2025",
        settings=Settings(vision_provider_chain="ollama"),
        client_factory=lambda _p: FakeClient(),
    )
    assert provider_used == "ollama:llama3.2:3b"
    assert text.startswith("Clean rate is 95.0%")
    assert captured_prompts[0].startswith('REPORT_JSON:{"project":"OYSHIA 2025"')
