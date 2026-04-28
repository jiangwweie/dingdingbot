import React, { createContext, useContext, useState, useCallback } from 'react';
import { Outlet, NavLink, useLocation } from 'react-router-dom';
import { RefreshCw, Activity, Zap, HeartPulse, FileText, LayoutDashboard, GitBranch, History, Scale, Sun, Moon, Monitor, WalletCards, CalendarClock, Settings, PlayCircle } from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { environmentModeLabel, environmentBadgeStyle, type EnvironmentMode } from '@/src/lib/runtime-format';
import { useTheme } from './ThemeContext';

// Context to trigger refreshes across pages
type RefreshContextType = {
  refreshCount: number;
};
const RefreshContext = createContext<RefreshContextType>({ refreshCount: 0 });

export const useRefreshContext = () => useContext(RefreshContext);

function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  return (
    <div className="flex border border-zinc-200 dark:border-zinc-800 rounded bg-zinc-50 dark:bg-zinc-900 p-0.5">
      <button
        onClick={() => setTheme('light')}
        className={cn("p-1 rounded cursor-pointer", theme === 'light' ? "bg-white dark:bg-zinc-800 shadow-sm" : "hover:bg-zinc-200 dark:hover:bg-zinc-800")}
        title="Light Mode"
      >
        <Sun className="w-3.5 h-3.5 text-zinc-600 dark:text-zinc-400" />
      </button>
      <button
        onClick={() => setTheme('dark')}
        className={cn("p-1 rounded cursor-pointer", theme === 'dark' ? "bg-white dark:bg-zinc-800 shadow-sm" : "hover:bg-zinc-200 dark:hover:bg-zinc-800")}
        title="Dark Mode"
      >
        <Moon className="w-3.5 h-3.5 text-zinc-600 dark:text-zinc-400" />
      </button>
      <button
        onClick={() => setTheme('system')}
        className={cn("p-1 rounded cursor-pointer", theme === 'system' ? "bg-white dark:bg-zinc-800 shadow-sm" : "hover:bg-zinc-200 dark:hover:bg-zinc-800")}
        title="System Preference"
      >
        <Monitor className="w-3.5 h-3.5 text-zinc-600 dark:text-zinc-400" />
      </button>
    </div>
  );
}

export default function AppLayout() {
  const [refreshCount, setRefreshCount] = useState(0);
  const location = useLocation();

  const handleManualRefresh = useCallback(() => {
    setRefreshCount(c => c + 1);
  }, []);

  const navItems = [
    {
      domain: '运行环境 (Runtime)',
      links: [
        { name: '系统概览', to: '/runtime/overview', icon: LayoutDashboard },
        { name: '投资组合', to: '/runtime/portfolio', icon: WalletCards },
        { name: '交易信号', to: '/runtime/signals', icon: Zap },
        { name: '执行情况', to: '/runtime/execution', icon: Activity },
        { name: '操作日志', to: '/runtime/events', icon: CalendarClock },
        { name: '系统健康度', to: '/runtime/health', icon: HeartPulse },
      ]
    },
    {
      domain: '策略研究 (Research)',
      links: [
        { name: '新建回测', to: '/research/new', icon: PlayCircle },
        { name: '回测历史', to: '/research/jobs', icon: History },
        { name: '候选策略', to: '/research/candidates', icon: FileText },
        { name: '回测上下文', to: '/research/replay/default', icon: GitBranch, hideDisabled: true },
        { name: '旧版报告', to: '/research/backtests', icon: History },
        { name: '策略对比', to: '/research/compare', icon: Scale },
      ]
    },
    {
      domain: '配置 (Config)',
      links: [
        { name: '快照库', to: '/config/snapshot', icon: Settings },
      ]
    }
  ];

  return (
    <RefreshContext.Provider value={{ refreshCount }}>
      <div className="flex h-screen w-full overflow-hidden font-sans text-zinc-900 dark:text-zinc-100 bg-white dark:bg-zinc-950">
        
        {/* Sidebar Navigation */}
        <aside className="w-48 flex-shrink-0 border-r border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/30 flex flex-col z-20">
          <div className="p-4 py-3 border-b border-zinc-200 dark:border-zinc-800 bg-zinc-100/50 dark:bg-zinc-900/80">
            <h1 className="text-[11px] font-bold tracking-widest text-blue-500 uppercase">Trading Desk</h1>
            <div className="flex items-center gap-2 mt-1">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]"></div>
              <p className="text-[10px] text-zinc-500 uppercase font-mono tracking-tighter">Sim-1 (Local)</p>
            </div>
          </div>
          
          <nav className="flex-1 px-2 py-4 space-y-6 overflow-y-auto">
            {navItems.map((group) => (
              <div key={group.domain}>
                <p className="px-2 text-[10px] font-bold text-zinc-400 dark:text-zinc-500 uppercase tracking-widest mb-1.5">
                  {group.domain}
                </p>
                <ul className="space-y-0.5">
                  {group.links.map(link => {
                    if (link.hideDisabled) return null; // simplify for now
                    const Icon = link.icon;
                    return (
                      <li key={link.to}>
                        <NavLink
                          to={link.to}
                          className={({ isActive }) => cn(
                            "flex items-center gap-2 px-2 py-[5px] text-[11px] font-medium rounded-sm transition-colors border-l-2",
                            isActive 
                              ? "bg-blue-600/10 text-blue-500 dark:text-blue-400 border-blue-500 font-bold" 
                              : "text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 hover:bg-zinc-200/50 dark:hover:bg-zinc-800/50 border-transparent"
                          )}
                        >
                          <Icon className="w-3.5 h-3.5" />
                          {link.name}
                        </NavLink>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </nav>
          
          <div className="p-3 border-t border-zinc-200 dark:border-zinc-800 bg-zinc-100/50 dark:bg-zinc-900/50">
            <div className="flex items-center space-x-2">
              <span className="text-[9px] text-zinc-600 dark:text-zinc-400 font-mono tracking-widest">ALPHA_01_ACTIVE</span>
            </div>
          </div>
        </aside>

        {/* Main Content */}
        <div className="flex-1 flex flex-col min-w-0 bg-white dark:bg-[#09090b]">
          {/* Top Header */}
          <header className="h-[38px] border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50/80 dark:bg-zinc-900/80 flex items-center justify-between px-4 z-10 backdrop-blur-sm">
            <div className="flex items-center space-x-3">
               <h2 className="text-xs font-bold uppercase tracking-widest text-zinc-700 dark:text-zinc-300">
                 {location.pathname.split('/').pop()?.replace('-', ' ')}
               </h2>
               <div className="h-3.5 w-px bg-zinc-300 dark:bg-zinc-700"></div>
               <span className="px-1.5 py-0.5 text-[9px] font-mono bg-zinc-200/50 dark:bg-zinc-800/50 rounded border border-zinc-300/50 dark:border-zinc-700/50 text-zinc-600 dark:text-zinc-400 font-bold">
                 REQ: 8824-X
               </span>
            </div>

            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-2">
                <span className="text-[10px] text-zinc-500 font-mono">Manual Sync</span>
                <button 
                  onClick={handleManualRefresh}
                  className="flex items-center space-x-1.5 px-2 py-1 hover:bg-zinc-200 dark:hover:bg-zinc-700 border border-zinc-300 dark:border-zinc-700 rounded-sm transition-colors text-zinc-700 dark:text-zinc-300"
                >
                  <RefreshCw className="w-3 h-3" />
                  <span className="text-[10px] font-bold uppercase">Refresh</span>
                </button>
              </div>
              <div className="h-4 w-px bg-zinc-300 dark:bg-zinc-700"></div>
              <ThemeToggle />
            </div>
          </header>

          {/* Page Content */}
          <main className="flex-1 overflow-y-auto p-4 md:p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </RefreshContext.Provider>
  );
}
