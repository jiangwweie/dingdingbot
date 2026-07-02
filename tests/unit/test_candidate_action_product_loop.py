from __future__ import annotations

from src.application.candidate_action_product_loop import build_candidate_action_product_loop
from src.application.production_strategy_family_admission import (
    build_production_strategy_family_admission_state,
)


def test_candidate_action_product_loop_represents_four_stage_non_live_contract():
    state = build_production_strategy_family_admission_state(now_ms=1770000000000)
    bundle = build_candidate_action_product_loop(
        owner_market_input={
            "regime": "trend",
            "mapped_family": "Trend",
            "risk_tier": "tiny",
        },
        budget_recommendation={
            "risk_tier": {"tier": "tiny"},
            "budget_envelope": {
                "status": "degraded_missing_account_facts",
                "envelope_id": "budget-envelope:read-model",
                "max_notional_per_action": "20",
                "total_budget": "60",
                "max_attempts": 1,
            },
            "missing_facts": ["account_facts"],
            "blockers": [
                {
                    "id": "budget_account_facts_missing",
                    "severity": "hard_blocker",
                }
            ],
        },
        selected_candidate={
            "family": "Trend",
            "carrier_id": "TF-001-live-readonly-v0",
        },
        candidate_output=[
            item.model_dump(mode="json")
            for item in state.trading_console_candidate_output
        ],
        generic_action_specs=[
            item.model_dump(mode="json") for item in state.generic_action_specs
        ],
        action_entry_payload_contracts=[
            item.model_dump(mode="json")
            for item in state.action_entry_payload_contracts
        ],
        action_entry_output=[
            item.model_dump(mode="json")
            for item in state.trading_console_action_entry_output
        ],
        final_gate_adapter_results=[
            item.model_dump(mode="json") for item in state.final_gate_adapter_results
        ],
        post_action_state={
            "status": "empty",
            "intent_count": 0,
            "entry_order_count": 0,
            "protection_order_count": 0,
            "review_count": 0,
            "audit_event_count": 0,
            "completed_intents_today_by_symbol": {},
            "review_ledger": {"lifecycle_status": "not_started_or_unknown"},
        },
        fact_context={
            "account": {"status": "not_available"},
            "environment": {"trading_env": "local"},
            "guards": {},
            "pg_positions": [],
            "pg_open_orders": [],
            "completed_intents_today_by_symbol": {},
        },
    )

    loops = {item.candidate_id: item for item in bundle.candidate_action_readiness_loop}
    assert set(loops) >= {
        "action-candidate:MI-001-BNB-LONG",
        "action-candidate:TF-001-live-readonly-v0",
        "action-candidate:MR-001-live-readonly-v0",
        "action-candidate:VB-001-live-readonly-v0",
    }

    trend = loops["action-candidate:TF-001-live-readonly-v0"]
    assert trend.readiness_state == "authorization_draft_ready"
    assert trend.confirmable_state == "owner_confirmable"
    assert trend.authorization_draft.draft_status == "authorization_draft_ready"
    assert trend.final_gate_readiness.status == "needs_owner_authorization"
    assert trend.operation_layer_preflight.status == (
        "official_preflight_path_available_after_authorization"
    )
    assert trend.operation_layer_preflight.preflight_endpoint == (
        "POST /api/brc/operations/preflight"
    )
    assert trend.operation_layer_preflight.not_submitted is True
    assert trend.protection_draft.template_id == (
        "protection-template:TF-001-live-readonly-v0"
    )
    assert trend.review_plan.template_id == "review-template:TF-001-live-readonly-v0"
    assert "trend continuation" in trend.review_plan.family_review_focus
    assert {stage.stage for stage in trend.stage_statuses} == {
        "candidate_authorization_final_gate_readiness",
        "owner_confirmed_console_action_entry",
        "operation_layer_dry_run_preflight",
        "protection_review_operational_loop",
    }
    assert "account_facts" in trend.final_gate_readiness.missing_facts

    mr = loops["action-candidate:MR-001-live-readonly-v0"]
    assert mr.confirmable_state == "budget_confirmable"
    assert mr.authorization_draft.mode == "budget_envelope"
    assert mr.budget_draft.budget_authorization_status == "needs_budget_authorization"
    assert mr.action_spec_draft.target_notional_usdt == "22"
    assert "snapback" in mr.review_plan.family_review_focus

    volatility = loops["action-candidate:VB-001-live-readonly-v0"]
    assert volatility.confirmable_state == "proposal_only"
    assert volatility.operation_layer_preflight.status == "disabled_by_policy"
    assert "true expansion" in volatility.review_plan.family_review_focus

    bnb = loops["action-candidate:MI-001-BNB-LONG"]
    assert bnb.confirmable_state == "dry_run_only"
    assert bnb.authorization_draft.mode == "historical_dry_run"
    assert "entry validity" in bnb.review_plan.family_review_focus

    for item in loops.values():
        assert item.backend_actionable is False
        assert item.may_execute_live is False
        assert item.owner_action_enabled is False
        assert item.places_order is False
        assert item.exchange_write_action is False
    assert bundle.no_action_guarantee["places_order"] is False
