import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import AppLayout from './components/layout/AppLayout';
import { ErrorBoundary } from './components/layout/ErrorBoundary';
import { ThemeProvider } from './components/layout/ThemeContext';
import { brcApi } from './services/api';
import {
  AccountOrdersV2,
  AnalysisV2,
  HomeV2,
  IntentsV2,
  StrategyGroupsV2,
  TraceV2,
} from './pages/brc/OwnerConsoleV2';
import Login from './pages/Login';
import './index.css';

const retiredRoutes = [
  'command-center',
  'markets-orders',
  'campaign',
  'review-evidence',
  'strategy-families',
  'fixed-testnet-rehearsal',
  'llm-copilot',
  'strategy-playbook',
  'risk-account',
  'runtime-control',
  'summary',
  'guide',
  'dashboard',
  'campaigns',
  'playbooks-strategy',
  'parameters',
  'audit-trail',
  'ai-investigator',
  'operator',
  'workflow',
  'review',
  'ledger',
  'audit',
  'runtime-safety',
  'developer',
];

function RequireAuth() {
  const location = useLocation();
  const [state, setState] = useState<'checking' | 'ok' | 'blocked'>('checking');

  useEffect(() => {
    brcApi.session()
      .then(() => setState('ok'))
      .catch(() => setState('blocked'));
  }, [location.pathname]);

  if (state === 'checking') {
    return <div className="p-6 text-sm text-zinc-500">检查 Owner 会话...</div>;
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
                <Route index element={<Navigate to="/home" replace />} />
                <Route path="home" element={<HomeV2 />} />
                <Route path="strategy-groups" element={<StrategyGroupsV2 />} />
                <Route path="intents" element={<IntentsV2 />} />
                <Route path="account-orders" element={<AccountOrdersV2 />} />
                <Route path="analysis" element={<AnalysisV2 />} />
                <Route path="trace" element={<TraceV2 />} />
                {retiredRoutes.map((route) => (
                  <Route key={route} path={route} element={<Navigate to="/home" replace />} />
                ))}
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/home" replace />} />
          </Routes>
        </BrowserRouter>
      </ThemeProvider>
    </ErrorBoundary>
  </StrictMode>,
);
