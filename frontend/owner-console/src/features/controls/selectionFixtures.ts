import type { SelectionPreview } from "./api";

/** Display-only test fixture; never used as runtime authority. */
export const selectionFixture: SelectionPreview = {
  control: { strategy_group_id: "CPM-RO-001", selection_spec_id: "CPM_ABSOLUTE_DIRECTIONAL_EFFICIENCY_V1",
    selection_mode: "static_baseline", pending_selection_mode: null, pending_effective_period_anchor_ms: null,
    pending_authorization_id: null, control_version: 7, rollback_baseline_id: "baseline", selection_epoch_id: null, updated_at_ms: 100 },
  runtime: { strategy_group_id: "CPM-RO-001", selection_spec_id: "CPM_ABSOLUTE_DIRECTIONAL_EFFICIENCY_V1", installed: true,
    selection_mode: "static_baseline", latest_successful_snapshot_id: null, latest_successful_cutoff_at_ms: null,
    latest_successful_committed_at_ms: null, latest_successful_completion_age_ms: null, latest_successful_selection_age_ms: null,
    latest_successful_cutoff_age_ms: null, membership_source_snapshot_id: null, membership_source_cutoff_at_ms: null,
    membership_source_age_ms: null, current_authority_id: null, current_authority_outcome: null,
    membership_valid_until_ms: null, consecutive_missed_periods: null, latest_ready_count: null, latest_selected_count: null,
    valid_empty_reason: null, materialization_generation_id: null, materialization_state: null, materialization_deadline_ms: null,
    vacuum_state: null, vacuum_fenced_at_ms: null, members: [], first_blocker: null, observed_at_ms: 100 },
  cadence_hours: 4, next_effective_period_anchor_ms: 360000000, next_eligibility_not_before_ms: 363600000,
};
