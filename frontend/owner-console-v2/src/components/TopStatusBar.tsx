import React from 'react';
import type { GlobalEntryState } from '../types/controls';
import { Pause, Play } from 'lucide-react';

export interface TopStatusBarProps {
  globalEntry: GlobalEntryState;
  enabledStrategyCount?: number;
  pausedStrategyCount: number;
  unknownStrategyCount?: number;
  totalActiveStrategies: number;
  onRequestAction?: (action: 'pause' | 'resume', version: number) => void;
  isActionDisabled?: boolean;
  disabledReason?: string;
}

export const TopStatusBar: React.FC<TopStatusBarProps> = ({
  globalEntry,
  enabledStrategyCount,
  pausedStrategyCount,
  unknownStrategyCount = 0,
  totalActiveStrategies,
  onRequestAction,
  isActionDisabled = false,
  disabledReason,
}) => {
  const isGlobalEnabled = globalEntry.configured_state === 'enabled';
  const targetAction = isGlobalEnabled ? 'pause' : 'resume';
  const isDisabled = isActionDisabled || !onRequestAction;
  const resolvedEnabledCount =
    enabledStrategyCount ?? Math.max(0, totalActiveStrategies - pausedStrategyCount - unknownStrategyCount);

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
              {isGlobalEnabled ? '配置开关已开启' : '已暂停新开仓'}
            </span>
          </div>

          <span className="hidden sm:inline text-text-muted opacity-30">|</span>

          <p className="text-xs text-text-secondary">
            {isGlobalEnabled ? (
              <span>仅控制新增开仓；不改变已有交易管理权。</span>
            ) : (
              <span className="text-status-amber font-medium">
                仅控制新增开仓；不改变已有交易管理权。新信号已被全局开关阻断。
              </span>
            )}
          </p>
        </div>

        {/* Right: Quick toggle button & metrics */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="hidden xl:flex items-center gap-3 text-xs text-text-muted">
            <div>
              <span>策略配置: </span>
              <strong className="font-mono text-text-primary ml-1">
                {resolvedEnabledCount} 已启用 / {pausedStrategyCount} 已暂停
                {unknownStrategyCount > 0 ? ` / ${unknownStrategyCount} 未知` : ''}
              </strong>
            </div>
            <span className="opacity-30">·</span>
            <div>
              <span>当前在管 </span>
              <strong className="font-mono text-text-primary">
                {globalEntry.active_ticket_count ?? 0} 笔
              </strong>
              <span className="ml-1">· 管理权与保护状态见持仓详情</span>
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

