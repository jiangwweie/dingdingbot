import type { components } from '../api/schema';

export type TradeListItem = components['schemas']['TradeListItem'];
export type TradeCausalityDetail = components['schemas']['TradeCausalityDetail'];
export type LifecycleStageView = components['schemas']['LifecycleStageView'];
export type MoneyMetric = components['schemas']['MoneyMetric'];
export type Freshness = components['schemas']['Freshness'];

export type TradeFilterMode = 'all' | 'active' | 'completed';

export type TradeOutcome = 'win' | 'loss' | 'breakeven' | 'in_progress' | 'closed';

export interface TradeEpisode {
  ticket_id: string;
  strategy_id: string;
  strategy_name_zh: string;
  strategy_timeframe: string;
  event_spec_id: string;
  symbol: string;
  side: 'long' | 'short';
  isActive: boolean;
  ticket_status: string;
  aggregate_status: string;
  lifecycle_stage: string;
  lifecycle_stage_zh: string;
  completed_stage_count: number;
  total_stage_count: number;
  issued_at_ms: number;
  issued_at_formatted: string;
  terminal_at_ms: number | null;
  closed_at_formatted: string | null;
  duration_ms: number;
  duration_formatted: string;
  outcome: TradeOutcome;
  outcome_zh: string;
  exit_reason: string | null;
  exit_reason_zh: string;
  protection_state: string;
  is_protected: boolean;
  net_pnl_formatted: string;
  net_pnl_val: string | null;
  net_pnl_is_positive: boolean | null;
  net_r_formatted: string;
  net_r_val: string | null;
  net_r_is_positive: boolean | null;
  gross_pnl_formatted: string;
  fees_formatted: string;
  funding_formatted: string;
  attention_items: string[];
  raw_item: TradeListItem;
}

export interface TradesSummaryMetrics {
  totalCount: number;
  activeCount: number;
  completedCount: number;
  winCount: number;
  lossCount: number;
  breakevenCount: number;
  evaluatedTradesCount: number;
  excludedFromWinRateCount: number;
  winRatePercent: number | null;
  winRateDenominatorText: string;
  totalNetPnlFormatted: string;
  pnlEvaluatedCount: number;
  hasPnlGaps: boolean;
  pnlCoverageText: string;
  totalNetRFormatted: string;
  rEvaluatedCount: number;
  hasRGaps: boolean;
  rCoverageText: string;
  isComplete: boolean;
  hasMore: boolean;
  scopeLabel: string;
}
