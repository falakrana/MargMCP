import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, useAuth } from './context/AuthContext';
import { Sidebar } from './components/Sidebar';
import { LoginPage } from './pages/LoginPage';
import { OverviewPage } from './pages/OverviewPage';
import { AgentsPage } from './pages/AgentsPage';
import { AgentDetailPage } from './pages/AgentDetailPage';
import { RunHistoryPage } from './pages/RunHistoryPage';
import { RunDetailPage } from './pages/RunDetailPage';
import { ErrorsPage } from './pages/ErrorsPage';
import { TracesPage } from './pages/TracesPage';
import { SettingsPage } from './pages/SettingsPage';
import { ApiError } from './api';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        if (error instanceof ApiError && (error.status === 401 || error.status === 403 || error.status === 404)) {
          return false;
        }
        return failureCount < 2;
      },
      refetchOnWindowFocus: true,
    },
  },
});

function AppShell() {
  const { isAuthenticated } = useAuth();

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="main-content" id="main-content" tabIndex={-1}>
        <Routes>
          <Route path="/" element={<Navigate to="/overview" replace />} />
          <Route path="/overview" element={<OverviewPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/agents/:agentId" element={<AgentDetailPage />} />
          <Route path="/runs" element={<RunHistoryPage />} />
          <Route path="/runs/:runId" element={<RunDetailPage />} />
          <Route path="/errors" element={<ErrorsPage />} />
          <Route path="/traces" element={<TracesPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/overview" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <AppShell />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
