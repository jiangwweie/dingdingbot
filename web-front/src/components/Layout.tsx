import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { Activity, BarChart2, Wallet, Bug, Settings, FlaskConical, Zap, Save, FileText, TrendingUp, ChevronDown, Monitor, Briefcase, Beaker, History, Sliders, Atom } from 'lucide-react';
import { cn } from '../lib/utils';
import { useEffect, useState } from 'react';
import SettingsPanel from './SettingsPanel';

// Navigation item type
interface NavItem {
  to: string;
  icon: React.ElementType;
  label: string;
}

// Navigation category type
interface NavCategory {
  id: string;
  label: string;
  icon: React.ElementType;
  color: string;
  items: NavItem[];
}

// Navigation data with categories
// FE-01 新导航结构：监控中心 / 回测沙箱 / 策略配置 / 系统设置
const navCategories: NavCategory[] = [
  {
    id: 'monitoring',
    label: '监控中心',
    icon: Monitor,
    color: 'blue',
    items: [
      { to: '/dashboard', icon: Activity, label: '仪表盘' },
      { to: '/signals', icon: BarChart2, label: '信号' },
      { to: '/attempts', icon: Bug, label: '尝试溯源' },
    ],
  },
  {
    id: 'trading',
    label: '交易管理',
    icon: Briefcase,
    color: 'green',
    items: [
      { to: '/positions', icon: TrendingUp, label: '仓位' },
      { to: '/orders', icon: FileText, label: '订单' },
    ],
  },
  {
    id: 'backtest',
    label: '回测沙箱',
    icon: Beaker,
    color: 'purple',
    items: [
      { to: '/backtest', icon: FlaskConical, label: '回测沙箱' },
      { to: '/pms-backtest', icon: BarChart2, label: 'PMS 回测' },
      { to: '/backtest-reports', icon: History, label: '回测报告' },
    ],
  },
  {
    id: 'config',
    label: '配置管理',
    icon: Sliders,
    color: 'cyan',
    items: [
      { to: '/config', icon: Atom, label: '配置中心' },
      { to: '/snapshots', icon: Save, label: '配置快照' },
    ],
  },
  {
    id: 'settings',
    label: '系统设置',
    icon: Settings,
    color: 'gray',
    items: [
      { to: '/account', icon: Wallet, label: '账户' },
    ],
  },
];

// Color mapping for categories
const colorClasses = {
  blue: {
    bg: 'bg-blue-50',
    bgHover: 'hover:bg-blue-50',
    text: 'text-blue-700',
    border: 'border-blue-200',
    active: 'bg-blue-100',
  },
  green: {
    bg: 'bg-green-50',
    bgHover: 'hover:bg-green-50',
    text: 'text-green-700',
    border: 'border-green-200',
    active: 'bg-green-100',
  },
  purple: {
    bg: 'bg-purple-50',
    bgHover: 'hover:bg-purple-50',
    text: 'text-purple-700',
    border: 'border-purple-200',
    active: 'bg-purple-100',
  },
  cyan: {
    bg: 'bg-cyan-50',
    bgHover: 'hover:bg-cyan-50',
    text: 'text-cyan-700',
    border: 'border-cyan-200',
    active: 'bg-cyan-100',
  },
  gray: {
    bg: 'bg-gray-50',
    bgHover: 'hover:bg-gray-50',
    text: 'text-gray-700',
    border: 'border-gray-200',
    active: 'bg-gray-100',
  },
  orange: {
    bg: 'bg-orange-50',
    bgHover: 'hover:bg-orange-50',
    text: 'text-orange-700',
    border: 'border-orange-200',
    active: 'bg-orange-100',
  },
};

export default function Layout() {
  const [countdown, setCountdown] = useState(30);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [expandedCategory, setExpandedCategory] = useState<string | null>('monitoring');
  const navigate = useNavigate();

  // Global 30s countdown timer for UI display
  useEffect(() => {
    const interval = setInterval(() => {
      setCountdown((prev) => (prev <= 1 ? 30 : prev - 1));
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  // Toggle category expansion
  const toggleCategory = (categoryId: string) => {
    setExpandedCategory(expandedCategory === categoryId ? null : categoryId);
  };

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

              {/* Desktop Navigation with Categories */}
              <nav className="hidden md:flex items-center gap-1">
                {navCategories.map((category) => {
                  const CategoryIcon = category.icon;
                  const colors = colorClasses[category.color as keyof typeof colorClasses];
                  const isExpanded = expandedCategory === category.id;
                  const hasActiveItem = category.items.some(
                    (item) => window.location.pathname === item.to
                  );

                  return (
                    <div key={category.id} className="relative">
                      {/* Category Button */}
                      <button
                        onClick={() => toggleCategory(category.id)}
                        className={cn(
                          'flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-all',
                          isExpanded || hasActiveItem
                            ? `${colors.bg} ${colors.text}`
                            : 'text-gray-500 hover:bg-gray-50'
                        )}
                      >
                        <CategoryIcon className="w-4 h-4" />
                        <span>{category.label}</span>
                        <ChevronDown
                          className={cn(
                            'w-3.5 h-3.5 transition-transform',
                            isExpanded ? 'rotate-180' : ''
                          )}
                        />
                      </button>

                      {/* Dropdown Menu */}
                      {isExpanded && (
                        <div className={cn(
                          'absolute top-full left-0 mt-1 min-w-[160px] rounded-xl shadow-lg border p-1 z-50 bg-white/95 backdrop-blur-xl',
                          colors.border
                        )}>
                          {category.items.map((item) => {
                            const ItemIcon = item.icon;
                            return (
                              <NavLink
                                key={item.to}
                                to={item.to}
                                onClick={() => setExpandedCategory(null)}
                                className={({ isActive }) =>
                                  cn(
                                    'flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                                    isActive
                                      ? `${colors.active} ${colors.text}`
                                      : 'text-gray-600 hover:bg-gray-50'
                                  )
                                }
                              >
                                <ItemIcon className="w-3.5 h-3.5" />
                                {item.label}
                              </NavLink>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
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
