import type { StrategyAdmissionHealth } from '../types/controls.ts';

export interface AdmissionEvaluationContext {
  strategy?: {
    strategy_group_id: string;
    configured_state: 'enabled' | 'paused';
    effective_state: string;
    reason?: string;
  } | null;
  globalEntry?: {
    configured_state: 'enabled' | 'paused';
    effective_state: 'enabled' | 'paused';
    first_blocker?: string | null;
  } | null;
  runtimeAuthority?: {
    effective_status: 'ready' | 'fenced';
    exchange_commands_enabled: boolean;
    first_blocker?: string | null;
    authority_outcome?: string | null;
    expires_at_ms?: number | null;
  } | null;
  capacity?: {
    remaining_ticket_slots?: number | null;
    active_ticket_count?: number | null;
    max_concurrent_tickets?: number | null;
  } | null;
  selectionAuthority?: {
    isMissing?: boolean;
    isExpired?: boolean;
    authorityOutcome?: string | null;
    expiresAtMs?: number | null;
  } | null;
  workerHealth?: {
    isHealthy?: boolean;
    summary?: string;
  } | null;
  isRetired?: boolean;
  nowMs?: number;
}

export function evaluateStrategyAdmissionHealth(ctx: AdmissionEvaluationContext): StrategyAdmissionHealth {
  // 1. Evidence missing
  if (!ctx || !ctx.strategy) {
    return {
      status: 'unknown',
      summary: '证据缺失 · 准入事实不可用',
      source: 'unknown_fact',
    };
  }

  const { strategy, globalEntry, runtimeAuthority, capacity, selectionAuthority, workerHealth, isRetired, nowMs = Date.now() } = ctx;

  // 2. Retired Strategy
  if (isRetired || strategy.strategy_group_id === 'SOR-001') {
    return {
      status: 'blocked',
      summary: '已永久退役 · 仅留存审计，禁止恢复',
      source: 'server_admission_fact',
    };
  }

  // 3. Strategy Configured Paused
  if (strategy.configured_state === 'paused') {
    return {
      status: 'blocked',
      summary: '策略已暂停 · 仅继续存量生命周期保护',
      source: 'server_admission_fact',
    };
  }

  // 4. Configured Enabled but Effective Blocked / Paused by Global
  if (strategy.effective_state === 'paused_by_global') {
    return {
      status: 'blocked',
      summary: '受限挂起 · 全局 ENTRY 已由 Owner 暂停',
      source: 'server_admission_fact',
    };
  }
  if (strategy.effective_state === 'paused') {
    return {
      status: 'blocked',
      summary: '准入阻断 · 策略实际状态处于暂停 (effective: paused)',
      source: 'server_admission_fact',
    };
  }
  if (strategy.effective_state !== 'enabled') {
    return {
      status: 'blocked',
      summary: `准入阻断 · 策略实际生效状态: ${strategy.effective_state}`,
      source: 'server_admission_fact',
    };
  }

  // 5. Global Entry Blocked or Paused
  if (globalEntry) {
    if (globalEntry.configured_state === 'paused') {
      return {
        status: 'blocked',
        summary: '受限挂起 · 全局 ENTRY 已由 Owner 暂停',
        source: 'server_admission_fact',
      };
    }
    if (globalEntry.effective_state === 'paused') {
      return {
        status: 'blocked',
        summary: `准入阻断 · 全局实际生效为暂停${globalEntry.first_blocker ? ` (${globalEntry.first_blocker})` : ''}`,
        source: 'server_admission_fact',
      };
    }
    if (globalEntry.first_blocker) {
      return {
        status: 'blocked',
        summary: `准入阻断 · 全局门禁: ${globalEntry.first_blocker}`,
        source: 'server_admission_fact',
      };
    }
  }

  // 6. Global Capacity Limit Reached
  if (capacity && typeof capacity.remaining_ticket_slots === 'number' && capacity.remaining_ticket_slots <= 0) {
    const act = capacity.active_ticket_count ?? '—';
    const max = capacity.max_concurrent_tickets ?? '—';
    return {
      status: 'blocked',
      summary: `准入阻断 · 全局总容量已达上限 (${act}/${max})`,
      source: 'server_admission_fact',
    };
  }

  // 7. Runtime Entry Authority Blocked / Missing / Expired
  if (!runtimeAuthority) {
    return {
      status: 'unknown',
      summary: '权威缺失 · 运行时准入凭据不可用',
      source: 'unknown_fact',
    };
  }
  if (runtimeAuthority.effective_status === 'fenced') {
    return {
      status: 'blocked',
      summary: `权威阻断 · 运行时围栏已建立${runtimeAuthority.first_blocker ? ` (${runtimeAuthority.first_blocker})` : ''}`,
      source: 'server_admission_fact',
    };
  }
  if (runtimeAuthority.exchange_commands_enabled === false) {
    return {
      status: 'blocked',
      summary: '权威阻断 · 交易指令通道已关闭 (exchange_commands_disabled)',
      source: 'server_admission_fact',
    };
  }
  if (runtimeAuthority.first_blocker) {
    return {
      status: 'blocked',
      summary: `权威阻断 · ${runtimeAuthority.first_blocker}`,
      source: 'server_admission_fact',
    };
  }
  if (runtimeAuthority.expires_at_ms && nowMs >= runtimeAuthority.expires_at_ms) {
    return {
      status: 'blocked',
      summary: '权威失效 · 运行时准入凭据已过期',
      source: 'server_admission_fact',
    };
  }

  // 8. Strategy Selection Authority (Missing or Expired)
  if (selectionAuthority) {
    if (selectionAuthority.isMissing) {
      return {
        status: 'blocked',
        summary: '权威缺失 · 策略选币授权不存在',
        source: 'server_admission_fact',
      };
    }
    if (selectionAuthority.isExpired || (selectionAuthority.expiresAtMs && nowMs >= selectionAuthority.expiresAtMs)) {
      return {
        status: 'blocked',
        summary: '权威失效 · 策略选币授权已过期',
        source: 'server_admission_fact',
      };
    }
  }

  // 9. Worker Health Check:
  // If Worker health fact is verified and healthy:
  if (workerHealth?.isHealthy === true) {
    return {
      status: 'cleared',
      summary: `准入畅通 · 全链路证据充分${workerHealth.summary ? ` (${workerHealth.summary})` : ''}`,
      source: 'server_admission_fact',
    };
  }

  // 10. Default when controls are enabled, no blockers, but Worker health is NOT verified:
  // Must NOT display "观察 Worker 运行正常", and must NOT claim to be cleared without full evidence.
  // Marked client_derived.
  return {
    status: 'unknown',
    summary: '控制已启用 · 实际准入状态待核实',
    source: 'client_derived',
  };
}
