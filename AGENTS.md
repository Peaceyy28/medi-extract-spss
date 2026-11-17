# AGENTS.md — MediExtract SPSS (read this first, every session)

You are an autonomous coding agent working on **MediExtract SPSS (HealthData Assistant)**, an automated clinical encounter form scanner, open-weight handwriting extractor, medical auto-coder, and inbuilt Web SPSS engine built for public health agencies and health insurance schemes (e.g., **OYSHIA** and **AHEAD Nigeria**).

- **Team (two developers):** **DuroT** (backend, open-weight OCR & SPSS pipeline) and **Peace** (product architect, HCI/UX & frontend).
- **Core Philosophy:** **HCI Humans-First.** Non-technical clinic staff must be able to scan, verify, and export SPSS datasets effortlessly without cognitive overload or technical jargon.

---

## 0. Mandatory start-of-session checklist

1. **Identify who you are working for** (Section 1). Do not proceed until this is certain.
2. **Read in order:** `README.md`, `docs/PRD.md`, `docs/shared/01-architecture.md`, `docs/shared/02-api-contracts.md`, `docs/shared/03-open-weight-models.md`, then your developer playbook (`docs/duro/README.md` or `docs/peace/README.md`) and, for Peace, `DESIGN.md`.
3. **Read `docs/requests.md`** for open cross-developer requests.
4. Run `git status` and `git branch --show-current`. Work only on the milestone branch for the task you were given.
5. Do **only** the milestone you were assigned. Do not start the next one, and do not add features not listed in your playbook unless the human explicitly asks.

---

## 1. Developer identity detection

| Human | Role | GitHub | Email | Owns |
| :--- | :--- | :--- | :--- | :--- |
| **DuroT** (Durotoluwa Taiwo) | Backend, Open-Weight OCR & SPSS Engine | `taiwodurotoluwa-svg` | `taiwodurotoluwa@gmail.com` | `/backend`, `/fixtures`, `/docs/duro` |
| **Peace** (Oluwanifemi Ojewusi) | Product Architect, HCI/UX & Frontend | `Peaceyy28` | `oluwanifemipeace3@gmail.com` | `/frontend`, `DESIGN.md`, `/docs/peace` |

Procedure:
1. If the human or launch prompt states who they are, confirm it in your first message (*"I am working for Peace on the frontend"* or *"I am working for DuroT on the backend"*).
2. Otherwise check `git config user.name` and `git config user.email` against the table above.
3. If still unclear, **stop and ask**: *"Are you DuroT (backend) or Peace (frontend)?"* Never guess and never act as both.

---

## 2. Workspace boundaries

| Path | Owner | Rule |
| :--- | :--- | :--- |
| `/backend/**` | DuroT | Peace's agent must not edit. |
| `/fixtures/**` | DuroT | Peace's agent reads only. Copies live in `/frontend/public/fixtures` (synced by script). |
| `/frontend/**` | Peace | DuroT's agent must not edit. |
| `DESIGN.md` | Peace | Creative authority belongs to Peace (`Peaceyy28`). |
| `/docs/duro/**`, `/docs/peace/**` | Respective owner | Owner updates status checkboxes and notes only. |
| `/docs/shared/**`, `/docs/PRD.md`, `/AGENTS.md`, `/README.md`, `/MASTER_PROMPTS.md`, `/LICENSE` | Both | Change only through a PR approved by **both** humans. |
| `/docs/requests.md`, `/docs/AI_ASSISTANCE.md` | Both | Append-only. |

If you need a contract change outside your workspace, **do not edit it unilaterally**. Add a row to `docs/requests.md` and notify your human.

---

## 3. Hard rules (never violate)

1. **HCI Humans-First Design:**
   - **Rule of 3 on Home Screen:** Everyday clinic clerks only see 3 core actions (*Scan Forms*, *Review Pending Words*, *View/Download SPSS*).
   - **Progressive Disclosure:** Complex SPSS Variable View editors and validation formula builders are tucked under *Project Setup / Supervisor Settings*, never cluttering the daily scanning flow.
   - **Plain-English Verification:** Show the cropped handwriting image snippet beside a simple question: *"The doctor wrote this. Does it say 'Malaria'? [Yes] [Change]"*.
2. **100% Patient Data Privacy (NDPA / HIPAA Compliance):**
   - **NEVER commit real `.sav` files containing patient names, phone numbers, or OYSHIA IDs to Git.** `.gitignore` blocks `*.sav` outside of synthetic anonymized test fixtures.
   - Runtime inference uses open-weight models (`Qwen2.5-VL`, `Florence-2`, `TrOCR`, `BAAI/bge-small-en-v1.5`). Zero patient PII is sent to external commercial cloud APIs.
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

## 4. Milestones and branches (`D1–D5` & `P1–P5`)

Ten milestones, ten clean PRs. Branch names are fixed.

| ID | Owner | Branch | Deliverable | Depends on |
| :--- | :--- | :--- | :--- | :--- |
| **D1** | DuroT | `feat/d1-spss-scaffold-contracts` | FastAPI scaffold, Pydantic contracts, `pyreadstat` `.sav`/`.sps` reader-writer, synthetic OYSHIA fixtures in `/fixtures` | none |
| **D2** | DuroT | `feat/d2-projects-autoschema` | Multi-Project workspace manager, auto-schema discovery from `.sav` templates and blank PDFs | D1 |
| **D3** | DuroT | `feat/d3-scanner-opencv-omr` | Hot-Folder watcher (`watchdog`), manual PDF/path ingestion, OpenCV deskew, contrast binarisation, checkbox OMR & bbox image cropping | D1, D2 |
| **D4** | DuroT | `feat/d4-vision-htr-autocoder` | Open-weight HTR (`Qwen2.5-VL` / `Florence-2` / `TrOCR`), confidence gate, $O(1)$ synonym + `BAAI/bge-small-en-v1.5` semantic medical auto-coder | D3 |
| **D5** | DuroT | `feat/d5-validation-analyst-reports` | Real-time single/cross-variable validation, $O(1)$ hash deduplication, single-pass $O(N)$ filtered Data Analyst Validation Report (PDF/Excel) | D4 |
| **P1** | Peace | `feat/p1-ui-ux-design-shell` | UI/UX research synthesis, finalized `DESIGN.md` tokens, 3+1 page Human-First SPA shell & mock fixture loader | contract file |
| **P2** | Peace | `feat/p2-scanner-ingestion-hub` | Dual-mode Scanner Hub UI (live Hot-Folder watch indicator + manual PDF drag-and-drop / path input + batch progress feed) | P1 |
| **P3** | Peace | `feat/p3-guided-verification` | Distraction-free Guided Verification Station (cropped handwriting viewer, plain-English Q&A card, keyboard shortcuts) | P1 (+ D1 fixtures) |
| **P4** | Peace | `feat/p4-web-spss-and-reports` | Virtualized $O(K)$ Dual-View Web SPSS Matrix (`Data View` $\leftrightarrow$ `Variable View`), live `1 ↔ Words` toggle, cell provenance popover & Filtered Analyst Report UI | P3 |
| **P5** | Peace | `feat/p5-live-integration-polish` | End-to-end live integration with DuroT's backend (`D1–D5`), Project Setup wizard, `.sav`/`.sps` export triggers & responsive polish | P4, D5 |

**Parallel mock-first rule:** Peace builds `P1–P4` against `/fixtures` without waiting on backend runtime code. DuroT builds `D1–D4` against `pyreadstat` and the OCR/auto-coding pipeline. `P5` and `D5` connect them.
