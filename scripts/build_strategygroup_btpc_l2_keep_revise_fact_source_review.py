#!/usr/bin/env python3
"""Build the BTPC L2 keep/revise/fact-source review artifact.

This command turns the BTPC proxy replay quality rollup into a stable local
review artifact. It is a Signal Observation review step: it can recommend what
local work comes next for BTPC L2 shadow observation, but it cannot promote
BTPC, satisfy live RequiredFacts, call FinalGate, call Operation Layer, or place
orders.
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
    EXTENDED_SOURCE_SAFETY_TRUE_KEYS,
    artifact_source_forbidden_effects,
    legacy_authority_mirror_effects_for_artifacts,
    legacy_authority_mirror_present_errors,
    non_executing_interaction,
    non_executing_safety_boundary,
    review_outcome_default_next_step,
    review_outcome_flag,
    review_outcome_state_boundary,
)

DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-btpc-l2-keep-revise-fact-source-review.json"
)
DEFAULT_OWNER_PROGRESS = (
    REPO_ROOT
    / "output/runtime-monitor/latest-btpc-l2-keep-revise-fact-source-review.md"
)


ACTION_SPECS = {
    "attach_live_derivatives_fact_sources_before_btpc_live_eligibility": {
        "review_area": "live_fact_source",
        "owner_priority": "signal-observation-grade-review",
        "action": "attach_live_derivatives_fact_sources_before_btpc_live_eligibility",
        "reason": "proxy_replay_resolves_missing_derivatives_context_for_l2_review_only",
        "completion_signal": "btpc_live_derivatives_fact_source_mapping_ready_without_live_authority",
        "validation_command": "python3 scripts/build_strategygroup_btpc_l2_keep_revise_fact_source_review.py",
    },
    "review_btpc_strong_uptrend_conflict_disable_rule": {
        "review_area": "classifier_rule",
        "owner_priority": "signal-observation-grade-review",
        "action": "review_btpc_strong_uptrend_conflict_disable_rule",
        "reason": "strong_uptrend_conflict_case_remains_revise_before_promotion",
        "completion_signal": "btpc_strong_uptrend_conflict_rule_review_recorded",
        "validation_command": "PYTHONDONTWRITEBYTECODE=1 pytest -q tests/unit/test_strategygroup_btpc_l2_keep_revise_fact_source_review.py",
    },
    "review_btpc_freshness_or_classifier_stale_signal_rule": {
        "review_area": "classifier_rule",
        "owner_priority": "signal-observation-grade-review",
        "action": "review_btpc_freshness_or_classifier_stale_signal_rule",
        "reason": "stale_signal_case_remains_revise_before_promotion",
        "completion_signal": "btpc_freshness_or_classifier_stale_signal_rule_review_recorded",
        "validation_command": "PYTHONDONTWRITEBYTECODE=1 pytest -q tests/unit/test_strategygroup_btpc_l2_keep_revise_fact_source_review.py",
    },
    "continue_btpc_l2_shadow_observation_with_proxy_context": {
        "review_area": "observation",
        "owner_priority": "signal-observation-grade-review",
        "action": "continue_btpc_l2_shadow_observation_with_proxy_context",
        "reason": "would_enter_proxy_reviewable_cases_exist_but_do_not_grant_live_authority",
        "completion_signal": "btpc_l2_shadow_observation_continues_with_proxy_context",
        "validation_command": "python3 scripts/run_strategygroup_runtime_local_monitor_sequence.py --daily-check-mode cache --owner-progress",
    },
}


def build_btpc_l2_keep_revise_fact_source_review(
    *,
    opportunity_review_work_loop_artifact: dict[str, Any],
    btpc_proxy_replay_quality_artifact: dict[str, Any],
) -> dict[str, Any]:
    btpc_quality_row = _btpc_strategy_quality_row(opportunity_review_work_loop_artifact)
    proxy_rollup = _as_dict(btpc_quality_row.get("btpc_proxy_replay_quality"))
    forbidden_effects = _forbidden_effects(
        opportunity_review_work_loop_artifact,
        btpc_proxy_replay_quality_artifact,
        btpc_quality_row,
    )
    source_ready = _source_ready(btpc_quality_row, proxy_rollup)
    action_rows = _action_rows(
        action_items=[str(item) for item in proxy_rollup.get("action_items") or []],
        case_rows=_dict_rows(btpc_proxy_replay_quality_artifact.get("case_rows")),
    )
    if forbidden_effects:
        status = "blocked_forbidden_effect"
    elif not source_ready:
        status = "btpc_l2_review_waiting_for_proxy_quality_rollup"
    elif action_rows:
        status = "btpc_l2_keep_revise_fact_source_review_ready"
    else:
        status = "btpc_l2_review_no_action_items"

    return {
        "schema": "brc.btpc_l2_keep_revise_fact_source_review.v1",
        "scope": "btpc_l2_keep_revise_fact_source_review",
        "status": status,
        "source_status": {
            "opportunity_review_work_loop": opportunity_review_work_loop_artifact.get("status"),
            "btpc_proxy_replay_quality_review": btpc_proxy_replay_quality_artifact.get(
                "status"
            ),
            "btpc_strategy_asset_recommendation": btpc_quality_row.get(
                "strategy_asset_recommendation"
            ),
        },
        "interaction": non_executing_interaction(
            "L0_local_btpc_l2_keep_revise_fact_source_review"
        ),
        "counts": {
            "action_item_count": len(action_rows),
            "live_fact_source_action_count": sum(
                1 for row in action_rows if row.get("review_area") == "live_fact_source"
            ),
            "classifier_rule_action_count": sum(
                1 for row in action_rows if row.get("review_area") == "classifier_rule"
            ),
            "observation_action_count": sum(
                1 for row in action_rows if row.get("review_area") == "observation"
            ),
            "proxy_replay_case_count": _int(proxy_rollup.get("case_count")),
            "proxy_reviewable_would_enter_count": _int(
                proxy_rollup.get("proxy_reviewable_would_enter_count")
            ),
            "revise_case_count": _int(proxy_rollup.get("revise_case_count")),
            "l4_scope_change_recommended_count": 0,
            "forbidden_effect_count": len(forbidden_effects),
        },
        "btpc_state": {
            "strategy_group_id": "BTPC-001",
            "current_tier": btpc_quality_row.get("current_tier"),
            "tier_state": btpc_quality_row.get("tier_state"),
            "strategy_asset_recommendation": btpc_quality_row.get(
                "strategy_asset_recommendation"
            ),
            "next_stage": btpc_quality_row.get("next_stage"),
            "l2_shadow_observation_can_continue": status
            == "btpc_l2_keep_revise_fact_source_review_ready",
            "revise_before_promotion": bool(action_rows),
            "live_required_facts_satisfied": False,
            "l2_promotion_authority": False,
            "l4_scope_change_recommended": False,
        },
        "action_rows": action_rows,
        "review_outcome_state": review_outcome_state_boundary(
            source_role="btpc_l2_keep_revise_fact_source_provenance",
            review_scope="l2_keep_revise_fact_source",
            extra={
                "strategy_group_id": "BTPC-001",
                "keep_l2_shadow_observation": (
                    status == "btpc_l2_keep_revise_fact_source_review_ready"
                ),
                "revise_fact_classifier_inputs_before_promotion": bool(action_rows),
                "attach_live_fact_sources_before_live_eligibility": any(
                    row.get("review_area") == "live_fact_source"
                    for row in action_rows
                ),
                "classifier_review_required_before_promotion": any(
                    row.get("review_area") == "classifier_rule"
                    for row in action_rows
                ),
                "proxy_review_satisfies_live_required_facts": False,
                "tier_policy_change_recommended_now": False,
                "l2_promotion_recommended_now": False,
                "l4_scope_change_recommended": False,
                "real_order_scope_change_recommended": False,
                "default_next_step": _default_next_step(status),
            },
        ),
        "safety_invariants": non_executing_safety_boundary(
            true_keys=(
                "local_btpc_l2_review_outcome_only",
                "proxy_review_is_not_live_required_fact",
                "input_is_not_execution_authority",
                "does_not_lower_owner_selected_leverage",
                "does_not_change_live_profile_or_sizing_defaults",
            ),
            source_forbidden_effects=forbidden_effects,
        ),
    }


def render_owner_progress_markdown(artifact: dict[str, Any]) -> str:
    counts = _as_dict(artifact.get("counts"))
    lines = [
        "# BTPC L2 Keep / Revise / Fact Source Review",
        "",
        "## Summary",
        "",
        f"- Status: `{artifact.get('status')}`",
        f"- Action items: `{counts.get('action_item_count', 0)}`",
        f"- Live fact-source actions: `{counts.get('live_fact_source_action_count', 0)}`",
        f"- Classifier-rule actions: `{counts.get('classifier_rule_action_count', 0)}`",
        "- L2 promotion authority: `false`",
        "- L4 scope change: `false`",
        "",
        "## Actions",
        "",
        _action_table(_dict_rows(artifact.get("action_rows"))),
        "",
        "## Next",
        "",
        f"- `{review_outcome_default_next_step(artifact)}`",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _btpc_strategy_quality_row(artifact: dict[str, Any]) -> dict[str, Any]:
    quality = _as_dict(artifact.get("strategy_asset_recommendations"))
    for row in _dict_rows(quality.get("rows")):
        if row.get("strategy_group_id") == "BTPC-001":
            return row
    return {}


def _source_ready(btpc_quality_row: dict[str, Any], proxy_rollup: dict[str, Any]) -> bool:
    return (
        btpc_quality_row.get("strategy_asset_recommendation")
        == "keep_l2_shadow_and_revise_fact_classifier_inputs"
        and btpc_quality_row.get("candidate_or_finalgate_authority") is False
        and proxy_rollup.get("ready") is True
        and proxy_rollup.get("live_required_facts_satisfied") is False
        and proxy_rollup.get("l4_scope_change_recommended") is False
    )


def _action_rows(
    *,
    action_items: list[str],
    case_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    decision_cases = _cases_by_review_outcome(case_rows)
    for item in action_items:
        spec = ACTION_SPECS.get(item)
        if not spec:
            continue
        row = dict(spec)
        row["source_action_item"] = item
        row["evidence_cases"] = decision_cases.get(item, [])
        row["live_required_fact_authority"] = False
        row["l2_promotion_authority"] = False
        row["l4_scope_change_recommended"] = False
        row["candidate_or_finalgate_authority"] = False
        row["operation_layer_authority"] = False
        row["exchange_write_authority"] = False
        output.append(row)
    return output


def _cases_by_review_outcome(case_rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {
        "attach_live_derivatives_fact_sources_before_btpc_live_eligibility": [],
        "review_btpc_strong_uptrend_conflict_disable_rule": [],
        "review_btpc_freshness_or_classifier_stale_signal_rule": [],
        "continue_btpc_l2_shadow_observation_with_proxy_context": [],
    }
    for row in case_rows:
        fixture = str(row.get("fixture_case") or "unknown")
        decision = str(row.get("proxy_replay_quality_review_outcome") or "")
        if decision == "revise_live_fact_collection_but_l2_proxy_reviewable":
            mapping[
                "attach_live_derivatives_fact_sources_before_btpc_live_eligibility"
            ].append(fixture)
        if decision == "revise_conflict_disable_before_l2_promotion":
            mapping["review_btpc_strong_uptrend_conflict_disable_rule"].append(fixture)
        if decision == "revise_freshness_or_classifier_before_l2_promotion":
            mapping["review_btpc_freshness_or_classifier_stale_signal_rule"].append(
                fixture
            )
        if decision == "keep_observing_l2_shadow_with_proxy_context":
            mapping["continue_btpc_l2_shadow_observation_with_proxy_context"].append(
                fixture
            )
    return mapping


def _forbidden_effects(*artifacts: dict[str, Any]) -> list[str]:
    effects = artifact_source_forbidden_effects(
        artifacts,
        true_keys=EXTENDED_SOURCE_SAFETY_TRUE_KEYS,
        include_interaction=True,
    )
    opportunity_artifact = artifacts[0] if artifacts else {}
    if review_outcome_flag(opportunity_artifact, "real_order_scope_change_recommended"):
        effects.append("opportunity_review_outcome.real_order_scope_change_recommended")
    if review_outcome_flag(opportunity_artifact, "l4_promotion_recommended"):
        effects.append("opportunity_review_outcome.l4_promotion_recommended")
    proxy_artifact = artifacts[1] if len(artifacts) > 1 else {}
    if review_outcome_flag(proxy_artifact, "proxy_replay_satisfies_live_required_facts"):
        effects.append("btpc_proxy_replay.proxy_replay_satisfies_live_required_facts")
    btpc_row = artifacts[2] if len(artifacts) > 2 else {}
    if btpc_row.get("candidate_or_finalgate_authority") is True:
        effects.append("btpc_quality_row.candidate_or_finalgate_authority")
    if btpc_row.get("not_l4_scope_change") is False:
        effects.append("btpc_quality_row.not_l4_scope_change_false")
    effects.extend(
        _legacy_authority_mirror_effects(
            opportunity_artifact=opportunity_artifact,
            proxy_artifact=proxy_artifact,
            btpc_quality_row=btpc_row,
        )
    )
    return sorted(set(effects))


def _legacy_authority_mirror_effects(
    *,
    opportunity_artifact: dict[str, Any],
    proxy_artifact: dict[str, Any],
    btpc_quality_row: dict[str, Any],
) -> list[str]:
    effects = legacy_authority_mirror_effects_for_artifacts(
        (
            ("opportunity_review_work_loop", opportunity_artifact),
            ("btpc_proxy_replay_quality", proxy_artifact),
        ),
        section_names=("safety_invariants", "review_outcome_state", "btpc_state"),
        row_names=("action_rows", "case_rows", "source_rows"),
        row_id_keys=("action", "fixture_case", "required_fact", "strategy_group_id"),
    )
    effects.extend(
        legacy_authority_mirror_present_errors(
            btpc_quality_row,
            label_prefix="btpc_quality_row.",
        )
    )
    return effects


def _default_next_step(status: str) -> str:
    if status == "blocked_forbidden_effect":
        return "stop_and_repair_btpc_l2_review_outcome_source_forbidden_effects"
    if status == "btpc_l2_review_waiting_for_proxy_quality_rollup":
        return "rerun_btpc_proxy_replay_quality_and_final_opportunity_review_work_loop"
    if status == "btpc_l2_review_no_action_items":
        return "continue_btpc_l2_shadow_observation_until_action_items_exist"
    return "execute_btpc_l2_fact_source_and_classifier_review_tasks_locally"


def _action_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "| Area | Action | Evidence | Exchange write |\n| --- | --- | --- | --- |\n| none | - | - | - |"
    output = [
        "| Area | Action | Evidence | Exchange write |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        output.append(
            "| `{}` | `{}` | `{}` | `{}` |".format(
                row.get("review_area"),
                row.get("action"),
                ",".join(str(item) for item in row.get("evidence_cases") or []),
                row.get("exchange_write_authority"),
            )
        )
    return "\n".join(output)


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return payload


def _load_optional_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _load_json_object(path)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)]


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--opportunity-review-work-loop-json",
    )
    parser.add_argument(
        "--btpc-proxy-replay-quality-json",
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OWNER_PROGRESS))
    args = parser.parse_args(argv)

    artifact = build_btpc_l2_keep_revise_fact_source_review(
        opportunity_review_work_loop_artifact=_load_optional_json_object(
            Path(args.opportunity_review_work_loop_json).expanduser()
        )
        if args.opportunity_review_work_loop_json
        else {},
        btpc_proxy_replay_quality_artifact=_load_optional_json_object(
            Path(args.btpc_proxy_replay_quality_json).expanduser()
        )
        if args.btpc_proxy_replay_quality_json
        else {},
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
