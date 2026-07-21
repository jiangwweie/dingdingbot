"""One pure, bounded reduction of runtime-control current truth.

This module deliberately does not replace aggregate transition ownership.  It
maps one already-read control-state snapshot to a deterministic operational
view which can be adapted by Candidate, Tradeability, Daily, Goal and Monitor
without each surface inventing a second definition of ``current``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.application.action_time.capability_certification import (
    current_action_time_capability_truth_by_lane,
)
from src.application.action_time.process_outcome_relevance import (
    process_outcome_has_current_blocking_authority,
)
from src.domain.runtime_semantic_kernel import (
    RuntimePhase,
    RuntimeSemanticState,
    RuntimeState,
    TerminalKind,
)
from src.domain.ticket_bound_exchange_command import (
    exchange_command_effect_is_terminal,
)


CURRENT_TRUTH_SCHEMA = "brc.current_truth_bundle.v1"
PRE_EFFECT_TICKET_STATUSES = frozenset(
    {
        "created",
        "preflight_pending",
        "finalgate_ready",
        "finalgate_rejected",
        "expired",
        "superseded",
        "invalidated",
    }
)
_WIP_LANES = ("CPM-RO-001", "MPG-001", "MI-001", "SOR-001", "BRF2-001")
_BLOCKER_PRIORITY = {
    "hard_safety_stop": 10,
    "outcome_unknown": 20,
    "protection_missing": 30,
    "reconciliation_mismatch": 30,
    "active_position_resolution": 40,
    "capacity_unreleased": 40,
    "action_time_boundary_not_reproduced": 50,
    "action_time_ticket_missing": 50,
    "action_time_preflight_ready": 50,
    "runtime_profile_scope_missing": 60,
    "policy_scope_missing": 60,
    "scope_not_attached": 60,
    "watcher_tick_missing": 70,
    "detector_not_attached": 70,
    "artifact_missing": 70,
    "computed_not_satisfied": 80,
    "market_wait_validated": 90,
}
_OWNER_BLOCKERS = {"policy_scope_missing", "runtime_profile_scope_missing", "scope_not_attached"}


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class LaneIdentity(_FrozenModel):
    strategy_group_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    side: str = Field(min_length=1)
    candidate_scope_id: str = ""

    @property
    def key(self) -> tuple[str, str, str]:
        return self.strategy_group_id, self.symbol, self.side


class LaneOperationalDecision(_FrozenModel):
    lane_identity: LaneIdentity
    stage_reached: str
    runtime_semantic_state: RuntimeState
    phase: RuntimePhase
    first_blocker: str
    blocker_owner: Literal["system", "owner", "market"]
    next_system_action: str
    owner_action_required: bool
    current_issue: bool
    historical_warnings: tuple[str, ...] = ()
    current_object_refs: dict[str, str] = Field(default_factory=dict)
    semantic_fingerprint: str = Field(min_length=1)


class TradeOperationalDecision(_FrozenModel):
    ticket_id: str = Field(min_length=1)
    action_time_lane_input_id: str = ""
    strategy_group_id: str = ""
    symbol: str = ""
    side: str = ""
    exposure_episode_id: str = ""
    netting_domain_key: str = ""
    phase: RuntimePhase
    state: RuntimeState
    protection_state: str
    reconciliation_state: str
    capacity_held: bool
    first_blocker: str
    next_system_action: str
    owner_state: Literal[
        "processing", "running", "needs_intervention", "completed"
    ]
    owner_message: str = Field(min_length=1)
    owner_action_required: bool
    semantic_fingerprint: str = Field(min_length=1)


class OperationalIncidentDecision(_FrozenModel):
    incident_fingerprint: str = Field(min_length=1)
    incident_id: str = Field(min_length=1)
    scope_kind: Literal["lane", "ticket", "system"]
    scope_identity: str = Field(min_length=1)
    phase: RuntimePhase
    blocker_family: str = Field(min_length=1)
    authority_object_ref: str = Field(min_length=1)
    state: Literal["open", "recovered"]
    owner_action_required: bool


class CurrentTruthBundle(_FrozenModel):
    schema_name: str = Field(default=CURRENT_TRUTH_SCHEMA, alias="schema")
    bundle_run_id: str = Field(min_length=1)
    runtime_head: str = ""
    read_now_ms: int = Field(gt=0)
    input_watermark: dict[str, Any]
    input_watermark_digest: str = Field(min_length=1)
    lane_decisions: tuple[LaneOperationalDecision, ...]
    trade_decisions: tuple[TradeOperationalDecision, ...]
    incident_decisions: tuple[OperationalIncidentDecision, ...]
    system_summary: dict[str, Any]


def semantic_state_for_aggregate(
    aggregate: str,
    status: str,
) -> RuntimeSemanticState:
    """Translate one owning aggregate status into the shared small kernel.

    This is intentionally a boundary adapter rather than a universal state
    machine.  Unknown values are fail-closed and retain their exact source in
    the reason code, so a new status cannot silently become healthy current
    state in one read model only.
    """

    normalized_aggregate = str(aggregate or "").strip().lower()
    normalized_status = str(status or "").strip().lower()
    terminal = {
        "expired": TerminalKind.EXPIRED,
        "rejected": TerminalKind.REJECTED,
        "completed": TerminalKind.COMPLETED,
        "closed": TerminalKind.COMPLETED,
        "cancelled": TerminalKind.CANCELLED,
        "invalidated": TerminalKind.CANCELLED,
        "not_selected": TerminalKind.NOT_SELECTED,
    }
    if normalized_status in terminal:
        return RuntimeSemanticState(
            phase=RuntimePhase.CLOSURE,
            state=RuntimeState.TERMINAL,
            terminal_kind=terminal[normalized_status],
        )
    if normalized_status in {"outcome_unknown", "submitted_unknown", "dispatching"}:
        return RuntimeSemanticState(
            phase=RuntimePhase.SUBMITTED,
            state=RuntimeState.OUTCOME_UNKNOWN,
            reason_code="outcome_unknown",
        )
    phase_by_aggregate = {
        "signal": RuntimePhase.OBSERVATION,
        "invocation": RuntimePhase.SELECTION,
        "promotion": RuntimePhase.SELECTION,
        "lane": RuntimePhase.SELECTION,
        "ticket": RuntimePhase.PRE_SUBMIT,
        "command": RuntimePhase.SUBMITTED,
        "lifecycle": RuntimePhase.PROTECTED,
        "process_outcome": RuntimePhase.OBSERVATION,
    }
    phase = phase_by_aggregate.get(normalized_aggregate)
    if phase is None:
        return RuntimeSemanticState(
            phase=RuntimePhase.OBSERVATION,
            state=RuntimeState.BLOCKED,
            reason_code=f"unsupported_runtime_aggregate:{normalized_aggregate or 'missing'}",
        )
    if normalized_status in {
        "fresh", "selected", "opened", "created", "preflight_pending",
        "finalgate_ready", "submitted", "protected", "running", "succeeded",
    }:
        return RuntimeSemanticState(phase=phase, state=RuntimeState.RUNNING)
    if normalized_status in {"blocked", "failed", "pending", "facts_refreshing", "ticket_pending"}:
        return RuntimeSemanticState(
            phase=phase,
            state=RuntimeState.BLOCKED,
            reason_code=normalized_status,
        )
    return RuntimeSemanticState(
        phase=phase,
        state=RuntimeState.BLOCKED,
        reason_code=(
            f"unsupported_runtime_status:{normalized_aggregate}:{normalized_status or 'missing'}"
        ),
    )


def reduce_current_truth(
    control_state: Mapping[str, Any],
    *,
    runtime_head: str = "",
    read_now_ms: int | None = None,
) -> CurrentTruthBundle:
    """Reduce a DB snapshot once; no I/O, mutation, or authority upgrade."""

    now_ms = int(read_now_ms or control_state.get("read_now_ms") or 0)
    if now_ms <= 0:
        raise ValueError("current_truth_read_now_ms_required")
    candidates = _active_candidates(control_state)
    watermark = _input_watermark(control_state, candidates=candidates, now_ms=now_ms)
    watermark_digest = _digest(watermark)
    capability = current_action_time_capability_truth_by_lane(
        control_state,
        current_runtime_head=runtime_head or _current_runtime_head(control_state),
    )
    lanes = tuple(
        _reduce_lane(
            control_state,
            candidate=candidate,
            now_ms=now_ms,
            capability=capability.get(_lane_key(candidate)),
        )
        for candidate in candidates
    )
    trades = tuple(
        _reduce_trade(control_state, row, now_ms=now_ms)
        for row in _rows(control_state, "action_time_tickets")
        if _ticket_current(row, now_ms)
        and _ticket_has_trade_decision_authority(control_state, row)
    )
    incidents = tuple(_incidents(lanes, trades, watermark_digest))
    summary = {
        "active_lane_count": len(lanes),
        "current_issue_count": sum(item.current_issue for item in lanes),
        "trade_current_issue_count": sum(
            item.state is not RuntimeState.TERMINAL for item in trades
        ),
        "owner_action_required": any(
            item.owner_action_required for item in lanes
        ) or any(item.owner_action_required for item in trades),
    }
    bundle_seed = {
        "watermark": watermark_digest,
        "runtime_head": runtime_head or _current_runtime_head(control_state),
        "lanes": [item.semantic_fingerprint for item in lanes],
        "trades": [item.semantic_fingerprint for item in trades],
    }
    bundle_digest = _digest(bundle_seed)
    return CurrentTruthBundle(
        bundle_run_id=f"current_bundle:{now_ms}:{bundle_digest[:20]}",
        runtime_head=runtime_head or _current_runtime_head(control_state),
        read_now_ms=now_ms,
        input_watermark=watermark,
        input_watermark_digest=watermark_digest,
        lane_decisions=lanes,
        trade_decisions=trades,
        incident_decisions=incidents,
        system_summary=summary,
    )


def lane_decision_by_key(bundle: CurrentTruthBundle) -> dict[tuple[str, str, str], LaneOperationalDecision]:
    return {item.lane_identity.key: item for item in bundle.lane_decisions}


def _reduce_lane(
    control_state: Mapping[str, Any],
    *,
    candidate: Mapping[str, Any],
    now_ms: int,
    capability: Any,
) -> LaneOperationalDecision:
    identity = LaneIdentity(
        strategy_group_id=str(candidate.get("strategy_group_id") or ""),
        symbol=str(candidate.get("symbol") or ""),
        side=str(candidate.get("side") or ""),
        candidate_scope_id=str(candidate.get("candidate_scope_id") or ""),
    )
    key = identity.key
    readiness = _latest_lane_row(control_state, "pretrade_readiness_rows", key, now_ms)
    fact = _latest_lane_fact(control_state, key, now_ms)
    coverage = _latest_lane_row(control_state, "watcher_runtime_coverage", key, now_ms)
    signal = _latest_lane_row(control_state, "live_signal_events", key, now_ms)
    outcome = _latest_blocking_process_outcome(control_state, key)
    blockers: list[str] = []
    if outcome:
        blockers.append(str(outcome.get("first_blocker") or "action_time_boundary_not_reproduced"))
    if capability is not None and capability.certified is False:
        blockers.append("action_time_boundary_not_reproduced")
    if readiness.get("first_blocker_class"):
        blockers.append(str(readiness["first_blocker_class"]))
    if not coverage or str(coverage.get("coverage_state") or "") != "covered":
        blockers.append("watcher_tick_missing")
    elif str(coverage.get("liveness_state") or "") not in {"healthy", "ok", "active"}:
        blockers.append("watcher_tick_missing")
    if not fact:
        blockers.append("detector_not_attached")
    elif fact.get("computed") is not True:
        blockers.append("artifact_missing")
    elif fact.get("satisfied") is not True:
        blockers.append(str(fact.get("blocker_class") or "computed_not_satisfied"))
    elif not signal:
        blockers.append("market_wait_validated")
    # A fresh signal with a current detector fact and healthy coverage has
    # crossed observation.  It must be represented as the Action-Time input,
    # not fall through to the reducer's defensive empty-blocker default.
    blocker = (
        "action_time_preflight_ready"
        if not blockers
        else _select_blocker(blockers)
    )
    state = (
        RuntimeState.RUNNING
        if blocker in {"market_wait_validated", "action_time_preflight_ready"}
        else RuntimeState.BLOCKED
    )
    phase = (
        RuntimePhase.OBSERVATION
        if blocker
        in {
            "market_wait_validated",
            "computed_not_satisfied",
            "watcher_tick_missing",
            "detector_not_attached",
            "artifact_missing",
        }
        else RuntimePhase.SELECTION
    )
    refs = {
        "candidate_scope_id": identity.candidate_scope_id,
        "signal_event_id": str(signal.get("signal_event_id") or ""),
        "process_outcome_id": str(outcome.get("process_outcome_id") or ""),
    }
    refs = {name: value for name, value in refs.items() if value}
    owner = "owner" if blocker in _OWNER_BLOCKERS else ("market" if blocker in {"market_wait_validated", "computed_not_satisfied"} else "system")
    fp = _digest({"identity": identity.model_dump(), "blocker": blocker, "refs": refs, "state": state.value})
    return LaneOperationalDecision(
        lane_identity=identity,
        stage_reached=str(candidate.get("tradeability_stage") or "armed_observation"),
        runtime_semantic_state=state,
        phase=phase,
        first_blocker=blocker,
        blocker_owner=owner,
        next_system_action=_next_action(blocker),
        owner_action_required=owner == "owner",
        current_issue=blocker
        not in {"market_wait_validated", "action_time_preflight_ready"},
        current_object_refs=refs,
        semantic_fingerprint=fp,
    )


def _reduce_trade(
    control_state: Mapping[str, Any],
    row: Mapping[str, Any],
    *,
    now_ms: int,
) -> TradeOperationalDecision:
    if _typed_trade_tables_present(control_state):
        return _reduce_typed_trade(control_state, row, now_ms=now_ms)
    if "available_control_state_tables" in control_state:
        return _typed_trade_result(
            row,
            {},
            str(row.get("netting_domain_key") or ""),
            RuntimePhase.SUBMITTED,
            RuntimeState.BLOCKED,
            "unknown",
            "unknown",
            True,
            "schema_revision_mismatch",
            "apply_current_trade_truth_schema",
            "needs_intervention",
            "运行数据库版本不完整，交易链路已停止并等待修复",
            True,
        )
    status = str(row.get("status") or "").lower()
    semantic_state = semantic_state_for_aggregate("ticket", status)
    unknown = semantic_state.state is RuntimeState.OUTCOME_UNKNOWN
    terminal = semantic_state.state is RuntimeState.TERMINAL
    protection = str(row.get("protection_state") or "unknown")
    reconciliation = str(row.get("reconciliation_state") or "unknown")
    blocker = "outcome_unknown" if unknown else ("protection_missing" if protection in {"missing", "failed"} else "")
    fp = _digest({"ticket_id": row.get("ticket_id"), "status": status, "blocker": blocker})
    return TradeOperationalDecision(
        ticket_id=str(row.get("ticket_id") or ""),
        strategy_group_id=str(row.get("strategy_group_id") or ""),
        symbol=str(row.get("symbol") or ""),
        side=str(row.get("side") or ""),
        exposure_episode_id=str(row.get("exposure_episode_id") or ""),
        netting_domain_key=str(row.get("netting_domain_key") or ""),
        phase=semantic_state.phase,
        state=semantic_state.state,
        protection_state=protection,
        reconciliation_state=reconciliation,
        capacity_held=not terminal,
        first_blocker=blocker,
        next_system_action=_next_action(blocker) if blocker else "continue_ticket_lifecycle",
        owner_state="completed" if terminal else "processing",
        owner_message=(
            "交易生命周期已完成" if terminal else "交易结果正在自动确认"
        ),
        owner_action_required=False,
        semantic_fingerprint=fp,
    )


def _reduce_typed_trade(
    state: Mapping[str, Any],
    ticket: Mapping[str, Any],
    *,
    now_ms: int,
) -> TradeOperationalDecision:
    ticket_id = str(ticket.get("ticket_id") or "")
    attempts = _matching_rows(
        state,
        "ticket_bound_protected_submit_attempts",
        "ticket_id",
        ticket_id,
    )
    if len(attempts) != 1:
        return _typed_trade_blocked(ticket, "current_truth_attempt_cardinality_invalid")
    attempt = attempts[0]
    attempt_id = str(attempt.get("protected_submit_attempt_id") or "")
    lane_input_id = str(ticket.get("action_time_lane_input_id") or "")
    lane_inputs = _matching_rows(
        state,
        "action_time_lane_inputs",
        "action_time_lane_input_id",
        lane_input_id,
    )
    if len(lane_inputs) != 1:
        return _typed_trade_blocked(
            ticket,
            "current_truth_lane_input_cardinality_invalid",
            attempt=attempt,
        )
    lane_input = lane_inputs[0]
    if any(
        str(lane_input.get(field) or "") != str(ticket.get(field) or "")
        for field in ("strategy_group_id", "symbol", "side")
    ):
        return _typed_trade_blocked(
            ticket,
            "current_truth_ticket_lane_identity_mismatch",
            attempt=attempt,
        )
    commands = _matching_rows(
        state,
        "ticket_bound_exchange_commands",
        "protected_submit_attempt_id",
        attempt_id,
    )
    entries = [row for row in commands if str(row.get("order_role") or "") == "ENTRY"]
    lifecycles = [
        row
        for row in _matching_rows(
            state,
            "ticket_bound_order_lifecycle_runs",
            "ticket_id",
            ticket_id,
        )
        if str(row.get("protected_submit_attempt_id") or "") == attempt_id
    ]
    if len(entries) != 1:
        return _typed_trade_blocked(
            ticket,
            "current_truth_entry_command_cardinality_invalid",
            attempt=attempt,
        )
    entry = entries[0]
    episode_id = str(ticket.get("exposure_episode_id") or "")
    netting_key = str(entry.get("netting_domain_key") or "")
    if (
        str(entry.get("ticket_id") or "") != ticket_id
        or str(entry.get("source_command_id") or "") != attempt_id
        or str(entry.get("command_source") or "") != "protected_submit"
        or str(entry.get("exposure_episode_id") or "") != episode_id
        or any(
            str(command.get("ticket_id") or "") != ticket_id
            or str(command.get("exposure_episode_id") or "") != episode_id
            or str(command.get("netting_domain_key") or "") != netting_key
            for command in commands
        )
    ):
        return _typed_trade_blocked(
            ticket,
            "current_truth_ticket_chain_identity_mismatch",
            attempt=attempt,
            netting_domain_key=netting_key,
        )
    entry_state = str(entry.get("command_state") or "")
    if (
        entry_state in {"dispatching", "outcome_unknown"}
        or str(attempt.get("entry_effect_state") or "") == "outcome_unknown"
    ):
        observed_at_ms = int(
            entry.get("updated_at_ms")
            or entry.get("exchange_observed_at_ms")
            or entry.get("created_at_ms")
            or 0
        )
        overdue = observed_at_ms <= 0 or now_ms - observed_at_ms >= 30_000
        return _typed_trade_result(
            ticket, attempt, netting_key, RuntimePhase.SUBMITTED,
            RuntimeState.OUTCOME_UNKNOWN,
            str(attempt.get("protection_barrier_state") or "unknown"),
            "pending", True, "entry_exchange_outcome_unknown",
            "reconcile_exact_entry_exchange_identity",
            "needs_intervention" if overdue else "processing",
            (
                "入场订单结果超过自动确认时限，需要介入"
                if overdue
                else "入场订单结果正在自动确认"
            ),
            overdue,
        )
    if len(lifecycles) != 1:
        return _typed_trade_blocked(
            ticket,
            "current_truth_lifecycle_cardinality_invalid",
            attempt=attempt,
            netting_domain_key=netting_key,
        )
    lifecycle = lifecycles[0]
    current_generation = int(attempt.get("protection_barrier_generation") or 1)
    current_by_role: dict[str, Mapping[str, Any]] = {}
    for role in ("SL", "TP1"):
        role_rows = [row for row in commands if str(row.get("order_role") or "") == role]
        if not role_rows:
            return _typed_trade_blocked(
                ticket,
                f"current_truth_{role.lower()}_command_missing",
                attempt=attempt,
                netting_domain_key=netting_key,
            )
        if any(
            int(row.get("command_generation") or 0) > current_generation
            for row in role_rows
        ):
            return _typed_trade_blocked(
                ticket,
                "current_truth_future_protection_generation",
                attempt=attempt,
                netting_domain_key=netting_key,
            )
        current_rows = [
            row
            for row in role_rows
            if int(row.get("command_generation") or 0) == current_generation
        ]
        if len(current_rows) != 1:
            return _typed_trade_blocked(
                ticket,
                f"current_truth_{role.lower()}_command_cardinality_invalid",
                attempt=attempt,
                netting_domain_key=netting_key,
            )
        current_by_role[role] = current_rows[0]

    recovery_rows = [
        row
        for row in _rows(state, "ticket_bound_protection_recovery_commands")
        if str(row.get("ticket_id") or "") == ticket_id
        or str(row.get("protected_submit_attempt_id") or "") == attempt_id
    ]
    if any(
        int(row.get("protection_barrier_generation") or 0)
        > current_generation
        for row in recovery_rows
    ):
        return _typed_trade_blocked(
            ticket,
            "current_truth_future_recovery_generation",
            attempt=attempt,
            netting_domain_key=netting_key,
        )
    stale_active_recovery = [
        row
        for row in recovery_rows
        if int(row.get("protection_barrier_generation") or 0)
        < current_generation
        and str(row.get("status") or "") == "prepared"
    ]
    if stale_active_recovery:
        return _typed_trade_blocked(
            ticket,
            "current_truth_stale_active_recovery_generation",
            attempt=attempt,
            netting_domain_key=netting_key,
        )
    current_recovery_rows = [
        row
        for row in recovery_rows
        if int(row.get("protection_barrier_generation") or 0)
        == current_generation
    ]
    if len(current_recovery_rows) > 1:
        return _typed_trade_blocked(
            ticket,
            "current_truth_recovery_cardinality_invalid",
            attempt=attempt,
            netting_domain_key=netting_key,
        )
    current_recovery = current_recovery_rows[0] if current_recovery_rows else {}
    recovery_roles = _recovery_roles(current_recovery)
    if current_recovery and (
        str(current_recovery.get("ticket_id") or "") != ticket_id
        or str(current_recovery.get("protected_submit_attempt_id") or "")
        != attempt_id
        or str(current_recovery.get("lifecycle_run_id") or "")
        != str(lifecycle.get("lifecycle_run_id") or "")
        or str(current_recovery.get("strategy_group_id") or "")
        != str(ticket.get("strategy_group_id") or "")
        or str(current_recovery.get("symbol") or "")
        != str(ticket.get("symbol") or "")
        or str(current_recovery.get("side") or "")
        != str(ticket.get("side") or "")
        or str(current_recovery.get("exposure_episode_id") or "") != episode_id
        or str(current_recovery.get("netting_domain_key") or "") != netting_key
        or str(current_recovery.get("source_entry_exchange_command_id") or "")
        != str(entry.get("exchange_command_id") or "")
        or _decimal_value(current_recovery.get("protection_quantity"))
        != _decimal_value(attempt.get("protection_quantity"))
        or not recovery_roles
        or not recovery_roles.issubset({"SL", "TP1"})
    ):
        return _typed_trade_blocked(
            ticket,
            "current_truth_recovery_identity_mismatch",
            attempt=attempt,
            netting_domain_key=netting_key,
        )

    ticks = [
        row
        for row in _matching_rows(
            state,
            "ticket_bound_reconciliation_ticks",
            "ticket_id",
            ticket_id,
        )
        if str(row.get("protected_submit_attempt_id") or "") == attempt_id
    ]
    tick = max(
        ticks,
        key=lambda row: (
            int(row.get("updated_at_ms") or row.get("created_at_ms") or 0),
            str(row.get("reconciliation_tick_id") or ""),
        ),
        default={},
    )
    if tick and str(tick.get("exposure_episode_id") or "") != episode_id:
        return _typed_trade_blocked(
            ticket,
            "current_truth_reconciliation_identity_mismatch",
            attempt=attempt,
            netting_domain_key=netting_key,
        )
    generation = current_generation
    active_incidents: list[Mapping[str, Any]] = []
    for incident in _rows(state, "runtime_incidents"):
        if str(incident.get("incident_type") or "") != "initial_stop_not_established":
            continue
        details = _dict_value(incident.get("details"))
        if str(details.get("ticket_id") or "") != ticket_id:
            continue
        incident_generation = int(
            details.get("protection_barrier_generation") or 0
        )
        if (
            incident_generation != generation
            and str(incident.get("status") or "")
            in {"closed", "invalidated"}
        ):
            continue
        if (
            str(details.get("protected_submit_attempt_id") or "") != attempt_id
            or str(details.get("exposure_episode_id") or "") != episode_id
            or str(details.get("netting_domain_key") or "") != netting_key
            or incident_generation != generation
        ):
            return _typed_trade_blocked(
                ticket,
                "current_truth_incident_identity_mismatch",
                attempt=attempt,
                netting_domain_key=netting_key,
            )
        if str(incident.get("status") or "") in {"open", "investigating", "recovering"}:
            active_incidents.append(incident)
    if len(active_incidents) > 1:
        return _typed_trade_blocked(
            ticket,
            "current_truth_incident_cardinality_invalid",
            attempt=attempt,
            netting_domain_key=netting_key,
        )
    active_holds = [
        row
        for row in _rows(state, "ticket_bound_scope_freezes")
        if str(row.get("source_ticket_id") or "") == ticket_id
        and str(row.get("source_kind") or "") == "protection_barrier"
        and str(row.get("status") or "") == "active"
    ]
    if any(
        row.get("netting_domain_key")
        and str(row.get("netting_domain_key")) != netting_key
        for row in active_holds
    ):
        return _typed_trade_blocked(
            ticket,
            "current_truth_hold_identity_mismatch",
            attempt=attempt,
            netting_domain_key=netting_key,
        )

    lifecycle_status = str(lifecycle.get("status") or "")
    barrier = str(attempt.get("protection_barrier_state") or "unknown")
    reservations = _matching_rows(
        state,
        "budget_reservations",
        "ticket_id",
        ticket_id,
    )
    reservation_status = str(reservations[0].get("status") or "") if len(reservations) == 1 else ""
    if str(ticket.get("status") or "") in {"closed", "completed"} or lifecycle_status in {
        "budget_settled",
        "review_recorded",
        "lifecycle_closed",
    }:
        terminal_release_proven = (
            lifecycle_status in {"review_recorded", "lifecycle_closed"}
            and str(attempt.get("entry_effect_state") or "")
            in {"accepted_filled", "reconciled_absent", "rejected"}
            and barrier == "closed"
            and str(tick.get("status") or "") == "matched"
            and str(tick.get("position_state") or "") == "flat"
            and reservation_status == "released"
            and not active_incidents
            and not active_holds
            and all(_exchange_command_terminal(row) for row in commands)
        )
        if not terminal_release_proven:
            return _typed_trade_blocked(
                ticket,
                "current_truth_terminal_release_proof_incomplete",
                attempt=attempt,
                netting_domain_key=netting_key,
            )
        return _typed_trade_result(
            ticket, attempt, netting_key, RuntimePhase.CLOSURE,
            RuntimeState.TERMINAL, barrier, "matched", False, "",
            "lifecycle_completed", "completed", "交易已平仓并完成结算记录", False,
        )
    if str(attempt.get("entry_effect_state") or "") == "accepted_zero_fill":
        return _typed_trade_result(
            ticket, attempt, netting_key, RuntimePhase.SUBMITTED,
            RuntimeState.RUNNING, barrier, str(tick.get("status") or "pending"),
            True, "entry_fill_pending",
            "reconcile_exact_entry_until_fill_or_authoritative_absence",
            "processing", "入场订单暂未成交，系统正在持续确认", False,
        )
    if active_incidents:
        blocker = str(active_incidents[0].get("blocker_class") or "initial_stop_not_established")
        return _typed_trade_result(
            ticket, attempt, netting_key, RuntimePhase.PROTECTED,
            RuntimeState.BLOCKED, barrier, str(tick.get("status") or "pending"),
            True, blocker, "recover_or_reconcile_initial_stop",
            "needs_intervention", "初始止损未建立，系统已冻结新增交易", True,
        )
    if active_holds:
        blocker = str(active_holds[0].get("first_blocker") or "protection_barrier_hold_active")
        return _typed_trade_result(
            ticket, attempt, netting_key, RuntimePhase.PROTECTED,
            RuntimeState.BLOCKED, barrier, str(tick.get("status") or "pending"),
            True, blocker, "repair_or_reconcile_protection_barrier_hold",
            "needs_intervention", "保护屏障仍处于冻结状态，需要处理后继续", True,
        )
    recovery_status = str(current_recovery.get("status") or "")
    if current_recovery and "SL" in recovery_roles:
        within_sla = (
            barrier == "initial_stop_pending"
            and now_ms < int(attempt.get("initial_stop_deadline_at_ms") or 0)
        )
        if recovery_status == "prepared" and not within_sla:
            return _typed_trade_result(
                ticket, attempt, netting_key, RuntimePhase.PROTECTED,
                RuntimeState.BLOCKED, barrier, str(tick.get("status") or "pending"),
                True, "initial_stop_recovery_in_progress",
                "continue_automatic_initial_stop_recovery",
                "needs_intervention", "初始止损尚未恢复，系统正在自动修复", True,
            )
        if recovery_status in {"blocked", "failed"}:
            return _typed_trade_result(
                ticket, attempt, netting_key, RuntimePhase.PROTECTED,
                RuntimeState.BLOCKED, barrier, str(tick.get("status") or "pending"),
                True,
                str(current_recovery.get("first_blocker") or "initial_stop_recovery_failed"),
                "repair_or_reconcile_initial_stop_recovery",
                "needs_intervention", "初始止损自动恢复失败，需要介入", True,
            )
    if (
        current_recovery
        and recovery_roles == {"TP1"}
        and recovery_status in {"blocked", "failed"}
        and barrier in {"initial_stop_confirmed", "degraded"}
    ):
        return _typed_trade_result(
            ticket, attempt, netting_key, RuntimePhase.PROTECTED,
            RuntimeState.RUNNING, "degraded", str(tick.get("status") or "pending"),
            True,
            str(current_recovery.get("first_blocker") or "tp1_recovery_failed"),
            "reconcile_or_retry_tp1_recovery",
            "running", "止损保护正常，止盈单恢复仍在自动处理", False,
        )
    if barrier == "initial_stop_pending":
        within_sla = now_ms < int(attempt.get("initial_stop_deadline_at_ms") or 0)
        return _typed_trade_result(
            ticket, attempt, netting_key, RuntimePhase.SUBMITTED,
            RuntimeState.RUNNING if within_sla else RuntimeState.BLOCKED,
            barrier, str(tick.get("status") or "pending"), True,
            "initial_stop_pending_within_sla" if within_sla else "initial_stop_deadline_exhausted",
            "establish_exact_initial_stop",
            "processing" if within_sla else "needs_intervention",
            (
                "入场已成交，系统正在建立止损保护"
                if within_sla
                else "初始止损已超过建立时限，需要介入"
            ),
            not within_sla,
        )
    if barrier == "degraded" or lifecycle_status == "protection_degraded":
        return _typed_trade_result(
            ticket, attempt, netting_key, RuntimePhase.PROTECTED,
            RuntimeState.RUNNING, "degraded", str(tick.get("status") or "pending"),
            True, "tp1_recovery_pending", "recover_or_reconcile_tp1",
            "running", "止损保护正常，止盈单正在自动恢复", False,
        )
    if barrier == "initial_stop_confirmed" and str(tick.get("status") or "") == "matched":
        return _typed_trade_result(
            ticket, attempt, netting_key, RuntimePhase.PROTECTED,
            RuntimeState.RUNNING, barrier, "matched", True, "",
            "continue_protected_lifecycle_monitoring", "running",
            "持仓保护与交易所状态正常", False,
        )
    return _typed_trade_blocked(
        ticket,
        "current_truth_typed_trade_state_unclassified",
        attempt=attempt,
        netting_domain_key=netting_key,
    )


def _typed_trade_result(
    ticket: Mapping[str, Any],
    attempt: Mapping[str, Any],
    netting_domain_key: str,
    phase: RuntimePhase,
    state: RuntimeState,
    protection_state: str,
    reconciliation_state: str,
    capacity_held: bool,
    blocker: str,
    next_action: str,
    owner_state: Literal["processing", "running", "needs_intervention", "completed"],
    owner_message: str,
    owner_action_required: bool,
) -> TradeOperationalDecision:
    facts = {
        "ticket_id": ticket.get("ticket_id"),
        "attempt_id": attempt.get("protected_submit_attempt_id"),
        "phase": phase.value,
        "state": state.value,
        "barrier": protection_state,
        "reconciliation": reconciliation_state,
        "blocker": blocker,
    }
    return TradeOperationalDecision(
        ticket_id=str(ticket.get("ticket_id") or ""),
        action_time_lane_input_id=str(
            ticket.get("action_time_lane_input_id") or ""
        ),
        strategy_group_id=str(ticket.get("strategy_group_id") or ""),
        symbol=str(ticket.get("symbol") or ""),
        side=str(ticket.get("side") or ""),
        exposure_episode_id=str(ticket.get("exposure_episode_id") or ""),
        netting_domain_key=netting_domain_key,
        phase=phase,
        state=state,
        protection_state=protection_state,
        reconciliation_state=reconciliation_state,
        capacity_held=capacity_held,
        first_blocker=blocker,
        next_system_action=next_action,
        owner_state=owner_state,
        owner_message=owner_message,
        owner_action_required=owner_action_required,
        semantic_fingerprint=_digest(facts),
    )


def _typed_trade_blocked(
    ticket: Mapping[str, Any],
    blocker: str,
    *,
    attempt: Mapping[str, Any] | None = None,
    netting_domain_key: str = "",
) -> TradeOperationalDecision:
    attempt = attempt or {}
    return _typed_trade_result(
        ticket,
        attempt,
        netting_domain_key,
        RuntimePhase.SUBMITTED,
        RuntimeState.BLOCKED,
        str(attempt.get("protection_barrier_state") or "unknown"),
        "unknown",
        True,
        blocker,
        "repair_typed_trade_current_truth",
        "processing",
        "交易链路事实不完整，系统正在修复",
        False,
    )


def _incidents(lanes: Sequence[LaneOperationalDecision], trades: Sequence[TradeOperationalDecision], watermark: str) -> list[OperationalIncidentDecision]:
    result: list[OperationalIncidentDecision] = []
    for item in lanes:
        if not item.current_issue or item.blocker_owner == "market":
            continue
        result.append(_incident("lane", ":".join(item.lane_identity.key), item.phase, item.first_blocker, item.current_object_refs.get("process_outcome_id") or item.lane_identity.candidate_scope_id, item.owner_action_required, watermark))
    for item in trades:
        if not item.first_blocker:
            continue
        result.append(_incident("ticket", item.ticket_id, item.phase, item.first_blocker, item.ticket_id, item.owner_action_required, watermark))
    return sorted(result, key=lambda item: (item.scope_kind, item.scope_identity, item.incident_fingerprint))


def _incident(scope_kind: Literal["lane", "ticket", "system"], scope_identity: str, phase: RuntimePhase, blocker: str, authority_ref: str, owner: bool, watermark: str) -> OperationalIncidentDecision:
    fingerprint = _digest({"scope_kind": scope_kind, "scope_identity": scope_identity, "phase": phase.value, "blocker": blocker, "authority": authority_ref})
    return OperationalIncidentDecision(incident_fingerprint=fingerprint, incident_id=_digest({"fingerprint": fingerprint, "opening": watermark}), scope_kind=scope_kind, scope_identity=scope_identity, phase=phase, blocker_family=blocker, authority_object_ref=authority_ref, state="open", owner_action_required=owner)


def _active_candidates(state: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    candidates = [row for row in _rows(state, "candidate_scope") if row.get("status") == "active" and str(row.get("strategy_group_id") or "") in _WIP_LANES]
    return sorted(candidates, key=lambda row: (_WIP_LANES.index(str(row.get("strategy_group_id"))), int(row.get("priority_rank") or 999), str(row.get("symbol") or ""), str(row.get("side") or "")))


def _latest_lane_row(state: Mapping[str, Any], name: str, key: tuple[str, str, str], now_ms: int) -> Mapping[str, Any]:
    rows = [row for row in _rows(state, name) if _lane_key(row) == key and _row_current(row, now_ms)]
    return max(rows, key=lambda row: (int(row.get("updated_at_ms") or row.get("observed_at_ms") or row.get("created_at_ms") or 0), str(row.get("id") or row.get("signal_event_id") or "")), default={})


def _latest_lane_fact(state: Mapping[str, Any], key: tuple[str, str, str], now_ms: int) -> Mapping[str, Any]:
    rows = [row for row in _rows(state, "runtime_fact_snapshots") if _lane_key(row) == key and str(row.get("fact_surface") or "") in {"pretrade_strategy", "pretrade_public"} and _row_current(row, now_ms)]
    return max(rows, key=lambda row: (str(row.get("fact_surface") or "") == "pretrade_strategy", int(row.get("observed_at_ms") or 0), str(row.get("fact_snapshot_id") or "")), default={})


def _latest_blocking_process_outcome(state: Mapping[str, Any], key: tuple[str, str, str]) -> Mapping[str, Any]:
    rows = [row for row in _rows(state, "runtime_process_outcomes") if _lane_key_from_scope(str(row.get("scope_key") or "")) == key and process_outcome_has_current_blocking_authority(state, row)]
    return max(rows, key=lambda row: (int(row.get("updated_at_ms") or 0), str(row.get("process_outcome_id") or "")), default={})


def _ticket_current(row: Mapping[str, Any], now_ms: int) -> bool:
    return _row_current(row, now_ms)


def _ticket_has_trade_decision_authority(
    state: Mapping[str, Any],
    ticket: Mapping[str, Any],
) -> bool:
    """Keep effect-free pre-submit Tickets under lane current truth.

    A typed trade decision owns the chain only after an exchange effect is
    possible.  Before that boundary, the lane decision remains authoritative.
    Submitted or otherwise post-boundary Tickets still enter the typed reducer
    with zero Attempts so missing effect lineage fails closed there.
    """

    if not _typed_trade_tables_present(state):
        return True
    status = str(ticket.get("status") or "").lower()
    if status not in PRE_EFFECT_TICKET_STATUSES:
        return True
    ticket_id = str(ticket.get("ticket_id") or "")
    attempts = _matching_rows(
        state,
        "ticket_bound_protected_submit_attempts",
        "ticket_id",
        ticket_id,
    )
    if len(attempts) > 1:
        return True
    ticket_entries = [
        row
        for row in _matching_rows(
            state,
            "ticket_bound_exchange_commands",
            "ticket_id",
            ticket_id,
        )
        if str(row.get("order_role") or "") == "ENTRY"
    ]
    if not attempts:
        return any(_entry_command_effect_is_possible(row) for row in ticket_entries)
    attempt = attempts[0]
    if (
        str(attempt.get("entry_effect_state") or "not_called") != "not_called"
        or attempt.get("exchange_write_called") is True
    ):
        return True
    return any(_entry_command_effect_is_possible(row) for row in ticket_entries)


def _entry_command_effect_is_possible(row: Mapping[str, Any]) -> bool:
    return row.get("exchange_write_called") is True or str(
        row.get("command_state") or ""
    ) in {
        "dispatching",
        "outcome_unknown",
        "confirmed_submitted",
        "confirmed_rejected",
        "reconciled_submitted",
    }


def _typed_trade_tables_present(state: Mapping[str, Any]) -> bool:
    required = {
        "ticket_bound_protected_submit_attempts",
        "action_time_lane_inputs",
        "ticket_bound_exchange_commands",
        "ticket_bound_protection_recovery_commands",
        "ticket_bound_order_lifecycle_runs",
        "ticket_bound_reconciliation_ticks",
        "runtime_incidents",
        "ticket_bound_scope_freezes",
    }
    available = state.get("available_control_state_tables")
    if isinstance(available, (list, tuple, set, frozenset)):
        return required.issubset({str(item) for item in available})
    return required.issubset(state)


def _recovery_roles(row: Mapping[str, Any]) -> set[str]:
    plan = _dict_value(row.get("command_plan"))
    orders = plan.get("submit_missing_orders")
    if not isinstance(orders, list):
        return set()
    return {
        str(order.get("order_role") or "").upper()
        for order in orders
        if isinstance(order, Mapping) and str(order.get("order_role") or "")
    }


def _decimal_value(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("NaN")


def _matching_rows(
    state: Mapping[str, Any],
    table: str,
    field: str,
    value: str,
) -> list[Mapping[str, Any]]:
    return [
        row for row in _rows(state, table) if str(row.get(field) or "") == value
    ]


def _exchange_command_terminal(row: Mapping[str, Any]) -> bool:
    return exchange_command_effect_is_terminal(
        command_state=str(row.get("command_state") or ""),
        exchange_order_status=(
            str(row.get("exchange_order_status"))
            if row.get("exchange_order_status") is not None
            else None
        ),
        result_facts_complete=row.get("result_facts_complete") in {True, 1},
    )


def _dict_value(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value.strip():
        parsed = json.loads(value)
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _row_current(row: Mapping[str, Any], now_ms: int) -> bool:
    if row.get("is_current") is False:
        return False
    valid_until = row.get("valid_until_ms") or row.get("expires_at_ms")
    return not valid_until or int(valid_until) >= now_ms


def _select_blocker(values: Sequence[str]) -> str:
    clean = [item for item in values if item]
    if not clean:
        return "detector_not_attached"
    return min(clean, key=lambda item: (_BLOCKER_PRIORITY.get(item, 65), item))


def _next_action(blocker: str) -> str:
    actions = {
        "market_wait_validated": (
            "continue_watcher_observation_until_fresh_signal"
        ),
        "action_time_preflight_ready": "materialize_action_time_ticket",
        "computed_not_satisfied": "continue_observation_with_failed_fact_matrix",
        "watcher_tick_missing": "refresh_readonly_watcher_for_candidate_symbol",
        "detector_not_attached": "attach_detector_for_candidate_symbol",
        "artifact_missing": "produce_per_symbol_readiness_evidence",
        "action_time_boundary_not_reproduced": (
            "repair_non_executing_action_time_rehearsal_path"
        ),
        "outcome_unknown": "reconcile_exact_exchange_command",
        "protection_missing": "materialize_ticket_bound_protection",
    }
    return actions.get(blocker, "reclassify_current_runtime_blocker")


def _input_watermark(state: Mapping[str, Any], *, candidates: Sequence[Mapping[str, Any]], now_ms: int) -> dict[str, Any]:
    tables = ("watcher_runtime_coverage", "runtime_fact_snapshots", "live_signal_events", "pretrade_readiness_rows", "promotion_candidates", "action_time_lane_inputs", "action_time_tickets", "runtime_process_outcomes")
    return {"read_now_ms": now_ms, "runtime_head": _current_runtime_head(state), "candidate_scope_ids": tuple(str(row.get("candidate_scope_id") or "") for row in candidates), "high_watermarks": {name: max((int(row.get("updated_at_ms") or row.get("observed_at_ms") or row.get("created_at_ms") or 0) for row in _rows(state, name)), default=0) for name in tables}}


def _current_runtime_head(state: Mapping[str, Any]) -> str:
    rows = _rows(state, "server_monitor_runs")
    return str(max(rows, key=lambda row: int(row.get("created_at_ms") or 0), default={}).get("runtime_head") or "")


def _rows(state: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = state.get(key)
    return [row for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def _lane_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return str(row.get("strategy_group_id") or ""), str(row.get("symbol") or ""), str(row.get("side") or "")


def _lane_key_from_scope(scope_key: str) -> tuple[str, str, str] | None:
    parts = scope_key.split(":")
    return (parts[1], parts[2], parts[3]) if len(parts) == 4 and parts[0] == "lane" and all(parts[1:]) else None


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return sha256(encoded.encode("utf-8")).hexdigest()
