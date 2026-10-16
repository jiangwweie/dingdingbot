import React, { useState } from 'react';
import { useOverviewData } from '../../hooks/useOverviewData';
import { SystemPulseCard } from './SystemPulseCard';
import { TodayMetricsDeck } from './TodayMetricsDeck';
import { ActiveEpisodesSection } from './ActiveEpisodesSection';
import { StrategyContributionSection } from './StrategyContributionSection';
import { RecentAttentionSection } from './RecentAttentionSection';
import { CausalityDrawer } from './CausalityDrawer';
import type { TradeEpisodeSummary } from '../../types/overview';
import { RefreshCw, AlertCircle } from 'lucide-react';

interface OverviewPageProps {
  onNavigateToControls: () => void;
}

export const OverviewPage: React.FC<OverviewPageProps> = ({ onNavigateToControls }) => {
  const {
    isLoading,
    isError,
    error,
    pulse,
    todayMetrics,
    episodes,
    strategies,
    attentionList,
    refetch,
  } = useOverviewData();

  const [selectedEpisode, setSelectedEpisode] = useState<TradeEpisodeSummary | null>(null);

  const handleManualRefresh = async () => {
    await refetch();
  };


  if (isLoading) {
    return (
      <div className="py-24 text-center">
        <div className="inline-block h-7 w-7 border-2 border-brand/30 border-t-brand rounded-full animate-spin mb-3" />
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
      <div className="rounded-xl border border-danger/30 bg-surface p-8 text-center max-w-lg mx-auto my-12 shadow-sm">
        <div className="inline-flex items-center justify-center h-12 w-12 rounded-full bg-danger/10 text-danger mb-4">
          <AlertCircle className="h-6 w-6" />
        </div>
        <h3 className="text-base font-bold text-text-primary">
          无法连接 Owner API
        </h3>
        <p className="mt-1.5 text-xs text-text-secondary leading-relaxed">
          {error instanceof Error ? error.message : '请检查生产网络或 HTTPS 证书是否就绪。严格拒绝任何静默 Mock 兜底。'}
        </p>
        <div className="mt-5">
          <button
            type="button"
            onClick={handleManualRefresh}
            className="inline-flex items-center gap-1.5 rounded bg-brand px-4 py-2 text-xs font-semibold text-white hover:bg-brand/90 transition-colors shadow-xs"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span>重新连接 (Retry)</span>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* 1. 顶部系统脉搏横幅 (5 秒定心丸 · 组合 /overview 与 /controls) */}
      <SystemPulseCard
        pulse={pulse}
        onNavigateToControls={onNavigateToControls}
      />

      {/* 2. 今日核心表现 (真实今日净收益 $ / 净 R / 今日信号与准入) */}
      <TodayMetricsDeck metrics={todayMetrics} />

      {/* 3. 当前在管交易 (Active Trade Episodes - 严格来自真实 Ticket 列表) */}
      <ActiveEpisodesSection
        episodes={episodes}
        onSelectEpisode={(ep) => setSelectedEpisode(ep)}
      />

      {/* 4. 双栏平衡区：左侧策略矩阵真实表现 + 右侧真实关注与异常 */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        {/* 左侧：今日策略表现 (真实读取 /strategies 快照) */}
        <div className="lg:col-span-7">
          <StrategyContributionSection strategies={strategies} />
        </div>

        {/* 右侧：需要关注与执行异常 (来自 overview.conclusion 与 attention_summary) */}
        <div className="lg:col-span-5">
          <RecentAttentionSection
            attentionList={attentionList}
            incidentsCount={pulse.incidents_count}
            conclusion={pulse.conclusion ?? 'no_action'}
          />

        </div>
      </div>

      {/* 5. 交易因果全链路 8 阶段真实追溯抽屉 */}
      <CausalityDrawer
        episode={selectedEpisode}
        onClose={() => setSelectedEpisode(null)}
      />
    </div>
  );
};
