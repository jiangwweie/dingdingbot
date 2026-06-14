#!/usr/bin/env python3
"""Build an Owner-readable StrategyGroup runtime pilot status packet.

This is a read-only product layer over StrategyGroup intake, live-facts
readiness, and runtime signal watcher evidence. It never creates candidates,
grants authorization, calls exchange write APIs, mutates PG, or places orders.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.application.runtime_strategy_signal_evaluation_service import (
    RuntimeStrategySignalEvaluationService,
)
from src.domain.strategy_semantics import initial_strategy_semantics_catalog


PREFERRED_GROUP_ID = "MPG-001"
FALLBACK_GROUP_ID = "TEQ-001"
DEFAULT_MAX_SYMBOLS = 3
UNSAFE_FLAGS = {
    "exchange_write_called",
    "order_created",
    "order_lifecycle_called",
    "execution_intent_created",
    "runtime_budget_mutated",
    "withdrawal_or_transfer_created",
}
ACTIVE_POSITION_STATUSES = {
    "active_position_present",
    "position_present",
    "not_flat",
}
OPEN_ORDER_STATUSES = {
    "open_orders_present",
    "open_order_present",
    "has_open_orders",
}


def _read_json(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value or [] if isinstance(item, dict)]


def _by_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item.get("strategy_group_id")): item for item in rows}


def _status(value: Any) -> str:
    return str(value or "unknown").strip().lower()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_symbol(value: Any) -> str:
    text = str(value or "").strip().upper()
    if ":" in text:
        text = text.split(":", 1)[0]
    return text.replace("/", "").replace("-", "").replace("_", "")


def _normalize_side(value: Any) -> str:
    return str(value or "").strip().lower()


def _candidate_checks(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("live_fact_key") or item.get("fact_key")): item
        for item in _items(row.get("candidate_fact_checks"))
    }


def _selected_symbols(
    *,
    group: dict[str, Any],
    readiness: dict[str, Any],
    max_symbols: int,
) -> list[str]:
    supported = [str(item) for item in group.get("supported_symbols") or []]
    ready_symbols = set(
        str(item)
        for item in ((readiness.get("exchange_rules") or {}).get("ready_symbols") or [])
    )
    selected = [symbol for symbol in supported if symbol in ready_symbols]
    if not selected:
        selected = supported
    return selected[:max_symbols]


def _selection_rank(
    *,
    group_id: str,
    readiness: dict[str, Any],
) -> tuple[int, int, int, int]:
    observe_penalty = 0 if readiness.get("observe_ready") else 10
    candidate_penalty = len(readiness.get("blockers") or [])
    preference = {PREFERRED_GROUP_ID: 0, FALLBACK_GROUP_ID: 1}.get(group_id, 5)
    ready_count = len((readiness.get("exchange_rules") or {}).get("ready_symbols") or [])
    return (observe_penalty, candidate_penalty, preference, -ready_count)


def _select_pilot(
    *,
    intake_packet: dict[str, Any],
    live_facts_readiness: dict[str, Any],
    requested_group_id: str | None,
) -> tuple[dict[str, Any] | None, dict[str, Any], str]:
    groups = _by_id(_items(intake_packet.get("strategy_picker")))
    readiness_by_id = _by_id(_items(live_facts_readiness.get("readiness")))
    if requested_group_id:
        group = groups.get(requested_group_id)
        return (
            group,
            readiness_by_id.get(requested_group_id, {}),
            "owner_requested_strategy_group",
        )

    preferred = groups.get(PREFERRED_GROUP_ID)
    fallback = groups.get(FALLBACK_GROUP_ID)
    preferred_readiness = readiness_by_id.get(PREFERRED_GROUP_ID, {})
    fallback_readiness = readiness_by_id.get(FALLBACK_GROUP_ID, {})
    if preferred and fallback:
        preferred_rank = _selection_rank(
            group_id=PREFERRED_GROUP_ID,
            readiness=preferred_readiness,
        )
        fallback_rank = _selection_rank(
            group_id=FALLBACK_GROUP_ID,
            readiness=fallback_readiness,
        )
        if fallback_rank < preferred_rank:
            return fallback, fallback_readiness, "fallback_teq_has_better_engineering_readiness"
        return preferred, preferred_readiness, "default_mpg_engineering_readiness_not_worse"
    if preferred:
        return preferred, preferred_readiness, "default_mpg_available"
    if fallback:
        return fallback, fallback_readiness, "fallback_teq_available"

    candidates = [
        (
            _selection_rank(
                group_id=str(group.get("strategy_group_id")),
                readiness=readiness_by_id.get(str(group.get("strategy_group_id")), {}),
            ),
            group,
        )
        for group in groups.values()
    ]
    if not candidates:
        return None, {}, "no_strategy_group_available"
    _rank, group = sorted(candidates, key=lambda item: item[0])[0]
    group_id = str(group.get("strategy_group_id"))
    return group, readiness_by_id.get(group_id, {}), "first_engineering_ready_group"


def _watcher_state(watcher_status: dict[str, Any]) -> dict[str, Any]:
    data = (
        watcher_status.get("data")
        if isinstance(watcher_status.get("data"), dict)
        else watcher_status
    )
    if data.get("scope") == "runtime_signal_watcher_post_signal_resume_pack":
        post_signal_auto_resume = _dict(data.get("post_signal_auto_resume"))
        prepared_evidence = _dict(data.get("prepared_evidence"))
        signal_input_json = (
            data.get("signal_input_json")
            or prepared_evidence.get("signal_input_json")
            or post_signal_auto_resume.get("signal_input_json")
        )
        prepared_authorization_id = (
            data.get("prepared_authorization_id")
            or prepared_evidence.get("prepared_authorization_id")
            or post_signal_auto_resume.get("prepared_authorization_id")
        )
        shadow_candidate_id = (
            data.get("shadow_candidate_id")
            or prepared_evidence.get("shadow_candidate_id")
            or post_signal_auto_resume.get("shadow_candidate_id")
        )
        safety = (
            data.get("safety_invariants")
            if isinstance(data.get("safety_invariants"), dict)
            else {}
        )
        unsafe_flags = list(safety.get("forbidden_effect_flags") or [])
        unsafe_flags.extend(
            name for name in sorted(UNSAFE_FLAGS)
            if safety.get(name) not in {False, None}
        )
        return {
            "deployment_status": (
                "ready"
                if data.get("status") != "blocked"
                else "unsafe_watcher_effect_detected"
            ),
            "wakeup_status": str(data.get("current_wakeup_status") or "unknown"),
            "operator_status": str(data.get("current_operator_status") or "unknown"),
            "status_packet_status": "unknown",
            "can_continue_steps_5_8": bool(data.get("can_continue_steps_5_8")),
            "current_gate": (
                "fresh_signal_or_prepared_shadow_ready"
                if data.get("can_continue_steps_5_8")
                else "waiting_for_fresh_strategy_signal"
            ),
            "blockers": list(data.get("blockers") or []),
            "warnings": list(data.get("warnings") or []),
            "unsafe_flags": sorted(set(str(item) for item in unsafe_flags if item)),
            "runtime_signal_summaries": _items(
                data.get("runtime_signal_summaries")
                or data.get("selected_runtime_signal_summaries")
            ),
            "signal_input_json": signal_input_json,
            "prepared_authorization_id": prepared_authorization_id,
            "shadow_candidate_id": shadow_candidate_id,
            "prepared_evidence": {
                "signal_input_json": signal_input_json,
                "shadow_candidate_id": shadow_candidate_id,
                "prepared_authorization_id": prepared_authorization_id,
                "ready_for_action_time_final_gate": bool(prepared_authorization_id),
            },
            "post_signal_auto_resume": post_signal_auto_resume,
        }
    deployment = (
        data.get("deployment_readiness")
        if isinstance(data.get("deployment_readiness"), dict)
        else {}
    )
    watcher = data.get("watcher") if isinstance(data.get("watcher"), dict) else {}
    status_packet = (
        data.get("status_packet") if isinstance(data.get("status_packet"), dict) else {}
    )
    resume = (
        data.get("post_signal_resume")
        if isinstance(data.get("post_signal_resume"), dict)
        else {}
    )
    post_signal_auto_resume = _dict(
        data.get("post_signal_auto_resume")
        or watcher.get("post_signal_auto_resume")
        or resume.get("post_signal_auto_resume")
    )
    prepared_evidence = _dict(data.get("prepared_evidence") or resume.get("prepared_evidence"))
    signal_input_json = (
        data.get("signal_input_json")
        or resume.get("signal_input_json")
        or prepared_evidence.get("signal_input_json")
        or post_signal_auto_resume.get("signal_input_json")
    )
    prepared_authorization_id = (
        data.get("prepared_authorization_id")
        or resume.get("prepared_authorization_id")
        or prepared_evidence.get("prepared_authorization_id")
        or post_signal_auto_resume.get("prepared_authorization_id")
    )
    shadow_candidate_id = (
        data.get("shadow_candidate_id")
        or resume.get("shadow_candidate_id")
        or prepared_evidence.get("shadow_candidate_id")
        or post_signal_auto_resume.get("shadow_candidate_id")
    )
    safety = (
        data.get("safety_invariants")
        if isinstance(data.get("safety_invariants"), dict)
        else {}
    )
    unsafe_flags = list(safety.get("forbidden_effect_flags") or [])
    unsafe_flags.extend(
        name for name in sorted(UNSAFE_FLAGS)
        if safety.get(name) not in {False, None}
    )
    blockers = list(watcher.get("blockers") or [])
    return {
        "deployment_status": str(deployment.get("status") or "unknown"),
        "wakeup_status": str(watcher.get("wakeup_status") or "unknown"),
        "operator_status": str(watcher.get("operator_status") or "unknown"),
        "status_packet_status": str(watcher.get("status_packet_status") or "unknown"),
        "can_continue_steps_5_8": bool(resume.get("can_continue_steps_5_8")),
        "current_gate": str(resume.get("current_gate") or "unknown"),
        "blockers": blockers,
        "warnings": list(watcher.get("warnings") or []),
        "unsafe_flags": sorted(set(str(item) for item in unsafe_flags if item)),
        "runtime_signal_summaries": _items(
            watcher.get("runtime_signal_summaries")
            or status_packet.get("runtime_signal_summaries")
            or data.get("runtime_signal_summaries")
        ),
        "signal_input_json": signal_input_json,
        "prepared_authorization_id": prepared_authorization_id,
        "shadow_candidate_id": shadow_candidate_id,
        "prepared_evidence": {
            "signal_input_json": signal_input_json,
            "shadow_candidate_id": shadow_candidate_id,
            "prepared_authorization_id": prepared_authorization_id,
            "ready_for_action_time_final_gate": bool(prepared_authorization_id),
        },
        "post_signal_auto_resume": post_signal_auto_resume,
    }


def _has_no_signal_blocker(blockers: list[Any]) -> bool:
    return any("strategy_signal_not_ready" in str(item) for item in blockers)


def _candidate_fact_summary(readiness: dict[str, Any]) -> dict[str, Any]:
    checks = _candidate_checks(readiness)
    active_position_status = _status((checks.get("active_position") or {}).get("status"))
    open_order_status = _status((checks.get("open_orders") or {}).get("status"))
    account_status = _status((checks.get("account") or {}).get("status"))
    return {
        "account_status": account_status,
        "active_position_status": active_position_status,
        "open_order_status": open_order_status,
        "active_position_blocked": active_position_status in ACTIVE_POSITION_STATUSES,
        "open_order_blocked": open_order_status in OPEN_ORDER_STATUSES,
        "candidate_blockers": list(readiness.get("blockers") or []),
    }


def _watcher_scope(group: dict[str, Any] | None) -> dict[str, Any]:
    scope = (
        group.get("watcher_scope")
        if group and isinstance(group.get("watcher_scope"), dict)
        else {}
    )
    return {
        "business_signal_validity": str(
            scope.get("business_signal_validity") or "unknown"
        ),
        "candidate_packet_freshness_seconds": scope.get(
            "candidate_packet_freshness_seconds"
        ),
    }


def _watcher_scope_alignment(
    *,
    selected_universe: list[str],
    selected_side: str,
    watcher: dict[str, Any],
) -> dict[str, Any]:
    summaries = _items(watcher.get("runtime_signal_summaries"))
    selected_symbols = {
        _normalize_symbol(symbol)
        for symbol in selected_universe
        if _normalize_symbol(symbol)
    }
    selected_sides = {
        _normalize_side(selected_side),
    } - {""}

    matched: list[dict[str, Any]] = []
    out_of_scope: list[dict[str, Any]] = []
    for summary in summaries:
        symbol = _normalize_symbol(summary.get("symbol"))
        side = _normalize_side(summary.get("side"))
        row = {
            "runtime_instance_id": summary.get("runtime_instance_id"),
            "strategy_family_id": summary.get("strategy_family_id"),
            "strategy_family_version_id": summary.get("strategy_family_version_id"),
            "symbol": summary.get("symbol"),
            "side": summary.get("side"),
            "status": summary.get("status"),
        }
        if symbol in selected_symbols and (not selected_sides or side in selected_sides):
            matched.append(row)
        else:
            out_of_scope.append(row)

    if not summaries:
        status = "not_visible"
        blocker = None
    elif not matched:
        status = "mismatch"
        blocker = "watcher_not_monitoring_selected_strategygroup_universe"
    elif out_of_scope:
        status = "mixed_scope"
        blocker = "watcher_monitoring_unselected_runtime_scope"
    else:
        status = "aligned"
        blocker = None

    return {
        "status": status,
        "selected_symbols": sorted(selected_symbols),
        "selected_side": sorted(selected_sides)[0] if selected_sides else None,
        "runtime_signal_summary_count": len(summaries),
        "matched_runtime_signal_summary_count": len(matched),
        "out_of_scope_runtime_signal_summary_count": len(out_of_scope),
        "matched_runtime_signal_summaries": matched,
        "out_of_scope_runtime_signal_summaries": out_of_scope[:10],
        "blocker": blocker,
        "automatic_recovery_action": (
            "create_or_attach_selected_strategygroup_runtime_then_constrain_watcher_scope"
            if blocker
            else "continue_selected_pilot_observation"
        ),
        "next_recover_condition": (
            "runtime_signal_watcher_monitors_only_selected_strategygroup_universe_and_side"
            if blocker
            else "watcher_scope_matches_selected_pilot"
        ),
    }


def _strategy_family_version_id(group: dict[str, Any] | None) -> str | None:
    if not group:
        return None
    for key in (
        "strategy_family_version_id",
        "strategy_group_version_id",
        "version_id",
    ):
        value = group.get(key)
        if value:
            return str(value)
    group_id = group.get("strategy_group_id")
    return f"{group_id}-v0" if group_id else None


def _runtime_bridge(group: dict[str, Any] | None) -> dict[str, Any]:
    if not group:
        return {
            "status": "not_selected",
            "strategy_family_id": None,
            "strategy_family_version_id": None,
            "semantics_binding_found": False,
            "evaluator_route_configured": False,
            "blockers": ["strategy_group_not_selected"],
            "automatic_recovery_action": "select_strategy_group",
            "next_recover_condition": "strategy_group_selected",
            "non_executing": True,
        }
    group_id = str(group.get("strategy_group_id"))
    version_id = _strategy_family_version_id(group)
    blockers: list[str] = []
    candidate_mode: str | None = None
    runtime_confirmation_mode: str | None = None
    semantics_binding_found = False
    try:
        binding = initial_strategy_semantics_catalog().get_binding(
            strategy_family_id=group_id,
            strategy_family_version_id=str(version_id),
        )
        semantics_binding_found = True
        candidate_mode = binding.candidate_mode.value
        runtime_confirmation_mode = binding.runtime_confirmation_mode.value
    except KeyError:
        blockers.append("strategy_semantics_binding_missing")

    evaluator_route_configured = RuntimeStrategySignalEvaluationService().route_configured(
        strategy_family_id=group_id,
        strategy_family_version_id=str(version_id),
    )
    if not evaluator_route_configured:
        blockers.append("strategy_evaluator_not_configured")

    status = "configured" if not blockers else "missing"
    return {
        "status": status,
        "strategy_family_id": group_id,
        "strategy_family_version_id": version_id,
        "semantics_binding_found": semantics_binding_found,
        "evaluator_route_configured": evaluator_route_configured,
        "candidate_mode": candidate_mode,
        "runtime_confirmation_mode": runtime_confirmation_mode,
        "blockers": sorted(dict.fromkeys(blockers)),
        "automatic_recovery_action": (
            "continue_to_runtime_scope_alignment"
            if status == "configured"
            else "add_strategy_semantics_binding_and_evaluator_route"
        ),
        "next_recover_condition": (
            "strategy_semantics_binding_and_evaluator_route_are_configured"
        ),
        "non_executing": True,
    }


def _dual_freshness(
    *,
    group: dict[str, Any] | None,
    readiness: dict[str, Any],
    watcher: dict[str, Any],
    owner_state: dict[str, Any],
    candidate_blockers: list[str],
) -> dict[str, Any]:
    scope = _watcher_scope(group)
    signal_status = "fresh" if watcher["can_continue_steps_5_8"] else "missing"
    if owner_state["status"] == "blocked_hard_safety_stop":
        action_time_status = "blocked_hard_safety_stop"
    elif owner_state["status"] == "blocked_active_position_resolution":
        action_time_status = "blocked_live_account_facts"
    elif owner_state["status"] == "blocked_runtime_scope_mismatch":
        action_time_status = "blocked_runtime_scope_mismatch"
    elif owner_state["status"] == "blocked_runtime_bridge_missing":
        action_time_status = "blocked_runtime_bridge_missing"
    elif not watcher["can_continue_steps_5_8"]:
        action_time_status = "not_reached_waiting_for_signal"
    elif readiness.get("armed_candidate_prepare_ready"):
        action_time_status = "ready_for_action_time_final_gate"
    else:
        action_time_status = "pending_required_facts"
    return {
        "strategy_signal": {
            "status": signal_status,
            "freshness_window": scope["business_signal_validity"],
            "candidate_packet_freshness_seconds": scope[
                "candidate_packet_freshness_seconds"
            ],
            "source": "runtime_signal_watcher",
            "current_gate": watcher["current_gate"],
            "blockers": list(watcher["blockers"]),
        },
        "action_time_facts": {
            "status": action_time_status,
            "requires_final_gate": True,
            "requires_official_operation_layer": True,
            "account_position_open_order_scope": "selected_universe",
            "candidate_fact_blockers": candidate_blockers,
            "reason": owner_state["blocked_reason"],
        },
    }


def _gate_row(
    *,
    gate: str,
    status: str,
    blocker_class: str,
    blocked_at: str,
    blocked_reason: str,
    next_recover_condition: str,
    automatic_recovery_action: str,
    downgrade_mode: str,
    hard_stop: bool = False,
    blockers: list[Any] | None = None,
) -> dict[str, Any]:
    return {
        "gate": gate,
        "status": status,
        "blocker_class": blocker_class,
        "blocked_at": blocked_at,
        "blocked_reason": blocked_reason,
        "next_recover_condition": next_recover_condition,
        "automatic_recovery_action": automatic_recovery_action,
        "downgrade_mode": downgrade_mode,
        "hard_stop": hard_stop,
        "owner_visible": status not in {"ready"},
        "blockers": list(blockers or []),
    }


def _gate_failure_ledger(
    *,
    group: dict[str, Any] | None,
    readiness: dict[str, Any],
    watcher: dict[str, Any],
    owner_state: dict[str, Any],
    fact_summary: dict[str, Any],
    candidate_blockers: list[str],
    runtime_bridge: dict[str, Any],
    watcher_scope_alignment: dict[str, Any],
) -> list[dict[str, Any]]:
    no_group = group is None
    account_blocked = (
        fact_summary["active_position_blocked"] or fact_summary["open_order_blocked"]
    )
    signal_ready = bool(watcher["can_continue_steps_5_8"])
    candidate_ready = bool(readiness.get("armed_candidate_prepare_ready"))
    hard_safety_stop = owner_state["status"] == "blocked_hard_safety_stop"
    bridge_blocked = runtime_bridge.get("status") != "configured"
    scope_blocked = owner_state["status"] == "blocked_runtime_scope_mismatch"
    ready_for_final_gate = owner_state["status"] == "ready_for_action_time_final_gate"

    group_status = "blocked" if no_group else "ready"
    bridge_status = "blocked" if bridge_blocked else "ready"
    account_status = "blocked" if account_blocked else "ready"
    watcher_scope_status = "blocked" if scope_blocked else "ready"
    if hard_safety_stop or bridge_blocked or scope_blocked:
        signal_status = "blocked"
    elif signal_ready:
        signal_status = "ready"
    else:
        signal_status = "waiting"
    if candidate_ready:
        required_facts_status = "ready"
    elif signal_ready:
        required_facts_status = "blocked"
    else:
        required_facts_status = "progressive_pending"

    owner_blocked_at = str(owner_state["blocked_at"])
    owner_reason = str(owner_state["blocked_reason"])
    owner_recover = str(owner_state["next_recover_condition"])
    owner_action = str(owner_state["automatic_recovery_action"])
    owner_downgrade = str(owner_state["downgrade_mode"])

    return [
        _gate_row(
            gate="strategy_group_handoff",
            status=group_status,
            blocker_class="missing_fact" if no_group else "none",
            blocked_at="strategy_group_selection" if no_group else "none",
            blocked_reason="no_strategy_group_handoff_available" if no_group else "none",
            next_recover_condition=(
                owner_recover if no_group else "strategy_group_handoff_selected"
            ),
            automatic_recovery_action=(
                owner_action if no_group else "continue_selected_pilot_observation"
            ),
            downgrade_mode=owner_downgrade if no_group else "armed_observation",
            blockers=[],
        ),
        _gate_row(
            gate="live_account_position_open_order",
            status=account_status,
            blocker_class="active_position_resolution" if account_blocked else "none",
            blocked_at="live_account_facts" if account_blocked else "none",
            blocked_reason=owner_reason if account_blocked else "none",
            next_recover_condition=(
                owner_recover
                if account_blocked
                else "account_position_and_open_order_facts_are_flat"
            ),
            automatic_recovery_action=(
                owner_action
                if account_blocked
                else "continue_selected_pilot_observation"
            ),
            downgrade_mode=(
                owner_downgrade if account_blocked else "armed_observation"
            ),
            blockers=[],
        ),
        _gate_row(
            gate="runtime_bridge",
            status=bridge_status,
            blocker_class="missing_fact" if bridge_blocked else "none",
            blocked_at="runtime_bridge" if bridge_blocked else "none",
            blocked_reason=owner_reason if bridge_blocked else "none",
            next_recover_condition=(
                str(runtime_bridge.get("next_recover_condition"))
                if bridge_blocked
                else "strategy_semantics_binding_and_evaluator_route_are_configured"
            ),
            automatic_recovery_action=(
                str(runtime_bridge.get("automatic_recovery_action"))
                if bridge_blocked
                else "continue_selected_pilot_observation"
            ),
            downgrade_mode=(
                owner_downgrade if bridge_blocked else "armed_observation"
            ),
            blockers=runtime_bridge.get("blockers") or [],
        ),
        _gate_row(
            gate="watcher_scope",
            status=watcher_scope_status,
            blocker_class="runtime_scope_mismatch" if scope_blocked else "none",
            blocked_at="runtime_signal_watcher_scope" if scope_blocked else "none",
            blocked_reason=(
                str(watcher_scope_alignment.get("blocker"))
                if scope_blocked
                else "none"
            ),
            next_recover_condition=(
                str(watcher_scope_alignment.get("next_recover_condition"))
                if scope_blocked
                else "watcher_scope_matches_selected_pilot"
            ),
            automatic_recovery_action=(
                str(watcher_scope_alignment.get("automatic_recovery_action"))
                if scope_blocked
                else "continue_selected_pilot_observation"
            ),
            downgrade_mode=(
                "observe_only_no_candidate_prepare"
                if scope_blocked
                else "armed_observation"
            ),
            blockers=(
                [watcher_scope_alignment.get("blocker")]
                if scope_blocked and watcher_scope_alignment.get("blocker")
                else []
            ),
        ),
        _gate_row(
            gate="strategy_signal",
            status=signal_status,
            blocker_class=(
                owner_state["blocker_class"]
                if owner_blocked_at in {
                    "watcher_signal",
                    "watcher_safety_invariants",
                    "runtime_bridge",
                    "runtime_signal_watcher_scope",
                }
                else ("none" if signal_ready else "waiting_for_market")
            ),
            blocked_at="none" if signal_ready else owner_blocked_at,
            blocked_reason="none" if signal_ready else owner_reason,
            next_recover_condition=(
                "fresh_strategy_signal_available" if signal_ready else owner_recover
            ),
            automatic_recovery_action=(
                "continue_to_required_facts_readiness" if signal_ready else owner_action
            ),
            downgrade_mode="armed_observation" if signal_ready else owner_downgrade,
            hard_stop=hard_safety_stop,
            blockers=watcher["blockers"],
        ),
        _gate_row(
            gate="RequiredFacts",
            status=required_facts_status,
            blocker_class="missing_fact" if candidate_blockers else "none",
            blocked_at="RequiredFacts" if candidate_blockers else "none",
            blocked_reason=(
                ",".join(candidate_blockers[:6])
                if candidate_blockers
                else "none"
            ),
            next_recover_condition=(
                "candidate_specific_protection_budget_next_gate_are_ready"
                if candidate_blockers
                else "required_facts_ready_for_candidate_prepare"
            ),
            automatic_recovery_action=(
                "collect_or_prepare_missing_candidate_specific_facts"
                if signal_ready and candidate_blockers
                else "wait_for_fresh_signal_before_candidate_specific_fact_materialization"
                if candidate_blockers
                else "continue_to_shadow_candidate_prepare"
            ),
            downgrade_mode=(
                "observe_only_no_real_submit"
                if candidate_blockers
                else "armed_observation"
            ),
            blockers=candidate_blockers,
        ),
        _gate_row(
            gate="FinalGate",
            status="ready_to_run" if ready_for_final_gate else "not_reached",
            blocker_class="none" if ready_for_final_gate else "not_reached",
            blocked_at="FinalGate",
            blocked_reason=(
                owner_reason
                if ready_for_final_gate
                else "action_time_final_gate_requires_fresh_candidate_authorization"
            ),
            next_recover_condition=(
                owner_recover
                if ready_for_final_gate
                else "fresh_candidate_runtime_grant_authorization_evidence_exists"
            ),
            automatic_recovery_action=(
                owner_action
                if ready_for_final_gate
                else "stop_before_action_time_final_gate_until_candidate_chain_exists"
            ),
            downgrade_mode=(
                owner_downgrade if ready_for_final_gate else "no_real_submit"
            ),
            hard_stop=True,
        ),
        _gate_row(
            gate="Operation Layer",
            status="not_reached",
            blocker_class="not_reached",
            blocked_at="Operation Layer",
            blocked_reason="official_operation_layer_requires_final_gate_pass",
            next_recover_condition="action_time_final_gate_passes_with_current_facts",
            automatic_recovery_action="stop_before_gateway_action_until_final_gate_passes",
            downgrade_mode="no_real_submit",
            hard_stop=True,
        ),
    ]


def _owner_state(
    *,
    selected_group_id: str | None,
    readiness: dict[str, Any],
    watcher: dict[str, Any],
    runtime_bridge: dict[str, Any],
    watcher_scope_alignment: dict[str, Any],
) -> dict[str, Any]:
    fact_summary = _candidate_fact_summary(readiness)
    observe_ready = bool(readiness.get("observe_ready"))
    candidate_ready = bool(readiness.get("armed_candidate_prepare_ready"))
    candidate_blockers = fact_summary["candidate_blockers"]
    auto_resume = _dict(watcher.get("post_signal_auto_resume"))
    if not selected_group_id:
        return {
            "status": "blocked_no_strategy_group",
            "blocker_class": "missing_fact",
            "blocked_at": "strategy_group_selection",
            "blocked_reason": "no_strategy_group_handoff_available",
            "next_recover_condition": (
                "strategy_group_handoff_intake_contains_at_least_one_group"
            ),
            "automatic_recovery_action": "rebuild_strategy_group_handoff_intake",
            "downgrade_mode": "no_runtime_observation",
        }
    if runtime_bridge.get("status") != "configured":
        return {
            "status": "blocked_runtime_bridge_missing",
            "blocker_class": "missing_fact",
            "blocked_at": "runtime_bridge",
            "blocked_reason": ",".join(
                str(item) for item in (runtime_bridge.get("blockers") or [])
            )
            or "strategy_runtime_bridge_missing",
            "next_recover_condition": str(
                runtime_bridge.get("next_recover_condition")
            ),
            "automatic_recovery_action": str(
                runtime_bridge.get("automatic_recovery_action")
            ),
            "downgrade_mode": "observe_only_no_runtime_evaluation",
        }
    if watcher["unsafe_flags"]:
        return {
            "status": "blocked_hard_safety_stop",
            "blocker_class": "hard_safety_stop",
            "blocked_at": "watcher_safety_invariants",
            "blocked_reason": "watcher_evidence_contains_forbidden_effect_flags",
            "next_recover_condition": (
                "forbidden_effect_flags_are_absent_in_current_evidence"
            ),
            "automatic_recovery_action": "stop_resume_path_and_investigate_watcher_evidence",
            "downgrade_mode": "manual_review_only",
        }
    if fact_summary["active_position_blocked"] or fact_summary["open_order_blocked"]:
        reason = (
            "active_position_present"
            if fact_summary["active_position_blocked"]
            else "open_orders_present"
        )
        return {
            "status": "blocked_active_position_resolution",
            "blocker_class": "active_position_resolution",
            "blocked_at": "live_account_facts",
            "blocked_reason": reason,
            "next_recover_condition": (
                "same_symbol_position_and_open_orders_are_flat_or_reconciled"
            ),
            "automatic_recovery_action": (
                "refresh_readonly_account_position_open_order_facts_then_reconcile"
            ),
            "downgrade_mode": "observe_only_no_candidate_prepare",
        }
    if not observe_ready:
        return {
            "status": "blocked_missing_fact",
            "blocker_class": "missing_fact",
            "blocked_at": "exchange_symbol_rules",
            "blocked_reason": "selected_strategy_group_is_not_observe_ready",
            "next_recover_condition": "exchange_rules_are_ready_for_selected_universe",
            "automatic_recovery_action": "refresh_readonly_exchange_rules_for_selected_symbols",
            "downgrade_mode": "no_runtime_observation",
        }
    if watcher["deployment_status"] in {"evidence_missing", "evidence_stale", "unknown"}:
        return {
            "status": "blocked_deployment_issue",
            "blocker_class": "deployment_issue",
            "blocked_at": "runtime_signal_watcher_evidence",
            "blocked_reason": f"watcher_evidence_{watcher['deployment_status']}",
            "next_recover_condition": "watcher_evidence_files_are_present_and_fresh",
            "automatic_recovery_action": (
                "run_or_wait_for_next_watcher_tick_and_rebuild_readiness_pack"
            ),
            "downgrade_mode": "observe_only_no_candidate_prepare",
        }
    if watcher_scope_alignment.get("status") in {"mismatch", "mixed_scope"}:
        return {
            "status": "blocked_runtime_scope_mismatch",
            "blocker_class": "runtime_scope_mismatch",
            "blocked_at": "runtime_signal_watcher_scope",
            "blocked_reason": str(watcher_scope_alignment.get("blocker")),
            "next_recover_condition": str(
                watcher_scope_alignment.get("next_recover_condition")
            ),
            "automatic_recovery_action": str(
                watcher_scope_alignment.get("automatic_recovery_action")
            ),
            "downgrade_mode": "observe_only_no_candidate_prepare",
        }
    if watcher["can_continue_steps_5_8"]:
        if candidate_ready:
            prepared_for_final_gate = (
                watcher.get("prepared_authorization_id")
                or auto_resume.get("status") == "ready_for_action_time_final_gate"
            )
            if prepared_for_final_gate:
                return {
                    "status": "ready_for_action_time_final_gate",
                    "blocker_class": "none",
                    "blocked_at": "FinalGate",
                    "blocked_reason": (
                        auto_resume.get("blocked_reason")
                        or "action_time_final_gate_not_run_yet"
                    ),
                    "next_recover_condition": (
                        auto_resume.get("next_recover_condition")
                        or "official_final_gate_preflight_passes_with_current_facts"
                    ),
                    "automatic_recovery_action": (
                        auto_resume.get("automatic_recovery_action")
                        or "run_official_action_time_final_gate_preflight"
                    ),
                    "downgrade_mode": (
                        auto_resume.get("downgrade_mode")
                        or "no_real_submit_until_final_gate_pass"
                    ),
                }
            return {
                "status": "ready_for_non_executing_prepare",
                "blocker_class": "none",
                "blocked_at": "none",
                "blocked_reason": "none",
                "next_recover_condition": "fresh_signal_already_available",
                "automatic_recovery_action": (
                    auto_resume.get("automatic_recovery_action")
                    or "prepare_shadow_candidate_runtime_grant_authorization_evidence"
                ),
                "downgrade_mode": "armed_observation",
            }
        return {
            "status": "blocked_missing_fact",
            "blocker_class": "missing_fact",
            "blocked_at": "RequiredFacts",
            "blocked_reason": (
                ",".join(candidate_blockers[:6])
                or "candidate_required_facts_missing"
            ),
            "next_recover_condition": "protection_budget_next_attempt_gate_and_account_facts_pass",
            "automatic_recovery_action": "collect_or_prepare_missing_candidate_specific_facts",
            "downgrade_mode": "observe_only_no_real_submit",
        }
    if _has_no_signal_blocker(watcher["blockers"]) or watcher["wakeup_status"] in {
        "operator_packet_needs_review",
        "owner_sleep_safe_observation_running",
        "observation_window_complete_no_signal",
        "unknown",
    }:
        return {
            "status": "waiting_for_market",
            "blocker_class": "waiting_for_market",
            "blocked_at": auto_resume.get("blocked_at") or "watcher_signal",
            "blocked_reason": (
                auto_resume.get("blocked_reason") or "no_fresh_strategy_signal"
            ),
            "next_recover_condition": (
                auto_resume.get("next_recover_condition")
                or "runtime_signal_watcher_observes_a_fresh_signal_for_selected_scope"
            ),
            "automatic_recovery_action": (
                auto_resume.get("automatic_recovery_action")
                or "continue_watcher_observation_and_notify_on_material_change"
            ),
            "downgrade_mode": auto_resume.get("downgrade_mode") or "observe_only",
        }
    return {
        "status": "blocked_operator_review",
        "blocker_class": "review_only_warning",
        "blocked_at": "operator_packet",
        "blocked_reason": watcher["wakeup_status"],
        "next_recover_condition": (
            "operator_packet_translates_to_fresh_signal_or_waiting_for_market"
        ),
        "automatic_recovery_action": "rebuild_watcher_status_and_resume_pack",
        "downgrade_mode": "observe_only_no_candidate_prepare",
    }


def build_packet(
    *,
    intake_packet: dict[str, Any],
    live_facts_readiness: dict[str, Any],
    watcher_status: dict[str, Any],
    selected_strategy_group_id: str | None = None,
    max_symbols: int = DEFAULT_MAX_SYMBOLS,
    generated_at_ms: int | None = None,
) -> dict[str, Any]:
    generated_at_ms = generated_at_ms or int(time.time() * 1000)
    group, readiness, selection_reason = _select_pilot(
        intake_packet=intake_packet,
        live_facts_readiness=live_facts_readiness,
        requested_group_id=selected_strategy_group_id,
    )
    group_id = str(group.get("strategy_group_id")) if group else None
    watcher = _watcher_state(watcher_status)
    fact_summary = _candidate_fact_summary(readiness)
    selected_universe = (
        _selected_symbols(group=group, readiness=readiness, max_symbols=max_symbols)
        if group
        else []
    )
    supported_sides = [
        str(item) for item in (group or {}).get("supported_sides") or []
    ]
    selected_side = supported_sides[0] if supported_sides else "unknown"
    runtime_bridge = _runtime_bridge(group)
    watcher_scope_alignment = _watcher_scope_alignment(
        selected_universe=selected_universe,
        selected_side=selected_side,
        watcher=watcher,
    )
    owner_state = _owner_state(
        selected_group_id=group_id,
        readiness=readiness,
        watcher=watcher,
        runtime_bridge=runtime_bridge,
        watcher_scope_alignment=watcher_scope_alignment,
    )
    risk_defaults = (
        (group or {}).get("risk_defaults")
        if isinstance((group or {}).get("risk_defaults"), dict)
        else {}
    )
    candidate_blockers = [str(item) for item in fact_summary["candidate_blockers"]]
    progressive_gaps = [
        blocker for blocker in candidate_blockers
        if blocker in {"protection:missing", "budget:missing", "next_attempt_gate:missing"}
    ]
    dual_freshness = _dual_freshness(
        group=group,
        readiness=readiness,
        watcher=watcher,
        owner_state=owner_state,
        candidate_blockers=candidate_blockers,
    )
    gate_failure_ledger = _gate_failure_ledger(
        group=group,
        readiness=readiness,
        watcher=watcher,
        owner_state=owner_state,
        fact_summary=fact_summary,
        candidate_blockers=candidate_blockers,
        runtime_bridge=runtime_bridge,
        watcher_scope_alignment=watcher_scope_alignment,
    )
    why_not_executable: list[str] = []
    if owner_state["status"] == "waiting_for_market":
        why_not_executable.append("no_fresh_strategy_signal")
    elif owner_state["blocked_reason"] != "none":
        why_not_executable.append(owner_state["blocked_reason"])
    if owner_state["status"] == "blocked_runtime_scope_mismatch":
        why_not_executable.append("watcher_scope_not_bound_to_selected_pilot")
    if progressive_gaps:
        why_not_executable.append(
            "candidate_specific_protection_budget_next_gate_pending_until_fresh_signal"
        )
    prepared_authorization_ready = (
        owner_state["status"] == "ready_for_action_time_final_gate"
    )
    non_executing_prepare_ready = (
        owner_state["status"] == "ready_for_non_executing_prepare"
    )
    candidate_evidence = {
        "signal_input_json": watcher.get("signal_input_json"),
        "shadow_candidate_id": watcher.get("shadow_candidate_id"),
        "prepared_authorization_id": watcher.get("prepared_authorization_id"),
        "ready_for_action_time_final_gate": bool(
            watcher.get("prepared_authorization_id")
        ),
    }

    strategy_status = (
        "armed_observation_waiting_for_signal"
        if owner_state["status"] == "waiting_for_market"
        else owner_state["status"]
    )
    packet = {
        "scope": "strategygroup_runtime_pilot_status",
        "status": owner_state["status"],
        "generated_at_ms": generated_at_ms,
        "pilot_selection": {
            "strategy_group_id": group_id,
            "selection_reason": selection_reason,
            "requested_strategy_group_id": selected_strategy_group_id,
            "selected_universe": selected_universe,
            "selected_side": selected_side,
            "risk_profile": {
                "tier": "tiny",
                "leverage": "1",
                "max_active_position": 1,
                "max_symbols": max_symbols,
                "max_notional_per_action_usdt": str(
                    risk_defaults.get("max_notional_per_action_usdt")
                    or risk_defaults.get("max_notional_usdt")
                    or "8"
                ),
            },
        },
        "owner_state": owner_state,
        "runtime_bridge": runtime_bridge,
        "watcher_scope_alignment": watcher_scope_alignment,
        "candidate_evidence": candidate_evidence,
        "post_signal_auto_resume": watcher["post_signal_auto_resume"],
        "control_board": {
            "strategy_group_row": {
                "id": group_id,
                "role": (group or {}).get("name") or group_id,
                "status": strategy_status,
                "signal_state": (
                    "fresh_signal_ready"
                    if watcher["can_continue_steps_5_8"]
                    else "waiting_for_fresh_signal"
                ),
                "facts_state": (
                    "candidate_facts_ready"
                    if readiness.get("armed_candidate_prepare_ready")
                    else "candidate_facts_pending"
                ),
                "risk_profile": "tiny_1x_max1",
                "hard_stop_state": (
                    "clean"
                    if not watcher["unsafe_flags"]
                    and not fact_summary["active_position_blocked"]
                    and not fact_summary["open_order_blocked"]
                    else "blocked"
                ),
                "next_action": owner_state["automatic_recovery_action"],
            },
            "runtime_row": {
                "budget": "pending_until_candidate_specific_budget",
                "attempts": "next_attempt_gate_pending_until_fresh_signal"
                if "next_attempt_gate:missing" in progressive_gaps
                else "available",
                "active_position": fact_summary["active_position_status"],
                "open_order": fact_summary["open_order_status"],
                "protection": (
                    "pending_until_candidate_specific_plan"
                    if "protection:missing" in progressive_gaps
                    else "ready"
                ),
                "next_gate": owner_state["blocked_at"],
                "runtime_bridge": runtime_bridge["status"],
                "watcher_scope": watcher_scope_alignment["status"],
            },
            "candidate_row": {
                "fresh_signal_id": candidate_evidence["signal_input_json"] or "pending",
                "signal_input_json": candidate_evidence["signal_input_json"],
                "shadow_candidate_id": candidate_evidence["shadow_candidate_id"],
                "prepared_authorization_id": candidate_evidence[
                    "prepared_authorization_id"
                ],
                "runtime_grant_status": (
                    "prepared_authorization_ready"
                    if candidate_evidence["prepared_authorization_id"]
                    else "pending"
                ),
                "authorization_evidence_status": (
                    "fresh_authorization_evidence_ready"
                    if candidate_evidence["prepared_authorization_id"]
                    else "pending"
                ),
                "symbol": selected_universe[0] if selected_universe else "pending",
                "side": selected_side,
                "candidate_state": (
                    "prepared_authorization_ready"
                    if prepared_authorization_ready
                    else "ready_for_non_executing_prepare"
                    if non_executing_prepare_ready
                    else "not_prepared"
                ),
                "blocker": owner_state["blocked_reason"],
                "final_gate_status": (
                    "ready_to_run" if prepared_authorization_ready else "not_reached"
                ),
                "operation_layer_status": "not_reached",
            },
            "review_row": {
                "outcome": "not_started",
                "review_decision": "keep_observing"
                if owner_state["status"] == "waiting_for_market"
                else "pending",
            },
        },
        "dual_freshness": dual_freshness,
        "gate_failure_ledger": gate_failure_ledger,
        "readiness_chain": [
            {
                "gate": "strategy_group_handoff",
                "status": "ready" if group else "blocked",
                "class": "missing_fact" if not group else "none",
            },
            {
                "gate": "live_account_position_open_order",
                "status": "ready"
                if not fact_summary["active_position_blocked"]
                and not fact_summary["open_order_blocked"]
                else "blocked",
                "class": "active_position_resolution"
                if fact_summary["active_position_blocked"] or fact_summary["open_order_blocked"]
                else "none",
            },
            {
                "gate": "runtime_bridge",
                "status": "ready"
                if runtime_bridge["status"] == "configured"
                else "blocked",
                "class": "missing_fact"
                if runtime_bridge["status"] != "configured"
                else "none",
                "blockers": runtime_bridge["blockers"],
            },
            {
                "gate": "watcher_scope",
                "status": "ready"
                if watcher_scope_alignment["status"] in {"aligned", "not_visible"}
                else "blocked",
                "class": "runtime_scope_mismatch"
                if watcher_scope_alignment["status"] in {"mismatch", "mixed_scope"}
                else "none",
                "blockers": (
                    [watcher_scope_alignment["blocker"]]
                    if watcher_scope_alignment.get("blocker")
                    else []
                ),
            },
            {
                "gate": "strategy_signal",
                "status": (
                    "fresh_signal_ready"
                    if watcher["can_continue_steps_5_8"]
                    else "waiting_for_market"
                ),
                "class": "waiting_for_market"
                if not watcher["can_continue_steps_5_8"]
                else "none",
            },
            {
                "gate": "RequiredFacts",
                "status": "ready"
                if readiness.get("armed_candidate_prepare_ready")
                else "progressive_pending",
                "class": "missing_fact" if candidate_blockers else "none",
                "blockers": candidate_blockers,
            },
            {
                "gate": "FinalGate",
                "status": (
                    "ready_to_run"
                    if owner_state["status"] == "ready_for_action_time_final_gate"
                    else "not_reached"
                ),
                "class": (
                    "none"
                    if owner_state["status"] == "ready_for_action_time_final_gate"
                    else "hard_safety_stop"
                ),
            },
            {
                "gate": "Operation Layer",
                "status": "not_reached",
                "class": "hard_safety_stop",
            },
        ],
        "why_not_executable": why_not_executable,
        "next_safe_checkpoint": owner_state["automatic_recovery_action"],
        "watcher": watcher,
        "source_anchor": {
            "intake": intake_packet.get("source_anchor") or {},
            "live_facts_source": live_facts_readiness.get("live_facts_source") or {},
            "watcher_report": (
                (watcher_status.get("data") or {}).get("deployment_readiness") or {}
                if isinstance(watcher_status.get("data"), dict)
                else {}
            ).get("report_dir"),
        },
        "safety_invariants": {
            **{name: False for name in sorted(UNSAFE_FLAGS)},
            "pilot_status_builder_only": True,
            "reads_existing_evidence_only": True,
            "registers_runtime": False,
            "creates_candidate": False,
            "authorizes_execution": False,
            "places_order": False,
            "mutates_pg": False,
        },
    }
    return packet


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Owner-readable StrategyGroup runtime pilot status.",
    )
    parser.add_argument("--intake-json", required=True)
    parser.add_argument("--live-facts-readiness-json", required=True)
    parser.add_argument("--watcher-status-json", required=True)
    parser.add_argument("--selected-strategy-group-id")
    parser.add_argument("--max-symbols", type=int, default=DEFAULT_MAX_SYMBOLS)
    parser.add_argument("--output-json", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    packet = build_packet(
        intake_packet=_read_json(args.intake_json),
        live_facts_readiness=_read_json(args.live_facts_readiness_json),
        watcher_status=_read_json(args.watcher_status_json),
        selected_strategy_group_id=args.selected_strategy_group_id,
        max_symbols=args.max_symbols,
    )
    _write_json(args.output_json, packet)
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if not packet["status"].startswith("blocked_hard_safety_stop") else 2


if __name__ == "__main__":
    raise SystemExit(main())
