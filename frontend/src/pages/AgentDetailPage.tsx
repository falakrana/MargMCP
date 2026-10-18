import { useQuery } from '@tanstack/react-query';
import { useParams, useNavigate } from 'react-router-dom';
import { Activity } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { api } from '../api';
import { Alert, StatusBadge, EmptyState, SkeletonRows } from '../components/ui';
import { fmtDatetime, fmtRelative, fmtDuration, fmtTokens } from '../utils';

export function AgentDetailPage() {
  const { agentId } = useParams<{ agentId: string }>();
  const { projectId } = useAuth();
  const navigate = useNavigate();

  const agentQ = useQuery({
    queryKey: ['agent', projectId, agentId],
    queryFn: () => api.agents.get(projectId, agentId!),
    enabled: !!agentId,
    staleTime: 30_000,
  });

  const runsQ = useQuery({
    queryKey: ['runs', projectId, { agent_id: agentId }],
    queryFn: () => api.runs.list(projectId, { agent_id: agentId, page_size: 50 }),
    enabled: !!agentId,
    staleTime: 15_000,
  });

  const agent = agentQ.data;
  const runs = runsQ.data?.items ?? [];

  if (agentQ.isError) {
    return (
      <div className="page">
        <Alert type="error">
          {agentQ.error instanceof Error ? agentQ.error.message : 'Failed to load agent'}
        </Alert>
      </div>
    );
  }

  return (
    <div className="page">
      {/* Header */}
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
          <button className="btn btn-ghost btn-sm" onClick={() => navigate('/agents')} aria-label="Back to agents">
            ← Agents
          </button>
          <span style={{ color: 'var(--border-medium)' }}>/</span>
          <span style={{ fontSize: 13, color: 'var(--text-tertiary)', fontFamily: 'JetBrains Mono, monospace' }}>
            {agentId}
          </span>
        </div>
        <h1 className="page-title">
          {agentQ.isLoading ? (
            <div className="skeleton" style={{ height: 24, width: 200 }} />
          ) : (
            <>{agent?.name ?? agentId}</>
          )}
        </h1>
      </div>

      {/* Detail grid */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-header">
          <div className="card-title">Agent Details</div>
          {agent?.auto_registered && (
            <span className="badge" style={{ background: 'var(--bg-muted)', border: '1px solid var(--border-light)', color: 'var(--text-tertiary)' }}>
              Auto-registered
            </span>
          )}
        </div>
        <div className="card-body">
          {agentQ.isLoading ? (
            <SkeletonRows rows={3} />
          ) : agent ? (
            <div className="detail-grid">
              <div className="detail-item">
                <span className="detail-label">Agent ID</span>
                <span className="detail-value mono">{agent.id}</span>
              </div>
              <div className="detail-item">
                <span className="detail-label">Project</span>
                <span className="detail-value mono">{agent.project_id}</span>
              </div>
              <div className="detail-item">
                <span className="detail-label">Total Runs</span>
                <span className="detail-value">{agent.run_count.toLocaleString()}</span>
              </div>
              <div className="detail-item">
                <span className="detail-label">Last Active</span>
                <span className="detail-value">{agent.last_run_at ? fmtRelative(agent.last_run_at) : '—'}</span>
              </div>
              <div className="detail-item">
                <span className="detail-label">Registered</span>
                <span className="detail-value">{fmtDatetime(agent.created_at)}</span>
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {/* Runs */}
      <div className="card">
        <div className="card-header">
          <div className="card-title">Runs for this agent</div>
          <button className="btn btn-secondary btn-sm" onClick={() => navigate(`/runs?agent_id=${agentId}`)} id="agent-detail-view-runs">
            All runs →
          </button>
        </div>

        {runsQ.isLoading ? (
          <SkeletonRows rows={6} />
        ) : runs.length === 0 ? (
          <EmptyState
            icon={<Activity size={28} />}
            title="No runs yet"
            description="This agent has no recorded runs."
          />
        ) : (
          <div className="table-wrapper">
            <table className="table-clickable">
              <thead>
                <tr>
                  <th>Run ID</th>
                  <th>Status</th>
                  <th>Duration</th>
                  <th>Tokens</th>
                  <th>LLM Calls</th>
                  <th>Tool Calls</th>
                  <th>Started</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr
                    key={r.run_id}
                    onClick={() => navigate(`/runs/${r.run_id}`)}
                    tabIndex={0}
                    onKeyDown={(e) => e.key === 'Enter' && navigate(`/runs/${r.run_id}`)}
                    id={`run-row-${r.run_id}`}
                  >
                    <td className="mono" style={{ fontSize: 12 }}>{r.run_id.slice(0, 16)}</td>
                    <td><StatusBadge status={r.status} /></td>
                    <td className="mono secondary">{fmtDuration(r.duration_ms)}</td>
                    <td className="mono secondary">{fmtTokens(r.total_tokens)}</td>
                    <td className="secondary">{r.llm_call_count}</td>
                    <td className="secondary">{r.tool_call_count}</td>
                    <td className="secondary">{fmtRelative(r.started_at)}</td>
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
