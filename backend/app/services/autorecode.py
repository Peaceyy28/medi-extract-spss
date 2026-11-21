"""Feature 11: 1-Click SPSS Auto-Recode & Computed Variables Engine."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from app.schemas import AutoRecodeRequest, MeasureLevel, VariableSchema, VariableType

AGE_GROUP_LABELS: dict[str, str] = {
    "1.0": "Under 5",
    "2.0": "5-17",
    "3.0": "18-35",
    "4.0": "36-59",
    "5.0": "60+ Elderly/Pensioner",
}

DISEASE_CATEGORY_LABELS: dict[str, str] = {
    "1.0": "Cardiovascular/HTN",
    "2.0": "Infectious/Malaria",
    "3.0": "Metabolic/Diabetes",
    "4.0": "Musculoskeletal",
    "5.0": "Gastrointestinal/PUD",
    "6.0": "Maternal/Reproductive",
    "7.0": "Respiratory/ENT",
    "8.0": "Other",
}

_CATEGORY_RULES: list[tuple[float, set[float], re.Pattern[str]]] = [
    (
        1.0,
        {2.0},
        re.compile(r"hypert|bp|cardiac|heart|angina|stroke|cvd", re.I),
    ),
    (
        2.0,
        {4.0, 73.0},
        re.compile(r"malaria|typhoid|enteric|sepsis|tb|tuberculosis|hepatitis|hiv|uti|urinary|infect|herpes|tinea|scabies", re.I),
    ),
    (
        3.0,
        {50.0},
        re.compile(r"diabet|hyperchol|hypogly|thyroid|metabolic|gout", re.I),
    ),
    (
        4.0,
        {1.0, 13.0, 91.0},
        re.compile(r"mss|wrist|knee|back pain|arthritis|spondyl|musculo|joint|fracture|sprain", re.I),
    ),
    (
        5.0,
        {22.0},
        re.compile(r"pud|dyspepsia|ulcer|gastr|gerd|appendic|diarrh|gastro", re.I),
    ),
    (
        6.0,
        {43.0, 44.0, 116.0, 117.0, 121.0, 224.0},
        re.compile(r"fibroid|pregnan|anc|miscarr|eclamp|pelvic inflam|pid|postpartum|menorrh|dysmen|vaginal|maternal", re.I),
    ),
    (
        7.0,
        set(),
        re.compile(r"respirat|urti|asthma|bronchit|pneumon|rhinit|tonsill|otitis|ent|cough", re.I),
    ),
]


def _classify_diagnosis_code(code: float, value_labels: dict[str, str]) -> float:
    label = value_labels.get(f"{float(code)}", "") or value_labels.get(str(int(code)), "")
    for cat_code, known_codes, pattern in _CATEGORY_RULES:
        if code in known_codes or (label and pattern.search(label)):
            return cat_code
    return 8.0


def apply_autorecode(
    df: pd.DataFrame,
    variables: list[VariableSchema],
    request: AutoRecodeRequest,
) -> tuple[pd.DataFrame, list[VariableSchema], list[VariableSchema]]:
    """Compute Age_Group, Primary_Disease_Category, Comorbidity_Count, and Polypharmacy_Count."""
    work_df = df.copy(deep=True)
    var_by_name: dict[str, VariableSchema] = {
        v.name: v.model_copy(deep=True) for v in variables
    }
    ordered_vars: list[VariableSchema] = [v.model_copy(deep=True) for v in variables]

    requested_set = set(request.variables) if request.variables else None

    def _want(name: str, flag: bool) -> bool:
        return flag and (requested_set is None or name in requested_set)

    added_vars: list[VariableSchema] = []

    def _upsert_var(new_var: VariableSchema) -> None:
        nonlocal ordered_vars
        if new_var.name in var_by_name:
            ordered_vars = [new_var if v.name == new_var.name else v for v in ordered_vars]
        else:
            ordered_vars.append(new_var)
        var_by_name[new_var.name] = new_var
        added_vars.append(new_var)

    # 1. Age_Group
    if _want("Age_Group", request.include_age_group) and "Age" in work_df.columns:
        ages = pd.to_numeric(work_df["Age"], errors="coerce")
        valid_mask = ages.notna() & (ages >= 0.0) & (ages <= 115.0)
        bins = [-0.1, 4.999999, 17.999999, 35.999999, 59.999999, 115.0]
        recoded = pd.cut(ages.where(valid_mask), bins=bins, labels=[1.0, 2.0, 3.0, 4.0, 5.0])
        work_df["Age_Group"] = pd.to_numeric(recoded, errors="coerce").astype("float64")
        _upsert_var(
            VariableSchema(
                index=len(ordered_vars) + 1,
                name="Age_Group",
                type=VariableType.NUMERIC,
                width=8,
                decimals=0,
                label="Epidemiological Age Group",
                value_labels=AGE_GROUP_LABELS,
                measure=MeasureLevel.ORDINAL,
            )
        )

    # 2. Primary_Disease_Category
    if _want("Primary_Disease_Category", request.include_disease_category) and "Diagnosis1" in work_df.columns:
        diag1_var = var_by_name.get("Diagnosis1")
        diag_labels = diag1_var.value_labels if diag1_var else {}
        diag_series = pd.to_numeric(work_df["Diagnosis1"], errors="coerce")
        unique_codes = [float(c) for c in diag_series.dropna().unique().tolist()]
        code_to_cat = {c: _classify_diagnosis_code(c, diag_labels) for c in unique_codes}
        work_df["Primary_Disease_Category"] = diag_series.map(
            lambda x: code_to_cat.get(float(x), np.nan) if pd.notna(x) else np.nan
        ).astype("float64")
        _upsert_var(
            VariableSchema(
                index=len(ordered_vars) + 1,
                name="Primary_Disease_Category",
                type=VariableType.NUMERIC,
                width=8,
                decimals=0,
                label="Broad Primary Disease Category",
                value_labels=DISEASE_CATEGORY_LABELS,
                measure=MeasureLevel.NOMINAL,
            )
        )

    # 3. Comorbidity_Count
    diag_cols = sorted(
        [c for c in work_df.columns if re.fullmatch(r"Diagnosis\d+", c)],
        key=lambda c: int(c.replace("Diagnosis", "")),
    )
    if _want("Comorbidity_Count", request.include_counts) and diag_cols:
        work_df["Comorbidity_Count"] = (
            work_df[diag_cols].notna().sum(axis=1).astype("float64")
        )
        _upsert_var(
            VariableSchema(
                index=len(ordered_vars) + 1,
                name="Comorbidity_Count",
                type=VariableType.NUMERIC,
                width=8,
                decimals=0,
                label="Active Diagnoses Count per Encounter",
                value_labels={},
                measure=MeasureLevel.SCALE,
            )
        )

    # 4. Polypharmacy_Count
    treat_cols = sorted(
        [c for c in work_df.columns if re.fullmatch(r"Treatment\d+", c)],
        key=lambda c: int(c.replace("Treatment", "")),
    )
    if _want("Polypharmacy_Count", request.include_counts) and treat_cols:
        work_df["Polypharmacy_Count"] = (
            work_df[treat_cols].notna().sum(axis=1).astype("float64")
        )
        _upsert_var(
            VariableSchema(
                index=len(ordered_vars) + 1,
                name="Polypharmacy_Count",
                type=VariableType.NUMERIC,
                width=8,
                decimals=0,
                label="Prescribed Medications Count per Encounter",
                value_labels={},
                measure=MeasureLevel.SCALE,
            )
        )

    for idx, var in enumerate(ordered_vars, start=1):
        var.index = idx

    return work_df, ordered_vars, added_vars
