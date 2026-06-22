#!/usr/bin/env python3
"""Record unified review-only StrategyGroup policy confirmation.

This command consumes the Owner Decision Package and records the Owner's
confirmation of the default review-only recommendations. It schedules the next
local evidence-closure wave and projects the result into an Owner-readable
perception snapshot.

It never mutates StrategyGroup registry authority, tier policy, live profile,
FinalGate, Operation Layer, exchange gateway, or order state.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_OWNER_DECISION_PACKAGE_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-owner-decision-package.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-review-only-policy-confirmation.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-review-only-policy-confirmation.md"
)

CONFIRMED_DEFAULTS = {
    "BRF-001:owner_policy_decision": {
        "selected_option_id": "approve_promote_review",
        "confirmed_recommendation": "approve_promote_review_without_live_scope_change",
        "review_only_policy_effect": "promote_review_lane_approved_without_live_scope_change",
        "queue_id": "P05-BRF-001",
        "queue_label": "BRF squeeze / RequiredFacts / forward outcome review",
        "done_when": "BRF has a promote-review evidence packet with squeeze risk, RequiredFacts readiness, and forward outcome separated from live authority.",
    },
    "BTPC-001:owner_policy_decision": {
        "selected_option_id": "keep_l2_shadow_revise",
        "confirmed_recommendation": "keep_l2_shadow_and_revise_fact_classifier_inputs",
        "review_only_policy_effect": "keep_l2_shadow_and_continue_fact_classifier_revision",
        "queue_id": "P05-BTPC-001",
        "queue_label": "BTPC stale / fact-source / classifier attribution closure",
        "done_when": "BTPC has an attribution packet that separates stale-gate false negatives, missing fact sources, classifier disables, and false-positive risk.",
    },
    "LSR-001:owner_policy_decision": {
        "selected_option_id": "formalize_short_revival",
        "confirmed_recommendation": "formalize_short_revival_rewrite_without_live_scope_change",
        "review_only_policy_effect": "short_revival_rewrite_review_lane_approved",
        "queue_id": "P05-LSR-001",
        "queue_label": "LSR short-revival rewrite evidence closure",
        "done_when": "LSR has a short-revival packet with side conflict policy, range-context RequiredFacts, and replay evidence.",
    },
    "MI-001:owner_policy_decision": {
        "selected_option_id": "formal_candidate_review",
        "confirmed_recommendation": "open_formal_candidate_review_and_overlap_check",
        "review_only_policy_effect": "formal_candidate_review_opened_without_registry_admission",
        "queue_id": "P05-MI-001",
        "queue_label": "MI identity / overlap / concentration packet",
        "done_when": "MI has an identity packet recommending formal candidate, MPG support capability, observe asset, or park with evidence.",
    },
    "CPM-RO-001:owner_policy_decision": {
        "selected_option_id": "observe_asset",
        "confirmed_recommendation": "keep_as_observation_asset_and_run_merge_review",
        "review_only_policy_effect": "observation_asset_merge_review_opened_without_registry_admission",
        "queue_id": "P05-CPM-RO-001",
        "queue_label": "CPM-RO semantic source / merge quality packet",
        "done_when": "CPM-RO has an identity packet recommending independent review, merge target, observe asset, or park with evidence.",
    },
    "MPG-001:member_policy_decision": {
        "selected_option_id": "approve_member_role_split",
        "confirmed_recommendation": "approve_member_role_split_without_live_scope_expansion",
        "review_only_policy_effect": "member_role_split_approved_without_member_live_scope_expansion",
        "queue_id": "P05-MPG-001",
        "queue_label": "MPG member role / exit-decay / risk boundary packet",
        "done_when": "MPG has a member-level packet that separates core, support, confirmation, scorer, and parked roles without expanding live scope.",
    },
}

FORBIDDEN_EFFECTS = (
    "registry_authority_changed",
    "tier_policy_changed",
    "live_profile_changed",
    "order_sizing_changed",
    "mpg_member_live_scope_expanded",
    "l4_real_order_scope_expanded",
    "shadow_candidate_created",
    "execution_intent_created",
    "final_gate_called",
    "operation_layer_called",
    "order_created",
    "exchange_write_called",
    "real_order_authority",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--owner-decision-package-json",
        default=str(DEFAULT_OWNER_DECISION_PACKAGE_JSON),
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    packet = build_review_only_policy_confirmation(
        owner_decision_package=_load_json_object(Path(args.owner_decision_package_json))
    )

    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    output_md.write_text(_markdown(packet, output_json, output_md), encoding="utf-8")
    print(
        json.dumps(
            {"status": packet["status"], "output_json": str(output_json)},
            ensure_ascii=False,
        )
    )
    return 0


def build_review_only_policy_confirmation(
    *, owner_decision_package: dict[str, Any]
) -> dict[str, Any]:
    _validate_decision_package(owner_decision_package)

    cards = {
        str(card.get("card_id")): card
        for card in _dict_rows(owner_decision_package.get("owner_decision_cards"))
    }
    confirmed_decisions = [
        _confirmed_decision(card_id, cards[card_id])
        for card_id in CONFIRMED_DEFAULTS
    ]
    next_wave_queue = [
        _perception_queue_item(owner_decision_package),
        *[_queue_item(row) for row in confirmed_decisions],
    ]
    owner_perception_snapshot = _owner_perception_snapshot(
        owner_decision_package,
        confirmed_decisions,
        next_wave_queue,
    )

    return {
        "schema": "brc.strategygroup_review_only_policy_confirmation.v1",
        "scope": "strategy_perception_evidence_closure_next_wave",
        "status": "review_only_policy_confirmation_ready",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_package": {
            "schema": owner_decision_package.get("schema"),
            "status": owner_decision_package.get("status"),
            "decision_count": _as_dict(
                owner_decision_package.get("owner_decision_summary")
            ).get("decision_count"),
        },
        "owner_confirmation": {
            "confirmation_mode": "unified_default_review_only_policy_confirmation",
            "confirmation_text": "统一；同意",
            "confirmed_default_recommendations": True,
            "review_only": True,
            "does_not_authorize_live_execution": True,
        },
        "confirmed_decisions": confirmed_decisions,
        "next_wave_queue": next_wave_queue,
        "owner_perception_snapshot": owner_perception_snapshot,
        "completion_boundary": {
            "current_stage": "review_only_policy_confirmed_next_wave_ready",
            "next_stage": "execute_local_evidence_closure_queue",
            "owner_policy_confirmation_required_now": False,
            "runtime_owner_intervention_required": False,
            "allowed_without_more_owner_input": [
                "build_review_only_evidence_packets",
                "refresh_strategy_quality_snapshot",
                "record_decision_ledger_review_inputs",
                "prepare_future_owner_cards",
            ],
            "blocked_until_separate_owner_confirmation": [
                "promote",
                "park",
                "kill",
                "registry_admission",
                "tier_policy_change",
                "live_profile_change",
                "mpg_member_live_scope_expansion",
                "real_order_scope_expansion",
            ],
        },
        "interaction": _interaction(),
        "safety_invariants": _safety_invariants(),
    }


def _validate_decision_package(packet: dict[str, Any]) -> None:
    if packet.get("status") != "owner_decision_package_ready":
        raise ValueError("owner decision package is not ready")
    safety = _as_dict(packet.get("safety_invariants"))
    active_forbidden = [key for key in FORBIDDEN_EFFECTS if safety.get(key) is True]
    if active_forbidden:
        raise ValueError(f"owner decision package has forbidden effects: {active_forbidden}")
    cards = {
        str(card.get("card_id")): card
        for card in _dict_rows(packet.get("owner_decision_cards"))
    }
    missing = [card_id for card_id in CONFIRMED_DEFAULTS if card_id not in cards]
    if missing:
        raise ValueError(f"owner decision package missing cards: {missing}")
    for card_id, expected in CONFIRMED_DEFAULTS.items():
        card = cards[card_id]
        if card.get("decision_ready") is not True:
            raise ValueError(f"owner decision card is not ready: {card_id}")
        if card.get("default_recommendation") != expected["confirmed_recommendation"]:
            raise ValueError(f"owner decision default mismatch: {card_id}")


def _confirmed_decision(card_id: str, card: dict[str, Any]) -> dict[str, Any]:
    spec = CONFIRMED_DEFAULTS[card_id]
    return {
        "card_id": card_id,
        "strategy_group_id": card.get("strategy_group_id"),
        "decision_type": card.get("decision_type"),
        "confirmed_default_recommendation": spec["confirmed_recommendation"],
        "selected_option_id": spec["selected_option_id"],
        "review_only_policy_effect": spec["review_only_policy_effect"],
        "next_system_action": card.get("next_system_action_if_approved"),
        "next_checkpoint": card.get("next_checkpoint"),
        "queue_id": spec["queue_id"],
        "queue_label": spec["queue_label"],
        "done_when": spec["done_when"],
        "review_only": True,
        "does_not_change_registry": True,
        "does_not_change_tier_policy": True,
        "does_not_change_live_profile": True,
        "does_not_expand_real_order_scope": True,
        "forbidden_effects": list(FORBIDDEN_EFFECTS),
    }


def _perception_queue_item(packet: dict[str, Any]) -> dict[str, Any]:
    snapshot = _as_dict(packet.get("strategy_quality_snapshot"))
    return {
        "queue_id": "P05-PERCEPTION-001",
        "strategy_group_id": "OWNER-PERCEPTION",
        "work_type": "owner_perception_projection",
        "priority": "P0.5-A",
        "actionable_task": "project_strategy_quality_snapshot_into_owner_progress",
        "input_card_id": None,
        "source_status": snapshot.get("status"),
        "validation_command": (
            "python3 scripts/build_strategygroup_review_only_policy_confirmation.py"
        ),
        "completion_signal": "owner_perception_snapshot_ready",
        "done_when": (
            "Owner sees P0 waiting_for_market plus P0.5 review-only strategy "
            "progress, confirmed lanes, and no live permission change."
        ),
        "review_only": True,
        "real_order_authority": False,
    }


def _queue_item(decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "queue_id": decision["queue_id"],
        "strategy_group_id": decision["strategy_group_id"],
        "work_type": "review_only_evidence_closure",
        "priority": _priority_for(decision["strategy_group_id"]),
        "actionable_task": decision["next_system_action"],
        "input_card_id": decision["card_id"],
        "confirmed_default_recommendation": decision["confirmed_default_recommendation"],
        "review_only_policy_effect": decision["review_only_policy_effect"],
        "validation_command": (
            "python3 scripts/build_strategygroup_review_only_policy_confirmation.py"
        ),
        "completion_signal": f"{decision['queue_id'].lower().replace('-', '_')}_ready",
        "done_when": decision["done_when"],
        "review_only": True,
        "real_order_authority": False,
    }


def _owner_perception_snapshot(
    packet: dict[str, Any],
    decisions: list[dict[str, Any]],
    queue: list[dict[str, Any]],
) -> dict[str, Any]:
    source_snapshot = _as_dict(packet.get("strategy_quality_snapshot"))
    decision_by_group = {
        str(row.get("strategy_group_id")): row for row in decisions
    }
    rows = []
    for row in _dict_rows(source_snapshot.get("rows")):
        group = str(row.get("strategy_group_id"))
        decision = decision_by_group.get(group)
        rows.append(
            {
                "strategy_group_id": group,
                "owner_state": row.get("owner_state"),
                "system_found": row.get("system_found"),
                "confirmed_review_only_decision": decision is not None,
                "confirmed_effect": decision.get("review_only_policy_effect") if decision else None,
                "next_queue_id": decision.get("queue_id") if decision else None,
                "no_live_permission": True,
            }
        )
    return {
        "status": "owner_perception_snapshot_ready",
        "owner_summary": (
            "P0 remains waiting for a fresh executable signal; P0.5 review-only "
            "strategy decisions are confirmed and queued for evidence closure; "
            "live permission is unchanged."
        ),
        "p0_state": source_snapshot.get("p0_state", "waiting_for_market"),
        "p0_5_state": "review_only_policy_confirmed",
        "queue_count": len(queue),
        "confirmed_decision_count": len(decisions),
        "no_live_permission": True,
        "rows": rows,
    }


def _priority_for(group: Any) -> str:
    if group in {"BRF-001", "BTPC-001", "LSR-001"}:
        return "P0.5-B"
    if group in {"MI-001", "CPM-RO-001"}:
        return "P0.5-C"
    if group == "MPG-001":
        return "P0.5-D"
    return "P0.5"


def _interaction() -> dict[str, Any]:
    return {
        "level": "L0_local_review_only_policy_confirmation",
        "remote_interaction_count": 0,
        "mutates_remote_files": False,
        "approaches_real_order": False,
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "calls_exchange_write": False,
        "places_order": False,
    }


def _safety_invariants() -> dict[str, Any]:
    return {
        "local_review_only": True,
        "server_interaction": False,
        "server_files_mutated": False,
        "runtime_started": False,
        "strategy_parameters_changed": False,
        "tier_policy_changed": False,
        "live_profile_changed": False,
        "registry_authority_changed": False,
        "mpg_member_live_scope_expanded": False,
        "l4_real_order_scope_expanded": False,
        "shadow_candidate_created": False,
        "execution_intent_created": False,
        "final_gate_called": False,
        "operation_layer_called": False,
        "order_created": False,
        "exchange_write_called": False,
        "real_order_authority": False,
        "preview_or_replay_treated_as_live_signal": False,
    }


def _markdown(packet: dict[str, Any], output_json: Path, output_md: Path) -> str:
    lines = [
        "# StrategyGroup Review-Only Policy Confirmation",
        "",
        "## Summary",
        "",
        f"- Status: `{packet['status']}`",
        "- Owner confirmation: `unified_default_review_only_policy_confirmation`",
        f"- Confirmed decisions: `{len(packet['confirmed_decisions'])}`",
        f"- Next wave queue items: `{len(packet['next_wave_queue'])}`",
        "- Real order authority: `false`",
        "- Live permission change: `false`",
        "",
        "## Owner Perception Snapshot",
        "",
        f"- Owner summary: {packet['owner_perception_snapshot']['owner_summary']}",
        f"- P0 state: `{packet['owner_perception_snapshot']['p0_state']}`",
        f"- P0.5 state: `{packet['owner_perception_snapshot']['p0_5_state']}`",
        "",
        "| StrategyGroup | Owner state | Confirmed effect | Next queue | Live permission |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in packet["owner_perception_snapshot"]["rows"]:
        lines.append(
            "| `{}` | {} | `{}` | `{}` | `{}` |".format(
                row["strategy_group_id"],
                row.get("owner_state") or "-",
                row.get("confirmed_effect") or "-",
                row.get("next_queue_id") or "-",
                "false",
            )
        )
    lines.extend(
        [
            "",
            "## Confirmed Decisions",
            "",
            "| Card | Selected option | Confirmed recommendation | Review-only effect | Next action |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in packet["confirmed_decisions"]:
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row["card_id"],
                row["selected_option_id"],
                row["confirmed_default_recommendation"],
                row["review_only_policy_effect"],
                row["next_system_action"],
            )
        )
    lines.extend(
        [
            "",
            "## Next Wave Queue",
            "",
            "| Queue | StrategyGroup | Priority | Task | Done when |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for item in packet["next_wave_queue"]:
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | {} |".format(
                item["queue_id"],
                item["strategy_group_id"],
                item["priority"],
                item["actionable_task"],
                item["done_when"],
            )
        )
    boundary = packet["completion_boundary"]
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            f"- Current stage: `{boundary['current_stage']}`",
            f"- Next stage: `{boundary['next_stage']}`",
            f"- Owner policy confirmation required now: `{str(boundary['owner_policy_confirmation_required_now']).lower()}`",
            f"- Runtime Owner intervention required: `{str(boundary['runtime_owner_intervention_required']).lower()}`",
            "- Blocked until separate Owner confirmation: "
            + ", ".join(f"`{item}`" for item in boundary["blocked_until_separate_owner_confirmation"]),
            "",
            "## Safety",
            "",
            "| Field | Value |",
            "| --- | --- |",
        ]
    )
    for key, value in packet["safety_invariants"].items():
        lines.append(f"| `{key}` | `{str(value).lower()}` |")
    lines.extend(
        [
            "",
            "## Output",
            "",
            f"- JSON: `{output_json}`",
            f"- Markdown: `{output_md}`",
            "",
        ]
    )
    return "\n".join(lines)


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"missing JSON input: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON input: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"JSON input must be an object: {path}")
    return data


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


if __name__ == "__main__":
    raise SystemExit(main())
