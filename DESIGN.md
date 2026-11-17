---
version: 1.0.0
name: MediExtract SPSS
theme: Human-First Clinical Clarity (Pending Final Visual Inspiration from Peace)
description: HCI-driven healthcare digitization interface prioritizing calm typography, progressive disclosure, tactile paper provenance, and zero cognitive overload for non-technical clinic staff.
---

# DESIGN.md — MediExtract SPSS Design System & HCI Specification

## 0. Authority & HCI Philosophy (`Peaceyy28`)

**Peace (`Peaceyy28`) holds creative authority** over the visual identity, spatial layout, typography, and interaction patterns of MediExtract SPSS.

> **Status Note:** Visual mood boards and aesthetic inspirations are currently being researched by Peace. Once visual references are finalized, Section 1 (Color & Surface Tokens) will be updated to match the exact chosen aesthetic before frontend code begins.

### Core HCI Principles (Don Norman & Nielsen Norman Standards)
1. **Humans First, Jargon Never:** A clinic records clerk or nurse does not think in *"boolean cross-variable assertions"*, *"WIA driver sockets"*, or *"32-column relational schemas"*. Every label, button, and alert must speak calm, everyday English.
2. **The Rule of 3 (Zero Cognitive Overload):** The primary workspace presents only three core jobs:
   - **1. Scan / Upload Forms**
   - **2. Review Pending Handwriting**
   - **3. View & Download SPSS Data**
3. **Progressive Disclosure:** Advanced capabilities (creating new Project templates, editing the 32-variable SPSS Variable View codebook, configuring custom validation formulas) live inside a dedicated **Project Setup (Supervisor)** area—completely out of the clerk's daily path.
4. **Physical Paper Provenance:** Every digital value is visually linked to a cropped image slice of the physical paper sheet so staff never have to search through physical filing cabinets.

---

## 1. Multi-Modal Validation & Confidence Signals

Per accessibility and clinical safety standards, data states **never rely on color alone**. Every status pairs color + icon + plain-English badge:

| Signal Enum | Meaning | Icon | Plain-English Label | UI Behaviour |
| :--- | :--- | :--- | :--- | :--- |
| `AUTO_VERIFIED` | Confidence $\ge 90\%$ and all validation rules pass | `✓` | Saved automatically | Auto-committed to SPSS dataset |
| `NEEDS_REVIEW` | Handwriting confidence $< 90\%$ or ambiguous term | `🔍` | Needs quick check | Surfaced in 1-at-a-time Guided Review Card |
| `RULE_CONTRADICTION` | Cross-variable logic failed (e.g. Male + Pregnancy) | `⚠️` | Logic mismatch | Highlighted with plain-English explanation |
| `DUPLICATE_COLLISION`| Composite key (`OYSHIA_ID + Date`) already exists | `⛔` | Already scanned | Side-by-side comparison to prevent double entry |

---

## 2. Core Page Architecture (3 + 1 Layout)

### 2.1 Top Bar
- **Project Switcher Dropdown:** `[ 📁 OYSHIA Encounter Forms 2025 ▾ ]` + `[+ New Project]`.
- **Scanner Status Pill:** Live pulse indicator (`Scanner Ready: Watching C:\EncounterForms\ScanQueue`).
- **Primary Navigation:** `Home` · `Review Queue` · `SPSS Data & Reports` · `Project Setup`.

### 2.2 Page 1 — The Scanner & Ingestion Home
- **Method A (Automatic):** Hands-free intake from the watched scanner folder.
- **Method B (Manual):** Drag-and-drop PDF/image zone or paste local file path.
- **Batch Progress Feed:** Clean summary showing how many sheets were auto-saved vs. how many words need review.

### 2.3 Page 2 — Guided Verification Station
- **Left Pane:** Cropped, high-contrast snippet of the doctor's handwritten entry on the physical form (with option to expand full sheet).
- **Right Pane:** Plain-English question (*"Doctor wrote 'Mss wrist pain'. Matched to: **1.0 - MSS OF THE WRIST**. Is this right?"*) with single-keystroke approval (`Enter`).

### 2.4 Page 3 — Inbuilt Web SPSS Studio & Analyst Reports
- **View Switcher:** `Data View (Cases)` $\leftrightarrow$ `Variable View (Codebook)` $\leftrightarrow$ `Validation Report`.
- **`1 ↔ Words` Value Labels Toggle:** Instantly switches cells between raw SPSS numeric codes (`2.0, 26, 1`) and human labels (`Hypertention, OORELOPE, Male`).
- **Filtered Analyst Report Drawer:** Filter by `FacilityPHC`, `LGA`, `Month`, or `Issue Type`, and export as a formatted PDF or Excel Discrepancy Log.
- **1-Click Export:** Native `.sav` binary, `.sps` syntax, or `.xlsx` workbook (with optional `[✓] Anonymize PII for Research`).

### 2.5 Page 4 — Project, Schema & Multi-File Merger Studio (Supervisor View)
- **2-Minute New Project Wizard:**
  1. Upload an existing `.sav` file to clone its Variable View automatically, **OR**
  2. Upload a blank questionnaire PDF to auto-discover fields and generate a draft Variable View.
- **Multi-Clerk SPSS Harmonizer & Master Merger:**
  - **Bulk `.SAV` Dropzone:** Drop 2 to 50+ clerks' `.sav` files at once.
  - **Pre-Merge Reconciliation Card:**
    - Shows auto-fixed capitalization/variable drift (`treatment2` $\rightarrow$ `Treatment2`).
    - Shows auto-resolved Value Label codebook collisions (e.g., *Clerk B's `265 = Costochondritis` recoded to `266` so it doesn't overwrite `265 = Eczema`*).
    - Simple 1-click prompt for any brand-new column added by a clerk (`[Map to Existing Variable ▾]` · `[Keep as New Standard Column]` · `[Drop Column]`).
  - **1-Click Master Merge:** Outputs unified `MASTER_MERGED.sav` + Merge Audit Summary.
