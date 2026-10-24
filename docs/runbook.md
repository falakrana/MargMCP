# Marg MCP — Operational Runbook

This runbook provides step-by-step operational instructions for starting, maintaining, troubleshooting, backing up, and recovering Marg MCP in development, staging, and production environments.

---

## 1. Architecture & Port Layout

| Service                      | Internal Port | External Port (Default) | Health Endpoint                             | Purpose                                        |
| ---------------------------- | ------------- | ----------------------- | ------------------------------------------- | ---------------------------------------------- |
| **Frontend Dashboard** | 80            | 80 (or 3001 dev)        | `/` (HTTP 200)                            | React 19 UI & Nginx Reverse Proxy              |
| **Backend API**        | 8000          | 8000                    | `/health/live`, `/healthz`, `/readyz` | Ingestion, Query, Retention, Diagnostic Engine |
| **Prometheus**         | 9090          | 9090                    | `/-/healthy`                              | Timeseries metrics scraper & storage           |
| **Grafana**            | 3000          | 3000                    | `/api/health`                             | Operational metrics visualization              |
| **Tempo**              | 3200 / 4318   | 3200 / 4318             | `/ready`                                  | Distributed OTLP trace store                   |

---

## 2. Startup and Shutdown Procedures

### Production Stack (Docker Compose)

#### Starting the stack

```bash
# 1. Ensure .env is populated with strong production credentials
cp .env.example .env
# Edit .env with secure random tokens (>= 32 chars for secret key, >= 24 chars for tokens)

# 2. Launch production stack in background
docker compose -f infra/docker-compose.prod.yml --env-file .env up -d

# 3. Verify container status
docker compose -f infra/docker-compose.prod.yml ps
```

#### Stopping the stack

```bash
# Graceful stop
docker compose -f infra/docker-compose.prod.yml down

# Graceful stop preserving volumes (data retained)
docker compose -f infra/docker-compose.prod.yml stop
```

#### Viewing logs

```bash
# View backend logs (structured JSON)
docker compose -f infra/docker-compose.prod.yml logs -f backend

# View frontend / reverse-proxy logs
docker compose -f infra/docker-compose.prod.yml logs -f frontend
```

---

## 3. Health & Readiness Verification

### 1. Liveness Probe

Ensures the backend process is running and responding to event-loop cycles:

```bash
curl -f http://localhost:8000/health/live
# or
curl -f http://localhost:8000/healthz

# Expected Response:
# {"status":"alive"} (HTTP 200)
```

### 2. Readiness Probe

Verifies that database connectivity is active and ready to accept traffic:

```bash
curl -f http://localhost:8000/health/ready
# or
curl -f http://localhost:8000/readyz

# Expected Response:
# {"status":"ready"} (HTTP 200)
# (If DB unreachable: HTTP 503 {"code":"not_ready","message":"Service is not ready."})
```

### 3. Prometheus Metrics Endpoint

Scrapes system and telemetry metrics (requires configured Bearer token):

```bash
curl -H "Authorization: Bearer <MARG_METRICS_TOKEN>" http://localhost:8000/metrics

# Expected Response:
# # HELP marg_ingestion_events_total ...
# marg_ingestion_events_total{status="accepted"} 124.0
```

---

## 4. Database Migrations & Schema Management

Marg uses Alembic for declarative schema migrations.

### Applying Pending Migrations

```bash
# From within the backend directory or container:
alembic upgrade head
```

### Checking Current Migration Revision

```bash
alembic current
```

### Creating a New Migration

```bash
alembic revision --autogenerate -m "add_new_column"
```

### Rolling Back the Most Recent Migration

```bash
alembic downgrade -1
```

---

## 5. Backup, Verification, & Restore

Marg includes an automated backup utility in `scripts/backup_db.py`.

### Automated Backup Creation

```bash
# Back up configured database (SQLite or PostgreSQL)
python scripts/backup_db.py backup --output-dir ./backups

# Output:
# [SUCCESS] Database backup created: ./backups/marg_backup_20261022_100000.db
# [VERIFIED] Backup integrity confirmed.
```

### Verifying a Backup File

```bash
python scripts/backup_db.py verify --input-file ./backups/marg_backup_20261022_100000.db
```

### Restoring from Backup

```bash
# For SQLite:
python scripts/backup_db.py restore --input-file ./backups/marg_backup_20261022_100000.db --force

# For PostgreSQL:
pg_restore -h <host> -U <user> -d agentops -c -v ./backups/marg_pg_backup_20261022_100000.dump
```

---

## 6. Retention and Telemetry Lifecycle

Telemetry data is subject to configurable retention periods:

- `MARG_RUN_RETENTION_DAYS` (default: 90 days)
- `MARG_TRACE_RETENTION_DAYS` (default: 30 days)

### Running Retention Purge (Dry Run)

Inspect which runs and events would be pruned without deleting anything:

```bash
python -m marg_backend.retention --dry-run
```

### Executing Live Retention Purge

```bash
python -m marg_backend.retention --apply
```

---

## 7. Incident Troubleshooting Playbooks

### Playbook 1: Backend Returns HTTP 503 `database_unavailable`

- **Symptom:** API returns 503 error; `/readyz` fails.
- **Root Cause:** Database connection pool exhausted or database server offline.
- **Triage Steps:**
  1. Check database server status (`pg_isready` or server connectivity).
  2. Inspect backend logs: `docker compose logs backend | grep -i "Database error"`.
  3. Verify connection pool parameters in `.env`: `DB_POOL_SIZE` (default 10), `MAX_OVERFLOW` (default 20).
  4. Ensure network connectivity between backend container and database host.

### Playbook 2: Ingestion Returns HTTP 429 `rate_limit_exceeded`

- **Symptom:** Monitored agents report 429 errors during high-volume event export.
- **Root Cause:** Ingestion rate limit exceeded (`MARG_RATE_LIMIT_INGEST_PER_MIN`, default: 1200 req/min).
- **Triage Steps:**
  1. The SDK automatically respects `Retry-After` headers and absorbs drops safely without crashing agents.
  2. If legitimate traffic is being throttled, increase the limit in `.env`:
     ```env
     MARG_RATE_LIMIT_INGEST_PER_MIN=3000
     ```
  3. Reload backend configuration.

### Playbook 3: Ingestion Returns HTTP 413 `payload_too_large`

- **Symptom:** SDK batch export fails with HTTP 413.
- **Root Cause:** Event batch size exceeds `MARG_MAX_PAYLOAD_BYTES` (default: 5MB).
- **Triage Steps:**
  1. In SDK configuration, reduce `batch_size` (e.g. from 100 to 50) in `marg_sdk/config.py`.
  2. Verify agents are not capturing large binary payloads or prompts (payload capture should remain off).

### Playbook 4: Tempo Trace Backend Unreachable

- **Symptom:** Backend logs warning `Failed to export OTLP trace`.
- **Root Cause:** Tempo container stopped or network unreachable.
- **Impact:** **Best-effort collection ensures the backend and agent run normally.** Runs and events are safely stored in Postgres/SQLite; only external OTLP trace visualization in Tempo is degraded.
- **Triage Steps:**
  1. Check Tempo container status: `docker compose ps tempo`.
  2. Check Tempo logs: `docker compose logs tempo`.
  3. Restart Tempo: `docker compose restart tempo`.

---

## 8. Rollback Procedure

If a deployed release experiences an unexpected issue:

1. **Container Rollback:**
   ```bash
   # Re-tag or redeploy previous known good image tag
   docker compose -f infra/docker-compose.prod.yml down
   # Checkout previous Git tag / commit
   git checkout <previous-stable-release-tag>
   docker compose -f infra/docker-compose.prod.yml up -d --build
   ```
2. **Database Rollback:**
   - If migrations were applied: `alembic downgrade <target_revision>`.
   - If schema corruption occurred: execute database restore from pre-deployment backup using `python scripts/backup_db.py restore`.
3. **Verify Health:**
   - Confirm `/health/live` returns 200.
   - Confirm `/readyz` returns 200.
   - Inspect `/metrics` for healthy request flows.
