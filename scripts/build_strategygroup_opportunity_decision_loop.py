#!/usr/bin/env python3
"""Build a local StrategyGroup opportunity-to-decision loop packet.

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
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
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
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-opportunity-decision-loop.json"
)
DEFAULT_OWNER_PROGRESS = (
    REPO_ROOT / "output/runtime-monitor/latest-opportunity-decision-loop.md"
)


def build_opportunity_decision_loop(
    *,
    expansion_review_packet: dict[str, Any],
    l2_readiness_packet: dict[str, Any],
    l2_intake_packet: dict[str, Any],
    replay_lab_packet: dict[str, Any],
) -> dict[str, Any]:
    review_rows = _dict_rows(expansion_review_packet.get("review_rows"))
    readiness_by_group = {
        str(row.get("strategy_group_id") or "unknown"): row
        for row in _dict_rows(l2_readiness_packet.get("readiness_rows"))
    }
    intake_by_group = {
        str(row.get("strategy_group_id") or "unknown"): row
        for row in _dict_rows(l2_intake_packet.get("source_readiness_rows"))
    }
    replay_by_group = _replay_summary_by_group(replay_lab_packet)
    decision_rows = [
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
    work_queue = _work_queue(decision_rows)
    forbidden_effects = _forbidden_effects(
        expansion_review_packet,
        l2_readiness_packet,
        l2_intake_packet,
        replay_lab_packet,
    )
    status = (
        "blocked_forbidden_effect"
        if forbidden_effects
        else "decision_loop_ready"
        if decision_rows
        else "no_observed_opportunities"
    )
    action_counts = Counter(row["decision_action"] for row in decision_rows)
    return {
        "schema": "brc.strategygroup_opportunity_decision_loop.v1",
        "scope": "strategygroup_opportunity_decision_loop",
        "status": status,
        "source_status": {
            "expansion_review": expansion_review_packet.get("status"),
            "l2_readiness": l2_readiness_packet.get("status"),
            "l2_intake": l2_intake_packet.get("status"),
            "replay_lab": replay_lab_packet.get("status"),
        },
        "interaction": {
            "level": "L0_local_opportunity_decision_loop",
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "counts": {
            "observed_opportunity_count": len(decision_rows),
            "replay_covered_count": sum(
                1 for row in decision_rows if row["replay_verification"]["covered"]
            ),
            "blocking_gap_group_count": sum(
                1 for row in decision_rows if row["blocking_gaps_before_l2"]
            ),
            "work_queue_item_count": work_queue["counts"]["total"],
            "scheduled_work_queue_item_count": work_queue["counts"]["scheduled"],
            "l2_enabled_count": sum(
                1
                for row in decision_rows
                if row["tier_state"] == "l2_shadow_candidate_observation_enabled"
            ),
            "real_order_authorized_count": 0,
            "l4_scope_change_recommended_count": 0,
            "forbidden_effect_count": len(forbidden_effects),
        },
        "action_counts": dict(sorted(action_counts.items())),
        "decision_rows": decision_rows,
        "work_queue": work_queue,
        "decision": {
            "repeatable_loop_ready": bool(decision_rows) and not forbidden_effects,
            "real_order_scope_change_recommended": False,
            "l4_promotion_recommended": False,
            "tier_policy_change_recommended_now": False,
            "default_next_step": _default_next_step(
                decision_rows, forbidden_effects, work_queue
            ),
        },
        "operator_command_plan": {
            "not_executed": True,
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
            "local_decision_loop_only": True,
            "input_is_not_execution_authority": True,
            "server_interaction": False,
            "server_files_mutated": False,
            "runtime_started": False,
            "strategy_parameters_changed": False,
            "tier_policy_changed": False,
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
    lines = [
        "# StrategyGroup Opportunity Decision Loop",
        "",
        "## Summary",
        "",
        f"- Status: `{packet.get('status')}`",
        f"- Observed opportunities: `{_as_dict(packet.get('counts')).get('observed_opportunity_count', 0)}`",
        f"- Replay covered: `{_as_dict(packet.get('counts')).get('replay_covered_count', 0)}`",
        "- L4 scope change: `false`",
        "- Real order authority: `false`",
        "",
        "## Decision Rows",
        "",
        _decision_table(_dict_rows(packet.get("decision_rows"))),
        "",
        "## Next",
        "",
        f"- `{_as_dict(packet.get('decision')).get('default_next_step')}`",
        "",
        "## Work Queue",
        "",
        _work_queue_table(_dict_rows(_as_dict(packet.get("work_queue")).get("items"))),
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
    decision_action = _decision_action(
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
            decision_action=decision_action,
            classifier_repair_spec=classifier_repair_spec,
            economic_replay_spec=economic_replay_spec,
            replay=replay,
        )
        for gap in gaps
    ]
    return {
        "strategy_group_id": strategy_group_id,
        "symbol": review_row.get("symbol") or readiness_row.get("symbol"),
        "side": review_row.get("side") or readiness_row.get("side"),
        "observed_signal": {
            "source": "signal_coverage_expansion_review",
            "would_enter": True,
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
        "decision_action": decision_action,
        "next_checkpoint": _next_checkpoint(decision_action),
        "real_order_authority": False,
        "l4_scope_change_recommended": False,
        "candidate_or_finalgate_authority": False,
    }


def _replay_summary_by_group(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for key in (
        "replay_samples",
        "l2_shadow_replay_samples",
        "l1_observe_replay_samples",
    ):
        samples.extend(_dict_rows(packet.get(key)))
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


def _decision_action(
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
    decision_action: str,
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
        decision_action=decision_action,
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
        "scheduled": decision_action != "park_or_vocabulary_only",
        "blocks_l2_progression": _blocks_l2_progression(
            decision_action=decision_action,
            readiness=readiness,
        ),
        "actionable_task": _actionable_gap_task(
            gap=gap,
            work_type=work_type,
            strategy_group_id=strategy_group_id,
            decision_action=decision_action,
            classifier_repair_spec=matching_repair_spec,
            economic_replay_spec=matching_economic_spec,
        ),
        "validation_command": _validation_command(work_type),
        "completion_signal": _completion_signal(
            work_type, matching_repair_spec, matching_economic_spec
        ),
        "repair_spec": matching_repair_spec,
        "economic_spec": matching_economic_spec,
    }


def _work_queue(rows: list[dict[str, Any]]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for row in rows:
        if row.get("decision_action") in {
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
        },
        "by_work_type": dict(sorted(by_type.items())),
        "by_owner_priority": dict(sorted(by_priority.items())),
        "items": items,
        "safety_invariants": {
            "local_work_queue_only": True,
            "changes_strategy_parameters": False,
            "changes_tier_policy": False,
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
            "mutates_server_files": False,
            "real_order_authorized": False,
        },
    }


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
        "decision_action": row.get("decision_action"),
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
        "real_order_authority": False,
        "l4_scope_change_recommended": False,
    }


def _row_level_queue_item(row: dict[str, Any]) -> dict[str, Any]:
    strategy_group_id = str(row.get("strategy_group_id") or "unknown")
    decision_action = str(row.get("decision_action") or "continue_observation_review")
    if decision_action == "continue_l2_shadow_quality_review":
        work_type = "strategy_quality_review"
        actionable_task = (
            f"{strategy_group_id}: collect L2 shadow outcome, cost, slippage, "
            "and invalidation evidence without changing L4 scope."
        )
        owner_priority = "P0.5-high"
    elif decision_action == "build_replay_corpus_before_l2":
        work_type = "replay_corpus_work"
        actionable_task = (
            f"{strategy_group_id}: add non-executing replay corpus before any L2 "
            "intake decision."
        )
        owner_priority = "P0.5-medium"
    else:
        work_type = "strategy_review_work"
        actionable_task = f"{strategy_group_id}: continue observe-only review."
        owner_priority = "P0.5-medium"
    return {
        "queue_id": _queue_id(strategy_group_id, work_type, decision_action),
        "strategy_group_id": strategy_group_id,
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "current_tier": row.get("current_tier"),
        "decision_action": decision_action,
        "work_type": work_type,
        "owner_priority": owner_priority,
        "scheduled": decision_action != "park_or_vocabulary_only",
        "blocks_l2_progression": decision_action
        in {"build_replay_corpus_before_l2", "add_would_enter_replay_case_before_l2"},
        "gap": None,
        "actionable_task": actionable_task,
        "validation_command": _validation_command(work_type),
        "completion_signal": _completion_signal(work_type),
        "real_order_authority": False,
        "l4_scope_change_recommended": False,
    }


def _owner_priority(*, decision_action: str, current_tier: str, work_type: str) -> str:
    if decision_action == "park_or_vocabulary_only":
        return "P0.5-low"
    if decision_action == "continue_l2_shadow_quality_review":
        return "P0.5-high" if current_tier == "L2" else "P0.5-medium"
    if work_type in {"classifier_or_rule_work", "economic_replay_work"}:
        return "P0.5-high"
    if work_type == "required_fact_or_market_data_work":
        return "P0.5-medium"
    return "P0.5-medium"


def _blocks_l2_progression(*, decision_action: str, readiness: str) -> bool:
    if decision_action in {
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
    decision_action: str,
    classifier_repair_spec: dict[str, Any],
    economic_replay_spec: dict[str, Any],
) -> str:
    prefix = f"{strategy_group_id}: {gap}"
    if decision_action == "park_or_vocabulary_only":
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
        "scripts/build_strategygroup_opportunity_decision_loop.py "
        "--output-json output/runtime-monitor/latest-opportunity-decision-loop.json "
        "--output-owner-progress output/runtime-monitor/latest-opportunity-decision-loop.md"
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
    }.get(work_type, "decision loop row no longer reports the gap")


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
    priority_rank = {"P0.5-high": 0, "P0.5-medium": 1, "P0.5-low": 2}
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
    work_types = {str(item.get("work_type")) for item in scheduled[:4]}
    groups = {str(item.get("strategy_group_id")) for item in scheduled[:4]}
    if "classifier_or_rule_work" in work_types:
        return "repair_classifier_or_disable_state_gaps_for_lsr_vcb"
    if "economic_replay_work" in work_types:
        return "run_cost_slippage_funding_replay_for_observed_would_enter_rows"
    if "required_fact_or_market_data_work" in work_types and "BTPC-001" in groups:
        return "continue_btpc_l2_shadow_fact_quality_review"
    return "execute_top_scheduled_p0_5_work_queue_items"


def _work_queue_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "| Priority | StrategyGroup | Work | Scheduled | Blocks L2 |\n| --- | --- | --- | --- | --- |\n| none | - | - | - | - |"
    output = [
        "| Priority | StrategyGroup | Work | Scheduled | Blocks L2 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows[:8]:
        output.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row.get("owner_priority"),
                row.get("strategy_group_id"),
                row.get("work_type"),
                str(row.get("scheduled")).lower(),
                str(row.get("blocks_l2_progression")).lower(),
            )
        )
    return "\n".join(output)


def _default_next_step(
    rows: list[dict[str, Any]],
    forbidden_effects: list[str],
    work_queue: dict[str, Any],
) -> str:
    if forbidden_effects:
        return "stop_and_repair_forbidden_source_effects"
    if not rows:
        return "continue_signal_coverage_monitoring"
    next_checkpoint = str(work_queue.get("next_local_checkpoint") or "")
    if next_checkpoint:
        return next_checkpoint
    if any(row["decision_action"] == "repair_blocking_gaps_with_replay_or_facts" for row in rows):
        return "map_blocking_gaps_to_required_facts_or_classifier_tasks"
    if any(row["decision_action"] == "build_replay_corpus_before_l2" for row in rows):
        return "add_missing_replay_corpus_before_l2"
    return "continue_l2_shadow_and_observe_only_review"


def _forbidden_effects(*packets: dict[str, Any]) -> list[str]:
    effects: list[str] = []
    for index, packet in enumerate(packets):
        safety = _as_dict(packet.get("safety_invariants"))
        for item in safety.get("source_forbidden_effects") or []:
            effects.append(f"packet_{index}.{item}")
        for key in (
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
        ):
            if safety.get(key) is True:
                effects.append(f"packet_{index}.safety.{key}")
    return sorted(set(effects))


def _decision_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "| StrategyGroup | Tier | Replay | Gaps | Decision |\n| --- | --- | ---: | ---: | --- |\n| none | - | - | - | - |"
    output = [
        "| StrategyGroup | Tier | Replay | Gaps | Decision |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for row in rows:
        output.append(
            "| `{}` | `{}` | {} | {} | `{}` |".format(
                row.get("strategy_group_id"),
                row.get("current_tier"),
                _as_dict(row.get("replay_verification")).get("sample_count", 0),
                len(row.get("blocking_gaps_before_l2") or []),
                row.get("decision_action"),
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--expansion-review-json", default=str(DEFAULT_EXPANSION_REVIEW_JSON)
    )
    parser.add_argument("--l2-readiness-json", default=str(DEFAULT_L2_READINESS_JSON))
    parser.add_argument("--l2-intake-json", default=str(DEFAULT_L2_INTAKE_JSON))
    parser.add_argument("--replay-lab-json", default=str(DEFAULT_REPLAY_LAB_JSON))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OWNER_PROGRESS))
    args = parser.parse_args(argv)

    packet = build_opportunity_decision_loop(
        expansion_review_packet=_load_json_object(
            Path(args.expansion_review_json).expanduser()
        ),
        l2_readiness_packet=_load_json_object(
            Path(args.l2_readiness_json).expanduser()
        ),
        l2_intake_packet=_load_json_object(Path(args.l2_intake_json).expanduser()),
        replay_lab_packet=_load_json_object(Path(args.replay_lab_json).expanduser()),
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
