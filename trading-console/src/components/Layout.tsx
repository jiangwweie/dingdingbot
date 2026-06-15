import React, { useState } from 'react';
import { Outlet, NavLink } from 'react-router-dom';
import { cn } from '@/lib/utils';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  CircleCheck,
  CircleDot,
  Database,
  FolderSearch,
  Home,
  Layers3,
  ListChecks,
  LogOut,
  Menu,
  RadioTower,
  ShieldCheck,
} from 'lucide-react';
import { DataStatusLine, FreshnessBadge, ReadModelErrorPanel } from './ui';
import { useReadModel } from '@/lib/tradingConsoleApi';
import { useAuth } from '@/lib/auth';
import { StatusChip, type ConsoleTone } from './console/ConsolePrimitives';
import { ThemeToggle } from './ThemeToggle';

const NAV_ITEMS = [
  { name: '控制总览', path: '/', icon: Home },
  { name: 'Pilot', path: '/pilot', icon: CircleDot },
  { name: '策略库', path: '/strategy', icon: Layers3 },
  { name: '策略接入', path: '/strategy-intake', icon: Database },
  { name: '运行治理', path: '/runtime', icon: ShieldCheck },
  { name: '信号监测', path: '/watcher', icon: RadioTower },
  { name: '交易与仓位', path: '/trades', icon: ListChecks },
  { name: '分析', path: '/analysis', icon: BarChart3 },
  { name: '异常介入', path: '/incident', icon: AlertTriangle },
  { name: '证据', path: '/evidence', icon: FolderSearch },
];

function ownerStatusTone(envelope: any, error: string | null): ConsoleTone {
  if (error || envelope?.blockers?.length > 0) return 'intervention';
  if (
    envelope?.freshness_status === 'degraded'
    || envelope?.freshness_status === 'warning'
    || envelope?.freshness_status === 'not_live_connected'
    || envelope?.warnings?.length > 0
    || envelope?.unavailable?.length > 0
  ) {
    return 'attention';
  }
  return 'normal';
}

function ownerStatusLabel(tone: ConsoleTone): string {
  if (tone === 'intervention' || tone === 'blocked') return '需要介入';
  if (tone === 'attention') return '有待关注项';
  return '当前无需操作';
}

export function AppShell() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const { session, logout } = useAuth();
  const { envelope: envData, error } = useReadModel<any>('/api/trading-console/operations-cockpit?include_exchange=true');
  const environment = envData?.data?.evidence?.environment || {};
  const overall = envData?.data?.overall_status || {};
  const updatedAt = envData?.generated_at_ms ? new Date(envData.generated_at_ms).toLocaleTimeString('zh-CN', { hour12: false }) : '未知';
  const envLabel = environment.trading_env === 'testnet'
    ? '测试'
    : environment.exchange_testnet === false
      ? '实盘受控'
      : '未知';
  const ownerTone = ownerStatusTone(envData, error);

  return (
    <div className="console-surface flex min-h-screen flex-col text-slate-100 md:flex-row">

      {/* Mobile Header */}
      <div className="md:hidden flex flex-col sticky top-0 z-20">
        <div className="flex items-center justify-between border-b border-slate-800 bg-slate-950/95 p-4">
          <div>
            <div className="font-semibold">BRC Owner Console</div>
            <div className="text-xs text-slate-500">策略运行账户 · {envLabel}</div>
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle compact />
            <button onClick={() => setMobileMenuOpen(!mobileMenuOpen)} className="cursor-pointer rounded-md border border-slate-700 bg-slate-900 p-2 text-slate-300">
              <Menu className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Sidebar */}
      <aside className={cn(
        "fixed md:relative top-0 left-0 h-screen w-64 bg-slate-950/95 border-r border-slate-800 flex flex-col z-30 transition-transform md:translate-x-0 overflow-y-auto console-scrollbar",
        mobileMenuOpen ? "translate-x-0" : "-translate-x-full"
      )}>
        <div className="hidden min-h-[72px] items-center justify-between border-b border-slate-800 px-5 md:flex">
          <div className="flex items-center gap-3">
            <CircleDot className="h-6 w-6 text-slate-400" />
            <div>
              <div className="text-lg font-semibold leading-5">BRC</div>
              <div className="text-[10px] font-medium uppercase text-slate-500">Owner Console</div>
            </div>
          </div>
          <ThemeToggle compact />
        </div>
        <nav className="flex-1 p-2 space-y-1">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              onClick={() => setMobileMenuOpen(false)}
              className={({ isActive }) => cn(
                "flex min-h-11 items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                isActive
                  ? "bg-slate-800/80 text-slate-50 shadow-[3px_0_0_#7ca7ff_inset]"
                  : "text-slate-400 hover:bg-slate-900/80 hover:text-slate-100"
              )}
            >
              <item.icon className="w-4 h-4" />
              {item.name}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-slate-800 p-3">
          <div className="mb-2 text-xs text-slate-500">
            登录：{session?.username || 'Operator'}
          </div>
          <button
            onClick={logout}
            className="flex w-full cursor-pointer items-center gap-2 rounded-md border border-slate-700 px-3 py-2 text-sm text-slate-300 transition hover:bg-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <LogOut className="w-4 h-4" />
            退出登录
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden">

        {/* Global Owner Status Bar */}
        <div className="flex min-h-[72px] shrink-0 flex-wrap items-center gap-3 border-b border-slate-800 bg-slate-950/70 px-4 py-3 text-xs backdrop-blur md:px-7">
          <button
            type="button"
            className="hidden cursor-pointer rounded-md border border-slate-800 p-2 text-slate-500 transition hover:bg-slate-900 hover:text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500 md:inline-flex"
            aria-label="导航状态"
          >
            <Menu className="h-4 w-4" />
          </button>
          <div className="flex min-w-0 items-center gap-3">
            <StatusChip tone={ownerTone} className="shrink-0">
              {ownerTone === 'normal' ? <CircleCheck className="h-3.5 w-3.5" /> : <Activity className="h-3.5 w-3.5" />}
              {ownerStatusLabel(ownerTone)}
            </StatusChip>
            {envData?.freshness_status && <FreshnessBadge status={envData.freshness_status} />}
            <span className="hidden text-slate-500 lg:inline">更新于 {updatedAt}</span>
          </div>
          <div className="ml-auto flex min-w-0 items-center gap-3 text-slate-500">
            <span className="hidden sm:inline">环境：{envLabel}</span>
            {overall.label && <span className="hidden truncate text-slate-300 md:inline">状态：{overall.label}</span>}
            <DataStatusLine envelope={envData} />
            {error && <span className="font-semibold text-rose-300">当前内容暂不可用</span>}
            <ThemeToggle />
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-800 text-xs font-semibold text-slate-200">
              OW
            </div>
            <span className="hidden text-slate-300 sm:inline">Owner</span>
          </div>
        </div>

        <div className="flex-1 overflow-auto p-4 md:p-7 console-scrollbar">
          <ReadModelErrorPanel error={error} />
          <Outlet />
        </div>
      </main>

      {/* Mobile Overlay */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-10 md:hidden"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}
    </div>
  );
}
