// @vitest-environment jsdom
import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, it, expect, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StrategyMatrix } from './StrategyMatrix';
import type { StrategyControlItem } from '../types/controls';

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const mockStrategies: StrategyControlItem[] = [
  {
    strategy_group_id: 'CPM-RO-001',
    name_zh: '动量突破',
    timeframe: '4h',
    configured_state: 'enabled',
    effective_state: 'enabled',
    control_version: 3,
    updated_at_ms: 1700000000000,
    reason_label: '正常运行',
    admission_health: {
      status: 'cleared',
      summary: '全部准入关卡通过',
      source: 'server_admission_fact',
    },
    active_tickets: [],
    strategy_version_id: 'cpm_v3.2',
  },
  {
    strategy_group_id: 'MPG-001',
    name_zh: '均值回归',
    timeframe: '1h',
    configured_state: 'enabled',
    effective_state: 'paused_by_global',
    control_version: 5,
    updated_at_ms: 1700000000000,
    reason_label: '全局 ENTRY 暂停',
    admission_health: {
      status: 'blocked',
      summary: '全局 ENTRY 暂停生效中',
      source: 'server_admission_fact',
    },
    active_tickets: [],
    strategy_version_id: 'mpg_v1.0',
  },
  {
    strategy_group_id: 'MI-001',
    name_zh: '微观结构动量',
    timeframe: '15m',
    configured_state: 'paused',
    effective_state: 'paused',
    control_version: 2,
    updated_at_ms: 1700000000000,
    reason_label: 'Owner 手动暂停新准入',
    admission_health: {
      status: 'blocked',
      summary: '单策略新准入暂停',
      source: 'server_admission_fact',
    },
    active_tickets: [],
    strategy_version_id: 'mi_v2.0',
  },
  {
    strategy_group_id: 'SOR-001',
    name_zh: '历史 SOR 路由',
    timeframe: '1m',
    configured_state: 'paused',
    effective_state: 'paused',
    control_version: 1,
    updated_at_ms: 1700000000000,
    reason_label: '永久退役',
    admission_health: {
      status: 'blocked',
      summary: '永久退役归档',
      source: 'server_admission_fact',
    },
    active_tickets: [],
    is_retired: true,
  },
];

describe('StrategyMatrix Component', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  it('renders all strategies with accurate status distinctions', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);

    act(() => {
      root.render(
        <QueryClientProvider client={queryClient}>
          <StrategyMatrix strategies={mockStrategies} />
        </QueryClientProvider>
      );
    });

    // Check CPM-RO-001 (enabled)
    const cpmRow = container.querySelector('[data-strategy-id="CPM-RO-001"]');
    expect(cpmRow).not.toBeNull();
    expect(cpmRow?.textContent).toContain('CPM-RO-001');
    expect(cpmRow?.textContent).toContain('配置: 已启用');
    expect(cpmRow?.textContent).toContain('暂停新准入');

    // Check MPG-001 (paused_by_global): MUST distinguish configured vs effective state
    const mpgRow = container.querySelector('[data-strategy-id="MPG-001"]');
    expect(mpgRow).not.toBeNull();
    expect(mpgRow?.textContent).toContain('MPG-001');
    expect(mpgRow?.textContent).toContain('配置: 已启用');
    expect(mpgRow?.textContent).toContain('全局暂停生效中');
    // Still enabled in configuration, so button offers "暂停新准入"
    expect(mpgRow?.textContent).toContain('暂停新准入');

    // Check MI-001 (paused)
    const miRow = container.querySelector('[data-strategy-id="MI-001"]');
    expect(miRow).not.toBeNull();
    expect(miRow?.textContent).toContain('MI-001');
    expect(miRow?.textContent).toContain('配置: 已暂停');
    expect(miRow?.textContent).toContain('恢复新准入');

    // Check SOR-001 (permanently retired)
    const sorRow = container.querySelector('[data-strategy-id="SOR-001"]');
    expect(sorRow).not.toBeNull();
    expect(sorRow?.textContent).toContain('SOR-001');
    expect(sorRow?.textContent).toContain('已退役 (RETIRED)');
    expect(sorRow?.textContent).toContain('已退役 (禁止恢复)');
    const sorButton = sorRow?.querySelector('button');
    expect(sorButton?.hasAttribute('disabled')).toBe(true);

    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('clicking 暂停新准入 opens modal with pause configuration', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);

    act(() => {
      root.render(
        <QueryClientProvider client={queryClient}>
          <StrategyMatrix strategies={mockStrategies} />
        </QueryClientProvider>
      );
    });

    const cpmRow = container.querySelector('[data-strategy-id="CPM-RO-001"]');
    const pauseBtn = cpmRow?.querySelector('button');

    act(() => {
      pauseBtn?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    // Modal dialog appears
    const modal = document.body.querySelector('[data-testid="totp-action-modal"]');
    expect(modal).not.toBeNull();
    expect(modal?.textContent).toContain('确认暂停新准入: CPM-RO-001');
    expect(modal?.textContent).toContain('暂停仅阻断');
    // TOTP field must NOT be rendered for pause
    expect(modal?.querySelector('input[inputmode="numeric"]')).toBeNull();
    // Reason input must be present
    expect(modal?.querySelector('input[placeholder*="本次控制操作原因"]')).not.toBeNull();

    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('clicking 恢复新准入 opens modal with TOTP requirement', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);

    act(() => {
      root.render(
        <QueryClientProvider client={queryClient}>
          <StrategyMatrix strategies={mockStrategies} />
        </QueryClientProvider>
      );
    });

    const miRow = container.querySelector('[data-strategy-id="MI-001"]');
    const resumeBtn = miRow?.querySelector('button');

    act(() => {
      resumeBtn?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    const modal = document.body.querySelector('[data-testid="totp-action-modal"]');
    expect(modal).not.toBeNull();
    expect(modal?.textContent).toContain('确认恢复新准入: MI-001');
    // TOTP field MUST be present for resume
    expect(modal?.querySelector('input[inputmode="numeric"]')).not.toBeNull();

    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('renders disabled "控制事实不可用" button when control facts are missing', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const strategiesWithMissingFacts: StrategyControlItem[] = [
      {
        strategy_group_id: 'CPM-RO-001',
        name_zh: '动量突破',
        timeframe: '4h',
        configured_state: undefined as any,
        effective_state: 'enabled',
        control_version: null as any,
        updated_at_ms: 1700000000000,
        reason_label: '缺失事实',
        admission_health: {
          status: 'unknown',
          summary: '缺少控制记录',
          source: 'unknown_fact',
        },
        active_tickets: [],
      },
    ];

    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);

    act(() => {
      root.render(
        <QueryClientProvider client={queryClient}>
          <StrategyMatrix strategies={strategiesWithMissingFacts} />
        </QueryClientProvider>
      );
    });

    const cpmRow = container.querySelector('[data-strategy-id="CPM-RO-001"]');
    expect(cpmRow).not.toBeNull();
    const btn = cpmRow?.querySelector('button');
    expect(btn?.textContent).toContain('控制事实不可用');
    expect(btn?.hasAttribute('disabled')).toBe(true);

    act(() => {
      root.unmount();
    });
    container.remove();
  });
});
