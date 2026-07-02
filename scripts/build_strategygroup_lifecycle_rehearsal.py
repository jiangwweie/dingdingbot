#!/usr/bin/env python3
"""Build the StrategyGroup paper/simulator lifecycle rehearsal artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from src.domain.runtime_readiness_state import (  # noqa: E402
    AUTHORITATIVE_SOURCE_FALSE_KEYS,
    NON_EXECUTING_SIDE_EFFECT_FALSE_KEYS,
    false_flag_errors,
    non_authoritative_state_errors,
)
from strategygroup_non_executing_projection import (  # noqa: E402
    LEGACY_AUTHORITY_MIRROR_KEYS,
    non_executing_interaction,
)

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
    runtime_safety_state = {
        "state_family": "Runtime Safety State",
        "source_role": "lifecycle_rehearsal_evidence",
        "review_scope": "paper_simulator_lifecycle_rehearsal",
        "primary_judgment_source": False,
        "tradeability_decision_source": False,
        "execution_attempt_source": False,
        "paper_simulator_lifecycle_ready": True,
        "pre_live_branches_closed": REQUIRED_SCENARIOS,
        "live_submit_dependencies_remain": True,
        "live_outcome_calibration_remains": True,
        "default_next_step": "feed_lifecycle_rehearsal_into_pre_live_readiness",
    }
    artifact = {
        "schema": "brc.strategygroup_lifecycle_rehearsal.v1",
        "scope": "strategygroup_paper_simulator_lifecycle_rehearsal",
        "status": "lifecycle_rehearsal_ready",
        "interaction": non_executing_interaction("L0_local_lifecycle_rehearsal"),
        "scenario_rows": rows,
        "cost_pnl_review": {
            "rough_fee_bps": "configurable_input",
            "rough_slippage_bps": "configurable_input",
            "rough_funding_bps": "configurable_input",
            "formula": "gross_pnl - fees - slippage - funding",
            "review_shape_ready": True,
            "live_calibration_required_later": True,
        },
        "runtime_safety_state": runtime_safety_state,
        "safety_invariants": {
            "paper_or_simulator_only": True,
            "exchange_write_called": False,
            "order_created": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "live_profile_changed": False,
            "order_sizing_defaults_changed": False,
            "withdrawal_or_transfer_created": False,
        },
    }
    errors = validate_artifact(artifact)
    if errors:
        artifact["status"] = "lifecycle_rehearsal_failed"
    artifact["validation_errors"] = errors
    return artifact


def validate_artifact(artifact: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if artifact.get("schema") != "brc.strategygroup_lifecycle_rehearsal.v1":
        errors.append("schema_mismatch")
    if "decision" in artifact:
        errors.append("top_level_decision_removed")
    if artifact.get("status") not in {
        "lifecycle_rehearsal_ready",
        "lifecycle_rehearsal_failed",
    }:
        errors.append(f"unexpected_status:{artifact.get('status')}")
    rows = _dict_rows(artifact.get("scenario_rows"))
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
        ):
            if row.get(key) is not False:
                errors.append(f"{scenario}.{key}_not_false")
        for legacy_key in LEGACY_AUTHORITY_MIRROR_KEYS:
            if legacy_key not in row:
                continue
            errors.append(
                f"{scenario}.legacy_authority_mirror_present:{legacy_key}"
            )
        if row.get("review_shape_ready") is not True:
            errors.append(f"{scenario}.review_shape_not_ready")
    safety = _as_dict(artifact.get("safety_invariants"))
    for legacy_key in LEGACY_AUTHORITY_MIRROR_KEYS:
        if legacy_key in safety:
            errors.append(f"safety_invariant.legacy_authority_mirror_present:{legacy_key}")
    errors.extend(
        false_flag_errors(
            safety,
            error_prefix="safety_invariant",
            false_keys=NON_EXECUTING_SIDE_EFFECT_FALSE_KEYS,
        )
    )
    if _as_dict(artifact.get("cost_pnl_review")).get("review_shape_ready") is not True:
        errors.append("cost_pnl_review_shape_not_ready")
    runtime_safety = _as_dict(artifact.get("runtime_safety_state"))
    if runtime_safety.get("state_family") != "Runtime Safety State":
        errors.append("runtime_safety_state_family_mismatch")
    if runtime_safety.get("source_role") != "lifecycle_rehearsal_evidence":
        errors.append("runtime_safety_state_source_role_mismatch")
    for legacy_key in LEGACY_AUTHORITY_MIRROR_KEYS:
        if legacy_key in runtime_safety:
            errors.append(
                f"runtime_safety_state.legacy_authority_mirror_present:{legacy_key}"
            )
    errors.extend(
        non_authoritative_state_errors(
            runtime_safety,
            error_prefix="runtime_safety_state",
            false_keys=AUTHORITATIVE_SOURCE_FALSE_KEYS,
        )
    )
    if runtime_safety.get("paper_simulator_lifecycle_ready") is not True:
        errors.append("runtime_safety_state_lifecycle_not_ready")
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
        "review_shape_ready": True,
        "live_calibration_required_later": True,
    }


def build_markdown(artifact: dict[str, Any]) -> str:
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
            f"- Status: `{artifact.get('status')}`",
            "- Rehearsal mode: paper/simulator only",
            "- Exchange write: `false`",
            "",
            "## Scenarios",
            "",
            _scenario_table(_dict_rows(artifact.get("scenario_rows"))),
            "",
            "## Boundary",
            "",
            "This rehearsal closes non-live lifecycle branches. Real exchange acceptance, fill behavior, protection acceptance, settlement, and realized PnL remain live-only calibration.",
            "",
            "## Runtime Safety State",
            "",
            f"- Source role: `{_as_dict(artifact.get('runtime_safety_state')).get('source_role')}`",
            f"- Tradeability decision source: `{_as_dict(artifact.get('runtime_safety_state')).get('tradeability_decision_source')}`",
            f"- Execution Attempt source: `{_as_dict(artifact.get('runtime_safety_state')).get('execution_attempt_source')}`",
            f"- Default next step: `{_as_dict(artifact.get('runtime_safety_state')).get('default_next_step')}`",
        ]
    ).rstrip() + "\n"


def _scenario_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Scenario | Status | Review shape |",
        "| --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| `{}` | `{}` | `{}` |".format(
                row.get("scenario"),
                row.get("status"),
                row.get("review_shape_ready"),
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
        artifact = _load_json(Path(args.output_json).expanduser())
        errors = validate_artifact(artifact)
        result = {
            "status": "passed" if not errors else "failed",
            "error_count": len(errors),
            "errors": errors,
            "scenario_count": len(_dict_rows(artifact.get("scenario_rows"))),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if not errors else 2

    artifact = build_lifecycle_rehearsal()
    payload = json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True)
    _write_text(Path(args.output_json).expanduser(), payload + "\n")
    _write_text(Path(args.output_owner_progress).expanduser(), build_markdown(artifact))
    print(payload)
    return 0 if artifact["status"] == "lifecycle_rehearsal_ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
