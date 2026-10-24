import { useQuery } from '@tanstack/react-query';
import { Settings, ShieldCheck, Clock, Database, Eye } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { api } from '../api';
import { Spinner } from '../components/ui';

export function SettingsPage() {
  const { projectId, logout } = useAuth();

  const projectQ = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => api.project.get(projectId),
    staleTime: 60_000,
  });

  const healthQ = useQuery({
    queryKey: ['health'],
    queryFn: () => api.health.ready(),
    staleTime: 10_000,
    refetchInterval: 30_000,
  });

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Settings</h1>
        <p className="page-desc">Project configuration and integration details</p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Project info */}
        <div className="card">
          <div className="card-header">
            <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Database size={16} /> Project
            </div>
          </div>
          <div className="card-body">
            {projectQ.isLoading ? (
              <Spinner />
            ) : projectQ.data ? (
              <div className="detail-grid">
                <div className="detail-item">
                  <span className="detail-label">Project ID</span>
                  <span className="detail-value mono">{projectQ.data.id}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Name</span>
                  <span className="detail-value">{projectQ.data.name}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Tenant</span>
                  <span className="detail-value mono">{projectQ.data.tenant_id}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Agents</span>
                  <span className="detail-value">{projectQ.data.agent_count}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Created</span>
                  <span className="detail-value">{new Date(projectQ.data.created_at).toLocaleDateString()}</span>
                </div>
              </div>
            ) : null}
          </div>
        </div>

        {/* Backend status */}
        <div className="card">
          <div className="card-header">
            <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <ShieldCheck size={16} /> Backend Health
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {healthQ.isLoading ? (
                <Spinner size={14} />
              ) : healthQ.data?.status === 'ready' ? (
                <span className="badge success"><span className="badge-dot" /> Ready</span>
              ) : (
                <span className="badge error"><span className="badge-dot" /> Unavailable</span>
              )}
            </div>
          </div>
          <div className="card-body">
            <p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
              Backend API at <code style={{ fontFamily: 'JetBrains Mono, monospace', background: 'var(--bg-muted)', padding: '1px 5px', borderRadius: 3 }}>http://localhost:8000</code>.
              Health is checked every 30 seconds.
            </p>
          </div>
        </div>

        {/* Integration guide */}
        <div className="card">
          <div className="card-header">
            <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Settings size={16} /> SDK Integration
            </div>
          </div>
          <div className="card-body">
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 16 }}>
              Use the AgentOps Python SDK to instrument your agents. Set the following environment variables:
            </p>
            <pre style={{
              background: 'var(--bg-subtle)',
              border: '1px solid var(--border-light)',
              borderRadius: 'var(--radius-md)',
              padding: '12px 16px',
              fontSize: 12,
              fontFamily: 'JetBrains Mono, monospace',
              color: 'var(--text-secondary)',
              overflowX: 'auto',
            }}>
{`MARG_API_ENDPOINT=http://localhost:8000
MARG_PROJECT_ID=${projectId}
MARG_API_KEY=<your-api-key>`}
            </pre>
          </div>
        </div>

        {/* Privacy */}
        <div className="card">
          <div className="card-header">
            <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Eye size={16} /> Privacy & Retention
            </div>
          </div>
          <div className="card-body">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, fontSize: 13, color: 'var(--text-secondary)' }}>
              <p>
                <strong style={{ color: 'var(--text-primary)' }}>Payload capture</strong> is controlled by <code style={{ fontFamily: 'JetBrains Mono, monospace', background: 'var(--bg-muted)', padding: '1px 4px', borderRadius: 3 }}>MARG_PAYLOAD_CAPTURE_ENABLED</code> on the server.
                When disabled (default), prompt and output content is not included in timeline responses.
              </p>
              <p>
                <strong style={{ color: 'var(--text-primary)' }}>Run records</strong> are retained for <code style={{ fontFamily: 'JetBrains Mono, monospace', background: 'var(--bg-muted)', padding: '1px 4px', borderRadius: 3 }}>MARG_RUN_RETENTION_DAYS</code> days (default: 90).
              </p>
              <p>
                <strong style={{ color: 'var(--text-primary)' }}>OTLP trace data</strong> retention is controlled by the trace backend (Tempo) and configured via <code style={{ fontFamily: 'JetBrains Mono, monospace', background: 'var(--bg-muted)', padding: '1px 4px', borderRadius: 3 }}>MARG_TRACE_RETENTION_DAYS</code>.
              </p>
            </div>
          </div>
        </div>

        {/* Session */}
        <div className="card">
          <div className="card-header">
            <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Clock size={16} /> Session
            </div>
          </div>
          <div className="card-body">
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 16 }}>
              Your API key is stored only in this browser session (sessionStorage). It is cleared automatically when you close the tab.
            </p>
            <button id="settings-logout" className="btn btn-secondary" onClick={logout}>
              Sign out of this session
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
