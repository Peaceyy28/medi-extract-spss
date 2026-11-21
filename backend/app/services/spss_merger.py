"""4-Layer Multi-Clerk SPSS Harmonizer & Master Merger (.sav Consolidator)."""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from rapidfuzz import fuzz

from app.config import get_settings
from app.schemas import (
    AlignmentClassification,
    ClerkScorecardItem,
    CodebookCollisionItem,
    DriftAction,
    MeasureLevel,
    MergeExecuteRequest,
    MergeExecuteResponse,
    MergeInspectResponse,
    TypeCoercionItem,
    VariableDriftItem,
    VariableSchema,
    VariableType,
)
from app.services.project_store import ProjectWorkspaceManager
from app.services.spss_engine import (
    format_code_key,
    read_sav_file,
    validate_sav_magic_bytes,
    write_sav_file,
)

FEMALE_ONLY_DIAGNOSIS_CODES: set[float] = {43.0, 44.0, 116.0, 117.0, 121.0, 224.0}
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _norm_var(name: str) -> str:
    return _NON_ALNUM_RE.sub("", name.strip().lower())


def _tokenize_var(name: str) -> set[str]:
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    spaced = re.sub(r"([A-Za-z])(\d)", r"\1 \2", spaced)
    tokens = [t for t in _NON_ALNUM_RE.split(spaced.lower()) if t and not t.isdigit()]
    return set(tokens)


def _norm_label(label: str) -> str:
    return re.sub(r"\s+", " ", label.strip().lower())


def _safe_filename(name: str, fallback_idx: int) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name).strip("._")
    return cleaned or f"clerk_{fallback_idx}.sav"


def _safe_int_token(raw: Any) -> str:
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


def _encounter_hash(row: dict[str, Any]) -> str | None:
    oid = str(row.get("OYSHIA_ID") or "").strip()
    if not oid or oid.lower() == "nan":
        return None
    year_str = _safe_int_token(row.get("Year"))
    month_str = _safe_int_token(row.get("Month"))
    fac_raw = str(row.get("FacilityPHC") or "").strip()
    payload = f"{oid}|{year_str}|{month_str}|{fac_raw}".lower()
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _best_fuzzy_match(
    source_name: str, master_names: list[str]
) -> tuple[str | None, float]:
    src_low = source_name.lower()
    src_tokens = _tokenize_var(source_name)
    best_name: str | None = None
    best_score = 0.0

    for master in master_names:
        wratio = fuzz.WRatio(src_low, master.lower()) / 100.0
        m_tokens = _tokenize_var(master)
        if src_tokens and m_tokens:
            overlap = len(src_tokens & m_tokens) / max(len(src_tokens), len(m_tokens))
            # Boost when key domain token matches (e.g., phone -> Phone_contact)
            token_bonus = 0.82 if (src_tokens & m_tokens) else 0.0
            score = max(wratio, overlap, token_bonus)
        else:
            score = wratio
        if score > best_score:
            best_score = score
            best_name = master

    return best_name, round(min(best_score, 1.0), 4)


def _can_coerce_to_numeric(series: pd.Series) -> bool:
    non_empty = [
        str(v).strip()
        for v in series.dropna().tolist()
        if str(v).strip() != "" and str(v).strip().lower() != "nan"
    ]
    if not non_empty:
        return True
    try:
        for item in non_empty:
            float(item)
        return True
    except (TypeError, ValueError):
        return False


def _count_logic_errors(df: pd.DataFrame) -> int:
    errors = 0
    if "Age" in df.columns:
        ages = pd.to_numeric(df["Age"], errors="coerce")
        bad_age = ages.notna() & ((ages < 0) | (ages > 115))
        errors += int(bad_age.sum())

    if "Sex" in df.columns and "Diagnosis1" in df.columns:
        sex = pd.to_numeric(df["Sex"], errors="coerce")
        diag1 = pd.to_numeric(df["Diagnosis1"], errors="coerce")
        bad_sex_diag = (sex == 1.0) & diag1.isin(FEMALE_ONLY_DIAGNOSIS_CODES)
        errors += int(bad_sex_diag.sum())
    return errors


def _missing_rate_pct(df: pd.DataFrame) -> float:
    if len(df) == 0 or len(df.columns) == 0:
        return 0.0
    core = [c for c in ("OYSHIA_ID", "Name", "Sex", "Age", "Diagnosis1") if c in df.columns]
    target = df[core] if core else df
    total_cells = target.shape[0] * target.shape[1]
    if total_cells == 0:
        return 0.0
    missing_cells = 0
    for col in target.columns:
        s = target[col]
        if pd.api.types.is_numeric_dtype(s):
            missing_cells += int(s.isna().sum())
        else:
            missing_cells += int(s.map(lambda x: x is None or pd.isna(x) or str(x).strip() == "").sum())
    return round((missing_cells / total_cells) * 100.0, 2)


def inspect_merge_files(
    store: ProjectWorkspaceManager,
    project_id: str,
    uploaded_files: list[tuple[str, bytes]],
) -> MergeInspectResponse:
    """Inspect 2+ clerk .sav files against project master schema without modifying sources."""
    project = store.get_project(project_id)
    if project is None:
        raise KeyError(f"Project '{project_id}' not found")

    if len(uploaded_files) < 2:
        raise ValueError("At least 2 .sav files are required for multi-clerk merge inspection.")

    for filename, payload in uploaded_files:
        if not validate_sav_magic_bytes(payload):
            raise ValueError(
                f"File '{filename}' is not a valid SPSS .sav binary ($FL2/$FL3 signature missing)."
            )

    stamp = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    merge_session_id = f"mrg_{stamp}_{uuid.uuid4().hex[:6]}"
    ws = store.get_project_workspace_path(project_id)
    session_dir = ws / "merge_sessions" / merge_session_id
    sources_dir = session_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)

    master_vars = list(project.variables)
    master_by_name: dict[str, VariableSchema] = {v.name: v for v in master_vars}
    master_norm_map: dict[str, str] = {_norm_var(v.name): v.name for v in master_vars}
    master_names = [v.name for v in master_vars]

    # Unified codebook per variable (seeded from master schema)
    unified_code_to_label: dict[str, dict[str, str]] = {}
    unified_norm_to_code: dict[str, dict[str, str]] = {}
    unified_max_code: dict[str, float] = {}
    for var in master_vars:
        c2l = dict(var.value_labels)
        n2c = {_norm_label(lbl): code for code, lbl in c2l.items()}
        unified_code_to_label[var.name] = c2l
        unified_norm_to_code[var.name] = n2c
        num_codes = []
        for k in c2l:
            try:
                num_codes.append(float(k))
            except (TypeError, ValueError):
                pass
        unified_max_code[var.name] = max(num_codes) if num_codes else 0.0

    # Parse and immutably save uploaded clerk files
    parsed_files: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for idx, (orig_name, payload) in enumerate(uploaded_files, start=1):
        safe_name = _safe_filename(orig_name, idx)
        if safe_name in seen_names:
            safe_name = f"{idx:02d}_{safe_name}"
        seen_names.add(safe_name)

        src_path = sources_dir / safe_name
        src_path.write_bytes(payload)
        df_clerk, vars_clerk, _ = read_sav_file(src_path)
        parsed_files.append(
            {
                "clerk_id": idx,
                "source_file": safe_name,
                "source_path": str(src_path),
                "df": df_clerk,
                "variables": vars_clerk,
            }
        )

    # Layer 1: Variable alignment
    variable_drifts: list[VariableDriftItem] = []
    exact_match_sets: list[set[str]] = []
    per_file_renames: dict[str, dict[str, str]] = {}
    per_file_suggested: dict[str, dict[str, str]] = {}

    for entry in parsed_files:
        fname = entry["source_file"]
        renames: dict[str, str] = {}
        suggestions: dict[str, str] = {}
        exact_cols: set[str] = set()

        for var in entry["variables"]:
            if var.name in master_by_name:
                exact_cols.add(var.name)
                continue

            norm = _norm_var(var.name)
            if norm in master_norm_map:
                target = master_norm_map[norm]
                renames[var.name] = target
                variable_drifts.append(
                    VariableDriftItem(
                        source_file=fname,
                        source_variable=var.name,
                        suggested_master_variable=target,
                        classification=AlignmentClassification.EXACT_MATCH,
                        action=DriftAction.AUTO_RENAME,
                        confidence=1.0,
                    )
                )
            else:
                best_master, score = _best_fuzzy_match(var.name, master_names)
                if score >= 0.75 and best_master is not None:
                    suggestions[var.name] = best_master
                    variable_drifts.append(
                        VariableDriftItem(
                            source_file=fname,
                            source_variable=var.name,
                            suggested_master_variable=best_master,
                            classification=AlignmentClassification.STRONG_SUGGESTION,
                            action=DriftAction.PROMPT_USER,
                            confidence=score,
                        )
                    )
                elif score >= 0.55 and best_master is not None:
                    suggestions[var.name] = best_master
                    variable_drifts.append(
                        VariableDriftItem(
                            source_file=fname,
                            source_variable=var.name,
                            suggested_master_variable=best_master,
                            classification=AlignmentClassification.POSSIBLE_MATCH,
                            action=DriftAction.PROMPT_USER,
                            confidence=score,
                        )
                    )
                else:
                    variable_drifts.append(
                        VariableDriftItem(
                            source_file=fname,
                            source_variable=var.name,
                            suggested_master_variable=None,
                            classification=AlignmentClassification.NO_MATCH,
                            action=DriftAction.KEEP_CUSTOM,
                            confidence=score,
                        )
                    )

        exact_match_sets.append(exact_cols)
        per_file_renames[fname] = renames
        per_file_suggested[fname] = suggestions

    exact_schema_matches = (
        len(set.intersection(*exact_match_sets)) if exact_match_sets else 0
    )

    # Layer 2 & 3: Semantic codebook reconciliation + type/width healing
    codebook_collisions: list[CodebookCollisionItem] = []
    type_coercions: list[TypeCoercionItem] = []
    per_file_recodes: dict[str, dict[str, dict[str, str]]] = {}
    per_file_collision_count: dict[str, int] = {e["source_file"]: 0 for e in parsed_files}
    max_string_widths: dict[str, int] = {
        v.name: v.width for v in master_vars if v.type == VariableType.STRING
    }

    for entry in parsed_files:
        fname = entry["source_file"]
        df_clerk: pd.DataFrame = entry["df"]
        renames = per_file_renames[fname]
        file_recodes: dict[str, dict[str, str]] = {}

        for var in entry["variables"]:
            aligned_name = renames.get(var.name, var.name)
            master_var = master_by_name.get(aligned_name)

            # Layer 3: Type & width check against master variable (or suggested mapping if compatible)
            if master_var is not None:
                if var.type != master_var.type:
                    if master_var.type == VariableType.NUMERIC and var.type == VariableType.STRING:
                        status = (
                            "AUTO_HEALED"
                            if _can_coerce_to_numeric(df_clerk[var.name])
                            else "INCOMPATIBLE"
                        )
                    else:
                        status = "AUTO_HEALED"
                    type_coercions.append(
                        TypeCoercionItem(
                            source_file=fname,
                            variable=aligned_name,
                            from_type=var.type,
                            to_type=master_var.type,
                            status=status,
                        )
                    )
                if master_var.type == VariableType.STRING:
                    col_max = (
                        df_clerk[var.name]
                        .dropna()
                        .astype(str)
                        .map(lambda s: len(s.encode("utf-8")))
                        .max()
                    )
                    max_string_widths[aligned_name] = max(
                        max_string_widths.get(aligned_name, 1),
                        int(col_max) if pd.notna(col_max) else 1,
                        var.width,
                    )
            elif var.type == VariableType.STRING:
                col_max = (
                    df_clerk[var.name]
                    .dropna()
                    .astype(str)
                    .map(lambda s: len(s.encode("utf-8")))
                    .max()
                )
                max_string_widths[aligned_name] = max(
                    max_string_widths.get(aligned_name, 1),
                    int(col_max) if pd.notna(col_max) else 1,
                    var.width,
                )

            # Layer 2: Semantic codebook reconciliation
            if not var.value_labels:
                continue

            c2l = unified_code_to_label.setdefault(aligned_name, {})
            n2c = unified_norm_to_code.setdefault(aligned_name, {})
            cur_max = unified_max_code.get(aligned_name, 0.0)
            var_recodes: dict[str, str] = {}

            series_vals = pd.to_numeric(df_clerk[var.name], errors="coerce")

            for code_key, clerk_label in var.value_labels.items():
                norm_lbl = _norm_label(clerk_label)
                try:
                    orig_code_num = float(code_key)
                except (TypeError, ValueError):
                    continue
                canon_key = format_code_key(orig_code_num, VariableType.NUMERIC)

                if norm_lbl in n2c:
                    canonical_code_str = n2c[norm_lbl]
                    if canonical_code_str != canon_key:
                        target_num = float(canonical_code_str)
                        rows_affected = int((series_vals == orig_code_num).sum())
                        var_recodes[canon_key] = canonical_code_str
                        codebook_collisions.append(
                            CodebookCollisionItem(
                                variable=aligned_name,
                                source_file=fname,
                                original_code=orig_code_num,
                                label=clerk_label,
                                conflict_with_master_label=f"{c2l[canonical_code_str]} (canonical code {canonical_code_str})",
                                new_assigned_code=target_num,
                                rows_recoded=rows_affected,
                            )
                        )
                        per_file_collision_count[fname] += 1
                elif canon_key in c2l:
                    existing_label = c2l[canon_key]
                    cur_max = max(cur_max, orig_code_num) + 1.0
                    new_code_str = format_code_key(cur_max, VariableType.NUMERIC)
                    unified_max_code[aligned_name] = cur_max
                    c2l[new_code_str] = clerk_label
                    n2c[norm_lbl] = new_code_str

                    rows_affected = int((series_vals == orig_code_num).sum())
                    var_recodes[canon_key] = new_code_str
                    codebook_collisions.append(
                        CodebookCollisionItem(
                            variable=aligned_name,
                            source_file=fname,
                            original_code=orig_code_num,
                            label=clerk_label,
                            conflict_with_master_label=existing_label,
                            new_assigned_code=cur_max,
                            rows_recoded=rows_affected,
                        )
                    )
                    per_file_collision_count[fname] += 1
                else:
                    c2l[canon_key] = clerk_label
                    n2c[norm_lbl] = canon_key
                    unified_max_code[aligned_name] = max(cur_max, orig_code_num)
                    cur_max = unified_max_code[aligned_name]

            if var_recodes:
                file_recodes[aligned_name] = var_recodes

        per_file_recodes[fname] = file_recodes

    # Layer 4 preview: O(1) cross-file duplicates & per-clerk quality scorecard
    seen_hashes: set[str] = set()
    cross_file_dups = 0
    scorecards: list[ClerkScorecardItem] = []

    for entry in parsed_files:
        fname = entry["source_file"]
        df_clerk = entry["df"].rename(columns=per_file_renames[fname])
        for rec in df_clerk.to_dict(orient="records"):
            h = _encounter_hash(rec)
            if h is None:
                continue
            if h in seen_hashes:
                cross_file_dups += 1
            else:
                seen_hashes.add(h)

        scorecards.append(
            ClerkScorecardItem(
                clerk_id=entry["clerk_id"],
                source_file=fname,
                rows_contributed=len(df_clerk),
                missing_rate_pct=_missing_rate_pct(df_clerk),
                logic_errors_count=_count_logic_errors(df_clerk),
                codebook_collisions_count=per_file_collision_count[fname],
            )
        )

    total_rows = sum(len(e["df"]) for e in parsed_files)
    response = MergeInspectResponse(
        merge_session_id=merge_session_id,
        files_uploaded=len(parsed_files),
        total_rows_across_files=total_rows,
        exact_schema_matches=exact_schema_matches,
        variable_drifts=variable_drifts,
        codebook_collisions_resolved=codebook_collisions,
        type_coercions=type_coercions,
        cross_file_duplicates_detected=cross_file_dups,
        clerk_quality_scorecard=scorecards,
    )

    plan_payload = {
        "merge_session_id": merge_session_id,
        "project_id": project_id,
        "files": [
            {
                "clerk_id": e["clerk_id"],
                "source_file": e["source_file"],
                "source_path": e["source_path"],
                "variables": [v.model_dump() for v in e["variables"]],
            }
            for e in parsed_files
        ],
        "per_file_renames": per_file_renames,
        "per_file_recodes": per_file_recodes,
        "unified_code_to_label": unified_code_to_label,
        "max_string_widths": max_string_widths,
        "scorecards": [s.model_dump() for s in scorecards],
    }
    plan_path = session_dir / "plan.json"
    plan_path.write_text(json.dumps(plan_payload, indent=2), encoding="utf-8")
    store.save_merge_session(
        merge_session_id=merge_session_id,
        project_id=project_id,
        inspect_json=response.model_dump_json(),
        plan_path=plan_path,
    )
    return response


def _resolve_approved_mappings_for_file(
    approved_mappings: dict[str, str | dict[str, str]],
    source_file: str,
    columns: set[str],
) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for key, val in approved_mappings.items():
        if isinstance(val, dict):
            if key == source_file:
                for src, dst in val.items():
                    if src in columns and dst:
                        resolved[src] = dst
        elif "::" in key:
            file_part, col_part = key.split("::", 1)
            if file_part == source_file and col_part in columns and isinstance(val, str):
                resolved[col_part] = val
        elif key in columns and isinstance(val, str):
            resolved[key] = val
    return resolved


def execute_merge(
    store: ProjectWorkspaceManager,
    project_id: str,
    request: MergeExecuteRequest,
) -> MergeExecuteResponse:
    """Execute harmonized multi-clerk merge, recode values, deduplicate, and export MASTER .sav."""
    project = store.get_project(project_id)
    if project is None:
        raise KeyError(f"Project '{project_id}' not found")

    session_row = store.get_merge_session(request.merge_session_id)
    if session_row is None or session_row["project_id"] != project_id:
        raise KeyError(f"Merge session '{request.merge_session_id}' not found")

    plan = json.loads(Path(session_row["plan_path"]).read_text(encoding="utf-8"))
    master_vars = [v.model_copy(deep=True) for v in project.variables]
    master_by_name = {v.name: v for v in master_vars}
    unified_code_to_label: dict[str, dict[str, str]] = plan["unified_code_to_label"]
    max_string_widths: dict[str, int] = plan["max_string_widths"]

    merged_frames: list[pd.DataFrame] = []
    custom_vars_seen: dict[str, VariableSchema] = {}
    total_recodes_applied = 0
    clerk_label_map: dict[str, str] = {}

    for f_entry in plan["files"]:
        fname = f_entry["source_file"]
        clerk_id = int(f_entry["clerk_id"])
        clerk_label_map[f"{float(clerk_id)}"] = fname

        df_clerk, vars_clerk, _ = read_sav_file(Path(f_entry["source_path"]))
        rename_map = dict(plan["per_file_renames"].get(fname, {}))
        rename_map.update(
            _resolve_approved_mappings_for_file(
                request.approved_mappings, fname, set(df_clerk.columns)
            )
        )
        if rename_map:
            df_clerk = df_clerk.rename(columns=rename_map)

        clerk_var_by_aligned: dict[str, VariableSchema] = {}
        for v_raw in vars_clerk:
            v = VariableSchema.model_validate(v_raw)
            aligned_name = rename_map.get(v.name, v.name)
            clerk_var_by_aligned[aligned_name] = v
            if aligned_name not in master_by_name and aligned_name not in custom_vars_seen:
                custom_v = v.model_copy(deep=True)
                custom_v.name = aligned_name
                if custom_v.type == VariableType.STRING:
                    custom_v.width = max(
                        custom_v.width, max_string_widths.get(aligned_name, 1)
                    )
                custom_vars_seen[aligned_name] = custom_v

        # Coerce types to master schema before numeric codebook recodes
        for col in list(df_clerk.columns):
            m_var = master_by_name.get(col)
            if m_var is None:
                continue
            if m_var.type == VariableType.NUMERIC:
                df_clerk[col] = pd.to_numeric(df_clerk[col], errors="coerce")
            elif m_var.type == VariableType.STRING:
                df_clerk[col] = df_clerk[col].map(
                    lambda x: ""
                    if x is None or (isinstance(x, float) and math.isnan(x))
                    else (str(int(x)) if isinstance(x, float) and x.is_integer() else str(x))
                )

        # Single-pass O(N) codebook recode map (prevents chained double-recodes)
        file_recodes = plan["per_file_recodes"].get(fname, {})
        for col, recode_str_map in file_recodes.items():
            if col not in df_clerk.columns or not recode_str_map:
                continue
            num_map = {float(k): float(v) for k, v in recode_str_map.items()}
            series = pd.to_numeric(df_clerk[col], errors="coerce")

            def _map_code(val: Any) -> Any:
                if val is None or pd.isna(val):
                    return np.nan
                fval = float(val)
                return num_map.get(fval, fval)

            mapped = series.map(_map_code)
            changed = int(((series.notna()) & (series != mapped)).sum())
            total_recodes_applied += changed
            df_clerk[col] = mapped

        if request.append_provenance:
            df_clerk["Source_Clerk_ID"] = float(clerk_id)
            df_clerk["Source_File_Name"] = fname
            df_clerk["Orig_Row_No"] = [float(i) for i in range(1, len(df_clerk) + 1)]

        merged_frames.append(df_clerk)

    # Assemble harmonized master variable list
    final_vars: list[VariableSchema] = []
    for var in master_vars:
        v = var.model_copy(deep=True)
        if v.name in unified_code_to_label:
            v.value_labels = dict(unified_code_to_label[v.name])
        if v.type == VariableType.STRING and v.name in max_string_widths:
            v.width = max(v.width, max_string_widths[v.name])
        final_vars.append(v)

    for c_name, c_var in custom_vars_seen.items():
        v = c_var.model_copy(deep=True)
        if v.name in unified_code_to_label:
            v.value_labels = dict(unified_code_to_label[v.name])
        final_vars.append(v)

    if request.append_provenance:
        max_fname_len = max([16, *(len(lbl.encode("utf-8")) for lbl in clerk_label_map.values())])
        final_vars.extend(
            [
                VariableSchema(
                    index=len(final_vars) + 1,
                    name="Source_Clerk_ID",
                    type=VariableType.NUMERIC,
                    width=8,
                    decimals=0,
                    label="Source Clerk File Identifier",
                    value_labels=clerk_label_map,
                    measure=MeasureLevel.NOMINAL,
                ),
                VariableSchema(
                    index=len(final_vars) + 2,
                    name="Source_File_Name",
                    type=VariableType.STRING,
                    width=max_fname_len,
                    decimals=0,
                    label="Original Clerk .SAV Filename",
                    measure=MeasureLevel.NOMINAL,
                ),
                VariableSchema(
                    index=len(final_vars) + 3,
                    name="Orig_Row_No",
                    type=VariableType.NUMERIC,
                    width=8,
                    decimals=0,
                    label="Original 1-Based Row Number in Clerk File",
                    measure=MeasureLevel.SCALE,
                ),
            ]
        )

    for idx, v in enumerate(final_vars, start=1):
        v.index = idx

    ordered_cols = [v.name for v in final_vars]
    aligned_frames: list[pd.DataFrame] = []
    for frame in merged_frames:
        f_copy = frame.copy()
        for var in final_vars:
            if var.name not in f_copy.columns:
                f_copy[var.name] = "" if var.type == VariableType.STRING else np.nan
        aligned_frames.append(f_copy[ordered_cols])

    merged_df = pd.concat(aligned_frames, ignore_index=True)

    # O(1) hash-set deduplication
    duplicates_removed = 0
    if request.deduplicate and len(merged_df) > 0:
        seen: set[str] = set()
        keep_mask: list[bool] = []
        for rec in merged_df.to_dict(orient="records"):
            h = _encounter_hash(rec)
            if h is None:
                keep_mask.append(True)
            elif h in seen:
                keep_mask.append(False)
                duplicates_removed += 1
            else:
                seen.add(h)
                keep_mask.append(True)
        merged_df = merged_df.loc[keep_mask].reset_index(drop=True)

    settings = get_settings()
    settings.ensure_data_dirs()
    export_dir = (settings.data_dir / "exports" / project_id).resolve()
    export_dir.mkdir(parents=True, exist_ok=True)
    out_filename = f"MASTER_MERGED_{request.merge_session_id}.sav"
    out_path = export_dir / out_filename
    write_sav_file(
        merged_df,
        final_vars,
        out_path,
        anonymize=False,
        file_label=f"MediExtract Master Merged ({request.merge_session_id})",
    )
    store.update_merge_session_output(request.merge_session_id, out_filename)

    if request.commit_to_project:
        store.save_project_dataset(project_id, merged_df, final_vars)

    scorecards = [ClerkScorecardItem.model_validate(s) for s in plan["scorecards"]]
    return MergeExecuteResponse(
        ok=True,
        merge_session_id=request.merge_session_id,
        project_id=project_id,
        total_rows_merged=len(merged_df),
        duplicates_removed=duplicates_removed,
        codebook_recodes_applied=total_recodes_applied,
        filename=out_filename,
        download_url=f"/api/v1/projects/{project_id}/exports/{out_filename}",
        clerk_quality_scorecard=scorecards,
    )
