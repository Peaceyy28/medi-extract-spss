# MASTER_PROMPTS.md — MediExtract SPSS Agent Bootstrap Prompts

Copy-paste the matching prompt below when launching an agent session for a specific milestone.

---

## Milestone 1 (M1) — UI/UX Research Synthesis & Design System

```text
We are working on MediExtract SPSS (Milestone M1: UI/UX & Design System).
1. Read AGENTS.md, DESIGN.md, docs/PRD.md, and docs/shared/02-api-contracts.md.
2. Incorporate the UI/UX visual inspirations and layout references provided by Peace into DESIGN.md.
3. Build the interactive frontend shell in /frontend following our strict HCI Humans-First rules (3-card home, distraction-free verification station, virtualized dual-view Web SPSS grid with 1 <-> Words toggle, and filtered validation report view).
4. Do not modify backend runtime files in this milestone.
```

---

## Milestone 2 (M2) — Core SPSS Engine & Multi-Project Manager

```text
We are working on MediExtract SPSS (Milestone M2: Core SPSS Engine & Multi-Project Manager).
1. Read AGENTS.md, docs/shared/01-architecture.md, and docs/shared/02-api-contracts.md.
2. Scaffold the FastAPI backend in /backend using uv and Python 3.12.
3. Implement the pyreadstat reader/writer service capable of loading existing .sav templates (extracting all variable names, types, widths, measurement levels, and value label codebooks) and exporting 100% native .sav binary and .sps syntax files.
4. Implement the Multi-Project workspace endpoints and automated pytest suite.
```

---

## Milestone 3 (M3) — Scanner Watcher, Vision OCR & Medical Auto-Coder

```text
We are working on MediExtract SPSS (Milestone M3: Scanner Ingestion, OCR & Medical Auto-Coder).
1. Read AGENTS.md, docs/shared/01-architecture.md, and docs/shared/03-open-weight-models.md.
2. Implement the dual ingestion pipeline: Hot-Folder file watcher + manual PDF/file-path intake.
3. Implement OpenCV pre-processing (deskew, contrast enhancement, page splitting, checkbox OMR) and open-weight HTR extraction with bounding-box image cropping and confidence scoring.
4. Implement the O(1) synonym dictionary + BAAI/bge-small-en-v1.5 semantic vector auto-coder mapping clinical text to SPSS numeric codes.
```

---

## Milestone 4 (M4) — Real-Time Validation & Data Analyst Reports

```text
We are working on MediExtract SPSS (Milestone M4: Validation Engine & Analyst Reports).
1. Read AGENTS.md, docs/PRD.md, and docs/shared/02-api-contracts.md.
2. Implement real-time single-variable range/codebook rules, cross-variable clinical contradiction rules, and O(1) hash-set duplicate collision detection.
3. Implement the single-pass O(N) Data Analyst Validation Report engine (missingness audit, age distribution & digit heaping, morbidity frequencies, facility rankings) with custom filtering by Facility, LGA, Month, and Issue Type.
```
