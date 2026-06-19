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
        "decision": {
            "repeatable_loop_ready": bool(decision_rows) and not forbidden_effects,
            "real_order_scope_change_recommended": False,
            "l4_promotion_recommended": False,
            "tier_policy_change_recommended_now": False,
            "default_next_step": _default_next_step(decision_rows, forbidden_effects),
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
    replay = _normalized_replay_summary(replay_summary)
    gap_work = [_gap_work_item(gap) for gap in gaps]
    decision_action = _decision_action(
        current_tier=current_tier,
        readiness=readiness,
        replay=replay,
        gaps=gaps,
    )
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


def _gap_work_item(gap: str) -> dict[str, str]:
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
    return {"gap": gap, "work_type": work_type}


def _default_next_step(rows: list[dict[str, Any]], forbidden_effects: list[str]) -> str:
    if forbidden_effects:
        return "stop_and_repair_forbidden_source_effects"
    if not rows:
        return "continue_signal_coverage_monitoring"
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
