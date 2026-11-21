import React from 'react';
import { useTheme } from '../context/ThemeContext';
import { Sun, Moon } from 'lucide-react';


export type NavTabId = 'overview' | 'trades' | 'strategies' | 'review' | 'controls';

interface NavbarProps {
  activeTab: NavTabId;
  onSelectTab: (tab: NavTabId) => void;
  isRealData?: boolean;
  isIsolatedMock?: boolean;
  onLogout?: () => void;
  isLoggingOut?: boolean;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  onSelectTab,
  isRealData = true,
  isIsolatedMock = false,
  onLogout,
  isLoggingOut = false,
}) => {
  const { theme, toggleTheme } = useTheme();

  const navItems: { id: NavTabId; label: string; en: string; badge?: string; available: boolean }[] = [
    { id: 'overview', label: '总览态势', en: 'Overview', available: true },
    { id: 'trades', label: '交易因果', en: 'Trades', available: true },
    { id: 'strategies', label: '策略选币', en: 'Strategies', available: true },
    { id: 'review', label: '复盘评估', en: 'Review', available: true },
    { id: 'controls', label: '主控中心', en: 'Controls', available: true },
  ];

  return (
    <header className="border-b border-border bg-surface">
      <div className="mx-auto flex h-12 max-w-[1520px] items-center justify-between px-3 sm:px-6">
        {/* Brand and 4+1 primary navigation */}
        <div className="flex items-center gap-4 sm:gap-8 min-w-0">
          <div
            className="flex items-center gap-2 sm:gap-2.5 cursor-pointer flex-none"
            onClick={() => onSelectTab('overview')}
          >
            <svg
              className="h-4 w-4 text-brand flex-none"
              viewBox="0 0 24 24"
              fill="currentColor"
              aria-hidden="true"
            >
              <path d="M12 2L4 12l8 10 8-10L12 2zm0 4.236L17.412 12 12 18.764 6.588 12 12 6.236z" />
            </svg>
            <span className="font-mono text-xs font-bold tracking-wider text-text-primary">
              BRC OWNER
            </span>
          </div>

          <nav className="hidden md:flex items-center gap-1" aria-label="主导航">
            {navItems.map((item) => {
              const isActive = activeTab === item.id;

              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    if (item.available) {
                      onSelectTab(item.id);
                    } else {
                      alert(`${item.label} (${item.en}) 遵循 4+1 IA 架构正在规划中，请先审阅总览与主控中心。`);
                    }
                  }}
                  className={`relative flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md transition-all cursor-pointer ${
                    isActive
                      ? 'font-bold text-text-primary bg-surface-elevated border border-border shadow-2xs'
                      : item.available
                      ? 'font-medium text-text-secondary hover:text-text-primary hover:bg-surface-subtle'
                      : 'font-normal text-text-muted hover:text-text-secondary'
                  }`}
                >
                  <span>{item.label}</span>
                  {item.badge && (
                    <span className="rounded bg-surface-subtle px-1 py-0.2 font-mono text-[9px] text-text-muted border border-border/40">
                      {item.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Right side: Real/Mock tag & Theme Switcher & Logout */}
        <div className="flex items-center gap-2 sm:gap-3 flex-none">
          <span
            className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[10px] sm:text-[11px] font-medium ${
              isRealData
                ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                : 'border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300'
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                isRealData ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'
              }`}
            />
            {isRealData ? (
              'REAL API · PROD'
            ) : (
              <>
                <span className="hidden sm:inline">{isIsolatedMock ? 'ISOLATED MOCK · 离线验证' : '数据未就绪'}</span>
                <span className="sm:hidden">{isIsolatedMock ? 'MOCK 验证' : '数据待核实'}</span>
              </>
            )}
          </span>

          <span className="text-text-muted opacity-40">·</span>

          {/* Theme Switcher */}
          <button
            type="button"
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? '切换至明亮主题' : '切换至暗色主题'}
            title={theme === 'dark' ? '切换至明亮主题' : '切换至暗色主题'}
            className="flex h-7 w-7 items-center justify-center rounded border border-border bg-surface-subtle text-text-secondary hover:bg-surface-elevated hover:text-text-primary transition-colors cursor-pointer"
          >
            {theme === 'dark' ? (
              <Sun className="h-3.5 w-3.5" />
            ) : (
              <Moon className="h-3.5 w-3.5" />
            )}
          </button>

          <span className="text-text-muted opacity-40">·</span>

          <button
            type="button"
            aria-label="退出登录"
            data-testid="navbar-logout-btn"
            disabled={isLoggingOut}
            className={`text-xs transition-colors cursor-pointer ${
              isLoggingOut ? 'text-text-muted opacity-50 cursor-not-allowed' : 'text-text-muted hover:text-danger'
            }`}
            onClick={onLogout}
          >
            {isLoggingOut ? '正在退出...' : '退出'}
          </button>
        </div>
      </div>
      <nav aria-label="移动主导航" className="flex gap-1 overflow-x-auto border-t border-border/60 px-3 py-2 md:hidden">
        {navItems.filter(item => item.available).map(item => (
          <button key={item.id} type="button" onClick={() => onSelectTab(item.id)}
            aria-current={activeTab === item.id ? 'page' : undefined}
            className={`flex-none rounded-md px-3 py-1.5 text-xs transition-colors ${activeTab === item.id ? 'bg-surface-elevated font-bold text-text-primary border border-border' : 'text-text-secondary hover:bg-surface-subtle'}`}>
            {item.label}
          </button>
        ))}
      </nav>
    </header>
  );
};

