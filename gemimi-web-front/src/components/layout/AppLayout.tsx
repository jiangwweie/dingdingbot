import React, { createContext, useContext, useState, useCallback } from 'react';
import { Outlet, NavLink, useLocation, useNavigate } from 'react-router-dom';
import {
  BookOpenCheck,
  GitBranch,
  History,
  ListChecks,
  LogOut,
  Moon,
  Monitor,
  RefreshCw,
  ShieldAlert,
  Sun,
  TerminalSquare,
} from 'lucide-react';
import { cn } from '@/src/lib/utils';
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
        ['light', Sun, 'Light Mode'],
        ['dark', Moon, 'Dark Mode'],
        ['system', Monitor, 'System Preference'],
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

const navItems = [
  {
    domain: 'BRC Campaign（风险试错）',
    links: [
      { name: 'Guide 操作向导', to: '/guide', icon: ListChecks },
      { name: 'Runtime Safety 运行安全', to: '/runtime-safety', icon: ShieldAlert },
      { name: 'Operator Plan 只读计划', to: '/operator', icon: TerminalSquare },
      { name: 'Workflow 受控流程', to: '/workflow', icon: GitBranch },
      { name: 'Review 复盘决策', to: '/review', icon: BookOpenCheck },
      { name: 'Ledger 操作记录', to: '/ledger', icon: History },
      { name: 'Developer Detail 技术详情', to: '/developer', icon: TerminalSquare },
    ],
  },
];

const routeTitles: Record<string, string> = {
  '/guide': 'Guide 操作向导',
  '/operator': 'Operator Plan 只读计划',
  '/workflow': 'Workflow 受控流程',
  '/review': 'Review 复盘决策',
  '/ledger': 'Ledger 操作记录',
  '/runtime-safety': 'Runtime Safety 运行安全',
  '/developer': 'Developer Detail 技术详情',
};

export default function AppLayout() {
  const [refreshCount, setRefreshCount] = useState(0);
  const location = useLocation();
  const navigate = useNavigate();

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
        <aside className="z-20 flex w-64 flex-shrink-0 flex-col border-r border-zinc-200 bg-zinc-50/50 dark:border-zinc-800 dark:bg-zinc-900/30">
          <div className="border-b border-zinc-200 bg-zinc-100/50 p-4 py-3 dark:border-zinc-800 dark:bg-zinc-900/80">
            <h1 className="text-[11px] font-bold uppercase tracking-widest text-blue-500">BRC Operator</h1>
            <div className="mt-1 flex items-center gap-2">
              <div className="h-1.5 w-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]" />
              <p className="font-mono text-[10px] uppercase tracking-tighter text-zinc-500">Local Console</p>
            </div>
          </div>

          <nav className="flex-1 space-y-6 overflow-y-auto px-2 py-4">
            {navItems.map((group) => (
              <div key={group.domain}>
                <p className="mb-1.5 px-2 text-[10px] font-bold uppercase tracking-widest text-zinc-400 dark:text-zinc-500">
                  {group.domain}
                </p>
                <ul className="space-y-0.5">
                  {group.links.map((link) => {
                    const Icon = link.icon;
                    return (
                      <li key={link.to}>
                        <NavLink
                          to={link.to}
                          className={({ isActive }) => cn(
                            'flex items-center gap-2 rounded-sm border-l-2 px-2 py-[6px] text-[11px] font-medium transition-colors',
                            isActive
                              ? 'border-blue-500 bg-blue-600/10 font-bold text-blue-500 dark:text-blue-400'
                              : 'border-transparent text-zinc-600 hover:bg-zinc-200/50 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800/50 dark:hover:text-zinc-100',
                          )}
                        >
                          <Icon className="h-3.5 w-3.5" />
                          {link.name}
                        </NavLink>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </nav>

          <div className="border-t border-zinc-200 bg-zinc-100/50 p-3 dark:border-zinc-800 dark:bg-zinc-900/50">
            <p className="text-[10px] leading-4 text-zinc-500">
              Live / withdrawal / strategy execution: <span className="font-bold text-rose-500">unauthorized</span>
            </p>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col bg-white dark:bg-[#09090b]">
          <header className="z-10 flex h-[38px] items-center justify-between border-b border-zinc-200 bg-zinc-50/80 px-4 backdrop-blur-sm dark:border-zinc-800 dark:bg-zinc-900/80">
            <div className="flex items-center space-x-3">
              <h2 className="text-xs font-bold uppercase tracking-widest text-zinc-700 dark:text-zinc-300">
                {routeTitles[location.pathname] || 'BRC Console'}
              </h2>
              <div className="h-3.5 w-px bg-zinc-300 dark:bg-zinc-700" />
              <span className="rounded border border-zinc-300/50 bg-zinc-200/50 px-1.5 py-0.5 font-mono text-[9px] font-bold text-zinc-600 dark:border-zinc-700/50 dark:bg-zinc-800/50 dark:text-zinc-400">
                OWNER-GATED
              </span>
            </div>

            <div className="flex items-center space-x-4">
              <button
                onClick={handleManualRefresh}
                className="flex items-center space-x-1.5 rounded-sm border border-zinc-300 px-2 py-1 text-zinc-700 transition-colors hover:bg-zinc-200 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-700"
              >
                <RefreshCw className="h-3 w-3" />
                <span className="text-[10px] font-bold uppercase">Refresh</span>
              </button>
              <div className="h-4 w-px bg-zinc-300 dark:bg-zinc-700" />
              <ThemeToggle />
              <button
                onClick={logout}
                className="flex items-center space-x-1.5 rounded-sm border border-zinc-300 px-2 py-1 text-zinc-700 transition-colors hover:bg-zinc-200 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-700"
              >
                <LogOut className="h-3 w-3" />
                <span className="text-[10px] font-bold uppercase">Logout</span>
              </button>
            </div>
          </header>

          <main className="flex-1 overflow-y-auto p-4 md:p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </RefreshContext.Provider>
  );
}
