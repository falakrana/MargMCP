import React, { createContext, useContext, useState, useEffect } from 'react';
import { api, hasToken, setToken, clearToken } from '../api';

interface AuthContextValue {
  projectId: string;
  isAuthenticated: boolean;
  login: (projectId: string, apiKey: string) => Promise<void>;
  logout: () => void;
  error: string | null;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const PROJECT_ID_KEY = 'agentops_project_id';

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [projectId, setProjectId] = useState<string>(
    () => sessionStorage.getItem(PROJECT_ID_KEY) ?? '',
  );
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(
    () => hasToken() && !!sessionStorage.getItem(PROJECT_ID_KEY),
  );
  const [error, setError] = useState<string | null>(null);

  // Verify token is still valid on mount
  useEffect(() => {
    if (isAuthenticated && projectId) {
      api.project.get(projectId).catch(() => {
        setIsAuthenticated(false);
        clearToken();
      });
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function login(pid: string, apiKey: string) {
    setError(null);
    setToken(apiKey);
    sessionStorage.setItem(PROJECT_ID_KEY, pid);
    try {
      await api.project.get(pid);
      setProjectId(pid);
      setIsAuthenticated(true);
    } catch (e: unknown) {
      clearToken();
      sessionStorage.removeItem(PROJECT_ID_KEY);
      const msg = e instanceof Error ? e.message : 'Authentication failed';
      setError(msg);
      throw e;
    }
  }

  function logout() {
    clearToken();
    sessionStorage.removeItem(PROJECT_ID_KEY);
    setIsAuthenticated(false);
    setProjectId('');
  }

  return (
    <AuthContext.Provider value={{ projectId, isAuthenticated, login, logout, error }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
