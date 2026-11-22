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
import type { NavTabId } from '../Navbar';
import { buildOverviewSameScopeSearch } from '../../utils/urlParams';
import { RefreshCw, AlertCircle, Send } from 'lucide-react';

interface OverviewPageProps {
  onNavigateToControls: () => void;
  onNavigateToTab?: (tab: NavTabId) => void;
  onNavigateWithSearch?: (tab: NavTabId, search: string) => void;
}

export const OverviewPage: React.FC<OverviewPageProps> = ({
  onNavigateToControls,
  onNavigateToTab,
  onNavigateWithSearch,
}) => {
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
    todayStartMs,
    todayEndMs,
    episodes,
    strategies,
    attentionList,
    notificationDelivery,
    refetch,
  } = useOverviewData();

  const [selectedEpisode, setSelectedEpisode] = useState<TradeEpisodeSummary | null>(null);
  const [highlightedStrategyId, setHighlightedStrategyId] = useState<string | null>(null);

  const handleManualRefresh = async () => {
    await refetch();
  };

  const navigateToSameScopeTab = (tab: 'review' | 'trades' | 'strategies', strategyGroupId?: string) => {
    const search = buildOverviewSameScopeSearch(tab, {
      from_ms: todayStartMs,
      to_ms: todayEndMs,
      strategy_group_id: strategyGroupId,
    });
    if (onNavigateWithSearch) {
      onNavigateWithSearch(tab, search);
      return;
    }
    if (typeof window !== 'undefined') {
      window.history.pushState(null, '', `${window.location.pathname}?${search}`);
    }
    onNavigateToTab?.(tab);
  };

  const scrollToElement = (id: string) => {
    if (typeof document === 'undefined') return;
    const el = document.getElementById(id);
    if (el && typeof el.scrollIntoView === 'function') {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  const handleLocateStrategy = (strategyId: string) => {
    setHighlightedStrategyId(strategyId);
    scrollToElement('active-episodes');
    setTimeout(() => {
      setHighlightedStrategyId((prev) => (prev === strategyId ? null : prev));
    }, 2500);
  };

  const handleLocateActiveEpisodes = () => {
    scrollToElement('active-episodes');
  };

  const handleScrollToAttention = () => {
    scrollToElement('recent-attention-section');
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

  const hasFeishuNotice =
    notificationDelivery &&
    (notificationDelivery.channel_state !== 'configured' ||
      notificationDelivery.pending_count > 0 ||
      notificationDelivery.failed_count > 0);

  return (
    <div className="space-y-5 animate-in fade-in-50 duration-150">
      {/* 1. 顶部状态区：系统脉搏 + 紧凑飞书通知状态 */}
      <div className="space-y-2">
        <SystemPulseCard
          pulse={pulse}
          onNavigateToControls={onNavigateToControls}
          attentionCount={attentionList.length}
          onScrollToAttention={handleScrollToAttention}
        />

        {/* 飞书通知投递状态条（保留已配置/待发/失败常驻，最近接受时间可点击/键盘展开） */}
        <div
          className={`rounded-lg border px-3 sm:px-4 py-2 text-xs flex flex-wrap items-center justify-between gap-2 sm:gap-3 shadow-2xs ${
            hasFeishuNotice
              ? 'border-amber-500/30 bg-amber-500/5'
              : 'border-border bg-surface'
          }`}
          aria-label="飞书通知投递状态"
        >
          <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
            <Send className="h-3.5 w-3.5 text-brand flex-none" />
            <strong className="font-semibold text-text-primary">首尔飞书通知</strong>
            <span className="text-text-muted">·</span>
            <span className="text-text-secondary font-medium">
              {notificationDelivery?.channel_state === 'configured'
                ? '已配置'
                : notificationDelivery?.channel_state === 'missing'
                ? '机器人未配置'
                : '通道待核实'}
            </span>
            {notificationDelivery && (
              <span className="font-mono text-text-muted">
                · 待发 {notificationDelivery.pending_count}
                {notificationDelivery.pending_count_capped ? '+' : ''} · 失败{' '}
                {notificationDelivery.failed_count}
                {notificationDelivery.failed_count_capped ? '+' : ''}
              </span>
            )}
          </div>

          <details className="text-text-muted text-[11px] font-mono sm:text-right">
            <summary className="cursor-pointer select-none font-sans text-brand hover:underline focus-visible:outline-2 focus-visible:outline-brand rounded px-1 inline-block">
              投递时间详情
            </summary>
            <div className="mt-1 break-all sm:break-normal">
              {notificationDelivery?.last_accepted_at_ms
                ? `最近平台接受 ${new Date(notificationDelivery.last_accepted_at_ms).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })}`
                : '尚无平台接受记录'}{' '}
              · 不代表已读
            </div>
          </details>
        </div>
      </div>

      {/* 2. 今日核心收益摘要 */}
      <TodayMetricsDeck
        metrics={todayMetrics}
        onNavigateToReview={
          onNavigateToTab || onNavigateWithSearch
            ? () => navigateToSameScopeTab('review')
            : undefined
        }
        onNavigateToTrades={
          onNavigateToTab || onNavigateWithSearch
            ? () => navigateToSameScopeTab('trades')
            : undefined
        }
      />

      {/* 3. 当前在管交易 (优先排在方向风险偏好之前) */}
      <ActiveEpisodesSection
        episodes={episodes}
        onSelectEpisode={(ep) => setSelectedEpisode(ep)}
        isLoading={ticketsLoading}
        isError={Boolean(ticketsError)}
        errorMessage={ticketsError}
        unloadedActiveCount={unloadedActiveCount}
        onRetry={refetchTickets}
        highlightedStrategyId={highlightedStrategyId}
      />

      {/* 4. 方向风险偏好 (单行摘要默认折叠，点击展开控制与详情) */}
      <DirectionalRiskCard />

      {/* 5. 双栏平衡区：左侧策略表现 + 右侧关注与异常 */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* 左侧：今日策略表现 */}
        <div className="lg:col-span-7">
          <StrategyContributionSection
            strategies={strategies}
            onLocateStrategy={handleLocateStrategy}
          />
        </div>

        {/* 右侧：需要关注与执行异常 */}
        <div className="lg:col-span-5">
          <RecentAttentionSection
            attentionList={attentionList}
            incidentsCount={pulse.incidents_count}
            conclusion={pulse.conclusion ?? 'no_action'}
            freshness={pulse.freshness}
            onNavigateToControls={onNavigateToControls}
            onLocateActiveEpisodes={handleLocateActiveEpisodes}
            onNavigateToTrades={
              onNavigateToTab || onNavigateWithSearch
                ? () => navigateToSameScopeTab('trades')
                : undefined
            }
          />
        </div>
      </div>

      {/* 6. 交易因果全链路 8 阶段追溯抽屉 */}
      <CausalityDrawer
        episode={selectedEpisode}
        onClose={() => setSelectedEpisode(null)}
      />
    </div>
  );
};
