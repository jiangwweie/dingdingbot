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
  { name: '策略组', to: '/strategy-groups', icon: GitBranch },
  { name: '执行意图', to: '/intents', icon: Zap },
  { name: '账户订单', to: '/account-orders', icon: Wallet },
  { name: '复盘分析', to: '/analysis', icon: BarChart3 },
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
      <div className="flex h-screen w-full flex-col overflow-hidden bg-slate-100 font-sans text-slate-900 dark:bg-slate-950 dark:text-slate-100">
        <header className="flex h-16 flex-shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6 dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center gap-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded bg-indigo-600 text-lg font-bold text-white">
              SC
            </div>
            <div>
              <h1 className="text-base font-bold leading-none text-slate-950 dark:text-white">策略控制台</h1>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">v2 主控工作台</p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <StatusCapsule boundary={boundary} />
            <div className="hidden h-6 w-px bg-slate-200 dark:bg-slate-800 md:block" />
            <ThemeToggle />
            <button
              onClick={handleManualRefresh}
              title="刷新状态"
              className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-slate-100 hover:text-indigo-600 dark:hover:bg-slate-800 dark:hover:text-indigo-400"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-full border border-slate-200 bg-slate-100 text-slate-500 dark:border-slate-700 dark:bg-slate-800">
                <User className="h-4 w-4" />
              </div>
              <span className="hidden text-sm font-medium text-slate-700 dark:text-slate-300 md:inline">Owner</span>
            </div>
          </div>
        </header>

        <main className="flex min-h-0 flex-1 overflow-hidden">
          <aside className="flex w-52 flex-shrink-0 flex-col gap-4 border-r border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900 md:w-64 md:p-6">
            <nav className="flex flex-col gap-1">
              {primaryNav.map((link) => (
                <NavItem key={link.to} {...link} />
              ))}
            </nav>
            <div className="mt-auto border-t border-slate-100 pt-4 dark:border-slate-800">
              <button
                onClick={logout}
                className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-500 transition-colors hover:bg-slate-50 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800/50 dark:hover:text-slate-200"
              >
                <LogOut className="h-4.5 w-4.5 text-slate-400 dark:text-slate-500" />
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
        className="flex items-center gap-2 rounded-full border border-teal-200/70 bg-teal-50 px-3 py-1.5 text-sm font-medium text-teal-900 transition-colors hover:bg-teal-100 dark:border-teal-900/50 dark:bg-teal-950/30 dark:text-teal-400 dark:hover:bg-teal-900/50"
      >
        <span className="h-2 w-2 rounded-full bg-teal-500 shadow-[0_0_8px_rgba(20,184,166,0.65)]" />
        {label}
        <span className="text-slate-400">·</span>
        禁止下单
      </button>
      {open ? (
        <div
          onMouseEnter={() => setOpen(true)}
          onMouseLeave={() => setOpen(false)}
          className="absolute right-0 top-full z-50 mt-2 w-72 rounded-lg border border-slate-200 bg-white p-4 text-sm shadow-lg dark:border-slate-700 dark:bg-slate-900"
        >
          <h3 className="mb-2 text-sm font-bold text-slate-800 dark:text-slate-200">当前模式：实盘只读</h3>
          <div className="space-y-2 text-xs text-slate-600 dark:text-slate-400">
            <StatusRow label="市场环境" value={env === 'live' ? '实盘只读' : env} />
            <StatusRow label="权限" value={permission === 'intent_recording' ? '记录意图' : permission} />
            <StatusRow label="下单" value={orderAllowed ? '已开放' : '禁止'} danger={orderAllowed} />
            <StatusRow label="执行指令" value={intentAllowed ? '已开放' : '禁止'} danger={intentAllowed} />
            <StatusRow label="最近检查" value={new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })} muted />
          </div>
          <p className="mt-3 border-t border-slate-100 pt-3 text-xs leading-5 text-slate-500 dark:border-slate-800 dark:text-slate-400">
            当前连接真实市场，只记录信号和执行意图。不会创建执行指令，也不会下单。
          </p>
        </div>
      ) : null}
    </div>
  );
}

function StatusRow({ label, value, danger, muted }: { label: string; value: string; danger?: boolean; muted?: boolean }) {
  return (
    <div className={cn('flex justify-between gap-3', muted && 'text-slate-400 dark:text-slate-500')}>
      <span>{label}：</span>
      <span className={cn(
        'font-medium text-slate-900 dark:text-slate-200',
        danger && 'text-red-600 dark:text-red-400',
        muted && 'text-slate-400 dark:text-slate-500',
      )}>
        {value}
      </span>
    </div>
  );
}

function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  return (
    <div className="flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-100 p-1 dark:border-slate-700 dark:bg-slate-800">
      {[
        ['light', Sun, '浅色模式'],
        ['dark', Moon, '深色模式'],
        ['system', Monitor, '跟随系统'],
      ].map(([value, Icon, title]) => (
        <button
          key={String(value)}
          onClick={() => setTheme(value as 'light' | 'dark' | 'system')}
          className={cn(
            'rounded-md p-1.5 transition-colors',
            theme === value
              ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-slate-100'
              : 'text-slate-500 hover:text-slate-900 dark:hover:text-slate-300',
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
        'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
        isActive
          ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-400'
          : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800/50 dark:hover:text-slate-200',
      )}
    >
      {({ isActive }) => (
        <>
          <Icon className={cn('h-4.5 w-4.5', isActive ? 'text-indigo-600 dark:text-indigo-400' : 'text-slate-400 dark:text-slate-500')} />
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
