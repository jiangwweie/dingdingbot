import { LayoutDashboard, GitBranch, Zap, Wallet, LineChart, Workflow, RefreshCw, LogOut, User, Info } from 'lucide-react';
import { useState } from 'react';
import { Outlet, NavLink, useLocation } from 'react-router-dom';
import { ModeToggle } from './ModeToggle';

export default function Layout() {
  const [showStatusInfo, setShowStatusInfo] = useState(false);
  const location = useLocation();

  const navItems = [
    { path: '/home', label: '首页', icon: LayoutDashboard },
    { path: '/strategy-groups', label: '策略组', icon: GitBranch },
    { path: '/intents', label: '执行意图', icon: Zap },
    { path: '/account-orders', label: '账户订单', icon: Wallet },
    { path: '/analysis', label: '复盘分析', icon: LineChart },
    { path: '/trace', label: '链路追踪', icon: Workflow },
  ];

  return (
    <div className="w-full h-screen bg-slate-100 dark:bg-slate-950 flex flex-col font-sans text-slate-900 dark:text-slate-100 overflow-hidden">
      {/* Top Navigation Bar */}
      <header className="h-16 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between px-8 flex-shrink-0">
        <div className="flex items-center gap-4">
          <div className="w-8 h-8 md:w-10 md:h-10 bg-indigo-600 rounded flex items-center justify-center text-white font-bold text-lg md:text-xl shrink-0">SC</div>
          <div>
            <h1 className="text-base md:text-lg font-bold leading-none dark:text-white">策略控制台</h1>
            <p className="text-xs text-slate-500 dark:text-slate-400">v2 主控工作台</p>
          </div>
        </div>

        <div className="flex items-center gap-4 md:gap-6">
          <div className="relative">
            <button
              onMouseEnter={() => setShowStatusInfo(true)}
              onMouseLeave={() => setShowStatusInfo(false)}
              className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-teal-200/50 dark:border-teal-900/50 bg-teal-50 dark:bg-teal-950/30 hover:bg-teal-100 dark:hover:bg-teal-900/50 transition-colors"
            >
              <div className="w-2 h-2 rounded-full bg-teal-500 shadow-[0_0_8px_rgba(20,184,166,0.6)]"></div>
              <span className="text-sm font-medium text-teal-900 dark:text-teal-400">实盘只读 · 记录意图</span>
            </button>

            {showStatusInfo && (
              <div className="absolute top-full mt-2 right-0 w-72 bg-white dark:bg-slate-900 rounded-lg shadow-lg border border-slate-200 dark:border-slate-700 p-4 z-50">
                <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200 mb-2">当前模式：实盘只读</h3>
                <ul className="text-xs text-slate-600 dark:text-slate-400 space-y-2">
                  <li className="flex justify-between"><span>权限：</span><span className="font-medium text-slate-900 dark:text-slate-200">记录意图</span></li>
                  <li className="flex justify-between"><span>下单：</span><span className="font-medium text-red-600 dark:text-red-400">禁止</span></li>
                  <li className="flex justify-between"><span>执行指令：</span><span className="font-medium text-red-600 dark:text-red-400">禁止</span></li>
                  <li className="flex justify-between text-slate-400 dark:text-slate-500 mt-2"><span>最近检查：</span><span>23:51:32</span></li>
                </ul>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-3 pt-3 border-t border-slate-100 dark:border-slate-800">
                  当前连接真实市场，只记录信号和执行意图。不会创建执行指令，也不会下单。
                </p>
              </div>
            )}
          </div>

          <div className="hidden md:block w-px h-6 bg-slate-200 dark:bg-slate-800"></div>

          <ModeToggle />

          <button className="text-slate-500 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors" title="刷新状态">
            <RefreshCw size={18} />
          </button>

          <div className="flex items-center gap-2 cursor-pointer group">
            <div className="w-8 h-8 rounded-full bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 flex items-center justify-center text-slate-500 group-hover:bg-indigo-50 dark:group-hover:bg-indigo-900/30 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">
              <User size={16} />
            </div>
            <span className="hidden md:inline text-sm font-medium text-slate-700 dark:text-slate-300 group-hover:text-indigo-700 dark:group-hover:text-indigo-400">Owner</span>
          </div>
        </div>
      </header>

      {/* Main Workspace */}
      <main className="flex-grow flex overflow-hidden">

        {/* Left Sidebar */}
        <aside className="w-48 md:w-64 bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 p-4 md:p-6 flex flex-col gap-4 flex-shrink-0">
          <nav className="flex flex-col gap-1">
            {navItems.map((item) => {
              const isActive = location.pathname.startsWith(item.path);
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors text-sm font-medium ${
                    isActive
                      ? 'bg-indigo-50 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-400'
                      : 'text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800/50 hover:text-slate-900 dark:hover:text-slate-200'
                  }`}
                >
                  <item.icon size={18} className={isActive ? 'text-indigo-600 dark:text-indigo-400' : 'text-slate-400 dark:text-slate-500'} />
                  {item.label}
                </NavLink>
              );
            })}
          </nav>

          <div className="mt-auto pt-4 border-t border-slate-100 dark:border-slate-800">
            <button className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-slate-500 dark:text-slate-400 w-full hover:bg-slate-50 dark:hover:bg-slate-800/50 hover:text-slate-900 dark:hover:text-slate-200 transition-colors">
              <LogOut size={18} className="text-slate-400 dark:text-slate-500" />
              退出登录
            </button>
          </div>
        </aside>

        {/* Center: Content View */}
        <section className="flex-grow bg-slate-50 dark:bg-slate-950 p-4 md:p-6 overflow-y-auto w-full">
          <div className="max-w-[1440px] mx-auto flex flex-col gap-6">
            <Outlet />
          </div>
        </section>
      </main>
    </div>
  );
}
