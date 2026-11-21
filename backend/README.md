# Backend — MediExtract SPSS Core Engine

FastAPI + `pyreadstat` + OpenCV + Open-Weight Vision (`Qwen2.5-VL` / `Llama-3.2`) & Semantic Auto-Coder (`BAAI/bge-small-en-v1.5`).

- **Status:** `D1–D5` complete and merged into `main` (PRs `#7`, `#8`, `#9`): `pyreadstat` SPSS engine, SQLite Multi-Project Workspaces, `.sav`/PDF Auto-Schema, Multi-Clerk `.sav` Merger, Auto-Recode, OpenCV/OMR/Watchdog Scanner, Open-Weight Vision HTR Provider Chain (`ollama,huggingface,groq`), Semantic Medical Auto-Coder (`BAAI/bge-small-en-v1.5`), Stage 3 Narrative Writer (`llama3.2:3b`), Startup Warm-Up (`model_warmup.py`), and $O(N)$ Validation & `VR-04-RX` PDF/Excel Analyst Reports.
- **Architecture & Contracts:** See [`../docs/shared/01-architecture.md`](../docs/shared/01-architecture.md) and [`../docs/shared/02-api-contracts.md`](../docs/shared/02-api-contracts.md).

## Local Setup (`uv` + Python 3.12+)

```powershell
cd backend
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -e ".[dev]"
copy .env.example .env
```

## Local Open-Weight Models (`C:\Users\USER\Documents\LLMs`)

Portable Ollama + model weights live outside Git in `C:\Users\USER\Documents\LLMs` (`OLLAMA_MODELS`, `OLLAMA_KEEP_ALIVE=30m`, `FASTEMBED_CACHE_PATH`):
- **Stage 1 (Vision HTR):** `qwen2.5vl:3b` (Ollama local GPU; cold/first `24.16s`, warm `14.13s` on Quadro RTX 4000 Max-Q)
- **Stage 2 (Medical Auto-Coder):** `BAAI/bge-small-en-v1.5` (FastEmbed ONNX; `2,236 ms` codebook warmup, `4.7–5.9 ms` per term)
- **Stage 3 (Report Narrative):** `llama3.2:3b` (Ollama local GPU; `12.21s` with compact JSON prompting & preamble stripping)
- **Startup Warm-Up:** FastAPI automatically preloads Ollama models on a non-blocking daemon thread using `MEDIEXTRACT_OLLAMA_KEEP_ALIVE=30m` (`MEDIEXTRACT_OLLAMA_WARMUP_ON_STARTUP=true`), keeping both models resident in VRAM between form scans.

## Verify Live Local Models & Run Tests

```powershell
# Automated unit & integration suite (0 MB downloaded, runs with deterministic stubs)
.\.venv\Scripts\pytest.exe -v

# Live end-to-end verification against real local Ollama GPU + FastEmbed ONNX models
.\.venv\Scripts\python.exe -m scripts.verify_local_models
```

## Two-Terminal Quickstart (Offline Mode)

```powershell
# Terminal 1: Start local Ollama pointed at C:\Users\USER\Documents\LLMs\ollama-models
$env:OLLAMA_MODELS = "C:\Users\USER\Documents\LLMs\ollama-models"
$env:OLLAMA_KEEP_ALIVE = "30m"
C:\Users\USER\Documents\LLMs\ollama\ollama.exe serve

# Terminal 2: Start the FastAPI server
cd backend
.\.venv\Scripts\uvicorn.exe app.main:app --reload --port 8000
```
