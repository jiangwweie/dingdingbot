#!/usr/bin/env python3
"""Build an Owner-readable StrategyGroup runtime pilot status read model.

This is a read-only product layer over StrategyGroup intake, live-facts
readiness, and runtime signal watcher evidence. It never creates candidates,
grants authorization, calls exchange write APIs, mutates PG, or places orders.
"""

from __future__ import annotations

from pathlib import Path
import sys
import time
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.application.runtime_strategy_signal_evaluation_service import (
    RuntimeStrategySignalEvaluationService,
)
from src.application.readmodels.owner_projection import (
    owner_non_authority_checkpoint,
    owner_state_source_checkpoint,
    owner_state_with_explicit_action_authority,
    owner_state_without_legacy_input_recovery_action,
)
from src.domain.strategy_semantics import initial_strategy_semantics_catalog


PREFERRED_GROUP_ID = "MPG-001"
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
    preference = 0 if group_id == PREFERRED_GROUP_ID else 5
    ready_count = len((readiness.get("exchange_rules") or {}).get("ready_symbols") or [])
    return (observe_penalty, candidate_penalty, preference, -ready_count)


def _select_pilot(
    *,
    intake_artifact: dict[str, Any],
    live_facts_readiness: dict[str, Any],
    requested_group_id: str | None,
) -> tuple[dict[str, Any] | None, dict[str, Any], str]:
    groups = _by_id(_items(intake_artifact.get("strategy_picker")))
    readiness_by_id = _by_id(_items(live_facts_readiness.get("readiness")))
    if requested_group_id:
        group = groups.get(requested_group_id)
        return (
            group,
            readiness_by_id.get(requested_group_id, {}),
            "owner_requested_strategy_group",
        )

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
    if group_id == PREFERRED_GROUP_ID:
        return group, readiness_by_id.get(group_id, {}), "preferred_mpg_engineering_ready"
    return group, readiness_by_id.get(group_id, {}), "best_engineering_ready_group"


def _watcher_state(watcher_status: dict[str, Any]) -> dict[str, Any]:
    data = (
        watcher_status.get("data")
        if isinstance(watcher_status.get("data"), dict)
        else watcher_status
    )
    if data.get("scope") == "runtime_signal_watcher_post_signal_resume_pack":
        post_signal_auto_resume = owner_state_without_legacy_input_recovery_action(
            _dict(data.get("post_signal_auto_resume"))
        )
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
            "watcher_status_evidence_status": "unknown",
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
            "action_time_resume": _dict(data.get("action_time_resume")),
            "post_signal_auto_resume": post_signal_auto_resume,
        }
    deployment = (
        data.get("deployment_readiness")
        if isinstance(data.get("deployment_readiness"), dict)
        else {}
    )
    watcher = data.get("watcher") if isinstance(data.get("watcher"), dict) else {}
    watcher_status_evidence = (
        data.get("watcher_status_evidence")
        if isinstance(data.get("watcher_status_evidence"), dict)
        else {}
    )
    resume = (
        data.get("post_signal_resume")
        if isinstance(data.get("post_signal_resume"), dict)
        else {}
    )
    post_signal_auto_resume = owner_state_without_legacy_input_recovery_action(
        _dict(
            data.get("post_signal_auto_resume")
            or watcher.get("post_signal_auto_resume")
            or resume.get("post_signal_auto_resume")
        )
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
        "watcher_status_evidence_status": str(
            watcher.get("watcher_status_evidence_status")
            or "unknown"
        ),
        "can_continue_steps_5_8": bool(resume.get("can_continue_steps_5_8")),
        "current_gate": str(resume.get("current_gate") or "unknown"),
        "blockers": blockers,
        "warnings": list(watcher.get("warnings") or []),
        "unsafe_flags": sorted(set(str(item) for item in unsafe_flags if item)),
        "runtime_signal_summaries": _items(
            watcher.get("runtime_signal_summaries")
            or watcher_status_evidence.get("runtime_signal_summaries")
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
        "action_time_resume": _dict(data.get("action_time_resume") or resume.get("action_time_resume")),
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
        "shadow_candidate_evidence_freshness_target_seconds": scope.get(
            "shadow_candidate_evidence_freshness_target_seconds"
        ),
    }


def _watcher_scope_alignment(
    *,
    selected_strategy_group_id: str | None,
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
    selected_group = str(selected_strategy_group_id or "").strip()

    matched: list[dict[str, Any]] = []
    out_of_scope: list[dict[str, Any]] = []
    for summary in summaries:
        strategy_group_id = str(summary.get("strategy_family_id") or "").strip()
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
        if (
            strategy_group_id == selected_group
            and symbol in selected_symbols
            and (not selected_sides or side in selected_sides)
        ):
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
        status = "expanded_scope"
        blocker = None
    else:
        status = "aligned"
        blocker = None

    return {
        "status": status,
        "selected_strategy_group_id": selected_group or None,
        "selected_symbols": sorted(selected_symbols),
        "selected_side": sorted(selected_sides)[0] if selected_sides else None,
        "runtime_signal_summary_count": len(summaries),
        "matched_runtime_signal_summary_count": len(matched),
        "out_of_scope_runtime_signal_summary_count": len(out_of_scope),
        "matched_runtime_signal_summaries": matched,
        "out_of_scope_runtime_signal_summaries": out_of_scope[:10],
        "blocker": blocker,
        "non_authority_checkpoint": (
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


def _runtime_binding(group: dict[str, Any] | None) -> dict[str, Any]:
    if not group:
        return {
            "status": "not_selected",
            "strategy_family_id": None,
            "strategy_family_version_id": None,
            "semantics_binding_found": False,
            "evaluator_route_configured": False,
            "blockers": ["strategy_group_not_selected"],
            "non_authority_checkpoint": "select_strategy_group",
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
        "non_authority_checkpoint": (
            "continue_to_runtime_scope_alignment"
            if status == "configured"
            else "add_strategy_semantics_binding_and_evaluator_route"
        ),
        "next_recover_condition": (
            "strategy_semantics_binding_and_evaluator_route_are_configured"
        ),
        "non_executing": True,
    }


def _strategy_group_board_rows(
    *,
    intake_artifact: dict[str, Any],
    live_facts_readiness: dict[str, Any],
    watcher: dict[str, Any],
    selected_group_id: str | None,
) -> list[dict[str, Any]]:
    readiness_by_id = _by_id(_items(live_facts_readiness.get("readiness")))
    summaries_by_group: dict[str, list[dict[str, Any]]] = {}
    for summary in _items(watcher.get("runtime_signal_summaries")):
        group_id = str(summary.get("strategy_family_id") or "")
        if group_id:
            summaries_by_group.setdefault(group_id, []).append(summary)

    rows: list[dict[str, Any]] = []
    for group in _items(intake_artifact.get("strategy_picker")):
        group_id = str(group.get("strategy_group_id") or "")
        readiness = readiness_by_id.get(group_id, {})
        binding = _runtime_binding(group)
        summaries = summaries_by_group.get(group_id, [])
        default_mode = str((group.get("picker") or {}).get("default_mode") or "")
        observe_ready = bool(readiness.get("observe_ready"))
        armed_ready = bool(readiness.get("armed_candidate_prepare_ready"))
        ready_symbols = list((readiness.get("exchange_rules") or {}).get("ready_symbols") or [])
        blocked_symbols = list((readiness.get("exchange_rules") or {}).get("blocked_symbols") or [])
        blockers = [str(item) for item in readiness.get("blockers") or []]
        warnings = [str(item) for item in readiness.get("warnings") or []]

        signal_types = {
            str(item.get("signal_type") or item.get("status") or "")
            for item in summaries
        }
        if binding.get("status") != "configured":
            runtime_state = "blocked"
            non_authority_checkpoint = "add_strategy_semantics_binding_and_evaluator_route"
            blocked_reason = ",".join(str(item) for item in binding.get("blockers") or [])
        elif not observe_ready:
            runtime_state = "blocked"
            non_authority_checkpoint = "refresh_exchange_rules_or_reduce_symbol_scope"
            blocked_reason = ",".join(blockers) or "no_exchange_ready_symbol"
        elif default_mode == "observe_only":
            runtime_state = "observe_only_ready"
            non_authority_checkpoint = "continue_observe_only_until_upgrade_facts_pass"
            blocked_reason = "observe_only_default"
        elif summaries and "no_action" not in signal_types:
            runtime_state = "signal_review"
            non_authority_checkpoint = "review_runtime_signal_summary"
            blocked_reason = "none"
        elif summaries:
            runtime_state = "observing"
            non_authority_checkpoint = "continue_watcher_observation"
            blocked_reason = "no_fresh_strategy_signal"
        else:
            runtime_state = "admission_ready"
            non_authority_checkpoint = "create_or_attach_strategygroup_runtime"
            blocked_reason = "runtime_not_selected_for_watcher_scope"

        rows.append(
            {
                "strategy_group_id": group_id,
                "name": group.get("name") or group_id,
                "selected": group_id == selected_group_id,
                "picker_rank": (group.get("picker") or {}).get("rank"),
                "default_mode": default_mode,
                "intake_status": group.get("intake_status"),
                "runtime_state": runtime_state,
                "signal_state": (
                    "fresh_or_review"
                    if runtime_state == "signal_review"
                    else "no_signal"
                    if summaries
                    else "not_observed"
                ),
                "required_facts": (
                    "pass"
                    if armed_ready
                    else "observe_ready"
                    if observe_ready
                    else "missing"
                ),
                "runtime_binding": binding.get("status"),
                "ready_symbols": ready_symbols,
                "blocked_symbols": blocked_symbols,
                "blockers": blockers,
                "warnings": warnings,
                "blocked_reason": blocked_reason,
                "non_authority_checkpoint": non_authority_checkpoint,
                "checkpoint_source": "candidate_runtime_state",
            }
        )
    return sorted(
        rows,
        key=lambda item: (
            item.get("picker_rank") if item.get("picker_rank") is not None else 999,
            str(item.get("strategy_group_id") or ""),
        ),
    )


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
    elif owner_state["status"] == "blocked_runtime_binding_missing":
        action_time_status = "blocked_runtime_binding_missing"
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
            "shadow_candidate_evidence_freshness_target_seconds": scope[
                "shadow_candidate_evidence_freshness_target_seconds"
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
    non_authority_checkpoint: str,
    authority_mode: str,
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
        "non_authority_checkpoint": non_authority_checkpoint,
        "authority_mode": authority_mode,
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
    runtime_binding: dict[str, Any],
    watcher_scope_alignment: dict[str, Any],
) -> list[dict[str, Any]]:
    no_group = group is None
    account_blocked = (
        fact_summary["active_position_blocked"] or fact_summary["open_order_blocked"]
    )
    signal_ready = bool(watcher["can_continue_steps_5_8"])
    candidate_ready = bool(readiness.get("armed_candidate_prepare_ready"))
    hard_safety_stop = owner_state["status"] == "blocked_hard_safety_stop"
    binding_blocked = runtime_binding.get("status") != "configured"
    scope_blocked = owner_state["status"] == "blocked_runtime_scope_mismatch"
    ready_for_final_gate = owner_state["status"] == "ready_for_action_time_final_gate"

    group_status = "blocked" if no_group else "ready"
    projection_status = "blocked" if binding_blocked else "ready"
    account_status = "blocked" if account_blocked else "ready"
    watcher_scope_status = "blocked" if scope_blocked else "ready"
    if hard_safety_stop or binding_blocked or scope_blocked:
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
    owner_action = _owner_checkpoint(owner_state)
    owner_authority = str(owner_state["authority_mode"])

    return [
        _gate_row(
            gate="pg_strategy_group_candidate_scope",
            status=group_status,
            blocker_class="missing_fact" if no_group else "none",
            blocked_at="strategy_group_selection" if no_group else "none",
            blocked_reason=(
                "no_pg_strategy_group_candidate_scope_available"
                if no_group
                else "none"
            ),
            next_recover_condition=(
                owner_recover if no_group else "pg_strategy_group_scope_selected"
            ),
            non_authority_checkpoint=(
                owner_action if no_group else "continue_selected_pilot_observation"
            ),
            authority_mode=owner_authority if no_group else "armed_observation",
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
            non_authority_checkpoint=(
                owner_action
                if account_blocked
                else "continue_selected_pilot_observation"
            ),
            authority_mode=(
                owner_authority if account_blocked else "armed_observation"
            ),
            blockers=[],
        ),
        _gate_row(
            gate="runtime_binding",
            status=projection_status,
            blocker_class="missing_fact" if binding_blocked else "none",
            blocked_at="runtime_binding" if binding_blocked else "none",
            blocked_reason=owner_reason if binding_blocked else "none",
            next_recover_condition=(
                str(runtime_binding.get("next_recover_condition"))
                if binding_blocked
                else "strategy_semantics_binding_and_evaluator_route_are_configured"
            ),
            non_authority_checkpoint=(
                str(runtime_binding.get("non_authority_checkpoint"))
                if binding_blocked
                else "continue_selected_pilot_observation"
            ),
            authority_mode=(
                owner_authority if binding_blocked else "armed_observation"
            ),
            blockers=runtime_binding.get("blockers") or [],
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
            non_authority_checkpoint=(
                str(watcher_scope_alignment.get("non_authority_checkpoint"))
                if scope_blocked
                else "continue_selected_pilot_observation"
            ),
            authority_mode=(
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
                    "runtime_binding",
                    "runtime_signal_watcher_scope",
                }
                else ("none" if signal_ready else "waiting_for_market")
            ),
            blocked_at="none" if signal_ready else owner_blocked_at,
            blocked_reason="none" if signal_ready else owner_reason,
            next_recover_condition=(
                "fresh_strategy_signal_available" if signal_ready else owner_recover
            ),
            non_authority_checkpoint=(
                "continue_to_required_facts_readiness" if signal_ready else owner_action
            ),
            authority_mode="armed_observation" if signal_ready else owner_authority,
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
            non_authority_checkpoint=(
                "collect_or_prepare_missing_candidate_specific_facts"
                if signal_ready and candidate_blockers
                else "wait_for_fresh_signal_before_candidate_specific_fact_materialization"
                if candidate_blockers
                else "continue_to_shadow_candidate_prepare"
            ),
            authority_mode=(
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
            non_authority_checkpoint=(
                owner_action
                if ready_for_final_gate
                else "stop_before_action_time_final_gate_until_candidate_chain_exists"
            ),
            authority_mode=(
                owner_authority if ready_for_final_gate else "no_real_submit"
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
            non_authority_checkpoint="stop_before_gateway_action_until_final_gate_passes",
            authority_mode="no_real_submit",
            hard_stop=True,
        ),
    ]


def _owner_state(
    *,
    selected_group_id: str | None,
    readiness: dict[str, Any],
    watcher: dict[str, Any],
    runtime_binding: dict[str, Any],
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
            "blocked_reason": "no_pg_strategy_group_candidate_scope_available",
            "next_recover_condition": (
                "pg_current_candidate_scope_projection_contains_at_least_one_group"
            ),
            "non_authority_checkpoint": "publish_pg_current_strategy_group_intake_projection",
            "authority_mode": "no_runtime_observation",
        }
    if runtime_binding.get("status") != "configured":
        return {
            "status": "blocked_runtime_binding_missing",
            "blocker_class": "missing_fact",
            "blocked_at": "runtime_binding",
            "blocked_reason": ",".join(
                str(item) for item in (runtime_binding.get("blockers") or [])
            )
            or "strategy_runtime_binding_missing",
            "next_recover_condition": str(
                runtime_binding.get("next_recover_condition")
            ),
            "non_authority_checkpoint": str(
                runtime_binding.get("non_authority_checkpoint")
            ),
            "authority_mode": "observe_only_no_runtime_evaluation",
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
            "non_authority_checkpoint": "stop_resume_path_and_investigate_watcher_evidence",
            "authority_mode": "manual_review_only",
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
            "non_authority_checkpoint": (
                "refresh_readonly_account_position_open_order_facts_then_reconcile"
            ),
            "authority_mode": "observe_only_no_candidate_prepare",
        }
    if not observe_ready:
        return {
            "status": "blocked_missing_fact",
            "blocker_class": "missing_fact",
            "blocked_at": "exchange_symbol_rules",
            "blocked_reason": "selected_strategy_group_is_not_observe_ready",
            "next_recover_condition": "exchange_rules_are_ready_for_selected_universe",
            "non_authority_checkpoint": "refresh_readonly_exchange_rules_for_selected_symbols",
            "authority_mode": "no_runtime_observation",
        }
    if watcher["deployment_status"] in {"evidence_missing", "evidence_stale", "unknown"}:
        return {
            "status": "blocked_deployment_issue",
            "blocker_class": "deployment_issue",
            "blocked_at": "runtime_signal_watcher_evidence",
            "blocked_reason": f"watcher_evidence_{watcher['deployment_status']}",
            "next_recover_condition": "watcher_evidence_files_are_present_and_fresh",
            "non_authority_checkpoint": (
                "run_or_wait_for_next_watcher_tick_and_rebuild_readiness_pack"
            ),
            "authority_mode": "observe_only_no_candidate_prepare",
        }
    if watcher_scope_alignment.get("status") == "mismatch":
        return {
            "status": "blocked_runtime_scope_mismatch",
            "blocker_class": "runtime_scope_mismatch",
            "blocked_at": "runtime_signal_watcher_scope",
            "blocked_reason": str(watcher_scope_alignment.get("blocker")),
            "next_recover_condition": str(
                watcher_scope_alignment.get("next_recover_condition")
            ),
            "non_authority_checkpoint": str(
                watcher_scope_alignment.get("non_authority_checkpoint")
            ),
            "authority_mode": "observe_only_no_candidate_prepare",
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
                    "non_authority_checkpoint": (
                        owner_state_source_checkpoint(
                            auto_resume,
                            default="run_official_action_time_final_gate_preflight",
                        )[0]
                    ),
                    "authority_mode": (
                        auto_resume.get("authority_mode")
                        or "no_real_submit_until_final_gate_pass"
                    ),
                }
            return {
                "status": "ready_for_non_executing_prepare",
                "blocker_class": "none",
                "blocked_at": "none",
                "blocked_reason": "none",
                "next_recover_condition": "fresh_signal_already_available",
                "non_authority_checkpoint": (
                    owner_state_source_checkpoint(
                        auto_resume,
                        default="prepare_shadow_candidate_runtime_grant_authorization_evidence",
                    )[0]
                ),
                "authority_mode": "armed_observation",
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
            "non_authority_checkpoint": "collect_or_prepare_missing_candidate_specific_facts",
            "authority_mode": "observe_only_no_real_submit",
        }
    if _has_no_signal_blocker(watcher["blockers"]) or watcher["wakeup_status"] in {
        "operator_evidence_needs_review",
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
            "non_authority_checkpoint": (
                owner_state_source_checkpoint(
                    auto_resume,
                    default="continue_watcher_observation_and_notify_on_material_change",
                )[0]
            ),
            "authority_mode": auto_resume.get("authority_mode") or "observe_only",
        }
    return {
        "status": "blocked_operator_review",
        "blocker_class": "review_only_warning",
        "blocked_at": "operator_review_evidence",
        "blocked_reason": watcher["wakeup_status"],
        "next_recover_condition": (
            "operator_review_evidence_translates_to_fresh_signal_or_waiting_for_market"
        ),
        "non_authority_checkpoint": "rebuild_watcher_status_and_resume_pack",
        "authority_mode": "observe_only_no_candidate_prepare",
    }


def _action_time_resume_state(
    *,
    owner_state: dict[str, Any],
    watcher: dict[str, Any],
    candidate_evidence: dict[str, Any],
) -> dict[str, Any]:
    existing = _dict(watcher.get("action_time_resume"))
    if existing:
        return existing

    prepared = bool(candidate_evidence.get("prepared_authorization_id"))
    if owner_state["status"] == "blocked_hard_safety_stop":
        status = "blocked"
        next_step = "resolve_hard_safety_stop_before_action_time_resume"
        allowed_auto_actions: list[str] = []
    elif prepared or owner_state["status"] == "ready_for_action_time_final_gate":
        status = "ready_for_action_time_final_gate"
        next_step = "run_official_action_time_final_gate_preflight"
        allowed_auto_actions = ["run_official_action_time_final_gate_preflight"]
    elif owner_state["status"] == "waiting_for_market":
        status = "waiting_for_market"
        next_step = "continue_watcher_observation"
        allowed_auto_actions = ["continue_watcher_observation"]
    else:
        status = "blocked"
        next_step = _owner_checkpoint(owner_state)
        allowed_auto_actions = []

    return {
        "status": status,
        "next_step": next_step,
        "signal_input_json": candidate_evidence.get("signal_input_json"),
        "shadow_candidate_id": candidate_evidence.get("shadow_candidate_id"),
        "prepared_authorization_id": candidate_evidence.get(
            "prepared_authorization_id"
        ),
        "allowed_auto_actions": allowed_auto_actions,
        "forbidden_auto_actions_until_final_gate_pass": [
            "official_operation_layer_submit",
            "exchange_order",
            "order_lifecycle_submit",
            "runtime_budget_mutation",
        ],
        "requires_fresh_action_time_facts": prepared,
        "requires_action_time_final_gate": True,
        "requires_official_operation_layer": True,
        "final_gate_status": "not_run" if prepared else "not_reached",
        "operation_layer_status": "not_reached",
        "places_order": False,
        "calls_order_lifecycle": False,
        "exchange_write_called": False,
        "withdrawal_or_transfer_requested": False,
    }


def _owner_action_item(
    *,
    owner_state: dict[str, Any],
    action_time_resume: dict[str, Any],
    post_signal_auto_resume: dict[str, Any],
) -> dict[str, Any]:
    status = str(owner_state.get("status") or "unknown")
    blocked_reason = str(owner_state.get("blocked_reason") or "none")
    blocked_at = str(owner_state.get("blocked_at") or "unknown")
    non_authority_checkpoint = _owner_checkpoint(owner_state)
    if status == "waiting_for_market":
        headline = "Watcher is active; waiting for a fresh strategy signal."
        owner_status_checkpoint = "none_wait_for_signal_notification"
    elif status == "ready_for_non_executing_prepare":
        headline = "Fresh signal is ready; system can prepare non-executing evidence."
        owner_status_checkpoint = "none_system_prepares_candidate_evidence"
    elif status == "ready_for_action_time_final_gate":
        headline = "Fresh authorization evidence is ready for action-time FinalGate."
        owner_status_checkpoint = "none_system_runs_official_finalgate"
    elif str(owner_state.get("blocker_class")) == "hard_safety_stop":
        headline = "Hard safety stop; automatic execution is halted."
        owner_status_checkpoint = "review_hard_safety_stop"
    elif str(owner_state.get("blocker_class")) == "active_position_resolution":
        headline = "Existing position or open-order state must be resolved first."
        owner_status_checkpoint = "review_position_resolution"
    else:
        headline = "Pilot cannot advance yet; recovery condition is explicit."
        owner_status_checkpoint = "none_system_attempts_recovery_if_bounded"

    return {
        "headline": headline,
        "current_state": status,
        "blocked_at": blocked_at,
        "blocked_reason": blocked_reason,
        "next_recover_condition": str(
            owner_state.get("next_recover_condition") or "unknown"
        ),
        "non_authority_checkpoint": non_authority_checkpoint,
        "checkpoint_source": "owner_state",
        "authority_mode": str(owner_state.get("authority_mode") or "unknown"),
        "owner_status_checkpoint": owner_status_checkpoint,
        "can_continue_without_owner_chat": bool(
            owner_state.get("can_continue_without_owner_chat")
            or post_signal_auto_resume.get("can_continue_without_owner_chat")
        ),
        "requires_action_time_final_gate": bool(
            owner_state.get("requires_action_time_final_gate")
            or action_time_resume.get("requires_action_time_final_gate")
            or post_signal_auto_resume.get("requires_action_time_final_gate")
        ),
        "requires_official_operation_layer": bool(
            owner_state.get("requires_official_operation_layer")
            or action_time_resume.get("requires_official_operation_layer")
            or post_signal_auto_resume.get("requires_official_operation_layer")
        ),
        "no_raw_evidence_review_required": True,
        "why_not_executable": []
        if blocked_reason == "none"
        else [blocked_reason],
    }


def _owner_checkpoint(owner_state: dict[str, Any]) -> str:
    return owner_non_authority_checkpoint(
        owner_state,
        default="review_current_state",
    )


def build_status_artifact(
    *,
    intake_artifact: dict[str, Any],
    live_facts_readiness: dict[str, Any],
    watcher_status: dict[str, Any],
    selected_strategy_group_id: str | None = None,
    max_symbols: int = DEFAULT_MAX_SYMBOLS,
    generated_at_ms: int | None = None,
) -> dict[str, Any]:
    generated_at_ms = generated_at_ms or int(time.time() * 1000)
    group, readiness, selection_reason = _select_pilot(
        intake_artifact=intake_artifact,
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
    runtime_binding = _runtime_binding(group)
    watcher_scope_alignment = _watcher_scope_alignment(
        selected_strategy_group_id=group_id,
        selected_universe=selected_universe,
        selected_side=selected_side,
        watcher=watcher,
    )
    owner_state = _owner_state(
        selected_group_id=group_id,
        readiness=readiness,
        watcher=watcher,
        runtime_binding=runtime_binding,
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
    action_time_resume = _action_time_resume_state(
        owner_state=owner_state,
        watcher=watcher,
        candidate_evidence=candidate_evidence,
    )
    owner_state = owner_state_with_explicit_action_authority(
        owner_state=owner_state,
        action_time_resume=action_time_resume,
    )
    checkpoint_source = str(owner_state.get("checkpoint_source") or "owner_state")
    if "non_authority_checkpoint" not in owner_state:
        source_checkpoint, checkpoint_source = owner_state_source_checkpoint(
            owner_state,
            default="",
        )
        if source_checkpoint:
            owner_state = {
                **owner_state,
                "non_authority_checkpoint": source_checkpoint,
            }
    owner_checkpoint = _owner_checkpoint(owner_state)
    owner_state_projection = {
        **owner_state_without_legacy_input_recovery_action(owner_state),
        "non_authority_checkpoint": owner_checkpoint,
        "checkpoint_source": checkpoint_source,
    }
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
        runtime_binding=runtime_binding,
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
    strategy_group_rows = _strategy_group_board_rows(
        intake_artifact=intake_artifact,
        live_facts_readiness=live_facts_readiness,
        watcher=watcher,
        selected_group_id=group_id,
    )

    strategy_status = (
        "armed_observation_waiting_for_signal"
        if owner_state["status"] == "waiting_for_market"
        else owner_state["status"]
    )
    artifact = {
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
        "owner_state": owner_state_projection,
        "runtime_binding": runtime_binding,
        "watcher_scope_alignment": watcher_scope_alignment,
        "candidate_evidence": candidate_evidence,
        "action_time_resume": action_time_resume,
        "post_signal_auto_resume": watcher["post_signal_auto_resume"],
        "control_board": {
            "strategy_group_rows": strategy_group_rows,
            "strategy_group_counts": {
                "total": len(strategy_group_rows),
                "selected": sum(1 for row in strategy_group_rows if row["selected"]),
                "observing": sum(
                    1 for row in strategy_group_rows
                    if row["runtime_state"] == "observing"
                ),
                "admission_ready": sum(
                    1 for row in strategy_group_rows
                    if row["runtime_state"] == "admission_ready"
                ),
                "blocked": sum(
                    1 for row in strategy_group_rows
                    if row["runtime_state"] == "blocked"
                ),
                "observe_only_ready": sum(
                    1 for row in strategy_group_rows
                    if row["runtime_state"] == "observe_only_ready"
                ),
            },
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
                "non_authority_checkpoint": owner_checkpoint,
                "checkpoint_source": "owner_state",
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
                "runtime_binding": runtime_binding["status"],
                "watcher_scope": watcher_scope_alignment["status"],
            },
            "candidate_row": {
                "signal_input_json": candidate_evidence["signal_input_json"],
                "shadow_candidate_id": candidate_evidence["shadow_candidate_id"],
                "prepared_authorization_id": candidate_evidence[
                    "prepared_authorization_id"
                ],
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
            },
            "review_row": {
                "outcome": "not_started",
                "review_outcome": "keep_observing"
                if owner_state["status"] == "waiting_for_market"
                else "pending",
            },
        },
        "dual_freshness": dual_freshness,
        "gate_failure_ledger": gate_failure_ledger,
        "readiness_chain": [
            {
                "gate": "pg_strategy_group_candidate_scope",
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
                "gate": "runtime_binding",
                "status": "ready"
                if runtime_binding["status"] == "configured"
                else "blocked",
                "class": "missing_fact"
                if runtime_binding["status"] != "configured"
                else "none",
                "blockers": runtime_binding["blockers"],
            },
            {
                "gate": "watcher_scope",
                "status": "ready"
                if watcher_scope_alignment["status"] in {
                    "aligned",
                    "expanded_scope",
                    "not_visible",
                }
                else "blocked",
                "class": "runtime_scope_mismatch"
                if watcher_scope_alignment["status"] == "mismatch"
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
                    else "not_reached"
                ),
            },
            {
                "gate": "Operation Layer",
                "status": "not_reached",
                "class": "not_reached",
            },
        ],
        "why_not_executable": why_not_executable,
        "owner_action_item": {
            **_owner_action_item(
                owner_state=owner_state,
                action_time_resume=action_time_resume,
                post_signal_auto_resume=watcher["post_signal_auto_resume"],
            ),
            "why_not_executable": why_not_executable,
        },
        "non_authority_checkpoint": owner_checkpoint,
        "checkpoint_source": "owner_state",
        "watcher": watcher,
        "source_anchor": {
            "intake": intake_artifact.get("source_anchor") or {},
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
    return artifact
