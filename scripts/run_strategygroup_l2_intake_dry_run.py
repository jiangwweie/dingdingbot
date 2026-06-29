#!/usr/bin/env python3
"""Run a local non-executing dry-run for conditional L2 StrategyGroup intake.

The dry-run validates that a broader observe-only StrategyGroup can be carried
as a main-control intake artifact without changing tier policy or touching the
real execution path. It does not create candidates, call FinalGate, call the
Operation Layer, or place orders.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.strategygroup_non_executing_projection import (  # noqa: E402
    L2_NON_EXECUTING_SOURCE_TRUE_KEYS,
    legacy_authority_mirror_effects_for_artifacts,
    non_executing_interaction,
    non_executing_safety_boundary,
    review_outcome_default_next_step,
    review_outcome_state_boundary,
    review_outcome_value,
    source_forbidden_effects,
)


DEFAULT_L2_READINESS_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-l2-readiness-review.json"
)
DEFAULT_HANDOFF_ROOT = REPO_ROOT / "docs/current/strategy-group-handoffs"
DEFAULT_OUTPUT_JSON = REPO_ROOT / "output/runtime-monitor/latest-l2-intake-dry-run.json"
DEFAULT_OWNER_PROGRESS = REPO_ROOT / "output/runtime-monitor/latest-l2-intake-dry-run.md"
REQUIRED_FACT_CATEGORIES = {"account", "derivatives", "exchange", "market", "risk", "strategy"}
EXECUTION_BOUNDARY_FALSE_FIELDS = {
    "runtime_registration_authorized",
    "candidate_creation_authorized",
    "final_gate_input",
    "operation_layer_input",
    "real_submit_authorized",
}


def build_l2_intake_dry_run(
    *,
    l2_readiness_artifact: dict[str, Any],
    handoff_root: Path = DEFAULT_HANDOFF_ROOT,
) -> dict[str, Any]:
    source_rows = [
        row
        for row in l2_readiness_artifact.get("readiness_rows") or []
        if isinstance(row, dict)
    ]
    rows = [
        row
        for row in source_rows
        if row.get("conditional_l2_review_candidate") is True
    ]
    enabled_rows = [
        row
        for row in source_rows
        if row.get("l2_shadow_candidate_observation_enabled") is True
    ]
    blocked_rows = [
        row
        for row in source_rows
        if row.get("conditional_l2_review_candidate") is not True
        and row.get("l2_shadow_candidate_observation_enabled") is not True
    ]
    dry_run_rows = [
        _dry_run_row(row=row, handoff_root=handoff_root)
        for row in rows
    ]
    failed_rows = [row for row in dry_run_rows if row["status"] != "passed"]
    forbidden_effects = _source_forbidden_effects(l2_readiness_artifact)

    if forbidden_effects:
        status = "blocked_forbidden_effect"
        owner_state = "needs_intervention"
        next_step = "review_l2_readiness_source_forbidden_effects"
    elif failed_rows:
        status = "l2_intake_dry_run_failed"
        owner_state = "coverage_review_needed"
        next_step = "repair_l2_intake_handoff_before_tier_policy_review"
    elif dry_run_rows:
        status = "l2_intake_dry_run_passed"
        owner_state = "coverage_review_ready"
        next_step = "review_l2_tier_policy_change_without_l4_scope_change"
    else:
        status = "l2_intake_dry_run_no_candidates"
        owner_state = "waiting_for_opportunity"
        next_step = "continue_signal_coverage_monitoring"

    return {
        "scope": "strategygroup_l2_intake_dry_run",
        "status": status,
        "owner_state": owner_state,
        "source_l2_readiness_status": l2_readiness_artifact.get("status"),
        "interaction": non_executing_interaction("L0_local_l2_intake_dry_run"),
        "counts": {
            "candidate_count": len(dry_run_rows),
            "passed_count": len(dry_run_rows) - len(failed_rows),
            "failed_count": len(failed_rows),
            "source_readiness_row_count": len(source_rows),
            "source_conditional_candidate_count": len(rows),
            "source_enabled_l2_count": len(enabled_rows),
            "source_blocked_count": len(blocked_rows),
            "forbidden_effect_count": len(forbidden_effects),
        },
        "dry_run_rows": dry_run_rows,
        "source_readiness_rows": [_source_row(row) for row in source_rows],
        "review_outcome_state": review_outcome_state_boundary(
            source_role="l2_intake_dry_run_provenance",
            review_scope="l2_intake_dry_run",
            extra={
                "default_next_step": next_step,
                "no_candidate_reason": (
                    "no_conditional_l2_review_candidates"
                    if not dry_run_rows
                    else None
                ),
                "tier_policy_change_ready_for_review": (
                    status == "l2_intake_dry_run_passed"
                ),
                "l4_scope_change_recommended": False,
                "shadow_candidate_creation_recommended_now": False,
                "groups_ready_for_l2_policy_review": [
                    row["strategy_group_id"]
                    for row in dry_run_rows
                    if row["status"] == "passed"
                ],
                "enabled_l2_groups": [
                    str(row.get("strategy_group_id") or "unknown")
                    for row in enabled_rows
                ],
                "blocked_groups": [
                    str(row.get("strategy_group_id") or "unknown")
                    for row in blocked_rows
                ],
            },
        ),
        "safety_invariants": non_executing_safety_boundary(
            true_keys=("review_only",),
            false_keys=(
                "server_interaction",
                "server_files_mutated",
                "runtime_started",
                "strategy_parameters_changed",
                "tier_policy_changed",
                "l4_real_order_scope_expanded",
                "shadow_candidate_created",
                "final_gate_called",
                "operation_layer_called",
                "order_created",
                "order_lifecycle_called",
                "exchange_write_called",
                "withdrawal_or_transfer_created",
            ),
            source_forbidden_effects=forbidden_effects,
        ),
    }


def render_owner_progress_markdown(artifact: dict[str, Any]) -> str:
    counts = artifact.get("counts") if isinstance(artifact.get("counts"), dict) else {}
    lines = [
        "# L2 Intake Dry-Run",
        "",
        "## Owner 摘要",
        "",
        f"- Status: `{artifact.get('status')}`",
        f"- Owner state: `{artifact.get('owner_state')}`",
        f"- Candidate count: `{counts.get('candidate_count', 0)}`",
        f"- Passed count: `{counts.get('passed_count', 0)}`",
        f"- Source enabled L2: `{counts.get('source_enabled_l2_count', 0)}`",
        f"- Source blocked rows: `{counts.get('source_blocked_count', 0)}`",
        f"- No-candidate reason: `{review_outcome_value(artifact, 'no_candidate_reason')}`",
        "- Tier policy changed: `false`",
        "- L4 scope changed: `false`",
        "- Real order: `false`",
        "",
        "## Rows",
        "",
        _rows_table([row for row in artifact.get("dry_run_rows") or [] if isinstance(row, dict)]),
        "",
        "## Source Readiness Rows",
        "",
        _source_rows_table(
            [
                row
                for row in artifact.get("source_readiness_rows") or []
                if isinstance(row, dict)
            ]
        ),
        "",
        "## 下一步",
        "",
        f"- `{review_outcome_default_next_step(artifact)}`",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _dry_run_row(*, row: dict[str, Any], handoff_root: Path) -> dict[str, Any]:
    strategy_group_id = str(row.get("strategy_group_id") or "unknown")
    handoff_path = handoff_root / strategy_group_id / "handoff.json"
    blockers: list[str] = []
    handoff = _read_json_object_if_exists(handoff_path)
    if not handoff:
        blockers.append("strategy_intake_source_json_missing")
    boundary = _dict(handoff.get("execution_boundary"))
    mode = _dict(handoff.get("mode_recommendation"))
    risk_defaults = _dict(handoff.get("risk_defaults"))
    required_facts = _dict(handoff.get("required_facts"))
    required_categories = set(required_facts)
    signal_rule = _dict(handoff.get("signal_ready_rule"))
    symbol = _exchange_symbol(row.get("symbol"))

    checks = {
        "intake_source_json_present": bool(handoff),
        "default_mode_observe_only": mode.get("default") == "observe_only",
        "conditional_signal_side_supported": row.get("side") in (handoff.get("supported_sides") or []),
        "conditional_signal_symbol_supported": symbol in (handoff.get("supported_symbols") or []),
        "required_fact_categories_present": REQUIRED_FACT_CATEGORIES.issubset(required_categories),
        "l2_signal_status_is_observe_only": signal_rule.get("status_name") == "would_enter_observe_only",
        "research_intake_source_only": boundary.get("research_intake_source_only") is True,
        "does_not_authorize_execution": all(
            boundary.get(name) is False for name in EXECUTION_BOUNDARY_FALSE_FIELDS
        ),
        "not_live_order_eligible": risk_defaults.get("risk_tier") == "not_live_order_eligible",
        "zero_live_notional": str(risk_defaults.get("max_notional_per_action_usdt") or "") == "0",
        "zero_active_positions": int(risk_defaults.get("max_active_positions") or 0) == 0,
        "source_l2_row_does_not_allow_real_order": row.get("may_place_real_order_now") is False,
        "source_l2_row_does_not_allow_shadow_now": row.get("may_create_shadow_candidate_now") is False,
    }
    blockers.extend(name for name, ok in checks.items() if ok is not True)
    return {
        "strategy_group_id": strategy_group_id,
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "status": "passed" if not blockers else "failed",
        "intake_source_json": str(handoff_path),
        "checks": checks,
        "blockers": blockers,
        "next_step": (
            "review_l2_tier_policy_change_without_l4_scope_change"
            if not blockers
            else "repair_l2_intake_handoff"
        ),
    }


def _source_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_group_id": str(row.get("strategy_group_id") or "unknown"),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "current_tier": row.get("current_tier"),
        "l2_readiness": row.get("l2_readiness"),
        "recommended_action": row.get("recommended_action"),
        "conditional_l2_review_candidate": (
            row.get("conditional_l2_review_candidate") is True
        ),
        "l2_shadow_candidate_observation_enabled": (
            row.get("l2_shadow_candidate_observation_enabled") is True
        ),
        "blocking_gaps_before_l2": [
            str(item) for item in row.get("blocking_gaps_before_l2") or []
        ],
    }


def _source_forbidden_effects(artifact: dict[str, Any]) -> list[str]:
    effects = source_forbidden_effects(
        (("source_l2_readiness", artifact),),
        true_keys=L2_NON_EXECUTING_SOURCE_TRUE_KEYS,
    )
    effects.extend(
        legacy_authority_mirror_effects_for_artifacts(
            (("source_l2_readiness", artifact),),
            root_section_name="root",
            section_names=("checks", "safety_invariants", "review_outcome_state"),
            row_names=("readiness_rows",),
            row_id_keys=("strategy_group_id", "symbol"),
        )
    )
    return sorted(set(effect for effect in effects if effect))


def _rows_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "| StrategyGroup | Status | Next Step |\n| --- | --- | --- |\n| none | - | - |"
    output = [
        "| StrategyGroup | Status | Next Step |",
        "| --- | --- | --- |",
    ]
    for row in rows:
        output.append(
            "| `{}` | `{}` | `{}` |".format(
                row.get("strategy_group_id"),
                row.get("status"),
                row.get("next_step"),
            )
        )
    return "\n".join(output)


def _source_rows_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return (
            "| StrategyGroup | Symbol | Side | Tier | L2 Readiness | Source State | Blocking gaps |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| none | - | - | - | - | - | - |"
        )
    output = [
        "| StrategyGroup | Symbol | Side | Tier | L2 Readiness | Source State | Blocking gaps |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        output.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row.get("strategy_group_id"),
                row.get("symbol"),
                row.get("side"),
                row.get("current_tier"),
                row.get("l2_readiness"),
                _source_state(row),
                _join_codes(row.get("blocking_gaps_before_l2")),
            )
        )
    return "\n".join(output)


def _source_state(row: dict[str, Any]) -> str:
    if row.get("conditional_l2_review_candidate") is True:
        return "conditional_l2_candidate"
    if row.get("l2_shadow_candidate_observation_enabled") is True:
        return "enabled_l2"
    return "blocked"


def _join_codes(values: Any) -> str:
    codes = [str(value) for value in values or [] if str(value or "").strip()]
    return ", ".join(codes[:4]) if codes else "none"


def _exchange_symbol(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    return text.replace("/", "").replace(":USDT", "")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return payload


def _read_json_object_if_exists(path: Path) -> dict[str, Any]:
    try:
        return _read_json_object(path)
    except FileNotFoundError:
        return {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--l2-readiness-json", default=str(DEFAULT_L2_READINESS_JSON))
    parser.add_argument("--handoff-root", default=str(DEFAULT_HANDOFF_ROOT))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OWNER_PROGRESS))
    args = parser.parse_args(argv)

    artifact = build_l2_intake_dry_run(
        l2_readiness_artifact=_read_json_object(
            Path(args.l2_readiness_json).expanduser()
        ),
        handoff_root=Path(args.handoff_root).expanduser(),
    )
    payload = json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    if args.output_owner_progress:
        owner_path = Path(args.output_owner_progress).expanduser()
        owner_path.parent.mkdir(parents=True, exist_ok=True)
        owner_path.write_text(render_owner_progress_markdown(artifact), encoding="utf-8")
    print(payload)
    return 0 if artifact["status"] != "blocked_forbidden_effect" else 2


if __name__ == "__main__":
    raise SystemExit(main())
