import React from 'react';
import type { GlobalEntryState } from '../types/controls';
import { Pause, Play } from 'lucide-react';

interface TopStatusBarProps {
  globalEntry: GlobalEntryState;
  pausedStrategyCount: number;
  totalActiveStrategies: number;
  onToggleGlobalEntry?: () => void;
}

export const TopStatusBar: React.FC<TopStatusBarProps> = ({
  globalEntry,
  pausedStrategyCount,
  totalActiveStrategies,
}) => {

  const isGlobalEnabled = globalEntry.configured_state === 'enabled';

  return (
    <section className="mb-4 rounded border border-border bg-surface p-4 shadow-xs">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        {/* Left: Global ENTRY Switch with crystal clear business explanation */}
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-3">
            <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">
              全局 ENTRY 准入
            </span>
            <span
              className={`inline-flex items-center gap-2 rounded px-3 py-1 text-xs font-semibold ${
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

          <span className="hidden sm:inline text-text-muted opacity-30">|</span>

          <p className="text-xs text-text-secondary">
            {isGlobalEnabled ? (
              <span>全局新开仓通道开启中 · 存量持仓保护不受限制</span>
            ) : (
              <span className="text-status-amber font-medium">
                新信号已阻断生成 Ticket · 已有持仓与止损仍由 Lifecycle 正常保护中
              </span>
            )}
          </p>
        </div>

        {/* Right: Quick toggle button & metrics */}
        <div className="flex items-center gap-4">
          <div className="hidden xl:flex items-center gap-4 text-xs text-text-muted">
            <div>
              <span>策略态势: </span>
              <strong className="font-mono text-text-primary ml-1">
                {totalActiveStrategies - pausedStrategyCount} 运行 / {pausedStrategyCount} 暂停
              </strong>
            </div>
            <span className="opacity-30">·</span>
            <div>
              <span>在管持仓: </span>
              <strong className="font-mono text-text-primary ml-1">
                {globalEntry.active_ticket_count} 笔 (受保护)
              </strong>
            </div>
          </div>

          <button
            type="button"
            disabled
            title="Phase 1 · 只读模式 (写操作未开放)"
            className="inline-flex items-center gap-2 rounded border border-border bg-surface-subtle px-3.5 py-1.5 text-xs font-semibold text-text-muted opacity-60 cursor-not-allowed shadow-none"
          >
            {isGlobalEnabled ? (
              <>
                <Pause className="h-3.5 w-3.5 text-text-muted" />
                暂停全局 (Phase 1 只读)
              </>
            ) : (
              <>
                <Play className="h-3.5 w-3.5 text-text-muted" />
                恢复全局 (Phase 1 只读)
              </>
            )}
          </button>

        </div>
      </div>
    </section>
  );
};

