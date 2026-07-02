#!/usr/bin/env python3
"""Record unified review-only StrategyGroup policy confirmation.

This command consumes the Owner Policy Package and records the Owner's
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
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from strategygroup_non_executing_projection import (  # noqa: E402
    review_only_forbidden_effects,
    review_only_interaction,
    review_only_legacy_authority_mirror_true_keys,
    review_only_safety_invariants,
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
    "BRF-001:owner_policy_choice": {
        "selected_option_id": "approve_promote_review",
        "confirmed_recommendation": "approve_promote_review_without_live_scope_change",
        "review_only_policy_effect": "promote_review_lane_approved_without_live_scope_change",
        "queue_id": "signal-observation-brf-001",
        "queue_label": "BRF squeeze / RequiredFacts / forward outcome review",
        "done_when": "BRF has a promote-review evidence artifact with squeeze risk, RequiredFacts readiness, and forward outcome separated from live authority.",
    },
    "BTPC-001:owner_policy_choice": {
        "selected_option_id": "keep_l2_shadow_revise",
        "confirmed_recommendation": "keep_l2_shadow_and_revise_fact_classifier_inputs",
        "review_only_policy_effect": "keep_l2_shadow_and_continue_fact_classifier_revision",
        "queue_id": "signal-observation-btpc-001",
        "queue_label": "BTPC stale / fact-source / classifier attribution closure",
        "done_when": "BTPC has an attribution artifact that separates stale-gate false negatives, missing fact sources, classifier disables, and false-positive risk.",
    },
    "LSR-001:owner_policy_choice": {
        "selected_option_id": "formalize_short_revival",
        "confirmed_recommendation": "formalize_short_revival_rewrite_without_live_scope_change",
        "review_only_policy_effect": "short_revival_rewrite_review_lane_approved",
        "queue_id": "signal-observation-lsr-001",
        "queue_label": "LSR short-revival rewrite evidence closure",
        "done_when": "LSR has a short-revival artifact with side conflict policy, range-context RequiredFacts, and replay evidence.",
    },
    "MI-001:owner_policy_choice": {
        "selected_option_id": "formal_candidate_review",
        "confirmed_recommendation": "open_formal_candidate_review_and_overlap_check",
        "review_only_policy_effect": "formal_candidate_review_opened_without_registry_admission",
        "queue_id": "signal-observation-mi-001",
        "queue_label": "MI identity / overlap / concentration review",
        "done_when": "MI has an identity review artifact recommending formal candidate, MPG support capability, observe asset, or park with evidence.",
    },
    "CPM-RO-001:owner_policy_choice": {
        "selected_option_id": "observe_asset",
        "confirmed_recommendation": "keep_as_observation_asset_and_run_merge_review",
        "review_only_policy_effect": "observation_asset_merge_review_opened_without_registry_admission",
        "queue_id": "signal-observation-cpm-ro-001",
        "queue_label": "CPM-RO semantic source / merge quality review",
        "done_when": "CPM-RO has an identity review artifact recommending independent review, merge target, observe asset, or park with evidence.",
    },
    "MPG-001:member_policy_decision": {
        "selected_option_id": "approve_member_role_split",
        "confirmed_recommendation": "approve_member_role_split_without_live_scope_expansion",
        "review_only_policy_effect": "member_role_split_approved_without_member_live_scope_expansion",
        "queue_id": "signal-observation-mpg-001",
        "queue_label": "MPG member role / exit-decay / risk boundary review",
        "done_when": "MPG has a member-level review artifact that separates core, support, confirmation, scorer, and parked roles without expanding live scope.",
    },
}

FORBIDDEN_EFFECTS = review_only_forbidden_effects()
LEGACY_AUTHORITY_MIRROR_TRUE_KEYS = review_only_legacy_authority_mirror_true_keys()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-policy-package-json")
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    policy_confirmation = build_review_only_policy_confirmation(
        owner_policy_package=_load_json_object(Path(args.owner_policy_package_json))
        if args.owner_policy_package_json
        else {}
    )

    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(policy_confirmation, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    output_md.write_text(
        _markdown(policy_confirmation, output_json, output_md), encoding="utf-8"
    )
    print(
        json.dumps(
            {"status": policy_confirmation["status"], "output_json": str(output_json)},
            ensure_ascii=False,
        )
    )
    return 0


def build_review_only_policy_confirmation(
    *, owner_policy_package: dict[str, Any]
) -> dict[str, Any]:
    _validate_policy_package(owner_policy_package)

    policy_items = {
        str(policy_item.get("policy_item_id")): policy_item
        for policy_item in _policy_items(owner_policy_package)
    }
    confirmed_policy_items = [
        _confirmed_policy_item(policy_item_id, policy_items[policy_item_id])
        for policy_item_id in CONFIRMED_DEFAULTS
    ]
    next_wave_queue = [
        _perception_queue_item(owner_policy_package),
        *[_queue_item(row) for row in confirmed_policy_items],
    ]
    owner_perception_snapshot = _owner_perception_snapshot(
        owner_policy_package,
        confirmed_policy_items,
        next_wave_queue,
    )

    return {
        "schema": "brc.strategygroup_review_only_policy_confirmation.v1",
        "scope": "strategy_perception_evidence_closure_next_wave",
        "status": "review_only_policy_confirmation_ready",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_package": {
            "source_role": "owner_policy_projection_source",
            "source_status": "owner_policy_source_ready",
            "owner_policy_item_count": _policy_summary(owner_policy_package).get(
                "owner_policy_item_count"
            ),
        },
        "owner_confirmation": {
            "confirmation_mode": "unified_default_review_only_policy_confirmation",
            "confirmation_text": "统一；同意",
            "confirmed_default_recommendations": True,
            "review_only": True,
            "does_not_authorize_live_execution": True,
        },
        "confirmed_policy_items": confirmed_policy_items,
        "next_wave_queue": next_wave_queue,
        "owner_perception_snapshot": owner_perception_snapshot,
        "completion_boundary": {
            "current_stage": "review_only_policy_confirmed_next_wave_ready",
            "next_stage": "execute_local_evidence_closure_queue",
            "owner_policy_confirmation_required_now": False,
            "runtime_owner_intervention_required": False,
            "allowed_without_more_owner_input": [
                "build_review_only_evidence_artifacts",
                "refresh_strategy_quality_snapshot",
                "record_strategy_asset_state_review_inputs",
                "prepare_future_owner_policy_items",
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


def _validate_policy_package(policy_package: dict[str, Any]) -> None:
    if policy_package.get("status") != "owner_policy_package_ready":
        raise ValueError("owner policy package is not ready")
    safety = _as_dict(policy_package.get("safety_invariants"))
    active_forbidden = [key for key in FORBIDDEN_EFFECTS if safety.get(key) is True]
    if active_forbidden:
        raise ValueError(f"owner policy package has forbidden effects: {active_forbidden}")
    legacy_mirrors = [
        key
        for key in LEGACY_AUTHORITY_MIRROR_TRUE_KEYS
        if safety.get(key) is True
    ]
    if legacy_mirrors:
        raise ValueError(
            f"owner policy package has legacy authority mirrors: {legacy_mirrors}"
        )
    policy_items = {
        str(policy_item.get("policy_item_id")): policy_item
        for policy_item in _policy_items(policy_package)
    }
    missing = [policy_item_id for policy_item_id in CONFIRMED_DEFAULTS if policy_item_id not in policy_items]
    if missing:
        raise ValueError(f"owner policy package missing policy_items: {missing}")
    for policy_item_id, expected in CONFIRMED_DEFAULTS.items():
        policy_item = policy_items[policy_item_id]
        if _policy_ready(policy_item) is not True:
            raise ValueError(f"owner policy policy_item is not ready: {policy_item_id}")
        if policy_item.get("default_recommendation") != expected["confirmed_recommendation"]:
            raise ValueError(f"owner policy default mismatch: {policy_item_id}")


def _confirmed_policy_item(policy_item_id: str, policy_item: dict[str, Any]) -> dict[str, Any]:
    spec = CONFIRMED_DEFAULTS[policy_item_id]
    return {
        "policy_item_id": policy_item_id,
        "strategy_group_id": policy_item.get("strategy_group_id"),
        "owner_policy_type": policy_item.get("owner_policy_type") or policy_item.get("decision_type"),
        "confirmed_default_recommendation": spec["confirmed_recommendation"],
        "selected_option_id": spec["selected_option_id"],
        "review_only_policy_effect": spec["review_only_policy_effect"],
        "strategy_review_checkpoint": policy_item.get("strategy_review_checkpoint_if_approved"),
        "next_checkpoint": policy_item.get("next_checkpoint"),
        "queue_id": spec["queue_id"],
        "queue_label": spec["queue_label"],
        "done_when": spec["done_when"],
        "review_only": True,
        "does_not_change_registry": True,
        "does_not_change_tier_policy": True,
        "does_not_change_live_profile": True,
        "does_not_expand_real_order_scope": True,
    }


def _perception_queue_item(policy_package: dict[str, Any]) -> dict[str, Any]:
    snapshot = _as_dict(policy_package.get("strategy_quality_snapshot"))
    return {
        "queue_id": "signal-observation-perception-001",
        "strategy_group_id": "OWNER-PERCEPTION",
        "work_type": "owner_perception_projection",
        "priority": "signal-observation-grade-A",
        "actionable_task": "project_strategy_quality_snapshot_into_owner_progress",
        "input_policy_item_id": None,
        "source_status": snapshot.get("status"),
        "validation_command": (
            "python3 scripts/build_strategygroup_review_only_policy_confirmation.py"
        ),
        "completion_signal": "owner_perception_snapshot_ready",
        "done_when": (
            "Owner sees P0 waiting_for_market plus Signal Observation "
            "review-only strategy progress, confirmed lanes, and no live "
            "permission change."
        ),
        "review_only": True,
    }


def _queue_item(decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "queue_id": decision["queue_id"],
        "strategy_group_id": decision["strategy_group_id"],
        "work_type": "review_only_evidence_closure",
        "priority": _priority_for(decision["strategy_group_id"]),
        "actionable_task": decision["strategy_review_checkpoint"],
        "input_policy_item_id": decision["policy_item_id"],
        "confirmed_default_recommendation": decision["confirmed_default_recommendation"],
        "review_only_policy_effect": decision["review_only_policy_effect"],
        "validation_command": (
            "python3 scripts/build_strategygroup_review_only_policy_confirmation.py"
        ),
        "completion_signal": f"{decision['queue_id'].lower().replace('-', '_')}_ready",
        "done_when": decision["done_when"],
        "review_only": True,
    }


def _owner_perception_snapshot(
    policy_package: dict[str, Any],
    confirmed_policy_items: list[dict[str, Any]],
    queue: list[dict[str, Any]],
) -> dict[str, Any]:
    source_snapshot = _as_dict(policy_package.get("strategy_quality_snapshot"))
    policy_item_by_group = {
        str(row.get("strategy_group_id")): row for row in confirmed_policy_items
    }
    rows = []
    for row in _dict_rows(source_snapshot.get("rows")):
        group = str(row.get("strategy_group_id"))
        policy_item = policy_item_by_group.get(group)
        rows.append(
            {
                "strategy_group_id": group,
                "owner_state": row.get("owner_state"),
                "system_found": row.get("system_found"),
                "confirmed_review_only_policy": policy_item is not None,
                "confirmed_effect": policy_item.get("review_only_policy_effect") if policy_item else None,
                "next_queue_id": policy_item.get("queue_id") if policy_item else None,
                "no_live_permission": True,
            }
        )
    return {
        "status": "owner_perception_snapshot_ready",
        "owner_summary": (
            "P0 remains waiting for a fresh executable signal; Signal "
            "Observation review-only strategy policies are confirmed and "
            "queued for evidence closure; live permission is unchanged."
        ),
        "p0_state": source_snapshot.get("p0_state", "waiting_for_market"),
        "signal_observation_review_state": "review_only_policy_confirmed",
        "queue_count": len(queue),
        "confirmed_policy_count": len(confirmed_policy_items),
        "no_live_permission": True,
        "rows": rows,
    }


def _priority_for(group: Any) -> str:
    if group in {"BRF-001", "BTPC-001", "LSR-001"}:
        return "signal-observation-grade-B"
    if group in {"MI-001", "CPM-RO-001"}:
        return "signal-observation-grade-C"
    if group == "MPG-001":
        return "signal-observation-grade-D"
    return "signal-observation-grade"


def _interaction() -> dict[str, Any]:
    return review_only_interaction(
        "L0_local_review_only_policy_confirmation",
        mutation_key="mutates_remote_files",
    )


def _safety_invariants() -> dict[str, Any]:
    return review_only_safety_invariants(
        include_runtime_started=True,
        include_authority_mirrors=False,
    )


def _markdown(policy_confirmation: dict[str, Any], output_json: Path, output_md: Path) -> str:
    lines = [
        "# StrategyGroup Review-Only Policy Confirmation",
        "",
        "## Summary",
        "",
        f"- Status: `{policy_confirmation['status']}`",
        "- Owner confirmation: `unified_default_review_only_policy_confirmation`",
        f"- Confirmed policy items: `{len(policy_confirmation['confirmed_policy_items'])}`",
        f"- Next wave queue items: `{len(policy_confirmation['next_wave_queue'])}`",
        "- Live permission change: `false`",
        "",
        "## Owner Perception Snapshot",
        "",
        f"- Owner summary: {policy_confirmation['owner_perception_snapshot']['owner_summary']}",
        f"- P0 state: `{policy_confirmation['owner_perception_snapshot']['p0_state']}`",
        "- Signal Observation review state: "
        f"`{policy_confirmation['owner_perception_snapshot']['signal_observation_review_state']}`",
        "",
        "| StrategyGroup | Owner state | Confirmed effect | Next queue | Live permission |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in policy_confirmation["owner_perception_snapshot"]["rows"]:
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
            "## Confirmed Policy Items",
            "",
            "| Policy item | Selected option | Confirmed recommendation | Review-only effect | Next action |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in policy_confirmation["confirmed_policy_items"]:
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row["policy_item_id"],
                row["selected_option_id"],
                row["confirmed_default_recommendation"],
                row["review_only_policy_effect"],
                row["strategy_review_checkpoint"],
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
    for item in policy_confirmation["next_wave_queue"]:
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | {} |".format(
                item["queue_id"],
                item["strategy_group_id"],
                item["priority"],
                item["actionable_task"],
                item["done_when"],
            )
        )
    boundary = policy_confirmation["completion_boundary"]
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
    for key, value in policy_confirmation["safety_invariants"].items():
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


def _policy_items(policy_package: dict[str, Any]) -> list[dict[str, Any]]:
    return _dict_rows(policy_package.get("owner_policy_items"))


def _policy_summary(policy_package: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(policy_package.get("owner_policy_summary"))


def _policy_ready(policy_item: dict[str, Any]) -> bool:
    if "owner_policy_ready" in policy_item:
        return policy_item.get("owner_policy_ready") is True
    return policy_item.get("decision_ready") is True


if __name__ == "__main__":
    raise SystemExit(main())
