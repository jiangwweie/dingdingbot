"""One pure, bounded reduction of runtime-control current truth.

This module deliberately does not replace aggregate transition ownership.  It
maps one already-read control-state snapshot to a deterministic operational
view which can be adapted by Candidate, Tradeability, Daily, Goal and Monitor
without each surface inventing a second definition of ``current``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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


CURRENT_TRUTH_SCHEMA = "brc.current_truth_bundle.v1"
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
    exposure_episode_id: str = ""
    netting_domain_key: str = ""
    phase: RuntimePhase
    state: RuntimeState
    protection_state: str
    reconciliation_state: str
    capacity_held: bool
    first_blocker: str
    next_system_action: str
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
    trades = tuple(_reduce_trade(row, now_ms=now_ms) for row in _rows(control_state, "action_time_tickets") if _ticket_current(row, now_ms))
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


def _reduce_trade(row: Mapping[str, Any], *, now_ms: int) -> TradeOperationalDecision:
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
        exposure_episode_id=str(row.get("exposure_episode_id") or ""),
        netting_domain_key=str(row.get("netting_domain_key") or ""),
        phase=semantic_state.phase,
        state=semantic_state.state,
        protection_state=protection,
        reconciliation_state=reconciliation,
        capacity_held=not terminal,
        first_blocker=blocker,
        next_system_action=_next_action(blocker) if blocker else "continue_ticket_lifecycle",
        owner_action_required=False,
        semantic_fingerprint=fp,
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
    return _row_current(row, now_ms) and str(row.get("status") or "").lower() not in {"expired", "rejected", "completed", "closed", "cancelled", "invalidated"}


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
