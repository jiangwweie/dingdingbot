import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { Activity, BarChart2, Wallet, Bug, Settings, FlaskConical, Zap, Save, FileText, TrendingUp } from 'lucide-react';
import { cn } from '../lib/utils';
import { useEffect, useState } from 'react';
import SettingsPanel from './SettingsPanel';

export default function Layout() {
  const [countdown, setCountdown] = useState(30);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const navigate = useNavigate();

  // Global 30s countdown timer for UI display
  useEffect(() => {
    const interval = setInterval(() => {
      setCountdown((prev) => (prev <= 1 ? 30 : prev - 1));
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const navItems = [
    { to: '/dashboard', icon: Activity, label: '仪表盘' },
    { to: '/signals', icon: BarChart2, label: '信号' },
    { to: '/positions', icon: TrendingUp, label: '仓位' },
    { to: '/orders', icon: FileText, label: '订单' },
    { to: '/backtest', icon: FlaskConical, label: '回测沙箱' },
    { to: '/pms-backtest', icon: BarChart2, label: 'PMS 回测' },
    { to: '/attempts', icon: Bug, label: '尝试溯源' },
    { to: '/account', icon: Wallet, label: '账户' },
    { to: '/strategies', icon: Zap, label: '策略工作台' },
    { to: '/snapshots', icon: Save, label: '配置快照' },
  ];

  return (
    <div className="min-h-screen flex flex-col">
      {/* Apple-style Glassmorphism Navbar */}
      <header className="sticky top-0 z-50 bg-white/70 backdrop-blur-xl border-b border-gray-200/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center gap-8">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 bg-black rounded-xl flex items-center justify-center text-white font-bold">
                  🐶
                </div>
                <span className="font-semibold text-lg tracking-tight">盯盘狗🐶</span>
              </div>
              
              <nav className="hidden md:flex space-x-1">
                {navItems.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={({ isActive }) =>
                      cn(
                        'flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                        isActive
                          ? 'bg-black/5 text-black'
                          : 'text-gray-500 hover:text-black hover:bg-black/5'
                      )
                    }
                  >
                    <item.icon className="w-4 h-4" />
                    {item.label}
                  </NavLink>
                ))}
              </nav>
            </div>

            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2 text-xs font-medium text-gray-500 bg-gray-100/80 px-3 py-1.5 rounded-full">
                <div className="w-2 h-2 rounded-full bg-apple-green animate-pulse" />
                <span>{countdown}s 后刷新</span>
              </div>
              <button
                onClick={() => setSettingsOpen(true)}
                className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                title="系统配置"
              >
                <Settings className="w-5 h-5 text-gray-600" />
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Settings Panel */}
      <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Outlet />
      </main>
    </div>
  );
}
