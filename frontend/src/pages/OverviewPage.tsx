import React from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  AreaChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, BarChart, Bar,
} from 'recharts';
import { Activity, Bot, CheckCircle, Clock, Zap } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { api } from '../api';
import { Spinner, EmptyState, StatusBadge, SkeletonRows } from '../components/ui';
import { fmtDuration, fmtRelative, fmtTokens, successRate, fmtId } from '../utils';
import { useNavigate } from 'react-router-dom';

// Build chart data from run list
function buildVolumeData(runs: import('../api').RunOut[]) {
  const buckets: Record<string, { hour: string; success: number; error: number; running: number }> = {};
  runs.forEach((r) => {
    const d = new Date(r.started_at);
    const key = `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:00`;
    if (!buckets[key]) buckets[key] = { hour: key, success: 0, error: 0, running: 0 };
    if (r.status === 'success') buckets[key].success++;
    else if (r.status === 'error') buckets[key].error++;
    else buckets[key].running++;
  });
  return Object.values(buckets).slice(-24);
}

export function OverviewPage() {
  const { projectId } = useAuth();
  const navigate = useNavigate();

  const projectQ = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => api.project.get(projectId),
    staleTime: 30_000,
  });

  const agentsQ = useQuery({
    queryKey: ['agents', projectId],
    queryFn: () => api.agents.list(projectId),
    staleTime: 30_000,
  });

  const runsQ = useQuery({
    queryKey: ['runs', projectId, { page: 1, page_size: 100 }],
    queryFn: () => api.runs.list(projectId, { page: 1, page_size: 100 }),
    staleTime: 15_000,
    refetchInterval: 30_000,
  });

  const errorsQ = useQuery({
    queryKey: ['errors', projectId],
    queryFn: () => api.errors.summary(projectId),
    staleTime: 30_000,
  });

  const runs = runsQ.data?.items ?? [];
  const totalRuns = runsQ.data?.total ?? 0;
  const agents = agentsQ.data ?? [];
  const errorData = errorsQ.data;

  const runningCount = runs.filter((r) => r.status === 'running').length;
  const totalTokens = runs.reduce((s, r) => s + r.total_tokens, 0);
  const avgDuration =
    runs.filter((r) => r.duration_ms != null).length > 0
      ? runs.filter((r) => r.duration_ms != null).reduce((s, r) => s + (r.duration_ms ?? 0), 0) /
        runs.filter((r) => r.duration_ms != null).length
      : null;

  const volumeData = buildVolumeData(runs);
  const recentRuns = runs.slice(0, 8);

  const isLoading = projectQ.isLoading || agentsQ.isLoading || runsQ.isLoading;

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Overview</h1>
        <p className="page-desc">
          {projectQ.data ? (
            <>Project <strong>{projectQ.data.name}</strong> · {projectQ.data.agent_count} agent{projectQ.data.agent_count !== 1 ? 's' : ''}</>
          ) : (
            <span className="skeleton" style={{ height: 14, width: 200, display: 'inline-block' }} />
          )}
        </p>
      </div>

      {/* Stat cards */}
      <div className="stat-grid">
        <StatCard
          label="Total Runs"
          icon={<Activity />}
          value={isLoading ? null : totalRuns.toLocaleString()}
          meta={runsQ.data ? `${runsQ.data.page_size} per page` : ''}
        />
        <StatCard
          label="Active Now"
          icon={<Clock />}
          value={isLoading ? null : String(runningCount)}
          meta="currently running"
          highlight={runningCount > 0}
        />
        <StatCard
          label="Agents"
          icon={<Bot />}
          value={isLoading ? null : String(agents.length)}
          meta="registered agents"
        />
        <StatCard
          label="Success Rate"
          icon={<CheckCircle />}
          value={isLoading ? null : successRate(errorData?.total_runs ?? 0, errorData?.error_runs ?? 0)}
          meta={errorData ? `${errorData.error_runs} errors` : ''}
        />
        <StatCard
          label="Avg Duration"
          icon={<Zap />}
          value={isLoading ? null : fmtDuration(avgDuration)}
          meta="per run (sample)"
        />
        <StatCard
          label="Total Tokens"
          icon={<Activity />}
          value={isLoading ? null : fmtTokens(totalTokens)}
          meta="across sample runs"
        />
      </div>

      {/* Charts row */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
        {/* Run volume */}
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Run Volume</div>
              <div className="card-subtitle">Success vs errors over time (UTC)</div>
            </div>
          </div>
          <div className="card-body chart-wrapper" style={{ padding: '12px 4px 4px' }}>
            {runsQ.isLoading ? (
              <div style={{ height: 180, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Spinner />
              </div>
            ) : volumeData.length === 0 ? (
              <EmptyState title="No data yet" description="Runs will appear here as they are ingested." />
            ) : (
              <ResponsiveContainer width="100%" height={180}>
                <AreaChart data={volumeData} margin={{ top: 4, right: 16, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="grad-success" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.18} />
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="grad-error" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#ef4444" stopOpacity={0.15} />
                      <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
                  <XAxis dataKey="hour" tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }} tickLine={false} />
                  <YAxis tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }} tickLine={false} axisLine={false} />
                  <Tooltip
                    contentStyle={{
                      background: 'var(--bg-base)',
                      border: '1px solid var(--border-light)',
                      borderRadius: 8,
                      fontSize: 12,
                      boxShadow: 'var(--shadow-md)',
                    }}
                  />
                  <Area type="monotone" dataKey="success" stroke="#10b981" strokeWidth={2} fill="url(#grad-success)" name="Success" />
                  <Area type="monotone" dataKey="error" stroke="#ef4444" strokeWidth={2} fill="url(#grad-error)" name="Error" />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Error summary */}
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Error Types</div>
              <div className="card-subtitle">Top failure categories</div>
            </div>
          </div>
          <div className="card-body chart-wrapper" style={{ padding: '12px 4px 4px' }}>
            {errorsQ.isLoading ? (
              <div style={{ height: 180, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Spinner />
              </div>
            ) : !errorData || errorData.groups.length === 0 ? (
              <EmptyState
                icon={<CheckCircle size={32} />}
                title="No errors"
                description="No failure groups in the current time window."
              />
            ) : (
              <ResponsiveContainer width="100%" height={180}>
                <BarChart
                  data={errorData.groups.slice(0, 8).map((g) => ({
                    name: g.error_type ?? 'unknown',
                    count: g.count,
                    agent: g.agent_id,
                  }))}
                  layout="vertical"
                  margin={{ top: 4, right: 16, left: 0, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }} tickLine={false} />
                  <YAxis
                    type="category"
                    dataKey="name"
                    tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }}
                    tickLine={false}
                    width={90}
                  />
                  <Tooltip
                    contentStyle={{
                      background: 'var(--bg-base)',
                      border: '1px solid var(--border-light)',
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                  />
                  <Bar dataKey="count" fill="#ef4444" fillOpacity={0.8} radius={[0, 4, 4, 0]} name="Errors" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>

      {/* Recent runs */}
      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">Recent Runs</div>
            <div className="card-subtitle">Latest 8 runs across all agents</div>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={() => navigate('/runs')} id="overview-view-all-runs">
            View all
          </button>
        </div>
        {runsQ.isLoading ? (
          <SkeletonRows rows={6} />
        ) : recentRuns.length === 0 ? (
          <EmptyState
            icon={<Activity size={32} />}
            title="No runs yet"
            description="Runs will appear here as your agents execute."
          />
        ) : (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Run ID</th>
                  <th>Agent</th>
                  <th>Status</th>
                  <th>Duration</th>
                  <th>Tokens</th>
                  <th>Started</th>
                </tr>
              </thead>
              <tbody>
                {recentRuns.map((r) => (
                  <tr
                    key={r.run_id}
                    style={{ cursor: 'pointer' }}
                    onClick={() => navigate(`/runs/${r.run_id}`)}
                    tabIndex={0}
                    onKeyDown={(e) => e.key === 'Enter' && navigate(`/runs/${r.run_id}`)}
                    aria-label={`Run ${r.run_id}`}
                  >
                    <td className="mono">{fmtId(r.run_id, 12)}</td>
                    <td className="secondary">{r.agent_id}</td>
                    <td><StatusBadge status={r.status} /></td>
                    <td className="mono secondary">{fmtDuration(r.duration_ms)}</td>
                    <td className="mono secondary">{fmtTokens(r.total_tokens)}</td>
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

interface StatCardProps {
  label: string;
  icon: React.ReactNode;
  value: string | null;
  meta?: string;
  highlight?: boolean;
}

function StatCard({ label, icon, value, meta, highlight }: StatCardProps) {
  return (
    <div className="stat-card" style={highlight ? { borderColor: 'var(--status-running-border)', background: 'var(--status-running-bg)' } : {}}>
      <div className="stat-label">
        {React.cloneElement(icon as React.ReactElement<{ size?: number }>, { size: 14 })}
        {label}
      </div>
      <div className="stat-value">
        {value == null ? (
          <div className="skeleton" style={{ height: 28, width: '60%' }} />
        ) : (
          value
        )}
      </div>
      {meta && <div className="stat-meta">{meta}</div>}
    </div>
  );
}
