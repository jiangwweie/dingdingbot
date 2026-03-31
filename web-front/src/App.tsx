import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Signals from './pages/Signals';
import SignalAttempts from './pages/SignalAttempts';
import Account from './pages/Account';
import Backtest from './pages/Backtest';
import StrategyWorkbench from './pages/StrategyWorkbench';
import Snapshots from './pages/Snapshots';
import Orders from './pages/Orders';
import Positions from './pages/Positions';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="signals" element={<Signals />} />
          <Route path="positions" element={<Positions />} />
          <Route path="orders" element={<Orders />} />
          <Route path="backtest" element={<Backtest />} />
          <Route path="attempts" element={<SignalAttempts />} />
          <Route path="account" element={<Account />} />
          <Route path="strategies" element={<StrategyWorkbench />} />
          <Route path="snapshots" element={<Snapshots />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
