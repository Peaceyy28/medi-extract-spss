"""Authentic IBM SPSS (.sav), syntax (.sps), Excel, CSV, and Stata (.dta) engine."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import openpyxl
import pandas as pd
import pyreadstat

from app.schemas import MeasureLevel, VariableSchema, VariableType

SAV_MAGIC_SIGNATURES: tuple[bytes, bytes] = (b"$FL2", b"$FL3")

_SPSS_FMT_RE = re.compile(r"^([A-Za-z]+)(\d+)?(?:\.(\d+))?$")
_DIRECT_PII_RE = re.compile(
    r"(^|_)(name|patient_name|full_name|phone|phone_contact|mobile|tel|address|email)($|_)",
    re.IGNORECASE,
)
_PSEUDONYM_ID_RE = re.compile(
    r"(^|_)(oyshia_id|patient_id|enrollee_id)($|_)",
    re.IGNORECASE,
)


def validate_sav_magic_bytes(data: bytes) -> bool:
    """Return True if leading bytes match SPSS .sav binary signature ($FL2/$FL3)."""
    return len(data) >= 4 and data[:4] in SAV_MAGIC_SIGNATURES


def validate_sav_file(path: Path) -> bool:
    """Verify file exists and begins with a valid SPSS .sav signature."""
    if not path.is_file():
        return False
    with path.open("rb") as fh:
        header = fh.read(4)
    return validate_sav_magic_bytes(header)


def parse_spss_format(
    fmt: str | None, fallback_width: int = 8, is_string: bool = False
) -> tuple[VariableType, int, int]:
    """Parse SPSS format string (e.g., F8.0, A40, DATE11) into (VariableType, width, decimals)."""
    if not fmt:
        if is_string:
            return VariableType.STRING, max(1, fallback_width), 0
        return VariableType.NUMERIC, max(1, fallback_width), 0

    match = _SPSS_FMT_RE.match(fmt.strip())
    if not match:
        if is_string:
            return VariableType.STRING, max(1, fallback_width), 0
        return VariableType.NUMERIC, max(1, fallback_width), 0

    prefix = match.group(1).upper()
    width = int(match.group(2)) if match.group(2) else max(1, fallback_width)
    decimals = int(match.group(3)) if match.group(3) else 0

    if prefix.startswith("A"):
        return VariableType.STRING, max(1, width), 0
    if "DATE" in prefix or prefix in {"TIME", "DTIME", "JDATE", "EDATE", "SDATE", "ADATE"}:
        return VariableType.DATE, max(1, width), 0
    return VariableType.NUMERIC, max(1, width), max(0, decimals)


def format_code_key(code: Any, var_type: VariableType) -> str:
    """Format a codebook key into canonical string representation (e.g. 1 -> '1.0')."""
    if var_type == VariableType.STRING:
        return str(code)
    try:
        return str(float(code))
    except (TypeError, ValueError):
        return str(code)


def _normalize_measure(raw_measure: str | None) -> MeasureLevel:
    if raw_measure in {"nominal", "ordinal", "scale"}:
        return MeasureLevel(raw_measure)
    return MeasureLevel.NOMINAL


def _is_missing_scalar(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _clean_json_scalar(value: Any) -> Any:
    """Convert NumPy/Pandas scalars and NaNs into JSON-safe native Python values."""
    if _is_missing_scalar(value):
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        fval = float(value)
        return None if math.isnan(fval) or math.isinf(fval) else fval
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def read_sav_file(path: Path) -> tuple[pd.DataFrame, list[VariableSchema], dict[str, Any]]:
    """Read an authentic SPSS .sav binary file into a DataFrame and VariableSchema list."""
    if not validate_sav_file(path):
        raise ValueError(f"Invalid SPSS .sav binary signature in {path.name}")

    df, meta = pyreadstat.read_sav(str(path), user_missing=True)

    column_labels_map = getattr(meta, "column_names_to_labels", {}) or {}
    orig_formats = getattr(meta, "original_variable_types", {}) or {}
    raw_value_labels = getattr(meta, "variable_value_labels", {}) or {}
    raw_measures = getattr(meta, "variable_measure", {}) or {}
    raw_missing = getattr(meta, "missing_ranges", {}) or {}
    readstat_types = getattr(meta, "readstat_variable_types", {}) or {}

    variables: list[VariableSchema] = []
    for idx, col in enumerate(meta.column_names, start=1):
        is_str = str(readstat_types.get(col, "")).lower() == "string" or (
            col in df.columns and pd.api.types.is_string_dtype(df[col]) and not pd.api.types.is_numeric_dtype(df[col])
        )
        fallback_w = 1
        if is_str and col in df.columns:
            max_bytes = df[col].dropna().astype(str).map(lambda s: len(s.encode("utf-8"))).max()
            if pd.notna(max_bytes):
                fallback_w = max(1, int(max_bytes))

        var_type, width, decimals = parse_spss_format(
            orig_formats.get(col),
            fallback_width=fallback_w if is_str else 8,
            is_string=is_str,
        )

        col_val_labels: dict[str, str] = {}
        for k, v in (raw_value_labels.get(col) or {}).items():
            col_val_labels[format_code_key(k, var_type)] = str(v)

        missing_vals: list[Any] = []
        for rng in raw_missing.get(col) or []:
            if isinstance(rng, dict):
                lo = rng.get("lo")
                hi = rng.get("hi")
                if lo == hi:
                    missing_vals.append(_clean_json_scalar(lo))
                else:
                    missing_vals.append({"lo": _clean_json_scalar(lo), "hi": _clean_json_scalar(hi)})
            else:
                missing_vals.append(_clean_json_scalar(rng))

        variables.append(
            VariableSchema(
                index=idx,
                name=col,
                type=var_type,
                width=width,
                decimals=decimals,
                label=str(column_labels_map.get(col) or ""),
                value_labels=col_val_labels,
                missing_values=missing_vals,
                measure=_normalize_measure(raw_measures.get(col)),
            )
        )

    extra_meta = {
        "file_label": getattr(meta, "file_label", "") or "",
        "number_rows": int(getattr(meta, "number_rows", len(df)) or len(df)),
        "number_columns": int(getattr(meta, "number_columns", len(df.columns)) or len(df.columns)),
    }
    return df, variables, extra_meta


def anonymize_dataframe(
    df: pd.DataFrame, variables: list[VariableSchema]
) -> tuple[pd.DataFrame, list[VariableSchema]]:
    """Strip direct PII columns and pseudonymize enrollee IDs on an export copy."""
    clean_df = df.copy(deep=True)
    kept_vars: list[VariableSchema] = []
    cols_to_drop: list[str] = []

    for var in variables:
        if var.name not in clean_df.columns:
            continue
        if _DIRECT_PII_RE.search(var.name) and "file" not in var.name.lower():
            cols_to_drop.append(var.name)
            continue

        new_var = var.model_copy(deep=True)
        if _PSEUDONYM_ID_RE.search(var.name):
            pseudo_values = [
                f"ANON_{i + 1:05d}" if not _is_missing_scalar(val) else ""
                for i, val in enumerate(clean_df[var.name].tolist())
            ]
            clean_df[var.name] = pseudo_values
            new_var.type = VariableType.STRING
            new_var.width = max(new_var.width, 16)
            new_var.decimals = 0
            new_var.value_labels = {}
        kept_vars.append(new_var)

    if cols_to_drop:
        clean_df = clean_df.drop(columns=cols_to_drop, errors="ignore")

    for new_idx, var in enumerate(kept_vars, start=1):
        var.index = new_idx

    return clean_df, kept_vars


def _prepare_export_frame_and_meta(
    df: pd.DataFrame,
    variables: list[VariableSchema],
    anonymize: bool = False,
) -> tuple[pd.DataFrame, list[VariableSchema]]:
    """Produce synchronized DataFrame and VariableSchema copy ready for binary export."""
    work_df = df.copy(deep=True)
    work_vars = [v.model_copy(deep=True) for v in variables if v.name in work_df.columns]

    # Include any columns present in df not yet listed in variables
    known_names = {v.name for v in work_vars}
    for col in work_df.columns:
        if col not in known_names:
            is_num = pd.api.types.is_numeric_dtype(work_df[col])
            work_vars.append(
                VariableSchema(
                    index=len(work_vars) + 1,
                    name=col,
                    type=VariableType.NUMERIC if is_num else VariableType.STRING,
                    width=8 if is_num else 64,
                    decimals=0,
                    label=col,
                    measure=MeasureLevel.NOMINAL,
                )
            )

    if anonymize:
        work_df, work_vars = anonymize_dataframe(work_df, work_vars)

    ordered_cols = [v.name for v in work_vars]
    work_df = work_df[ordered_cols]

    for var in work_vars:
        if var.type == VariableType.STRING:
            work_df[var.name] = work_df[var.name].map(
                lambda x: "" if _is_missing_scalar(x) else str(x)
            )
            max_bytes = work_df[var.name].map(lambda s: len(s.encode("utf-8"))).max()
            if pd.notna(max_bytes):
                var.width = max(var.width, int(max_bytes), 1)
        elif var.type == VariableType.NUMERIC:
            work_df[var.name] = pd.to_numeric(work_df[var.name], errors="coerce")

    return work_df, work_vars


def write_sav_file(
    df: pd.DataFrame,
    variables: list[VariableSchema],
    output_path: Path,
    anonymize: bool = False,
    file_label: str = "MediExtract SPSS Export",
) -> Path:
    """Write a native IBM SPSS .sav binary file with complete metadata via pyreadstat."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    work_df, work_vars = _prepare_export_frame_and_meta(df, variables, anonymize=anonymize)

    column_labels: dict[str, str] = {}
    variable_value_labels: dict[str, dict[Any, str]] = {}
    variable_measure: dict[str, str] = {}
    variable_format: dict[str, str] = {}
    missing_ranges: dict[str, list[Any]] = {}

    for var in work_vars:
        if var.label:
            column_labels[var.name] = var.label
        variable_measure[var.name] = var.measure.value

        if var.type == VariableType.STRING:
            variable_format[var.name] = f"A{max(1, var.width)}"
            if var.value_labels:
                variable_value_labels[var.name] = {
                    str(k): str(v) for k, v in var.value_labels.items()
                }
        elif var.type == VariableType.DATE:
            variable_format[var.name] = f"DATE{max(9, var.width)}"
        else:
            min_width = max(var.width, var.decimals + 2, 1)
            variable_format[var.name] = f"F{min_width}.{var.decimals}"
            if var.value_labels:
                converted: dict[float, str] = {}
                for k, v in var.value_labels.items():
                    try:
                        converted[float(k)] = str(v)
                    except (TypeError, ValueError):
                        continue
                if converted:
                    variable_value_labels[var.name] = converted

        if var.missing_values:
            col_missing: list[Any] = []
            for item in var.missing_values:
                if isinstance(item, dict) and "lo" in item and "hi" in item:
                    col_missing.append({"lo": item["lo"], "hi": item["hi"]})
                elif item is not None:
                    col_missing.append(item)
            if col_missing:
                missing_ranges[var.name] = col_missing

    pyreadstat.write_sav(
        work_df,
        str(output_path),
        file_label=file_label,
        column_labels=column_labels,
        variable_value_labels=variable_value_labels or None,
        missing_ranges=missing_ranges or None,
        variable_measure=variable_measure,
        variable_format=variable_format,
    )
    return output_path


def _spss_escape(text: str) -> str:
    """Escape single quotes for IBM SPSS syntax strings."""
    return text.replace("'", "''")


def _format_sps_code(code_str: str, var_type: VariableType) -> str:
    if var_type == VariableType.STRING:
        return f"'{_spss_escape(code_str)}'"
    try:
        num = float(code_str)
        if num.is_integer():
            return str(int(num))
        return str(num)
    except (TypeError, ValueError):
        return f"'{_spss_escape(code_str)}'"


def generate_sps_syntax(
    variables: list[VariableSchema],
    sav_filename: str = "dataset.sav",
    include_autorecode: bool = False,
) -> str:
    """Generate reproducible IBM SPSS (.sps) syntax matching Variable View metadata."""
    lines: list[str] = [
        "* MediExtract SPSS — Reproducible IBM SPSS Syntax.",
        f"GET FILE='{_spss_escape(sav_filename)}'.",
        "",
    ]

    labeled = [v for v in variables if v.label]
    if labeled:
        lines.append("VARIABLE LABELS")
        for idx, var in enumerate(labeled):
            terminator = "." if idx == len(labeled) - 1 else ""
            lines.append(f"  {var.name} '{_spss_escape(var.label)}'{terminator}")
        lines.append("")

    val_labeled = [v for v in variables if v.value_labels]
    if val_labeled:
        lines.append("VALUE LABELS")
        for idx, var in enumerate(val_labeled):
            prefix = "  " if idx == 0 else "  /"
            entries = " ".join(
                f"{_format_sps_code(k, var.type)} '{_spss_escape(v)}'"
                for k, v in var.value_labels.items()
            )
            terminator = "." if idx == len(val_labeled) - 1 else ""
            lines.append(f"{prefix}{var.name} {entries}{terminator}")
        lines.append("")

    missing_vars = [v for v in variables if v.missing_values]
    if missing_vars:
        lines.append("MISSING VALUES")
        for idx, var in enumerate(missing_vars):
            vals = []
            for item in var.missing_values:
                if isinstance(item, dict) and "lo" in item and "hi" in item:
                    vals.append(f"{item['lo']} THRU {item['hi']}")
                elif item is not None:
                    vals.append(str(item))
            if vals:
                terminator = "." if idx == len(missing_vars) - 1 else ""
                lines.append(f"  {var.name} ({', '.join(vals)}){terminator}")
        lines.append("")

    if variables:
        lines.append("VARIABLE LEVEL")
        for idx, var in enumerate(variables):
            terminator = "." if idx == len(variables) - 1 else ""
            lines.append(f"  {var.name} ({var.measure.value.upper()}){terminator}")
        lines.append("")

    if include_autorecode:
        lines.extend(
            [
                "* Feature 11: Auto-Recode & Computed Variables.",
                "RECODE Age (LOWEST THRU 4=1) (5 THRU 17=2) (18 THRU 35=3) (36 THRU 59=4) (60 THRU HIGHEST=5) INTO Age_Group.",
                "VARIABLE LABELS Age_Group 'Epidemiological Age Group'.",
                "VALUE LABELS Age_Group 1 'Under 5' 2 '5-17' 3 '18-35' 4 '36-59' 5 '60+ Elderly/Pensioner'.",
                "COMPUTE Comorbidity_Count = NVALID(Diagnosis1 TO Diagnosis7).",
                "COMPUTE Polypharmacy_Count = NVALID(Treatment1 TO Treatment7).",
                "VARIABLE LABELS Comorbidity_Count 'Active Diagnoses Count' Polypharmacy_Count 'Prescribed Drugs Count'.",
                "",
            ]
        )

    lines.append("EXECUTE.")
    lines.append("")
    return "\n".join(lines)


def write_xlsx_with_codebook(
    df: pd.DataFrame,
    variables: list[VariableSchema],
    output_path: Path,
    anonymize: bool = False,
) -> Path:
    """Export dataset to Excel (.xlsx) with Data and Codebook worksheets."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    work_df, work_vars = _prepare_export_frame_and_meta(df, variables, anonymize=anonymize)

    wb = openpyxl.Workbook()
    ws_data = wb.active
    ws_data.title = "Data"

    headers = list(work_df.columns)
    ws_data.append(headers)
    for row in work_df.itertuples(index=False, name=None):
        ws_data.append([_clean_json_scalar(cell) for cell in row])

    ws_codebook = wb.create_sheet(title="Codebook")
    ws_codebook.append(
        ["Index", "Variable", "Type", "Width", "Decimals", "Measure", "Label", "Value Labels"]
    )
    for var in work_vars:
        summary = "; ".join(f"{k}={v}" for k, v in list(var.value_labels.items())[:250])
        ws_codebook.append(
            [
                var.index,
                var.name,
                var.type.value,
                var.width,
                var.decimals,
                var.measure.value,
                var.label,
                summary,
            ]
        )

    wb.save(str(output_path))
    return output_path


def write_csv_file(
    df: pd.DataFrame,
    variables: list[VariableSchema],
    output_path: Path,
    anonymize: bool = False,
) -> Path:
    """Export dataset to UTF-8 CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    work_df, _ = _prepare_export_frame_and_meta(df, variables, anonymize=anonymize)
    work_df.to_csv(output_path, index=False, encoding="utf-8")
    return output_path


def write_dta_file(
    df: pd.DataFrame,
    variables: list[VariableSchema],
    output_path: Path,
    anonymize: bool = False,
) -> Path:
    """Export dataset to Stata (.dta) binary via pyreadstat, honoring Stata metadata limits."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    work_df, work_vars = _prepare_export_frame_and_meta(df, variables, anonymize=anonymize)

    column_labels: dict[str, str] = {}
    variable_value_labels: dict[str, dict[int, str]] = {}

    for var in work_vars:
        if var.label:
            column_labels[var.name] = var.label[:80]
        if var.type == VariableType.NUMERIC and var.value_labels:
            int_labels: dict[int, str] = {}
            all_int = True
            for k, v in var.value_labels.items():
                try:
                    fval = float(k)
                    if not fval.is_integer():
                        all_int = False
                        break
                    int_labels[int(fval)] = str(v)[:80]
                except (TypeError, ValueError):
                    all_int = False
                    break
            if all_int and int_labels:
                variable_value_labels[var.name] = int_labels
                # Ensure Stata integer-compatible values where labeled
                non_na = work_df[var.name].dropna()
                if len(non_na) > 0 and (non_na % 1 == 0).all():
                    work_df[var.name] = work_df[var.name].astype("Int64")

    pyreadstat.write_dta(
        work_df,
        str(output_path),
        column_labels=column_labels or None,
        variable_value_labels=variable_value_labels or None,
        version=14,
    )
    return output_path


def resolve_value_label(value: Any, var: VariableSchema) -> str:
    """Resolve raw cell value to human-readable label for '1 <-> Words' Web SPSS view."""
    cleaned = _clean_json_scalar(value)
    if cleaned is None or cleaned == "":
        return ""

    if var.value_labels:
        key = format_code_key(cleaned, var.type)
        if key in var.value_labels:
            return var.value_labels[key]
        raw_str = str(cleaned)
        if raw_str in var.value_labels:
            return var.value_labels[raw_str]

    if isinstance(cleaned, float) and cleaned.is_integer():
        return str(int(cleaned))
    return str(cleaned)


def dataframe_cell_to_json(value: Any) -> Any:
    """Public wrapper converting DataFrame cell scalar to JSON-safe Python primitive."""
    return _clean_json_scalar(value)
