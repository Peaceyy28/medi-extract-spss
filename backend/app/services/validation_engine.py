"""Single-pass O(N) Clinical Validation, Prescription Audit (VR-04-RX), and Analyst Reporting."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

import numpy as np
import pandas as pd

from app.schemas import (
    ClinicalAudit,
    ContradictionItem,
    DemographicsAudit,
    FacilityRankingItem,
    MissingnessItem,
    RuleSeverity,
    TopDiagnosisItem,
    ValidationReportFilter,
    ValidationReportResponse,
    ValidationSummary,
    VariableSchema,
    VariableType,
)

FEMALE_ONLY_DIAGNOSIS_CODES: set[float] = {43.0, 44.0, 116.0, 117.0, 121.0, 224.0}
_FEMALE_DX_PATTERN = re.compile(
    r"fibroid|pregnan|anc|miscarr|eclamp|postpartum|menorrh|dysmen|vaginal|pelvic inflam",
    re.I,
)
_MANDATORY_VARS: set[str] = {"OYSHIA_ID", "Name", "Diagnosis1"}

_ANTIDIABETIC_CODES: set[float] = {54.0}
_ANTIDIABETIC_RX_RE = re.compile(r"metformin|glibenclamide|glimepiride|insulin", re.I)
_DIABETIC_DX_CODES: set[float] = {50.0}
_DIABETIC_DX_RE = re.compile(r"diabet|hyperglyc", re.I)

_ANTIHTN_CODES: set[float] = {14.0, 15.0}
_ANTIHTN_RX_RE = re.compile(
    r"amlodipine|lisinopril|nifedipine|losartan|methyldopa|atenolol|bisoprolol",
    re.I,
)
_HTN_DX_CODES: set[float] = {2.0, 117.0}
_HTN_DX_RE = re.compile(r"hypert|cardiac|heart|eclamp|angina|stroke", re.I)

_ANTIMALARIAL_CODES: set[float] = {1.0}
_ANTIMALARIAL_RX_RE = re.compile(
    r"artemether|lumefantrine|artesunate|dihydroartemisinin", re.I
)
_MALARIA_DX_CODES: set[float] = {4.0, 73.0}
_MALARIA_DX_RE = re.compile(r"malaria", re.I)


def _safe_int_token(raw: Any) -> str:
    """Parse integer-like scalar into normalized string without failing on dirty text."""
    if raw is None:
        return ""
    try:
        if pd.isna(raw):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(raw, (int, np.integer)):
        return str(int(raw))
    if isinstance(raw, (float, np.floating)):
        fval = float(raw)
        return "" if math.isnan(fval) or math.isinf(fval) else str(int(fval))
    text = str(raw).strip()
    if not text or text.lower() == "nan":
        return ""
    try:
        return str(int(float(text)))
    except (TypeError, ValueError):
        return text


def compute_whipple_index(ages: pd.Series) -> float | None:
    """Compute Whipple's digit-preference index over ages 23-62 (100 = no heaping, 500 = extreme)."""
    num = pd.to_numeric(ages, errors="coerce").dropna()
    in_range = num[(num >= 23.0) & (num <= 62.0)]
    total = int(len(in_range))
    if total == 0:
        return None
    multiples_of_5 = int(((in_range.round() % 5) == 0).sum())
    return round((500.0 * multiples_of_5) / total, 2)


def apply_report_filters(
    df: pd.DataFrame, filter_req: ValidationReportFilter | None
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Filter DataFrame by facility, LGA, month, and year while preserving 1-based case_index."""
    work = df.copy()
    work["__case_index"] = np.arange(1, len(work) + 1, dtype=np.int64)
    applied: dict[str, Any] = {}

    if filter_req is None:
        applied["issue_type"] = "ALL"
        return work, applied

    if filter_req.facility_phc and "FacilityPHC" in work.columns:
        needle = filter_req.facility_phc.strip().lower()
        if needle:
            mask = (
                work["FacilityPHC"]
                .astype(str)
                .str.lower()
                .str.contains(needle, regex=False, na=False)
            )
            work = work[mask]
            applied["facility_phc"] = filter_req.facility_phc.strip()

    if filter_req.lga_code is not None and str(filter_req.lga_code).strip() != "" and "LGA" in work.columns:
        raw_lga = str(filter_req.lga_code).strip()
        lga_num = pd.to_numeric(work["LGA"], errors="coerce")
        try:
            target_num = float(raw_lga)
            mask = lga_num == target_num
        except ValueError:
            mask = work["LGA"].astype(str).str.strip().str.lower() == raw_lga.lower()
        work = work[mask]
        applied["lga_code"] = raw_lga

    if filter_req.month is not None and "Month" in work.columns:
        month_num = pd.to_numeric(work["Month"], errors="coerce")
        work = work[month_num == float(filter_req.month)]
        applied["month"] = int(filter_req.month)

    if filter_req.year is not None and "Year" in work.columns:
        year_num = pd.to_numeric(work["Year"], errors="coerce")
        work = work[year_num == float(filter_req.year)]
        applied["year"] = int(filter_req.year)

    applied["issue_type"] = (filter_req.issue_type or "ALL").upper()
    return work, applied


def _filter_contradictions_by_issue_type(
    contradictions: list[ContradictionItem], issue_type: str
) -> list[ContradictionItem]:
    norm = (issue_type or "ALL").strip().upper()
    if norm in {"", "ALL"}:
        return contradictions
    alias_map = {
        "RX": "VR-04-RX",
        "PRESCRIPTION": "VR-04-RX",
        "CONTRADICTION": "VR-02",
        "AGE": "VR-01",
        "AGE_OUTLIER": "VR-01",
        "CODEBOOK": "VR-03",
        "DUPLICATE": "VR-05",
        "MISSING": "VR-00",
    }
    target_rule = alias_map.get(norm, norm)
    return [c for c in contradictions if c.rule_id.upper() == target_rule]


def _codes_matching(
    value_labels: dict[str, str], base_codes: set[float], pattern: re.Pattern[str]
) -> set[float]:
    matched = set(base_codes)
    for k, lbl in value_labels.items():
        if pattern.search(lbl):
            try:
                matched.add(float(k))
            except (TypeError, ValueError):
                continue
    return matched


def _label_for_code(value_labels: dict[str, str], code: float) -> str:
    return (
        value_labels.get(f"{float(code)}")
        or value_labels.get(str(int(code)) if float(code).is_integer() else str(code))
        or str(int(code) if float(code).is_integer() else code)
    )


def run_validation_report(
    project_id: str,
    df: pd.DataFrame,
    variables: list[VariableSchema],
    filter_req: ValidationReportFilter | None = None,
    schema_version: str = "1.0.0",
) -> ValidationReportResponse:
    """Execute single-pass vectorized validation rules and generate analyst audit metrics."""
    work, filters_applied = apply_report_filters(df, filter_req)
    total_cases = len(work)
    var_map = {v.name: v for v in variables}

    diag_cols = sorted(
        [c for c in work.columns if re.fullmatch(r"Diagnosis\d+", c)],
        key=lambda c: int(c.replace("Diagnosis", "")),
    )
    treat_cols = sorted(
        [c for c in work.columns if re.fullmatch(r"Treatment\d+", c)],
        key=lambda c: int(c.replace("Treatment", "")),
    )

    diag_labels = var_map["Diagnosis1"].value_labels if "Diagnosis1" in var_map else {}
    treat_labels = var_map["Treatment1"].value_labels if "Treatment1" in var_map else {}
    sex_labels = var_map["Sex"].value_labels if "Sex" in var_map else {"1.0": "Male", "2.0": "Female"}

    case_indices = work["__case_index"].to_numpy()
    flagged_cases: set[int] = set()
    contradictions: list[ContradictionItem] = []

    num_cache: dict[str, pd.Series] = {}
    if total_cases > 0:
        numeric_candidates: list[str] = [
            v.name for v in variables if v.type != VariableType.STRING and v.name in work.columns
        ]
        for extra_col in ("Age", "Sex", *diag_cols, *treat_cols):
            if extra_col in work.columns and extra_col not in numeric_candidates:
                numeric_candidates.append(extra_col)
        for cname in numeric_candidates:
            num_cache[cname] = pd.to_numeric(work[cname], errors="coerce")

    # 1. VR-00: Vectorized Missingness Audit across all variables
    missingness_audit: list[MissingnessItem] = []
    if total_cases > 0:
        for var in variables:
            if var.name not in work.columns:
                continue
            col_series = work[var.name]
            if var.type == VariableType.STRING:
                miss_mask = col_series.isna() | (col_series.astype(str).str.strip() == "")
            else:
                num_col = num_cache.get(var.name)
                if num_col is None:
                    num_col = pd.to_numeric(col_series, errors="coerce")
                miss_mask = num_col.isna()

            miss_count = int(miss_mask.sum())
            if miss_count > 0:
                miss_pct = round((miss_count / total_cases) * 100.0, 2)
                sev = (
                    RuleSeverity.BLOCKER
                    if (var.name in _MANDATORY_VARS and miss_pct >= 5.0)
                    else RuleSeverity.WARNING
                )
                missingness_audit.append(
                    MissingnessItem(
                        variable=var.name,
                        missing_count=miss_count,
                        missing_pct=miss_pct,
                        severity=sev,
                    )
                )
                if var.name in {"OYSHIA_ID", "Diagnosis1"}:
                    for ci in case_indices[miss_mask.to_numpy()]:
                        flagged_cases.add(int(ci))
                        contradictions.append(
                            ContradictionItem(
                                case_index=int(ci),
                                rule_id="VR-00",
                                description=f"Missing mandatory field '{var.name}'",
                            )
                        )

    # 2. VR-01: Single-variable Age bounds (0 <= Age <= 115) & Demographics
    age_mean: float | None = None
    age_median: float | None = None
    age_min: float | None = None
    age_max: float | None = None
    age_outliers = 0
    whipple_idx: float | None = None

    if "Age" in num_cache and total_cases > 0:
        ages = num_cache["Age"]
        valid_ages = ages.dropna()
        if len(valid_ages) > 0:
            age_mean = round(float(valid_ages.mean()), 2)
            age_median = round(float(valid_ages.median()), 2)
            age_min = round(float(valid_ages.min()), 2)
            age_max = round(float(valid_ages.max()), 2)
            whipple_idx = compute_whipple_index(valid_ages)

        outlier_mask = ages.notna() & ((ages < 0.0) | (ages > 115.0))
        age_outliers = int(outlier_mask.sum())
        if age_outliers > 0:
            for ci, bad_age in zip(
                case_indices[outlier_mask.to_numpy()],
                ages[outlier_mask].tolist(),
            ):
                flagged_cases.add(int(ci))
                contradictions.append(
                    ContradictionItem(
                        case_index=int(ci),
                        rule_id="VR-01",
                        description=f"Out-of-range Age ({bad_age}); expected 0..115",
                    )
                )

    sex_distribution: dict[str, int] = {}
    if "Sex" in num_cache and total_cases > 0:
        sex_num = num_cache["Sex"]
        counts = sex_num.dropna().value_counts()
        for code_val, cnt in counts.items():
            lbl = _label_for_code(sex_labels, float(code_val))
            sex_distribution[lbl] = int(cnt)

    # 3. VR-02: Cross-Variable Clinical Contradiction (Male + Female-Only Diagnosis)
    female_codes = _codes_matching(diag_labels, FEMALE_ONLY_DIAGNOSIS_CODES, _FEMALE_DX_PATTERN)
    if "Sex" in num_cache and diag_cols and total_cases > 0:
        is_male = num_cache["Sex"] == 1.0
        for dcol in diag_cols:
            d_num = num_cache[dcol]
            bad_mask = is_male & d_num.isin(female_codes)
            if bad_mask.any():
                for ci, code_val in zip(
                    case_indices[bad_mask.to_numpy()],
                    d_num[bad_mask].tolist(),
                ):
                    lbl = _label_for_code(diag_labels, float(code_val))
                    flagged_cases.add(int(ci))
                    contradictions.append(
                        ContradictionItem(
                            case_index=int(ci),
                            rule_id="VR-02",
                            description=f"Male patient (Sex=1) coded with Diagnosis={int(float(code_val))} ({lbl})",
                        )
                    )

    # 4. VR-03: Allowed Codebook Membership
    if total_cases > 0:
        for var in variables:
            if var.name not in num_cache or not var.value_labels or var.type != VariableType.NUMERIC:
                continue
            allowed = set()
            for k in var.value_labels:
                try:
                    allowed.add(float(k))
                except (TypeError, ValueError):
                    continue
            if not allowed:
                continue
            col_num = num_cache[var.name]
            bad_code_mask = col_num.notna() & ~col_num.isin(allowed)
            if bad_code_mask.any():
                for ci, bad_val in zip(
                    case_indices[bad_code_mask.to_numpy()],
                    col_num[bad_code_mask].tolist(),
                ):
                    flagged_cases.add(int(ci))
                    contradictions.append(
                        ContradictionItem(
                            case_index=int(ci),
                            rule_id="VR-03",
                            description=f"Code {bad_val} in '{var.name}' is outside allowed codebook",
                        )
                    )

    # 5. VR-04-RX: Diagnosis-to-Drug Clinical Plausibility Check (Prescription Audit)
    diag_frame = (
        pd.DataFrame({c: num_cache[c] for c in diag_cols}, index=work.index)
        if diag_cols and total_cases > 0
        else None
    )
    treat_frame = (
        pd.DataFrame({c: num_cache[c] for c in treat_cols}, index=work.index)
        if treat_cols and total_cases > 0
        else None
    )
    if diag_frame is not None and treat_frame is not None:
        antidiab_rx = _codes_matching(treat_labels, _ANTIDIABETIC_CODES, _ANTIDIABETIC_RX_RE)
        diab_dx = _codes_matching(diag_labels, _DIABETIC_DX_CODES, _DIABETIC_DX_RE)

        antihtn_rx = _codes_matching(treat_labels, _ANTIHTN_CODES, _ANTIHTN_RX_RE)
        htn_dx = _codes_matching(diag_labels, _HTN_DX_CODES, _HTN_DX_RE)

        antimal_rx = _codes_matching(treat_labels, _ANTIMALARIAL_CODES, _ANTIMALARIAL_RX_RE)
        malaria_dx = _codes_matching(diag_labels, _MALARIA_DX_CODES, _MALARIA_DX_RE)

        bad_diab = treat_frame.isin(antidiab_rx).any(axis=1) & ~diag_frame.isin(diab_dx).any(axis=1)
        bad_htn = treat_frame.isin(antihtn_rx).any(axis=1) & ~diag_frame.isin(htn_dx).any(axis=1)
        bad_mal = treat_frame.isin(antimal_rx).any(axis=1) & ~diag_frame.isin(malaria_dx).any(axis=1)

        mismatch_mask = (bad_diab | bad_htn | bad_mal).to_numpy()
        if mismatch_mask.any():
            mismatch_positions = np.flatnonzero(mismatch_mask)
            for pos in mismatch_positions:
                ci = int(case_indices[pos])
                row_treats = [
                    float(v) for v in treat_frame.iloc[pos].tolist() if pd.notna(v)
                ]
                row_diags = [
                    float(v) for v in diag_frame.iloc[pos].tolist() if pd.notna(v)
                ]
                unmatched_rx_strs: list[str] = []
                if bad_diab.iloc[pos]:
                    for code in row_treats:
                        if code in antidiab_rx:
                            unmatched_rx_strs.append(f"{_label_for_code(treat_labels, code)} ({int(code)})")
                if bad_htn.iloc[pos]:
                    for code in row_treats:
                        if code in antihtn_rx:
                            unmatched_rx_strs.append(f"{_label_for_code(treat_labels, code)} ({int(code)})")
                if bad_mal.iloc[pos]:
                    for code in row_treats:
                        if code in antimal_rx:
                            unmatched_rx_strs.append(f"{_label_for_code(treat_labels, code)} ({int(code)})")

                dx_strs = [
                    f"{_label_for_code(diag_labels, code)} ({code})"
                    for code in row_diags
                ] or ["None"]
                flagged_cases.add(ci)
                contradictions.append(
                    ContradictionItem(
                        case_index=ci,
                        rule_id="VR-04-RX",
                        description=(
                            f"Diagnosis-to-Drug Mismatch: Prescribed {', '.join(unmatched_rx_strs)} "
                            f"with only {', '.join(dx_strs)} listed under Diagnoses"
                        ),
                    )
                )

    # 6. VR-05: O(1) Hash-Set Duplicate Encounter Check
    duplicates_prevented = 0
    if total_cases > 0 and "OYSHIA_ID" in work.columns:
        seen_hashes: set[str] = set()
        oids = work["OYSHIA_ID"].tolist()
        years = work["Year"].tolist() if "Year" in work.columns else [None] * total_cases
        months = work["Month"].tolist() if "Month" in work.columns else [None] * total_cases
        facs = work["FacilityPHC"].tolist() if "FacilityPHC" in work.columns else [""] * total_cases

        for ci, oid_raw, yr_raw, mo_raw, fac_raw in zip(
            case_indices, oids, years, months, facs
        ):
            oid = "" if oid_raw is None or pd.isna(oid_raw) else str(oid_raw).strip()
            if not oid:
                continue
            yr_s = _safe_int_token(yr_raw)
            mo_s = _safe_int_token(mo_raw)
            fac_s = "" if fac_raw is None or pd.isna(fac_raw) else str(fac_raw).strip()
            digest = hashlib.sha256(f"{oid}|{yr_s}|{mo_s}|{fac_s}".lower().encode("utf-8")).hexdigest()
            if digest in seen_hashes:
                duplicates_prevented += 1
                flagged_cases.add(int(ci))
                contradictions.append(
                    ContradictionItem(
                        case_index=int(ci),
                        rule_id="VR-05",
                        description=f"Duplicate encounter for '{oid}' ({yr_s}-{mo_s}, {fac_s})",
                    )
                )
            else:
                seen_hashes.add(digest)

    # 7. Clinical Audit: Top Diagnoses & Polypharmacy
    top_diagnoses: list[TopDiagnosisItem] = []
    if diag_cols and total_cases > 0:
        stacked_diag = pd.concat(
            [num_cache[c] for c in diag_cols],
            ignore_index=True,
        ).dropna()
        if len(stacked_diag) > 0:
            vc = stacked_diag.value_counts().head(10)
            for code_val, cnt in vc.items():
                fcode = float(code_val)
                top_diagnoses.append(
                    TopDiagnosisItem(
                        code=fcode,
                        label=_label_for_code(diag_labels, fcode),
                        count=int(cnt),
                        pct=round((int(cnt) / total_cases) * 100.0, 2),
                    )
                )

    mean_drugs = 0.0
    if treat_frame is not None:
        drug_counts = treat_frame.notna().sum(axis=1)
        mean_drugs = round(float(drug_counts.mean()), 2)

    # 8. Health Facility Performance Ranking
    facility_ranking: list[FacilityRankingItem] = []
    if "FacilityPHC" in work.columns and total_cases > 0:
        clean_flags = [int(ci) not in flagged_cases for ci in case_indices]
        fac_series = work["FacilityPHC"].fillna("Unspecified Facility").astype(str).str.strip()
        fac_df = pd.DataFrame({"facility": fac_series, "is_clean": clean_flags})
        grouped = fac_df.groupby("facility", as_index=False).agg(
            cases=("is_clean", "count"),
            clean_count=("is_clean", "sum"),
        )
        for row in grouped.to_dict(orient="records"):
            cases_n = int(row["cases"])
            clean_n = int(row["clean_count"])
            facility_ranking.append(
                FacilityRankingItem(
                    facility=str(row["facility"] or "Unspecified Facility"),
                    cases=cases_n,
                    clean_rate_pct=round((clean_n / cases_n) * 100.0, 2) if cases_n else 0.0,
                )
            )
        facility_ranking.sort(key=lambda item: (-item.clean_rate_pct, -item.cases, item.facility))

    flagged_count = len(flagged_cases)
    clean_count = max(0, total_cases - flagged_count)
    clean_rate = round((clean_count / total_cases) * 100.0, 2) if total_cases else 0.0

    filtered_contradictions = _filter_contradictions_by_issue_type(
        contradictions, filter_req.issue_type if filter_req else "ALL"
    )
    filtered_contradictions.sort(key=lambda c: (c.case_index, c.rule_id))

    return ValidationReportResponse(
        schema_version=schema_version,
        project_id=project_id,
        filters_applied=filters_applied,
        summary=ValidationSummary(
            total_cases_evaluated=total_cases,
            clean_cases_count=clean_count,
            clean_rate_pct=clean_rate,
            flagged_cases_count=flagged_count,
            duplicates_prevented=duplicates_prevented,
        ),
        missingness_audit=missingness_audit,
        demographics_audit=DemographicsAudit(
            age_mean=age_mean,
            age_median=age_median,
            age_min=age_min,
            age_max=age_max,
            age_outliers_count=age_outliers,
            digit_preference_whipple_index=whipple_idx,
            sex_distribution=sex_distribution,
        ),
        clinical_audit=ClinicalAudit(
            top_diagnoses=top_diagnoses,
            mean_drugs_per_encounter=mean_drugs,
            contradictions_found=filtered_contradictions,
        ),
        facility_ranking=facility_ranking,
    )
