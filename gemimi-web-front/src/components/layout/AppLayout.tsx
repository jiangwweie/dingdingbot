import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  BarChart3,
  GitBranch,
  Home,
  LogOut,
  Monitor,
  Moon,
  RefreshCw,
  Route,
  SquarePlus,
  Sun,
  User,
  Wallet,
  Zap,
} from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { brcApi } from '@/src/services/api';
import { useTheme } from './ThemeContext';

type RefreshContextType = {
  refreshCount: number;
};

const RefreshContext = createContext<RefreshContextType>({ refreshCount: 0 });

export const useRefreshContext = () => useContext(RefreshContext);

const primaryNav = [
  { name: '首页', to: '/home', icon: Home },
  { name: '发起试验', to: '/trial-confirmation', icon: SquarePlus },
  { name: '策略候选', to: '/strategy-candidates', icon: GitBranch },
  { name: '执行计划', to: '/intents', icon: Zap },
  { name: '账户与订单', to: '/account-orders', icon: Wallet },
  { name: '复盘', to: '/analysis', icon: BarChart3 },
  { name: '链路追踪', to: '/trace', icon: Route },
];

export default function AppLayout() {
  const [refreshCount, setRefreshCount] = useState(0);
  const [boundary, setBoundary] = useState<Record<string, unknown> | null>(null);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    brcApi.readiness()
      .then((payload) => {
        if (!cancelled) setBoundary(payload.environment_boundary || {});
      })
      .catch(() => {
        if (!cancelled) setBoundary(null);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshCount, location.pathname]);

  const handleManualRefresh = useCallback(() => {
    setRefreshCount((count) => count + 1);
  }, []);

  async function logout() {
    await brcApi.logout().catch(() => undefined);
    navigate('/login', { replace: true });
  }

  return (
    <RefreshContext.Provider value={{ refreshCount }}>
      <div className="flex h-screen w-full flex-col overflow-hidden bg-slate-50 font-sans text-slate-950 dark:bg-slate-950 dark:text-slate-50">
        <header className="flex h-16 flex-shrink-0 items-center justify-between border-b border-amber-500/25 bg-white px-6 shadow-[0_1px_0_rgba(245,158,11,0.12)] dark:border-amber-500/15 dark:bg-slate-950">
          <div className="flex items-center gap-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-amber-400/40 bg-amber-500 text-lg font-bold text-slate-950 shadow-[0_0_18px_rgba(245,158,11,0.25)]">
              SC
            </div>
            <div>
              <h1 className="text-base font-bold leading-none text-slate-950 dark:text-slate-50">策略控制台</h1>
              <p className="mt-1 text-xs text-amber-700 dark:text-amber-200/75">Owner decision cockpit</p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <StatusCapsule boundary={boundary} />
            <div className="hidden h-6 w-px bg-amber-500/20 md:block" />
            <ThemeToggle />
            <button
              onClick={handleManualRefresh}
              title="刷新状态"
              className="cursor-pointer rounded-lg p-2 text-slate-500 transition-colors duration-200 hover:bg-amber-50 hover:text-amber-700 focus:outline-none focus:ring-2 focus:ring-amber-400/50 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-amber-300"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-full border border-purple-400/30 bg-purple-50 text-purple-700 dark:bg-purple-500/10 dark:text-purple-200">
                <User className="h-4 w-4" />
              </div>
              <span className="hidden text-sm font-medium text-slate-700 dark:text-slate-200 md:inline">Owner</span>
            </div>
          </div>
        </header>

        <main className="flex min-h-0 flex-1 overflow-hidden">
          <aside className="flex w-52 flex-shrink-0 flex-col gap-4 border-r border-amber-500/20 bg-white p-4 dark:border-amber-500/15 dark:bg-slate-950 md:w-64 md:p-6">
            <nav className="flex flex-col gap-1">
              {primaryNav.map((link) => (
                <NavItem key={link.to} {...link} />
              ))}
            </nav>
            <div className="mt-auto border-t border-amber-500/20 pt-4 dark:border-amber-500/15">
              <button
                onClick={logout}
                className="flex w-full cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-500 transition-colors duration-200 hover:bg-amber-50 hover:text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-400/50 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-amber-100"
              >
                <LogOut className="h-4.5 w-4.5 text-slate-500" />
                退出登录
              </button>
            </div>
          </aside>

          <section className="min-w-0 flex-1 overflow-y-auto bg-slate-50 p-4 dark:bg-slate-950 md:p-6">
            <div className="mx-auto flex max-w-[1440px] flex-col gap-6">
              <Outlet />
            </div>
          </section>
        </main>
      </div>
    </RefreshContext.Provider>
  );
}

function StatusCapsule({ boundary }: { boundary: Record<string, unknown> | null }) {
  const [open, setOpen] = useState(false);
  const env = displayValue(boundary, 'trading_env', displayValue(boundary, 'current', '暂未上报'));
  const permission = displayValue(boundary, 'resolved_permission', displayValue(boundary, 'brc_execution_permission_max', '暂未上报'));
  const liveReadOnly = displayBoolean(boundary?.live_read_only, env === 'live');
  const orderAllowed = displayBoolean(boundary?.order_allowed, false);
  const intentAllowed = displayBoolean(boundary?.execution_intent_allowed, false);
  const label = liveReadOnly ? '实盘只读 · 记录意图' : '只读观察中';
  const tooltip = '当前连接真实市场，只记录信号和执行意图。不会创建执行指令，也不会下单。';

  return (
    <div className="relative">
      <button
        type="button"
        title={tooltip}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onClick={() => setOpen((value) => !value)}
        className="flex cursor-pointer items-center gap-2 rounded-full border border-amber-400/45 bg-amber-50 px-3 py-1.5 text-sm font-medium text-amber-900 transition-colors duration-200 hover:bg-amber-100 focus:outline-none focus:ring-2 focus:ring-amber-400/50 dark:border-amber-400/35 dark:bg-amber-500/10 dark:text-amber-100 dark:hover:bg-amber-500/15"
      >
        <span className="h-2 w-2 rounded-full bg-amber-400 shadow-[0_0_10px_rgba(245,158,11,0.8)]" />
        {label}
        <span className="text-amber-700/50 dark:text-amber-200/50">·</span>
        禁止下单
      </button>
      {open ? (
        <div
          onMouseEnter={() => setOpen(true)}
          onMouseLeave={() => setOpen(false)}
          className="absolute right-0 top-full z-50 mt-2 w-72 rounded-xl border border-amber-500/25 bg-white p-4 text-sm shadow-xl shadow-slate-900/10 dark:border-amber-500/20 dark:bg-slate-950 dark:shadow-black/40"
        >
          <h3 className="mb-2 text-sm font-bold text-slate-900 dark:text-slate-100">当前模式：实盘只读</h3>
          <div className="space-y-2 text-xs text-slate-600 dark:text-slate-300">
            <StatusRow label="市场环境" value={env === 'live' ? '实盘只读' : env} />
            <StatusRow label="权限" value={permission === 'intent_recording' ? '记录意图' : permission} />
            <StatusRow label="下单" value={orderAllowed ? '已开放' : '禁止'} danger={orderAllowed} />
            <StatusRow label="执行指令" value={intentAllowed ? '已开放' : '禁止'} danger={intentAllowed} />
            <StatusRow label="最近检查" value={new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })} muted />
          </div>
          <p className="mt-3 border-t border-amber-500/15 pt-3 text-xs leading-5 text-slate-500 dark:text-slate-400">
            当前连接真实市场，只记录信号和执行意图。不会创建执行指令，也不会下单。
          </p>
        </div>
      ) : null}
    </div>
  );
}

function StatusRow({ label, value, danger, muted }: { label: string; value: string; danger?: boolean; muted?: boolean }) {
  return (
    <div className={cn('flex justify-between gap-3', muted && 'text-slate-500')}>
      <span>{label}：</span>
      <span className={cn(
        'font-medium text-slate-900 dark:text-slate-100',
        danger && 'text-red-400',
        muted && 'text-slate-500',
      )}>
        {value}
      </span>
    </div>
  );
}

function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  return (
    <div className="flex items-center gap-1 rounded-lg border border-amber-500/25 bg-amber-50 p-1 dark:border-amber-500/15 dark:bg-slate-900">
      {[
        ['light', Sun, '浅色模式'],
        ['dark', Moon, '深色模式'],
        ['system', Monitor, '跟随系统'],
      ].map(([value, Icon, title]) => (
        <button
          key={String(value)}
          onClick={() => setTheme(value as 'light' | 'dark' | 'system')}
          className={cn(
            'cursor-pointer rounded-md p-1.5 transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-amber-400/50',
            theme === value
              ? 'bg-purple-500 text-white shadow-sm'
              : 'text-slate-500 hover:text-amber-800 dark:text-slate-400 dark:hover:text-amber-100',
          )}
          title={String(title)}
        >
          <Icon className="h-3.5 w-3.5" />
        </button>
      ))}
    </div>
  );
}

function NavItem({
  name,
  to,
  icon: Icon,
}: {
  name: string;
  to: string;
  icon: React.ComponentType<{ className?: string }>;
}) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) => cn(
        'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-amber-400/50',
        isActive
          ? 'bg-purple-100 text-amber-900 shadow-[inset_3px_0_0_rgba(245,158,11,0.95)] dark:bg-purple-500/15 dark:text-amber-100'
          : 'text-slate-500 hover:bg-amber-50 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-100',
      )}
    >
      {({ isActive }) => (
        <>
          <Icon className={cn('h-4.5 w-4.5', isActive ? 'text-amber-600 dark:text-amber-300' : 'text-slate-500')} />
          {name}
        </>
      )}
    </NavLink>
  );
}

function displayValue(source: Record<string, unknown> | null, key: string, fallback: string): string {
  const value = source?.[key];
  if (value === undefined || value === null || value === '') return fallback;
  return String(value);
}

function displayBoolean(value: unknown, fallback: boolean) {
  if (typeof value === 'boolean') return value;
  return fallback;
}
