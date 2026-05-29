import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { Outlet, NavLink, Link, useLocation, useNavigate } from 'react-router-dom';
import {
  Bot,
  BookOpenCheck,
  ChevronDown,
  GitBranch,
  History,
  ListChecks,
  LogOut,
  Moon,
  Monitor,
  MoreHorizontal,
  PlayCircle,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Sun,
  TerminalSquare,
} from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { Badge } from '@/src/components/ui/Badge';
import { brcApi } from '@/src/services/api';
import { useTheme } from './ThemeContext';

type RefreshContextType = {
  refreshCount: number;
};
const RefreshContext = createContext<RefreshContextType>({ refreshCount: 0 });

export const useRefreshContext = () => useContext(RefreshContext);

function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  return (
    <div className="flex rounded border border-zinc-200 bg-zinc-50 p-0.5 dark:border-zinc-800 dark:bg-zinc-900">
      {[
        ['light', Sun, 'Light'],
        ['dark', Moon, 'Dark'],
        ['system', Monitor, 'System'],
      ].map(([value, Icon, title]) => (
        <button
          key={String(value)}
          onClick={() => setTheme(value as 'light' | 'dark' | 'system')}
          className={cn(
            'cursor-pointer rounded p-1',
            theme === value ? 'bg-white shadow-sm dark:bg-zinc-800' : 'hover:bg-zinc-200 dark:hover:bg-zinc-800',
          )}
          title={String(title)}
        >
          <Icon className="h-3.5 w-3.5 text-zinc-600 dark:text-zinc-400" />
        </button>
      ))}
    </div>
  );
}

const primaryNav = [
  { name: 'Command Center', to: '/command-center', icon: Monitor },
  { name: 'Markets & Orders', to: '/markets-orders', icon: ShieldCheck },
  { name: 'Campaign', to: '/campaign', icon: ListChecks },
  { name: 'Review / Evidence', to: '/review-evidence', icon: BookOpenCheck },
  { name: 'Strategy Families', to: '/strategy-families', icon: GitBranch },
];

const moreNav = [
  { name: 'Fixed Rehearsal', to: '/fixed-testnet-rehearsal', icon: PlayCircle },
  { name: 'Strategy / Playbook', to: '/strategy-playbook', icon: GitBranch },
  { name: 'Campaigns legacy', to: '/campaigns', icon: ListChecks },
  { name: 'Review legacy', to: '/review', icon: BookOpenCheck },
  { name: 'Audit Trail', to: '/audit-trail', icon: History },
  { name: 'Ledger', to: '/ledger', icon: History },
  { name: 'Guide legacy', to: '/guide', icon: ListChecks },
  { name: 'Read-only Operator', to: '/operator', icon: TerminalSquare },
  { name: 'LLM legacy', to: '/llm-copilot', icon: Bot },
  { name: 'Workflow legacy', to: '/workflow', icon: GitBranch },
  { name: 'Runtime Control', to: '/runtime-control', icon: ShieldAlert },
  { name: 'Developer Detail', to: '/developer', icon: TerminalSquare },
];

const routeTitles: Record<string, string> = {
  '/command-center': 'Command Center',
  '/markets-orders': 'Markets & Orders',
  '/campaign': 'Campaign',
  '/review-evidence': 'Review / Evidence',
  '/strategy-families': 'Strategy Families',
  '/fixed-testnet-rehearsal': 'Fixed Testnet Rehearsal',
  '/llm-copilot': 'LLM legacy',
  '/strategy-playbook': 'Strategy / Playbook',
  '/risk-account': 'Risk & Account legacy',
  '/runtime-control': 'Runtime Control legacy',
  '/guide': 'Guide legacy',
  '/operator': 'Read-only Operator legacy',
  '/workflow': 'Workflow legacy',
  '/review': 'Review legacy',
  '/ledger': 'Ledger',
  '/campaigns': 'Campaigns legacy',
  '/audit-trail': 'Audit Trail',
  '/developer': 'Developer Detail',
};

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
      <div className="flex h-screen w-full overflow-hidden bg-white font-sans text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
        <aside className="z-20 flex w-56 flex-shrink-0 flex-col border-r border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900">
          <div className="border-b border-zinc-200 p-4 dark:border-zinc-800">
            <Link to="/command-center" className="block">
              <h1 className="text-sm font-bold text-zinc-900 dark:text-zinc-100">BRC Console</h1>
              <p className="mt-1 text-[10px] font-bold uppercase tracking-widest text-zinc-500">Local Owner</p>
            </Link>
          </div>

          <nav className="flex-1 overflow-y-auto px-2 py-3">
            <p className="mb-2 px-2 text-[10px] font-bold uppercase tracking-widest text-zinc-400">Phase 0</p>
            <ul className="space-y-1">
              {primaryNav.map((link) => (
                <NavItem key={link.to} {...link} />
              ))}
            </ul>

            <details className="mt-5" open={moreNav.some((item) => item.to === location.pathname)}>
              <summary className="flex cursor-pointer list-none items-center justify-between px-2 text-[10px] font-bold uppercase tracking-widest text-zinc-400">
                <span className="flex items-center gap-1.5"><MoreHorizontal className="h-3 w-3" /> Legacy / Developer</span>
                <ChevronDown className="h-3 w-3" />
              </summary>
              <ul className="mt-2 space-y-1">
                {moreNav.map((link) => (
                  <NavItem key={link.to} {...link} compact />
                ))}
              </ul>
            </details>
          </nav>

          <div className="space-y-2 border-t border-zinc-200 p-3 dark:border-zinc-800">
            <div className="flex items-center justify-between">
              <Badge variant="info">{displayValue(boundary, 'trading_env', displayValue(boundary, 'current', 'unknown'))}</Badge>
              <Badge variant={displayValue(boundary, 'resolved_permission', 'read_only') === 'intent_recording' ? 'warning' : 'outline'}>
                {permissionDisplay(boundary)}
              </Badge>
            </div>
            <p className="text-[10px] leading-4 text-zinc-500">
              Owner view is read-only for trading. Live 只读 / Intent Recording does not mean live trading enabled.
            </p>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col bg-white dark:bg-[#09090b]">
          <header className="z-10 flex h-12 items-center justify-between border-b border-zinc-200 bg-white px-4 dark:border-zinc-800 dark:bg-zinc-950">
            <div className="flex items-center gap-3">
              <h2 className="text-sm font-bold text-zinc-900 dark:text-zinc-100">
                {routeTitles[location.pathname] || 'BRC Console'}
              </h2>
              <Badge variant="outline">TRADING_ENV {displayValue(boundary, 'trading_env', 'unknown')}</Badge>
              <Badge variant={displayValue(boundary, 'order_allowed', 'false') === 'true' ? 'danger' : 'success'}>
                orders {displayValue(boundary, 'order_allowed', 'false') === 'true' ? 'allowed' : 'disabled'}
              </Badge>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={handleManualRefresh}
                className="inline-flex items-center gap-1.5 rounded-sm border border-zinc-300 px-2.5 py-1.5 text-xs font-medium text-zinc-700 transition-colors hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                刷新
              </button>
              <ThemeToggle />
              <button
                onClick={logout}
                className="inline-flex items-center gap-1.5 rounded-sm border border-zinc-300 px-2.5 py-1.5 text-xs font-medium text-zinc-700 transition-colors hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
              >
                <LogOut className="h-3.5 w-3.5" />
                退出
              </button>
            </div>
          </header>

          <main className="flex-1 overflow-y-auto p-4">
            <Outlet />
          </main>
        </div>
      </div>
    </RefreshContext.Provider>
  );
}

function displayValue(source: Record<string, unknown> | null, key: string, fallback: string): string {
  const value = source?.[key];
  if (value === undefined || value === null || value === '') return fallback;
  return String(value);
}

function permissionDisplay(boundary: Record<string, unknown> | null): string {
  const permission = displayValue(boundary, 'resolved_permission', 'read_only');
  const liveReadOnly = displayValue(boundary, 'live_read_only', 'false') === 'true';
  if (liveReadOnly && permission === 'intent_recording') return 'Live 只读 / Intent Recording';
  return permission;
}

function NavItem({
  name,
  to,
  icon: Icon,
  compact = false,
}: {
  name: string;
  to: string;
  icon: React.ComponentType<{ className?: string }>;
  compact?: boolean;
}) {
  return (
    <li>
      <NavLink
        to={to}
        className={({ isActive }) => cn(
          'flex items-center gap-2 rounded-sm px-2 text-sm font-medium transition-colors',
          compact ? 'py-1.5 text-xs' : 'py-2.5',
          isActive
            ? 'bg-blue-600 text-white'
            : 'text-zinc-600 hover:bg-zinc-200/70 hover:text-zinc-950 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100',
        )}
      >
        <Icon className="h-4 w-4" />
        {name}
      </NavLink>
    </li>
  );
}
