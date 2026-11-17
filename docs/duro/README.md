# DuroT's Execution Playbook (`@taiwodurotoluwa-svg`)

**Owner:** Durotoluwa Taiwo (**DuroT**)  
**Scope:** `/backend`, `/fixtures`, `/docs/duro`  
**Contract Reference:** [`../shared/02-api-contracts.md`](../shared/02-api-contracts.md)

---

## Milestone Checklist (`D1–D5`)

- [ ] **D1 — FastAPI Scaffold, Pydantic Contracts & `pyreadstat` Core Engine** (`feat/d1-spss-scaffold-contracts`)
  - [ ] Initialize FastAPI project in `/backend` (Python 3.12+ / `uv`).
  - [ ] Implement Pydantic models matching `docs/shared/02-api-contracts.md` byte-for-byte.
  - [ ] Build `pyreadstat` service to read `.sav` files (extracting variable names, types, widths, decimals, value label codebooks, and measurement levels) and export genuine binary `.sav` + reproducible `.sps` syntax files.
  - [ ] Commit synthetic, non-PII OYSHIA fixture JSON & `.sav` in `/fixtures` so Peace can test `P1–P4` immediately.
  - [ ] Add `pytest` unit tests for `.sav` round-trip integrity.

- [ ] **D2 — Multi-Project Workspace Manager & Auto-Schema Discovery** (`feat/d2-projects-autoschema`)
  - [ ] Implement isolated project workspaces (`GET /api/v1/projects`, `POST /api/v1/projects`).
  - [ ] Mode A: Clone Variable View schema directly from an uploaded `.sav` template.
  - [ ] Mode B: Auto-discover draft Variable View schema from an uploaded blank questionnaire PDF.

- [ ] **D3 — Dual Scanner Ingestion, OpenCV Pre-processor & OMR** (`feat/d3-scanner-opencv-omr`)
  - [ ] Implement `watchdog` Hot-Folder listener (`C:\EncounterForms\ScanQueue`) with write-completion debouncing + manual PDF/file-path upload endpoint.
  - [ ] Implement OpenCV pre-processing: page deskewing, CLAHE contrast enhancement, and multi-page splitting.
  - [ ] Implement deterministic checkbox Optical Mark Recognition (OMR) and field bounding-box cropping (`crops/{batch_id}/{case_id}_{var}.webp`).

- [ ] **D4 — Open-Weight Vision HTR & Semantic Medical Auto-Coder** (`feat/d4-vision-htr-autocoder`)
  - [ ] Integrate open-weight handwriting recognition (`Qwen2.5-VL` / `Florence-2` / `TrOCR`) with token log-probability confidence scoring.
  - [ ] Build $O(1)$ normalized synonym dictionary + `BAAI/bge-small-en-v1.5` (384-d) vector cosine matcher mapping handwritten diagnoses and treatments to official SPSS numeric codes.
  - [ ] Route fields with $\text{Confidence} < 0.90$ to the Guided Verification queue (`GET /api/v1/projects/{id}/reviews`).

- [ ] **D5 — Real-Time Validation Engine & $O(N)$ Data Analyst Reports** (`feat/d5-validation-analyst-reports`)
  - [ ] Implement single-variable range/codebook rules, cross-variable clinical contradiction rules (e.g., Male + Pregnancy), and $O(1)$ hash-set duplicate encounter detection.
  - [ ] Implement single-pass $O(N)$ vectorized Data Analyst Validation Report (`POST /api/v1/projects/{id}/reports/validation`) with custom filtering (`FacilityPHC`, `LGA`, `Month`, `Issue Type`), Whipple digit-preference index, morbidity frequencies, facility rankings, and PDF/Excel export.
