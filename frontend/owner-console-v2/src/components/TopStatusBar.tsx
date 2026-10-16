import React from 'react';
import type { GlobalEntryState } from '../types/controls';
import { Pause, Play } from 'lucide-react';

interface TopStatusBarProps {
  globalEntry: GlobalEntryState;
  pausedStrategyCount: number;
  totalActiveStrategies: number;
  onToggleGlobalEntry: () => void;
}

export const TopStatusBar: React.FC<TopStatusBarProps> = ({
  globalEntry,
  pausedStrategyCount,
  totalActiveStrategies,
  onToggleGlobalEntry,
}) => {
  const isGlobalEnabled = globalEntry.configured_state === 'enabled';

  return (
    <section className="mb-4 rounded border border-border-base bg-surface-1 p-3.5 shadow-sm">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        {/* Left: Global ENTRY Switch with crystal clear business explanation */}
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-3">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              全局 ENTRY 准入
            </span>
            <span
              className={`inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-semibold ${
                isGlobalEnabled
                  ? 'border border-status-green/30 bg-status-green-bg text-status-green'
                  : 'border border-status-amber/30 bg-status-amber-bg text-status-amber'
              }`}
            >
              <span
                className={`h-2 w-2 rounded-full ${
                  isGlobalEnabled ? 'bg-status-green' : 'bg-status-amber'
                }`}
              />
              {isGlobalEnabled ? '允许新开仓 (Enabled)' : '已暂停新开仓 (Paused)'}
            </span>
          </div>

          <span className="hidden sm:inline text-slate-700">|</span>

          <p className="text-xs text-slate-400">
            {isGlobalEnabled ? (
              <span>全局新开仓通道开启中 · 存量持仓保护不受限制</span>
            ) : (
              <span className="text-status-amber">
                新信号已阻断生成 Ticket · 已有持仓与止损仍由 Lifecycle 正常保护中
              </span>
            )}
          </p>
        </div>

        {/* Right: Quick toggle button & metrics */}
        <div className="flex items-center gap-4">
          <div className="hidden xl:flex items-center gap-4 text-xs">
            <div>
              <span className="text-slate-500">策略态势: </span>
              <strong className="font-mono text-slate-200">
                {totalActiveStrategies - pausedStrategyCount} 运行 / {pausedStrategyCount} 暂停
              </strong>
            </div>
            <span className="text-slate-700">·</span>
            <div>
              <span className="text-slate-500">在管持仓: </span>
              <strong className="font-mono text-slate-200">
                {globalEntry.active_ticket_count} 笔 (受保护)
              </strong>
            </div>
          </div>

          <button
            type="button"
            onClick={onToggleGlobalEntry}
            className={`inline-flex items-center gap-1.5 rounded border px-3 py-1.5 text-xs font-medium transition-colors ${
              isGlobalEnabled
                ? 'border-border-strong bg-surface-2 text-slate-200 hover:bg-surface-3 hover:text-white'
                : 'border-status-green/50 bg-status-green-bg text-status-green hover:bg-status-green/20'
            }`}
          >
            {isGlobalEnabled ? (
              <>
                <Pause className="h-3.5 w-3.5 text-status-amber" />
                暂停全局新开仓
              </>
            ) : (
              <>
                <Play className="h-3.5 w-3.5 text-status-green" />
                恢复全局新开仓 (需 TOTP)
              </>
            )}
          </button>
        </div>
      </div>
    </section>
  );
};
