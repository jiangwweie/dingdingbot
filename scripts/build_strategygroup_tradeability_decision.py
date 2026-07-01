#!/usr/bin/env python3
"""Build the StrategyGroup Tradeability Decision read model.

The decision answers one product question for every active or newly absorbed
candidate: can it trade now, and if not, what is the first blocker? It is
non-executing and must never create live authority.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.domain.required_facts_readiness import (  # noqa: E402
    required_facts_status_for_tradeability,
)
from src.domain.runtime_readiness_state import (  # noqa: E402
    candidate_authorization_state_from_runtime_safety_artifact,
    live_submit_ready_for_strategy_artifact,
    runtime_safety_state_from_artifact,
)
from scripts.strategygroup_non_executing_projection import (  # noqa: E402
    recursive_true_key_paths,
)

DEFAULT_REGISTRY_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-registry-baseline.json"
)
DEFAULT_TIER_POLICY_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-tradeability-decision.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-tradeability-decision.md"
)

SCHEMA = "brc.strategygroup_tradeability_decision.v1"
JULY_BULLISH_REBOUND_HYPOTHESIS_ID = "JULY-BULLISH-REBOUND-TRADE-PATH-CLOSURE-001"

DECISION_ORDER = {
    "tradable_now": 0,
    "not_tradable_safety_stop": 1,
    "not_tradable_asset_admission": 2,
    "not_tradable_policy": 3,
    "not_tradable_facts": 4,
    "not_tradable_execution_gate": 5,
    "not_tradable_market_wait": 6,
    "not_tradable_strategy_quality": 7,
}

CONTRACT_BLOCKER_CLASSES = {
    "artifact_missing",
    "schema_invalid",
    "detector_not_attached",
    "watcher_tick_missing",
    "scope_not_attached",
    "computed_not_satisfied",
    "replay_live_rule_mismatch",
    "action_time_boundary_not_reproduced",
    "policy_scope_missing",
    "runtime_profile_scope_missing",
    "market_wait_validated",
    "active_position_resolution",
    "hard_safety_stop",
    "review_only_warning",
}

BLOCKER_DECISION_BY_CLASS = {
    "artifact_missing": "not_tradable_facts",
    "schema_invalid": "not_tradable_facts",
    "detector_not_attached": "not_tradable_facts",
    "watcher_tick_missing": "not_tradable_facts",
    "scope_not_attached": "not_tradable_asset_admission",
    "computed_not_satisfied": "not_tradable_market_wait",
    "replay_live_rule_mismatch": "not_tradable_facts",
    "action_time_boundary_not_reproduced": "not_tradable_execution_gate",
    "policy_scope_missing": "not_tradable_policy",
    "runtime_profile_scope_missing": "not_tradable_execution_gate",
    "market_wait_validated": "not_tradable_market_wait",
    "active_position_resolution": "not_tradable_execution_gate",
    "hard_safety_stop": "not_tradable_safety_stop",
    "review_only_warning": "not_tradable_strategy_quality",
}

BLOCKER_OWNER_BY_CLASS = {
    "artifact_missing": "engineering",
    "schema_invalid": "engineering",
    "detector_not_attached": "engineering",
    "watcher_tick_missing": "runtime",
    "scope_not_attached": "engineering",
    "computed_not_satisfied": "market",
    "replay_live_rule_mismatch": "engineering",
    "action_time_boundary_not_reproduced": "runtime",
    "policy_scope_missing": "owner",
    "runtime_profile_scope_missing": "runtime",
    "market_wait_validated": "market",
    "active_position_resolution": "runtime",
    "hard_safety_stop": "safety",
    "review_only_warning": "strategy_review",
}

BLOCKER_PRIORITY = {
    "hard_safety_stop": 0,
    "artifact_missing": 10,
    "schema_invalid": 20,
    "detector_not_attached": 30,
    "watcher_tick_missing": 40,
    "scope_not_attached": 50,
    "policy_scope_missing": 55,
    "runtime_profile_scope_missing": 58,
    "replay_live_rule_mismatch": 60,
    "action_time_boundary_not_reproduced": 70,
    "active_position_resolution": 75,
    "computed_not_satisfied": 80,
    "market_wait_validated": 90,
    "review_only_warning": 100,
}

REPLAY_LIVE_PARITY_SCHEMA = "brc.replay_live_parity_audit.v1"
ACTION_TIME_BOUNDARY_SCHEMA = "brc.strategy_fresh_signal_action_time_boundary.v1"
MI_TRIAL_ADMISSION_SCHEMA = "brc.mi_trial_admission_decision.v1"
REPLAY_LIVE_PARITY_STRATEGY_IDS = {"CPM-RO-001", "MPG-001", "SOR-001"}
ACTION_TIME_BOUNDARY_STRATEGY_IDS = {"CPM-RO-001", "MPG-001", "SOR-001"}

LEGACY_BLOCKER_CLASS_MAP = {
    "brf2_candidate_authorization_evidence_not_created": "action_time_boundary_not_reproduced",
    "brf2_shadow_candidate_evidence_ready_authorization_evidence_not_created": "action_time_boundary_not_reproduced",
    "brf2_watcher_fact_input_missing": "watcher_tick_missing",
    "cpm_candidate_authorization_evidence_not_created": "action_time_boundary_not_reproduced",
    "cpm_disable_fact_active": "computed_not_satisfied",
    "cpm_dry_run_submit_rehearsal_gap": "action_time_boundary_not_reproduced",
    "cpm_registry_identity_gap": "scope_not_attached",
    "cpm_required_facts_mapping_gap": "artifact_missing",
    "cpm_runtime_signal_capture_gap": "detector_not_attached",
    "cpm_watcher_scope_gap": "watcher_tick_missing",
    "experiment_worthiness_or_loss_envelope_unclosed": "review_only_warning",
    "forbidden_effect_detected": "hard_safety_stop",
    "fresh_brf2_short_signal_absent": "market_wait_validated",
    "fresh_cpm_long_signal_absent": "market_wait_validated",
    "fresh_cpm_short_signal_absent": "market_wait_validated",
    "fresh_executable_signal_absent": "market_wait_validated",
    "fresh_mpg_long_signal_absent": "market_wait_validated",
    "fresh_session_range_signal_absent": "market_wait_validated",
    "fresh_signal_absent": "market_wait_validated",
    "fresh_sor_long_signal_absent": "market_wait_validated",
    "fresh_sor_session_range_signal_absent": "market_wait_validated",
    "fresh_strategy_signal_absent": "market_wait_validated",
    "mpg_high_beta_public_facts_gap": "scope_not_attached",
    "mpg_public_facts_gap": "scope_not_attached",
    "official_runtime_chain_ready": "market_wait_validated",
    "owner_trial_scope_or_capital_policy_missing": "policy_scope_missing",
    "portfolio_tradeability_decision_state_missing": "schema_invalid",
    "private_action_time_facts_required": "action_time_boundary_not_reproduced",
    "required_facts_mapping_gap": "artifact_missing",
    "required_facts_or_classifier_mapping_unclosed": "artifact_missing",
    "short_squeeze_risk_state_disable_active": "computed_not_satisfied",
    "strategy_group_not_admitted_as_final_trial_asset": "scope_not_attached",
}

FORBIDDEN_TRUE_KEYS = {
    "actionable_now",
    "real_order_authority",
    "registry_authority_changed",
    "tier_policy_changed",
    "live_profile_changed",
    "order_sizing_changed",
    "execution_intent_created",
    "creates_execution_intent",
    "submit_authorization_created",
    "final_gate_called",
    "calls_finalgate",
    "operation_layer_called",
    "calls_operation_layer",
    "order_created",
    "places_order",
    "exchange_write_called",
    "calls_exchange_write",
    "withdrawal_or_transfer_created",
    "preview_or_replay_treated_as_live_signal",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--capital-trial-envelope-projection-json",
        help=(
            "Explicit capital-trial envelope projection input. Runtime callers "
            "should pass this path; omitting it prevents stale capital-trial "
            "projection output from changing Tradeability judgment."
        ),
    )
    parser.add_argument("--registry-json", default=str(DEFAULT_REGISTRY_JSON))
    parser.add_argument("--tier-policy-json", default=str(DEFAULT_TIER_POLICY_JSON))
    parser.add_argument(
        "--signal-coverage-json",
        help=(
            "Explicit signal-coverage input. Runtime callers should pass this "
            "path; omitting it prevents stale signal-coverage output from "
            "changing Tradeability judgment."
        ),
    )
    parser.add_argument(
        "--runtime-safety-state-json",
        help=(
            "Explicit Runtime Safety State input. Runtime "
            "callers should pass this path; omitting it prevents stale "
            "Runtime Safety evidence from granting Tradeability judgment."
        ),
    )
    parser.add_argument(
        "--trial-asset-admission-proposal-json",
        help=(
            "Explicit Strategy Asset State admission proposal input. Runtime "
            "callers should pass this path; omitting it prevents stale "
            "trial-asset admission output from changing Tradeability judgment."
        ),
    )
    parser.add_argument(
        "--brf2-owner-trial-policy-scope-json",
        help=(
            "Explicit BRF2 Owner trial policy scope input. Runtime callers "
            "should pass this path; omitting it prevents stale Owner policy "
            "scope output from changing Tradeability judgment."
        ),
    )
    parser.add_argument(
        "--cpm-identity-routing-decision-json",
        help="Explicit CPM identity routing decision input.",
    )
    parser.add_argument(
        "--cpm-owner-trial-policy-scope-json",
        help="Explicit CPM Owner trial policy scope input.",
    )
    parser.add_argument(
        "--cpm-required-facts-mapping-json",
        help="Explicit CPM RequiredFacts mapping input.",
    )
    parser.add_argument(
        "--cpm-runtime-signal-capture-json",
        help="Explicit CPM runtime signal capture input.",
    )
    parser.add_argument(
        "--cpm-shadow-candidate-evidence-json",
        help="Explicit CPM shadow candidate evidence input.",
    )
    parser.add_argument(
        "--cpm-dry-run-submit-rehearsal-json",
        help="Explicit CPM dry-run submit rehearsal input.",
    )
    parser.add_argument(
        "--three-strategy-live-trial-portfolio-json",
        help=(
            "Explicit Strategy Asset / Trial Envelope portfolio input. Runtime "
            "callers should pass this path; omitting it prevents stale "
            "portfolio output from changing Tradeability judgment."
        ),
    )
    parser.add_argument(
        "--brf2-runtime-signal-capture-json",
        help=(
            "Explicit BRF2 runtime signal capture input. Runtime callers should "
            "pass this path; omitting it keeps signal-capture evidence absent "
            "instead of reading a stale latest-* artifact."
        ),
    )
    parser.add_argument(
        "--brf2-shadow-candidate-evidence-json",
        help=(
            "Explicit BRF2 shadow candidate evidence provenance input. Runtime "
            "callers should pass this path; omitting it keeps shadow evidence "
            "provenance absent instead of reading a stale default artifact."
        ),
    )
    parser.add_argument(
        "--trial-grade-signal-gate-audit-json",
        help=(
            "Explicit trial-grade signal-gate audit input. Runtime callers "
            "should pass this path; omitting it prevents stale trial-grade "
            "audit output from changing Tradeability judgment."
        ),
    )
    parser.add_argument(
        "--replay-live-parity-audit-json",
        help="Explicit replay/live parity audit input for first-blocker classification.",
    )
    parser.add_argument(
        "--mi-trial-admission-decision-json",
        help="Explicit MI trial admission decision input.",
    )
    parser.add_argument(
        "--strategy-fresh-signal-action-time-boundary-json",
        help="Explicit action-time boundary readiness input.",
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    decision_artifact = build_tradeability_decision(
        capital_trial_envelope_projection=(
            _read_json(Path(args.capital_trial_envelope_projection_json))
            if args.capital_trial_envelope_projection_json
            else {}
        ),
        registry=_read_json(Path(args.registry_json)),
        tier_policy=_read_json(Path(args.tier_policy_json)),
        signal_coverage=(
            _read_json(Path(args.signal_coverage_json))
            if args.signal_coverage_json
            else {}
        ),
        runtime_safety_state=(
            _read_json(Path(args.runtime_safety_state_json))
            if args.runtime_safety_state_json
            else {}
        ),
        trial_asset_admission_proposal=_read_optional_json(
            Path(args.trial_asset_admission_proposal_json)
        )
        if args.trial_asset_admission_proposal_json
        else {},
        brf2_owner_trial_policy_scope=(
            _read_optional_json(Path(args.brf2_owner_trial_policy_scope_json))
            if args.brf2_owner_trial_policy_scope_json
            else {}
        ),
        cpm_identity_routing_decision=(
            _read_optional_json(Path(args.cpm_identity_routing_decision_json))
            if args.cpm_identity_routing_decision_json
            else {}
        ),
        cpm_owner_trial_policy_scope=(
            _read_optional_json(Path(args.cpm_owner_trial_policy_scope_json))
            if args.cpm_owner_trial_policy_scope_json
            else {}
        ),
        cpm_required_facts_mapping=(
            _read_optional_json(Path(args.cpm_required_facts_mapping_json))
            if args.cpm_required_facts_mapping_json
            else {}
        ),
        cpm_runtime_signal_capture=(
            _read_optional_json(Path(args.cpm_runtime_signal_capture_json))
            if args.cpm_runtime_signal_capture_json
            else {}
        ),
        cpm_shadow_candidate_evidence=(
            _read_optional_json(Path(args.cpm_shadow_candidate_evidence_json))
            if args.cpm_shadow_candidate_evidence_json
            else {}
        ),
        cpm_dry_run_submit_rehearsal=(
            _read_optional_json(Path(args.cpm_dry_run_submit_rehearsal_json))
            if args.cpm_dry_run_submit_rehearsal_json
            else {}
        ),
        three_strategy_live_trial_portfolio=(
            _read_optional_json(Path(args.three_strategy_live_trial_portfolio_json))
            if args.three_strategy_live_trial_portfolio_json
            else {}
        ),
        brf2_runtime_signal_capture=(
            _read_optional_json(Path(args.brf2_runtime_signal_capture_json))
            if args.brf2_runtime_signal_capture_json
            else {}
        ),
        brf2_shadow_candidate_evidence=(
            _read_optional_json(Path(args.brf2_shadow_candidate_evidence_json))
            if args.brf2_shadow_candidate_evidence_json
            else {}
        ),
        trial_grade_signal_gate_audit=(
            _read_optional_json(Path(args.trial_grade_signal_gate_audit_json))
            if args.trial_grade_signal_gate_audit_json
            else {}
        ),
        replay_live_parity_audit=(
            _read_optional_json(Path(args.replay_live_parity_audit_json))
            if args.replay_live_parity_audit_json
            else {}
        ),
        mi_trial_admission_decision=(
            _read_optional_json(Path(args.mi_trial_admission_decision_json))
            if args.mi_trial_admission_decision_json
            else {}
        ),
        strategy_fresh_signal_action_time_boundary=(
            _read_optional_json(
                Path(args.strategy_fresh_signal_action_time_boundary_json)
            )
            if args.strategy_fresh_signal_action_time_boundary_json
            else {}
        ),
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_owner_progress)
    _write_json(output_json, decision_artifact)
    _write_text(output_md, _markdown(decision_artifact, output_json))
    print(
        json.dumps(
            {
                "status": decision_artifact["status"],
                "row_count": decision_artifact["summary"]["row_count"],
                "top_decision": decision_artifact["summary"]["top_decision"],
                "top_strategy_group_id": decision_artifact["summary"]["top_strategy_group_id"],
                "tradable_now_count": decision_artifact["summary"]["tradable_now_count"],
                "output_json": str(output_json),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if decision_artifact["status"] == "tradeability_decision_ready" else 2


def build_tradeability_decision(
    *,
    capital_trial_envelope_projection: dict[str, Any],
    registry: dict[str, Any],
    tier_policy: dict[str, Any],
    signal_coverage: dict[str, Any],
    runtime_safety_state: dict[str, Any],
    trial_asset_admission_proposal: dict[str, Any] | None = None,
    brf2_owner_trial_policy_scope: dict[str, Any] | None = None,
    cpm_identity_routing_decision: dict[str, Any] | None = None,
    cpm_owner_trial_policy_scope: dict[str, Any] | None = None,
    cpm_required_facts_mapping: dict[str, Any] | None = None,
    cpm_runtime_signal_capture: dict[str, Any] | None = None,
    cpm_shadow_candidate_evidence: dict[str, Any] | None = None,
    cpm_dry_run_submit_rehearsal: dict[str, Any] | None = None,
    three_strategy_live_trial_portfolio: dict[str, Any] | None = None,
    brf2_runtime_signal_capture: dict[str, Any] | None = None,
    brf2_shadow_candidate_evidence: dict[str, Any] | None = None,
    trial_grade_signal_gate_audit: dict[str, Any] | None = None,
    replay_live_parity_audit: dict[str, Any] | None = None,
    mi_trial_admission_decision: dict[str, Any] | None = None,
    strategy_fresh_signal_action_time_boundary: dict[str, Any] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    forbidden_effects = _forbidden_effects(
        capital_trial_envelope_projection,
        registry,
        tier_policy,
        signal_coverage,
        trial_asset_admission_proposal or {},
        brf2_owner_trial_policy_scope or {},
        cpm_identity_routing_decision or {},
        cpm_owner_trial_policy_scope or {},
        cpm_required_facts_mapping or {},
        cpm_runtime_signal_capture or {},
        cpm_shadow_candidate_evidence or {},
        cpm_dry_run_submit_rehearsal or {},
        three_strategy_live_trial_portfolio or {},
        brf2_runtime_signal_capture or {},
        brf2_shadow_candidate_evidence or {},
        trial_grade_signal_gate_audit or {},
        replay_live_parity_audit or {},
        mi_trial_admission_decision or {},
        strategy_fresh_signal_action_time_boundary or {},
    )
    registry_rows = _registry_rows_by_id(registry)
    tier_rows = _tier_rows_by_id(tier_policy)
    candidate_rows = _candidate_rows_by_id(capital_trial_envelope_projection)
    observed_rows = _observe_only_rows_by_id(signal_coverage)
    admission_proposals = _admission_proposals_by_id(
        trial_asset_admission_proposal or {}
    )
    owner_policy_scopes = _owner_policy_scopes_by_id(
        brf2_owner_trial_policy_scope or {}
    )
    owner_policy_scopes.update(
        _owner_policy_scopes_by_id(cpm_owner_trial_policy_scope or {})
    )
    portfolio = three_strategy_live_trial_portfolio or {}
    portfolio_seats = _portfolio_seats_by_id(portfolio)
    trial_envelope = _portfolio_trial_envelope(portfolio)
    trial_grade_rows = _trial_grade_rows_by_id(trial_grade_signal_gate_audit or {})

    all_ids = set(candidate_rows)
    all_ids.update(tier_rows)
    all_ids.update(observed_rows)
    all_ids.update(admission_proposals)
    all_ids.update(owner_policy_scopes)
    all_ids.update(portfolio_seats)
    if _mi_trial_admission_present(mi_trial_admission_decision or {}):
        all_ids.add("MI-001")
    if "MPG-001" in registry_rows:
        all_ids.add("MPG-001")

    selected_strategy_group_id = _selected_strategy_group_id(
        capital_trial_envelope_projection=capital_trial_envelope_projection,
        trial_asset_admission_proposal=trial_asset_admission_proposal or {},
    )
    rows = [
        _decision_row(
            strategy_group_id=strategy_group_id,
            candidate=candidate_rows.get(strategy_group_id, {}),
            registry_row=registry_rows.get(strategy_group_id, {}),
            tier_row=tier_rows.get(strategy_group_id, {}),
            observed_row=observed_rows.get(strategy_group_id, {}),
            admission_proposal=admission_proposals.get(strategy_group_id, {}),
            owner_policy_scope=owner_policy_scopes.get(strategy_group_id, {}),
            portfolio_seat=portfolio_seats.get(strategy_group_id, {}),
            trial_envelope=trial_envelope,
            brf2_runtime_signal_capture=(
                brf2_runtime_signal_capture or {}
                if strategy_group_id == "BRF2-001"
                else {}
            ),
            brf2_shadow_candidate_evidence=(
                brf2_shadow_candidate_evidence or {}
                if strategy_group_id == "BRF2-001"
                else {}
            ),
            cpm_identity_routing_decision=(
                cpm_identity_routing_decision or {}
                if strategy_group_id == "CPM-RO-001"
                else {}
            ),
            cpm_required_facts_mapping=(
                cpm_required_facts_mapping or {}
                if strategy_group_id == "CPM-RO-001"
                else {}
            ),
            cpm_runtime_signal_capture=(
                cpm_runtime_signal_capture or {}
                if strategy_group_id == "CPM-RO-001"
                else {}
            ),
            cpm_shadow_candidate_evidence=(
                cpm_shadow_candidate_evidence or {}
                if strategy_group_id == "CPM-RO-001"
                else {}
            ),
            cpm_dry_run_submit_rehearsal=(
                cpm_dry_run_submit_rehearsal or {}
                if strategy_group_id == "CPM-RO-001"
                else {}
            ),
            trial_grade_row=trial_grade_rows.get(strategy_group_id, {}),
            runtime_safety_state=runtime_safety_state,
            replay_live_parity_audit=replay_live_parity_audit or {},
            mi_trial_admission_decision=mi_trial_admission_decision or {},
            strategy_fresh_signal_action_time_boundary=(
                strategy_fresh_signal_action_time_boundary or {}
            ),
            forbidden_effects=forbidden_effects,
        )
        for strategy_group_id in sorted(all_ids, key=_strategy_sort_key)
    ]
    july_trade_paths = _july_bullish_rebound_trade_path_closure(rows)
    summary = _summary(rows, selected_strategy_group_id=selected_strategy_group_id)
    consistency_checks = _consistency_checks(
        rows=rows,
        summary=summary,
        runtime_safety_state=runtime_safety_state,
    )
    status = (
        "blocked_forbidden_effect"
        if forbidden_effects
        else "blocked_internal_consistency"
        if not all(consistency_checks.values())
        else "tradeability_decision_ready"
        if rows
        else "tradeability_decision_needs_input"
    )
    return {
        "schema": SCHEMA,
        "scope": "strategygroup_tradeability_decision_read_model",
        "status": status,
        "generated_at_utc": generated_at_utc
        or datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "decision_rows": rows,
        "july_bullish_rebound_trade_path_closure": july_trade_paths,
        "owner_summary": {
            "state": "交易资格已判定",
            "top_strategy_group_id": summary["top_strategy_group_id"],
            "top_decision": summary["top_decision"],
            "top_first_blocker": summary["top_first_blocker_class"],
            "owner_policy_blocker_present": summary["owner_first_blocker_count"] > 0,
            "owner_intervention_required": False,
        },
        "checks": {
            "one_current_decision_per_strategy_group": len(rows)
            == len({row["strategy_group_id"] for row in rows}),
            "forbidden_effects": forbidden_effects,
            **consistency_checks,
            "market_wait_only_after_admission": all(
                row["decision"] != "not_tradable_market_wait"
                or row["stage"]
                in {"armed_observation", "tiny_live_ready", "live_submit_ready"}
                for row in rows
            ),
            "market_wait_validated_has_full_checklist": all(
                row["first_blocker_class"] != "market_wait_validated"
                or _as_dict(row.get("market_wait_validation")).get("valid")
                is True
                for row in rows
            ),
            "july_bullish_rebound_paths_consumed": july_trade_paths["checks"][
                "machine_consumed_path_count"
            ]
            >= 5,
            "cpm_non_market_blocker_preserved": july_trade_paths["checks"][
                "cpm_non_market_blocker_preserved"
            ],
        },
        "interaction": _interaction(),
        "safety_invariants": {
            "decision_generator_changes_runtime_safety_state": False,
            "decision_generator_creates_execution_attempt": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
    }


def _decision_row(
    *,
    strategy_group_id: str,
    candidate: dict[str, Any],
    registry_row: dict[str, Any],
    tier_row: dict[str, Any],
    observed_row: dict[str, Any],
    admission_proposal: dict[str, Any],
    owner_policy_scope: dict[str, Any],
    portfolio_seat: dict[str, Any],
    trial_envelope: dict[str, Any],
    brf2_runtime_signal_capture: dict[str, Any],
    brf2_shadow_candidate_evidence: dict[str, Any],
    cpm_identity_routing_decision: dict[str, Any],
    cpm_required_facts_mapping: dict[str, Any],
    cpm_runtime_signal_capture: dict[str, Any],
    cpm_shadow_candidate_evidence: dict[str, Any],
    cpm_dry_run_submit_rehearsal: dict[str, Any],
    trial_grade_row: dict[str, Any],
    runtime_safety_state: dict[str, Any],
    replay_live_parity_audit: dict[str, Any],
    mi_trial_admission_decision: dict[str, Any],
    strategy_fresh_signal_action_time_boundary: dict[str, Any],
    forbidden_effects: list[str],
) -> dict[str, Any]:
    blockers = [str(item) for item in candidate.get("trial_blockers") or []]
    registry_present = bool(registry_row)
    tier_present = bool(tier_row)
    stage = _stage(
        strategy_group_id=strategy_group_id,
        candidate=candidate,
        registry_row=registry_row,
        tier_row=tier_row,
        observed_row=observed_row,
        admission_proposal=admission_proposal,
        owner_policy_scope=owner_policy_scope,
        portfolio_seat=portfolio_seat,
        runtime_safety_state=runtime_safety_state,
        mi_trial_admission_decision=mi_trial_admission_decision,
    )
    brf2_shadow_candidate_evidence_provenance = (
        _brf2_shadow_candidate_evidence_provenance(
            brf2_shadow_candidate_evidence
        )
    )
    brf2_candidate_authorization_state = (
        candidate_authorization_state_from_runtime_safety_artifact(
            runtime_safety_state,
            strategy_group_id="BRF2-001",
        )
    )
    classifier = _first_blocker(
        strategy_group_id=strategy_group_id,
        stage=stage,
        candidate=candidate,
        admission_proposal=admission_proposal,
        owner_policy_scope=owner_policy_scope,
        registry_row=registry_row,
        registry_present=registry_present,
        tier_present=tier_present,
        tier_row=tier_row,
        observed_row=observed_row,
        portfolio_seat=portfolio_seat,
        brf2_runtime_signal_capture=brf2_runtime_signal_capture,
        brf2_candidate_authorization_state=brf2_candidate_authorization_state,
        cpm_identity_routing_decision=cpm_identity_routing_decision,
        cpm_required_facts_mapping=cpm_required_facts_mapping,
        cpm_runtime_signal_capture=cpm_runtime_signal_capture,
        cpm_shadow_candidate_evidence=cpm_shadow_candidate_evidence,
        cpm_dry_run_submit_rehearsal=cpm_dry_run_submit_rehearsal,
        replay_live_parity_audit=replay_live_parity_audit,
        mi_trial_admission_decision=mi_trial_admission_decision,
        strategy_fresh_signal_action_time_boundary=(
            strategy_fresh_signal_action_time_boundary
        ),
        blockers=blockers,
        runtime_safety_state=runtime_safety_state,
        forbidden_effects=forbidden_effects,
    )
    runtime_safety_reference = _runtime_safety_reference(
        strategy_group_id=strategy_group_id,
        runtime_safety_state=runtime_safety_state,
    )
    policy_scope = _policy_scope(
        strategy_group_id,
        candidate,
        portfolio_seat,
        owner_policy_scope,
        trial_envelope,
    )
    owner_policy_recorded = _policy_recorded(owner_policy_scope) or (
        admission_proposal.get("owner_policy_recorded") is True
        and admission_proposal.get("owner_policy_scope_missing") is False
    )
    cpm_admission_policy_closed = (
        strategy_group_id == "CPM-RO-001"
        and registry_present
        and tier_present
        and owner_policy_recorded
        and cpm_identity_routing_decision.get("identity_decision")
        == "standalone_trial_asset"
        and cpm_identity_routing_decision.get("cpm_long_vs_mpg_long_distinct")
        is True
    )
    resolved_blockers = _resolved_blockers(
        blockers,
        strategy_group_id=strategy_group_id,
        owner_policy_recorded=owner_policy_recorded,
        cpm_admission_policy_closed=cpm_admission_policy_closed,
    )
    signal_grade_status = _signal_grade_status(
        strategy_group_id=strategy_group_id,
        trial_grade_row=trial_grade_row,
        portfolio_seat=portfolio_seat,
    )
    runtime_readiness = _as_dict(portfolio_seat.get("runtime_readiness"))
    required_facts_status = required_facts_status_for_tradeability(
        strategy_group_id=strategy_group_id,
        stage=stage,
        armed_observation_ready=runtime_readiness.get("armed_observation_ready")
        is True,
        required_facts_mapping_ready=(
            portfolio_seat.get("required_facts_mapping_ready") is True
        ),
        has_required_facts_draft=bool(candidate.get("required_facts_draft")),
        blocker_text=" ".join(blockers),
        has_registry_required_facts_summary=bool(
            registry_row.get("required_facts_summary")
        ),
    )
    if (
        strategy_group_id == "CPM-RO-001"
        and cpm_required_facts_mapping.get("status")
        == "cpm_required_facts_mapping_ready"
        and cpm_required_facts_mapping.get("required_facts_mapping_ready") is True
    ):
        required_facts_status = "ready"
    market_wait_validation = _market_wait_validation(
        strategy_group_id=strategy_group_id,
        stage=stage,
        classifier=classifier,
        registry_present=registry_present,
        tier_present=tier_present,
        tier_row=tier_row,
        portfolio_seat=portfolio_seat,
        owner_policy_recorded=owner_policy_recorded,
        required_facts_status=required_facts_status,
        cpm_admission_policy_closed=cpm_admission_policy_closed,
        cpm_required_facts_mapping=cpm_required_facts_mapping,
        cpm_runtime_signal_capture=cpm_runtime_signal_capture,
        cpm_dry_run_submit_rehearsal=cpm_dry_run_submit_rehearsal,
        brf2_runtime_signal_capture=brf2_runtime_signal_capture,
        replay_live_parity_audit=replay_live_parity_audit,
        strategy_fresh_signal_action_time_boundary=(
            strategy_fresh_signal_action_time_boundary
        ),
        runtime_safety_state=runtime_safety_state,
    )
    if (
        classifier["first_blocker_class"] == "market_wait_validated"
        and not market_wait_validation["valid"]
    ):
        classifier = _classifier(
            "not_tradable_facts",
            "artifact_missing",
            "market_wait_validated checklist is incomplete",
            "engineering",
            "complete_market_wait_validation_checklist",
            "market_wait_validated",
        )
        market_wait_validation = _market_wait_validation(
            strategy_group_id=strategy_group_id,
            stage=stage,
            classifier=classifier,
            registry_present=registry_present,
            tier_present=tier_present,
            tier_row=tier_row,
            portfolio_seat=portfolio_seat,
            owner_policy_recorded=owner_policy_recorded,
            required_facts_status=required_facts_status,
            cpm_admission_policy_closed=cpm_admission_policy_closed,
            cpm_required_facts_mapping=cpm_required_facts_mapping,
            cpm_runtime_signal_capture=cpm_runtime_signal_capture,
            cpm_dry_run_submit_rehearsal=cpm_dry_run_submit_rehearsal,
            brf2_runtime_signal_capture=brf2_runtime_signal_capture,
            replay_live_parity_audit=replay_live_parity_audit,
            strategy_fresh_signal_action_time_boundary=(
                strategy_fresh_signal_action_time_boundary
            ),
            runtime_safety_state=runtime_safety_state,
        )
    trade_paths = _trade_paths_for_strategy(
        strategy_group_id=strategy_group_id,
        row_classifier=classifier,
        required_facts_status=required_facts_status,
    )
    observe_only_exit = _observe_only_exit_for_strategy(
        strategy_group_id=strategy_group_id,
        stage=stage,
        candidate=candidate,
        registry_row=registry_row,
        observed_row=observed_row,
    )
    row = {
        "strategy_group_id": strategy_group_id,
        "stage": stage,
        "decision": classifier["decision"],
        "can_trade_now": classifier["decision"] == "tradable_now",
        "first_blocker_class": classifier["first_blocker_class"],
        "first_blocker_detail": classifier["first_blocker_detail"],
        "legacy_blocker_raw": classifier["legacy_blocker_raw"],
        "blocker_owner": classifier["blocker_owner"],
        "next_action": classifier["next_action"],
        "after_next_state": classifier["after_next_state"],
        "secondary_blockers": _secondary_blockers(
            blockers,
            classifier,
            resolved_blockers,
            strategy_group_id=strategy_group_id,
            cpm_admission_policy_closed=cpm_admission_policy_closed,
        ),
        "resolved_blockers": resolved_blockers,
        "policy_scope": policy_scope,
        "required_facts_status": required_facts_status,
        "market_wait_validation": market_wait_validation,
        "trade_paths": trade_paths,
        "observe_only_exit": observe_only_exit,
        "runtime_scope_status": {
            "registry_admitted": registry_present,
            "trial_asset_admission_proposal_ready": bool(admission_proposal),
            "owner_policy_recorded": owner_policy_recorded,
            "owner_policy_scope_missing": bool(admission_proposal)
            and not owner_policy_recorded,
            "brf2_trial_identity": str(
                _as_dict(owner_policy_scope.get("policy")).get("trial_identity") or ""
            ),
            "registry_default_tier": str(registry_row.get("default_tier") or "unknown"),
            "tier_policy_present": tier_present,
            "tier_policy_tier": str(tier_row.get("tier") or "unknown"),
            "tier_policy_mode": str(tier_row.get("mode") or "unknown"),
            "trial_eligible": registry_row.get("trial_eligible") is True,
            "observe_only_would_enter": bool(observed_row),
            "live_trial_portfolio_seat": bool(portfolio_seat),
            "live_trial_portfolio_stage": str(portfolio_seat.get("stage") or ""),
            "trial_envelope_id": str(trial_envelope.get("trial_envelope_id") or ""),
            "trial_envelope_primary": trial_envelope.get(
                "primary_judgment_source"
            )
            is True,
            "brf2_runtime_signal_capture_status": str(
                brf2_runtime_signal_capture.get("status") or ""
            ),
            "brf2_current_signal_state": str(
                _as_dict(
                    brf2_runtime_signal_capture.get("signal_detector_preview")
                ).get("current_signal_state")
                or ""
            ),
            "cpm_identity_decision": str(
                cpm_identity_routing_decision.get("identity_decision") or ""
            ),
            "cpm_runtime_signal_capture_status": str(
                cpm_runtime_signal_capture.get("status") or ""
            ),
            "cpm_current_signal_state": str(
                _as_dict(
                    cpm_runtime_signal_capture.get("signal_detector_preview")
                ).get("current_signal_state")
                or ""
            ),
            "mi_trial_admission_decision": str(
                mi_trial_admission_decision.get("trial_admission_decision") or ""
            )
            if strategy_group_id == "MI-001"
            else "",
            "mi_promotion_scope": str(
                mi_trial_admission_decision.get("promotion_scope") or ""
            )
            if strategy_group_id == "MI-001"
            else "",
        },
        "signal_grade_status": signal_grade_status,
        "evidence_snapshot": _evidence_snapshot(
            strategy_group_id=strategy_group_id,
            candidate=candidate,
            observed_row=observed_row,
            cpm_admission_policy_closed=cpm_admission_policy_closed,
            classifier=classifier,
        ),
        "runtime_safety_reference": runtime_safety_reference,
        "authority_boundary": (
            "tradeability_decision_is_read_model; runtime_safety_state_reports_live_submit_ready_for_strategy; execution_attempt_required_for_lifecycle_entry"
            if classifier["decision"] == "tradable_now"
            else "tradeability_decision_is_read_model; runtime_safety_state_controls_live_submit_readiness; no_finalgate_no_operation_layer"
        ),
    }
    if strategy_group_id == "BRF2-001":
        row["brf2_shadow_candidate_evidence_provenance"] = (
            brf2_shadow_candidate_evidence_provenance
        )
    return row


def _first_blocker(
    *,
    strategy_group_id: str,
    stage: str,
    candidate: dict[str, Any],
    admission_proposal: dict[str, Any],
    owner_policy_scope: dict[str, Any],
    registry_row: dict[str, Any],
    registry_present: bool,
    tier_present: bool,
    tier_row: dict[str, Any],
    observed_row: dict[str, Any],
    portfolio_seat: dict[str, Any],
    brf2_runtime_signal_capture: dict[str, Any],
    brf2_candidate_authorization_state: dict[str, Any],
    cpm_identity_routing_decision: dict[str, Any],
    cpm_required_facts_mapping: dict[str, Any],
    cpm_runtime_signal_capture: dict[str, Any],
    cpm_shadow_candidate_evidence: dict[str, Any],
    cpm_dry_run_submit_rehearsal: dict[str, Any],
    replay_live_parity_audit: dict[str, Any],
    mi_trial_admission_decision: dict[str, Any],
    strategy_fresh_signal_action_time_boundary: dict[str, Any],
    blockers: list[str],
    runtime_safety_state: dict[str, Any],
    forbidden_effects: list[str],
) -> dict[str, str]:
    if forbidden_effects:
        return _classifier(
            "not_tradable_safety_stop",
            "forbidden_effect_detected",
            ",".join(forbidden_effects),
            "safety",
            "remove_forbidden_authority_effect_before_any_tradeability_review",
            "safety_clear_for_tradeability_review",
        )
    if stage == "role_only_intake_candidate":
        return _classifier(
            "not_tradable_strategy_quality",
            "role_only_or_classifier_asset_not_trial_candidate",
            "candidate is useful for role/classifier review, not a trade candidate",
            "strategy_review",
            "complete_role_merge_or_classifier_review",
            "classifier_or_role_support_asset",
        )
    if strategy_group_id == "CPM-RO-001":
        cpm = _cpm_first_blocker(
            stage=stage,
            registry_present=registry_present,
            tier_present=tier_present,
            candidate=candidate,
            registry_row=registry_row,
            tier_row=tier_row,
            observed_row=observed_row,
            admission_proposal=admission_proposal,
            owner_policy_scope=owner_policy_scope,
            portfolio_seat=portfolio_seat,
            identity_routing_decision=cpm_identity_routing_decision,
            required_facts_mapping=cpm_required_facts_mapping,
            runtime_signal_capture=cpm_runtime_signal_capture,
            shadow_candidate_evidence=cpm_shadow_candidate_evidence,
            dry_run_submit_rehearsal=cpm_dry_run_submit_rehearsal,
            replay_live_parity_audit=replay_live_parity_audit,
            blockers=blockers,
        )
        if cpm:
            return cpm
    if strategy_group_id == "MI-001":
        mi_guard = _mi_trial_admission_guard(mi_trial_admission_decision)
        if mi_guard:
            return mi_guard
    if strategy_group_id == "MI-001" and _mi_trial_admission_candidate(
        mi_trial_admission_decision
    ):
        if _mi_readonly_observation_scope_attached(mi_trial_admission_decision):
            return _classifier(
                "not_tradable_policy",
                "policy_scope_missing",
                (
                    "MI trial admission candidate has readonly observation "
                    "scope; Owner trial policy is not recorded"
                ),
                "owner",
                "record_scoped_owner_policy",
                "policy_scope_recorded",
            )
        return _classifier(
            "not_tradable_asset_admission",
            "scope_not_attached",
            "MI trial admission candidate is recorded; runtime observation scope is not attached",
            "engineering",
            "attach_mi_trial_candidate_to_runtime_observation_scope",
            "armed_observation",
        )
    if stage == "observe_only_would_enter":
        exit_rule = _observe_only_exit_for_strategy(
            strategy_group_id=strategy_group_id,
            stage=stage,
            candidate=candidate,
            registry_row=registry_row,
            observed_row=observed_row,
        )
        return _classifier(
            "not_tradable_strategy_quality",
            str(exit_rule.get("first_blocker") or "observe_only_exit_decision_required"),
            (
                "latest would-enter is observe-only and has a fact-backed main-control exit decision"
                if exit_rule
                else "latest would-enter is observe-only and lacks an explicit exit decision"
            ),
            "strategy_review",
            str(exit_rule.get("next_action") or "apply_observe_only_exit_decision"),
            str(exit_rule.get("post_action_expected_state") or "strategy_asset_state_updated"),
        )
    owner_policy_recorded = _policy_recorded(owner_policy_scope) or (
        admission_proposal.get("owner_policy_recorded") is True
        and admission_proposal.get("owner_policy_scope_missing") is False
    )
    if admission_proposal and not owner_policy_recorded:
        return _classifier(
            "not_tradable_policy",
            "owner_trial_scope_or_capital_policy_missing",
            "trial asset admission proposal is ready; Owner trial policy is missing",
            "owner",
            "record_owner_trial_scope_policy",
            "admitted_trial_asset",
        )
    if _row_live_submit_ready(
        strategy_group_id=strategy_group_id,
        runtime_safety_state=runtime_safety_state,
    ):
        return _classifier(
            "tradable_now",
            "official_runtime_chain_ready",
            "fresh signal, facts, authority, FinalGate, and Operation Layer are ready",
            "runtime",
            "continue_official_live_submit_chain",
            "live_submit_ready",
        )
    if strategy_group_id == "BRF2-001":
        brf2_capture_blocker = _brf2_runtime_signal_capture_blocker(
            brf2_runtime_signal_capture
        )
        if brf2_capture_blocker:
            if (
                brf2_capture_blocker["decision"]
                == "not_tradable_execution_gate"
            ):
                brf2_candidate_blocker = (
                    _brf2_candidate_authorization_state_blocker(
                        brf2_candidate_authorization_state
                    )
                )
                if brf2_candidate_blocker:
                    return brf2_candidate_blocker
            return brf2_capture_blocker
    external_blocker = _external_first_blocker(
        strategy_group_id=strategy_group_id,
        replay_live_parity_audit=replay_live_parity_audit,
        strategy_fresh_signal_action_time_boundary=(
            strategy_fresh_signal_action_time_boundary
        ),
    )
    if external_blocker:
        return external_blocker
    if strategy_group_id == "MPG-001" and _mpg_waits_for_market(
        tier_row=tier_row,
        runtime_safety_state=runtime_safety_state,
    ):
        return _classifier(
            "not_tradable_market_wait",
            "fresh_executable_signal_absent",
            "MPG is the admitted live lane, but no fresh executable signal exists",
            "market",
            "continue_armed_observation_until_fresh_signal",
            "live_submit_ready",
        )

    portfolio_blocker = _portfolio_first_blocker(portfolio_seat)
    if portfolio_blocker:
        return portfolio_blocker

    if strategy_group_id == "BRF2-001" and owner_policy_recorded:
        return _classifier(
            "not_tradable_facts",
            "required_facts_mapping_gap",
            "Owner trial policy is recorded; RequiredFacts mapping must close before armed observation",
            "engineering",
            "close_brf2_required_facts_mapping_for_armed_observation",
            "armed_observation",
        )

    text = " ".join([stage, " ".join(blockers), str(candidate.get("identity_status") or "")]).lower()
    if (
        not registry_present
        or "registry_identity" in text
        or "execution_tier_not_in_policy_or_registry" in text
        or "identity_review" in text
        or "source_non_executing_trial_readiness_not_closed" in text
    ):
        return _classifier(
            "not_tradable_asset_admission",
            "strategy_group_not_admitted_as_final_trial_asset",
            "candidate is visible but not admitted into registry/tier/runtime trial scope",
            "engineering",
            "build_trial_asset_admission_proposal",
            "trial_asset_admission_candidate",
        )
    if any(token in text for token in ("fact", "stale", "classifier", "rewrite", "squeeze", "forward_outcome_pending", "range_context")):
        return _classifier(
            "not_tradable_facts",
            "required_facts_or_classifier_mapping_unclosed",
            "facts, freshness, classifier, or side-specific review is not closed",
            "engineering",
            "close_requiredfacts_classifier_and_replay_mapping",
            "armed_observation",
        )
    if any(token in text for token in ("owner_policy", "owner_capital", "trial_identity", "capital_scope")):
        return _classifier(
            "not_tradable_policy",
            "owner_trial_scope_or_capital_policy_missing",
            "trial capital, profile, symbol/side, attempt cap, or identity policy is missing",
            "owner",
            "record_owner_trial_scope_policy",
            "trial_asset_admission_candidate",
        )
    if any(token in text for token in ("finalgate", "operation_layer", "protection", "exchange", "account")):
        return _classifier(
            "not_tradable_execution_gate",
            "action_time_execution_gate_not_reached",
            "official action-time gate has not been reached",
            "runtime",
            "wait_for_action_time_gate_after_signal_and_facts",
            "live_submit_ready",
        )
    if "fresh_signal_absent" in text:
        return _classifier(
            "not_tradable_market_wait",
            "fresh_executable_signal_absent",
            "admission and facts are closed; only fresh signal is missing",
            "market",
            "continue_armed_observation_until_fresh_signal",
            "live_submit_ready",
        )
    return _classifier(
        "not_tradable_strategy_quality",
        "experiment_worthiness_or_loss_envelope_unclosed",
        "experiment thesis or loss envelope is not closed enough for trial",
        "strategy_review",
        "complete_experiment_worthiness_and_loss_envelope_review",
        "trial_asset_admission_candidate",
    )


def _brf2_runtime_signal_capture_blocker(artifact: dict[str, Any]) -> dict[str, str]:
    if _status(artifact) != "brf2_runtime_signal_capture_ready":
        return {}
    preview = _as_dict(artifact.get("signal_detector_preview"))
    signal_state = str(preview.get("current_signal_state") or "")
    first_blocker_class = str(
        preview.get("first_blocker_class") or "fresh_brf2_short_signal_absent"
    )
    next_action = str(
        preview.get("signal_capture_checkpoint")
        or "continue_brf2_armed_observation_until_fresh_signal"
    )
    blocker_owner = str(preview.get("first_blocker_owner") or "market")
    if signal_state == "fact_input_missing":
        return _classifier(
            "not_tradable_facts",
            first_blocker_class,
            "BRF2 RequiredFacts mapping is defined, but watcher fact input is not attached to runtime signal capture",
            blocker_owner,
            next_action,
            "armed_observation",
        )
    if signal_state == "fresh_signal_present":
        return _classifier(
            "not_tradable_execution_gate",
            "brf2_candidate_authorization_evidence_not_created",
            "BRF2 fresh signal is present in the non-executing detector; shadow evidence exists before official candidate authorization and action-time evidence",
            "runtime",
            "build_brf2_shadow_candidate_evidence_for_action_time_chain",
            "shadow_candidate_evidence_ready",
        )
    if signal_state in {"fresh_signal_absent", "blocked_by_disable_fact"}:
        return _classifier(
            "not_tradable_market_wait",
            first_blocker_class,
            "BRF2 runtime signal capture is attached; no fresh actionable short signal exists",
            blocker_owner,
            next_action,
            "live_submit_ready",
        )
    return {}


def _cpm_first_blocker(
    *,
    stage: str,
    registry_present: bool,
    tier_present: bool,
    candidate: dict[str, Any],
    registry_row: dict[str, Any],
    tier_row: dict[str, Any],
    observed_row: dict[str, Any],
    admission_proposal: dict[str, Any],
    owner_policy_scope: dict[str, Any],
    portfolio_seat: dict[str, Any],
    identity_routing_decision: dict[str, Any],
    required_facts_mapping: dict[str, Any],
    runtime_signal_capture: dict[str, Any],
    shadow_candidate_evidence: dict[str, Any],
    dry_run_submit_rehearsal: dict[str, Any],
    replay_live_parity_audit: dict[str, Any],
    blockers: list[str],
) -> dict[str, str]:
    text = " ".join(
        [
            stage,
            " ".join(blockers),
            str(candidate.get("identity_status") or ""),
            str(candidate.get("candidate_status") or ""),
            str(observed_row.get("decision") or ""),
            str(observed_row.get("reason") or ""),
            str(registry_row.get("first_tradeability_blocker") or ""),
            str(portfolio_seat.get("first_tradeability_blocker") or ""),
        ]
    ).lower()
    identity_closed = (
        identity_routing_decision.get("identity_decision")
        == "standalone_trial_asset"
        and identity_routing_decision.get("cpm_long_vs_mpg_long_distinct") is True
    )
    if (
        not registry_present
        or not tier_present
        or not identity_closed
        or (not identity_closed and "registry_identity" in text)
        or (not identity_closed and "identity_review" in text)
        or (not identity_closed and "identity incomplete" in text)
        or (not identity_closed and "scope_unclear" in text)
    ):
        return _classifier(
            "not_tradable_asset_admission",
            "cpm_registry_identity_gap",
            "CPM is visible as an observation/review asset, but registry identity or tier scope is not closed",
            "engineering",
            "close_cpm_registry_identity_and_tier_scope_before_armed_observation",
            "trial_asset_admission_candidate",
        )

    runtime_readiness = _as_dict(portfolio_seat.get("runtime_readiness"))
    owner_policy_recorded = (
        owner_policy_scope.get("owner_policy_recorded") is True
        or owner_policy_scope.get("cpm_policy_scope_recorded") is True
        or admission_proposal.get("owner_policy_recorded") is True
        or portfolio_seat.get("owner_policy_recorded") is True
        or _as_dict(portfolio_seat.get("policy_scope")).get("owner_policy_recorded")
        is True
    )
    owner_policy_missing = (
        admission_proposal.get("owner_policy_scope_missing") is True
        or portfolio_seat.get("owner_policy_scope_missing") is True
        or _as_dict(portfolio_seat.get("policy_scope")).get("owner_policy_scope_missing")
        is True
        or "missing_policy" in text
        or "owner_policy" in text
    )
    if owner_policy_missing and not owner_policy_recorded:
        return _classifier(
            "not_tradable_policy",
            "cpm_policy_missing",
            "CPM identity exists, but Owner policy/profile/scope is not recorded for armed observation",
            "owner",
            "record_cpm_owner_trial_scope_policy",
            "admitted_trial_asset",
        )

    required_facts_mapping_ready = (
        required_facts_mapping.get("status") == "cpm_required_facts_mapping_ready"
        and required_facts_mapping.get("required_facts_mapping_ready") is True
    ) or (
        portfolio_seat.get("required_facts_mapping_ready") is True
        or runtime_readiness.get("required_facts_mapping_ready") is True
    )
    watcher_scope_ready = (
        runtime_signal_capture.get("status") == "cpm_runtime_signal_capture_ready"
        and _as_dict(runtime_signal_capture.get("checks")).get("watcher_scope_ready")
        is True
    ) or (
        portfolio_seat.get("watcher_scope_ready") is True
        or runtime_readiness.get("watcher_scope_ready") is True
        or runtime_readiness.get("armed_observation_ready") is True
    )
    if not required_facts_mapping_ready:
        return _classifier(
            "not_tradable_facts",
            "cpm_required_facts_mapping_gap",
            "CPM RequiredFacts mapping is not closed enough for armed observation",
            "engineering",
            "close_cpm_required_facts_mapping",
            "armed_observation",
        )
    if not watcher_scope_ready:
        return _classifier(
            "not_tradable_facts",
            "cpm_watcher_scope_gap",
            "CPM watcher scope is not attached to the runtime observation path",
            "engineering",
            "attach_cpm_watcher_scope_before_market_wait_projection",
            "armed_observation",
        )

    dry_run_shape_ready = (
        dry_run_submit_rehearsal.get("status")
        in {
            "cpm_dry_run_submit_rehearsal_passed",
            "cpm_dry_run_submit_rehearsal_shape_ready",
        }
        and (
            dry_run_submit_rehearsal.get("dry_run_submit_rehearsal")
            in {"passed", "fresh_signal_passed", "shape_ready"}
            or _as_dict(dry_run_submit_rehearsal.get("checks")).get(
                "submit_rehearsal_shape_ready"
            )
            is True
        )
    )
    if not dry_run_shape_ready:
        return _classifier(
            "not_tradable_facts",
            "cpm_dry_run_submit_rehearsal_gap",
            "CPM RequiredFacts and watcher scope are attached, but the submit rehearsal shape is not yet closed",
            "engineering",
            "run_cpm_non_executing_submit_rehearsal",
            "armed_observation",
        )

    preview = _as_dict(runtime_signal_capture.get("signal_detector_preview"))
    signal_state = str(preview.get("current_signal_state") or "")
    if signal_state == "fresh_signal_present":
        return _classifier(
            "not_tradable_execution_gate",
            "cpm_candidate_authorization_evidence_not_created",
            "CPM fresh signal is present in the non-executing detector; official candidate authorization evidence is still required",
            "runtime",
            "prepare_cpm_candidate_authorization_evidence",
            "shadow_candidate_evidence_ready",
        )
    if signal_state == "blocked_by_disable_fact":
        return _classifier(
            "not_tradable_market_wait",
            str(preview.get("first_blocker_class") or "cpm_disable_fact_active"),
            "CPM watcher scope is attached, but a disable fact is active",
            str(preview.get("first_blocker_owner") or "market"),
            str(
                preview.get("signal_capture_checkpoint")
                or "continue_cpm_armed_observation_until_disable_clears"
            ),
            "live_submit_ready",
        )

    external_blocker = _external_first_blocker(
        strategy_group_id="CPM-RO-001",
        replay_live_parity_audit=replay_live_parity_audit,
        strategy_fresh_signal_action_time_boundary={},
    )
    if external_blocker:
        return external_blocker

    return _classifier(
        "not_tradable_market_wait",
        "fresh_cpm_long_signal_absent",
        "CPM identity, policy, RequiredFacts mapping, and watcher scope are closed; no fresh CPM long rebound signal exists",
        "market",
        "continue_cpm_long_armed_observation_until_reclaim_signal",
        "live_submit_ready",
    )


def _brf2_candidate_authorization_state_blocker(
    state: dict[str, Any],
) -> dict[str, str]:
    if state.get("status") != "candidate_authorization_evidence_pending":
        return {}
    if state.get("authorization_evidence_created") is True:
        return {}
    return _classifier(
        "not_tradable_execution_gate",
        "brf2_shadow_candidate_evidence_ready_authorization_evidence_not_created",
        "BRF2 fresh signal shadow evidence is ready; official candidate authorization evidence and action-time gates are not created",
        "runtime",
        "prepare_fresh_candidate_authorization_evidence",
        "candidate_authorization_evidence_pending_action_time_finalgate",
    )


@dataclass(frozen=True)
class _BRF2ShadowCandidateEvidenceProvenance:
    status: str
    active: bool
    strategy_group_id: str
    shadow_candidate_evidence_ready: bool
    shadow_candidate_evidence_id: str
    signal_state: str
    first_blocker_class: str
    first_blocker_owner: str
    next_runtime_step: str
    projection_role: str = "shadow_candidate_evidence_provenance"
    state_source: str = "brf2_shadow_candidate_evidence"
    primary_judgment_source: bool = False
    non_executing_evidence: bool = True

    @classmethod
    def from_artifact(
        cls, artifact: dict[str, Any]
    ) -> "_BRF2ShadowCandidateEvidenceProvenance":
        status = _status(artifact) or "missing"
        first_blocker = _as_dict(artifact.get("first_blocker"))
        candidate = _as_dict(artifact.get("shadow_candidate_evidence"))
        return cls(
            status=status,
            active=status
            in {
                "brf2_shadow_candidate_evidence_ready",
                "brf2_shadow_candidate_evidence_waiting_for_fresh_signal",
            },
            strategy_group_id=str(artifact.get("strategy_group_id") or ""),
            shadow_candidate_evidence_ready=(
                artifact.get("shadow_candidate_evidence_ready") is True
            ),
            shadow_candidate_evidence_id=str(
                candidate.get("shadow_candidate_evidence_id") or ""
            ),
            signal_state=str(candidate.get("signal_state") or "unknown"),
            first_blocker_class=str(first_blocker.get("class") or "missing"),
            first_blocker_owner=str(first_blocker.get("owner") or "unknown"),
            next_runtime_step=str(artifact.get("next_runtime_step") or ""),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "active": self.active,
            "strategy_group_id": self.strategy_group_id,
            "shadow_candidate_evidence_ready": self.shadow_candidate_evidence_ready,
            "shadow_candidate_evidence_id": self.shadow_candidate_evidence_id,
            "signal_state": self.signal_state,
            "first_blocker_class": self.first_blocker_class,
            "first_blocker_owner": self.first_blocker_owner,
            "next_runtime_step": self.next_runtime_step,
            "projection_role": self.projection_role,
            "state_source": self.state_source,
            "primary_judgment_source": self.primary_judgment_source,
            "non_executing_evidence": self.non_executing_evidence,
        }


def _brf2_shadow_candidate_evidence_provenance(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    return _BRF2ShadowCandidateEvidenceProvenance.from_artifact(artifact).as_dict()


def _market_wait_validation(
    *,
    strategy_group_id: str,
    stage: str,
    classifier: dict[str, str],
    registry_present: bool,
    tier_present: bool,
    tier_row: dict[str, Any],
    portfolio_seat: dict[str, Any],
    owner_policy_recorded: bool,
    required_facts_status: str,
    cpm_admission_policy_closed: bool,
    cpm_required_facts_mapping: dict[str, Any],
    cpm_runtime_signal_capture: dict[str, Any],
    cpm_dry_run_submit_rehearsal: dict[str, Any],
    brf2_runtime_signal_capture: dict[str, Any],
    replay_live_parity_audit: dict[str, Any],
    strategy_fresh_signal_action_time_boundary: dict[str, Any],
    runtime_safety_state: dict[str, Any],
) -> dict[str, Any]:
    if classifier["first_blocker_class"] != "market_wait_validated":
        return {"valid": False, "not_applicable": True, "checks": {}}

    runtime_readiness = _as_dict(portfolio_seat.get("runtime_readiness"))
    cpm_mapping_ready = (
        cpm_required_facts_mapping.get("status") == "cpm_required_facts_mapping_ready"
        and cpm_required_facts_mapping.get("required_facts_mapping_ready") is True
    )
    cpm_capture_ready = (
        cpm_runtime_signal_capture.get("status") == "cpm_runtime_signal_capture_ready"
        and _as_dict(cpm_runtime_signal_capture.get("checks")).get(
            "watcher_scope_ready"
        )
        is True
    )
    cpm_rehearsal_ready = (
        cpm_dry_run_submit_rehearsal.get("status")
        in {
            "cpm_dry_run_submit_rehearsal_passed",
            "cpm_dry_run_submit_rehearsal_shape_ready",
        }
        and (
            cpm_dry_run_submit_rehearsal.get("dry_run_submit_rehearsal")
            in {"passed", "fresh_signal_passed", "shape_ready"}
            or _as_dict(cpm_dry_run_submit_rehearsal.get("checks")).get(
                "submit_rehearsal_shape_ready"
            )
            is True
        )
    )
    brf2_capture_ready = (
        brf2_runtime_signal_capture.get("status")
        == "brf2_runtime_signal_capture_ready"
    )
    external_lane_checks = _market_wait_external_lane_checks(
        strategy_group_id=strategy_group_id,
        replay_live_parity_audit=replay_live_parity_audit,
        strategy_fresh_signal_action_time_boundary=(
            strategy_fresh_signal_action_time_boundary
        ),
    )
    generic_runtime_ready = (
        bool(portfolio_seat)
        or runtime_readiness.get("armed_observation_ready") is True
        or runtime_readiness.get("watcher_scope_ready") is True
    )

    checks = {
        "asset_admission": stage
        in {"armed_observation", "tiny_live_ready", "live_submit_ready"},
        "scope": bool(registry_present or tier_present or portfolio_seat),
        "policy": bool(
            owner_policy_recorded
            or cpm_admission_policy_closed
            or portfolio_seat
        ),
        "symbol": bool(
            strategy_group_id in {"CPM-RO-001", "BRF2-001"}
            or external_lane_checks["symbol"]
        ),
        "detector": bool(
            cpm_capture_ready
            if strategy_group_id == "CPM-RO-001"
            else brf2_capture_ready
            if strategy_group_id == "BRF2-001"
            else external_lane_checks["detector"]
        ),
        "watcher_input": bool(
            cpm_capture_ready
            if strategy_group_id == "CPM-RO-001"
            else brf2_capture_ready
            if strategy_group_id == "BRF2-001"
            else external_lane_checks["watcher_input"]
        ),
        "facts": bool(
            required_facts_status in {"ready", "action_time_only"}
            or cpm_mapping_ready
            or external_lane_checks["facts"]
        ),
        "failed_facts_clear": bool(
            strategy_group_id in {"CPM-RO-001", "BRF2-001"}
            or external_lane_checks["failed_facts_clear"]
        ),
        "classification": classifier["first_blocker_class"]
        in CONTRACT_BLOCKER_CLASSES,
        "action_time_path": bool(
            cpm_rehearsal_ready
            if strategy_group_id == "CPM-RO-001"
            else brf2_capture_ready
            if strategy_group_id == "BRF2-001"
            else external_lane_checks["action_time_path"]
        ),
        "fresh_signal": classifier["legacy_blocker_raw"]
        in LEGACY_BLOCKER_CLASS_MAP,
    }
    return {
        "valid": all(checks.values()),
        "not_applicable": False,
        "checks": checks,
    }


def _classifier(
    decision: str,
    first_blocker_class: str,
    first_blocker_detail: str,
    blocker_owner: str,
    next_action: str,
    after_next_state: str,
) -> dict[str, str]:
    legacy_blocker_raw = first_blocker_class
    if decision != "tradable_now":
        contract_class = _contract_blocker_class(first_blocker_class, decision)
        decision = BLOCKER_DECISION_BY_CLASS.get(contract_class, decision)
        blocker_owner = BLOCKER_OWNER_BY_CLASS.get(contract_class, blocker_owner)
        first_blocker_class = contract_class
    return {
        "decision": decision,
        "first_blocker_class": first_blocker_class,
        "first_blocker_detail": first_blocker_detail,
        "blocker_owner": blocker_owner,
        "next_action": next_action,
        "after_next_state": after_next_state,
        "legacy_blocker_raw": legacy_blocker_raw,
    }


def _external_first_blocker(
    *,
    strategy_group_id: str,
    replay_live_parity_audit: dict[str, Any],
    strategy_fresh_signal_action_time_boundary: dict[str, Any],
) -> dict[str, str]:
    replay_guard = _external_artifact_guard(
        artifact=replay_live_parity_audit,
        artifact_name="replay_live_parity_audit",
        expected_schema=REPLAY_LIVE_PARITY_SCHEMA,
        expected_status="replay_live_parity_audit_ready",
        required_strategy_ids=REPLAY_LIVE_PARITY_STRATEGY_IDS,
        row_keys=("per_symbol_mismatch_table",),
        strategy_group_id=strategy_group_id,
    )
    if replay_guard:
        return replay_guard
    action_time_guard = _external_artifact_guard(
        artifact=strategy_fresh_signal_action_time_boundary,
        artifact_name="strategy_fresh_signal_action_time_boundary",
        expected_schema=ACTION_TIME_BOUNDARY_SCHEMA,
        expected_status="strategy_fresh_signal_action_time_boundary_ready",
        required_strategy_ids=ACTION_TIME_BOUNDARY_STRATEGY_IDS,
        row_keys=(
            "strategy_rows",
            "per_strategy_boundary_table",
            "boundary_rows",
            "strategy_group_rows",
            "decision_rows",
        ),
        strategy_group_id=strategy_group_id,
    )
    if action_time_guard:
        return action_time_guard
    rows = _external_blocker_rows(
        strategy_group_id=strategy_group_id,
        replay_live_parity_audit=replay_live_parity_audit,
        strategy_fresh_signal_action_time_boundary=(
            strategy_fresh_signal_action_time_boundary
        ),
    )
    if not rows:
        return {}
    row = sorted(
        rows,
        key=lambda item: (
            BLOCKER_PRIORITY.get(str(item.get("blocker_class") or ""), 999),
            str(item.get("symbol") or ""),
        ),
    )[0]
    blocker_class = str(row.get("blocker_class") or "")
    failed_facts = _string_list(row.get("failed_facts"))
    symbol = str(row.get("symbol") or "strategy_scope")
    detail = str(row.get("detail") or "")
    if not detail:
        detail = (
            (
                f"{strategy_group_id}/{symbol} external blocker classified as "
                f"{blocker_class}"
            )
            if not failed_facts
            else (
                f"{strategy_group_id}/{symbol} computed facts not satisfied: "
                f"{','.join(failed_facts)}"
            )
        )
    next_action = str(row.get("next_action") or _next_action_for_contract(blocker_class))
    return _classifier(
        BLOCKER_DECISION_BY_CLASS.get(blocker_class, "not_tradable_facts"),
        blocker_class,
        detail,
        BLOCKER_OWNER_BY_CLASS.get(blocker_class, "engineering"),
        next_action,
        str(row.get("after_next_state") or _after_next_state_for_contract(blocker_class)),
    )


def _external_blocker_rows(
    *,
    strategy_group_id: str,
    replay_live_parity_audit: dict[str, Any],
    strategy_fresh_signal_action_time_boundary: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _dict_rows(replay_live_parity_audit.get("per_symbol_mismatch_table")):
        if str(row.get("strategy_group_id") or "") != strategy_group_id:
            continue
        if not _external_row_shape_valid(row):
            rows.append(
                {
                    "symbol": str(row.get("symbol") or ""),
                    "blocker_class": "schema_invalid",
                    "detail": "replay_live_parity_audit row shape is invalid",
                    "next_action": "repair_artifact_schema_and_add_regression",
                    "after_next_state": "artifact_schema_valid",
                }
            )
            continue
        blocker_class = _contract_blocker_class(
            str(row.get("blocker_class") or row.get("first_blocker_class") or ""),
            "not_tradable_facts",
        )
        rows.append(
            {
                "symbol": str(row.get("symbol") or ""),
                "blocker_class": blocker_class,
                "failed_facts": _string_list(row.get("failed_facts")),
                "next_action": str(
                    row.get("next_action") or _next_action_for_contract(blocker_class)
                ),
                "after_next_state": _after_next_state_for_contract(blocker_class),
            }
        )
    for row in _action_time_boundary_rows(strategy_fresh_signal_action_time_boundary):
        if str(row.get("strategy_group_id") or "") != strategy_group_id:
            continue
        if not _external_row_shape_valid(row):
            rows.append(
                {
                    "symbol": str(row.get("symbol") or ""),
                    "blocker_class": "schema_invalid",
                    "detail": (
                        "strategy_fresh_signal_action_time_boundary row shape "
                        "is invalid"
                    ),
                    "next_action": "repair_artifact_schema_and_add_regression",
                    "after_next_state": "artifact_schema_valid",
                }
            )
            continue
        blocker_class = _contract_blocker_class(
            str(
                row.get("blocker_class")
                or row.get("first_blocker_class")
                or row.get("first_blocker")
                or ""
            ),
            "not_tradable_execution_gate",
        )
        if not blocker_class:
            continue
        rows.append(
            {
                "symbol": str(row.get("symbol") or ""),
                "blocker_class": blocker_class,
                "detail": str(
                    row.get("first_blocker_detail")
                    or row.get("detail")
                    or row.get("first_blocker")
                    or "action-time boundary did not reproduce"
                ),
                "next_action": _next_action_for_contract(blocker_class),
                "after_next_state": str(
                    row.get("after_next_state")
                    or _after_next_state_for_contract(blocker_class)
                ),
            }
        )
    return rows


def _market_wait_external_lane_checks(
    *,
    strategy_group_id: str,
    replay_live_parity_audit: dict[str, Any],
    strategy_fresh_signal_action_time_boundary: dict[str, Any],
) -> dict[str, bool]:
    parity_ready_symbols = {
        str(row.get("symbol") or "")
        for row in _dict_rows(replay_live_parity_audit.get("per_symbol_mismatch_table"))
        if str(row.get("strategy_group_id") or "") == strategy_group_id
        and str(row.get("symbol") or "")
        and _contract_blocker_class(
            str(row.get("blocker_class") or row.get("first_blocker_class") or ""),
            "not_tradable_market_wait",
        )
        == "market_wait_validated"
        and row.get("detector_attached") is True
        and row.get("watcher_tick_present") is True
        and row.get("computed") is True
        and not _string_list(row.get("failed_facts"))
    }
    action_time_ready_symbols = {
        str(row.get("symbol") or "")
        for row in _action_time_boundary_rows(strategy_fresh_signal_action_time_boundary)
        if str(row.get("strategy_group_id") or "") == strategy_group_id
        and str(row.get("symbol") or "")
        and _contract_blocker_class(
            str(
                row.get("blocker_class")
                or row.get("first_blocker_class")
                or row.get("first_blocker")
                or ""
            ),
            "not_tradable_market_wait",
        )
        == "market_wait_validated"
        and (
            row.get("action_time_path_ready") is True
            or row.get("dry_run_submit_rehearsal_ready") is True
        )
    }
    matched_symbols = parity_ready_symbols & action_time_ready_symbols
    return {
        "symbol": bool(matched_symbols),
        "detector": bool(matched_symbols),
        "watcher_input": bool(matched_symbols),
        "facts": bool(matched_symbols),
        "failed_facts_clear": bool(matched_symbols),
        "action_time_path": bool(matched_symbols),
    }


def _action_time_boundary_rows(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in (
        "strategy_rows",
        "per_strategy_boundary_table",
        "boundary_rows",
        "strategy_group_rows",
        "decision_rows",
    ):
        rows.extend(_dict_rows(artifact.get(key)))
    return rows


def _external_artifact_guard(
    *,
    artifact: dict[str, Any],
    artifact_name: str,
    expected_schema: str,
    expected_status: str,
    required_strategy_ids: set[str],
    row_keys: tuple[str, ...],
    strategy_group_id: str,
) -> dict[str, str]:
    if not artifact:
        return {}
    if strategy_group_id not in required_strategy_ids:
        return {}
    if _artifact_marked_fixture_or_partial(artifact):
        return _invalid_external_artifact_classifier(
            artifact_name=artifact_name,
            blocker_class="schema_invalid",
            detail=f"{artifact_name} is marked fixture or partial",
        )
    if _status(artifact) != expected_status:
        return _invalid_external_artifact_classifier(
            artifact_name=artifact_name,
            blocker_class="schema_invalid",
            detail=f"{artifact_name} status is not {expected_status}",
        )
    if artifact.get("schema") != expected_schema:
        return _invalid_external_artifact_classifier(
            artifact_name=artifact_name,
            blocker_class="schema_invalid",
            detail=f"{artifact_name} schema is not {expected_schema}",
        )
    if not _parseable_timestamp(str(artifact.get("generated_at_utc") or "")):
        return _invalid_external_artifact_classifier(
            artifact_name=artifact_name,
            blocker_class="schema_invalid",
            detail=f"{artifact_name} generated_at_utc is missing or invalid",
        )
    summary = _as_dict(artifact.get("summary"))
    rows = _external_artifact_rows(artifact, row_keys)
    strategy_ids = {
        str(row.get("strategy_group_id") or "")
        for row in rows
        if str(row.get("strategy_group_id") or "")
    }
    summary_strategy_count = _int(summary.get("strategy_count"))
    if summary_strategy_count < len(required_strategy_ids):
        return _invalid_external_artifact_classifier(
            artifact_name=artifact_name,
            blocker_class="artifact_missing",
            detail=f"{artifact_name} summary does not cover required WIP lanes",
        )
    if not required_strategy_ids <= strategy_ids:
        return _invalid_external_artifact_classifier(
            artifact_name=artifact_name,
            blocker_class="artifact_missing",
            detail=f"{artifact_name} rows do not cover required WIP lanes",
        )
    if artifact_name == "replay_live_parity_audit":
        if _int(summary.get("replay_signal_count")) <= 0:
            return _invalid_external_artifact_classifier(
                artifact_name=artifact_name,
                blocker_class="artifact_missing",
                detail=f"{artifact_name} replay_signal_count is empty",
            )
        if not _dict_rows(artifact.get("per_symbol_mismatch_table")):
            return _invalid_external_artifact_classifier(
                artifact_name=artifact_name,
                blocker_class="artifact_missing",
                detail=f"{artifact_name} per_symbol_mismatch_table is empty",
            )
    return {}


def _external_artifact_rows(
    artifact: dict[str, Any],
    row_keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in row_keys:
        rows.extend(_dict_rows(artifact.get(key)))
    return rows


def _external_row_shape_valid(row: dict[str, Any]) -> bool:
    if not str(row.get("strategy_group_id") or ""):
        return False
    blocker_class = str(
        row.get("blocker_class")
        or row.get("first_blocker_class")
        or row.get("first_blocker")
        or ""
    )
    if not blocker_class:
        return False
    return _contract_blocker_class(blocker_class) in CONTRACT_BLOCKER_CLASSES


def _artifact_marked_fixture_or_partial(artifact: dict[str, Any]) -> bool:
    status = _status(artifact).lower()
    scope = str(artifact.get("scope") or "").lower()
    marker_values = json.dumps(
        [
            artifact.get("fixture"),
            artifact.get("partial"),
            artifact.get("source"),
            _as_dict(artifact.get("summary")).get("source"),
            _as_dict(artifact.get("summary")).get("artifact_kind"),
        ],
        ensure_ascii=False,
    ).lower()
    return any(
        token in status or token in scope or token in marker_values
        for token in ("fixture", "partial")
    )


def _parseable_timestamp(value: str) -> bool:
    if not value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _invalid_external_artifact_classifier(
    *,
    artifact_name: str,
    blocker_class: str,
    detail: str,
) -> dict[str, str]:
    return _classifier(
        BLOCKER_DECISION_BY_CLASS.get(blocker_class, "not_tradable_facts"),
        blocker_class,
        detail,
        BLOCKER_OWNER_BY_CLASS.get(blocker_class, "engineering"),
        _next_action_for_contract(blocker_class),
        _after_next_state_for_contract(blocker_class),
    )


def _mi_trial_admission_candidate(artifact: dict[str, Any]) -> bool:
    if _mi_trial_admission_guard(artifact):
        return False
    return (
        _status(artifact) == "mi_trial_admission_decision_ready"
        and artifact.get("trial_admission_decision")
        == "trial_asset_admission_candidate"
        and artifact.get("promotion_scope") == "trial_admission"
    )


def _mi_readonly_observation_scope_attached(artifact: dict[str, Any]) -> bool:
    watcher_scope = _as_dict(artifact.get("watcher_scope"))
    symbol_scope = _as_dict(artifact.get("symbol_scope"))
    watcher_symbols = watcher_scope.get("symbol_scope")
    readonly_candidates = symbol_scope.get("readonly_watcher_candidates")
    return bool(
        (isinstance(watcher_symbols, list) and watcher_symbols)
        or (isinstance(readonly_candidates, list) and readonly_candidates)
    )


def _mi_trial_admission_present(artifact: dict[str, Any]) -> bool:
    return bool(artifact) and (
        _status(artifact) == "mi_trial_admission_decision_ready"
        or artifact.get("trial_admission_decision") is not None
        or artifact.get("promotion_scope") is not None
        or artifact.get("strategy_group_id") == "MI-001"
    )


def _mi_trial_admission_guard(artifact: dict[str, Any]) -> dict[str, str]:
    if not _mi_trial_admission_present(artifact):
        return {}
    if _artifact_marked_fixture_or_partial(artifact):
        return _invalid_external_artifact_classifier(
            artifact_name="mi_trial_admission_decision",
            blocker_class="schema_invalid",
            detail="mi_trial_admission_decision is marked fixture or partial",
        )
    if _status(artifact) != "mi_trial_admission_decision_ready":
        return _invalid_external_artifact_classifier(
            artifact_name="mi_trial_admission_decision",
            blocker_class="schema_invalid",
            detail=(
                "mi_trial_admission_decision status is not "
                "mi_trial_admission_decision_ready"
            ),
        )
    if artifact.get("schema") != MI_TRIAL_ADMISSION_SCHEMA:
        return _invalid_external_artifact_classifier(
            artifact_name="mi_trial_admission_decision",
            blocker_class="schema_invalid",
            detail=(
                "mi_trial_admission_decision schema is not "
                f"{MI_TRIAL_ADMISSION_SCHEMA}"
            ),
        )
    if not _parseable_timestamp(str(artifact.get("generated_at_utc") or "")):
        return _invalid_external_artifact_classifier(
            artifact_name="mi_trial_admission_decision",
            blocker_class="schema_invalid",
            detail="mi_trial_admission_decision generated_at_utc is missing or invalid",
        )
    if artifact.get("strategy_group_id") != "MI-001":
        return _invalid_external_artifact_classifier(
            artifact_name="mi_trial_admission_decision",
            blocker_class="schema_invalid",
            detail="mi_trial_admission_decision strategy_group_id is not MI-001",
        )
    tradeability = _as_dict(artifact.get("tradeability"))
    if (
        artifact.get("trial_admission_decision")
        not in {"trial_asset_admission_candidate", "park"}
        or artifact.get("promotion_scope") != "trial_admission"
        or not str(tradeability.get("first_blocker") or "")
    ):
        return _invalid_external_artifact_classifier(
            artifact_name="mi_trial_admission_decision",
            blocker_class="schema_invalid",
            detail="mi_trial_admission_decision row shape is invalid",
        )
    return {}


def _contract_blocker_class(blocker: str, decision: str = "") -> str:
    lowered = blocker.lower()
    if blocker in CONTRACT_BLOCKER_CLASSES:
        return blocker
    if lowered in LEGACY_BLOCKER_CLASS_MAP:
        return LEGACY_BLOCKER_CLASS_MAP[lowered]
    if lowered in {"", "none"}:
        return "market_wait_validated" if decision == "not_tradable_market_wait" else "artifact_missing"
    if any(token in lowered for token in ("forbidden", "safety", "hard_stop")):
        return "hard_safety_stop"
    if any(token in lowered for token in ("owner", "capital", "trial_identity", "policy")):
        return "policy_scope_missing"
    if any(
        token in lowered
        for token in (
            "registry",
            "identity",
            "tier",
            "non_executing_trial_readiness",
            "not_admitted",
            "scope",
        )
    ):
        return "scope_not_attached"
    if any(token in lowered for token in ("schema", "decision_state_missing")):
        return "schema_invalid"
    if any(token in lowered for token in ("detector", "runtime_signal_capture_gap")):
        return "detector_not_attached"
    if any(token in lowered for token in ("watcher", "tick", "fact_input")):
        return "watcher_tick_missing"
    if any(token in lowered for token in ("role_only", "stop", "overfit", "role", "filler", "quality", "loss_envelope", "worthiness")):
        return "review_only_warning"
    if any(token in lowered for token in ("rule_mismatch", "replay_live")):
        return "replay_live_rule_mismatch"
    if any(
        token in lowered
        for token in (
            "finalgate",
            "operation_layer",
            "candidate_authorization",
            "shadow_candidate",
            "dry_run_submit_rehearsal",
            "action_time",
            "exchange",
            "account",
            "protection",
        )
    ):
        return "action_time_boundary_not_reproduced"
    if lowered.startswith("fresh_") or "fresh_signal" in lowered:
        return "schema_invalid"
    if any(
        token in lowered
        for token in (
            "required_facts",
            "fact",
            "stale",
            "classifier",
            "rewrite",
            "squeeze",
            "disable",
            "forward",
            "range_context",
        )
    ):
        return "computed_not_satisfied" if decision == "not_tradable_market_wait" else "artifact_missing"
    return "review_only_warning"


def _next_action_for_contract(blocker_class: str) -> str:
    return {
        "artifact_missing": "generate_or_wire_current_artifact",
        "schema_invalid": "repair_artifact_schema_and_add_regression",
        "detector_not_attached": "attach_live_detector_to_selected_lane",
        "watcher_tick_missing": "refresh_or_repair_watcher_fact_source",
        "scope_not_attached": "produce_scoped_live_observation_or_scope_proposal",
        "computed_not_satisfied": "continue_observation_with_failed_fact_matrix",
        "replay_live_rule_mismatch": "normalize_replay_live_rules_or_record_revision",
        "action_time_boundary_not_reproduced": "repair_non_executing_action_time_rehearsal_path",
        "policy_scope_missing": "record_scoped_owner_policy",
        "runtime_profile_scope_missing": "bind_runtime_profile_scope",
        "market_wait_validated": "continue_armed_observation_until_fresh_signal",
        "active_position_resolution": "resolve_active_position_or_open_order",
        "hard_safety_stop": "remove_hard_safety_violation",
        "review_only_warning": "record_strategy_review_decision",
    }.get(blocker_class, "repair_tradeability_blocker_classification")


def _after_next_state_for_contract(blocker_class: str) -> str:
    return {
        "artifact_missing": "artifact_ready",
        "schema_invalid": "artifact_schema_valid",
        "detector_not_attached": "detector_attached",
        "watcher_tick_missing": "watcher_tick_present",
        "scope_not_attached": "armed_observation",
        "computed_not_satisfied": "live_submit_ready",
        "replay_live_rule_mismatch": "replay_live_rule_aligned",
        "action_time_boundary_not_reproduced": "action_time_rehearsal_ready",
        "policy_scope_missing": "admitted_trial_asset",
        "runtime_profile_scope_missing": "runtime_profile_scope_bound",
        "market_wait_validated": "live_submit_ready",
        "active_position_resolution": "runtime_safety_clear",
        "hard_safety_stop": "safety_clear_for_tradeability_review",
        "review_only_warning": "strategy_asset_state_updated",
    }.get(blocker_class, "tradeability_decision_ready")


def _stage(
    *,
    strategy_group_id: str,
    candidate: dict[str, Any],
    registry_row: dict[str, Any],
    tier_row: dict[str, Any],
    observed_row: dict[str, Any],
    admission_proposal: dict[str, Any],
    owner_policy_scope: dict[str, Any],
    portfolio_seat: dict[str, Any],
    runtime_safety_state: dict[str, Any],
    mi_trial_admission_decision: dict[str, Any] | None = None,
) -> str:
    if _row_live_submit_ready(
        strategy_group_id=strategy_group_id,
        runtime_safety_state=runtime_safety_state,
    ):
        return "live_submit_ready"
    owner_policy_recorded = _policy_recorded(owner_policy_scope) or (
        admission_proposal.get("owner_policy_recorded") is True
        and admission_proposal.get("owner_policy_scope_missing") is False
    )
    if (
        strategy_group_id == "CPM-RO-001"
        and registry_row.get("trial_eligible") is True
        and tier_row.get("mode") == "armed_observation"
        and owner_policy_recorded
    ):
        return "armed_observation"
    portfolio_stage = str(portfolio_seat.get("stage") or "")
    if portfolio_stage == "armed_observation":
        return "armed_observation"
    if strategy_group_id == "MI-001" and _mi_trial_admission_candidate(
        mi_trial_admission_decision or {}
    ):
        return "trial_asset_admission_candidate"
    if admission_proposal:
        if owner_policy_recorded:
            return str(admission_proposal.get("proposed_stage") or "admitted_trial_asset")
        return "trial_asset_admission_candidate"
    if portfolio_seat:
        portfolio_stage = str(portfolio_seat.get("stage") or "")
        if portfolio_stage == "armed_observation_ready":
            return "armed_observation"
        if portfolio_stage:
            return portfolio_stage
    if strategy_group_id == "MPG-001" and _mpg_waits_for_market(
        tier_row=tier_row,
        runtime_safety_state=runtime_safety_state,
    ):
        return "armed_observation"
    position = str(candidate.get("research_intake_position") or "")
    if position == "role_only_intake_candidate":
        return "role_only_intake_candidate"
    if candidate.get("candidate_family") == "short_research_intake":
        return "tiny_live_intake_candidate"
    if candidate:
        if str(candidate.get("candidate_status") or "").startswith("trial_prepare"):
            return "trial_asset_admission_candidate"
        return "trial_asset_admission_candidate"
    if observed_row:
        return "observe_only_would_enter"
    if tier_row and registry_row.get("trial_eligible") is True:
        return "armed_observation"
    if tier_row:
        return "admitted_trial_asset"
    return "research_candidate"


def _mpg_waits_for_market(
    *,
    tier_row: dict[str, Any],
    runtime_safety_state: dict[str, Any],
) -> bool:
    runtime_safety = runtime_safety_state_from_artifact(runtime_safety_state)
    return (
        tier_row.get("mode") == "tiny_real_order_eligible"
        and runtime_safety.get("live_submit_ready") is False
        and runtime_safety.get("live_submit_ready_false_reason") == "no_fresh_signal"
    )


def _row_live_submit_ready(
    *,
    strategy_group_id: str,
    runtime_safety_state: dict[str, Any],
) -> bool:
    return live_submit_ready_for_strategy_artifact(
        artifact=runtime_safety_state,
        strategy_group_id=strategy_group_id,
    )


def _runtime_safety_reference(
    *,
    strategy_group_id: str,
    runtime_safety_state: dict[str, Any],
) -> dict[str, Any]:
    runtime_safety = runtime_safety_state_from_artifact(runtime_safety_state)
    return {
        "state_source": "runtime_safety_state",
        "strategy_group_id": strategy_group_id,
        "live_submit_ready_for_strategy": _row_live_submit_ready(
            strategy_group_id=strategy_group_id,
            runtime_safety_state=runtime_safety_state,
        ),
        "live_submit_ready": runtime_safety.get("live_submit_ready") is True,
        "live_submit_ready_false_reason": str(
            runtime_safety.get("live_submit_ready_false_reason") or ""
        ),
        "execution_attempt_required_for_lifecycle_entry": True,
    }


def _candidate_rows_by_id(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in _dict_rows(artifact.get("capital_trial_eligibility_rows")):
        strategy_id = str(row.get("strategy_group_id") or "")
        if strategy_id:
            rows[strategy_id] = row
    selected = _as_dict(artifact.get("selected_non_mpg_trial_candidate"))
    selected_id = str(selected.get("strategy_group_id") or "")
    if selected_id:
        rows[selected_id] = {**rows.get(selected_id, {}), **selected}
    return rows


def _registry_rows_by_id(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("strategy_group_id")): row
        for row in _dict_rows(artifact.get("rows"))
        if row.get("strategy_group_id")
    }


def _tier_rows_by_id(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = _as_dict(artifact.get("current_strategy_groups"))
    return {str(key): _as_dict(value) for key, value in rows.items()}


def _observe_only_rows_by_id(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    broader = _as_dict(artifact.get("broader_observation"))
    rows: dict[str, dict[str, Any]] = {}
    for row in _dict_rows(broader.get("would_enter_signals")):
        strategy_id = str(row.get("strategy_group_id") or "")
        if strategy_id:
            rows.setdefault(strategy_id, row)
    return rows


def _admission_proposals_by_id(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if _status(artifact) != "trial_asset_admission_proposal_ready":
        return {}
    proposal = _as_dict(artifact.get("proposal"))
    strategy_id = str(proposal.get("strategy_group_id") or "")
    return {strategy_id: proposal} if strategy_id else {}


def _owner_policy_scopes_by_id(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not _policy_recorded(artifact):
        return {}
    policy = _as_dict(artifact.get("policy"))
    strategy_id = str(policy.get("strategy_group_id") or "")
    return {strategy_id: artifact} if strategy_id else {}


def _portfolio_seats_by_id(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not artifact:
        return {}
    seats = _as_dict(artifact.get("seat_readiness"))
    return {str(key): _as_dict(value) for key, value in seats.items()}


def _portfolio_trial_envelope(artifact: dict[str, Any]) -> dict[str, Any]:
    envelope = _as_dict(artifact.get("trial_envelope"))
    if envelope:
        return envelope
    return {}


def _trial_grade_rows_by_id(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if _status(artifact) != "trial_grade_signal_gate_audit_ready":
        return {}
    rows = _as_dict(artifact.get("strategy_group_rows"))
    return {str(key): _as_dict(value) for key, value in rows.items()}


def _signal_grade_status(
    *,
    strategy_group_id: str,
    trial_grade_row: dict[str, Any],
    portfolio_seat: dict[str, Any],
) -> dict[str, Any]:
    runtime_readiness = _as_dict(portfolio_seat.get("runtime_readiness"))
    if not trial_grade_row:
        return {
            "strategy_group_id": strategy_group_id,
            "trial_grade_audit_ready": False,
            "controlled_live_standby_ready": runtime_readiness.get(
                "controlled_live_standby_ready"
            )
            is True,
            "stage_5_waiting_live_opportunity_ready": runtime_readiness.get(
                "stage_5_waiting_live_opportunity_ready"
            )
            is True,
        }
    assessment = _as_dict(trial_grade_row.get("signal_grade_current_assessment"))
    counts_30d = _as_dict(
        _as_dict(
            _as_dict(trial_grade_row.get("verified_recent_window_counts")).get(
                "windows_days"
            )
        ).get("30")
    )
    projection = _as_dict(trial_grade_row.get("fixture_replay_projection"))
    tomorrow = _as_dict(trial_grade_row.get("tomorrow_same_structure_assessment"))
    authority = _as_dict(trial_grade_row.get("authority_boundary"))
    return {
        "strategy_group_id": strategy_group_id,
        "trial_grade_audit_ready": True,
        "current_gate_looks_like": str(
            assessment.get("current_gate_looks_like") or "unknown"
        ),
        "controlled_live_standby_ready": runtime_readiness.get(
            "controlled_live_standby_ready"
        )
        is True,
        "stage_5_waiting_live_opportunity_ready": runtime_readiness.get(
            "stage_5_waiting_live_opportunity_ready"
        )
        is True,
        "recent_30d_trial_grade_observation_count": _int(
            counts_30d.get("trial_grade_observation_count")
        ),
        "recent_30d_action_time_trial_submit_count": _int(
            counts_30d.get("action_time_trial_submit_count")
        ),
        "fixture_trial_grade_trigger_case_count": _int(
            projection.get("trial_grade_trigger_case_count")
        ),
        "max_loss_estimate_usdt": str(
            projection.get("max_loss_estimate_usdt") or ""
        ),
        "would_enter_controlled_live_trial_if_same_structure": (
            tomorrow.get("would_enter_controlled_live_trial") is True
        ),
        "trial_grade_signal_can_prepare_controlled_live": (
            authority.get("trial_grade_signal_can_prepare_controlled_live") is True
        ),
        "trial_grade_signal_can_bypass_hard_safety_gates": (
            authority.get("trial_grade_signal_can_bypass_hard_safety_gates") is True
        ),
    }


def _policy_scope(
    strategy_group_id: str,
    candidate: dict[str, Any],
    portfolio_seat: dict[str, Any],
    owner_policy_scope: dict[str, Any],
    trial_envelope: dict[str, Any],
) -> dict[str, Any]:
    if _policy_recorded(owner_policy_scope):
        policy = _as_dict(owner_policy_scope.get("policy"))
        return {
            "source": (
                "cpm_owner_trial_policy_scope"
                if policy.get("strategy_group_id") == "CPM-RO-001"
                else "brf2_owner_trial_policy_scope"
            ),
            "capital_scope": _as_dict(policy.get("capital_scope")),
            "profile": "runtime_profile_and_action_time_exchange_facts",
            "symbol_scope": [str(policy.get("symbol_scope") or "")],
            "side_scope": _string_list(policy.get("side_scope")),
            "leverage_scenario": policy.get("leverage_scenario", "not_applicable"),
            "max_notional": _as_dict(policy.get("max_notional")),
            "attempt_cap": policy.get("attempt_cap"),
            "loss_unit": _as_dict(policy.get("loss_unit")),
            "daily_loss_cap_units": policy.get("daily_loss_cap_units"),
            "max_consecutive_losses": policy.get("max_consecutive_losses"),
            "valid_until": policy.get("valid_until"),
            "trial_identity": policy.get("trial_identity"),
            "missing_policy_fields": [],
        }
    envelope_scope = _trial_envelope_policy_scope(
        strategy_group_id=strategy_group_id,
        trial_envelope=trial_envelope,
    )
    if envelope_scope:
        return envelope_scope
    portfolio_scope = _as_dict(portfolio_seat.get("policy_scope"))
    if portfolio_scope:
        return {
            "source": "legacy_portfolio_seat_policy_scope",
            "capital_scope": portfolio_scope.get("capital_scope", "not_applicable"),
            "profile": portfolio_scope.get("profile", "not_applicable"),
            "symbol_scope": _string_list(portfolio_scope.get("symbol_scope")),
            "side_scope": _string_list(portfolio_scope.get("side_scope")),
            "leverage_scenario": portfolio_scope.get(
                "leverage_scenario", "not_applicable"
            ),
            "attempt_cap": portfolio_scope.get(
                "attempt_cap", "owner_policy_required"
            ),
            "loss_unit": portfolio_scope.get("loss_unit", "owner_policy_required"),
            "missing_policy_fields": _string_list(
                portfolio_scope.get("missing_policy_fields")
            ),
        }
    missing = [str(item) for item in candidate.get("risk_boundary_missing") or []]
    return {
        "source": "capital_trial_candidate",
        "capital_scope": _policy_value(candidate, "capital_scope", missing),
        "profile": "owner_policy_required" if missing else "not_applicable",
        "symbol_scope": [str(item) for item in candidate.get("symbol_scope") or []],
        "side_scope": [str(item) for item in candidate.get("side_scope") or []],
        "leverage_scenario": "owner_policy_required" if missing else "not_applicable",
        "attempt_cap": _as_dict(candidate.get("risk_envelope")).get(
            "attempt_cap_per_review_cycle", "owner_policy_required"
        ),
        "loss_unit": _as_dict(candidate.get("risk_envelope")).get(
            "daily_loss_cap_units", "owner_policy_required"
        ),
        "missing_policy_fields": missing,
    }


def _trial_envelope_policy_scope(
    *,
    strategy_group_id: str,
    trial_envelope: dict[str, Any],
) -> dict[str, Any]:
    if not trial_envelope:
        return {}
    applies_to = _string_list(trial_envelope.get("applies_to_strategy_groups"))
    if applies_to and strategy_group_id not in applies_to:
        return {}
    summaries = _as_dict(trial_envelope.get("seat_policy_summaries"))
    seat_summary = _as_dict(summaries.get(strategy_group_id))
    if not seat_summary:
        return {}
    return {
        "source": "trial_envelope",
        "trial_envelope_id": trial_envelope.get("trial_envelope_id"),
        "capital_scope": seat_summary.get(
            "capital_scope", trial_envelope.get("capital")
        ),
        "profile": "trial_envelope_policy_boundary",
        "symbol_scope": _string_list(seat_summary.get("symbol_scope")),
        "side_scope": _string_list(seat_summary.get("side_scope")),
        "leverage_scenario": trial_envelope.get(
            "leverage_scenario", "owner_policy_required"
        ),
        "max_notional": _as_dict(trial_envelope.get("max_notional")),
        "attempt_cap": seat_summary.get(
            "attempt_cap", trial_envelope.get("attempt_cap", "owner_policy_required")
        ),
        "loss_unit": seat_summary.get(
            "loss_unit", trial_envelope.get("loss_unit", "owner_policy_required")
        ),
        "daily_loss_cap_units": trial_envelope.get(
            "daily_loss_cap_units", "owner_policy_required"
        ),
        "max_consecutive_losses": trial_envelope.get(
            "max_consecutive_losses", "owner_policy_required"
        ),
        "protection_required": trial_envelope.get("protection_required") is True,
        "review_required": trial_envelope.get("review_required") is True,
        "missing_policy_fields": [],
    }


def _july_bullish_rebound_trade_path_closure(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    paths = [
        path
        for row in rows
        for path in _dict_rows(row.get("trade_paths"))
    ]
    exits = [
        _as_dict(row.get("observe_only_exit"))
        for row in rows
        if _as_dict(row.get("observe_only_exit")).get("exit_decision")
    ]
    first_blockers = {
        str(row.get("strategy_group_id") or ""): str(row.get("first_blocker_class") or "")
        for row in rows
    }
    path_ids = {str(path.get("path_id") or "") for path in paths}
    long_path_ids = {str(path.get("path_id") or "") for path in paths if path.get("side") == "long"}
    short_path_ids = {str(path.get("path_id") or "") for path in paths if path.get("side") == "short"}
    rbr_exit_strategy_ids = {
        str(exit_row.get("strategy_group_id") or "")
        for exit_row in exits
    }
    required_rbr_exit_strategy_ids = {"RBR-001", "RBR2-001"}
    trigger_diffs = {
        str(path.get("path_id")): _as_dict(path.get("production_vs_trial_trigger_diff"))
        for path in paths
        if _as_dict(path.get("production_vs_trial_trigger_diff"))
    }
    return {
        "status": "july_bullish_rebound_trade_path_closure_ready",
        "hypothesis_id": JULY_BULLISH_REBOUND_HYPOTHESIS_ID,
        "market_regime_hypothesis": "2026_july_early_mid_bullish_or_rebound_window",
        "machine_consumption_surface": "tradeability_decision",
        "paths": paths,
        "observe_only_exits": exits,
        "production_vs_trial_trigger_diffs": trigger_diffs,
        "summary": {
            "machine_consumed_path_count": len(paths),
            "long_side_path_count": len(long_path_ids),
            "short_side_guard_path_count": len(short_path_ids),
            "required_long_paths_present": all(
                path_id in path_ids
                for path_id in {"CPM-LONG", "MPG-LONG", "SOR-LONG"}
            ),
            "required_short_guard_paths_present": all(
                path_id in path_ids for path_id in {"BRF2-SHORT", "CPM-SHORT"}
            ),
            "rbr_exit_decision_count": len(exits),
            "required_rbr_exit_rows_present": (
                required_rbr_exit_strategy_ids <= rbr_exit_strategy_ids
            ),
            "tradable_now_count": sum(
                path.get("can_trade_now") is True for path in paths
            ),
            "real_order_authority_count": 0,
        },
        "checks": {
            "machine_consumed_path_count": len(paths),
            "required_path_ids_present": all(
                path_id in path_ids
                for path_id in {
                    "CPM-LONG",
                    "MPG-LONG",
                    "SOR-LONG",
                    "BRF2-SHORT",
                    "CPM-SHORT",
                }
            ),
            "cpm_mapping_gap_removed_from_first_blockers": all(
                blocker != "cpm_required_facts_mapping_gap"
                for strategy_id, blocker in first_blockers.items()
                if strategy_id in {"CPM-RO-001", "CPM-001"}
            ),
            "cpm_non_market_blocker_preserved": all(
                blocker
                not in {
                    "fresh_cpm_long_signal_absent",
                    "fresh_cpm_short_signal_absent",
                }
                or next(
                    (
                        row.get("stage")
                        in {"armed_observation", "tiny_live_ready", "live_submit_ready"}
                        and row.get("required_facts_status") in {"ready", "action_time_only"}
                        for row in rows
                        if str(row.get("strategy_group_id") or "")
                        in {"CPM-RO-001", "CPM-001"}
                    ),
                    False,
                )
                for strategy_id, blocker in first_blockers.items()
                if strategy_id in {"CPM-RO-001", "CPM-001"}
            ),
            "rbr_observe_only_has_exit_decision": (
                required_rbr_exit_strategy_ids <= rbr_exit_strategy_ids
                and all(
                    exit_row.get("exit_decision")
                    in {
                        "upgrade_to_trial_candidate",
                        "merge_as_classifier",
                        "keep_observing",
                        "park",
                        "kill",
                    }
                    for exit_row in exits
                    if str(exit_row.get("strategy_group_id") or "")
                    in required_rbr_exit_strategy_ids
                )
            ),
            "capital_scope_uses_action_time_exchange_available_balance": all(
                path.get("capital_scope_source")
                == "action_time_exchange_available_balance"
                for path in paths
            ),
            "no_fixed_30u_contract": all(
                forbidden not in json.dumps(path, ensure_ascii=False).lower()
                for path in paths
                for forbidden in ("amount=30", "amount_30", "30u", "30 usdt")
            ),
        },
        "authority_boundary": (
            "read_model_only; no FinalGate call; no Operation Layer call; no exchange write; "
            "fresh signal and action-time exchange facts still required before any live submit"
        ),
    }


def _trade_paths_for_strategy(
    *,
    strategy_group_id: str,
    row_classifier: dict[str, str],
    required_facts_status: str,
) -> list[dict[str, Any]]:
    path_ids = {
        "CPM-RO-001": ["CPM-LONG", "CPM-SHORT"],
        "MPG-001": ["MPG-LONG"],
        "SOR-001": ["SOR-LONG"],
        "BRF2-001": ["BRF2-SHORT"],
    }.get(strategy_group_id, [])
    return [
        _trade_path_state(
            strategy_group_id=strategy_group_id,
            path_id=path_id,
            row_classifier=row_classifier,
            required_facts_status=required_facts_status,
        )
        for path_id in path_ids
    ]


def _trade_path_state(
    *,
    strategy_group_id: str,
    path_id: str,
    row_classifier: dict[str, str],
    required_facts_status: str,
) -> dict[str, Any]:
    spec = _trade_path_spec(path_id)
    can_trade_now = row_classifier["decision"] == "tradable_now"
    if row_classifier["decision"] in {"tradable_now", "not_tradable_market_wait"}:
        required_facts_mapping_status = spec.get(
            "required_facts_mapping_status",
            (
                "ready"
                if required_facts_status in {"ready", "action_time_only"}
                else required_facts_status
            ),
        )
    else:
        required_facts_mapping_status = (
            "ready"
            if required_facts_status in {"ready", "action_time_only"}
            else required_facts_status
        )
    if can_trade_now:
        first_blocker = "none"
        blocker_owner = "runtime"
        next_action = "continue_official_live_submit_chain"
        post_action_expected_state = "execution_attempt"
    elif row_classifier["decision"] == "not_tradable_market_wait":
        row_first_blocker = row_classifier["first_blocker_class"]
        generic_market_wait_blockers = {
            "fresh_executable_signal_absent",
            "fresh_strategy_signal_absent",
        }
        inherit_row_market_blocker = (
            bool(row_first_blocker)
            and row_first_blocker not in generic_market_wait_blockers
            and not row_first_blocker.startswith("fresh_")
        )
        if inherit_row_market_blocker:
            first_blocker = row_first_blocker
        else:
            first_blocker = spec["first_blocker"]
        blocker_owner = row_classifier["blocker_owner"]
        next_action = (
            row_classifier["next_action"]
            if inherit_row_market_blocker
            else spec["next_action"]
        )
        post_action_expected_state = row_classifier["after_next_state"]
    else:
        first_blocker = row_classifier["first_blocker_class"]
        blocker_owner = row_classifier["blocker_owner"]
        next_action = row_classifier["next_action"]
        post_action_expected_state = row_classifier["after_next_state"]
    return {
        "strategy_group_id": strategy_group_id,
        "path_id": path_id,
        "side": spec["side"],
        "role": spec["role"],
        "priority": spec["priority"],
        "trigger_required_facts": spec["trigger_required_facts"],
        "disable_facts": spec["disable_facts"],
        "stop_or_invalidation": spec["stop_or_invalidation"],
        "time_stop": spec["time_stop"],
        "attempt_cap": "runtime_profile_or_owner_scoped_attempt_cap",
        "capital_scope_source": "action_time_exchange_available_balance",
        "can_trade_now": can_trade_now,
        "first_blocker": first_blocker,
        "blocker_owner": blocker_owner,
        "next_action": next_action,
        "post_action_expected_state": post_action_expected_state,
        "required_facts_mapping_status": required_facts_mapping_status,
        "watcher_scope": spec["watcher_scope"],
        "production_vs_trial_trigger_diff": spec.get(
            "production_vs_trial_trigger_diff", {}
        ),
        "field_level_fresh_signal_absent_reason": spec[
            "field_level_fresh_signal_absent_reason"
        ],
        "authority_boundary": (
            "path_state_only; not FinalGate input; not Operation Layer input; "
            "not real-order authority"
        ),
    }


def _trade_path_spec(path_id: str) -> dict[str, Any]:
    specs: dict[str, dict[str, Any]] = {
        "CPM-LONG": {
            "side": "long",
            "role": "bullish rebound / pullback-reclaim / trend continuation primary candidate",
            "priority": "P0",
            "trigger_required_facts": [
                "htf_trend_intact",
                "pullback_depth_normal",
                "reclaim_confirmed",
                "invalidated_below_level",
                "liquidity_ok",
                "funding_not_extreme",
                "action_time_available_balance",
            ],
            "disable_facts": [
                "htf_trend_broken",
                "pullback_depth_abnormal",
                "reclaim_failed_or_stale",
                "liquidity_not_ok",
                "funding_extreme",
                "active_position_or_open_order_conflict",
            ],
            "stop_or_invalidation": "invalidated_below_level",
            "time_stop": "exit_or_reassess_if_reclaim_followthrough_stale_before_runtime_profile_horizon",
            "watcher_scope": {
                "symbols": "runtime_profile_supported_symbols",
                "timeframes": ["15m", "1h", "4h"],
                "cadence": "5-15m near reclaim; 15-30m otherwise",
            },
            "first_blocker": "fresh_cpm_long_signal_absent",
            "next_action": "continue_cpm_long_armed_observation_until_reclaim_signal",
            "required_facts_mapping_status": "ready",
            "field_level_fresh_signal_absent_reason": {
                "missing_or_false": [
                    "htf_trend_intact",
                    "pullback_depth_normal",
                    "reclaim_confirmed",
                ],
                "action_time_only": ["action_time_available_balance"],
            },
        },
        "CPM-SHORT": {
            "side": "short",
            "role": "bounce-loss / rebound failure guard",
            "priority": "P2",
            "trigger_required_facts": [
                "htf_weakness_or_rebound_context",
                "bounce_depth_normal",
                "bounce_loss_confirmed",
                "invalidated_above_level",
                "liquidity_ok",
                "funding_not_extreme",
                "action_time_available_balance",
            ],
            "disable_facts": [
                "htf_strength_recovered",
                "bounce_depth_abnormal",
                "bounce_loss_not_confirmed",
                "liquidity_not_ok",
                "funding_extreme",
                "active_position_or_open_order_conflict",
            ],
            "stop_or_invalidation": "invalidated_above_level",
            "time_stop": "exit_or_reassess_if_bounce_loss_followthrough_stale_before_runtime_profile_horizon",
            "watcher_scope": {
                "symbols": "runtime_profile_supported_symbols",
                "timeframes": ["15m", "1h", "4h"],
                "cadence": "5-15m near bounce-loss; 15-30m otherwise",
            },
            "first_blocker": "fresh_cpm_short_signal_absent",
            "next_action": "continue_cpm_short_guard_observation_until_bounce_loss_signal",
            "required_facts_mapping_status": "ready",
            "field_level_fresh_signal_absent_reason": {
                "missing_or_false": [
                    "htf_weakness_or_rebound_context",
                    "bounce_depth_normal",
                    "bounce_loss_confirmed",
                ],
                "action_time_only": ["action_time_available_balance"],
            },
        },
        "MPG-LONG": {
            "side": "long",
            "role": "momentum / trend continuation candidate",
            "priority": "P1",
            "trigger_required_facts": [
                "closed_momentum_persistence_bar",
                "trend_continuation_context",
                "pullback_or_breakout_not_overextended",
                "volume_or_range_confirmation",
                "liquidity_ok",
                "funding_not_extreme",
                "action_time_available_balance",
            ],
            "disable_facts": [
                "momentum_exhaustion",
                "overextension_disable",
                "liquidity_not_ok",
                "funding_extreme",
                "active_position_or_open_order_conflict",
            ],
            "stop_or_invalidation": "momentum_structure_invalidated_or_runtime_profile_stop",
            "time_stop": "runtime_profile_time_stop_after_stale_continuation",
            "watcher_scope": {
                "symbols": "selected_runtime_scope",
                "timeframes": ["5m", "15m", "1h"],
                "cadence": "5-15m",
            },
            "first_blocker": "fresh_mpg_long_signal_absent",
            "next_action": "continue_mpg_armed_observation_until_fresh_momentum_signal",
            "field_level_fresh_signal_absent_reason": {
                "missing_or_false": [
                    "closed_momentum_persistence_bar",
                    "trend_continuation_context",
                    "volume_or_range_confirmation",
                ],
                "action_time_only": ["action_time_available_balance"],
            },
            "production_vs_trial_trigger_diff": _mpg_trigger_diff(),
        },
        "SOR-LONG": {
            "side": "long",
            "role": "session breakout / opening-range continuation / frequency fill candidate",
            "priority": "P1",
            "trigger_required_facts": [
                "session_window_active",
                "closed_opening_range",
                "closed_breakout_or_revival_trigger",
                "post_open_decay_clear",
                "liquidity_ok",
                "funding_not_extreme",
                "action_time_available_balance",
            ],
            "disable_facts": [
                "invalid_session_window",
                "open_range_not_closed",
                "post_open_decay_active",
                "liquidity_not_ok",
                "funding_extreme",
                "active_position_or_open_order_conflict",
            ],
            "stop_or_invalidation": "session_range_reentry_or_runtime_profile_stop",
            "time_stop": "same_session_time_stop_before_stale_breakout",
            "watcher_scope": {
                "symbols": "session_supported_runtime_scope",
                "timeframes": ["5m", "15m", "1h"],
                "cadence": "5m near session; 5-15m near trigger",
            },
            "first_blocker": "fresh_sor_long_signal_absent",
            "next_action": "continue_sor_session_observation_until_fresh_long_trigger",
            "field_level_fresh_signal_absent_reason": {
                "missing_or_false": [
                    "session_window_active",
                    "closed_opening_range",
                    "closed_breakout_or_revival_trigger",
                ],
                "action_time_only": ["action_time_available_balance"],
            },
            "production_vs_trial_trigger_diff": _sor_trigger_diff(),
        },
        "BRF2-SHORT": {
            "side": "short",
            "role": "late-rally failure / rally failure guard",
            "priority": "P2",
            "trigger_required_facts": [
                "rally_failure_context",
                "closed_1h_ohlcv",
                "failure_reversal_confirmed",
                "squeeze_risk_state",
                "liquidity_ok",
                "funding_not_extreme",
                "action_time_available_balance",
            ],
            "disable_facts": [
                "rally_continuation_intact",
                "squeeze_risk_extreme",
                "liquidity_not_ok",
                "funding_extreme",
                "active_position_or_open_order_conflict",
            ],
            "stop_or_invalidation": "rally_failure_invalidated_above_level_or_runtime_profile_stop",
            "time_stop": "runtime_profile_time_stop_after_stale_failure_followthrough",
            "watcher_scope": {
                "symbols": "brf2_research_supported_symbols_only",
                "timeframes": ["15m", "1h"],
                "cadence": "5-15m near rally failure",
            },
            "first_blocker": "fresh_brf2_short_signal_absent",
            "next_action": "continue_brf2_armed_observation_until_fresh_signal",
            "required_facts_mapping_status": "ready",
            "field_level_fresh_signal_absent_reason": {
                "missing_or_false": [
                    "rally_failure_context",
                    "failure_reversal_confirmed",
                    "squeeze_risk_state_clear",
                ],
                "action_time_only": ["action_time_available_balance"],
            },
        },
    }
    return specs[path_id]


def _mpg_trigger_diff() -> dict[str, Any]:
    return {
        "hard_gates": [
            "closed_momentum_persistence_bar",
            "trend_continuation_context",
            "action_time_exchange_available_balance",
            "liquidity_ok",
            "active_position_and_open_order_clear",
            "protection_template_available",
        ],
        "review_warnings": [
            "thin_recent_replay_sample",
            "coarse_slippage_estimate",
            "post_entry_momentum_decay_uncalibrated",
        ],
        "downgrade_to_warning_moves_closer_to_execution_attempt": [
            "thin_recent_replay_sample",
            "coarse_slippage_estimate",
        ],
        "cannot_relax": [
            "closed_momentum_persistence_bar",
            "action_time_exchange_available_balance",
            "active_position_and_open_order_clear",
            "FinalGate",
            "Operation Layer",
            "protection_template_available",
        ],
    }


def _sor_trigger_diff() -> dict[str, Any]:
    return {
        "hard_gates": [
            "session_window_active",
            "closed_opening_range",
            "closed_breakout_or_revival_trigger",
            "action_time_exchange_available_balance",
            "liquidity_ok",
            "active_position_and_open_order_clear",
            "protection_template_available",
        ],
        "review_warnings": [
            "session_slippage_estimate_rough",
            "post_open_decay_sample_thin",
            "long_revival_branch_has_limited_live_history",
        ],
        "downgrade_to_warning_moves_closer_to_execution_attempt": [
            "session_slippage_estimate_rough",
            "long_revival_branch_has_limited_live_history",
        ],
        "cannot_relax": [
            "session_window_active",
            "closed_opening_range",
            "closed_breakout_or_revival_trigger",
            "action_time_exchange_available_balance",
            "active_position_and_open_order_clear",
            "FinalGate",
            "Operation Layer",
            "protection_template_available",
        ],
    }


def _observe_only_exit_for_strategy(
    *,
    strategy_group_id: str,
    stage: str,
    candidate: dict[str, Any],
    registry_row: dict[str, Any],
    observed_row: dict[str, Any],
) -> dict[str, Any]:
    if (
        strategy_group_id == "RBR-001"
        and stage == "observe_only_would_enter"
        and observed_row
        and registry_row
    ):
        return {
            "strategy_group_id": "RBR-001",
            "exit_decision": "park",
            "reason": "latest observe-only row exists, but range-boundary rejection remains L1/observe-only and lacks a bounded real loss envelope for the current July bullish/rebound mainline",
            "first_blocker": "rbr_loss_boundary_not_expressible_for_mainline",
            "next_action": "park_rbr_until_material_new_edge_or_loss_boundary_evidence",
            "post_action_expected_state": "parked_not_mainline_blocker",
            "evidence_source": "signal_coverage_observe_only_row + registry_row",
            "authority_boundary": "observe_only_exit_rule; no trial admission; no live authority",
        }
    rbr2_explicit_decision = str(
        candidate.get("strategy_asset_decision")
        or candidate.get("asset_state_decision")
        or candidate.get("review_outcome")
        or ""
    )
    if (
        strategy_group_id == "RBR2-001"
        and not rbr2_explicit_decision
        and stage == "role_only_intake_candidate"
    ):
        rbr2_explicit_decision = "merge_as_classifier"
    if strategy_group_id == "RBR2-001" and rbr2_explicit_decision:
        exit_decision = (
            "merge_as_classifier"
            if rbr2_explicit_decision
            in {"keep_observing", "merge", "merge_as_classifier"}
            else rbr2_explicit_decision
        )
        return {
            "strategy_group_id": "RBR2-001",
            "exit_decision": exit_decision,
            "reason": "RBR2 exit decision is projected only from explicit Strategy Asset State or candidate review outcome",
            "first_blocker": str(
                candidate.get("first_blocker")
                or "rbr2_explicit_asset_state_decision_present"
            ),
            "next_action": str(
                candidate.get("next_action")
                or "apply_rbr2_explicit_strategy_asset_state_decision"
            ),
            "post_action_expected_state": str(
                candidate.get("post_action_expected_state")
                or "strategy_asset_state_updated"
            ),
            "evidence_source": "explicit_candidate_strategy_asset_decision",
            "authority_boundary": "strategy_asset_state_exit_projection; no standalone submit authority",
        }
    return {}


def _policy_value(candidate: dict[str, Any], field: str, missing: list[str]) -> str:
    if field in missing:
        return "owner_policy_required"
    return str(candidate.get(field) or "not_applicable")


def _policy_recorded(artifact: dict[str, Any]) -> bool:
    policy = _as_dict(artifact.get("policy"))
    brf2_recorded = (
        artifact.get("status") == "brf2_owner_trial_policy_scope_recorded"
        and artifact.get("brf2_policy_scope_recorded") is True
        and artifact.get("owner_policy_scope_missing") is False
        and policy.get("strategy_group_id") == "BRF2-001"
    )
    cpm_recorded = (
        artifact.get("status") == "cpm_owner_trial_policy_scope_recorded"
        and artifact.get("cpm_policy_scope_recorded") is True
        and artifact.get("owner_policy_scope_missing") is False
        and policy.get("strategy_group_id") == "CPM-RO-001"
    )
    return brf2_recorded or cpm_recorded


def _portfolio_first_blocker(portfolio_seat: dict[str, Any]) -> dict[str, str]:
    blocker = _as_dict(portfolio_seat.get("first_blocker"))
    if not blocker:
        return {}
    decision_state = str(blocker.get("decision_state") or "")
    if not decision_state:
        return _classifier(
            "not_tradable_execution_gate",
            "portfolio_tradeability_decision_state_missing",
            "portfolio seat first_blocker is present but lacks an explicit Tradeability decision_state",
            "engineering",
            "repair_portfolio_tradeability_decision_evidence",
            "tradeability_decision_ready",
        )
    projection = _as_dict(portfolio_seat.get("tradeability_decision_evidence"))
    return _classifier(
        decision_state,
        str(blocker.get("first_blocker_class") or "fresh_signal_absent"),
        str(
            blocker.get("first_blocker_detail")
            or blocker.get("first_blocker_class")
            or "portfolio seat blocker"
        ),
        str(blocker.get("blocker_owner") or "market"),
        str(blocker.get("next_action") or "continue_armed_observation"),
        str(projection.get("next_state_after_blocker_removed") or "live_submit_ready"),
    )


def _secondary_blockers(
    blockers: list[str],
    classifier: dict[str, str],
    resolved_blockers: list[dict[str, str]] | None = None,
    *,
    strategy_group_id: str = "",
    cpm_admission_policy_closed: bool = False,
) -> list[dict[str, str]]:
    resolved = {row["blocker"] for row in resolved_blockers or []}
    rows: list[dict[str, str]] = []
    for blocker in blockers:
        if blocker in resolved:
            continue
        if (
            strategy_group_id == "CPM-RO-001"
            and cpm_admission_policy_closed
            and classifier["decision"] == "not_tradable_market_wait"
            and _cpm_market_wait_secondary_blocker_suppressed(blocker)
        ):
            continue
        klass = _class_for_blocker(blocker)
        if klass == classifier["first_blocker_class"]:
            continue
        rows.append({"blocker": blocker, "class": klass})
    return rows


def _resolved_blockers(
    blockers: list[str],
    *,
    strategy_group_id: str,
    owner_policy_recorded: bool,
    cpm_admission_policy_closed: bool = False,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if strategy_group_id == "BRF2-001" and owner_policy_recorded:
        for blocker in blockers:
            if _owner_policy_blocker_resolved_by_brf2_scope(blocker):
                rows.append(
                    {
                        "blocker": blocker,
                        "class": "policy",
                        "resolved_by": "brf2_owner_trial_policy_scope",
                    }
                )
        return rows
    if strategy_group_id != "CPM-RO-001" or not cpm_admission_policy_closed:
        return []
    for blocker in blockers:
        if _cpm_admission_policy_blocker_resolved(blocker):
            rows.append(
                {
                    "blocker": blocker,
                    "class": _class_for_blocker(blocker),
                    "resolved_by": "cpm_registry_identity_and_owner_trial_policy",
                }
            )
    return rows


def _owner_policy_blocker_resolved_by_brf2_scope(blocker: str) -> bool:
    lowered = blocker.lower()
    resolved_tokens = (
        "owner_capital_scope_not_confirmed",
        "owner_trial_identity_not_confirmed",
        "owner_policy_scope_not_confirmed",
        "capital_scope_not_confirmed",
        "trial_identity_not_confirmed",
    )
    return any(token in lowered for token in resolved_tokens)


def _cpm_admission_policy_blocker_resolved(blocker: str) -> bool:
    lowered = blocker.lower()
    resolved_tokens = (
        "registry_identity_unresolved",
        "identity_or_merge_review",
        "identity_review",
        "owner_capital_scope_not_confirmed",
        "owner_trial_identity_not_confirmed",
        "owner_policy_scope_not_confirmed",
        "capital_scope_not_confirmed",
        "trial_identity_not_confirmed",
    )
    return any(token in lowered for token in resolved_tokens)


def _cpm_market_wait_secondary_blocker_suppressed(blocker: str) -> bool:
    lowered = blocker.lower()
    suppressed_tokens = (
        "would_enter_forward_outcome_pending",
        "fresh_signal_absent",
        "action_time_finalgate_not_reached",
        "official_operation_layer_not_reached",
    )
    return any(token in lowered for token in suppressed_tokens)


def _evidence_snapshot(
    *,
    strategy_group_id: str,
    candidate: dict[str, Any],
    observed_row: dict[str, Any],
    cpm_admission_policy_closed: bool,
    classifier: dict[str, str],
) -> dict[str, Any]:
    candidate_status = str(candidate.get("candidate_status") or "")
    trial_recommendation = str(candidate.get("trial_recommendation") or "")
    if (
        strategy_group_id == "CPM-RO-001"
        and cpm_admission_policy_closed
        and classifier["decision"] == "not_tradable_market_wait"
    ):
        candidate_status = "armed_observation"
        trial_recommendation = "continue_cpm_long_armed_observation_until_fresh_signal"
    return {
        "recent_opportunity_count": _int(candidate.get("recent_opportunity_count")),
        "would_enter_forward_positive_count": _int(
            candidate.get("would_enter_forward_positive_count")
        ),
        "tradable_forward_count": _int(candidate.get("tradable_forward_count")),
        "ranking_score": _int(candidate.get("ranking_score")),
        "candidate_status": candidate_status,
        "trial_recommendation": trial_recommendation,
        "latest_observe_only_symbol": str(observed_row.get("symbol") or ""),
        "latest_observe_only_side": str(observed_row.get("side") or ""),
    }


def _class_for_blocker(blocker: str) -> str:
    return _contract_blocker_class(blocker)


def _consistency_checks(
    *,
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    runtime_safety_state: dict[str, Any],
) -> dict[str, bool]:
    return {
        "row_count_matches_decision_rows": summary["row_count"] == len(rows),
        "decision_rows_do_not_emit_legacy_authority_mirrors": all(
            "actionable_now" not in row and "real_order_authority" not in row
            for row in rows
        ),
        "tradable_now_scoped_to_live_submit": all(
            row["decision"] != "tradable_now"
            or _row_live_submit_ready(
                strategy_group_id=str(row.get("strategy_group_id") or ""),
                runtime_safety_state=runtime_safety_state,
            )
            for row in rows
        ),
        "first_blocker_classes_follow_contract": all(
            row["decision"] == "tradable_now"
            or row["first_blocker_class"] in CONTRACT_BLOCKER_CLASSES
            for row in rows
        ),
    }


def _summary(
    rows: list[dict[str, Any]],
    *,
    selected_strategy_group_id: str = "",
) -> dict[str, Any]:
    selected_candidate_top = next(
        (
            row
            for row in rows
            if str(row.get("strategy_group_id") or "") == selected_strategy_group_id
        ),
        {},
    )
    tradable_top = next(
        (
            row
            for row in sorted(
                rows,
                key=lambda row: _strategy_sort_key(
                    str(row.get("strategy_group_id") or "")
                ),
            )
            if row.get("decision") == "tradable_now"
        ),
        {},
    )
    ranked_status_top = (
        sorted(
            rows,
            key=lambda row: (
                DECISION_ORDER.get(str(row.get("decision")), 99),
                _strategy_sort_key(str(row.get("strategy_group_id") or "")),
            ),
        )[0]
        if rows
        else {}
    )
    top = tradable_top or selected_candidate_top or ranked_status_top
    by_decision: dict[str, int] = {}
    by_owner: dict[str, int] = {}
    for row in rows:
        by_decision[str(row["decision"])] = by_decision.get(str(row["decision"]), 0) + 1
        by_owner[str(row["blocker_owner"])] = by_owner.get(str(row["blocker_owner"]), 0) + 1
    trial_grade_standby_count = sum(
        _as_dict(row.get("signal_grade_status")).get("controlled_live_standby_ready")
        is True
        for row in rows
    )
    stage_5_ready_count = sum(
        _as_dict(row.get("signal_grade_status")).get(
            "stage_5_waiting_live_opportunity_ready"
        )
        is True
        for row in rows
    )
    return {
        "row_count": len(rows),
        "tradable_now_count": sum(row["decision"] == "tradable_now" for row in rows),
        "owner_first_blocker_count": by_owner.get("owner", 0),
        "engineering_first_blocker_count": by_owner.get("engineering", 0),
        "market_first_blocker_count": by_owner.get("market", 0),
        "runtime_first_blocker_count": by_owner.get("runtime", 0),
        "strategy_review_first_blocker_count": by_owner.get("strategy_review", 0),
        "by_decision": by_decision,
        "by_blocker_owner": by_owner,
        "controlled_live_standby_count": trial_grade_standby_count,
        "stage_5_waiting_live_opportunity_ready_count": stage_5_ready_count,
        "selected_strategy_group_id": selected_strategy_group_id,
        "selected_candidate_strategy_group_id": str(
            selected_candidate_top.get("strategy_group_id") or ""
        ),
        "selected_candidate_decision": str(
            selected_candidate_top.get("decision") or "none"
        ),
        "selected_candidate_first_blocker_class": str(
            selected_candidate_top.get("first_blocker_class") or "none"
        ),
        "selected_candidate_next_action": str(
            selected_candidate_top.get("next_action") or "none"
        ),
        "top_strategy_group_id": str(top.get("strategy_group_id") or ""),
        "top_decision": str(top.get("decision") or "none"),
        "top_first_blocker_class": str(top.get("first_blocker_class") or "none"),
        "top_next_action": str(top.get("next_action") or "none"),
    }


def _selected_strategy_group_id(
    *,
    capital_trial_envelope_projection: dict[str, Any],
    trial_asset_admission_proposal: dict[str, Any],
) -> str:
    proposal_id = str(
        _as_dict(trial_asset_admission_proposal.get("proposal")).get(
            "strategy_group_id"
        )
        or ""
    )
    if proposal_id:
        return proposal_id
    summary = _as_dict(capital_trial_envelope_projection.get("capital_trial_summary"))
    return str(
        summary.get("selected_short_strategy_group_id")
        or summary.get("selected_non_mpg_strategy_group_id")
        or _as_dict(capital_trial_envelope_projection.get("selected_non_mpg_trial_candidate")).get(
            "strategy_group_id"
        )
        or ""
    )


def _markdown(artifact: dict[str, Any], output_json: Path) -> str:
    summary = artifact["summary"]
    lines = [
        "## StrategyGroup Tradeability Decision",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Generated: `{artifact['generated_at_utc']}`",
        f"- Output JSON: `{output_json}`",
        f"- Decision rows: `{summary['row_count']}`",
        f"- Tradable now: `{summary['tradable_now_count']}`",
        f"- Top blocker: `{summary['top_strategy_group_id']}` / `{summary['top_decision']}` / `{summary['top_first_blocker_class']}`",
        f"- Next action: `{summary['top_next_action']}`",
        "",
        "## Decision Rows",
        "",
        "| StrategyGroup | Stage | Decision | First Blocker | Owner | Next Action | After |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in artifact["decision_rows"]:
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row["strategy_group_id"],
                row["stage"],
                row["decision"],
                row["first_blocker_class"],
                row["blocker_owner"],
                row["next_action"],
                row["after_next_state"],
            )
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- Tradeability Decision is a read model only.",
            "- It does not call FinalGate, Operation Layer, or exchange write.",
            "- Runtime Safety State remains the live-submit safety source; Execution Attempt remains the lifecycle entry object.",
        ]
    )
    return "\n".join(lines) + "\n"


def _forbidden_effects(*source_artifacts: dict[str, Any]) -> list[str]:
    return recursive_true_key_paths(*source_artifacts, true_keys=FORBIDDEN_TRUE_KEYS)


def _interaction() -> dict[str, Any]:
    return {
        "level": "L0_local_tradeability_decision",
        "remote_interaction_count": 0,
        "mutates_remote_files": False,
        "approaches_real_order": False,
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "calls_exchange_write": False,
        "places_order": False,
    }


def _strategy_sort_key(strategy_group_id: str) -> tuple[int, str]:
    priority = {
        "MPG-001": 0,
        "BRF2-001": 1,
        "RBR-001": 2,
        "RBR2-001": 3,
        "BTPC-001": 4,
        "LSR-001": 5,
        "BRF-001": 6,
        "MI-001": 7,
        "CPM-RO-001": 8,
    }
    return priority.get(strategy_group_id, 100), strategy_group_id


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _status(value: Any) -> str:
    return str(value.get("status") or "") if isinstance(value, dict) else ""


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _read_json(path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _yes_no(value: bool) -> str:
    return "是" if value else "否"


if __name__ == "__main__":
    raise SystemExit(main())
