"""Tests for Milestone D2 Multi-Project Workspaces & Mode A/B Auto-Schema Discovery."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pyreadstat
from fastapi.testclient import TestClient

from app.services.project_store import reset_project_store_cache

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"
SYNTHETIC_SAV = FIXTURES_DIR / "oyshia_encounter_synthetic.sav"


def _build_blank_questionnaire_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    lines = [
        "AHEAD FAMILY PLANNING ENCOUNTER FORM",
        "1. Facility Name: ____________________________",
        "Patient Name: _______________________________",
        "Sex: [ ] Male  [ ] Female",
        "Age (Years): ____",
        "Date of Visit: ____/____/______",
        "Referral: [ ] No  [ ] Yes",
        "Primary Clinical Diagnosis: ___________________",
    ]
    y = 60
    for line in lines:
        page.insert_text((50, y), line, fontsize=11)
        y += 24
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_create_project_mode_a_sav_template_and_persistence(client: TestClient) -> None:
    sav_bytes = SYNTHETIC_SAV.read_bytes()

    # Schema-only clone (import_cases=false)
    res = client.post(
        "/api/v1/projects",
        data={"name": "AHEAD Study Template", "mode": "sav", "import_cases": "false"},
        files={"file": ("oyshia_template.sav", sav_bytes, "application/octet-stream")},
    )
    assert res.status_code == 201
    proj = res.json()
    pid = proj["project_id"]
    assert pid.startswith("PRJ-")
    assert proj["total_cases"] == 0
    assert len(proj["variables"]) == 32

    # 0-row project should export cleanly as a valid empty .sav
    res_sav = client.get(f"/api/v1/projects/{pid}/export/sav")
    assert res_sav.status_code == 200
    assert res_sav.content[:4] in {b"$FL2", b"$FL3"}

    # Verify SQLite persistence across cache reset
    reset_project_store_cache()
    res_vars = client.get(f"/api/v1/projects/{pid}/variables")
    assert res_vars.status_code == 200
    assert len(res_vars.json()) == 32

    # Clone WITH cases (import_cases=true)
    res_full = client.post(
        "/api/v1/projects",
        data={"name": "OYSHIA Clone Full", "mode": "sav", "import_cases": "true"},
        files={"file": ("oyshia_full.sav", sav_bytes, "application/octet-stream")},
    )
    assert res_full.status_code == 201
    assert res_full.json()["total_cases"] == 100

    # Delete workspace
    del_res = client.delete(f"/api/v1/projects/{pid}")
    assert del_res.status_code == 200
    assert client.get(f"/api/v1/projects/{pid}").status_code == 404


def test_create_project_mode_b_blank_pdf_discovery(client: TestClient) -> None:
    pdf_bytes = _build_blank_questionnaire_pdf()

    res = client.post(
        "/api/v1/projects",
        data={"name": "AHEAD Family Planning Survey", "mode": "pdf"},
        files={"file": ("ahead_blank_form.pdf", pdf_bytes, "application/pdf")},
    )
    assert res.status_code == 201
    proj = res.json()
    assert proj["total_cases"] == 0

    var_map = {v["name"]: v for v in proj["variables"]}
    assert "Sex" in var_map
    assert var_map["Sex"]["value_labels"] == {"1.0": "Male", "2.0": "Female"}
    assert "Age_Years" in var_map
    assert var_map["Age_Years"]["type"] == "numeric"
    assert var_map["Age_Years"]["measure"] == "scale"
    assert "Date_of_Visit" in var_map
    assert var_map["Date_of_Visit"]["type"] == "date"
    assert "Referral" in var_map
    assert var_map["Referral"]["value_labels"] == {"1.0": "No", "2.0": "Yes"}


def test_reject_spoofed_sav_or_pdf_templates(client: TestClient) -> None:
    bad_sav = client.post(
        "/api/v1/projects",
        data={"name": "Spoofed SAV", "mode": "sav"},
        files={"file": ("fake.sav", b"Year,Age\n2025,40\n", "application/octet-stream")},
    )
    assert bad_sav.status_code == 400

    bad_pdf = client.post(
        "/api/v1/projects",
        data={"name": "Spoofed PDF", "mode": "pdf"},
        files={"file": ("fake.pdf", b"not a pdf at all", "application/pdf")},
    )
    assert bad_pdf.status_code == 400
