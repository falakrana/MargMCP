import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ExternalLink,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Sparkles,
  Brain,
  ShieldCheck,
  CheckCircle2,
  HelpCircle,
  RefreshCw,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { api } from '../api';
import type { SpanOut, EventOut, DiagnosticReport } from '../api';
import { StatusBadge, Spinner, Alert, Tabs, Pagination, EmptyState, SkeletonRows } from '../components/ui';
import { fmtDatetime, fmtDuration, fmtId } from '../utils';

// Build indented tree from flat spans
function buildTree(spans: SpanOut[]): { span: SpanOut; depth: number }[] {
  const byId = new Map(spans.map((s) => [s.span_id, s]));
  const children = new Map<string | null, SpanOut[]>();
  spans.forEach((s) => {
    const pid = s.parent_span_id && byId.has(s.parent_span_id) ? s.parent_span_id : null;
    if (!children.has(pid)) children.set(pid, []);
    children.get(pid)!.push(s);
  });

  const result: { span: SpanOut; depth: number }[] = [];

  function walk(spanId: string | null, depth: number) {
    const kids = children.get(spanId) ?? [];
    kids.forEach((s) => {
      result.push({ span: s, depth });
      walk(s.span_id, depth + 1);
    });
  }
  walk(null, 0);
  return result;
}

function EventRow({ event }: { event: EventOut }) {
  const [expanded, setExpanded] = useState(false);
  const hasData = Object.keys(event.data).length > 0;

  return (
    <div style={{ borderBottom: '1px solid var(--border-light)', padding: '10px 16px' }}>
      <div
        style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: hasData ? 'pointer' : 'default' }}
        onClick={() => hasData && setExpanded((v) => !v)}
        role={hasData ? 'button' : undefined}
        aria-expanded={hasData ? expanded : undefined}
        tabIndex={hasData ? 0 : undefined}
        onKeyDown={(e) => hasData && e.key === 'Enter' && setExpanded((v) => !v)}
      >
        {hasData ? (
          expanded ? <ChevronDown size={14} style={{ flexShrink: 0, color: 'var(--text-tertiary)' }} /> : <ChevronRight size={14} style={{ flexShrink: 0, color: 'var(--text-tertiary)' }} />
        ) : <span style={{ width: 14, flexShrink: 0 }} />}
        <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: 'var(--text-tertiary)', whiteSpace: 'nowrap' }}>
          {new Date(event.timestamp).toISOString().slice(11, 23)}Z
        </span>
        <span style={{
          fontSize: 12,
          fontWeight: 500,
          padding: '1px 6px',
          borderRadius: 'var(--radius-sm)',
          background: 'var(--bg-muted)',
          border: '1px solid var(--border-light)',
          color: 'var(--text-secondary)',
          whiteSpace: 'nowrap',
        }}>
          {event.event_type}
        </span>
        <span style={{ fontSize: 12, color: 'var(--text-tertiary)', fontFamily: 'JetBrains Mono, monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {fmtId(event.event_id)}
        </span>
      </div>
      {expanded && hasData && (
        <pre style={{
          marginTop: 8,
          marginLeft: 24,
          padding: '10px 12px',
          background: 'var(--bg-subtle)',
          border: '1px solid var(--border-light)',
          borderRadius: 'var(--radius-md)',
          fontSize: 11.5,
          color: 'var(--text-secondary)',
          fontFamily: 'JetBrains Mono, monospace',
          overflowX: 'auto',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
        }}>
          {JSON.stringify(event.data, null, 2)}
        </pre>
      )}
    </div>
  );
}

function SpanRow({ span, depth }: { span: SpanOut; depth: number }) {
  const isRoot = !span.parent_span_id;
  const statusCls = span.status === 'ok' || span.status === 'success'
    ? 'success' : span.status === 'error' ? 'error'
    : span.status === 'running' ? 'running' : 'cancelled';

  return (
    <div
      className={`timeline-span${isRoot ? ' is-root' : ''}`}
      style={{ marginLeft: depth * 20 }}
      id={`span-${span.span_id}`}
    >
      {span.parent_missing && (
        <AlertTriangle size={13} style={{ color: 'var(--status-running-dot)', flexShrink: 0 }} aria-label="Parent span not in result set" />
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span className="span-name">{span.name}</span>
          <span className={`badge ${statusCls}`} style={{ fontSize: 11 }}>
            <span className="badge-dot" />
            {span.status}
          </span>
          {span.duration_ms != null && (
            <span className="span-meta">{fmtDuration(span.duration_ms)}</span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 12, marginTop: 3 }}>
          <span className="span-meta" style={{ fontSize: 11 }}>
            {span.event_type}
          </span>
          <span className="span-meta" style={{ fontSize: 11 }}>
            {fmtId(span.span_id, 12)}
          </span>
        </div>
      </div>
    </div>
  );
}

export function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const { projectId } = useAuth();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('Timeline');
  const [eventPage, setEventPage] = useState(1);
  const [diagReport, setDiagReport] = useState<DiagnosticReport | null>(null);
  const [isDiagnosing, setIsDiagnosing] = useState(false);
  const [diagError, setDiagError] = useState<string | null>(null);
  const [diagQuestion, setDiagQuestion] = useState('');
  const [showEvidence, setShowEvidence] = useState(false);

  const handleDiagnose = async (questionText?: string) => {
    if (!projectId || !runId) return;
    setIsDiagnosing(true);
    setDiagError(null);
    try {
      const rep = await api.diagnostics.run(projectId, runId, questionText || undefined);
      setDiagReport(rep);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Diagnostic request failed';
      setDiagError(msg);
    } finally {
      setIsDiagnosing(false);
    }
  };

  const timelineQ = useQuery({
    queryKey: ['timeline', projectId, runId, eventPage],
    queryFn: () =>
      api.runs.timeline(projectId, runId!, {
        eventPage,
        eventPageSize: 50,
      }),
    enabled: !!runId,
    staleTime: 30_000,
  });

  const tl = timelineQ.data;
  const run = tl?.run;
  const isError = run?.status === 'error';
  const effectiveTab = !isError && activeTab === 'AI Diagnosis' ? 'Timeline' : activeTab;

  if (timelineQ.isError) {
    return (
      <div className="page">
        <Alert type="error">
          {timelineQ.error instanceof Error ? timelineQ.error.message : 'Failed to load run'}
        </Alert>
      </div>
    );
  }

  const tree = tl ? buildTree(tl.spans) : [];

  return (
    <div className="page">
      {/* Breadcrumb */}
      <div style={{ marginBottom: 16 }}>
        <button className="btn btn-ghost btn-sm" onClick={() => navigate('/runs')} style={{ marginRight: 8 }}>
          ← Runs
        </button>
        <span style={{ fontSize: 12, color: 'var(--text-tertiary)', fontFamily: 'JetBrains Mono, monospace' }}>
          {runId}
        </span>
      </div>

      {/* Status banner */}
      {tl && !tl.is_complete && (
        <div className="alert alert-warning" style={{ marginBottom: 16 }}>
          <AlertTriangle size={15} />
          This run has not yet received a terminal event — it may still be in progress.
        </div>
      )}
      {tl?.trace_data_may_have_expired && (
        <div className="alert alert-info" style={{ marginBottom: 16 }}>
          Trace data may have expired in the OTLP backend. The local run record is still available.
        </div>
      )}

      {/* Run header */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-header">
          <div>
            <div className="card-title" style={{ fontSize: 15 }}>
              {timelineQ.isLoading ? <div className="skeleton" style={{ height: 20, width: 220 }} /> : `Run: ${fmtId(runId ?? '', 20)}`}
            </div>
            <div className="card-subtitle">
              {run ? `Agent: ${run.agent_id} · ${run.environment}` : ''}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {run && <StatusBadge status={run.status} />}
            {isError && (
              <button
                id="run-diagnose-btn"
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => {
                  setActiveTab('AI Diagnosis');
                  if (!diagReport && !isDiagnosing) {
                    void handleDiagnose();
                  }
                }}
                disabled={isDiagnosing}
                style={{ display: 'flex', alignItems: 'center', gap: 6 }}
              >
                <Sparkles size={13} />
                {isDiagnosing ? 'Diagnosing...' : 'AI Diagnose'}
              </button>
            )}
            {tl?.trace_link && (
              <a
                id="run-trace-link"
                href={tl.trace_link}
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-secondary btn-sm"
              >
                <ExternalLink size={13} /> Grafana Trace
              </a>
            )}
          </div>
        </div>

        <div className="card-body">
          {timelineQ.isLoading ? (
            <SkeletonRows rows={3} />
          ) : run ? (
            <div className="detail-grid">
              <div className="detail-item">
                <span className="detail-label">Run ID</span>
                <span className="detail-value mono">{run.run_id}</span>
              </div>
              <div className="detail-item">
                <span className="detail-label">Trace ID</span>
                <span className="detail-value mono">{run.trace_id}</span>
              </div>
              <div className="detail-item">
                <span className="detail-label">Agent</span>
                <span className="detail-value">{run.agent_id}</span>
              </div>
              <div className="detail-item">
                <span className="detail-label">Status</span>
                <StatusBadge status={run.status} />
              </div>
              <div className="detail-item">
                <span className="detail-label">Duration</span>
                <span className="detail-value">{fmtDuration(run.duration_ms)}</span>
              </div>
              <div className="detail-item">
                <span className="detail-label">Started</span>
                <span className="detail-value">{fmtDatetime(run.started_at)}</span>
              </div>
              <div className="detail-item">
                <span className="detail-label">Ended</span>
                <span className="detail-value">{fmtDatetime(run.ended_at)}</span>
              </div>
              <div className="detail-item">
                <span className="detail-label">LLM Calls</span>
                <span className="detail-value">{run.llm_call_count}</span>
              </div>
              <div className="detail-item">
                <span className="detail-label">Tool Calls</span>
                <span className="detail-value">{run.tool_call_count}</span>
              </div>
              <div className="detail-item">
                <span className="detail-label">Total Tokens</span>
                <span className="detail-value">{run.total_tokens.toLocaleString()}</span>
              </div>
              <div className="detail-item">
                <span className="detail-label">Prompt Tokens</span>
                <span className="detail-value">{run.total_prompt_tokens.toLocaleString()}</span>
              </div>
              <div className="detail-item">
                <span className="detail-label">Completion Tokens</span>
                <span className="detail-value">{run.total_completion_tokens.toLocaleString()}</span>
              </div>
              {run.error_type && (
                <div className="detail-item">
                  <span className="detail-label">Error Type</span>
                  <span className="detail-value" style={{ color: 'var(--status-error-text)' }}>{run.error_type}</span>
                </div>
              )}
              {run.error_summary && (
                <div className="detail-item" style={{ gridColumn: '1 / -1' }}>
                  <span className="detail-label">Error Summary</span>
                  <span className="detail-value" style={{ color: 'var(--status-error-text)', fontWeight: 400 }}>{run.error_summary}</span>
                </div>
              )}
              {run.deployment_version && (
                <div className="detail-item">
                  <span className="detail-label">Version</span>
                  <span className="detail-value mono">{run.deployment_version}</span>
                </div>
              )}
              <div className="detail-item">
                <span className="detail-label">SDK</span>
                <span className="detail-value mono">{run.sdk_version}</span>
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {/* Tabs: Spans / Events */}
      <div className="card">
        <div style={{ padding: '0 20px' }}>
          <Tabs
            tabs={isError ? ['Timeline', 'Events', 'Correlation', 'AI Diagnosis'] : ['Timeline', 'Events', 'Correlation']}
            active={effectiveTab}
            onChange={setActiveTab}
          />
        </div>

        {effectiveTab === 'Timeline' && (
          <div style={{ padding: '12px 16px' }}>
            {timelineQ.isLoading ? (
              <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
                <Spinner />
              </div>
            ) : tree.length === 0 ? (
              <EmptyState title="No spans" description="No span data is available for this run." />
            ) : (
              <>
                {tl?.spans_truncated && (
                  <div className="alert alert-warning" style={{ marginBottom: 12 }}>
                    Span result was truncated. Only the first {tl.span_count} spans are shown.
                  </div>
                )}
                <div className="timeline" id="run-timeline">
                  {tree.map(({ span, depth }) => (
                    <SpanRow key={span.span_id} span={span} depth={depth} />
                  ))}
                </div>
              </>
            )}
          </div>
        )}

        {effectiveTab === 'Events' && (
          <div>
            {timelineQ.isLoading ? (
              <SkeletonRows rows={8} />
            ) : !tl || tl.events.length === 0 ? (
              <EmptyState title="No events" description="No events have been recorded for this run." />
            ) : (
              <>
                {tl.events.map((event) => (
                  <EventRow key={event.event_id} event={event} />
                ))}
                <Pagination
                  page={eventPage}
                  pageSize={tl.event_page_size}
                  total={tl.total_event_count}
                  onPage={setEventPage}
                />
              </>
            )}
          </div>
        )}

        {effectiveTab === 'Correlation' && (
          <div className="card-body">
            {timelineQ.isLoading ? (
              <SkeletonRows rows={4} />
            ) : tl ? (
              <div className="detail-grid">
                <div className="detail-item">
                  <span className="detail-label">Run ID</span>
                  <span className="detail-value mono">{tl.correlation_links.run_id}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Trace ID</span>
                  <span className="detail-value mono">{tl.correlation_links.trace_id}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Root Span ID</span>
                  <span className="detail-value mono">{tl.correlation_links.root_span_id}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Run Record Expires</span>
                  <span className="detail-value">{fmtDatetime(tl.correlation_links.run_metadata_expires_at)}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Trace Data Expires</span>
                  <span className="detail-value">{fmtDatetime(tl.correlation_links.trace_data_expires_at)}</span>
                </div>
                {tl.correlation_links.metric_window && (
                  <>
                    <div className="detail-item">
                      <span className="detail-label">Metric Window Start</span>
                      <span className="detail-value mono">{tl.correlation_links.metric_window.start}</span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-label">Metric Window End</span>
                      <span className="detail-value mono">{tl.correlation_links.metric_window.end}</span>
                    </div>
                  </>
                )}
                {tl.trace_link && (
                  <div className="detail-item" style={{ gridColumn: '1/-1' }}>
                    <span className="detail-label">OTLP Deep Link</span>
                    <a id="correlation-trace-link" href={tl.trace_link} target="_blank" rel="noopener noreferrer" style={{ fontSize: 13, fontFamily: 'JetBrains Mono, monospace', wordBreak: 'break-all' }}>
                      {tl.trace_link}
                    </a>
                  </div>
                )}
              </div>
            ) : null}
          </div>
        )}

        {isError && effectiveTab === 'AI Diagnosis' && (
          <div style={{ padding: '20px 24px' }}>
            {/* Top query bar */}
            <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
              <input
                id="diagnostic-question-input"
                type="text"
                className="input"
                placeholder="Ask a specific diagnostic question (e.g. Why did this run fail? Was it slow?)"
                value={diagQuestion}
                onChange={(e) => setDiagQuestion(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && !isDiagnosing && void handleDiagnose(diagQuestion)}
                style={{ flex: 1 }}
              />
              <button
                id="submit-diagnose-btn"
                type="button"
                className="btn btn-primary"
                disabled={isDiagnosing}
                onClick={() => void handleDiagnose(diagQuestion)}
                style={{ display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap' }}
              >
                {isDiagnosing ? <Spinner /> : <Sparkles size={14} />}
                {isDiagnosing ? 'Analyzing...' : diagReport ? 'Re-diagnose' : 'Run AI Diagnosis'}
              </button>
            </div>

            {diagError && (
              <div className="alert alert-error" style={{ marginBottom: 16 }}>
                <AlertTriangle size={15} />
                <span>{diagError}</span>
              </div>
            )}

            {isDiagnosing ? (
              <div style={{ padding: '60px 20px', textAlign: 'center', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-light)' }}>
                <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
                  <Spinner />
                </div>
                <div style={{ fontWeight: 600, fontSize: 15, color: 'var(--text-primary)', marginBottom: 6 }}>
                  Synthesizing Root-Cause Diagnosis...
                </div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', maxWidth: 480, margin: '0 auto' }}>
                  The diagnostic engine is collecting telemetry spans, error records, baseline comparisons, and prompting the configured LLM with strict evidence citations.
                </div>
              </div>
            ) : !diagReport ? (
              <div style={{ padding: '50px 20px', textAlign: 'center', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-md)', border: '1px dashed var(--border-medium)' }}>
                <Brain size={36} style={{ color: 'var(--accent-500)', marginBottom: 12 }} />
                <h3 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>
                  AI Root-Cause Diagnostic Assistant
                </h3>
                <p style={{ fontSize: 13, color: 'var(--text-secondary)', maxWidth: 520, margin: '0 auto 20px', lineHeight: 1.5 }}>
                  Investigate execution failures, latency anomalies, and tool execution issues. The assistant queries historical runs and traces through a strictly read-only layer with zero hallucinations.
                </p>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => void handleDiagnose()}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
                >
                  <Sparkles size={14} /> Diagnose Run Now
                </button>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                {/* Notice & Meta */}
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', background: 'var(--accent-50)', border: '1px solid var(--accent-200)', borderRadius: 'var(--radius-md)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: 'var(--accent-700)' }}>
                    <ShieldCheck size={16} />
                    <span>{diagReport.read_only_notice}</span>
                  </div>
                  <div style={{ display: 'flex', gap: 12, fontSize: 12, color: 'var(--text-secondary)', flexWrap: 'wrap' }}>
                    {diagReport.meta.model && (
                      <span className="mono" style={{ background: 'var(--bg-base)', padding: '2px 8px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
                        Model: {diagReport.meta.model} ({diagReport.meta.provider ?? 'ai'})
                      </span>
                    )}
                    <span style={{ background: 'var(--bg-base)', padding: '2px 8px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
                      {diagReport.meta.tool_calls} tool queries
                    </span>
                    <span style={{ background: 'var(--bg-base)', padding: '2px 8px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
                      {diagReport.meta.evidence_items} evidence items
                    </span>
                    <span style={{ background: 'var(--bg-base)', padding: '2px 8px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
                      {(diagReport.meta.duration_ms / 1000).toFixed(1)}s
                    </span>
                  </div>
                </div>

                {/* Likely Explanations */}
                <div>
                  <h4 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Brain size={16} style={{ color: 'var(--accent-500)' }} />
                    Likely Explanations & Hypotheses
                  </h4>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {diagReport.likely_explanations.map((hyp, i) => (
                      <div key={i} style={{ padding: '14px 16px', background: 'var(--bg-base)', border: '1px solid var(--border-medium)', borderRadius: 'var(--radius-md)' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                          <span style={{
                            fontSize: 11,
                            fontWeight: 600,
                            textTransform: 'uppercase',
                            padding: '2px 6px',
                            borderRadius: 'var(--radius-sm)',
                            background: hyp.confidence === 'high' ? 'var(--status-ok-bg)' : hyp.confidence === 'medium' ? 'var(--status-running-bg)' : 'var(--bg-muted)',
                            color: hyp.confidence === 'high' ? 'var(--status-ok-text)' : hyp.confidence === 'medium' ? 'var(--status-running-text)' : 'var(--text-secondary)',
                            border: `1px solid ${hyp.confidence === 'high' ? 'var(--status-ok-border)' : hyp.confidence === 'medium' ? 'var(--status-running-border)' : 'var(--border-light)'}`,
                          }}>
                            {hyp.confidence} confidence
                          </span>
                        </div>
                        <div style={{ fontSize: 13.5, color: 'var(--text-primary)', lineHeight: 1.5, marginBottom: 8 }}>
                          {hyp.explanation}
                        </div>
                        {hyp.uncertainty && (
                          <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontStyle: 'italic', marginBottom: 8 }}>
                            Uncertainty: {hyp.uncertainty}
                          </div>
                        )}
                        {hyp.evidence.length > 0 && (
                          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                            <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>Evidence:</span>
                            {hyp.evidence.map((ev, ei) => (
                              <span key={ei} className="mono" style={{ fontSize: 11, background: 'var(--bg-muted)', padding: '2px 6px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)' }}>
                                {ev}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Direct Findings */}
                <div>
                  <h4 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <CheckCircle2 size={16} style={{ color: 'var(--status-ok-dot)' }} />
                    Direct Observed Facts (Verified Evidence)
                  </h4>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {diagReport.findings.map((f, i) => (
                      <div key={i} style={{ padding: '12px 14px', background: 'var(--bg-subtle)', border: '1px solid var(--border-light)', borderRadius: 'var(--radius-md)' }}>
                        <div style={{ fontSize: 13, color: 'var(--text-primary)', marginBottom: 6, lineHeight: 1.4 }}>
                          {f.statement}
                        </div>
                        {f.evidence.length > 0 && (
                          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                            {f.evidence.map((ev, ei) => (
                              <span key={ei} className="mono" style={{ fontSize: 11, background: 'var(--bg-base)', padding: '1px 5px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-light)', color: 'var(--text-secondary)' }}>
                                {ev}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Recommended Next Checks & Unknowns */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
                  {diagReport.next_checks.length > 0 && (
                    <div style={{ padding: '14px 16px', background: 'var(--bg-base)', border: '1px solid var(--border-light)', borderRadius: 'var(--radius-md)' }}>
                      <h5 style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
                        <RefreshCw size={14} style={{ color: 'var(--accent-500)' }} /> Recommended Next Checks
                      </h5>
                      <ul style={{ paddingLeft: 18, margin: 0, fontSize: 12.5, color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {diagReport.next_checks.map((nc, i) => (
                          <li key={i}>{nc}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {diagReport.unknown.length > 0 && (
                    <div style={{ padding: '14px 16px', background: 'var(--bg-base)', border: '1px solid var(--border-light)', borderRadius: 'var(--radius-md)' }}>
                      <h5 style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
                        <HelpCircle size={14} style={{ color: 'var(--status-running-dot)' }} /> Unresolved Questions
                      </h5>
                      <ul style={{ paddingLeft: 18, margin: 0, fontSize: 12.5, color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {diagReport.unknown.map((u, i) => (
                          <li key={i}>{u}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>

                {/* Evidence citations toggle */}
                <div style={{ borderTop: '1px solid var(--border-light)', paddingTop: 14 }}>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => setShowEvidence((v) => !v)}
                    style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-secondary)' }}
                  >
                    {showEvidence ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    <span>{showEvidence ? 'Hide' : 'View'} Cited Evidence Records ({diagReport.evidence.length})</span>
                  </button>

                  {showEvidence && (
                    <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {diagReport.evidence.map((ev, i) => (
                        <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'baseline', padding: '6px 10px', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-sm)', fontSize: 12 }}>
                          <span className="mono" style={{ fontWeight: 500, color: 'var(--accent-600)', minWidth: 60 }}>
                            {ev.type}
                          </span>
                          <span className="mono" style={{ color: 'var(--text-secondary)', minWidth: 200 }}>
                            {ev.ref}
                          </span>
                          <span style={{ color: 'var(--text-primary)' }}>
                            {ev.summary}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
