# Backend — MediExtract SPSS Core Engine

FastAPI + `pyreadstat` + OpenCV + Open-Weight Vision (`Qwen2.5-VL` / `Llama-3.2`) & Semantic Auto-Coder (`BAAI/bge-small-en-v1.5`).

- **Current Branch / Milestones:** `D1–D5` (`feat/d5-validation-analyst-reports`) — Complete backend (`D1–D5`): `pyreadstat` SPSS engine, SQLite Multi-Project Workspaces, `.sav`/PDF Auto-Schema, Multi-Clerk `.sav` Merger, Auto-Recode, OpenCV/OMR/Watchdog Scanner, Open-Weight Vision HTR Provider Chain (`ollama,huggingface,groq`), Semantic Medical Auto-Coder (`BAAI/bge-small-en-v1.5`), Stage 3 Narrative Writer (`llama3.2:3b`), and $O(N)$ Validation & `VR-04-RX` PDF/Excel Analyst Reports.
- **Architecture & Contracts:** See [`../docs/shared/01-architecture.md`](../docs/shared/01-architecture.md) and [`../docs/shared/02-api-contracts.md`](../docs/shared/02-api-contracts.md).

## Local Setup (`uv` + Python 3.12+)

```powershell
cd backend
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -e ".[dev]"
copy .env.example .env
```

## Local Open-Weight Models (`C:\Users\USER\Documents\LLMs`)

Portable Ollama + model weights live outside Git in `C:\Users\USER\Documents\LLMs` (`OLLAMA_MODELS` & `FASTEMBED_CACHE_PATH`):
- **Stage 1 (Vision HTR):** `qwen2.5vl:3b` (Ollama local GPU)
- **Stage 2 (Medical Auto-Coder):** `BAAI/bge-small-en-v1.5` (FastEmbed ONNX)
- **Stage 3 (Report Narrative):** `llama3.2:3b` (Ollama local GPU)

## Verify Live Local Models & Run Tests

```powershell
# Automated unit & integration suite (0 MB downloaded, runs with deterministic stubs)
.\.venv\Scripts\pytest.exe -v

# Live end-to-end verification against real local Ollama GPU + FastEmbed ONNX models
.\.venv\Scripts\python.exe -m scripts.verify_local_models
```

## Run Backend API Server

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```
