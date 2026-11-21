"""Live end-to-end verification & latency benchmark for local open-weight models in Documents\\LLMs."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.config import reset_settings_cache  # noqa: E402
from app.schemas import ValidationReportFilter  # noqa: E402
from app.services.autocoder import get_embedder, get_project_autocoder, reset_autocoder_cache, reset_embedder_cache  # noqa: E402
from app.services.narrative_writer import generate_report_narrative  # noqa: E402
from app.services.project_store import get_project_store, reset_project_store_cache  # noqa: E402
from app.services.validation_engine import run_validation_report  # noqa: E402
from app.services.vision_htr import VisionHTRClient  # noqa: E402


def _make_sample_handwritten_form_webp() -> bytes:
    img = np.full((900, 1200, 3), 252, dtype=np.uint8)
    lines = [
        "OYO STATE HEALTH INSURANCE AGENCY (OYSHIA) - ENCOUNTER FORM",
        "Year: 2025    Month: 10",
        "FacilityPHC: General Hospital, Igboho    LGA: 26",
        "OYSHIA_ID: SYN-OY-00999    Name: Synthetic Test Patient",
        "Sex: Female    Age: 48    Phone_contact: 0800-000-0999",
        "Diagnosis1: Malaria",
        "Diagnosis2: Hypertension",
        "Treatment1: Amlodipine 5mg daily",
        "Treatment2: Artemether-Lumefantrine",
    ]
    y = 70
    for idx, line in enumerate(lines):
        scale = 0.85 if idx == 0 else 0.78
        thickness = 2
        cv2.putText(img, line, (45, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (25, 35, 90), thickness)
        y += 85
    ok, buf = cv2.imencode(".webp", img, [cv2.IMWRITE_WEBP_QUALITY, 90])
    assert ok
    return buf.tobytes()


def main() -> None:
    os.environ["MEDIEXTRACT_VISION_PROVIDER_CHAIN"] = "ollama"
    os.environ["MEDIEXTRACT_EMBEDDING_BACKEND"] = "fastembed"
    os.environ.setdefault("MEDIEXTRACT_FASTEMBED_CACHE_PATH", r"C:\Users\USER\Documents\LLMs\fastembed")
    reset_settings_cache()
    reset_embedder_cache()
    reset_autocoder_cache()
    reset_project_store_cache()

    store = get_project_store()
    project = store.get_project("proj_oyshia_2025")
    assert project is not None

    print("=== 1. Real FastEmbed (BAAI/bge-small-en-v1.5) Auto-Coder Benchmark ===")
    t0 = time.perf_counter()
    embedder = get_embedder()
    coder = get_project_autocoder("proj_oyshia_2025", project.variables, embedder=embedder)
    # Warm up Diagnosis1 + Treatment1 embedding matrices
    _ = coder.code_term("Diagnosis1", "Malaria")
    _ = coder.code_term("Treatment1", "Paracetamol")
    t_warm = (time.perf_counter() - t0) * 1000.0
    print(f"Codebook warmup (419 labels embedded via BGE ONNX): {t_warm:.1f} ms")

    test_terms = [
        ("Diagnosis1", "HTN"),
        ("Diagnosis1", "Mss wrist pain (?trauma)"),
        ("Diagnosis1", "elevated blood sugar"),
        ("Treatment1", "Tab Amlod 5mg dly"),
        ("Diagnosis1", "xzqflp qwertz"),
    ]
    for var_name, term in test_terms:
        q0 = time.perf_counter()
        res = coder.code_term(var_name, term)
        dt = (time.perf_counter() - q0) * 1000.0
        print(
            f"  [{var_name}] '{term}' -> tier={res.match_tier}, code={res.matched_code}, "
            f"label={res.matched_label!r}, sim={res.similarity:.4f}, quarantined={res.quarantined} ({dt:.2f} ms)"
        )

    print("\n=== 2. Real Ollama Vision HTR (qwen2.5vl:3b on RTX 4000) ===")
    img_bytes = _make_sample_handwritten_form_webp()
    v_client = VisionHTRClient()
    v0 = time.perf_counter()
    v_out = v_client.extract_page(
        img_bytes,
        ["Year", "Month", "FacilityPHC", "OYSHIA_ID", "Name", "Sex", "Age", "Diagnosis1", "Diagnosis2", "Treatment1"],
        page_number=1,
    )
    vt = time.perf_counter() - v0
    print(f"Provider: {v_out.provider_used} ({v_out.model_used}) in {vt:.2f}s")
    for k, pred in v_out.fields.items():
        print(f"  {k}: {pred.raw_text!r} (conf={pred.ocr_confidence:.3f})")

    print("\n=== 3. Real Ollama Narrative Writer (llama3.2:3b on RTX 4000) ===")
    df, variables = store.get_dataframe_and_schema("proj_oyshia_2025")  # type: ignore[misc]
    report = run_validation_report("proj_oyshia_2025", df, variables, ValidationReportFilter())
    n0 = time.perf_counter()
    narrative, used = generate_report_narrative(report, project.name)
    nt = time.perf_counter() - n0
    print(f"Provider: {used} in {nt:.2f}s")
    print(f"Narrative: {narrative}")


if __name__ == "__main__":
    main()
