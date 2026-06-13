/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AppShell } from './components/Layout';
import { AuthProvider, useAuth } from './lib/auth';
import { ThemeProvider } from './lib/theme';
import Dashboard from './pages/Dashboard';
import OrderLedger from './pages/OrderLedger';
import CarrierShelf from './pages/CarrierShelf';
import AuthorizationState from './pages/AuthorizationState';
import RecoveryState from './pages/RecoveryState';
import ReviewState from './pages/ReviewState';
import AuditChain from './pages/AuditChain';
import WatcherStatus from './pages/WatcherStatus';
import Login from './pages/Login';

function ProtectedShell() {
  const { session, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="console-surface flex min-h-screen items-center justify-center text-sm text-slate-600 dark:text-slate-300">
        正在确认登录状态...
      </div>
    );
  }

  if (!session?.authenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <AppShell />;
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/" element={<ProtectedShell />}>
              <Route index element={<Dashboard />} />
              <Route path="strategy" element={<CarrierShelf />} />
              <Route path="runtime" element={<AuthorizationState />} />
              <Route path="watcher" element={<WatcherStatus />} />
              <Route path="trades" element={<OrderLedger />} />
              <Route path="analysis" element={<ReviewState />} />
              <Route path="incident" element={<RecoveryState />} />
              <Route path="evidence" element={<AuditChain />} />
              <Route path="account" element={<Navigate to="/trades" replace />} />
              <Route path="ledger" element={<Navigate to="/trades" replace />} />
              <Route path="protection" element={<Navigate to="/trades" replace />} />
              <Route path="carrier" element={<Navigate to="/strategy" replace />} />
              <Route path="authorization" element={<Navigate to="/runtime" replace />} />
              <Route path="execution" element={<Navigate to="/runtime" replace />} />
              <Route path="action-entry" element={<Navigate to="/runtime" replace />} />
              <Route path="recovery" element={<Navigate to="/incident" replace />} />
              <Route path="review" element={<Navigate to="/analysis" replace />} />
              <Route path="audit" element={<Navigate to="/evidence" replace />} />
              <Route path="signals" element={<Navigate to="/runtime" replace />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  );
}
