#!/usr/bin/env python3
"""Build the minimal StrategyGroup Decision Ledger.

This command compresses existing local P0.5 evidence into one current
StrategyGroup decision row per group. It consumes lower-level opportunity,
no-action, and replay evidence, but it does not create live authority, mutate
strategy parameters, start runtime, call FinalGate, call the Operation Layer,
write to an exchange, or place orders.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OPPORTUNITY_DECISION_LOOP_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-opportunity-decision-loop.json"
)
DEFAULT_SIGNAL_COVERAGE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-signal-coverage-diagnostic.json"
)
DEFAULT_TIER_POLICY_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-decision-ledger.json"
)
DEFAULT_OWNER_PROGRESS = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-decision-ledger.md"
)

ALLOWED_DECISIONS = {
    "go_live",
    "do_not_go_live",
    "keep_observing",
    "revise",
    "park",
    "kill",
    "promote",
    "block_for_safety",
}


def build_strategygroup_decision_ledger(
    *,
    opportunity_decision_loop_packet: dict[str, Any],
    signal_coverage_packet: dict[str, Any],
    tier_policy: dict[str, Any],
) -> dict[str, Any]:
    no_action_by_group = _high_priority_no_action_by_group(signal_coverage_packet)
    quality_rows = _dict_rows(
        _as_dict(opportunity_decision_loop_packet.get("strategy_quality_decisions")).get(
            "rows"
        )
    )
    current_tier_by_group = _current_tier_by_group(tier_policy)
    ledger_rows: list[dict[str, Any]] = []
    used_groups: set[str] = set()

    for row in quality_rows:
        group = str(row.get("strategy_group_id") or "unknown")
        ledger_rows.append(
            _ledger_row_from_quality(
                row=row,
                no_action_row=no_action_by_group.get(group),
                default_tier=current_tier_by_group.get(group, "unknown"),
            )
        )
        used_groups.add(group)

    for group, no_action_row in sorted(no_action_by_group.items()):
        if group in used_groups:
            continue
        ledger_rows.append(
            _ledger_row_from_no_action(
                group=group,
                row=no_action_row,
                tier=current_tier_by_group.get(group, "unknown"),
            )
        )

    ledger_rows = sorted(
        [_normalize_ledger_row(row) for row in ledger_rows],
        key=lambda row: str(row.get("strategy_group_id") or ""),
    )
    forbidden_effects = _forbidden_effects(
        opportunity_decision_loop_packet,
        signal_coverage_packet,
    )
    decision_counts = Counter(str(row.get("decision") or "unknown") for row in ledger_rows)
    tier_review_rows = [_tier_review_row(row) for row in ledger_rows]
    status = (
        "blocked_forbidden_effect"
        if forbidden_effects
        else "decision_ledger_ready"
        if ledger_rows
        else "decision_ledger_empty"
    )
    return {
        "schema": "brc.strategygroup_decision_ledger.v1",
        "scope": "strategygroup_decision_ledger",
        "status": status,
        "source_status": {
            "opportunity_decision_loop": opportunity_decision_loop_packet.get("status"),
            "signal_coverage": signal_coverage_packet.get("status"),
        },
        "interaction": {
            "level": "L0_local_strategygroup_decision_ledger",
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "counts": {
            "strategy_group_count": len(ledger_rows),
            "current_row_count": len(ledger_rows),
            "high_priority_no_action_group_count": len(no_action_by_group),
            "forbidden_effect_count": len(forbidden_effects),
            "real_order_authorized_count": 0,
            "l4_scope_change_recommended_count": 0,
        },
        "decision_counts": dict(sorted(decision_counts.items())),
        "required_row_fields": [
            "strategy_group_id",
            "tier",
            "opportunity_type",
            "decision",
            "reason",
            "required_next_evidence",
            "authority_boundary",
            "next_checkpoint",
        ],
        "ledger_rows": ledger_rows,
        "tier_review": {
            "status": "ready" if ledger_rows and not forbidden_effects else "empty",
            "basis": "decision_ledger_only",
            "rows": tier_review_rows,
            "counts": dict(
                sorted(
                    Counter(str(row.get("tier_review_decision")) for row in tier_review_rows).items()
                )
            ),
        },
        "decision": {
            "single_main_product": True,
            "one_current_row_per_strategy_group": _one_row_per_group(ledger_rows),
            "raw_replay_samples_duplicated": False,
            "no_action_attribution_is_field_input_only": True,
            "replay_decision_bridge_is_field_input_only": True,
            "real_order_scope_change_recommended": False,
            "l4_promotion_recommended": False,
            "default_next_step": _default_next_step(ledger_rows, forbidden_effects),
        },
        "safety_invariants": {
            "local_decision_ledger_only": True,
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
    counts = _as_dict(packet.get("counts"))
    lines = [
        "# StrategyGroup Decision Ledger",
        "",
        "## Summary",
        "",
        f"- Status: `{packet.get('status')}`",
        f"- Current rows: `{counts.get('current_row_count', 0)}`",
        f"- High-priority no-action groups: `{counts.get('high_priority_no_action_group_count', 0)}`",
        "- Single main product: `true`",
        "- Real order authority: `false`",
        "- L4 scope change: `false`",
        "",
        "## Current Decisions",
        "",
        _ledger_table(_dict_rows(packet.get("ledger_rows"))),
        "",
        "## Tier Review",
        "",
        _tier_review_table(_dict_rows(_as_dict(packet.get("tier_review")).get("rows"))),
        "",
        "## Next",
        "",
        f"- `{_as_dict(packet.get('decision')).get('default_next_step')}`",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _ledger_row_from_quality(
    *,
    row: dict[str, Any],
    no_action_row: dict[str, Any] | None,
    default_tier: str,
) -> dict[str, Any]:
    quality_decision = str(row.get("strategy_quality_decision") or "")
    decision = _decision_from_quality(quality_decision)
    evidence = _as_dict(row.get("evidence"))
    no_action_reason = _no_action_reason(no_action_row)
    replay_part = "replay_samples:{} revise_samples:{}".format(
        _int(evidence.get("replay_sample_count")),
        _int(evidence.get("revise_sample_count")),
    )
    base_reason = str(row.get("reason") or quality_decision or "decision_loop_evidence")
    reason = _join_reason_parts([base_reason, no_action_reason, replay_part])
    next_checkpoint = str(row.get("next_stage") or "continue_local_review")
    return {
        "strategy_group_id": str(row.get("strategy_group_id") or "unknown"),
        "tier": str(row.get("current_tier") or default_tier or "unknown"),
        "opportunity_type": (
            "no_action"
            if no_action_row and _int(evidence.get("would_enter_sample_count")) <= 0
            else "would_enter"
        ),
        "decision": decision,
        "reason": reason,
        "required_next_evidence": _required_next_evidence(
            decision=decision,
            quality_row=row,
            no_action_row=no_action_row,
        ),
        "authority_boundary": _authority_boundary(row),
        "next_checkpoint": next_checkpoint,
    }


def _ledger_row_from_no_action(
    *,
    group: str,
    row: dict[str, Any],
    tier: str,
) -> dict[str, Any]:
    decision = _decision_from_no_action(row)
    return {
        "strategy_group_id": group,
        "tier": tier,
        "opportunity_type": "no_action",
        "decision": decision,
        "reason": _no_action_reason(row) or "high_priority_no_action_requires_review",
        "required_next_evidence": _required_next_evidence_from_no_action(row),
        "authority_boundary": "local_decision_support_only; real_order_authority=false; no_finalgate_no_operation_layer_no_exchange_write",
        "next_checkpoint": _next_checkpoint_from_no_action(row),
    }


def _decision_from_quality(quality_decision: str) -> str:
    if quality_decision in {
        "revise_before_l2",
        "keep_l2_shadow_and_revise_fact_classifier_inputs",
    }:
        return "revise"
    if quality_decision.startswith("keep_observing"):
        return "keep_observing"
    if quality_decision == "prepare_l2_intake_review_without_promotion":
        return "promote"
    if quality_decision == "park_until_new_edge":
        return "park"
    if quality_decision == "needs_replay_before_quality_decision":
        return "keep_observing"
    return "keep_observing"


def _decision_from_no_action(row: dict[str, Any]) -> str:
    action = str(row.get("policy_recommended_action") or "")
    readiness = str(row.get("policy_l2_readiness") or "")
    reasons = " ".join(str(item) for item in row.get("reason_codes") or [])
    if "park" in action or "park" in readiness:
        return "park"
    if any(token in action + " " + readiness + " " + reasons for token in ("rewrite", "redesign", "classifier", "facts")):
        return "revise"
    return "keep_observing"


def _required_next_evidence(
    *,
    decision: str,
    quality_row: dict[str, Any],
    no_action_row: dict[str, Any] | None,
) -> str:
    revision = _as_dict(quality_row.get("revision_completion"))
    execution = _as_dict(quality_row.get("revision_execution"))
    evidence = _as_dict(quality_row.get("evidence"))
    if decision == "revise":
        if revision.get("status") not in {"no_revision_required", "local_revision_completion_ready"}:
            blockers = revision.get("completion_blockers") or []
            return "complete_revision_specs:{}".format(",".join(str(item) for item in blockers) or "pending")
        if execution.get("status") not in {"no_revision_execution_required", "local_revision_execution_complete"}:
            blockers = execution.get("execution_blockers") or []
            return "execute_local_revision_tasks:{}".format(",".join(str(item) for item in blockers) or "pending")
        return str(quality_row.get("next_stage") or "post_revision_replay_review")
    if decision == "promote":
        return "tier_review_and_owner_lane_boundary_before_any_policy_change"
    if decision == "park":
        return "material_new_edge_evidence"
    if no_action_row:
        return _required_next_evidence_from_no_action(no_action_row)
    if _int(evidence.get("fact_source_pending_item_count")):
        return "attach_required_fact_sources"
    if _int(evidence.get("replay_sample_count")) <= 0:
        return "add_non_executing_replay_coverage"
    return str(quality_row.get("next_stage") or "continue_observation")


def _required_next_evidence_from_no_action(row: dict[str, Any]) -> str:
    readiness = str(row.get("policy_l2_readiness") or "")
    action = str(row.get("policy_recommended_action") or "")
    if "classifier" in readiness or "classifier" in action:
        return "classifier_disable_or_entry_state_review"
    if "fact" in readiness or "fact" in action:
        return "required_fact_source_mapping"
    if "rewrite" in readiness or "rewrite" in action:
        return "side_specific_classifier_rewrite_review"
    if "l2_shadow" in readiness or "l2_shadow" in action:
        return "l2_shadow_quality_observation"
    return "next_high_priority_replay_or_market_observation"


def _next_checkpoint_from_no_action(row: dict[str, Any]) -> str:
    action = str(row.get("policy_recommended_action") or "")
    if action:
        return action
    return _required_next_evidence_from_no_action(row)


def _authority_boundary(row: dict[str, Any]) -> str:
    if (
        row.get("real_order_authority") is False
        and row.get("candidate_or_finalgate_authority") is False
        and row.get("not_l4_scope_change") is True
    ):
        return "local_decision_support_only; real_order_authority=false; no_l4_scope_change; no_finalgate_no_operation_layer_no_exchange_write"
    return "local_decision_support_only; real_order_authority=false; no_finalgate_no_operation_layer_no_exchange_write"


def _normalize_ledger_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "strategy_group_id": str(row.get("strategy_group_id") or "unknown"),
        "tier": str(row.get("tier") or "unknown"),
        "opportunity_type": str(row.get("opportunity_type") or "no_action"),
        "decision": str(row.get("decision") or "keep_observing"),
        "reason": str(row.get("reason") or "decision_required"),
        "required_next_evidence": str(row.get("required_next_evidence") or "none"),
        "authority_boundary": str(row.get("authority_boundary") or ""),
        "next_checkpoint": str(row.get("next_checkpoint") or "continue_local_review"),
    }
    if normalized["decision"] not in ALLOWED_DECISIONS:
        normalized["decision"] = "keep_observing"
    return normalized


def _tier_review_row(row: dict[str, Any]) -> dict[str, Any]:
    decision = str(row.get("decision") or "")
    tier_review_decision = {
        "keep_observing": "keep_current_tier",
        "revise": "revise_before_tier_change",
        "promote": "promote_candidate_for_review",
        "park": "park",
        "kill": "kill",
        "go_live": "go_live_review",
        "do_not_go_live": "do_not_go_live",
        "block_for_safety": "block_for_safety",
    }.get(decision, "keep_current_tier")
    return {
        "strategy_group_id": row.get("strategy_group_id"),
        "tier": row.get("tier"),
        "tier_review_decision": tier_review_decision,
        "basis_decision": decision,
        "next_checkpoint": row.get("next_checkpoint"),
        "real_order_authority": False,
        "l4_scope_change_recommended": False,
    }


def _high_priority_no_action_by_group(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = _dict_rows(
        _as_dict(packet.get("broader_observation")).get("high_priority_no_action_signals")
    )
    result: dict[str, dict[str, Any]] = {}
    priority_rank = {"P0_5": 0, "P1": 1, "P2": 2}
    for row in rows:
        if str(row.get("signal_type") or "") != "no_action":
            continue
        group = str(row.get("strategy_group_id") or "unknown")
        current = result.get(group)
        if current is None or priority_rank.get(str(row.get("coverage_review_priority")), 9) < priority_rank.get(str(current.get("coverage_review_priority")), 9):
            result[group] = row
    return result


def _no_action_reason(row: dict[str, Any] | None) -> str:
    if not row:
        return ""
    summary = str(row.get("human_summary") or "").strip()
    codes = ",".join(str(item) for item in row.get("reason_codes") or [])
    if summary and codes:
        return f"no_action:{summary} codes:{codes}"
    return summary or (f"no_action_codes:{codes}" if codes else "")


def _current_tier_by_group(policy: dict[str, Any]) -> dict[str, str]:
    output: dict[str, str] = {}
    for group, data in _as_dict(policy.get("current_strategy_groups")).items():
        output[str(group)] = str(_as_dict(data).get("tier") or "unknown")
    known_new = _as_dict(_as_dict(policy.get("new_strategy_group_defaults")).get("known_new_groups"))
    for base, tier in known_new.items():
        output.setdefault(f"{base}-001", str(tier or "unknown"))
    return output


def _default_next_step(rows: list[dict[str, Any]], forbidden_effects: list[str]) -> str:
    if forbidden_effects:
        return "stop_and_repair_forbidden_source_effects"
    if any(row.get("decision") == "revise" for row in rows):
        return "execute_or_verify_top_revision_checkpoints_without_live_authority_expansion"
    if any(row.get("decision") == "promote" for row in rows):
        return "run_ledger_based_tier_review_before_policy_change"
    if any(row.get("decision") == "park" for row in rows):
        return "keep_parked_groups_out_of_p0_5_active_work"
    if rows:
        return "continue_waiting_for_market_and_refresh_decision_ledger"
    return "continue_signal_coverage_monitoring"


def _forbidden_effects(*packets: dict[str, Any]) -> list[str]:
    effects: list[str] = []
    for index, packet in enumerate(packets):
        for source_name in ("safety_invariants", "interaction"):
            source = _as_dict(packet.get(source_name))
            for key in (
                "server_files_mutated",
                "runtime_started",
                "strategy_parameters_changed",
                "tier_policy_changed",
                "shadow_candidate_created",
                "execution_intent_created",
                "final_gate_called",
                "calls_finalgate",
                "operation_layer_called",
                "calls_operation_layer",
                "order_created",
                "order_lifecycle_called",
                "exchange_write_called",
                "calls_exchange_write",
                "places_order",
                "withdrawal_or_transfer_created",
            ):
                if source.get(key) is True:
                    effects.append(f"packet_{index}.{source_name}.{key}")
            for item in source.get("source_forbidden_effects") or []:
                effects.append(f"packet_{index}.{source_name}.{item}")
    return sorted(set(effects))


def _one_row_per_group(rows: list[dict[str, Any]]) -> bool:
    groups = [str(row.get("strategy_group_id") or "unknown") for row in rows]
    return len(groups) == len(set(groups))


def _ledger_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "| StrategyGroup | Tier | Type | Decision | Next |\n| --- | --- | --- | --- | --- |\n| none | - | - | - | - |"
    output = [
        "| StrategyGroup | Tier | Type | Decision | Next |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        output.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row.get("strategy_group_id"),
                row.get("tier"),
                row.get("opportunity_type"),
                row.get("decision"),
                row.get("next_checkpoint"),
            )
        )
    return "\n".join(output)


def _tier_review_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "| StrategyGroup | Tier | Tier Review | Basis |\n| --- | --- | --- | --- |\n| none | - | - | - |"
    output = [
        "| StrategyGroup | Tier | Tier Review | Basis |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        output.append(
            "| `{}` | `{}` | `{}` | `{}` |".format(
                row.get("strategy_group_id"),
                row.get("tier"),
                row.get("tier_review_decision"),
                row.get("basis_decision"),
            )
        )
    return "\n".join(output)


def _join_reason_parts(parts: list[str]) -> str:
    return "; ".join(part for part in (p.strip() for p in parts) if part)


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
        "--opportunity-decision-loop-json",
        default=str(DEFAULT_OPPORTUNITY_DECISION_LOOP_JSON),
    )
    parser.add_argument("--signal-coverage-json", default=str(DEFAULT_SIGNAL_COVERAGE_JSON))
    parser.add_argument("--tier-policy-json", default=str(DEFAULT_TIER_POLICY_JSON))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OWNER_PROGRESS))
    args = parser.parse_args(argv)

    packet = build_strategygroup_decision_ledger(
        opportunity_decision_loop_packet=_load_json_object(
            Path(args.opportunity_decision_loop_json).expanduser()
        ),
        signal_coverage_packet=_load_json_object(
            Path(args.signal_coverage_json).expanduser()
        ),
        tier_policy=_load_json_object(Path(args.tier_policy_json).expanduser()),
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
