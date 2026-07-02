#!/usr/bin/env python3
"""Build an L1-to-L2 readiness review from signal coverage expansion evidence.

This is a local read-only review. It may identify which observe-only
StrategyGroups deserve handoff-intake or dry-run work, but it does not change
tiers, start runtimes, create shadow candidates, call FinalGate, call Operation
Layer, or place orders.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from strategygroup_non_executing_projection import (  # noqa: E402
    L2_NON_EXECUTING_SOURCE_TRUE_KEYS,
    legacy_authority_mirror_effects_for_artifacts,
    legacy_authority_mirror_present_errors,
    non_executing_interaction,
    non_executing_safety_boundary,
    review_outcome_default_next_step,
    review_outcome_state_boundary,
    source_forbidden_effects,
)

DEFAULT_EXPANSION_POLICY_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/main-control-signal-coverage-expansion-policy.json"
)
DEFAULT_OUTPUT_JSON = REPO_ROOT / "output/runtime-monitor/latest-l2-readiness-review.json"
DEFAULT_OWNER_PROGRESS = REPO_ROOT / "output/runtime-monitor/latest-l2-readiness-review.md"


READY_OR_CONDITIONAL = {"conditional_l2_review_candidate", "l2_review_ready"}
L2_ALREADY_ENABLED = {"l2_shadow_candidate_observation_enabled"}


def build_l2_readiness_review(
    *,
    expansion_review_artifact: dict[str, Any],
    expansion_policy: dict[str, Any],
) -> dict[str, Any]:
    policy_groups = _as_dict(expansion_policy.get("strategy_groups"))
    review_rows = _review_rows_with_enabled_l2_policy(
        _dict_rows(expansion_review_artifact.get("review_rows")),
        policy_groups,
    )
    readiness_rows = [
        _readiness_row(row=row, policy=_as_dict(policy_groups.get(str(row.get("strategy_group_id") or ""))))
        for row in review_rows
    ]
    conditional_rows = [
        row
        for row in readiness_rows
        if row["l2_readiness"] in READY_OR_CONDITIONAL
    ]
    enabled_rows = [
        row
        for row in readiness_rows
        if row["l2_readiness"] in L2_ALREADY_ENABLED
    ]
    blocked_rows = [
        row
        for row in readiness_rows
        if row["l2_readiness"] not in READY_OR_CONDITIONAL
        and row["l2_readiness"] not in L2_ALREADY_ENABLED
    ]
    forbidden_effects = _forbidden_effects(expansion_review_artifact, expansion_policy)

    if forbidden_effects:
        status = "blocked_forbidden_effect"
        owner_state = "needs_intervention"
        next_step = "review_l2_readiness_source_forbidden_effects"
    elif conditional_rows:
        status = "l2_readiness_review_has_conditional_candidate"
        owner_state = "coverage_review_needed"
        next_step = _conditional_next_step(conditional_rows)
    elif enabled_rows:
        status = "l2_readiness_review_already_enabled"
        owner_state = "coverage_policy_current"
        next_step = "continue_l2_shadow_candidate_observation_without_l4_scope_change"
    elif readiness_rows:
        status = "l2_readiness_review_all_blocked"
        owner_state = "coverage_review_needed"
        next_step = "keep_observe_only_and_replay_review"
    else:
        status = "l2_readiness_review_no_rows"
        owner_state = "waiting_for_opportunity"
        next_step = "continue_signal_coverage_monitoring"

    return {
        "scope": "strategygroup_l2_readiness_review",
        "status": status,
        "owner_state": owner_state,
        "source_expansion_review_status": expansion_review_artifact.get("status"),
        "interaction": non_executing_interaction("L0_local_l2_readiness_review"),
        "counts": {
            "review_row_count": len(readiness_rows),
            "conditional_l2_candidate_count": len(conditional_rows),
            "enabled_l2_count": len(enabled_rows),
            "blocked_count": len(blocked_rows),
            "classifier_repair_spec_ready_count": sum(
                1
                for row in readiness_rows
                if _as_dict(row.get("classifier_repair_spec")).get("status")
                == "local_repair_spec_ready"
            ),
            "economic_replay_spec_ready_count": sum(
                1
                for row in readiness_rows
                if _as_dict(row.get("economic_replay_spec")).get("status")
                == "local_economic_replay_spec_ready"
            ),
            "classifier_revision_executed_count": sum(
                1
                for row in readiness_rows
                if _as_dict(
                    _as_dict(row.get("classifier_repair_spec")).get(
                        "revision_execution"
                    )
                ).get("status")
                == "local_classifier_revision_executed"
            ),
            "economic_replay_executed_count": sum(
                1
                for row in readiness_rows
                if _as_dict(
                    _as_dict(row.get("economic_replay_spec")).get("replay_execution")
                ).get("status")
                == "local_economic_replay_executed"
            ),
            "forbidden_effect_count": len(forbidden_effects),
        },
        "readiness_rows": readiness_rows,
        "review_outcome_state": review_outcome_state_boundary(
            source_role="l2_readiness_review_provenance",
            review_scope="l2_readiness_review",
            extra={
                "tier_policy_change_recommended": False,
                "l4_scope_change_recommended": False,
                "shadow_candidate_creation_recommended_now": False,
                "handoff_intake_recommended_groups": [
                    row["strategy_group_id"] for row in conditional_rows
                ],
                "enabled_l2_groups": [
                    row["strategy_group_id"] for row in enabled_rows
                ],
                "default_next_step": next_step,
            },
        ),
        "safety_invariants": non_executing_safety_boundary(
            true_keys=(
                "review_only",
                "does_not_change_tier_policy",
                "does_not_expand_l4_real_order_scope",
                "does_not_create_shadow_candidate",
            ),
            false_keys=(
                "server_interaction",
                "server_files_mutated",
                "runtime_started",
                "strategy_parameters_changed",
                "tier_policy_changed",
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
    lines = [
        "# L2 观察面准备度评审",
        "",
        "## Owner 摘要",
        "",
        f"- Status: `{artifact.get('status')}`",
        f"- Owner state: `{artifact.get('owner_state')}`",
        f"- Conditional L2 candidates: `{_as_dict(artifact.get('counts')).get('conditional_l2_candidate_count', 0)}`",
        f"- Enabled L2 groups: `{_as_dict(artifact.get('counts')).get('enabled_l2_count', 0)}`",
        f"- Blocked rows: `{_as_dict(artifact.get('counts')).get('blocked_count', 0)}`",
        "- Tier policy change: `false`",
        "- L4 scope change: `false`",
        "- Shadow candidate now: `false`",
        "",
        "## Readiness Rows",
        "",
        _readiness_table(_dict_rows(artifact.get("readiness_rows"))),
        "",
        "## 下一步",
        "",
        f"- `{review_outcome_default_next_step(artifact)}`",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _readiness_row(*, row: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    strategy_group_id = str(row.get("strategy_group_id") or "unknown")
    l2_readiness = str(policy.get("l2_readiness") or "missing_policy")
    return {
        "strategy_group_id": strategy_group_id,
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "current_tier": row.get("current_tier")
        or policy.get("current_main_control_tier")
        or policy.get("current_tier"),
        "coverage_review_priority": policy.get("coverage_review_priority") or "unknown",
        "l2_readiness": l2_readiness,
        "recommended_action": policy.get("recommended_action")
        or "require_policy_before_l2_review",
        "positive_evidence": [str(item) for item in policy.get("positive_evidence") or []],
        "blocking_gaps_before_l2": [
            str(item) for item in policy.get("blocking_gaps_before_l2") or []
        ],
        "classifier_repair_spec": _classifier_repair_spec(policy),
        "economic_replay_spec": _economic_replay_spec(policy),
        "conditional_l2_review_candidate": l2_readiness in READY_OR_CONDITIONAL,
        "l2_shadow_candidate_observation_enabled": l2_readiness in L2_ALREADY_ENABLED,
        "may_change_tier_policy_now": False,
        "may_create_shadow_candidate_now": False,
        "may_place_real_order_now": False,
    }


def _review_rows_with_enabled_l2_policy(
    review_rows: list[dict[str, Any]],
    policy_groups: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = list(review_rows)
    existing_groups = {
        str(row.get("strategy_group_id") or "unknown") for row in review_rows
    }
    for group, policy_value in sorted(policy_groups.items()):
        if group in existing_groups:
            continue
        policy = _as_dict(policy_value)
        if str(policy.get("l2_readiness") or "") not in L2_ALREADY_ENABLED:
            continue
        rows.append(
            {
                "strategy_group_id": group,
                "symbol": policy.get("symbol"),
                "side": policy.get("side"),
                "current_tier": policy.get("current_main_control_tier")
                or policy.get("current_tier"),
                "source": "runtime_tier_policy_enabled_l2_shadow",
                "would_enter": False,
            }
        )
    return rows


def _classifier_repair_spec(policy: dict[str, Any]) -> dict[str, Any]:
    spec = _as_dict(policy.get("classifier_repair_spec"))
    if not spec:
        return {}
    return {
        "status": str(spec.get("status") or "unknown"),
        "target_classifier": str(spec.get("target_classifier") or "unknown"),
        "blocking_gap_keys": [
            str(item) for item in spec.get("blocking_gap_keys") or []
        ],
        "required_entry_states": [
            str(item) for item in spec.get("required_entry_states") or []
        ],
        "required_disable_states": [
            str(item) for item in spec.get("required_disable_states") or []
        ],
        "replay_acceptance_cases": [
            str(item) for item in spec.get("replay_acceptance_cases") or []
        ],
        "acceptance_signal": str(spec.get("acceptance_signal") or ""),
        "revision_execution": _revision_execution(spec.get("revision_execution")),
        "not_execution_authority": spec.get("not_execution_authority") is True,
        "not_l2_promotion_authority": spec.get("not_l2_promotion_authority") is True,
        "not_l4_scope_change": spec.get("not_l4_scope_change") is True,
    }


def _economic_replay_spec(policy: dict[str, Any]) -> dict[str, Any]:
    spec = _as_dict(policy.get("economic_replay_spec"))
    if not spec:
        return {}
    return {
        "status": str(spec.get("status") or "unknown"),
        "blocking_gap_keys": [
            str(item) for item in spec.get("blocking_gap_keys") or []
        ],
        "required_cost_fields": [
            str(item) for item in spec.get("required_cost_fields") or []
        ],
        "replay_acceptance_cases": [
            str(item) for item in spec.get("replay_acceptance_cases") or []
        ],
        "acceptance_signal": str(spec.get("acceptance_signal") or ""),
        "replay_execution": _replay_execution(spec.get("replay_execution")),
        "not_execution_authority": spec.get("not_execution_authority") is True,
        "not_l2_promotion_authority": spec.get("not_l2_promotion_authority") is True,
        "not_l4_scope_change": spec.get("not_l4_scope_change") is True,
    }


def _revision_execution(value: Any) -> dict[str, Any]:
    execution = _as_dict(value)
    if not execution:
        return {}
    return {
        "status": str(execution.get("status") or "unknown"),
        "implementation_ref": str(execution.get("implementation_ref") or ""),
        "logic_version": str(execution.get("logic_version") or ""),
        "executed_entry_states": [
            str(item) for item in execution.get("executed_entry_states") or []
        ],
        "executed_disable_states": [
            str(item) for item in execution.get("executed_disable_states") or []
        ],
        "validation_cases": [
            str(item) for item in execution.get("validation_cases") or []
        ],
        "not_execution_authority": execution.get("not_execution_authority") is True,
        "not_l2_promotion_authority": execution.get("not_l2_promotion_authority")
        is True,
        "not_l4_scope_change": execution.get("not_l4_scope_change") is True,
    }


def _replay_execution(value: Any) -> dict[str, Any]:
    execution = _as_dict(value)
    if not execution:
        return {}
    return {
        "status": str(execution.get("status") or "unknown"),
        "implementation_ref": str(execution.get("implementation_ref") or ""),
        "covered_cost_fields": [
            str(item) for item in execution.get("covered_cost_fields") or []
        ],
        "validation_cases": [
            str(item) for item in execution.get("validation_cases") or []
        ],
        "not_execution_authority": execution.get("not_execution_authority") is True,
        "not_l2_promotion_authority": execution.get("not_l2_promotion_authority")
        is True,
        "not_l4_scope_change": execution.get("not_l4_scope_change") is True,
    }


def _conditional_next_step(rows: list[dict[str, Any]]) -> str:
    missing_handoff = any(
        "main_control_handoff_not_imported" in row.get("blocking_gaps_before_l2", [])
        for row in rows
    )
    if missing_handoff:
        return "prepare_conditional_l2_handoff_intake_without_tier_change"
    return "run_conditional_l2_dry_run_without_tier_change"


def _forbidden_effects(
    expansion_review_artifact: dict[str, Any],
    expansion_policy: dict[str, Any],
) -> list[str]:
    effects = source_forbidden_effects(
        (
            ("expansion_review", expansion_review_artifact),
            ("expansion_policy", expansion_policy),
        ),
        true_keys=L2_NON_EXECUTING_SOURCE_TRUE_KEYS,
    )
    effects.extend(
        legacy_authority_mirror_effects_for_artifacts(
            (("expansion_review", expansion_review_artifact),),
            section_names=("safety_invariants",),
            row_names=("review_rows",),
            row_id_keys=("strategy_group_id",),
        )
    )
    policy_groups = _as_dict(expansion_policy.get("strategy_groups"))
    for group, policy in policy_groups.items():
        effects.extend(
            legacy_authority_mirror_present_errors(
                _as_dict(policy),
                label_prefix=f"expansion_policy.strategy_groups.{group}.",
            )
        )
    return sorted(set(effects))


def _readiness_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return (
            "| StrategyGroup | Symbol | Side | Tier | Priority | L2 Readiness | Action | Blocking gaps |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
            "| none | - | - | - | - | - | - | - |"
        )
    output = [
        "| StrategyGroup | Symbol | Side | Tier | Priority | L2 Readiness | Action | Blocking gaps |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        output.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row.get("strategy_group_id"),
                row.get("symbol"),
                row.get("side"),
                row.get("current_tier"),
                row.get("coverage_review_priority"),
                row.get("l2_readiness"),
                row.get("recommended_action"),
                _join_codes(row.get("blocking_gaps_before_l2")),
            )
        )
    return "\n".join(output)


def _join_codes(values: Any) -> str:
    codes = [str(value) for value in values or [] if str(value or "").strip()]
    return ", ".join(codes[:4]) if codes else "none"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)]


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return payload


def _load_optional_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _load_json_object(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expansion-review-json")
    parser.add_argument("--expansion-policy-json", default=str(DEFAULT_EXPANSION_POLICY_JSON))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OWNER_PROGRESS))
    args = parser.parse_args(argv)

    artifact = build_l2_readiness_review(
        expansion_review_artifact=_load_optional_json_object(
            Path(args.expansion_review_json).expanduser()
        )
        if args.expansion_review_json
        else {},
        expansion_policy=_load_json_object(Path(args.expansion_policy_json).expanduser()),
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
