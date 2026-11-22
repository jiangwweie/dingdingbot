// @vitest-environment jsdom
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TopStatusBar } from './TopStatusBar';
import { CapacitySection } from './CapacitySection';
import { RecentOperations } from './RecentOperations';
import { StrategyMatrix } from './StrategyMatrix';
import { ControlledFlattenModal } from './ControlledFlattenModal';
import { formatControlOperationState } from '../mapping/controlStateMapping';
import type { StrategyControlItem } from '../types/controls';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const container = document.createElement('div');
document.body.appendChild(container);
let root: ReturnType<typeof createRoot> | undefined;

afterEach(() => {
  act(() => root?.unmount());
  root = undefined;
  container.innerHTML = '';
});

function render(element: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  root = createRoot(container);
  act(() => root!.render(<QueryClientProvider client={qc}>{element}</QueryClientProvider>));
}

describe('Controls page productization & truth constraints', () => {
  it('TopStatusBar avoids claiming all active tickets are protected and uses 已启用', () => {
    render(
      <TopStatusBar
        globalEntry={{
          configured_state: 'enabled',
          effective_state: 'enabled',
          policy_version: 31,
          active_ticket_count: 2,
          updated_at_ms: 1700000000000,
        }}
        pausedStrategyCount={1}
        totalActiveStrategies={4}
        onRequestAction={vi.fn()}
      />
    );
    expect(container.textContent).toContain('配置开关已开启');
    expect(container.textContent).toContain('仅控制新增开仓；不改变已有交易管理权');
    expect(container.textContent).toContain('3 已启用 / 1 已暂停');
    expect(container.textContent).toContain('当前在管 2 笔');
    expect(container.textContent).toContain('管理权与保护状态见持仓详情');
    expect(container.textContent).not.toContain('(受保护)');
    expect(container.textContent).not.toContain('运行 /');
  });

  it('CapacitySection uses real policyVersion, dynamic zero-count, and guards max_concurrent_tickets === 0', () => {
    render(
      <CapacitySection
        policyVersion={31}
        activeTicketCount={1}
        capacity={{
          max_concurrent_tickets: 0,
          max_same_strategy_side: 1,
          family_limits: { rally_failure_short: 1 },
          strategy_side_active_counts: {
            'MPG-001:long': 1,
            'CPM-RO-001:long': 0,
            'MI-001:short': 0,
          },
        }}
      />
    );
    expect(container.textContent).toContain('Policy v31');
    expect(container.textContent).not.toContain('Policy v28');
    expect(container.textContent).toContain('1 / 0 笔 (上限为 0，禁止新开仓)');
    expect(container.textContent).toContain('其余 2 个策略方向当前为 0 占用');
    expect(container.textContent).not.toContain('NaN%');
  });

  it('RecentOperations translates known states, marks unknown states as 状态待核实, and omits dead links', () => {
    render(
      <RecentOperations
        operations={[
          {
            authorization_id: 'op-1',
            name: '受控平仓',
            state: 'future_unknown_state',
            ticket_count: 1,
            updated_at_ms: 1700000000000,
            first_blocker: null,
          },
        ]}
      />
    );
    expect(container.textContent).toContain('状态待核实');
    expect(container.textContent).toContain('future_unknown_state');
    expect(container.textContent).not.toContain('执行中: future_unknown_state');
    expect(container.textContent).not.toContain('查看全部历史审计流水');
  });

  it('StrategyMatrix dynamically counts active/retired strategies, guards missing facts, and renders mobile cards', () => {
    const strategies: StrategyControlItem[] = [
      {
        strategy_group_id: 'MPG-001',
        name_zh: '多周期共振',
        timeframe: '4h',
        configured_state: 'enabled',
        effective_state: 'enabled',
        control_version: 4,
        reason_label: '正常启用',
        admission_health: { status: 'blocked', summary: '容量已满，暂不可开新仓' },
        active_tickets: [],
        active_ticket_count: 0,
        is_retired: false,
      } as StrategyControlItem,
      {
        strategy_group_id: 'MI-001',
        name_zh: '动量突破',
        timeframe: '1h',
        configured_state: 'unknown' as StrategyControlItem['configured_state'],
        effective_state: 'unknown' as StrategyControlItem['effective_state'],
        control_version: undefined as unknown as number,
        reason_label: '缺失',
        admission_health: { status: 'unknown', summary: '控制事实不可用' },
        active_tickets: [],
        active_ticket_count: 0,
        is_retired: false,
      } as StrategyControlItem,
      {
        strategy_group_id: 'SOR-001',
        name_zh: 'Crypto SOR',
        timeframe: '1h',
        configured_state: 'paused',
        effective_state: 'paused',
        control_version: 1,
        reason_label: '已退役',
        admission_health: { status: 'blocked', summary: '永久退役' },
        active_tickets: [],
        active_ticket_count: 0,
        is_retired: true,
      } as StrategyControlItem,
    ];

    const onSelectTicket = vi.fn();
    strategies[0].active_tickets = [
      { ticket_id: 'ticket:btc-1', symbol: 'BTCUSDT', side: 'long', pnl_r: '+0.92 R' },
    ];
    strategies[0].active_ticket_count = 1;

    render(<StrategyMatrix strategies={strategies} onSelectTicket={onSelectTicket} />);
    expect(container.textContent).toContain('2 个在役策略 · 1 个退役归档');
    expect(container.textContent).not.toContain('5 个在役策略');
    expect(container.textContent).toContain('控制事实不可用');
    expect(container.textContent).toContain('已退役 (禁止恢复)');
    const mobileList = container.querySelector('[data-testid="strategy-matrix-mobile"]');
    expect(mobileList).toBeTruthy();
    expect(mobileList?.textContent).toContain('配置: 未知');
    const mobileTicketBtn = mobileList?.querySelector<HTMLButtonElement>('button[data-ticket-id="ticket:btc-1"]');
    expect(mobileTicketBtn).toBeTruthy();
    act(() => mobileTicketBtn!.click());
    expect(onSelectTicket).toHaveBeenCalledWith('ticket:btc-1');
  });

  it('TopStatusBar renders explicit 未知 count without subtracting unknown from total', () => {
    render(
      <TopStatusBar
        globalEntry={{
          configured_state: 'enabled',
          effective_state: 'enabled',
          policy_version: 31,
          active_ticket_count: 1,
          updated_at_ms: 1700000000000,
        }}
        enabledStrategyCount={2}
        pausedStrategyCount={1}
        unknownStrategyCount={1}
        totalActiveStrategies={4}
        onRequestAction={vi.fn()}
      />
    );
    expect(container.textContent).toContain('2 已启用 / 1 已暂停 / 1 未知');
  });

  it('translates all formal ControlOperationState enum values and identifies ticket_not_flattenable:*:manual_open', () => {
    const formalStates = [
      ['validating', '校验中'],
      ['pending', '待执行'],
      ['claimed', '已认领'],
      ['exits_requested', '已发出平仓指令'],
      ['exit_in_progress', '平仓执行中'],
      ['reconciliation_pending', '待对账确认'],
      ['settlement_pending', '待结算确认'],
      ['review_pending', '待复盘确认'],
      ['completed', '已完成'],
      ['blocked', '已阻断'],
      ['needs_intervention', '需人工介入'],
    ] as const;
    for (const [raw, expected] of formalStates) {
      const res = formatControlOperationState(raw);
      expect(res.label).toBe(expected);
      expect(res.isUnknown).toBe(false);
    }
    expect(formatControlOperationState('unknown_future').label).toBe('状态待核实');

    render(
      <ControlledFlattenModal
        open
        onClose={vi.fn()}
        preview={{
          owner_policy_version: 29,
          snapshot_digest: 'sha256:test',
          ticket_ids: ['ticket:manual-1'],
          ticket_states: { 'ticket:manual-1': 'blocked' },
          first_blocker: 'ticket_not_flattenable:ticket:manual-1:manual_open',
        } as never}
        isSubmitting={false}
        isVerifying={false}
        errorMessage={null}
        isUnknownResult={false}
        onConfirm={vi.fn()}
        onVerifyStatus={vi.fn()}
      />
    );
    const modal = document.body.querySelector('[data-testid="controlled-flatten-modal"]');
    expect(modal?.textContent).toContain('人工接管（MANUAL）持仓');
    expect(modal?.textContent).toContain('ticket_not_flattenable:ticket:manual-1:manual_open');
  });
});
