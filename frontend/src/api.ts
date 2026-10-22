// Central API client — all requests go through here
// Credentials: uses Bearer token stored in sessionStorage.
// Never exposes the admin token in the bundle.

const API_BASE = '';

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function getToken(): string | null {
  if (typeof sessionStorage === 'undefined') return null;
  return sessionStorage.getItem('agentops_api_key');
}

export function setToken(token: string): void {
  if (typeof sessionStorage !== 'undefined') {
    sessionStorage.setItem('agentops_api_key', token);
  }
}

export function clearToken(): void {
  if (typeof sessionStorage !== 'undefined') {
    sessionStorage.removeItem('agentops_api_key');
  }
}

export function hasToken(): boolean {
  return !!getToken();
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (!res.ok) {
    let code = 'http_error';
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      code = body.code ?? code;
      message = body.message ?? message;
    } catch {
      // ignore
    }
    throw new ApiError(res.status, code, message);
  }

  if (res.status === 204) return undefined as unknown as T;
  return res.json() as Promise<T>;
}

// ── Types (matching backend schemas) ────────────────────────

export interface ProjectOut {
  id: string;
  tenant_id: string;
  name: string;
  created_at: string;
  agent_count: number;
}

export interface AgentOut {
  id: string;
  project_id: string;
  name: string;
  auto_registered: boolean;
  created_at: string;
  run_count: number;
  last_run_at: string | null;
}

export type RunStatus = 'running' | 'success' | 'error' | 'cancelled' | 'unknown';

export interface RunOut {
  run_id: string;
  agent_id: string;
  project_id: string;
  trace_id: string;
  root_span_id: string;
  environment: string;
  status: RunStatus;
  started_at: string;
  ended_at: string | null;
  duration_ms: number | null;
  error_type: string | null;
  error_summary: string | null;
  deployment_version: string | null;
  sdk_version: string;
  llm_call_count: number;
  tool_call_count: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface EventOut {
  event_id: string;
  run_id: string;
  agent_id: string;
  event_type: string;
  environment: string;
  timestamp: string;
  data: Record<string, unknown>;
}

export interface RunListOut {
  items: RunOut[];
  total: number;
  page: number;
  page_size: number;
}

export interface RunDetailOut {
  run: RunOut;
  events: EventOut[];
  event_count: number;
  events_truncated: boolean;
}

export interface ErrorGroup {
  agent_id: string;
  error_type: string | null;
  count: number;
  last_seen: string;
}

export interface ErrorSummaryOut {
  total_runs: number;
  error_runs: number;
  groups: ErrorGroup[];
}

export interface SpanOut {
  span_id: string;
  parent_span_id: string | null;
  name: string;
  event_id: string;
  event_type: string;
  start_time: string;
  end_time: string;
  duration_ms: number | null;
  status: string;
  attributes: Record<string, unknown>;
  parent_missing: boolean;
}

export interface CorrelationLinks {
  run_id: string;
  trace_id: string;
  root_span_id: string;
  run_metadata_expires_at: string;
  trace_data_expires_at: string;
  metric_window: { start: string; end: string } | null;
}

export interface RunTimelineOut {
  run: RunOut;
  is_complete: boolean;
  trace_data_may_have_expired: boolean;
  spans: SpanOut[];
  spans_truncated: boolean;
  span_count: number;
  events: EventOut[];
  total_event_count: number;
  event_page: number;
  event_page_size: number;
  trace_link: string | null;
  correlation_links: CorrelationLinks;
}

// ── Query params ─────────────────────────────────────────────

export interface RunsFilter {
  agent_id?: string;
  status?: RunStatus | '';
  environment?: string;
  started_after?: string;
  started_before?: string;
  page?: number;
  page_size?: number;
}

// ── API functions ─────────────────────────────────────────────

export const api = {
  health: {
    live: () => request<{ status: string }>('/health/live'),
    ready: () => request<{ status: string }>('/health/ready'),
  },

  project: {
    get: (projectId: string) =>
      request<ProjectOut>(`/v1/projects/${projectId}`),
  },

  agents: {
    list: (projectId: string) =>
      request<AgentOut[]>(`/v1/projects/${projectId}/agents`),
    get: (projectId: string, agentId: string) =>
      request<AgentOut>(`/v1/projects/${projectId}/agents/${agentId}`),
  },

  runs: {
    list: (projectId: string, filter: RunsFilter = {}) => {
      const params = new URLSearchParams();
      if (filter.agent_id) params.set('agent_id', filter.agent_id);
      if (filter.status) params.set('status', filter.status);
      if (filter.environment) params.set('environment', filter.environment);
      if (filter.started_after) params.set('started_after', filter.started_after);
      if (filter.started_before) params.set('started_before', filter.started_before);
      if (filter.page) params.set('page', String(filter.page));
      if (filter.page_size) params.set('page_size', String(filter.page_size));
      const qs = params.toString();
      return request<RunListOut>(`/v1/projects/${projectId}/runs${qs ? `?${qs}` : ''}`);
    },
    detail: (projectId: string, runId: string, maxEvents = 500) =>
      request<RunDetailOut>(`/v1/projects/${projectId}/runs/${runId}?max_events=${maxEvents}`),
    timeline: (
      projectId: string,
      runId: string,
      opts: { eventPage?: number; eventPageSize?: number } = {},
    ) => {
      const params = new URLSearchParams();
      if (opts.eventPage) params.set('event_page', String(opts.eventPage));
      if (opts.eventPageSize) params.set('event_page_size', String(opts.eventPageSize));
      const qs = params.toString();
      return request<RunTimelineOut>(
        `/v1/projects/${projectId}/runs/${runId}/timeline${qs ? `?${qs}` : ''}`,
      );
    },
  },

  errors: {
    summary: (
      projectId: string,
      opts: { agent_id?: string; started_after?: string; started_before?: string } = {},
    ) => {
      const params = new URLSearchParams();
      if (opts.agent_id) params.set('agent_id', opts.agent_id);
      if (opts.started_after) params.set('started_after', opts.started_after);
      if (opts.started_before) params.set('started_before', opts.started_before);
      const qs = params.toString();
      return request<ErrorSummaryOut>(
        `/v1/projects/${projectId}/errors/summary${qs ? `?${qs}` : ''}`,
      );
    },
  },

  diagnostics: {
    run: (projectId: string, runId: string, question?: string) =>
      request<DiagnosticReport>(`/v1/projects/${projectId}/diagnose/run`, {
        method: 'POST',
        body: JSON.stringify({ run_id: runId, ...(question ? { question } : {}) }),
      }),
    agent: (
      projectId: string,
      agentId: string,
      opts: { started_after?: string; started_before?: string; question?: string } = {},
    ) =>
      request<DiagnosticReport>(`/v1/projects/${projectId}/diagnose/agent`, {
        method: 'POST',
        body: JSON.stringify({ agent_id: agentId, ...opts }),
      }),
  },
};

export interface DiagnosticScope {
  kind: 'run' | 'agent';
  project_id: string;
  agent_id?: string;
  run_id?: string;
  started_after?: string;
  started_before?: string;
  question?: string;
}

export interface DiagnosticFinding {
  statement: string;
  evidence: string[];
}

export interface DiagnosticHypothesis {
  explanation: string;
  confidence: 'high' | 'medium' | 'low';
  evidence: string[];
  uncertainty?: string;
}

export interface DiagnosticEvidenceRef {
  ref: string;
  type: 'run' | 'span' | 'metric' | 'errors' | 'comparison';
  summary: string;
}

export interface DiagnosticMeta {
  provider?: string;
  model?: string;
  tool_calls: number;
  llm_calls: number;
  duration_ms: number;
  generated_at: string;
  evidence_items: number;
  llm_skipped: boolean;
  dropped_uncited_statements: number;
  rejected_citations: number;
  blocked_action_claims: number;
  suspicious_content_detected: number;
}

export interface DiagnosticReport {
  scope: DiagnosticScope;
  findings: DiagnosticFinding[];
  likely_explanations: DiagnosticHypothesis[];
  evidence: DiagnosticEvidenceRef[];
  unknown: string[];
  next_checks: string[];
  read_only_notice: string;
  meta: DiagnosticMeta;
}

