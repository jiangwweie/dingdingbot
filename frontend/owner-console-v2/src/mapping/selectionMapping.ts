import type { SelectionDiagnosticData, GenericUniverseMember } from '../types/controls.ts';
import type { GenericSelectionPreview, OrbSelectionPreview } from '../api/controlsApi.ts';
import { cleanSymbol } from '../utils/symbol.ts';

export function mapPreviewToDiagnostic(
  strategyGroupId: string,
  preview: GenericSelectionPreview | OrbSelectionPreview | undefined,
  nowMs: number = Date.now()
): SelectionDiagnosticData | null {
  if (!preview) return null;
  const isOrb = strategyGroupId === 'SOR-1H-001' || 'strategy_label' in preview;

  if (isOrb) {
    const orb = preview as OrbSelectionPreview;
    const runtime = orb.runtime;
    const control = orb.control;

    if (!runtime) {
      return {
        kind: 'orb',
        strategy_group_id: strategyGroupId,
        installed: orb.installed ?? false,
        cadence_hours: 24,
        selection_mode: (control?.selection_mode as any) ?? 'dynamic_selection',
        pending_selection_mode: (control?.pending_selection_mode as any) ?? null,
        pending_effective_period_anchor_ms: control?.pending_effective_period_anchor_ms ?? null,
        rollback_baseline_id: control?.rollback_baseline_id ?? null,
        selection_epoch_id: control?.selection_epoch_id ?? null,
        control_version: control?.control_version ?? 1,
        authority_status_zh: '权威缺失 / 尚未生效',
        authority_outcome: null,
        authority_id: null,
        authority_effective_from_ms: null,
        authority_expires_at_ms: null,
        first_eligible_close_time_ms: null,
        snapshot_expires_at_ms: null,
        snapshot_cutoff_at_ms: null,
        snapshot_decision_at_ms: null,
        snapshot_created_at_ms: null,
        candidate_count: 24,
        ready_count: 0,
        selected_count: 0,
        selected_members: [],
        materialization_state: '未提供',
        vacuum_state: '未提供',
        vacuum_is_blocking: false,
      };
    }

    const snapshotDisp = runtime.snapshot_disposition;
    const snapshot = snapshotDisp?.snapshot;
    const selectedMembers = snapshotDisp?.selected_members ?? [];
    const candidateCount = snapshot?.candidate_count ?? 24;
    const selectedCount = snapshot?.selected_count ?? selectedMembers.length;
    const readyCount = snapshot?.ready_count ?? candidateCount;

    // Authority evaluation - strictly no default ACTIVE_NEW
    const currAuth = runtime.current_authority;
    const authority = currAuth?.authority as Record<string, any> | undefined;
    const authorityOutcome = authority?.authority_outcome ? String(authority.authority_outcome) : null;
    const authorityId = authority?.selection_authority_id ? String(authority.selection_authority_id) : null;
    const authEffectiveFromMs = typeof authority?.effective_from_ms === 'number' ? authority.effective_from_ms : null;
    const authExpiresAtMs = typeof authority?.expires_at_ms === 'number' ? authority.expires_at_ms : null;
    const firstEligibleCloseTimeMs = runtime.first_eligible_close_time_ms ?? (typeof authority?.first_eligible_close_time_ms === 'number' ? authority.first_eligible_close_time_ms : null);

    let authorityStatusZh = '权威缺失 / 未生效';
    if (authority) {
      if (authExpiresAtMs && nowMs >= authExpiresAtMs) {
        authorityStatusZh = `权威已过期 (${authorityOutcome ?? 'EXPIRED'})`;
      } else if (authEffectiveFromMs && nowMs < authEffectiveFromMs) {
        authorityStatusZh = `权威未生效 (${authorityOutcome ?? 'PENDING'})`;
      } else if (authorityOutcome === 'VALID_EMPTY') {
        authorityStatusZh = '权威生效 · 空集合入围 (VALID_EMPTY)';
      } else if (authorityOutcome) {
        authorityStatusZh = `权威有效 · ${authorityOutcome}`;
      } else {
        authorityStatusZh = '权威已授权';
      }
    }

    // Materialization Generation state - reads real lifecycle_state
    const matGen = runtime.materialization_generation as Record<string, any> | null | undefined;
    const materializationState = matGen?.lifecycle_state ? String(matGen.lifecycle_state) : '无活动物化';

    // Vacuum evaluation - check actual blocking vs resolved
    const vacuums = runtime.entry_vacuums ?? [];
    const blockingVacuum = vacuums.find(
      (v) =>
        v.resolved_at_ms === null &&
        !['RESOLVED_ACTIVE', 'RESOLVED_FALLBACK', 'RESOLVED_CONTINUITY', 'VALID_EMPTY'].includes(v.state)
    );
    let vacuumState = '无隔离 (Clear)';
    let vacuumIsBlocking = false;
    if (blockingVacuum) {
      vacuumIsBlocking = true;
      vacuumState = `隔离中 · ${blockingVacuum.state}${blockingVacuum.first_blocker ? ` (${blockingVacuum.first_blocker})` : ''}`;
    } else if (vacuums.length > 0) {
      vacuumState = `已解除隔离 (${vacuums[0].state})`;
    }

    return {
      kind: 'orb',
      strategy_group_id: strategyGroupId,
      installed: orb.installed ?? true,
      cadence_hours: 24, // SOR-1H ORB 日选币周期 24h
      selection_mode: (control?.selection_mode as any) ?? 'dynamic_selection',
      pending_selection_mode: (control?.pending_selection_mode as any) ?? null,
      pending_effective_period_anchor_ms: control?.pending_effective_period_anchor_ms ?? null,
      rollback_baseline_id: control?.rollback_baseline_id ?? null,
      selection_epoch_id: control?.selection_epoch_id ?? null,
      control_version: control?.control_version ?? 1,
      authority_status_zh: authorityStatusZh,
      authority_outcome: authorityOutcome,
      authority_id: authorityId,
      authority_effective_from_ms: authEffectiveFromMs,
      authority_expires_at_ms: authExpiresAtMs,
      first_eligible_close_time_ms: firstEligibleCloseTimeMs,
      snapshot_expires_at_ms: snapshot?.expires_at_ms ?? null,
      snapshot_cutoff_at_ms: snapshot?.feature_cutoff_at_ms ?? null,
      snapshot_decision_at_ms: snapshot?.decision_at_ms ?? null,
      snapshot_created_at_ms: snapshot?.created_at_ms ?? null,
      candidate_count: candidateCount,
      ready_count: readyCount,
      selected_count: selectedCount,
      selected_members: selectedMembers,
      materialization_state: materializationState,
      vacuum_state: vacuumState,
      vacuum_is_blocking: vacuumIsBlocking,
    };
  }

  // Generic Selection (CPM-RO-001, BRF2-001, MI-001, MPG-001)
  const generic = preview as GenericSelectionPreview;
  const runtime = generic.runtime;
  const control = generic.control;

  const members: GenericUniverseMember[] = (runtime.members ?? []).map((m) => ({
    facts: {
      exchange_instrument_id: cleanSymbol(m.facts.exchange_instrument_id),
      runtime_scope_id: m.facts.runtime_scope_id,
      policy_enabled: m.facts.policy_enabled,
      scope_entry_enabled: m.facts.scope_entry_enabled,
      entry_submit_enabled: m.facts.entry_submit_enabled,
      warm_valid_until_ms: m.facts.warm_valid_until_ms,
      policy_version: m.facts.policy_version,
    },
    first_blocker: m.first_blocker ?? null,
  }));

  const cadenceHours = generic.cadence_hours ?? 4;
  const currentOutcome = runtime.current_authority_outcome ?? null;
  const currentBlocker = runtime.first_blocker ?? null;

  let authorityStatusZh = '权威未生效 / 缺失';
  if (currentBlocker) {
    authorityStatusZh = `准入阻断 · ${currentBlocker}`;
  } else if (currentOutcome) {
    authorityStatusZh = `权威有效 · ${currentOutcome}`;
  } else if (runtime.installed) {
    authorityStatusZh = '权威有效 · 承接上一周期连续性';
  }

  const latestReadyCount = runtime.latest_ready_count ?? members.length;
  const latestSelectedCount = runtime.latest_selected_count ?? members.filter((m) => m.first_blocker === null).length;

  return {
    kind: 'generic',
    strategy_group_id: strategyGroupId,
    installed: runtime.installed ?? true,
    cadence_hours: cadenceHours,
    selection_mode: (control?.selection_mode as any) ?? 'dynamic_selection',
    pending_selection_mode: (control?.pending_selection_mode as any) ?? null,
    pending_effective_period_anchor_ms: control?.pending_effective_period_anchor_ms ?? null,
    rollback_baseline_id: control?.rollback_baseline_id ?? null,
    selection_epoch_id: control?.selection_epoch_id ?? null,
    control_version: control?.control_version ?? 1,
    current_authority_id: runtime.current_authority_id ?? null,
    current_authority_outcome: currentOutcome,
    authority_status_zh: authorityStatusZh,
    first_blocker: currentBlocker,
    membership_valid_until_ms: runtime.membership_valid_until_ms ?? null,
    consecutive_missed_periods: runtime.consecutive_missed_periods ?? null,
    latest_ready_count: latestReadyCount,
    latest_selected_count: latestSelectedCount,
    materialization_generation_id: runtime.materialization_generation_id ?? null,
    materialization_state: runtime.materialization_state ?? '无活动物化',
    materialization_deadline_ms: runtime.materialization_deadline_ms ?? null,
    vacuum_state: runtime.vacuum_state ?? 'clear',
    vacuum_fenced_at_ms: runtime.vacuum_fenced_at_ms ?? null,
    latest_successful_completion_age_ms: runtime.latest_successful_completion_age_ms ?? null,
    latest_successful_cutoff_age_ms: runtime.latest_successful_cutoff_age_ms ?? null,
    membership_source_age_ms: runtime.membership_source_age_ms ?? null,
    members,
  };
}
