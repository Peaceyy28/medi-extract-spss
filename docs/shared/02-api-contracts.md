# 02 — API Contracts (Single Source of Truth)

**Schema Version:** `1.0.0`

All endpoints are prefixed with `/api/v1`. Both `/backend` and `/frontend` adhere strictly to these shapes.

---

## 1. Core Enums

```typescript
type MeasureLevel = "nominal" | "ordinal" | "scale";
type VariableType = "numeric" | "string" | "date";
type ValidationStatus = "AUTO_VERIFIED" | "NEEDS_REVIEW" | "RULE_CONTRADICTION" | "DUPLICATE_COLLISION";
type RuleSeverity = "WARNING" | "BLOCKER";
```

---

## 2. Project & SPSS Variable Schema (`Variable View`)

```json
{
  "project_id": "proj_oyshia_2025",
  "name": "OYSHIA Encounter Forms 2025",
  "created_at": "2026-11-13T12:00:00Z",
  "watch_folder": "C:\\EncounterForms\\ScanQueue",
  "total_cases": 10981,
  "pending_reviews": 3,
  "variables": [
    {
      "index": 1,
      "name": "Year",
      "type": "numeric",
      "width": 8,
      "decimals": 0,
      "label": "Encounter Calendar Year",
      "value_labels": {},
      "missing_values": [],
      "measure": "scale"
    },
    {
      "index": 7,
      "name": "Sex",
      "type": "numeric",
      "width": 8,
      "decimals": 0,
      "label": "Biological Sex of Enrollee",
      "value_labels": { "1.0": "Male", "2.0": "Female" },
      "missing_values": [],
      "measure": "nominal"
    },
    {
      "index": 10,
      "name": "Diagnosis1",
      "type": "numeric",
      "width": 8,
      "decimals": 0,
      "label": "Primary Clinical Diagnosis",
      "value_labels": {
        "1.0": "MSS OF THE WRIST",
        "2.0": "Hypertention",
        "4.0": "Malaria",
        "50.0": "DIABETES"
      },
      "missing_values": [],
      "measure": "nominal"
    }
  ]
}
```

---

## 3. Guided Verification Item (`Verification Station`)

```json
{
  "review_id": "rev_84_04_diag2",
  "project_id": "proj_oyshia_2025",
  "batch_id": "BATCH-2025-084",
  "case_index": 10982,
  "patient_summary": "Adeleke Taofeeq O. (Male, Age 48) — General Hospital, Igboho",
  "variable_name": "Diagnosis2",
  "variable_label": "Secondary Clinical Diagnosis",
  "status": "NEEDS_REVIEW",
  "raw_handwriting_text": "Mss wrist pain (?trauma)",
  "confidence": 0.68,
  "crop_image_url": "/api/v1/crops/BATCH-2025-084/case_04_Diagnosis2.webp",
  "full_page_url": "/api/v1/scans/BATCH-2025-084/page_04.webp",
  "suggested_candidates": [
    { "code": 1.0, "label": "MSS OF THE WRIST", "similarity": 0.91 },
    { "code": 13.0, "label": "MSS PAIN", "similarity": 0.84 },
    { "code": 91.0, "label": "MSS PAIN OF RIGHT KNEE", "similarity": 0.72 }
  ]
}
```

---

## 4. Filtered Data Analyst Validation Report

`POST /api/v1/projects/{project_id}/reports/validation`

**Request Body (Optional Filters):**
```json
{
  "facility_phc": "General Hospital, Igboho",
  "lga_code": "26",
  "month": 10,
  "year": 2025,
  "issue_type": "ALL"
}
```

**Response Body:**
```json
{
  "schema_version": "1.0.0",
  "project_id": "proj_oyshia_2025",
  "filters_applied": { "lga_code": "26", "month": 10, "year": 2025 },
  "summary": {
    "total_cases_evaluated": 10981,
    "clean_cases_count": 10829,
    "clean_rate_pct": 98.62,
    "flagged_cases_count": 152,
    "duplicates_prevented": 6
  },
  "missingness_audit": [
    { "variable": "OYSHIA_ID", "missing_count": 14, "missing_pct": 0.13, "severity": "WARNING" },
    { "variable": "Phone_contact", "missing_count": 118, "missing_pct": 1.07, "severity": "WARNING" }
  ],
  "demographics_audit": {
    "age_mean": 46.4,
    "age_median": 47.0,
    "age_min": 1.0,
    "age_max": 98.0,
    "age_outliers_count": 2,
    "digit_preference_whipple_index": 108.2,
    "sex_distribution": { "Male": 4173, "Female": 6808 }
  },
  "clinical_audit": {
    "top_diagnoses": [
      { "code": 2.0, "label": "Hypertention", "count": 3412, "pct": 31.07 },
      { "code": 4.0, "label": "Malaria", "count": 2890, "pct": 26.32 },
      { "code": 50.0, "label": "DIABETES", "count": 1420, "pct": 12.93 }
    ],
    "mean_drugs_per_encounter": 2.84,
    "contradictions_found": [
      {
        "case_index": 4102,
        "rule_id": "VR-02",
        "description": "Male patient (Sex=1) coded with Diagnosis=43 (FIBROID)"
      }
    ]
  },
  "facility_ranking": [
    { "facility": "General Hospital, Igboho", "cases": 1420, "clean_rate_pct": 99.2 },
    { "facility": "Adeoyo Maternity Hospital", "cases": 2110, "clean_rate_pct": 97.5 }
  ]
}
```

---

## 5. REST Endpoints Summary

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/projects` | List all projects and active scanner watch status |
| `POST` | `/api/v1/projects` | Create new project from `.sav` template or blank PDF |
| `POST` | `/api/v1/projects/{id}/ingest` | Upload scanned PDF/images or ingest from local file path |
| `GET` | `/api/v1/projects/{id}/reviews` | Fetch pending Guided Verification items |
| `POST` | `/api/v1/projects/{id}/reviews/{rev_id}/confirm` | Confirm or override a low-confidence field and commit to SPSS |
| `GET` | `/api/v1/projects/{id}/cases` | Paginated / virtual-window query of SPSS Data View rows |
| `POST` | `/api/v1/projects/{id}/reports/validation` | Generate full or filtered Data Analyst Validation Report |
| `GET` | `/api/v1/projects/{id}/export/sav` | Download native `.sav` binary (optional `?anonymize=true`) |
| `GET` | `/api/v1/projects/{id}/export/sps` | Download reproducible IBM SPSS `.sps` syntax file |
