from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_strategygroup_capital_trial_envelope_projection.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_capital_trial_envelope_projection",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _safe() -> dict:
    return {
        "actionable_now": False,
        "real_order_authority": False,
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "calls_exchange_write": False,
        "places_order": False,
        "registry_authority_changed": False,
        "tier_policy_changed": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "preview_or_replay_treated_as_live_signal": False,
    }


def _audit_row(group: str, would_enter: int, positive: int, tradable: int) -> dict:
    return {
        "strategy_group_id": group,
        "would_enter_count": would_enter,
        "would_enter_forward_positive_count": positive,
        "dominant_blocker_classes": [{"key": "observe_only_would_enter", "count": would_enter}],
        "would_enter_forward_outcome_summary": {
            "event_count": would_enter,
            "by_window": {
                "12h": {
                    "completed": would_enter,
                    "pending": 0,
                    "tradable_mfe_after_cost_count": tradable,
                }
            },
        },
    }


def _portfolio() -> dict:
    rows = [
        ("MPG-001", "L4", "trial_waiting", 0, 0, True),
        ("BRF-001", "L1", "promote_review", 1, 0, False),
        ("LSR-001", "L1", "revise", 2, 2, False),
        ("MI-001", "unknown", "identity_review", 23, 22, False),
        ("CPM-RO-001", "unknown", "identity_review", 18, 13, False),
        ("BTPC-001", "L2", "revise", 0, 0, False),
    ]
    portfolio_rows = [
        {
            "strategy_group_id": group,
            "execution_tier": tier,
            "evidence_stage": stage,
            "recent_opportunity_count": would_enter,
            "would_enter_forward_positive_count": positive,
            "evidence_gaps": [],
            "trial_eligible": trial_eligible,
            "actionable_now": False,
            "live_permission_change": False,
            "does_not_authorize_live_execution": True,
        }
        for group, tier, stage, would_enter, positive, trial_eligible in rows
    ]
    return {
        "status": "portfolio_board_ready",
        "portfolio_summary": {"portfolio_row_count": 10},
        "portfolio_rows": portfolio_rows,
        "trial_candidate_pool": {
            "candidate_count": 5,
            "eligible_now_count": 1,
            "actionable_now_count": 0,
            "live_permission_change_count": 0,
            "rows": [
                {
                    "strategy_group_id": group,
                    "pool_stage": pool_stage,
                    "trial_blockers": [],
                    "actionable_now": False,
                    "live_permission_change": False,
                }
                for group, pool_stage in [
                    ("MPG-001", "selected_live_lane_waiting_for_market"),
                    ("BRF-001", "promote_review_candidate"),
                    ("LSR-001", "rewrite_candidate_after_revision"),
                    ("MI-001", "identity_candidate_review"),
                    ("CPM-RO-001", "identity_candidate_review"),
                ]
            ],
        },
        "interaction": {"remote_interaction_count": 0},
        "safety_invariants": _safe(),
    }


def _capture_audit() -> dict:
    return {
        "status": "strategy_capture_gap_audit_ready",
        "strategy_expectation_rows": [
            _audit_row("BRF-001", 1, 0, 0),
            _audit_row("LSR-001", 2, 2, 2),
            _audit_row("MI-001", 23, 22, 22),
            _audit_row("CPM-RO-001", 18, 13, 13),
            _audit_row("BTPC-001", 0, 0, 0),
        ],
        "would_enter_events": [
            {
                "strategy_group_id": "MI-001",
                "candidate_id": "MI-001-SOL-LONG",
                "symbol": "SOL/USDT:USDT",
                "side": "long",
                "signal_type": "would_enter",
                "no_order_permission": True,
            },
            {
                "strategy_group_id": "LSR-001",
                "candidate_id": "LSR-001-XRP-LONG",
                "symbol": "XRP/USDT:USDT",
                "side": "short",
                "signal_type": "would_enter",
                "no_order_permission": True,
            },
        ],
        "safety_invariants": _safe(),
    }


def _research_intake_review() -> dict:
    return {
        "status": "research_intake_review_ready",
        "candidate_rows": [
            {
                "strategy_group_id": "BRF2-001",
                "strategy_direction": "bear_rally_failure_right_tail_short",
                "main_control_intake_position": (
                    "paper_observation_admission_candidate"
                ),
                "source_recommended_runtime_stage": (
                    "tiny_live_intake_candidate_with_path_risk"
                ),
                "paper_observation_ready": True,
                "source_non_executing_trial_readiness": False,
                "required_facts_draft": [
                    "closed_1h_ohlcv",
                    "closed_4h_trend",
                    "squeeze_risk_state",
                ],
                "disable_or_review_facts_draft": [
                    "disable_strong_reclaim_proxy"
                ],
                "known_risks": ["3_of_11_cap4_events_hit_5m_stop"],
                "risk_envelope": {"attempt_cap_per_review_cycle": 3},
                "path_risk_evidence": {
                    "accepted_event_count": 11,
                    "path_safe_count": 8,
                    "stop_hit_count": 3,
                },
                "paper_observation_evidence_shape": {
                    "record_type": "paper_observation_only",
                    "must_not_feed": [
                        "FinalGate",
                        "Operation Layer",
                        "exchange_write",
                        "Tradeability Decision authority",
                        "Runtime Safety State authority",
                    ],
                },
                "actionable_now": False,
                "real_order_authority": False,
            },
            {
                "strategy_group_id": "RBR2-001",
                "strategy_direction": "range_upper_boundary_mean_reversion_short",
                "main_control_intake_position": "role_only_intake_candidate",
                "paper_observation_ready": True,
                "source_non_executing_trial_readiness": False,
                "known_risks": ["5m_stop_hit_rate_is_high"],
                "path_risk_evidence": {
                    "accepted_events": 78,
                    "path_safe_5m_count": 32,
                },
                "actionable_now": False,
                "real_order_authority": False,
            },
        ],
        "safety_invariants": _safe(),
    }


def test_capital_trial_envelope_projection_selects_mi_without_live_authority():
    module = _load_module()

    packet = module.build_capital_trial_envelope_projection(
        portfolio_board=_portfolio(),
        capture_gap_audit=_capture_audit(),
    )

    assert packet["status"] == "trial_envelope_projection_ready"
    assert packet["projection_schema"] == (
        "brc.strategygroup_capital_trial_envelope_projection.v1"
    )
    assert packet["projection_status"] == "trial_envelope_projection_ready"
    assert packet["projection_metadata"] == {
        "artifact_role": "trial_envelope_projection",
        "strategygroup_lifecycle_owner": False,
        "tradeability_decision_source": False,
        "runtime_truth_source": False,
        "owner_supervision_projection": True,
        "audit_evidence": True,
        "primary_object": "trial_envelope_v0",
    }
    assert packet["runtime_posture"]["signal_observation_grade"] == (
        "capital_trial_prepare_candidate_selected"
    )
    assert "p05_capital_trial" not in packet["goal_progress_projection"]
    assert "tiny_live_ready" not in packet["goal_progress_projection"]
    assert packet["goal_progress_projection"]["signal_observation_capital_trial"] == (
        "trial_prepare_candidate_pending_owner_policy"
    )
    assert packet["capital_trial_summary"]["selected_non_mpg_strategy_group_id"] == "MI-001"
    assert packet["capital_trial_summary"]["trial_envelope_generated"] is True
    assert "actionable_now_count" not in packet["capital_trial_summary"]
    assert packet["capital_trial_summary"]["live_permission_change_count"] == 0
    assert "real_order_authority_count" not in packet["capital_trial_summary"]
    selected = packet["selected_non_mpg_trial_candidate"]
    assert selected["candidate_status"] == "trial_prepare_candidate_pending_owner_policy"
    assert selected["symbol_scope"] == ["SOL/USDT:USDT"]
    assert selected["side_scope"] == ["long"]
    assert "registry_identity_unresolved" in selected["trial_blockers"]
    assert packet["owner_policy_checkpoint"]["runtime_owner_intervention_required"] is False

    trial_envelope = packet["trial_envelope_v0"]
    assert trial_envelope["schema"] == "brc.strategygroup_capital_trial_envelope.v0"
    assert trial_envelope["strategy_group_id"] == "MI-001"
    assert trial_envelope["trial_boundary"]["max_attempts"] == 1
    assert trial_envelope["trial_boundary"]["max_notional"] == "owner_policy_required"
    assert "actionable_now" not in trial_envelope
    assert trial_envelope["live_permission_change"] is False
    assert "real_order_authority" not in trial_envelope
    assert "actionability_source" not in trial_envelope["authority_boundary"]
    assert "actionable_now" not in trial_envelope["authority_boundary"]
    assert "real_order_authority" not in trial_envelope["authority_boundary"]
    assert "creates_execution_intent" not in trial_envelope["authority_boundary"]
    assert trial_envelope["authority_boundary"]["calls_finalgate"] is False
    assert trial_envelope["authority_boundary"]["calls_operation_layer"] is False
    assert trial_envelope["authority_boundary"]["calls_exchange_write"] is False
    assert trial_envelope["authority_boundary"]["places_order"] is False
    assert "creates_execution_intent" not in packet["safety_invariants"]
    assert "execution_intent_created" not in packet["safety_invariants"]
    assert "actionable_now" not in packet["safety_invariants"]
    assert "real_order_authority" not in packet["safety_invariants"]


def test_capital_trial_envelope_projection_prefers_brf2_short_candidate_from_research_intake():
    module = _load_module()

    packet = module.build_capital_trial_envelope_projection(
        portfolio_board=_portfolio(),
        capture_gap_audit=_capture_audit(),
        research_intake_review=_research_intake_review(),
    )

    assert packet["status"] == "trial_envelope_projection_ready"
    summary = packet["capital_trial_summary"]
    assert summary["selected_non_mpg_strategy_group_id"] == "BRF2-001"
    assert summary["selected_short_strategy_group_id"] == "BRF2-001"
    assert summary["short_experiment_candidate_count"] == 1
    assert "short_candidate_trade_count" not in summary
    assert summary["trial_envelope_generated"] is True
    assert "actionable_now_count" not in summary
    assert summary["live_permission_change_count"] == 0
    assert "real_order_authority_count" not in summary

    selected = packet["selected_non_mpg_trial_candidate"]
    assert selected["candidate_family"] == "short_research_intake"
    assert selected["candidate_status"] == (
        "short_experiment_evidence_pending_owner_policy"
    )
    assert selected["strategy_asset_current_decision"] == "promote"
    assert selected["strategy_asset_seed_source"] == (
        "curated_research_intake_strategy_asset_seed"
    )
    assert "decision_source" not in selected
    assert "decision" not in selected
    assert selected["reason"] == "promote_to_tiny_live_intake_candidate_not_live_ready"
    assert selected["promotion_scope"] == "intake_only"
    assert selected["promotion_target"] == (
        "paper_observation_or_experiment_evidence"
    )
    assert selected["tiny_live_ready"] is False
    assert selected["next_checkpoint"] == "BRF2-001_tiny_live_intake_evidence"
    assert selected["side_scope"] == ["short"]
    assert "source_non_executing_trial_readiness_not_closed" in selected[
        "trial_blockers"
    ]
    rows = {
        row["strategy_group_id"]: row
        for row in packet["capital_trial_eligibility_rows"]
    }
    assert rows["RBR2-001"]["strategy_asset_current_decision"] == "unknown"
    assert rows["RBR2-001"]["strategy_asset_seed_source"] == (
        "missing_strategy_asset_seed"
    )
    assert "decision_source" not in rows["RBR2-001"]
    assert rows["RBR2-001"]["strategy_asset_current_decision"] != "keep_observing"

    trial_envelope = packet["trial_envelope_v0"]
    assert trial_envelope["strategy_group_id"] == "BRF2-001"
    assert trial_envelope["candidate_status"] == (
        "short_experiment_evidence_pending_owner_policy"
    )
    assert trial_envelope["policy_outcome"] == "promote"
    assert "decision" not in trial_envelope
    assert "candidate-trade packet" not in trial_envelope["hypothesis"]
    assert "candidate-trade evidence" in trial_envelope["hypothesis"]
    assert trial_envelope["reason"] == (
        "promote_to_tiny_live_intake_candidate_not_live_ready"
    )
    assert trial_envelope["promotion_scope"] == "intake_only"
    assert trial_envelope["promotion_target"] == (
        "paper_observation_or_experiment_evidence"
    )
    assert trial_envelope["tiny_live_ready"] is False
    assert trial_envelope["next_checkpoint"] == (
        "BRF2-001_tiny_live_intake_evidence"
    )
    assert trial_envelope["side_scope"] == ["short"]
    assert trial_envelope["required_facts_draft"] == [
        "closed_1h_ohlcv",
        "closed_4h_trend",
        "squeeze_risk_state",
    ]
    assert "actionable_now" not in selected
    assert "real_order_authority" not in selected
    assert "actionable_now" not in trial_envelope
    assert "real_order_authority" not in trial_envelope
    assert trial_envelope["authority_boundary"]["promotion_scope"] == "intake_only"
    assert trial_envelope["authority_boundary"]["promotion_scope_is_intake_only"] is True
    assert trial_envelope["authority_boundary"]["tiny_live_ready"] is False
    assert trial_envelope["authority_boundary"]["unscoped_promote"] is False
    assert "review_outcome" in trial_envelope["review_fields"]
    assert "review_decision" not in trial_envelope["review_fields"]
    assert trial_envelope["authority_boundary"]["calls_finalgate"] is False
    assert trial_envelope["authority_boundary"]["calls_operation_layer"] is False
    assert trial_envelope["authority_boundary"]["calls_exchange_write"] is False
    assert "actionable_now" not in trial_envelope["authority_boundary"]
    assert "real_order_authority" not in trial_envelope["authority_boundary"]
    assert "Tradeability Decision authority" in trial_envelope[
        "paper_observation_evidence_shape"
    ]["must_not_feed"]
    assert "Runtime Safety State authority" in trial_envelope[
        "paper_observation_evidence_shape"
    ]["must_not_feed"]
    assert "actionable_now" not in trial_envelope[
        "paper_observation_evidence_shape"
    ]["must_not_feed"]
    projection_md = module._projection_markdown(
        packet,
        Path("/tmp/latest-strategygroup-capital-trial-envelope-projection.json"),
        Path("/tmp/latest-strategygroup-capital-trial-envelope-v0.json"),
    )
    trial_md = module._trial_envelope_markdown(
        trial_envelope,
        Path("/tmp/latest-strategygroup-capital-trial-envelope-v0.json"),
    )
    assert "Tiny live ready" not in projection_md
    assert "Tiny live ready" not in trial_md
    assert "Actionable now" not in trial_md
    assert "Real order authority" not in trial_md
    assert trial_envelope["authority_boundary"]["places_order"] is False
    assert "creates_execution_intent" not in trial_envelope["authority_boundary"]
    assert "creates_execution_intent" not in packet["safety_invariants"]
    assert "execution_intent_created" not in packet["safety_invariants"]


def test_capital_trial_envelope_projection_rejects_unscoped_promote_artifact():
    module = _load_module()

    safety = module._safety_invariants()
    trial_envelope = {
        "schema": "brc.strategygroup_capital_trial_envelope.v0",
        "policy_outcome": "promote",
        "promotion_scope": "not_applicable",
        "tiny_live_ready": False,
        "live_permission_change": False,
        "authority_boundary": {
            "promotion_scope": "not_applicable",
            "unscoped_promote": False,
        },
    }

    reasons = module._projection_reject_reasons(
        eligibility_rows=[{"strategy_group_id": item} for item in [
            "BRF2-001",
            "MI-001",
            "LSR-001",
            "BRF-001",
            "CPM-RO-001",
        ]],
        ranking=[{"strategy_group_id": "BRF2-001"}],
        selected={"strategy_group_id": "BRF2-001"},
        trial_envelope=trial_envelope,
        safety=safety,
    )

    assert "unscoped_promote_forbidden" in reasons
    assert "authority_boundary_promotion_scope_missing" in reasons


def test_capital_trial_envelope_projection_rejects_legacy_actionability_mirrors():
    module = _load_module()

    reasons = module._projection_reject_reasons(
        eligibility_rows=[
            {"strategy_group_id": item}
            for item in [
                "BRF2-001",
                "MI-001",
                "LSR-001",
                "BRF-001",
                "CPM-RO-001",
            ]
        ],
        ranking=[{"strategy_group_id": "BRF2-001"}],
        selected={"strategy_group_id": "BRF2-001"},
        trial_envelope={
            "schema": "brc.strategygroup_capital_trial_envelope.v0",
            "policy_outcome": "pending",
            "actionable_now": False,
            "live_permission_change": False,
            "real_order_authority": False,
        },
        safety=module._safety_invariants(),
    )

    assert "trial_envelope.legacy_authority_mirror_present:actionable_now" in reasons
    assert (
        "trial_envelope.legacy_authority_mirror_present:real_order_authority"
        in reasons
    )


def test_capital_trial_envelope_projection_keeps_insufficient_evidence_as_engineering_queue():
    module = _load_module()

    packet = module.build_capital_trial_envelope_projection(
        portfolio_board=_portfolio(),
        capture_gap_audit=_capture_audit(),
    )

    queue = {
        row["strategy_group_id"]: row
        for row in packet["engineering_continuation_queue"]
    }
    assert queue["LSR-001"]["next_engineering_bottleneck"] == (
        "defer_until_rewrite_and_range_facts_closed"
    )
    assert queue["BRF-001"]["next_engineering_bottleneck"] == (
        "defer_until_squeeze_requiredfacts_forward_completed"
    )
    assert queue["CPM-RO-001"]["next_engineering_bottleneck"] == (
        "defer_until_identity_or_merge_review_closed"
    )
    assert queue["BTPC-001"]["next_engineering_bottleneck"] == (
        "defer_until_fact_source_classifier_closed"
    )


def test_capital_trial_envelope_projection_rejects_forbidden_source_effects():
    module = _load_module()
    portfolio = _portfolio()
    portfolio["safety_invariants"]["calls_exchange_write"] = True

    try:
        module.build_capital_trial_envelope_projection(
            portfolio_board=portfolio,
            capture_gap_audit=_capture_audit(),
        )
    except ValueError as exc:
        assert "forbidden effects" in str(exc)
    else:
        raise AssertionError("expected forbidden source effect to fail")


def test_capital_trial_envelope_projection_rejects_source_legacy_mirror_separately():
    module = _load_module()
    portfolio = _portfolio()
    portfolio["safety_invariants"]["actionable_now"] = True

    try:
        module.build_capital_trial_envelope_projection(
            portfolio_board=portfolio,
            capture_gap_audit=_capture_audit(),
        )
    except ValueError as exc:
        assert "legacy authority mirrors" in str(exc)
        assert "forbidden effects" not in str(exc)
    else:
        raise AssertionError("expected legacy authority mirror to fail")


def test_capital_trial_envelope_projection_cli_writes_projection_and_trial_envelope(tmp_path, capsys):
    module = _load_module()
    portfolio_json = tmp_path / "portfolio.json"
    audit_json = tmp_path / "audit.json"
    output_json = tmp_path / "projection.json"
    output_md = tmp_path / "projection.md"
    trial_json = tmp_path / "trial.json"
    trial_md = tmp_path / "trial.md"
    portfolio_json.write_text(json.dumps(_portfolio()), encoding="utf-8")
    audit_json.write_text(json.dumps(_capture_audit()), encoding="utf-8")

    exit_code = module.main(
        [
            "--portfolio-board-json",
            str(portfolio_json),
            "--capture-gap-audit-json",
            str(audit_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
            "--output-trial-envelope-json",
            str(trial_json),
            "--output-trial-envelope-md",
            str(trial_md),
        ]
    )

    assert exit_code == 0
    projection = json.loads(output_json.read_text(encoding="utf-8"))
    trial = json.loads(trial_json.read_text(encoding="utf-8"))
    assert projection["status"] == "trial_envelope_projection_ready"
    assert projection["projection_status"] == "trial_envelope_projection_ready"
    assert trial["strategy_group_id"] == "MI-001"
    assert "creates_execution_intent" not in trial["authority_boundary"]
    assert "creates_execution_intent" not in projection["safety_invariants"]
    assert "execution_intent_created" not in projection["safety_invariants"]
    assert "actionable_now" not in trial
    assert "real_order_authority" not in trial
    assert "actionable_now" not in trial["authority_boundary"]
    assert "real_order_authority" not in trial["authority_boundary"]
    assert "actionable_now" not in projection["safety_invariants"]
    assert "real_order_authority" not in projection["safety_invariants"]
    assert "StrategyGroup Capital Trial Envelope Projection" in output_md.read_text(
        encoding="utf-8"
    )
    assert "Trial packet generated" not in output_md.read_text(encoding="utf-8")
    assert "Trial envelope generated" in output_md.read_text(encoding="utf-8")
    trial_md_text = trial_md.read_text(encoding="utf-8")
    assert "StrategyGroup Capital Trial Envelope v0" in trial_md_text
    assert "Actionable now" not in trial_md_text
    assert "Real order authority" not in trial_md_text
