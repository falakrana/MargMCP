import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, TrendingUp } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { api } from '../api';
import { Spinner, Alert, EmptyState } from '../components/ui';
import { fmtRelative, successRate } from '../utils';

export function ErrorsPage() {
  const { projectId } = useAuth();
  const navigate = useNavigate();

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['errors', projectId],
    queryFn: () => api.errors.summary(projectId),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

  const rate = data ? successRate(data.total_runs, data.error_runs) : '—';

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Errors & Failures</h1>
        <p className="page-desc">Aggregated error summary across all agents</p>
      </div>

      {isError && (
        <Alert type="error">
          {error instanceof Error ? error.message : 'Failed to load error summary'}
        </Alert>
      )}

      {/* Summary stat cards */}
      <div className="stat-grid" style={{ marginBottom: 20 }}>
        <div className="stat-card">
          <div className="stat-label"><TrendingUp size={14} /> Total Runs</div>
          <div className="stat-value">
            {isLoading ? <div className="skeleton" style={{ height: 28, width: '60%' }} /> : (data?.total_runs ?? 0).toLocaleString()}
          </div>
        </div>
        <div className="stat-card" style={data && data.error_runs > 0 ? { borderColor: 'var(--status-error-border)', background: 'var(--status-error-bg)' } : {}}>
          <div className="stat-label"><AlertTriangle size={14} /> Error Runs</div>
          <div className="stat-value" style={data && data.error_runs > 0 ? { color: 'var(--status-error-text)' } : {}}>
            {isLoading ? <div className="skeleton" style={{ height: 28, width: '60%' }} /> : (data?.error_runs ?? 0).toLocaleString()}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Success Rate</div>
          <div className="stat-value">{isLoading ? <div className="skeleton" style={{ height: 28, width: '50%' }} /> : rate}</div>
        </div>
      </div>

      {/* Error groups table */}
      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">Error Groups</div>
            <div className="card-subtitle">Grouped by error type and agent</div>
          </div>
        </div>

        {isLoading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
            <Spinner />
          </div>
        ) : !data || data.groups.length === 0 ? (
          <EmptyState
            icon={<AlertTriangle size={32} />}
            title="No errors"
            description="There are no recorded failure groups in this project."
          />
        ) : (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Error Type</th>
                  <th>Count</th>
                  <th>Last Seen</th>
                </tr>
              </thead>
              <tbody>
                {data.groups.map((g, i) => (
                  <tr
                    key={i}
                    style={{ cursor: 'pointer' }}
                    onClick={() => navigate(`/runs?agent_id=${g.agent_id}&status=error`)}
                    tabIndex={0}
                    onKeyDown={(e) => e.key === 'Enter' && navigate(`/runs?agent_id=${g.agent_id}&status=error`)}
                    id={`error-group-${i}`}
                  >
                    <td style={{ fontWeight: 500, fontFamily: 'JetBrains Mono, monospace', fontSize: 12 }}>{g.agent_id}</td>
                    <td>
                      <span style={{
                        padding: '2px 8px',
                        background: 'var(--status-error-bg)',
                        border: '1px solid var(--status-error-border)',
                        borderRadius: 'var(--radius-full)',
                        fontSize: 12,
                        color: 'var(--status-error-text)',
                      }}>
                        {g.error_type ?? 'unknown'}
                      </span>
                    </td>
                    <td>
                      <strong style={{ color: 'var(--status-error-text)' }}>{g.count.toLocaleString()}</strong>
                    </td>
                    <td className="secondary">{fmtRelative(g.last_seen)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
