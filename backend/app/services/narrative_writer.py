"""Stage 3: Local Open-Weight Narrative Writer (Llama-3.2-3B-Instruct) for Validation Reports."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from openai import OpenAI

from app.config import Settings, get_settings
from app.schemas import ValidationReportResponse
from app.services.vision_htr import VisionProvider, build_vision_provider_chain

_LOGGER = logging.getLogger(__name__)


def _fallback_narrative(report: ValidationReportResponse, project_name: str) -> str:
    s = report.summary
    d = report.demographics_audit
    top_dx = (
        ", ".join(f"{item.label} ({item.pct}%)" for item in report.clinical_audit.top_diagnoses[:3])
        or "none recorded"
    )
    whipple_txt = (
        f"Whipple digit-preference index is {d.digit_preference_whipple_index}."
        if d.digit_preference_whipple_index is not None
        else "Whipple digit-preference index was not applicable."
    )
    return (
        f"In {project_name}, {s.total_cases_evaluated} encounters were audited with a "
        f"{s.clean_rate_pct}% clean-data rate ({s.clean_cases_count} clean, {s.flagged_cases_count} flagged, "
        f"{s.duplicates_prevented} duplicate prevented). Top morbidities include {top_dx}, "
        f"with a mean of {report.clinical_audit.mean_drugs_per_encounter} prescribed drugs per encounter. "
        f"{whipple_txt} {len(report.clinical_audit.contradictions_found)} rule or prescription flags "
        f"require supervisor review."
    )


def _strip_preamble(text: str) -> str:
    """Drop conversational intro lines like 'Here is a summary:' when findings follow."""
    stripped = text.strip()
    lines = stripped.splitlines()
    if len(lines) > 1:
        first_lower = lines[0].strip().lower()
        if first_lower.startswith("here is") or first_lower.startswith("here's"):
            remainder = "\n".join(lines[1:]).strip()
            if remainder:
                return remainder
    return stripped


def _default_narrative_client(provider: VisionProvider) -> Any:
    return OpenAI(
        base_url=provider.base_url,
        api_key=provider.api_key,
        timeout=120.0 if provider.name == "ollama" else 60.0,
        max_retries=1,
    )


def generate_report_narrative(
    report: ValidationReportResponse,
    project_name: str,
    settings: Settings | None = None,
    client_factory: Callable[[VisionProvider], Any] | None = None,
) -> tuple[str, str]:
    """Generate a concise plain-English M&E summary using Llama-3.2-3B (with deterministic fallback)."""
    cfg = settings or get_settings()
    chain = build_vision_provider_chain(cfg)
    factory = client_factory or _default_narrative_client

    compact_facts = {
        "project": project_name,
        "summary": report.summary.model_dump(),
        "demographics": report.demographics_audit.model_dump(),
        "top_diagnoses": [d.model_dump() for d in report.clinical_audit.top_diagnoses[:5]],
        "mean_drugs_per_encounter": report.clinical_audit.mean_drugs_per_encounter,
        "contradictions_sample": [c.model_dump() for c in report.clinical_audit.contradictions_found[:5]],
        "top_facilities": [f.model_dump() for f in report.facility_ranking[:5]],
    }
    compact_json = json.dumps(compact_facts, separators=(",", ":"), default=str)

    for provider in chain:
        if provider.name == "stub":
            return _fallback_narrative(report, project_name), "stub"

        model_name = (
            cfg.ollama_narrative_model.strip()
            if provider.name == "ollama"
            else provider.model
        )
        try:
            client = factory(provider)
            resp = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a concise public-health Monitoring & Evaluation analyst. "
                            "Write 3 to 4 plain-English sentences summarizing ONLY the numbers in the JSON report. "
                            "Mention clean rate, leading morbidities, age/Whipple findings, and any VR-02 or VR-04-RX issues. "
                            "Never invent numbers or bullet lists. "
                            "Start directly with the findings — no preamble such as 'Here is a summary'."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"REPORT_JSON:{compact_json}",
                    },
                ],
                temperature=0.2,
                max_tokens=220,
            )
            text = _strip_preamble(resp.choices[0].message.content or "")
            if text:
                return text, f"{provider.name}:{model_name}"
        except Exception as exc:
            _LOGGER.warning(
                "Narrative generation failed on '%s' (%s); trying fallback.",
                provider.name,
                type(exc).__name__,
            )

    return _fallback_narrative(report, project_name), "fallback-template"
