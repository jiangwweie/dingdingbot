#!/usr/bin/env python3
"""Build a read-only review packet for StrategyGroup coverage expansion.

The input is a signal coverage diagnostic packet. The output explains whether
broader observe-only would-enter signals should trigger an observation-scope
review. It never promotes a StrategyGroup into real-order eligibility and never
creates runtime, candidate, FinalGate, Operation Layer, or order actions.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SIGNAL_COVERAGE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-signal-coverage-diagnostic.json"
)
DEFAULT_TIER_POLICY_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json"
)
DEFAULT_EXPANSION_POLICY_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/main-control-signal-coverage-expansion-policy.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-signal-coverage-expansion-review.json"
)
DEFAULT_OWNER_PROGRESS = (
    REPO_ROOT / "output/runtime-monitor/latest-signal-coverage-expansion-review.md"
)


def build_signal_coverage_expansion_review(
    *,
    signal_coverage_packet: dict[str, Any],
    tier_policy: dict[str, Any],
    expansion_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    broader = _as_dict(signal_coverage_packet.get("broader_observation"))
    would_enter = _dict_rows(broader.get("would_enter_signals"))
    current_tiers = _current_tiers(tier_policy)
    new_default_tiers = _new_default_tiers(tier_policy)
    policy_groups = _as_dict(_as_dict(expansion_policy).get("strategy_groups"))
    review_rows = [
        _review_row(
            signal=row,
            current_tiers=current_tiers,
            new_default_tiers=new_default_tiers,
            expansion_policy=_as_dict(
                policy_groups.get(str(row.get("strategy_group_id") or ""))
            ),
        )
        for row in would_enter
    ]
    actionable_review_rows = [
        row for row in review_rows if _row_needs_priority_review(row)
    ]
    forbidden_effects = _forbidden_effects(signal_coverage_packet)

    if forbidden_effects:
        status = "blocked_forbidden_effect"
        owner_state = "needs_intervention"
        next_step = "review_signal_coverage_source_forbidden_effects"
    elif actionable_review_rows:
        status = "review_needed_broader_observe_only_would_enter"
        owner_state = "coverage_review_needed"
        next_step = "review_observe_only_expansion_candidates"
    elif review_rows:
        status = "low_priority_observe_only_would_enter_parked"
        owner_state = "waiting_for_opportunity"
        next_step = "continue_mainline_and_keep_low_priority_observation_parked"
    else:
        status = "no_expansion_review_needed"
        owner_state = "waiting_for_opportunity"
        next_step = "continue_mainline_and_replay_monitoring"

    return {
        "scope": "strategygroup_signal_coverage_expansion_review",
        "status": status,
        "owner_state": owner_state,
        "source_signal_coverage_status": signal_coverage_packet.get("status"),
        "interaction": {
            "level": "L0_local_signal_coverage_expansion_review",
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "counts": {
            "broader_would_enter_signal_count": len(would_enter),
            "review_row_count": len(review_rows),
            "actionable_review_row_count": len(actionable_review_rows),
            "low_priority_or_parked_review_row_count": (
                len(review_rows) - len(actionable_review_rows)
            ),
            "new_strategy_group_review_count": sum(
                1 for row in review_rows if row["source_category"] == "new_default"
            ),
            "current_strategy_group_review_count": sum(
                1 for row in review_rows if row["source_category"] == "current"
            ),
            "forbidden_effect_count": len(forbidden_effects),
        },
        "review_rows": review_rows,
        "decision": {
            "observation_scope_review_recommended": bool(actionable_review_rows),
            "low_priority_observation_recorded": bool(review_rows)
            and not actionable_review_rows,
            "real_order_scope_change_recommended": False,
            "l4_promotion_recommended": False,
            "default_next_step": next_step,
            "reason": (
                "broader_observe_only_would_enter_signals_exist"
                if review_rows
                else "no_broader_would_enter_signal"
            ),
        },
        "operator_command_plan": {
            "not_executed": True,
            "next_step": next_step,
            "starts_runtime": False,
            "changes_strategy_parameters": False,
            "changes_tier_policy": False,
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
            "calls_final_gate": False,
            "calls_operation_layer": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "withdrawal_or_transfer_requested": False,
        },
        "safety_invariants": {
            "review_only": True,
            "input_is_not_execution_authority": True,
            "does_not_expand_l4_real_order_scope": True,
            "does_not_modify_runtime_scope": True,
            "server_interaction": False,
            "server_files_mutated": False,
            "runtime_started": False,
            "strategy_parameters_changed": False,
            "tier_policy_changed": False,
            "shadow_candidate_created": False,
            "execution_intent_created": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "withdrawal_or_transfer_created": False,
            "source_forbidden_effects": forbidden_effects,
        },
    }


def build_owner_progress_markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# 策略观察面扩展评审",
        "",
        "## Owner 摘要",
        "",
        f"- Status: `{packet.get('status')}`",
        f"- Owner state: `{packet.get('owner_state')}`",
        f"- Broader would-enter: `{_as_dict(packet.get('counts')).get('broader_would_enter_signal_count', 0)}`",
        "- 实盘范围变更建议: `false`",
        "- L4 晋级建议: `false`",
        "",
        "## 观察级机会",
        "",
        _review_table(_dict_rows(packet.get("review_rows"))),
        "",
        "## 安全边界",
        "",
        "- 不修改策略参数",
        "- 不修改 tier policy",
        "- 不扩大 L4 实盘范围",
        "- 不调用 FinalGate / Operation Layer",
        "- 不创建订单或 exchange write",
        "",
        "## 下一步",
        "",
        f"- `{_as_dict(packet.get('decision')).get('default_next_step')}`",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _review_row(
    *,
    signal: dict[str, Any],
    current_tiers: dict[str, str],
    new_default_tiers: dict[str, str],
    expansion_policy: dict[str, Any],
) -> dict[str, Any]:
    strategy_group_id = str(signal.get("strategy_group_id") or "unknown")
    normalized_key = _normalize_strategy_group_key(strategy_group_id)
    if strategy_group_id in current_tiers:
        source_category = "current"
        current_tier = current_tiers[strategy_group_id]
    elif normalized_key in new_default_tiers:
        source_category = "new_default"
        current_tier = new_default_tiers[normalized_key]
    else:
        source_category = "unknown"
        current_tier = "unclassified"

    return {
        "strategy_group_id": strategy_group_id,
        "normalized_key": normalized_key,
        "source_category": source_category,
        "current_tier": current_tier,
        "symbol": signal.get("symbol"),
        "side": signal.get("side"),
        "confidence": signal.get("confidence"),
        "reason_codes": [str(item) for item in signal.get("reason_codes") or []],
        "coverage_review_priority": str(
            expansion_policy.get("coverage_review_priority") or "unknown"
        ),
        "policy_l2_readiness": str(
            expansion_policy.get("l2_readiness") or "unknown"
        ),
        "policy_recommended_action": str(
            expansion_policy.get("recommended_action") or "require_policy_review"
        ),
        "suggested_scope_action": _suggested_scope_action(
            source_category=source_category,
            current_tier=current_tier,
        ),
        "suggested_next_tier": _suggested_next_tier(
            source_category=source_category,
            current_tier=current_tier,
        ),
        "may_place_real_order_after_this_review": False,
        "requires_owner_live_lane_change_for_l4": True,
        "execution_boundary": _execution_boundary(current_tier=current_tier),
    }


def _row_needs_priority_review(row: dict[str, Any]) -> bool:
    priority = str(row.get("coverage_review_priority") or "unknown")
    readiness = str(row.get("policy_l2_readiness") or "unknown")
    if priority in {"P2", "P2_low", "low"}:
        return False
    if readiness == "blocked_parked_negative_evidence":
        return False
    return True


def _suggested_scope_action(*, source_category: str, current_tier: str) -> str:
    if current_tier == "L0":
        return "consider_l1_observe_only_intake"
    if current_tier == "L1":
        return "keep_l1_observe_only_and_review_for_l2_shadow_candidate"
    if current_tier == "L2":
        return "review_shadow_candidate_quality"
    if current_tier == "L3":
        return "review_armed_observation_quality"
    if current_tier == "L4":
        return "keep_official_runtime_chain_boundary"
    if source_category == "unknown":
        return "require_handoff_classification_before_observation"
    return "review_strategygroup_scope"


def _suggested_next_tier(*, source_category: str, current_tier: str) -> str:
    if source_category == "unknown":
        return "L0_or_L1_after_handoff"
    if current_tier == "L1":
        return "L2_after_handoff_review_and_dry_run"
    return current_tier


def _execution_boundary(*, current_tier: str) -> str:
    if current_tier == "L1":
        return "observe-only; no candidate/order"
    if current_tier == "L2":
        return "shadow review only; no FinalGate/Operation Layer"
    if current_tier == "L3":
        return "armed observation review; no Operation Layer"
    if current_tier == "L4":
        return "official chain only; preview is not submit authority"
    return "handoff classification required before observation"


def _normalize_strategy_group_key(strategy_group_id: str) -> str:
    if strategy_group_id.endswith("-001"):
        return strategy_group_id[:-4]
    return strategy_group_id


def _current_tiers(tier_policy: dict[str, Any]) -> dict[str, str]:
    current = _as_dict(tier_policy.get("current_strategy_groups"))
    return {
        str(key): str(_as_dict(value).get("tier"))
        for key, value in current.items()
        if _as_dict(value).get("tier")
    }


def _new_default_tiers(tier_policy: dict[str, Any]) -> dict[str, str]:
    defaults = _as_dict(tier_policy.get("new_strategy_group_defaults"))
    known = _as_dict(defaults.get("known_new_groups"))
    return {str(key): str(value) for key, value in known.items() if str(value)}


def _forbidden_effects(packet: dict[str, Any]) -> list[str]:
    safety = _as_dict(packet.get("safety_invariants"))
    checks = _as_dict(packet.get("checks"))
    effects = [str(item) for item in safety.get("source_forbidden_effects") or []]
    effects.extend(str(item) for item in checks.get("forbidden_effects") or [])
    for key in (
        "shadow_candidate_created",
        "execution_intent_created",
        "final_gate_called",
        "operation_layer_called",
        "order_created",
        "order_lifecycle_called",
        "exchange_write_called",
        "withdrawal_or_transfer_created",
    ):
        if safety.get(key) is True:
            effects.append(f"safety.{key}")
    return sorted(set(effect for effect in effects if effect))


def _review_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return (
            "| StrategyGroup | Symbol | Side | Confidence | Tier | Next tier | Action | Boundary |\n"
            "| --- | --- | --- | ---: | --- | --- | --- | --- |\n"
            "| none | - | - | - | - | - | - | - |"
        )
    output = [
        "| StrategyGroup | Symbol | Side | Confidence | Tier | Next tier | Action | Boundary |",
        "| --- | --- | --- | ---: | --- | --- | --- | --- |",
    ]
    for row in rows:
        output.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row.get("strategy_group_id"),
                row.get("symbol"),
                row.get("side"),
                row.get("confidence"),
                row.get("current_tier"),
                row.get("suggested_next_tier"),
                row.get("suggested_scope_action"),
                row.get("execution_boundary"),
            )
        )
    return "\n".join(output)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)]


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal-coverage-json", default=str(DEFAULT_SIGNAL_COVERAGE_JSON))
    parser.add_argument("--tier-policy-json", default=str(DEFAULT_TIER_POLICY_JSON))
    parser.add_argument(
        "--expansion-policy-json",
        default=str(DEFAULT_EXPANSION_POLICY_JSON),
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OWNER_PROGRESS))
    args = parser.parse_args(argv)

    packet = build_signal_coverage_expansion_review(
        signal_coverage_packet=_load_json_object(
            Path(args.signal_coverage_json).expanduser()
        ),
        tier_policy=_load_json_object(Path(args.tier_policy_json).expanduser()),
        expansion_policy=_load_json_object(Path(args.expansion_policy_json).expanduser()),
    )
    payload = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    if args.output_owner_progress:
        owner_path = Path(args.output_owner_progress).expanduser()
        owner_path.parent.mkdir(parents=True, exist_ok=True)
        owner_path.write_text(build_owner_progress_markdown(packet), encoding="utf-8")
    print(payload)
    return 0 if packet["status"] != "blocked_forbidden_effect" else 2


if __name__ == "__main__":
    raise SystemExit(main())
