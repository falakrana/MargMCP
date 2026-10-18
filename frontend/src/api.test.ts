import { describe, it, expect, beforeEach, vi } from 'vitest';
import { api, ApiError, setToken, clearToken, hasToken } from './api';

describe('ApiError', () => {
  it('instantiates correctly with status, code, and message', () => {
    const err = new ApiError(404, 'not_found', 'Agent not found');
    expect(err).toBeInstanceOf(Error);
    expect(err.status).toBe(404);
    expect(err.code).toBe('not_found');
    expect(err.message).toBe('Agent not found');
  });
});

describe('Token management', () => {
  const store = new Map<string, string>();
  beforeEach(() => {
    store.clear();
    globalThis.sessionStorage = {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, val: string) => { store.set(key, val); },
      removeItem: (key: string) => { store.delete(key); },
      clear: () => store.clear(),
      length: store.size,
      key: () => null,
    };
    clearToken();
  });

  it('sets and retrieves auth token from sessionStorage', () => {
    expect(hasToken()).toBe(false);
    setToken('test_key_123');
    expect(hasToken()).toBe(true);
    clearToken();
    expect(hasToken()).toBe(false);
  });
});

describe('API request layer', () => {
  const store = new Map<string, string>();
  beforeEach(() => {
    vi.restoreAllMocks();
    store.clear();
    globalThis.sessionStorage = {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, val: string) => { store.set(key, val); },
      removeItem: (key: string) => { store.delete(key); },
      clear: () => store.clear(),
      length: store.size,
      key: () => null,
    };
    clearToken();
  });

  it('attaches Authorization header when token is set', async () => {
    setToken('sk_secret_token');
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'ok' }),
    });
    globalThis.fetch = mockFetch;

    await api.health.live();

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers['Authorization']).toBe('Bearer sk_secret_token');
  });

  it('throws ApiError with server response details on non-2xx', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ code: 'unauthorized', message: 'Invalid or missing API key' }),
    });
    globalThis.fetch = mockFetch;

    await expect(api.project.get('proj_123')).rejects.toThrow(ApiError);
  });

  it('constructs runs query string properly with filter parameters', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [], total: 0, page: 1, page_size: 25, total_pages: 0 }),
    });
    globalThis.fetch = mockFetch;

    await api.runs.list('proj_1', {
      page: 2,
      page_size: 10,
      status: 'error',
      agent_id: 'agent_abc',
    });

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain('/v1/projects/proj_1/runs');
    expect(url).toContain('page=2');
    expect(url).toContain('page_size=10');
    expect(url).toContain('status=error');
    expect(url).toContain('agent_id=agent_abc');
  });
});
