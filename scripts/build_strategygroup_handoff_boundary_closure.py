#!/usr/bin/env python3
"""Build the StrategyGroup handoff-boundary closure packet.

This packet turns the VCB / LSR / BRF missing-handoff state from vague
quality-wave text into an explicit, machine-checkable boundary. It is
governance-only and cannot create live actionability.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUALITY_WAVE_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-quality-wave-current.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-handoff-boundary-closure-current.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-handoff-boundary-closure-current.md"
)

REQUIRED_EXPLICIT_MISSING_GROUPS = ["VCB-001", "LSR-001", "BRF-001"]
SAFETY_FALSE_KEYS = [
    "actionable_now",
    "real_order_authority",
    "l2_shadow_authority_created",
    "l4_scope_change_recommended",
    "calls_finalgate",
    "calls_operation_layer",
    "calls_exchange_write",
    "places_order",
    "changes_live_profile",
    "changes_order_sizing_defaults",
]


def build_handoff_boundary_closure(quality_wave: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for row in _dict_rows(quality_wave.get("rows")):
        group = str(row.get("strategy_group_id") or "")
        coverage = _as_dict(row.get("source_coverage"))
        handoff_present = coverage.get("handoff_pack") is True
        if group in REQUIRED_EXPLICIT_MISSING_GROUPS:
            boundary_state = "explicit_missing_handoff_boundary_accepted"
            next_checkpoint = "create_handoff_pack_before_l2_or_l4_review"
        elif group == "BTPC-001" and handoff_present:
            boundary_state = "handoff_present_non_executing_input"
            next_checkpoint = "continue_btpc_fact_classifier_guard"
        elif str(row.get("current_decision")) == "park":
            boundary_state = "parked_no_handoff_boundary"
            next_checkpoint = "keep_parked_until_material_new_edge_evidence"
        else:
            boundary_state = "boundary_state_recorded"
            next_checkpoint = str(row.get("next_engineering_checkpoint") or "")
        rows.append(
            {
                "strategy_group_id": group,
                "current_tier": row.get("current_tier"),
                "current_decision": row.get("current_decision"),
                "primary_gap_class": row.get("primary_gap_class"),
                "handoff_pack_present": handoff_present,
                "replay_corpus_present": coverage.get("replay_corpus") is True,
                "required_facts_mapping_present": (
                    coverage.get("required_facts_mapping") is True
                ),
                "boundary_state": boundary_state,
                "boundary_is_explicit": (
                    group not in REQUIRED_EXPLICIT_MISSING_GROUPS
                    or boundary_state == "explicit_missing_handoff_boundary_accepted"
                ),
                "system_can_continue": row.get("system_can_continue") is True,
                "trial_eligibility_may_be_reviewed_by_owner_policy": True,
                "actionable_now": False,
                "l2_shadow_authority_created": False,
                "l4_scope_change_recommended": False,
                "real_order_authority": False,
                "owner_manual_operation_required": False,
                "next_checkpoint": next_checkpoint,
            }
        )
    explicit_missing_count = sum(
        1
        for row in rows
        if row["strategy_group_id"] in REQUIRED_EXPLICIT_MISSING_GROUPS
        and row["boundary_state"] == "explicit_missing_handoff_boundary_accepted"
    )
    errors = validate_packet(
        {
            "schema": "brc.strategygroup_handoff_boundary_closure.v1",
            "status": "handoff_boundary_closure_ready",
            "rows": rows,
            "safety_invariants": {key: False for key in SAFETY_FALSE_KEYS},
        }
    )
    status = "handoff_boundary_closure_ready" if not errors else "handoff_boundary_closure_failed"
    return {
        "schema": "brc.strategygroup_handoff_boundary_closure.v1",
        "scope": "strategygroup_handoff_boundary_closure",
        "status": status,
        "source_status": {"quality_wave": quality_wave.get("status")},
        "interaction": {
            "level": "L0_local_handoff_boundary_closure",
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "counts": {
            "row_count": len(rows),
            "explicit_missing_boundary_count": explicit_missing_count,
            "required_explicit_missing_boundary_count": len(
                REQUIRED_EXPLICIT_MISSING_GROUPS
            ),
        },
        "rows": rows,
        "decision": {
            "all_required_missing_boundaries_explicit": (
                explicit_missing_count == len(REQUIRED_EXPLICIT_MISSING_GROUPS)
            ),
            "vcb_lsr_brf_can_continue_observe_only": True,
            "promote_or_live_authority_created": False,
            "default_next_step": "use_explicit_boundaries_before_tier_or_handoff_review",
        },
        "safety_invariants": {key: False for key in SAFETY_FALSE_KEYS},
        "validation_errors": errors,
    }


def validate_packet(packet: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if packet.get("schema") != "brc.strategygroup_handoff_boundary_closure.v1":
        errors.append("schema_mismatch")
    rows = _dict_rows(packet.get("rows"))
    rows_by_group = {str(row.get("strategy_group_id") or ""): row for row in rows}
    for group in REQUIRED_EXPLICIT_MISSING_GROUPS:
        row = rows_by_group.get(group)
        if not row:
            errors.append(f"{group}.missing_boundary_row")
            continue
        if row.get("boundary_state") != "explicit_missing_handoff_boundary_accepted":
            errors.append(f"{group}.missing_handoff_boundary_not_explicit")
        if row.get("handoff_pack_present") is True:
            errors.append(f"{group}.handoff_pack_unexpectedly_present")
        if row.get("actionable_now") is True:
            errors.append(f"{group}.actionable_now_true")
        for key in (
            "l2_shadow_authority_created",
            "l4_scope_change_recommended",
            "real_order_authority",
            "owner_manual_operation_required",
        ):
            if row.get(key) is True:
                errors.append(f"{group}.{key}_true")
    safety = _as_dict(packet.get("safety_invariants"))
    for key in SAFETY_FALSE_KEYS:
        if safety.get(key) is not False:
            errors.append(f"safety_invariant_not_false:{key}")
    return errors


def build_markdown(packet: dict[str, Any]) -> str:
    return "\n".join(
        [
            "---",
            "title: STRATEGYGROUP_HANDOFF_BOUNDARY_CLOSURE_CURRENT",
            "status: CURRENT",
            "authority: docs/current/strategy-group-handoffs/strategygroup-handoff-boundary-closure-current.json",
            "last_verified: 2026-06-20",
            "---",
            "",
            "# StrategyGroup Handoff Boundary Closure Current",
            "",
            "## Summary",
            "",
            f"- Status: `{packet.get('status')}`",
            "- Scope: VCB / LSR / BRF missing handoff boundaries are explicit.",
            "- Actionability: `false`",
            "- Real order authority: `false`",
            "",
            "## Rows",
            "",
            _rows_table(_dict_rows(packet.get("rows"))),
            "",
            "## Boundary",
            "",
            "This packet is local governance evidence only. It does not promote a StrategyGroup, satisfy live RequiredFacts, call FinalGate, call Operation Layer, or authorize a real order.",
        ]
    ).rstrip() + "\n"


def _rows_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| StrategyGroup | Tier | Decision | Boundary | Next |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row.get("strategy_group_id"),
                row.get("current_tier"),
                row.get("current_decision"),
                row.get("boundary_state"),
                row.get("next_checkpoint"),
            )
        )
    return "\n".join(lines)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return payload


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quality-wave-json", default=str(DEFAULT_QUALITY_WAVE_JSON))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if args.check:
        packet = _load_json(Path(args.output_json).expanduser())
        errors = validate_packet(packet)
        result = {
            "status": "passed" if not errors else "failed",
            "error_count": len(errors),
            "errors": errors,
            "row_count": len(_dict_rows(packet.get("rows"))),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if not errors else 2

    packet = build_handoff_boundary_closure(
        _load_json(Path(args.quality_wave_json).expanduser())
    )
    payload = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True)
    _write_text(Path(args.output_json).expanduser(), payload + "\n")
    _write_text(Path(args.output_owner_progress).expanduser(), build_markdown(packet))
    print(payload)
    return 0 if packet["status"] == "handoff_boundary_closure_ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
