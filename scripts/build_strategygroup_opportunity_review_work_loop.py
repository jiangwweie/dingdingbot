#!/usr/bin/env python3
"""Build a local StrategyGroup opportunity-to-review work loop artifact.

This command turns already-built local artifacts into repeatable decision rows:

observe-only would-enter opportunity
-> replay verification
-> blocking gaps
-> fact/classifier/tier decision

It is local and non-executing. It never starts runtimes, changes strategy
parameters, changes tier policy, creates candidates, calls FinalGate, calls
Operation Layer, places orders, mutates server files, or writes to an exchange.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from strategygroup_non_executing_projection import (  # noqa: E402
    non_executing_interaction,
    non_executing_safety_boundary,
    review_outcome_default_next_step,
    review_outcome_flag,
    review_outcome_state_boundary,
    source_forbidden_effects,
)

DEFAULT_EXPANSION_REVIEW_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-signal-coverage-expansion-review.json"
)
DEFAULT_L2_READINESS_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-l2-readiness-review.json"
)
DEFAULT_L2_INTAKE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-l2-intake-dry-run.json"
)
DEFAULT_REPLAY_LAB_JSON = REPO_ROOT / "output/runtime-monitor/latest-runtime-replay-lab.json"
DEFAULT_POST_REVISION_REPLAY_REVIEW_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-post-revision-replay-review.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-opportunity-review-work-loop.json"
)
DEFAULT_OWNER_PROGRESS = (
    REPO_ROOT / "output/runtime-monitor/latest-opportunity-review-work-loop.md"
)


def build_opportunity_review_work_loop(
    *,
    expansion_review_artifact: dict[str, Any],
    l2_readiness_artifact: dict[str, Any],
    l2_intake_artifact: dict[str, Any],
    replay_lab_artifact: dict[str, Any],
    post_revision_review_artifact: dict[str, Any] | None = None,
    btpc_proxy_replay_quality_artifact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    post_revision_review_artifact = post_revision_review_artifact or {}
    btpc_proxy_replay_quality_artifact = btpc_proxy_replay_quality_artifact or {}
    readiness_by_group = {
        str(row.get("strategy_group_id") or "unknown"): row
        for row in _dict_rows(l2_readiness_artifact.get("readiness_rows"))
    }
    review_rows = _decision_source_rows(
        _dict_rows(expansion_review_artifact.get("review_rows")),
        readiness_by_group,
    )
    intake_by_group = {
        str(row.get("strategy_group_id") or "unknown"): row
        for row in _dict_rows(l2_intake_artifact.get("source_readiness_rows"))
    }
    replay_by_group = _replay_summary_by_group(replay_lab_artifact)
    opportunity_review_rows = [
        _decision_row(
            review_row=row,
            readiness_row=readiness_by_group.get(
                str(row.get("strategy_group_id") or "unknown"), {}
            ),
            intake_row=intake_by_group.get(
                str(row.get("strategy_group_id") or "unknown"), {}
            ),
            replay_summary=replay_by_group.get(
                str(row.get("strategy_group_id") or "unknown"), {}
            ),
        )
        for row in review_rows
    ]
    work_queue = _work_queue(opportunity_review_rows)
    strategy_asset_recommendations = _strategy_asset_recommendations(
        rows=opportunity_review_rows,
        work_items=_dict_rows(work_queue.get("items")),
        btpc_proxy_replay_quality_artifact=btpc_proxy_replay_quality_artifact,
    )
    forbidden_effects = _forbidden_effects(
        expansion_review_artifact,
        l2_readiness_artifact,
        l2_intake_artifact,
        replay_lab_artifact,
        post_revision_review_artifact,
        btpc_proxy_replay_quality_artifact,
    )
    status = (
        "blocked_forbidden_effect"
        if forbidden_effects
        else "review_work_loop_ready"
        if opportunity_review_rows
        else "no_observed_opportunities"
    )
    review_work_action_counts = Counter(
        row["review_work_action"] for row in opportunity_review_rows
    )
    return {
        "schema": "brc.strategygroup_opportunity_review_work_loop.v1",
        "scope": "strategygroup_opportunity_review_work_loop",
        "status": status,
        "source_status": {
            "expansion_review": expansion_review_artifact.get("status"),
            "l2_readiness": l2_readiness_artifact.get("status"),
            "l2_intake": l2_intake_artifact.get("status"),
            "replay_lab": replay_lab_artifact.get("status"),
            "post_revision_replay_review": post_revision_review_artifact.get("status"),
            "btpc_proxy_replay_quality_review": (
                btpc_proxy_replay_quality_artifact.get("status")
            ),
        },
        "interaction": non_executing_interaction(
            "L0_local_opportunity_review_work_loop"
        ),
        "counts": {
            "observed_opportunity_count": len(opportunity_review_rows),
            "replay_covered_count": sum(
                1 for row in opportunity_review_rows if row["replay_verification"]["covered"]
            ),
            "blocking_gap_group_count": sum(
                1 for row in opportunity_review_rows if row["blocking_gaps_before_l2"]
            ),
            "work_queue_item_count": work_queue["counts"]["total"],
            "scheduled_work_queue_item_count": work_queue["counts"]["scheduled"],
            "coverage_ready_item_count": work_queue["counts"]["coverage_ready"],
            "coverage_pending_item_count": work_queue["counts"]["coverage_pending"],
            "strategy_asset_recommendation_pending_count": work_queue["counts"][
                "strategy_asset_recommendation_pending"
            ],
            "strategy_asset_recommendation_count": strategy_asset_recommendations["counts"][
                "total"
            ],
            "revise_before_l2_count": strategy_asset_recommendations["counts"][
                "revise_before_l2"
            ],
            "l2_enabled_count": sum(
                1
                for row in opportunity_review_rows
                if row["tier_state"] == "l2_shadow_candidate_observation_enabled"
            ),
            "l4_scope_change_recommended_count": 0,
            "forbidden_effect_count": len(forbidden_effects),
            "post_revision_replay_review_passed": (
                1 if _post_revision_review_passed(post_revision_review_artifact) else 0
            ),
            "btpc_proxy_replay_quality_ready": (
                1
                if _btpc_proxy_replay_quality_ready(
                    btpc_proxy_replay_quality_artifact
                )
                else 0
            ),
            "btpc_proxy_replay_quality_case_count": _int(
                _as_dict(btpc_proxy_replay_quality_artifact.get("counts")).get(
                    "replay_case_count"
                )
            ),
            "btpc_proxy_replay_quality_revise_case_count": (
                _btpc_proxy_replay_quality_revise_case_count(
                    btpc_proxy_replay_quality_artifact
                )
            ),
        },
        "review_work_action_counts": dict(sorted(review_work_action_counts.items())),
        "opportunity_review_rows": opportunity_review_rows,
        "work_queue": work_queue,
        "strategy_asset_recommendations": strategy_asset_recommendations,
        "review_outcome_state": review_outcome_state_boundary(
            source_role="signal_observation_work_queue_provenance",
            review_scope="signal_observation_work_queue",
            extra={
                "repeatable_loop_ready": (
                    bool(opportunity_review_rows) and not forbidden_effects
                ),
                "real_order_scope_change_recommended": False,
                "l4_promotion_recommended": False,
                "tier_policy_change_recommended_now": False,
                "post_revision_replay_review_passed": _post_revision_review_passed(
                    post_revision_review_artifact
                ),
                "btpc_proxy_replay_quality_ready": _btpc_proxy_replay_quality_ready(
                    btpc_proxy_replay_quality_artifact
                ),
                "default_next_step": _default_next_step(
                    opportunity_review_rows,
                    forbidden_effects,
                    work_queue,
                    strategy_asset_recommendations,
                    post_revision_review_artifact,
                ),
            },
        ),
        "safety_invariants": non_executing_safety_boundary(
            true_keys=(
                "local_opportunity_review_loop_only",
                "input_is_not_execution_authority",
            ),
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
    lines = [
        "# StrategyGroup Opportunity Review Work Loop",
        "",
        "## Summary",
        "",
        f"- Status: `{artifact.get('status')}`",
        f"- Observed opportunities: `{_as_dict(artifact.get('counts')).get('observed_opportunity_count', 0)}`",
        f"- Replay covered: `{_as_dict(artifact.get('counts')).get('replay_covered_count', 0)}`",
        "- L4 scope change: `false`",
        "",
        "## Opportunity Review Rows",
        "",
        _review_work_table(_dict_rows(artifact.get("opportunity_review_rows"))),
        "",
        "## Next",
        "",
        f"- `{review_outcome_default_next_step(artifact)}`",
        "",
        "## Work Queue",
        "",
        _work_queue_table(_dict_rows(_as_dict(artifact.get("work_queue")).get("items"))),
        "",
        "## Strategy Asset Recommendations",
        "",
        _strategy_quality_table(
            _dict_rows(_as_dict(artifact.get("strategy_asset_recommendations")).get("rows"))
        ),
    ]
    return "\n".join(lines).rstrip() + "\n"


def _decision_row(
    *,
    review_row: dict[str, Any],
    readiness_row: dict[str, Any],
    intake_row: dict[str, Any],
    replay_summary: dict[str, Any],
) -> dict[str, Any]:
    strategy_group_id = str(review_row.get("strategy_group_id") or "unknown")
    readiness = str(readiness_row.get("l2_readiness") or "missing_l2_readiness")
    current_tier = str(
        review_row.get("current_tier")
        or readiness_row.get("current_tier")
        or intake_row.get("current_tier")
        or "unknown"
    )
    gaps = [
        str(item)
        for item in (
            readiness_row.get("blocking_gaps_before_l2")
            or intake_row.get("blocking_gaps_before_l2")
            or []
        )
    ]
    classifier_repair_spec = _as_dict(readiness_row.get("classifier_repair_spec"))
    economic_replay_spec = _as_dict(readiness_row.get("economic_replay_spec"))
    replay = _normalized_replay_summary(replay_summary)
    review_work_action = _review_work_action(
        current_tier=current_tier,
        readiness=readiness,
        replay=replay,
        gaps=gaps,
    )
    gap_work = [
        _gap_work_item(
            gap,
            strategy_group_id=strategy_group_id,
            current_tier=current_tier,
            readiness=readiness,
            review_work_action=review_work_action,
            classifier_repair_spec=classifier_repair_spec,
            economic_replay_spec=economic_replay_spec,
            replay=replay,
        )
        for gap in gaps
    ]
    observed_source = str(
        review_row.get("source") or "signal_coverage_expansion_review"
    )
    observed_would_enter = (
        review_row.get("would_enter")
        if isinstance(review_row.get("would_enter"), bool)
        else True
    )
    return {
        "strategy_group_id": strategy_group_id,
        "symbol": review_row.get("symbol") or readiness_row.get("symbol"),
        "side": review_row.get("side") or readiness_row.get("side"),
        "observed_signal": {
            "source": observed_source,
            "would_enter": observed_would_enter,
            "confidence": review_row.get("confidence"),
            "reason_codes": [str(item) for item in review_row.get("reason_codes") or []],
            "execution_boundary": review_row.get("execution_boundary"),
        },
        "current_tier": current_tier,
        "tier_state": readiness,
        "replay_verification": replay,
        "positive_evidence": [
            str(item) for item in readiness_row.get("positive_evidence") or []
        ],
        "classifier_repair_spec": classifier_repair_spec,
        "economic_replay_spec": economic_replay_spec,
        "blocking_gaps_before_l2": gaps,
        "gap_work_items": gap_work,
        "review_work_action": review_work_action,
        "next_checkpoint": _next_checkpoint(review_work_action),
        "l4_scope_change_recommended": False,
        "candidate_or_finalgate_authority": False,
    }


def _decision_source_rows(
    review_rows: list[dict[str, Any]],
    readiness_by_group: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = list(review_rows)
    existing_groups = {
        str(row.get("strategy_group_id") or "unknown") for row in review_rows
    }
    for group, readiness in sorted(readiness_by_group.items()):
        if group in existing_groups:
            continue
        if readiness.get("l2_readiness") != "l2_shadow_candidate_observation_enabled":
            continue
        rows.append(
            {
                "strategy_group_id": group,
                "symbol": readiness.get("symbol"),
                "side": readiness.get("side"),
                "current_tier": readiness.get("current_tier"),
                "source": "l2_readiness_enabled_shadow_continuity",
                "would_enter": False,
                "confidence": None,
                "reason_codes": ["l2_shadow_candidate_observation_enabled"],
                "execution_boundary": "local L2 shadow quality review only; no FinalGate/Operation Layer",
            }
        )
    return rows


def _replay_summary_by_group(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for key in (
        "replay_samples",
        "l2_shadow_replay_samples",
        "l1_observe_replay_samples",
    ):
        samples.extend(_dict_rows(artifact.get(key)))
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in samples:
        grouped[str(sample.get("strategy_group_id") or "unknown")].append(sample)
    return {group: _summarize_replay_samples(rows) for group, rows in grouped.items()}


def _summarize_replay_samples(rows: list[dict[str, Any]]) -> dict[str, Any]:
    would_enter = [
        row
        for row in rows
        if "would_enter" in str(row.get("signal_status") or "")
        and row.get("blocker_class") != "waiting_for_market"
    ]
    no_action = [
        row
        for row in rows
        if row.get("blocker_class") == "waiting_for_market"
        or str(row.get("signal_status") or "").startswith("no_signal")
    ]
    revise = [
        row
        for row in rows
        if str(row.get("review_recommendation") or "") == "revise"
        or "revision" in str(row.get("signal_status") or "")
        or "rewrite" in str(row.get("signal_status") or "")
    ]
    boundary_ok = all(
        row.get("real_order_allowed") is not True
        and row.get("exchange_write_allowed") is not True
        and row.get("operation_layer_submit_allowed") is not True
        for row in rows
    )
    return {
        "covered": bool(rows),
        "sample_count": len(rows),
        "would_enter_sample_count": len(would_enter),
        "no_action_sample_count": len(no_action),
        "revise_sample_count": len(revise),
        "review_shape_present": bool(would_enter),
        "non_executing_boundary_ok": boundary_ok,
        "cost_review_fields_by_case": _cost_review_fields_by_case(rows),
        "fixture_cases": sorted(
            str(row.get("fixture_case"))
            for row in rows
            if str(row.get("fixture_case") or "").strip()
        ),
    }


def _normalized_replay_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "covered": bool(summary.get("covered")),
        "sample_count": _int(summary.get("sample_count")),
        "would_enter_sample_count": _int(summary.get("would_enter_sample_count")),
        "no_action_sample_count": _int(summary.get("no_action_sample_count")),
        "revise_sample_count": _int(summary.get("revise_sample_count")),
        "review_shape_present": bool(summary.get("review_shape_present")),
        "non_executing_boundary_ok": bool(summary.get("non_executing_boundary_ok")),
        "cost_review_fields_by_case": {
            str(key): [str(item) for item in value or []]
            for key, value in _as_dict(summary.get("cost_review_fields_by_case")).items()
        },
        "fixture_cases": [str(item) for item in summary.get("fixture_cases") or []],
    }


def _review_work_action(
    *,
    current_tier: str,
    readiness: str,
    replay: dict[str, Any],
    gaps: list[str],
) -> str:
    if readiness == "l2_shadow_candidate_observation_enabled":
        return "continue_l2_shadow_quality_review"
    if readiness == "blocked_parked_negative_evidence":
        return "park_or_vocabulary_only"
    if not replay["covered"]:
        return "build_replay_corpus_before_l2"
    if not replay["review_shape_present"]:
        return "add_would_enter_replay_case_before_l2"
    if gaps:
        return "repair_blocking_gaps_with_replay_or_facts"
    if current_tier == "L1":
        return "prepare_l2_intake_review_without_tier_change"
    return "continue_observation_review"


def _next_checkpoint(action: str) -> str:
    return {
        "continue_l2_shadow_quality_review": (
            "collect_l2_shadow_outcomes_and_cost_slippage_quality"
        ),
        "park_or_vocabulary_only": "keep_as_low_priority_vocabulary_until_new_edge",
        "build_replay_corpus_before_l2": "add_group_replay_corpus_and_would_enter_case",
        "add_would_enter_replay_case_before_l2": "add_would_enter_replay_case",
        "repair_blocking_gaps_with_replay_or_facts": (
            "map_blocking_gaps_to_required_facts_or_classifier_tasks"
        ),
        "prepare_l2_intake_review_without_tier_change": (
            "run_l2_handoff_intake_dry_run_without_l4_scope_change"
        ),
    }.get(action, "continue_observation_review")


def _gap_work_item(
    gap: str,
    *,
    strategy_group_id: str,
    current_tier: str,
    readiness: str,
    review_work_action: str,
    classifier_repair_spec: dict[str, Any],
    economic_replay_spec: dict[str, Any],
    replay: dict[str, Any],
) -> dict[str, Any]:
    lowered = gap.lower()
    if any(token in lowered for token in ("classifier", "rewrite", "disable")):
        work_type = "classifier_or_rule_work"
    elif any(
        token in lowered
        for token in ("open_interest", "ratio", "margin", "liquidation", "facts")
    ):
        work_type = "required_fact_or_market_data_work"
    elif any(token in lowered for token in ("cost", "slippage", "leverage", "m2m")):
        work_type = "economic_replay_work"
    elif any(token in lowered for token in ("negative", "failed", "parked")):
        work_type = "strategy_quality_review"
    else:
        work_type = "strategy_review_work"
    owner_priority = _owner_priority(
        review_work_action=review_work_action,
        current_tier=current_tier,
        work_type=work_type,
    )
    matching_repair_spec = _matching_classifier_repair_spec(
        gap=gap,
        work_type=work_type,
        classifier_repair_spec=classifier_repair_spec,
        replay=replay,
    )
    matching_economic_spec = _matching_economic_replay_spec(
        gap=gap,
        work_type=work_type,
        economic_replay_spec=economic_replay_spec,
        replay=replay,
    )
    return {
        "gap": gap,
        "work_type": work_type,
        "owner_priority": owner_priority,
        "scheduled": review_work_action != "park_or_vocabulary_only",
        "blocks_l2_progression": _blocks_l2_progression(
            review_work_action=review_work_action,
            readiness=readiness,
        ),
        "actionable_task": _actionable_gap_task(
            gap=gap,
            work_type=work_type,
            strategy_group_id=strategy_group_id,
            review_work_action=review_work_action,
            classifier_repair_spec=matching_repair_spec,
            economic_replay_spec=matching_economic_spec,
        ),
        "validation_command": _validation_command(work_type),
        "completion_signal": _completion_signal(
            work_type, matching_repair_spec, matching_economic_spec
        ),
        "repair_spec": matching_repair_spec,
        "economic_spec": matching_economic_spec,
        **_coverage_state(
            review_work_action=review_work_action,
            work_type=work_type,
            scheduled=review_work_action != "park_or_vocabulary_only",
            repair_spec=matching_repair_spec,
            economic_spec=matching_economic_spec,
        ),
    }


def _work_queue(rows: list[dict[str, Any]]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for row in rows:
        if row.get("review_work_action") in {
            "build_replay_corpus_before_l2",
            "add_would_enter_replay_case_before_l2",
        }:
            items.append(_row_level_queue_item(row))
            continue
        gap_items = _dict_rows(row.get("gap_work_items"))
        if gap_items:
            for gap_item in gap_items:
                items.append(_queue_item(row, gap_item))
        else:
            items.append(_row_level_queue_item(row))
    items.sort(key=_work_queue_sort_key)
    by_type = Counter(str(item.get("work_type") or "unknown") for item in items)
    by_priority = Counter(str(item.get("owner_priority") or "unknown") for item in items)
    by_coverage_status = Counter(
        str(item.get("coverage_status") or "unknown") for item in items
    )
    scheduled = [item for item in items if item.get("scheduled") is True]
    return {
        "status": "ready" if items else "empty",
        "next_local_checkpoint": _next_local_work_checkpoint(scheduled),
        "counts": {
            "total": len(items),
            "scheduled": len(scheduled),
            "blocked_l2_progression": sum(
                1 for item in items if item.get("blocks_l2_progression") is True
            ),
            "real_order_authorized": 0,
            "l4_scope_change_recommended": 0,
            "coverage_ready": sum(
                1 for item in items if item.get("coverage_ready") is True
            ),
            "coverage_pending": sum(
                1
                for item in items
                if item.get("scheduled") is True
                and item.get("coverage_status")
                in {"needs_replay_or_spec", "fact_source_pending"}
            ),
            "strategy_asset_recommendation_pending": sum(
                1
                for item in items
                if item.get("coverage_status") == "strategy_asset_recommendation_pending"
            ),
            "strategy_review_pending": sum(
                1
                for item in items
                if item.get("coverage_status") == "strategy_review_pending"
            ),
        },
        "by_work_type": dict(sorted(by_type.items())),
        "by_owner_priority": dict(sorted(by_priority.items())),
        "by_coverage_status": dict(sorted(by_coverage_status.items())),
        "items": items,
        "safety_invariants": non_executing_safety_boundary(
            true_keys=("local_work_queue_only",),
            false_keys=(
                "changes_strategy_parameters",
                "changes_tier_policy",
                "creates_shadow_candidate",
                "calls_finalgate",
                "calls_operation_layer",
                "calls_exchange_write",
                "places_order",
                "mutates_server_files",
                "real_order_authorized",
            ),
            include_source_forbidden_effects=False,
        ),
    }


def _strategy_asset_recommendations(
    *,
    rows: list[dict[str, Any]],
    work_items: list[dict[str, Any]],
    btpc_proxy_replay_quality_artifact: dict[str, Any],
) -> dict[str, Any]:
    output_rows = [
        _strategy_asset_recommendation_row(
            row=row,
            work_items=[
                item
                for item in work_items
                if item.get("strategy_group_id") == row.get("strategy_group_id")
            ],
            btpc_proxy_replay_quality_artifact=btpc_proxy_replay_quality_artifact,
        )
        for row in rows
    ]
    strategy_asset_recommendation_counts = Counter(
        str(row.get("strategy_asset_recommendation") or "unknown")
        for row in output_rows
    )
    revision_task_count = sum(
        len(row.get("revision_tasks") or []) for row in output_rows
    )
    revision_ready_count = sum(
        1
        for row in output_rows
        for task in row.get("revision_tasks") or []
        if task.get("revision_ready") is True
    )
    classifier_revision_task_count = sum(
        1
        for row in output_rows
        for task in row.get("revision_tasks") or []
        if task.get("work_type") == "classifier_or_rule_work"
    )
    economic_revision_task_count = sum(
        1
        for row in output_rows
        for task in row.get("revision_tasks") or []
        if task.get("work_type") == "economic_replay_work"
    )
    classifier_revision_ready_count = sum(
        1
        for row in output_rows
        for task in row.get("revision_tasks") or []
        if task.get("work_type") == "classifier_or_rule_work"
        and task.get("revision_ready") is True
    )
    economic_revision_ready_count = sum(
        1
        for row in output_rows
        for task in row.get("revision_tasks") or []
        if task.get("work_type") == "economic_replay_work"
        and task.get("revision_ready") is True
    )
    remaining_revision_blocker_count = revision_task_count - revision_ready_count
    revision_executed_count = sum(
        1
        for row in output_rows
        for task in row.get("revision_tasks") or []
        if task.get("revision_executed") is True
    )
    classifier_revision_executed_count = sum(
        1
        for row in output_rows
        for task in row.get("revision_tasks") or []
        if task.get("work_type") == "classifier_or_rule_work"
        and task.get("revision_executed") is True
    )
    economic_revision_executed_count = sum(
        1
        for row in output_rows
        for task in row.get("revision_tasks") or []
        if task.get("work_type") == "economic_replay_work"
        and task.get("revision_executed") is True
    )
    remaining_revision_execution_count = revision_task_count - revision_executed_count
    revision_status_counts = Counter(
        str(task.get("revision_status") or "unknown")
        for row in output_rows
        for task in row.get("revision_tasks") or []
    )
    revision_execution_status_counts = Counter(
        str(task.get("revision_execution_status") or "unknown")
        for row in output_rows
        for task in row.get("revision_tasks") or []
    )
    btpc_proxy_ready_count = sum(
        1
        for row in output_rows
        if _as_dict(row.get("btpc_proxy_replay_quality")).get("ready") is True
    )
    btpc_proxy_case_count = sum(
        _int(_as_dict(row.get("btpc_proxy_replay_quality")).get("case_count"))
        for row in output_rows
    )
    btpc_proxy_revise_case_count = sum(
        _int(_as_dict(row.get("btpc_proxy_replay_quality")).get("revise_case_count"))
        for row in output_rows
    )
    return {
        "status": "ready" if output_rows else "empty",
        "next_checkpoint": _strategy_quality_next_checkpoint(output_rows),
        "counts": {
            "total": len(output_rows),
            "revise_before_l2": strategy_asset_recommendation_counts.get(
                "revise_before_l2", 0
            ),
            "keep_observing": sum(
                count
                for decision, count in strategy_asset_recommendation_counts.items()
                if str(decision).startswith("keep_observing")
            ),
            "park": strategy_asset_recommendation_counts.get("park_until_new_edge", 0),
            "needs_replay": strategy_asset_recommendation_counts.get(
                "needs_replay_before_asset_recommendation", 0
            ),
            "revision_task": revision_task_count,
            "revision_ready": revision_ready_count,
            "classifier_revision_task": classifier_revision_task_count,
            "classifier_revision_ready": classifier_revision_ready_count,
            "economic_revision_task": economic_revision_task_count,
            "economic_revision_ready": economic_revision_ready_count,
            "remaining_revision_blocker": remaining_revision_blocker_count,
            "revision_executed": revision_executed_count,
            "classifier_revision_executed": classifier_revision_executed_count,
            "economic_revision_executed": economic_revision_executed_count,
            "remaining_revision_execution": remaining_revision_execution_count,
            "btpc_proxy_replay_quality_ready": btpc_proxy_ready_count,
            "btpc_proxy_replay_quality_case": btpc_proxy_case_count,
            "btpc_proxy_replay_quality_revise_case": btpc_proxy_revise_case_count,
            "real_order_authorized": 0,
            "l4_scope_change_recommended": 0,
        },
        "by_strategy_asset_recommendation": dict(
            sorted(strategy_asset_recommendation_counts.items())
        ),
        "by_revision_status": dict(sorted(revision_status_counts.items())),
        "by_revision_execution_status": dict(
            sorted(revision_execution_status_counts.items())
        ),
        "revision_completion": {
            "status": _revision_completion_status(
                revision_task_count=revision_task_count,
                revision_ready_count=revision_ready_count,
            ),
            "revision_task_count": revision_task_count,
            "revision_ready_count": revision_ready_count,
            "classifier_revision_ready_count": classifier_revision_ready_count,
            "economic_revision_ready_count": economic_revision_ready_count,
            "remaining_revision_blocker_count": remaining_revision_blocker_count,
            "not_l2_promotion_authority": True,
            "not_l4_scope_change": True,
            "candidate_or_finalgate_authority": False,
        },
        "revision_execution": {
            "status": _revision_execution_status(
                revision_task_count=revision_task_count,
                revision_executed_count=revision_executed_count,
            ),
            "revision_task_count": revision_task_count,
            "revision_executed_count": revision_executed_count,
            "classifier_revision_executed_count": classifier_revision_executed_count,
            "economic_revision_executed_count": economic_revision_executed_count,
            "remaining_revision_execution_count": remaining_revision_execution_count,
            "not_l2_promotion_authority": True,
            "not_l4_scope_change": True,
            "candidate_or_finalgate_authority": False,
        },
        "rows": output_rows,
        "safety_invariants": non_executing_safety_boundary(
            true_keys=("local_strategy_asset_recommendation_only",),
            false_keys=(
                "changes_strategy_parameters",
                "changes_tier_policy",
                "creates_shadow_candidate",
                "calls_finalgate",
                "calls_operation_layer",
                "calls_exchange_write",
                "places_order",
                "mutates_server_files",
                "real_order_authorized",
                "l4_scope_change_recommended",
            ),
            include_source_forbidden_effects=False,
        ),
    }


def _strategy_asset_recommendation_row(
    *,
    row: dict[str, Any],
    work_items: list[dict[str, Any]],
    btpc_proxy_replay_quality_artifact: dict[str, Any],
) -> dict[str, Any]:
    strategy_group_id = str(row.get("strategy_group_id") or "unknown")
    replay = _as_dict(row.get("replay_verification"))
    btpc_proxy_quality = _btpc_proxy_replay_quality_rollup(
        strategy_group_id=strategy_group_id,
        artifact=btpc_proxy_replay_quality_artifact,
    )
    coverage_ready_count = sum(
        1 for item in work_items if item.get("coverage_ready") is True
    )
    fact_pending_count = sum(
        1
        for item in work_items
        if item.get("coverage_status") == "fact_source_pending"
    )
    strategy_asset_recommendation_pending_count = sum(
        1
        for item in work_items
        if item.get("coverage_status") == "strategy_asset_recommendation_pending"
    )
    parked_count = sum(
        1 for item in work_items if item.get("coverage_status") == "parked"
    )
    revise_sample_count = _int(replay.get("revise_sample_count"))
    if row.get("review_work_action") == "park_or_vocabulary_only":
        decision = "park_until_new_edge"
        reason = "parked_negative_or_low_quality_evidence"
    elif replay.get("covered") is not True:
        decision = "needs_replay_before_asset_recommendation"
        reason = "missing_local_replay_coverage"
    elif coverage_ready_count and (
        revise_sample_count > 0 or strategy_asset_recommendation_pending_count > 0
    ):
        decision = "revise_before_l2"
        reason = "coverage_ready_but_revise_or_negative_evidence_present"
    elif row.get("tier_state") == "l2_shadow_candidate_observation_enabled":
        if btpc_proxy_quality.get("ready") is True:
            decision = "keep_l2_shadow_and_revise_fact_classifier_inputs"
            reason = "btpc_proxy_replay_quality_ready_with_review_only_revisions"
        else:
            decision = (
                "keep_observing_l2_shadow_with_fact_review"
                if fact_pending_count
                else "keep_observing_l2_shadow"
            )
            reason = "l2_shadow_observation_active_without_real_order_scope_change"
    elif row.get("review_work_action") == "prepare_l2_intake_review_without_tier_change":
        decision = "prepare_l2_intake_review_without_promotion"
        reason = "review_shape_ready_but_tier_change_not_authorized_here"
    else:
        decision = "continue_observe_only_review"
        reason = "insufficient_quality_decision_evidence"
    revision_tasks = _revision_tasks_for_quality_decision(
        decision=decision,
        work_items=work_items,
    )
    revision_ready_count = sum(
        1 for task in revision_tasks if task.get("revision_ready") is True
    )
    revision_blockers = sorted(
        {
            str(task.get("completion_blocker"))
            for task in revision_tasks
            if task.get("completion_blocker")
        }
    )
    revision_executed_count = sum(
        1 for task in revision_tasks if task.get("revision_executed") is True
    )
    revision_execution_blockers = sorted(
        {
            str(task.get("execution_blocker"))
            for task in revision_tasks
            if task.get("execution_blocker")
        }
    )
    return {
        "strategy_group_id": strategy_group_id,
        "current_tier": row.get("current_tier"),
        "tier_state": row.get("tier_state"),
        "strategy_asset_recommendation": decision,
        "reason": reason,
        "next_stage": _next_stage_for_strategy_asset_recommendation(decision),
        "evidence": {
            "replay_sample_count": _int(replay.get("sample_count")),
            "would_enter_sample_count": _int(replay.get("would_enter_sample_count")),
            "revise_sample_count": revise_sample_count,
            "coverage_ready_item_count": coverage_ready_count,
            "fact_source_pending_item_count": fact_pending_count,
            "strategy_asset_recommendation_pending_item_count": strategy_asset_recommendation_pending_count,
            "parked_item_count": parked_count,
            "blocking_gap_count": len(row.get("blocking_gaps_before_l2") or []),
            "btpc_proxy_replay_quality_ready": btpc_proxy_quality.get("ready") is True,
            "btpc_proxy_replay_quality_case_count": _int(
                btpc_proxy_quality.get("case_count")
            ),
            "btpc_proxy_replay_quality_revise_case_count": _int(
                btpc_proxy_quality.get("revise_case_count")
            ),
            "btpc_proxy_reviewable_would_enter_count": _int(
                btpc_proxy_quality.get("proxy_reviewable_would_enter_count")
            ),
        },
        "btpc_proxy_replay_quality": btpc_proxy_quality,
        "revision_tasks": revision_tasks,
        "revision_task_count": len(revision_tasks),
        "revision_ready_count": revision_ready_count,
        "revision_completion": {
            "status": _revision_completion_status(
                revision_task_count=len(revision_tasks),
                revision_ready_count=revision_ready_count,
            ),
            "ready_count": revision_ready_count,
            "remaining_blocker_count": len(revision_tasks) - revision_ready_count,
            "completion_blockers": revision_blockers,
        },
        "revision_execution": {
            "status": _revision_execution_status(
                revision_task_count=len(revision_tasks),
                revision_executed_count=revision_executed_count,
            ),
            "executed_count": revision_executed_count,
            "remaining_execution_count": len(revision_tasks)
            - revision_executed_count,
            "execution_blockers": revision_execution_blockers,
        },
        "not_l2_promotion_authority": True,
        "not_l4_scope_change": True,
        "candidate_or_finalgate_authority": False,
    }


def _revision_tasks_for_quality_decision(
    *,
    decision: str,
    work_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if decision != "revise_before_l2":
        return []
    tasks: list[dict[str, Any]] = []
    for item in work_items:
        if item.get("coverage_ready") is not True:
            continue
        work_type = str(item.get("work_type") or "")
        if work_type not in {"classifier_or_rule_work", "economic_replay_work"}:
            continue
        revision_state = _revision_task_state(item=item, work_type=work_type)
        tasks.append(
            {
                "queue_id": item.get("queue_id"),
                "work_type": work_type,
                "gap": item.get("gap"),
                "actionable_task": item.get("actionable_task"),
                "validation_command": item.get("validation_command"),
                "completion_signal": item.get("completion_signal"),
                "revision_stage": _revision_stage_for_work_type(work_type),
                "coverage_status": item.get("coverage_status"),
                **revision_state,
                "not_l2_promotion_authority": True,
                "not_l4_scope_change": True,
                "candidate_or_finalgate_authority": False,
            }
        )
    return tasks


def _revision_task_state(*, item: dict[str, Any], work_type: str) -> dict[str, Any]:
    if work_type == "classifier_or_rule_work":
        return _classifier_revision_task_state(_as_dict(item.get("repair_spec")))
    if work_type == "economic_replay_work":
        return _economic_revision_task_state(_as_dict(item.get("economic_spec")))
    return {
        "revision_status": "revision_spec_not_applicable",
        "revision_ready": False,
        "acceptance_case_coverage_ready": False,
        "required_entry_state_count": 0,
        "required_disable_state_count": 0,
        "required_cost_field_count": 0,
        "completion_blocker": "unsupported_revision_work_type",
    }


def _classifier_revision_task_state(repair_spec: dict[str, Any]) -> dict[str, Any]:
    coverage = _as_dict(repair_spec.get("replay_case_coverage"))
    execution = _as_dict(repair_spec.get("revision_execution"))
    entry_states = [str(item) for item in repair_spec.get("required_entry_states") or []]
    disable_states = [
        str(item) for item in repair_spec.get("required_disable_states") or []
    ]
    no_authority_boundary = (
        repair_spec.get("not_execution_authority") is True
        and repair_spec.get("not_l2_promotion_authority") is True
        and repair_spec.get("not_l4_scope_change") is True
    )
    blocker = None
    if not repair_spec:
        blocker = "repair_spec_missing"
    elif repair_spec.get("status") != "local_repair_spec_ready":
        blocker = "repair_spec_not_ready"
    elif coverage.get("covered") is not True:
        blocker = "acceptance_case_coverage_missing"
    elif not entry_states:
        blocker = "required_entry_states_missing"
    elif not disable_states:
        blocker = "required_disable_states_missing"
    elif not no_authority_boundary:
        blocker = "authority_boundary_missing"
    execution_blocker = _revision_execution_blocker(
        execution=execution,
        expected_status="local_classifier_revision_executed",
        required_items=("executed_entry_states", "executed_disable_states"),
    )
    return {
        "revision_status": (
            "local_revision_spec_ready"
            if blocker is None
            else "revision_spec_incomplete"
        ),
        "revision_ready": blocker is None,
        "acceptance_case_coverage_ready": coverage.get("covered") is True,
        "required_entry_state_count": len(entry_states),
        "required_disable_state_count": len(disable_states),
        "required_cost_field_count": 0,
        "completion_blocker": blocker,
        "revision_execution_status": str(execution.get("status") or "not_executed"),
        "revision_executed": execution_blocker is None,
        "execution_blocker": execution_blocker,
    }


def _economic_revision_task_state(economic_spec: dict[str, Any]) -> dict[str, Any]:
    coverage = _as_dict(economic_spec.get("economic_case_coverage"))
    execution = _as_dict(economic_spec.get("replay_execution"))
    cost_fields = [str(item) for item in economic_spec.get("required_cost_fields") or []]
    no_authority_boundary = (
        economic_spec.get("not_execution_authority") is True
        and economic_spec.get("not_l2_promotion_authority") is True
        and economic_spec.get("not_l4_scope_change") is True
    )
    blocker = None
    if not economic_spec:
        blocker = "economic_spec_missing"
    elif economic_spec.get("status") != "local_economic_replay_spec_ready":
        blocker = "economic_spec_not_ready"
    elif coverage.get("covered") is not True:
        blocker = "economic_case_coverage_missing"
    elif not cost_fields:
        blocker = "required_cost_fields_missing"
    elif not no_authority_boundary:
        blocker = "authority_boundary_missing"
    execution_blocker = _revision_execution_blocker(
        execution=execution,
        expected_status="local_economic_replay_executed",
        required_items=("covered_cost_fields",),
    )
    return {
        "revision_status": (
            "local_economic_review_ready"
            if blocker is None
            else "economic_review_incomplete"
        ),
        "revision_ready": blocker is None,
        "acceptance_case_coverage_ready": coverage.get("covered") is True,
        "required_entry_state_count": 0,
        "required_disable_state_count": 0,
        "required_cost_field_count": len(cost_fields),
        "completion_blocker": blocker,
        "revision_execution_status": str(execution.get("status") or "not_executed"),
        "revision_executed": execution_blocker is None,
        "execution_blocker": execution_blocker,
    }


def _revision_execution_blocker(
    *,
    execution: dict[str, Any],
    expected_status: str,
    required_items: tuple[str, ...],
) -> str | None:
    no_authority_boundary = (
        execution.get("not_execution_authority") is True
        and execution.get("not_l2_promotion_authority") is True
        and execution.get("not_l4_scope_change") is True
    )
    if not execution:
        return "revision_execution_missing"
    if execution.get("status") != expected_status:
        return "revision_execution_status_not_ready"
    for key in required_items:
        if not execution.get(key):
            return f"{key}_missing"
    if not execution.get("validation_cases"):
        return "revision_execution_validation_cases_missing"
    if not no_authority_boundary:
        return "revision_execution_authority_boundary_missing"
    return None


def _revision_completion_status(
    *, revision_task_count: int, revision_ready_count: int
) -> str:
    if revision_task_count <= 0:
        return "no_revision_required"
    if revision_task_count == revision_ready_count:
        return "local_revision_completion_ready"
    if revision_ready_count:
        return "partial_revision_completion_ready"
    return "revision_completion_blocked"


def _revision_execution_status(
    *, revision_task_count: int, revision_executed_count: int
) -> str:
    if revision_task_count <= 0:
        return "no_revision_execution_required"
    if revision_task_count == revision_executed_count:
        return "local_revision_execution_complete"
    if revision_executed_count:
        return "partial_revision_execution_complete"
    return "revision_execution_pending"


def _revision_stage_for_work_type(work_type: str) -> str:
    return {
        "classifier_or_rule_work": "classifier_disable_state_revision",
        "economic_replay_work": "economic_survival_review",
    }.get(work_type, "strategy_quality_revision")


def _next_stage_for_strategy_asset_recommendation(decision: str) -> str:
    return {
        "revise_before_l2": "record_revise_decision_and_keep_l1_until_review_passes",
        "keep_l2_shadow_and_revise_fact_classifier_inputs": (
            "feed_btpc_proxy_replay_quality_into_l2_keep_revise_or_fact_source_review"
        ),
        "keep_observing_l2_shadow_with_fact_review": (
            "continue_l2_shadow_and_attach_fact_sources"
        ),
        "keep_observing_l2_shadow": "continue_l2_shadow_quality_review",
        "park_until_new_edge": "park_until_new_evidence",
        "needs_replay_before_asset_recommendation": "add_replay_or_spec_coverage_before_l2",
        "prepare_l2_intake_review_without_promotion": (
            "run_l2_handoff_intake_dry_run_without_l4_scope_change"
        ),
        "continue_observe_only_review": "continue_observe_only_review",
    }.get(decision, "continue_local_review")


def _strategy_quality_next_checkpoint(rows: list[dict[str, Any]]) -> str:
    revise_groups = [
        str(row.get("strategy_group_id"))
        for row in rows
        if row.get("strategy_asset_recommendation") == "revise_before_l2"
    ]
    if revise_groups:
        executed_groups = [
            str(row.get("strategy_group_id"))
            for row in rows
            if row.get("strategy_asset_recommendation") == "revise_before_l2"
            and _as_dict(row.get("revision_execution")).get("status")
            == "local_revision_execution_complete"
        ]
        if executed_groups and set(executed_groups) == set(revise_groups):
            return "run_{}_post_revision_replay_review_before_l2".format(
                "_".join(sorted(executed_groups)).lower().replace("-", "")
            )
        ready_groups = [
            str(row.get("strategy_group_id"))
            for row in rows
            if row.get("strategy_asset_recommendation") == "revise_before_l2"
            and _as_dict(row.get("revision_completion")).get("status")
            == "local_revision_completion_ready"
        ]
        if ready_groups and set(ready_groups) == set(revise_groups):
            return "execute_{}_local_revision_tasks_before_l2".format(
                "_".join(sorted(ready_groups)).lower().replace("-", "")
            )
        return "record_{}_strategy_quality_revise_before_l2".format(
            "_".join(sorted(revise_groups)).lower().replace("-", "")
        )
    if any(
        row.get("strategy_asset_recommendation")
        == "keep_l2_shadow_and_revise_fact_classifier_inputs"
        for row in rows
    ):
        return "feed_btpc_proxy_replay_quality_into_l2_keep_revise_or_fact_source_review"
    if any(
        row.get("strategy_asset_recommendation")
        == "keep_observing_l2_shadow_with_fact_review"
        for row in rows
    ):
        return "continue_btpc_l2_shadow_fact_quality_review"
    if any(
        row.get("strategy_asset_recommendation") == "needs_replay_before_asset_recommendation"
        for row in rows
    ):
        return "add_missing_replay_before_strategy_asset_recommendation"
    return "continue_l2_shadow_and_observe_only_review"


def _btpc_proxy_replay_quality_ready(artifact: dict[str, Any]) -> bool:
    return (
        _source_status(artifact) == "btpc_proxy_replay_quality_review_ready"
        and review_outcome_flag(artifact, "proxy_replay_quality_review_ready")
        and review_outcome_flag(artifact, "proxy_replay_satisfies_live_required_facts")
        is False
    )


def _btpc_proxy_replay_quality_revise_case_count(artifact: dict[str, Any]) -> int:
    return sum(
        1
        for row in _dict_rows(artifact.get("case_rows"))
        if str(row.get("proxy_replay_quality_review_outcome") or "").startswith("revise_")
    )


def _btpc_proxy_replay_quality_rollup(
    *,
    strategy_group_id: str,
    artifact: dict[str, Any],
) -> dict[str, Any]:
    if strategy_group_id != "BTPC-001" or not artifact:
        return {}
    counts = _as_dict(artifact.get("counts"))
    ready = _btpc_proxy_replay_quality_ready(artifact)
    case_rows = _dict_rows(artifact.get("case_rows"))
    proxy_replay_quality_review_outcome_counts = Counter(
        str(row.get("proxy_replay_quality_review_outcome") or "unknown")
        for row in case_rows
    )
    action_items = _btpc_proxy_quality_action_items(case_rows)
    return {
        "ready": ready,
        "status": artifact.get("status"),
        "case_count": _int(counts.get("replay_case_count")) or len(case_rows),
        "would_enter_case_count": _int(counts.get("would_enter_case_count")),
        "proxy_reviewable_would_enter_count": _int(
            counts.get("proxy_reviewable_would_enter_count")
        ),
        "missing_derivatives_proxy_reviewable_count": _int(
            counts.get("proxy_resolved_missing_derivatives_context_count")
        ),
        "revise_case_count": _btpc_proxy_replay_quality_revise_case_count(artifact),
        "keep_observing_count": _int(counts.get("keep_observing_count")),
        "proxy_replay_quality_review_outcome_counts": dict(
            sorted(proxy_replay_quality_review_outcome_counts.items())
        ),
        "action_items": action_items,
        "default_next_step": review_outcome_default_next_step(artifact),
        "live_required_facts_satisfied": False,
        "l4_scope_change_recommended": False,
        "candidate_or_finalgate_authority": False,
    }


def _btpc_proxy_quality_action_items(case_rows: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    decisions = {
        str(row.get("proxy_replay_quality_review_outcome") or "")
        for row in case_rows
    }
    if "revise_live_fact_collection_but_l2_proxy_reviewable" in decisions:
        actions.append(
            "attach_live_derivatives_fact_sources_before_btpc_live_eligibility"
        )
    if "revise_conflict_disable_before_l2_promotion" in decisions:
        actions.append("review_btpc_strong_uptrend_conflict_disable_rule")
    if "revise_freshness_or_classifier_before_l2_promotion" in decisions:
        actions.append("review_btpc_freshness_or_classifier_stale_signal_rule")
    if "keep_observing_l2_shadow_with_proxy_context" in decisions:
        actions.append("continue_btpc_l2_shadow_observation_with_proxy_context")
    return actions


def _queue_item(row: dict[str, Any], gap_item: dict[str, Any]) -> dict[str, Any]:
    strategy_group_id = str(row.get("strategy_group_id") or "unknown")
    work_type = str(gap_item.get("work_type") or "strategy_review_work")
    gap = str(gap_item.get("gap") or "row_level_review")
    return {
        "queue_id": _queue_id(strategy_group_id, work_type, gap),
        "strategy_group_id": strategy_group_id,
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "current_tier": row.get("current_tier"),
        "review_work_action": row.get("review_work_action"),
        "work_type": work_type,
        "owner_priority": gap_item.get("owner_priority"),
        "scheduled": gap_item.get("scheduled") is True,
        "blocks_l2_progression": gap_item.get("blocks_l2_progression") is True,
        "gap": gap,
        "actionable_task": gap_item.get("actionable_task"),
        "validation_command": gap_item.get("validation_command"),
        "completion_signal": gap_item.get("completion_signal"),
        "repair_spec": _as_dict(gap_item.get("repair_spec")),
        "economic_spec": _as_dict(gap_item.get("economic_spec")),
        "coverage_status": gap_item.get("coverage_status"),
        "coverage_ready": gap_item.get("coverage_ready") is True,
        "next_stage_recommendation": gap_item.get("next_stage_recommendation"),
        "l4_scope_change_recommended": False,
    }


def _row_level_queue_item(row: dict[str, Any]) -> dict[str, Any]:
    strategy_group_id = str(row.get("strategy_group_id") or "unknown")
    review_work_action = str(row.get("review_work_action") or "continue_observation_review")
    if review_work_action == "continue_l2_shadow_quality_review":
        work_type = "strategy_quality_review"
        actionable_task = (
            f"{strategy_group_id}: collect L2 shadow outcome, cost, slippage, "
            "and invalidation evidence without changing L4 scope."
        )
        owner_priority = "signal-observation-grade-high"
    elif review_work_action == "build_replay_corpus_before_l2":
        work_type = "replay_corpus_work"
        actionable_task = (
            f"{strategy_group_id}: add non-executing replay corpus before any L2 "
            "intake decision."
        )
        owner_priority = "signal-observation-grade-medium"
    else:
        work_type = "strategy_review_work"
        actionable_task = f"{strategy_group_id}: continue observe-only review."
        owner_priority = "signal-observation-grade-medium"
    return {
        "queue_id": _queue_id(strategy_group_id, work_type, review_work_action),
        "strategy_group_id": strategy_group_id,
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "current_tier": row.get("current_tier"),
        "review_work_action": review_work_action,
        "work_type": work_type,
        "owner_priority": owner_priority,
        "scheduled": review_work_action != "park_or_vocabulary_only",
        "blocks_l2_progression": review_work_action
        in {"build_replay_corpus_before_l2", "add_would_enter_replay_case_before_l2"},
        "gap": None,
        "actionable_task": actionable_task,
        "validation_command": _validation_command(work_type),
        "completion_signal": _completion_signal(work_type),
        **_coverage_state(
            review_work_action=review_work_action,
            work_type=work_type,
            scheduled=review_work_action != "park_or_vocabulary_only",
            repair_spec={},
            economic_spec={},
        ),
        "l4_scope_change_recommended": False,
    }


def _owner_priority(*, review_work_action: str, current_tier: str, work_type: str) -> str:
    if review_work_action == "park_or_vocabulary_only":
        return "signal-observation-grade-low"
    if review_work_action == "continue_l2_shadow_quality_review":
        return (
            "signal-observation-grade-high"
            if current_tier == "L2"
            else "signal-observation-grade-medium"
        )
    if work_type in {"classifier_or_rule_work", "economic_replay_work"}:
        return "signal-observation-grade-high"
    if work_type == "required_fact_or_market_data_work":
        return "signal-observation-grade-medium"
    return "signal-observation-grade-medium"


def _blocks_l2_progression(*, review_work_action: str, readiness: str) -> bool:
    if review_work_action in {
        "repair_blocking_gaps_with_replay_or_facts",
        "build_replay_corpus_before_l2",
        "add_would_enter_replay_case_before_l2",
    }:
        return True
    return str(readiness).startswith("blocked_")


def _actionable_gap_task(
    *,
    gap: str,
    work_type: str,
    strategy_group_id: str,
    review_work_action: str,
    classifier_repair_spec: dict[str, Any],
    economic_replay_spec: dict[str, Any],
) -> str:
    prefix = f"{strategy_group_id}: {gap}"
    if review_work_action == "park_or_vocabulary_only":
        return f"{prefix}; keep parked unless new evidence appears."
    if work_type == "classifier_or_rule_work":
        target = classifier_repair_spec.get("target_classifier")
        if target:
            return (
                f"{prefix}; repair `{target}` using the listed entry/disable "
                "states and replay acceptance cases."
            )
        return f"{prefix}; define the runtime classifier or disable-state rule that removes the false-positive path."
    if work_type == "required_fact_or_market_data_work":
        return f"{prefix}; attach or model the missing required fact source for replay and readiness review."
    if work_type == "economic_replay_work":
        if economic_replay_spec:
            return (
                f"{prefix}; verify required cost, fill-slot, and leverage-survival "
                "fields against replay acceptance cases."
            )
        return f"{prefix}; replay with cost, slippage, funding, fill slot, and leverage survival fields."
    if work_type == "strategy_quality_review":
        return f"{prefix}; decide whether negative evidence means revise, park, or kill before L2."
    return f"{prefix}; resolve in strategy review before tier promotion."


def _validation_command(work_type: str) -> str:
    if work_type in {"economic_replay_work", "replay_corpus_work"}:
        return (
            "PYTHONDONTWRITEBYTECODE=1 python3 "
            "scripts/run_strategygroup_runtime_replay_lab.py "
            "--output-json output/runtime-monitor/latest-runtime-replay-lab.json "
            "--output-owner-progress output/runtime-monitor/latest-runtime-replay-lab.md"
        )
    if work_type in {
        "classifier_or_rule_work",
        "required_fact_or_market_data_work",
        "strategy_quality_review",
    }:
        return (
            "PYTHONDONTWRITEBYTECODE=1 python3 "
            "scripts/build_strategygroup_l2_readiness_review.py "
            "--output-json output/runtime-monitor/latest-l2-readiness-review.json "
            "--output-owner-progress output/runtime-monitor/latest-l2-readiness-review.md"
        )
    return (
        "PYTHONDONTWRITEBYTECODE=1 python3 "
        "scripts/build_strategygroup_opportunity_review_work_loop.py "
        "--output-json output/runtime-monitor/latest-opportunity-review-work-loop.json "
        "--output-owner-progress output/runtime-monitor/latest-opportunity-review-work-loop.md"
    )


def _completion_signal(
    work_type: str,
    repair_spec: dict[str, Any] | None = None,
    economic_spec: dict[str, Any] | None = None,
) -> str:
    if repair_spec and repair_spec.get("acceptance_signal"):
        return str(repair_spec["acceptance_signal"])
    if economic_spec and economic_spec.get("acceptance_signal"):
        return str(economic_spec["acceptance_signal"])
    return {
        "classifier_or_rule_work": "classifier gap removed or downgraded to review-only warning",
        "required_fact_or_market_data_work": "required fact gap removed or explicit non-blocking proxy documented",
        "economic_replay_work": "cost/slippage/funding survival fields present in replay review",
        "strategy_quality_review": "revise/park/kill decision recorded before promotion",
        "replay_corpus_work": "non-executing replay sample covers would-enter and no-action paths",
    }.get(work_type, "review work loop row no longer reports the gap")


def _coverage_state(
    *,
    review_work_action: str,
    work_type: str,
    scheduled: bool,
    repair_spec: dict[str, Any],
    economic_spec: dict[str, Any],
) -> dict[str, Any]:
    if not scheduled or review_work_action == "park_or_vocabulary_only":
        coverage_status = "parked"
    elif work_type == "classifier_or_rule_work":
        repair_coverage = _as_dict(repair_spec.get("replay_case_coverage"))
        coverage_status = (
            "local_replay_coverage_ready"
            if repair_coverage.get("covered") is True
            else "needs_replay_or_spec"
        )
    elif work_type == "economic_replay_work":
        economic_coverage = _as_dict(economic_spec.get("economic_case_coverage"))
        coverage_status = (
            "local_replay_coverage_ready"
            if economic_coverage.get("covered") is True
            else "needs_replay_or_spec"
        )
    elif work_type == "required_fact_or_market_data_work":
        coverage_status = "fact_source_pending"
    elif work_type == "strategy_quality_review":
        coverage_status = "strategy_asset_recommendation_pending"
    elif work_type == "strategy_review_work":
        coverage_status = "strategy_review_pending"
    else:
        coverage_status = "needs_replay_or_spec"
    return {
        "coverage_status": coverage_status,
        "coverage_ready": coverage_status == "local_replay_coverage_ready",
        "next_stage_recommendation": _next_stage_recommendation_for_coverage(
            coverage_status
        ),
    }


def _next_stage_recommendation_for_coverage(coverage_status: str) -> str:
    return {
        "local_replay_coverage_ready": (
            "strategy_quality_review_before_l2_no_promotion"
        ),
        "needs_replay_or_spec": "add_replay_or_spec_coverage_before_l2",
        "fact_source_pending": "attach_fact_source_before_l2_review",
        "strategy_asset_recommendation_pending": "record_revise_park_or_promote_recommendation",
        "strategy_review_pending": "continue_observe_only_review",
        "parked": "park_until_new_evidence",
    }.get(coverage_status, "continue_local_review")


def _matching_classifier_repair_spec(
    *,
    gap: str,
    work_type: str,
    classifier_repair_spec: dict[str, Any],
    replay: dict[str, Any],
) -> dict[str, Any]:
    if work_type != "classifier_or_rule_work" or not classifier_repair_spec:
        return {}
    gap_keys = [
        str(item) for item in classifier_repair_spec.get("blocking_gap_keys") or []
    ]
    if gap not in gap_keys:
        return {}
    replay_acceptance_cases = [
        str(item)
        for item in classifier_repair_spec.get("replay_acceptance_cases") or []
    ]
    fixture_cases = [str(item) for item in replay.get("fixture_cases") or []]
    fixture_case_set = set(fixture_cases)
    covered_cases = [
        item for item in replay_acceptance_cases if item in fixture_case_set
    ]
    missing_cases = [
        item for item in replay_acceptance_cases if item not in fixture_case_set
    ]
    return {
        "status": str(classifier_repair_spec.get("status") or "unknown"),
        "target_classifier": str(
            classifier_repair_spec.get("target_classifier") or "unknown"
        ),
        "required_entry_states": [
            str(item) for item in classifier_repair_spec.get("required_entry_states") or []
        ],
        "required_disable_states": [
            str(item)
            for item in classifier_repair_spec.get("required_disable_states") or []
        ],
        "replay_acceptance_cases": replay_acceptance_cases,
        "replay_case_coverage": {
            "covered": bool(replay_acceptance_cases) and not missing_cases,
            "required_case_count": len(replay_acceptance_cases),
            "covered_cases": covered_cases,
            "missing_cases": missing_cases,
        },
        "acceptance_signal": str(classifier_repair_spec.get("acceptance_signal") or ""),
        "revision_execution": _as_dict(
            classifier_repair_spec.get("revision_execution")
        ),
        "not_execution_authority": classifier_repair_spec.get("not_execution_authority")
        is True,
        "not_l2_promotion_authority": classifier_repair_spec.get(
            "not_l2_promotion_authority"
        )
        is True,
        "not_l4_scope_change": classifier_repair_spec.get("not_l4_scope_change") is True,
    }


def _matching_economic_replay_spec(
    *,
    gap: str,
    work_type: str,
    economic_replay_spec: dict[str, Any],
    replay: dict[str, Any],
) -> dict[str, Any]:
    if work_type != "economic_replay_work" or not economic_replay_spec:
        return {}
    gap_keys = [
        str(item) for item in economic_replay_spec.get("blocking_gap_keys") or []
    ]
    if gap not in gap_keys:
        return {}
    replay_acceptance_cases = [
        str(item)
        for item in economic_replay_spec.get("replay_acceptance_cases") or []
    ]
    required_cost_fields = [
        str(item) for item in economic_replay_spec.get("required_cost_fields") or []
    ]
    fields_by_case = _as_dict(replay.get("cost_review_fields_by_case"))
    case_coverage: dict[str, dict[str, Any]] = {}
    for fixture_case in replay_acceptance_cases:
        present_fields = set(str(item) for item in fields_by_case.get(fixture_case) or [])
        missing_fields = [
            field for field in required_cost_fields if field not in present_fields
        ]
        case_coverage[fixture_case] = {
            "covered": not missing_fields,
            "present_fields": sorted(present_fields),
            "missing_fields": missing_fields,
        }
    missing_cases = [
        fixture_case
        for fixture_case in replay_acceptance_cases
        if fixture_case not in fields_by_case
    ]
    uncovered_cases = [
        fixture_case
        for fixture_case, coverage in case_coverage.items()
        if coverage["covered"] is not True
    ]
    return {
        "status": str(economic_replay_spec.get("status") or "unknown"),
        "required_cost_fields": required_cost_fields,
        "replay_acceptance_cases": replay_acceptance_cases,
        "economic_case_coverage": {
            "covered": bool(replay_acceptance_cases)
            and not missing_cases
            and not uncovered_cases,
            "required_case_count": len(replay_acceptance_cases),
            "missing_cases": missing_cases,
            "uncovered_cases": uncovered_cases,
            "case_coverage": case_coverage,
        },
        "acceptance_signal": str(economic_replay_spec.get("acceptance_signal") or ""),
        "replay_execution": _as_dict(economic_replay_spec.get("replay_execution")),
        "not_execution_authority": economic_replay_spec.get("not_execution_authority")
        is True,
        "not_l2_promotion_authority": economic_replay_spec.get(
            "not_l2_promotion_authority"
        )
        is True,
        "not_l4_scope_change": economic_replay_spec.get("not_l4_scope_change") is True,
    }


def _cost_review_fields_by_case(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    output: dict[str, list[str]] = {}
    for row in rows:
        fixture_case = str(row.get("fixture_case") or "")
        if not fixture_case:
            continue
        cost_review = _as_dict(row.get("cost_review"))
        output[fixture_case] = sorted(
            str(key)
            for key, value in cost_review.items()
            if value is not None and str(value) != ""
        )
    return output


def _queue_id(strategy_group_id: str, work_type: str, label: str) -> str:
    return "{}:{}:{}".format(strategy_group_id, work_type, _slug(label))


def _slug(value: str) -> str:
    chars: list[str] = []
    previous_dash = False
    for char in value.lower():
        if char.isalnum():
            chars.append(char)
            previous_dash = False
        elif not previous_dash:
            chars.append("-")
            previous_dash = True
    slug = "".join(chars).strip("-")
    return slug[:80] or "item"


def _work_queue_sort_key(item: dict[str, Any]) -> tuple[int, int, str, str]:
    priority_rank = {
        "signal-observation-grade-high": 0,
        "signal-observation-grade-medium": 1,
        "signal-observation-grade-low": 2,
    }
    work_rank = {
        "classifier_or_rule_work": 0,
        "economic_replay_work": 1,
        "required_fact_or_market_data_work": 2,
        "strategy_quality_review": 3,
        "strategy_review_work": 4,
        "replay_corpus_work": 5,
    }
    return (
        priority_rank.get(str(item.get("owner_priority")), 9),
        work_rank.get(str(item.get("work_type")), 9),
        str(item.get("strategy_group_id") or ""),
        str(item.get("queue_id") or ""),
    )


def _next_local_work_checkpoint(scheduled: list[dict[str, Any]]) -> str:
    if not scheduled:
        return "continue_waiting_for_live_signal_and_keep_low_priority_observation"
    if any(
        item.get("next_stage_recommendation")
        == "strategy_quality_review_before_l2_no_promotion"
        for item in scheduled
    ):
        return "record_strategy_asset_recommendations_for_coverage_ready_items"
    work_types = {str(item.get("work_type")) for item in scheduled[:4]}
    groups = {str(item.get("strategy_group_id")) for item in scheduled[:4]}
    if "classifier_or_rule_work" in work_types:
        return "repair_classifier_or_disable_state_gaps_for_lsr_vcb"
    if "economic_replay_work" in work_types:
        return "run_cost_slippage_funding_replay_for_observed_would_enter_rows"
    if "required_fact_or_market_data_work" in work_types and "BTPC-001" in groups:
        return "continue_btpc_l2_shadow_fact_quality_review"
    return "execute_top_scheduled_signal_observation_work_queue_items"


def _work_queue_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "| Priority | StrategyGroup | Work | Coverage | Next | Scheduled | Blocks L2 |\n| --- | --- | --- | --- | --- | --- | --- |\n| none | - | - | - | - | - | - |"
    output = [
        "| Priority | StrategyGroup | Work | Coverage | Next | Scheduled | Blocks L2 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows[:8]:
        output.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row.get("owner_priority"),
                row.get("strategy_group_id"),
                row.get("work_type"),
                row.get("coverage_status"),
                row.get("next_stage_recommendation"),
                str(row.get("scheduled")).lower(),
                str(row.get("blocks_l2_progression")).lower(),
            )
        )
    return "\n".join(output)


def _strategy_quality_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "| StrategyGroup | Tier | Decision | Next | Replay | Revise | Coverage Ready | Revision Tasks | Revision Ready | Revision Executed |\n| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |\n| none | - | - | - | - | - | - | - | - | - |"
    output = [
        "| StrategyGroup | Tier | Decision | Next | Replay | Revise | Coverage Ready | Revision Tasks | Revision Ready | Revision Executed |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        evidence = _as_dict(row.get("evidence"))
        execution = _as_dict(row.get("revision_execution"))
        output.append(
            "| `{}` | `{}` | `{}` | `{}` | {} | {} | {} | {} | {} | {} |".format(
                row.get("strategy_group_id"),
                row.get("current_tier"),
                row.get("strategy_asset_recommendation"),
                row.get("next_stage"),
                evidence.get("replay_sample_count", 0),
                evidence.get("revise_sample_count", 0),
                evidence.get("coverage_ready_item_count", 0),
                row.get("revision_task_count", 0),
                row.get("revision_ready_count", 0),
                execution.get("executed_count", 0),
            )
        )
    return "\n".join(output)


def _default_next_step(
    rows: list[dict[str, Any]],
    forbidden_effects: list[str],
    work_queue: dict[str, Any],
    strategy_asset_recommendations: dict[str, Any],
    post_revision_review_artifact: dict[str, Any],
) -> str:
    if forbidden_effects:
        return "stop_and_repair_forbidden_source_effects"
    if not rows:
        return "continue_signal_coverage_monitoring"
    strategy_quality_next = str(
        strategy_asset_recommendations.get("next_checkpoint") or ""
    )
    if strategy_quality_next and strategy_quality_next != (
        "continue_l2_shadow_and_observe_only_review"
    ):
        post_revision_next = _post_revision_next_step(
            strategy_quality_next=strategy_quality_next,
            post_revision_review_artifact=post_revision_review_artifact,
        )
        if post_revision_next:
            return post_revision_next
        return strategy_quality_next
    next_checkpoint = str(work_queue.get("next_local_checkpoint") or "")
    if next_checkpoint:
        return next_checkpoint
    if any(row["review_work_action"] == "repair_blocking_gaps_with_replay_or_facts" for row in rows):
        return "map_blocking_gaps_to_required_facts_or_classifier_tasks"
    if any(row["review_work_action"] == "build_replay_corpus_before_l2" for row in rows):
        return "add_missing_replay_corpus_before_l2"
    return "continue_l2_shadow_and_observe_only_review"


def _forbidden_effects(*artifacts: dict[str, Any]) -> list[str]:
    effects = source_forbidden_effects(
        (
            (f"artifact_{index}", artifact)
            for index, artifact in enumerate(artifacts)
        ),
        true_keys=(
            "server_files_mutated",
            "runtime_started",
            "strategy_parameters_changed",
            "tier_policy_changed",
            "shadow_candidate_created",
            "execution_intent_created",
            "final_gate_called",
            "operation_layer_called",
            "order_created",
            "order_lifecycle_called",
            "exchange_write_called",
            "withdrawal_or_transfer_created",
        ),
    )
    for index, artifact in enumerate(artifacts):
        if review_outcome_flag(artifact, "proxy_replay_satisfies_live_required_facts"):
            effects.append(
                "artifact_{}.review_outcome_state."
                "proxy_replay_satisfies_live_required_facts".format(index)
            )
    return sorted(set(effects))


def _post_revision_next_step(
    *,
    strategy_quality_next: str,
    post_revision_review_artifact: dict[str, Any],
) -> str | None:
    if strategy_quality_next != "run_lsr001_vcb001_post_revision_replay_review_before_l2":
        return None
    if not post_revision_review_artifact:
        return None
    if _post_revision_review_passed(post_revision_review_artifact):
        return "record_lsr001_vcb001_post_revision_quality_before_l2"
    if _source_status(post_revision_review_artifact) == "blocked":
        return "repair_lsr001_vcb001_post_revision_replay_failures"
    return None


def _post_revision_review_passed(artifact: dict[str, Any]) -> bool:
    return (
        _source_status(artifact) == "passed"
        and review_outcome_flag(artifact, "post_revision_replay_review_passed")
    )


def _source_status(artifact: dict[str, Any]) -> str:
    return str(artifact.get("status") or "") if isinstance(artifact, dict) else ""


def _review_work_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "| StrategyGroup | Tier | Replay | Gaps | Review Work |\n| --- | --- | ---: | ---: | --- |\n| none | - | - | - | - |"
    output = [
        "| StrategyGroup | Tier | Replay | Gaps | Review Work |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for row in rows:
        output.append(
            "| `{}` | `{}` | {} | {} | `{}` |".format(
                row.get("strategy_group_id"),
                row.get("current_tier"),
                _as_dict(row.get("replay_verification")).get("sample_count", 0),
                len(row.get("blocking_gaps_before_l2") or []),
                row.get("review_work_action"),
            )
        )
    return "\n".join(output)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)]


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return payload


def _load_optional_json_object(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        return _load_json_object(path)
    except FileNotFoundError:
        return {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--expansion-review-json", default=str(DEFAULT_EXPANSION_REVIEW_JSON)
    )
    parser.add_argument("--l2-readiness-json", default=str(DEFAULT_L2_READINESS_JSON))
    parser.add_argument("--l2-intake-json", default=str(DEFAULT_L2_INTAKE_JSON))
    parser.add_argument("--replay-lab-json", default=str(DEFAULT_REPLAY_LAB_JSON))
    parser.add_argument(
        "--post-revision-review-json",
        default=str(DEFAULT_POST_REVISION_REPLAY_REVIEW_JSON),
    )
    parser.add_argument(
        "--btpc-proxy-replay-quality-json",
        default="",
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OWNER_PROGRESS))
    args = parser.parse_args(argv)

    artifact = build_opportunity_review_work_loop(
        expansion_review_artifact=_load_json_object(
            Path(args.expansion_review_json).expanduser()
        ),
        l2_readiness_artifact=_load_json_object(
            Path(args.l2_readiness_json).expanduser()
        ),
        l2_intake_artifact=_load_json_object(Path(args.l2_intake_json).expanduser()),
        replay_lab_artifact=_load_json_object(Path(args.replay_lab_json).expanduser()),
        post_revision_review_artifact=_load_optional_json_object(
            Path(args.post_revision_review_json).expanduser()
            if args.post_revision_review_json
            else None
        ),
        btpc_proxy_replay_quality_artifact=_load_optional_json_object(
            Path(args.btpc_proxy_replay_quality_json).expanduser()
            if args.btpc_proxy_replay_quality_json
            else None
        ),
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
