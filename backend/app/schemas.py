"""Pydantic schemas matching docs/shared/02-api-contracts.md (v1.0.0)."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class MeasureLevel(str, Enum):
    """SPSS variable measurement level."""

    NOMINAL = "nominal"
    ORDINAL = "ordinal"
    SCALE = "scale"


class VariableType(str, Enum):
    """SPSS variable storage type."""

    NUMERIC = "numeric"
    STRING = "string"
    DATE = "date"


class ValidationStatus(str, Enum):
    """Row or field verification/validation status."""

    AUTO_VERIFIED = "AUTO_VERIFIED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    RULE_CONTRADICTION = "RULE_CONTRADICTION"
    DUPLICATE_COLLISION = "DUPLICATE_COLLISION"


class RuleSeverity(str, Enum):
    """Severity of a clinical or schema validation rule."""

    WARNING = "WARNING"
    BLOCKER = "BLOCKER"


class AlignmentClassification(str, Enum):
    """Classification for multi-clerk variable alignment."""

    EXACT_MATCH = "EXACT_MATCH"
    STRONG_SUGGESTION = "STRONG_SUGGESTION"
    POSSIBLE_MATCH = "POSSIBLE_MATCH"
    NO_MATCH = "NO_MATCH"
    INCOMPATIBLE = "INCOMPATIBLE"


class DriftAction(str, Enum):
    """Recommended or user-selected action for schema drift."""

    AUTO_RENAME = "AUTO_RENAME"
    PROMPT_USER = "PROMPT_USER"
    KEEP_CUSTOM = "KEEP_CUSTOM"
    IGNORE = "IGNORE"


class ExportFormat(str, Enum):
    """Supported dataset deliverable export formats."""

    SAV = "sav"
    SPS = "sps"
    XLSX = "xlsx"
    CSV = "csv"
    DTA = "dta"


class FieldProvenance(BaseModel):
    """Paper-form coordinate provenance attached to every extracted field."""

    page_number: int = Field(ge=1)
    bbox: list[float] = Field(min_length=4, max_length=4)
    crop_image_uri: str
    raw_ocr_text: str
    confidence: float = Field(ge=0.0, le=1.0)


class VariableSchema(BaseModel):
    """SPSS Variable View metadata definition."""

    index: int = Field(ge=1)
    name: str
    type: VariableType
    width: int = Field(default=8, ge=1)
    decimals: int = Field(default=0, ge=0)
    label: str = ""
    value_labels: dict[str, str] = Field(default_factory=dict)
    missing_values: list[Any] = Field(default_factory=list)
    measure: MeasureLevel = MeasureLevel.NOMINAL


class ProjectSchema(BaseModel):
    """Isolated project workspace metadata and SPSS Variable View."""

    project_id: str
    name: str
    created_at: str
    watch_folder: str
    total_cases: int = 0
    pending_reviews: int = 0
    variables: list[VariableSchema] = Field(default_factory=list)


class ProjectListResponse(BaseModel):
    """Response for GET /api/v1/projects."""

    projects: list[ProjectSchema]
    scanner_watch_active: bool = False
    watch_folder: str


class SuggestedCandidate(BaseModel):
    """Candidate SPSS codebook entry proposed by the auto-coder."""

    code: float
    label: str
    similarity: float = Field(ge=0.0, le=1.0)


class ReviewItem(BaseModel):
    """Guided Verification Station item (<90% confidence field)."""

    review_id: str
    project_id: str
    batch_id: str
    case_index: int
    patient_summary: str
    variable_name: str
    variable_label: str
    status: ValidationStatus = ValidationStatus.NEEDS_REVIEW
    raw_handwriting_text: str
    confidence: float = Field(ge=0.0, le=1.0)
    crop_image_url: str
    full_page_url: str
    suggested_candidates: list[SuggestedCandidate] = Field(default_factory=list)


class ReviewConfirmRequest(BaseModel):
    """Payload to confirm, edit, flag, or mark N/A a review item."""

    action: Literal["confirm", "edit", "flag", "na"] = "confirm"
    selected_code: float | str | None = None
    corrected_text: str | None = None
    reviewer: str = "clinic_clerk"
    reason: str | None = None


class CaseRow(BaseModel):
    """Single virtualized row in Web SPSS Data View."""

    case_index: int
    values: dict[str, Any]
    labels: dict[str, str]
    provenance: dict[str, FieldProvenance] = Field(default_factory=dict)
    validation_status: ValidationStatus = ValidationStatus.AUTO_VERIFIED


class CasesPageResponse(BaseModel):
    """Paginated response for GET /api/v1/projects/{id}/cases."""

    project_id: str
    total_cases: int
    offset: int
    limit: int
    rows: list[CaseRow]


class ValidationReportFilter(BaseModel):
    """Optional filter parameters for POST /api/v1/projects/{id}/reports/validation."""

    facility_phc: str | None = None
    lga_code: str | None = None
    month: int | None = None
    year: int | None = None
    issue_type: str = "ALL"


class ValidationSummary(BaseModel):
    """High-level quality counts in validation report."""

    total_cases_evaluated: int
    clean_cases_count: int
    clean_rate_pct: float
    flagged_cases_count: int
    duplicates_prevented: int


class MissingnessItem(BaseModel):
    """Per-variable missingness metric."""

    variable: str
    missing_count: int
    missing_pct: float
    severity: RuleSeverity


class DemographicsAudit(BaseModel):
    """Demographic profiling & digit-heaping summary."""

    age_mean: float | None = None
    age_median: float | None = None
    age_min: float | None = None
    age_max: float | None = None
    age_outliers_count: int = 0
    digit_preference_whipple_index: float | None = None
    sex_distribution: dict[str, int] = Field(default_factory=dict)


class TopDiagnosisItem(BaseModel):
    """Leading morbidity frequency item."""

    code: float
    label: str
    count: int
    pct: float


class ContradictionItem(BaseModel):
    """Flagged clinical or cross-variable contradiction."""

    case_index: int
    rule_id: str
    description: str


class ClinicalAudit(BaseModel):
    """Clinical morbidity, polypharmacy, and contradiction audit."""

    top_diagnoses: list[TopDiagnosisItem] = Field(default_factory=list)
    mean_drugs_per_encounter: float = 0.0
    contradictions_found: list[ContradictionItem] = Field(default_factory=list)


class FacilityRankingItem(BaseModel):
    """Facility data quality ranking row."""

    facility: str
    cases: int
    clean_rate_pct: float


class ValidationReportResponse(BaseModel):
    """Full response for POST /api/v1/projects/{id}/reports/validation."""

    schema_version: str = "1.0.0"
    project_id: str
    filters_applied: dict[str, Any] = Field(default_factory=dict)
    summary: ValidationSummary
    missingness_audit: list[MissingnessItem] = Field(default_factory=list)
    demographics_audit: DemographicsAudit
    clinical_audit: ClinicalAudit
    facility_ranking: list[FacilityRankingItem] = Field(default_factory=list)


class VariableDriftItem(BaseModel):
    """Variable name/case drift detected during multi-clerk .sav inspection."""

    source_file: str
    source_variable: str
    suggested_master_variable: str | None = None
    classification: AlignmentClassification | None = None
    action: DriftAction
    confidence: float = Field(ge=0.0, le=1.0)


class CodebookCollisionItem(BaseModel):
    """Semantic codebook value-label collision resolved across clerk files."""

    variable: str
    source_file: str
    original_code: float
    label: str
    conflict_with_master_label: str
    new_assigned_code: float
    rows_recoded: int


class TypeCoercionItem(BaseModel):
    """Type or string-width healing detected during merge inspection."""

    source_file: str
    variable: str
    from_type: VariableType
    to_type: VariableType
    status: str = "AUTO_HEALED"


class ClerkScorecardItem(BaseModel):
    """Per-clerk quality metrics generated during multi-clerk merge."""

    clerk_id: int
    source_file: str
    rows_contributed: int
    missing_rate_pct: float
    logic_errors_count: int
    codebook_collisions_count: int


class MergeInspectResponse(BaseModel):
    """Response for POST /api/v1/projects/{id}/merge/inspect."""

    merge_session_id: str
    files_uploaded: int
    total_rows_across_files: int
    exact_schema_matches: int
    variable_drifts: list[VariableDriftItem] = Field(default_factory=list)
    codebook_collisions_resolved: list[CodebookCollisionItem] = Field(default_factory=list)
    type_coercions: list[TypeCoercionItem] = Field(default_factory=list)
    cross_file_duplicates_detected: int = 0
    clerk_quality_scorecard: list[ClerkScorecardItem] = Field(default_factory=list)


class MergeExecuteRequest(BaseModel):
    """Request payload for POST /api/v1/projects/{id}/merge/execute."""

    merge_session_id: str
    approved_mappings: dict[str, str | dict[str, str]] = Field(default_factory=dict)
    deduplicate: bool = True
    append_provenance: bool = True
    commit_to_project: bool = True


class MergeExecuteResponse(BaseModel):
    """Response payload for POST /api/v1/projects/{id}/merge/execute."""

    ok: bool = True
    merge_session_id: str
    project_id: str
    total_rows_merged: int
    duplicates_removed: int
    codebook_recodes_applied: int = 0
    filename: str
    download_url: str
    clerk_quality_scorecard: list[ClerkScorecardItem] = Field(default_factory=list)


class AutoRecodeRequest(BaseModel):
    """Request payload for POST /api/v1/projects/{id}/transform/autorecode."""

    include_age_group: bool = True
    include_disease_category: bool = True
    include_counts: bool = True
    variables: list[str] | None = None


class AutoRecodeResponse(BaseModel):
    """Response payload for POST /api/v1/projects/{id}/transform/autorecode."""

    ok: bool = True
    project_id: str
    variables_added: list[str]
    variables_schema: list[VariableSchema] = Field(default_factory=list)
    total_cases_updated: int


class ExportRequest(BaseModel):
    """Request payload for POST /api/v1/projects/{id}/export."""

    format: ExportFormat = ExportFormat.SAV
    anonymize: bool = False
    filters: dict[str, Any] = Field(default_factory=dict)


class ExportResponse(BaseModel):
    """Response payload for POST /api/v1/projects/{id}/export."""

    ok: bool = True
    project_id: str
    format: ExportFormat
    filename: str
    size_bytes: int
    anonymized: bool
    download_url: str


class HealthResponse(BaseModel):
    """Response payload for GET /api/v1/health."""

    status: str = "ok"
    schema_version: str = "1.0.0"
    service: str = "medi-extract-spss"
    pyreadstat_version: str
    active_projects: int


class IngestFileStatus(str, Enum):
    """Outcome for an individual file processed during batch ingestion."""

    INGESTED = "INGESTED"
    DUPLICATE_SKIPPED = "DUPLICATE_SKIPPED"
    REJECTED_INVALID_FORMAT = "REJECTED_INVALID_FORMAT"


class OmrFieldResult(BaseModel):
    """Deterministic Optical Mark Recognition outcome for a checkbox/radio group."""

    variable_name: str
    selected_code: float | None = None
    selected_label: str | None = None
    fill_ratios: dict[str, float] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    status: ValidationStatus
    provenance: FieldProvenance


class CroppedFieldArtifact(BaseModel):
    """Metadata linking an extracted form field to its WebP crop artifact."""

    variable_name: str
    page_number: int = Field(ge=1)
    bbox: list[float] = Field(min_length=4, max_length=4)
    crop_image_uri: str


class IngestedPageRecord(BaseModel):
    """Pre-processed single encounter page with OMR outputs and field crop URLs."""

    page_number: int = Field(ge=1)
    case_index: int = Field(ge=1)
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    deskew_angle_deg: float = 0.0
    full_page_url: str
    crops: list[CroppedFieldArtifact] = Field(default_factory=list)
    omr_results: list[OmrFieldResult] = Field(default_factory=list)


class IngestedDocumentRecord(BaseModel):
    """Document-level record within an ingested scanning batch."""

    document_id: str
    filename: str
    mime_type: str
    sha256: str
    size_bytes: int
    status: IngestFileStatus
    page_count: int = 0
    pages: list[IngestedPageRecord] = Field(default_factory=list)
    duplicate_of_batch_id: str | None = None
    error: str | None = None


class BatchRecord(BaseModel):
    """Batch ingestion ledger record following Project -> Batch -> Documents -> Pages."""

    batch_id: str
    project_id: str
    source: Literal["manual_upload", "local_path", "hot_folder"]
    facility: str = ""
    reporting_period: str = ""
    description: str = ""
    created_at: str
    document_count: int = 0
    page_count: int = 0
    documents: list[IngestedDocumentRecord] = Field(default_factory=list)


class LocalPathIngestRequest(BaseModel):
    """Request payload for POST /api/v1/projects/{id}/ingest/paths."""

    file_paths: list[str] = Field(min_length=1)
    facility: str = ""
    reporting_period: str = ""
    description: str = ""
    duplicate_policy: Literal["skip", "allow"] = "skip"


class ScannerWatchStatus(BaseModel):
    """Live state of the watchdog Hot-Folder scanner listener."""

    active: bool
    watch_folder: str
    project_id: str | None = None
    debounce_ms: int = 500
    files_processed_count: int = 0
    last_event_at: str | None = None


class ScannerWatchStartRequest(BaseModel):
    """Request payload to start watching a Hot-Folder directory."""

    project_id: str
    watch_folder: str | None = None
    debounce_ms: int = Field(default=500, ge=50, le=5000)
