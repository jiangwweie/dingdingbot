import React from 'react';
import type { GlobalEntryState } from '../types/controls';
import { Pause, Play } from 'lucide-react';

export interface TopStatusBarProps {
  globalEntry: GlobalEntryState;
  pausedStrategyCount: number;
  totalActiveStrategies: number;
  onRequestAction?: (action: 'pause' | 'resume', version: number) => void;
  isActionDisabled?: boolean;
  disabledReason?: string;
}

export const TopStatusBar: React.FC<TopStatusBarProps> = ({
  globalEntry,
  pausedStrategyCount,
  totalActiveStrategies,
  onRequestAction,
  isActionDisabled = false,
  disabledReason,
}) => {
  const isGlobalEnabled = globalEntry.configured_state === 'enabled';
  const targetAction = isGlobalEnabled ? 'pause' : 'resume';
  const isDisabled = isActionDisabled || !onRequestAction;

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
            disabled={isDisabled}
            title={disabledReason ?? (isGlobalEnabled ? '暂停全局策略新开仓准入' : '恢复全局新开仓通道')}
            onClick={() => onRequestAction?.(targetAction, globalEntry.policy_version)}
            className={`inline-flex items-center gap-2 rounded border px-3.5 py-1.5 text-xs font-semibold transition-colors cursor-pointer disabled:cursor-not-allowed disabled:opacity-50 ${
              isGlobalEnabled
                ? 'border-status-amber/50 bg-status-amber-bg text-status-amber hover:bg-status-amber/20'
                : 'border-status-green/50 bg-status-green-bg text-status-green hover:bg-status-green/20'
            }`}
          >
            {isGlobalEnabled ? (
              <>
                <Pause className="h-3.5 w-3.5 text-status-amber" />
                暂停全局新准入
              </>
            ) : (
              <>
                <Play className="h-3.5 w-3.5 text-status-green" />
                恢复全局新准入
              </>
            )}
          </button>
        </div>
      </div>
    </section>
  );
};

