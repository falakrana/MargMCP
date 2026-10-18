import React from 'react';
import { statusClass, statusLabel } from '../utils';

interface StatusBadgeProps {
  status: string;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const cls = statusClass(status);
  return (
    <span className={`badge ${cls}`}>
      <span className="badge-dot" />
      {statusLabel(status)}
    </span>
  );
}

interface SpinnerProps {
  size?: number;
}

export function Spinner({ size = 20 }: SpinnerProps) {
  return (
    <div
      className="spinner"
      style={{ width: size, height: size }}
      role="status"
      aria-label="Loading"
    />
  );
}

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="empty-state">
      {icon && <span style={{ color: 'var(--text-tertiary)', marginBottom: 12 }}>{icon}</span>}
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {action && <div style={{ marginTop: 16 }}>{action}</div>}
    </div>
  );
}

interface AlertProps {
  type?: 'error' | 'warning' | 'info';
  children: React.ReactNode;
  icon?: React.ReactNode;
}

export function Alert({ type = 'error', children, icon }: AlertProps) {
  return (
    <div className={`alert alert-${type}`} role="alert">
      {icon}
      <span>{children}</span>
    </div>
  );
}

interface SkeletonProps {
  height?: number | string;
  width?: number | string;
  style?: React.CSSProperties;
}

export function Skeleton({ height = 16, width = '100%', style }: SkeletonProps) {
  return <div className="skeleton" style={{ height, width, ...style }} />;
}

export function SkeletonRows({ rows = 5 }: { rows?: number }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: '16px 20px' }}>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} height={18} width={`${70 + (i % 3) * 10}%`} />
      ))}
    </div>
  );
}

interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onPage: (p: number) => void;
}

export function Pagination({ page, pageSize, total, onPage }: PaginationProps) {
  const totalPages = Math.ceil(total / pageSize);
  const from = Math.min((page - 1) * pageSize + 1, total);
  const to = Math.min(page * pageSize, total);

  return (
    <div className="pagination">
      <span>
        {total === 0
          ? 'No results'
          : `${from}–${to} of ${total.toLocaleString()}`}
      </span>
      <div className="pagination-controls">
        <button
          id="pagination-prev"
          className="btn btn-secondary btn-sm"
          onClick={() => onPage(page - 1)}
          disabled={page <= 1}
          aria-label="Previous page"
        >
          ← Prev
        </button>
        <span style={{ fontSize: 12, color: 'var(--text-tertiary)', padding: '0 4px' }}>
          {page} / {Math.max(totalPages, 1)}
        </span>
        <button
          id="pagination-next"
          className="btn btn-secondary btn-sm"
          onClick={() => onPage(page + 1)}
          disabled={page >= totalPages}
          aria-label="Next page"
        >
          Next →
        </button>
      </div>
    </div>
  );
}

interface TabsProps {
  tabs: string[];
  active: string;
  onChange: (tab: string) => void;
}

export function Tabs({ tabs, active, onChange }: TabsProps) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button
          key={t}
          role="tab"
          aria-selected={active === t}
          className={`tab${active === t ? ' active' : ''}`}
          onClick={() => onChange(t)}
          id={`tab-${t.toLowerCase().replace(/\s/g, '-')}`}
        >
          {t}
        </button>
      ))}
    </div>
  );
}
