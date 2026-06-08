import React, { useEffect, useState } from 'react';
import { Outlet, NavLink } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { LayoutDashboard, Users, List, Box, ShieldCheck, PlayCircle, Activity, History, Server, LineChart, Moon, Sun, Menu, ShieldAlert, LogOut, Target } from 'lucide-react';
import { Badge, DataStatusLine, FreshnessBadge, ReadModelErrorPanel } from './ui';
import { useReadModel } from '@/lib/tradingConsoleApi';
import { useAuth } from '@/lib/auth';

const NAV_ITEMS = [
  { name: 'Cockpit', path: '/', icon: LayoutDashboard },
  { name: '账户总览', path: '/account', icon: Users },
  { name: '订单台账', path: '/ledger', icon: List },
  { name: '保护健康', path: '/protection', icon: ShieldAlert },
  { name: '行动对象', path: '/carrier', icon: Box },
  { name: '有界实盘授权', path: '/authorization', icon: ShieldCheck },
  { name: '实盘执行控制', path: '/execution', icon: PlayCircle },
  { name: '行动入口', path: '/action-entry', icon: Target },
  { name: '异常恢复', path: '/recovery', icon: Activity },
  { name: '实盘复盘', path: '/review', icon: History },
  { name: '技术审计', path: '/audit', icon: Server },
  { name: '信号图表预留', path: '/signals', icon: LineChart },
];

export function AppShell() {
  const [darkMode, setDarkMode] = useState(() => document.documentElement.classList.contains('dark'));
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const { session, logout } = useAuth();
  const { envelope: envData, error } = useReadModel<any>('/api/trading-console/operations-cockpit?include_exchange=true');
  const environment = envData?.data?.evidence?.environment || {};
  const overall = envData?.data?.overall_status || {};
  const updatedAt = envData?.generated_at_ms ? new Date(envData.generated_at_ms).toLocaleTimeString() : '未知';
  const envLabel = environment.trading_env === 'testnet'
    ? '测试'
    : environment.exchange_testnet === false
      ? '实盘只读'
      : '未知';

  useEffect(() => {
    if (darkMode) document.documentElement.classList.add('dark');
    else document.documentElement.classList.remove('dark');
  }, [darkMode]);

  return (
    <div className="min-h-screen flex flex-col md:flex-row bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100">

      {/* Mobile Header */}
      <div className="md:hidden flex flex-col sticky top-0 z-20">
        <div className="flex items-center justify-between p-4 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
          <div>
            <div className="font-semibold">交易控制台</div>
            <div className="text-xs text-slate-500">子账户：BNB 行动账户 · {envLabel}</div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setDarkMode(!darkMode)} className="p-2 rounded-md bg-slate-100 dark:bg-slate-800">
              {darkMode ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>
            <button onClick={() => setMobileMenuOpen(!mobileMenuOpen)} className="p-2 rounded-md bg-slate-100 dark:bg-slate-800">
              <Menu className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Sidebar */}
      <aside className={cn(
        "fixed md:relative top-0 left-0 h-screen w-64 bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 flex flex-col z-30 transition-transform md:translate-x-0 overflow-y-auto",
        mobileMenuOpen ? "translate-x-0" : "-translate-x-full"
      )}>
        <div className="p-4 border-b border-slate-200 dark:border-slate-800 hidden md:flex items-center justify-between">
          <span className="font-semibold font-mono tracking-tight">交易控制台</span>
          <button onClick={() => setDarkMode(!darkMode)} className="p-1 px-2 text-xs rounded border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 transition">
            {darkMode ? 'Light' : 'Dark'}
          </button>
        </div>
        <nav className="flex-1 p-2 space-y-1">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              onClick={() => setMobileMenuOpen(false)}
              className={({ isActive }) => cn(
                "flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors",
                isActive
                  ? "bg-slate-100 dark:bg-slate-800 text-blue-600 dark:text-blue-400 font-medium"
                  : "text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800/50"
              )}
            >
              <item.icon className="w-4 h-4" />
              {item.name}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-slate-200 dark:border-slate-800 p-3">
          <div className="text-xs text-slate-500 dark:text-slate-400 mb-2">
            登录：{session?.username || 'Operator'}
          </div>
          <button
            onClick={logout}
            className="w-full flex items-center gap-2 rounded-md border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition"
          >
            <LogOut className="w-4 h-4" />
            退出登录
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden">

        {/* Global Owner Status Bar */}
        <div className={cn(
          "px-4 py-2 text-xs border-b border-slate-200 dark:border-slate-800 flex flex-wrap items-center gap-3 transition-colors shrink-0",
          envData?.blockers?.length > 0 ? "bg-rose-50 dark:bg-rose-900/20" :
          envData?.freshness_status === 'degraded' || envData?.freshness_status === 'warning' || envData?.warnings?.length > 0 ? "bg-amber-50 dark:bg-amber-900/20" :
          envData?.freshness_status === 'not_live_connected' ? "bg-slate-50 dark:bg-slate-900" :
          "bg-white dark:bg-slate-900"
        )}>
          <span className="font-semibold text-slate-700 dark:text-slate-200">交易控制台</span>
          <span className="text-slate-400">·</span>
          <span className="text-slate-600 dark:text-slate-300">子账户：BNB 行动账户</span>
          <Badge variant="muted">只读</Badge>
          <span className="text-slate-600 dark:text-slate-300">环境：{envLabel}</span>
          {envData?.freshness_status && <FreshnessBadge status={envData.freshness_status} />}
          {overall.status && <span className="font-semibold text-slate-700 dark:text-slate-200">状态：{overall.label || overall.status}</span>}
          {envData?.blockers?.length > 0 && <span className="font-semibold text-red-600 dark:text-red-400">存在阻断项</span>}
          {error && <span className="font-semibold text-red-600 dark:text-red-400">当前内容暂不可用</span>}
          <div className="ml-auto flex items-center gap-3 text-slate-500">
            <DataStatusLine envelope={envData} />
            <span>更新时间：{updatedAt}</span>
          </div>
        </div>

        <div className="flex-1 overflow-auto p-4 md:p-8">
          <ReadModelErrorPanel error={error} />
          <Outlet />
        </div>
      </main>

      {/* Mobile Overlay */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 bg-black/20 dark:bg-black/40 z-10 md:hidden"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}
    </div>
  );
}
