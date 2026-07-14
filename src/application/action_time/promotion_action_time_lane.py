#!/usr/bin/env python3
"""Materialize PG fresh signals into promotion candidates and one action-time lane.

This script is the PG-only L4 -> L5 bridge:

live_signal_event + readiness + runtime scope + facts
-> promotion candidates
-> one real-submit action-time lane
-> lane-scoped budget reservation and protection reference

It does not call FinalGate, Operation Layer, exchange write APIs, order
lifecycle, withdrawals, transfers, live profile mutation, or order sizing
mutation.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.application.readmodels.daily_live_enablement_table import WIP_LANES  # noqa: E402
from src.application.action_time.capital_safety_guard import (  # noqa: E402
    current_scope_blockers,
)
from src.application.action_time.account_capacity_reservation import (  # noqa: E402
    AccountCapacityReservationResult,
    apply_account_capacity_to_sizing,
)
from src.application.action_time.identity_conservation import (  # noqa: E402
    RuntimeLaneIdentityConservationError,
    RuntimeLaneLineage,
    require_runtime_lane_identity_match,
    require_runtime_lane_lineage_match,
    runtime_lane_identity_from_live_signal,
    runtime_lane_lineage_from_record,
)
from src.application.action_time.pricing_sizing import (  # noqa: E402
    pricing_reference_from_action_time_fact_values,
)
from src.domain.action_time_invocation import (  # noqa: E402
    ActionTimeInvocationEvidence,
)
from src.domain.execution_sizing import (  # noqa: E402
    ExecutionAccountCapacity,
    ExecutionInstrumentRules,
    ExecutionSizingDecision,
    ExecutionSizingPolicy,
    decide_execution_sizing,
)
from src.infrastructure.runtime_control_state_repository import (  # noqa: E402
    PgBackedRuntimeControlStateRepository,
    RuntimeControlStateRepositoryError,
    is_current_action_time_lane,
    is_current_live_signal,
)
from src.application.runtime_process_outcome import (  # noqa: E402
    materialize_runtime_process_outcome,
    runtime_process_exit_code,
)
from src.application.strategy_semantic_admission import (  # noqa: E402
    materialize_active_strategy_semantic_admissions,
)
from src.domain.runtime_lane_identity import (  # noqa: E402
    RuntimeLaneIdentity,
    RuntimeLaneIdentityMismatch,
)


OPEN_REAL_LANE_STATUSES = {
    "opened",
    "facts_refreshing",
    "ticket_pending",
    "ticket_created",
}
PROMOTION_AUTHORITY_BOUNDARY = (
    "pg_promotion_candidate_non_executing; "
    "no_finalgate_no_operation_layer_no_exchange_write"
)
LANE_AUTHORITY_BOUNDARY = (
    "pg_real_submit_candidate_identity_only; "
    "no_finalgate_no_operation_layer_no_exchange_write"
)
FORBIDDEN_EFFECTS = {
    "finalgate_called": False,
    "operation_layer_called": False,
    "exchange_write_called": False,
    "order_created": False,
    "order_lifecycle_called": False,
    "withdrawal_or_transfer_created": False,
    "live_profile_changed": False,
    "order_sizing_changed": False,
}


@dataclass(frozen=True)
class CandidateBundle:
    candidate: dict[str, Any]
    runtime_scope: dict[str, Any]
    policy: dict[str, Any]
    event_binding: dict[str, Any]
    event_spec: dict[str, Any]
    signal: dict[str, Any]
    readiness: dict[str, Any]
    public_fact: dict[str, Any]
    action_time_fact: dict[str, Any]
    account_safe_fact: dict[str, Any]
    account_mode_fact: dict[str, Any]
    coverage: dict[str, Any]
    owner_policy_version: str
    account_id: str
    blockers: tuple[str, ...]
    sizing_risk_decision: ExecutionSizingDecision | None = None
    lane_identity: RuntimeLaneIdentity | None = None
    source_lineage: RuntimeLaneLineage | None = None
    action_time_invocation_id: str | None = None

    @property
    def key(self) -> tuple[str, str, str]:
        return _lane_key(self.candidate)

    @property
    def promotion_candidate_id(self) -> str:
        return _stable_id(
            "promotion",
            str(self.signal["signal_event_id"]),
        )

    @property
    def action_time_lane_input_id(self) -> str:
        return _stable_id("lane", self.promotion_candidate_id)

    @property
    def budget_reservation_id(self) -> str:
        return _stable_id("budget", self.action_time_lane_input_id)

    @property
    def protection_ref_id(self) -> str:
        return _stable_id(
            "protection",
            str(self.event_spec["event_spec_id"]),
            str(self.action_time_fact["fact_snapshot_id"]),
        )


def materialize_pg_promotion_action_time_lane(
    conn: sa.engine.Connection,
    *,
    now_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(now_ms or time.time() * 1000)
    started_at_ms = now_ms

    def result(status: str, **kwargs: Any) -> dict[str, Any]:
        payload = _result(status, **kwargs)
        signal_table = sa.Table(
            "brc_live_signal_events",
            sa.MetaData(),
            autoload_with=conn,
        )
        signal_count = int(
            conn.execute(sa.select(sa.func.count()).select_from(signal_table)).scalar_one()
        )
        if not sa.inspect(conn).has_table("brc_runtime_process_outcomes"):
            return payload
        process_row = materialize_runtime_process_outcome(
            conn,
            process_name="promotion_action_time_lane",
            scope_key="global",
            run_id=_stable_id("promotion_process_run", str(now_ms), status),
            result_status=status,
            blockers=list(kwargs.get("blockers") or []),
            started_at_ms=started_at_ms,
            completed_at_ms=now_ms,
            runtime_head=os.getenv("BRC_RUNTIME_HEAD", "runtime-head-unknown"),
            source_watermark=f"live_signal_events:{signal_count}",
        )
        payload["process_outcome"] = process_row
        return payload

    _expire_stale_open_promotions(conn, now_ms=now_ms)
    _expire_stale_open_real_lanes(conn, now_ms=now_ms)
    if sa.inspect(conn).has_table("brc_strategy_semantic_admissions"):
        materialize_active_strategy_semantic_admissions(conn, now_ms=now_ms)
    try:
        control_state = PgBackedRuntimeControlStateRepository(
            conn,
            now_ms=now_ms,
        ).read_action_time_control_state()
    except RuntimeControlStateRepositoryError as exc:
        return result(
            "blocked",
            now_ms=now_ms,
            blockers=[f"runtime_control_state_invalid:{exc}"],
            next_action="repair_pg_runtime_control_state",
        )

    open_lanes = _open_real_submit_lanes(control_state)
    if open_lanes:
        lane = sorted(open_lanes, key=lambda row: str(row.get("action_time_lane_input_id") or ""))[0]
        lane_expires_at_ms = int(lane.get("expires_at_ms") or 0)
        if lane_expires_at_ms <= now_ms:
            return result(
                "open_action_time_lane_expired",
                now_ms=now_ms,
                action_time_lane_input_id=str(lane.get("action_time_lane_input_id") or ""),
                promotion_candidate_id=str(lane.get("promotion_candidate_id") or ""),
                signal_event_id=str(lane.get("signal_event_id") or ""),
                strategy_group_id=str(lane.get("strategy_group_id") or ""),
                symbol=str(lane.get("symbol") or ""),
                side=str(lane.get("side") or ""),
                blockers=["open_action_time_lane_expired_not_closed"],
                next_action="expire_or_close_pg_action_time_lane",
            )
        return result(
            "action_time_lane_already_open",
            now_ms=now_ms,
            action_time_lane_input_id=str(lane.get("action_time_lane_input_id") or ""),
            promotion_candidate_id=str(lane.get("promotion_candidate_id") or ""),
            signal_event_id=str(lane.get("signal_event_id") or ""),
            strategy_group_id=str(lane.get("strategy_group_id") or ""),
            symbol=str(lane.get("symbol") or ""),
            side=str(lane.get("side") or ""),
            blockers=[],
            next_action="materialize_action_time_ticket",
        )

    bundles = _fresh_signal_bundles(control_state, now_ms=now_ms)
    if not bundles:
        return result(
            "no_fresh_signal",
            now_ms=now_ms,
            blockers=[],
            next_action="continue_watcher_observation",
        )

    bundles = _apply_same_session_opposite_side_conflicts(bundles)
    bundles = _apply_allocation_capital_scope(bundles, now_ms=now_ms)
    eligible = [bundle for bundle in bundles if not bundle.blockers]
    blocked = [bundle for bundle in bundles if bundle.blockers]
    selected = _select_winner(eligible)
    selected_id = selected.promotion_candidate_id if selected else ""
    allocation = _allocation_decision_row(
        bundles=bundles,
        eligible=eligible,
        selected=selected,
        now_ms=now_ms,
    )
    if sa.inspect(conn).has_table("brc_allocation_decisions"):
        _upsert_row(
            conn,
            "brc_allocation_decisions",
            "allocation_decision_id",
            allocation,
        )

    promotion_rows: list[dict[str, Any]] = []
    for bundle in blocked:
        promotion_rows.append(
            _promotion_row(
                bundle,
                now_ms=now_ms,
                status="blocked",
                arbitration_rank=None,
                closed_at_ms=now_ms,
                allocation=allocation,
            )
        )
    for rank, bundle in enumerate(_ranked_candidates(eligible), start=1):
        promotion_rows.append(
            _promotion_row(
                bundle,
                now_ms=now_ms,
                status="arbitration_won"
                if bundle.promotion_candidate_id == selected_id
                else "arbitration_lost",
                arbitration_rank=rank,
                closed_at_ms=None
                if bundle.promotion_candidate_id == selected_id
                else now_ms,
                allocation=allocation,
            )
        )

    if selected is None:
        for row in promotion_rows:
            _upsert_row(conn, "brc_promotion_candidates", "promotion_candidate_id", row)
        return result(
            "promotion_candidates_blocked",
            now_ms=now_ms,
            blockers=_dedupe(
                blocker
                for bundle in blocked
                for blocker in bundle.blockers
            ),
            promotion_candidate_count=len(promotion_rows),
            allocation_decision_id=allocation["allocation_decision_id"],
            next_action="repair_first_blocked_fresh_signal_candidate",
            per_candidate_results=_candidate_results(bundles, selected=None),
        )

    lane = _lane_row(selected, now_ms=now_ms)
    terminal_blockers = _terminal_identity_reuse_blockers(
        conn,
        promotion_row=next(
            row
            for row in promotion_rows
            if row["promotion_candidate_id"] == selected.promotion_candidate_id
        ),
        lane_row=lane,
    )
    if terminal_blockers:
        return result(
            "terminal_action_time_identity_not_reopened",
            now_ms=now_ms,
            blockers=terminal_blockers,
            promotion_candidate_count=len(promotion_rows),
            next_action="wait_for_next_fresh_signal_observation",
            per_candidate_results=_candidate_results(bundles, selected=None),
        )
    for row in promotion_rows:
        _upsert_row(conn, "brc_promotion_candidates", "promotion_candidate_id", row)
    budget = _budget_row(selected, now_ms=now_ms)
    protection = _protection_row(selected)
    _upsert_row(conn, "brc_action_time_lane_inputs", "action_time_lane_input_id", lane)
    _upsert_row(conn, "brc_budget_reservations", "budget_reservation_id", budget)
    _upsert_row(conn, "brc_protection_references", "protection_ref_id", protection)

    return result(
        "promotion_action_time_lane_created",
        now_ms=now_ms,
        promotion_candidate_id=selected.promotion_candidate_id,
        allocation_decision_id=allocation["allocation_decision_id"],
        action_time_lane_input_id=selected.action_time_lane_input_id,
        budget_reservation_id=selected.budget_reservation_id,
        protection_ref_id=selected.protection_ref_id,
        signal_event_id=str(selected.signal["signal_event_id"]),
        strategy_group_id=str(selected.candidate["strategy_group_id"]),
        symbol=str(selected.candidate["symbol"]),
        side=str(selected.candidate["side"]),
        blockers=[],
        promotion_candidate_count=len(promotion_rows),
        next_action="materialize_action_time_ticket",
        per_candidate_results=_candidate_results(bundles, selected=selected),
    )


def materialize_action_time_invocation_promotion_action_time_lane(
    conn: sa.engine.Connection,
    *,
    evidence: ActionTimeInvocationEvidence,
    account_capacity: AccountCapacityReservationResult | None = None,
) -> dict[str, Any]:
    """Promote exactly one invocation; never reselect from Candidate Pool.

    The bounded current PG state remains the source for policy, scope, and
    safety checks.  Generic `brc_pretrade_readiness_rows` is intentionally not
    read as an execution input here.
    """

    now_ms = int(evidence.stage_at_ms)
    _expire_stale_open_promotions(conn, now_ms=now_ms)
    _expire_stale_open_real_lanes(conn, now_ms=now_ms)
    if sa.inspect(conn).has_table("brc_strategy_semantic_admissions"):
        materialize_active_strategy_semantic_admissions(conn, now_ms=now_ms)
    try:
        control_state = PgBackedRuntimeControlStateRepository(
            conn,
            now_ms=now_ms,
        ).read_action_time_control_state()
    except RuntimeControlStateRepositoryError as exc:
        return _invocation_promotion_result(
            "action_time_invocation_promotion_blocked",
            evidence=evidence,
            blockers=[f"runtime_control_state_invalid:{exc}"],
            next_action="repair_pg_runtime_control_state",
        )

    open_lanes = _open_real_submit_lanes(control_state)
    if open_lanes:
        lane = sorted(
            open_lanes,
            key=lambda row: str(row.get("action_time_lane_input_id") or ""),
        )[0]
        if (
            str(lane.get("action_time_invocation_id") or "")
            == evidence.invocation.action_time_invocation_id
            and str(lane.get("signal_event_id") or "")
            == evidence.invocation.signal_event_id
        ):
            return _invocation_promotion_result(
                "action_time_lane_already_open",
                evidence=evidence,
                blockers=[],
                next_action="materialize_action_time_ticket",
                action_time_lane_input_id=str(
                    lane.get("action_time_lane_input_id") or ""
                ),
                promotion_candidate_id=str(
                    lane.get("promotion_candidate_id") or ""
                ),
            )
        return _invocation_promotion_result(
            "action_time_invocation_promotion_blocked",
            evidence=evidence,
            blockers=["action_time_invocation_open_lane_conflict"],
            next_action="wait_for_current_action_time_lane_to_close",
            action_time_lane_input_id=str(lane.get("action_time_lane_input_id") or ""),
            promotion_candidate_id=str(lane.get("promotion_candidate_id") or ""),
        )

    bundle = _invocation_candidate_bundle(control_state, evidence=evidence)
    bundle = _apply_allocation_capital_scope([bundle], now_ms=now_ms)[0]
    if account_capacity is not None:
        if not account_capacity.allowed:
            return _invocation_promotion_result(
                "action_time_invocation_promotion_blocked",
                evidence=evidence,
                blockers=[
                    account_capacity.first_blocker
                    or "account_capacity_not_allowed"
                ],
                next_action="preserve_account_capacity_blocker",
            )
        if bundle.sizing_risk_decision is None:
            return _invocation_promotion_result(
                "action_time_invocation_promotion_blocked",
                evidence=evidence,
                blockers=["account_capacity_sizing_decision_missing"],
                next_action="repair_action_time_sizing_before_capacity_claim",
            )
        try:
            bundle = replace(
                bundle,
                sizing_risk_decision=apply_account_capacity_to_sizing(
                    bundle.sizing_risk_decision,
                    account_capacity,
                ),
            )
        except ValueError as exc:
            return _invocation_promotion_result(
                "action_time_invocation_promotion_blocked",
                evidence=evidence,
                blockers=[f"account_capacity_sizing_conflict:{exc}"],
                next_action="repair_account_capacity_projection",
            )
    if bundle.blockers:
        return _invocation_promotion_result(
            "action_time_invocation_promotion_blocked",
            evidence=evidence,
            blockers=list(bundle.blockers),
            next_action="preserve_exact_invocation_promotion_blocker",
        )

    allocation = _allocation_decision_row(
        bundles=[bundle],
        eligible=[bundle],
        selected=bundle,
        now_ms=now_ms,
    )
    if sa.inspect(conn).has_table("brc_allocation_decisions"):
        _upsert_row(
            conn,
            "brc_allocation_decisions",
            "allocation_decision_id",
            allocation,
        )
    promotion = _promotion_row(
        bundle,
        now_ms=now_ms,
        status="arbitration_won",
        arbitration_rank=1,
        closed_at_ms=None,
        allocation=allocation,
    )
    lane = _lane_row(bundle, now_ms=now_ms)
    terminal_blockers = _terminal_identity_reuse_blockers(
        conn,
        promotion_row=promotion,
        lane_row=lane,
    )
    if terminal_blockers:
        return _invocation_promotion_result(
            "terminal_action_time_identity_not_reopened",
            evidence=evidence,
            blockers=terminal_blockers,
            next_action="wait_for_next_fresh_signal_observation",
        )
    budget = _budget_row(bundle, now_ms=now_ms)
    protection = _protection_row(bundle)
    _upsert_row(
        conn,
        "brc_promotion_candidates",
        "promotion_candidate_id",
        promotion,
    )
    _upsert_row(
        conn,
        "brc_action_time_lane_inputs",
        "action_time_lane_input_id",
        lane,
    )
    _upsert_row(conn, "brc_budget_reservations", "budget_reservation_id", budget)
    _upsert_row(conn, "brc_protection_references", "protection_ref_id", protection)
    return _invocation_promotion_result(
        "promotion_action_time_lane_created",
        evidence=evidence,
        blockers=[],
        next_action="materialize_action_time_ticket",
        promotion_candidate_id=bundle.promotion_candidate_id,
        action_time_lane_input_id=bundle.action_time_lane_input_id,
        budget_reservation_id=bundle.budget_reservation_id,
        protection_ref_id=bundle.protection_ref_id,
        allocation_decision_id=allocation["allocation_decision_id"],
    )


def _invocation_candidate_bundle(
    control_state: dict[str, Any],
    *,
    evidence: ActionTimeInvocationEvidence,
) -> CandidateBundle:
    """Assemble the one exact bundle permitted by invocation evidence."""

    invocation = evidence.invocation
    candidate = _row_with_value(
        _rows(control_state.get("candidate_scope")),
        "candidate_scope_id",
        invocation.lane_identity.candidate_scope_id,
        required_status="active",
    )
    runtime_scope = _row_with_value(
        _rows(control_state.get("runtime_scope_bindings")),
        "runtime_scope_binding_id",
        invocation.lane_identity.runtime_scope_binding_id,
        required_status="active",
    )
    policy = _row_with_value(
        _rows(control_state.get("owner_policy_current")),
        "policy_current_id",
        invocation.lane_identity.policy_current_id,
    )
    event_binding = _row_with_value(
        _rows(control_state.get("candidate_scope_event_bindings")),
        "binding_id",
        invocation.lane_identity.candidate_scope_event_binding_id,
        required_status="active",
    )
    event_spec = _row_with_value(
        _rows(control_state.get("strategy_side_event_specs")),
        "event_spec_id",
        invocation.lane_identity.event_spec_id,
        required_status="current",
    )
    signal = _row_with_value(
        _rows(control_state.get("live_signal_events")),
        "signal_event_id",
        invocation.signal_event_id,
    )
    public_fact = _fact_by_id(
        control_state,
        evidence.public_fact_snapshot_id,
    )
    action_time_fact = _fact_by_id(
        control_state,
        evidence.action_time_fact_snapshot_id,
    )
    account_safe_fact = _fact_by_id(
        control_state,
        evidence.account_safe_fact_snapshot_id,
    )
    account_mode_fact = _fact_by_id(
        control_state,
        evidence.account_mode_fact_snapshot_id,
    )
    coverage = _current_coverage_by_lane(control_state).get(
        _lane_key(candidate),
        {},
    )
    owner_policy_version = _owner_policy_version_by_id(control_state).get(
        str(policy.get("policy_current_id") or ""),
        "",
    )
    lane_identity, source_lineage, identity_blockers = (
        _signal_lane_identity_and_lineage(signal)
        if signal
        else (None, None, ["action_time_invocation_signal_not_visible"])
    )
    direct_blockers: list[str] = [*identity_blockers]
    for label, row in (
        ("candidate", candidate),
        ("runtime_scope", runtime_scope),
        ("policy", policy),
        ("event_binding", event_binding),
        ("event_spec", event_spec),
        ("signal", signal),
        ("public_fact", public_fact),
        ("action_time_fact", action_time_fact),
        ("account_safe_fact", account_safe_fact),
        ("account_mode_fact", account_mode_fact),
    ):
        if not row:
            direct_blockers.append(f"action_time_invocation_{label}_missing")
    if lane_identity is not None and (
        lane_identity.identity_key != invocation.lane_identity.identity_key
    ):
        direct_blockers.append(
            "runtime_lane_identity_mismatch:invocation_to_promotion_signal"
        )
    if source_lineage is None or (
        source_lineage.source_watermark != invocation.source_watermark
    ):
        direct_blockers.append(
            "runtime_lane_identity_mismatch:invocation_to_promotion_source_watermark"
        )
    for fact, surface in (
        (action_time_fact, "action_time"),
        (account_safe_fact, "account_safe"),
        (account_mode_fact, "account_mode"),
    ):
        if fact and str(fact.get("action_time_invocation_id") or "") != (
            invocation.action_time_invocation_id
        ):
            direct_blockers.append(
                f"action_time_invocation_{surface}_fact_reference_mismatch"
            )
    direct_blockers.extend(
        _candidate_blockers(
            control_state,
            now_ms=evidence.stage_at_ms,
            candidate=candidate,
            runtime_scope=runtime_scope,
            policy=policy,
            event_binding=event_binding,
            event_spec=event_spec,
            signal=signal,
            readiness=None,
            public_fact=public_fact,
            action_time_fact=action_time_fact,
            account_safe_fact=account_safe_fact,
            account_mode_fact=account_mode_fact,
            coverage=coverage,
            owner_policy_version=owner_policy_version,
            account_id=_account_id(control_state, candidate),
            lane_identity=lane_identity,
            require_typed_coverage=True,
        )
    )
    return CandidateBundle(
        candidate=candidate,
        runtime_scope=runtime_scope,
        policy=policy,
        event_binding=event_binding,
        event_spec=event_spec,
        signal=signal,
        readiness={
            "readiness_row_id": (
                "action_time_invocation:"
                + invocation.action_time_invocation_id
            ),
            "scope_state": str(candidate.get("scope_state") or ""),
            "risk_state": "acceptable",
        },
        public_fact=public_fact,
        action_time_fact=action_time_fact,
        account_safe_fact=account_safe_fact,
        account_mode_fact=account_mode_fact,
        coverage=coverage,
        owner_policy_version=owner_policy_version,
        account_id=_account_id(control_state, candidate),
        blockers=tuple(_dedupe(direct_blockers)),
        lane_identity=lane_identity,
        source_lineage=source_lineage,
        action_time_invocation_id=invocation.action_time_invocation_id,
    )


def _row_with_value(
    rows: list[dict[str, Any]],
    key: str,
    value: str,
    *,
    required_status: str | None = None,
) -> dict[str, Any]:
    for row in rows:
        if str(row.get(key) or "") != str(value or ""):
            continue
        if required_status is not None and str(row.get("status") or "") != required_status:
            continue
        return row
    return {}


def _invocation_promotion_result(
    status: str,
    *,
    evidence: ActionTimeInvocationEvidence,
    blockers: list[str],
    next_action: str,
    **values: Any,
) -> dict[str, Any]:
    return {
        "schema": "brc.action_time_invocation_promotion.v1",
        "status": status,
        "action_time_invocation_id": evidence.invocation.action_time_invocation_id,
        "signal_event_id": evidence.invocation.signal_event_id,
        "strategy_group_id": evidence.invocation.lane_identity.strategy_group_id,
        "symbol": evidence.invocation.lane_identity.symbol,
        "side": evidence.invocation.lane_identity.side,
        "stage_at_ms": evidence.stage_at_ms,
        "blockers": _dedupe(blockers),
        "next_action": next_action,
        "authority_boundary": PROMOTION_AUTHORITY_BOUNDARY,
        "forbidden_effects": FORBIDDEN_EFFECTS,
        **values,
    }


def _terminal_identity_reuse_blockers(
    conn: sa.engine.Connection,
    *,
    promotion_row: dict[str, Any],
    lane_row: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    blockers.extend(
        _signal_progression_reuse_blockers(
            conn,
            signal_event_id=str(lane_row.get("signal_event_id") or ""),
        )
    )
    promotion_status = _existing_status(
        conn,
        table_name="brc_promotion_candidates",
        pk_name="promotion_candidate_id",
        pk_value=str(promotion_row["promotion_candidate_id"]),
    )
    if promotion_status in {"expired"} and str(promotion_row.get("status") or "") in {
        "eligible",
        "arbitration_pending",
        "arbitration_won",
    }:
        blockers.append(
            "terminal_promotion_identity_reuse:"
            + str(promotion_row["promotion_candidate_id"])
        )
    lane_status = _existing_status(
        conn,
        table_name="brc_action_time_lane_inputs",
        pk_name="action_time_lane_input_id",
        pk_value=str(lane_row["action_time_lane_input_id"]),
    )
    if (
        lane_status in {"closed", "expired", "invalidated"}
        and str(lane_row.get("status") or "") in OPEN_REAL_LANE_STATUSES
    ):
        blockers.append(
            "terminal_action_time_lane_identity_reuse:"
            + str(lane_row["action_time_lane_input_id"])
        )
    return blockers


def _signal_progression_reuse_blockers(
    conn: sa.engine.Connection,
    *,
    signal_event_id: str,
) -> list[str]:
    signal_event_id = str(signal_event_id or "").strip()
    if not signal_event_id:
        return ["signal_event_id_missing_for_action_time_identity"]

    checks = [
        (
            "brc_action_time_lane_inputs",
            "signal_event_already_has_action_time_lane",
            """
            SELECT action_time_lane_input_id AS entity_id
            FROM brc_action_time_lane_inputs
            WHERE signal_event_id = :signal_event_id
            LIMIT 1
            """,
        ),
        (
            "brc_action_time_tickets",
            "signal_event_already_has_action_time_ticket",
            """
            SELECT ticket_id AS entity_id
            FROM brc_action_time_tickets
            WHERE signal_event_id = :signal_event_id
            LIMIT 1
            """,
        ),
        (
            "brc_ticket_bound_protected_submit_attempts",
            "signal_event_already_has_protected_submit_attempt",
            """
            SELECT attempt.protected_submit_attempt_id AS entity_id
            FROM brc_ticket_bound_protected_submit_attempts AS attempt
            JOIN brc_action_time_tickets AS ticket
              ON ticket.ticket_id = attempt.ticket_id
            WHERE ticket.signal_event_id = :signal_event_id
            LIMIT 1
            """,
        ),
    ]
    blockers: list[str] = []
    for _table_name, blocker_prefix, sql in checks:
        row = conn.execute(
            sa.text(sql),
            {"signal_event_id": signal_event_id},
        ).mappings().first()
        if row:
            blockers.append(f"{blocker_prefix}:{signal_event_id}:{row['entity_id']}")
    return blockers


def _existing_status(
    conn: sa.engine.Connection,
    *,
    table_name: str,
    pk_name: str,
    pk_value: str,
) -> str:
    metadata = sa.MetaData()
    table = sa.Table(table_name, metadata, autoload_with=conn)
    row = conn.execute(
        sa.select(table.c.status).where(table.c[pk_name] == pk_value).limit(1)
    ).mappings().first()
    return str(row["status"] or "") if row else ""


def _expire_stale_open_promotions(
    conn: sa.engine.Connection,
    *,
    now_ms: int,
) -> int:
    expired_rows = [
        dict(row)
        for row in conn.execute(
            sa.text(
                """
                SELECT promotion_candidate_id, status
                FROM brc_promotion_candidates
                WHERE status IN ('eligible', 'arbitration_pending', 'arbitration_won')
                  AND closed_at_ms IS NULL
                  AND expires_at_ms IS NOT NULL
                  AND expires_at_ms <= :now_ms
                """
            ),
            {"now_ms": now_ms},
        ).mappings()
    ]
    if not expired_rows:
        return 0
    conn.execute(
        sa.text(
            """
            UPDATE brc_promotion_candidates
            SET status = 'expired',
                closed_at_ms = :now_ms
            WHERE status IN ('eligible', 'arbitration_pending', 'arbitration_won')
              AND closed_at_ms IS NULL
              AND expires_at_ms IS NOT NULL
              AND expires_at_ms <= :now_ms
            """
        ),
        {"now_ms": now_ms},
    )
    for row in expired_rows:
        _insert_state_transition_event(
            conn,
            state_table="brc_promotion_candidates",
            entity_id=str(row["promotion_candidate_id"]),
            from_status=str(row["status"]),
            to_status="expired",
            transition_reason="promotion_candidate_expired_before_action_time_lane",
            trigger_ref="materialize_pg_promotion_action_time_lane",
            writer="materialize_pg_promotion_action_time_lane",
            now_ms=now_ms,
        )
    return len(expired_rows)


def _expire_stale_open_real_lanes(
    conn: sa.engine.Connection,
    *,
    now_ms: int,
) -> int:
    expired_rows = [
        dict(row)
        for row in conn.execute(
            sa.text(
                """
                SELECT action_time_lane_input_id, status
                FROM brc_action_time_lane_inputs
                WHERE lane_scope = 'real_submit_candidate'
                  AND status IN ('opened', 'facts_refreshing', 'ticket_pending')
                  AND closed_at_ms IS NULL
                  AND expires_at_ms IS NOT NULL
                  AND expires_at_ms <= :now_ms
                """
            ),
            {"now_ms": now_ms},
        ).mappings()
    ]
    if expired_rows:
        conn.execute(
            sa.text(
                """
                UPDATE brc_action_time_lane_inputs
                SET status = 'expired',
                    closed_at_ms = :now_ms,
                    first_blocker_class = COALESCE(
                        first_blocker_class,
                        'expired_open_action_time_lane_cleanup_required'
                    )
                WHERE lane_scope = 'real_submit_candidate'
                  AND status IN ('opened', 'facts_refreshing', 'ticket_pending')
                  AND closed_at_ms IS NULL
                  AND expires_at_ms IS NOT NULL
                  AND expires_at_ms <= :now_ms
                """
            ),
            {"now_ms": now_ms},
        )
        for row in expired_rows:
            _insert_state_transition_event(
                conn,
                state_table="brc_action_time_lane_inputs",
                entity_id=str(row["action_time_lane_input_id"]),
                from_status=str(row["status"]),
                to_status="expired",
                transition_reason="action_time_lane_expired_before_materialization",
                trigger_ref="materialize_pg_promotion_action_time_lane",
                writer="materialize_pg_promotion_action_time_lane",
                now_ms=now_ms,
            )
    closed_rows = _close_stale_ticket_created_lanes_without_current_ticket(
        conn,
        now_ms=now_ms,
    )
    return len(expired_rows) + closed_rows


def _close_stale_ticket_created_lanes_without_current_ticket(
    conn: sa.engine.Connection,
    *,
    now_ms: int,
) -> int:
    rows = [
        dict(row)
        for row in conn.execute(
            sa.text(
                """
                SELECT
                  lane.action_time_lane_input_id,
                  lane.status AS lane_status,
                  ticket.ticket_id,
                  ticket.status AS ticket_status,
                  ticket.expires_at_ms AS ticket_expires_at_ms
                FROM brc_action_time_lane_inputs AS lane
                LEFT JOIN brc_action_time_tickets AS ticket
                  ON ticket.action_time_lane_input_id = lane.action_time_lane_input_id
                WHERE lane.lane_scope = 'real_submit_candidate'
                  AND lane.status = 'ticket_created'
                  AND lane.closed_at_ms IS NULL
                  AND lane.expires_at_ms IS NOT NULL
                  AND lane.expires_at_ms <= :now_ms
                """
            ),
            {"now_ms": now_ms},
        ).mappings()
    ]
    transitioned = 0
    for row in rows:
        ticket_status = str(row.get("ticket_status") or "")
        ticket_expires_at_ms = row.get("ticket_expires_at_ms")
        if (
            ticket_status in {"created", "preflight_pending", "finalgate_ready"}
            and ticket_expires_at_ms is not None
            and int(ticket_expires_at_ms or 0) > now_ms
        ):
            continue
        to_status = "closed" if row.get("ticket_id") else "invalidated"
        reason = (
            "ticket_created_lane_closed_after_ticket_non_current"
            if to_status == "closed"
            else "ticket_created_lane_invalidated_missing_ticket"
        )
        lane_id = str(row["action_time_lane_input_id"])
        conn.execute(
            sa.text(
                """
                UPDATE brc_action_time_lane_inputs
                SET status = :to_status,
                    closed_at_ms = :now_ms,
                    first_blocker_class = COALESCE(first_blocker_class, :reason)
                WHERE action_time_lane_input_id = :lane_id
                  AND status = 'ticket_created'
                  AND closed_at_ms IS NULL
                """
            ),
            {
                "lane_id": lane_id,
                "to_status": to_status,
                "now_ms": now_ms,
                "reason": reason,
            },
        )
        _insert_state_transition_event(
            conn,
            state_table="brc_action_time_lane_inputs",
            entity_id=lane_id,
            from_status=str(row["lane_status"]),
            to_status=to_status,
            transition_reason=reason,
            trigger_ref="materialize_pg_promotion_action_time_lane",
            writer="materialize_pg_promotion_action_time_lane",
            now_ms=now_ms,
        )
        transitioned += 1
    return transitioned


def _insert_state_transition_event(
    conn: sa.engine.Connection,
    *,
    state_table: str,
    entity_id: str,
    from_status: str,
    to_status: str,
    transition_reason: str,
    trigger_ref: str,
    writer: str,
    now_ms: int,
) -> None:
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_state_transition_events (
              transition_event_id, state_table, entity_id, from_status,
              to_status, transition_reason, trigger_ref, writer, occurred_at_ms
            ) VALUES (
              :transition_event_id, :state_table, :entity_id, :from_status,
              :to_status, :transition_reason, :trigger_ref, :writer, :occurred_at_ms
            )
            """
        ),
        {
            "transition_event_id": _stable_id(
                "state_transition",
                state_table,
                entity_id,
                to_status,
                str(now_ms),
            ),
            "state_table": state_table,
            "entity_id": entity_id,
            "from_status": from_status,
            "to_status": to_status,
            "transition_reason": transition_reason,
            "trigger_ref": trigger_ref,
            "writer": writer,
            "occurred_at_ms": now_ms,
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--require-database-url", action="store_true")
    parser.add_argument(
        "--allow-non-postgres-for-test",
        action="store_true",
        help="Allow SQLite or other SQLAlchemy URLs only for local unit tests.",
    )
    parser.add_argument("--now-ms", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.require_database_url and not args.database_url:
        print(
            "ERROR: PG_DATABASE_URL is required for PG promotion/action-time lane materializer",
            file=sys.stderr,
        )
        return 2
    if not args.database_url:
        print("ERROR: --database-url or PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    if (
        not args.allow_non_postgres_for_test
        and not args.database_url.startswith(("postgresql://", "postgresql+psycopg://"))
    ):
        print("ERROR: PG promotion/action-time lane materializer requires PostgreSQL DSN", file=sys.stderr)
        return 2

    engine = sa.create_engine(args.database_url)
    try:
        with engine.begin() as conn:
            report = materialize_pg_promotion_action_time_lane(conn, now_ms=args.now_ms)
    except sa.exc.SQLAlchemyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, default=str))
    else:
        print(report["status"])
    return _report_exit_code(report)


def _report_exit_code(report: dict[str, Any]) -> int:
    process_outcome = report.get("process_outcome")
    if isinstance(process_outcome, dict):
        return runtime_process_exit_code(process_outcome)
    return 1 if report["status"] in {"blocked", "promotion_candidates_blocked"} else 0


def _fresh_signal_bundles(
    control_state: dict[str, Any],
    *,
    now_ms: int,
) -> list[CandidateBundle]:
    candidates = _active_candidate_rows(control_state)
    runtime_by_candidate = _active_by(control_state, "runtime_scope_bindings", "candidate_scope_id")
    policy_by_id = {
        str(row.get("policy_current_id") or ""): row
        for row in _rows(control_state.get("owner_policy_current"))
    }
    event_binding_by_candidate = _active_by(
        control_state,
        "candidate_scope_event_bindings",
        "candidate_scope_id",
    )
    event_by_id = {
        str(row.get("event_spec_id") or ""): row
        for row in _rows(control_state.get("strategy_side_event_specs"))
        if row.get("status") == "current"
    }
    readiness_by_lane = {
        _lane_key(row): row
        for row in _rows(control_state.get("pretrade_readiness_rows"))
    }
    coverage_by_lane = _current_coverage_by_lane(control_state)
    owner_policy_version_by_id = _owner_policy_version_by_id(control_state)

    bundles: list[CandidateBundle] = []
    for candidate in candidates:
        candidate_scope_id = str(candidate.get("candidate_scope_id") or "")
        event_binding = event_binding_by_candidate.get(candidate_scope_id, {})
        event_spec = event_by_id.get(str(event_binding.get("event_spec_id") or ""), {})
        signal = _fresh_signal_for_candidate(
            control_state,
            candidate=candidate,
            event_spec=event_spec,
            now_ms=now_ms,
        )
        if not signal:
            continue
        lane_identity, source_lineage, identity_blockers = (
            _signal_lane_identity_and_lineage(signal)
        )
        runtime_scope = runtime_by_candidate.get(candidate_scope_id, {})
        policy = policy_by_id.get(str(candidate.get("policy_current_id") or ""), {})
        readiness = readiness_by_lane.get(_lane_key(candidate), {})
        public_fact = _fact_by_id(
            control_state,
            str(signal.get("fact_snapshot_id") or ""),
        )
        action_time_fact = _latest_fact(
            control_state,
            candidate=candidate,
            runtime_profile_id=str(runtime_scope.get("runtime_profile_id") or ""),
            fact_surface="action_time",
        )
        account_safe_fact = _latest_fact(
            control_state,
            candidate=candidate,
            runtime_profile_id=str(runtime_scope.get("runtime_profile_id") or ""),
            fact_surface="account_safe",
            allow_global=True,
        )
        account_mode_fact = _latest_fact(
            control_state,
            candidate=candidate,
            runtime_profile_id=str(runtime_scope.get("runtime_profile_id") or ""),
            fact_surface="account_mode",
            allow_global=True,
        )
        coverage = coverage_by_lane.get(_lane_key(candidate), {})
        owner_policy_version = owner_policy_version_by_id.get(
            str(policy.get("policy_current_id") or ""),
            "",
        )
        account_id = _account_id(control_state, candidate)
        blockers = tuple(
            [
                *identity_blockers,
                *_candidate_blockers(
                control_state,
                now_ms=now_ms,
                candidate=candidate,
                runtime_scope=runtime_scope,
                policy=policy,
                event_binding=event_binding,
                event_spec=event_spec,
                signal=signal,
                readiness=readiness,
                public_fact=public_fact,
                action_time_fact=action_time_fact,
                account_safe_fact=account_safe_fact,
                account_mode_fact=account_mode_fact,
                coverage=coverage,
                owner_policy_version=owner_policy_version,
                account_id=account_id,
                lane_identity=lane_identity,
                ),
            ]
        )
        bundles.append(
            CandidateBundle(
                candidate=candidate,
                runtime_scope=runtime_scope,
                policy=policy,
                event_binding=event_binding,
                event_spec=event_spec,
                signal=signal,
                readiness=readiness,
                public_fact=public_fact,
                action_time_fact=action_time_fact,
                account_safe_fact=account_safe_fact,
                account_mode_fact=account_mode_fact,
                coverage=coverage,
                owner_policy_version=owner_policy_version,
                account_id=account_id,
                blockers=blockers,
                lane_identity=lane_identity,
                source_lineage=source_lineage,
            )
        )
    return bundles


def _apply_same_session_opposite_side_conflicts(
    bundles: list[CandidateBundle],
) -> list[CandidateBundle]:
    sides_by_session: dict[tuple[str, str, int], set[str]] = {}
    for bundle in bundles:
        key = (
            str(bundle.candidate.get("strategy_group_id") or ""),
            str(bundle.candidate.get("symbol") or ""),
            int(bundle.signal.get("trigger_candle_close_time_ms") or 0),
        )
        sides_by_session.setdefault(key, set()).add(str(bundle.candidate.get("side") or ""))

    conflict_keys = {
        key
        for key, sides in sides_by_session.items()
        if "long" in sides and "short" in sides
    }
    if not conflict_keys:
        return bundles

    out: list[CandidateBundle] = []
    for bundle in bundles:
        key = (
            str(bundle.candidate.get("strategy_group_id") or ""),
            str(bundle.candidate.get("symbol") or ""),
            int(bundle.signal.get("trigger_candle_close_time_ms") or 0),
        )
        if key in conflict_keys:
            out.append(
                replace(
                    bundle,
                    blockers=tuple(
                        _dedupe([*bundle.blockers, "same_session_opposite_side_conflict"])
                    ),
                )
            )
        else:
            out.append(bundle)
    return out


def _signal_lane_identity_and_lineage(
    signal: dict[str, Any],
) -> tuple[RuntimeLaneIdentity | None, RuntimeLaneLineage | None, list[str]]:
    """Require typed identity for migrated current signal rows.

    A pre-118 test schema has no identity columns at all. It is not a runtime
    fallback: after migration the columns are present on every row and a blank
    value becomes a first-boundary fail-closed blocker.
    """

    if "lane_identity_key" not in signal:
        return None, None, []
    try:
        identity = runtime_lane_identity_from_live_signal(signal)
        lineage = runtime_lane_lineage_from_record(signal)
    except RuntimeLaneIdentityConservationError as exc:
        return None, None, [exc.blocker]
    if lineage.lane_identity_key != identity.identity_key:
        return None, None, ["runtime_lane_identity_mismatch:signal_lineage_key"]
    return identity, lineage, []


def _signal_identity_matches_current_lane(
    *,
    lane_identity: RuntimeLaneIdentity | None,
    candidate: dict[str, Any],
    runtime_scope: dict[str, Any],
    policy: dict[str, Any],
    event_binding: dict[str, Any],
    event_spec: dict[str, Any],
) -> list[str]:
    if lane_identity is None:
        return []
    try:
        current_identity = RuntimeLaneIdentity(
            candidate_scope_id=str(candidate.get("candidate_scope_id") or ""),
            candidate_scope_event_binding_id=str(
                event_binding.get("binding_id") or ""
            ),
            runtime_scope_binding_id=str(
                runtime_scope.get("runtime_scope_binding_id") or ""
            ),
            runtime_instance_id=lane_identity.runtime_instance_id,
            runtime_profile_id=str(runtime_scope.get("runtime_profile_id") or ""),
            policy_current_id=str(runtime_scope.get("policy_current_id") or ""),
            strategy_group_id=str(candidate.get("strategy_group_id") or ""),
            strategy_group_version_id=str(
                event_spec.get("strategy_group_version_id") or ""
            ),
            symbol=str(candidate.get("symbol") or ""),
            asset_class=str(candidate.get("asset_class") or ""),
            side=str(candidate.get("side") or ""),
            event_spec_id=str(event_spec.get("event_spec_id") or ""),
            event_spec_version=str(event_spec.get("event_spec_version") or ""),
            event_id=str(event_spec.get("event_id") or ""),
            timeframe=str(event_spec.get("timeframe") or ""),
            time_authority=str(event_spec.get("time_authority") or ""),
        )
        if str(policy.get("policy_current_id") or "") != current_identity.policy_current_id:
            return ["runtime_lane_identity_mismatch:signal_to_promotion_policy"]
        require_runtime_lane_identity_match(
            expected=lane_identity,
            actual=current_identity,
            boundary="signal_to_promotion",
        )
    except RuntimeLaneIdentityMismatch as exc:
        return [str(exc)]
    except (TypeError, ValueError):
        return ["runtime_lane_identity_mismatch:signal_to_promotion_current_scope"]
    return []


def _lineage_match_blocker(
    *,
    expected: RuntimeLaneLineage | None,
    actual_row: dict[str, Any],
    boundary: str,
) -> str | None:
    if expected is None:
        return None
    try:
        actual = runtime_lane_lineage_from_record(actual_row)
        require_runtime_lane_lineage_match(
            expected=expected,
            actual=actual,
            boundary=boundary,
        )
    except RuntimeLaneIdentityConservationError as exc:
        return exc.blocker
    except RuntimeLaneIdentityMismatch as exc:
        return str(exc)
    return None


def _candidate_blockers(
    control_state: dict[str, Any],
    *,
    now_ms: int,
    candidate: dict[str, Any],
    runtime_scope: dict[str, Any],
    policy: dict[str, Any],
    event_binding: dict[str, Any],
    event_spec: dict[str, Any],
    signal: dict[str, Any],
    readiness: dict[str, Any] | None,
    public_fact: dict[str, Any],
    action_time_fact: dict[str, Any],
    account_safe_fact: dict[str, Any],
    account_mode_fact: dict[str, Any],
    coverage: dict[str, Any],
    owner_policy_version: str,
    account_id: str,
    lane_identity: RuntimeLaneIdentity | None,
    require_typed_coverage: bool = False,
) -> list[str]:
    blockers: list[str] = []
    blockers.extend(
        current_scope_blockers(
            control_state,
            strategy_group_id=candidate.get("strategy_group_id"),
            symbol=candidate.get("symbol"),
            side=candidate.get("side"),
        )
    )
    _require_identity_match(blockers, candidate, runtime_scope, "runtime_scope")
    _require_identity_match(blockers, candidate, policy, "policy")
    _require_identity_match(blockers, candidate, event_binding, "event_binding")
    _require_identity_match(blockers, candidate, event_spec, "event_spec", keys=("strategy_group_id", "side"))
    _require_identity_match(blockers, candidate, signal, "signal")
    if readiness is not None:
        _require_identity_match(blockers, candidate, readiness, "readiness")
    _require_identity_match(blockers, candidate, public_fact, "public_fact")
    _require_identity_match(blockers, candidate, action_time_fact, "action_time_fact")
    blockers.extend(
        _signal_identity_matches_current_lane(
            lane_identity=lane_identity,
            candidate=candidate,
            runtime_scope=runtime_scope,
            policy=policy,
            event_binding=event_binding,
            event_spec=event_spec,
        )
    )

    if not event_binding:
        blockers.append("candidate_event_binding_missing")
    if not event_spec:
        blockers.append("event_spec_missing")
    if str(signal.get("event_spec_id") or "") != str(event_spec.get("event_spec_id") or ""):
        blockers.append("signal_event_spec_mismatch")
    if str(signal.get("candidate_scope_id") or "") != str(candidate.get("candidate_scope_id") or ""):
        blockers.append("signal_candidate_scope_mismatch")
    if signal.get("source_kind") != "live_market":
        blockers.append(f"signal_event_not_live_market:{signal.get('source_kind') or 'missing'}")
    if signal.get("status") != "facts_validated":
        blockers.append(f"signal_event_not_facts_validated:{signal.get('status') or 'missing'}")
    if signal.get("freshness_state") != "fresh":
        blockers.append(f"signal_event_not_fresh:{signal.get('freshness_state') or 'missing'}")
    if int(signal.get("expires_at_ms") or 0) <= now_ms:
        blockers.append("signal_event_expired")
    if int(signal.get("event_time_ms") or 0) <= 0:
        blockers.append("signal_event_time_missing")
    if int(signal.get("event_time_ms") or 0) != int(signal.get("trigger_candle_close_time_ms") or 0):
        blockers.append("signal_event_time_mismatch:trigger_candle_close_time_ms")
    if int(signal.get("created_at_ms") or 0) == int(signal.get("event_time_ms") or 0):
        blockers.append("signal_generated_at_used_as_event_time")
    if signal.get("execution_eligible") is not True:
        blockers.append("signal_execution_eligibility_missing_or_false")
    if signal.get("signal_grade") not in {
        "trial_grade_signal",
        "production_grade_signal",
    }:
        blockers.append(
            f"signal_grade_not_execution_eligible:{signal.get('signal_grade') or 'missing'}"
        )
    if signal.get("required_execution_mode") not in {
        "trial_live",
        "production_live",
    }:
        blockers.append(
            "signal_required_execution_mode_not_live:"
            f"{signal.get('required_execution_mode') or 'missing'}"
        )
    if event_spec.get("execution_eligibility_enabled") is not True:
        blockers.append("event_spec_execution_eligibility_disabled")
    if str(signal.get("signal_grade") or "") != str(
        event_spec.get("declared_signal_grade") or ""
    ):
        blockers.append("signal_event_spec_grade_mismatch")
    if str(signal.get("required_execution_mode") or "") != str(
        event_spec.get("declared_required_execution_mode") or ""
    ):
        blockers.append("signal_event_spec_execution_mode_mismatch")
    if not str(signal.get("authority_source_ref") or "").strip():
        blockers.append("signal_authority_source_ref_missing")

    if runtime_scope.get("status") != "active":
        blockers.append("runtime_scope_binding_not_active")
    for flag in (
        "selected_strategygroup_scope",
        "symbol_side_scope_closed",
        "notional_leverage_scope_closed",
        "live_submit_allowed",
    ):
        if runtime_scope.get(flag) is not True:
            blockers.append(f"runtime_scope_not_closed:{flag}")
    if policy.get("enabled_state") != "enabled":
        blockers.append("owner_policy_not_enabled")
    if policy.get("pretrade_candidate_allowed") is not True:
        blockers.append("owner_policy_blocks_pretrade")
    if policy.get("action_time_rehearsal_allowed") is not True:
        blockers.append("owner_policy_blocks_action_time")
    if policy.get("live_submit_allowed") not in {"scoped", "conditional_hard_gated"}:
        blockers.append("owner_policy_blocks_live_submit")
    if not owner_policy_version:
        blockers.append("owner_policy_version_missing")

    if candidate.get("scope_state") != "live_submit_allowed":
        blockers.append(f"candidate_scope_not_live_submit:{candidate.get('scope_state') or 'missing'}")
    if readiness is not None:
        if readiness.get("readiness_state") != "action_time_lane":
            blockers.append(
                "readiness_not_action_time_lane:"
                f"{readiness.get('readiness_state') or 'missing'}"
            )
        if readiness.get("public_facts_state") != "satisfied":
            blockers.append(
                "public_facts_not_satisfied:"
                f"{readiness.get('public_facts_state') or 'missing'}"
            )
        if readiness.get("signal_lifecycle_status") != "facts_validated":
            blockers.append("readiness_signal_not_facts_validated")
        if readiness.get("signal_freshness_state") != "fresh":
            blockers.append("readiness_signal_not_fresh")
        if readiness.get("risk_state") != "acceptable":
            blockers.append(
                f"risk_state_not_acceptable:{readiness.get('risk_state') or 'missing'}"
            )
        readiness_scope_state = str(readiness.get("scope_state") or "")
        candidate_scope_state = str(candidate.get("scope_state") or "")
        if (
            readiness_scope_state != "live_submit_allowed"
            and not (
                candidate_scope_state == "live_submit_allowed"
                and readiness_scope_state
                == "conditional_action_time_rehearsal_allowed"
            )
        ):
            blockers.append(
                "readiness_scope_not_live_submit:"
                f"{readiness.get('scope_state') or 'missing'}"
            )
        if readiness.get("promotion_state") != "action_time_lane":
            blockers.append(
                "readiness_promotion_not_action_time_lane:"
                f"{readiness.get('promotion_state') or 'missing'}"
            )
        if readiness.get("first_blocker_class") != "action_time_preflight_ready":
            blockers.append(
                "readiness_not_action_time_preflight_ready:"
                f"{readiness.get('first_blocker_class') or 'missing'}"
            )

    if coverage.get("coverage_state") != "covered":
        blockers.append(f"runtime_coverage_not_covered:{coverage.get('coverage_state') or 'missing'}")
    if coverage.get("liveness_state") not in {"healthy", "ok", "active"}:
        blockers.append(f"runtime_coverage_not_healthy:{coverage.get('liveness_state') or 'missing'}")
    if coverage.get("is_current") is not True:
        blockers.append("runtime_coverage_not_current")
    if int(coverage.get("valid_until_ms") or 0) <= now_ms:
        blockers.append("runtime_coverage_expired")
    if require_typed_coverage:
        blockers.extend(
            _invocation_coverage_identity_blockers(
                coverage=coverage,
                expected_lane_identity=lane_identity,
            )
        )

    _assert_fact_ready(blockers, "public_fact", public_fact, now_ms=now_ms)
    _assert_fact_ready(blockers, "action_time_fact", action_time_fact, now_ms=now_ms)
    _assert_fact_ready(blockers, "account_safe_fact", account_safe_fact, now_ms=now_ms)
    _assert_fact_ready(blockers, "account_mode_fact", account_mode_fact, now_ms=now_ms)
    account_values = _as_dict(account_safe_fact.get("fact_values"))
    if account_values.get("account_safe") is not True:
        blockers.append("account_safe_fact_not_true")
    if account_values.get("open_orders_clear") is not True:
        blockers.append("open_orders_not_clear")
    if account_values.get("active_position_or_open_order_clear") is False:
        blockers.append("active_position_or_open_order_conflict")

    blockers.extend(
        _required_fact_blockers(
            control_state,
            event_spec_id=str(event_spec.get("event_spec_id") or ""),
            fact_values=_as_dict(action_time_fact.get("fact_values")),
        )
    )
    protection_ref_type = str(event_spec.get("protection_ref_type") or "")
    if not protection_ref_type:
        blockers.append("protection_ref_type_missing")
    elif _decimal(_as_dict(action_time_fact.get("fact_values")).get(protection_ref_type)) <= 0:
        blockers.append(f"protection_reference_fact_missing:{protection_ref_type}")
    if _tp1_price(action_time_fact=action_time_fact) <= 0:
        blockers.append("tp1_reference_missing")

    if _decimal(policy.get("planned_stop_risk_fraction")) <= 0:
        blockers.append("policy_planned_stop_risk_fraction_invalid")
    if _decimal(policy.get("max_initial_margin_utilization")) <= 0:
        blockers.append("policy_max_initial_margin_utilization_invalid")
    if int(policy.get("max_leverage") or 0) <= 0:
        blockers.append("policy_max_leverage_invalid")
    if account_id == "":
        blockers.append("account_id_missing")

    return _dedupe(blockers)


def _invocation_coverage_identity_blockers(
    *,
    coverage: dict[str, Any],
    expected_lane_identity: RuntimeLaneIdentity | None,
) -> list[str]:
    """Require watcher coverage to prove the Invocation's exact runtime lane.

    Coverage is an independent watcher observation, so its watermark must be
    present but need not equal the signal watermark.  The immutable lane
    identity, however, must match exactly; a label-level symbol/side match is
    not sufficient evidence to create a Ticket.
    """

    if expected_lane_identity is None:
        return [
            "runtime_lane_identity_mismatch:invocation_coverage_expected_identity_missing"
        ]
    if not str(coverage.get("source_watermark") or "").strip():
        return ["runtime_coverage_source_watermark_missing"]
    try:
        actual_lane_identity = RuntimeLaneIdentity.model_validate(
            {
                field: coverage.get(field)
                for field in RuntimeLaneIdentity.model_fields
            }
        )
    except (TypeError, ValueError):
        return ["runtime_lane_identity_mismatch:coverage_typed_identity"]
    if (
        str(coverage.get("lane_identity_key") or "")
        != actual_lane_identity.identity_key
    ):
        return ["runtime_lane_identity_mismatch:coverage_identity_key"]
    try:
        require_runtime_lane_identity_match(
            expected=expected_lane_identity,
            actual=actual_lane_identity,
            boundary="invocation_to_coverage",
        )
    except RuntimeLaneIdentityMismatch as exc:
        return [str(exc)]
    return []


def _promotion_row(
    bundle: CandidateBundle,
    *,
    now_ms: int,
    status: str,
    arbitration_rank: int | None,
    closed_at_ms: int | None,
    allocation: dict[str, Any],
) -> dict[str, Any]:
    expires_at_ms = min(
        int(bundle.signal.get("expires_at_ms") or 0),
        int(bundle.public_fact.get("valid_until_ms") or 0),
        int(bundle.action_time_fact.get("valid_until_ms") or 0),
    )
    if expires_at_ms <= 0:
        expires_at_ms = int(bundle.signal.get("expires_at_ms") or now_ms)
    requested_risk_at_stop = _requested_risk_at_stop(bundle)
    selected = (
        str(allocation.get("selected_promotion_candidate_id") or "")
        == bundle.promotion_candidate_id
    )
    allocation_state = (
        "ineligible"
        if status == "blocked"
        else "selected"
        if selected
        else "deferred"
    )
    row = {
        "promotion_candidate_id": bundle.promotion_candidate_id,
        "signal_event_id": str(bundle.signal["signal_event_id"]),
        "readiness_row_id": str(bundle.readiness.get("readiness_row_id") or ""),
        "strategy_group_id": str(bundle.candidate["strategy_group_id"]),
        "symbol": str(bundle.candidate["symbol"]),
        "side": str(bundle.candidate["side"]),
        "promotion_scope": "live_submit_candidate",
        "status": status,
        "scope_state": str(bundle.readiness.get("scope_state") or bundle.candidate.get("scope_state") or ""),
        "risk_state": str(bundle.readiness.get("risk_state") or ""),
        "facts_snapshot_id": str(bundle.public_fact.get("fact_snapshot_id") or ""),
        "blockers": list(bundle.blockers),
        "arbitration_rank": arbitration_rank,
        "allocation_decision_id": allocation["allocation_decision_id"],
        "allocation_rank": arbitration_rank,
        "requested_risk_at_stop": requested_risk_at_stop
        if requested_risk_at_stop > 0
        else None,
        "allocated_risk_at_stop": requested_risk_at_stop
        if selected and requested_risk_at_stop > 0
        else Decimal("0")
        if status != "blocked"
        else None,
        "allocation_state": allocation_state,
        "created_at_ms": now_ms,
        "expires_at_ms": expires_at_ms,
        "closed_at_ms": closed_at_ms,
        "authority_boundary": PROMOTION_AUTHORITY_BOUNDARY,
        "signal_grade": str(bundle.signal["signal_grade"]),
        "required_execution_mode": str(bundle.signal["required_execution_mode"]),
        "execution_eligible": bool(bundle.signal["execution_eligible"]),
        "authority_source_ref": str(bundle.signal["authority_source_ref"]),
    }
    if bundle.source_lineage is not None:
        row.update(bundle.source_lineage.model_dump(mode="json"))
    if bundle.action_time_invocation_id is not None:
        row["action_time_invocation_id"] = bundle.action_time_invocation_id
    return row


def _allocation_decision_row(
    *,
    bundles: list[CandidateBundle],
    eligible: list[CandidateBundle],
    selected: CandidateBundle | None,
    now_ms: int,
) -> dict[str, Any]:
    cycle_identity = "|".join(
        sorted(
            str(bundle.signal.get("signal_event_id") or bundle.promotion_candidate_id)
            for bundle in bundles
        )
    )
    cycle_ref = _stable_id("allocation_cycle", cycle_identity)
    selected_id = selected.promotion_candidate_id if selected else None
    capital_scope_ref = (
        f"account:{selected.account_id}"
        if selected and selected.account_id
        else "no_selected_capital_scope"
    )
    return {
        "allocation_decision_id": _stable_id(
            "allocation_decision",
            cycle_ref,
            "allocation-policy-v0",
        ),
        "allocation_policy_version": "allocation-policy-v0",
        "arbitration_cycle_ref": cycle_ref,
        "max_new_action_time_lanes": 1,
        "eligible_candidate_count": len(eligible),
        "selected_candidate_count": 1 if selected else 0,
        "capital_scope_ref": capital_scope_ref,
        "selected_promotion_candidate_id": selected_id,
        "created_at_ms": now_ms,
    }


def _requested_risk_at_stop(bundle: CandidateBundle) -> Decimal:
    decision = bundle.sizing_risk_decision
    return decision.planned_stop_risk if decision is not None else Decimal("0")


def _sizing_risk_decision_result(
    bundle: CandidateBundle,
    *,
    now_ms: int,
):
    pricing_result = pricing_reference_from_action_time_fact_values(
        _as_dict(bundle.action_time_fact.get("fact_values"))
    )
    if pricing_result.reference is None:
        return None, list(pricing_result.blockers)
    protection = _protection_row(bundle)
    pricing = pricing_result.reference
    account_values = _as_dict(bundle.account_safe_fact.get("fact_values"))
    leverage_by_symbol = _as_dict(
        account_values.get("exchange_max_leverage_by_symbol")
    )
    try:
        exchange_max_leverage = int(
            leverage_by_symbol.get(str(bundle.candidate.get("symbol") or ""))
            or 0
        )
    except (TypeError, ValueError):
        exchange_max_leverage = 0
    if not 1 <= exchange_max_leverage <= 125:
        return None, ["exchange_leverage_bracket_missing_or_invalid"]
    try:
        policy = ExecutionSizingPolicy(
            planned_stop_risk_fraction=_decimal(
                bundle.policy.get("planned_stop_risk_fraction")
            ),
            max_initial_margin_utilization=_decimal(
                bundle.policy.get("max_initial_margin_utilization")
            ),
            max_leverage=int(bundle.policy.get("max_leverage") or 0),
            policy_version=bundle.owner_policy_version,
        )
        account = ExecutionAccountCapacity(
            total_wallet_balance=_decimal(
                account_values.get("total_wallet_balance")
            ),
            available_balance=_decimal(account_values.get("available_balance")),
            source_fact_snapshot_id=str(
                bundle.account_safe_fact.get("fact_snapshot_id") or ""
            ),
            observed_at_ms=int(
                bundle.account_safe_fact.get("observed_at_ms") or 0
            ),
            valid_until_ms=int(
                bundle.account_safe_fact.get("valid_until_ms") or 0
            ),
        )
        rules = ExecutionInstrumentRules(
            symbol=str(bundle.candidate.get("symbol") or ""),
            side=pricing.side,
            entry_reference_price=pricing.entry_reference_price,
            min_qty=pricing.min_qty,
            qty_step=pricing.qty_step,
            min_notional=pricing.min_notional,
            exchange_max_leverage=exchange_max_leverage,
            source_fact_snapshot_id=pricing.source_fact_snapshot_id,
            observed_at_ms=pricing.observed_at_ms,
            valid_until_ms=pricing.valid_until_ms,
        )
    except (TypeError, ValueError) as exc:
        return None, [f"dynamic_execution_sizing_input_invalid:{exc}"]
    result = decide_execution_sizing(
        rules=rules,
        account=account,
        policy=policy,
        protective_stop_price=_decimal(protection.get("reference_price")),
        now_ms=now_ms,
    )
    return result.decision, list(result.blockers)


def _apply_allocation_capital_scope(
    bundles: list[CandidateBundle],
    *,
    now_ms: int,
) -> list[CandidateBundle]:
    guarded: list[CandidateBundle] = []
    for bundle in bundles:
        blockers = list(bundle.blockers)
        decision, decision_blockers = _sizing_risk_decision_result(
            bundle,
            now_ms=now_ms,
        )
        blockers.extend(decision_blockers)
        guarded.append(
            replace(
                bundle,
                blockers=tuple(_dedupe(blockers)),
                sizing_risk_decision=decision,
            )
        )
    return guarded


def _lane_row(bundle: CandidateBundle, *, now_ms: int) -> dict[str, Any]:
    expires_at_ms = min(
        int(bundle.signal["expires_at_ms"]),
        int(bundle.public_fact["valid_until_ms"]),
        int(bundle.action_time_fact["valid_until_ms"]),
        int(bundle.account_safe_fact["valid_until_ms"]),
        int(bundle.account_mode_fact["valid_until_ms"]),
    )
    row = {
        "action_time_lane_input_id": bundle.action_time_lane_input_id,
        "promotion_candidate_id": bundle.promotion_candidate_id,
        "strategy_group_id": str(bundle.candidate["strategy_group_id"]),
        "symbol": str(bundle.candidate["symbol"]),
        "side": str(bundle.candidate["side"]),
        "runtime_profile_id": str(bundle.runtime_scope["runtime_profile_id"]),
        "lane_scope": "real_submit_candidate",
        "status": "ticket_pending",
        "signal_event_id": str(bundle.signal["signal_event_id"]),
        "public_fact_snapshot_id": str(bundle.public_fact["fact_snapshot_id"]),
        "action_time_fact_snapshot_id": str(bundle.action_time_fact["fact_snapshot_id"]),
        "runtime_scope_binding_id": str(bundle.runtime_scope["runtime_scope_binding_id"]),
        "candidate_authorization_ref": f"candidate_auth:{bundle.promotion_candidate_id}",
        "runtime_safety_snapshot_id": None,
        "first_blocker_class": "action_time_preflight_ready",
        "created_at_ms": now_ms,
        "expires_at_ms": expires_at_ms,
        "closed_at_ms": None,
        "authority_boundary": LANE_AUTHORITY_BOUNDARY,
        "signal_grade": str(bundle.signal["signal_grade"]),
        "required_execution_mode": str(bundle.signal["required_execution_mode"]),
        "execution_eligible": bool(bundle.signal["execution_eligible"]),
        "authority_source_ref": str(bundle.signal["authority_source_ref"]),
    }
    if bundle.source_lineage is not None:
        row.update(bundle.source_lineage.model_dump(mode="json"))
    if bundle.action_time_invocation_id is not None:
        row.update(
            {
                "action_time_invocation_id": bundle.action_time_invocation_id,
                "account_safe_fact_snapshot_id": str(
                    bundle.account_safe_fact["fact_snapshot_id"]
                ),
                "account_mode_fact_snapshot_id": str(
                    bundle.account_mode_fact["fact_snapshot_id"]
                ),
            }
        )
    return row


def _budget_row(bundle: CandidateBundle, *, now_ms: int) -> dict[str, Any]:
    decision = bundle.sizing_risk_decision
    if decision is None:
        raise ValueError("selected promotion has no sizing/risk decision")
    target_notional = decision.effective_notional
    leverage = Decimal(decision.selected_leverage)
    reserved_margin = decision.reserved_margin
    return {
        "budget_reservation_id": bundle.budget_reservation_id,
        "promotion_candidate_id": bundle.promotion_candidate_id,
        "action_time_lane_input_id": bundle.action_time_lane_input_id,
        "ticket_id": None,
        "signal_event_id": str(bundle.signal["signal_event_id"]),
        "event_spec_id": str(bundle.event_spec["event_spec_id"]),
        "runtime_profile_id": str(bundle.runtime_scope["runtime_profile_id"]),
        "account_id": bundle.account_id,
        "strategy_group_id": str(bundle.candidate["strategy_group_id"]),
        "symbol": str(bundle.candidate["symbol"]),
        "side": str(bundle.candidate["side"]),
        "target_notional": target_notional,
        "leverage": leverage,
        "effective_notional": target_notional,
        "selected_leverage": int(decision.selected_leverage),
        "planned_stop_risk_budget": decision.planned_stop_risk_budget,
        "planned_stop_risk": decision.planned_stop_risk,
        "reserved_margin": reserved_margin,
        "entry_reference_price": decision.entry_reference_price,
        "stop_price": decision.protective_stop_price,
        "intended_qty": decision.intended_qty,
        "risk_at_stop": decision.planned_stop_risk,
        "risk_reservation_basis": decision.risk_reservation_basis,
        "reserved_at_ms": now_ms,
        "expires_at_ms": min(
            int(bundle.signal["expires_at_ms"]),
            int(bundle.action_time_fact["valid_until_ms"]),
            decision.valid_until_ms,
        ),
        "status": "active",
        "release_reason": None,
        "policy_version": bundle.owner_policy_version,
    }


def _protection_row(bundle: CandidateBundle) -> dict[str, Any]:
    fact_values = _as_dict(bundle.action_time_fact.get("fact_values"))
    reference_type = str(bundle.event_spec["protection_ref_type"])
    return {
        "protection_ref_id": bundle.protection_ref_id,
        "event_spec_id": str(bundle.event_spec["event_spec_id"]),
        "strategy_group_id": str(bundle.candidate["strategy_group_id"]),
        "symbol": str(bundle.candidate["symbol"]),
        "side": str(bundle.candidate["side"]),
        "reference_type": reference_type,
        "reference_price": _decimal(fact_values.get(reference_type)),
        "invalidation_condition": f"invalidate_if_price_crosses_{reference_type}",
        "stop_order_type": "stop_market",
        "stop_time_in_force": "GTC",
        "protection_policy_version": bundle.owner_policy_version,
        "source_fact_snapshot_id": str(bundle.action_time_fact["fact_snapshot_id"]),
        "expires_at_ms": int(bundle.action_time_fact["valid_until_ms"]),
    }


def _tp1_price(*, action_time_fact: dict[str, Any]) -> Decimal:
    fact_values = _as_dict(action_time_fact.get("fact_values"))
    for key in (
        "take_profit_1",
        "tp1_price",
        "tp1_reference_price",
        "first_take_profit_price",
    ):
        value = _decimal(fact_values.get(key))
        if value > 0:
            return value
    return Decimal("0")


def _fresh_signal_for_candidate(
    control_state: dict[str, Any],
    *,
    candidate: dict[str, Any],
    event_spec: dict[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    rows = []
    for row in _rows(control_state.get("live_signal_events")):
        if not is_current_live_signal(row, now_ms):
            continue
        if str(row.get("candidate_scope_id") or "") != str(candidate.get("candidate_scope_id") or ""):
            continue
        if str(row.get("event_spec_id") or "") != str(event_spec.get("event_spec_id") or ""):
            continue
        if _lane_key(row) != _lane_key(candidate):
            continue
        rows.append(row)
    if not rows:
        return {}
    return sorted(rows, key=lambda row: int(row.get("observed_at_ms") or 0))[-1]


def _open_real_submit_lanes(control_state: dict[str, Any]) -> list[dict[str, Any]]:
    now_ms = _control_state_now_ms(control_state)
    return [
        row
        for row in _rows(control_state.get("action_time_lane_inputs"))
        if is_current_action_time_lane(row, now_ms)
    ]


def _control_state_now_ms(control_state: dict[str, Any]) -> int:
    try:
        value = int(control_state.get("read_now_ms") or 0)
    except (TypeError, ValueError):
        value = 0
    if value > 0:
        return value
    return int(time.time() * 1000)


def _active_candidate_rows(control_state: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        [
            row
            for row in _rows(control_state.get("candidate_scope"))
            if row.get("status") == "active"
        ],
        key=_candidate_sort_key,
    )


def _active_by(
    control_state: dict[str, Any],
    table_key: str,
    key_name: str,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in _rows(control_state.get(table_key)):
        if row.get("status") != "active":
            continue
        key = str(row.get(key_name) or "")
        if key:
            result[key] = row
    return result


def _current_coverage_by_lane(control_state: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    result: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in _rows(control_state.get("watcher_runtime_coverage")):
        if row.get("is_current") is not True:
            continue
        result[_lane_key(row)] = row
    return result


def _fact_by_id(control_state: dict[str, Any], fact_snapshot_id: str) -> dict[str, Any]:
    if not fact_snapshot_id:
        return {}
    return next(
        (
            row
            for row in _rows(control_state.get("runtime_fact_snapshots"))
            if row.get("fact_snapshot_id") == fact_snapshot_id
        ),
        {},
    )


def _latest_fact(
    control_state: dict[str, Any],
    *,
    candidate: dict[str, Any],
    runtime_profile_id: str,
    fact_surface: str,
    allow_global: bool = False,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for row in _rows(control_state.get("runtime_fact_snapshots")):
        if row.get("fact_surface") != fact_surface:
            continue
        if not _fact_scope_matches(
            row,
            candidate=candidate,
            runtime_profile_id=runtime_profile_id,
            allow_global=allow_global,
        ):
            continue
        rows.append(row)
    if not rows:
        return {}
    return sorted(rows, key=lambda row: int(row.get("observed_at_ms") or 0))[-1]


def _fact_scope_matches(
    row: dict[str, Any],
    *,
    candidate: dict[str, Any],
    runtime_profile_id: str,
    allow_global: bool,
) -> bool:
    for key in ("strategy_group_id", "symbol", "side"):
        value = row.get(key)
        if value is None and allow_global:
            continue
        if value is not None and str(value or "") != str(candidate.get(key) or ""):
            return False
    value = row.get("runtime_profile_id")
    if value is None and allow_global:
        return True
    return str(value or "") == runtime_profile_id


def _owner_policy_version_by_id(control_state: dict[str, Any]) -> dict[str, str]:
    events = {
        str(row.get("policy_event_id") or ""): row
        for row in _rows(control_state.get("owner_policy_events"))
    }
    result: dict[str, str] = {}
    for policy in _rows(control_state.get("owner_policy_current")):
        policy_current_id = str(policy.get("policy_current_id") or "")
        for policy_event_id in _as_list(policy.get("policy_event_ids")):
            version = str(events.get(str(policy_event_id), {}).get("policy_version") or "")
            if version:
                result[policy_current_id] = version
                break
    return result


def _required_fact_blockers(
    control_state: dict[str, Any],
    *,
    event_spec_id: str,
    fact_values: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    for row in _rows(control_state.get("strategy_event_required_facts")):
        if row.get("event_spec_id") != event_spec_id:
            continue
        if row.get("status") != "current" or row.get("required_for_promotion") is not True:
            continue
        fact_key = str(row.get("fact_key") or "")
        satisfied = _fact_condition_satisfied(row, fact_values)
        if row.get("disable_on_match") is True:
            if _disable_fact_unknown(fact_key, fact_values):
                blockers.append(f"disable_fact_missing:{fact_key}")
                continue
            if satisfied:
                blockers.append(f"disable_fact_active:{fact_key}")
            continue
        if not satisfied:
            blockers.append(f"required_fact_not_satisfied:{fact_key}")
    return blockers


def _disable_fact_unknown(fact_key: str, fact_values: dict[str, Any]) -> bool:
    if fact_key not in fact_values:
        return True
    observed = fact_values.get(fact_key)
    if observed is None:
        return True
    if isinstance(observed, str) and observed.strip().lower() in {
        "",
        "unknown",
        "missing",
        "null",
    }:
        return True
    return False


def _fact_condition_satisfied(row: dict[str, Any], fact_values: dict[str, Any]) -> bool:
    fact_key = str(row.get("fact_key") or "")
    operator = str(row.get("operator") or "")
    observed = fact_values.get(fact_key)
    expected = row.get("expected_value")
    if operator == "exists":
        return observed is not None
    if operator == "not_exists":
        return observed is None
    if operator == "eq":
        return _normalized_scalar(observed) == _normalized_scalar(expected)
    if operator == "neq":
        return _normalized_scalar(observed) != _normalized_scalar(expected)
    if operator in {"gt", "gte", "lt", "lte"}:
        observed_dec = _decimal(observed)
        expected_dec = _decimal(expected)
        if operator == "gt":
            return observed_dec > expected_dec
        if operator == "gte":
            return observed_dec >= expected_dec
        if operator == "lt":
            return observed_dec < expected_dec
        return observed_dec <= expected_dec
    if operator == "in":
        return isinstance(expected, list) and observed in expected
    if operator == "not_in":
        return isinstance(expected, list) and observed not in expected
    if operator == "expr_ref":
        return observed is True
    return False


def _normalized_scalar(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text.lower() == "true":
        return True
    if text.lower() == "false":
        return False
    if text.lower() == "null":
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def _assert_fact_ready(
    blockers: list[str],
    label: str,
    fact: dict[str, Any],
    *,
    now_ms: int,
) -> None:
    if not fact:
        blockers.append(f"{label}_snapshot_missing")
        return
    if fact.get("computed") is not True:
        blockers.append(f"{label}_not_computed")
    if fact.get("satisfied") is not True:
        blockers.append(f"{label}_not_satisfied")
    if fact.get("freshness_state") != "fresh":
        blockers.append(f"{label}_not_fresh")
    if int(fact.get("valid_until_ms") or 0) <= now_ms:
        blockers.append(f"{label}_expired")


def _require_identity_match(
    blockers: list[str],
    candidate: dict[str, Any],
    row: dict[str, Any],
    label: str,
    *,
    keys: tuple[str, ...] = ("strategy_group_id", "symbol", "side"),
) -> None:
    if not row:
        blockers.append(f"{label}_missing")
        return
    for key in keys:
        if key in row and str(row.get(key) or "") != str(candidate.get(key) or ""):
            blockers.append(f"{label}_mismatch:{key}")


def _select_winner(candidates: list[CandidateBundle]) -> CandidateBundle | None:
    ranked = _ranked_candidates(candidates)
    return ranked[0] if ranked else None


def _ranked_candidates(candidates: list[CandidateBundle]) -> list[CandidateBundle]:
    return sorted(candidates, key=_bundle_sort_key)


def _bundle_sort_key(bundle: CandidateBundle) -> tuple[int, int, int, str, str]:
    return (
        _strategy_priority(str(bundle.candidate.get("strategy_group_id") or "")),
        int(bundle.candidate.get("priority_rank") or 999),
        -int(bundle.signal.get("observed_at_ms") or 0),
        str(bundle.candidate.get("symbol") or ""),
        str(bundle.candidate.get("side") or ""),
    )


def _candidate_sort_key(row: dict[str, Any]) -> tuple[int, int, str, str]:
    return (
        _strategy_priority(str(row.get("strategy_group_id") or "")),
        int(row.get("priority_rank") or 999),
        str(row.get("symbol") or ""),
        str(row.get("side") or ""),
    )


def _strategy_priority(strategy_group_id: str) -> int:
    try:
        return list(WIP_LANES).index(strategy_group_id)
    except ValueError:
        return 999


def _account_id(control_state: dict[str, Any], candidate: dict[str, Any]) -> str:
    version_id = ""
    for group in _rows(control_state.get("strategy_groups")):
        if group.get("strategy_group_id") == candidate.get("strategy_group_id"):
            version_id = str(group.get("current_version_id") or "")
            break
    version = next(
        (
            row
            for row in _rows(control_state.get("strategy_group_versions"))
            if row.get("strategy_group_version_id") == version_id
        ),
        {},
    )
    return str(_as_dict(version.get("risk_envelope")).get("account_id") or "")


def _candidate_results(
    bundles: list[CandidateBundle],
    *,
    selected: CandidateBundle | None,
) -> list[dict[str, Any]]:
    selected_id = selected.promotion_candidate_id if selected else ""
    return [
        {
            "strategy_group_id": str(bundle.candidate.get("strategy_group_id") or ""),
            "symbol": str(bundle.candidate.get("symbol") or ""),
            "side": str(bundle.candidate.get("side") or ""),
            "signal_event_id": str(bundle.signal.get("signal_event_id") or ""),
            "promotion_candidate_id": bundle.promotion_candidate_id,
            "action_time_lane_input_id": bundle.action_time_lane_input_id
            if bundle.promotion_candidate_id == selected_id
            else "",
            "status": "selected"
            if bundle.promotion_candidate_id == selected_id
            else "blocked"
            if bundle.blockers
            else "arbitration_lost",
            "blockers": list(bundle.blockers),
        }
        for bundle in _ranked_candidates(bundles)
    ]


def _result(status: str, *, now_ms: int, blockers: list[str], next_action: str, **extra: Any) -> dict[str, Any]:
    return {
        "schema": "brc.pg_promotion_action_time_lane_materialization.v1",
        "status": status,
        "generated_at_ms": now_ms,
        "blockers": blockers,
        "next_action": next_action,
        "forbidden_effects": FORBIDDEN_EFFECTS,
        "authority_boundary": (
            "pg_promotion_action_time_lane_materializer; "
            "no_finalgate_no_operation_layer_no_exchange_write"
        ),
        **extra,
    }


def _upsert_row(
    conn: sa.engine.Connection,
    table_name: str,
    pk_name: str,
    row: dict[str, Any],
) -> None:
    metadata = sa.MetaData()
    table = sa.Table(table_name, metadata, autoload_with=conn)
    pk = table.c[pk_name]
    values = {key: value for key, value in row.items() if key in table.c}
    existing = conn.execute(
        sa.select(pk).where(pk == row[pk_name]).limit(1)
    ).scalar_one_or_none()
    if existing is None:
        conn.execute(table.insert().values(**values))
    else:
        conn.execute(table.update().where(pk == row[pk_name]).values(**values))


def _lane_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("strategy_group_id") or ""),
        str(row.get("symbol") or ""),
        str(row.get("side") or ""),
    )


def _stable_id(prefix: str, *parts: str) -> str:
    raw = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    readable = ":".join(_safe_id_part(part) for part in parts if part)[:120]
    return f"{prefix}:{readable}:{digest}" if readable else f"{prefix}:{digest}"


def _safe_id_part(value: str) -> str:
    return (
        str(value)
        .replace("/", "_")
        .replace(":", "_")
        .replace(" ", "_")
        .replace("\\", "_")
    )


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("-1")


def _dedupe(values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "")
        if text and text not in result:
            result.append(text)
    return result


def _rows(value: Any) -> list[dict[str, Any]]:
    return [item for item in _as_list(value) if isinstance(item, dict)]


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return []
        return decoded if isinstance(decoded, list) else []
    return []


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


if __name__ == "__main__":
    raise SystemExit(main())
