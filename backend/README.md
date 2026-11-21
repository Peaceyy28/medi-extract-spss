# Backend — MediExtract SPSS Core Engine

FastAPI + `pyreadstat` + OpenCV + Open-Weight Vision & Semantic Auto-Coder (`BAAI/bge-small-en-v1.5`).

- **Current Branch / Milestones:** `D1` (`feat/d1-spss-scaffold-contracts`) — Core contracts, `pyreadstat` `.sav`/`.sps`/`.xlsx`/`.csv`/`.dta` engine, and synthetic OYSHIA fixtures.
- **Architecture & Contracts:** See [`../docs/shared/01-architecture.md`](../docs/shared/01-architecture.md) and [`../docs/shared/02-api-contracts.md`](../docs/shared/02-api-contracts.md).

## Local Setup (`uv` + Python 3.12+)

```powershell
cd backend
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -e ".[dev]"
```

## Generate Synthetic Non-PII Fixtures

```powershell
.\.venv\Scripts\python.exe -m scripts.generate_synthetic_fixtures
```

## Run Backend API Server

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

## Run Tests

```powershell
.\.venv\Scripts\pytest.exe -v
```
