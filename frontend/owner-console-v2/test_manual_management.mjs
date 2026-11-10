import assert from 'node:assert/strict';
import { mapTradeListItemToEpisode } from './src/mapping/tradeEpisodeMapping.ts';
import { mapActiveTicketToOverviewEpisode } from './src/mapping/ticketMapping.ts';

const base = {
  ticket_id: 'manual',
  ticket_status: 'issued',
  terminal_at_ms: null,
  issued_at_ms: 1000,
  strategy_group_id: 'CPM-RO-001',
  event_spec_id: 'event',
  exchange_instrument_id: 'binance-usdm:BTCUSDT:perpetual',
  position_side: 'long',
  aggregate_status: 'position_protected',
  lifecycle_stage: 'protection',
  completed_stage_count: 3,
  total_stage_count: 8,
  net_pnl: { value: null, unit: 'USDT' },
  net_r: { value: null, unit: 'R' },
  gross_pnl: { value: null, unit: 'USDT' },
  fees: { value: null, unit: 'USDT' },
  funding: { value: null, unit: 'USDT' },
  attention_items: [],
};

// 1. Trades Page Mapping Tests
const manual = mapTradeListItemToEpisode({
  ...base,
  management_mode: 'MANUAL',
  manual_risk_reason: 'manual_stop_coverage_incomplete',
});
assert.equal(manual.is_protected, false);
assert.match(manual.protection_state, /人工管理.*待核实/);

const review = mapTradeListItemToEpisode({ ...base, management_mode: 'REVIEW_REQUIRED' });
assert.equal(review.is_protected, false);
assert.match(review.protection_state, /接管待核实/);

const automatic = mapTradeListItemToEpisode({ ...base, management_mode: 'AUTO' });
assert.equal(automatic.is_protected, true);

// 2. Overview Page Active Ticket Mapping Tests
const overviewManualWithReason = mapActiveTicketToOverviewEpisode(
  {
    ...base,
    management_mode: 'MANUAL',
    manual_risk_reason: 'manual_stop_coverage_incomplete',
  },
  '均线回踩做多'
);
assert.equal(overviewManualWithReason.management_mode, 'MANUAL');
assert.equal(overviewManualWithReason.is_protected, false);
assert.equal(overviewManualWithReason.protection_state, '人工管理 · 保护待核实');
assert.equal(overviewManualWithReason.manual_risk_reason, 'manual_stop_coverage_incomplete');

const overviewManualClean = mapActiveTicketToOverviewEpisode(
  {
    ...base,
    management_mode: 'MANUAL',
    manual_risk_reason: null,
  },
  '均线回踩做多'
);
assert.equal(overviewManualClean.management_mode, 'MANUAL');
assert.equal(overviewManualClean.is_protected, false);
assert.equal(overviewManualClean.protection_state, '人工管理 · 以当前订单为准');

const overviewReview = mapActiveTicketToOverviewEpisode(
  {
    ...base,
    management_mode: 'REVIEW_REQUIRED',
  },
  '相对强弱冲量'
);
assert.equal(overviewReview.management_mode, 'REVIEW_REQUIRED');
assert.equal(overviewReview.is_protected, false);
assert.equal(overviewReview.protection_state, '接管待核实 · 自动处置暂停');

const overviewAutoProtected = mapActiveTicketToOverviewEpisode(
  {
    ...base,
    management_mode: 'AUTO',
    aggregate_status: 'position_protected',
  },
  '假反弹衰竭做空'
);
assert.equal(overviewAutoProtected.management_mode, 'AUTO');
assert.equal(overviewAutoProtected.is_protected, true);
assert.equal(overviewAutoProtected.protection_state, '后端已确认保护');

const overviewAutoPending = mapActiveTicketToOverviewEpisode(
  {
    ...base,
    management_mode: 'AUTO',
    aggregate_status: 'protection_pending',
  },
  '假反弹衰竭做空'
);
assert.equal(overviewAutoPending.management_mode, 'AUTO');
assert.equal(overviewAutoPending.is_protected, false);
assert.equal(overviewAutoPending.protection_state, '保护安装或切换进行中');

console.log('Manual/review ownership and overview active ticket protection truth assertions: ALL PASS');
