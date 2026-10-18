import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { Spinner } from '../components/ui';

export function LoginPage() {
  const { login, error: authError } = useAuth();
  const [projectId, setProjectId] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [loading, setLoading] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    if (!projectId.trim()) { setFormError('Project ID is required.'); return; }
    if (!apiKey.trim()) { setFormError('API key is required.'); return; }
    setLoading(true);
    try {
      await login(projectId.trim(), apiKey.trim());
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : 'Login failed. Check your credentials.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--bg-subtle)',
      padding: 24,
    }}>
      <div style={{
        width: '100%',
        maxWidth: 400,
      }}>
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{
            width: 48,
            height: 48,
            background: 'var(--accent-500)',
            borderRadius: 14,
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            fontSize: 22,
            fontWeight: 700,
            marginBottom: 16,
          }}>
            A
          </div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.3px' }}>
            AgentOps MCP
          </h1>
          <p style={{ fontSize: 14, color: 'var(--text-secondary)', marginTop: 4 }}>
            Sign in to your monitoring dashboard
          </p>
        </div>

        {/* Card */}
        <div className="card">
          <div className="card-body">
            <form id="login-form" onSubmit={handleSubmit} noValidate>
              {(formError || authError) && (
                <div className="alert alert-error" role="alert" style={{ marginBottom: 16 }}>
                  <svg viewBox="0 0 16 16" fill="currentColor" style={{ width: 14, height: 14, flexShrink: 0 }}>
                    <path d="M8 1a7 7 0 1 1 0 14A7 7 0 0 1 8 1Zm.75 3.75a.75.75 0 0 0-1.5 0v4a.75.75 0 0 0 1.5 0v-4Zm0 6.5a.75.75 0 1 0-1.5 0 .75.75 0 0 0 1.5 0Z" />
                  </svg>
                  {formError ?? authError}
                </div>
              )}

              <div style={{ marginBottom: 16 }}>
                <label htmlFor="login-project-id" style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 6, color: 'var(--text-primary)' }}>
                  Project ID
                </label>
                <input
                  id="login-project-id"
                  type="text"
                  className="input"
                  placeholder="e.g. synthetic-demo"
                  value={projectId}
                  onChange={(e) => setProjectId(e.target.value)}
                  autoComplete="username"
                  autoFocus
                  disabled={loading}
                />
              </div>

              <div style={{ marginBottom: 24 }}>
                <label htmlFor="login-api-key" style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 6, color: 'var(--text-primary)' }}>
                  API Key
                </label>
                <input
                  id="login-api-key"
                  type="password"
                  className="input"
                  placeholder="aop_…"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  autoComplete="current-password"
                  disabled={loading}
                />
              </div>

              <button
                id="login-submit"
                type="submit"
                className="btn btn-primary"
                disabled={loading}
                style={{ width: '100%', justifyContent: 'center', padding: '9px 14px' }}
              >
                {loading ? <><Spinner size={16} /> Signing in…</> : 'Sign in'}
              </button>
            </form>
          </div>
        </div>

        <p style={{ textAlign: 'center', fontSize: 12, color: 'var(--text-tertiary)', marginTop: 20 }}>
          Your API key is stored only in this browser session and is never sent to any third party.
        </p>
      </div>
    </div>
  );
}
