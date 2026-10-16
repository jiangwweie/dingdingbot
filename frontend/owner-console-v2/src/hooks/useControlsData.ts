import { useQuery } from '@tanstack/react-query';
import { fetchControls, controlsQueryKey, type ControlsResponse } from '../api/controlsApi';
import type {
  GlobalEntryState,
  StrategyControlItem,
  AccountCapacityData,
  RecentOperationItem,
  SelectionDiagnosticData,
} from '../types/controls';
import {
  initialGlobalEntry,
  initialStrategies,
  mockAccountCapacity,
  mockRecentOperations,
  mockSelectionMap,
} from '../mock/controlsData';

// Strategy display dictionary
const STRATEGY_META: Record<string, { name_zh: string; timeframe: string; is_retired?: boolean }> = {
  'CPM-RO-001': { name_zh: '均线回踩做多', timeframe: '1h close' },
  'BRF2-001': { name_zh: '假反弹衰竭做空', timeframe: '1h close' },
  'MI-001': { name_zh: '相对强弱冲量', timeframe: '1h close' },
  'MPG-001': { name_zh: '趋势动量持续', timeframe: '1h close' },
  'SOR-1H-001': { name_zh: '单边突破 (1h/15m)', timeframe: '1h close' },
  'SOR-001': { name_zh: '旧单边突破策略', timeframe: '已停用', is_retired: true },
};

function formatReasonLabel(reason: string): string {
  if (!reason) return '系统默认状态';
  if (reason.includes('initialize') || reason.includes('init')) return '系统初始化启用';
  if (reason.includes('manual') || reason.includes('resume')) return 'Owner 手动恢复';
  if (reason.includes('pause')) return 'Owner 手动暂停';
  if (reason.includes('retire')) return 'Owner 永久退役';
  return reason;
}

export function useControlsData() {
  const query = useQuery({
    queryKey: controlsQueryKey,
    queryFn: fetchControls,
    retry: false,
    staleTime: 10_000,
  });

  const isRealData = query.isSuccess && !!query.data;
  const raw: ControlsResponse | undefined = query.data;

  // 1. Map Global Entry
  const globalEntry: GlobalEntryState = isRealData && raw
    ? {
        configured_state: raw.global_entry.configured_state,
        effective_state: raw.global_entry.effective_state,
        policy_version: raw.global_entry.policy_version,
        active_ticket_count: raw.global_entry.active_ticket_count,
        first_blocker: raw.global_entry.first_blocker ?? null,
      }
    : initialGlobalEntry;

  // 2. Map Strategies
  const strategies: StrategyControlItem[] = isRealData && raw
    ? raw.strategies.map((s) => {
        const meta = STRATEGY_META[s.strategy_group_id] ?? {
          name_zh: s.strategy_group_id,
          timeframe: '1h close',
        };
        const isRetired = meta.is_retired || s.strategy_group_id === 'SOR-001';
        const isGlobalPaused = raw.global_entry.configured_state === 'paused';
        const isCapacityFull = raw.account_capacity.remaining_ticket_slots <= 0;

        let admissionStatus: 'cleared' | 'blocked' = 'cleared';
        let admissionSummary = '准入畅通 · 观察 Worker 运行正常';

        if (isRetired) {
          admissionStatus = 'blocked';
          admissionSummary = '已永久退役 · 仅留存审计，禁止恢复';
        } else if (isGlobalPaused) {
          admissionStatus = 'blocked';
          admissionSummary = '受限挂起 · 全局 ENTRY 已由 Owner 暂停';
        } else if (isCapacityFull) {
          admissionStatus = 'blocked';
          admissionSummary = `准入阻断 · 全局总容量已达上限 (${raw.account_capacity.active_ticket_count}/${raw.account_capacity.max_concurrent_tickets})`;
        } else if (s.configured_state === 'paused') {
          admissionStatus = 'blocked';
          admissionSummary = '策略已暂停 · 仅继续存量生命周期保护';
        }

        return {
          strategy_group_id: s.strategy_group_id,
          name_zh: meta.name_zh,
          timeframe: meta.timeframe,
          configured_state: s.configured_state,
          effective_state: s.effective_state,
          control_version: s.control_version,
          updated_at_ms: s.updated_at_ms,
          reason_label: formatReasonLabel(s.reason),
          is_retired: isRetired,
          admission_health: {
            status: admissionStatus,
            summary: admissionSummary,
            source: 'server_admission_fact',
          },
          active_tickets: [],
        };
      })
    : initialStrategies;

  // 3. Map Capacity
  const capacity: AccountCapacityData = isRealData && raw
    ? {
        max_concurrent_tickets: raw.account_capacity.max_concurrent_tickets,
        active_ticket_count: raw.account_capacity.active_ticket_count,
        remaining_ticket_slots: raw.account_capacity.remaining_ticket_slots,
        max_same_strategy_side: raw.account_capacity.max_same_strategy_side ?? 2,
        gross_stop_risk: raw.account_capacity.gross_stop_risk ?? '0',
        gross_stop_risk_limit: raw.account_capacity.gross_stop_risk_limit ?? null,
        max_gross_stop_risk_fraction: raw.account_capacity.max_gross_stop_risk_fraction ?? '0.03',
        long_stop_risk: raw.account_capacity.long_stop_risk ?? '0',
        short_stop_risk: raw.account_capacity.short_stop_risk ?? '0',
        directional_stop_risk_limit: raw.account_capacity.directional_stop_risk_limit ?? null,
        directional_stop_risk_limit_fraction: raw.account_capacity.directional_stop_risk_limit_fraction ?? '0.02',
        reserved_margin: raw.account_capacity.reserved_margin ?? '0',
        gross_initial_margin_limit: raw.account_capacity.gross_initial_margin_limit ?? null,
        max_gross_initial_margin_utilization: raw.account_capacity.max_gross_initial_margin_utilization ?? '0.25',
        wallet_balance_basis: raw.account_capacity.wallet_balance_basis ?? null,
        margin_balance_basis: raw.account_capacity.margin_balance_basis ?? null,
        family_active_counts: raw.account_capacity.family_active_counts ?? {},
        family_limits: {
          long_continuation: raw.account_capacity.family_limits?.long_continuation ?? 2,
          rally_failure_short: raw.account_capacity.family_limits?.rally_failure_short ?? 1,
          ...raw.account_capacity.family_limits,
        },
        strategy_side_active_counts: (raw.account_capacity as any).strategy_side_active_counts ?? {},
        source: raw.account_capacity.source ?? 'current_projection',
      }
    : mockAccountCapacity;

  // 4. Map Operations
  const operations: RecentOperationItem[] = isRealData && raw
    ? raw.recent_operations.map((op) => ({
        authorization_id: op.authorization_id,
        name: '受控平仓全部仓位',
        ticket_count: 3,
        updated_at_ms: op.created_at_ms,
        created_at_ms: op.created_at_ms,
        state: op.state,
        result_label: op.state === 'completed' ? (op.first_blocker ? '曾需关注，现已完成' : '已完成') : op.state,
        first_blocker: op.first_blocker ?? null,
      }))
    : mockRecentOperations;

  // 5. Selection Map
  const selectionMap: Record<string, SelectionDiagnosticData> = mockSelectionMap;

  return {
    isRealData,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    generatedAtMs: raw?.generated_at_ms ?? Date.now(),
    refetch: query.refetch,
    // Data objects
    globalEntry,
    strategies,
    capacity,
    operations,
    selectionMap,
  };
}
