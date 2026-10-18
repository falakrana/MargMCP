import { useState } from 'react';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { GitBranch, Search } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { api } from '../api';
import { StatusBadge, SkeletonRows, EmptyState, Alert, Pagination } from '../components/ui';
import { fmtRelative, fmtDuration, fmtId } from '../utils';

// The "Traces" page is a view of runs that have trace IDs — basically all runs.
// Clicking a run opens the RunDetailPage → Correlation tab.
export function TracesPage() {
  const { projectId } = useAuth();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [agentFilter, setAgentFilter] = useState('');

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['runs-traces', projectId, page, agentFilter],
    queryFn: () =>
      api.runs.list(projectId, {
        page,
        page_size: 25,
        agent_id: agentFilter || undefined,
      }),
    staleTime: 15_000,
    placeholderData: keepPreviousData,
  });

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Trace Explorer</h1>
        <p className="page-desc">Browse runs with their OTLP trace and span data</p>
      </div>

      {isError && (
        <Alert type="error">
          {error instanceof Error ? error.message : 'Failed to load traces'}
        </Alert>
      )}

      <div className="card">
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border-light)' }}>
          <div className="filter-bar">
            <div style={{ position: 'relative' }}>
              <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-tertiary)', pointerEvents: 'none' }} />
              <input
                id="traces-filter-agent"
                className="input"
                style={{ paddingLeft: 30, minWidth: 200 }}
                placeholder="Filter by agent ID…"
                value={agentFilter}
                onChange={(e) => { setAgentFilter(e.target.value); setPage(1); }}
              />
            </div>
            {agentFilter && (
              <button className="btn btn-ghost btn-sm" onClick={() => { setAgentFilter(''); setPage(1); }}>
                Clear
              </button>
            )}
          </div>
        </div>

        {isLoading ? (
          <SkeletonRows rows={10} />
        ) : !data || data.items.length === 0 ? (
          <EmptyState
            icon={<GitBranch size={32} />}
            title="No traces found"
            description="Traces are recorded when runs are ingested."
          />
        ) : (
          <div className="table-wrapper">
            <table className="table-clickable">
              <thead>
                <tr>
                  <th>Run ID</th>
                  <th>Trace ID</th>
                  <th>Agent</th>
                  <th>Status</th>
                  <th>Duration</th>
                  <th>Started</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((r) => (
                  <tr
                    key={r.run_id}
                    onClick={() => navigate(`/runs/${r.run_id}`)}
                    tabIndex={0}
                    onKeyDown={(e) => e.key === 'Enter' && navigate(`/runs/${r.run_id}`)}
                    aria-label={`Trace for run ${r.run_id}`}
                    id={`trace-row-${r.run_id}`}
                  >
                    <td className="mono" style={{ fontSize: 11.5 }}>{fmtId(r.run_id, 16)}</td>
                    <td className="mono" style={{ fontSize: 11.5, color: 'var(--accent-600)' }}>{fmtId(r.trace_id, 16)}</td>
                    <td className="secondary">{r.agent_id}</td>
                    <td><StatusBadge status={r.status} /></td>
                    <td className="mono secondary">{fmtDuration(r.duration_ms)}</td>
                    <td className="secondary">{fmtRelative(r.started_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <Pagination
          page={page}
          pageSize={25}
          total={data?.total ?? 0}
          onPage={setPage}
        />
      </div>
    </div>
  );
}
