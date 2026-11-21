"""Semantic Medical Auto-Coder: O(1) normalized synonym lookup + BGE 384-d cosine matching."""

from __future__ import annotations

import hashlib
import json
import re
import threading
import zlib
from typing import Protocol

import numpy as np
from rapidfuzz import fuzz

from app.config import Settings, get_settings
from app.schemas import AutoCodeResponse, SuggestedCandidate, VariableSchema

_PAREN_RE = re.compile(r"\(([^)]*)\)")
_DOSAGE_PREFIX_RE = re.compile(
    r"^(?:tab|tabs|tablet|cap|caps|capsule|syr|syrup|inj|iv|im|oint|cream|drops)\.?\s+",
    re.IGNORECASE,
)
_DOSAGE_TOKEN_RE = re.compile(
    r"\b(?:\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|iu|%)|od|bd|tds|qid|qds|prn|stat|dly|daily|nocte|x\d+d?)\b",
    re.IGNORECASE,
)
_PUNCT_RE = re.compile(r"[^a-z0-9/\s]+")
_STOPWORDS = {"of", "the", "and", "with", "in", "on", "to", "for", "a", "an", "or"}
_LOW_WEIGHT_CLINICAL = {"pain", "acute", "chronic", "mild", "severe", "suspected", "trauma", "history"}

CLINICAL_SYNONYMS: dict[str, str] = {
    # Diagnoses
    "htn": "hypertention",
    "high bp": "hypertention",
    "hypertension": "hypertention",
    "elevated bp": "hypertention",
    "mp": "malaria parasite",
    "mp+": "malaria parasite",
    "mp++": "malaria parasite",
    "malaria parasite": "malaria parasite",
    "acute malaria": "malaria",
    "malaria": "malaria",
    "pud": "pud / dyspepsia",
    "dyspepsia": "pud / dyspepsia",
    "peptic ulcer": "pud / dyspepsia",
    "dm": "diabetes",
    "t2dm": "diabetes",
    "diabetes mellitus": "diabetes",
    "anc": "pregnancy / anc",
    "antenatal": "pregnancy / anc",
    "pregnancy": "pregnancy / anc",
    "urti": "upper respiratory tract infection",
    "uti": "urinary tract infection",
    "pid": "pelvic inflammatory disease",
    "pph": "postpartum haemorrhage",
    "fibroid": "fibroid",
    "oa": "osteoarthritis",
    "gerd": "gastroesophageal reflux disease",
    "bph": "benign prostatic hyperplasia",
    # Treatments
    "act": "artemether-lumefantrine (act)",
    "coartem": "artemether-lumefantrine (act)",
    "lonart": "artemether-lumefantrine (act)",
    "artemether": "artemether-lumefantrine (act)",
    "pcm": "paracetamol",
    "panadol": "paracetamol",
    "paracetamol": "paracetamol",
    "amlod": "amlodipine",
    "amlodipine": "amlodipine",
    "lisino": "lisinopril",
    "lisinopril": "lisinopril",
    "omep": "omeprazole",
    "omeprazole": "omeprazole",
    "metform": "metformin",
    "metformin": "metformin",
    "glucophage": "metformin",
    "amoxil": "amoxicillin",
    "amoxicillin": "amoxicillin",
    "augmentin": "amoxicillin-clavulanate",
    "flagyl": "metronidazole",
    "metronidazole": "metronidazole",
    "cipro": "ciprofloxacin",
    "ciprofloxacin": "ciprofloxacin",
    "ors": "oral rehydration salts (ors)",
    # Investigations
    "rdt": "malaria rdt",
    "mrdt": "malaria rdt",
    "fbc": "full blood count (fbc)",
    "pcv": "packed cell volume (pcv)",
    "fbs": "fasting blood glucose",
    "fbg": "fasting blood glucose",
    "rbs": "random blood glucose",
    "rbg": "random blood glucose",
    "pt": "pregnancy test (pt)",
    "ecg": "electrocardiogram (ecg)",
}


def normalize_clinical_text(text: str) -> str:
    """Normalize clinical shorthand, dosages, punctuation, and whitespace."""
    cleaned = text.strip().lower()
    cleaned = cleaned.replace("?", " ")
    cleaned = _DOSAGE_PREFIX_RE.sub("", cleaned)
    cleaned = _DOSAGE_TOKEN_RE.sub(" ", cleaned)
    cleaned = _PUNCT_RE.sub(" ", cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned


class Embedder(Protocol):
    """Protocol for 384-d L2-normalised text embedders."""

    def embed(self, texts: list[str]) -> np.ndarray:
        """Embed strings into an L2-normalised (N, D) float32 array."""
        ...


class FastEmbedEmbedder:
    """Lazy-loading local ONNX embedder via fastembed (BAAI/bge-small-en-v1.5)."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-en-v1.5",
        cache_dir: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.cache_dir = cache_dir
        self._model = None
        self._lock = threading.Lock()

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        with self._lock:
            if self._model is None:
                from fastembed import TextEmbedding

                kwargs: dict[str, object] = {"threads": 4}
                if self.cache_dir:
                    kwargs["cache_dir"] = self.cache_dir
                self._model = TextEmbedding(self.model_name, **kwargs)  # type: ignore[arg-type]

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 384), dtype=np.float32)
        self._ensure_model()
        raw = list(self._model.embed(texts))  # type: ignore[union-attr]
        arr = np.array(raw, dtype=np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        return arr / np.maximum(norms, 1e-12)


class HFApiEmbedder:
    """Hugging Face Inference feature-extraction fallback when local ONNX is skipped."""

    def __init__(
        self,
        token: str,
        model_name: str = "BAAI/bge-small-en-v1.5",
        base_url: str = "https://api-inference.huggingface.co/pipeline/feature-extraction",
    ) -> None:
        self.token = token
        self.model_name = model_name
        self.endpoint = f"{base_url.rstrip('/')}/{model_name}"

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 384), dtype=np.float32)

        import httpx

        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                self.endpoint,
                headers=headers,
                json={"inputs": texts, "options": {"wait_for_model": True}},
            )
            resp.raise_for_status()
            data = resp.json()

        arr = np.array(data, dtype=np.float32)
        if arr.ndim == 3:
            arr = arr.mean(axis=1)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        return arr / np.maximum(norms, 1e-12)


class DeterministicStubEmbedder:
    """Zero-download deterministic 384-d token + char-ngram projection for offline tests."""

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dim), dtype=np.float32)

        mat = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row_idx, raw in enumerate(texts):
            norm = normalize_clinical_text(raw)
            tokens = [t for t in norm.split() if t not in _STOPWORDS]
            for tok in tokens:
                weight = 0.65 if tok in _LOW_WEIGHT_CLINICAL else (2.4 if len(tok) >= 4 else 1.5)
                bucket = zlib.crc32(f"w:{tok}".encode("utf-8")) % self.dim
                mat[row_idx, bucket] += weight
                for prefix_len in (3, 4):
                    if len(tok) >= prefix_len:
                        for j in range(len(tok) - prefix_len + 1):
                            gram = tok[j : j + prefix_len]
                            gb = zlib.crc32(f"g:{gram}".encode("utf-8")) % self.dim
                            mat[row_idx, gb] += 0.65

        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        return mat / np.maximum(norms, 1e-12)


_EMBEDDER_LOCK = threading.Lock()
_EMBEDDER_INSTANCE: Embedder | None = None


def get_embedder(settings: Settings | None = None) -> Embedder:
    """Return configured singleton Embedder without triggering downloads unnecessarily."""
    global _EMBEDDER_INSTANCE
    with _EMBEDDER_LOCK:
        if _EMBEDDER_INSTANCE is not None:
            return _EMBEDDER_INSTANCE

        cfg = settings or get_settings()
        backend = cfg.embedding_backend.strip().lower()
        if backend == "stub":
            _EMBEDDER_INSTANCE = DeterministicStubEmbedder()
        elif backend == "hf_api":
            _EMBEDDER_INSTANCE = HFApiEmbedder(token=cfg.hf_token, model_name=cfg.embedding_model)
        else:
            _EMBEDDER_INSTANCE = FastEmbedEmbedder(
                model_name=cfg.embedding_model,
                cache_dir=cfg.resolved_fastembed_cache_path(),
            )
        return _EMBEDDER_INSTANCE


def reset_embedder_cache() -> None:
    """Clear cached embedder singleton (used in tests)."""
    global _EMBEDDER_INSTANCE
    with _EMBEDDER_LOCK:
        _EMBEDDER_INSTANCE = None


class MedicalAutoCoder:
    """Hybrid O(1) dictionary + semantic embedding auto-coder for SPSS codebooks."""

    def __init__(
        self,
        variables: list[VariableSchema],
        embedder: Embedder | None = None,
    ) -> None:
        self._embedder = embedder or get_embedder()
        self._var_map: dict[str, VariableSchema] = {v.name: v for v in variables}
        self._norm_indexes: dict[str, dict[str, tuple[float, str]]] = {}
        self._label_lists: dict[str, list[tuple[float, str, str]]] = {}
        self._matrix_cache: dict[str, np.ndarray] = {}
        self._matrix_lock = threading.Lock()

        for var in variables:
            if not var.value_labels:
                continue
            norm_map: dict[str, tuple[float, str]] = {}
            entries: list[tuple[float, str, str]] = []
            for code_str, label in var.value_labels.items():
                try:
                    code_num = float(code_str)
                except (TypeError, ValueError):
                    continue
                norm_lbl = normalize_clinical_text(label)
                norm_map[norm_lbl] = (code_num, label)
                entries.append((code_num, label, norm_lbl))
            if entries:
                self._norm_indexes[var.name] = norm_map
                self._label_lists[var.name] = entries

    def _get_matrix(self, variable_name: str) -> np.ndarray:
        with self._matrix_lock:
            cached = self._matrix_cache.get(variable_name)
            if cached is not None:
                return cached
            entries = self._label_lists[variable_name]
            texts = [lbl for _, lbl, _ in entries]
            mat = self._embedder.embed(texts)
            self._matrix_cache[variable_name] = mat
            return mat

    def code_term(
        self,
        variable_name: str,
        raw_text: str,
        top_k: int = 3,
        quarantine_threshold: float = 0.50,
    ) -> AutoCodeResponse:
        """Map a clinical phrase or abbreviation onto a variable's SPSS numeric codebook."""
        norm = normalize_clinical_text(raw_text)
        entries = self._label_lists.get(variable_name)
        norm_map = self._norm_indexes.get(variable_name)

        if not entries or not norm_map or not norm:
            return AutoCodeResponse(
                variable_name=variable_name,
                raw_text=raw_text,
                normalized_text=norm,
                match_tier="QUARANTINED",
                matched_code=None,
                matched_label=None,
                similarity=0.0,
                quarantined=True,
                candidates=[],
            )

        # Tier 1a: True O(1) exact normalized match (zero embedding or fuzzy work)
        if norm in norm_map:
            exact_code, exact_label = norm_map[norm]
            return AutoCodeResponse(
                variable_name=variable_name,
                raw_text=raw_text,
                normalized_text=norm,
                match_tier="EXACT",
                matched_code=exact_code,
                matched_label=exact_label,
                similarity=1.0,
                quarantined=False,
                candidates=[SuggestedCandidate(code=exact_code, label=exact_label, similarity=1.0)],
            )

        # Tier 1b: True O(1) clinical synonym map lookup (zero embedding or fuzzy work)
        syn_target = CLINICAL_SYNONYMS.get(norm)
        if syn_target and syn_target in norm_map:
            syn_code, syn_label = norm_map[syn_target]
            return AutoCodeResponse(
                variable_name=variable_name,
                raw_text=raw_text,
                normalized_text=norm,
                match_tier="SYNONYM",
                matched_code=syn_code,
                matched_label=syn_label,
                similarity=0.96,
                quarantined=False,
                candidates=[SuggestedCandidate(code=syn_code, label=syn_label, similarity=0.96)],
            )

        # Tier 2: Semantic embedding + lexical WRatio scoring for unseen clinical variants
        matrix = self._get_matrix(variable_name)
        q_vec = self._embedder.embed([norm])[0]
        cos_scores = matrix @ q_vec

        scored: list[tuple[float, float, str]] = []
        for idx, (code_num, orig_label, norm_lbl) in enumerate(entries):
            cos_sim = float(max(0.0, min(1.0, cos_scores[idx])))
            lex_sim = fuzz.WRatio(norm, norm_lbl) / 100.0
            blended = min(1.0, round(0.70 * cos_sim + 0.30 * lex_sim, 4))
            scored.append((blended, code_num, orig_label))

        scored.sort(key=lambda item: item[0], reverse=True)
        top_candidates = [
            SuggestedCandidate(code=c, label=lbl, similarity=sim)
            for sim, c, lbl in scored[:top_k]
        ]

        best_sim, best_code, best_label = scored[0]
        if best_sim < quarantine_threshold:
            return AutoCodeResponse(
                variable_name=variable_name,
                raw_text=raw_text,
                normalized_text=norm,
                match_tier="QUARANTINED",
                matched_code=None,
                matched_label=None,
                similarity=best_sim,
                quarantined=True,
                candidates=top_candidates,
            )

        return AutoCodeResponse(
            variable_name=variable_name,
            raw_text=raw_text,
            normalized_text=norm,
            match_tier="VECTOR",
            matched_code=best_code,
            matched_label=best_label,
            similarity=best_sim,
            quarantined=False,
            candidates=top_candidates,
        )


_AUTOCODER_CACHE_LOCK = threading.Lock()
_AUTOCODER_CACHE: dict[tuple[str, str, int], MedicalAutoCoder] = {}


def _schema_signature(variables: list[VariableSchema]) -> str:
    payload = [
        (v.name, sorted(v.value_labels.items()))
        for v in variables
        if v.value_labels
    ]
    return hashlib.sha256(json.dumps(payload).encode("utf-8")).hexdigest()[:16]


def get_project_autocoder(
    project_id: str,
    variables: list[VariableSchema],
    embedder: Embedder | None = None,
) -> MedicalAutoCoder:
    """Return cached MedicalAutoCoder holding pre-embedded codebook matrices."""
    emb = embedder or get_embedder()
    key = (project_id, _schema_signature(variables), id(emb))
    with _AUTOCODER_CACHE_LOCK:
        cached = _AUTOCODER_CACHE.get(key)
        if cached is not None:
            return cached
        coder = MedicalAutoCoder(variables=variables, embedder=emb)
        _AUTOCODER_CACHE[key] = coder
        return coder


def reset_autocoder_cache() -> None:
    """Clear cached project MedicalAutoCoder instances (used in tests)."""
    with _AUTOCODER_CACHE_LOCK:
        _AUTOCODER_CACHE.clear()
