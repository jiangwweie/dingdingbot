import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import AppLayout from './components/layout/AppLayout';
import { ErrorBoundary } from './components/layout/ErrorBoundary';
import { ThemeProvider } from './components/layout/ThemeContext';
import { brcApi } from './services/api';
import Dashboard from './pages/brc/Dashboard';
import Ledger from './pages/brc/Ledger';
import Operator from './pages/brc/Operator';
import Review from './pages/brc/Review';
import RuntimeSafety from './pages/brc/RuntimeSafety';
import Workflow from './pages/brc/Workflow';
import Login from './pages/Login';
import './index.css';

function RequireAuth() {
  const location = useLocation();
  const [state, setState] = useState<'checking' | 'ok' | 'blocked'>('checking');

  useEffect(() => {
    brcApi.session()
      .then(() => setState('ok'))
      .catch(() => setState('blocked'));
  }, [location.pathname]);

  if (state === 'checking') {
    return <div className="p-6 text-xs text-zinc-500">检查 Owner 会话...</div>;
  }
  if (state === 'blocked') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <ThemeProvider defaultTheme="dark" storageKey="brc-console-theme">
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route element={<RequireAuth />}>
              <Route path="/" element={<AppLayout />}>
                <Route index element={<Navigate to="/dashboard" replace />} />
                <Route path="dashboard" element={<Dashboard />} />
                <Route path="operator" element={<Operator />} />
                <Route path="workflow" element={<Workflow />} />
                <Route path="review" element={<Review />} />
                <Route path="ledger" element={<Ledger />} />
                <Route path="runtime-safety" element={<RuntimeSafety />} />
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </BrowserRouter>
      </ThemeProvider>
    </ErrorBoundary>
  </StrictMode>,
);
