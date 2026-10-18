# Phase 6 — Monitoring Dashboard Documentation

## Overview

The AgentOps Monitoring Dashboard provides a single-pane-of-glass user interface for inspecting AI agent runs, telemetry, traces, and system reliability.

Following the design preference for a **minimalist whitish theme**, the UI uses a clean light palette (`#ffffff` canvas, `#f8fafc` subtle background, `#e2e8f0` crisp borders, `#0f172a` high-contrast typography, and `#4f46e5` indigo accent) with semantic status badges and accessible data visualizations.

---

## Architecture & Technology Stack

- **Framework:** React 19 + TypeScript 5
- **Build Tool:** Vite 8 (fast HMR, sub-second production builds)
- **State Management & Data Fetching:** `@tanstack/react-query` v5 with automatic background refetching and cached queries
- **Routing:** `react-router-dom` v7 with nested routes and URL search parameter synchronization
- **Charts:** `recharts` for responsive SVG run volume, latency, and distribution visualizations
- **Icons:** `lucide-react` for consistent, accessible iconography
- **Styling:** Vanilla CSS design system (`index.css`) built on CSS custom properties (variables) for consistent spacing, colors, borders, and shadows

---

## Pages & Capabilities

### 1. Overview Dashboard (`/`)
- **Key Metrics (KPIs):** Total runs, Success rate %, Avg duration, Total tokens ingested, Active agent count, and Error count.
- **Charts:**
  - 24-hour / recent run volume area chart.
  - Latency bar chart across recent runs.
  - Status breakdown (success, error, running, cancelled).
- **Activity Feed:** Quick list of most active agents and recent run executions with status badges.

### 2. Agents Directory (`/agents`) & Detail (`/agents/:agentId`)
- Lists all registered agents with runtime metadata, registered environment, total runs, total errors, and last activity time.
- Search filter for instantly locating agents by ID or name.
- Agent Detail page shows agent-specific stats and a pre-filtered run history table.

### 3. Run History (`/runs`)
- Paginated table of all agent runs.
- Filterable by Status (`running`, `success`, `error`, `cancelled`), Agent ID, and Environment (`development`, `staging`, `production`).
- Columns include Run ID, Agent ID, Environment, Status, Duration, Token Count, and Timestamp.
- Clicking any row navigates directly to the Run Detail view.

### 4. Run Detail & Span Timeline (`/runs/:runId`)
- **Header:** Run ID, status badge, agent, environment, total duration, tokens consumed, started at, and ended at.
- **Tabs:**
  - **Span Tree (Waterfall):** Hierarchical nested visualization of parent and child spans. Visualizes span durations with proportional bars, status tags (`ok`, `error`), span operations (`agent`, `llm`, `tool`, `retrieval`), and latency breakdown.
  - **Event Log:** Chronological stream of all lifecycle and operational events. Each event row expands on click to show formatted JSON metadata and payload summaries.
  - **Correlation Links:** Trace ID, Root Span ID, retention expiry flags (`trace_data_may_have_expired`), metric observation windows, and deep links to external OTLP backends (Grafana/Tempo).

### 5. Trace Explorer (`/traces`)
- Directory of runs indexed by their OTLP Trace IDs.
- Provides immediate jumping into the Run Detail correlation tab.

### 6. Errors & Diagnostics (`/errors`)
- Grouped failure summaries by error type.
- Shows total occurrences, last seen timestamp, and affected agents.
- Click-through filter immediately opens Run History scoped to runs that encountered that specific error.

### 7. Settings & Connectivity (`/settings`)
- Displays current Project ID and masked API key.
- Live backend health status check (`/health/live` and `/health/ready`).
- Privacy and security posture indicator (payload capture status, retention policies).
- Quick SDK copy-paste integration guide.
- Session sign-out / API key replacement.

---

## Security & Privacy

1. **Authentication Token Storage:**
   - The dashboard authenticates against the FastAPI backend using `Bearer <API_KEY>`.
   - The token is stored strictly in `sessionStorage` (in memory per browser tab session).
   - The key is **never** written to `localStorage`, baked into client bundles, or logged.
2. **Payload Protection:**
   - Raw prompts, completions, and sensitive tool arguments are omitted by default unless payload capture is explicitly enabled on the backend.
   - The UI displays structured attributes and redacted summaries safely.
3. **CORS Isolation:**
   - In development, the backend enables CORS specifically for the local Vite origin (`http://localhost:3001`).
   - In production, static assets and API routes are served behind a unified reverse proxy without wildcard origins.

---

## Manual Verification Checklist for Human Review

Follow these steps to manually verify the Phase 6 dashboard:

1. **Start the backend (if not already running):**
   ```powershell
   .\.venv\Scripts\python -m backend.agentops_backend.main
   ```
   Confirm backend is listening on `http://localhost:8000`.

2. **Start the frontend dev server:**
   ```powershell
   cd frontend
   npm run dev
   ```
   Open `http://localhost:3001` in your browser.

3. **Verify Authentication:**
   - When opened, if no API key is set in session, an authentication modal or prompt appears.
   - Enter your project API key (e.g. from `.env` or generated during seed).
   - Enter Project ID (e.g. `default`).

4. **Verify Overview Page:**
   - Confirm stat cards render (Total Runs, Success Rate %, Duration, Tokens, Active Agents).
   - Check that the charts render smoothly with no console errors.
   - Verify recent runs table.

5. **Verify Run History & Filters:**
   - Navigate to `/runs`.
   - Test filtering by status (`success`, `error`) and agent ID.
   - Test page pagination buttons.

6. **Verify Run Detail & Timeline:**
   - Click on any run row to navigate to `/runs/:runId`.
   - Verify the Span Tree tab shows the nested span hierarchy with proportional duration bars.
   - Click on the Events tab; click an event row to expand JSON metadata.
   - Check the Correlation Links tab for trace ID and OTLP link.

7. **Verify Errors Page:**
   - Navigate to `/errors`.
   - Verify error breakdown cards and table. Click a row and confirm it filters run history.

8. **Verify Settings Page:**
   - Navigate to `/settings`.
   - Confirm health check indicators show "Live: OK" and "Ready: OK".
