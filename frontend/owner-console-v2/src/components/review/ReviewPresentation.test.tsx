// @vitest-environment jsdom
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ReviewCenterItem, ReviewCenterSummary } from '../../types/review';
import { computeReviewSummary } from '../../mapping/reviewSummary';
import { formatReviewExitReason } from '../../mapping/reviewMapping';
import { ReviewMetricsDeck } from './ReviewMetricsDeck';
import { ReviewTable } from './ReviewTable';

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
  it('uses readable reasons, retaining audit context separately', () => {
    const raw = 'owner_flatten_all:owner-authorization:exact';
    expect(formatReviewExitReason(raw)).toEqual({ label: 'Owner 全部持仓受控平仓', raw });
    expect(formatReviewExitReason('pre_tp1_time_stop_hit').label).toBe('TP1 前持仓超时退出');
    expect(formatReviewExitReason('future_unknown').label).toBe('退出原因未识别');
    expect(formatReviewExitReason(null).label).toBe('退出原因未确认');
  });
});
