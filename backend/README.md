# Marg Backend (Ingestion + Query API)

FastAPI service that receives SDK telemetry, validates and stores it in PostgreSQL, and serves it back through project‑scoped query endpoints. Full API reference: [`docs/api.md`](../docs/api.md). Data model: [`docs/data-model.md`](../docs/data-model.md).

## Layout

```
marg_backend/
  main.py        app factory, error handlers
  config.py      env-driven settings
  routes.py      health / ingestion / query / admin routers
  auth.py        API-key hashing + auth dependencies + project check
  ingestion.py   validation, idempotent persistence, run state machine
  queries.py     query service (always project-scoped)
  registry.py    project / agent / API-key registration
  models.py      SQLAlchemy models + indexes
  schemas.py     Pydantic request/response models
  seed.py        SYNTHETIC demo data
migrations/      Alembic
tests/
```

## Run locally (SQLite, no Docker)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

$env:MARG_DATABASE_URL = "sqlite:///./marg_dev.db"
$env:MARG_SECRET_KEY   = "<random string>"      # required outside development, >= 32 chars
$env:MARG_ADMIN_TOKEN  = "<random token>"
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m marg_backend.seed          # optional synthetic data; prints a demo key once
.\.venv\Scripts\uvicorn.exe marg_backend.main:app_factory --factory --port 8000
```

## Run with PostgreSQL (Docker)

```bash
cp .env.example .env   # then set real POSTGRES_PASSWORD, MARG_SECRET_KEY, MARG_ADMIN_TOKEN
docker compose -f infra/docker-compose.yml --env-file .env up --build
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest --cov=marg_backend --cov-report=term-missing
```

## Configuration

See `.env.example`. Notable: `MARG_MAX_PAYLOAD_BYTES`, `MARG_MAX_BATCH_SIZE`, `MARG_AUTO_REGISTER_AGENTS`, `MARG_AUTO_CREATE_TABLES` (dev only).
