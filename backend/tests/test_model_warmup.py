"""Unit tests for Ollama startup warm-up and provider-aware timeout defaults."""

from __future__ import annotations

from typing import Any

import pytest

from app.config import Settings
from app.services import model_warmup
from app.services.vision_htr import VisionProvider, _default_client_factory


def test_warmup_skips_when_chain_is_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fail_if_called(url: str, payload: dict[str, Any], timeout: float = 180.0) -> None:
        calls.append((url, payload))
        raise AssertionError("HTTP post must not run when provider chain excludes ollama")

    monkeypatch.setattr(model_warmup, "_post_ollama_generate", fail_if_called)
    cfg = Settings(vision_provider_chain="stub")
    assert model_warmup.warm_up_local_models(cfg) == []
    assert calls == []
    assert model_warmup.start_background_warmup(cfg) is None


def test_warmup_posts_unique_ollama_models_and_swallows_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[tuple[str, dict[str, Any], float]] = []

    def fake_post(url: str, payload: dict[str, Any], timeout: float = 180.0) -> None:
        recorded.append((url, payload, timeout))
        if payload["model"] == "llama3.2:3b":
            raise RuntimeError("simulated transient connection refused")

    monkeypatch.setattr(model_warmup, "_post_ollama_generate", fake_post)
    cfg = Settings(
        vision_provider_chain="ollama",
        ollama_base_url="http://localhost:11434/v1/",
        ollama_vision_model="qwen2.5vl:3b",
        ollama_narrative_model="llama3.2:3b",
        ollama_keep_alive="30m",
    )

    loaded = model_warmup.warm_up_local_models(cfg)
    assert loaded == ["qwen2.5vl:3b"]
    assert recorded == [
        ("http://localhost:11434/api/generate", {"model": "qwen2.5vl:3b", "keep_alive": "30m"}, 180.0),
        ("http://localhost:11434/api/generate", {"model": "llama3.2:3b", "keep_alive": "30m"}, 180.0),
    ]


def test_vision_client_uses_provider_aware_timeouts() -> None:
    ollama_client = _default_client_factory(
        VisionProvider(name="ollama", base_url="http://localhost:11434/v1", api_key="ollama", model="qwen2.5vl:3b")
    )
    groq_client = _default_client_factory(
        VisionProvider(name="groq", base_url="https://api.groq.com/openai/v1", api_key="k", model="m")
    )
    assert ollama_client.timeout == 180.0
    assert groq_client.timeout == 60.0
    assert ollama_client.max_retries == 1
