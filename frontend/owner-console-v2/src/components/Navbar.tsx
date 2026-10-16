import React from 'react';
import { MOCK_ENV_LABEL } from '../mock/controlsData';
import { useTheme } from '../context/ThemeContext';
import { Sun, Moon } from 'lucide-react';

export const Navbar: React.FC = () => {
  const { theme, toggleTheme } = useTheme();

  return (
    <header className="border-b border-border bg-surface">
      <div className="mx-auto flex h-12 max-w-[1520px] items-center justify-between px-4 sm:px-6">
        {/* Brand and primary navigation */}
        <div className="flex items-center gap-8">
          <div className="flex items-center gap-2.5">
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
            <span className="px-3 py-1.5 text-xs font-medium text-text-muted hover:text-text-primary cursor-not-allowed transition-colors">
              总览
            </span>
            <span className="px-3 py-1.5 text-xs font-medium text-text-muted hover:text-text-primary cursor-not-allowed transition-colors">
              策略
            </span>
            <span className="px-3 py-1.5 text-xs font-medium text-text-muted hover:text-text-primary cursor-not-allowed transition-colors">
              交易
            </span>
            <span className="px-3 py-1.5 text-xs font-medium text-text-muted hover:text-text-primary cursor-not-allowed transition-colors">
              复盘
            </span>
            <span className="relative px-3 py-1.5 text-xs font-semibold text-text-primary after:absolute after:bottom-0 after:left-3 after:right-3 after:h-0.5 after:bg-brand">
              控制中心
            </span>
          </nav>
        </div>

        {/* Right side: Mock banner & Theme Switcher & Actions */}
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1.5 rounded border border-brand/40 bg-brand/10 px-2.5 py-0.5 font-mono text-[11px] font-medium text-brand">
            <span className="h-1.5 w-1.5 rounded-full bg-brand animate-pulse" />
            {MOCK_ENV_LABEL}
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
            className="text-xs text-text-muted hover:text-text-primary transition-colors"
            onClick={() => alert('Mock 环境：退出交互演示')}
          >
            退出
          </button>
        </div>
      </div>
    </header>
  );
};

