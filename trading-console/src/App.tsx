/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AppShell } from './components/Layout';
import { AuthProvider, useAuth } from './lib/auth';
import Dashboard from './pages/Dashboard';
import AccountRisk from './pages/AccountRisk';
import OrderLedger from './pages/OrderLedger';
import ProtectionHealth from './pages/ProtectionHealth';
import CarrierShelf from './pages/CarrierShelf';
import AuthorizationState from './pages/AuthorizationState';
import ExecutionControl from './pages/ExecutionControl';
import RecoveryState from './pages/RecoveryState';
import ReviewState from './pages/ReviewState';
import AuditChain from './pages/AuditChain';
import SignalMarkerFeed from './pages/SignalMarkerFeed';
import Login from './pages/Login';

function ProtectedShell() {
  const { session, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-600 dark:text-slate-300 flex items-center justify-center text-sm">
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
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<ProtectedShell />}>
            <Route index element={<Dashboard />} />
            <Route path="account" element={<AccountRisk />} />
            <Route path="ledger" element={<OrderLedger />} />
            <Route path="protection" element={<ProtectionHealth />} />
            <Route path="carrier" element={<CarrierShelf />} />
            <Route path="authorization" element={<AuthorizationState />} />
            <Route path="execution" element={<ExecutionControl />} />
            <Route path="recovery" element={<RecoveryState />} />
            <Route path="review" element={<ReviewState />} />
            <Route path="audit" element={<AuditChain />} />
            <Route path="signals" element={<SignalMarkerFeed />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
