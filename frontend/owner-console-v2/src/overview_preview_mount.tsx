import React, { useState, useEffect } from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider, useTheme } from './context/ThemeContext';
import { Navbar, type NavTabId } from './components/Navbar';
import { OverviewPage } from './components/overview/OverviewPage';
import { TradesPage } from './components/trades/TradesPage';
import { StrategiesPage } from './components/strategies/StrategiesPage';
import { ReviewPage } from './components/review/ReviewPage';
import { ControlsPage } from './components/ControlsPage';
import { apiClient } from './api/client';
import './index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false, staleTime: 0 },
  },
});

type ScenarioKey = 'normal' | 'manual' | 'empty';

let currentScenario: ScenarioKey = 'normal';

const getInitialScenario = (): ScenarioKey => {
  if (typeof window !== 'undefined') {
    const s = new URLSearchParams(window.location.search).get('scenario');
    if (s === 'normal' || s === 'manual' || s === 'empty') return s;
  }
  return 'normal';
};

const getInitialTheme = (): 'dark' | 'light' => {
  if (typeof window !== 'undefined') {
    const t = new URLSearchParams(window.location.search).get('theme');
    if (t === 'light' || t === 'dark') return t;
  }
  return 'dark';
};

const shouldHideControls = (): boolean => {
  if (typeof window !== 'undefined') {
    return new URLSearchParams(window.location.search).get('hide_controls') === 'true';
  }
  return false;
};

const getInitialTab = (): NavTabId => {
  if (typeof window !== 'undefined') {
    const t = new URLSearchParams(window.location.search).get('tab');
    if (t === 'trades' || t === 'strategies' || t === 'review' || t === 'controls' || t === 'overview') return t;
  }
  return 'overview';
};

// Global verification interface
declare global {
  interface Window {
    __recordedUnexpectedRequests?: Array<{ method: string; pathname: string; url: string; time: number }>;
    __getOverviewVerification?: () => {
      href: string;
      isLoaded: boolean;
      scenario: ScenarioKey;
      innerWidth: number;
      innerHeight: number;
      scrollWidth: number;
      scrollHeight: number;
      hasCriticalElements: boolean;
      overflowElements: Array<{ tag: string; id: string; className: string; right: number; width: number }>;
      unexpectedRequests: Array<{ method: string; pathname: string; url: string; time: number }>;
    };
  }
}

if (typeof window !== 'undefined') {
  window.__recordedUnexpectedRequests = [];
}

currentScenario = getInitialScenario();

// ==========================================
// SCENARIO MOCKS
// ==========================================

function getMockOverview(scenario: ScenarioKey) {
  const nowMs = Date.now();
  if (scenario === 'normal') {
    return {
      code: 0,
      message: 'ok',
      data: {
        account_snapshot: {
          wallet_balance: '2450.00',
          available_balance: '1800.00',
          margin_mode: 'cross',
          updated_at_ms: nowMs - 60000,
        },
        active_ticket_count: 2,
        active_ticket_ids: [
          'ticket:76be9c73106d6a80ac8150a555f8f902',
          'ticket:98cf1a22106d6a80ac8150a555f8f111',
        ],
        admitted_signal_count: 6,
        rejected_signal_count: 2,
        today_signal_count: 8,
        execution_incident_count: 0,
        ticket_capacity: 1,
        observed_at_ms: nowMs,
        conclusion: {
          level: 'no_action' as const,
          summary: null,
        },
        attention_summary: [],
        evidence: [],
        notification_delivery: {
          channel_state: 'configured',
          pending_count: 0,
          pending_count_capped: false,
          failed_count: 0,
          failed_count_capped: false,
          last_accepted_at_ms: nowMs - 1800000,
        },
        today_net_pnl: {
          value: '342.50',
          unit: 'USDT',
          unavailable_reason: null,
        },
        today_net_r: {
          value: '2.85',
          unit: 'R',
          unavailable_reason: null,
        },
        performance: {
          from_ms: nowMs - 36000000,
          confirmed_count: 8,
          sample_count: 8,
          win_count: 6,
          loss_count: 2,
          breakeven_count: 0,
          unreviewed_count: 0,
          verified_totals: {
            net_pnl: { value: '342.50', unit: 'USDT' },
            net_r: { value: '2.85', unit: 'R' },
            gross_pnl: { value: '360.00', unit: 'USDT' },
            fees: { value: '-17.50', unit: 'USDT' },
            funding: { value: '0.00', unit: 'USDT' },
          },
          by_strategy_group: {
            'BRF2-001': {
              sample_count: 4,
              win_count: 3,
              loss_count: 1,
              confirmed_count: 4,
              breakeven_count: 0,
              unreviewed_count: 0,
              verified_totals: {
                net_pnl: { value: '210.00', unit: 'USDT' },
                net_r: { value: '1.80', unit: 'R' },
                gross_pnl: { value: '220.00', unit: 'USDT' },
                fees: { value: '-10.00', unit: 'USDT' },
                funding: { value: '0.00', unit: 'USDT' },
              },
              metric_coverage: {},
            },
            'CPM-RO-001': {
              sample_count: 4,
              win_count: 3,
              loss_count: 1,
              confirmed_count: 4,
              breakeven_count: 0,
              unreviewed_count: 0,
              verified_totals: {
                net_pnl: { value: '132.50', unit: 'USDT' },
                net_r: { value: '1.05', unit: 'R' },
                gross_pnl: { value: '140.00', unit: 'USDT' },
                fees: { value: '-7.50', unit: 'USDT' },
                funding: { value: '0.00', unit: 'USDT' },
              },
              metric_coverage: {},
            },
          },
          metric_coverage: {},
        },
      },
      freshness: 'fresh' as const,
      generated_at: new Date(nowMs).toISOString(),
      snapshot_id: 'snap-mock-normal',
    };
  }

  if (scenario === 'manual') {
    return {
      code: 0,
      message: 'ok',
      data: {
        account_snapshot: {
          wallet_balance: '2450.00',
          available_balance: '1920.00',
          margin_mode: 'cross',
          updated_at_ms: nowMs - 60000,
        },
        active_ticket_count: 1,
        active_ticket_ids: ['ticket:4a8c90fe106d6a80ac8150a555f8feee'],
        admitted_signal_count: 4,
        rejected_signal_count: 1,
        today_signal_count: 5,
        execution_incident_count: 0,
        ticket_capacity: 2,
        observed_at_ms: nowMs,
        conclusion: {
          level: 'attention' as const,
          summary: '检测到 1 笔仓位触发外部干预，整笔已永久移交人工管理',
        },
        attention_summary: [
          '检测到 1 笔仓位触发外部干预，整笔已永久移交人工管理',
          '全局 ENTRY 正常，存量仓位处于人工管理模式',
        ],
        evidence: [],
        notification_delivery: {
          channel_state: 'configured',
          pending_count: 0,
          pending_count_capped: false,
          failed_count: 0,
          failed_count_capped: false,
          last_accepted_at_ms: nowMs - 900000,
        },
        today_net_pnl: {
          value: '85.20',
          unit: 'USDT',
          unavailable_reason: null,
        },
        today_net_r: {
          value: '0.92',
          unit: 'R',
          unavailable_reason: null,
        },
        performance: {
          from_ms: nowMs - 36000000,
          confirmed_count: 4,
          sample_count: 4,
          win_count: 3,
          loss_count: 1,
          breakeven_count: 0,
          unreviewed_count: 0,
          verified_totals: {
            net_pnl: { value: '85.20', unit: 'USDT' },
            net_r: { value: '0.92', unit: 'R' },
            gross_pnl: { value: '93.20', unit: 'USDT' },
            fees: { value: '-8.00', unit: 'USDT' },
            funding: { value: '0.00', unit: 'USDT' },
          },
          by_strategy_group: {
            'CPM-RO-001': {
              sample_count: 4,
              win_count: 3,
              loss_count: 1,
              confirmed_count: 4,
              breakeven_count: 0,
              unreviewed_count: 0,
              verified_totals: {
                net_pnl: { value: '85.20', unit: 'USDT' },
                net_r: { value: '0.92', unit: 'R' },
                gross_pnl: { value: '93.20', unit: 'USDT' },
                fees: { value: '-8.00', unit: 'USDT' },
                funding: { value: '0.00', unit: 'USDT' },
              },
              metric_coverage: {},
            },
          },
          metric_coverage: {},
        },
      },
      freshness: 'fresh' as const,
      generated_at: new Date(nowMs).toISOString(),
      snapshot_id: 'snap-mock-manual',
    };
  }

  // scenario === 'empty'
  return {
    code: 0,
    message: 'ok',
    data: {
      account_snapshot: {
        wallet_balance: '2100.00',
        available_balance: '2100.00',
        margin_mode: 'cross',
        updated_at_ms: nowMs - 1200000,
      },
      active_ticket_count: 0,
      active_ticket_ids: [],
      admitted_signal_count: 0,
      rejected_signal_count: 2,
      today_signal_count: 2,
      execution_incident_count: 1,
      ticket_capacity: 3,
      observed_at_ms: nowMs - 1800000,
      conclusion: {
        level: 'attention' as const,
        summary: '数据生成时间已滞后，请核实后台监控 Worker 状态',
      },
      attention_summary: [
        '数据生成时间已滞后，请核实后台监控 Worker 状态',
        '全局 ENTRY 入场处于暂停状态',
      ],
      evidence: [],
      notification_delivery: {
        channel_state: 'configured',
        pending_count: 1,
        pending_count_capped: false,
        failed_count: 0,
        failed_count_capped: false,
        last_accepted_at_ms: nowMs - 7200000,
      },
      today_net_pnl: {
        value: null,
        unit: 'USDT',
        unavailable_reason: '今日暂无已完结交易结算事实',
      },
      today_net_r: {
        value: null,
        unit: 'R',
        unavailable_reason: '今日暂无已完结交易结算事实',
      },
      performance: {
        from_ms: nowMs - 36000000,
        confirmed_count: 0,
        sample_count: 0,
        win_count: 0,
        loss_count: 0,
        breakeven_count: 0,
        unreviewed_count: 0,
        verified_totals: {
          net_pnl: { value: null, unit: 'USDT' },
          net_r: { value: null, unit: 'R' },
          gross_pnl: { value: null, unit: 'USDT' },
          fees: { value: null, unit: 'USDT' },
          funding: { value: null, unit: 'USDT' },
        },
        by_strategy_group: {},
        metric_coverage: {},
      },
    },
    freshness: 'stale' as const,
    generated_at: new Date(nowMs - 1800000).toISOString(),
    snapshot_id: 'snap-mock-empty',
  };
}

function getMockControls(scenario: ScenarioKey) {
  const nowMs = Date.now();
  const isPaused = scenario === 'empty';

  return {
    account_capacity: {
      max_concurrent_tickets: 3,
      active_ticket_count: scenario === 'normal' ? 2 : scenario === 'manual' ? 1 : 0,
      strategy_side_active_counts: {},
    },
    current_operation: null,
    dynamic_selection: null,
    events: [],
    generated_at_ms: nowMs,
    global_entry: {
      configured_state: isPaused ? ('paused' as const) : ('enabled' as const),
      effective_state: isPaused ? ('paused' as const) : ('enabled' as const),
      policy_version: 29,
      active_ticket_count: scenario === 'empty' ? 0 : 1,
    },
    recent_operations: [],
    runtime_entry_authority: {
      venue_id: 'binance-usdm',
      account_id: 'primary',
      status: 'ready',
      effective_status: 'ready',
      exchange_commands_enabled: true,
    },
    strategies: [
      {
        strategy_group_id: 'CPM-RO-001',
        strategy_name: '均线回踩做多',
        configured_state: isPaused ? ('paused' as const) : ('enabled' as const),
        effective_state: isPaused ? ('paused' as const) : ('enabled' as const),
        control_version: 3,
      },
      {
        strategy_group_id: 'BRF2-001',
        strategy_name: '假反弹衰竭做空',
        configured_state: isPaused ? ('paused' as const) : ('enabled' as const),
        effective_state: isPaused ? ('paused' as const) : ('enabled' as const),
        control_version: 3,
      },
      {
        strategy_group_id: 'MI-001',
        strategy_name: '相对强弱冲量',
        configured_state: isPaused ? ('paused' as const) : ('enabled' as const),
        effective_state: isPaused ? ('paused' as const) : ('enabled' as const),
        control_version: 3,
      },
      {
        strategy_group_id: 'MPG-001',
        strategy_name: '趋势动量持续',
        configured_state: isPaused ? ('paused' as const) : ('enabled' as const),
        effective_state: isPaused ? ('paused' as const) : ('enabled' as const),
        control_version: 3,
      },
      {
        strategy_group_id: 'SOR-1H-001',
        strategy_name: '单边突破 (1h/15m)',
        configured_state: isPaused ? ('paused' as const) : ('enabled' as const),
        effective_state: isPaused ? ('paused' as const) : ('enabled' as const),
        control_version: 3,
      },
    ],
  };
}

function getMockTickets(scenario: ScenarioKey) {
  const nowMs = Date.now();
  if (scenario === 'normal') {
    return {
      code: 0,
      message: 'ok',
      data: {
        items: [
          {
            ticket_id: 'ticket:76be9c73106d6a80ac8150a555f8f902',
            strategy_group_id: 'BRF2-001',
            event_spec_id: 'event:brf2-001',
            exchange_instrument_id: 'binance-usdm:LTCUSDT:perpetual',
            position_side: 'short' as const,
            ticket_status: 'active',
            terminal_at_ms: null,
            issued_at_ms: nowMs - 9910000,
            aggregate_status: 'position_protected',
            lifecycle_stage: 'protection' as const,
            completed_stage_count: 4,
            total_stage_count: 8 as const,
            management_mode: 'AUTO' as const,
            manual_risk_reason: null,
            net_pnl: { value: '165.00', unit: 'USDT' },
            net_r: { value: '1.24', unit: 'R' },
            gross_pnl: { value: '170.00', unit: 'USDT' },
            fees: { value: '-5.00', unit: 'USDT' },
            funding: { value: '0.00', unit: 'USDT' },
            attention_items: [],
            evidence: [],
          },
          {
            ticket_id: 'ticket:98cf1a22106d6a80ac8150a555f8f111',
            strategy_group_id: 'CPM-RO-001',
            event_spec_id: 'event:cpm-002',
            exchange_instrument_id: 'binance-usdm:SOLUSDT:perpetual',
            position_side: 'long' as const,
            ticket_status: 'active',
            terminal_at_ms: null,
            issued_at_ms: nowMs - 3600000,
            aggregate_status: 'entry_submitted',
            lifecycle_stage: 'entry' as const,
            completed_stage_count: 2,
            total_stage_count: 8 as const,
            management_mode: 'AUTO' as const,
            manual_risk_reason: null,
            net_pnl: { value: null, unit: 'USDT' },
            net_r: { value: null, unit: 'R' },
            gross_pnl: { value: null, unit: 'USDT' },
            fees: { value: null, unit: 'USDT' },
            funding: { value: null, unit: 'USDT' },
            attention_items: ['入场回报已确认，等待初始止损挂单事实确认'],
            evidence: [],
          },
        ],
        next_cursor: null,
      },
    };
  }

  if (scenario === 'manual') {
    return {
      code: 0,
      message: 'ok',
      freshness: 'fresh' as const,
      data: {
        items: [
          {
            ticket_id: 'ticket:4a8c90fe106d6a80ac8150a555f8feee',
            strategy_group_id: 'CPM-RO-001',
            event_spec_id: 'event:cpm-003',
            exchange_instrument_id: 'binance-usdm:BTCUSDT:perpetual',
            position_side: 'long' as const,
            ticket_status: 'active',
            terminal_at_ms: null,
            issued_at_ms: nowMs - 14400000,
            aggregate_status: 'position_protected',
            lifecycle_stage: 'protection' as const,
            completed_stage_count: 4,
            total_stage_count: 8 as const,
            management_mode: 'MANUAL' as const,
            manual_risk_reason: 'MANUAL_TAKEOVER_ACTIVE_ON_SYMBOL: BTCUSDT',
            management_orders: [
              {
                exchange_order_id: 'ord-stop-9001',
                remaining_quantity: '0.025',
                terms: { order_type: 'STOP_MARKET', trigger_price: '89900.0' },
              },
            ],
            net_pnl: { value: '85.20', unit: 'USDT' },
            net_r: { value: '0.92', unit: 'R' },
            gross_pnl: { value: '93.20', unit: 'USDT' },
            fees: { value: '-8.00', unit: 'USDT' },
            funding: { value: '0.00', unit: 'USDT' },
            attention_items: ['整笔已转人工管理 · 外部干预触发'],
            evidence: [],
          },
        ],
        next_cursor: null,
      },
    };
  }

  // empty
  return {
    code: 0,
    message: 'ok',
    freshness: 'fresh' as const,
    data: {
      items: [],
      next_cursor: null,
    },
  };
}

function getMockPerformance(scenario: ScenarioKey) {
  const nowMs = Date.now();
  const fromMs = nowMs - 30 * 86_400_000;
  const isManual = scenario === 'manual';
  return {
    data: {
      sample_count: 14,
      confirmed_count: isManual ? 12 : 14,
      unreviewed_count: 0,
      win_count: 9,
      loss_count: 5,
      breakeven_count: 0,
      from_ms: fromMs,
      to_ms: nowMs,
      summary_scope: 'full_window',
      time_basis: 'terminal',
      view: 'all',
      exit_scope: 'all',
      snapshot_id: `profit:mock-${scenario}`,
      complete_review_count: isManual ? 12 : 14,
      incomplete_review_count: isManual ? 2 : 0,
      attention_count: isManual ? 2 : 0,
      verified_totals: {
        gross_pnl: { value: '512.40', unit: 'USDT', unavailable_reason: null },
        net_pnl: { value: '468.20', unit: 'USDT', unavailable_reason: null },
        net_r: { value: '4.1800', unit: 'R', unavailable_reason: null },
        fees: { value: '-41.10', unit: 'USDT', unavailable_reason: null },
        funding: { value: '-3.10', unit: 'USDT', unavailable_reason: null },
      },
      metric_coverage: {
        gross_pnl: { available_count: 14, total_count: 14, missing_ticket_ids: [] },
        net_pnl: {
          available_count: isManual ? 12 : 14,
          total_count: 14,
          missing_ticket_ids: isManual ? ['ticket:unloaded-missing-999'] : [],
        },
        net_r: {
          available_count: isManual ? 12 : 14,
          total_count: 14,
          missing_ticket_ids: isManual ? ['ticket:unloaded-missing-999'] : [],
        },
        fees: { available_count: 14, total_count: 14, missing_ticket_ids: [] },
        funding: { available_count: isManual ? 12 : 14, total_count: 14, missing_ticket_ids: [] },
      },
      breakdown: {
        strategy: {
          sample_count: 12,
          confirmed_count: 12,
          unreviewed_count: 0,
          win_count: 8,
          loss_count: 4,
          breakeven_count: 0,
          verified_totals: {
            gross_pnl: { value: '490.00', unit: 'USDT', unavailable_reason: null },
            net_pnl: { value: '450.20', unit: 'USDT', unavailable_reason: null },
            net_r: { value: '4.0200', unit: 'R', unavailable_reason: null },
            fees: { value: '-36.70', unit: 'USDT', unavailable_reason: null },
            funding: { value: '-3.10', unit: 'USDT', unavailable_reason: null },
          },
          metric_coverage: {},
        },
        owner: {
          sample_count: 2,
          confirmed_count: 0,
          unreviewed_count: 0,
          win_count: 1,
          loss_count: 1,
          breakeven_count: 0,
          verified_totals: {
            gross_pnl: { value: '22.40', unit: 'USDT', unavailable_reason: null },
            net_pnl: { value: '18.00', unit: 'USDT', unavailable_reason: null },
            net_r: { value: '0.1600', unit: 'R', unavailable_reason: null },
            fees: { value: '-4.40', unit: 'USDT', unavailable_reason: null },
            funding: { value: '0.00', unit: 'USDT', unavailable_reason: null },
          },
          metric_coverage: {},
        },
        safety: {
          sample_count: 0,
          confirmed_count: 0,
          unreviewed_count: 0,
          win_count: 0,
          loss_count: 0,
          breakeven_count: 0,
          verified_totals: {
            gross_pnl: { value: null, unit: 'USDT', unavailable_reason: 'no_review_evidence' },
            net_pnl: { value: null, unit: 'USDT', unavailable_reason: 'no_review_evidence' },
            net_r: { value: null, unit: 'R', unavailable_reason: 'no_review_evidence' },
            fees: { value: null, unit: 'USDT', unavailable_reason: 'no_review_evidence' },
            funding: { value: null, unit: 'USDT', unavailable_reason: 'no_review_evidence' },
          },
          metric_coverage: {},
        },
        unknown: {
          sample_count: 0,
          confirmed_count: 0,
          unreviewed_count: 0,
          win_count: 0,
          loss_count: 0,
          breakeven_count: 0,
          verified_totals: {
            gross_pnl: { value: null, unit: 'USDT', unavailable_reason: 'no_review_evidence' },
            net_pnl: { value: null, unit: 'USDT', unavailable_reason: 'no_review_evidence' },
            net_r: { value: null, unit: 'R', unavailable_reason: 'no_review_evidence' },
            fees: { value: null, unit: 'USDT', unavailable_reason: 'no_review_evidence' },
            funding: { value: null, unit: 'USDT', unavailable_reason: 'no_review_evidence' },
          },
          metric_coverage: {},
        },
      },
    },
  };
}

function getMockDirectionalRisk(scenario: ScenarioKey) {
  const nowMs = Date.now();
  return {
    control: {
      venue_id: 'binance-usdm',
      account_id: 'primary',
      version: 1,
      view: 'neutral' as const,
      rule_digest: 'sha256:54563b9f46a0370f2efda893fd6b4acc18ed6933f75961818ae7003b0f1a1406',
      rule_id: 'owner-directional-risk:v2',
      effective_at_ms: nowMs - 7200000,
    },
    long_limit: '0.04',
    short_limit: '0.04',
    long_risk_at_stop: scenario === 'manual' ? '45.00' : '18.50',
    short_risk_at_stop: scenario === 'manual' ? '0.00' : '24.00',
    wallet_balance_at_last_admission: '2450.00',
    balance_captured_at_ms: nowMs - 1800000,
    review_due: scenario === 'empty',
    observed_at_ms: nowMs,
    long_over_limit_at_last_balance: false,
    short_over_limit_at_last_balance: false,
  };
}

// ==========================================
// STRICT MOCK ROUTER & NETWORK ISOLATION
// ==========================================

function handleMockApiRequest(method: string, urlStr: string): Response | null {
  let pathname = urlStr;
  try {
    const parsed = new URL(urlStr, typeof window !== 'undefined' ? window.location.origin : 'http://localhost');
    pathname = parsed.pathname;
  } catch {
    // pathname remains urlStr
  }

  const normalizedMethod = (method || 'GET').toUpperCase();

  if (normalizedMethod === 'GET' && /^\/api\/owner\/v1\/tickets\/[^/]+\/exit-plan$/.test(pathname)) {
    return new Response(JSON.stringify({ plan: null }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  }

  // 1. Exact Method + Exact Path Routing
  if (normalizedMethod === 'GET' && pathname === '/api/owner/v1/overview') {
    return new Response(JSON.stringify(getMockOverview(currentScenario)), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  if (normalizedMethod === 'GET' && pathname === '/api/owner/v1/controls/directional-risk') {
    return new Response(JSON.stringify(getMockDirectionalRisk(currentScenario)), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  if (normalizedMethod === 'GET' && pathname === '/api/owner/v1/controls/exit-configuration') {
    const events = [
      'CPM-RO-001:CPM-LONG:v3',
      'MI-001:MI-LONG:v3',
      'MPG-001:MPG-LONG:v3',
      'BRF2-001:BRF2-SHORT:v3',
      'SOR-1H-001:SOR-1H-LONG:v1',
      'SOR-1H-001:SOR-1H-SHORT:v1',
    ].map((e, i) => ({
      event_spec_id: `event_spec:${e}`,
      expected_binding_id: `binding-${i}`,
      expected_binding_revision: 1,
      reward_multiple: i < 4 ? '1.0' : '1.2',
      target_fraction: i < 4 ? '0.05' : '0.5',
      minimum_lift: i < 4,
      max_actual_fraction: i < 4 ? '0.5' : '1',
      ma50_enabled: i < 3,
    }));
    return new Response(
      JSON.stringify({
        current: { revision: 2 },
        intent: {
          product_id: 'brc-app-manual-v1',
          venue_id: 'binance-usdm',
          account_id: 'seoul-manual-1',
          expected_revision: 2,
          events,
        },
        sources: events.map((ev) => ({
          event_spec_id: ev.event_spec_id,
          profile: {
            tp1: { reward_multiple: ev.reward_multiple, quantity_fraction: ev.target_fraction },
            execution: { quantity_policy: ev.minimum_lift ? 'target_floor_then_minimum' : 'floor_only' },
          },
        })),
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } }
    );
  }

  if (normalizedMethod === 'POST' && pathname === '/api/owner/v1/controls/exit-configuration/preview') {
    const nowMs = Date.now();
    const events = [
      'CPM-RO-001:CPM-LONG:v3',
      'MI-001:MI-LONG:v3',
      'MPG-001:MPG-LONG:v3',
      'BRF2-001:BRF2-SHORT:v3',
      'SOR-1H-001:SOR-1H-LONG:v1',
      'SOR-1H-001:SOR-1H-SHORT:v1',
    ].map((e, i) => ({
      event_spec_id: `event_spec:${e}`,
      expected_binding_id: `binding-${i}`,
      expected_binding_revision: 1,
      reward_multiple: i === 0 ? '1.5' : i < 4 ? '1.0' : '1.2',
      target_fraction: i < 4 ? '0.05' : '0.5',
      minimum_lift: i < 4,
      max_actual_fraction: i === 3 ? '0.4' : i < 4 ? '0.5' : '1',
      ma50_enabled: i === 1 ? false : i < 3,
    }));
    return new Response(
      JSON.stringify({
        intent: {
          product_id: 'brc-app-manual-v1',
          venue_id: 'binance-usdm',
          account_id: 'seoul-manual-1',
          expected_revision: 2,
          events,
        },
        profiles: events.map((ev) => ({
          event_spec_id: ev.event_spec_id,
          profile: {
            tp1: { reward_multiple: ev.reward_multiple, quantity_fraction: ev.target_fraction },
            execution: { quantity_policy: ev.minimum_lift ? 'target_floor_then_minimum' : 'floor_only' },
          },
        })),
        preview_digest: `sha256:${'a'.repeat(64)}`,
        valid_until_ms: nowMs + 300_000,
        source_configuration_revision: 2,
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } }
    );
  }

  if (normalizedMethod === 'GET' && pathname === '/api/owner/v1/controls/risk-budget') {
    return new Response(
      JSON.stringify({
        venue_id: 'binance-usdm',
        account_id: 'seoul-manual-1',
        baseline: '0.025',
        gross_limit: '0.075',
        minimum_risk: '0.0125',
        long_limit: '0.050',
        short_limit: '0.050',
        entry_enabled: true,
        long_risk_at_stop: '0',
        short_risk_at_stop: '0',
        policy_version: 29,
        directional_version: 6,
        pending_baseline: null,
        pending_directional_view: null,
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } }
    );
  }

  if (normalizedMethod === 'GET' && pathname === '/api/owner/v1/controls') {
    return new Response(JSON.stringify(getMockControls(currentScenario)), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  if (normalizedMethod === 'GET' && pathname === '/api/owner/v1/controls/selection/preview') {
    const nowMs = Date.now();
    return new Response(
      JSON.stringify({
        freshness: 'fresh',
        generated_at: new Date(nowMs).toISOString(),
        data: {
          strategy_group_id: 'CPM-RO-001',
          selection_mode: 'dynamic_selection',
          cadence_hours: 4,
          installed: true,
          authority_id: 'auth-sel-1',
          authority_status: 'valid',
          rollback_baseline_id: 'baseline-static-1',
          selection_epoch_id: 'epoch-1',
          candidate_count: 12,
          selected_count: 4,
          snapshot_decision_at_ms: nowMs - 600_000,
          members: [],
        },
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } }
    );
  }

  if (normalizedMethod === 'POST' && pathname === '/api/owner/v1/controls/exposure/flatten-all/preview') {
    return new Response(
      JSON.stringify({
        owner_policy_version: 29,
        snapshot_digest: 'sha256:mockmanual290000',
        ticket_ids: ['ticket:manual-takeover-001'],
        ticket_states: {
          'ticket:manual-takeover-001': 'blocked',
        },
        tickets: [
          {
            ticket_id: 'ticket:manual-takeover-001',
            strategy_group_id: 'MPG-001',
            exchange_instrument_id: 'binance-usdm:BTCUSDT:perpetual',
            position_side: 'long',
            management_mode: 'MANUAL',
            lifecycle_stage: 'protected',
          },
        ],
        first_blocker: currentScenario === 'manual' ? 'ticket_not_flattenable:ticket:manual-takeover-001:manual_open' : null,
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } }
    );
  }

  if (normalizedMethod === 'GET' && pathname === '/api/owner/v1/tickets') {
    const base = getMockTickets(currentScenario);
    if (getInitialTab() === 'trades' && currentScenario !== 'empty') {
      const nowMs = Date.now();
      base.data.items.push(
        {
          ticket_id: 'ticket:completed-brf2-001',
          strategy_group_id: 'BRF2-001',
          event_spec_id: 'event:brf2-done',
          exchange_instrument_id: 'binance-usdm:ETHUSDT:perpetual',
          position_side: 'short' as const,
          ticket_status: 'terminal',
          terminal_at_ms: nowMs - 3600000,
          issued_at_ms: nowMs - 10800000,
          aggregate_status: 'terminal',
          lifecycle_stage: 'review' as const,
          completed_stage_count: 8,
          total_stage_count: 8 as const,
          management_mode: 'AUTO' as const,
          manual_risk_reason: null,
          net_pnl: { value: '210.00', unit: 'USDT' },
          net_r: { value: '1.80', unit: 'R' },
          gross_pnl: { value: '220.00', unit: 'USDT' },
          fees: { value: '-10.00', unit: 'USDT' },
          funding: { value: '0.00', unit: 'USDT' },
          attention_items: [],
          evidence: [],
        } as never,
        {
          ticket_id: 'ticket:completed-gross-002',
          strategy_group_id: 'CPM-RO-001',
          event_spec_id: 'event:cpm-gross',
          exchange_instrument_id: 'binance-usdm:SOLUSDT:perpetual',
          position_side: 'long' as const,
          ticket_status: 'terminal',
          terminal_at_ms: nowMs - 7200000,
          issued_at_ms: nowMs - 14400000,
          aggregate_status: 'terminal',
          lifecycle_stage: 'review' as const,
          completed_stage_count: 8,
          total_stage_count: 8 as const,
          management_mode: 'AUTO' as const,
          manual_risk_reason: null,
          net_pnl: { value: null, unit: 'USDT', unavailable_reason: 'funding_unavailable' },
          net_r: { value: null, unit: 'R', unavailable_reason: 'funding_unavailable' },
          gross_pnl: { value: '42.50', unit: 'USDT' },
          fees: { value: '-3.20', unit: 'USDT' },
          funding: { value: null, unit: 'USDT' },
          attention_items: [],
          evidence: [],
        } as never
      );
    }
    return new Response(JSON.stringify(base), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  if (normalizedMethod === 'GET' && pathname === '/api/owner/v1/performance') {
    return new Response(JSON.stringify(getMockPerformance(currentScenario)), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  if (normalizedMethod === 'GET' && pathname === '/api/owner/v1/strategies') {
    return new Response(
      JSON.stringify({
        code: 0,
        message: 'ok',
        freshness: 'fresh',
        data: {
          performance: getMockPerformance(currentScenario).data,
          items: [
            {
              strategy_group_id: 'CPM-RO-001',
              strategy_version_id: 'sgv:CPM-RO-001:v1',
              version: 1,
              is_current: true,
              name: '均线回踩做多',
              timeframe: '1h',
              ticket_count: 8,
              observation_count: 24,
              natural_terminal_count: 6,
              controlled_exit_count: 2,
              safety_exit_count: 0,
              unknown_exit_count: 0,
              tp1_reached_count: 4,
              tp1_not_reached_count: 2,
              confirmed_review_count: 6,
              pending_review_count: 2,
              win_count: 4,
              loss_count: 2,
              net_pnl: { value: '258.20', unit: 'USDT' },
              net_r: { value: '2.38', unit: 'R' },
              metric_coverage: { net_pnl: { available_count: 6, total_count: 8 } },
            },
            {
              strategy_group_id: 'BRF2-001',
              strategy_version_id: 'sgv:BRF2-001:v3',
              version: 3,
              is_current: true,
              name: '假反弹衰竭做空',
              timeframe: '1h',
              ticket_count: 6,
              observation_count: 19,
              natural_terminal_count: 6,
              controlled_exit_count: 0,
              safety_exit_count: 0,
              unknown_exit_count: 0,
              tp1_reached_count: 4,
              tp1_not_reached_count: 2,
              confirmed_review_count: 6,
              pending_review_count: 0,
              win_count: 5,
              loss_count: 1,
              net_pnl: { value: '210.00', unit: 'USDT' },
              net_r: { value: '1.80', unit: 'R' },
              metric_coverage: { net_pnl: { available_count: 6, total_count: 6 } },
            },
          ],
        },
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } }
    );
  }

  if (normalizedMethod === 'GET' && /^\/api\/owner\/v1\/controls\/strategies\/[^/]+\/selection$/.test(pathname)) {
    return new Response(
      JSON.stringify({
        installed: true,
        cadence_hours: 4,
        runtime: {
          installed: true,
          current_authority_id: 'auth-mock-1',
          current_authority_outcome: 'VALID_NEW',
          first_blocker: null,
          latest_ready_count: 2,
          latest_selected_count: 2,
          membership_valid_until_ms: Date.now() + 3600000,
          materialization_generation_id: 'mat-1',
          materialization_state: 'ACTIVE',
          members: [],
        },
        control: { selection_mode: 'dynamic_selection', control_version: 1 },
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } }
    );
  }

  if (normalizedMethod === 'GET' && /^\/api\/owner\/v1\/tickets\/([^/]+)\/causality$/.test(pathname)) {
    const match = /^\/api\/owner\/v1\/tickets\/([^/]+)\/causality$/.exec(pathname);
    const ticketId = decodeURIComponent(match?.[1] ?? 'ticket:mock');
    const nowMs = Date.now();
    const activeMatch = getMockTickets(currentScenario).data.items.find((t) => t.ticket_id === ticketId);
    if (activeMatch) {
      return new Response(
        JSON.stringify({
          code: 0,
          message: 'ok',
          data: {
            trade: activeMatch,
            current_stage: activeMatch.lifecycle_stage,
            price_plan: {
              actual_entry_price: '91250.0',
              entry_reference_price: '91240.0',
              initial_stop_price: '89900.0',
              active_stop_price: '89900.0',
              ticket_quantity: '0.025',
            },
            stages: [],
            annotations: [],
            raw_commands: [],
            raw_events: [],
          },
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } }
      );
    }
    return new Response(
      JSON.stringify({
        code: 0,
        message: 'ok',
        data: {
          trade: {
            ticket_id: ticketId,
            strategy_group_id: 'CPM-RO-001',
            event_spec_id: 'event:mock-causality',
            exchange_instrument_id: 'binance-usdm:BTCUSDT:perpetual',
            position_side: 'long',
            ticket_status: 'terminal',
            terminal_at_ms: nowMs - 1800000,
            issued_at_ms: nowMs - 7200000,
            aggregate_status: 'terminal',
            lifecycle_stage: 'review',
            completed_stage_count: 8,
            total_stage_count: 8,
            net_pnl: { value: null, unit: 'USDT', unavailable_reason: 'funding_unavailable' },
            net_r: { value: null, unit: 'R', unavailable_reason: 'funding_unavailable' },
            gross_pnl: { value: '35.00', unit: 'USDT' },
            fees: { value: '-2.50', unit: 'USDT' },
            funding: { value: null, unit: 'USDT' },
            attention_items: [],
            evidence: [],
          },
          current_stage: 'review',
          price_plan: {
            actual_entry_price: '91250.0',
            entry_reference_price: '91240.0',
            initial_stop_price: '89900.0',
            active_stop_price: '91250.0',
            ticket_quantity: '0.025',
          },
          stages: [
            {
              key: 'signal',
              label: '信号',
              status: 'complete',
              summary: '策略信号生成并记录',
              duration_ms: 12,
              started_at_ms: nowMs - 7200000,
              completed_at_ms: nowMs - 7199988,
              evidence: [],
            },
          ],
          annotations: [],
          raw_commands: [],
          raw_events: [],
        },
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } }
    );
  }

  // 1g. /api/owner/v1/review
  if (normalizedMethod === 'GET' && pathname === '/api/owner/v1/review') {
    const nowMs = Date.now();
    return new Response(
      JSON.stringify({
        freshness: 'fresh',
        generated_at: new Date(nowMs).toISOString(),
        source_watermark: new Date(nowMs).toISOString(),
        data: {
          from_ms: nowMs - 30 * 86400_000,
          to_ms: nowMs,
          total_reviewed_count: 3,
          complete_count: 0,
          incomplete_evidence_count: 2,
          waiting_review_count: 1,
          attention_count: 1,
          next_cursor: null,
          net_pnl: { value: null, unit: 'USDT', unavailable_reason: 'incomplete_review_economics' },
          net_r: { value: null, unit: 'R', unavailable_reason: 'incomplete_review_economics' },
          fees: { value: '-2.00', unit: 'USDT', unavailable_reason: null },
          funding: { value: null, unit: 'USDT', unavailable_reason: 'funding_unavailable' },
          strategy_group_samples: [
            {
              strategy_group_id: 'MPG-001',
              sample_count: 3,
              evidence_state: 'observe_only',
              evidence: [{ kind: 'ticket', identity: 'ticket:exec-gap', occurred_at_ms: nowMs - 3600_000 }],
            },
          ],
          execution_quality_breakdown: [
            {
              label: 'evidence_incomplete',
              count: 1,
              evidence: [{ kind: 'ticket', identity: 'ticket:exec-gap', occurred_at_ms: nowMs - 3600_000 }],
            },
            {
              label: 'complete',
              count: 1,
              evidence: [{ kind: 'ticket', identity: 'ticket:econ-gap', occurred_at_ms: nowMs - 7200_000 }],
            },
          ],
          exit_reason_breakdown: [
            {
              label: 'pre_tp1_time_stop_hit',
              count: 2,
              evidence: [{ kind: 'ticket', identity: 'ticket:exec-gap', occurred_at_ms: nowMs - 3600_000 }],
            },
          ],
          items: [
          {
            ticket_id: 'ticket:exec-gap',
            strategy_group_id: 'MPG-001',
            exchange_instrument_id: 'binance-usdm:BTCUSDT:perpetual',
            position_side: 'long',
            terminal_at_ms: nowMs - 3600_000,
            review: {
              ticket_id: 'ticket:exec-gap',
              execution_classification: 'evidence_incomplete',
              review_status: 'incomplete_evidence',
              exit_reason: 'pre_tp1_time_stop_hit',
              exit_attribution: {
                code: 'pre_tp1_time_stop_hit',
                label: 'TP1 前持仓超时退出',
                detail: '持仓在 TP1 触发前到达时间止损窗口并受控平仓。',
                source: 'exit_event',
                evidence: [],
              },
              economic_summary: {
                gross_pnl: { value: '24.50', unit: 'USDT', unavailable_reason: null },
                fees: { value: '-1.20', unit: 'USDT', unavailable_reason: null },
                funding: { value: '0.35', unit: 'USDT', unavailable_reason: null },
                net_pnl: { value: '23.65', unit: 'USDT', unavailable_reason: null },
                net_r: { value: '1.4200', unit: 'R', unavailable_reason: null },
              },
              execution_gaps: [
                { code: 'stop_trace_missing', label: '保护止损轨迹待核实', impact: '执行链未完全闭合，但不影响已成交净额核算' },
              ],
              economic_gaps: [],
              attention_items: [],
              sentences: [
                {
                  template_id: 'execution_incomplete',
                  text: '保护止损部分轨迹尚待核实。',
                  evidence: [{ kind: 'ticket', identity: 'ticket:exec-gap', occurred_at_ms: nowMs - 3600_000 }],
                },
                {
                  template_id: 'economics_complete',
                  text: '毛收益、手续费与资金费均已完整核实。',
                  evidence: [],
                },
              ],
              final_conclusion: '执行证据存在待核实项，但收益核算已完整确认。',
              evidence: [{ kind: 'ticket', identity: 'ticket:exec-gap', occurred_at_ms: nowMs - 3600_000 }],
            },
          },
          {
            ticket_id: 'ticket:econ-gap',
            strategy_group_id: 'MPG-001',
            exchange_instrument_id: 'binance-usdm:ETHUSDT:perpetual',
            position_side: 'short',
            terminal_at_ms: nowMs - 7200_000,
            review: {
              ticket_id: 'ticket:econ-gap',
              execution_classification: 'complete',
              review_status: 'incomplete_evidence',
              exit_reason: 'owner_flatten_all:manual-1',
              exit_attribution: {
                code: 'owner_flatten_all',
                label: 'Owner 全部持仓受控平仓',
                detail: 'Owner 发起受控平仓。',
                source: 'review_fills',
                evidence: [],
              },
              economic_summary: {
                gross_pnl: { value: '14.20', unit: 'USDT', unavailable_reason: null },
                fees: { value: '-0.80', unit: 'USDT', unavailable_reason: null },
                funding: { value: null, unit: 'USDT', unavailable_reason: 'funding_unavailable' },
                net_pnl: { value: null, unit: 'USDT', unavailable_reason: 'funding_unavailable' },
                net_r: { value: null, unit: 'R', unavailable_reason: 'funding_unavailable' },
              },
              execution_gaps: [],
              economic_gaps: [
                { code: 'funding_unavailable', label: '资金费无法精确归因', impact: '净收益暂不可确认，仅展示毛收益' },
              ],
              attention_items: ['funding_unavailable'],
              sentences: [],
              final_conclusion: '执行链路已核实，资金费缺项导致净收益待确认。',
              evidence: [{ kind: 'ticket', identity: 'ticket:econ-gap', occurred_at_ms: nowMs - 7200_000 }],
            },
          },
          {
            ticket_id: 'ticket:waiting',
            strategy_group_id: 'MPG-001',
            exchange_instrument_id: 'binance-usdm:SOLUSDT:perpetual',
            position_side: 'long',
            terminal_at_ms: nowMs - 10800_000,
            review: {
              ticket_id: 'ticket:waiting',
              execution_classification: 'waiting_review',
              review_status: 'waiting_review',
              exit_reason: null,
              economic_summary: {
                gross_pnl: { value: null, unit: 'USDT', unavailable_reason: 'review_missing' },
                fees: { value: null, unit: 'USDT', unavailable_reason: 'review_missing' },
                funding: { value: null, unit: 'USDT', unavailable_reason: 'review_missing' },
                net_pnl: { value: null, unit: 'USDT', unavailable_reason: 'review_missing' },
                net_r: { value: null, unit: 'R', unavailable_reason: 'review_missing' },
              },
              execution_gaps: [],
              economic_gaps: [],
              attention_items: [],
              sentences: [],
              final_conclusion: null,
              evidence: [],
            },
          },
          ],
        },
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } }
    );
  }

  // 2. Strict Sandbox Barrier: any other /api/* request is strictly rejected & recorded
  if (pathname.startsWith('/api/') || pathname.includes('/api/')) {
    const record = { method: normalizedMethod, pathname, url: urlStr, time: Date.now() };
    if (typeof window !== 'undefined') {
      window.__recordedUnexpectedRequests = window.__recordedUnexpectedRequests || [];
      window.__recordedUnexpectedRequests.push(record);
    }
    console.error('[ISOLATED_MOCK_BLOCKED] Attempted unauthorized API request in isolated mock preview:', record);
    return new Response(
      JSON.stringify({
        code: 403,
        error: 'BLOCKED_BY_ISOLATED_MOCK',
        message: `未授权的网络请求被严格隔离沙箱阻断: ${normalizedMethod} ${pathname}`,
      }),
      { status: 403, headers: { 'Content-Type': 'application/json' } }
    );
  }

  return null; // Static assets, styles, HMR
}

apiClient.use({
  async onRequest({ request }) {
    const res = handleMockApiRequest(request.method, request.url);
    if (res) return res;

    // Safety fallback: reject any unhandled apiClient calls
    const record = { method: request.method, pathname: request.url, url: request.url, time: Date.now() };
    if (typeof window !== 'undefined') {
      window.__recordedUnexpectedRequests = window.__recordedUnexpectedRequests || [];
      window.__recordedUnexpectedRequests.push(record);
    }
    return new Response(
      JSON.stringify({
        code: 403,
        error: 'BLOCKED_BY_ISOLATED_MOCK',
        message: `未授权的 APIClient 请求被隔离沙箱阻断: ${request.method} ${request.url}`,
      }),
      { status: 403, headers: { 'Content-Type': 'application/json' } }
    );
  },
});

const originalFetch = window.fetch;
window.fetch = async function (input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
  const method = (init?.method || (typeof input === 'object' && 'method' in input ? input.method : 'GET') || 'GET').toUpperCase();

  const mockRes = handleMockApiRequest(method, url);
  if (mockRes) {
    return mockRes;
  }

  // Double barrier: any fetch containing /api/ must NEVER fall through to originalFetch
  if (url.includes('/api/')) {
    const record = { method, pathname: url, url, time: Date.now() };
    window.__recordedUnexpectedRequests = window.__recordedUnexpectedRequests || [];
    window.__recordedUnexpectedRequests.push(record);
    return new Response(
      JSON.stringify({
        code: 403,
        error: 'BLOCKED_BY_ISOLATED_MOCK',
        message: `未授权的全局 fetch API 请求被隔离沙箱阻断: ${method} ${url}`,
      }),
      { status: 403, headers: { 'Content-Type': 'application/json' } }
    );
  }

  return originalFetch(input, init);
};

// ==========================================
// AUTOMATED VERIFICATION EXPOSURE
// ==========================================

if (typeof window !== 'undefined') {
  window.__getOverviewVerification = () => {
    const activeTab = getInitialTab();
    const isTrades = activeTab === 'trades';
    const isStrategies = activeTab === 'strategies';
    const isReview = activeTab === 'review';
    const isControls = activeTab === 'controls';
    const pulseEl = document.querySelector('[data-testid="capacity-pulse"]');
    const pnlEl = document.querySelector('[data-testid="net-pnl-card"]');
    const rEl = document.querySelector('[data-testid="net-r-card"]');
    const dirRiskEl = document.querySelector('section[aria-label="方向风险偏好"]');
    const feishuEl = document.querySelector('[aria-label="飞书通知投递状态"]');
    const episodesSection = document.querySelector('h2');

    const tradesFilterEl = document.querySelector('[data-testid="trades-filter-bar"]');
    const incomeSummaryEl = document.querySelector('[data-testid="income-summary"]');
    const activeCovEl = document.querySelector('[data-testid="active-coverage"]');
    const strategiesFilterEl = document.querySelector('[data-testid="strategies-time-range-bar"]');
    const strategiesTableEl = document.querySelector('[data-testid="strategies-matrix-table"]');
    const reviewFilterEl = document.querySelector('[data-testid="review-filter-bar"]');
    const reviewTableEl = document.querySelector('[data-testid="review-table"]') || document.querySelector('[data-testid="review-mobile-list"]');
    const controlsMatrixEl = document.querySelector('[data-testid="controls-strategy-matrix"]');
    const controlsCapEl = document.querySelector('[data-testid="capacity-section"]');

    const innerWidth = window.innerWidth;
    const innerHeight = window.innerHeight;
    const scrollWidth = document.documentElement.scrollWidth;
    const scrollHeight = Math.max(document.documentElement.scrollHeight, document.body.scrollHeight);

    // Scan all DOM elements for right-edge boundary bleeding
    const allEls = Array.from(document.querySelectorAll('*'));
    const overflowElements: Array<{ tag: string; id: string; className: string; right: number; width: number }> = [];

    for (const el of allEls) {
      if (['HTML', 'BODY', 'SCRIPT', 'STYLE', 'HEAD', 'META', 'TITLE'].includes(el.tagName)) continue;
      const closedDisclosure = el.closest('details:not([open])');
      if (closedDisclosure && !closedDisclosure.querySelector(':scope > summary')?.contains(el)) continue;
      const rect = el.getBoundingClientRect();
      // Allow 1px subpixel tolerance
      if (rect.width > 0 && rect.right > innerWidth + 1) {
        overflowElements.push({
          tag: el.tagName,
          id: el.id,
          className: typeof el.className === 'string' ? el.className.slice(0, 80) : '',
          right: Math.round(rect.right),
          width: Math.round(rect.width),
        });
      }
    }

    const hasCriticalElements = isTrades
      ? Boolean(tradesFilterEl && incomeSummaryEl && activeCovEl)
      : isStrategies
      ? Boolean(strategiesFilterEl && incomeSummaryEl && strategiesTableEl)
      : isReview
      ? Boolean(reviewFilterEl && incomeSummaryEl && reviewTableEl)
      : isControls
      ? Boolean(controlsMatrixEl && controlsCapEl)
      : Boolean(pulseEl && pnlEl && rEl && dirRiskEl && feishuEl && episodesSection);

    return {
      href: window.location.href,
      isLoaded: hasCriticalElements && document.readyState === 'complete' && queryClient.isFetching() === 0,
      scenario: currentScenario,
      innerWidth,
      innerHeight,
      scrollWidth,
      scrollHeight,
      hasCriticalElements,
      overflowElements,
      unexpectedRequests: window.__recordedUnexpectedRequests || [],
    };
  };
}

// ==========================================
// PREVIEW HARNESS COMPONENT
// ==========================================

function OverviewPreviewHarness() {
  const [activeTab, setActiveTab] = useState<NavTabId>(getInitialTab);
  const [scenario, setScenarioState] = useState<ScenarioKey>(currentScenario);
  const { theme, setTheme, toggleTheme } = useTheme();
  const hideControls = shouldHideControls();

  useEffect(() => {
    const initialTheme = getInitialTheme();
    if (initialTheme && initialTheme !== theme) {
      setTheme(initialTheme);
    }
  }, [setTheme, theme]);

  const handleScenarioChange = (s: ScenarioKey) => {
    currentScenario = s;
    setScenarioState(s);
    queryClient.invalidateQueries();
  };

  return (
    <div className="min-h-screen bg-background text-text-primary">
      {/* Optional Top Controller Bar for Review */}
      {!hideControls && (
        <div className="border-b border-border bg-surface-subtle px-4 py-2 text-xs flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-text-secondary">隔离 Mock 场景:</span>
            <button
              type="button"
              id="btn-scenario-normal"
              className={`px-2.5 py-1 rounded cursor-pointer ${
                scenario === 'normal'
                  ? 'bg-brand text-white font-bold'
                  : 'bg-surface text-text-muted hover:text-text-primary'
              }`}
              onClick={() => handleScenarioChange('normal')}
            >
              场景 1: 正常自动运行 (AUTO)
            </button>
            <button
              type="button"
              id="btn-scenario-manual"
              className={`px-2.5 py-1 rounded cursor-pointer ${
                scenario === 'manual'
                  ? 'bg-brand text-white font-bold'
                  : 'bg-surface text-text-muted hover:text-text-primary'
              }`}
              onClick={() => handleScenarioChange('manual')}
            >
              场景 2: 人工接管触发 (MANUAL)
            </button>
            <button
              type="button"
              id="btn-scenario-empty"
              className={`px-2.5 py-1 rounded cursor-pointer ${
                scenario === 'empty'
                  ? 'bg-brand text-white font-bold'
                  : 'bg-surface text-text-muted hover:text-text-primary'
              }`}
              onClick={() => handleScenarioChange('empty')}
            >
              场景 3: 市场空仓与陈旧数据 (STALE)
            </button>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-text-muted">主题: {theme}</span>
            <button
              type="button"
              id="btn-toggle-theme"
              className="px-2 py-1 rounded bg-surface border border-border text-xs cursor-pointer"
              onClick={toggleTheme}
            >
              切换主题
            </button>
          </div>
        </div>
      )}

      {/* App Navbar with isRealData={false} */}
      <Navbar
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        isRealData={false}
        isIsolatedMock
        onLogout={() => {}}
      />

      {/* Page Content: Real OverviewPage, TradesPage or StrategiesPage component */}
      <main className="mx-auto max-w-[1520px] px-3 sm:px-6 py-5">
        {activeTab === 'trades' ? (
          <TradesPage />
        ) : activeTab === 'strategies' ? (
          <StrategiesPage />
        ) : activeTab === 'review' ? (
          <ReviewPage />
        ) : activeTab === 'controls' ? (
          <ControlsPage />
        ) : (
          <OverviewPage
            onNavigateToControls={() => setActiveTab('controls')}
            onNavigateToTab={setActiveTab}
          />
        )}
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <OverviewPreviewHarness />
      </ThemeProvider>
    </QueryClientProvider>
  </React.StrictMode>
);
