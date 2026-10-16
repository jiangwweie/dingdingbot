import React from 'react';
import { useTheme } from '../context/ThemeContext';
import { Sun, Moon } from 'lucide-react';


export type NavTabId = 'overview' | 'trades' | 'strategies' | 'review' | 'controls';

interface NavbarProps {
  activeTab: NavTabId;
  onSelectTab: (tab: NavTabId) => void;
  isRealData?: boolean;
  onLogout?: () => void;
  isLoggingOut?: boolean;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  onSelectTab,
  isRealData = true,
  onLogout,
  isLoggingOut = false,
}) => {
  const { theme, toggleTheme } = useTheme();

  const navItems: { id: NavTabId; label: string; en: string; badge?: string; available: boolean }[] = [
    { id: 'overview', label: '总览态势', en: 'Overview', available: true },
    { id: 'trades', label: '交易因果', en: 'Trades', available: true },
    { id: 'strategies', label: '策略选币', en: 'Strategies', badge: '规划中', available: false },
    { id: 'review', label: '复盘评估', en: 'Review', badge: '规划中', available: false },
    { id: 'controls', label: '主控中心', en: 'Controls', available: true },
  ];

  return (
    <header className="border-b border-border bg-surface">
      <div className="mx-auto flex h-12 max-w-[1520px] items-center justify-between px-4 sm:px-6">
        {/* Brand and 4+1 primary navigation */}
        <div className="flex items-center gap-8">
          <div
            className="flex items-center gap-2.5 cursor-pointer"
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
                  className={`relative flex items-center gap-1.5 px-3 py-1.5 text-xs transition-colors ${
                    isActive
                      ? 'font-semibold text-text-primary after:absolute after:bottom-0 after:left-3 after:right-3 after:h-0.5 after:bg-brand'
                      : item.available
                      ? 'font-medium text-text-secondary hover:text-text-primary'
                      : 'font-normal text-text-muted hover:text-text-secondary cursor-pointer'
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

        {/* Right side: Real API tag & Theme Switcher & Logout */}
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1.5 rounded border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-0.5 font-mono text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
            {isRealData ? 'REAL API · PROD' : 'OFFLINE'}
          </span>


          <span className="text-text-muted opacity-40">·</span>

          {/* Theme Switcher */}
          <button
            type="button"
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? '切换至明亮主题' : '切换至暗色主题'}
            title={theme === 'dark' ? '切换至明亮主题' : '切换至暗色主题'}
            className="flex h-7 w-7 items-center justify-center rounded border border-border bg-surface-subtle text-text-secondary hover:bg-surface-elevated hover:text-text-primary transition-colors"
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
    </header>
  );
};

