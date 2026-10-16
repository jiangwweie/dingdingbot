import { useQuery } from '@tanstack/react-query';
import { fetchOverview, overviewQueryKey } from '../api/overviewApi';
import { fetchControls, controlsQueryKey } from '../api/controlsApi';
import { fetchTickets, ticketsQueryKey } from '../api/ticketsApi';
import { fetchStrategies, strategiesQueryKey } from '../api/strategiesApi';
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
  'SOR-001': { name_zh: '旧单边突破策略', timeframe: '已停用' },
};

const STAGE_LABELS: Record<string, string> = {
  signal: '信号',
  admission: '准入',
  entry: '入场',
  protection: '保护',
  tp_runner: '止盈 / Runner',
  exit: '退出',
  reconciliation: '对账',
  review: '复盘',
};

function getUtcDayStartMs(nowMs = Date.now()): number {
  const d = new Date(nowMs);
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
}

function formatMetric(metric?: { value: string | null; unit: string; unavailable_reason?: string | null } | null): string {
  if (!metric || metric.value === null || metric.value === undefined) {
    return '--';
  }
  const num = Number(metric.value);
  const sign = num > 0 ? '+' : '';
  const unitSuffix = metric.unit === 'USDT' ? ' USDT' : metric.unit === 'R' ? ' R' : '';
  return `${sign}${metric.value}${unitSuffix}`;
}

export function useOverviewData() {
  const nowMs = Date.now();
  const todayStartMs = getUtcDayStartMs(nowMs);

  const overviewQuery = useQuery({
    queryKey: overviewQueryKey,
    queryFn: fetchOverview,
    staleTime: 10_000,
    retry: false,
  });

  const controlsQuery = useQuery({
    queryKey: controlsQueryKey,
    queryFn: fetchControls,
    staleTime: 10_000,
    retry: false,
  });

  const ticketsQuery = useQuery({
    queryKey: ticketsQueryKey({ from_ms: nowMs - 7 * 86_400_000, to_ms: nowMs }),
    queryFn: () => fetchTickets({ from_ms: nowMs - 7 * 86_400_000, to_ms: nowMs, limit: 50 }),
    staleTime: 10_000,
    retry: false,
  });

  const strategiesQuery = useQuery({
    queryKey: strategiesQueryKey({ from_ms: todayStartMs, to_ms: nowMs, view: 'current' }),
    queryFn: () => fetchStrategies({ from_ms: todayStartMs, to_ms: nowMs, view: 'current' }),
    staleTime: 15_000,
    retry: false,
  });

  const isLoading = overviewQuery.isLoading || controlsQuery.isLoading;
  const isError = overviewQuery.isError || controlsQuery.isError;
  const error = overviewQuery.error || controlsQuery.error;

  const rawOverview = overviewQuery.data?.data;
  const rawControls = controlsQuery.data;
  const rawTickets = ticketsQuery.data?.data?.items ?? [];
  const rawStrategies = strategiesQuery.data?.data?.items ?? [];

  // 1. System Pulse
  const freshness = overviewQuery.data?.freshness ?? 'unavailable';
  const conclusionLevel = rawOverview?.conclusion?.level ?? 'no_action';
  const incidentCount = rawOverview?.execution_incident_count ?? 0;
  const totalStrategies = rawControls?.strategies?.length ?? 0;
  const activeStrategies =
    rawControls?.strategies?.filter((s) => s.configured_state === 'enabled').length ?? 0;
  const globalEntryEnabled = rawControls?.global_entry?.configured_state === 'enabled';
  const entryStatusLabel = globalEntryEnabled ? 'ENTRY 正常' : 'ENTRY 暂停';

  let healthStatus: 'healthy' | 'attention' | 'danger' = 'healthy';
  let statusLabel = '正常运行';
  let summary = `${totalStrategies} 个策略 · ${entryStatusLabel} · ${
    incidentCount > 0 ? `${incidentCount} 项执行异常` : '无异常'
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
    statusLabel = freshness === 'stale' ? '数据陈旧' : freshness === 'unavailable' ? '数据不可用' : '需要关注';
    summary = `${totalStrategies} 个策略 · ${entryStatusLabel} · ${
      incidentCount > 0 ? `${incidentCount} 项异常待核实` : '存在需关注事实'
    }`;
  }

  const pulse: SystemPulseData = {
    status: healthStatus,
    status_label: statusLabel,
    summary,
    details:
      freshness === 'fresh'
        ? '观察、准入、生命周期服务持续运转中'
        : freshness === 'stale'
        ? '数据生成时间已滞后，请核实后台监控 Worker 状态'
        : '事实数据生成中或当前不可用',
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
    incidents_count: incidentCount,
    active_ticket_count: rawOverview?.active_ticket_count ?? rawControls?.account_capacity?.active_ticket_count ?? 0,
    ticket_capacity_total:
      rawOverview?.ticket_capacity ?? rawControls?.account_capacity?.max_concurrent_tickets ?? 2,
    snapshot_id: overviewQuery.data?.snapshot_id,
    generated_at: overviewQuery.data?.generated_at,
  };

  // 2. Today Performance Metrics
  const netPnlVal = rawOverview?.today_net_pnl?.value;
  const netRVal = rawOverview?.today_net_r?.value;

  const todayMetrics: TodayPerformanceMetrics = {
    net_pnl_formatted: formatMetric(rawOverview?.today_net_pnl),
    net_pnl_is_positive: netPnlVal !== null && netPnlVal !== undefined ? Number(netPnlVal) >= 0 : null,
    net_r_formatted: formatMetric(rawOverview?.today_net_r),
    net_r_is_positive: netRVal !== null && netRVal !== undefined ? Number(netRVal) >= 0 : null,
    today_signal_count: rawOverview?.today_signal_count ?? 0,
    admitted_signal_count: rawOverview?.admitted_signal_count ?? 0,
    rejected_signal_count: rawOverview?.rejected_signal_count ?? 0,
    execution_incident_count: incidentCount,
    pnl_unavailable_reason: rawOverview?.today_net_pnl?.unavailable_reason,
  };

  // 3. Active Episodes (mapped strictly from real Ticket items)
  const activeTicketIdSet = new Set(rawOverview?.active_ticket_ids ?? []);
  const activeTickets = rawTickets.filter(
    (t) =>
      t.terminal_at_ms === null ||
      t.ticket_status === 'active' ||
      activeTicketIdSet.has(t.ticket_id)
  );

  const episodes: TradeEpisodeSummary[] = activeTickets.map((t) => {
    const meta = STRATEGY_META[t.strategy_group_id] ?? {
      name_zh: t.strategy_group_id,
      timeframe: '1h close',
    };
    const stageZh = STAGE_LABELS[t.lifecycle_stage] ?? t.lifecycle_stage;

    return {
      ticket_id: t.ticket_id,
      strategy_id: t.strategy_group_id,
      strategy_name_zh: meta.name_zh,
      symbol: t.exchange_instrument_id,
      side: t.position_side,
      lifecycle_stage: t.lifecycle_stage,
      lifecycle_stage_zh: stageZh,
      completed_stage_count: t.completed_stage_count,
      total_stage_count: t.total_stage_count,
      ticket_status: t.ticket_status,
      issued_at_ms: t.issued_at_ms,
      issued_at_formatted: new Date(t.issued_at_ms).toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      }),
      attention_items: t.attention_items ?? [],
      net_pnl_formatted: formatMetric(t.net_pnl),
      net_r_formatted: formatMetric(t.net_r),
    };
  });

  // 4. Strategy Contributions
  const strategyItems: StrategyPerformanceItem[] =
    rawStrategies.length > 0
      ? rawStrategies.map((s) => {
          const meta = STRATEGY_META[s.strategy_group_id] ?? {
            name_zh: s.strategy_group_display_name ?? s.strategy_group_id,
            timeframe: '1h close',
          };
          const ctrl = rawControls?.strategies?.find((c) => c.strategy_group_id === s.strategy_group_id);
          const isPaused = ctrl?.configured_state === 'paused';

          return {
            strategy_id: s.strategy_group_id,
            name_zh: meta.name_zh,
            timeframe: meta.timeframe,
            status: isPaused ? 'paused' : 'running',
            status_label: isPaused ? '已暂停' : '运行中',
            ticket_count: s.ticket_count,
            win_count: s.win_count,
            loss_count: s.loss_count,
            net_pnl_formatted: formatMetric(s.net_pnl),
            net_r_formatted: formatMetric(s.net_r),
            active_tickets_count: 0,
          };
        })
      : (rawControls?.strategies ?? []).map((s) => {
          const meta = STRATEGY_META[s.strategy_group_id] ?? {
            name_zh: s.strategy_group_id,
            timeframe: '1h close',
          };
          const isPaused = s.configured_state === 'paused';
          return {
            strategy_id: s.strategy_group_id,
            name_zh: meta.name_zh,
            timeframe: meta.timeframe,
            status: isPaused ? 'paused' : 'running',
            status_label: isPaused ? '已暂停' : '运行中',
            ticket_count: 0,
            win_count: 0,
            loss_count: 0,
            net_pnl_formatted: '--',
            net_r_formatted: '--',
            active_tickets_count: 0,
          };
        });

  // 5. Attention Items
  const attentionList: AttentionItem[] = [];
  if (rawOverview?.attention_summary && rawOverview.attention_summary.length > 0) {
    rawOverview.attention_summary.forEach((att, idx) => {
      attentionList.push({
        id: `att-${idx}`,
        type: 'warning',
        title: att,
      });
    });
  }
  if (incidentCount > 0) {
    attentionList.push({
      id: 'incident-count',
      type: 'alert',
      title: `存在 ${incidentCount} 项未决执行异常 (Incident)`,
      detail: '请核实命令流水与对账状态',
    });
  }
  if (attentionList.length === 0) {
    attentionList.push({
      id: 'clean-state',
      type: 'info',
      title: '一切正常，无需介入',
      detail: '当前无阻断、无执行异常、全局准入及保护策略处于健康状态。',
    });
  }

  const refetch = async () => {
    await Promise.all([
      overviewQuery.refetch(),
      controlsQuery.refetch(),
      ticketsQuery.refetch(),
      strategiesQuery.refetch(),
    ]);
  };

  return {
    isLoading,
    isError,
    error,
    pulse,
    todayMetrics,
    episodes,
    strategies: strategyItems,
    attentionList,
    refetch,
  };
}
