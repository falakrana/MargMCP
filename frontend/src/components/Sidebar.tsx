import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Bot,
  Activity,
  AlertTriangle,
  GitBranch,
  Settings,
  LogOut,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';

interface NavItemDef {
  to: string;
  icon: React.ReactNode;
  label: string;
}

const NAV_ITEMS: NavItemDef[] = [
  { to: '/overview', icon: <LayoutDashboard />, label: 'Overview' },
  { to: '/agents', icon: <Bot />, label: 'Agents' },
  { to: '/runs', icon: <Activity />, label: 'Run History' },
  { to: '/errors', icon: <AlertTriangle />, label: 'Errors' },
  { to: '/traces', icon: <GitBranch />, label: 'Traces' },
  { to: '/settings', icon: <Settings />, label: 'Settings' },
];

export function Sidebar() {
  const { projectId, logout } = useAuth();

  return (
    <aside className="sidebar" role="navigation" aria-label="Main navigation">
      {/* Logo */}
      <div className="sidebar-logo">
        <div className="sidebar-logo-mark" aria-hidden="true">A</div>
        <div className="sidebar-logo-text">
          <span className="sidebar-logo-name">AgentOps MCP</span>
          <span className="sidebar-logo-sub">Dashboard</span>
        </div>
      </div>

      {/* Project pill */}
      <div style={{ padding: '12px 20px 4px' }}>
        <div style={{
          background: 'var(--bg-muted)',
          border: '1px solid var(--border-light)',
          borderRadius: 'var(--radius-md)',
          padding: '6px 10px',
          fontSize: 12,
          color: 'var(--text-secondary)',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}>
          <span style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-tertiary)' }}>
            Project
          </span>
          <span
            id="sidebar-project-id"
            style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
            title={projectId}
          >
            {projectId}
          </span>
        </div>
      </div>

      {/* Nav */}
      <nav className="sidebar-nav">
        <div className="nav-section-label">Navigation</div>
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            id={`nav-${item.label.toLowerCase().replace(/\s/g, '-')}`}
            className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
          >
            {item.icon}
            {item.label}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="sidebar-footer">
        <button
          id="sidebar-logout"
          className="nav-item"
          style={{ width: '100%', background: 'none', border: 'none', cursor: 'pointer', marginBottom: 8 }}
          onClick={logout}
          aria-label="Sign out"
        >
          <LogOut style={{ width: 16, height: 16, color: 'var(--text-tertiary)' }} />
          <span style={{ fontSize: 13.5 }}>Sign out</span>
        </button>
        <div className="version">v6.0 · AgentOps MCP</div>
      </div>
    </aside>
  );
}
