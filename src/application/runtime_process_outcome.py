"""Typed PG process outcome semantics independent from trading opportunity."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal
from hashlib import sha256

from pydantic import BaseModel, ConfigDict
import sqlalchemy as sa

from src.domain.runtime_lane_identity import RuntimeLaneIdentity
from src.domain.runtime_semantic_kernel import (
    RuntimeSemanticState,
    semantic_state_for_process_outcome,
)


class RuntimeProcessOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    process_name: str
    process_state: Literal[
        "succeeded",
        "noop",
        "business_blocked",
        "retryable_failure",
        "hard_failure",
    ]
    business_state: Literal[
        "running",
        "waiting_for_opportunity",
        "processing",
        "temporarily_unavailable",
        "needs_intervention",
        "paused",
        "completed",
    ]
    first_blocker: str = ""

    @property
    def semantic_state(self) -> RuntimeSemanticState:
        """Shared state semantics for current projection consumers.

        This keeps process outcomes from maintaining another implicit notion of
        terminal/current relevance while aggregate-specific lifecycle state
        remains owned by the lifecycle reducer.
        """

        return semantic_state_for_process_outcome(
            process_state=self.process_state,
            reason_code=self.first_blocker,
        )


PROCESS_SUCCESS_STATES = {"succeeded", "noop", "business_blocked"}
PROCESS_FAILURE_STATES = {"retryable_failure", "hard_failure"}
RUNTIME_LANE_PROCESS_NAMES = {
    "live_signal_materialization",
    "action_time_fact_snapshots",
    "promotion_action_time_lane",
    "action_time_ticket_sequence",
    "action_time_capability_certification",
    "action_time_signal_arbitration",
}


def runtime_process_exit_code(
    outcome: RuntimeProcessOutcome | Mapping[str, object],
) -> int:
    process_state = (
        outcome.process_state
        if isinstance(outcome, RuntimeProcessOutcome)
        else str(outcome.get("process_state") or "")
    )
    if process_state in PROCESS_SUCCESS_STATES:
        return 0
    if process_state in PROCESS_FAILURE_STATES:
        return 1
    raise ValueError(f"unsupported runtime process state: {process_state or 'missing'}")


NOOP_STATUSES = {
    "no_fresh_signal",
    "no_current_fresh_live_signal",
    "no_operation_layer_handoff_ready",
    "no_unknown_commands",
    "healthy_waiting_quiet",
    "action_time_lane_already_open",
    "action_time_ticket_sequence_signal_already_processed",
}
TEMPORARILY_UNAVAILABLE_BUSINESS_STATUSES = {
    "action_time_fact_snapshots_blocked",
    "action_time_invocation_fact_snapshot_blocked",
    "action_time_invocation_promotion_blocked",
    "promotion_candidates_blocked",
    "action_time_ticket_sequence_blocked",
    "action_time_ticket_sequence_rolled_back",
    "action_time_refresh_sequence_business_blocked",
}
# This is the one parent status that is already a structured interpretation of
# a child's safe business stop.  Other action-time statuses still pass through
# failure-prefix classification first, so an exception or projection failure is
# never silently relabeled as a safe business block.
EXPLICIT_SAFE_PARENT_BUSINESS_STATUSES = {
    "action_time_refresh_sequence_business_blocked",
}
PROCESS_FAILURE_PREFIXES = (
    "runtime_control_state_invalid",
    "database_",
    "pg_",
    "watcher_or_service_failure",
    "exchange_command_lookup_failed",
    "action_time_sequence_exception",
    "action_time_current_projection_publish_failed",
)
HARD_FAILURE_PREFIXES = (
    "identity_mismatch",
    "cross_scope",
    "runtime_lane_identity_mismatch",
    "forbidden_effect",
    "exchange_command_hard_stopped",
)


def classify_process_outcome(
    *,
    process_name: str,
    result_status: str,
    blockers: list[str],
) -> RuntimeProcessOutcome:
    normalized = [str(item) for item in blockers if str(item)]
    first = normalized[0] if normalized else ""
    if result_status in NOOP_STATUSES and not normalized:
        return RuntimeProcessOutcome(
            process_name=process_name,
            process_state="noop",
            business_state="waiting_for_opportunity",
        )
    # A parent must conserve a child's explicit safe business stop instead of
    # reclassifying it from a blocker-code prefix.  The child already records
    # whether a cross-scope/identity issue is a hard failure at its own stage.
    if result_status in EXPLICIT_SAFE_PARENT_BUSINESS_STATUSES:
        return RuntimeProcessOutcome(
            process_name=process_name,
            process_state="business_blocked",
            business_state="temporarily_unavailable",
            first_blocker=first or result_status,
        )
    if any(first.startswith(prefix) for prefix in HARD_FAILURE_PREFIXES):
        return RuntimeProcessOutcome(
            process_name=process_name,
            process_state="hard_failure",
            business_state="needs_intervention",
            first_blocker=first,
        )
    if first.endswith("_timeout") or any(
        first.startswith(prefix) for prefix in PROCESS_FAILURE_PREFIXES
    ):
        return RuntimeProcessOutcome(
            process_name=process_name,
            process_state="retryable_failure",
            business_state="temporarily_unavailable",
            first_blocker=first,
        )
    if normalized or result_status in {
        "blocked",
        *TEMPORARILY_UNAVAILABLE_BUSINESS_STATUSES,
    }:
        return RuntimeProcessOutcome(
            process_name=process_name,
            process_state="business_blocked",
            business_state=(
                "temporarily_unavailable"
                if result_status in TEMPORARILY_UNAVAILABLE_BUSINESS_STATUSES
                else "needs_intervention"
            ),
            first_blocker=first or result_status,
        )
    business_state = (
        "completed"
        if result_status.endswith(("completed", "submitted", "created", "committed"))
        else "processing"
    )
    return RuntimeProcessOutcome(
        process_name=process_name,
        process_state="succeeded",
        business_state=business_state,
    )


def materialize_runtime_process_outcome(
    conn: sa.engine.Connection,
    *,
    process_name: str,
    scope_key: str | None,
    run_id: str,
    result_status: str,
    blockers: list[str],
    started_at_ms: int,
    completed_at_ms: int,
    runtime_head: str,
    source_watermark: str,
    projector_owner: str = "runtime_process_outcome_projector",
    lane_identity: RuntimeLaneIdentity | None = None,
    action_time_invocation_id: str | None = None,
) -> dict[str, object]:
    if process_name in RUNTIME_LANE_PROCESS_NAMES and lane_identity is None:
        raise ValueError(f"runtime_lane_identity_required:{process_name}")
    outcome = classify_process_outcome(
        process_name=process_name,
        result_status=result_status,
        blockers=blockers,
    )
    table = sa.Table(
        "brc_runtime_process_outcomes",
        sa.MetaData(),
        autoload_with=conn,
    )
    typed_lane_storage = {
        "scope_kind",
        "lane_identity_key",
    }.issubset(table.c.keys())
    if lane_identity is not None:
        resolved_scope_key = scope_key or (
            f"lane:{lane_identity.strategy_group_id}:{lane_identity.symbol}:"
            f"{lane_identity.side}"
        )
        identity = (
            f"{process_name}|{lane_identity.identity_key}|{source_watermark}"
            if typed_lane_storage
            else f"{process_name}|{resolved_scope_key}"
        )
        typed_identity: dict[str, object] = {
            "scope_kind": "runtime_lane",
            "candidate_scope_id": lane_identity.candidate_scope_id,
            "candidate_scope_event_binding_id": (
                lane_identity.candidate_scope_event_binding_id
            ),
            "runtime_scope_binding_id": lane_identity.runtime_scope_binding_id,
            "runtime_instance_id": lane_identity.runtime_instance_id,
            "runtime_profile_id": lane_identity.runtime_profile_id,
            "policy_current_id": lane_identity.policy_current_id,
            "strategy_group_id": lane_identity.strategy_group_id,
            "strategy_group_version_id": lane_identity.strategy_group_version_id,
            "symbol": lane_identity.symbol,
            "exchange_instrument_id": lane_identity.exchange_instrument_id,
            "asset_class": lane_identity.asset_class,
            "side": lane_identity.side,
            "event_spec_id": lane_identity.event_spec_id,
            "event_spec_version": lane_identity.event_spec_version,
            "event_id": lane_identity.event_id,
            "timeframe": lane_identity.timeframe,
            "time_authority": lane_identity.time_authority,
            "lane_identity_key": lane_identity.identity_key,
        }
    else:
        resolved_scope_key = str(scope_key or "").strip()
        if not resolved_scope_key:
            raise ValueError("scope_key is required for an unscoped process outcome")
        identity = f"{process_name}|{resolved_scope_key}"
        typed_identity = {"scope_kind": "legacy_unscoped"}
    row: dict[str, object] = {
        "process_outcome_id": (
            "process_outcome:"
            + sha256(identity.encode("utf-8")).hexdigest()[:32]
        ),
        "process_name": process_name,
        "scope_key": resolved_scope_key,
        "run_id": run_id,
        "process_state": outcome.process_state,
        "business_state": outcome.business_state,
        "first_blocker": outcome.first_blocker or None,
        "started_at_ms": started_at_ms,
        "completed_at_ms": completed_at_ms,
        "runtime_head": runtime_head,
        "source_watermark": source_watermark,
        "projector_owner": projector_owner,
        "updated_at_ms": completed_at_ms,
        **typed_identity,
    }
    if action_time_invocation_id is not None:
        row["action_time_invocation_id"] = str(action_time_invocation_id)
    row = {key: value for key, value in row.items() if key in table.c}
    existing = conn.execute(
        sa.select(table.c.process_outcome_id).where(
            table.c.process_outcome_id == row["process_outcome_id"]
        )
    ).first()
    if existing:
        conn.execute(
            table.update()
            .where(table.c.process_outcome_id == row["process_outcome_id"])
            .values(**row)
        )
    else:
        conn.execute(table.insert().values(**row))
    return row
