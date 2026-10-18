import { useState } from 'react';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Activity, Search } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { api } from '../api';
import type { RunStatus } from '../api';
import { StatusBadge, SkeletonRows, EmptyState, Alert, Pagination } from '../components/ui';
import { fmtRelative, fmtDuration, fmtTokens } from '../utils';

const STATUSES: { value: RunStatus | ''; label: string }[] = [
  { value: '', label: 'All statuses' },
  { value: 'running', label: 'Running' },
  { value: 'success', label: 'Success' },
  { value: 'error', label: 'Error' },
  { value: 'cancelled', label: 'Cancelled' },
];

const ENVIRONMENTS = ['', 'development', 'staging', 'production'];

export function RunHistoryPage() {
  const { projectId } = useAuth();
  const navigate = useNavigate();
  const [search] = useSearchParams();

  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<RunStatus | ''>(
    (search.get('status') as RunStatus | '') ?? '',
  );
  const [agentId, setAgentId] = useState(search.get('agent_id') ?? '');
  const [environment, setEnvironment] = useState('');
  const pageSize = 25;

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['runs', projectId, { page, status, agentId, environment, pageSize }],
    queryFn: () =>
      api.runs.list(projectId, {
        page,
        page_size: pageSize,
        status: status || undefined,
        agent_id: agentId || undefined,
        environment: environment || undefined,
      }),
    staleTime: 15_000,
    placeholderData: keepPreviousData,
  });

  const runs = data?.items ?? [];

  function handleReset() {
    setPage(1);
    setStatus('');
    setAgentId('');
    setEnvironment('');
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Run History</h1>
        <p className="page-desc">All agent runs with filtering and pagination</p>
      </div>

      {isError && (
        <Alert type="error">
          {error instanceof Error ? error.message : 'Failed to load runs'}
        </Alert>
      )}

      <div className="card">
        {/* Filter bar */}
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border-light)' }}>
          <div className="filter-bar">
            {/* Agent ID search */}
            <div style={{ position: 'relative' }}>
              <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-tertiary)', pointerEvents: 'none' }} />
              <input
                id="runs-filter-agent"
                className="input"
                style={{ paddingLeft: 30, minWidth: 180 }}
                placeholder="Agent ID…"
                value={agentId}
                onChange={(e) => { setAgentId(e.target.value); setPage(1); }}
              />
            </div>

            {/* Status */}
            <select
              id="runs-filter-status"
              className="input select"
              value={status}
              onChange={(e) => { setStatus(e.target.value as RunStatus | ''); setPage(1); }}
            >
              {STATUSES.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>

            {/* Environment */}
            <select
              id="runs-filter-env"
              className="input select"
              value={environment}
              onChange={(e) => { setEnvironment(e.target.value); setPage(1); }}
            >
              {ENVIRONMENTS.map((e) => (
                <option key={e} value={e}>{e || 'All environments'}</option>
              ))}
            </select>

            {(status || agentId || environment) && (
              <button id="runs-filter-reset" className="btn btn-ghost btn-sm" onClick={handleReset}>
                Clear filters
              </button>
            )}
          </div>
        </div>

        {/* Table */}
        {isLoading ? (
          <SkeletonRows rows={10} />
        ) : runs.length === 0 ? (
          <EmptyState
            icon={<Activity size={32} />}
            title="No runs found"
            description="Try adjusting your filters."
            action={
              <button className="btn btn-secondary btn-sm" onClick={handleReset}>
                Clear all filters
              </button>
            }
          />
        ) : (
          <div className="table-wrapper">
            <table className="table-clickable">
              <thead>
                <tr>
                  <th>Run ID</th>
                  <th>Agent</th>
                  <th>Status</th>
                  <th>Env</th>
                  <th>Duration</th>
                  <th>Tokens</th>
                  <th>LLM</th>
                  <th>Tool</th>
                  <th>Started</th>
                </tr>
              </thead>
              <tbody>
                {(data?.items ?? []).map((r) => (
                  <tr
                    key={r.run_id}
                    onClick={() => navigate(`/runs/${r.run_id}`)}
                    tabIndex={0}
                    onKeyDown={(e) => e.key === 'Enter' && navigate(`/runs/${r.run_id}`)}
                    aria-label={`Open run ${r.run_id}`}
                    id={`run-row-${r.run_id}`}
                  >
                    <td className="mono" style={{ fontSize: 11.5 }}>{r.run_id.slice(0, 16)}</td>
                    <td className="secondary" style={{ fontSize: 12 }}>{r.agent_id}</td>
                    <td><StatusBadge status={r.status} /></td>
                    <td>
                      <span className="metric-highlight">{r.environment}</span>
                    </td>
                    <td className="mono secondary">{fmtDuration(r.duration_ms)}</td>
                    <td className="mono secondary">{fmtTokens(r.total_tokens)}</td>
                    <td className="secondary">{r.llm_call_count}</td>
                    <td className="secondary">{r.tool_call_count}</td>
                    <td className="secondary" style={{ fontSize: 12 }}>{fmtRelative(r.started_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <Pagination
          page={page}
          pageSize={pageSize}
          total={data?.total ?? 0}
          onPage={setPage}
        />
      </div>
    </div>
  );
}
