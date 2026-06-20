#!/usr/bin/env python3
"""Build the BTPC fact/classifier revise guard packet.

The guard rolls up the BTPC fact-source decision, live derivatives source map,
and classifier rule review into one machine-checkable revise lane. It keeps
BTPC in L2 shadow review and explicitly prevents L4 or live-order authority.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BTPC_L2_DECISION_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-btpc-l2-keep-revise-fact-source-decision.json"
)
DEFAULT_BTPC_LIVE_SOURCE_MAPPING_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-btpc-live-derivatives-fact-source-mapping.json"
)
DEFAULT_BTPC_CLASSIFIER_RULE_REVIEW_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-btpc-classifier-rule-review.json"
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
    "btpc_l2_keep_revise_fact_source_decision": (
        "btpc_l2_keep_revise_fact_source_decision_ready"
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
        "btpc_l2_keep_revise_fact_source_decision": l2_decision,
        "btpc_live_derivatives_fact_source_mapping": live_source_mapping,
        "btpc_classifier_rule_review": classifier_rule_review,
    }
    source_rows = [_source_row(name, packet) for name, packet in sources.items()]
    errors = _validate_sources(sources)
    status = "btpc_fact_classifier_guard_ready" if not errors else "btpc_fact_classifier_guard_failed"
    return {
        "schema": "brc.strategygroup_btpc_fact_classifier_guard.v1",
        "scope": "strategygroup_btpc_fact_classifier_guard",
        "status": status,
        "interaction": {
            "level": "L0_local_btpc_fact_classifier_guard",
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "source_rows": source_rows,
        "btpc_state": {
            "strategy_group_id": "BTPC-001",
            "current_tier": "L2",
            "decision": "revise",
            "fact_source_guard_ready": not errors,
            "classifier_guard_ready": not errors,
            "l2_shadow_observation_can_continue": not errors,
            "mapping_satisfies_live_required_facts": False,
            "classifier_review_satisfies_live_required_facts": False,
            "actionable_now": False,
            "l2_promotion_authority": False,
            "l4_scope_change_recommended": False,
            "real_order_authority": False,
        },
        "decision": {
            "keep_l2_shadow_observation": not errors,
            "revise_fact_classifier_inputs_before_promotion": True,
            "owner_risk_acceptance_may_advance_trial_eligibility_only": True,
            "owner_risk_acceptance_cannot_set_actionable_now_true": True,
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
        "safety_invariants": {
            "local_guard_only": True,
            "actionable_now": False,
            "real_order_authority": False,
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


def validate_packet(packet: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if packet.get("schema") != "brc.strategygroup_btpc_fact_classifier_guard.v1":
        errors.append("schema_mismatch")
    if packet.get("status") != "btpc_fact_classifier_guard_ready":
        errors.append(f"status_not_ready:{packet.get('status')}")
    rows = {str(row.get("artifact") or ""): row for row in _dict_rows(packet.get("source_rows"))}
    for artifact, expected in EXPECTED_STATUSES.items():
        row = rows.get(artifact)
        if not row:
            errors.append(f"{artifact}.missing_source_row")
            continue
        if row.get("status") != expected:
            errors.append(f"{artifact}.unexpected_status:{row.get('status')}")
        if row.get("forbidden_effects"):
            errors.append(f"{artifact}.forbidden_effects_present")
    state = _as_dict(packet.get("btpc_state"))
    for key in (
        "mapping_satisfies_live_required_facts",
        "classifier_review_satisfies_live_required_facts",
        "actionable_now",
        "l2_promotion_authority",
        "l4_scope_change_recommended",
        "real_order_authority",
    ):
        if state.get(key) is not False:
            errors.append(f"btpc_state_not_false:{key}")
    decision = _as_dict(packet.get("decision"))
    if decision.get("owner_risk_acceptance_cannot_set_actionable_now_true") is not True:
        errors.append("owner_risk_acceptance_rule_missing")
    for key in (
        "l2_promotion_recommended_now",
        "l4_scope_change_recommended",
        "real_order_scope_change_recommended",
    ):
        if decision.get(key) is not False:
            errors.append(f"decision_not_false:{key}")
    return errors


def _source_row(name: str, packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact": name,
        "status": packet.get("status"),
        "expected_status": EXPECTED_STATUSES[name],
        "ready": packet.get("status") == EXPECTED_STATUSES[name],
        "forbidden_effects": _forbidden_effects(packet),
        "default_next_step": _as_dict(packet.get("decision")).get("default_next_step"),
    }


def _validate_sources(sources: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for name, packet in sources.items():
        if packet.get("status") != EXPECTED_STATUSES[name]:
            errors.append(f"{name}.unexpected_status:{packet.get('status')}")
        for effect in _forbidden_effects(packet):
            errors.append(f"{name}.{effect}")
    return errors


def _forbidden_effects(packet: dict[str, Any]) -> list[str]:
    effects: list[str] = []
    for section, key in FORBIDDEN_TRUE_PATHS:
        if _as_dict(packet.get(section)).get(key) is True:
            effects.append(f"{section}.{key}")
    for item in _as_dict(packet.get("safety_invariants")).get("source_forbidden_effects") or []:
        effects.append(f"safety_invariants.source_forbidden_effects.{item}")
    return sorted(set(effects))


def build_markdown(packet: dict[str, Any]) -> str:
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
            f"- Status: `{packet.get('status')}`",
            "- StrategyGroup: `BTPC-001`",
            "- Current decision: `revise`",
            "- Actionable now: `false`",
            "- Real order authority: `false`",
            "",
            "## Source Rows",
            "",
            _source_table(_dict_rows(packet.get("source_rows"))),
            "",
            "## Boundary",
            "",
            "This guard preserves the BTPC revise lane. It does not promote BTPC, satisfy live RequiredFacts, call FinalGate, call Operation Layer, or authorize a real order.",
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


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--btpc-l2-decision-json", default=str(DEFAULT_BTPC_L2_DECISION_JSON))
    parser.add_argument(
        "--btpc-live-source-mapping-json",
        default=str(DEFAULT_BTPC_LIVE_SOURCE_MAPPING_JSON),
    )
    parser.add_argument(
        "--btpc-classifier-rule-review-json",
        default=str(DEFAULT_BTPC_CLASSIFIER_RULE_REVIEW_JSON),
    )
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
            "source_row_count": len(_dict_rows(packet.get("source_rows"))),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if not errors else 2

    packet = build_btpc_fact_classifier_guard(
        l2_decision=_load_json(Path(args.btpc_l2_decision_json).expanduser()),
        live_source_mapping=_load_json(
            Path(args.btpc_live_source_mapping_json).expanduser()
        ),
        classifier_rule_review=_load_json(
            Path(args.btpc_classifier_rule_review_json).expanduser()
        ),
    )
    payload = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True)
    _write_text(Path(args.output_json).expanduser(), payload + "\n")
    _write_text(Path(args.output_owner_progress).expanduser(), build_markdown(packet))
    print(payload)
    return 0 if packet["status"] == "btpc_fact_classifier_guard_ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
