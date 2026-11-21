"""D1 Fixture-backed project and case repository (bridge to D2 SQLite workspace manager)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from app.config import get_settings
from app.schemas import CaseRow, CasesPageResponse, ProjectSchema, ValidationStatus, VariableSchema
from app.services.spss_engine import (
    dataframe_cell_to_json,
    read_sav_file,
    resolve_value_label,
)

DEFAULT_PROJECT_ID = "proj_oyshia_2025"


class FixtureProjectStore:
    """Loads synthetic OYSHIA .sav fixture into memory for D1 endpoints."""

    def __init__(self, fixtures_dir: Path, watch_folder: str) -> None:
        self._fixtures_dir = fixtures_dir
        self._watch_folder = watch_folder
        self._projects: dict[str, ProjectSchema] = {}
        self._dataframes: dict[str, pd.DataFrame] = {}
        self._variables: dict[str, list[VariableSchema]] = {}
        self._load_default_fixture()

    def _load_default_fixture(self) -> None:
        sav_path = self._fixtures_dir / "oyshia_encounter_synthetic.sav"
        if not sav_path.is_file():
            return

        df, variables, _ = read_sav_file(sav_path)
        project = ProjectSchema(
            project_id=DEFAULT_PROJECT_ID,
            name="OYSHIA Encounter Forms 2025 (Synthetic Fixture)",
            created_at="2026-11-13T12:00:00Z",
            watch_folder=self._watch_folder,
            total_cases=len(df),
            pending_reviews=5,
            variables=variables,
        )
        self._projects[DEFAULT_PROJECT_ID] = project
        self._dataframes[DEFAULT_PROJECT_ID] = df
        self._variables[DEFAULT_PROJECT_ID] = variables

    def list_projects(self) -> list[ProjectSchema]:
        return list(self._projects.values())

    def get_project(self, project_id: str) -> ProjectSchema | None:
        return self._projects.get(project_id)

    def get_dataframe_and_schema(
        self, project_id: str
    ) -> tuple[pd.DataFrame, list[VariableSchema]] | None:
        df = self._dataframes.get(project_id)
        variables = self._variables.get(project_id)
        if df is None or variables is None:
            return None
        return df, variables

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

            rows.append(
                CaseRow(
                    case_index=case_idx,
                    values=values,
                    labels=labels,
                    provenance={},
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


@lru_cache(maxsize=1)
def get_fixture_store() -> FixtureProjectStore:
    settings = get_settings()
    return FixtureProjectStore(
        fixtures_dir=settings.fixtures_dir,
        watch_folder=settings.watch_folder,
    )


def reset_fixture_store_cache() -> None:
    get_fixture_store.cache_clear()
