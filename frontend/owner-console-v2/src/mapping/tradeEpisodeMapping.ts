import { MoneyDecimal, protectionFact, terminalFact } from './tradeTruth.ts';
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
): { formatted: string; value: string | null; isPositive: boolean | null } {
  if (!metric || metric.value === null || metric.value === undefined || metric.unavailable_reason) {
    if (metric?.unavailable_reason === 'ticket_active') {
      return { formatted: defaultActiveText, value: null, isPositive: null };
    }
    return { formatted: '—', value: null, isPositive: null };
  }

  let num;
  try { num = new MoneyDecimal(metric.value); } catch { return {formatted: '—', value:null,isPositive:null}; }
  if (!num.isFinite()) {
    return { formatted: '—', value: null, isPositive: null };
  }

  const sign = num.isPositive() && !num.isZero() ? '+' : '';
  return {formatted:`${sign}${num.toFixed(2)} ${metric.unit}`.trim(), value:num.toString(),isPositive:num.isZero()?null:num.isPositive()};
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
  const eligible = !isActive && terminalFact(item) !== '未成交终止';
  const netPnlResult = formatMoneyMetric(eligible ? item.net_pnl : null, activePlaceholder);
  const netRResult = formatMoneyMetric(eligible ? item.net_r : null, activePlaceholder);
  const grossPnlResult = formatMoneyMetric(item.gross_pnl, activePlaceholder);
  const feesResult = formatMoneyMetric(item.fees, activePlaceholder);
  const fundingResult = formatMoneyMetric(item.funding, activePlaceholder);

  // Outcome
  let outcome: TradeEpisode['outcome'] = 'in_progress';
  let outcomeZh = '进行中';

  if (!isActive) {
    if (terminalFact(item) === '已结算' && netRResult.value !== null && netPnlResult.value !== null) {
      if (new MoneyDecimal(netRResult.value).gt(0)) {
        outcome = 'win';
        outcomeZh = terminalFact(item) + ' · 盈利 (Win)';
      } else if (new MoneyDecimal(netRResult.value).lt(0)) {
        outcome = 'loss';
        outcomeZh = terminalFact(item) + ' · 亏损 (Loss)';
      } else {
        outcome = 'breakeven';
        outcomeZh = terminalFact(item) + ' · 平保 (BE)';
      }
    } else {
      outcome = 'closed';
      outcomeZh = terminalFact(item);
    }
  }

  // Protection state
  const protection = protectionFact(item.aggregate_status);
  const isProtected = protection.confirmed;
  const protectionState = protection.label;

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
    net_pnl_formatted: isActive ? '在管中 · 未结' : netPnlResult.formatted,
    net_pnl_val: netPnlResult.value,
    net_pnl_is_positive: netPnlResult.isPositive,
    net_r_formatted: isActive ? '在管中 · 未结' : netRResult.formatted,
    net_r_val: netRResult.value,
    net_r_is_positive: netRResult.isPositive,
    gross_pnl_formatted: grossPnlResult.formatted,
    fees_formatted: feesResult.formatted,
    funding_formatted: fundingResult.formatted,
    attention_items: [...(item.attention_items ?? [])],
    raw_item: item,
  };
}

export function computeTradesSummaryMetrics(
  episodes: TradeEpisode[],
  pagination?: { hasMore?: boolean }
): TradesSummaryMetrics {
  const totalCount = episodes.length;
  const activeCount = episodes.filter((t) => t.isActive).length;
  const completedEpisodes = episodes.filter((t) => !t.isActive);
  const completedCount = completedEpisodes.length;

  let winCount = 0;
  let lossCount = 0;
  let breakevenCount = 0;
  let sumNetPnl = new MoneyDecimal(0);
  let pnlEvaluatedCount = 0;
  let sumNetR = new MoneyDecimal(0);
  let rEvaluatedCount = 0;

  completedEpisodes.forEach((t) => {
    if (t.outcome === 'win') winCount++;
    else if (t.outcome === 'loss') lossCount++;
    else if (t.outcome === 'breakeven') breakevenCount++;

    if (t.net_pnl_val !== null && t.net_pnl_val !== undefined) {
      sumNetPnl = sumNetPnl.plus(t.net_pnl_val);
      pnlEvaluatedCount++;
    }
    if (t.net_r_val !== null && t.net_r_val !== undefined) {
      sumNetR = sumNetR.plus(t.net_r_val);
      rEvaluatedCount++;
    }
  });

  const evaluatedTradesCount = winCount + lossCount;
  const excludedFromWinRateCount = completedCount - evaluatedTradesCount;
  const winRatePercent =
    evaluatedTradesCount > 0 ? Math.round((winCount / evaluatedTradesCount) * 100) : null;

  const winRateDenominatorText =
    completedCount === 0
      ? '暂无已结束交易'
      : evaluatedTradesCount > 0
      ? excludedFromWinRateCount > 0
        ? `基准: ${winCount} 胜 / ${lossCount} 负 (排除 ${excludedFromWinRateCount} 笔平保/未评)`
        : `基准: ${winCount} 胜 / ${lossCount} 负 (全量评估)`
      : `未产生胜负评定 (${completedCount} 笔平保或未评)`;

  const hasPnlGaps = completedCount > 0 && pnlEvaluatedCount < completedCount;
  const totalNetPnlFormatted = pnlEvaluatedCount > 0
    ? `${sumNetPnl.gt(0) ? '+' : ''}${sumNetPnl.toFixed(2)} USDT`
    : '—';

  const pnlCoverageText =
    completedCount === 0
      ? '暂无历史记录'
      : hasPnlGaps
      ? `已记录合计 · 覆盖 ${pnlEvaluatedCount}/${completedCount} 笔 (存在缺口)`
      : `已加载经济数据齐全 · 覆盖 ${completedCount} 笔`;

  const hasRGaps = completedCount > 0 && rEvaluatedCount < completedCount;
  const totalNetRFormatted = rEvaluatedCount > 0
    ? `${sumNetR.gt(0) ? '+' : ''}${sumNetR.toFixed(2)} R`
    : '—';

  const rCoverageText =
    completedCount === 0
      ? '暂无历史记录'
      : hasRGaps
      ? `已记录合计 · 覆盖 ${rEvaluatedCount}/${completedCount} 笔 (存在缺口)`
      : `单位风险倍数 (R) · 覆盖 ${completedCount} 笔`;

  const hasMore = Boolean(pagination?.hasMore);
  const isComplete = !hasMore;
  const scopeLabel =
    totalCount === 0
      ? '暂无数据'
      : hasMore
      ? '已加载范围统计 (尚有未加载数据)'
      : `已加载当前 30 天范围全部账本 · 共 ${totalCount} 笔`;

  return {
    totalCount,
    activeCount,
    completedCount,
    winCount,
    lossCount,
    breakevenCount,
    evaluatedTradesCount,
    excludedFromWinRateCount,
    winRatePercent,
    winRateDenominatorText,
    totalNetPnlFormatted,
    pnlEvaluatedCount,
    hasPnlGaps,
    pnlCoverageText,
    totalNetRFormatted,
    rEvaluatedCount,
    hasRGaps,
    rCoverageText,
    isComplete,
    hasMore,
    scopeLabel,
  };
}
