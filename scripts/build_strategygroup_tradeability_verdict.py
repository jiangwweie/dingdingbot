#!/usr/bin/env python3
"""Build the StrategyGroup Tradeability Verdict read model.

The verdict answers one product question for every active or newly absorbed
candidate: can it trade now, and if not, what is the first blocker? It is
non-executing and must never create live authority.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_CAPITAL_TRIAL_BRIDGE_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-capital-trial-readiness-bridge.json"
)
DEFAULT_REGISTRY_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-registry-baseline.json"
)
DEFAULT_TIER_POLICY_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json"
)
DEFAULT_SIGNAL_COVERAGE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-signal-coverage-diagnostic.json"
)
DEFAULT_LIVE_SUBMIT_READINESS_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-live-submit-readiness-bridge.json"
)
DEFAULT_TRIAL_ASSET_ADMISSION_PROPOSAL_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-trial-asset-admission-proposal.json"
)
DEFAULT_BRF2_OWNER_TRIAL_POLICY_SCOPE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-owner-trial-policy-scope.json"
)
DEFAULT_THREE_STRATEGY_LIVE_TRIAL_PORTFOLIO_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-three-strategy-live-trial-portfolio.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-tradeability-verdict.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-tradeability-verdict.md"
)

SCHEMA = "brc.strategygroup_tradeability_verdict.v1"

VERDICT_ORDER = {
    "tradable_now": 0,
    "not_tradable_safety_stop": 1,
    "not_tradable_asset_admission": 2,
    "not_tradable_policy": 3,
    "not_tradable_facts": 4,
    "not_tradable_execution_gate": 5,
    "not_tradable_market_wait": 6,
    "not_tradable_strategy_quality": 7,
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
        "--capital-trial-readiness-bridge-json",
        default=str(DEFAULT_CAPITAL_TRIAL_BRIDGE_JSON),
    )
    parser.add_argument("--registry-json", default=str(DEFAULT_REGISTRY_JSON))
    parser.add_argument("--tier-policy-json", default=str(DEFAULT_TIER_POLICY_JSON))
    parser.add_argument(
        "--signal-coverage-json", default=str(DEFAULT_SIGNAL_COVERAGE_JSON)
    )
    parser.add_argument(
        "--live-submit-readiness-json",
        default=str(DEFAULT_LIVE_SUBMIT_READINESS_JSON),
    )
    parser.add_argument(
        "--trial-asset-admission-proposal-json",
        default=str(DEFAULT_TRIAL_ASSET_ADMISSION_PROPOSAL_JSON),
    )
    parser.add_argument(
        "--brf2-owner-trial-policy-scope-json",
        default=str(DEFAULT_BRF2_OWNER_TRIAL_POLICY_SCOPE_JSON),
    )
    parser.add_argument(
        "--three-strategy-live-trial-portfolio-json",
        default=str(DEFAULT_THREE_STRATEGY_LIVE_TRIAL_PORTFOLIO_JSON),
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    packet = build_tradeability_verdict(
        capital_trial_bridge=_read_json(Path(args.capital_trial_readiness_bridge_json)),
        registry=_read_json(Path(args.registry_json)),
        tier_policy=_read_json(Path(args.tier_policy_json)),
        signal_coverage=_read_json(Path(args.signal_coverage_json)),
        live_submit_readiness=_read_json(Path(args.live_submit_readiness_json)),
        trial_asset_admission_proposal=_read_optional_json(
            Path(args.trial_asset_admission_proposal_json)
        ),
        brf2_owner_trial_policy_scope=_read_optional_json(
            Path(args.brf2_owner_trial_policy_scope_json)
        ),
        three_strategy_live_trial_portfolio=_read_optional_json(
            Path(args.three_strategy_live_trial_portfolio_json)
        ),
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_owner_progress)
    _write_json(output_json, packet)
    _write_text(output_md, _markdown(packet, output_json))
    print(
        json.dumps(
            {
                "status": packet["status"],
                "row_count": packet["summary"]["row_count"],
                "top_verdict": packet["summary"]["top_verdict"],
                "top_strategy_group_id": packet["summary"]["top_strategy_group_id"],
                "actionable_now_count": packet["summary"]["actionable_now_count"],
                "output_json": str(output_json),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if packet["status"] == "tradeability_verdict_ready" else 2


def build_tradeability_verdict(
    *,
    capital_trial_bridge: dict[str, Any],
    registry: dict[str, Any],
    tier_policy: dict[str, Any],
    signal_coverage: dict[str, Any],
    live_submit_readiness: dict[str, Any],
    trial_asset_admission_proposal: dict[str, Any] | None = None,
    brf2_owner_trial_policy_scope: dict[str, Any] | None = None,
    three_strategy_live_trial_portfolio: dict[str, Any] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    forbidden_effects = _forbidden_effects(
        capital_trial_bridge,
        registry,
        tier_policy,
        signal_coverage,
        trial_asset_admission_proposal or {},
        brf2_owner_trial_policy_scope or {},
        three_strategy_live_trial_portfolio or {},
    )
    registry_rows = _registry_rows_by_id(registry)
    tier_rows = _tier_rows_by_id(tier_policy)
    candidate_rows = _candidate_rows_by_id(capital_trial_bridge)
    observed_rows = _observe_only_rows_by_id(signal_coverage)
    admission_proposals = _admission_proposals_by_id(
        trial_asset_admission_proposal or {}
    )
    owner_policy_scopes = _owner_policy_scopes_by_id(
        brf2_owner_trial_policy_scope or {}
    )
    portfolio_seats = _portfolio_seats_by_id(three_strategy_live_trial_portfolio or {})

    all_ids = set(candidate_rows)
    all_ids.update(tier_rows)
    all_ids.update(observed_rows)
    all_ids.update(admission_proposals)
    all_ids.update(owner_policy_scopes)
    all_ids.update(portfolio_seats)
    if "MPG-001" in registry_rows:
        all_ids.add("MPG-001")

    selected_strategy_group_id = _selected_strategy_group_id(
        capital_trial_bridge=capital_trial_bridge,
        trial_asset_admission_proposal=trial_asset_admission_proposal or {},
    )
    rows = [
        _verdict_row(
            strategy_group_id=strategy_group_id,
            candidate=candidate_rows.get(strategy_group_id, {}),
            registry_row=registry_rows.get(strategy_group_id, {}),
            tier_row=tier_rows.get(strategy_group_id, {}),
            observed_row=observed_rows.get(strategy_group_id, {}),
            admission_proposal=admission_proposals.get(strategy_group_id, {}),
            owner_policy_scope=owner_policy_scopes.get(strategy_group_id, {}),
            portfolio_seat=portfolio_seats.get(strategy_group_id, {}),
            live_submit_readiness=live_submit_readiness,
            forbidden_effects=forbidden_effects,
        )
        for strategy_group_id in sorted(all_ids, key=_strategy_sort_key)
    ]
    summary = _summary(rows, selected_strategy_group_id=selected_strategy_group_id)
    consistency_checks = _consistency_checks(
        rows=rows,
        summary=summary,
        live_submit_readiness=live_submit_readiness,
    )
    status = (
        "blocked_forbidden_effect"
        if forbidden_effects
        else "blocked_internal_consistency"
        if not all(consistency_checks.values())
        else "tradeability_verdict_ready"
        if rows
        else "tradeability_verdict_needs_input"
    )
    return {
        "schema": SCHEMA,
        "scope": "strategygroup_tradeability_verdict_read_model",
        "status": status,
        "generated_at_utc": generated_at_utc
        or datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "verdict_rows": rows,
        "owner_summary": {
            "state": "交易资格已判定",
            "top_strategy_group_id": summary["top_strategy_group_id"],
            "top_verdict": summary["top_verdict"],
            "top_first_blocker": summary["top_first_blocker_class"],
            "owner_policy_blocker_present": summary["owner_first_blocker_count"] > 0,
            "owner_intervention_required": False,
            "real_order_authority": summary["real_order_authority_count"] > 0,
            "actionable_now": summary["actionable_now_count"] > 0,
        },
        "checks": {
            "row_count": summary["row_count"],
            "one_current_verdict_per_strategy_group": len(rows)
            == len({row["strategy_group_id"] for row in rows}),
            "tradable_now_count": summary["tradable_now_count"],
            "actionable_now_count": summary["actionable_now_count"],
            "real_order_authority_count": summary["real_order_authority_count"],
            "forbidden_effects": forbidden_effects,
            "owner_policy_blocker_present": summary["owner_first_blocker_count"] > 0,
            "owner_decision_required": False,
            **consistency_checks,
            "market_wait_only_after_admission": all(
                row["verdict"] != "not_tradable_market_wait"
                or row["stage"]
                in {"armed_observation", "tiny_live_ready", "live_submit_ready"}
                for row in rows
            ),
        },
        "interaction": _interaction(),
        "safety_invariants": {
            "actionable_now": False,
            "real_order_authority": False,
            "verdict_generator_actionable_now": False,
            "verdict_generator_real_order_authority": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
    }


def _verdict_row(
    *,
    strategy_group_id: str,
    candidate: dict[str, Any],
    registry_row: dict[str, Any],
    tier_row: dict[str, Any],
    observed_row: dict[str, Any],
    admission_proposal: dict[str, Any],
    owner_policy_scope: dict[str, Any],
    portfolio_seat: dict[str, Any],
    live_submit_readiness: dict[str, Any],
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
        live_submit_readiness=live_submit_readiness,
    )
    classifier = _first_blocker(
        strategy_group_id=strategy_group_id,
        stage=stage,
        candidate=candidate,
        admission_proposal=admission_proposal,
        owner_policy_scope=owner_policy_scope,
        registry_present=registry_present,
        tier_present=tier_present,
        tier_row=tier_row,
        portfolio_seat=portfolio_seat,
        blockers=blockers,
        live_submit_readiness=live_submit_readiness,
        forbidden_effects=forbidden_effects,
    )
    actionable_now = classifier["verdict"] == "tradable_now"
    real_order_authority = classifier["verdict"] == "tradable_now"
    policy_scope = _policy_scope(candidate, portfolio_seat, owner_policy_scope)
    owner_policy_recorded = _policy_recorded(owner_policy_scope) or (
        admission_proposal.get("owner_policy_recorded") is True
        and admission_proposal.get("owner_policy_scope_missing") is False
    )
    return {
        "strategy_group_id": strategy_group_id,
        "stage": stage,
        "verdict": classifier["verdict"],
        "first_blocker_class": classifier["first_blocker_class"],
        "first_blocker_detail": classifier["first_blocker_detail"],
        "blocker_owner": classifier["blocker_owner"],
        "next_action": classifier["next_action"],
        "after_next_state": classifier["after_next_state"],
        "secondary_blockers": _secondary_blockers(blockers, classifier),
        "policy_scope": policy_scope,
        "required_facts_status": _required_facts_status(
            strategy_group_id=strategy_group_id,
            stage=stage,
            candidate=candidate,
            registry_row=registry_row,
            blockers=blockers,
        ),
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
        },
        "evidence_snapshot": {
            "recent_opportunity_count": _int(candidate.get("recent_opportunity_count")),
            "would_enter_forward_positive_count": _int(
                candidate.get("would_enter_forward_positive_count")
            ),
            "tradable_forward_count": _int(candidate.get("tradable_forward_count")),
            "ranking_score": _int(candidate.get("ranking_score")),
            "candidate_status": str(candidate.get("candidate_status") or ""),
            "trial_recommendation": str(candidate.get("trial_recommendation") or ""),
            "latest_observe_only_symbol": str(observed_row.get("symbol") or ""),
            "latest_observe_only_side": str(observed_row.get("side") or ""),
        },
        "actionable_now": actionable_now,
        "real_order_authority": real_order_authority,
        "authority_boundary": (
            "runtime_scoped_live_submit_ready; official_chain_may_continue"
            if actionable_now
            else "tradeability_verdict_is_read_model_only; actionable_now=false; "
            "real_order_authority=false; no_finalgate_no_operation_layer"
        ),
    }


def _first_blocker(
    *,
    strategy_group_id: str,
    stage: str,
    candidate: dict[str, Any],
    admission_proposal: dict[str, Any],
    owner_policy_scope: dict[str, Any],
    registry_present: bool,
    tier_present: bool,
    tier_row: dict[str, Any],
    portfolio_seat: dict[str, Any],
    blockers: list[str],
    live_submit_readiness: dict[str, Any],
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
    if stage == "observe_only_would_enter":
        return _classifier(
            "not_tradable_strategy_quality",
            "observe_only_signal_not_trial_candidate",
            "latest would-enter is observe-only and lacks trial/live scope",
            "strategy_review",
            "complete_observe_only_role_review_before_trial_admission",
            "trial_asset_admission_candidate",
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
    if strategy_group_id == "BRF2-001" and owner_policy_recorded:
        return _classifier(
            "not_tradable_facts",
            "required_facts_mapping_gap",
            "Owner trial policy is recorded; RequiredFacts mapping must close before armed observation",
            "engineering",
            "close_brf2_required_facts_mapping_for_armed_observation",
            "armed_observation",
        )

    if strategy_group_id == "MPG-001" and _mpg_waits_for_market(
        tier_row=tier_row,
        live_submit_readiness=live_submit_readiness,
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

    text = " ".join([stage, " ".join(blockers), str(candidate.get("identity_status") or "")]).lower()
    if (
        not registry_present
        or "registry_identity" in text
        or "execution_tier_not_in_policy_or_registry" in text
        or "identity_review" in text
        or "source_tiny_live_ready_false" in text
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
    if _row_live_submit_ready(
        strategy_group_id=strategy_group_id,
        live_submit_readiness=live_submit_readiness,
    ):
        return _classifier(
            "tradable_now",
            "official_runtime_chain_ready",
            "fresh signal, facts, authority, FinalGate, and Operation Layer are ready",
            "runtime",
            "continue_official_live_submit_chain",
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


def _classifier(
    verdict: str,
    first_blocker_class: str,
    first_blocker_detail: str,
    blocker_owner: str,
    next_action: str,
    after_next_state: str,
) -> dict[str, str]:
    return {
        "verdict": verdict,
        "first_blocker_class": first_blocker_class,
        "first_blocker_detail": first_blocker_detail,
        "blocker_owner": blocker_owner,
        "next_action": next_action,
        "after_next_state": after_next_state,
    }


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
    live_submit_readiness: dict[str, Any],
) -> str:
    if _row_live_submit_ready(
        strategy_group_id=strategy_group_id,
        live_submit_readiness=live_submit_readiness,
    ):
        return "live_submit_ready"
    owner_policy_recorded = _policy_recorded(owner_policy_scope) or (
        admission_proposal.get("owner_policy_recorded") is True
        and admission_proposal.get("owner_policy_scope_missing") is False
    )
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
        live_submit_readiness=live_submit_readiness,
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
    live_submit_readiness: dict[str, Any],
) -> bool:
    checks = _as_dict(live_submit_readiness.get("checks"))
    decision = _as_dict(live_submit_readiness.get("decision"))
    return (
        tier_row.get("mode") == "tiny_real_order_eligible"
        and checks.get("live_submit_ready") is False
        and decision.get("live_submit_ready_false_reason") == "no_fresh_signal"
    )


def _row_live_submit_ready(
    *,
    strategy_group_id: str,
    live_submit_readiness: dict[str, Any],
) -> bool:
    checks = _as_dict(live_submit_readiness.get("checks"))
    decision = _as_dict(live_submit_readiness.get("decision"))
    scoped_strategy_group_ids = _live_submit_strategy_group_ids(
        live_submit_readiness
    )
    return (
        checks.get("live_submit_ready") is True
        and decision.get("actionable_now") is True
        and decision.get("real_order_authority") is True
        and strategy_group_id in scoped_strategy_group_ids
    )


def _live_submit_strategy_group_ids(packet: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    id_keys = {
        "strategy_group_id",
        "selected_strategy_group_id",
        "selected_strategygroup_id",
        "runtime_strategy_group_id",
        "live_strategy_group_id",
    }
    ids_keys = {
        "strategy_group_ids",
        "selected_strategy_group_ids",
        "runtime_strategy_group_ids",
        "live_strategy_group_ids",
    }

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in id_keys and isinstance(item, str) and item:
                    ids.add(item)
                elif key in ids_keys and isinstance(item, list):
                    ids.update(str(entry) for entry in item if str(entry))
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(packet)
    return ids


def _candidate_rows_by_id(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in _dict_rows(packet.get("capital_trial_eligibility_rows")):
        strategy_id = str(row.get("strategy_group_id") or "")
        if strategy_id:
            rows[strategy_id] = row
    selected = _as_dict(packet.get("selected_non_mpg_trial_candidate"))
    selected_id = str(selected.get("strategy_group_id") or "")
    if selected_id:
        rows[selected_id] = {**rows.get(selected_id, {}), **selected}
    return rows


def _registry_rows_by_id(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("strategy_group_id")): row
        for row in _dict_rows(packet.get("rows"))
        if row.get("strategy_group_id")
    }


def _tier_rows_by_id(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = _as_dict(packet.get("current_strategy_groups"))
    return {str(key): _as_dict(value) for key, value in rows.items()}


def _observe_only_rows_by_id(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    broader = _as_dict(packet.get("broader_observation"))
    rows: dict[str, dict[str, Any]] = {}
    for row in _dict_rows(broader.get("would_enter_signals")):
        strategy_id = str(row.get("strategy_group_id") or "")
        if strategy_id:
            rows.setdefault(strategy_id, row)
    return rows


def _admission_proposals_by_id(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if _status(packet) != "trial_asset_admission_proposal_ready":
        return {}
    proposal = _as_dict(packet.get("proposal"))
    strategy_id = str(proposal.get("strategy_group_id") or "")
    return {strategy_id: proposal} if strategy_id else {}


def _owner_policy_scopes_by_id(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not _policy_recorded(packet):
        return {}
    policy = _as_dict(packet.get("policy"))
    strategy_id = str(policy.get("strategy_group_id") or "")
    return {strategy_id: packet} if strategy_id else {}


def _portfolio_seats_by_id(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not packet:
        return {}
    seats = _as_dict(packet.get("seat_readiness"))
    return {str(key): _as_dict(value) for key, value in seats.items()}


def _policy_scope(
    candidate: dict[str, Any],
    portfolio_seat: dict[str, Any],
    owner_policy_scope: dict[str, Any],
) -> dict[str, Any]:
    if _policy_recorded(owner_policy_scope):
        policy = _as_dict(owner_policy_scope.get("policy"))
        return {
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
    portfolio_scope = _as_dict(portfolio_seat.get("policy_scope"))
    if portfolio_scope:
        return {
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


def _policy_value(candidate: dict[str, Any], field: str, missing: list[str]) -> str:
    if field in missing:
        return "owner_policy_required"
    return str(candidate.get(field) or "not_applicable")


def _policy_recorded(packet: dict[str, Any]) -> bool:
    policy = _as_dict(packet.get("policy"))
    return (
        packet.get("status") == "brf2_owner_trial_policy_scope_recorded"
        and packet.get("brf2_policy_scope_recorded") is True
        and packet.get("owner_policy_scope_missing") is False
        and policy.get("strategy_group_id") == "BRF2-001"
    )


def _portfolio_first_blocker(portfolio_seat: dict[str, Any]) -> dict[str, str]:
    blocker = _as_dict(portfolio_seat.get("first_blocker"))
    if not blocker:
        return {}
    projection = _as_dict(portfolio_seat.get("tradeability_projection"))
    return _classifier(
        str(blocker.get("verdict") or "not_tradable_market_wait"),
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


def _required_facts_status(
    *,
    strategy_group_id: str,
    stage: str,
    candidate: dict[str, Any],
    registry_row: dict[str, Any],
    blockers: list[str],
) -> str:
    text = " ".join(blockers).lower()
    if strategy_group_id == "MPG-001":
        return "action_time_only"
    if candidate.get("required_facts_draft"):
        return "missing"
    if any(token in text for token in ("fact", "stale", "classifier", "rewrite", "squeeze")):
        return "missing"
    if registry_row.get("required_facts_summary"):
        return "action_time_only"
    if stage in {"role_only_intake_candidate", "observe_only_would_enter"}:
        return "not_applicable"
    return "missing"


def _secondary_blockers(
    blockers: list[str],
    classifier: dict[str, str],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for blocker in blockers:
        klass = _class_for_blocker(blocker)
        if klass == classifier["first_blocker_class"]:
            continue
        rows.append({"blocker": blocker, "class": klass})
    return rows


def _class_for_blocker(blocker: str) -> str:
    lowered = blocker.lower()
    if any(token in lowered for token in ("registry", "identity", "tier", "tiny_live_ready")):
        return "asset_admission"
    if any(token in lowered for token in ("owner", "capital", "trial_identity")):
        return "policy"
    if any(token in lowered for token in ("fact", "stale", "classifier", "rewrite", "squeeze", "forward", "range")):
        return "facts"
    if "fresh_signal" in lowered:
        return "market"
    if any(token in lowered for token in ("finalgate", "operation_layer", "exchange", "account", "protection")):
        return "execution_gate"
    if any(token in lowered for token in ("stop", "overfit", "role", "filler", "quality")):
        return "strategy_quality"
    return "review"


def _consistency_checks(
    *,
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    live_submit_readiness: dict[str, Any],
) -> dict[str, bool]:
    return {
        "row_count_matches_verdict_rows": summary["row_count"] == len(rows),
        "tradable_now_rows_have_authority": all(
            row["verdict"] != "tradable_now"
            or (
                row.get("actionable_now") is True
                and row.get("real_order_authority") is True
            )
            for row in rows
        ),
        "authority_rows_are_tradable_now": all(
            not (
                row.get("actionable_now") is True
                or row.get("real_order_authority") is True
            )
            or row["verdict"] == "tradable_now"
            for row in rows
        ),
        "tradable_now_scoped_to_live_submit": all(
            row["verdict"] != "tradable_now"
            or _row_live_submit_ready(
                strategy_group_id=str(row.get("strategy_group_id") or ""),
                live_submit_readiness=live_submit_readiness,
            )
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
            if row.get("verdict") == "tradable_now"
        ),
        {},
    )
    fallback_top = (
        sorted(
            rows,
            key=lambda row: (
                VERDICT_ORDER.get(str(row.get("verdict")), 99),
                _strategy_sort_key(str(row.get("strategy_group_id") or "")),
            ),
        )[0]
        if rows
        else {}
    )
    top = tradable_top or selected_candidate_top or fallback_top
    by_verdict: dict[str, int] = {}
    by_owner: dict[str, int] = {}
    for row in rows:
        by_verdict[str(row["verdict"])] = by_verdict.get(str(row["verdict"]), 0) + 1
        by_owner[str(row["blocker_owner"])] = by_owner.get(str(row["blocker_owner"]), 0) + 1
    return {
        "row_count": len(rows),
        "tradable_now_count": sum(row["verdict"] == "tradable_now" for row in rows),
        "actionable_now_count": sum(
            row.get("actionable_now") is True for row in rows
        ),
        "real_order_authority_count": sum(
            row.get("real_order_authority") is True for row in rows
        ),
        "owner_first_blocker_count": by_owner.get("owner", 0),
        "engineering_first_blocker_count": by_owner.get("engineering", 0),
        "market_first_blocker_count": by_owner.get("market", 0),
        "runtime_first_blocker_count": by_owner.get("runtime", 0),
        "strategy_review_first_blocker_count": by_owner.get("strategy_review", 0),
        "by_verdict": by_verdict,
        "by_blocker_owner": by_owner,
        "selected_strategy_group_id": selected_strategy_group_id,
        "selected_candidate_strategy_group_id": str(
            selected_candidate_top.get("strategy_group_id") or ""
        ),
        "selected_candidate_verdict": str(
            selected_candidate_top.get("verdict") or "none"
        ),
        "selected_candidate_first_blocker_class": str(
            selected_candidate_top.get("first_blocker_class") or "none"
        ),
        "selected_candidate_next_action": str(
            selected_candidate_top.get("next_action") or "none"
        ),
        "top_strategy_group_id": str(top.get("strategy_group_id") or ""),
        "top_verdict": str(top.get("verdict") or "none"),
        "top_first_blocker_class": str(top.get("first_blocker_class") or "none"),
        "top_next_action": str(top.get("next_action") or "none"),
    }


def _selected_strategy_group_id(
    *,
    capital_trial_bridge: dict[str, Any],
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
    summary = _as_dict(capital_trial_bridge.get("capital_trial_summary"))
    return str(
        summary.get("selected_short_strategy_group_id")
        or summary.get("selected_non_mpg_strategy_group_id")
        or _as_dict(capital_trial_bridge.get("selected_non_mpg_trial_candidate")).get(
            "strategy_group_id"
        )
        or ""
    )


def _markdown(packet: dict[str, Any], output_json: Path) -> str:
    summary = packet["summary"]
    lines = [
        "## StrategyGroup Tradeability Verdict",
        "",
        f"- Status: `{packet['status']}`",
        f"- Generated: `{packet['generated_at_utc']}`",
        f"- Output JSON: `{output_json}`",
        f"- Verdict rows: `{summary['row_count']}`",
        f"- Tradable now: `{summary['tradable_now_count']}`",
        f"- Top blocker: `{summary['top_strategy_group_id']}` / `{summary['top_verdict']}` / `{summary['top_first_blocker_class']}`",
        f"- Next action: `{summary['top_next_action']}`",
        f"- Real order authority: `{_yes_no(summary['real_order_authority_count'] > 0)}`",
        "",
        "## Verdict Rows",
        "",
        "| StrategyGroup | Stage | Verdict | First Blocker | Owner | Next Action | After |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in packet["verdict_rows"]:
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row["strategy_group_id"],
                row["stage"],
                row["verdict"],
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
            "- Verdict is a read model only.",
            "- It does not call FinalGate, Operation Layer, or exchange write.",
            "- It does not set actionable_now or real_order_authority.",
        ]
    )
    return "\n".join(lines) + "\n"


def _forbidden_effects(*packets: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for index, packet in enumerate(packets):
        _walk_forbidden(packet, prefix=f"source[{index}]", found=found)
    return list(dict.fromkeys(found))


def _walk_forbidden(value: Any, *, prefix: str, found: list[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}"
            if key in FORBIDDEN_TRUE_KEYS and item is True:
                found.append(path)
            _walk_forbidden(item, prefix=path, found=found)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk_forbidden(item, prefix=f"{prefix}[{index}]", found=found)


def _interaction() -> dict[str, Any]:
    return {
        "level": "L0_local_tradeability_verdict",
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
