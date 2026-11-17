# Peace's Execution Playbook (`@Peaceyy28`)

**Owner:** Oluwanifemi Ojewusi (**Peace**)  
**Scope:** `/frontend`, `DESIGN.md`, `/docs/peace`  
**Contract Reference:** [`../shared/02-api-contracts.md`](../shared/02-api-contracts.md)

---

## Milestone Checklist (`P1–P5`)

- [x] **M0 — Architecture, PRD & Monorepo Setup**
  - [x] Inspect benchmark OYSHIA `.sav` dataset (10,981 cases, 32 variables, 178 diagnoses, 46 investigations, 241 treatments, 33 LGAs).
  - [x] Define 9 Core Product Pillars, Big $O$ complexity guarantees, and HCI Humans-First principles.
  - [x] Author stakeholder-ready `docs/PRD.md`, `AGENTS.md`, `DESIGN.md`, and `docs/shared/*`.

- [x] **P1 — The Evidence Lab Design System & Evidence Review Workstation** (`feat/p1-ui-ux-design-shell`) *(Batch 1 Complete)*
  - [x] Lock in **The Evidence Lab** design tokens in `DESIGN.md` (`#F3F0E8`, `#FBFAF6`, `#202824`, `#17201D`, `#B9553D`, `#D5A34E`, `#477660`, `#858B83` + `IBM Plex Sans`, `Newsreader`, `IBM Plex Mono`).
  - [x] Build genuine JPG/PNG/multi-page PDF upload boundary (`frontend/js/upload.js`) & honest backend API client (`frontend/js/api.js`).
  - [x] Build paginated, exception-based Batch Review Queue (`frontend/js/queue.js`) with all 5 status views and 7 reason filters.
  - [x] Build 50/50 Evidence Split Workstation (`frontend/js/evidence-split.js`) with Deep Graphite document viewport (zoom, pan, fit, full-page, page nav, coordinate highlight, missing-source state) and Machine Interpretation (separating OCR Confidence from Codebook Similarity, Confirm/Edit/Flag with audit trail & keyboard shortcuts).

- [x] **P2 — The Receiving Desk (Screen 02: Paper Intake)** (`feat/p1-ui-ux-design-shell`) *(Batch 2 Complete)*
  - [x] Implement `Project -> Batch -> Documents -> Pages` hierarchy (`frontend/js/intake.js`).
  - [x] Build Batch Creation flow (auto-generated `BATCH-YYYY-NNNN` reference, Facility, Reporting Period, Description) and Breadcrumb navigation (`Projects / Selected Project / Selected Batch`).
  - [x] Build magic-byte file signature verification (`PDF`, `JPG`, `PNG`), SHA-256 content fingerprinting, and interactive Duplicate Detection resolution.
  - [x] Build paginated Intake Ledger (search, sort, status filter, facility filter, multi-selection, page-level Document Detail modal, explicit Delete confirmation) and distinct Document vs. Page overview counts.

- [x] **P3 — Screen 04: The Evidence Room & Review Queue** (`feat/p1-ui-ux-design-shell`)
  - [x] Direct `#nav-split` ("Evidence Room") route with designed empty state, document switcher, multi-field list, `Fit Width` / `Fit Page`, `Confirm` / `Edit` / `Flag` / `N/A or Missing`, unsaved-change guard, document progress bar, and Supervisor Quality Sampling (`evidence-split.js`, `evidence-room.css`, `queue.js`).

- [x] **P4 — Screens 05–06: The Quality Observatory & The Analysis Studio** (`feat/p1-ui-ux-design-shell`)
  - [x] Quality Observatory (`observatory.js`, `quality-observatory.css`): Value/Logical/Duplicate rules, `VR-04-RX` Prescription Audit, 6-category landscape, Field-Quality Map, Issue Investigator, and Dataset Readiness Gate.
  - [x] Analysis Studio (`studio.js`, `analysis-studio.css`): 50-row windowed Dual-View Web SPSS Data View, `Values` ↔ `Labels` toggle, Variable View metadata, Dataset Overview, Cell & Provenance Inspector, and `Auto-Recode` definitions.

- [x] **P5 — Screens 03 & 07: Master Merger & Intelligence/Export Hub UI** (`feat/p1-ui-ux-design-shell`)
  - [x] Master Merger (`merger.js`, `master-merger.css`): `.sav` magic-byte check, Variable Alignment, SVG Codebook Reconciliation Bench, Conflict Register, and Merge Gate.
  - [x] Intelligence & Export Hub (`export-hub.js`, `export-hub.css`): Schema-driven filtering, descriptive charts, Report Builder/Preview, Anonymisation preview, client-side `.csv`/`.sps` export generation, and Export History Register.
  - [ ] Connect to DuroT's FastAPI / `pyreadstat` / OCR backend endpoints on `http://localhost:8000/api/v1` once implemented.
