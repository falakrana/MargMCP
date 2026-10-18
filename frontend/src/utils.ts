// Shared utility helpers

import { format, formatDistanceToNow, parseISO } from 'date-fns';
import type { RunStatus } from './api';

/** Format an ISO datetime string to a human-readable local string. */
export function fmtDatetime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return format(parseISO(iso), 'MMM d, yyyy HH:mm:ss');
  } catch {
    return iso;
  }
}

/** Format ISO as "X ago" */
export function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return formatDistanceToNow(parseISO(iso), { addSuffix: true });
  } catch {
    return iso;
  }
}

/** Format duration in milliseconds to human string */
export function fmtDuration(ms: number | null | undefined): string {
  if (ms == null) return '—';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(2)}s`;
  const m = Math.floor(ms / 60_000);
  const s = ((ms % 60_000) / 1000).toFixed(0);
  return `${m}m ${s}s`;
}

/** Truncate a UUID-like string for display */
export function fmtId(id: string, len = 8): string {
  return id?.slice(0, len) ?? '—';
}

/** Map status to CSS class name */
export function statusClass(status: string): string {
  switch (status) {
    case 'success':
    case 'ok':
      return 'success';
    case 'error':
      return 'error';
    case 'running':
      return 'running';
    case 'cancelled':
      return 'cancelled';
    default:
      return 'unknown';
  }
}

/** Format token count compactly */
export function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

/** Get a human-readable label for a status */
export function statusLabel(status: RunStatus | string): string {
  switch (status) {
    case 'success': return 'Success';
    case 'error': return 'Error';
    case 'running': return 'Running';
    case 'cancelled': return 'Cancelled';
    case 'ok': return 'OK';
    default: return 'Unknown';
  }
}

/** Compute success rate percentage */
export function successRate(total: number, errors: number): string {
  if (total === 0) return '—';
  return `${(((total - errors) / total) * 100).toFixed(1)}%`;
}
