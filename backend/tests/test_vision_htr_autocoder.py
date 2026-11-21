"""Tests for Milestone D4: Vision HTR provider chain, confidence gate, auto-coder, and review commit."""

from __future__ import annotations

import json
import math
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.config import Settings
from app.schemas import ValidationStatus
from app.services.autocoder import DeterministicStubEmbedder, MedicalAutoCoder
from app.services.project_store import get_project_store
from app.services.vision_htr import (
    VisionHTRClient,
    VisionProvider,
    build_vision_provider_chain,
    compute_ocr_confidence_from_logprobs,
    compute_total_confidence,
    evaluate_confidence_gate,
)
from tests.test_scanner_opencv_omr import _draw_synthetic_form_image, _encode_png


def test_confidence_math_and_gate() -> None:
    # Geometric mean probability exp(mean(log p))
    probs = [0.95, 0.90, 0.96]
    lps = [math.log(p) for p in probs]
    conf = compute_ocr_confidence_from_logprobs(lps)
    expected = round((0.95 * 0.90 * 0.96) ** (1 / 3), 4)
    assert abs(conf - expected) < 1e-4

    # min(Conf_OCR, Sim_code)
    assert compute_total_confidence(0.95, 0.88) == 0.88
    assert compute_total_confidence(0.68, 0.94) == 0.68
    assert compute_total_confidence(0.92, None) == 0.92

    assert evaluate_confidence_gate(0.90) == ValidationStatus.AUTO_VERIFIED
    assert evaluate_confidence_gate(0.8999) == ValidationStatus.NEEDS_REVIEW


def test_autocoder_exact_synonym_vector_and_quarantine(client: TestClient) -> None:
    store = get_project_store()
    project = store.get_project("proj_oyshia_2025")
    assert project is not None

    coder = MedicalAutoCoder(project.variables, embedder=DeterministicStubEmbedder())

    # O(1) synonym lookups
    htn = coder.code_term("Diagnosis1", "HTN")
    assert htn.match_tier == "SYNONYM"
    assert htn.matched_code == 2.0
    assert htn.matched_label == "Hypertention"

    amlod = coder.code_term("Treatment1", "Tab Amlod 5mg dly")
    assert amlod.match_tier == "SYNONYM"
    assert amlod.matched_code == 14.0
    assert amlod.matched_label == "Amlodipine"

    pud = coder.code_term("Diagnosis1", "PUD")
    assert pud.matched_code == 22.0

    # Vector similarity ranking for noisy handwritten note
    mss = coder.code_term("Diagnosis2", "Mss wrist pain (?trauma)")
    assert mss.quarantined is False
    assert mss.matched_code == 1.0
    assert mss.matched_label == "MSS OF THE WRIST"

    # Unprecedented gibberish quarantined safely
    gib = coder.code_term("Diagnosis1", "xzqflp qwertz")
    assert gib.quarantined is True
    assert gib.match_tier == "QUARANTINED"
    assert gib.matched_code is None

    # Endpoint test
    res = client.post(
        "/api/v1/projects/proj_oyshia_2025/autocode",
        json={"variable_name": "Diagnosis1", "raw_text": "High BP", "top_k": 3},
    )
    assert res.status_code == 200
    assert res.json()["matched_code"] == 2.0


def test_vision_provider_chain_selection_and_failover() -> None:
    settings = Settings(
        vision_provider_chain="huggingface,groq,ollama",
        hf_token="hf_test_token",
        groq_api_key="",  # unconfigured -> skipped
        ollama_base_url="http://localhost:11434/v1",
    )
    chain = build_vision_provider_chain(settings)
    assert [p.name for p in chain] == ["huggingface", "ollama"]

    calls: list[str] = []

    def fake_factory(provider: VisionProvider):
        class FakeCompletions:
            def create(self, **kwargs):
                calls.append(provider.name)
                if provider.name == "huggingface":
                    err = RuntimeError("Rate limit 429")
                    setattr(err, "status_code", 429)
                    raise err
                msg = SimpleNamespace(
                    content=json.dumps(
                        {
                            "fields": {
                                "Diagnosis1": {"raw_text": "Malaria", "confidence": 0.96}
                            }
                        }
                    )
                )
                lp = SimpleNamespace(content=[SimpleNamespace(logprob=math.log(0.95))])
                choice = SimpleNamespace(message=msg, logprobs=lp)
                return SimpleNamespace(choices=[choice])

        return SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))

    htr = VisionHTRClient(settings=settings, client_factory=fake_factory)
    out = htr.extract_page(b"fake-webp", ["Diagnosis1"], page_number=1)
    assert calls == ["huggingface", "ollama"]
    assert out.provider_used == "ollama"
    assert out.fields["Diagnosis1"].raw_text == "Malaria"
    assert out.fields["Diagnosis1"].ocr_confidence == 0.95


def test_batch_extract_review_confirm_spss_commit_and_immutable_audit(
    client: TestClient,
) -> None:
    # 1. Ingest synthetic encounter sheet (Female=2.0, Referral=Yes=2.0)
    png_bytes = _encode_png(_draw_synthetic_form_image(tick_sex="Female", tick_referral="Yes"))
    ingest_res = client.post(
        "/api/v1/projects/proj_oyshia_2025/ingest",
        data={"facility": "General Hospital, Igboho"},
        files=[("files", ("sheet_d4.png", png_bytes, "image/png"))],
    )
    assert ingest_res.status_code == 201
    batch_id = ingest_res.json()["batch_id"]

    # 2. Extract batch (uses stub Vision HTR + OMR + Auto-Coder)
    ext_res = client.post(
        f"/api/v1/projects/proj_oyshia_2025/batches/{batch_id}/extract"
    )
    assert ext_res.status_code == 200
    ext = ext_res.json()
    assert ext["cases_added"] == 1
    assert ext["auto_verified_fields"] >= 8
    assert ext["reviews_queued"] >= 1

    # 3. Verify Case #101 committed with provenance & auto-coded Diagnosis1=2.0, Treatment1=14.0, Sex=2.0
    cases_res = client.get("/api/v1/projects/proj_oyshia_2025/cases?offset=100&limit=5")
    assert cases_res.status_code == 200
    cases_data = cases_res.json()
    assert cases_data["total_cases"] == 101
    new_row = cases_data["rows"][0]
    assert new_row["case_index"] == 101
    assert new_row["values"]["Sex"] == 2.0
    assert new_row["values"]["Diagnosis1"] == 2.0
    assert new_row["values"]["Treatment1"] == 14.0
    assert "Diagnosis1" in new_row["provenance"]
    assert new_row["provenance"]["Diagnosis1"]["crop_image_uri"].startswith("/api/v1/crops/")

    # 4. Fetch pending review for Diagnosis2 (<0.90 confidence) and confirm with edit
    revs_res = client.get(f"/api/v1/projects/proj_oyshia_2025/reviews?batch_id={batch_id}")
    assert revs_res.status_code == 200
    revs = revs_res.json()
    diag2_rev = next(r for r in revs if r["variable_name"] == "Diagnosis2")
    assert diag2_rev["confidence"] < 0.90
    assert diag2_rev["suggested_candidates"][0]["code"] == 1.0

    confirm_res = client.post(
        f"/api/v1/projects/proj_oyshia_2025/reviews/{diag2_rev['review_id']}/confirm",
        json={
            "action": "edit",
            "selected_code": 1.0,
            "corrected_text": "MSS OF THE WRIST",
            "reviewer": "clerk_duro",
            "reason": "Verified against cropped handwriting",
        },
    )
    assert confirm_res.status_code == 200
    conf_body = confirm_res.json()
    assert conf_body["review"]["status"] == "AUTO_VERIFIED"
    assert conf_body["audit_entry"]["raw_ocr_text"] == "Mss wrist pain (?trauma)"
    assert conf_body["audit_entry"]["selected_code"] == 1.0

    # Verify SPSS Data View row updated to Diagnosis2 = 1.0 & audit trail persisted
    row_after = client.get("/api/v1/projects/proj_oyshia_2025/cases?offset=100&limit=5").json()["rows"][0]
    assert row_after["values"]["Diagnosis2"] == 1.0

    audit_res = client.get(
        f"/api/v1/projects/proj_oyshia_2025/reviews/{diag2_rev['review_id']}/audit"
    )
    assert audit_res.status_code == 200
    assert len(audit_res.json()) == 1
    assert audit_res.json()[0]["raw_ocr_text"] == "Mss wrist pain (?trauma)"


def test_project_autocoder_cache_reuses_embeddings() -> None:
    from app.services.autocoder import get_project_autocoder

    class CountingEmbedder(DeterministicStubEmbedder):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def embed(self, texts: list[str]) -> np.ndarray:
            self.calls += 1
            return super().embed(texts)

    store = get_project_store()
    project = store.get_project("proj_oyshia_2025")
    assert project is not None
    emb = CountingEmbedder()

    c1 = get_project_autocoder("proj_oyshia_2025", project.variables, embedder=emb)
    c1.code_term("Diagnosis1", "Mss wrist pain (?trauma)")
    calls_after_first = emb.calls

    c2 = get_project_autocoder("proj_oyshia_2025", project.variables, embedder=emb)
    assert c1 is c2
    c2.code_term("Diagnosis1", "HTN")
    assert emb.calls == calls_after_first + 1  # only query embedded, codebook matrix reused!
