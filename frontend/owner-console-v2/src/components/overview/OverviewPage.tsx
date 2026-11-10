import React, { useState } from 'react';
import { useOverviewData } from '../../hooks/useOverviewData';
import { SystemPulseCard } from './SystemPulseCard';
import { TodayMetricsDeck } from './TodayMetricsDeck';
import { ActiveEpisodesSection } from './ActiveEpisodesSection';
import { StrategyContributionSection } from './StrategyContributionSection';
import { RecentAttentionSection } from './RecentAttentionSection';
import { CausalityDrawer } from './CausalityDrawer';
import { DirectionalRiskCard } from './DirectionalRiskCard';
import type { TradeEpisodeSummary } from '../../types/overview';
import { RefreshCw, AlertCircle, Send } from 'lucide-react';

interface OverviewPageProps {
  onNavigateToControls: () => void;
}

export const OverviewPage: React.FC<OverviewPageProps> = ({ onNavigateToControls }) => {
  const {
    isLoading,
    isError,
    error,
    ticketsLoading,
    ticketsError,
    unloadedActiveCount,
    refetchTickets,
    pulse,
    todayMetrics,
    episodes,
    strategies,
    attentionList,
    notificationDelivery,
    refetch,
  } = useOverviewData();

  const [selectedEpisode, setSelectedEpisode] = useState<TradeEpisodeSummary | null>(null);

  const handleManualRefresh = async () => {
    await refetch();
  };

  if (isLoading) {
    return (
      <div className="py-24 text-center">
        <div className="inline-block h-8 w-8 border-2 border-brand/30 border-t-brand rounded-full animate-spin mb-3.5" />
        <h3 className="text-sm font-semibold text-text-primary">
          正在从生产 API 加载控制台事实...
        </h3>
        <p className="mt-1 text-xs text-text-muted">
          读取 /api/owner/v1/overview、/controls、/tickets、/strategies
        </p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-xl border border-rose-500/30 bg-surface p-8 text-center max-w-lg mx-auto my-12 shadow-sm">
        <div className="inline-flex items-center justify-center h-12 w-12 rounded-full bg-rose-500/10 text-rose-600 dark:text-rose-400 mb-4">
          <AlertCircle className="h-6 w-6" />
        </div>
        <h3 className="text-base font-bold text-text-primary">
          无法连接 Owner API
        </h3>
        <p className="mt-2 text-xs text-text-secondary leading-relaxed">
          {error instanceof Error ? error.message : '请检查生产网络或 HTTPS 证书是否就绪。严格拒绝任何静默 Mock 兜底。'}
        </p>
        <div className="mt-6">
          <button
            type="button"
            onClick={handleManualRefresh}
            className="inline-flex items-center gap-1.5 rounded-md bg-brand px-4 py-2 text-xs font-semibold text-white hover:bg-brand/90 transition-colors shadow-xs cursor-pointer"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span>重新连接 (Retry)</span>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-in fade-in-50 duration-150">
      {/* 1. 顶部系统脉搏横幅 */}
      <SystemPulseCard
        pulse={pulse}
        onNavigateToControls={onNavigateToControls}
      />

      {/* 飞书通知投递状态条 */}
      <div className="rounded-lg border border-border bg-surface px-3 sm:px-4 py-2.5 text-xs flex flex-wrap items-center justify-between gap-2 sm:gap-3 shadow-2xs" aria-label="飞书通知投递状态">
        <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
          <Send className="h-3.5 w-3.5 text-brand flex-none" />
          <strong className="font-semibold text-text-primary">首尔飞书通知</strong>
          <span className="text-text-muted">·</span>
          <span className="text-text-secondary">
            {notificationDelivery?.channel_state === 'configured'
              ? '独立机器人已配置'
              : notificationDelivery?.channel_state === 'missing'
              ? '机器人未配置'
              : '通道待核实'}
          </span>
          {notificationDelivery && (
            <span className="font-mono text-text-muted">
              (待发 {notificationDelivery.pending_count}{notificationDelivery.pending_count_capped ? '+' : ''} · 失败 {notificationDelivery.failed_count}{notificationDelivery.failed_count_capped ? '+' : ''})
            </span>
          )}
        </div>
        <span className="text-text-muted text-[11px] font-mono break-all sm:break-normal">
          {notificationDelivery?.last_accepted_at_ms
            ? `最近平台接受 ${new Date(notificationDelivery.last_accepted_at_ms).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })}`
            : '尚无平台接受记录'} · 不代表已读
        </span>
      </div>

      {/* 2. 今日核心表现 */}
      <TodayMetricsDeck metrics={todayMetrics} />

      {/* 方向风险偏好 */}
      <DirectionalRiskCard />

      {/* 3. 当前在管交易 (Active Trade Episodes) */}
      <ActiveEpisodesSection
        episodes={episodes}
        onSelectEpisode={(ep) => setSelectedEpisode(ep)}
        isLoading={ticketsLoading}
        isError={Boolean(ticketsError)}
        errorMessage={ticketsError}
        unloadedActiveCount={unloadedActiveCount}
        onRetry={refetchTickets}
      />

      {/* 4. 双栏平衡区：左侧策略表现 + 右侧关注与异常 */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* 左侧：今日策略表现 */}
        <div className="lg:col-span-7">
          <StrategyContributionSection strategies={strategies} />
        </div>

        {/* 右侧：需要关注与执行异常 */}
        <div className="lg:col-span-5">
          <RecentAttentionSection
            attentionList={attentionList}
            incidentsCount={pulse.incidents_count}
            freshness={pulse.freshness}
        conclusion={pulse.conclusion ?? 'no_action'}
          />
        </div>
      </div>

      {/* 5. 交易因果全链路 8 阶段追溯抽屉 */}
      <CausalityDrawer
        episode={selectedEpisode}
        onClose={() => setSelectedEpisode(null)}
      />
    </div>
  );
};
