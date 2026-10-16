import React from 'react';
import { MOCK_ENV_LABEL } from '../mock/controlsData';

export const Navbar: React.FC = () => {
  return (
    <header className="border-b border-border-base bg-surface-1">
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
            <span className="font-mono text-xs font-bold tracking-wider text-slate-100">
              BRC OWNER
            </span>
          </div>

          <nav className="hidden md:flex items-center gap-1" aria-label="主导航">
            <span className="px-3 py-1.5 text-xs font-medium text-slate-400 hover:text-slate-200 cursor-not-allowed transition-colors">
              总览
            </span>
            <span className="px-3 py-1.5 text-xs font-medium text-slate-400 hover:text-slate-200 cursor-not-allowed transition-colors">
              策略
            </span>
            <span className="px-3 py-1.5 text-xs font-medium text-slate-400 hover:text-slate-200 cursor-not-allowed transition-colors">
              交易
            </span>
            <span className="px-3 py-1.5 text-xs font-medium text-slate-400 hover:text-slate-200 cursor-not-allowed transition-colors">
              复盘
            </span>
            <span className="relative px-3 py-1.5 text-xs font-semibold text-slate-100 after:absolute after:bottom-0 after:left-3 after:right-3 after:h-0.5 after:bg-brand">
              控制中心
            </span>
          </nav>
        </div>

        {/* Runtime info & Mock banner */}
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1.5 rounded border border-brand/40 bg-brand/10 px-2 py-0.5 font-mono text-[11px] font-medium text-brand">
            <span className="h-1.5 w-1.5 rounded-full bg-brand animate-pulse" />
            {MOCK_ENV_LABEL}
          </span>

          <span className="text-slate-600">·</span>

          <span className="font-mono text-xs text-slate-400 tabular-numbers">
            Policy v28
          </span>

          <span className="text-slate-600">·</span>

          <button
            type="button"
            className="text-xs text-slate-400 hover:text-slate-200 transition-colors"
            onClick={() => alert('Mock 环境：退出交互演示')}
          >
            退出
          </button>
        </div>
      </div>
    </header>
  );
};
