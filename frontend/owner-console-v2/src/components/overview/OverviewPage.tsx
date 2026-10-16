import React, { useState } from 'react';
import { SystemPulseCard } from './SystemPulseCard';
import { TodayMetricsDeck } from './TodayMetricsDeck';
import { ActiveEpisodesSection } from './ActiveEpisodesSection';
import { StrategyContributionSection } from './StrategyContributionSection';
import { RecentAttentionSection } from './RecentAttentionSection';
import { CausalityDrawer } from './CausalityDrawer';
import {
  mockSystemPulse,
  mockTodayMetrics,
  mockActiveEpisodes,
  mockStrategyContributions,
  mockRecentEvents,
} from '../../mock/overviewData';
import type { TradeEpisodeSummary } from '../../types/overview';

interface OverviewPageProps {
  onNavigateToControls: () => void;
}

export const OverviewPage: React.FC<OverviewPageProps> = ({ onNavigateToControls }) => {
  const [pulse] = useState(mockSystemPulse);
  const [metrics] = useState(mockTodayMetrics);
  const [episodes] = useState(mockActiveEpisodes);
  const [strategies] = useState(mockStrategyContributions);
  const [events] = useState(mockRecentEvents);

  // Causality Drawer State
  const [selectedEpisode, setSelectedEpisode] = useState<TradeEpisodeSummary | null>(null);

  return (
    <div className="space-y-4">
      {/* 1. 顶部系统脉搏横幅 (5 秒定心丸) */}
      <SystemPulseCard
        pulse={pulse}
        onNavigateToControls={onNavigateToControls}
      />

      {/* 2. 今日核心表现 (净收益 $ / 净 R / 已完结交易 - 无传统大卡片余额) */}
      <TodayMetricsDeck metrics={metrics} />

      {/* 3. 当前在管交易 (Active Trade Episodes) */}
      <ActiveEpisodesSection
        episodes={episodes}
        onSelectEpisode={(ep) => setSelectedEpisode(ep)}
      />

      {/* 4. 双栏平衡区：左侧策略矩阵贡献 + 右侧异常与事件关注 */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        {/* 左侧：今日策略表现 (动态 5 策略矩阵) */}
        <div className="lg:col-span-7">
          <StrategyContributionSection strategies={strategies} />
        </div>

        {/* 右侧：系统异常与需要关注 (0项异常 · 一切正常 · 最近通知) */}
        <div className="lg:col-span-5">
          <RecentAttentionSection
            events={events}
            incidentsCount={pulse.incidents_count}
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
