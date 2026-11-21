// @vitest-environment jsdom
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ReviewCenterItem, ReviewCenterSummary } from '../../types/review';
import { computeReviewSummary } from '../../mapping/reviewSummary';
import { formatPnlWithGrossFallback, formatReviewExitReason, formatReviewFreshness } from '../../mapping/reviewMapping';
import { mapTradeListItemToEpisode, computeTradesSummaryMetrics } from '../../mapping/tradeEpisodeMapping';
import type { TradeListItem } from '../../types/trades';
import { ReviewMetricsDeck } from './ReviewMetricsDeck';
import { ReviewTable } from './ReviewTable';
import { ReviewFilterBar } from './ReviewFilterBar';
import { ReviewBreakdownSections } from './ReviewBreakdownSections';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const money = (value: string | null, unit: 'R' | 'USDT' = 'USDT') => ({ value, unit, unavailable_reason: value === null ? 'funding_unavailable' : null });
function item(id: string, missing = false): ReviewCenterItem {
  return {
    ticket_id: id, strategy_group_id: 'BRF2-001', exchange_instrument_id: 'binance-usdm:BTCUSDT:perpetual', position_side: 'long', terminal_at_ms: 1700000000000,
    review: {
      ticket_id: id, execution_classification: 'complete', review_status: missing ? 'incomplete_evidence' : 'complete',
      exit_reason: 'pre_tp1_time_stop_hit', exit_attribution: { code: 'pre_tp1_time_stop_hit', label: 'TP1 前持仓超时退出', source: 'exit_event', evidence: [] },
      economic_summary: { gross_pnl: money('10'), fees: money('1'), funding: money(missing ? null : '0.1'), net_pnl: money(missing ? null : '9.1'), net_r: money(missing ? null : '1', 'R') },
      execution_gaps: [], economic_gaps: missing ? [{ code: 'funding_unavailable', label: '资金费无法精确归因', impact: '净收益未知' }] : [],
      attention_items: [], sentences: [], final_conclusion: null, evidence: [{ kind: 'ticket', identity: id, occurred_at_ms: 1700000000000 }],
    },
  };
}
const container = document.createElement('div');
document.body.appendChild(container);
let root: ReturnType<typeof createRoot> | undefined;
afterEach(() => { act(() => root?.unmount()); root = undefined; container.innerHTML = ''; });
function render(element: React.ReactNode) { root = createRoot(container); act(() => root!.render(element)); }
const base = { from_ms: 1699900000000, to_ms: 1700100000000, next_cursor: null, strategy_group_samples: [] } as unknown as ReviewCenterSummary;
describe('Review explanations and metric coverage', () => {
  it('shows partial coverage and links each missing Ticket without hiding complete fees', () => {
    const summary = computeReviewSummary([item('ticket:1'), item('ticket:2', true)], base, 'next');
    expect(summary.net_pnl.value).toBeNull();
    expect(summary.verified_totals?.net_pnl.value).toBe('9.1');
    expect(summary.fees.value).toBe('2');
    const select = vi.fn();
    render(<ReviewMetricsDeck summary={summary} totalAttentionCount={0} onSelectTicket={select} />);
    expect(container.querySelector('[data-testid="coverage-net_pnl"]')?.textContent).toContain('部分合计 · 覆盖 1/2');
    expect(container.querySelector('[data-testid="coverage-fees"]')?.textContent).toContain('已核实合计 · 覆盖 2/2');
    act(() => container.querySelector<HTMLButtonElement>('[data-testid="coverage-net_pnl"] button')!.click());
    expect(select).toHaveBeenCalledWith('ticket:2');
    expect(container.textContent).toContain('尚有后续分页');
  });
  it('keeps execution and financial gaps distinct in the actual expanded table', () => {
    render(<ReviewTable items={[item('ticket:2', true)]} onSelectTicket={vi.fn()} />);
    expect(container.textContent).toContain('执行证据');
    expect(container.textContent).toContain('链路已核实');
    expect(container.textContent).toContain('有核算缺项');
    expect(container.textContent).not.toContain('执行质量');
    act(() => container.querySelector<HTMLButtonElement>('button[aria-expanded]')!.click());
    expect(container.textContent).toContain('资金费无法精确归因');
    expect(container.textContent).toContain('退出归因与审计详情');
  });
  it('preserves zero, exact cancellation, empty and all-missing coverage honestly', () => {
    const zero = item('zero'); zero.review.economic_summary.net_pnl = money('0');
    const summary = computeReviewSummary([zero, item('missing', true)], base);
    expect(summary.verified_totals?.net_pnl.value).toBe('0');
    expect(summary.metric_coverage?.net_pnl.available_count).toBe(1);
    expect(computeReviewSummary([], base).verified_totals?.net_pnl.value).toBeNull();
    expect(computeReviewSummary([item('missing', true)], base).verified_totals?.net_pnl.value).toBeNull();
  });
  it('shows known gross PnL when funding is missing without calculating net PnL', () => {
    const display = formatPnlWithGrossFallback(money(null), money('6.45'));
    expect(display.formatted).toBe('+6.45 USDT（资费不完整）');
    expect(display.isGrossFallback).toBe(true);
    expect(formatPnlWithGrossFallback({ ...money(null), unavailable_reason: 'incomplete_review_economics' }, money('6.45')).isGrossFallback).toBe(false);
    const trade: TradeListItem = {
      ticket_id: 'ticket:gross', strategy_group_id: 'BRF2-001', event_spec_id: 'spec:1', exchange_instrument_id: 'binance-usdm:BTCUSDT:perpetual', position_side: 'long',
      ticket_status: 'terminal', aggregate_status: 'terminal', lifecycle_stage: 'review', issued_at_ms: 1699999999000, terminal_at_ms: 1700000000000,
      review_id: 'review:gross', review_revision: 1, economics_completeness: 'funding_unavailable', completed_stage_count: 8, total_stage_count: 8,
      exit_reason: 'pre_tp1_time_stop_hit', exit_reason_unavailable_reason: null,
      gross_pnl: money('6.45'), fees: money('0.2'), funding: money(null), net_pnl: money(null), net_r: money(null, 'R'), attention_items: [], evidence: [],
    };
    const episode = mapTradeListItemToEpisode(trade);
    expect(episode.net_pnl_formatted).toBe('+6.45 USDT（资费不完整）');
    expect(episode.net_pnl_val).toBeNull();
    expect(episode.outcome).toBe('closed');
    expect(computeTradesSummaryMetrics([episode]).totalNetPnlFormatted).toBe('—');
    const row = item('ticket:gross', true);
    row.review.economic_summary.gross_pnl = money('6.45');
    render(<ReviewTable items={[row]} onSelectTicket={vi.fn()} />);
    expect(container.textContent).toContain('+6.45 USDT（资费不完整）');
    expect(container.textContent).toContain('毛收益');
    expect(computeReviewSummary([row], base).net_pnl.value).toBeNull();
    expect(formatPnlWithGrossFallback(money(null), money(null)).isGrossFallback).toBe(false);
    expect(formatPnlWithGrossFallback(money('0'), money('6.45')).formatted).toBe('0.00 USDT');
  });
  it('uses readable reasons, retaining audit context separately', () => {
    const raw = 'owner_flatten_all:owner-authorization:exact';
    expect(formatReviewExitReason(raw)).toEqual({ label: 'Owner 全部持仓受控平仓', raw });
    expect(formatReviewExitReason('pre_tp1_time_stop_hit').label).toBe('TP1 前持仓超时退出');
    expect(formatReviewExitReason('future_unknown').label).toBe('退出原因未识别');
    expect(formatReviewExitReason(null).label).toBe('退出原因未确认');
  });

  it('keeps execution evidence, economics status, and overall review status independent', () => {
    const execIncompleteEconComplete = item('ticket:exec-gap', false);
    execIncompleteEconComplete.review.execution_classification = 'evidence_incomplete';
    execIncompleteEconComplete.review.review_status = 'incomplete_evidence';
    execIncompleteEconComplete.review.execution_gaps = [{ code: 'stop_trace_missing', label: '止损轨迹待核实', impact: '执行链未完全闭合' }];

    const waitingItem = item('ticket:waiting', false);
    waitingItem.review.execution_classification = 'waiting_review';
    waitingItem.review.review_status = 'waiting_review';

    render(<ReviewTable items={[execIncompleteEconComplete, waitingItem]} onSelectTicket={vi.fn()} />);
    const tableText = container.querySelector('[data-testid="review-table"]')?.textContent ?? '';
    expect(tableText).toContain('存在待核实项');
    expect(tableText).toContain('核算完整');
    expect(tableText).toContain('等待复盘');
    expect(container.querySelector('[data-testid="review-mobile-list"]')?.textContent).toContain('复盘: 存在待核实项');
  });

  it('shows all active URL filters in ReviewFilterBar and resets them completely', () => {
    const onReset = vi.fn();
    render(
      <ReviewFilterBar
        filters={{
          range: '30d',
          from_ms: 1699900000000,
          to_ms: 1700100000000,
          strategy_version_id: 'v2.1',
          exchange_instrument_id: 'binance-usdm:ETHUSDT:perpetual',
          position_side: 'short',
          exit_scope: 'owner',
          view: 'current',
        }}
        onChange={vi.fn()}
        onReset={onReset}
      />
    );
    expect(container.textContent).toContain('版本: v2.1');
    expect(container.textContent).toContain('标的: ETHUSDT');
    expect(container.textContent).toContain('方向: 空头');
    expect(container.textContent).toContain('退出范围: Owner 平仓');
    expect(container.textContent).toContain('仅当前版本');
    const resetBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('清除筛选'));
    expect(resetBtn).toBeTruthy();
    act(() => resetBtn!.click());
    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it('renders ReviewBreakdownSections with Chinese sample count and applicability details', () => {
    render(
      <ReviewBreakdownSections
        summary={{
          ...base,
          strategy_group_samples: [
            {
              strategy_group_id: 'MPG-001',
              sample_count: 3,
              evidence_state: 'observe_only',
              evidence: [{ kind: 'ticket', identity: 'ticket:1', occurred_at_ms: 1700000000000 }],
            },
          ],
          execution_quality_breakdown: [],
          exit_reason_breakdown: [],
        }}
        onSelectTicket={vi.fn()}
      />
    );
    expect(container.textContent).toContain('策略组样本分布');
    expect(container.textContent).toContain('已加载 3 笔复盘样本');
    expect(container.textContent).toContain('仅供观察');
  });

  it('distinguishes all four freshness states without collapsing non-fresh states', () => {
    expect(formatReviewFreshness('fresh')).toEqual({ label: '快照新鲜', tone: 'success' });
    expect(formatReviewFreshness('stale')).toEqual({ label: '数据滞后', tone: 'attention' });
    expect(formatReviewFreshness('unavailable')).toEqual({ label: '新鲜度不可确认', tone: 'neutral' });
    expect(formatReviewFreshness('contradictory')).toEqual({ label: '数据矛盾', tone: 'danger' });
  });
});
