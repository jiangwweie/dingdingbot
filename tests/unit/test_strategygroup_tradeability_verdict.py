from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_strategygroup_tradeability_verdict.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_tradeability_verdict",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _capital_trial_bridge() -> dict:
    return {
        "status": "capital_trial_readiness_bridge_ready",
        "capital_trial_eligibility_rows": [
            {
                "strategy_group_id": "BRF2-001",
                "candidate_family": "short_research_intake",
                "candidate_status": "short_candidate_trade_packet_pending_owner_policy",
                "research_intake_position": "paper_observation_admission_candidate",
                "identity_status": "main_control_research_intake_asset",
                "execution_tier": "unknown",
                "pool_stage": "tiny_live_intake_candidate_with_path_risk",
                "promotion_scope": "intake_only",
                "tiny_live_ready": False,
                "owner_policy_required": True,
                "risk_boundary_ready": False,
                "risk_boundary_missing": [
                    "capital_scope",
                    "max_notional",
                    "valid_until",
                    "trial_identity",
                ],
                "risk_envelope": {
                    "attempt_cap_per_review_cycle": 3,
                    "daily_loss_cap_units": 1,
                },
                "symbol_scope": ["owner_policy_required"],
                "side_scope": ["short"],
                "recent_opportunity_count": 11,
                "would_enter_forward_positive_count": 8,
                "tradable_forward_count": 8,
                "ranking_score": 597,
                "trial_recommendation": "candidate_trade_prepare_pending_owner_policy",
                "trial_blockers": [
                    "source_tiny_live_ready_false",
                    "owner_capital_scope_not_confirmed",
                    "owner_trial_identity_not_confirmed",
                    "fresh_signal_absent",
                    "action_time_finalgate_not_reached",
                    "official_operation_layer_not_reached",
                ],
                "required_facts_draft": [
                    "closed_1h_ohlcv",
                    "squeeze_risk_state",
                ],
                "actionable_now": False,
                "real_order_authority": False,
            },
            {
                "strategy_group_id": "BTPC-001",
                "candidate_family": "portfolio_capture_gap",
                "identity_status": "registry_or_portfolio_identity_present",
                "execution_tier": "L2",
                "candidate_status": "revise_before_trial_prepare",
                "side_scope": ["short"],
                "trial_recommendation": "defer_until_fact_source_classifier_closed",
                "trial_blockers": [
                    "no_action_or_classifier_attribution_needs_closure",
                    "stale_fact_source_classifier_blocker_unclosed",
                    "fresh_signal_absent",
                    "action_time_finalgate_not_reached",
                    "official_operation_layer_not_reached",
                ],
                "actionable_now": False,
                "real_order_authority": False,
            },
            {
                "strategy_group_id": "RBR2-001",
                "candidate_family": "short_research_intake",
                "research_intake_position": "role_only_intake_candidate",
                "candidate_status": "role_only_short_candidate_trade_watchlist",
                "side_scope": ["short"],
                "trial_blockers": [
                    "best role is filler not main right-tail engine",
                    "fresh_signal_absent",
                ],
                "actionable_now": False,
                "real_order_authority": False,
            },
        ],
        "selected_non_mpg_trial_candidate": {
            "strategy_group_id": "BRF2-001",
            "candidate_family": "short_research_intake",
            "candidate_status": "short_candidate_trade_packet_pending_owner_policy",
            "research_intake_position": "paper_observation_admission_candidate",
            "promotion_scope": "intake_only",
            "tiny_live_ready": False,
            "side_scope": ["short"],
            "trial_blockers": [
                "source_tiny_live_ready_false",
                "owner_capital_scope_not_confirmed",
                "fresh_signal_absent",
            ],
        },
    }


def _registry() -> dict:
    return {
        "status": "registry_ready",
        "rows": [
            {
                "strategy_group_id": "MPG-001",
                "default_tier": "L4",
                "trial_eligible": True,
                "supported_sides": ["long"],
                "required_facts_summary": {"market": "latest price"},
                "actionable_now": False,
                "real_order_authority": False,
            },
            {
                "strategy_group_id": "BTPC-001",
                "default_tier": "L2",
                "trial_eligible": False,
                "supported_sides": ["short"],
                "required_facts_summary": {"market": "closed candles"},
                "actionable_now": False,
                "real_order_authority": False,
            },
            {
                "strategy_group_id": "RBR-001",
                "default_tier": "L1",
                "trial_eligible": False,
                "supported_sides": ["short_review"],
                "actionable_now": False,
                "real_order_authority": False,
            },
        ],
    }


def _tier_policy() -> dict:
    return {
        "current_strategy_groups": {
            "MPG-001": {
                "tier": "L4",
                "mode": "tiny_real_order_eligible",
            },
            "BTPC-001": {
                "tier": "L2",
                "mode": "shadow_candidate",
            },
        }
    }


def _signal_coverage() -> dict:
    return {
        "status": "mainline_no_signal_low_priority_broader_would_enter",
        "checks": {
            "runtime_ready_signal_count": 0,
            "broader_would_enter_signal_count": 1,
        },
        "broader_observation": {
            "would_enter_signals": [
                {
                    "strategy_group_id": "RBR-001",
                    "symbol": "ADA/USDT:USDT",
                    "side": "short",
                    "signal_type": "would_enter",
                    "not_live_signal": True,
                    "actionable_now": False,
                    "real_order_authority": False,
                }
            ]
        },
    }


def _live_submit_readiness() -> dict:
    return {
        "status": "live_submit_standby_waiting_for_market",
        "checks": {
            "live_submit_ready": False,
            "fresh_signal_state": "none",
        },
        "decision": {
            "live_submit_ready": False,
            "live_submit_ready_false_reason": "no_fresh_signal",
            "actionable_now": False,
            "real_order_authority": False,
        },
    }


def _live_submit_readiness_ready_for(strategy_group_id: str | None) -> dict:
    packet = {
        "status": "live_submit_ready",
        "checks": {
            "live_submit_ready": True,
            "fresh_signal_state": "fresh_selected_strategygroup_signal",
        },
        "decision": {
            "live_submit_ready": True,
            "actionable_now": True,
            "real_order_authority": True,
        },
    }
    if strategy_group_id:
        packet["selected_strategy_group_id"] = strategy_group_id
        packet["runtime_scope"] = {"strategy_group_id": strategy_group_id}
        packet["fresh_signal"] = {"strategy_group_id": strategy_group_id}
    return packet


def _trial_asset_admission_proposal() -> dict:
    return {
        "status": "trial_asset_admission_proposal_ready",
        "proposal": {
            "strategy_group_id": "BRF2-001",
            "current_stage": "tiny_live_intake_candidate",
            "proposed_stage": "trial_asset_admission_candidate",
            "next_action": "record_owner_trial_scope_policy",
            "after_next_state": "admitted_trial_asset",
            "actionable_now": False,
            "real_order_authority": False,
        },
        "checks": {
            "owner_policy_blocker_present": True,
            "owner_decision_required": False,
            "actionable_now": False,
            "real_order_authority": False,
        },
        "safety_invariants": {
            "actionable_now": False,
            "real_order_authority": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
    }


def test_tradeability_verdict_classifies_first_blockers_without_authority():
    module = _load_module()

    packet = module.build_tradeability_verdict(
        capital_trial_bridge=_capital_trial_bridge(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        live_submit_readiness=_live_submit_readiness(),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["verdict_rows"]}
    assert packet["status"] == "tradeability_verdict_ready"
    assert rows["BRF2-001"]["verdict"] == "not_tradable_asset_admission"
    assert rows["BRF2-001"]["first_blocker_class"] == (
        "strategy_group_not_admitted_as_final_trial_asset"
    )
    assert rows["BRF2-001"]["blocker_owner"] == "engineering"
    assert rows["BRF2-001"]["next_action"] == "build_trial_asset_admission_proposal"
    assert rows["BRF2-001"]["after_next_state"] == "trial_asset_admission_candidate"

    assert rows["MPG-001"]["verdict"] == "not_tradable_market_wait"
    assert rows["MPG-001"]["stage"] == "armed_observation"
    assert rows["MPG-001"]["blocker_owner"] == "market"

    assert rows["BTPC-001"]["verdict"] == "not_tradable_facts"
    assert rows["BTPC-001"]["first_blocker_class"] == (
        "required_facts_or_classifier_mapping_unclosed"
    )

    assert rows["RBR-001"]["verdict"] == "not_tradable_strategy_quality"
    assert rows["RBR-001"]["stage"] == "observe_only_would_enter"
    assert rows["RBR-001"]["evidence_snapshot"]["latest_observe_only_symbol"] == (
        "ADA/USDT:USDT"
    )

    assert rows["RBR2-001"]["stage"] == "role_only_intake_candidate"
    assert rows["RBR2-001"]["verdict"] == "not_tradable_strategy_quality"

    assert packet["summary"]["tradable_now_count"] == 0
    assert packet["summary"]["actionable_now_count"] == 0
    assert packet["summary"]["real_order_authority_count"] == 0
    assert packet["checks"]["market_wait_only_after_admission"] is True
    for row in packet["verdict_rows"]:
        assert row["actionable_now"] is False
        assert row["real_order_authority"] is False


def test_tradeability_verdict_advances_brf2_to_policy_blocker_after_proposal():
    module = _load_module()

    packet = module.build_tradeability_verdict(
        capital_trial_bridge=_capital_trial_bridge(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        live_submit_readiness=_live_submit_readiness(),
        trial_asset_admission_proposal=_trial_asset_admission_proposal(),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["verdict_rows"]}
    assert rows["BRF2-001"]["stage"] == "trial_asset_admission_candidate"
    assert rows["BRF2-001"]["verdict"] == "not_tradable_policy"
    assert rows["BRF2-001"]["blocker_owner"] == "owner"
    assert rows["BRF2-001"]["next_action"] == "record_owner_trial_scope_policy"
    assert rows["BRF2-001"]["after_next_state"] == "admitted_trial_asset"
    assert rows["BRF2-001"]["runtime_scope_status"][
        "trial_asset_admission_proposal_ready"
    ] is True
    assert packet["checks"]["owner_policy_blocker_present"] is True
    assert packet["checks"]["owner_decision_required"] is False


def test_scoped_live_submit_only_marks_matching_strategy_group_tradable():
    module = _load_module()

    packet = module.build_tradeability_verdict(
        capital_trial_bridge=_capital_trial_bridge(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        live_submit_readiness=_live_submit_readiness_ready_for("MPG-001"),
        trial_asset_admission_proposal=_trial_asset_admission_proposal(),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["verdict_rows"]}
    assert rows["MPG-001"]["stage"] == "live_submit_ready"
    assert rows["MPG-001"]["verdict"] == "tradable_now"
    assert rows["MPG-001"]["actionable_now"] is True
    assert rows["MPG-001"]["real_order_authority"] is True

    assert rows["BRF2-001"]["verdict"] == "not_tradable_policy"
    assert rows["BTPC-001"]["verdict"] != "tradable_now"
    assert rows["RBR-001"]["verdict"] != "tradable_now"
    assert rows["RBR2-001"]["verdict"] != "tradable_now"
    assert packet["summary"]["tradable_now_count"] == 1
    assert packet["summary"]["top_strategy_group_id"] == "MPG-001"
    assert packet["summary"]["top_verdict"] == "tradable_now"
    assert packet["summary"]["selected_candidate_strategy_group_id"] == "BRF2-001"
    assert packet["summary"]["selected_candidate_verdict"] == "not_tradable_policy"
    assert packet["summary"]["actionable_now_count"] == 1
    assert packet["summary"]["real_order_authority_count"] == 1
    assert packet["checks"]["tradable_now_rows_have_authority"] is True
    assert packet["checks"]["authority_rows_are_tradable_now"] is True
    assert packet["checks"]["tradable_now_scoped_to_live_submit"] is True


def test_unscoped_live_submit_ready_does_not_make_any_row_tradable():
    module = _load_module()

    packet = module.build_tradeability_verdict(
        capital_trial_bridge=_capital_trial_bridge(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        live_submit_readiness=_live_submit_readiness_ready_for(None),
        trial_asset_admission_proposal=_trial_asset_admission_proposal(),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["verdict_rows"]}
    assert rows["MPG-001"]["verdict"] != "tradable_now"
    assert rows["BRF2-001"]["verdict"] == "not_tradable_policy"
    assert packet["summary"]["tradable_now_count"] == 0
    assert packet["summary"]["actionable_now_count"] == 0
    assert packet["summary"]["real_order_authority_count"] == 0
    for row in packet["verdict_rows"]:
        assert row["actionable_now"] is False
        assert row["real_order_authority"] is False


def test_tradeability_verdict_cli_writes_json_and_markdown(tmp_path: Path):
    module = _load_module()
    bridge_json = tmp_path / "bridge.json"
    registry_json = tmp_path / "registry.json"
    tier_json = tmp_path / "tier.json"
    signal_json = tmp_path / "signal.json"
    live_json = tmp_path / "live.json"
    output_json = tmp_path / "verdict.json"
    output_md = tmp_path / "verdict.md"
    bridge_json.write_text(json.dumps(_capital_trial_bridge()), encoding="utf-8")
    registry_json.write_text(json.dumps(_registry()), encoding="utf-8")
    tier_json.write_text(json.dumps(_tier_policy()), encoding="utf-8")
    signal_json.write_text(json.dumps(_signal_coverage()), encoding="utf-8")
    live_json.write_text(json.dumps(_live_submit_readiness()), encoding="utf-8")

    exit_code = module.main(
        [
            "--capital-trial-readiness-bridge-json",
            str(bridge_json),
            "--registry-json",
            str(registry_json),
            "--tier-policy-json",
            str(tier_json),
            "--signal-coverage-json",
            str(signal_json),
            "--live-submit-readiness-json",
            str(live_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ]
    )

    assert exit_code == 0
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    assert packet["status"] == "tradeability_verdict_ready"
    assert packet["schema"] == module.SCHEMA
    assert packet["scope"] == "strategygroup_tradeability_verdict_read_model"
    assert packet["generated_at_utc"]
    assert packet["owner_summary"]["real_order_authority"] is False
    assert packet["summary"]["row_count"] == len(packet["verdict_rows"])
    assert packet["checks"]["row_count_matches_verdict_rows"] is True
    assert packet["checks"]["tradable_now_rows_have_authority"] is True
    assert packet["checks"]["authority_rows_are_tradable_now"] is True
    assert packet["checks"]["tradable_now_scoped_to_live_submit"] is True
    assert "StrategyGroup Tradeability Verdict" in output_md.read_text(
        encoding="utf-8"
    )
