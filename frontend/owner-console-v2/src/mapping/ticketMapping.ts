/**
 * Ticket Mapping and Active Ticket Accounting Truth
 * 
 * Ensures that active tickets and unloaded tickets are strictly derived from
 * real authoritative facts without fabricating synthetic tickets.
 */

export interface TicketBadgeItem {
  type: 'ticket' | 'count_only' | 'empty';
  id?: string;
  count?: number;
  label?: string;
  symbol?: string;
  side?: 'long' | 'short';
  pnl_r?: string;
}

/**
 * Computes the number of authoritative active tickets that have not yet been loaded
 * in the paginated response.
 *
 * @param authoritativeCount Active count reported by authoritative state (e.g. Overview or AccountCapacity)
 * @param loadedCount Number of ticket objects loaded in the current page
 */
export function computeUnloadedActiveCount(
  authoritativeCount: number | null | undefined,
  loadedCount: number
): number {
  if (typeof authoritativeCount === 'number' && authoritativeCount > loadedCount) {
    return authoritativeCount - loadedCount;
  }
  return 0;
}

/**
 * Derives badges for strategy matrix positions without fabricating fake ticket IDs.
 */
export function formatTicketOccupationBadge(
  activeTickets: Array<{ ticket_id?: string; id?: string; symbol?: string; side?: 'long' | 'short'; pnl_r?: string }> | undefined,
  activeTicketCount: number | undefined
): TicketBadgeItem[] {
  if (activeTickets && activeTickets.length > 0) {
    return activeTickets.map((t) => ({
      type: 'ticket' as const,
      id: t.ticket_id ?? t.id,
      symbol: t.symbol,
      side: t.side,
      pnl_r: t.pnl_r,
    }));
  }
  if (typeof activeTicketCount === 'number' && activeTicketCount > 0) {
    return [
      {
        type: 'count_only' as const,
        count: activeTicketCount,
        label: `${activeTicketCount} 个占用`,
      },
    ];
  }
  return [{ type: 'empty' as const, count: 0, label: '0 个占用' }];
}

import { protectionFact } from './tradeTruth.ts';
import { cleanSymbol } from '../utils/symbol.ts';
import { formatReviewMoneyMetric } from './reviewMapping.ts';
import type { TradeListItem, MoneyMetric } from '../types/trades.ts';
import type { TradeEpisodeSummary } from '../types/overview.ts';

const STAGE_LABELS: Record<string, string> = {
  signal: '信号',
  admission: '准入',
  entry: '入场',
  protection: '保护安装',
  manual: '人工管理',
  tp_runner: '止盈 / Runner',
  exit: '退出',
  reconciliation: '对账',
  review: '复盘',
};

function formatMetric(metric?: { value: string | null; unit: string; unavailable_reason?: string | null } | null): string {
  if (!metric || metric.value == null) return '--';
  return formatReviewMoneyMetric(metric as MoneyMetric, { sign: true }).formatted;
}

export function mapActiveTicketToOverviewEpisode(
  t: TradeListItem,
  strategyNameZh?: string
): TradeEpisodeSummary {
  const stageZh = STAGE_LABELS[t.lifecycle_stage] ?? t.lifecycle_stage;
  const protection =
    t.management_mode === 'MANUAL'
      ? { confirmed: false, label: t.manual_risk_reason ? '人工管理 · 保护待核实' : '人工管理 · 以当前订单为准' }
      : t.management_mode === 'REVIEW_REQUIRED'
      ? { confirmed: false, label: '接管待核实 · 自动处置暂停' }
      : protectionFact(t.aggregate_status);

  return {
    ticket_id: t.ticket_id,
    strategy_id: t.strategy_group_id,
    strategy_name_zh: strategyNameZh ?? t.strategy_group_id,
    symbol: cleanSymbol(t.exchange_instrument_id),
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
    management_mode: t.management_mode,
    is_protected: protection.confirmed,
    protection_state: protection.label,
    manual_risk_reason: t.manual_risk_reason,
  };
}
