from __future__ import annotations

from src.application.action_spec_final_gate_adapter import (
    ActionCandidateAdapterInput,
    ActionSpecDraftInput,
    ActionSpecFinalGateAdapterService,
    FinalGateFactInput,
)


def _service() -> ActionSpecFinalGateAdapterService:
    return ActionSpecFinalGateAdapterService()


def _candidate(**overrides):
    data = {
        "candidate_id": "action-candidate:TF-001-live-readonly-v0",
        "family": "Trend",
        "strategy_family_id": "TF-001-live-readonly-v0",
        "carrier_id": "TF-001-live-readonly-v0",
        "admission_level": "L3",
        "candidate_status": "supported_but_backend_not_actionable",
        "action_registry_supported": True,
        "proposal_role": "trend_candidate",
        "warnings": ["weak current alpha proof", "regime uncertainty"],
        "hard_blockers": [],
    }
    data.update(overrides)
    return ActionCandidateAdapterInput(**data)


def _action_spec(**overrides):
    data = {
        "action_spec_id": "action-spec:TF-001-live-readonly-v0",
        "status": "valid_blocked_final_gate",
        "family": "Trend",
        "strategy_family_id": "TF-001-live-readonly-v0",
        "carrier_id": "TF-001-live-readonly-v0",
        "admission_level": "L3",
        "action_registry_supported": True,
        "proposal_role": "trend_candidate",
        "supported_symbols": ["SOL/USDT:USDT"],
        "supported_sides": ["long"],
        "symbol": "SOL/USDT:USDT",
        "side": "long",
        "quantity": "0.1",
        "max_notional": "20",
        "leverage": "1",
        "max_attempts": 1,
        "protection_mode": "single_tp_plus_sl",
        "review_requirement": "post_action_review_required",
        "protection_template": {
            "template_id": "protection-template:TF-001-live-readonly-v0",
            "mode": "single_tp_plus_sl",
            "mandatory": True,
            "hard_blockers": [],
        },
        "review_template": {
            "template_id": "review-template:TF-001-live-readonly-v0",
            "post_action_required": True,
        },
        "warnings": ["false continuation"],
        "hard_blockers": [],
    }
    data.update(overrides)
    return ActionSpecDraftInput(**data)


def _ready_facts():
    return FinalGateFactInput(
        owner_authorization_ref="owner-authorization:TF-001-live-readonly-v0",
        account_facts_ref="account-facts:fresh",
        reconciliation_facts_ref="reconciliation:fresh",
        operation_layer_ref="operation-layer:preflight",
        runtime_guard_ref="runtime-guard:clear",
    )


def test_adapter_marks_complete_spec_ready_for_official_final_gate_only():
    result = _service().adapt(
        candidate=_candidate(),
        action_spec=_action_spec(owner_authorization_ref="owner-authorization:TF-001-live-readonly-v0"),
        facts=_ready_facts(),
    )

    assert result.action_spec.status == "valid"
    assert result.final_gate_preview.status == "ready_for_final_gate"
    assert result.final_gate_preview.product_message.startswith(
        "This candidate can be converted to an ActionSpec"
    )
    assert result.final_gate_preview.may_execute_live is False
    assert result.final_gate_preview.owner_action_enabled is False
    assert result.final_gate_preview.places_order is False
    assert result.final_gate_is_execution_gate is True
    assert result.no_action_guarantee["places_order"] is False


def test_adapter_classifies_missing_owner_authorization_before_final_gate():
    result = _service().adapt(
        candidate=_candidate(),
        action_spec=_action_spec(),
        facts=FinalGateFactInput(),
    )

    assert result.action_spec.status == "valid"
    assert result.final_gate_preview.status == "needs_owner_authorization"
    assert result.final_gate_preview.authorization_required is True
    assert "missing_owner_authorization" in result.hard_blockers
    assert "missing_account_facts" in result.hard_blockers
    assert "weak current alpha proof" in result.warnings
    assert result.action_spec.creates_execution_intent is False
    assert result.action_spec.exchange_write_action is False


def test_adapter_classifies_budget_authorization_for_mr_candidate():
    result = _service().adapt(
        candidate=_candidate(
            candidate_id="action-candidate:MR-001-live-readonly-v0",
            family="Mean reversion",
            strategy_family_id="MR-001-live-readonly-v0",
            carrier_id="MR-001-live-readonly-v0",
            admission_level="L2",
            proposal_role="range_candidate",
        ),
        action_spec=_action_spec(
            action_spec_id="action-spec:MR-001-live-readonly-v0",
            family="Mean reversion",
            strategy_family_id="MR-001-live-readonly-v0",
            carrier_id="MR-001-live-readonly-v0",
            admission_level="L2",
            proposal_role="range_candidate",
            supported_symbols=["ETH/USDT:USDT", "BTC/USDT:USDT"],
            symbol="ETH/USDT:USDT",
            quantity=None,
            target_notional_usdt="22",
            max_notional="25",
            budget_envelope_ref="budget-envelope:MR-001-live-readonly-v0",
        ),
        facts=FinalGateFactInput(
            account_facts_ref="account-facts:fresh",
            reconciliation_facts_ref="reconciliation:fresh",
            operation_layer_ref="operation-layer:preflight",
            runtime_guard_ref="runtime-guard:clear",
        ),
    )

    assert result.action_spec.status == "valid"
    assert result.action_spec.target_notional_usdt == "22"
    assert result.final_gate_preview.status == "needs_budget_authorization"
    assert result.final_gate_preview.budget_required is True
    assert "missing_budget_authorization" in result.hard_blockers
    assert result.final_gate_preview.places_order is False


def test_adapter_keeps_volatility_proposal_only():
    result = _service().adapt(
        candidate=_candidate(
            candidate_id="action-candidate:VB-001-live-readonly-v0",
            family="Volatility expansion",
            strategy_family_id="VB-001-live-readonly-v0",
            carrier_id="VB-001-live-readonly-v0",
            admission_level="L2",
            candidate_status="proposal",
            action_registry_supported=False,
            proposal_role="volatility_candidate",
            warnings=["fake breakout"],
        ),
        action_spec=_action_spec(
            action_spec_id="action-spec:VB-001-live-readonly-v0",
            status="proposal_non_action",
            family="Volatility expansion",
            strategy_family_id="VB-001-live-readonly-v0",
            carrier_id="VB-001-live-readonly-v0",
            admission_level="L2",
            action_registry_supported=False,
            proposal_role="volatility_candidate",
            supported_symbols=["BTC/USDT:USDT", "ETH/USDT:USDT"],
            symbol="BTC/USDT:USDT",
            quantity="0.001",
        ),
        facts=_ready_facts(),
    )

    assert result.action_spec.status == "proposal_only"
    assert result.final_gate_preview.status == "proposal_only"
    assert "proposal_only_candidate" in result.hard_blockers
    assert result.final_gate_preview.may_execute_live is False
    assert result.final_gate_preview.owner_action_enabled is False


def test_adapter_keeps_bnb_historical_sample_dry_run_only():
    result = _service().adapt(
        candidate=_candidate(
            candidate_id="action-candidate:MI-001-BNB-LONG",
            family="BNB manual bounded live proof",
            strategy_family_id="MI-001",
            carrier_id="MI-001-BNB-LONG",
            admission_level="L0",
            candidate_status="historical_proof_not_current_authorization",
            proposal_role="historical_regression_sample",
            dry_run_only=True,
        ),
        action_spec=_action_spec(
            action_spec_id="action-spec:MI-001-BNB-LONG",
            status="historical_proof_not_current_authorization",
            family="BNB manual bounded live proof",
            strategy_family_id="MI-001",
            carrier_id="MI-001-BNB-LONG",
            admission_level="L0",
            proposal_role="historical_regression_sample",
            supported_symbols=["BNB/USDT:USDT"],
            symbol="BNB/USDT:USDT",
            quantity="0.01",
        ),
        facts=_ready_facts(),
    )

    assert result.action_spec.status == "dry_run_only"
    assert result.final_gate_preview.status == "dry_run_only"
    assert "dry_run_only_candidate" in result.hard_blockers
    assert result.final_gate_preview.places_order is False


def test_adapter_prioritizes_scope_mismatch_and_missing_protection():
    scope_result = _service().adapt(
        candidate=_candidate(),
        action_spec=_action_spec(symbol="DOGE/USDT:USDT"),
        facts=_ready_facts(),
    )
    assert scope_result.action_spec.status == "invalid"
    assert scope_result.final_gate_preview.status == "blocked_by_scope_mismatch"
    assert "symbol_outside_carrier_scope" in scope_result.hard_blockers

    protection_result = _service().adapt(
        candidate=_candidate(),
        action_spec=_action_spec(
            owner_authorization_ref="owner-authorization:TF-001-live-readonly-v0",
            protection_template={
                "template_id": "protection-template:TF-001-live-readonly-v0",
                "mode": "single_tp_plus_sl",
                "hard_blockers": ["TP/SL plan unavailable"],
            },
        ),
        facts=_ready_facts(),
    )
    assert protection_result.final_gate_preview.status == (
        "blocked_by_missing_protection_template"
    )
    assert "missing_or_incomplete_protection_template" in protection_result.hard_blockers
