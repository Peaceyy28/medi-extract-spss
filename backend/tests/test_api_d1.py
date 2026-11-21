"""FastAPI endpoint integration tests for Milestone D1."""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pyreadstat
from fastapi.testclient import TestClient

from app.services.spss_engine import validate_sav_magic_bytes


def test_health_and_projects_endpoints(client: TestClient) -> None:
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["schema_version"] == "1.0.0"
    assert body["active_projects"] >= 1

    res_list = client.get("/api/v1/projects")
    assert res_list.status_code == 200
    proj_list = res_list.json()
    assert proj_list["projects"][0]["project_id"] == "proj_oyshia_2025"

    res_one = client.get("/api/v1/projects/proj_oyshia_2025")
    assert res_one.status_code == 200
    proj = res_one.json()
    assert proj["total_cases"] == 100
    assert len(proj["variables"]) == 32

    assert client.get("/api/v1/projects/does_not_exist").status_code == 404


def test_cases_pagination_search_and_labels(client: TestClient) -> None:
    res = client.get("/api/v1/projects/proj_oyshia_2025/cases?offset=0&limit=10")
    assert res.status_code == 200
    data = res.json()
    assert data["total_cases"] == 100
    assert len(data["rows"]) == 10
    first = data["rows"][0]
    assert first["case_index"] == 1
    assert first["labels"]["Sex"] in {"Male", "Female"}

    res_search = client.get("/api/v1/projects/proj_oyshia_2025/cases?search=Igboho&limit=50")
    assert res_search.status_code == 200
    filtered = res_search.json()
    assert 0 < filtered["total_cases"] < 100
    assert all("Igboho" in row["values"]["FacilityPHC"] for row in filtered["rows"])

    res_sorted = client.get("/api/v1/projects/proj_oyshia_2025/cases?sort_by=Age&sort_dir=desc&limit=5")
    assert res_sorted.status_code == 200
    ages = [r["values"]["Age"] for r in res_sorted.json()["rows"]]
    assert ages == sorted(ages, reverse=True)
    assert ages[0] == 140.0  # planted age outlier floats to top


def test_sav_and_sps_direct_downloads(client: TestClient, tmp_path: Path) -> None:
    res_sav = client.get("/api/v1/projects/proj_oyshia_2025/export/sav")
    assert res_sav.status_code == 200
    assert validate_sav_magic_bytes(res_sav.content)

    sav_file = tmp_path / "downloaded.sav"
    sav_file.write_bytes(res_sav.content)
    df, meta = pyreadstat.read_sav(str(sav_file))
    assert len(df) == 100
    assert "Name" in df.columns
    assert meta.variable_value_labels["Diagnosis1"][2.0] == "Hypertention"

    res_anon = client.get("/api/v1/projects/proj_oyshia_2025/export/sav?anonymize=true")
    assert res_anon.status_code == 200
    anon_file = tmp_path / "anon.sav"
    anon_file.write_bytes(res_anon.content)
    df_anon, _ = pyreadstat.read_sav(str(anon_file))
    assert "Name" not in df_anon.columns
    assert "Phone_contact" not in df_anon.columns

    res_sps = client.get("/api/v1/projects/proj_oyshia_2025/export/sps?include_autorecode=true")
    assert res_sps.status_code == 200
    assert "VARIABLE LABELS" in res_sps.text
    assert "RECODE Age" in res_sps.text


def test_post_export_all_formats_and_path_traversal_guard(client: TestClient, tmp_path: Path) -> None:
    for fmt in ("sav", "sps", "xlsx", "csv", "dta"):
        res = client.post(
            "/api/v1/projects/proj_oyshia_2025/export",
            json={"format": fmt, "anonymize": fmt == "csv"},
        )
        assert res.status_code == 200
        meta = res.json()
        assert meta["ok"] is True
        assert meta["format"] == fmt
        assert meta["size_bytes"] > 0

        dl = client.get(meta["download_url"])
        assert dl.status_code == 200
        assert len(dl.content) == meta["size_bytes"]

        if fmt == "xlsx":
            out = tmp_path / "dl.xlsx"
            out.write_bytes(dl.content)
            wb = openpyxl.load_workbook(out)
            assert "Codebook" in wb.sheetnames

    bad = client.get("/api/v1/projects/proj_oyshia_2025/exports/..%2Fsecrets.sav")
    assert bad.status_code in {400, 404}
