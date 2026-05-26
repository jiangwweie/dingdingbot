import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import AppLayout from './components/layout/AppLayout';
import { ErrorBoundary } from './components/layout/ErrorBoundary';
import { ThemeProvider } from './components/layout/ThemeContext';
import { brcApi } from './services/api';
import CommandCenter from './pages/brc/CommandCenter';
import DeveloperDetail from './pages/brc/DeveloperDetail';
import AuditTrail from './pages/brc/AuditTrail';
import Campaigns from './pages/brc/Campaigns';
import Guide from './pages/brc/Guide';
import Ledger from './pages/brc/Ledger';
import LlmCopilot from './pages/brc/LlmCopilot';
import Operator from './pages/brc/Operator';
import Review from './pages/brc/Review';
import RiskAccount from './pages/brc/RiskAccount';
import RuntimeControl from './pages/brc/RuntimeControl';
import StrategyPlaybook from './pages/brc/StrategyPlaybook';
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
                <Route index element={<Navigate to="/command-center" replace />} />
                <Route path="command-center" element={<CommandCenter />} />
                <Route path="llm-copilot" element={<LlmCopilot />} />
                <Route path="strategy-playbook" element={<StrategyPlaybook />} />
                <Route path="risk-account" element={<RiskAccount />} />
                <Route path="runtime-control" element={<RuntimeControl />} />
                <Route path="summary" element={<Navigate to="/command-center" replace />} />
                <Route path="guide" element={<Guide />} />
                <Route path="dashboard" element={<Navigate to="/command-center" replace />} />
                <Route path="markets-orders" element={<Navigate to="/risk-account" replace />} />
                <Route path="campaigns" element={<Campaigns />} />
                <Route path="playbooks-strategy" element={<Navigate to="/strategy-playbook" replace />} />
                <Route path="parameters" element={<Navigate to="/risk-account" replace />} />
                <Route path="audit-trail" element={<AuditTrail />} />
                <Route path="ai-investigator" element={<Navigate to="/llm-copilot" replace />} />
                <Route path="operator" element={<Operator />} />
                <Route path="workflow" element={<Workflow />} />
                <Route path="review" element={<Review />} />
                <Route path="ledger" element={<Ledger />} />
                <Route path="runtime-safety" element={<Navigate to="/runtime-control" replace />} />
                <Route path="developer" element={<DeveloperDetail />} />
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/command-center" replace />} />
          </Routes>
        </BrowserRouter>
      </ThemeProvider>
    </ErrorBoundary>
  </StrictMode>,
);
