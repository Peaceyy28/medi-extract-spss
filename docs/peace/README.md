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

- [ ] **P2 — Dual-Mode Scanner & Ingestion Hub UI** (`feat/p2-scanner-ingestion-hub`)
  - [ ] Build live Scanner & Hot-Folder watch indicator (`C:\EncounterForms\ScanQueue`).
  - [ ] Build manual PDF drag-and-drop zone + local file-path input field.
  - [ ] Build Recent Scanner Batches progress table with status badges.

- [ ] **P3 — Distraction-Free Guided Verification Station** (`feat/p3-guided-verification`)
  - [ ] Build cropped handwriting snippet viewer (with pan/zoom and full-page toggle).
  - [ ] Build plain-English Question & Answer confirmation card with semantic codebook candidate dropdown.
  - [ ] Implement keyboard navigation (`Enter` to approve, `Tab` to switch).

- [ ] **P4 — Virtualized Dual-View Web SPSS Matrix & Analyst Reports UI** (`feat/p4-web-spss-and-reports`)
  - [ ] Build $O(K)$ virtualized Data View spreadsheet (60 FPS on 10,981+ cases) and Variable View codebook inspector.
  - [ ] Implement the live `1 ↔ Words` Value Labels toggle button, 1-Click Auto-Recode button (`Age_Group` & `Primary_Disease_Category`), and cell-click cropped paper provenance popover.
  - [ ] Build the Filtered Data Analyst Validation Report interface (`FacilityPHC`, `LGA`, `Month`, `Issue Type` filters + Diagnosis-to-Drug Prescription Audit alerts + scorecards & charts).

- [ ] **P5 — Live Backend Integration, Project Setup Wizard & Multi-Clerk `.SAV` Merger UI** (`feat/p5-live-integration-polish`)
  - [ ] Connect frontend to DuroT's `D1–D5` endpoints.
  - [ ] Build the 2-Minute New Project Wizard (`.sav` template upload vs. blank PDF upload).
  - [ ] Build the Multi-Clerk SPSS Harmonizer & Master Merger UI (bulk dropzone for 30+ `.sav` files, pre-merge variable/codebook reconciliation card, Per-Clerk Quality Scorecard, and 1-click unified `MASTER.sav` download).
  - [ ] Connect 1-click `.sav`, `.sps`, PDF report, and Excel exports (including `[✓] Anonymize PII for Research`).
