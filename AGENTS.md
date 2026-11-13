# AGENTS.md — MediExtract SPSS (read this first, every session)

You are an autonomous coding agent working on **MediExtract SPSS (HealthData Assistant)**, an automated clinical encounter form scanner, open-weight handwriting extractor, medical auto-coder, and inbuilt Web SPSS engine built for public health agencies and health insurance schemes (e.g., **OYSHIA** and **AHEAD Nigeria**).

- **Product Architect & Lead:** Oluwanifemi Ojewusi (**Peace** / `@Peaceyy28`).
- **Core Philosophy:** **HCI Humans-First.** Non-technical clinic staff must be able to scan, verify, and export SPSS datasets effortlessly without cognitive overload or technical jargon.

---

## 0. Mandatory start-of-session checklist

1. **Read in order:** `README.md`, `docs/PRD.md`, `docs/shared/01-architecture.md`, `docs/shared/02-api-contracts.md`, `docs/shared/03-open-weight-models.md`, and `DESIGN.md`.
2. **Check current milestone status** in `docs/peace/README.md` and `docs/requests.md`.
3. Run `git status` and `git branch --show-current`.
4. Do **only** the milestone or task requested by Peace. Never jump ahead to writing runtime code when the session is dedicated to UI/UX research or architecture review.

---

## 1. Developer identity & authority

| Human | Role | GitHub | Email | Authority |
| :--- | :--- | :--- | :--- | :--- |
| **Peace** (Oluwanifemi Ojewusi) | Product Architect, UI/UX & Full-Stack Lead | `Peaceyy28` | `oluwanifemipeace3@gmail.com` | Full repository (`/backend`, `/frontend`, `/fixtures`, `/docs`, `DESIGN.md`) |

---

## 2. Hard rules (never violate)

1. **HCI Humans-First Design:**
   - **Rule of 3 on Home Screen:** Everyday clinic clerks only see 3 core actions (*Scan Forms*, *Review Pending Words*, *View/Download SPSS*).
   - **Progressive Disclosure:** Complex SPSS Variable View editors and validation formula builders are tucked under *Project Setup / Supervisor Settings*, never cluttering the daily scanning flow.
   - **Plain-English Verification:** Never show raw JSON or database error codes to users. Show the cropped handwriting image snippet beside a simple question: *"The doctor wrote this. Does it say 'Malaria'? [Yes] [Change]"*.
2. **100% Patient Data Privacy (NDPA / HIPAA Compliance):**
   - **NEVER commit real `.sav` files containing patient names, phone numbers, or OYSHIA IDs to Git.** `.gitignore` blocks `*.sav` outside of synthetic anonymized test fixtures.
   - Runtime inference uses local open-weight models (`Qwen2.5-VL`, `Florence-2`, `TrOCR`, `BAAI/bge-small-en-v1.5`). Zero patient PII is sent to external commercial cloud APIs.
3. **Strict Paper Provenance:**
   - Every extracted field carries `{page_number, bbox: [x, y, w, h], crop_image_uri, raw_ocr_text, confidence}`.
   - Clicking any cell in the Web SPSS Data View or Review Queue displays the exact cropped snippet from the physical paper scan.
4. **Authentic Native SPSS Binary Compatibility:**
   - Exports must use `pyreadstat` to generate genuine IBM SPSS `.sav` binary files and `.sps` syntax files with all Variable Labels, Value Labels (e.g., 178 diagnoses, 241 treatments, 33 LGAs), and Measurement Levels (`Nominal`, `Ordinal`, `Scale`) intact. Never pass off a plain `.csv` as an SPSS export.
5. **Big $O$ Algorithmic Discipline:**
   - Grid rendering must use virtualized windowing ($O(K)$ where $K \approx 30$ visible rows).
   - Duplicate encounter detection (`OYSHIA_ID + Date + Facility`) must use an $O(1)$ hash set.
   - Medical entity auto-coding must use $O(1)$ normalized synonym lookup + $O(\log D)$ vector similarity.
   - Dataset validation reports must use $O(N)$ single-pass vectorized columnar operations.
6. **Contract is Law:**
   - `docs/shared/02-api-contracts.md` is the single source of truth between `/backend` and `/frontend`.

---

## 3. Milestones and branches

| ID | Branch | Deliverable | Depends on |
| :--- | :--- | :--- | :--- |
| **M0** | `main` | Repository structure, PRD, Architecture, API Contracts, Open-Weight Model Strategy | none |
| **M1** | `feat/m1-ui-ux-design-system` | UI/UX research synthesis, finalized `DESIGN.md` tokens, interactive high-fidelity frontend shell | M0 |
| **M2** | `feat/m2-spss-core-engine` | FastAPI backend, `pyreadstat` `.sav` reader/writer, Multi-Project manager, Auto-Schema generator | M0 |
| **M3** | `feat/m3-scanner-ocr-autocoder` | Hot-folder watcher, OpenCV deskew/OMR, open-weight HTR pipeline, BGE medical entity auto-coder | M2 |
| **M4** | `feat/m4-validation-and-reports` | Real-time single/cross-variable validation engine, $O(1)$ deduplication, Data Analyst filtered PDF/Excel reports | M2, M3 |
| **M5** | `feat/m5-integration-and-pilot` | End-to-end Web SPSS Studio + Verification Station live integration, offline packaging, automated tests | M1–M4 |
