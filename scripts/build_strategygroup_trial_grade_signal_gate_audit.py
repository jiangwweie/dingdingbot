#!/usr/bin/env python3
"""Build a trial-grade signal gate audit for MPG, BRF2, and SOR.

This artifact answers whether current fresh-signal gates are closer to
production-grade or bounded trial-grade. It is non-executing: replay, preview,
and proxy observations never become live RequiredFacts, FinalGate input,
Operation Layer evidence, exchange writes, or order authority.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.strategygroup_non_executing_projection import (  # noqa: E402
    non_executing_interaction,
    non_executing_safety_invariants,
)

DEFAULT_MPG_REPLAY_CORPUS_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/MPG-001/replay/mpg-001-replay-corpus.json"
)
DEFAULT_BRF_REPLAY_CORPUS_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/BRF-001/replay/brf-001-l1-observe-replay-corpus.json"
)
DEFAULT_SOR_HANDOFF_JSON = (
    REPO_ROOT / "docs/current/strategy-group-handoffs/SOR-001/handoff.json"
)
DEFAULT_SOR_REPLAY_CORPUS_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/SOR-001/replay/sor-001-session-trigger-replay-corpus.json"
)
DEFAULT_LIVE_PREVIEW_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-live-market-strategy-preview.json"
)
DEFAULT_LOCAL_PREVIEW_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-local-sqlite-strategy-preview.json"
)
DEFAULT_BRF2_POLICY_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-owner-trial-policy-scope.json"
)
DEFAULT_BRF2_CAPTURE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-runtime-signal-capture.json"
)
DEFAULT_THREE_STRATEGY_PORTFOLIO_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-three-strategy-live-trial-portfolio.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-trial-grade-signal-gate-audit.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-trial-grade-signal-gate-audit.md"
)

SCHEMA = "brc.strategygroup_trial_grade_signal_gate_audit.v1"
STRATEGY_GROUPS = ("MPG-001", "BRF2-001", "SOR-001")
RECENT_WINDOWS_DAYS = (7, 14, 30)

HARD_SAFETY_GATES = [
    "selected_strategygroup_scope",
    "allocated_subaccount_profile_boundary",
    "action_time_required_facts_fresh",
    "candidate_authorization_evidence",
    "action_time_finalgate",
    "official_operation_layer",
    "exchange_native_protection",
    "no_duplicate_submit",
    "no_conflicting_active_position_or_open_order",
    "exchange_rules_and_min_notional_ready",
    "no_secret_or_credential_mutation",
    "no_live_profile_or_order_sizing_expansion",
    "no_withdrawal_or_transfer",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mpg-replay-corpus-json", default=str(DEFAULT_MPG_REPLAY_CORPUS_JSON)
    )
    parser.add_argument(
        "--brf-replay-corpus-json", default=str(DEFAULT_BRF_REPLAY_CORPUS_JSON)
    )
    parser.add_argument("--sor-handoff-json", default=str(DEFAULT_SOR_HANDOFF_JSON))
    parser.add_argument(
        "--sor-replay-corpus-json", default=str(DEFAULT_SOR_REPLAY_CORPUS_JSON)
    )
    parser.add_argument("--live-preview-json", default=str(DEFAULT_LIVE_PREVIEW_JSON))
    parser.add_argument("--local-preview-json", default=str(DEFAULT_LOCAL_PREVIEW_JSON))
    parser.add_argument("--brf2-policy-json", default=str(DEFAULT_BRF2_POLICY_JSON))
    parser.add_argument("--brf2-capture-json", default=str(DEFAULT_BRF2_CAPTURE_JSON))
    parser.add_argument(
        "--three-strategy-portfolio-json",
        default=str(DEFAULT_THREE_STRATEGY_PORTFOLIO_JSON),
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    audit_artifact = build_trial_grade_signal_gate_audit(
        mpg_replay_corpus=_read_optional_json(Path(args.mpg_replay_corpus_json)),
        brf_replay_corpus=_read_optional_json(Path(args.brf_replay_corpus_json)),
        sor_handoff=_read_optional_json(Path(args.sor_handoff_json)),
        sor_replay_corpus=_read_optional_json(Path(args.sor_replay_corpus_json)),
        live_preview=_read_optional_json(Path(args.live_preview_json)),
        local_preview=_read_optional_json(Path(args.local_preview_json)),
        brf2_policy=_read_optional_json(Path(args.brf2_policy_json)),
        brf2_capture=_read_optional_json(Path(args.brf2_capture_json)),
        three_strategy_portfolio=_read_optional_json(
            Path(args.three_strategy_portfolio_json)
        ),
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_owner_progress)
    _write_json(output_json, audit_artifact)
    _write_text(output_md, _markdown(audit_artifact, output_json))
    print(
        json.dumps(
            {
                "status": audit_artifact["status"],
                "strategy_group_count": audit_artifact["summary"]["strategy_group_count"],
                "trial_grade_observation_count_30d": audit_artifact["summary"][
                    "trial_grade_observation_count_30d"
                ],
                "action_time_trial_submit_count_30d": audit_artifact["summary"][
                    "action_time_trial_submit_count_30d"
                ],
                "output_json": str(output_json),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if audit_artifact["status"] == "trial_grade_signal_gate_audit_ready" else 2


def build_trial_grade_signal_gate_audit(
    *,
    mpg_replay_corpus: dict[str, Any],
    brf_replay_corpus: dict[str, Any],
    sor_handoff: dict[str, Any],
    live_preview: dict[str, Any],
    sor_replay_corpus: dict[str, Any] | None = None,
    local_preview: dict[str, Any] | None = None,
    brf2_policy: dict[str, Any] | None = None,
    brf2_capture: dict[str, Any] | None = None,
    three_strategy_portfolio: dict[str, Any] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    local_preview = local_preview or {}
    sor_replay_corpus = sor_replay_corpus or {}
    brf2_policy = brf2_policy or {}
    brf2_capture = brf2_capture or {}
    three_strategy_portfolio = three_strategy_portfolio or {}
    preview_rows = _preview_rows(live_preview, source_name="live_preview")
    preview_rows += _preview_rows(local_preview, source_name="local_preview")
    as_of_ms = _as_of_ms(preview_rows)

    strategy_rows = {
        "MPG-001": _strategy_audit_row(
            strategy_group_id="MPG-001",
            preview_rows=preview_rows,
            as_of_ms=as_of_ms,
            replay_samples=_dict_rows(mpg_replay_corpus.get("replay_samples")),
            brf2_policy=brf2_policy,
            brf2_capture=brf2_capture,
            sor_handoff=sor_handoff,
            three_strategy_portfolio=three_strategy_portfolio,
        ),
        "BRF2-001": _strategy_audit_row(
            strategy_group_id="BRF2-001",
            preview_rows=preview_rows,
            as_of_ms=as_of_ms,
            replay_samples=_dict_rows(brf_replay_corpus.get("replay_samples")),
            brf2_policy=brf2_policy,
            brf2_capture=brf2_capture,
            sor_handoff=sor_handoff,
            three_strategy_portfolio=three_strategy_portfolio,
        ),
        "SOR-001": _strategy_audit_row(
            strategy_group_id="SOR-001",
            preview_rows=preview_rows,
            as_of_ms=as_of_ms,
            replay_samples=_dict_rows(sor_replay_corpus.get("replay_samples")),
            brf2_policy=brf2_policy,
            brf2_capture=brf2_capture,
            sor_handoff=sor_handoff,
            three_strategy_portfolio=three_strategy_portfolio,
        ),
    }
    summary = _summary(strategy_rows)
    return {
        "schema": SCHEMA,
        "scope": "strategygroup_trial_grade_signal_gate_audit_non_executing",
        "status": "trial_grade_signal_gate_audit_ready",
        "generated_at_utc": generated_at_utc
        or datetime.now(timezone.utc).isoformat(),
        "signal_grade_catalog": _signal_grade_catalog(),
        "audit_question": (
            "Are MPG-001, BRF2-001, and SOR-001 fresh signal gates "
            "production-grade strict or suitable for bounded 30U trial-grade?"
        ),
        "strategy_group_rows": strategy_rows,
        "summary": summary,
        "hard_safety_gate_list": HARD_SAFETY_GATES,
        "live_trial_policy_update": {
            "scope": "30U_bounded_trial_only",
            "does_not_change_production_grade_authority": True,
            "does_not_expand_live_profile": True,
            "does_not_change_order_sizing_defaults": True,
            "trial_grade_signal_may_enter_bounded_trial": True,
            "production_grade_signal_required_for_scale_up": True,
            "action_time_chain_still_required": [
                "fresh_signal",
                "live_required_facts",
                "candidate_authorization_evidence",
                "action_time_finalgate",
                "official_operation_layer",
                "protection_account_exchange_facts",
            ],
        },
        "checks": {
            "signal_grade_catalog_present": True,
            "all_selected_strategy_groups_covered": set(strategy_rows)
            == set(STRATEGY_GROUPS),
            "hard_safety_gates_not_relaxed": True,
            "risk_expressed_as_envelope": all(
                bool(row["risk_envelope"]) for row in strategy_rows.values()
            ),
            "recent_counts_are_source_qualified": True,
            "replay_or_proxy_not_action_time_authority": True,
        },
        "interaction": _interaction(),
        "safety_invariants": _safety_invariants(),
    }


def _strategy_audit_row(
    *,
    strategy_group_id: str,
    preview_rows: list[dict[str, Any]],
    as_of_ms: int,
    replay_samples: list[dict[str, Any]],
    brf2_policy: dict[str, Any],
    brf2_capture: dict[str, Any],
    sor_handoff: dict[str, Any],
    three_strategy_portfolio: dict[str, Any],
) -> dict[str, Any]:
    matching_rows = [
        row for row in preview_rows if _row_matches_strategy(row, strategy_group_id)
    ]
    production_profile, trial_profile = _gate_profiles(
        strategy_group_id=strategy_group_id,
        brf2_capture=brf2_capture,
        sor_handoff=sor_handoff,
    )
    risk_envelope = _risk_envelope(
        strategy_group_id=strategy_group_id,
        brf2_policy=brf2_policy,
        sor_handoff=sor_handoff,
        three_strategy_portfolio=three_strategy_portfolio,
    )
    verified_counts = _verified_recent_window_counts(
        strategy_group_id=strategy_group_id,
        rows=matching_rows,
        as_of_ms=as_of_ms,
    )
    replay_projection = _fixture_replay_projection(
        strategy_group_id=strategy_group_id,
        replay_samples=replay_samples,
        risk_envelope=risk_envelope,
    )
    false_positive_pack = _false_positive_review_pack(
        strategy_group_id=strategy_group_id,
        replay_samples=replay_samples,
        risk_envelope=risk_envelope,
    )
    trial_gate_diff = _trial_gate_diff(strategy_group_id, brf2_capture=brf2_capture)
    current_gate_assessment = _current_gate_assessment(
        strategy_group_id=strategy_group_id,
        trial_gate_diff=trial_gate_diff,
        verified_counts=verified_counts,
        replay_projection=replay_projection,
    )
    return {
        "strategy_group_id": strategy_group_id,
        "signal_grade_current_assessment": current_gate_assessment,
        "production_grade_gate_profile": production_profile,
        "trial_grade_gate_profile": trial_profile,
        "trial_grade_trigger_diff": trial_gate_diff,
        "hard_safety_gate_list": HARD_SAFETY_GATES,
        "risk_envelope": risk_envelope,
        "verified_recent_window_counts": verified_counts,
        "fixture_replay_projection": replay_projection,
        "false_positive_review_pack": false_positive_pack,
        "tomorrow_same_structure_assessment": _tomorrow_assessment(
            strategy_group_id=strategy_group_id,
            verified_counts=verified_counts,
            replay_projection=replay_projection,
        ),
        "authority_boundary": {
            "trial_grade_signal_can_prepare_30u_trial": True,
            "trial_grade_signal_can_bypass_hard_safety_gates": False,
            "replay_or_proxy_counts_are_live_signals": False,
        },
    }


def _signal_grade_catalog() -> dict[str, dict[str, Any]]:
    return {
        "observe_only_signal": {
            "may_place_order": False,
            "use": "record_replay_repair_classifier",
        },
        "trial_grade_signal": {
            "may_place_order": "only_inside_scoped_small_capital_trial_after_action_time_gates",
            "use": "enter_30u_bounded_live_trial",
        },
        "production_grade_signal": {
            "may_place_order": "yes_after_higher_tier_or_production_policy_and_action_time_gates",
            "use": "future_scale_up_or_regularized_runtime_operation",
        },
        "invalid_signal": {
            "may_place_order": False,
            "use": "attribution_replay_rule_repair",
        },
    }


def _gate_profiles(
    *,
    strategy_group_id: str,
    brf2_capture: dict[str, Any],
    sor_handoff: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if strategy_group_id == "BRF2-001":
        preview = _as_dict(brf2_capture.get("signal_detector_preview"))
        missing = _string_list(preview.get("missing_required_fact_keys"))
        return (
            {
                "grade": "production_grade_signal",
                "required_conditions": [
                    "BRF2 native runtime watcher fact input",
                    "closed_1h_ohlcv",
                    "closed_5m_ohlcv",
                    "rally_context",
                    "rally_failure_trigger_state",
                    "short_squeeze_risk_state_clear_or_bounded",
                    "strong_reclaim_disable_state_clear",
                    "liquidity_and_spread_acceptable",
                    "action_time_live_required_facts",
                ],
                "current_missing_or_strict_conditions": missing,
            },
            {
                "grade": "trial_grade_signal",
                "required_conditions": [
                    "closed_1h_ohlcv",
                    "closed_5m_ohlcv_or_readonly_tick_proxy_for_observation",
                    "rally_failure_or_bear_rally_would_enter_context",
                    "short_squeeze_risk_not_red",
                    "strong_reclaim_not_active",
                    "spread_liquidity_not_unknown",
                    "30U_policy_envelope",
                    "action_time_live_required_facts_before_submit",
                ],
                "warnings_allowed": [
                    "path_risk_known",
                    "proxy_observation_source",
                    "weak_reclaim_context_uncertainty",
                    "coarse_liquidity_proxy",
                ],
            },
        )
    if strategy_group_id == "SOR-001":
        rule = _as_dict(sor_handoff.get("signal_ready_rule"))
        return (
            {
                "grade": "production_grade_signal",
                "required_conditions": [
                    "closed_open_range_bars",
                    "closed_trigger_bar",
                    "tradfi_session_mapping_state",
                    "post_open_decay_disable_clear",
                    "session_gap_fill_review",
                    "action_time_live_required_facts",
                ],
                "confidence_min": str(rule.get("confidence_min") or "0.58"),
            },
            {
                "grade": "trial_grade_signal",
                "required_conditions": [
                    "closed_open_range_bars",
                    "closed_trigger_bar",
                    "session_window_matched",
                    "post_open_decay_not_active",
                    "stop_protection_required",
                    "30U_policy_envelope",
                    "action_time_live_required_facts_before_submit",
                ],
                "warnings_allowed": [
                    "session_false_breakout_risk",
                    "mark_funding_session_review_uncertainty",
                ],
            },
        )
    return (
        {
            "grade": "production_grade_signal",
            "required_conditions": [
                "selected_L4_strategygroup_scope",
                "production_fresh_signal",
                "full_member_persistence_and_exhaustion_checks",
                "action_time_live_required_facts",
            ],
        },
        {
            "grade": "trial_grade_signal",
            "required_conditions": [
                "selected_strategygroup_scope",
                "fresh_momentum_signal",
                "required_facts_ready",
                "protection_required",
                "action_time_live_required_facts_before_submit",
            ],
            "warnings_allowed": [
                "false_breakout_risk",
                "fast_reversal_risk",
                "member_concentration_warning",
            ],
        },
    )


def _trial_gate_diff(strategy_group_id: str, brf2_capture: dict[str, Any]) -> list[dict[str, Any]]:
    if strategy_group_id == "BRF2-001":
        preview = _as_dict(brf2_capture.get("signal_detector_preview"))
        missing = set(_string_list(preview.get("missing_required_fact_keys")))
        return [
            _diff(
                "rally_context",
                "required_exact_bear_or_weak_reclaim_context",
                "warning_if_brf_reference_would_enter_context_exists",
                "downgrade_to_warning_for_trial",
                currently_blocks="rally_context" in missing,
            ),
            _diff(
                "rally_failure_trigger_state",
                "required_confirmed_native_runtime_failure_trigger",
                "accept_bear_rally_failure_would_enter_proxy_for_review_then_rebuild_action_time_facts",
                "downgrade_to_warning_for_trial",
                currently_blocks="rally_failure_trigger_state" in missing,
            ),
            _diff(
                "short_squeeze_risk_state",
                "clear_or_bounded_required",
                "red_or_unbounded_remains_hard_disable",
                "keep_hard_disable",
            ),
            _diff(
                "liquidity_downshift_state",
                "strict_liquidity_confirmation_required",
                "coarse_proxy_allowed_as_warning_only",
                "downgrade_to_warning_for_trial",
            ),
            _diff(
                "action_time_live_required_facts",
                "required",
                "required",
                "keep_hard_gate",
            ),
        ]
    if strategy_group_id == "SOR-001":
        return [
            _diff(
                "session_range_confidence",
                "production_confidence_and_session_quality_required",
                "lower_confidence_can_be_warning_inside_30u_trial",
                "downgrade_to_warning_for_trial",
            ),
            _diff(
                "closed_open_range_and_trigger_bar",
                "required",
                "required",
                "keep_hard_gate",
            ),
            _diff(
                "post_open_decay_disable_state",
                "clear_required",
                "clear_required",
                "keep_hard_disable",
            ),
            _diff(
                "sor_replay_source",
                "required_for_scale_up",
                "missing_source_blocks_confident_trial_grade_calibration",
                "needs_replay_source",
            ),
        ]
    return [
        _diff(
            "member_persistence_depth",
            "full_production_confirmation_required",
            "may_be_warning_if_core_fresh_signal_and_required_facts_pass",
            "downgrade_to_warning_for_trial",
        ),
        _diff(
            "false_breakout_risk",
            "must_be_low_for_production",
            "known_risk_enters_loss_envelope",
            "downgrade_to_warning_for_trial",
        ),
        _diff(
            "action_time_live_required_facts",
            "required",
            "required",
            "keep_hard_gate",
        ),
    ]


def _diff(
    condition: str,
    production_grade_treatment: str,
    trial_grade_treatment: str,
    recommendation: str,
    *,
    currently_blocks: bool = False,
) -> dict[str, Any]:
    return {
        "condition": condition,
        "production_grade_treatment": production_grade_treatment,
        "trial_grade_treatment": trial_grade_treatment,
        "recommendation": recommendation,
        "currently_blocks_production_grade": currently_blocks,
    }


def _risk_envelope(
    *,
    strategy_group_id: str,
    brf2_policy: dict[str, Any],
    sor_handoff: dict[str, Any],
    three_strategy_portfolio: dict[str, Any],
) -> dict[str, Any]:
    if strategy_group_id == "BRF2-001":
        policy = _as_dict(brf2_policy.get("policy"))
        return {
            "capital_scope": policy.get("capital_scope")
            or {"amount": "30", "currency": "USDT", "type": "trial"},
            "loss_unit": policy.get("loss_unit")
            or {"amount": "10", "currency": "USDT", "basis": "30U / 3 attempts"},
            "attempt_cap": _int(policy.get("attempt_cap"), default=3),
            "max_consecutive_losses": _int(
                policy.get("max_consecutive_losses"), default=2
            ),
            "pause_conditions": policy.get("pause_conditions")
            or [
                "two_consecutive_losses",
                "missing_required_path_or_liquidation_buffer_evidence",
            ],
            "path_risk_treatment": "known_path_risk_enters_envelope_not_trade_denial",
            "stop_or_protection_required": True,
        }
    if strategy_group_id == "SOR-001":
        risk = _as_dict(sor_handoff.get("risk_defaults"))
        return {
            "capital_scope": {
                "amount": "30",
                "currency": "USDT",
                "type": "proposed_trial_only_not_policy_authority",
            },
            "loss_unit": {"amount": "10", "currency": "USDT", "basis": "3 attempts"},
            "attempt_cap": 3,
            "max_consecutive_losses": 2,
            "pause_conditions": [
                "session_false_breakout_review_required",
                "post_open_decay_detected",
                "missing_stop_or_exit_plan",
            ],
            "handoff_risk_defaults": risk,
            "path_risk_treatment": "session_gap_and_false_breakout_risk_enter_envelope",
            "stop_or_protection_required": True,
        }
    seat = _as_dict(
        _as_dict(three_strategy_portfolio.get("seat_readiness")).get("MPG-001")
    )
    return {
        "capital_scope": {
            "amount": "30",
            "currency": "USDT",
            "type": "trial_grade_audit_envelope_not_sizing_default",
        },
        "loss_unit": {"amount": "10", "currency": "USDT", "basis": "3 attempts"},
        "attempt_cap": 3,
        "max_consecutive_losses": 2,
        "pause_conditions": [
            "false_breakout_or_fast_reversal_review_required",
            "missing_protection",
            "active_position_or_open_order_conflict",
        ],
        "current_stage": seat.get("stage") or "armed_observation",
        "path_risk_treatment": "false_breakout_and_fast_reversal_enter_envelope",
        "stop_or_protection_required": True,
    }


def _verified_recent_window_counts(
    *,
    strategy_group_id: str,
    rows: list[dict[str, Any]],
    as_of_ms: int,
) -> dict[str, Any]:
    windows: dict[str, Any] = {}
    for days in RECENT_WINDOWS_DAYS:
        cutoff = as_of_ms - days * 24 * 60 * 60 * 1000
        in_window = [
            row for row in rows if _timestamp_ms(row) and _timestamp_ms(row) >= cutoff
        ]
        trial_obs = [row for row in in_window if _is_trial_grade_observation(row, strategy_group_id)]
        production = [
            row for row in in_window if _is_production_grade_observation(row, strategy_group_id)
        ]
        invalid = [row for row in in_window if str(row.get("signal_type")) == "invalid"]
        windows[str(days)] = {
            "source": "timestamped_preview_rows",
            "as_of_utc": _ms_to_iso(as_of_ms),
            "row_count": len(in_window),
            "trial_grade_observation_count": len(trial_obs),
            "production_grade_observation_count": len(production),
            "action_time_trial_submit_count": 0,
            "invalid_signal_count": len(invalid),
            "evidence_level": (
                "timestamped_proxy_or_preview_observation_not_action_time_submit"
                if in_window
                else "no_timestamped_rows_for_strategy_in_window"
            ),
            "matched_signal_ids": [
                str(row.get("candidate_id") or row.get("record_id") or "")
                for row in trial_obs
            ],
        }
    return {
        "windows_days": windows,
        "counts_do_not_authorize_submit": True,
        "verified_recent_counts_are_action_time_counts": False,
    }


def _fixture_replay_projection(
    *,
    strategy_group_id: str,
    replay_samples: list[dict[str, Any]],
    risk_envelope: dict[str, Any],
) -> dict[str, Any]:
    trial_cases = [
        sample
        for sample in replay_samples
        if _sample_would_trigger_trial(sample, strategy_group_id=strategy_group_id)
    ]
    production_cases = [
        sample for sample in replay_samples if _sample_would_trigger_production(sample)
    ]
    max_loss = _max_loss_estimate(risk_envelope)
    return {
        "source": (
            "timestampless_fixture_replay_projection"
            if replay_samples
            else "missing_strategy_specific_replay_source"
        ),
        "recent_7_14_30_day_counts_available": False,
        "sample_count": len(replay_samples),
        "trial_grade_trigger_case_count": len(trial_cases),
        "production_grade_trigger_case_count": len(production_cases),
        "would_trigger_cases": [
            str(sample.get("fixture_case") or sample.get("event_id") or "")
            for sample in trial_cases
        ],
        "max_loss_estimate_usdt": str(max_loss),
        "projection_boundary": (
            "fixture cases show gate behavior only; they are not recent-market counts "
            "and cannot satisfy live RequiredFacts."
        ),
    }


def _false_positive_review_pack(
    *,
    strategy_group_id: str,
    replay_samples: list[dict[str, Any]],
    risk_envelope: dict[str, Any],
) -> list[dict[str, Any]]:
    risky = [
        sample
        for sample in replay_samples
        if _sample_is_false_positive_or_loss_review(sample)
    ]
    if strategy_group_id == "SOR-001" and not risky:
        return [
            {
                "case": "sor_replay_source_missing",
                "potential_loss_reason": "session_false_breakout_or_gap_fill_not_calibrated",
                "estimated_loss_usdt": str(_loss_unit(risk_envelope)),
                "mitigation": "build_sor_session_trigger_replay_source_before_scale_up",
            }
        ]
    return [
        {
            "case": str(sample.get("fixture_case") or sample.get("event_id") or ""),
            "potential_loss_reason": _potential_loss_reason(sample),
            "estimated_loss_usdt": str(_loss_unit(risk_envelope)),
            "mitigation": _mitigation(strategy_group_id, sample),
        }
        for sample in risky
    ]


def _current_gate_assessment(
    *,
    strategy_group_id: str,
    trial_gate_diff: list[dict[str, Any]],
    verified_counts: dict[str, Any],
    replay_projection: dict[str, Any],
) -> dict[str, Any]:
    count_30d = _int(
        _as_dict(_as_dict(verified_counts.get("windows_days")).get("30")).get(
            "trial_grade_observation_count"
        )
    )
    if strategy_group_id == "BRF2-001":
        return {
            "current_gate_looks_like": "production_grade_strict_with_trial_grade_proxy_evidence",
            "trial_grade_audit_needed": True,
            "current_answer": (
                "BRF2 has bounded policy and mapping, but native fresh rule remains strict; "
                "recent BRF proxy observations can support trial-grade review only."
            ),
            "trial_grade_observation_count_30d": count_30d,
        }
    if strategy_group_id == "SOR-001":
        replay_ready = replay_projection["trial_grade_trigger_case_count"] > 0
        return {
            "current_gate_looks_like": (
                "conditional_armed_observation_with_trial_grade_replay_calibration"
                if replay_ready
                else "conditional_armed_observation_without_replay_calibration"
            ),
            "trial_grade_audit_needed": True,
            "current_answer": (
                "SOR has session trigger replay shape for trial-grade calibration, but no recent timestamped trigger."
                if replay_ready
                else "SOR needs session trigger replay/source coverage before confident trial-grade calibration."
            ),
            "trial_grade_observation_count_30d": count_30d,
        }
    return {
        "current_gate_looks_like": "l4_production_path_with_trial_grade_warning_candidates",
        "trial_grade_audit_needed": True,
        "current_answer": "MPG can downgrade strategy-quality risks to warnings only when hard runtime gates still pass.",
        "trial_grade_observation_count_30d": count_30d,
        "fixture_trial_trigger_case_count": replay_projection[
            "trial_grade_trigger_case_count"
        ],
    }


def _tomorrow_assessment(
    *,
    strategy_group_id: str,
    verified_counts: dict[str, Any],
    replay_projection: dict[str, Any],
) -> dict[str, Any]:
    count_30d = _int(
        _as_dict(_as_dict(verified_counts.get("windows_days")).get("30")).get(
            "trial_grade_observation_count"
        )
    )
    if strategy_group_id == "BRF2-001":
        will_enter = count_30d > 0
        return {
            "if_same_structure_appears_tomorrow": (
                "enter_non_executing_trial_candidate_review_then_action_time_gate"
                if will_enter
                else "continue_armed_observation"
            ),
            "would_enter_30u_trial": will_enter,
            "reason": "BRF2 can use BRF short would-enter proxy for trial-grade review, but submit still needs live action-time facts.",
        }
    if strategy_group_id == "SOR-001":
        replay_ready = replay_projection["trial_grade_trigger_case_count"] > 0
        return {
            "if_same_structure_appears_tomorrow": (
                "enter_non_executing_session_trial_review_then_action_time_gate"
                if replay_ready
                else "not_proven_until_sor_session_replay_source_exists"
            ),
            "would_enter_30u_trial": replay_ready,
            "reason": (
                "SOR replay source now defines trial-grade session trigger behavior; submit still needs live action-time facts."
                if replay_ready
                else "SOR lacks strategy-specific recent replay/source calibration for trial-grade trigger counts."
            ),
        }
    return {
        "if_same_structure_appears_tomorrow": "enter_trial_only_if_selected_scope_and_action_time_hard_gates_pass",
        "would_enter_30u_trial": replay_projection["trial_grade_trigger_case_count"] > 0,
        "reason": "MPG trial-grade can treat false-breakout/fast-reversal risk as envelope risk, not as authority bypass.",
    }


def _summary(strategy_rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    trial_30d = sum(
        _int(
            _as_dict(
                _as_dict(row["verified_recent_window_counts"]["windows_days"]).get("30")
            ).get("trial_grade_observation_count")
        )
        for row in strategy_rows.values()
    )
    action_time_30d = sum(
        _int(
            _as_dict(
                _as_dict(row["verified_recent_window_counts"]["windows_days"]).get("30")
            ).get("action_time_trial_submit_count")
        )
        for row in strategy_rows.values()
    )
    return {
        "strategy_group_count": len(strategy_rows),
        "trial_grade_observation_count_30d": trial_30d,
        "action_time_trial_submit_count_30d": action_time_30d,
        "production_grade_observation_count_30d": sum(
            _int(
                _as_dict(
                    _as_dict(row["verified_recent_window_counts"]["windows_days"]).get(
                        "30"
                    )
                ).get("production_grade_observation_count")
            )
            for row in strategy_rows.values()
        ),
        "hard_safety_gates_relaxed": False,
        "risk_treatment": "strategy_risk_to_envelope_not_generic_blocker",
        "next_engineering_bottleneck": (
            "convert trial-grade audit into 30U trial admission policy wording "
            "and runtime trigger calibration without changing production authority."
        ),
    }


def _preview_rows(source_artifact: dict[str, Any], *, source_name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("would_enter_signals", "no_action_signals", "invalid_signals"):
        for row in _dict_rows(source_artifact.get(key)):
            item = dict(row)
            item["_source_name"] = source_name
            rows.append(item)
    preview = _as_dict(source_artifact.get("preview"))
    for key in ("current_signals", "signal_history", "candidates"):
        for row in _dict_rows(preview.get(key)):
            item = dict(row)
            item["_source_name"] = source_name
            rows.append(item)
    return _dedupe_rows(rows)


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, int]] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        key = (
            str(row.get("candidate_id") or row.get("record_id") or ""),
            str(row.get("strategy_group_id") or ""),
            str(row.get("symbol") or ""),
            _timestamp_ms(row),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _row_matches_strategy(row: dict[str, Any], strategy_group_id: str) -> bool:
    row_group = str(row.get("strategy_group_id") or "")
    if row_group == strategy_group_id:
        return True
    if strategy_group_id == "BRF2-001":
        return row_group == "BRF-001" and str(row.get("side") or "").lower() == "short"
    return False


def _is_trial_grade_observation(row: dict[str, Any], strategy_group_id: str) -> bool:
    signal_type = str(row.get("signal_type") or "")
    if signal_type in {"invalid", "no_action", ""}:
        return False
    if strategy_group_id == "BRF2-001":
        reason_codes = {str(item) for item in row.get("reason_codes") or []}
        return str(row.get("side") or "").lower() == "short" and bool(
            reason_codes
            & {
                "brf_bear_rally_extended",
                "brf_rally_high_rejected",
                "brf_short_squeeze_risk_reviewed",
            }
        )
    return str(row.get("strategy_group_id") or "") == strategy_group_id


def _is_production_grade_observation(
    row: dict[str, Any], strategy_group_id: str
) -> bool:
    return (
        str(row.get("strategy_group_id") or "") == strategy_group_id
        and str(row.get("signal_type") or "") in {"ready", "fresh_signal", "current"}
        and row.get("not_execution_intent") is not True
    )


def _sample_would_trigger_trial(
    sample: dict[str, Any], *, strategy_group_id: str
) -> bool:
    status = str(sample.get("signal_status") or "")
    blocker = str(sample.get("blocker_class") or "")
    fixture = str(sample.get("fixture_case") or "")
    if sample.get("required_facts_ready") is not True:
        return False
    if status in {"no_signal", "stale_signal"}:
        return False
    if blocker in {"missing_fact", "hard_safety_stop", "active_position_resolution"}:
        return False
    if strategy_group_id == "BRF2-001" and "squeeze" in fixture:
        return False
    if strategy_group_id == "SOR-001" and (
        "false" in fixture or "decay" in fixture
    ):
        return False
    return "would_enter" in status or "fresh_signal" in status


def _sample_would_trigger_production(sample: dict[str, Any]) -> bool:
    return (
        sample.get("required_facts_ready") is True
        and str(sample.get("blocker_class") or "") == "none"
        and "fresh_signal" in str(sample.get("signal_status") or "")
    )


def _sample_is_false_positive_or_loss_review(sample: dict[str, Any]) -> bool:
    fixture = str(sample.get("fixture_case") or "")
    blocker = str(sample.get("blocker_class") or "")
    recommendation = str(sample.get("review_recommendation") or "")
    return (
        "false" in fixture
        or "reversal" in fixture
        or "squeeze" in fixture
        or "decay" in fixture
        or blocker == "review_only_warning"
        or recommendation == "revise"
    )


def _potential_loss_reason(sample: dict[str, Any]) -> str:
    fixture = str(sample.get("fixture_case") or "")
    if "squeeze" in fixture:
        return "short_squeeze_or_strong_reclaim_before_failure_confirms"
    if "false" in fixture:
        return "false_breakout_or_false_rejection"
    if "reversal" in fixture:
        return "fast_reversal_after_entry"
    if "missing" in fixture:
        return "missing_context_can_turn_signal_into_noise"
    return "strategy_quality_warning_can_hit_loss_unit"


def _mitigation(strategy_group_id: str, sample: dict[str, Any]) -> str:
    if strategy_group_id == "BRF2-001":
        return "keep_squeeze_and_reclaim_disable_hard_then_pause_after_loss_unit"
    if strategy_group_id == "SOR-001":
        return "require_closed_session_range_trigger_and_time_stop"
    return "keep_protection_and_review_false_breakout_after_each_attempt"


def _max_loss_estimate(risk_envelope: dict[str, Any]) -> Decimal:
    return _loss_unit(risk_envelope) * Decimal(_int(risk_envelope.get("attempt_cap"), default=1))


def _loss_unit(risk_envelope: dict[str, Any]) -> Decimal:
    loss_unit = _as_dict(risk_envelope.get("loss_unit"))
    try:
        return Decimal(str(loss_unit.get("amount") or "10"))
    except Exception:
        return Decimal("10")


def _as_of_ms(rows: list[dict[str, Any]]) -> int:
    timestamps = [_timestamp_ms(row) for row in rows if _timestamp_ms(row) > 0]
    if timestamps:
        return max(timestamps)
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _timestamp_ms(row: dict[str, Any]) -> int:
    return _int(row.get("market_bar_timestamp_ms") or row.get("evaluated_at_ms"))


def _ms_to_iso(value: int) -> str:
    if value <= 0:
        return ""
    return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat()


def _interaction() -> dict[str, Any]:
    return non_executing_interaction("L0_local_trial_grade_signal_gate_audit")


def _safety_invariants() -> dict[str, bool]:
    return non_executing_safety_invariants(
        extra_false_keys=(
            "replay_or_proxy_signal_treated_as_live_signal",
            "action_time_required_facts_satisfied_by_proxy",
            "authorization_evidence_created",
        ),
        include_authority_mirrors=False,
    )


def _markdown(audit_artifact: dict[str, Any], output_json: Path) -> str:
    summary = audit_artifact["summary"]
    lines = [
        "## Trial-Grade Signal Gate Audit",
        "",
        f"- Status: `{audit_artifact['status']}`",
        f"- Generated: `{audit_artifact['generated_at_utc']}`",
        f"- Output JSON: `{output_json}`",
        "- Scope: `30U bounded trial only`",
        "",
        "## Summary",
        "",
        f"- StrategyGroups: `{summary['strategy_group_count']}`",
        f"- 30d trial-grade observations: `{summary['trial_grade_observation_count_30d']}`",
        f"- 30d action-time trial submits: `{summary['action_time_trial_submit_count_30d']}`",
        "- Hard safety gates relaxed: `否`",
        "",
        "## Strategy Rows",
        "",
        "| StrategyGroup | Current gate | 30d trial observations | Fixture trial cases | Max loss estimate | Tomorrow assessment |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in audit_artifact["strategy_group_rows"].values():
        counts_30d = _as_dict(row["verified_recent_window_counts"]["windows_days"]["30"])
        tomorrow = _as_dict(row["tomorrow_same_structure_assessment"])
        lines.append(
            "| "
            f"`{row['strategy_group_id']}` | "
            f"`{row['signal_grade_current_assessment']['current_gate_looks_like']}` | "
            f"{counts_30d.get('trial_grade_observation_count', 0)} | "
            f"{row['fixture_replay_projection']['trial_grade_trigger_case_count']} | "
            f"{row['fixture_replay_projection']['max_loss_estimate_usdt']} | "
            f"`{tomorrow.get('if_same_structure_appears_tomorrow')}` |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- Trial-grade risk is expressed as envelope: attempt cap, loss unit, pause rule, protection, and review.",
            "- Replay, preview, and proxy rows do not satisfy action-time RequiredFacts.",
            "- This artifact does not call FinalGate, Operation Layer, exchange write, or order creation.",
        ]
    )
    return "\n".join(lines) + "\n"


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


if __name__ == "__main__":
    raise SystemExit(main())
