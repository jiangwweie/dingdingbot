import { useEffect, useMemo, useState } from 'react';
import { mapManagementHealth } from '../mapping/managementHealthMapping';
import { effectiveOverviewFreshness, overviewLiveOptions } from '../mapping/overviewSnapshot';
import { useQuery } from '@tanstack/react-query';
import { fetchOverview, overviewQueryKey } from '../api/overviewApi';
import { fetchControls, controlsQueryKey } from '../api/controlsApi';
import { fetchTickets, ticketsQueryKey } from '../api/ticketsApi';
import { formatReviewMoneyMetric } from '../mapping/reviewMapping';
import { getBeijingDayStartMs } from '../utils/timeRange';
import { computeUnloadedActiveCount, mapActiveTicketToOverviewEpisode } from '../mapping/ticketMapping';
import type {
  SystemPulseData,
  TodayPerformanceMetrics,
  TradeEpisodeSummary,
  StrategyPerformanceItem,
  AttentionItem,
} from '../types/overview';

const STRATEGY_META: Record<string, { name_zh: string; timeframe: string }> = {
  'CPM-RO-001': { name_zh: '均线回踩做多', timeframe: '1h close' },
  'BRF2-001': { name_zh: '假反弹衰竭做空', timeframe: '1h close' },
  'MI-001': { name_zh: '相对强弱冲量', timeframe: '1h close' },
  'MPG-001': { name_zh: '趋势动量持续', timeframe: '1h close' },
  'SOR-1H-001': { name_zh: '单边突破 (1h/15m)', timeframe: '1h close' },
  'SOR-1H-LONG-001': { name_zh: 'SOR-多', timeframe: '1h close' },
  'SOR-1H-SHORT-001': { name_zh: 'SOR-空', timeframe: '1h close' },
  'SOR-001': { name_zh: '旧单边突破策略', timeframe: '已停用' },
};

function formatMetric(metric?: { value: string | null; unit: string; unavailable_reason?: string | null } | null): string {
  if (!metric || metric.value==null) return '--';
  return formatReviewMoneyMetric(metric as import('../types/trades').MoneyMetric,{sign:true}).formatted;
}

import { cleanSymbol } from '../utils/symbol';
export { cleanSymbol };

export function useOverviewData() {
  const [displayNow, setDisplayNow] = useState(Date.now);
  useEffect(() => {
    const timer = window.setInterval(() => setDisplayNow(Date.now()), 5_000);
    const update = () => setDisplayNow(Date.now());
    document.addEventListener('visibilitychange', update);
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', update); };
  }, []);

  const overviewQuery = useQuery({
    queryKey: overviewQueryKey,
    queryFn: fetchOverview,
    ...overviewLiveOptions,
    staleTime: 15_000,
    retry: false,
  });

  const controlsQuery = useQuery({
    queryKey: controlsQueryKey,
    queryFn: fetchControls,
    ...overviewLiveOptions,
    staleTime: 15_000,
    retry: false,
  });

  const ticketsParams = useMemo(() => ({ limit: 100 }), []);
  const ticketsQuery = useQuery({
    queryKey: ticketsQueryKey(ticketsParams),
    queryFn: () => fetchTickets(ticketsParams),
    ...overviewLiveOptions,
    staleTime: 15_000,
    retry: false,
  });

  const isLoading = overviewQuery.isLoading || controlsQuery.isLoading;
  const isError = overviewQuery.isError || controlsQuery.isError;
  const error = overviewQuery.error || controlsQuery.error;

  const rawOverview = overviewQuery.data?.data;
  const rawControls = controlsQuery.data;
  const rawTickets = ticketsQuery.data?.data?.items ?? [];
  const todayStartMs = rawOverview?.performance?.from_ms ?? getBeijingDayStartMs();
  const rawObservedMs = rawOverview?.observed_at_ms ?? Date.now();
  const todayEndMs = rawObservedMs > todayStartMs ? rawObservedMs : todayStartMs + 60_000;

  // Active tickets mapping (terminal_at_ms === null means actively in flight)
  const authoritativeActiveCount = rawOverview?.active_ticket_count ?? null;
  const activeTicketIdSet = new Set(rawOverview?.active_ticket_ids ?? []);
  const matchingActiveTickets = rawTickets.filter(
    (t) =>
      t.terminal_at_ms === null ||
      t.ticket_status === 'active' ||
      activeTicketIdSet.has(t.ticket_id)
  );

  // If ticketsQuery failed, we do NOT pretend active tickets is 0
  const activeTicketCount = authoritativeActiveCount ?? matchingActiveTickets.length;
  const unloadedActiveCount = computeUnloadedActiveCount(
    authoritativeActiveCount,
    matchingActiveTickets.length
  );

  // Account capacity - strictly no default 3!
  const maxCapacity =
    rawControls?.account_capacity?.max_concurrent_tickets ??
    (rawOverview?.ticket_capacity != null && rawOverview.ticket_capacity > 0
      ? (activeTicketCount ?? 0) + rawOverview.ticket_capacity
      : null);

  // Count active tickets per strategy
  const activeCountByStrategy = new Map<string, number>();
  matchingActiveTickets.forEach((t) => {
    activeCountByStrategy.set(
      t.strategy_group_id,
      (activeCountByStrategy.get(t.strategy_group_id) ?? 0) + 1
    );
  });
  // Also check strategy_side_active_counts from account capacity if matchingActiveTickets is empty
  if (matchingActiveTickets.length === 0 && rawControls?.account_capacity?.strategy_side_active_counts) {
    Object.entries(rawControls.account_capacity.strategy_side_active_counts).forEach(
      ([scopeKey, count]) => {
        const strategyId = scopeKey.split(':')[0];
        if (strategyId) {
          activeCountByStrategy.set(
            strategyId,
            (activeCountByStrategy.get(strategyId) ?? 0) + count
          );
        }
      }
    );
  }

  // 1. System Pulse
  const freshness = effectiveOverviewFreshness(
    overviewQuery.data?.freshness ?? 'unavailable',
    overviewQuery.data?.generated_at,
    Math.max(displayNow, overviewQuery.dataUpdatedAt),
    overviewQuery.dataUpdatedAt || undefined,
  );
  const conclusionLevel = rawOverview?.conclusion?.level ?? 'no_action';
  const incidentCount = rawOverview?.execution_incident_count ?? 0;
  const totalStrategies = rawControls?.strategies?.length ?? 0;
  const activeStrategies =
    rawControls?.strategies?.filter((s) => s.configured_state === 'enabled').length ?? 0;
  const globalEntryEnabled = rawControls?.global_entry?.configured_state === 'enabled';
  const entryStatusLabel = globalEntryEnabled ? '新开仓开关：开启' : '新开仓开关：已暂停';

  let healthStatus: 'healthy' | 'attention' | 'danger' = 'healthy';
  let statusLabel = '正常运行';
  let summary = `策略已启用 ${activeStrategies}/${totalStrategies} · ${entryStatusLabel} · ${
    incidentCount > 0 ? `${incidentCount} 项执行异常` : '无执行异常'
  }`;

  if (conclusionLevel === 'intervention' || freshness === 'contradictory') {
    healthStatus = 'danger';
    statusLabel = '需立即介入';
    summary = '系统检测到数据冲突或需要 Owner 紧急介入';
  } else if (
    conclusionLevel === 'attention' ||
    freshness === 'stale' ||
    freshness === 'unavailable' ||
    incidentCount > 0 ||
    !globalEntryEnabled
  ) {
    healthStatus = 'attention';
    statusLabel =
      freshness === 'stale'
        ? '数据陈旧'
        : freshness === 'unavailable'
        ? '数据不可用'
        : '需要关注';
    summary = `策略已启用 ${activeStrategies}/${totalStrategies} · ${entryStatusLabel} · ${
      incidentCount > 0 ? `${incidentCount} 项异常待核实` : '存在需关注事实'
    }`;
  }

  const managementHealth = mapManagementHealth(rawOverview?.management_feed, rawOverview?.observed_at_ms ?? Date.now());
  if (managementHealth.blocked && healthStatus !== 'danger') {
    healthStatus = 'attention';
    statusLabel = '新开仓受阻';
    summary = managementHealth.summary;
  }
  const pulse: SystemPulseData = {
    status: healthStatus,
    status_label: statusLabel,
    summary,
    details: managementHealth.details || (
      freshness === 'fresh'
        ? '观察、准入、生命周期服务持续运转中'
        : freshness === 'stale'
        ? '数据生成时间已滞后，请核实后台监控 Worker 状态'
        : '事实数据生成中或当前只读证据不可用'),
    conclusion: conclusionLevel,
    freshness,
    freshness_label:
      freshness === 'fresh'
        ? 'FRESH (实时)'
        : freshness === 'stale'
        ? 'STALE (滞后)'
        : freshness === 'contradictory'
        ? 'CONTRADICTORY (矛盾)'
        : 'UNAVAILABLE',
    total_strategy_count: totalStrategies,
    active_strategy_count: activeStrategies,
    entry_status_label: entryStatusLabel,
    global_entry_enabled: globalEntryEnabled,
    incidents_count: incidentCount,
    active_ticket_count: activeTicketCount,
    ticket_capacity_total: maxCapacity,
    snapshot_id: overviewQuery.data?.snapshot_id,
    generated_at: overviewQuery.data?.generated_at,
  };

  // 2. Today Performance Metrics (with per-metric coverage support)
  const netPnlVal = rawOverview?.today_net_pnl?.value;
  const netRVal = rawOverview?.today_net_r?.value;
  const perf = rawOverview?.performance;
  const metricCov = (perf?.metric_coverage ?? {}) as Record<
    string,
    { available_count?: number; total_count?: number } | undefined
  >;

  const pnlAvail = metricCov.net_pnl?.available_count ?? perf?.confirmed_count;
  const pnlTotal = metricCov.net_pnl?.total_count ?? perf?.sample_count;
  const pnlIsPartial =
    typeof pnlAvail === 'number' && typeof pnlTotal === 'number' && pnlAvail < pnlTotal;
  const pnlCoverage =
    typeof pnlAvail === 'number' && typeof pnlTotal === 'number'
      ? `${pnlIsPartial ? '部分核实' : '已核实'} ${pnlAvail}/${pnlTotal} 笔${pnlIsPartial ? ' · 部分合计' : ''}`
      : undefined;

  const rAvail = metricCov.net_r?.available_count ?? perf?.confirmed_count;
  const rTotal = metricCov.net_r?.total_count ?? perf?.sample_count;
  const rIsPartial =
    typeof rAvail === 'number' && typeof rTotal === 'number' && rAvail < rTotal;
  const rCoverage =
    typeof rAvail === 'number' && typeof rTotal === 'number'
      ? `${rIsPartial ? '部分核实' : '已核实'} ${rAvail}/${rTotal} 笔${rIsPartial ? ' · 部分合计' : ''}`
      : undefined;

  const todayMetrics: TodayPerformanceMetrics = {
    income_coverage: perf
      ? `上海今日终态交易 · ${pnlIsPartial ? '部分核实' : '已核实'} ${perf.confirmed_count}/${perf.sample_count} 笔${
          perf.confirmed_count < perf.sample_count ? ' · 部分合计' : ''
        }`
      : undefined,
    pnl_coverage: pnlCoverage,
    pnl_is_partial: pnlIsPartial,
    r_coverage: rCoverage,
    r_is_partial: rIsPartial,
    net_pnl_formatted: formatMetric(rawOverview?.today_net_pnl),
    net_pnl_is_positive:
      netPnlVal !== null && netPnlVal !== undefined ? Number(netPnlVal) >= 0 : null,
    net_r_formatted: formatMetric(rawOverview?.today_net_r),
    net_r_is_positive:
      netRVal !== null && netRVal !== undefined ? Number(netRVal) >= 0 : null,
    today_signal_count: rawOverview?.today_signal_count ?? 0,
    admitted_signal_count: rawOverview?.admitted_signal_count ?? 0,
    rejected_signal_count: rawOverview?.rejected_signal_count ?? 0,
    execution_incident_count: incidentCount,
    pnl_unavailable_reason: rawOverview?.today_net_pnl?.unavailable_reason,
  };

  // 3. Active Episodes (mapped strictly from real Ticket items, empty if tickets query failed)
  const episodes: TradeEpisodeSummary[] = ticketsQuery.isError
    ? []
    : matchingActiveTickets.map((t) => {
        const meta = STRATEGY_META[t.strategy_group_id] ?? {
          name_zh: t.strategy_group_id,
          timeframe: '1h close',
        };
        return mapActiveTicketToOverviewEpisode(t, meta.name_zh);
      });

  // Per-group contributions and headline are from the same full-window snapshot.
  const strategyItems: StrategyPerformanceItem[] = Object.entries(rawOverview?.performance?.by_strategy_group ?? {}).map(([group,stats])=>{
    const meta=STRATEGY_META[group] ?? {name_zh:group,timeframe:'1h close'};
    const paused=rawControls?.strategies?.find(c=>c.strategy_group_id===group)?.configured_state==='paused';
    return {strategy_id:group,strategy_version_id:null,name_zh:meta.name_zh,timeframe:meta.timeframe,status:paused?'paused':'running',status_label:paused?'已暂停':'已启用',ticket_count:stats.sample_count,win_count:stats.win_count,loss_count:stats.loss_count,net_pnl_formatted:formatMetric(stats.verified_totals.net_pnl),net_r_formatted:formatMetric(stats.verified_totals.net_r),active_tickets_count:activeCountByStrategy.get(group)??0,is_metrics_available:stats.confirmed_count>0};
  });

  // 5. Attention Items (derived strictly from authoritative facts, never deduce global protection completeness or fabricate worker watermark details)
  const attentionList: AttentionItem[] = [];

  const inferActionTarget = (text: string): AttentionItem['action_target'] => {
    if (text.includes('人工管理') || text.includes('外部干预') || text.includes('仓位') || text.includes('持仓')) {
      return 'active_episodes';
    }
    if (text.includes('ENTRY') || text.includes('准入') || text.includes('暂停')) {
      return 'controls';
    }
    return undefined;
  };

  if (rawOverview?.conclusion?.summary && conclusionLevel !== 'no_action') {
    const summaryText = rawOverview.conclusion.summary;
    attentionList.push({
      id: 'conclusion-summary',
      type: conclusionLevel === 'intervention' ? 'alert' : 'warning',
      title: summaryText,
      detail: conclusionLevel === 'intervention' ? '需立即介入核实' : undefined,
      action_target: inferActionTarget(summaryText),
    });
  }

  if (freshness === 'unavailable') {
    attentionList.push({
      id: 'freshness-unavailable',
      type: 'warning',
      title: '数据新鲜度为 UNAVAILABLE',
      detail: '概览事实数据正在生成中或后台只读证据水印滞后。',
    });
  } else if (freshness === 'stale') {
    attentionList.push({
      id: 'freshness-stale',
      type: 'warning',
      title: '数据新鲜度为 STALE (滞后)',
      detail: '概览事实数据已滞后，请核实后台监控 Worker 状态。',
    });
  }

  if (!globalEntryEnabled) {
    attentionList.push({
      id: 'global-entry-paused',
      type: 'warning',
      title: '全局 ENTRY 入场处于暂停状态',
      detail: '新入场被阻断，存量持仓继续受生命周期保护。',
      action_target: 'controls',
    });
  }

  if (rawOverview?.attention_summary && rawOverview.attention_summary.length > 0) {
    rawOverview.attention_summary.forEach((att, idx) => {
      if (att !== rawOverview?.conclusion?.summary && !attentionList.some((item) => item.title === att)) {
        attentionList.push({
          id: `att-${idx}`,
          type: 'warning',
          title: att,
          action_target: inferActionTarget(att),
        });
      }
    });
  }

  if (incidentCount > 0) {
    attentionList.push({
      id: 'incident-count',
      type: 'alert',
      title: `存在 ${incidentCount} 项未决执行异常 (Incident)`,
      detail: '请核实命令流水与对账状态',
      action_target: 'trades',
    });
  }


  const refetch = async () => {
    await Promise.all([
      overviewQuery.refetch(),
      controlsQuery.refetch(),
      ticketsQuery.refetch(),

    ]);
  };

  return {
    notificationDelivery: rawOverview?.notification_delivery,
    isLoading,
    isError,
    error,
    ticketsLoading: ticketsQuery.isLoading,
    ticketsError: ticketsQuery.isError
      ? ticketsQuery.error instanceof Error
        ? ticketsQuery.error.message
        : '无法读取 Ticket 列表'
      : null,
    unloadedActiveCount,
    strategiesLoading: overviewQuery.isLoading,
    strategiesError: overviewQuery.isError ? '收益统计读取失败' : null,
    todayStartMs,
    todayEndMs,
    refetchTickets: () => ticketsQuery.refetch(),
    refetchStrategies: () => overviewQuery.refetch(),
    pulse,
    todayMetrics,
    episodes,
    strategies: strategyItems,
    attentionList,
    refetch,
  };
}
