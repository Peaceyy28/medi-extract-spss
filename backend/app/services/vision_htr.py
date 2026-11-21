"""Open-weight Vision HTR provider chain (Ollama / Hugging Face / Groq) & confidence math."""

from __future__ import annotations

import base64
import json
import logging
import math
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
from openai import OpenAI

from app.config import Settings, get_settings
from app.schemas import ValidationStatus

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class VisionProvider:
    """Configured open-weight multimodal inference provider."""

    name: str
    base_url: str
    api_key: str
    model: str


@dataclass(frozen=True)
class ExtractedFieldPrediction:
    """Single field prediction returned by Vision HTR."""

    raw_text: str
    ocr_confidence: float


@dataclass(frozen=True)
class PageHTROutput:
    """Full-page structured extraction result with provider provenance."""

    provider_used: str
    model_used: str
    fields: dict[str, ExtractedFieldPrediction]


def compute_ocr_confidence_from_logprobs(logprobs: list[float]) -> float:
    """Compute geometric mean probability exp(mean(log p_j)) clamped to [0.0, 1.0]."""
    if not logprobs:
        return 0.0
    mean_lp = float(np.mean(np.asarray(logprobs, dtype=np.float64)))
    prob = math.exp(mean_lp)
    return round(max(0.0, min(1.0, prob)), 4)


def compute_total_confidence(
    ocr_confidence: float, code_similarity: float | None = None
) -> float:
    """Combine OCR confidence and semantic code similarity via min(Conf_OCR, Sim_code)."""
    if code_similarity is None:
        val = ocr_confidence
    else:
        val = min(ocr_confidence, code_similarity)
    return round(max(0.0, min(1.0, val)), 4)


def evaluate_confidence_gate(
    total_confidence: float, threshold: float = 0.90
) -> ValidationStatus:
    """Route fields >= threshold to AUTO_VERIFIED and < threshold to NEEDS_REVIEW."""
    return (
        ValidationStatus.AUTO_VERIFIED
        if total_confidence >= threshold
        else ValidationStatus.NEEDS_REVIEW
    )


def build_vision_provider_chain(settings: Settings) -> list[VisionProvider]:
    """Build ordered Vision HTR provider chain, skipping unconfigured providers."""
    names = [
        p.strip().lower()
        for p in settings.vision_provider_chain.split(",")
        if p.strip()
    ]
    chain: list[VisionProvider] = []
    for name in names:
        if name == "ollama":
            url = settings.ollama_base_url.strip()
            if url:
                chain.append(
                    VisionProvider(
                        name="ollama",
                        base_url=url,
                        api_key="ollama",
                        model=settings.ollama_vision_model.strip() or "qwen2.5vl:3b",
                    )
                )
        elif name == "huggingface":
            token = settings.hf_token.strip()
            if token:
                chain.append(
                    VisionProvider(
                        name="huggingface",
                        base_url=settings.hf_base_url.strip(),
                        api_key=token,
                        model=settings.hf_vision_model.strip()
                        or "Qwen/Qwen2.5-VL-7B-Instruct",
                    )
                )
        elif name == "groq":
            key = settings.groq_api_key.strip()
            if key:
                chain.append(
                    VisionProvider(
                        name="groq",
                        base_url=settings.groq_base_url.strip(),
                        api_key=key,
                        model=settings.groq_vision_model.strip()
                        or "meta-llama/llama-4-scout-17b-16e-instruct",
                    )
                )
        elif name == "stub":
            chain.append(
                VisionProvider(
                    name="stub",
                    base_url="stub://local",
                    api_key="stub",
                    model="stub-vision-v1",
                )
            )
    return chain


def _stub_extract_page(page_number: int) -> PageHTROutput:
    """Deterministic zero-download HTR stub simulating real high & low confidence fields."""
    fields = {
        "Year": ExtractedFieldPrediction(raw_text="2025", ocr_confidence=0.99),
        "Month": ExtractedFieldPrediction(raw_text="10", ocr_confidence=0.98),
        "FacilityPHC": ExtractedFieldPrediction(
            raw_text="General Hospital, Igboho", ocr_confidence=0.96
        ),
        "LGA": ExtractedFieldPrediction(raw_text="26", ocr_confidence=0.97),
        "OYSHIA_ID": ExtractedFieldPrediction(
            raw_text=f"SYN-OY-D4{page_number:03d}", ocr_confidence=0.95
        ),
        "Name": ExtractedFieldPrediction(
            raw_text=f"Synthetic Enrollee D4-{page_number:02d}", ocr_confidence=0.94
        ),
        "Age": ExtractedFieldPrediction(raw_text="48", ocr_confidence=0.97),
        "Phone_contact": ExtractedFieldPrediction(
            raw_text=f"0800-004-{page_number:04d}", ocr_confidence=0.95
        ),
        "Diagnosis1": ExtractedFieldPrediction(raw_text="HTN", ocr_confidence=0.95),
        # Intentionally low-confidence handwriting sample routed to Guided Review Queue (<0.90)
        "Diagnosis2": ExtractedFieldPrediction(
            raw_text="Mss wrist pain (?trauma)", ocr_confidence=0.68
        ),
        "Treatment1": ExtractedFieldPrediction(
            raw_text="Tab Amlod 5mg dly", ocr_confidence=0.94
        ),
    }
    return PageHTROutput(
        provider_used="stub",
        model_used="stub-vision-v1",
        fields=fields,
    )


def _extract_json_dict(raw_text: str) -> dict[str, Any]:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("Vision model response JSON must be an object")
    return parsed


def _default_client_factory(provider: VisionProvider) -> Any:
    return OpenAI(
        base_url=provider.base_url,
        api_key=provider.api_key,
        timeout=30.0,
    )


class VisionHTRClient:
    """Multimodal HTR client with ordered provider failover and logprob scoring."""

    def __init__(
        self,
        settings: Settings | None = None,
        client_factory: Callable[[VisionProvider], Any] | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client_factory = client_factory or _default_client_factory
        self._disabled_providers: set[str] = set()

    def extract_page(
        self,
        image_bytes: bytes,
        target_fields: list[str],
        page_number: int = 1,
    ) -> PageHTROutput:
        """Extract clinical form fields from a page scan across the configured provider chain."""
        chain = build_vision_provider_chain(self._settings)
        if not chain:
            raise RuntimeError(
                "No Vision HTR providers configured. Enable Ollama locally or set HF_TOKEN / GROQ_API_KEY."
            )

        last_error: Exception | None = None
        for provider in chain:
            if provider.name in self._disabled_providers:
                continue

            if provider.name == "stub":
                return _stub_extract_page(page_number)

            try:
                return self._call_openai_vision(provider, image_bytes, target_fields)
            except Exception as exc:
                status_code = getattr(exc, "status_code", None)
                if status_code in {401, 403}:
                    self._disabled_providers.add(provider.name)
                    _LOGGER.warning(
                        "Vision provider '%s' rejected credentials (HTTP %s); disabled for session.",
                        provider.name,
                        status_code,
                    )
                else:
                    _LOGGER.warning(
                        "Vision provider '%s' failed (%s); failing over.",
                        provider.name,
                        type(exc).__name__,
                    )
                last_error = exc

        raise RuntimeError(
            f"All Vision HTR providers in chain failed: {last_error}"
        ) from last_error

    def _call_openai_vision(
        self,
        provider: VisionProvider,
        image_bytes: bytes,
        target_fields: list[str],
    ) -> PageHTROutput:
        client = self._client_factory(provider)
        b64_img = base64.b64encode(image_bytes).decode("ascii")
        fields_csv = ", ".join(target_fields[:32])
        prompt = (
            "You are a clinical encounter form handwriting transcription engine. "
            "Read the scanned form and return ONLY valid JSON with key 'fields' mapping "
            f"each variable ({fields_csv}) to "
            '{"raw_text": string, "confidence": number between 0 and 1}. '
            "Do not invent values that are blank or illegible."
        )
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/webp;base64,{b64_img}"},
                    },
                ],
            }
        ]

        try:
            resp = client.chat.completions.create(
                model=provider.model,
                messages=messages,
                temperature=0.0,
                max_tokens=1400,
                response_format={"type": "json_object"},
                logprobs=True,
            )
        except Exception as exc:
            msg = str(exc).lower()
            if "response_format" in msg or "logprobs" in msg:
                resp = client.chat.completions.create(
                    model=provider.model,
                    messages=messages,
                    temperature=0.0,
                    max_tokens=1400,
                )
            else:
                raise

        choice = resp.choices[0]
        content = choice.message.content or "{}"
        parsed = _extract_json_dict(content)
        raw_fields = parsed.get("fields", parsed)
        if not isinstance(raw_fields, dict):
            raise ValueError("Missing 'fields' object in Vision HTR response")

        token_logprobs: list[float] = []
        lp_obj = getattr(choice, "logprobs", None)
        if lp_obj and getattr(lp_obj, "content", None):
            for tok in lp_obj.content:
                lp = getattr(tok, "logprob", None)
                if isinstance(lp, (int, float)):
                    token_logprobs.append(float(lp))

        global_lp_conf = (
            compute_ocr_confidence_from_logprobs(token_logprobs)
            if token_logprobs
            else None
        )

        extracted: dict[str, ExtractedFieldPrediction] = {}
        for var_name, val in raw_fields.items():
            if isinstance(val, dict):
                txt = str(val.get("raw_text") or "").strip()
                raw_conf = float(val.get("confidence", 0.85))
            else:
                txt = str(val or "").strip()
                raw_conf = 0.85

            if not txt:
                continue
            conf = (
                min(raw_conf, global_lp_conf)
                if global_lp_conf is not None
                else raw_conf
            )
            extracted[str(var_name)] = ExtractedFieldPrediction(
                raw_text=txt,
                ocr_confidence=round(max(0.0, min(1.0, conf)), 4),
            )

        return PageHTROutput(
            provider_used=provider.name,
            model_used=provider.model,
            fields=extracted,
        )
