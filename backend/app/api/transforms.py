"""SPSS Transform endpoints (Feature 11 Auto-Recode & Computed Variables)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas import AutoRecodeRequest, AutoRecodeResponse
from app.services.autorecode import apply_autorecode
from app.services.project_store import get_project_store

router = APIRouter(prefix="/projects", tags=["transforms"])


@router.post("/{project_id}/transform/autorecode", response_model=AutoRecodeResponse)
def transform_autorecode(
    project_id: str,
    payload: AutoRecodeRequest | None = None,
) -> AutoRecodeResponse:
    """Compute Age_Group, Primary_Disease_Category, Comorbidity_Count, and Polypharmacy_Count."""
    store = get_project_store()
    loaded = store.get_dataframe_and_schema(project_id)
    if loaded is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    df, variables = loaded
    req = payload or AutoRecodeRequest()
    new_df, updated_vars, added_vars = apply_autorecode(df, variables, req)
    store.save_project_dataset(project_id, new_df, updated_vars)

    return AutoRecodeResponse(
        ok=True,
        project_id=project_id,
        variables_added=[v.name for v in added_vars],
        variables_schema=added_vars,
        total_cases_updated=len(new_df),
    )
