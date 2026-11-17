# Product Requirements Document (PRD)

**Project Name:** MediExtract SPSS (HealthData Assistant)  
**Product Version:** 1.0 (Stakeholder & Architectural Review)  
**Target Organization:** Public Health Agencies, Research Institutes & Health Insurance Schemes (e.g., OYSHIA, AHEAD Nigeria)  
**Author:** Oluwanifemi Ojewusi (Peace)  
**Date:** November 2026  

---

## 1. Executive Summary

Healthcare agencies and medical research bodies process tens of thousands of paper encounter records, patient registers, and survey questionnaires annually. In organizations like the Oyo State Health Insurance Agency (OYSHIA) and AHEAD Nigeria, paper forms are manually transcribed into IBM SPSS Statistics (`.sav`) datasets.

This legacy manual entry workflow has four critical bottlenecks:
1. **Slow throughput:** Manual transcription of handwriting and diagnosis lookups creates massive data backlogs.
2. **Transcription errors:** Translating clinical terms into 178+ diagnosis codes and 241+ treatment codes causes human coding errors.
3. **Expensive licensing & fragmentation:** Staff require dedicated IBM SPSS licenses just to view or clean datasets.
4. **Data quality & validation blind spots:** Inconsistent age records, missing mandatory IDs, and contradictory clinical entries are often caught months after data collection.

**MediExtract SPSS** is an automated, human-centered **Intelligent Document Processing (IDP) and Web-native SPSS Platform**. It connects physical paper scanners directly to an open-weight AI engine that reads handwriting, maps medical diagnoses to official SPSS numeric codebooks, runs real-time statistical validation, and exports 100% native SPSS binary (`.sav`) files—all running locally with zero cloud subscription fees and total patient privacy.

---

## 2. User Personas & Workflows

| Persona | Role | Primary Goals & Jobs-to-be-Done | Pain Points Solved |
| :--- | :--- | :--- | :--- |
| **Clinic Records Clerk** *(Non-Technical)* | Feeds physical paper sheets into scanners and performs day-to-day intake. | Wants a zero-confusion interface to scan 50–100 sheets in a batch, confirm any unclear handwriting with one click, and see that data is saved. | No longer types 32 columns manually; never has to memorize or look up numeric codebooks. |
| **M&E / Quality Supervisor** | Oversees data integrity across health facilities and approves monthly batches. | Reviews flagged discrepancies, verifies facility compliance, and generates data quality audit reports. | Instant access to facility rankings, missing value audits, and cross-variable contradiction logs. |
| **Principal Investigator / Biostatistician** | Conducts epidemiological research, regressions, and donor reporting. | Needs authentic, uncorrupted `.sav` files with preserved value labels, measurement levels, and reproducible SPSS syntax (`.sps`). | No more broken CSV imports; codebooks, labels, and missing value rules remain 100% intact. |

---

## 3. Detailed Feature Specifications (11 Core Pillars)

### Feature 1: Dual-Mode Ingestion (Scanner Hot Folder + Manual Upload)
* **Automatic Hot-Folder Watcher:** Background process continuously monitors `C:\EncounterForms\ScanQueue`. The moment a physical scanner drops a PDF/TIFF, the file is ingested within 1 second.
* **Manual / Flexible Ingestion:** Drag-and-drop zone and file path input field for scanned PDFs received via email, USB flash drive, or existing desktop archives.
* **Pre-processing:** Automatic page deskewing (straightening tilted sheets), contrast binarization (enhancing faint blue ink), and multi-page batch splitting into individual encounter records.

### Feature 2: Open-Weight Vision & Handwriting Engine
* **Hybrid Recognition Pipeline:**
  * **Checkbox OMR:** High-precision computer vision pixel-density analysis for tick-boxes, sex selection, and radio groups.
  * **Handwritten Text Recognition (HTR):** Lightweight open-weight models (`Qwen2.5-VL` / `Florence-2` / `TrOCR`) transcribing cursive, handwritten patient names, ID numbers, and clinical notes.
* **Confidence Scoring (Safety Net):** Every extracted value is scored (0%–100%). Fields $\ge 90\%$ confidence are auto-committed; fields $< 90\%$ are queued for 1-click human verification.

### Feature 3: Medical Entity Auto-Coder (Text $\rightarrow$ SPSS Code)
* **The Problem Solved:** Doctors write clinical descriptions (*"Hypertension"*, *"HTN"*, *"High BP"*), but SPSS requires numeric codes (e.g. `Code 2.0`).
* **Semantic Dictionary Lookup:** Inverted dictionary and `BAAI/bge-small-en-v1.5` embedding matching maps written terms to the official 178 diagnoses and 241 prescribed medications in milliseconds.
* **Unrecognized Term Quarantine:** If an unprecedented clinical term is written, it is flagged for supervisor categorization without halting batch processing.

### Feature 4: "Projects" Architecture (Multi-Study & Custom Form Support)
* **Isolated Project Workspaces:** Supports multiple parallel studies and forms (e.g., *Project 1: OYSHIA Encounter Records*, *Project 2: AHEAD Family Planning Survey*, *Project 3: Maternal Health Register*).
* **Auto-Schema Generator (Template Creator):**
  * **From Existing SPSS:** Upload any `.sav` file; the system auto-extracts all 32+ variables, value labels, and measurement levels.
  * **From Blank Form PDF:** Upload a blank questionnaire; AI auto-discovers question boxes, labels, and proposed variable names.

### Feature 5: Human-First Guided Verification Station
* **Rule of 3 (HCI Standard):** Clerks never see intimidating codebooks or raw databases during verification.
* **Focused Inspection Card:**
  * Displays a high-resolution cropped image of the doctor's handwriting.
  * Asks in plain English: *"The doctor wrote this. Does it say **'MSS OF THE WRIST'**? [Yes, Save] [Change]"*.
* **Rapid Review:** Keyboard-driven review (`Enter` to accept) cuts verification time to seconds per form.

### Feature 6: SPSS-Grade Real-Time Validation, Prescription Audit & Quality Reporting
* **Live Constraint Checks:**
  * Single-variable range checks (e.g. `Age` $\ge 0$ and $\le 115$).
  * Allowed codebook membership (flags codes outside the official list).
  * Cross-variable clinical contradictions (e.g. Male patients with pregnancy/miscarriage diagnoses).
  * **Diagnosis-to-Drug Clinical Plausibility Check (Prescription Audit):** Cross-checks prescribed medications (`Treatment1`–`Treatment7`) against all listed diagnoses (`Diagnosis1`–`Diagnosis7`). Flags cases where chronic or specialized drugs (e.g., `Amlodipine`, `Metformin`, `Lisinopril`) are dispensed without a matching clinical indication recorded on the encounter sheet.
  * Deduplication check ($O(1)$ hash check on `OYSHIA_ID` + `Date` + `Facility`).
* **Detailed Data Analyst Audit Report:**
  * Complete missing value analysis across all variables.
  * Age distribution profiling & digit heaping detection (detecting guessed ages).
  * Leading morbidity frequencies and polypharmacy statistics.
  * Health facility performance ranking (clean data rate per hospital).
* **Drill-Down / Filtered Reporting:** Generates customized audit reports filtered by specific Hospital, LGA, Date Range, or Condition.

### Feature 7: Inbuilt Dual-View Web SPSS Matrix
* **Data View:** Virtualized spreadsheet displaying all patient records.
* **Variable View:** Metadata tab showing variable names, labels, missing value rules, and value label codebooks.
* **Value Labels Toggle (`1 ↔ Words`):** 1-click toggle to switch between numeric codes (`2.0, 1`) and readable text (`Hypertension, Male`).
* **Audit Provenance (Paper Proof):** Clicking any cell opens a popover showing the original cropped paper form snippet where that exact value was written.

### Feature 8: 1-Click Native SPSS Binary Export (`.sav` + `.sps`)
* **Authentic Binary Generation:** Uses `pyreadstat` to produce genuine, uncorrupted IBM SPSS `.sav` files with preserved variable labels, codebooks, and missing value rules.
* **Reproducible Syntax (`.sps`):** Generates standardized SPSS syntax scripts for academic publication and donor verification.
* **Universal Exports:** 1-click export to Excel (`.xlsx`) with separate data and codebook sheets, as well as CSV and Stata (`.dta`).

### Feature 9: 100% Local Privacy & Offline Resilience
* **Zero Cloud Dependency:** Operates entirely on the local computer or local office network (LAN); immune to hospital internet outages.
* **NDPA / HIPAA Compliance:** Sensitive patient medical data and names never leave the local machine.
* **1-Click De-Identification:** Option to export anonymized datasets (stripping patient names and phone numbers) for academic research.

### Feature 10: Multi-Clerk SPSS Harmonizer & Master Merger (`.sav` Consolidator)
* **The Real-World Problem Solved:** When 30+ data entry clerks enter records independently on separate laptops, their `.sav` files inevitably diverge—clerks add custom variable names, use slightly different capitalization (`treatment2` vs `Treatment2`), change string widths, or assign conflicting numeric codes to new diagnoses (e.g., Clerk A assigns `265 = Eczema` while Clerk B assigns `265 = Asthma`). Standard IBM SPSS `Add Cases` either fails with type/width errors or silently corrupts medical data when numeric codes collide.
* **4-Layer Automatic Harmonization Pipeline:**
  1. **Master Variable Name Alignment:** Compares all uploaded `.sav` files against the project's Standard Variable List. Automatically normalizes case/spelling drift and prompts 1-click mapping for custom columns added by individual clerks.
  2. **Semantic Codebook Reconciliation (By Meaning, Not Raw Number):** Reads every file's `variable_value_labels` dictionary before merging. If File A maps `265 -> Eczema` and File B maps `265 -> Asthma`, the engine detects the collision, assigns `265 -> Eczema` and `266 -> Asthma` in the unified master codebook, and **automatically recodes File B's case values** from `265` to `266`. Conversely, if two clerks assigned different numbers to the *same* diagnosis (`265 -> Asthma` and `270 -> Asthma`), both are unified under one canonical code.
  3. **Type & String-Width Auto-Healing:** Automatically coerces mismatched types (e.g., String `"26"` $\rightarrow$ Numeric `26.0`) and expands string variable widths to the maximum length across all uploaded files so zero text is truncated.
  4. **Cross-Clerk Deduplication ($O(1)$ Hash Set):** Detects and removes duplicate patient encounters entered across different laptops (`OYSHIA_ID + Date + Facility`).
  5. **Clerk Source Provenance Tracking (`Entered_By_Clerk` & `Orig_Row_No`):** Automatically appends provenance variables (`Source_Clerk_ID`, `Source_File_Name`, `Orig_Row_No`) to every row in `MASTER_MERGED.sav` alongside a **Per-Clerk Quality & Error Scorecard**, enabling supervisors to trace any discrepancy directly back to the exact clerk and original file row.
* **Output:** Produces a single, 100% harmonized `MASTER_MERGED.sav` file alongside a **Merge & Harmonization Audit Report** detailing every reconciled variable, recoded value label, and per-clerk accuracy score.

### Feature 11: 1-Click SPSS Auto-Recode & Computed Variables Engine (`Transform → Recode` Automation)
* **The Problem Solved:** After data cleaning, biostatisticians typically spend hours writing SPSS `RECODE` and `COMPUTE` syntax to group continuous and granular variables before running frequency tables and cross-tabulations.
* **Automated Derived Variables (With Full SPSS Value Labels):**
  * **`Age_Group`:** Automatically recodes continuous `Age` into standard epidemiological brackets (`1 = Under 5`, `2 = 5–17`, `3 = 18–35`, `4 = 36–59`, `5 = 60+ Elderly/Pensioner`).
  * **`Primary_Disease_Category`:** Groups the 178 granular diagnosis codes into broad clinical classes (`1 = Cardiovascular/HTN`, `2 = Infectious/Malaria`, `3 = Metabolic/Diabetes`, `4 = Musculoskeletal`, `5 = Gastrointestinal/PUD`, `6 = Maternal/Reproductive`, `7 = Respiratory/ENT`, `8 = Other`).
  * **`Comorbidity_Count` & `Polypharmacy_Count`:** Automatically counts the number of active diagnoses (`Diagnosis1`–`Diagnosis7`) and prescribed drugs (`Treatment1`–`Treatment7`) per patient encounter.
