#!/usr/bin/env python3
"""Build a main-control review for strategy-research intake candidates.

This command consumes a research-only tiny-live intake artifact and converts it
into a final-side review artifact. It absorbs strategy assets for review,
paper observation, and role coverage only. It does not grant tiny-live
readiness, runtime authority, FinalGate input, Operation Layer input, exchange
writes, tier-policy changes, live-profile changes, or order-sizing changes.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.strategygroup_non_executing_projection import (
    LEGACY_AUTHORITY_MIRROR_KEYS,
    authority_boundary_candidate_true_key_effects,
    non_executing_interaction,
    non_executing_safety_boundary,
)


DEFAULT_RESEARCH_INTAKE_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/research-intake-snapshots/tiny-live-intake-candidates.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-research-intake-review.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-research-intake-review.md"
)

SCHEMA = "brc.strategygroup_research_intake_review.v1"

FORBIDDEN_SOURCE_AUTHORITY_KEYS = (
    "exchange_write",
    "execution_authority",
    "finalgate_input",
    "live_profile_change",
    "live_required_facts",
    "operation_layer_input",
    "order_created",
    "tier_policy_change",
)
LEGACY_AUTHORITY_MIRROR_TRUE_KEYS = LEGACY_AUTHORITY_MIRROR_KEYS

FALSE_OUTPUT_KEYS = (
    "finalgate_input",
    "operation_layer_input",
    "exchange_write",
    "order_created",
    "live_profile_change",
    "tier_policy_change",
    "order_sizing_change",
)

MAIN_CONTROL_POSITIONS = {
    "BRF2-001": {
        "position": "paper_observation_admission_candidate",
        "curated_strategy_asset_seed_decision": "promote",
        "promotion_scope": "intake_only",
        "promotion_target": "paper_observation_or_experiment_evidence",
        "next_checkpoint": "BRF2-001_paper_observation_admission_evidence",
        "required_next_evidence": (
            "paper_observation_evidence_shape_requiredfacts_disable_facts_and_review_ledger_mapping"
        ),
        "intake_reason": (
            "first_priority_trial_intake_asset_for_review_only_paper_observation"
        ),
    },
    "RBR2-001": {
        "position": "role_only_intake_candidate",
        "curated_strategy_asset_seed_decision": "keep_observing",
        "next_checkpoint": "RBR2-001_role_only_range_detector_classifier_merge_note",
        "required_next_evidence": (
            "range_detector_facts_and_failed_upside_expansion_classifier_merge_review"
        ),
        "intake_reason": (
            "role_only_range_reversion_filler_due_to_high_5m_stop_hit_rate"
        ),
    },
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--research-intake-json", default=str(DEFAULT_RESEARCH_INTAKE_JSON)
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    review_artifact = build_research_intake_review(
        research_intake_artifact=_load_json_object(Path(args.research_intake_json)),
        source_path=Path(args.research_intake_json),
    )
    payload = json.dumps(review_artifact, ensure_ascii=False, indent=2, sort_keys=True)
    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(payload + "\n", encoding="utf-8")

    output_md = Path(args.output_owner_progress)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(
        render_owner_progress_markdown(review_artifact), encoding="utf-8"
    )

    print(payload)
    return 0 if review_artifact["status"] != "blocked_forbidden_source_authority" else 2


def build_research_intake_review(
    *,
    research_intake_artifact: dict[str, Any],
    source_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    source_forbidden_effects = authority_boundary_candidate_true_key_effects(
        research_intake_artifact,
        true_keys=FORBIDDEN_SOURCE_AUTHORITY_KEYS,
    )
    legacy_authority_mirrors = [
        f"legacy_authority_mirror_present:{path}"
        for path in authority_boundary_candidate_true_key_effects(
            research_intake_artifact,
            true_keys=LEGACY_AUTHORITY_MIRROR_TRUE_KEYS,
        )
    ]
    source_forbidden_effects.extend(legacy_authority_mirrors)
    candidate_rows = [
        _candidate_row(candidate)
        for candidate in _dict_rows(research_intake_artifact.get("candidates"))
    ]
    strategy_decision_provenance_rows = [
        _strategy_decision_provenance_row(row) for row in candidate_rows
    ]
    status = (
        "blocked_forbidden_source_authority"
        if source_forbidden_effects
        else "research_intake_review_ready"
        if candidate_rows and _summary_objective_met(research_intake_artifact)
        else "research_intake_review_needs_work"
    )
    counts = _counts(candidate_rows)
    return {
        "schema": SCHEMA,
        "scope": "main_control_research_intake_review_only",
        "status": status,
        "generated_at_utc": generated_at_utc
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_status": {
            "research_intake_json": str(source_path or DEFAULT_RESEARCH_INTAKE_JSON),
            "source_schema": research_intake_artifact.get("schema"),
            "source_scope": research_intake_artifact.get("scope"),
            "source_status": research_intake_artifact.get("status"),
            "summary_objective_met": _summary_objective_met(
                research_intake_artifact
            ),
            "candidate_count": len(candidate_rows),
            "source_forbidden_effects": source_forbidden_effects,
        },
        "summary": counts,
        "absorbed_asset_fields": [
            "strategy_semantics",
            "required_facts_draft",
            "disable_or_review_facts_draft",
            "risk_envelope",
            "path_risk_evidence",
            "paper_observation_proposal",
            "review_ledger_mapping",
        ],
        "not_absorbed_authority_fields": [
            "tiny_live_ready",
            "runtime actionability",
            "FinalGate input",
            "Operation Layer input",
            "real-order authority",
            "live_profile_change",
            "order_sizing_change",
            "tier_policy_change",
        ],
        "candidate_rows": candidate_rows,
        "strategy_decision_provenance_rows": strategy_decision_provenance_rows,
        "paper_observation_admission": _paper_observation_admission(candidate_rows),
        "role_only_intake": _role_only_intake(candidate_rows),
        "owner_progress_projection": {
            "p0_state": "waiting_for_market",
            "signal_observation_state": "research_intake_review_active",
            "owner_summary": (
                "Strategy-research intake candidates are visible to main control "
                "as review-only assets; live permission is unchanged."
            ),
            "owner_intervention_required": False,
            "owner_policy_confirmation_required_now": False,
            "no_live_permission": True,
        },
        "interaction": _interaction(),
        "safety_invariants": _safety_invariants(source_forbidden_effects),
    }


def _candidate_row(candidate: dict[str, Any]) -> dict[str, Any]:
    strategy_id = str(candidate.get("strategy_id") or "unknown")
    position = MAIN_CONTROL_POSITIONS.get(strategy_id, {})
    required_facts = _string_list(candidate.get("required_facts_draft"))
    disable_facts = _string_list(candidate.get("disable_or_review_facts_draft"))
    promotion_scope = str(position.get("promotion_scope") or "not_applicable")
    promotion_target = str(position.get("promotion_target") or "not_applicable")
    return {
        "strategy_group_id": strategy_id,
        "strategy_direction": str(candidate.get("strategy_direction") or "unknown"),
        "source_intake_status": str(candidate.get("intake_status") or "unknown"),
        "source_recommended_runtime_stage": str(
            candidate.get("recommended_runtime_stage") or "unknown"
        ),
        "main_control_intake_position": str(
            position.get("position") or "research_intake_candidate_review"
        ),
        "promotion_scope": promotion_scope,
        "promotion_target": promotion_target,
        "intake_reason": str(
            position.get("intake_reason")
            or "main_control_review_required_before_any_authority_change"
        ),
        "paper_observation_ready": bool(candidate.get("paper_observation_ready")),
        "source_non_executing_trial_readiness": bool(
            candidate.get("tiny_live_ready")
        ),
        "finalgate_input": False,
        "operation_layer_input": False,
        "exchange_write": False,
        "order_created": False,
        "live_profile_change": False,
        "tier_policy_change": False,
        "order_sizing_change": False,
        "required_facts_draft": required_facts,
        "disable_or_review_facts_draft": disable_facts,
        "risk_envelope": _as_dict(candidate.get("risk_envelope")),
        "path_risk_evidence": _as_dict(candidate.get("evidence")),
        "known_risks": _string_list(candidate.get("known_risks")),
        "source_reports": _source_report_refs(candidate.get("source_reports")),
        "paper_observation_evidence_shape": _paper_observation_evidence_shape(
            strategy_id=strategy_id,
            required_facts=required_facts,
            disable_facts=disable_facts,
        ),
        "review_ledger_mapping": {
            "records_would_enter": True,
            "records_paper_outcome": True,
            "allowed_decisions": ["keep_observing", "revise", "promote", "park"],
            "promote_requires_promotion_scope": True,
            "live_outcome_required": False,
            "live_permission_change": False,
        },
    }


def _strategy_decision_provenance_row(row: dict[str, Any]) -> dict[str, Any]:
    position = MAIN_CONTROL_POSITIONS.get(str(row.get("strategy_group_id")), {})
    decision = str(position.get("curated_strategy_asset_seed_decision") or "unknown")
    promotion_scope = str(row.get("promotion_scope") or "not_applicable")
    promotion_target = str(row.get("promotion_target") or "not_applicable")
    return {
        "strategy_group_id": row["strategy_group_id"],
        "tier": "unknown",
        "opportunity_type": "research_intake",
        "current_decision": decision,
        "strategy_asset_seed_source": (
            "curated_research_intake_strategy_asset_seed"
            if position.get("curated_strategy_asset_seed_decision")
            else "missing_strategy_asset_seed"
        ),
        "promotion_scope": promotion_scope,
        "promotion_target": promotion_target,
        "reason": (
            "research_intake:{}; direction:{}; source_non_executing_trial_readiness:{}; "
            "main_control_absorbs_asset_not_execution_authority; promotion_scope:{}"
        ).format(
            row["main_control_intake_position"],
            row["strategy_direction"],
            str(row["source_non_executing_trial_readiness"]).lower(),
            promotion_scope,
        ),
        "required_next_evidence": str(
            position.get("required_next_evidence")
            or "main_control_intake_review_before_any_authority_change"
        ),
        "authority_boundary": (
            "main_control_research_intake_review_only; research_input_not_execution_authority; "
            f"promotion_scope={promotion_scope}; promotion_target={promotion_target}; "
            "non_executing_trial_readiness=false; runtime_safety_gate_required; "
            "no_official_live_order_authority; "
            "no_finalgate_no_operation_layer_no_exchange_write"
        ),
        "next_checkpoint": str(
            position.get("next_checkpoint")
            or f"{row['strategy_group_id']}_main_control_research_intake_review"
        ),
    }


def _paper_observation_evidence_shape(
    *,
    strategy_id: str,
    required_facts: list[str],
    disable_facts: list[str],
) -> dict[str, Any]:
    return {
        "strategy_group_id": strategy_id,
        "record_type": "paper_observation_only",
        "fresh_signal_source": "future_observation_only_not_live_signal",
        "required_facts_draft": required_facts,
        "disable_or_review_facts_draft": disable_facts,
        "must_record": [
            "would_enter_timestamp",
            "symbol",
            "side",
            "strategy_direction",
            "required_facts_snapshot",
            "disable_or_review_fact_snapshot",
            "paper_forward_outcome",
            "review_outcome",
        ],
        "must_not_feed": [
            "FinalGate",
            "Operation Layer",
            "exchange_write",
            "live RequiredFacts",
            "Tradeability Decision authority",
            "Runtime Safety State authority",
        ],
    }


def _paper_observation_admission(rows: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [
        row
        for row in rows
        if row["main_control_intake_position"]
        == "paper_observation_admission_candidate"
    ]
    return {
        "candidate_count": len(candidates),
        "strategy_group_ids": [row["strategy_group_id"] for row in candidates],
        "next_checkpoint": "build_paper_observation_evidence_before_any_tiny_live_ready",
        "live_permission_change": False,
    }


def _role_only_intake(rows: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [
        row
        for row in rows
        if row["main_control_intake_position"] == "role_only_intake_candidate"
    ]
    return {
        "candidate_count": len(candidates),
        "strategy_group_ids": [row["strategy_group_id"] for row in candidates],
        "role_use": [
            "range_detector_review",
            "failed_upside_expansion_classifier_family",
            "other_short_strategy_filter_or_filler_material",
        ],
        "main_trial_priority": False,
        "live_permission_change": False,
    }


def _counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "candidate_count": len(rows),
        "paper_observation_admission_candidate_count": sum(
            1
            for row in rows
            if row["main_control_intake_position"]
            == "paper_observation_admission_candidate"
        ),
        "role_only_intake_candidate_count": sum(
            1
            for row in rows
            if row["main_control_intake_position"] == "role_only_intake_candidate"
        ),
        "paper_observation_ready_count": sum(
            1 for row in rows if row["paper_observation_ready"]
        ),
        "source_non_executing_trial_readiness_count": sum(
            1 for row in rows if row["source_non_executing_trial_readiness"]
        ),
        "finalgate_input_count": 0,
        "operation_layer_input_count": 0,
        "exchange_write_count": 0,
        "live_profile_change_count": 0,
        "tier_policy_change_count": 0,
    }


def render_owner_progress_markdown(artifact: dict[str, Any]) -> str:
    summary = _as_dict(artifact.get("summary"))
    lines = [
        "# StrategyGroup Research Intake Review",
        "",
        "## Summary",
        "",
        f"- Status: `{artifact.get('status')}`",
        f"- Candidate count: `{summary.get('candidate_count', 0)}`",
        f"- Paper observation candidates: `{summary.get('paper_observation_admission_candidate_count', 0)}`",
        f"- Role-only candidates: `{summary.get('role_only_intake_candidate_count', 0)}`",
        "- FinalGate input: `false`",
        "- Operation Layer input: `false`",
        "",
        "## Candidate Rows",
        "",
        "| StrategyGroup | Direction | Intake Position | Promotion Scope | Paper Observation | Next |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    by_next = {
        row["strategy_group_id"]: ledger["next_checkpoint"]
        for row, ledger in zip(
            _dict_rows(artifact.get("candidate_rows")),
            _dict_rows(artifact.get("strategy_decision_provenance_rows")),
            strict=False,
        )
    }
    for row in _dict_rows(artifact.get("candidate_rows")):
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row.get("strategy_group_id"),
                row.get("strategy_direction"),
                row.get("main_control_intake_position"),
                row.get("promotion_scope"),
                str(row.get("paper_observation_ready")).lower(),
                by_next.get(str(row.get("strategy_group_id")), "continue_review"),
            )
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- Main control absorbs strategy assets, RequiredFacts drafts, disable/review facts, risk envelope, path-risk evidence, and review mapping.",
            "- Main control does not absorb tiny-live readiness, actionable authority, FinalGate input, Operation Layer input, live profile change, tier policy change, or exchange write permission.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _summary_objective_met(research_intake_artifact: dict[str, Any]) -> bool:
    return _as_dict(research_intake_artifact.get("summary")).get("objective_met") is True


def _interaction() -> dict[str, Any]:
    return non_executing_interaction("L0_local_research_intake_review")


def _safety_invariants(source_forbidden_effects: list[str]) -> dict[str, Any]:
    return non_executing_safety_boundary(
        true_keys=(
            "main_control_review_only",
            "research_input_is_not_execution_authority",
        ),
        false_keys=(
            "server_files_mutated",
            "strategy_parameters_changed",
            "registry_authority_changed",
            "tier_policy_changed",
            "live_profile_changed",
            "order_sizing_changed",
            "tiny_live_ready",
            "final_gate_called",
            "operation_layer_called",
            "exchange_write_called",
            "order_created",
            "withdrawal_or_transfer_created",
        ),
        source_forbidden_effects=source_forbidden_effects,
    )


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _source_report_refs(value: Any) -> list[str]:
    refs: list[str] = []
    for item in _string_list(value):
        path = Path(item)
        refs.append(path.name if path.name else item)
    return refs


def _load_json_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return data


if __name__ == "__main__":
    raise SystemExit(main())
