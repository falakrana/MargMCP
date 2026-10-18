import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Bot, Activity, Clock } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { api } from '../api';
import { SkeletonRows, EmptyState, Alert } from '../components/ui';
import { fmtDatetime, fmtRelative } from '../utils';

export function AgentsPage() {
  const { projectId } = useAuth();
  const navigate = useNavigate();

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['agents', projectId],
    queryFn: () => api.agents.list(projectId),
    staleTime: 30_000,
  });

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Agents</h1>
        <p className="page-desc">All registered agents in this project</p>
      </div>

      {isError && (
        <Alert type="error">
          Failed to load agents: {error instanceof Error ? error.message : 'Unknown error'}
        </Alert>
      )}

      <div className="card">
        <div className="card-header">
          <div className="card-title">{data ? `${data.length} agent${data.length !== 1 ? 's' : ''}` : 'Agents'}</div>
        </div>

        {isLoading ? (
          <SkeletonRows rows={6} />
        ) : !data || data.length === 0 ? (
          <EmptyState
            icon={<Bot size={32} />}
            title="No agents yet"
            description="Agents are registered automatically when events arrive."
          />
        ) : (
          <div className="table-wrapper">
            <table className="table-clickable">
              <thead>
                <tr>
                  <th>Agent ID</th>
                  <th>Name</th>
                  <th>Runs</th>
                  <th>Last Active</th>
                  <th>Registered</th>
                  <th>Auto</th>
                </tr>
              </thead>
              <tbody>
                {data.map((agent) => (
                  <tr
                    key={agent.id}
                    onClick={() => navigate(`/agents/${agent.id}`)}
                    tabIndex={0}
                    onKeyDown={(e) => e.key === 'Enter' && navigate(`/agents/${agent.id}`)}
                    aria-label={`Agent ${agent.name}`}
                    id={`agent-row-${agent.id}`}
                  >
                    <td className="mono">{agent.id}</td>
                    <td style={{ fontWeight: 500 }}>{agent.name}</td>
                    <td>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                        <Activity size={13} style={{ color: 'var(--text-tertiary)' }} />
                        {agent.run_count.toLocaleString()}
                      </span>
                    </td>
                    <td className="secondary">
                      <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                        <Clock size={12} style={{ color: 'var(--text-tertiary)' }} />
                        {agent.last_run_at ? fmtRelative(agent.last_run_at) : '—'}
                      </span>
                    </td>
                    <td className="secondary">{fmtDatetime(agent.created_at)}</td>
                    <td>
                      {agent.auto_registered ? (
                        <span className="badge" style={{ background: 'var(--bg-muted)', border: '1px solid var(--border-light)', color: 'var(--text-tertiary)' }}>Auto</span>
                      ) : (
                        <span className="badge" style={{ background: 'var(--accent-50)', border: '1px solid var(--accent-200)', color: 'var(--accent-700)' }}>Manual</span>
                      )}
                    </td>
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
