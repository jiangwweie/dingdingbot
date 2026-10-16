import type { TradeListItem, TradeEpisode, MoneyMetric, TradesSummaryMetrics } from '../types/trades.ts';
import { cleanSymbol } from '../utils/symbol.ts';
import { formatDuration } from '../utils/time.ts';

export const STRATEGY_META: Record<string, { name_zh: string; timeframe: string }> = {
  'CPM-RO-001': { name_zh: '均线回踩做多', timeframe: '1h close' },
  'BRF2-001': { name_zh: '假反弹衰竭做空', timeframe: '1h close' },
  'MI-001': { name_zh: '相对强弱冲量', timeframe: '1h close' },
  'MPG-001': { name_zh: '趋势动量持续', timeframe: '1h close' },
  'SOR-1H-001': { name_zh: '单边突破 (1h/15m)', timeframe: '1h close' },
  'SOR-001': { name_zh: '旧单边突破策略', timeframe: '已退役' },
  'SOR-US-EQ-PERP-001': { name_zh: '美股 Perp 突破', timeframe: '1h close' },
};

export const STAGE_LABELS_ZH: Record<string, string> = {
  signal: '信号 (Signal)',
  admission: '准入评估 (Admission)',
  entry: '入场下单 (Entry)',
  protection: '保护安装 (Protection)',
  tp_runner: '止盈 / Runner (TP/Runner)',
  exit: '退出执行 (Exit)',
  reconciliation: '账本对账 (Reconciliation)',
  review: '事后复盘 (Review)',
};

export const EXIT_REASON_ZH: Record<string, string> = {
  'Initial Stop': '初始止损 (Initial Stop)',
  'TP1 + Runner Exit': '止盈平保 (TP1 + Runner Exit)',
  'Controlled Exit': '受控平仓 (Controlled Exit)',
  'External Flat / Exit Fills Unavailable': '外部平仓已确认',
  'stop_loss': '止损触发',
  'take_profit': '止盈触发',
  'tp1_hit': 'TP1 触发',
  'exit_reason_evidence_missing': '证据待补全',
  'exit_not_applicable': '不适用',
  'ticket_active': '持仓未退出',
};

export function formatMoneyMetric(
  metric: MoneyMetric | null | undefined,
  defaultActiveText: string = '—'
): { formatted: string; value: number | null; isPositive: boolean | null } {
  if (!metric || metric.value === null || metric.value === undefined) {
    if (metric?.unavailable_reason === 'ticket_active') {
      return { formatted: defaultActiveText, value: null, isPositive: null };
    }
    return { formatted: '—', value: null, isPositive: null };
  }

  const num = Number(metric.value);
  if (isNaN(num)) {
    return { formatted: `${metric.value} ${metric.unit}`, value: null, isPositive: null };
  }

  const sign = num > 0 ? '+' : '';
  const formattedNum = num.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  return {
    formatted: `${sign}${formattedNum} ${metric.unit}`.trim(),
    value: num,
    isPositive: num > 0 ? true : num < 0 ? false : null,
  };
}

export function mapTradeListItemToEpisode(
  item: TradeListItem,
  nowMs: number = Date.now()
): TradeEpisode {
  const meta = STRATEGY_META[item.strategy_group_id] ?? {
    name_zh: item.strategy_group_id,
    timeframe: '1h close',
  };

  const isActive = item.terminal_at_ms === null;
  const stageZh = STAGE_LABELS_ZH[item.lifecycle_stage] ?? item.lifecycle_stage;

  // Duration
  const durationMs = isActive
    ? Math.max(0, nowMs - item.issued_at_ms)
    : Math.max(0, (item.terminal_at_ms ?? nowMs) - item.issued_at_ms);
  const durationFormatted = formatDuration(durationMs);

  // Time format
  const issuedDate = new Date(item.issued_at_ms);
  const issuedFormatted = issuedDate.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });

  const closedFormatted = item.terminal_at_ms
    ? new Date(item.terminal_at_ms).toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      })
    : null;

  // Economics
  const activePlaceholder = isActive ? '持仓中 · 未结' : '—';
  const netPnlResult = formatMoneyMetric(item.net_pnl, activePlaceholder);
  const netRResult = formatMoneyMetric(item.net_r, activePlaceholder);
  const grossPnlResult = formatMoneyMetric(item.gross_pnl, activePlaceholder);
  const feesResult = formatMoneyMetric(item.fees, activePlaceholder);
  const fundingResult = formatMoneyMetric(item.funding, activePlaceholder);

  // Outcome
  let outcome: TradeEpisode['outcome'] = 'in_progress';
  let outcomeZh = '进行中';

  if (!isActive) {
    if (netRResult.value !== null) {
      if (netRResult.value > 0) {
        outcome = 'win';
        outcomeZh = '盈利 (Win)';
      } else if (netRResult.value < 0) {
        outcome = 'loss';
        outcomeZh = '亏损 (Loss)';
      } else {
        outcome = 'breakeven';
        outcomeZh = '平保 (BE)';
      }
    } else {
      outcome = 'closed';
      outcomeZh = '已平仓';
    }
  }

  // Protection state
  const isProtected = item.aggregate_status === 'position_protected';
  const protectionState = isProtected
    ? '已受保护 (Protected)'
    : item.aggregate_status || (isActive ? '保护未就绪' : '平仓终态');

  // Exit reason
  const rawExitReason = item.exit_reason;
  const exitReasonZh = rawExitReason
    ? (EXIT_REASON_ZH[rawExitReason] ?? rawExitReason)
    : item.exit_reason_unavailable_reason
    ? (EXIT_REASON_ZH[item.exit_reason_unavailable_reason] ?? '未就绪')
    : '—';

  return {
    ticket_id: item.ticket_id,
    strategy_id: item.strategy_group_id,
    strategy_name_zh: meta.name_zh,
    strategy_timeframe: meta.timeframe,
    event_spec_id: item.event_spec_id,
    symbol: cleanSymbol(item.exchange_instrument_id),
    side: item.position_side,
    isActive,
    ticket_status: item.ticket_status,
    aggregate_status: item.aggregate_status,
    lifecycle_stage: item.lifecycle_stage,
    lifecycle_stage_zh: stageZh,
    completed_stage_count: item.completed_stage_count,
    total_stage_count: item.total_stage_count,
    issued_at_ms: item.issued_at_ms,
    issued_at_formatted: issuedFormatted,
    terminal_at_ms: item.terminal_at_ms,
    closed_at_formatted: closedFormatted,
    duration_ms: durationMs,
    duration_formatted: durationFormatted,
    outcome,
    outcome_zh: outcomeZh,
    exit_reason: rawExitReason,
    exit_reason_zh: exitReasonZh,
    protection_state: protectionState,
    is_protected: isProtected,
    net_pnl_formatted: netPnlResult.formatted,
    net_pnl_val: netPnlResult.value,
    net_pnl_is_positive: netPnlResult.isPositive,
    net_r_formatted: netRResult.formatted,
    net_r_val: netRResult.value,
    net_r_is_positive: netRResult.isPositive,
    gross_pnl_formatted: grossPnlResult.formatted,
    fees_formatted: feesResult.formatted,
    funding_formatted: fundingResult.formatted,
    attention_items: [...(item.attention_items ?? [])],
    raw_item: item,
  };
}

export function computeTradesSummaryMetrics(episodes: TradeEpisode[]): TradesSummaryMetrics {
  const totalCount = episodes.length;
  const activeCount = episodes.filter((t) => t.isActive).length;
  const completedEpisodes = episodes.filter((t) => !t.isActive);
  const completedCount = completedEpisodes.length;

  let winCount = 0;
  let lossCount = 0;
  let breakevenCount = 0;
  let sumNetPnl = 0;
  let hasPnl = false;
  let sumNetR = 0;
  let hasR = false;

  completedEpisodes.forEach((t) => {
    if (t.outcome === 'win') winCount++;
    else if (t.outcome === 'loss') lossCount++;
    else if (t.outcome === 'breakeven') breakevenCount++;

    if (t.net_pnl_val !== null && t.net_pnl_val !== undefined) {
      sumNetPnl += t.net_pnl_val;
      hasPnl = true;
    }
    if (t.net_r_val !== null && t.net_r_val !== undefined) {
      sumNetR += t.net_r_val;
      hasR = true;
    }
  });

  const evaluatedTrades = winCount + lossCount;
  const winRatePercent =
    evaluatedTrades > 0 ? Math.round((winCount / evaluatedTrades) * 100) : null;

  const totalNetPnlFormatted = hasPnl
    ? `${sumNetPnl > 0 ? '+' : ''}${sumNetPnl.toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })} USDT`
    : '—';

  const totalNetRFormatted = hasR
    ? `${sumNetR > 0 ? '+' : ''}${sumNetR.toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })} R`
    : '—';

  return {
    totalCount,
    activeCount,
    completedCount,
    winCount,
    lossCount,
    breakevenCount,
    winRatePercent,
    totalNetPnlFormatted,
    totalNetRFormatted,
  };
}
