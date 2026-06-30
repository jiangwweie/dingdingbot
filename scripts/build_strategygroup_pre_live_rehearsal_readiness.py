#!/usr/bin/env python3
"""Build the StrategyGroup pre-live rehearsal readiness artifact."""

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

DEFAULT_QUALITY_WAVE_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-quality-wave-current.json"
)
DEFAULT_HANDOFF_BOUNDARY_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-handoff-boundary-closure-current.json"
)
DEFAULT_BTPC_GUARD_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-btpc-fact-classifier-guard-current.json"
)
DEFAULT_LIFECYCLE_REHEARSAL_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-lifecycle-rehearsal-current.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-pre-live-rehearsal-readiness-current.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-pre-live-rehearsal-readiness-current.md"
)

EXPECTED_INPUT_STATUSES = {
    "quality_wave": "quality_wave_ready",
    "handoff_boundary_closure": "handoff_boundary_closure_ready",
    "btpc_fact_classifier_guard": "btpc_fact_classifier_guard_ready",
    "lifecycle_rehearsal": "lifecycle_rehearsal_ready",
}

def build_pre_live_rehearsal_readiness(
    *,
    quality_wave: dict[str, Any],
    handoff_boundary: dict[str, Any],
    btpc_guard: dict[str, Any],
    lifecycle_rehearsal: dict[str, Any],
) -> dict[str, Any]:
    inputs = {
        "quality_wave": quality_wave,
        "handoff_boundary_closure": handoff_boundary,
        "btpc_fact_classifier_guard": btpc_guard,
        "lifecycle_rehearsal": lifecycle_rehearsal,
    }
    input_rows = [
        {
            "input": name,
            "status": artifact.get("status"),
            "expected_status": EXPECTED_INPUT_STATUSES[name],
            "ready": artifact.get("status") == EXPECTED_INPUT_STATUSES[name],
        }
        for name, artifact in inputs.items()
    ]
    errors = _validate_inputs(inputs)
    status = "pre_live_rehearsal_ready" if not errors else "pre_live_rehearsal_not_ready"
    runtime_readiness_state = {
        "state_family": "Runtime Readiness State",
        "source_role": "pre_live_rehearsal_readiness_evidence",
        "readiness_scope": "pre_live_rehearsal",
        "primary_judgment_source": False,
        "tradeability_decision_source": False,
        "execution_attempt_source": False,
        "pre_live_rehearsal_ready": not errors,
        "live_submit_ready": False,
        "live_outcome_calibrated": False,
        "deploy_worthy_local_checkpoint": not errors,
        "default_next_step": (
            "stage_worthy_local_checkpoint_ready_for_owner_deploy_decision"
            if not errors
            else "repair_pre_live_rehearsal_inputs"
        ),
    }
    return {
        "schema": "brc.strategygroup_pre_live_rehearsal_readiness.v1",
        "scope": "strategygroup_pre_live_rehearsal_readiness",
        "status": status,
        "interaction": non_executing_interaction(
            "L0_local_pre_live_rehearsal_readiness"
        ),
        "input_rows": input_rows,
        "strategygroup_decision_impact": _strategygroup_decision_impact(quality_wave),
        "closed_engineering_problem": (
            "Quality Wave governance is now connected to monitor sequence, explicit "
            "handoff boundaries, BTPC revise guards, lifecycle rehearsal, and one "
            "pre-live readiness checkpoint."
        ),
        "capability_unlocked": (
            "Standard local sequence can regenerate pre_live_rehearsal_ready without "
            "claiming live submit authority."
        ),
        "next_engineering_bottleneck": (
            "live_submit dependencies: fresh selected signal, action-time live "
            "RequiredFacts, candidate/auth evidence, FinalGate, Operation Layer, "
            "protection/account/exchange facts; then live_outcome_calibration from "
            "real fill, slippage, protection, settlement, and realized PnL."
        ),
        "remaining_live_submit_dependencies": [
            "fresh_selected_strategygroup_signal",
            "action_time_live_required_facts",
            "candidate_and_authorization_evidence",
            "action_time_finalgate_pass",
            "official_operation_layer_submit_path",
            "protection_account_and_exchange_facts",
        ],
        "remaining_live_outcome_calibration_dependencies": [
            "real_exchange_accept_or_reject",
            "actual_fill_or_partial_fill_behavior",
            "actual_slippage_fee_funding",
            "actual_protection_acceptance",
            "actual_reconciliation_settlement",
            "realized_pnl_review",
        ],
        "runtime_readiness_state": runtime_readiness_state,
        "safety_invariants": {
            "local_readiness_only": True,
            "live_submit_ready": False,
            "live_outcome_calibrated": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "exchange_write_called": False,
            "order_created": False,
            "live_profile_changed": False,
            "order_sizing_defaults_changed": False,
            "withdrawal_or_transfer_created": False,
        },
        "validation_errors": errors,
    }


def validate_artifact(artifact: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if artifact.get("schema") != "brc.strategygroup_pre_live_rehearsal_readiness.v1":
        errors.append("schema_mismatch")
    if "decision" in artifact:
        errors.append("top_level_decision_removed")
    if artifact.get("status") != "pre_live_rehearsal_ready":
        errors.append(f"status_not_ready:{artifact.get('status')}")
    runtime_readiness = _as_dict(artifact.get("runtime_readiness_state"))
    if runtime_readiness.get("state_family") != "Runtime Readiness State":
        errors.append("runtime_readiness_state_family_mismatch")
    if (
        runtime_readiness.get("source_role")
        != "pre_live_rehearsal_readiness_evidence"
    ):
        errors.append("runtime_readiness_state_source_role_mismatch")
    if runtime_readiness.get("pre_live_rehearsal_ready") is not True:
        errors.append("pre_live_rehearsal_ready_not_true")
    errors.extend(
        non_authoritative_state_errors(
            runtime_readiness,
            error_prefix="runtime_readiness_state",
            false_keys=(
                *AUTHORITATIVE_SOURCE_FALSE_KEYS,
                "live_submit_ready",
                "live_outcome_calibrated",
            ),
        )
    )
    for removed_mirror in LEGACY_AUTHORITY_MIRROR_KEYS:
        if removed_mirror in runtime_readiness:
            errors.append(
                "runtime_readiness_state."
                f"legacy_authority_mirror_present:{removed_mirror}"
            )
    if not artifact.get("remaining_live_submit_dependencies"):
        errors.append("missing_live_submit_dependencies")
    if not artifact.get("remaining_live_outcome_calibration_dependencies"):
        errors.append("missing_live_outcome_calibration_dependencies")
    safety = _as_dict(artifact.get("safety_invariants"))
    errors.extend(
        false_flag_errors(
            safety,
            error_prefix="safety_invariant",
            false_keys=(
                "live_submit_ready",
                "live_outcome_calibrated",
                *NON_EXECUTING_SIDE_EFFECT_FALSE_KEYS,
            ),
        )
    )
    for removed_mirror in LEGACY_AUTHORITY_MIRROR_KEYS:
        if removed_mirror in safety:
            errors.append(
                f"safety_invariant.legacy_authority_mirror_present:{removed_mirror}"
            )
    return errors


def _validate_inputs(inputs: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for name, artifact in inputs.items():
        expected = EXPECTED_INPUT_STATUSES[name]
        if artifact.get("status") != expected:
            errors.append(f"{name}.unexpected_status:{artifact.get('status')}")
        if name == "quality_wave":
            provenance = _as_dict(artifact.get("strategy_asset_state_provenance"))
            if provenance.get("source_role") != "quality_evidence_provenance":
                errors.append("quality_wave.strategy_asset_state_provenance_missing")
            if not _dict_rows(provenance.get("rows")):
                errors.append("quality_wave.strategy_asset_state_provenance_rows_missing")
        for effect in _forbidden_effects(artifact):
            errors.append(f"{name}.{effect}")
    return errors


def _forbidden_effects(artifact: dict[str, Any]) -> list[str]:
    effects: list[str] = []
    for section, keys in (
        (
            "interaction",
            [
                "mutates_remote_files",
                "approaches_real_order",
                "calls_finalgate",
                "calls_operation_layer",
                "calls_exchange_write",
                "places_order",
            ],
        ),
        (
            "safety_invariants",
            [
                "final_gate_called",
                "operation_layer_called",
                "exchange_write_called",
                "order_created",
                "live_profile_changed",
                "order_sizing_defaults_changed",
                "withdrawal_or_transfer_created",
            ],
        ),
    ):
        values = _as_dict(artifact.get(section))
        for key in keys:
            if values.get(key) is True:
                effects.append(f"{section}.{key}")
        if section == "safety_invariants":
            for key in LEGACY_AUTHORITY_MIRROR_KEYS:
                if values.get(key) is True:
                    effects.append(
                        f"{section}.legacy_authority_mirror_present:{key}"
                    )
    return sorted(set(effects))


def _strategygroup_decision_impact(quality_wave: dict[str, Any]) -> list[dict[str, Any]]:
    output = []
    provenance = _as_dict(quality_wave.get("strategy_asset_state_provenance"))
    provenance_rows = _dict_rows(provenance.get("rows"))
    source_role = str(provenance.get("source_role") or "")
    for row in provenance_rows:
        group = str(row.get("strategy_group_id") or "")
        output.append(
            {
                "strategy_group_id": group,
                "current_tier": row.get("current_tier"),
                "current_decision": row.get("current_decision"),
                "source_role": source_role,
                "primary_judgment_source": False,
                "decision_impact": _impact_for_row(row),
            }
        )
    return output


def _impact_for_row(row: dict[str, Any]) -> str:
    group = str(row.get("strategy_group_id") or "")
    if group == "BTPC-001":
        return "revise lane guarded; L2 shadow may continue; no L4/live authority"
    if group in {"VCB-001", "LSR-001", "BRF-001"}:
        return "observe-only decision retained with explicit missing handoff boundary"
    if group == "RBR-001":
        return "park decision retained until material new edge evidence"
    return "current decision retained"


def build_markdown(artifact: dict[str, Any]) -> str:
    return "\n".join(
        [
            "---",
            "title: STRATEGYGROUP_PRE_LIVE_REHEARSAL_READINESS_CURRENT",
            "status: CURRENT",
            "authority: docs/current/strategy-group-handoffs/strategygroup-pre-live-rehearsal-readiness-current.json",
            "last_verified: 2026-06-20",
            "---",
            "",
            "# StrategyGroup Pre-Live Rehearsal Readiness Current",
            "",
            "## Summary",
            "",
            f"- Status: `{artifact.get('status')}`",
            "- Pre-live rehearsal ready: `{}`".format(
                _as_dict(artifact.get("runtime_readiness_state")).get(
                    "pre_live_rehearsal_ready"
                )
            ),
            "- Live submit ready: `false`",
            "",
            "## Inputs",
            "",
            _input_table(_dict_rows(artifact.get("input_rows"))),
            "",
            "## StrategyGroup Decision Impact",
            "",
            _impact_table(_dict_rows(artifact.get("strategygroup_decision_impact"))),
            "",
            "## Next Engineering Bottleneck",
            "",
            str(artifact.get("next_engineering_bottleneck") or ""),
            "",
            "## Runtime Readiness State",
            "",
            f"- Source role: `{_as_dict(artifact.get('runtime_readiness_state')).get('source_role')}`",
            f"- Tradeability decision source: `{_as_dict(artifact.get('runtime_readiness_state')).get('tradeability_decision_source')}`",
            f"- Execution Attempt source: `{_as_dict(artifact.get('runtime_readiness_state')).get('execution_attempt_source')}`",
            f"- Default next step: `{_as_dict(artifact.get('runtime_readiness_state')).get('default_next_step')}`",
        ]
    ).rstrip() + "\n"


def _input_table(rows: list[dict[str, Any]]) -> str:
    lines = ["| Input | Status | Ready |", "| --- | --- | --- |"]
    for row in rows:
        lines.append(
            "| `{}` | `{}` | `{}` |".format(
                row.get("input"), row.get("status"), row.get("ready")
            )
        )
    return "\n".join(lines)


def _impact_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| StrategyGroup | Tier | Decision | Impact |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| `{}` | `{}` | `{}` | {} |".format(
                row.get("strategy_group_id"),
                row.get("current_tier"),
                row.get("current_decision"),
                row.get("decision_impact"),
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
    parser.add_argument("--handoff-boundary-json", default=str(DEFAULT_HANDOFF_BOUNDARY_JSON))
    parser.add_argument("--btpc-guard-json", default=str(DEFAULT_BTPC_GUARD_JSON))
    parser.add_argument(
        "--lifecycle-rehearsal-json",
        default=str(DEFAULT_LIFECYCLE_REHEARSAL_JSON),
    )
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
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if not errors else 2

    artifact = build_pre_live_rehearsal_readiness(
        quality_wave=_load_json(Path(args.quality_wave_json).expanduser()),
        handoff_boundary=_load_json(Path(args.handoff_boundary_json).expanduser()),
        btpc_guard=_load_json(Path(args.btpc_guard_json).expanduser()),
        lifecycle_rehearsal=_load_json(
            Path(args.lifecycle_rehearsal_json).expanduser()
        ),
    )
    payload = json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True)
    _write_text(Path(args.output_json).expanduser(), payload + "\n")
    _write_text(Path(args.output_owner_progress).expanduser(), build_markdown(artifact))
    print(payload)
    return 0 if artifact["status"] == "pre_live_rehearsal_ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
