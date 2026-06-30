#!/usr/bin/env python3
"""Build the BTPC fact/classifier revise guard artifact.

The guard rolls up the BTPC fact-source review, live derivatives source map,
and classifier rule review into one machine-checkable revise lane. It keeps
BTPC in L2 shadow review and explicitly prevents L4 or live-order authority.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from strategygroup_non_executing_projection import (  # noqa: E402
    RUNTIME_AUTHORITY_SOURCES,
    legacy_authority_mirror_effects_for_artifacts,
    non_executing_interaction,
    review_outcome_default_next_step,
    review_outcome_source_validation_errors,
    review_outcome_state_from,
    review_outcome_state_boundary,
    review_outcome_state_validation_errors,
    section_true_key_effects,
    source_forbidden_effects,
)

DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-btpc-fact-classifier-guard-current.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-btpc-fact-classifier-guard-current.md"
)

EXPECTED_STATUSES = {
    "btpc_l2_keep_revise_fact_source_review": (
        "btpc_l2_keep_revise_fact_source_review_ready"
    ),
    "btpc_live_derivatives_fact_source_mapping": (
        "btpc_live_derivatives_fact_source_mapping_ready_without_live_authority"
    ),
    "btpc_classifier_rule_review": (
        "btpc_classifier_rule_review_recorded_without_live_authority"
    ),
}
FORBIDDEN_TRUE_PATHS = [
    ("decision", "l2_promotion_recommended_now"),
    ("decision", "l4_scope_change_recommended"),
    ("decision", "real_order_scope_change_recommended"),
    ("review_outcome_state", "l2_promotion_recommended_now"),
    ("review_outcome_state", "l4_scope_change_recommended"),
    ("review_outcome_state", "real_order_scope_change_recommended"),
    ("interaction", "mutates_remote_files"),
    ("interaction", "approaches_real_order"),
    ("interaction", "calls_finalgate"),
    ("interaction", "calls_operation_layer"),
    ("interaction", "calls_exchange_write"),
    ("interaction", "places_order"),
    ("safety_invariants", "server_files_mutated"),
    ("safety_invariants", "runtime_started"),
    ("safety_invariants", "live_profile_changed"),
    ("safety_invariants", "order_sizing_defaults_changed"),
    ("safety_invariants", "tier_policy_changed"),
    ("safety_invariants", "l2_promotion_authorized"),
    ("safety_invariants", "l4_real_order_scope_expanded"),
    ("safety_invariants", "shadow_candidate_created"),
    ("safety_invariants", "execution_intent_created"),
    ("safety_invariants", "final_gate_called"),
    ("safety_invariants", "operation_layer_called"),
    ("safety_invariants", "order_created"),
    ("safety_invariants", "order_lifecycle_called"),
    ("safety_invariants", "exchange_write_called"),
    ("safety_invariants", "withdrawal_or_transfer_created"),
]


def build_btpc_fact_classifier_guard(
    *,
    l2_decision: dict[str, Any],
    live_source_mapping: dict[str, Any],
    classifier_rule_review: dict[str, Any],
) -> dict[str, Any]:
    sources = {
        "btpc_l2_keep_revise_fact_source_review": l2_decision,
        "btpc_live_derivatives_fact_source_mapping": live_source_mapping,
        "btpc_classifier_rule_review": classifier_rule_review,
    }
    source_rows = [_source_row(name, artifact) for name, artifact in sources.items()]
    errors = _validate_sources(sources)
    status = "btpc_fact_classifier_guard_ready" if not errors else "btpc_fact_classifier_guard_failed"
    return {
        "schema": "brc.strategygroup_btpc_fact_classifier_guard.v1",
        "scope": "strategygroup_btpc_fact_classifier_guard",
        "status": status,
        "interaction": non_executing_interaction(
            "L0_local_btpc_fact_classifier_guard"
        ),
        "source_rows": source_rows,
        "btpc_state": {
            "strategy_group_id": "BTPC-001",
            "current_tier": "L2",
            "current_review_outcome": "revise",
            "fact_source_guard_ready": not errors,
            "classifier_guard_ready": not errors,
            "l2_shadow_observation_can_continue": not errors,
            "mapping_satisfies_live_required_facts": False,
            "classifier_review_satisfies_live_required_facts": False,
            "l2_promotion_authority": False,
            "l4_scope_change_recommended": False,
        },
        "review_outcome_state": review_outcome_state_boundary(
            source_role="btpc_fact_classifier_guard_provenance",
            review_scope="fact_classifier_guard",
            runtime_authority_sources=RUNTIME_AUTHORITY_SOURCES,
            extra={
                "strategy_group_id": "BTPC-001",
                "keep_l2_shadow_observation": not errors,
                "revise_fact_classifier_inputs_before_promotion": True,
                "owner_risk_acceptance_may_advance_trial_eligibility_only": True,
                "owner_risk_acceptance_cannot_grant_runtime_authority": True,
                "mapping_satisfies_live_required_facts": False,
                "classifier_review_satisfies_live_required_facts": False,
                "tier_policy_change_recommended_now": False,
                "l2_promotion_recommended_now": False,
                "l4_scope_change_recommended": False,
                "real_order_scope_change_recommended": False,
                "default_next_step": (
                    "continue_btpc_l2_shadow_observation_with_fact_classifier_guard"
                    if not errors
                    else "repair_btpc_fact_classifier_guard_inputs"
                ),
            },
        ),
        "safety_invariants": {
            "local_guard_only": True,
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
    if artifact.get("schema") != "brc.strategygroup_btpc_fact_classifier_guard.v1":
        errors.append("schema_mismatch")
    if artifact.get("status") != "btpc_fact_classifier_guard_ready":
        errors.append(f"status_not_ready:{artifact.get('status')}")
    if "decision" in artifact:
        errors.append("legacy_top_level_decision_present")
    rows = {str(row.get("artifact") or ""): row for row in _dict_rows(artifact.get("source_rows"))}
    for artifact_name, expected in EXPECTED_STATUSES.items():
        row = rows.get(artifact_name)
        if not row:
            errors.append(f"{artifact_name}.missing_source_row")
            continue
        if row.get("status") != expected:
            errors.append(f"{artifact_name}.unexpected_status:{row.get('status')}")
        if row.get("forbidden_effects"):
            errors.append(f"{artifact_name}.forbidden_effects_present")
    state = _as_dict(artifact.get("btpc_state"))
    if "decision" in state:
        errors.append("btpc_state_legacy_decision_present")
    if state.get("current_review_outcome") != "revise":
        errors.append("btpc_state_current_review_outcome_mismatch")
    for key in (
        "mapping_satisfies_live_required_facts",
        "classifier_review_satisfies_live_required_facts",
        "l2_promotion_authority",
        "l4_scope_change_recommended",
    ):
        if state.get(key) is not False:
            errors.append(f"btpc_state_not_false:{key}")
    errors.extend(
        review_outcome_state_validation_errors(
            review_outcome_state_from(artifact),
            expected_source_role="btpc_fact_classifier_guard_provenance",
            false_keys=(
                "l2_promotion_recommended_now",
                "l4_scope_change_recommended",
                "real_order_scope_change_recommended",
            ),
            require_runtime_authority_sources=True,
            require_owner_runtime_authority_rule=True,
        )
    )
    safety = _as_dict(artifact.get("safety_invariants"))
    for key in (
        "final_gate_called",
        "operation_layer_called",
        "exchange_write_called",
        "order_created",
        "live_profile_changed",
        "order_sizing_defaults_changed",
        "withdrawal_or_transfer_created",
    ):
        if safety.get(key) is not False:
            errors.append(f"safety_invariants_not_false:{key}")
    return errors


def _source_row(name: str, artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact": name,
        "status": artifact.get("status"),
        "expected_status": EXPECTED_STATUSES[name],
        "ready": artifact.get("status") == EXPECTED_STATUSES[name],
        "forbidden_effects": _forbidden_effects(artifact),
        "default_next_step": _source_default_next_step(name, artifact),
    }


def _source_default_next_step(name: str, artifact: dict[str, Any]) -> str | None:
    return review_outcome_default_next_step(artifact) or None


def _validate_sources(sources: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for name, artifact in sources.items():
        if artifact.get("status") != EXPECTED_STATUSES[name]:
            errors.append(f"{name}.unexpected_status:{artifact.get('status')}")
        errors.extend(
            review_outcome_source_validation_errors(
                artifact,
                source_name=name,
            )
        )
        for effect in _forbidden_effects(artifact):
            errors.append(f"{name}.{effect}")
    return errors


def _forbidden_effects(artifact: dict[str, Any]) -> list[str]:
    effects = section_true_key_effects(artifact, FORBIDDEN_TRUE_PATHS)
    effects.extend(
        source_forbidden_effects(
            (("", artifact),),
            true_keys=(),
            source_names=("safety_invariants",),
            source_effect_includes_source_name=True,
        )
    )
    effects.extend(_legacy_authority_mirror_effects(artifact))
    return sorted(set(effects))


def _legacy_authority_mirror_effects(artifact: dict[str, Any]) -> list[str]:
    return legacy_authority_mirror_effects_for_artifacts(
        (("", artifact),),
        section_names=("safety_invariants", "review_outcome_state", "btpc_state"),
        row_names=("action_rows", "case_rows", "source_rows"),
        row_id_keys=("strategy_group_id", "action", "fixture_case", "artifact"),
    )


def build_markdown(artifact: dict[str, Any]) -> str:
    return "\n".join(
        [
            "---",
            "title: STRATEGYGROUP_BTPC_FACT_CLASSIFIER_GUARD_CURRENT",
            "status: CURRENT",
            "authority: docs/current/strategy-group-handoffs/strategygroup-btpc-fact-classifier-guard-current.json",
            "last_verified: 2026-06-20",
            "---",
            "",
            "# StrategyGroup BTPC Fact Classifier Guard Current",
            "",
            "## Summary",
            "",
            f"- Status: `{artifact.get('status')}`",
            "- StrategyGroup: `BTPC-001`",
            "- Current review outcome: `revise`",
            "- Review outcome state: `btpc_fact_classifier_guard_provenance`",
            "",
            "## Source Rows",
            "",
            _source_table(_dict_rows(artifact.get("source_rows"))),
            "",
            "## Boundary",
            "",
            "This guard preserves the BTPC revise lane. It does not promote BTPC, satisfy live RequiredFacts, call FinalGate, call Operation Layer, or write to an exchange.",
        ]
    ).rstrip() + "\n"


def _source_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Artifact | Status | Ready | Forbidden effects |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        effects = row.get("forbidden_effects") or []
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` |".format(
                row.get("artifact"),
                row.get("status"),
                row.get("ready"),
                ",".join(str(item) for item in effects) if effects else "none",
            )
        )
    return "\n".join(lines)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return payload


def _load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _load_json(path)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--btpc-l2-review-json")
    parser.add_argument(
        "--btpc-live-source-mapping-json"
    )
    parser.add_argument(
        "--btpc-classifier-rule-review-json"
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
            "source_row_count": len(_dict_rows(artifact.get("source_rows"))),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if not errors else 2

    artifact = build_btpc_fact_classifier_guard(
        l2_decision=_load_optional_json(Path(args.btpc_l2_review_json).expanduser())
        if args.btpc_l2_review_json
        else {},
        live_source_mapping=_load_optional_json(
            Path(args.btpc_live_source_mapping_json).expanduser()
        )
        if args.btpc_live_source_mapping_json
        else {},
        classifier_rule_review=_load_optional_json(
            Path(args.btpc_classifier_rule_review_json).expanduser()
        )
        if args.btpc_classifier_rule_review_json
        else {},
    )
    payload = json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True)
    _write_text(Path(args.output_json).expanduser(), payload + "\n")
    _write_text(Path(args.output_owner_progress).expanduser(), build_markdown(artifact))
    print(payload)
    return 0 if artifact["status"] == "btpc_fact_classifier_guard_ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
