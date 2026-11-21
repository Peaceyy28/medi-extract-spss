"""Unit tests for pyreadstat .sav round-trip integrity, anonymization, and exports."""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pandas as pd
import pyreadstat
import pytest

from app.services.spss_engine import (
    generate_sps_syntax,
    read_sav_file,
    validate_sav_file,
    write_csv_file,
    write_dta_file,
    write_sav_file,
    write_xlsx_with_codebook,
)

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"
SYNTHETIC_SAV = FIXTURES_DIR / "oyshia_encounter_synthetic.sav"


def test_sav_round_trip_preserves_metadata_and_values(tmp_path: Path) -> None:
    df1, vars1, meta1 = read_sav_file(SYNTHETIC_SAV)

    assert len(df1) == 100
    assert len(vars1) == 32
    assert meta1["number_columns"] == 32

    var_by_name = {v.name: v for v in vars1}
    assert len(var_by_name["LGA"].value_labels) == 33
    assert len(var_by_name["Diagnosis1"].value_labels) == 178
    assert len(var_by_name["Investigation1"].value_labels) == 46
    assert len(var_by_name["Treatment1"].value_labels) == 241
    assert var_by_name["Diagnosis1"].value_labels["2.0"] == "Hypertention"
    assert var_by_name["Age"].measure.value == "scale"
    assert var_by_name["Sex"].measure.value == "nominal"

    out_sav = tmp_path / "roundtrip.sav"
    write_sav_file(df1, vars1, out_sav, anonymize=False)
    assert validate_sav_file(out_sav)

    df2, vars2, _ = read_sav_file(out_sav)
    assert list(df1.columns) == list(df2.columns)
    assert len(df1) == len(df2)

    for v1, v2 in zip(vars1, vars2):
        assert v1.name == v2.name
        assert v1.type == v2.type
        assert v1.label == v2.label
        assert v1.measure == v2.measure
        assert v1.value_labels == v2.value_labels

    pd.testing.assert_frame_equal(df1, df2, check_dtype=False)


def test_magic_byte_validation_rejects_spoofed_csv(tmp_path: Path) -> None:
    spoof = tmp_path / "fake.sav"
    spoof.write_text("Year,Month,Age\n2025,1,42\n", encoding="utf-8")

    assert not validate_sav_file(spoof)
    with pytest.raises(ValueError, match="Invalid SPSS .sav binary signature"):
        read_sav_file(spoof)


def test_anonymize_strips_pii_without_mutating_source(tmp_path: Path) -> None:
    df_orig, vars_orig, _ = read_sav_file(SYNTHETIC_SAV)
    orig_cols = list(df_orig.columns)

    anon_sav = tmp_path / "anon.sav"
    write_sav_file(df_orig, vars_orig, anon_sav, anonymize=True)

    # Original frame untouched
    assert list(df_orig.columns) == orig_cols
    assert "Name" in df_orig.columns
    assert "Phone_contact" in df_orig.columns

    df_anon, vars_anon, _ = read_sav_file(anon_sav)
    assert "Name" not in df_anon.columns
    assert "Phone_contact" not in df_anon.columns
    assert "OYSHIA_ID" in df_anon.columns
    assert df_anon["OYSHIA_ID"].iloc[0].startswith("ANON_")
    assert [v.index for v in vars_anon] == list(range(1, len(vars_anon) + 1))


def test_sps_syntax_and_other_exports(tmp_path: Path) -> None:
    df, variables, _ = read_sav_file(SYNTHETIC_SAV)

    sps = generate_sps_syntax(variables, sav_filename="oyshia_encounter_synthetic.sav", include_autorecode=True)
    assert "VARIABLE LABELS" in sps
    assert "VALUE LABELS" in sps
    assert "VARIABLE LEVEL" in sps
    assert "RECODE Age" in sps
    assert "EXECUTE." in sps

    xlsx_path = write_xlsx_with_codebook(df, variables, tmp_path / "export.xlsx", anonymize=False)
    wb = openpyxl.load_workbook(xlsx_path)
    assert wb.sheetnames == ["Data", "Codebook"]
    assert wb["Data"].max_row == 101  # 1 header + 100 cases
    assert wb["Codebook"].max_row == 33  # 1 header + 32 variables

    csv_path = write_csv_file(df, variables, tmp_path / "export.csv", anonymize=True)
    csv_df = pd.read_csv(csv_path)
    assert len(csv_df) == 100
    assert "Name" not in csv_df.columns

    dta_path = write_dta_file(df, variables, tmp_path / "export.dta", anonymize=True)
    dta_df, _ = pyreadstat.read_dta(str(dta_path))
    assert len(dta_df) == 100
    assert "Name" not in dta_df.columns
