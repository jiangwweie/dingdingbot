// @vitest-environment jsdom
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ActiveEpisodesSection } from './ActiveEpisodesSection';
import type { TradeEpisodeSummary } from '../../types/overview';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let root: ReturnType<typeof createRoot>;
let container: HTMLDivElement;

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
});

function render(props: {
  episodes: TradeEpisodeSummary[];
  onSelectEpisode?: (ep: TradeEpisodeSummary) => void;
  isLoading?: boolean;
  isError?: boolean;
}) {
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(
      <ActiveEpisodesSection
        episodes={props.episodes}
        onSelectEpisode={props.onSelectEpisode ?? vi.fn()}
        isLoading={props.isLoading}
        isError={props.isError}
      />
    );
  });
}

describe('ActiveEpisodesSection Management Authority & Protection Truth', () => {
  it('renders MANUAL ticket with permanent takeover banner and does not claim automatic protection', () => {
    const manualEpisode: TradeEpisodeSummary = {
      ticket_id: 'tkt-manual-001',
      strategy_id: 'CPM-RO-001',
      strategy_name_zh: '均线回踩做多',
      symbol: 'BTCUSDT',
      side: 'long',
      lifecycle_stage: 'manual',
      lifecycle_stage_zh: '人工管理',
      completed_stage_count: 4,
      total_stage_count: 8,
      ticket_status: 'active',
      issued_at_formatted: '09:00:00',
      management_mode: 'MANUAL',
      is_protected: false,
      protection_state: '人工管理 · 保护待核实',
      manual_risk_reason: 'manual_stop_coverage_incomplete',
    };

    render({ episodes: [manualEpisode] });

    expect(container.textContent).toContain('整笔已转人工管理');
    expect(container.textContent).toContain('外部干预已触发永久接管');
    expect(container.textContent).toContain('既有挂单是否有效以交易所最新订单事实为准');
    expect(container.textContent).toContain('程序不再自动退出或修改保护');
    expect(container.textContent).toContain('新增开仓受限原因：manual_stop_coverage_incomplete');
    expect(container.textContent).toContain('人工管理 · 保护待核实');
    expect(container.textContent).not.toContain('程序自动管理');
    expect(container.textContent).not.toContain('已确认保护');
  });

  it('renders REVIEW_REQUIRED ticket with pending verification banner and paused disposition', () => {
    const reviewEpisode: TradeEpisodeSummary = {
      ticket_id: 'tkt-review-002',
      strategy_id: 'BRF2-001',
      strategy_name_zh: '假反弹衰竭做空',
      symbol: 'ETHUSDT',
      side: 'short',
      lifecycle_stage: 'protection',
      lifecycle_stage_zh: '保护安装',
      completed_stage_count: 3,
      total_stage_count: 8,
      ticket_status: 'active',
      issued_at_formatted: '11:00:00',
      management_mode: 'REVIEW_REQUIRED',
      is_protected: false,
      protection_state: '接管待核实 · 自动处置暂停',
    };

    render({ episodes: [reviewEpisode] });

    expect(container.textContent).toContain('接管待核实');
    expect(container.textContent).toContain('自动处置已暂停');
    expect(container.textContent).toContain('订单或持仓事实待核实，程序已暂停该笔自动处置');
    expect(container.textContent).not.toContain('程序自动管理');
    expect(container.textContent).not.toContain('已确认保护');
  });

  it('renders AUTO ticket with separate management authority and unconfirmed protection state', () => {
    const autoPendingEpisode: TradeEpisodeSummary = {
      ticket_id: 'tkt-auto-pending-003',
      strategy_id: 'MI-001',
      strategy_name_zh: '相对强弱冲量',
      symbol: 'SOLUSDT',
      side: 'long',
      lifecycle_stage: 'protection',
      lifecycle_stage_zh: '保护安装',
      completed_stage_count: 3,
      total_stage_count: 8,
      ticket_status: 'active',
      issued_at_formatted: '12:00:00',
      management_mode: 'AUTO',
      is_protected: false,
      protection_state: '保护安装或切换进行中',
    };

    render({ episodes: [autoPendingEpisode] });

    expect(container.textContent).toContain('程序自动管理');
    expect(container.textContent).toContain('保护安装或切换进行中');
    expect(container.textContent).not.toContain('已确认保护');
    expect(container.textContent).not.toContain('整笔已转人工管理');
  });

  it('renders AUTO ticket with confirmed protection state properly', () => {
    const autoConfirmedEpisode: TradeEpisodeSummary = {
      ticket_id: 'tkt-auto-confirmed-004',
      strategy_id: 'MI-001',
      strategy_name_zh: '相对强弱冲量',
      symbol: 'UNIUSDT',
      side: 'long',
      lifecycle_stage: 'protection',
      lifecycle_stage_zh: '保护安装',
      completed_stage_count: 4,
      total_stage_count: 8,
      ticket_status: 'active',
      issued_at_formatted: '12:30:00',
      management_mode: 'AUTO',
      is_protected: true,
      protection_state: '后端已确认保护 (7.24)',
    };

    render({ episodes: [autoConfirmedEpisode] });

    expect(container.textContent).toContain('程序自动管理');
    expect(container.textContent).toContain('后端已确认保护 (7.24)');
    expect(container.textContent).not.toContain('整笔已转人工管理');
  });

  it('deduplicates redundant manual takeover attention items while preserving distinct attention items and unknown risk codes', () => {
    const manualEpisodeWithUnknownReason: TradeEpisodeSummary = {
      ticket_id: 'tkt-manual-005',
      strategy_id: 'CPM-RO-001',
      strategy_name_zh: '均线回踩做多',
      symbol: 'BTCUSDT',
      side: 'long',
      lifecycle_stage: 'protection',
      lifecycle_stage_zh: '保护安装',
      completed_stage_count: 4,
      total_stage_count: 8,
      ticket_status: 'active',
      issued_at_formatted: '09:00:00',
      management_mode: 'MANUAL',
      is_protected: false,
      protection_state: '人工管理 · 保护待核实',
      manual_risk_reason: 'custom_unknown_reason_code_99',
      attention_items: ['整笔已转人工管理 · 外部干预触发', '独立订单差异待核对'],
    };

    render({ episodes: [manualEpisodeWithUnknownReason] });

    // Unknown risk reason code must never be discarded
    expect(container.textContent).toContain('新增开仓受限原因：custom_unknown_reason_code_99');
    // Pure redundant manual takeover attention string is deduplicated, distinct one is kept
    expect(container.textContent).not.toContain('外部干预触发');
    expect(container.textContent).toContain('独立订单差异待核对');
  });

  it('preserves attention items that contain supplemental risk facts even when they share manual/review prefixes (P1 regression)', () => {
    const manualSupplemental: TradeEpisodeSummary = {
      ticket_id: 'tkt-manual-supp-006',
      strategy_id: 'CPM-RO-001',
      strategy_name_zh: '均线回踩做多',
      symbol: 'BTCUSDT',
      side: 'long',
      lifecycle_stage: 'manual',
      lifecycle_stage_zh: '人工管理',
      completed_stage_count: 4,
      total_stage_count: 8,
      ticket_status: 'active',
      issued_at_formatted: '09:00:00',
      management_mode: 'MANUAL',
      is_protected: false,
      protection_state: '人工管理 · 保护待核实',
      attention_items: ['整笔已转人工管理；止损已撤销，当前没有保护单'],
    };

    const reviewSupplemental: TradeEpisodeSummary = {
      ticket_id: 'tkt-review-supp-007',
      strategy_id: 'BRF2-001',
      strategy_name_zh: '假反弹衰竭做空',
      symbol: 'ETHUSDT',
      side: 'short',
      lifecycle_stage: 'protection',
      lifecycle_stage_zh: '保护安装',
      completed_stage_count: 3,
      total_stage_count: 8,
      ticket_status: 'active',
      issued_at_formatted: '10:00:00',
      management_mode: 'REVIEW_REQUIRED',
      is_protected: false,
      protection_state: '接管待核实 · 自动处置暂停',
      attention_items: ['接管待核实；存在未核实残留订单'],
    };

    render({ episodes: [manualSupplemental, reviewSupplemental] });

    expect(container.textContent).toContain('整笔已转人工管理；止损已撤销，当前没有保护单');
    expect(container.textContent).toContain('接管待核实；存在未核实残留订单');
  });
});
