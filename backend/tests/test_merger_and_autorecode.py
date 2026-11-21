"""Tests for Multi-Clerk SPSS Harmonizer (.sav Merger) and 1-Click Auto-Recode."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyreadstat
from fastapi.testclient import TestClient


def _write_temp_sav(
    path: Path,
    df: pd.DataFrame,
    column_labels: dict[str, str],
    value_labels: dict[str, dict] | None = None,
    measures: dict[str, str] | None = None,
    formats: dict[str, str] | None = None,
) -> bytes:
    pyreadstat.write_sav(
        df,
        str(path),
        column_labels=column_labels,
        variable_value_labels=value_labels,
        variable_measure=measures,
        variable_format=formats,
    )
    return path.read_bytes()


def test_multi_clerk_harmonizer_inspect_and_execute(
    client: TestClient, tmp_path: Path
) -> None:
    # Seed a clean master schema project via Clerk A template (0 rows initially)
    df_a = pd.DataFrame(
        {
            "Year": [2025.0, 2025.0],
            "Month": [10.0, 10.0],
            "FacilityPHC": ["Adeoyo Hospital", "Ring Road Hospital"],
            "LGA": [6.0, 10.0],
            "OYSHIA_ID": ["OY-001", "OY-002"],
            "Name": ["Patient One", "Patient Two"],
            "Sex": [2.0, 1.0],
            "Age": [34.0, 51.0],
            "Phone_contact": ["0800-111-0001", "0800-111-0002"],
            "Diagnosis1": [265.0, 4.0],
            "Treatment2": [14.0, 1.0],
        }
    )
    a_val_labels = {
        "Sex": {1.0: "Male", 2.0: "Female"},
        "Diagnosis1": {4.0: "Malaria", 265.0: "Eczema"},
        "Treatment2": {1.0: "ACT", 14.0: "Amlodipine"},
    }
    a_bytes = _write_temp_sav(
        tmp_path / "Clerk_A.sav",
        df_a,
        column_labels={c: c for c in df_a.columns},
        value_labels=a_val_labels,
        measures={"Age": "scale", "Sex": "nominal", "Diagnosis1": "nominal"},
        formats={"FacilityPHC": "A20", "Phone_contact": "A15"},
    )

    proj_res = client.post(
        "/api/v1/projects",
        data={"name": "Harmonizer Master", "mode": "sav", "import_cases": "false"},
        files={"file": ("master.sav", a_bytes, "application/octet-stream")},
    )
    assert proj_res.status_code == 201
    pid = proj_res.json()["project_id"]

    # Clerk B introduces:
    # - case drift: treatment2 -> Treatment2
    # - fuzzy drift: Patient_Phone2 -> Phone_contact
    # - codebook collision: 265.0 = Asthma (master has 265.0 = Eczema)
    # - duplicate meaning: 270.0 = Malaria (master has 4.0 = Malaria)
    # - type mismatch: LGA as string "26"
    # - longer string width on FacilityPHC
    # - 1 duplicate encounter matching Clerk A row 1 (OY-001, 2025, 10, Adeoyo Hospital)
    # - 1 logic error: Male (Sex=1) with FIBROID (43.0)
    df_b = pd.DataFrame(
        {
            "Year": [2025.0, 2025.0, 2025.0],
            "Month": [10.0, 10.0, 10.0],
            "FacilityPHC": [
                "Adeoyo Hospital",
                "General Hospital Igboho Specialist Annex",
                "Iseyin General Hospital",
            ],
            "LGA": ["6", "26", "16"],
            "OYSHIA_ID": ["OY-001", "OY-003", "OY-004"],
            "Name": ["Patient One", "Patient Three", "Patient Four"],
            "Sex": [2.0, 2.0, 1.0],
            "Age": [34.0, 29.0, 44.0],
            "Patient_Phone2": ["0800-111-0001", "0800-222-0003", "0800-222-0004"],
            "Diagnosis1": [270.0, 265.0, 43.0],
            "treatment2": [14.0, 1.0, 14.0],
        }
    )
    b_bytes = _write_temp_sav(
        tmp_path / "Clerk_B.sav",
        df_b,
        column_labels={c: c for c in df_b.columns},
        value_labels={
            "Sex": {1.0: "Male", 2.0: "Female"},
            "Diagnosis1": {265.0: "Asthma", 270.0: "Malaria", 43.0: "FIBROID"},
            "treatment2": {1.0: "ACT", 14.0: "Amlodipine"},
        },
        formats={"FacilityPHC": "A45", "LGA": "A4", "Patient_Phone2": "A15"},
    )

    # Clerk C introduces custom column Ward_Note
    df_c = pd.DataFrame(
        {
            "Year": [2025.0],
            "Month": [10.0],
            "FacilityPHC": ["Oyo General"],
            "LGA": [28.0],
            "OYSHIA_ID": ["OY-005"],
            "Name": ["Patient Five"],
            "Sex": [2.0],
            "Age": [40.0],
            "Phone_contact": ["0800-333-0005"],
            "Diagnosis1": [4.0],
            "Treatment2": [1.0],
            "Ward_Note": ["Outpatient Clinic"],
        }
    )
    c_bytes = _write_temp_sav(
        tmp_path / "Clerk_C.sav",
        df_c,
        column_labels={c: c for c in df_c.columns},
        value_labels={"Diagnosis1": {4.0: "Malaria"}},
    )

    # Inspect step
    inspect_res = client.post(
        f"/api/v1/projects/{pid}/merge/inspect",
        files=[
            ("files", ("Clerk_A.sav", a_bytes, "application/octet-stream")),
            ("files", ("Clerk_B.sav", b_bytes, "application/octet-stream")),
            ("files", ("Clerk_C.sav", c_bytes, "application/octet-stream")),
        ],
    )
    assert inspect_res.status_code == 200
    plan = inspect_res.json()
    assert plan["files_uploaded"] == 3
    assert plan["total_rows_across_files"] == 6
    assert plan["cross_file_duplicates_detected"] == 1

    drifts = {(d["source_variable"], d["action"]): d for d in plan["variable_drifts"]}
    assert ("treatment2", "AUTO_RENAME") in drifts
    assert drifts[("treatment2", "AUTO_RENAME")]["suggested_master_variable"] == "Treatment2"
    assert ("Patient_Phone2", "PROMPT_USER") in drifts
    assert drifts[("Patient_Phone2", "PROMPT_USER")]["suggested_master_variable"] == "Phone_contact"
    assert ("Ward_Note", "KEEP_CUSTOM") in drifts

    collisions = {(c["original_code"], c["label"]): c for c in plan["codebook_collisions_resolved"]}
    assert collisions[(265.0, "Asthma")]["new_assigned_code"] == 266.0
    assert collisions[(265.0, "Asthma")]["rows_recoded"] == 1
    assert collisions[(270.0, "Malaria")]["new_assigned_code"] == 4.0
    assert collisions[(270.0, "Malaria")]["rows_recoded"] == 1

    coercions = {(t["variable"], t["from_type"], t["to_type"]): t for t in plan["type_coercions"]}
    assert ("LGA", "string", "numeric") in coercions

    scorecard_by_file = {s["source_file"]: s for s in plan["clerk_quality_scorecard"]}
    assert scorecard_by_file["Clerk_B.sav"]["logic_errors_count"] == 1
    assert scorecard_by_file["Clerk_B.sav"]["codebook_collisions_count"] == 2

    # Execute step with approved mapping Patient_Phone2 -> Phone_contact
    exec_res = client.post(
        f"/api/v1/projects/{pid}/merge/execute",
        json={
            "merge_session_id": plan["merge_session_id"],
            "approved_mappings": {"Clerk_B.sav": {"Patient_Phone2": "Phone_contact"}},
            "deduplicate": True,
            "append_provenance": True,
            "commit_to_project": True,
        },
    )
    assert exec_res.status_code == 200
    merged_meta = exec_res.json()
    assert merged_meta["total_rows_merged"] == 5  # 6 rows - 1 cross-file duplicate
    assert merged_meta["duplicates_removed"] == 1
    assert merged_meta["codebook_recodes_applied"] == 2

    # Download and inspect MASTER_MERGED .sav binary
    dl = client.get(merged_meta["download_url"])
    assert dl.status_code == 200
    out_sav = tmp_path / "downloaded_master.sav"
    out_sav.write_bytes(dl.content)
    df_m, meta_m = pyreadstat.read_sav(str(out_sav))

    assert len(df_m) == 5
    assert "Source_Clerk_ID" in df_m.columns
    assert "Source_File_Name" in df_m.columns
    assert "Orig_Row_No" in df_m.columns
    assert "Ward_Note" in df_m.columns
    assert "Patient_Phone2" not in df_m.columns

    # Unified Diagnosis1 codebook preserves 265=Eczema AND maps 266=Asthma & 4=Malaria
    diag_labels = meta_m.variable_value_labels["Diagnosis1"]
    assert diag_labels[265.0] == "Eczema"
    assert diag_labels[266.0] == "Asthma"
    assert diag_labels[4.0] == "Malaria"

    # Verify Clerk B's Patient Three got recoded to 266.0 (Asthma) and LGA=26.0 numeric, full string preserved
    p3 = df_m.loc[df_m["OYSHIA_ID"] == "OY-003"].iloc[0]
    assert p3["Diagnosis1"] == 266.0
    assert p3["LGA"] == 26.0
    assert p3["FacilityPHC"] == "General Hospital Igboho Specialist Annex"
    assert p3["Phone_contact"] == "0800-222-0003"
    assert p3["Source_File_Name"] == "Clerk_B.sav"


def test_merge_inspect_rejects_fewer_than_two_or_spoofed_files(client: TestClient) -> None:
    res_one = client.post(
        "/api/v1/projects/proj_oyshia_2025/merge/inspect",
        files=[("files", ("only_one.sav", b"$FL2dummy", "application/octet-stream"))],
    )
    assert res_one.status_code == 400

    res_bad = client.post(
        "/api/v1/projects/proj_oyshia_2025/merge/inspect",
        files=[
            ("files", ("a.sav", b"not_sav", "application/octet-stream")),
            ("files", ("b.sav", b"not_sav_either", "application/octet-stream")),
        ],
    )
    assert res_bad.status_code == 400


def test_autorecode_computed_variables_and_sav_export(
    client: TestClient, tmp_path: Path
) -> None:
    res = client.post(
        "/api/v1/projects/proj_oyshia_2025/transform/autorecode",
        json={},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert set(body["variables_added"]) == {
        "Age_Group",
        "Primary_Disease_Category",
        "Comorbidity_Count",
        "Polypharmacy_Count",
    }
    assert body["total_cases_updated"] == 100

    # Idempotent re-run does not duplicate columns
    res2 = client.post("/api/v1/projects/proj_oyshia_2025/transform/autorecode", json={})
    assert res2.status_code == 200
    vars_res = client.get("/api/v1/projects/proj_oyshia_2025/variables")
    var_names = [v["name"] for v in vars_res.json()]
    assert len(var_names) == 36
    assert var_names.count("Age_Group") == 1

    # Export .sav and verify derived Value Labels & Age=140 outlier -> NaN
    sav_res = client.get("/api/v1/projects/proj_oyshia_2025/export/sav")
    assert sav_res.status_code == 200
    out = tmp_path / "recoded.sav"
    out.write_bytes(sav_res.content)
    df, meta = pyreadstat.read_sav(str(out))

    assert meta.variable_value_labels["Age_Group"][5.0] == "60+ Elderly/Pensioner"
    assert meta.variable_value_labels["Primary_Disease_Category"][1.0] == "Cardiovascular/HTN"

    # Row 12 (index 11) has planted Age=140 -> Age_Group should be missing (NaN)
    assert pd.isna(df.iloc[11]["Age_Group"])
    # Row 14 (index 13) has Diagnosis1=4.0 (Malaria) -> Primary_Disease_Category=2.0 (Infectious/Malaria)
    assert df.iloc[13]["Primary_Disease_Category"] == 2.0
    assert df.iloc[13]["Comorbidity_Count"] == 1.0
    assert df.iloc[13]["Polypharmacy_Count"] == 2.0
