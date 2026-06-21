#!/usr/bin/env python3
"""Review L2 tier-policy readiness after a local L2 intake dry-run.

This script is intentionally non-executing. It only checks whether a
StrategyGroup that passed L2 intake dry-run is eligible for a runtime tier
policy change from L1 observe-only into L2 shadow-candidate observation. It
does not mutate the policy file, start runtime, create candidates, call
FinalGate, call the Operation Layer, or place orders.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_L2_INTAKE_DRY_RUN_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-l2-intake-dry-run.json"
)
DEFAULT_TIER_POLICY_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-l2-tier-policy-review.json"
)
DEFAULT_OWNER_PROGRESS = (
    REPO_ROOT / "output/runtime-monitor/latest-l2-tier-policy-review.md"
)
TARGET_TIER = "L2"
TARGET_MODE = "shadow_candidate"


def build_l2_tier_policy_review(
    *,
    l2_intake_packet: dict[str, Any],
    tier_policy: dict[str, Any],
) -> dict[str, Any]:
    groups = _groups_ready_for_review(l2_intake_packet)
    current_groups = _dict(tier_policy.get("current_strategy_groups"))
    new_defaults = _dict(_dict(tier_policy.get("new_strategy_group_defaults")).get("known_new_groups"))
    tier_definitions = _dict(tier_policy.get("tier_definitions"))
    target_definition = _dict(tier_definitions.get(TARGET_TIER))
    forbidden_effects = _source_forbidden_effects(l2_intake_packet)

    rows = [
        _review_row(
            strategy_group_id=group,
            l2_intake_packet=l2_intake_packet,
            current_groups=current_groups,
            new_defaults=new_defaults,
            target_definition=target_definition,
        )
        for group in groups
    ]
    failed_rows = [row for row in rows if row["status"] == "failed"]
    ready_rows = [row for row in rows if row["status"] == "ready_to_apply"]
    applied_rows = [row for row in rows if row["status"] == "already_applied"]

    if forbidden_effects:
        status = "blocked_forbidden_effect"
        owner_state = "needs_intervention"
        next_step = "review_l2_intake_source_forbidden_effects"
    elif failed_rows:
        status = "l2_tier_policy_review_failed"
        owner_state = "coverage_review_needed"
        next_step = "repair_l2_tier_policy_preconditions"
    elif ready_rows:
        status = "l2_tier_policy_review_recommended"
        owner_state = "coverage_policy_update_ready"
        next_step = "apply_l2_tier_policy_without_l4_scope_change"
    elif applied_rows:
        status = "l2_tier_policy_review_applied"
        owner_state = "coverage_policy_current"
        next_step = "continue_l2_shadow_candidate_observation_without_l4_scope_change"
    else:
        status = "l2_tier_policy_review_no_candidates"
        owner_state = "waiting_for_opportunity"
        next_step = "continue_signal_coverage_monitoring"

    return {
        "scope": "strategygroup_l2_tier_policy_review",
        "status": status,
        "owner_state": owner_state,
        "source_l2_intake_status": l2_intake_packet.get("status"),
        "interaction": {
            "level": "L0_local_l2_tier_policy_review",
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "counts": {
            "candidate_count": len(rows),
            "ready_to_apply_count": len(ready_rows),
            "already_applied_count": len(applied_rows),
            "failed_count": len(failed_rows),
            "forbidden_effect_count": len(forbidden_effects),
        },
        "review_rows": rows,
        "decision": {
            "default_next_step": next_step,
            "target_tier": TARGET_TIER,
            "target_mode": TARGET_MODE,
            "groups_ready_to_apply_l2": [
                row["strategy_group_id"] for row in ready_rows
            ],
            "groups_already_l2": [row["strategy_group_id"] for row in applied_rows],
            "l4_scope_change_recommended": False,
            "real_order_scope_change_recommended": False,
            "shadow_candidate_creation_recommended_now": False,
        },
        "operator_command_plan": {
            "not_executed": True,
            "next_step": next_step,
            "starts_runtime": False,
            "changes_strategy_parameters": False,
            "changes_tier_policy": status == "l2_tier_policy_review_recommended",
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
            "server_interaction": False,
            "server_files_mutated": False,
            "runtime_started": False,
            "strategy_parameters_changed": False,
            "l4_real_order_scope_expanded": False,
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
    counts = _dict(packet.get("counts"))
    lines = [
        "# L2 Tier Policy Review",
        "",
        "## Owner 摘要",
        "",
        f"- Status: `{packet.get('status')}`",
        f"- Owner state: `{packet.get('owner_state')}`",
        f"- Candidate count: `{counts.get('candidate_count', 0)}`",
        f"- Ready to apply: `{counts.get('ready_to_apply_count', 0)}`",
        f"- Already L2: `{counts.get('already_applied_count', 0)}`",
        "- L4 scope change: `false`",
        "- Real order: `false`",
        "",
        "## Rows",
        "",
        _rows_table([row for row in packet.get("review_rows") or [] if isinstance(row, dict)]),
        "",
        "## 下一步",
        "",
        f"- `{_dict(packet.get('decision')).get('default_next_step')}`",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _review_row(
    *,
    strategy_group_id: str,
    l2_intake_packet: dict[str, Any],
    current_groups: dict[str, Any],
    new_defaults: dict[str, Any],
    target_definition: dict[str, Any],
) -> dict[str, Any]:
    base_key = _base_strategy_group_key(strategy_group_id)
    current_item = _dict(current_groups.get(strategy_group_id))
    current_tier = str(current_item.get("tier") or "")
    current_mode = str(current_item.get("mode") or "")
    default_tier = str(new_defaults.get(base_key) or "")
    source = "current_strategy_groups" if current_item else "new_strategy_group_defaults"
    dry_run_row = _dry_run_row(l2_intake_packet, strategy_group_id)

    checks = {
        "dry_run_status_passed": l2_intake_packet.get("status") == "l2_intake_dry_run_passed",
        "dry_run_row_passed": _dict(dry_run_row).get("status") == "passed",
        "target_tier_exists": bool(target_definition),
        "target_tier_is_non_real_order": target_definition.get("may_place_real_order") is False,
        "target_tier_does_not_reach_finalgate": target_definition.get("may_reach_finalgate") is False,
        "target_tier_does_not_reach_operation_layer": target_definition.get("may_reach_operation_layer") is False,
        "target_tier_allows_shadow_candidate": target_definition.get("may_prepare_shadow_candidate") is True,
        "source_policy_allows_l1_to_l2_review": (
            current_tier in {"", "L1", TARGET_TIER}
            and (bool(current_item) or default_tier == "L1")
        ),
        "not_l4_now": current_tier != "L4",
        "does_not_recommend_l4": True,
    }
    blockers = [name for name, ok in checks.items() if ok is not True]
    if blockers:
        status = "failed"
    elif current_tier == TARGET_TIER and current_mode == TARGET_MODE:
        status = "already_applied"
    else:
        status = "ready_to_apply"

    return {
        "strategy_group_id": strategy_group_id,
        "source": source,
        "current_tier": current_tier or default_tier or "unclassified",
        "current_mode": current_mode or "observe_only",
        "target_tier": TARGET_TIER,
        "target_mode": TARGET_MODE,
        "status": status,
        "checks": checks,
        "blockers": blockers,
        "policy_patch_shape": {
            "current_strategy_groups": {
                strategy_group_id: {
                    "tier": TARGET_TIER,
                    "mode": TARGET_MODE,
                    "reason": (
                        "Passed main-control L2 intake dry-run; may prepare "
                        "non-executing shadow-candidate evidence only and remains "
                        "outside L4 real-order scope."
                    ),
                }
            },
            "new_strategy_group_defaults": {
                "remove_known_new_group": base_key,
            },
        },
    }


def _groups_ready_for_review(packet: dict[str, Any]) -> list[str]:
    decision = _dict(packet.get("decision"))
    groups = [str(item) for item in decision.get("groups_ready_for_l2_policy_review") or []]
    return sorted(set(group for group in groups if group))


def _dry_run_row(packet: dict[str, Any], strategy_group_id: str) -> dict[str, Any]:
    for row in packet.get("dry_run_rows") or []:
        if isinstance(row, dict) and row.get("strategy_group_id") == strategy_group_id:
            return row
    return {}


def _source_forbidden_effects(packet: dict[str, Any]) -> list[str]:
    safety = _dict(packet.get("safety_invariants"))
    effects = [str(item) for item in safety.get("source_forbidden_effects") or []]
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
            effects.append(f"source_l2_intake.safety.{key}")
    return sorted(set(effects))


def _base_strategy_group_key(strategy_group_id: str) -> str:
    if strategy_group_id.endswith("-001"):
        return strategy_group_id[:-4]
    return strategy_group_id


def _rows_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "| StrategyGroup | Status | Current | Target |\n| --- | --- | --- | --- |\n| none | - | - | - |"
    output = [
        "| StrategyGroup | Status | Current | Target |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        output.append(
            "| `{}` | `{}` | `{}` | `{}` |".format(
                row.get("strategy_group_id"),
                row.get("status"),
                row.get("current_tier"),
                row.get("target_tier"),
            )
        )
    return "\n".join(output)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--l2-intake-dry-run-json", default=str(DEFAULT_L2_INTAKE_DRY_RUN_JSON))
    parser.add_argument("--tier-policy-json", default=str(DEFAULT_TIER_POLICY_JSON))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OWNER_PROGRESS))
    args = parser.parse_args(argv)

    packet = build_l2_tier_policy_review(
        l2_intake_packet=_read_json_object(Path(args.l2_intake_dry_run_json).expanduser()),
        tier_policy=_read_json_object(Path(args.tier_policy_json).expanduser()),
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
