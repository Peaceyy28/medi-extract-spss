# MASTER_PROMPTS.md — MediExtract SPSS Agent Bootstrap Prompts

Copy-paste the matching prompt below when launching an agent session for your assigned milestone.

---

## Backend Milestones — DuroT (`@taiwodurotoluwa-svg`)

### D1 — FastAPI Scaffold, Contracts & `pyreadstat` Core Engine
```text
I am DuroT working on the backend (Milestone D1: feat/d1-spss-scaffold-contracts).
1. Read AGENTS.md, docs/shared/01-architecture.md, docs/shared/02-api-contracts.md, and docs/duro/README.md.
2. Scaffold the FastAPI backend in /backend (Python 3.12+ / uv) and implement Pydantic schemas matching 02-api-contracts.md.
3. Build the pyreadstat service to read .sav metadata/codebooks and write 100% native .sav binary and .sps syntax files.
4. Generate synthetic, non-PII OYSHIA fixtures in /fixtures and add pytest unit tests. Do not edit /frontend.
```

### D2 — Multi-Project Workspace Manager & Auto-Schema Discovery
```text
I am DuroT working on the backend (Milestone D2: feat/d2-projects-autoschema).
1. Read AGENTS.md, docs/shared/02-api-contracts.md, and docs/duro/README.md.
2. Implement isolated Multi-Project workspaces and auto-schema generation from uploaded .sav templates or blank questionnaire PDFs.
3. Add pytest tests and update docs/duro/README.md. Do not edit /frontend.
```

### D3 — Dual Scanner Ingestion, OpenCV Pre-processor & OMR
```text
I am DuroT working on the backend (Milestone D3: feat/d3-scanner-opencv-omr).
1. Read AGENTS.md, docs/shared/01-architecture.md, and docs/duro/README.md.
2. Implement the watchdog Hot-Folder scanner listener + manual PDF/file-path ingestion.
3. Implement OpenCV page deskewing, CLAHE contrast enhancement, page splitting, checkbox OMR, and field bounding-box image cropping.
```

### D4 — Open-Weight Vision HTR & Semantic Medical Auto-Coder
```text
I am DuroT working on the backend (Milestone D4: feat/d4-vision-htr-autocoder).
1. Read AGENTS.md, docs/shared/03-open-weight-models.md, and docs/duro/README.md.
2. Integrate open-weight HTR (Qwen2.5-VL / Florence-2 / TrOCR) with confidence scoring.
3. Implement the O(1) synonym dictionary + BAAI/bge-small-en-v1.5 semantic vector auto-coder mapping clinical text to SPSS numeric codes.
```

### D5 — Real-Time Validation & $O(N)$ Data Analyst Reports
```text
I am DuroT working on the backend (Milestone D5: feat/d5-validation-analyst-reports).
1. Read AGENTS.md, docs/shared/02-api-contracts.md, and docs/duro/README.md.
2. Implement real-time single/cross-variable validation rules and O(1) hash-set duplicate encounter detection.
3. Implement the single-pass O(N) Data Analyst Validation Report endpoint with custom filtering (FacilityPHC, LGA, Month, Issue Type) and PDF/Excel export.
```

---

## Frontend & UX Milestones — Peace (`@Peaceyy28`)

### P1 — UI/UX Research Synthesis, Design Tokens & SPA Shell
```text
I am Peace working on the frontend (Milestone P1: feat/p1-ui-ux-design-shell).
1. Read AGENTS.md, DESIGN.md, docs/PRD.md, docs/shared/02-api-contracts.md, and docs/peace/README.md.
2. Incorporate the UI/UX visual inspirations and design tokens into DESIGN.md.
3. Build the 3+1 page Human-First SPA shell in /frontend with mock fixture loader. Do not edit /backend.
```

### P2 — Dual-Mode Scanner & Ingestion Hub UI
```text
I am Peace working on the frontend (Milestone P2: feat/p2-scanner-ingestion-hub).
1. Read AGENTS.md, DESIGN.md, and docs/peace/README.md.
2. Build the Scanner & Ingestion Hub (live Hot-Folder indicator, manual PDF drag-and-drop / file-path input, and Recent Batches feed). Do not edit /backend.
```

### P3 — Distraction-Free Guided Verification Station
```text
I am Peace working on the frontend (Milestone P3: feat/p3-guided-verification).
1. Read AGENTS.md, DESIGN.md, docs/shared/02-api-contracts.md, and docs/peace/README.md.
2. Build the Guided Verification Station (cropped handwriting snippet viewer, plain-English Q&A confirmation card, semantic codebook dropdown, and Enter/Tab keyboard shortcuts). Do not edit /backend.
```

### P4 — Virtualized Dual-View Web SPSS Matrix & Analyst Reports UI
```text
I am Peace working on the frontend (Milestone P4: feat/p4-web-spss-and-reports).
1. Read AGENTS.md, DESIGN.md, docs/shared/02-api-contracts.md, and docs/peace/README.md.
2. Build the O(K) virtualized Web SPSS Data View, Variable View codebook table, live 1 <-> Words toggle button, cell paper-crop popover, and Filtered Data Analyst Report UI. Do not edit /backend.
```

### P5 — Live Integration, Project Setup Wizard & Export Polish
```text
I am Peace working on the frontend (Milestone P5: feat/p5-live-integration-polish).
1. Read AGENTS.md, DESIGN.md, docs/shared/02-api-contracts.md, and docs/peace/README.md.
2. Connect the frontend to the live backend endpoints (D1–D5), wire the 2-Minute New Project Wizard, and verify native .sav/.sps/PDF/Excel exports.
```
