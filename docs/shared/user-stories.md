# MediExtract SPSS — User Stories & Acceptance Criteria

This document defines concrete, testable **User Stories** for each MediExtract build so frontend (`@Peaceyy28`) and backend (`@taiwodurotoluwa-svg`) work share an unambiguous Definition of Done.

---

## Screen 01 — The Project Index (`P1 / D2`)

### US-01.1 — Create a Project from an SPSS Template (`.sav`) or Blank PDF
- **Persona:** M&E Supervisor / Lead Researcher
- **Story:** As a supervisor, I want to create a new clinical project by uploading an existing `.sav` template or blank questionnaire PDF, so that MediExtract knows the target variables and codebook for all incoming batches.
- **Acceptance Criteria:**
  - [ ] Clicking **Create New Project** opens the setup modal with `.sav` Template and Questionnaire PDF modes.
  - [ ] Submitting creates a `PRJ-YYYY-NNN` workspace card and selects it as the active project.
  - [ ] When the backend is live, `POST /api/v1/projects` persists the schema and variable metadata.
- **Integration Boundary:** Client-side workspace state when offline; `POST /api/v1/projects` (`D2`) when live.

---

## Screen 02 — The Receiving Desk (`P2 / D3`)

### US-02.1 — Batch Creation & Paper Intake with Duplicate Detection
- **Persona:** Clinic Records Clerk
- **Story:** As a clerk, I want to group scanned encounter forms (`PDF`, `JPG`, `PNG`) into named facility batches with magic-byte and SHA-256 duplicate checks, so that corrupted or duplicate scans are caught before OCR runs.
- **Acceptance Criteria:**
  - [ ] Creating a batch generates a `BATCH-YYYY-NNNN` reference under the active project.
  - [ ] Uploaded files undergo client-side magic-byte signature validation (`%PDF-`, JPEG, PNG).
  - [ ] Duplicate SHA-256 hashes trigger an explicit resolution prompt instead of silent overwrite.
- **Integration Boundary:** `POST /api/v1/projects/{id}/upload` (`D3`) when live.

---

## Screen 03 — The Master Merger (`P5 / D1`)

### US-03.1 — Reconcile Multi-Clerk `.sav` Schemas & Codebooks
- **Persona:** M&E Supervisor
- **Story:** As a supervisor, I want to inspect multiple clerks' `.sav` files, align drifted variable names/types, and resolve value-label collisions before merging, so that the master dataset preserves data integrity and clerk provenance.
- **Acceptance Criteria:**
  - [ ] Only valid `$FL2`/`$FL3` `.sav` files are accepted into the Source Register; originals remain immutable.
  - [ ] Variable Alignment classifies `EXACT_MATCH`, `STRONG_SUGGESTION`, `POSSIBLE_MATCH`, `NO_MATCH`, and `INCOMPATIBLE`.
  - [ ] Codebook Reconciliation displays source-to-master mappings with collision alerts.
  - [ ] Merge execution is blocked while mandatory conflicts remain unresolved or when `pyreadstat` is offline.
- **Integration Boundary:** `POST /api/v1/projects/{id}/merge/inspect` and `/merge/execute` (`D1`).

---

## Screen 04 — The Evidence Room (`P1 / P3 / D4`)

### US-04.1 — Inspect Original Handwriting Alongside Extracted Fields
- **Persona:** Clinic Records Clerk
- **Story:** As a clerk, I want to view the original scanned form next to every extracted field with zoom, pan, and coordinate highlighting, so that I can verify uncertain values against the paper evidence.
- **Acceptance Criteria:**
  - [ ] Clicking **Evidence Room** in the top nav opens directly (showing a designed empty state if no documents exist).
  - [ ] Selecting an extracted field updates the bounding-box highlight only when real `bbox` coordinates exist; otherwise it states coordinates are unavailable.
  - [ ] Left viewer supports zoom in/out, pan, Fit Width, Fit Page, Full Page modal, and multipage navigation.

### US-04.2 — Confirm, Edit, Flag, or Mark N/A with Immutable Audit Trail
- **Persona:** Clinic Records Clerk
- **Story:** As a clerk, I want to confirm, correct, flag, or mark fields N/A/Missing without overwriting the original AI extraction, so that every dataset change is traceable.
- **Acceptance Criteria:**
  - [ ] Editing a field keeps `extractedText` untouched, stores `correctedText` separately, and logs reviewer + timestamp + reason in `auditHistory`.
  - [ ] Navigating away with unsaved edits triggers a confirmation prompt.
  - [ ] Document Review cannot be marked complete while required fields remain unresolved.
- **Integration Boundary:** `POST /api/v1/projects/{id}/reviews/{reviewId}/confirm` (`D4`).

---

## Screen 05 — The Quality Observatory (`P4 / D5`)

### US-05.1 — Run Validation Rules & Prescription Audit (`VR-04-RX`)
- **Persona:** M&E Supervisor / Clinical Reviewer
- **Story:** As a supervisor, I want to run value, logical, duplicate, and `VR-04-RX` prescription-audit rules and inspect flagged records in a focused panel, so that dataset anomalies are resolved with full provenance before analysis.
- **Acceptance Criteria:**
  - [ ] Validation status never shows `Completed` before validation actually runs.
  - [ ] Quality Landscape and Field-Quality Map filter the Issue Register on click.
  - [ ] `VR-04-RX` flags appear as `Clinical review` prompts without asserting medical error or auto-editing values.
  - [ ] Dataset Readiness Gate blocks supervisor approval until unresolved issues are addressed.
- **Integration Boundary:** `POST /api/v1/projects/{id}/validate` (`D5`).

---

## Screen 06 — The Analysis Studio (`P4 / D1`)

### US-06.1 — Dual-View Web SPSS Inspection (`Values` ↔ `Labels`)
- **Persona:** Data Analyst / Statistician
- **Story:** As an analyst, I want to inspect records in a windowed Data View and Variable View with a live `Values`/`Labels` toggle and cell-level provenance, so that I can verify coding and prepare transformations for statistical analysis.
- **Acceptance Criteria:**
  - [ ] Data View renders 50-row windows with sticky headers, sorting, search, and cell selection.
  - [ ] Toggling **Values / Labels** changes display labels without mutating underlying codes.
  - [ ] Selecting a cell displays its variable label, source file, original row, and `Trace to Evidence Split →` link when available.
  - [ ] Planned `Auto-Recode` variables (`Age_Group`, `Primary_Disease_Category`, `Comorbidity_Count`, `Polypharmacy_Count`) display `Pending Backend Engine` honestly until connected.

---

## Screen 07 — The Intelligence & Export Hub (`P5 / D1 / D5`)

### US-07.1 — Filter, Preview Institutional Report & Export Deliverables
- **Persona:** Data Analyst / M&E Supervisor
- **Story:** As an analyst, I want to filter the dataset, preview descriptive charts and institutional reports, configure optional anonymisation, and export `.csv`/`.sps`/`.sav`/`.xlsx`/`.dta` deliverables, so that research-ready outputs retain full traceability.
- **Acceptance Criteria:**
  - [ ] Schema-driven filters update matching record counts and all 4 descriptive charts dynamically.
  - [ ] Anonymisation operates strictly on an export copy and displays the re-identification caveat.
  - [ ] `.csv` and `.sps` generate real downloadable files in Export History; `.sav`/`.xlsx`/`.dta` require the live `pyreadstat`/`openpyxl` backend and never generate spoofed files.
- **Integration Boundary:** `POST /api/v1/projects/{id}/export` (`D1 / D5`).
