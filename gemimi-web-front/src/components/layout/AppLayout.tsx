import React, { createContext, useContext, useState, useCallback } from 'react';
import { Outlet, NavLink, useLocation } from 'react-router-dom';
import { RefreshCw, Activity, Zap, HeartPulse, FileText, LayoutDashboard, GitBranch, History, Scale, Sun, Moon, Monitor, WalletCards, CalendarClock, Settings, PlayCircle } from 'lucide-react';
import { cn } from '@/src/lib/utils';
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
        { name: '研究任务', to: '/research/jobs', icon: History },
        { name: '候选策略', to: '/research/candidates', icon: FileText },
        { name: '回测上下文', to: '/research/replay/default', icon: GitBranch, hideDisabled: true },
        { name: '历史报告', to: '/research/backtests', icon: History },
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
        <aside className="w-60 flex-shrink-0 border-r border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/50 flex flex-col z-20">
          <div className="p-6">
            <h1 className="text-xs font-bold tracking-widest text-blue-400 uppercase">交易控制台</h1>
            <p className="text-[10px] text-zinc-500 mt-1 uppercase font-mono tracking-tighter">Sim-1 (本地模拟)</p>
          </div>
          
          <nav className="flex-1 px-4 space-y-6 overflow-y-auto">
            {navItems.map((group) => (
              <div key={group.domain}>
                <p className="px-2 text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-3">
                  {group.domain}
                </p>
                <ul className="space-y-1">
                  {group.links.map(link => {
                    if (link.hideDisabled) return null; // simplify for now
                    const Icon = link.icon;
                    return (
                      <li key={link.to}>
                        <NavLink
                          to={link.to}
                          className={({ isActive }) => cn(
                            "flex items-center gap-3 px-2 py-1.5 text-sm rounded transition-colors border-l-2",
                            isActive 
                              ? "bg-blue-600/10 text-blue-400 border-blue-500" 
                              : "text-zinc-600 dark:text-zinc-400 hover:text-zinc-800 dark:text-zinc-200 border-transparent"
                          )}
                        >
                          <Icon className="w-4 h-4" />
                          {link.name}
                        </NavLink>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </nav>
          
          <div className="p-4 mt-auto border-t border-zinc-200 dark:border-zinc-800">
            <div className="flex items-center space-x-2">
              <div className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]"></div>
              <span className="text-[10px] text-zinc-600 dark:text-zinc-400 font-mono">INSTANCE_ALPHA_01</span>
            </div>
          </div>
        </aside>

        {/* Main Content */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Top Header */}
          <header className="h-14 border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 flex items-center justify-between px-6 z-10">
            <div className="flex items-center space-x-4">
               <h2 className="text-sm font-semibold tracking-tight capitalize">{location.pathname.split('/').pop()?.replace('-', ' ')}</h2>
               <span className="px-2 py-0.5 text-[10px] font-mono bg-zinc-100 dark:bg-zinc-800 rounded border border-zinc-300 dark:border-zinc-700 text-zinc-600 dark:text-zinc-400">ID: 8824-X</span>
            </div>

            <div className="flex items-center space-x-6">
              <ThemeToggle />
              <div className="flex flex-col items-end">
                <span className="text-[10px] text-zinc-500 uppercase font-bold">仅支持手动刷新</span>
                <span className="text-[11px] text-blue-400 font-mono">使用按钮 &rarr;</span>
              </div>
              <button 
                onClick={handleManualRefresh}
                className="flex items-center space-x-2 px-3 py-1.5 bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 border border-zinc-300 dark:border-zinc-700 rounded transition-colors text-zinc-700 dark:text-zinc-300"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span className="text-xs font-medium">手动刷新</span>
              </button>
            </div>
          </header>

          {/* Page Content */}
          <main className="flex-1 overflow-y-auto p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </RefreshContext.Provider>
  );
}
