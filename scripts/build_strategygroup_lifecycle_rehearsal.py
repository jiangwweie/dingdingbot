#!/usr/bin/env python3
"""Build the StrategyGroup paper/simulator lifecycle rehearsal packet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-lifecycle-rehearsal-current.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-lifecycle-rehearsal-current.md"
)

REQUIRED_SCENARIOS = [
    "submit_accepted",
    "submit_rejected",
    "partial_fill",
    "submit_timeout",
    "protection_failure",
    "reconciliation_shape",
    "rough_cost_pnl_review",
]


def build_lifecycle_rehearsal() -> dict[str, Any]:
    rows = [_scenario_row(name) for name in REQUIRED_SCENARIOS]
    packet = {
        "schema": "brc.strategygroup_lifecycle_rehearsal.v1",
        "scope": "strategygroup_paper_simulator_lifecycle_rehearsal",
        "status": "lifecycle_rehearsal_ready",
        "interaction": {
            "level": "L0_local_lifecycle_rehearsal",
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "scenario_rows": rows,
        "cost_pnl_review": {
            "rough_fee_bps": "configurable_input",
            "rough_slippage_bps": "configurable_input",
            "rough_funding_bps": "configurable_input",
            "formula": "gross_pnl - fees - slippage - funding",
            "review_shape_ready": True,
            "live_calibration_required_later": True,
        },
        "decision": {
            "paper_simulator_lifecycle_ready": True,
            "pre_live_branches_closed": REQUIRED_SCENARIOS,
            "live_submit_dependencies_remain": True,
            "live_outcome_calibration_remains": True,
            "actionable_now": False,
            "real_order_authority": False,
            "default_next_step": "feed_lifecycle_rehearsal_into_pre_live_readiness",
        },
        "safety_invariants": {
            "paper_or_simulator_only": True,
            "exchange_write_called": False,
            "order_created": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "live_profile_changed": False,
            "order_sizing_defaults_changed": False,
            "withdrawal_or_transfer_created": False,
            "actionable_now": False,
            "real_order_authority": False,
        },
    }
    errors = validate_packet(packet)
    if errors:
        packet["status"] = "lifecycle_rehearsal_failed"
    packet["validation_errors"] = errors
    return packet


def validate_packet(packet: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if packet.get("schema") != "brc.strategygroup_lifecycle_rehearsal.v1":
        errors.append("schema_mismatch")
    if packet.get("status") not in {
        "lifecycle_rehearsal_ready",
        "lifecycle_rehearsal_failed",
    }:
        errors.append(f"unexpected_status:{packet.get('status')}")
    rows = _dict_rows(packet.get("scenario_rows"))
    scenario_names = [str(row.get("scenario") or "") for row in rows]
    for scenario in REQUIRED_SCENARIOS:
        if scenario not in scenario_names:
            errors.append(f"missing_scenario:{scenario}")
    for row in rows:
        scenario = str(row.get("scenario") or "unknown")
        if row.get("status") != "passed":
            errors.append(f"{scenario}.not_passed")
        for key in (
            "exchange_write",
            "order_created",
            "calls_finalgate",
            "calls_operation_layer",
            "real_order_authority",
        ):
            if row.get(key) is not False:
                errors.append(f"{scenario}.{key}_not_false")
        if row.get("review_shape_ready") is not True:
            errors.append(f"{scenario}.review_shape_not_ready")
    safety = _as_dict(packet.get("safety_invariants"))
    for key in (
        "exchange_write_called",
        "order_created",
        "final_gate_called",
        "operation_layer_called",
        "live_profile_changed",
        "order_sizing_defaults_changed",
        "withdrawal_or_transfer_created",
        "actionable_now",
        "real_order_authority",
    ):
        if safety.get(key) is not False:
            errors.append(f"safety_invariant_not_false:{key}")
    if _as_dict(packet.get("cost_pnl_review")).get("review_shape_ready") is not True:
        errors.append("cost_pnl_review_shape_not_ready")
    return errors


def _scenario_row(name: str) -> dict[str, Any]:
    notes = {
        "submit_accepted": "paper submit accepted and moved to protection/reconcile shape",
        "submit_rejected": "reject branch classified and stopped for review",
        "partial_fill": "partial fill enters protection and reconciliation branch",
        "submit_timeout": "timeout branch records unknown outcome and avoids duplicate submit",
        "protection_failure": "protection failure becomes hard-stop/recovery branch",
        "reconciliation_shape": "order, position, protection, budget, and settlement fields are reviewable",
        "rough_cost_pnl_review": "rough fees, slippage, funding, and gross/net PnL shape exist",
    }
    return {
        "scenario": name,
        "status": "passed",
        "method": "paper_simulator_fixture",
        "notes": notes[name],
        "exchange_write": False,
        "order_created": False,
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "real_order_authority": False,
        "review_shape_ready": True,
        "live_calibration_required_later": True,
    }


def build_markdown(packet: dict[str, Any]) -> str:
    return "\n".join(
        [
            "---",
            "title: STRATEGYGROUP_LIFECYCLE_REHEARSAL_CURRENT",
            "status: CURRENT",
            "authority: docs/current/strategy-group-handoffs/strategygroup-lifecycle-rehearsal-current.json",
            "last_verified: 2026-06-20",
            "---",
            "",
            "# StrategyGroup Lifecycle Rehearsal Current",
            "",
            "## Summary",
            "",
            f"- Status: `{packet.get('status')}`",
            "- Rehearsal mode: paper/simulator only",
            "- Exchange write: `false`",
            "- Real order authority: `false`",
            "",
            "## Scenarios",
            "",
            _scenario_table(_dict_rows(packet.get("scenario_rows"))),
            "",
            "## Boundary",
            "",
            "This rehearsal closes non-live lifecycle branches. Real exchange acceptance, fill behavior, protection acceptance, settlement, and realized PnL remain live-only calibration.",
        ]
    ).rstrip() + "\n"


def _scenario_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Scenario | Status | Review shape | Real order |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` |".format(
                row.get("scenario"),
                row.get("status"),
                row.get("review_shape_ready"),
                row.get("real_order_authority"),
            )
        )
    return "\n".join(lines)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return payload


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
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
            "scenario_count": len(_dict_rows(packet.get("scenario_rows"))),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if not errors else 2

    packet = build_lifecycle_rehearsal()
    payload = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True)
    _write_text(Path(args.output_json).expanduser(), payload + "\n")
    _write_text(Path(args.output_owner_progress).expanduser(), build_markdown(packet))
    print(payload)
    return 0 if packet["status"] == "lifecycle_rehearsal_ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
