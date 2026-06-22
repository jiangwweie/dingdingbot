#!/usr/bin/env python3
"""Build a review-only Capital Trial Readiness Bridge.

This command converts the StrategyGroup Portfolio Board trial pool into a
pre-registered capital-trial readiness packet. It is non-executing: it never
changes registry authority, tier policy, live profiles, order sizing, FinalGate,
Operation Layer, exchange state, or real-order authority.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_PORTFOLIO_BOARD_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-portfolio-board.json"
)
DEFAULT_CAPTURE_GAP_AUDIT_JSON = (
    REPO_ROOT / "output/runtime-monitor/strategy-capture-gap-audit-20260622.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-capital-trial-readiness-bridge.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-capital-trial-readiness-bridge.md"
)
DEFAULT_TRIAL_PACKET_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-capital-trial-packet-v0.json"
)
DEFAULT_TRIAL_PACKET_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-capital-trial-packet-v0.md"
)
DEFAULT_RESEARCH_INTAKE_REVIEW_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-research-intake-review.json"
)

SCHEMA = "brc.strategygroup_capital_trial_readiness_bridge.v1"
TRIAL_PACKET_SCHEMA = "brc.strategygroup_capital_trial_packet.v0"

FORBIDDEN_EFFECTS = (
    "actionable_now",
    "real_order_authority",
    "registry_authority_changed",
    "tier_policy_changed",
    "live_profile_changed",
    "order_sizing_changed",
    "mpg_member_live_scope_expanded",
    "l4_real_order_scope_expanded",
    "shadow_candidate_created",
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
)

TRIAL_REVIEW_ORDER = (
    "MI-001",
    "LSR-001",
    "BRF-001",
    "CPM-RO-001",
    "BTPC-001",
)
SHORT_RESEARCH_INTAKE_ORDER = (
    "BRF2-001",
    "RBR2-001",
)

OWNER_POLICY_FIELDS = (
    "capital_scope",
    "max_notional",
    "valid_until",
    "slippage_limit",
    "trial_identity",
)

BRF2_PROMOTION_SCOPE = "intake_only"
BRF2_PROMOTION_TARGET = "paper_observation_or_candidate_trade_packet"
BRF2_PROMOTION_REASON = "promote_to_tiny_live_intake_candidate_not_live_ready"
BRF2_NEXT_CHECKPOINT = "BRF2-001_tiny_live_intake_candidate_packet"
BRF2_REQUIRED_NEXT_EVIDENCE = (
    "owner_policy_scope",
    "paper_observation_packet",
    "RequiredFacts draft",
    "disable facts",
    "path-risk review",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--portfolio-board-json", default=str(DEFAULT_PORTFOLIO_BOARD_JSON)
    )
    parser.add_argument(
        "--capture-gap-audit-json", default=str(DEFAULT_CAPTURE_GAP_AUDIT_JSON)
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument(
        "--output-trial-packet-json", default=str(DEFAULT_TRIAL_PACKET_JSON)
    )
    parser.add_argument("--output-trial-packet-md", default=str(DEFAULT_TRIAL_PACKET_MD))
    parser.add_argument(
        "--research-intake-review-json",
        default="",
        help=(
            "Optional main-control research intake review artifact. When supplied, "
            "paper-observation short candidates can enter the candidate-trade pool "
            "without live authority."
        ),
    )
    args = parser.parse_args(argv)

    portfolio_board = _read_json(Path(args.portfolio_board_json))
    capture_gap_audit = _read_json(Path(args.capture_gap_audit_json))
    research_intake_review = (
        _read_json(Path(args.research_intake_review_json))
        if args.research_intake_review_json
        else None
    )
    packet = build_capital_trial_readiness_bridge(
        portfolio_board=portfolio_board,
        capture_gap_audit=capture_gap_audit,
        research_intake_review=research_intake_review,
    )
    trial_packet = packet["trial_packet_v0"]

    output_json = Path(args.output_json)
    output_md = Path(args.output_owner_progress)
    trial_json = Path(args.output_trial_packet_json)
    trial_md = Path(args.output_trial_packet_md)
    _write_json(output_json, packet)
    _write_text(output_md, _bridge_markdown(packet, output_json, trial_json))
    _write_json(trial_json, trial_packet)
    _write_text(trial_md, _trial_packet_markdown(trial_packet, trial_json))

    print(
        json.dumps(
            {
                "status": packet["status"],
                "selected_non_mpg_strategy_group_id": packet[
                    "capital_trial_summary"
                ]["selected_non_mpg_strategy_group_id"],
                "trial_packet_generated": packet["capital_trial_summary"][
                    "trial_packet_generated"
                ],
                "actionable_now_count": packet["capital_trial_summary"][
                    "actionable_now_count"
                ],
                "output_json": str(output_json),
            },
            ensure_ascii=False,
        )
    )
    return 0 if packet["status"] == "capital_trial_readiness_bridge_ready" else 2


def build_capital_trial_readiness_bridge(
    *,
    portfolio_board: dict[str, Any],
    capture_gap_audit: dict[str, Any],
    research_intake_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _validate_safety("portfolio_board", portfolio_board)
    _validate_safety("capture_gap_audit", capture_gap_audit)
    if research_intake_review is not None:
        _validate_safety("research_intake_review", research_intake_review)

    portfolio_rows = _portfolio_rows_by_id(portfolio_board)
    trial_pool_rows = _trial_pool_rows_by_id(portfolio_board)
    audit_rows = _audit_rows_by_id(capture_gap_audit)
    would_enter_events = _would_enter_events_by_id(capture_gap_audit)
    research_rows = _research_intake_rows_by_id(research_intake_review or {})
    generated_at = datetime.now(timezone.utc).isoformat()

    eligibility_rows = [
        _eligibility_row_for_strategy(
            strategy_group_id=strategy_group_id,
            portfolio_rows=portfolio_rows,
            trial_pool_rows=trial_pool_rows,
            audit_rows=audit_rows,
            would_enter_events=would_enter_events,
            research_rows=research_rows,
        )
        for strategy_group_id in _trial_review_order(research_rows)
    ]
    ranking = sorted(
        eligibility_rows,
        key=lambda row: (
            -int(row["ranking_score"]),
            _trial_review_order(research_rows).index(row["strategy_group_id"]),
        ),
    )
    selected = next(
        (
            row
            for row in ranking
            if row["strategy_group_id"] != "MPG-001"
            and (
                row["trial_recommendation"].startswith("candidate_trade_prepare")
                or row["trial_recommendation"].startswith("trial_prepare")
            )
        ),
        ranking[0] if ranking else {},
    )
    trial_packet = _trial_packet_v0(selected, generated_at=generated_at)
    continuation_queue = [
        _engineering_continuation_item(row)
        for row in eligibility_rows
        if row["engineering_continue"] is True
    ]
    policy_checkpoint = _owner_policy_checkpoint(selected)
    safety = _safety_invariants()

    reject_reasons = _bridge_reject_reasons(
        eligibility_rows=eligibility_rows,
        ranking=ranking,
        selected=selected,
        trial_packet=trial_packet,
        safety=safety,
    )
    status = (
        "capital_trial_readiness_bridge_ready"
        if not reject_reasons
        else "capital_trial_readiness_bridge_needs_work"
    )

    return {
        "schema": SCHEMA,
        "scope": "strategygroup_capital_trial_readiness_bridge_review_only",
        "status": status,
        "generated_at_utc": generated_at,
        "runtime_posture": {
            "p0_state": "waiting_for_market",
            "p0_5_state": "capital_trial_prepare_candidate_selected",
            "runtime_owner_intervention_required": False,
            "no_live_permission": True,
        },
        "capital_trial_summary": {
            "portfolio_row_count": len(portfolio_rows),
            "eligibility_row_count": len(eligibility_rows),
            "non_mpg_trial_candidate_count": sum(
                1
                for row in eligibility_rows
                if row["strategy_group_id"] != "MPG-001"
                and row["trial_recommendation"] != "not_a_trial_candidate_now"
            ),
            "selected_non_mpg_strategy_group_id": selected.get("strategy_group_id"),
            "selected_candidate_status": selected.get("candidate_status"),
            "trial_packet_generated": bool(trial_packet),
            "actionable_now_count": 0,
            "live_permission_change_count": 0,
            "real_order_authority_count": 0,
            "short_candidate_trade_count": sum(
                1
                for row in eligibility_rows
                if row.get("candidate_family") == "short_research_intake"
                and row["trial_recommendation"].startswith(
                    "candidate_trade_prepare"
                )
            ),
            "selected_short_strategy_group_id": (
                selected.get("strategy_group_id")
                if selected.get("candidate_family") == "short_research_intake"
                else None
            ),
            "owner_policy_checkpoint_count": 1 if policy_checkpoint else 0,
            "engineering_continuation_count": len(continuation_queue),
        },
        "capital_trial_eligibility_rows": eligibility_rows,
        "non_mpg_trial_candidate_ranking": ranking,
        "selected_non_mpg_trial_candidate": selected,
        "trial_packet_v0": trial_packet,
        "owner_policy_checkpoint": policy_checkpoint,
        "engineering_continuation_queue": continuation_queue,
        "goal_progress_projection": {
            "p05_capital_trial": selected.get("candidate_status"),
            "promotion_scope": selected.get("promotion_scope") or "not_applicable",
            "tiny_live_ready": selected.get("tiny_live_ready") is True,
            "owner_intervention_required": False,
            "owner_policy_decision_required_later": True,
            "no_live_permission": True,
            "summary": (
                "First non-MPG short experiment candidate selected from "
                "review-only evidence; promotion scope is intake-only and "
                "this is not live execution permission."
            ),
        },
        "reject_reasons": reject_reasons,
        "interaction": _interaction(),
        "safety_invariants": safety,
        "source_status": {
            "portfolio_board": str(portfolio_board.get("status") or "unknown"),
            "capture_gap_audit": str(capture_gap_audit.get("status") or "unknown"),
            "research_intake_review": str(
                (research_intake_review or {}).get("status") or "not_supplied"
            ),
            "would_enter_sampled_count": len(
                capture_gap_audit.get("would_enter_events")
                if isinstance(capture_gap_audit.get("would_enter_events"), list)
                else []
            ),
        },
    }


def _trial_review_order(
    research_rows: dict[str, dict[str, Any]],
) -> list[str]:
    return _dedupe(
        [
            strategy_group_id
            for strategy_group_id in SHORT_RESEARCH_INTAKE_ORDER
            if strategy_group_id in research_rows
        ]
        + list(TRIAL_REVIEW_ORDER)
    )


def _eligibility_row_for_strategy(
    *,
    strategy_group_id: str,
    portfolio_rows: dict[str, dict[str, Any]],
    trial_pool_rows: dict[str, dict[str, Any]],
    audit_rows: dict[str, dict[str, Any]],
    would_enter_events: dict[str, list[dict[str, Any]]],
    research_rows: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    research_row = research_rows.get(strategy_group_id)
    if research_row is not None:
        return _research_intake_eligibility_row(
            strategy_group_id=strategy_group_id,
            research_row=research_row,
        )
    return _eligibility_row(
        strategy_group_id=strategy_group_id,
        portfolio_row=portfolio_rows.get(strategy_group_id, {}),
        trial_pool_row=trial_pool_rows.get(strategy_group_id, {}),
        audit_row=audit_rows.get(strategy_group_id, {}),
        sampled_events=would_enter_events.get(strategy_group_id, []),
    )


def _research_intake_eligibility_row(
    *,
    strategy_group_id: str,
    research_row: dict[str, Any],
) -> dict[str, Any]:
    evidence = _as_dict(research_row.get("path_risk_evidence"))
    opportunity_count = _int(
        evidence.get("accepted_event_count")
        or evidence.get("accepted_events")
        or evidence.get("sample_event_count")
    )
    forward_positive = _int(
        evidence.get("path_safe_count") or evidence.get("path_safe_5m_count")
    )
    if opportunity_count == 0 and forward_positive > 0:
        opportunity_count = forward_positive
    direction = str(research_row.get("strategy_direction") or "unknown")
    blockers = _research_intake_blockers(research_row)
    recommendation, candidate_status = _research_trial_recommendation(
        strategy_group_id=strategy_group_id,
        research_row=research_row,
    )
    promotion = _research_promotion_semantics(
        strategy_group_id=strategy_group_id,
        recommendation=recommendation,
    )
    ranking_score = _research_ranking_score(
        strategy_group_id=strategy_group_id,
        opportunity_count=opportunity_count,
        forward_positive=forward_positive,
        blockers=blockers,
    )
    return {
        "strategy_group_id": strategy_group_id,
        "candidate_family": "short_research_intake",
        "execution_tier": "unknown",
        "evidence_stage": str(
            research_row.get("main_control_intake_position")
            or "research_intake_review"
        ),
        "pool_stage": str(
            research_row.get("source_recommended_runtime_stage")
            or "research_intake_candidate"
        ),
        "candidate_status": candidate_status,
        "recent_opportunity_count": opportunity_count,
        "would_enter_forward_positive_count": forward_positive,
        "tradable_forward_count": forward_positive,
        "forward_pending_count": 0,
        "sampled_event_count": opportunity_count,
        "dominant_sampled_candidate_id": strategy_group_id,
        "symbol_scope": _research_symbol_scope(research_row),
        "side_scope": ["short"] if "short" in direction else [],
        "dominant_blocker": blockers[0] if blockers else "none",
        "identity_status": "main_control_research_intake_asset",
        "risk_boundary_ready": False,
        "risk_boundary_missing": list(OWNER_POLICY_FIELDS),
        "trial_blockers": blockers,
        "ranking_score": ranking_score,
        "trial_recommendation": recommendation,
        **promotion,
        "owner_policy_required": recommendation.startswith(
            "candidate_trade_prepare"
        ),
        "owner_policy_required_now": False,
        "engineering_continue": recommendation != "not_a_trial_candidate_now",
        "actionable_now": False,
        "live_permission_change": False,
        "real_order_authority": False,
        "does_not_authorize_live_execution": True,
        "research_intake_position": str(
            research_row.get("main_control_intake_position") or "unknown"
        ),
        "required_facts_draft": _string_list(
            research_row.get("required_facts_draft")
        ),
        "disable_or_review_facts_draft": _string_list(
            research_row.get("disable_or_review_facts_draft")
        ),
        "risk_envelope": _as_dict(research_row.get("risk_envelope")),
        "path_risk_evidence": evidence,
        "paper_observation_packet_shape": _as_dict(
            research_row.get("paper_observation_packet_shape")
        ),
    }


def _eligibility_row(
    *,
    strategy_group_id: str,
    portfolio_row: dict[str, Any],
    trial_pool_row: dict[str, Any],
    audit_row: dict[str, Any],
    sampled_events: list[dict[str, Any]],
) -> dict[str, Any]:
    opportunity_count = _int(
        portfolio_row.get("recent_opportunity_count") or audit_row.get("would_enter_count")
    )
    forward_positive = _int(
        portfolio_row.get("would_enter_forward_positive_count")
        or audit_row.get("would_enter_forward_positive_count")
    )
    completed_tradable = _max_tradable_after_cost(audit_row)
    pending_count = _pending_forward_count(audit_row)
    symbol_scope, side_scope, dominant_candidate = _sampled_scope(sampled_events)
    blockers = _trial_blockers(
        strategy_group_id=strategy_group_id,
        portfolio_row=portfolio_row,
        trial_pool_row=trial_pool_row,
        audit_row=audit_row,
        sampled_events=sampled_events,
    )
    ranking_score = _ranking_score(
        strategy_group_id=strategy_group_id,
        opportunity_count=opportunity_count,
        forward_positive=forward_positive,
        tradable_count=completed_tradable,
        blockers=blockers,
    )
    recommendation, candidate_status = _trial_recommendation(
        strategy_group_id=strategy_group_id,
        opportunity_count=opportunity_count,
        forward_positive=forward_positive,
        blockers=blockers,
    )
    owner_policy_required = recommendation.startswith("trial_prepare")
    return {
        "strategy_group_id": strategy_group_id,
        "candidate_family": "portfolio_capture_gap",
        "execution_tier": str(portfolio_row.get("execution_tier") or "unknown"),
        "evidence_stage": str(portfolio_row.get("evidence_stage") or "unknown"),
        "pool_stage": str(trial_pool_row.get("pool_stage") or "not_in_trial_pool"),
        "candidate_status": candidate_status,
        "recent_opportunity_count": opportunity_count,
        "would_enter_forward_positive_count": forward_positive,
        "tradable_forward_count": completed_tradable,
        "forward_pending_count": pending_count,
        "sampled_event_count": len(sampled_events),
        "dominant_sampled_candidate_id": dominant_candidate,
        "symbol_scope": symbol_scope,
        "side_scope": side_scope,
        "dominant_blocker": _dominant_blocker(audit_row, blockers),
        "identity_status": _identity_status(strategy_group_id, portfolio_row, blockers),
        "risk_boundary_ready": False,
        "risk_boundary_missing": list(OWNER_POLICY_FIELDS),
        "trial_blockers": blockers,
        "ranking_score": ranking_score,
        "trial_recommendation": recommendation,
        "decision": "pending",
        "reason": recommendation,
        "promotion_scope": "not_applicable",
        "promotion_target": "not_applicable",
        "tiny_live_ready": False,
        "next_checkpoint": f"{strategy_group_id}_capital_trial_review",
        "required_next_evidence": [],
        "authority_boundary_summary": (
            "promotion_scope=not_applicable; tiny_live_ready=false; "
            "actionable_now=false; real_order_authority=false"
        ),
        "owner_policy_required": owner_policy_required,
        "owner_policy_required_now": False,
        "engineering_continue": recommendation != "not_a_trial_candidate_now",
        "actionable_now": False,
        "live_permission_change": False,
        "real_order_authority": False,
        "does_not_authorize_live_execution": True,
    }


def _trial_packet_v0(
    selected: dict[str, Any],
    *,
    generated_at: str,
) -> dict[str, Any]:
    strategy_group_id = str(selected.get("strategy_group_id") or "")
    return {
        "schema": TRIAL_PACKET_SCHEMA,
        "packet_id": f"trial-packet-v0:{strategy_group_id}:20260622",
        "generated_at_utc": generated_at,
        "strategy_group_id": strategy_group_id,
        "decision": selected.get("decision") or "pending",
        "reason": selected.get("reason") or selected.get("trial_recommendation"),
        "promotion_scope": selected.get("promotion_scope") or "not_applicable",
        "promotion_target": selected.get("promotion_target") or "not_applicable",
        "tiny_live_ready": selected.get("tiny_live_ready") is True,
        "next_checkpoint": selected.get("next_checkpoint")
        or f"{strategy_group_id}_capital_trial_review",
        "required_next_evidence": selected.get("required_next_evidence") or [],
        "candidate_status": selected.get("candidate_status")
        or "trial_prepare_candidate_pending_owner_policy",
        "hypothesis": (
            "BRF2-001 bear-rally-failure short has a research-intake paper "
            "observation asset with explicit path-risk evidence, RequiredFacts "
            "draft, disable/review facts, and risk envelope. It can be prepared "
            "as a non-executing candidate-trade packet, pending Owner policy "
            "scope and future official live gates."
            if strategy_group_id == "BRF2-001"
            else "RBR2-001 range-upper-boundary short is role-only intake material "
            "for range detector and failed-upside-expansion classifier review; "
            "it is not the primary candidate-trade lane."
            if strategy_group_id == "RBR2-001"
            else
            "MI-001 SOL long momentum-impulse observe-only samples have enough "
            "recent cost-after-MFE evidence to prepare a bounded capital trial, "
            "but identity, capital scope, and live-action facts remain unresolved."
            if strategy_group_id == "MI-001"
            else "Selected StrategyGroup has review-only evidence for a future bounded capital trial."
        ),
        "evidence_refs": {
            "portfolio_board": str(DEFAULT_PORTFOLIO_BOARD_JSON),
            "capture_gap_audit": str(DEFAULT_CAPTURE_GAP_AUDIT_JSON),
            "recent_opportunity_count": selected.get("recent_opportunity_count"),
            "would_enter_forward_positive_count": selected.get(
                "would_enter_forward_positive_count"
            ),
            "tradable_forward_count": selected.get("tradable_forward_count"),
            "sampled_event_count": selected.get("sampled_event_count"),
            "research_intake_position": selected.get("research_intake_position"),
        },
        "symbol_scope": selected.get("symbol_scope") or ["owner_policy_required"],
        "side_scope": selected.get("side_scope") or ["owner_policy_required"],
        "required_facts_draft": selected.get("required_facts_draft") or [],
        "disable_or_review_facts_draft": (
            selected.get("disable_or_review_facts_draft") or []
        ),
        "risk_envelope": selected.get("risk_envelope") or {},
        "path_risk_evidence": selected.get("path_risk_evidence") or {},
        "paper_observation_packet_shape": (
            selected.get("paper_observation_packet_shape") or {}
        ),
        "trial_boundary": {
            "max_notional": "owner_policy_required",
            "max_attempts": 1,
            "valid_until": "owner_policy_required",
            "capital_scope": "owner_policy_required",
            "slippage_limit": "owner_policy_required",
            "fresh_signal_required": True,
            "required_facts_required": True,
            "candidate_authorization_required": True,
            "action_time_finalgate_required": True,
            "official_operation_layer_required": True,
            "exchange_native_protection_required": True,
        },
        "stop_policy": {
            "required": True,
            "policy": "exchange_native_stop_or_official_protection_required_before_submit",
        },
        "kill_conditions": [
            "owner_policy_not_accepted",
            "strategy_identity_unresolved",
            "fresh_signal_absent",
            "required_facts_missing_or_stale",
            "candidate_authorization_missing",
            "action_time_finalgate_not_passed",
            "official_operation_layer_not_passed",
            "protection_plan_missing",
            "active_position_or_open_order_conflict",
            "slippage_above_owner_policy",
            "reconciliation_or_settlement_unavailable",
        ],
        "review_fields": [
            "submit_attempt_id",
            "fill_status",
            "avg_fill_price",
            "slippage",
            "fees",
            "funding",
            "mfe",
            "mae",
            "pnl",
            "protection_status",
            "reconciliation_status",
            "settlement_status",
            "review_decision",
        ],
        "authority_boundary": {
            "pre_registered_review_only": True,
            "promotion_scope": selected.get("promotion_scope") or "not_applicable",
            "promotion_scope_is_intake_only": (
                selected.get("promotion_scope") == BRF2_PROMOTION_SCOPE
            ),
            "tiny_live_ready": selected.get("tiny_live_ready") is True,
            "unscoped_promote": False,
            "actionability_source": "runtime_only",
            "actionable_now": False,
            "live_permission_change": False,
            "real_order_authority": False,
            "registry_admission": False,
            "tier_policy_change": False,
            "live_profile_change": False,
            "order_sizing_change": False,
            "creates_execution_intent": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
            "preview_or_replay_treated_as_live_signal": False,
        },
        "requires_owner_policy_acceptance": True,
        "requires_fresh_signal": True,
        "requires_required_facts": True,
        "requires_finalgate": True,
        "requires_operation_layer": True,
        "actionable_now": False,
        "live_permission_change": False,
        "real_order_authority": False,
    }


def _trial_blockers(
    *,
    strategy_group_id: str,
    portfolio_row: dict[str, Any],
    trial_pool_row: dict[str, Any],
    audit_row: dict[str, Any],
    sampled_events: list[dict[str, Any]],
) -> list[str]:
    blockers = [
        str(item)
        for item in (
            trial_pool_row.get("trial_blockers")
            or portfolio_row.get("evidence_gaps")
            or []
        )
        if str(item)
    ]
    if strategy_group_id in {"MI-001", "CPM-RO-001"}:
        blockers.append("registry_identity_unresolved")
    if strategy_group_id == "LSR-001":
        blockers.append("side_specific_rewrite_not_closed")
        blockers.append("range_context_required")
    if strategy_group_id == "BRF-001":
        blockers.append("squeeze_classifier_required")
        blockers.append("requiredfacts_review_required")
    if strategy_group_id == "BTPC-001":
        blockers.append("stale_fact_source_classifier_blocker_unclosed")
    if _int(audit_row.get("would_enter_count")) <= 0:
        blockers.append("no_recent_would_enter")
    if not sampled_events and _int(audit_row.get("would_enter_count")) > 0:
        blockers.append("would_enter_sample_not_available")
    blockers.extend(
        [
            "owner_capital_scope_not_confirmed",
            "fresh_signal_absent",
            "action_time_finalgate_not_reached",
            "official_operation_layer_not_reached",
        ]
    )
    return _dedupe(blockers)


def _research_intake_blockers(research_row: dict[str, Any]) -> list[str]:
    blockers = _string_list(research_row.get("known_risks"))
    if research_row.get("paper_observation_ready") is not True:
        blockers.append("paper_observation_not_ready")
    if research_row.get("source_tiny_live_ready") is not True:
        blockers.append("source_tiny_live_ready_false")
    blockers.extend(
        [
            "owner_capital_scope_not_confirmed",
            "owner_trial_identity_not_confirmed",
            "fresh_signal_absent",
            "action_time_finalgate_not_reached",
            "official_operation_layer_not_reached",
        ]
    )
    return _dedupe(blockers)


def _trial_recommendation(
    *,
    strategy_group_id: str,
    opportunity_count: int,
    forward_positive: int,
    blockers: list[str],
) -> tuple[str, str]:
    blocker_set = set(blockers)
    if strategy_group_id == "MI-001" and opportunity_count >= 10 and forward_positive >= 10:
        return (
            "trial_prepare_after_owner_identity_and_capital_policy",
            "trial_prepare_candidate_pending_owner_policy",
        )
    if strategy_group_id == "LSR-001" and forward_positive > 0:
        return (
            "defer_until_rewrite_and_range_facts_closed",
            "trial_prepare_watchlist_after_revision",
        )
    if strategy_group_id == "BRF-001":
        return (
            "defer_until_squeeze_requiredfacts_forward_completed",
            "promote_review_before_trial_prepare",
        )
    if strategy_group_id == "CPM-RO-001" and opportunity_count > 0:
        return (
            "defer_until_identity_or_merge_review_closed",
            "identity_review_before_trial_prepare",
        )
    if strategy_group_id == "BTPC-001" or "stale_fact_source_classifier_blocker_unclosed" in blocker_set:
        return (
            "defer_until_fact_source_classifier_closed",
            "revise_before_trial_prepare",
        )
    return "not_a_trial_candidate_now", "not_selected"


def _research_trial_recommendation(
    *,
    strategy_group_id: str,
    research_row: dict[str, Any],
) -> tuple[str, str]:
    if (
        strategy_group_id == "BRF2-001"
        and research_row.get("main_control_intake_position")
        == "paper_observation_admission_candidate"
        and research_row.get("paper_observation_ready") is True
    ):
        return (
            "candidate_trade_prepare_pending_owner_policy",
            "short_candidate_trade_packet_pending_owner_policy",
        )
    if strategy_group_id == "RBR2-001":
        return (
            "role_only_short_candidate_trade_watchlist",
            "role_only_short_candidate_trade_watchlist",
        )
    return "research_intake_review_before_trial_prepare", "research_intake_review"


def _research_promotion_semantics(
    *,
    strategy_group_id: str,
    recommendation: str,
) -> dict[str, Any]:
    if (
        strategy_group_id == "BRF2-001"
        and recommendation == "candidate_trade_prepare_pending_owner_policy"
    ):
        return {
            "decision": "promote",
            "reason": BRF2_PROMOTION_REASON,
            "promotion_scope": BRF2_PROMOTION_SCOPE,
            "promotion_target": BRF2_PROMOTION_TARGET,
            "tiny_live_ready": False,
            "next_checkpoint": BRF2_NEXT_CHECKPOINT,
            "required_next_evidence": list(BRF2_REQUIRED_NEXT_EVIDENCE),
            "authority_boundary_summary": (
                "promotion_scope=intake_only; tiny_live_ready=false; "
                "actionable_now=false; real_order_authority=false"
            ),
        }
    return {
        "decision": "keep_observing",
        "reason": recommendation,
        "promotion_scope": "not_applicable",
        "promotion_target": "not_applicable",
        "tiny_live_ready": False,
        "next_checkpoint": f"{strategy_group_id}_research_intake_review",
        "required_next_evidence": [],
        "authority_boundary_summary": (
            "promotion_scope=not_applicable; tiny_live_ready=false; "
            "actionable_now=false; real_order_authority=false"
        ),
    }


def _ranking_score(
    *,
    strategy_group_id: str,
    opportunity_count: int,
    forward_positive: int,
    tradable_count: int,
    blockers: list[str],
) -> int:
    score = opportunity_count * 3 + forward_positive * 5 + tradable_count * 4
    if strategy_group_id == "MI-001":
        score += 40
    if strategy_group_id == "LSR-001":
        score += 20
    if strategy_group_id == "BRF-001":
        score += 10
    if strategy_group_id == "CPM-RO-001":
        score -= 10
    if strategy_group_id == "BTPC-001":
        score -= 40
    if any("stale" in blocker for blocker in blockers):
        score -= 50
    return score


def _research_ranking_score(
    *,
    strategy_group_id: str,
    opportunity_count: int,
    forward_positive: int,
    blockers: list[str],
) -> int:
    score = opportunity_count * 3 + forward_positive * 8
    if strategy_group_id == "BRF2-001":
        score += 500
    if strategy_group_id == "RBR2-001":
        score -= 100
    if any("high_5m_stop" in blocker for blocker in blockers):
        score -= 80
    return score


def _owner_policy_checkpoint(selected: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "owner_policy_required_later",
        "runtime_owner_intervention_required": False,
        "strategy_group_id": selected.get("strategy_group_id"),
        "decision_type": "capital_trial_identity_and_risk_boundary",
        "required_before_any_actual_trial": list(OWNER_POLICY_FIELDS),
        "does_not_block_engineering": True,
        "does_not_authorize_live_execution": True,
    }


def _engineering_continuation_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_group_id": row["strategy_group_id"],
        "candidate_status": row["candidate_status"],
        "next_engineering_bottleneck": row["trial_recommendation"],
        "trial_blockers": row["trial_blockers"],
        "blocked_until": "engineering_closure_or_owner_policy_checkpoint",
        "does_not_authorize_live_execution": True,
    }


def _bridge_reject_reasons(
    *,
    eligibility_rows: list[dict[str, Any]],
    ranking: list[dict[str, Any]],
    selected: dict[str, Any],
    trial_packet: dict[str, Any],
    safety: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if len(eligibility_rows) < len(TRIAL_REVIEW_ORDER):
        reasons.append("eligibility_rows_incomplete")
    if not ranking:
        reasons.append("ranking_missing")
    if selected.get("strategy_group_id") == "MPG-001" or not selected.get(
        "strategy_group_id"
    ):
        reasons.append("non_mpg_candidate_not_selected")
    if trial_packet.get("schema") != TRIAL_PACKET_SCHEMA:
        reasons.append("trial_packet_missing")
    if trial_packet.get("actionable_now") is not False:
        reasons.append("trial_packet_actionable_now_not_false")
    if trial_packet.get("live_permission_change") is not False:
        reasons.append("trial_packet_live_permission_change_not_false")
    if trial_packet.get("real_order_authority") is not False:
        reasons.append("trial_packet_real_order_authority_not_false")
    if trial_packet.get("decision") == "promote":
        if trial_packet.get("promotion_scope") != BRF2_PROMOTION_SCOPE:
            reasons.append("unscoped_promote_forbidden")
        boundary = trial_packet.get("authority_boundary")
        if not isinstance(boundary, dict):
            boundary = {}
        if boundary.get("promotion_scope") != BRF2_PROMOTION_SCOPE:
            reasons.append("authority_boundary_promotion_scope_missing")
        if boundary.get("unscoped_promote") is not False:
            reasons.append("authority_boundary_unscoped_promote_not_false")
        if trial_packet.get("tiny_live_ready") is not False:
            reasons.append("trial_packet_tiny_live_ready_not_false")
    for key, value in safety.items():
        if key in FORBIDDEN_EFFECTS and value is True:
            reasons.append(f"forbidden_effect:{key}")
    return _dedupe(reasons)


def _portfolio_rows_by_id(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = packet.get("portfolio_rows")
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("strategy_group_id")): row
        for row in rows
        if isinstance(row, dict) and row.get("strategy_group_id")
    }


def _trial_pool_rows_by_id(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    pool = packet.get("trial_candidate_pool")
    rows = pool.get("rows") if isinstance(pool, dict) else []
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("strategy_group_id")): row
        for row in rows
        if isinstance(row, dict) and row.get("strategy_group_id")
    }


def _audit_rows_by_id(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = packet.get("strategy_expectation_rows")
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("strategy_group_id")): row
        for row in rows
        if isinstance(row, dict) and row.get("strategy_group_id")
    }


def _research_intake_rows_by_id(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = packet.get("candidate_rows")
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("strategy_group_id")): row
        for row in rows
        if isinstance(row, dict) and row.get("strategy_group_id")
    }


def _would_enter_events_by_id(packet: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    events = packet.get("would_enter_events")
    by_id: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(events, list):
        return by_id
    for event in events:
        if not isinstance(event, dict):
            continue
        strategy_group_id = str(event.get("strategy_group_id") or "")
        if strategy_group_id:
            by_id.setdefault(strategy_group_id, []).append(event)
    return by_id


def _sampled_scope(events: list[dict[str, Any]]) -> tuple[list[str], list[str], str]:
    symbols = _sorted_counter_values(event.get("symbol") for event in events)
    sides = _sorted_counter_values(event.get("side") for event in events)
    candidates = _sorted_counter_values(event.get("candidate_id") for event in events)
    return symbols, sides, candidates[0] if candidates else ""


def _sorted_counter_values(values: Any) -> list[str]:
    counter = Counter(str(value) for value in values if value)
    return [
        value
        for value, _count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def _research_symbol_scope(row: dict[str, Any]) -> list[str]:
    shape = _as_dict(row.get("paper_observation_packet_shape"))
    symbol = shape.get("symbol")
    if symbol:
        return [str(symbol)]
    return ["owner_policy_required"]


def _max_tradable_after_cost(audit_row: dict[str, Any]) -> int:
    summary = audit_row.get("would_enter_forward_outcome_summary")
    if not isinstance(summary, dict):
        return 0
    by_window = summary.get("by_window")
    if not isinstance(by_window, dict):
        return 0
    return max(
        (
            _int(row.get("tradable_mfe_after_cost_count"))
            for row in by_window.values()
            if isinstance(row, dict)
        ),
        default=0,
    )


def _pending_forward_count(audit_row: dict[str, Any]) -> int:
    summary = audit_row.get("would_enter_forward_outcome_summary")
    if not isinstance(summary, dict):
        return 0
    by_window = summary.get("by_window")
    if not isinstance(by_window, dict):
        return 0
    return sum(
        _int(row.get("pending"))
        for row in by_window.values()
        if isinstance(row, dict)
    )


def _dominant_blocker(audit_row: dict[str, Any], blockers: list[str]) -> str:
    dominant = audit_row.get("dominant_blocker_classes")
    if isinstance(dominant, list) and dominant:
        first = dominant[0]
        if isinstance(first, dict) and first.get("key"):
            return str(first["key"])
    for blocker in blockers:
        if blocker:
            return blocker
    return "none"


def _identity_status(
    strategy_group_id: str,
    portfolio_row: dict[str, Any],
    blockers: list[str],
) -> str:
    if strategy_group_id in {"MI-001", "CPM-RO-001"}:
        return "identity_review_required"
    if "registry_identity_unresolved" in blockers:
        return "identity_review_required"
    if portfolio_row:
        return "registry_or_portfolio_identity_present"
    return "unknown"


def _validate_safety(name: str, packet: dict[str, Any]) -> None:
    safety = packet.get("safety_invariants")
    if not isinstance(safety, dict):
        safety = {}
    forbidden = [
        key
        for key in FORBIDDEN_EFFECTS
        if safety.get(key) is True or packet.get(key) is True
    ]
    if forbidden:
        raise ValueError(f"{name} has forbidden effects: {', '.join(forbidden)}")


def _safety_invariants() -> dict[str, bool]:
    return {
        "actionable_now": False,
        "real_order_authority": False,
        "registry_authority_changed": False,
        "tier_policy_changed": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "mpg_member_live_scope_expanded": False,
        "l4_real_order_scope_expanded": False,
        "shadow_candidate_created": False,
        "execution_intent_created": False,
        "creates_execution_intent": False,
        "submit_authorization_created": False,
        "final_gate_called": False,
        "calls_finalgate": False,
        "operation_layer_called": False,
        "calls_operation_layer": False,
        "order_created": False,
        "places_order": False,
        "exchange_write_called": False,
        "calls_exchange_write": False,
        "withdrawal_or_transfer_created": False,
        "preview_or_replay_treated_as_live_signal": False,
    }


def _interaction() -> dict[str, Any]:
    return {
        "level": "L0_local_capital_trial_readiness_bridge",
        "remote_interaction_count": 0,
        "mutates_remote_files": False,
        "approaches_real_order": False,
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "calls_exchange_write": False,
        "places_order": False,
    }


def _bridge_markdown(packet: dict[str, Any], output_json: Path, trial_json: Path) -> str:
    summary = packet["capital_trial_summary"]
    selected = packet["selected_non_mpg_trial_candidate"]
    lines = [
        "## StrategyGroup Capital Trial Readiness Bridge",
        "",
        f"- Status: {packet['status']}",
        f"- Generated: {packet['generated_at_utc']}",
        f"- Output JSON: {output_json}",
        f"- Trial Packet v0 JSON: {trial_json}",
        f"- Selected non-MPG candidate: {summary['selected_non_mpg_strategy_group_id']}",
        f"- Selected candidate status: {summary['selected_candidate_status']}",
        f"- Trial packet generated: {_yes_no(bool(summary['trial_packet_generated']))}",
        f"- Actionable now count: {summary['actionable_now_count']}",
        f"- Live permission change count: {summary['live_permission_change_count']}",
        f"- Real order authority count: {summary['real_order_authority_count']}",
        "",
        "## Selected Candidate",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| StrategyGroup | {selected.get('strategy_group_id')} |",
        f"| Execution Tier | {selected.get('execution_tier')} |",
        f"| Evidence Stage | {selected.get('evidence_stage')} |",
        f"| Recent opportunities | {selected.get('recent_opportunity_count')} |",
        f"| Forward positive | {selected.get('would_enter_forward_positive_count')} |",
        f"| Symbol scope | {_list_or_none(selected.get('symbol_scope') or [])} |",
        f"| Side scope | {_list_or_none(selected.get('side_scope') or [])} |",
        f"| Decision | {selected.get('decision')} |",
        f"| Reason | {selected.get('reason')} |",
        f"| Promotion scope | {selected.get('promotion_scope')} |",
        f"| Promotion target | {selected.get('promotion_target')} |",
        f"| Tiny live ready | {_yes_no(selected.get('tiny_live_ready') is True)} |",
        f"| Next checkpoint | {selected.get('next_checkpoint')} |",
        f"| Recommendation | {selected.get('trial_recommendation')} |",
        "",
        "## Ranking",
        "",
        "| Rank | StrategyGroup | Recommendation | Score | Blockers |",
        "| ---: | --- | --- | ---: | --- |",
    ]
    for index, row in enumerate(packet["non_mpg_trial_candidate_ranking"], start=1):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(index),
                    str(row["strategy_group_id"]),
                    str(row["trial_recommendation"]),
                    str(row["ranking_score"]),
                    _list_or_none(row["trial_blockers"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _trial_packet_markdown(packet: dict[str, Any], output_json: Path) -> str:
    boundary = packet["authority_boundary"]
    lines = [
        "## StrategyGroup Capital Trial Packet v0",
        "",
        f"- Packet ID: {packet['packet_id']}",
        f"- StrategyGroup: {packet['strategy_group_id']}",
        f"- Candidate status: {packet['candidate_status']}",
        f"- Decision: {packet['decision']}",
        f"- Reason: {packet['reason']}",
        f"- Promotion scope: {packet['promotion_scope']}",
        f"- Promotion target: {packet['promotion_target']}",
        f"- Tiny live ready: {_yes_no(packet['tiny_live_ready'] is True)}",
        f"- Next checkpoint: {packet['next_checkpoint']}",
        f"- Output JSON: {output_json}",
        f"- Actionable now: {_yes_no(bool(packet['actionable_now']))}",
        f"- Live permission change: {_yes_no(bool(packet['live_permission_change']))}",
        f"- Real order authority: {_yes_no(bool(packet['real_order_authority']))}",
        "",
        "## Boundary",
        "",
        "| Check | Value |",
        "| --- | --- |",
    ]
    for key in (
        "pre_registered_review_only",
        "registry_admission",
        "tier_policy_change",
        "live_profile_change",
        "creates_execution_intent",
        "calls_finalgate",
        "calls_operation_layer",
        "calls_exchange_write",
        "places_order",
    ):
        lines.append(f"| {key} | {_yes_no(bool(boundary.get(key)))} |")
    return "\n".join(lines) + "\n"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object JSON at {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write_text(
        path,
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _yes_no(value: bool) -> str:
    return "是" if value else "否"


def _list_or_none(values: list[Any]) -> str:
    if not values:
        return "none"
    return ", ".join(str(value) for value in values)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _dedupe(values: Any) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value)))


if __name__ == "__main__":
    raise SystemExit(main())
