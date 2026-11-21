"""Deterministic, non-PII synthetic OYSHIA fixture generator (32 variables, 100 encounters)."""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.schemas import (  # noqa: E402
    AlignmentClassification,
    CaseRow,
    CasesPageResponse,
    ClerkScorecardItem,
    ClinicalAudit,
    CodebookCollisionItem,
    ContradictionItem,
    DemographicsAudit,
    DriftAction,
    FacilityRankingItem,
    FieldProvenance,
    MeasureLevel,
    MergeInspectResponse,
    MissingnessItem,
    ProjectSchema,
    ReviewItem,
    RuleSeverity,
    SuggestedCandidate,
    TopDiagnosisItem,
    TypeCoercionItem,
    ValidationReportResponse,
    ValidationStatus,
    ValidationSummary,
    VariableDriftItem,
    VariableSchema,
    VariableType,
)
from app.services.spss_engine import (  # noqa: E402
    dataframe_cell_to_json,
    generate_sps_syntax,
    resolve_value_label,
    write_sav_file,
)

FIXTURES_DIR = _BACKEND_DIR.parent / "fixtures"

LGA_LABELS: dict[str, str] = {
    "1.0": "Afijio",
    "2.0": "Akinyele",
    "3.0": "Atiba",
    "4.0": "Atisbo",
    "5.0": "Egbeda",
    "6.0": "Ibadan North",
    "7.0": "Ibadan North-East",
    "8.0": "Ibadan North-West",
    "9.0": "Ibadan South-East",
    "10.0": "Ibadan South-West",
    "11.0": "Ibarapa Central",
    "12.0": "Ibarapa East",
    "13.0": "Ibarapa North",
    "14.0": "Ido",
    "15.0": "Irepo",
    "16.0": "Iseyin",
    "17.0": "Itesiwaju",
    "18.0": "Iwajowa",
    "19.0": "Kajola",
    "20.0": "Lagelu",
    "21.0": "Ogbomosho North",
    "22.0": "Ogbomosho South",
    "23.0": "Ogo Oluwa",
    "24.0": "Olorunsogo",
    "25.0": "Oluyole",
    "26.0": "Oorelope",
    "27.0": "Ori Ire",
    "28.0": "Oyo East",
    "29.0": "Oyo West",
    "30.0": "Saki East",
    "31.0": "Saki West",
    "32.0": "Surulere",
    "33.0": "Ona Ara",
}

SEX_LABELS: dict[str, str] = {"1.0": "Male", "2.0": "Female"}
EMPLOYER_LABELS: dict[str, str] = {
    "1.0": "State Civil Service",
    "2.0": "Local Government Staff",
    "3.0": "Formal Private Sector",
    "4.0": "Informal / Artisan",
    "5.0": "Vulnerable / Equity Fund",
}
REFERRAL_LABELS: dict[str, str] = {"1.0": "No", "2.0": "Yes"}


def _build_diagnosis_labels() -> dict[str, str]:
    exact = {
        "1.0": "MSS OF THE WRIST",
        "2.0": "Hypertention",
        "4.0": "Malaria",
        "13.0": "MSS PAIN",
        "22.0": "PUD / Dyspepsia",
        "43.0": "FIBROID",
        "44.0": "PREGNANCY / ANC",
        "50.0": "DIABETES",
        "73.0": "MALARIA PARASITE",
        "91.0": "MSS PAIN OF RIGHT KNEE",
        "116.0": "MISCARRIAGE",
        "117.0": "ECLAMPSIA",
        "121.0": "PELVIC INFLAMMATORY DISEASE",
        "224.0": "POSTPARTUM HAEMORRHAGE",
    }
    clinical_pool = [
        "Upper Respiratory Tract Infection",
        "Acute Gastroenteritis",
        "Urinary Tract Infection",
        "Enteric Fever (Typhoid)",
        "Bronchial Asthma",
        "Osteoarthritis",
        "Acute Bronchitis",
        "Allergic Rhinitis",
        "Bacterial Conjunctivitis",
        "Otitis Media",
        "Tonsillitis",
        "Dermatitis / Eczema",
        "Tinea Corporis",
        "Iron Deficiency Anaemia",
        "Sickle Cell Crisis",
        "Community Acquired Pneumonia",
        "Low Back Pain",
        "Cervical Spondylosis",
        "Migraine Headache",
        "Tension Headache",
        "Gastroesophageal Reflux Disease",
        "Acute Appendicitis",
        "Benign Prostatic Hyperplasia",
        "Cellulitis",
        "Soft Tissue Injury",
        "Laceration / Wound Care",
        "Hypercholesterolaemia",
        "Congestive Cardiac Failure",
        "Chronic Kidney Disease",
        "Tuberculosis (Pulmonary)",
        "Hepatitis B Infection",
        "Herpes Zoster",
        "Scabies",
        "Urticaria",
        "Dental Caries / Pulpitis",
        "Periodontitis",
        "Refractive Error",
        "Cataract",
        "Glaucoma",
        "Hypertensive Heart Disease",
        "Diabetic Foot Ulcer",
        "Hypoglycaemia",
        "Seizure Disorder",
        "Vertigo",
        "Anxiety Disorder",
        "Insomnia",
        "Menorrhagia",
        "Dysmenorrhoea",
        "Vaginal Candidiasis",
        "Neonatal Sepsis",
    ]
    labels = dict(exact)
    idx = 0
    code_num = 3
    while len(labels) < 178:
        key = f"{code_num}.0"
        if key not in labels:
            base = clinical_pool[idx % len(clinical_pool)]
            suffix = "" if idx < len(clinical_pool) else f" (Subtype {idx // len(clinical_pool) + 1})"
            labels[key] = f"{base}{suffix}"
            idx += 1
        code_num += 1
    return dict(sorted(labels.items(), key=lambda kv: float(kv[0])))


def _build_investigation_labels() -> dict[str, str]:
    base = [
        "Malaria RDT",
        "Malaria Parasite Microscopy",
        "Fasting Blood Glucose",
        "Random Blood Glucose",
        "Full Blood Count (FBC)",
        "Packed Cell Volume (PCV)",
        "Urinalysis",
        "Urine Microscopy Culture & Sensitivity",
        "Widal Reaction Test",
        "Stool Microscopy",
        "Electrolytes Urea & Creatinine (E/U/Cr)",
        "Liver Function Test (LFT)",
        "Lipid Profile",
        "HbA1c",
        "Hepatitis B Surface Antigen (HBsAg)",
        "Hepatitis C Virus Screening",
        "Retro-Viral Screening (HIV)",
        "Blood Group & Genotype",
        "Erythrocyte Sedimentation Rate (ESR)",
        "Pregnancy Test (PT)",
        "Pelvic Ultrasound Scan",
        "Abdominal Ultrasound Scan",
        "Obstetric Ultrasound Scan",
        "Chest X-Ray",
        "Lumbar Spine X-Ray",
        "Wrist / Extremity X-Ray",
        "Electrocardiogram (ECG)",
        "Echocardiography",
        "Sputum AFB / GeneXpert",
        "High Vaginal Swab (HVS) MCS",
        "PSA Screening",
        "Thyroid Function Test",
        "Serum Uric Acid",
        "Serum Bilirubin",
        "Blood Culture",
        "Wound Swab MCS",
        "Throat Swab MCS",
        "Prothrombin Time / INR",
        "D-Dimer",
        "Ferritin & Iron Studies",
        "Peak Expiratory Flow Rate",
        "Visual Acuity Assessment",
        "Fundoscopy",
        "Audiometry",
        "Pap Smear",
        "CRP Quantitative",
    ]
    return {f"{i + 1}.0": name for i, name in enumerate(base)}


def _build_treatment_labels() -> dict[str, str]:
    exact = {
        "1.0": "Artemether-Lumefantrine (ACT)",
        "2.0": "Paracetamol",
        "14.0": "Amlodipine",
        "15.0": "Lisinopril",
        "20.0": "Omeprazole",
        "54.0": "Metformin",
    }
    med_pool = [
        "Amoxicillin",
        "Amoxicillin-Clavulanate",
        "Ciprofloxacin",
        "Metronidazole",
        "Azithromycin",
        "Cefuroxime",
        "Ceftriaxone",
        "Doxycycline",
        "Erythromycin",
        "Gentamicin",
        "Ibuprofen",
        "Diclofenac",
        "Naproxen",
        "Celecoxib",
        "Tramadol",
        "Aspirin 75mg",
        "Nifedipine",
        "Losartan",
        "Hydrochlorothiazide",
        "Furosemide",
        "Atenolol",
        "Bisoprolol",
        "Methyldopa",
        "Glibenclamide",
        "Glimepiride",
        "Insulin (Soluble)",
        "Insulin (Premixed)",
        "Atorvastatin",
        "Simvastatin",
        "Clopidogrel",
        "Salbutamol Inhaler",
        "Prednisolone",
        "Hydrocortisone",
        "Loratadine",
        "Cetirizine",
        "Chlorpheniramine",
        "Rabeprazole",
        "Antacid Suspension",
        "Hyoscine Butylbromide",
        "Oral Rehydration Salts (ORS)",
        "Zinc Sulphate",
        "Loperamide",
        "Folic Acid",
        "Ferrous Sulphate",
        "Vitamin B Complex",
        "Vitamin C",
        "Multivitamin",
        "Calcium + Vitamin D3",
        "Clotrimazole Pessary",
        "Fluconazole",
        "Artesunate Injection",
        "Dihydroartemisinin-Piperaquine",
        "Mupirocin Ointment",
        "Betamethasone Cream",
        "Calamine Lotion",
        "Gentamicin Eye Drops",
        "Ciprofloxacin Ear Drops",
        "Tetanus Toxoid",
        "Normal Saline IV",
        "Ringer Lactate IV",
    ]
    labels = dict(exact)
    idx = 0
    code_num = 3
    while len(labels) < 241:
        key = f"{code_num}.0"
        if key not in labels:
            base = med_pool[idx % len(med_pool)]
            suffix = "" if idx < len(med_pool) else f" ({250 * ((idx // len(med_pool)) + 1)}mg/Variant)"
            labels[key] = f"{base}{suffix}"
            idx += 1
        code_num += 1
    return dict(sorted(labels.items(), key=lambda kv: float(kv[0])))


DIAGNOSIS_LABELS = _build_diagnosis_labels()
INVESTIGATION_LABELS = _build_investigation_labels()
TREATMENT_LABELS = _build_treatment_labels()

SYNTHETIC_FACILITIES = [
    ("General Hospital, Igboho", 26.0),
    ("Adeoyo Maternity Hospital", 6.0),
    ("Ring Road State Hospital", 10.0),
    ("General Hospital, Oyo", 28.0),
    ("General Hospital, Iseyin", 16.0),
    ("General Hospital, Ogbomosho", 21.0),
]


def build_oyshia_variables() -> list[VariableSchema]:
    """Return the canonical 32-variable OYSHIA clinical encounter Variable View."""
    vars_list: list[VariableSchema] = [
        VariableSchema(index=1, name="Year", type=VariableType.NUMERIC, width=8, decimals=0, label="Encounter Calendar Year", measure=MeasureLevel.SCALE),
        VariableSchema(index=2, name="Month", type=VariableType.NUMERIC, width=8, decimals=0, label="Encounter Calendar Month", measure=MeasureLevel.SCALE),
        VariableSchema(index=3, name="FacilityPHC", type=VariableType.STRING, width=64, decimals=0, label="Health Facility / PHC Name", measure=MeasureLevel.NOMINAL),
        VariableSchema(index=4, name="LGA", type=VariableType.NUMERIC, width=8, decimals=0, label="Local Government Area", value_labels=LGA_LABELS, measure=MeasureLevel.NOMINAL),
        VariableSchema(index=5, name="OYSHIA_ID", type=VariableType.STRING, width=24, decimals=0, label="Synthetic Enrollee Insurance ID", measure=MeasureLevel.NOMINAL),
        VariableSchema(index=6, name="Name", type=VariableType.STRING, width=48, decimals=0, label="Synthetic Enrollee Full Name", measure=MeasureLevel.NOMINAL),
        VariableSchema(index=7, name="Sex", type=VariableType.NUMERIC, width=8, decimals=0, label="Biological Sex of Enrollee", value_labels=SEX_LABELS, measure=MeasureLevel.NOMINAL),
        VariableSchema(index=8, name="Age", type=VariableType.NUMERIC, width=8, decimals=0, label="Age in Years", measure=MeasureLevel.SCALE),
        VariableSchema(index=9, name="Phone_contact", type=VariableType.STRING, width=20, decimals=0, label="Synthetic Phone Contact", measure=MeasureLevel.NOMINAL),
        VariableSchema(index=10, name="Employer", type=VariableType.NUMERIC, width=8, decimals=0, label="Enrollee Sector / Employer Group", value_labels=EMPLOYER_LABELS, measure=MeasureLevel.NOMINAL),
        VariableSchema(index=11, name="Referral", type=VariableType.NUMERIC, width=8, decimals=0, label="Referral Status", value_labels=REFERRAL_LABELS, measure=MeasureLevel.NOMINAL),
    ]

    idx = 12
    for slot in range(1, 8):
        lbl = "Primary Clinical Diagnosis" if slot == 1 else f"Clinical Diagnosis {slot}"
        vars_list.append(
            VariableSchema(
                index=idx,
                name=f"Diagnosis{slot}",
                type=VariableType.NUMERIC,
                width=8,
                decimals=0,
                label=lbl,
                value_labels=DIAGNOSIS_LABELS,
                measure=MeasureLevel.NOMINAL,
            )
        )
        idx += 1

    for slot in range(1, 8):
        vars_list.append(
            VariableSchema(
                index=idx,
                name=f"Investigation{slot}",
                type=VariableType.NUMERIC,
                width=8,
                decimals=0,
                label=f"Laboratory / Diagnostic Investigation {slot}",
                value_labels=INVESTIGATION_LABELS,
                measure=MeasureLevel.NOMINAL,
            )
        )
        idx += 1

    for slot in range(1, 8):
        vars_list.append(
            VariableSchema(
                index=idx,
                name=f"Treatment{slot}",
                type=VariableType.NUMERIC,
                width=8,
                decimals=0,
                label=f"Prescribed Medication {slot}",
                value_labels=TREATMENT_LABELS,
                measure=MeasureLevel.NOMINAL,
            )
        )
        idx += 1

    return vars_list


def generate_synthetic_dataframe(num_rows: int = 100, seed: int = 42) -> pd.DataFrame:
    """Create 100 deterministic non-PII synthetic encounters with 5 planted validation anomalies."""
    rng = random.Random(seed)
    clinical_profiles = [
        ([4.0], [1.0, 6.0], [1.0, 2.0]),            # Malaria -> RDT, PCV -> ACT, Paracetamol
        ([2.0], [11.0, 27.0], [14.0, 15.0]),        # Hypertension -> E/U/Cr, ECG -> Amlodipine, Lisinopril
        ([50.0, 2.0], [3.0, 14.0], [54.0, 14.0]),   # Diabetes + HTN -> FBG, HbA1c -> Metformin, Amlodipine
        ([22.0], [10.0], [20.0]),                   # PUD/Dyspepsia -> Stool -> Omeprazole
        ([1.0, 13.0], [26.0], [2.0]),               # MSS Wrist + Pain -> X-Ray -> Paracetamol
    ]

    records: list[dict[str, object]] = []
    for i in range(1, num_rows + 1):
        facility, lga_code = SYNTHETIC_FACILITIES[(i - 1) % len(SYNTHETIC_FACILITIES)]
        profile_idx = (i - 1) % len(clinical_profiles)
        diags, invs, treats = clinical_profiles[profile_idx]

        sex = 1.0 if rng.random() < 0.4 else 2.0
        age = float(rng.randint(4, 78))
        if sex == 2.0 and i % 15 == 0:
            diags, invs, treats = [44.0], [20.0, 23.0], [45.0]  # ANC -> PT, Scan -> Folic Acid

        row: dict[str, object] = {
            "Year": 2025.0,
            "Month": float(((i - 1) % 12) + 1),
            "FacilityPHC": facility,
            "LGA": lga_code,
            "OYSHIA_ID": f"SYN-OY-{i:05d}",
            "Name": f"Synthetic Enrollee {i:03d}",
            "Sex": sex,
            "Age": age,
            "Phone_contact": f"0800-000-{i:04d}",
            "Employer": float(((i - 1) % 5) + 1),
            "Referral": 2.0 if i % 10 == 0 else 1.0,
        }
        for slot in range(1, 8):
            row[f"Diagnosis{slot}"] = float(diags[slot - 1]) if slot <= len(diags) else np.nan
            row[f"Investigation{slot}"] = float(invs[slot - 1]) if slot <= len(invs) else np.nan
            row[f"Treatment{slot}"] = float(treats[slot - 1]) if slot <= len(treats) else np.nan
        records.append(row)

    # Plant 5 deterministic test anomalies (Rows 11..15)
    # 1. Missing mandatory OYSHIA_ID (Row 11 -> index 10)
    records[10]["OYSHIA_ID"] = ""
    # 2. Impossible age outlier (Row 12 -> index 11)
    records[11]["Age"] = 140.0
    # 3. Cross-variable contradiction: Male with FIBROID (43.0) (Row 13 -> index 12)
    records[12]["Sex"] = 1.0
    records[12]["Diagnosis1"] = 43.0
    # 4. VR-04-RX Diagnosis-to-Drug mismatch: Malaria only (4.0) + Metformin (54.0) & Amlodipine (14.0)
    records[13]["Diagnosis1"] = 4.0
    for slot in range(2, 8):
        records[13][f"Diagnosis{slot}"] = np.nan
    records[13]["Treatment1"] = 54.0
    records[13]["Treatment2"] = 14.0
    # 5. Duplicate encounter matching Row 1 (Row 15 -> index 14)
    records[14]["OYSHIA_ID"] = records[0]["OYSHIA_ID"]
    records[14]["Year"] = records[0]["Year"]
    records[14]["Month"] = records[0]["Month"]
    records[14]["FacilityPHC"] = records[0]["FacilityPHC"]

    return pd.DataFrame(records)


def generate_all_fixtures() -> None:
    """Write .sav, .sps, and JSON contract fixtures into /fixtures."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    variables = build_oyshia_variables()
    df = generate_synthetic_dataframe(num_rows=100, seed=42)

    sav_path = FIXTURES_DIR / "oyshia_encounter_synthetic.sav"
    write_sav_file(
        df=df,
        variables=variables,
        output_path=sav_path,
        anonymize=False,
        file_label="OYSHIA Synthetic Non-PII Encounter Fixtures",
    )

    sps_path = FIXTURES_DIR / "oyshia_encounter_synthetic.sps"
    sps_path.write_text(
        generate_sps_syntax(variables, sav_filename="oyshia_encounter_synthetic.sav"),
        encoding="utf-8",
    )

    project_schema = ProjectSchema(
        project_id="proj_oyshia_2025",
        name="OYSHIA Encounter Forms 2025 (Synthetic Fixture)",
        created_at="2026-11-13T12:00:00Z",
        watch_folder=r"C:\EncounterForms\ScanQueue",
        total_cases=len(df),
        pending_reviews=5,
        variables=variables,
    )
    (FIXTURES_DIR / "oyshia_project_schema.json").write_text(
        project_schema.model_dump_json(indent=2),
        encoding="utf-8",
    )

    var_map = {v.name: v for v in variables}
    sample_rows: list[CaseRow] = []
    for idx in range(25):
        rec = df.iloc[idx].to_dict()
        values = {k: dataframe_cell_to_json(v) for k, v in rec.items()}
        labels = {k: resolve_value_label(v, var_map[k]) for k, v in rec.items()}
        provenance = {
            "Diagnosis1": FieldProvenance(
                page_number=idx + 1,
                bbox=[0.18, 0.52, 0.34, 0.06],
                crop_image_uri=f"/api/v1/crops/BATCH-2025-SYN/case_{idx + 1:02d}_Diagnosis1.webp",
                raw_ocr_text=labels.get("Diagnosis1", ""),
                confidence=0.95 if idx not in {12, 13} else 0.72,
            )
        }
        status = ValidationStatus.AUTO_VERIFIED
        if idx == 12:
            status = ValidationStatus.RULE_CONTRADICTION
        elif idx == 13:
            status = ValidationStatus.NEEDS_REVIEW
        elif idx == 14:
            status = ValidationStatus.DUPLICATE_COLLISION

        sample_rows.append(
            CaseRow(
                case_index=idx + 1,
                values=values,
                labels=labels,
                provenance=provenance,
                validation_status=status,
            )
        )

    cases_sample = CasesPageResponse(
        project_id="proj_oyshia_2025",
        total_cases=len(df),
        offset=0,
        limit=25,
        rows=sample_rows,
    )
    (FIXTURES_DIR / "oyshia_cases_sample.json").write_text(
        cases_sample.model_dump_json(indent=2),
        encoding="utf-8",
    )

    reviews_sample = [
        ReviewItem(
            review_id="rev_syn_01_diag2",
            project_id="proj_oyshia_2025",
            batch_id="BATCH-2025-SYN",
            case_index=4,
            patient_summary="Synthetic Enrollee 004 (Female, Age 39) — General Hospital, Oyo",
            variable_name="Diagnosis2",
            variable_label="Clinical Diagnosis 2",
            status=ValidationStatus.NEEDS_REVIEW,
            raw_handwriting_text="Mss wrist pain (?trauma)",
            confidence=0.68,
            crop_image_url="/api/v1/crops/BATCH-2025-SYN/case_04_Diagnosis2.webp",
            full_page_url="/api/v1/scans/BATCH-2025-SYN/page_04.webp",
            suggested_candidates=[
                SuggestedCandidate(code=1.0, label="MSS OF THE WRIST", similarity=0.91),
                SuggestedCandidate(code=13.0, label="MSS PAIN", similarity=0.84),
                SuggestedCandidate(code=91.0, label="MSS PAIN OF RIGHT KNEE", similarity=0.72),
            ],
        ),
        ReviewItem(
            review_id="rev_syn_02_diag1",
            project_id="proj_oyshia_2025",
            batch_id="BATCH-2025-SYN",
            case_index=14,
            patient_summary="Synthetic Enrollee 014 (Male, Age 52) — Adeoyo Maternity Hospital",
            variable_name="Diagnosis1",
            variable_label="Primary Clinical Diagnosis",
            status=ValidationStatus.NEEDS_REVIEW,
            raw_handwriting_text="High BP / HTN",
            confidence=0.81,
            crop_image_url="/api/v1/crops/BATCH-2025-SYN/case_14_Diagnosis1.webp",
            full_page_url="/api/v1/scans/BATCH-2025-SYN/page_14.webp",
            suggested_candidates=[
                SuggestedCandidate(code=2.0, label="Hypertention", similarity=0.94),
                SuggestedCandidate(code=50.0, label="DIABETES", similarity=0.41),
            ],
        ),
        ReviewItem(
            review_id="rev_syn_03_diag1",
            project_id="proj_oyshia_2025",
            batch_id="BATCH-2025-SYN",
            case_index=21,
            patient_summary="Synthetic Enrollee 021 (Female, Age 29) — Ring Road State Hospital",
            variable_name="Diagnosis1",
            variable_label="Primary Clinical Diagnosis",
            status=ValidationStatus.NEEDS_REVIEW,
            raw_handwriting_text="Dyspepsia / PUD",
            confidence=0.79,
            crop_image_url="/api/v1/crops/BATCH-2025-SYN/case_21_Diagnosis1.webp",
            full_page_url="/api/v1/scans/BATCH-2025-SYN/page_21.webp",
            suggested_candidates=[
                SuggestedCandidate(code=22.0, label="PUD / Dyspepsia", similarity=0.96),
            ],
        ),
        ReviewItem(
            review_id="rev_syn_04_treat1",
            project_id="proj_oyshia_2025",
            batch_id="BATCH-2025-SYN",
            case_index=35,
            patient_summary="Synthetic Enrollee 035 (Female, Age 61) — General Hospital, Igboho",
            variable_name="Treatment1",
            variable_label="Prescribed Medication 1",
            status=ValidationStatus.NEEDS_REVIEW,
            raw_handwriting_text="Tab Amlod 5mg dly",
            confidence=0.84,
            crop_image_url="/api/v1/crops/BATCH-2025-SYN/case_35_Treatment1.webp",
            full_page_url="/api/v1/scans/BATCH-2025-SYN/page_35.webp",
            suggested_candidates=[
                SuggestedCandidate(code=14.0, label="Amlodipine", similarity=0.92),
                SuggestedCandidate(code=15.0, label="Lisinopril", similarity=0.58),
            ],
        ),
        ReviewItem(
            review_id="rev_syn_05_diag1",
            project_id="proj_oyshia_2025",
            batch_id="BATCH-2025-SYN",
            case_index=48,
            patient_summary="Synthetic Enrollee 048 (Male, Age 19) — General Hospital, Iseyin",
            variable_name="Diagnosis1",
            variable_label="Primary Clinical Diagnosis",
            status=ValidationStatus.NEEDS_REVIEW,
            raw_handwriting_text="MP ++",
            confidence=0.76,
            crop_image_url="/api/v1/crops/BATCH-2025-SYN/case_48_Diagnosis1.webp",
            full_page_url="/api/v1/scans/BATCH-2025-SYN/page_48.webp",
            suggested_candidates=[
                SuggestedCandidate(code=73.0, label="MALARIA PARASITE", similarity=0.91),
                SuggestedCandidate(code=4.0, label="Malaria", similarity=0.88),
            ],
        ),
    ]
    (FIXTURES_DIR / "oyshia_reviews_sample.json").write_text(
        json.dumps([r.model_dump() for r in reviews_sample], indent=2),
        encoding="utf-8",
    )

    validation_report = ValidationReportResponse(
        schema_version="1.0.0",
        project_id="proj_oyshia_2025",
        filters_applied={"issue_type": "ALL"},
        summary=ValidationSummary(
            total_cases_evaluated=100,
            clean_cases_count=95,
            clean_rate_pct=95.0,
            flagged_cases_count=5,
            duplicates_prevented=1,
        ),
        missingness_audit=[
            MissingnessItem(variable="OYSHIA_ID", missing_count=1, missing_pct=1.0, severity=RuleSeverity.WARNING),
        ],
        demographics_audit=DemographicsAudit(
            age_mean=42.1,
            age_median=41.0,
            age_min=4.0,
            age_max=140.0,
            age_outliers_count=1,
            digit_preference_whipple_index=104.0,
            sex_distribution={"Male": 40, "Female": 60},
        ),
        clinical_audit=ClinicalAudit(
            top_diagnoses=[
                TopDiagnosisItem(code=2.0, label="Hypertention", count=38, pct=38.0),
                TopDiagnosisItem(code=4.0, label="Malaria", count=21, pct=21.0),
                TopDiagnosisItem(code=50.0, label="DIABETES", count=19, pct=19.0),
            ],
            mean_drugs_per_encounter=1.6,
            contradictions_found=[
                ContradictionItem(
                    case_index=13,
                    rule_id="VR-02",
                    description="Male patient (Sex=1) coded with Diagnosis=43 (FIBROID)",
                ),
                ContradictionItem(
                    case_index=14,
                    rule_id="VR-04-RX",
                    description="Diagnosis-to-Drug Mismatch: Prescribed Metformin (54) & Amlodipine (14) with only Malaria (4.0) listed under Diagnoses",
                ),
            ],
        ),
        facility_ranking=[
            FacilityRankingItem(facility="General Hospital, Igboho", cases=17, clean_rate_pct=100.0),
            FacilityRankingItem(facility="Adeoyo Maternity Hospital", cases=17, clean_rate_pct=88.24),
        ],
    )
    (FIXTURES_DIR / "oyshia_validation_report_sample.json").write_text(
        validation_report.model_dump_json(indent=2),
        encoding="utf-8",
    )

    merge_inspect = MergeInspectResponse(
        merge_session_id="mrg_2025_syn_01",
        files_uploaded=4,
        total_rows_across_files=100,
        exact_schema_matches=29,
        variable_drifts=[
            VariableDriftItem(
                source_file="Clerk_SynA_Oct.sav",
                source_variable="treatment2",
                suggested_master_variable="Treatment2",
                classification=AlignmentClassification.EXACT_MATCH,
                action=DriftAction.AUTO_RENAME,
                confidence=1.0,
            ),
            VariableDriftItem(
                source_file="Clerk_SynB_Oct.sav",
                source_variable="Patient_Phone2",
                suggested_master_variable="Phone_contact",
                classification=AlignmentClassification.STRONG_SUGGESTION,
                action=DriftAction.PROMPT_USER,
                confidence=0.82,
            ),
        ],
        codebook_collisions_resolved=[
            CodebookCollisionItem(
                variable="Diagnosis1",
                source_file="Clerk_SynB_Oct.sav",
                original_code=265.0,
                label="Costochondritis",
                conflict_with_master_label="Eczema",
                new_assigned_code=266.0,
                rows_recoded=4,
            ),
        ],
        type_coercions=[
            TypeCoercionItem(
                source_file="Clerk_SynC_Oct.sav",
                variable="LGA",
                from_type=VariableType.STRING,
                to_type=VariableType.NUMERIC,
                status="AUTO_HEALED",
            ),
        ],
        cross_file_duplicates_detected=1,
        clerk_quality_scorecard=[
            ClerkScorecardItem(
                clerk_id=1,
                source_file="Clerk_SynA_Oct.sav",
                rows_contributed=50,
                missing_rate_pct=0.0,
                logic_errors_count=0,
                codebook_collisions_count=0,
            ),
            ClerkScorecardItem(
                clerk_id=2,
                source_file="Clerk_SynB_Oct.sav",
                rows_contributed=50,
                missing_rate_pct=2.0,
                logic_errors_count=2,
                codebook_collisions_count=1,
            ),
        ],
    )
    (FIXTURES_DIR / "oyshia_merge_inspect_sample.json").write_text(
        merge_inspect.model_dump_json(indent=2),
        encoding="utf-8",
    )

    print(f"Generated synthetic fixtures in {FIXTURES_DIR} ({len(variables)} variables, {len(df)} rows)")


if __name__ == "__main__":
    generate_all_fixtures()
