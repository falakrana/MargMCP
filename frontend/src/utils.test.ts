import { describe, it, expect } from 'vitest';
import {
  fmtDuration,
  fmtRelative,
  fmtDatetime,
  fmtTokens,
  fmtId,
  statusClass,
  statusLabel,
  successRate,
} from './utils';

describe('fmtDuration', () => {
  it('handles null/undefined gracefully', () => {
    expect(fmtDuration(null)).toBe('—');
    expect(fmtDuration(undefined)).toBe('—');
  });

  it('formats milliseconds under 1 second', () => {
    expect(fmtDuration(120)).toBe('120ms');
    expect(fmtDuration(0)).toBe('0ms');
    expect(fmtDuration(999)).toBe('999ms');
  });

  it('formats seconds with 2 decimal places', () => {
    expect(fmtDuration(1500)).toBe('1.50s');
    expect(fmtDuration(45200)).toBe('45.20s');
  });

  it('formats minutes and seconds', () => {
    expect(fmtDuration(65000)).toBe('1m 5s');
    expect(fmtDuration(125000)).toBe('2m 5s');
  });
});

describe('fmtId', () => {
  it('truncates UUID to specified length', () => {
    expect(fmtId('abcdef1234567890')).toBe('abcdef12');
    expect(fmtId('abcdef1234567890', 4)).toBe('abcd');
  });

  it('handles empty or missing gracefully', () => {
    expect(fmtId('')).toBe('');
    expect(fmtId(null as unknown as string)).toBe('—');
  });
});

describe('fmtTokens', () => {
  it('formats raw numbers under 1000', () => {
    expect(fmtTokens(0)).toBe('0');
    expect(fmtTokens(950)).toBe('950');
  });

  it('formats thousands with k suffix', () => {
    expect(fmtTokens(1200)).toBe('1.2k');
    expect(fmtTokens(50000)).toBe('50.0k');
  });

  it('formats millions with M suffix', () => {
    expect(fmtTokens(1500000)).toBe('1.5M');
  });
});

describe('statusClass & statusLabel', () => {
  it('maps known statuses to CSS classes correctly', () => {
    expect(statusClass('success')).toBe('success');
    expect(statusClass('ok')).toBe('success');
    expect(statusClass('error')).toBe('error');
    expect(statusClass('running')).toBe('running');
    expect(statusClass('cancelled')).toBe('cancelled');
    expect(statusClass('other')).toBe('unknown');
  });

  it('maps statuses to readable labels', () => {
    expect(statusLabel('success')).toBe('Success');
    expect(statusLabel('error')).toBe('Error');
    expect(statusLabel('running')).toBe('Running');
    expect(statusLabel('cancelled')).toBe('Cancelled');
    expect(statusLabel('ok')).toBe('OK');
    expect(statusLabel('something_else')).toBe('Unknown');
  });
});

describe('successRate', () => {
  it('calculates percentage accurately', () => {
    expect(successRate(100, 5)).toBe('95.0%');
    expect(successRate(10, 0)).toBe('100.0%');
    expect(successRate(10, 10)).toBe('0.0%');
  });

  it('handles 0 total gracefully', () => {
    expect(successRate(0, 0)).toBe('—');
  });
});

describe('fmtDatetime & fmtRelative', () => {
  it('handles empty inputs', () => {
    expect(fmtDatetime(null)).toBe('—');
    expect(fmtDatetime(undefined)).toBe('—');
    expect(fmtRelative(null)).toBe('—');
    expect(fmtRelative(undefined)).toBe('—');
  });

  it('formats valid ISO dates', () => {
    const formatted = fmtDatetime('2026-10-15T12:00:00Z');
    expect(formatted).not.toBe('—');
    expect(formatted).toContain('2026');
  });
});
