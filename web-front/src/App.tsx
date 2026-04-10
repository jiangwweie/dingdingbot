import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Signals from './pages/Signals';
import SignalAttempts from './pages/SignalAttempts';
import Account from './pages/Account';
import Backtest from './pages/Backtest';
import PMSBacktest from './pages/PMSBacktest';
import BacktestReports from './pages/BacktestReports';
import Snapshots from './pages/Snapshots';
import Orders from './pages/Orders';
import Positions from './pages/Positions';
import ConfigManagement from './pages/ConfigManagement';
import ConfigProfiles from './pages/ConfigProfiles';
// 新增：FE-01 配置导航重构
import StrategyConfig from './pages/config/StrategyConfig';
import SystemSettings from './pages/config/SystemSettings';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          {/* 默认重定向到仪表盘 */}
          <Route index element={<Navigate to="/dashboard" replace />} />

          {/* 监控中心 */}
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="signals" element={<Signals />} />
          <Route path="attempts" element={<SignalAttempts />} />

          {/* 交易管理 */}
          <Route path="positions" element={<Positions />} />
          <Route path="orders" element={<Orders />} />

          {/* 回测沙箱 */}
          <Route path="backtest" element={<Backtest />} />
          <Route path="backtest-reports" element={<BacktestReports />} />
          <Route path="pms-backtest" element={<PMSBacktest />} />

          {/* 配置管理 - FE-01 新增路由 */}
          <Route path="config" element={<ConfigManagement />} />
          <Route path="config/strategies" element={<StrategyConfig />} />
          <Route path="config/system" element={<SystemSettings />} />
          <Route path="config/profiles" element={<ConfigProfiles />} />

          {/* 其他 */}
          <Route path="snapshots" element={<Snapshots />} />
          <Route path="account" element={<Account />} />

          {/* 旧路由重定向 (向后兼容) */}
          <Route path="profiles/*" element={<Navigate to="/config" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
