"""Non-blocking startup warm-up for local Ollama vision and narrative models."""

from __future__ import annotations

import logging
import threading
from typing import Any

import httpx

from app.config import Settings, get_settings

_LOGGER = logging.getLogger(__name__)


def _ollama_enabled(settings: Settings) -> bool:
    chain = [
        p.strip().lower()
        for p in settings.vision_provider_chain.split(",")
        if p.strip()
    ]
    return "ollama" in chain


def _resolve_ollama_root(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3].rstrip("/")
    return base


def _post_ollama_generate(
    url: str, payload: dict[str, Any], timeout: float = 180.0
) -> None:
    resp = httpx.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()


def warm_up_local_models(settings: Settings | None = None) -> list[str]:
    """Preload configured Ollama models into VRAM with keep-alive so first forms don't stall."""
    cfg = settings or get_settings()
    if not _ollama_enabled(cfg):
        return []

    root = _resolve_ollama_root(cfg.ollama_base_url)
    if not root:
        return []

    url = f"{root}/api/generate"
    seen: set[str] = set()
    models: list[str] = []
    for candidate in (cfg.ollama_vision_model, cfg.ollama_narrative_model):
        name = candidate.strip()
        if name and name not in seen:
            seen.add(name)
            models.append(name)

    loaded: list[str] = []
    for model_name in models:
        try:
            _post_ollama_generate(
                url,
                {"model": model_name, "keep_alive": cfg.ollama_keep_alive},
                timeout=180.0,
            )
            loaded.append(model_name)
            _LOGGER.info("Preloaded Ollama model '%s' (keep_alive=%s).", model_name, cfg.ollama_keep_alive)
        except Exception as exc:
            _LOGGER.warning(
                "Ollama warm-up skipped for '%s' (%s).",
                model_name,
                type(exc).__name__,
            )
    return loaded


def start_background_warmup(
    settings: Settings | None = None,
) -> threading.Thread | None:
    """Spawn a daemon thread to warm up Ollama models without blocking FastAPI startup."""
    cfg = settings or get_settings()
    if not cfg.ollama_warmup_on_startup or not _ollama_enabled(cfg):
        return None
    thread = threading.Thread(
        target=warm_up_local_models,
        args=(cfg,),
        name="ollama-warmup",
        daemon=True,
    )
    thread.start()
    return thread
