"""SQLite-backed Multi-Project Workspace Manager with isolated project directories."""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator, Literal

import numpy as np
import pandas as pd

from app.config import get_settings
from app.schemas import (
    BatchRecord,
    CaseRow,
    CasesPageResponse,
    FieldProvenance,
    IngestFileStatus,
    ProjectSchema,
    ReviewAuditEntry,
    ReviewItem,
    ValidationStatus,
    VariableSchema,
    VariableType,
)
from app.services.pdf_schema_discovery import discover_schema_from_blank_pdf, validate_pdf_magic_bytes
from app.services.spss_engine import (
    dataframe_cell_to_json,
    read_sav_file,
    resolve_value_label,
    validate_sav_magic_bytes,
    write_sav_file,
)

DEFAULT_PROJECT_ID = "proj_oyshia_2025"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name).strip("._")
    return cleaned or "uploaded_file"


def empty_dataframe_from_schema(variables: list[VariableSchema]) -> pd.DataFrame:
    """Create a properly typed 0-row DataFrame matching Variable View definitions."""
    data: dict[str, pd.Series] = {}
    for var in variables:
        if var.type == VariableType.STRING:
            data[var.name] = pd.Series([], dtype="object")
        else:
            data[var.name] = pd.Series([], dtype="float64")
    return pd.DataFrame(data)


class ProjectWorkspaceManager:
    """Manages isolated Multi-Project workspaces backed by SQLite + workspace .sav files."""

    def __init__(self, data_dir: Path, fixtures_dir: Path, default_watch_folder: str) -> None:
        self._data_dir = data_dir
        self._fixtures_dir = fixtures_dir
        self._default_watch_folder = default_watch_folder
        self._db_path = self._data_dir / "mediextract.db"
        self._projects_root = self._data_dir / "projects"
        self._projects_root.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._seed_default_project()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self._db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    watch_folder TEXT NOT NULL,
                    source_mode TEXT NOT NULL,
                    template_filename TEXT,
                    total_cases INTEGER NOT NULL DEFAULT 0,
                    pending_reviews INTEGER NOT NULL DEFAULT 0,
                    variables_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS merge_sessions (
                    merge_session_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    inspect_json TEXT NOT NULL,
                    plan_path TEXT NOT NULL,
                    output_filename TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS batches (
                    batch_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    facility TEXT NOT NULL,
                    reporting_period TEXT NOT NULL,
                    description TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    document_count INTEGER NOT NULL,
                    page_count INTEGER NOT NULL,
                    batch_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ingested_documents (
                    document_id TEXT PRIMARY KEY,
                    batch_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    status TEXT NOT NULL,
                    page_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reviews (
                    review_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    batch_id TEXT NOT NULL,
                    case_index INTEGER NOT NULL,
                    variable_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    review_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS review_audit_log (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    raw_ocr_text TEXT NOT NULL,
                    selected_code_json TEXT,
                    corrected_text TEXT,
                    reviewer TEXT NOT NULL,
                    reason TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )

    def _workspace_dir(self, project_id: str) -> Path:
        ws = self._projects_root / project_id
        ws.mkdir(parents=True, exist_ok=True)
        return ws

    def _seed_default_project(self) -> None:
        sav_fixture = self._fixtures_dir / "oyshia_encounter_synthetic.sav"
        if not sav_fixture.is_file():
            return

        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            if count > 0:
                return

        df, variables, _ = read_sav_file(sav_fixture)
        ws = self._workspace_dir(DEFAULT_PROJECT_ID)
        templates_dir = ws / "source_templates"
        templates_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(sav_fixture, templates_dir / "oyshia_encounter_synthetic.sav")
        shutil.copy2(sav_fixture, ws / "dataset.sav")

        reviews_fixture = self._fixtures_dir / "oyshia_reviews_sample.json"
        seeded_reviews: list[ReviewItem] = []
        if reviews_fixture.is_file():
            raw_revs = json.loads(reviews_fixture.read_text(encoding="utf-8"))
            seeded_reviews = [ReviewItem.model_validate(item) for item in raw_revs]

        now = "2026-11-13T12:00:00Z"
        vars_json = json.dumps([v.model_dump() for v in variables])
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO projects (
                    project_id, name, created_at, watch_folder, source_mode,
                    template_filename, total_cases, pending_reviews, variables_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    DEFAULT_PROJECT_ID,
                    "OYSHIA Encounter Forms 2025 (Synthetic Fixture)",
                    now,
                    self._default_watch_folder,
                    "fixture_seed",
                    "oyshia_encounter_synthetic.sav",
                    len(df),
                    len(seeded_reviews),
                    vars_json,
                    now,
                ),
            )
            for rev in seeded_reviews:
                conn.execute(
                    """
                    INSERT INTO reviews (
                        review_id, project_id, batch_id, case_index, variable_name,
                        status, review_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rev.review_id,
                        rev.project_id,
                        rev.batch_id,
                        rev.case_index,
                        rev.variable_name,
                        rev.status.value,
                        rev.model_dump_json(),
                        now,
                        now,
                    ),
                )

    def _next_project_id(self) -> str:
        year = datetime.now(timezone.utc).year
        prefix = f"PRJ-{year}-"
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT project_id FROM projects WHERE project_id LIKE ?",
                (f"{prefix}%",),
            ).fetchall()
        max_seq = 0
        for row in rows:
            pid = row["project_id"]
            tail = pid[len(prefix) :]
            if tail.isdigit():
                max_seq = max(max_seq, int(tail))
        return f"{prefix}{max_seq + 1:03d}"

    def _row_to_project(self, row: sqlite3.Row) -> ProjectSchema:
        vars_raw = json.loads(row["variables_json"])
        variables = [VariableSchema.model_validate(item) for item in vars_raw]
        return ProjectSchema(
            project_id=row["project_id"],
            name=row["name"],
            created_at=row["created_at"],
            watch_folder=row["watch_folder"],
            total_cases=int(row["total_cases"]),
            pending_reviews=int(row["pending_reviews"]),
            variables=variables,
        )

    def list_projects(self) -> list[ProjectSchema]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM projects ORDER BY created_at ASC, project_id ASC"
            ).fetchall()
        return [self._row_to_project(r) for r in rows]

    def get_project(self, project_id: str) -> ProjectSchema | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        return self._row_to_project(row) if row is not None else None

    def delete_project(self, project_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM merge_sessions WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM review_audit_log WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM reviews WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM ingested_documents WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM batches WHERE project_id = ?", (project_id,))
            deleted = cur.rowcount > 0
        ws = self._projects_root / project_id
        if ws.exists():
            shutil.rmtree(ws, ignore_errors=True)
        return deleted

    def create_project_from_sav(
        self,
        name: str,
        sav_bytes: bytes,
        filename: str,
        watch_folder: str | None = None,
        import_cases: bool = False,
    ) -> ProjectSchema:
        if not validate_sav_magic_bytes(sav_bytes):
            raise ValueError("Invalid SPSS .sav file: missing $FL2/$FL3 binary signature.")

        project_id = self._next_project_id()
        ws = self._workspace_dir(project_id)
        safe_name = _safe_filename(filename)
        template_path = ws / "source_templates" / safe_name
        template_path.parent.mkdir(parents=True, exist_ok=True)
        template_path.write_bytes(sav_bytes)

        df, variables, _ = read_sav_file(template_path)
        if import_cases and len(df) > 0:
            write_sav_file(df, variables, ws / "dataset.sav", anonymize=False)
            total_cases = len(df)
        else:
            total_cases = 0

        now = _utc_now_iso()
        wf = watch_folder or str(ws / "scan_queue")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO projects (
                    project_id, name, created_at, watch_folder, source_mode,
                    template_filename, total_cases, pending_reviews, variables_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    name.strip(),
                    now,
                    wf,
                    "sav_template",
                    safe_name,
                    total_cases,
                    0,
                    json.dumps([v.model_dump() for v in variables]),
                    now,
                ),
            )
        return self.get_project(project_id)  # type: ignore[return-value]

    def create_project_from_blank_pdf(
        self,
        name: str,
        pdf_bytes: bytes,
        filename: str,
        watch_folder: str | None = None,
    ) -> ProjectSchema:
        if not validate_pdf_magic_bytes(pdf_bytes):
            raise ValueError("Invalid PDF file: missing %PDF- header.")

        project_id = self._next_project_id()
        ws = self._workspace_dir(project_id)
        safe_name = _safe_filename(filename)
        template_path = ws / "source_templates" / safe_name
        template_path.parent.mkdir(parents=True, exist_ok=True)
        template_path.write_bytes(pdf_bytes)

        variables = discover_schema_from_blank_pdf(pdf_bytes)
        now = _utc_now_iso()
        wf = watch_folder or str(ws / "scan_queue")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO projects (
                    project_id, name, created_at, watch_folder, source_mode,
                    template_filename, total_cases, pending_reviews, variables_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    name.strip(),
                    now,
                    wf,
                    "blank_pdf",
                    safe_name,
                    0,
                    0,
                    json.dumps([v.model_dump() for v in variables]),
                    now,
                ),
            )
        return self.get_project(project_id)  # type: ignore[return-value]

    def create_project_empty(
        self,
        name: str,
        variables: list[VariableSchema] | None = None,
        watch_folder: str | None = None,
    ) -> ProjectSchema:
        project_id = self._next_project_id()
        ws = self._workspace_dir(project_id)
        vars_list = variables or []
        now = _utc_now_iso()
        wf = watch_folder or str(ws / "scan_queue")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO projects (
                    project_id, name, created_at, watch_folder, source_mode,
                    template_filename, total_cases, pending_reviews, variables_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    name.strip(),
                    now,
                    wf,
                    "blank_schema",
                    None,
                    0,
                    0,
                    json.dumps([v.model_dump() for v in vars_list]),
                    now,
                ),
            )
        return self.get_project(project_id)  # type: ignore[return-value]

    def get_dataframe_and_schema(
        self, project_id: str
    ) -> tuple[pd.DataFrame, list[VariableSchema]] | None:
        project = self.get_project(project_id)
        if project is None:
            return None

        ws = self._workspace_dir(project_id)
        dataset_path = ws / "dataset.sav"
        if dataset_path.is_file():
            df, _, _ = read_sav_file(dataset_path)
            return df, project.variables

        return empty_dataframe_from_schema(project.variables), project.variables

    def save_project_dataset(
        self,
        project_id: str,
        df: pd.DataFrame,
        variables: list[VariableSchema],
        pending_reviews: int | None = None,
    ) -> ProjectSchema:
        project = self.get_project(project_id)
        if project is None:
            raise KeyError(f"Project '{project_id}' not found")

        ws = self._workspace_dir(project_id)
        dataset_path = ws / "dataset.sav"
        if len(df) > 0:
            write_sav_file(df, variables, dataset_path, anonymize=False)
        elif dataset_path.is_file():
            dataset_path.unlink()

        now = _utc_now_iso()
        new_pending = project.pending_reviews if pending_reviews is None else pending_reviews
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE projects
                SET total_cases = ?, pending_reviews = ?, variables_json = ?, updated_at = ?
                WHERE project_id = ?
                """,
                (
                    len(df),
                    int(new_pending),
                    json.dumps([v.model_dump() for v in variables]),
                    now,
                    project_id,
                ),
            )
        return self.get_project(project_id)  # type: ignore[return-value]

    def get_cases_page(
        self,
        project_id: str,
        offset: int = 0,
        limit: int = 50,
        search: str | None = None,
        sort_by: str | None = None,
        sort_dir: Literal["asc", "desc"] = "asc",
    ) -> CasesPageResponse | None:
        loaded = self.get_dataframe_and_schema(project_id)
        if loaded is None:
            return None

        df, variables = loaded
        if len(df) == 0:
            return CasesPageResponse(
                project_id=project_id,
                total_cases=0,
                offset=offset,
                limit=limit,
                rows=[],
            )

        var_map = {v.name: v for v in variables}
        work_df = df.copy()
        work_df["__case_index"] = range(1, len(work_df) + 1)

        if search:
            needle = search.strip().lower()
            if needle:
                mask = work_df.drop(columns=["__case_index"]).apply(
                    lambda col: col.astype(str).str.lower().str.contains(needle, regex=False, na=False)
                ).any(axis=1)
                work_df = work_df[mask]

        if sort_by and sort_by in work_df.columns:
            work_df = work_df.sort_values(
                by=sort_by,
                ascending=(sort_dir == "asc"),
                kind="mergesort",
                na_position="last",
            )

        total_matched = len(work_df)
        sliced = work_df.iloc[offset : offset + limit]
        provenance_all = self.load_provenance(project_id)

        rows: list[CaseRow] = []
        for record in sliced.to_dict(orient="records"):
            case_idx = int(record.pop("__case_index"))
            values: dict[str, Any] = {}
            labels: dict[str, str] = {}
            for col, raw_val in record.items():
                values[col] = dataframe_cell_to_json(raw_val)
                if col in var_map:
                    labels[col] = resolve_value_label(raw_val, var_map[col])
                else:
                    labels[col] = "" if values[col] is None else str(values[col])

            raw_case_prov = provenance_all.get(str(case_idx), {})
            parsed_prov = {
                k: FieldProvenance.model_validate(v)
                for k, v in raw_case_prov.items()
            }

            rows.append(
                CaseRow(
                    case_index=case_idx,
                    values=values,
                    labels=labels,
                    provenance=parsed_prov,
                    validation_status=ValidationStatus.AUTO_VERIFIED,
                )
            )

        return CasesPageResponse(
            project_id=project_id,
            total_cases=total_matched,
            offset=offset,
            limit=limit,
            rows=rows,
        )

    def load_provenance(self, project_id: str) -> dict[str, dict[str, Any]]:
        prov_path = self._workspace_dir(project_id) / "provenance.json"
        if not prov_path.is_file():
            return {}
        return json.loads(prov_path.read_text(encoding="utf-8"))

    def save_provenance(
        self, project_id: str, provenance_map: dict[str, dict[str, Any]]
    ) -> None:
        prov_path = self._workspace_dir(project_id) / "provenance.json"
        prov_path.write_text(json.dumps(provenance_map, indent=2), encoding="utf-8")

    def upsert_review(self, review: ReviewItem) -> None:
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO reviews (
                    review_id, project_id, batch_id, case_index, variable_name,
                    status, review_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(review_id) DO UPDATE SET
                    status = excluded.status,
                    review_json = excluded.review_json,
                    updated_at = excluded.updated_at
                """,
                (
                    review.review_id,
                    review.project_id,
                    review.batch_id,
                    review.case_index,
                    review.variable_name,
                    review.status.value,
                    review.model_dump_json(),
                    now,
                    now,
                ),
            )
            pending = conn.execute(
                "SELECT COUNT(*) FROM reviews WHERE project_id = ? AND status = ?",
                (review.project_id, ValidationStatus.NEEDS_REVIEW.value),
            ).fetchone()[0]
            conn.execute(
                "UPDATE projects SET pending_reviews = ?, updated_at = ? WHERE project_id = ?",
                (int(pending), now, review.project_id),
            )

    def list_reviews(
        self,
        project_id: str,
        status: str | None = None,
        batch_id: str | None = None,
    ) -> list[ReviewItem]:
        query = "SELECT review_json FROM reviews WHERE project_id = ?"
        params: list[Any] = [project_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        if batch_id:
            query += " AND batch_id = ?"
            params.append(batch_id)
        query += " ORDER BY case_index ASC, review_id ASC"
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [ReviewItem.model_validate_json(r["review_json"]) for r in rows]

    def get_review(self, project_id: str, review_id: str) -> ReviewItem | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT review_json FROM reviews WHERE project_id = ? AND review_id = ?",
                (project_id, review_id),
            ).fetchone()
        return ReviewItem.model_validate_json(row["review_json"]) if row is not None else None

    def resolve_review(
        self,
        project_id: str,
        review_id: str,
        new_status: ValidationStatus,
        action: str,
        selected_code: float | str | None,
        corrected_text: str | None,
        reviewer: str,
        reason: str | None,
    ) -> tuple[ReviewItem, ReviewAuditEntry, int]:
        existing = self.get_review(project_id, review_id)
        if existing is None:
            raise KeyError(f"Review '{review_id}' not found")

        updated = existing.model_copy(update={"status": new_status})
        now = _utc_now_iso()

        with self._connect() as conn:
            conn.execute(
                "UPDATE reviews SET status = ?, review_json = ?, updated_at = ? WHERE review_id = ?",
                (new_status.value, updated.model_dump_json(), now, review_id),
            )
            cur = conn.execute(
                """
                INSERT INTO review_audit_log (
                    review_id, project_id, action, raw_ocr_text,
                    selected_code_json, corrected_text, reviewer, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    project_id,
                    action,
                    existing.raw_handwriting_text,
                    json.dumps(selected_code) if selected_code is not None else None,
                    corrected_text,
                    reviewer,
                    reason,
                    now,
                ),
            )
            audit_id = int(cur.lastrowid)
            pending = int(
                conn.execute(
                    "SELECT COUNT(*) FROM reviews WHERE project_id = ? AND status = ?",
                    (project_id, ValidationStatus.NEEDS_REVIEW.value),
                ).fetchone()[0]
            )
            conn.execute(
                "UPDATE projects SET pending_reviews = ?, updated_at = ? WHERE project_id = ?",
                (pending, now, project_id),
            )

        audit_entry = ReviewAuditEntry(
            audit_id=audit_id,
            review_id=review_id,
            project_id=project_id,
            action=action,
            raw_ocr_text=existing.raw_handwriting_text,
            selected_code=selected_code,
            corrected_text=corrected_text,
            reviewer=reviewer,
            reason=reason,
            created_at=now,
        )
        return updated, audit_entry, pending

    def list_review_audit(
        self, project_id: str, review_id: str
    ) -> list[ReviewAuditEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM review_audit_log WHERE project_id = ? AND review_id = ? ORDER BY audit_id ASC",
                (project_id, review_id),
            ).fetchall()
        entries: list[ReviewAuditEntry] = []
        for r in rows:
            sel = json.loads(r["selected_code_json"]) if r["selected_code_json"] is not None else None
            entries.append(
                ReviewAuditEntry(
                    audit_id=int(r["audit_id"]),
                    review_id=r["review_id"],
                    project_id=r["project_id"],
                    action=r["action"],
                    raw_ocr_text=r["raw_ocr_text"],
                    selected_code=sel,
                    corrected_text=r["corrected_text"],
                    reviewer=r["reviewer"],
                    reason=r["reason"],
                    created_at=r["created_at"],
                )
            )
        return entries

    def get_project_workspace_path(self, project_id: str) -> Path:
        return self._workspace_dir(project_id)

    def save_merge_session(
        self,
        merge_session_id: str,
        project_id: str,
        inspect_json: str,
        plan_path: Path,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO merge_sessions (
                    merge_session_id, project_id, created_at, status, inspect_json, plan_path
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    merge_session_id,
                    project_id,
                    _utc_now_iso(),
                    "INSPECTED",
                    inspect_json,
                    str(plan_path),
                ),
            )

    def get_merge_session(self, merge_session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM merge_sessions WHERE merge_session_id = ?",
                (merge_session_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def update_merge_session_output(
        self, merge_session_id: str, output_filename: str
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE merge_sessions SET status = ?, output_filename = ? WHERE merge_session_id = ?",
                ("EXECUTED", output_filename, merge_session_id),
            )

    def next_batch_id(self) -> str:
        year = datetime.now(timezone.utc).year
        prefix = f"BATCH-{year}-"
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT batch_id FROM batches WHERE batch_id LIKE ?",
                (f"{prefix}%",),
            ).fetchall()
        max_seq = 0
        for row in rows:
            tail = row["batch_id"][len(prefix) :]
            if tail.isdigit():
                max_seq = max(max_seq, int(tail))
        return f"{prefix}{max_seq + 1:04d}"

    def find_duplicate_document(
        self, project_id: str, sha256: str
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM ingested_documents
                WHERE project_id = ? AND sha256 = ? AND status = ?
                ORDER BY created_at ASC LIMIT 1
                """,
                (project_id, sha256, IngestFileStatus.INGESTED.value),
            ).fetchone()
        return dict(row) if row is not None else None

    def save_batch(self, batch: BatchRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO batches (
                    batch_id, project_id, source, facility, reporting_period,
                    description, created_at, document_count, page_count, batch_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch.batch_id,
                    batch.project_id,
                    batch.source,
                    batch.facility,
                    batch.reporting_period,
                    batch.description,
                    batch.created_at,
                    batch.document_count,
                    batch.page_count,
                    batch.model_dump_json(),
                ),
            )
            for doc in batch.documents:
                conn.execute(
                    """
                    INSERT INTO ingested_documents (
                        document_id, batch_id, project_id, filename, sha256,
                        status, page_count, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        doc.document_id,
                        batch.batch_id,
                        batch.project_id,
                        doc.filename,
                        doc.sha256,
                        doc.status.value,
                        doc.page_count,
                        batch.created_at,
                    ),
                )

    def list_batches(self, project_id: str) -> list[BatchRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT batch_json FROM batches WHERE project_id = ? ORDER BY created_at DESC, batch_id DESC",
                (project_id,),
            ).fetchall()
        return [BatchRecord.model_validate_json(r["batch_json"]) for r in rows]

    def get_batch(self, project_id: str, batch_id: str) -> BatchRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT batch_json FROM batches WHERE project_id = ? AND batch_id = ?",
                (project_id, batch_id),
            ).fetchone()
        return BatchRecord.model_validate_json(row["batch_json"]) if row is not None else None


@lru_cache(maxsize=1)
def get_project_store() -> ProjectWorkspaceManager:
    settings = get_settings()
    settings.ensure_data_dirs()
    return ProjectWorkspaceManager(
        data_dir=settings.data_dir,
        fixtures_dir=settings.fixtures_dir,
        default_watch_folder=settings.watch_folder,
    )


def reset_project_store_cache() -> None:
    get_project_store.cache_clear()
