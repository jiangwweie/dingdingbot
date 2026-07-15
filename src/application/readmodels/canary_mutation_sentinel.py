"""Versioned bounded database mutation sentinel for deployment canaries."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator


@dataclass(frozen=True)
class CanarySentinelSpec:
    slice_id: str
    relation: str
    row_limit: int
    columns: tuple[str, ...]


CANARY_FACT_COLUMNS_V1 = (
    "fact_snapshot_id", "strategy_group_id", "symbol", "side",
    "runtime_profile_id", "fact_surface", "source_kind", "source_ref",
    "computed", "satisfied", "freshness_state", "failed_facts",
    "fact_values", "blocker_class", "observed_at_ms", "valid_until_ms",
    "created_at_ms", "action_time_invocation_id",
)
CANARY_SIGNAL_COLUMNS_V1 = (
    "signal_event_id", "candidate_scope_id", "event_spec_id",
    "strategy_group_id", "symbol", "side", "detector_key", "signal_type",
    "source_kind", "status", "freshness_state", "confidence",
    "fact_snapshot_id", "reason_codes", "signal_payload", "event_time_ms",
    "trigger_candle_close_time_ms", "observed_at_ms", "expires_at_ms",
    "invalidated_at_ms", "created_at_ms", "candidate_scope_event_binding_id",
    "runtime_scope_binding_id", "runtime_instance_id", "runtime_profile_id",
    "policy_current_id", "strategy_group_version_id", "asset_class",
    "event_spec_version", "event_id", "timeframe", "time_authority",
    "lane_identity_key", "source_watermark", "signal_grade",
    "required_execution_mode", "execution_eligible", "authority_source_ref",
)
CANARY_PROCESS_OUTCOME_COLUMNS_V1 = (
    "process_outcome_id", "process_name", "scope_key", "run_id",
    "process_state", "business_state", "first_blocker", "started_at_ms",
    "completed_at_ms", "runtime_head", "source_watermark",
    "projector_owner", "updated_at_ms", "scope_kind", "candidate_scope_id",
    "candidate_scope_event_binding_id", "runtime_scope_binding_id",
    "runtime_instance_id", "runtime_profile_id", "policy_current_id",
    "strategy_group_id", "strategy_group_version_id", "symbol", "asset_class",
    "side", "event_spec_id", "event_spec_version", "event_id", "timeframe",
    "time_authority", "lane_identity_key", "legacy_evidence",
    "action_time_invocation_id",
)
CANARY_LANE_COLUMNS_V1 = (
    "action_time_lane_input_id", "promotion_candidate_id", "strategy_group_id",
    "symbol", "side", "runtime_profile_id", "lane_scope", "status",
    "signal_event_id", "public_fact_snapshot_id", "action_time_fact_snapshot_id",
    "runtime_scope_binding_id", "candidate_authorization_ref",
    "runtime_safety_snapshot_id", "first_blocker_class", "created_at_ms",
    "expires_at_ms", "closed_at_ms", "authority_boundary", "signal_grade",
    "required_execution_mode", "execution_eligible", "authority_source_ref",
    "lane_identity_key", "source_watermark", "action_time_invocation_id",
    "account_safe_fact_snapshot_id", "account_mode_fact_snapshot_id",
)
CANARY_TICKET_COLUMNS_V1 = (
    "ticket_id", "action_time_lane_input_id", "promotion_candidate_id",
    "signal_event_id", "event_spec_id", "event_spec_version_id",
    "candidate_scope_id", "runtime_scope_binding_id", "strategy_group_id",
    "strategy_group_version_id", "symbol", "exchange_instrument_id", "side",
    "event_id", "event_time_ms", "trigger_candle_close_time_ms",
    "runtime_profile_id", "public_fact_snapshot_id",
    "action_time_fact_snapshot_id", "account_safe_fact_snapshot_id",
    "account_mode_snapshot_id", "budget_reservation_id", "protection_ref_id",
    "execution_policy_id", "execution_policy_version", "owner_policy_version",
    "sizing_policy_version", "protection_policy_version", "target_notional",
    "leverage", "expires_at_ms", "status", "authority_boundary", "ticket_hash",
    "created_under_versions_hash", "created_at_ms", "signal_grade",
    "required_execution_mode", "execution_eligible", "authority_source_ref",
    "effective_notional", "selected_leverage", "planned_stop_risk_budget",
    "planned_stop_risk", "lane_identity_key", "source_watermark",
    "action_time_invocation_id", "exit_policy_id", "exit_policy_version",
    "exit_policy_snapshot", "exit_policy_hash",
)
CANARY_PROTECTED_ATTEMPT_COLUMNS_V1 = (
    "protected_submit_attempt_id", "ticket_id", "finalgate_pass_id",
    "operation_layer_handoff_id", "operation_submit_command_id",
    "runtime_safety_snapshot_id", "action_time_lane_input_id",
    "strategy_group_id", "symbol", "side", "runtime_profile_id",
    "submit_mode_decision_id", "submit_mode", "status", "submit_allowed",
    "blockers", "warnings", "trusted_fact_refs", "submit_request",
    "submit_result", "identity_evidence", "official_operation_layer_submit_called",
    "exchange_write_called", "order_created", "order_lifecycle_called",
    "withdrawal_or_transfer_created", "live_profile_changed",
    "order_sizing_changed", "authority_boundary", "created_at_ms",
    "updated_at_ms", "signal_grade", "required_execution_mode",
    "execution_eligible", "authority_source_ref",
)
CANARY_EXCHANGE_COMMAND_COLUMNS_V1 = (
    "exchange_command_id", "protected_submit_attempt_id", "ticket_id",
    "operation_submit_command_id", "account_id", "strategy_group_id",
    "runtime_profile_id", "exchange_instrument_id", "gateway_symbol", "symbol",
    "order_role", "side", "gateway_side", "local_order_id", "parent_order_id",
    "client_order_id", "command_generation", "request_fingerprint", "order_type",
    "amount", "price", "stop_price", "reduce_only", "authority_source_ref",
    "command_state", "outcome_class", "exchange_order_id", "exchange_error_code",
    "exchange_error_message", "prepared_at_ms", "dispatch_started_at_ms",
    "resolved_at_ms", "updated_at_ms", "exchange_id", "position_mode",
    "position_side", "position_bucket", "netting_domain_key", "reduce_intent",
    "command_kind", "command_source", "source_command_id",
    "target_exchange_order_id", "claim_owner", "claim_token",
    "claim_started_at_ms", "claim_expires_at_ms", "execution_attempt_count",
    "last_reconciled_at_ms", "exchange_result", "desired_leverage",
    "execution_style", "time_in_force", "post_only", "market_fallback_allowed",
)
CANARY_LIFECYCLE_COLUMNS_V1 = (
    "lifecycle_run_id", "ticket_id", "protected_submit_attempt_id",
    "strategy_group_id", "symbol", "side", "runtime_profile_id", "status",
    "entry_local_order_id", "entry_exchange_order_id", "entry_fill_confirmed",
    "entry_filled_qty", "entry_avg_price", "exit_protection_set_id",
    "first_blocker", "blockers", "warnings", "authority_boundary",
    "created_at_ms", "updated_at_ms",
)
CANARY_PROTECTION_SET_COLUMNS_V1 = (
    "exit_protection_set_id", "ticket_id", "protected_submit_attempt_id",
    "entry_local_order_id", "entry_exchange_order_id", "strategy_group_id",
    "symbol", "side", "entry_filled_qty", "entry_avg_price", "status",
    "sl_order_id", "tp1_order_id", "runner_qty", "protection_complete",
    "reconciled_with_exchange", "first_blocker", "blockers", "warnings",
    "authority_boundary", "created_at_ms", "updated_at_ms",
)
CANARY_PROTECTION_ORDER_COLUMNS_V1 = (
    "exit_protection_order_id", "exit_protection_set_id", "ticket_id", "role",
    "local_order_id", "exchange_order_id", "status", "order_type", "side",
    "qty", "price", "trigger_price", "reduce_only",
    "replaces_exit_protection_order_id", "created_at_ms", "updated_at_ms",
    "generation",
)
CANARY_EXIT_POLICY_CURRENT_COLUMNS_V1 = (
    "ticket_id", "exit_protection_set_id", "exit_policy_id",
    "exit_policy_version", "exit_policy_hash", "exit_execution_snapshot",
    "exit_execution_hash", "actual_r_per_unit", "resolved_tp1_price",
    "resolved_tp1_target_qty", "tp1_cumulative_filled_qty",
    "tp1_completion_state", "remaining_position_qty", "state",
    "last_evaluated_watermark_ms", "next_evaluation_not_before_ms",
    "last_decision_kind", "last_reason_code", "active_runner_order_id",
    "active_runner_generation", "active_runner_stop", "runner_break_even_floor",
    "runner_floor_applied_at_ms", "pending_runner_order_id", "pending_generation",
    "replaced_runner_order_id", "first_blocker", "updated_at_ms",
)
CANARY_ACCOUNT_MODE_COLUMNS_V1 = (
    "account_mode_current_id", "account_id", "exchange_id", "runtime_profile_id",
    "position_mode", "dual_side_position", "position_mode_safe", "status",
    "fact_snapshot_id", "source_kind", "source_ref", "observed_at_ms",
    "valid_until_ms", "updated_at_ms",
)
CANARY_LIFECYCLE_CAPABILITY_COLUMNS_V1 = (
    "capability_id", "status", "certification_ref", "updated_at_ms",
    "proof_schema", "proof_payload",
)
CANARY_PRETRADE_COLUMNS_V1 = (
    "readiness_row_id", "candidate_scope_id", "strategy_group_id", "symbol",
    "side", "readiness_state", "detector_state", "watcher_state",
    "public_facts_state", "signal_lifecycle_status", "signal_freshness_state",
    "risk_state", "scope_state", "promotion_state", "first_blocker_class",
    "first_blocker_detail", "next_action", "stop_condition", "evidence_ref",
    "source_watermark", "valid_until_ms",
)
CANARY_GOAL_COLUMNS_V1 = (
    "goal_status_current_id", "status", "fresh_signal_present",
    "ready_for_real_order_action", "owner_action_required", "blockers",
    "input_watermark", "projection_run_id",
)
CANARY_SNAPSHOT_COLUMNS_V1 = (
    "snapshot_id", "model_type", "source_watermark", "owner_projector",
    "input_watermark", "output_path", "is_current", "generated_by",
    "semantic_payload",
)
CANARY_PROJECTION_RUN_COLUMNS_V1 = (
    "projection_run_id", "model_type", "owner_projector", "code_version",
    "source_mode", "projection_target", "input_watermark", "source_priority",
    "legacy_diagnostics_read", "legacy_diagnostics_affected_current", "status",
    "error_detail",
)


CANARY_SENTINEL_SPECS_V1 = (
    CanarySentinelSpec("facts", "brc_runtime_fact_snapshots", 128, CANARY_FACT_COLUMNS_V1),
    CanarySentinelSpec("signals", "brc_live_signal_events", 22, CANARY_SIGNAL_COLUMNS_V1),
    CanarySentinelSpec("process_current", "brc_runtime_process_outcomes", 111, CANARY_PROCESS_OUTCOME_COLUMNS_V1),
    CanarySentinelSpec("process_window", "brc_runtime_process_outcomes", 256, CANARY_PROCESS_OUTCOME_COLUMNS_V1),
    CanarySentinelSpec("lanes", "brc_action_time_lane_inputs", 22, CANARY_LANE_COLUMNS_V1),
    CanarySentinelSpec("tickets", "brc_action_time_tickets", 22, CANARY_TICKET_COLUMNS_V1),
    CanarySentinelSpec("protected_attempts", "brc_ticket_bound_protected_submit_attempts", 44, CANARY_PROTECTED_ATTEMPT_COLUMNS_V1),
    CanarySentinelSpec("exchange_commands", "brc_ticket_bound_exchange_commands", 88, CANARY_EXCHANGE_COMMAND_COLUMNS_V1),
    CanarySentinelSpec("lifecycles", "brc_ticket_bound_order_lifecycle_runs", 22, CANARY_LIFECYCLE_COLUMNS_V1),
    CanarySentinelSpec("protection_sets", "brc_ticket_bound_exit_protection_sets", 22, CANARY_PROTECTION_SET_COLUMNS_V1),
    CanarySentinelSpec("protection_orders", "brc_ticket_bound_exit_protection_orders", 88, CANARY_PROTECTION_ORDER_COLUMNS_V1),
    CanarySentinelSpec("exit_policy", "brc_ticket_exit_policy_current", 22, CANARY_EXIT_POLICY_CURRENT_COLUMNS_V1),
    CanarySentinelSpec("account_modes", "brc_exchange_account_modes_current", 22, CANARY_ACCOUNT_MODE_COLUMNS_V1),
    CanarySentinelSpec("lifecycle_capability", "brc_runtime_capabilities_current", 1, CANARY_LIFECYCLE_CAPABILITY_COLUMNS_V1),
    CanarySentinelSpec("pretrade", "brc_pretrade_readiness_rows", 22, CANARY_PRETRADE_COLUMNS_V1),
    CanarySentinelSpec("goal", "brc_goal_status_current", 1, CANARY_GOAL_COLUMNS_V1),
    CanarySentinelSpec("snapshots", "brc_control_read_model_snapshots", 3, CANARY_SNAPSHOT_COLUMNS_V1),
    CanarySentinelSpec("projection_runs", "brc_projection_runs", 3, CANARY_PROJECTION_RUN_COLUMNS_V1),
)
_SPEC_BY_ID = MappingProxyType({spec.slice_id: spec for spec in CANARY_SENTINEL_SPECS_V1})


class CanaryMutationSentinelProjection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_id: str = "brc.canary_mutation_sentinel.v1"
    canary_db_now_ms: int = Field(ge=0)
    canary_window_floor_ms: int = Field(ge=0)
    slices: dict[str, tuple[dict[str, Any], ...]]
    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @classmethod
    def freeze(
        cls,
        *,
        canary_db_now_ms: int,
        canary_window_floor_ms: int,
        slices: Mapping[str, Sequence[Mapping[str, Any]]],
        require_complete: bool = False,
    ) -> "CanaryMutationSentinelProjection":
        if canary_window_floor_ms > canary_db_now_ms:
            raise ValueError("canary_window_invalid")
        if require_complete and set(slices) != set(_SPEC_BY_ID):
            raise ValueError("canary_sentinel_slice_set_mismatch")
        normalized: dict[str, tuple[dict[str, Any], ...]] = {}
        for slice_id, raw_rows in slices.items():
            spec = _SPEC_BY_ID.get(slice_id)
            if spec is None:
                raise ValueError(f"canary_sentinel_unknown_slice:{slice_id}")
            if len(raw_rows) > spec.row_limit:
                raise ValueError(f"canary_sentinel_row_limit_exceeded:{slice_id}")
            rows: list[dict[str, Any]] = []
            for raw in raw_rows:
                row = dict(raw)
                if set(row) != set(spec.columns):
                    raise ValueError(f"canary_sentinel_schema_mismatch:{slice_id}")
                rows.append({name: row[name] for name in spec.columns})
            normalized[slice_id] = tuple(
                sorted(rows, key=lambda row: _canonical_bytes(row))
            )
        payload = {
            "schema_id": "brc.canary_mutation_sentinel.v1",
            "slices": normalized,
        }
        raw = _canonical_bytes(payload)
        if len(raw) > 16 * 1024 * 1024:
            raise ValueError("canary_sentinel_input_too_large")
        return cls(
            canary_db_now_ms=canary_db_now_ms,
            canary_window_floor_ms=canary_window_floor_ms,
            slices=normalized,
            digest="sha256:" + sha256(raw).hexdigest(),
        )


class CanaryMutationSentinelScopeV1(BaseModel):
    """Exact identifiers frozen before the first deployment canary."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_id: str = "brc.canary_mutation_sentinel_scope.v1"
    fact_snapshot_ids: tuple[str, ...] = Field(max_length=128)
    signal_event_ids: tuple[str, ...] = Field(max_length=22)
    lane_ids: tuple[str, ...] = Field(max_length=22)
    lane_identity_keys: tuple[str, ...] = Field(max_length=22)
    ticket_ids: tuple[str, ...] = Field(max_length=22)
    protected_attempt_ids: tuple[str, ...] = Field(max_length=44)
    lifecycle_ids: tuple[str, ...] = Field(max_length=22)
    protection_set_ids: tuple[str, ...] = Field(max_length=22)
    account_mode_ids: tuple[str, ...] = Field(max_length=22)
    readiness_keys: tuple[tuple[str, str, str], ...] = Field(max_length=22)
    snapshot_ids: tuple[str, ...] = Field(max_length=3)
    projection_run_ids: tuple[str, ...] = Field(max_length=3)
    release_activation_process_outcome_id: str = Field(min_length=1, max_length=220)

    @model_validator(mode="after")
    def validate_ordered_unique_scope(self) -> "CanaryMutationSentinelScopeV1":
        for name in (
            "fact_snapshot_ids", "signal_event_ids", "lane_ids",
            "lane_identity_keys", "ticket_ids", "protected_attempt_ids",
            "lifecycle_ids", "protection_set_ids", "account_mode_ids",
            "readiness_keys", "snapshot_ids", "projection_run_ids",
        ):
            values = tuple(getattr(self, name))
            if values != tuple(sorted(values)) or len(values) != len(set(values)):
                raise ValueError(f"canary_scope_not_ordered_unique:{name}")
        return self


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
