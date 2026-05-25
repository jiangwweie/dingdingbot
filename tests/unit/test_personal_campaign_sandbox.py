from __future__ import annotations

from decimal import Decimal

import pytest

from src.application.personal_campaign_sandbox import (
    PersonalCampaignSandboxDisabled,
    apply_human_arm_decision,
    apply_position_and_campaign_controls,
    build_campaign_sandbox_scenario_catalog,
    build_risk_order_plan,
    build_trade_intent,
    evaluate_campaign_sandbox_trace_invariants,
    run_campaign_sandbox_trace,
    run_campaign_sandbox_scenario,
    simulate_execution_receipt,
)
from src.domain.models import Direction
from src.domain.personal_campaign import (
    CampaignDecision,
    CampaignInvariantStatus,
    CampaignLifecycleStatus,
    CampaignRiskCaps,
    CampaignSandboxSettings,
    CampaignState,
    ExecutionReceiptStatus,
    FeatureSnapshot,
    HumanArmAction,
    HumanArmDecision,
    ModeAdvice,
    ModeDefaultAction,
    PositionLifecycleStatus,
    SandboxOrderRequest,
    StrategyContract,
)


def _advice() -> ModeAdvice:
    return ModeAdvice(
        mode_id="sq02_downside_cont_review",
        strategy_contract_id="SQ02_DOWNSIDE_CONT_V0",
        why="candidate setup deserves Owner review",
        evidence=["closed_bar_setup_packet"],
        caveats=["design_only_no_runtime_candidate"],
        default_action=ModeDefaultAction.OBSERVE,
    )


def _contract() -> StrategyContract:
    return StrategyContract(
        strategy_contract_id="SQ02_DOWNSIDE_CONT_V0",
        strategy_name="SQ02 downside continuation sandbox skeleton",
        setup_condition_key="setup_present",
        invalidation_condition_key="setup_invalidated",
        direction=Direction.SHORT,
        required_feature_snapshot=["setup_present", "setup_invalidated"],
    )


def _feature_snapshot(
    *,
    setup_present: bool = True,
    setup_invalidated: bool = False,
    strategy_contract_id: str = "SQ02_DOWNSIDE_CONT_V0",
) -> FeatureSnapshot:
    return FeatureSnapshot(
        snapshot_id="snapshot-unit",
        strategy_contract_id=strategy_contract_id,
        feature_timestamp_ms=1000,
        conditions={
            "setup_present": setup_present,
            "setup_invalidated": setup_invalidated,
        },
    )


def _arm_decision(action: HumanArmAction = HumanArmAction.ARM) -> HumanArmDecision:
    return HumanArmDecision(
        decision=action,
        strategy_contract_id="SQ02_DOWNSIDE_CONT_V0",
        campaign_id="campaign-local-001",
        session_id="session-001",
        allowed_from_ms=1000,
        allowed_until_ms=2000,
        decided_by="owner",
        audit_provenance="local_unit_test",
        reason=f"test_{action.value}",
    )


def _state(status: CampaignLifecycleStatus = CampaignLifecycleStatus.OBSERVE) -> CampaignState:
    return CampaignState(
        campaign_id="campaign-local-001",
        capital_bucket=Decimal("1000"),
        status=status,
    )


def _caps() -> CampaignRiskCaps:
    return CampaignRiskCaps(
        risk_capital=Decimal("1000"),
        max_order_loss=Decimal("25"),
        max_campaign_loss=Decimal("100"),
        max_notional=Decimal("500"),
        max_leverage=3,
        profit_protect_threshold=Decimal("80"),
    )


def _order_request(
    *,
    max_loss: Decimal = Decimal("20"),
    notional: Decimal = Decimal("300"),
    leverage: int = 2,
) -> SandboxOrderRequest:
    return SandboxOrderRequest(
        symbol="ETH/USDT:USDT",
        max_loss=max_loss,
        notional=notional,
        leverage=leverage,
        feature_snapshot={"setup_present": True, "setup_invalidated": False},
    )


def _armed_state() -> tuple[CampaignState, HumanArmDecision]:
    decision = _arm_decision()
    state = apply_human_arm_decision(_advice(), decision, _state())
    return state, decision


def test_allow_path_builds_full_local_campaign_chain():
    state, decision = _armed_state()
    intent = build_trade_intent(
        _contract(),
        decision,
        state,
        _feature_snapshot(),
    )
    plan = build_risk_order_plan(intent, _order_request(), _caps(), state)
    receipt = simulate_execution_receipt(plan)
    position_state, campaign_state = apply_position_and_campaign_controls(
        receipt,
        state,
        _caps(),
    )

    assert _advice().llm_role == "explain_audit_suggest_only"
    assert _contract().disabled_by_default is True
    assert state.status == CampaignLifecycleStatus.ARMED
    assert intent.decision == CampaignDecision.ALLOW
    assert intent.no_exchange_side_effect is True
    assert plan.decision == CampaignDecision.ALLOW
    assert plan.planned_order is not None
    assert plan.protection_requirements == [
        "protective_stop_required",
        "position_lifecycle_monitor_required",
        "campaign_loss_lock_required",
    ]
    assert receipt.status == ExecutionReceiptStatus.SIMULATED_ACCEPTED
    assert receipt.simulated_order_id == "sim-campaign-local-001-session-001"
    assert position_state.status == PositionLifecycleStatus.OPEN_PROTECTED
    assert campaign_state.status == CampaignLifecycleStatus.ARMED


def test_contract_rejects_when_setup_absent_or_invalidated():
    state, decision = _armed_state()

    absent = build_trade_intent(
        _contract(),
        decision,
        state,
        _feature_snapshot(setup_present=False),
    )
    invalidated = build_trade_intent(
        _contract(),
        decision,
        state,
        _feature_snapshot(setup_invalidated=True),
    )

    assert absent.decision == CampaignDecision.REJECT
    assert absent.trigger_reason == "setup_condition_absent"
    assert invalidated.decision == CampaignDecision.REJECT
    assert invalidated.trigger_reason == "contract_invalidated"


def test_order_plan_rejects_owner_cap_breaches_before_execution():
    state, decision = _armed_state()
    intent = build_trade_intent(
        _contract(),
        decision,
        state,
        _feature_snapshot(),
    )

    plan = build_risk_order_plan(
        intent,
        _order_request(max_loss=Decimal("30"), notional=Decimal("700"), leverage=4),
        _caps(),
        state,
    )
    receipt = simulate_execution_receipt(plan)

    assert plan.decision == CampaignDecision.REJECT
    assert plan.planned_order is None
    assert plan.reasons == [
        "order_loss_cap_exceeded",
        "order_notional_cap_exceeded",
        "order_leverage_cap_exceeded",
    ]
    assert receipt.status == ExecutionReceiptStatus.BLOCKED
    assert receipt.simulated_order_id is None


def test_human_pause_blocks_intent_and_order_plan():
    pause_decision = _arm_decision(HumanArmAction.PAUSE)
    paused_state = apply_human_arm_decision(_advice(), pause_decision, _state())
    intent = build_trade_intent(
        _contract(),
        pause_decision,
        paused_state,
        _feature_snapshot(),
    )
    plan = build_risk_order_plan(intent, _order_request(), _caps(), paused_state)

    assert paused_state.status == CampaignLifecycleStatus.PAUSED
    assert intent.decision == CampaignDecision.REJECT
    assert intent.trigger_reason == "campaign_not_armed"
    assert plan.decision == CampaignDecision.REJECT
    assert plan.reasons == [
        "intent_rejected:campaign_not_armed",
        "campaign_paused",
        "unsupported_intent_action:none",
    ]


def test_position_protection_gap_hard_locks_campaign_and_future_plans():
    state, decision = _armed_state()
    intent = build_trade_intent(
        _contract(),
        decision,
        state,
        _feature_snapshot(),
    )
    plan = build_risk_order_plan(intent, _order_request(), _caps(), state)
    receipt = simulate_execution_receipt(plan)

    position_state, locked_state = apply_position_and_campaign_controls(
        receipt,
        state,
        _caps(),
        protection_missing=True,
    )
    future_plan = build_risk_order_plan(intent, _order_request(), _caps(), locked_state)

    assert position_state.status == PositionLifecycleStatus.CLOSE_REQUIRED
    assert position_state.hard_lock_required is True
    assert locked_state.status == CampaignLifecycleStatus.HARD_LOCKED
    assert locked_state.hard_lock_reason == "position_protection_missing"
    assert future_plan.decision == CampaignDecision.REJECT
    assert "campaign_hard_locked" in future_plan.reasons


def test_campaign_loss_lock_hard_locks_lifecycle():
    state, decision = _armed_state()
    intent = build_trade_intent(
        _contract(),
        decision,
        state,
        _feature_snapshot(),
    )
    plan = build_risk_order_plan(intent, _order_request(), _caps(), state)
    receipt = simulate_execution_receipt(plan)

    position_state, locked_state = apply_position_and_campaign_controls(
        receipt,
        state,
        _caps(),
        realized_pnl_delta=Decimal("-101"),
    )

    assert position_state.status == PositionLifecycleStatus.HARD_LOCKED
    assert position_state.reduce_or_close_required is True
    assert locked_state.loss_lock is True
    assert locked_state.hard_lock_reason == "campaign_loss_cap_reached"


def test_profit_protect_sets_reduce_requirement_without_withdrawal_instruction():
    state, decision = _armed_state()
    intent = build_trade_intent(
        _contract(),
        decision,
        state,
        _feature_snapshot(),
    )
    plan = build_risk_order_plan(intent, _order_request(), _caps(), state)
    receipt = simulate_execution_receipt(plan)

    position_state, protected_state = apply_position_and_campaign_controls(
        receipt,
        state,
        _caps(),
        realized_pnl_delta=Decimal("90"),
    )

    assert position_state.status == PositionLifecycleStatus.REDUCE_REQUIRED
    assert position_state.reduce_or_close_required is True
    assert protected_state.profit_protect_active is True
    assert not hasattr(protected_state, "withdrawal_pending")


def test_sandbox_runner_is_disabled_by_default():
    with pytest.raises(PersonalCampaignSandboxDisabled, match="disabled by default"):
        run_campaign_sandbox_trace(
            mode_advice=_advice(),
            human_arm_decision=_arm_decision(),
            strategy_contract=_contract(),
            initial_campaign_state=_state(),
            caps=_caps(),
            order_request=_order_request(),
            feature_snapshot=_feature_snapshot(),
        )


def test_enabled_sandbox_runner_returns_serializable_trace_with_no_side_effects():
    trace = run_campaign_sandbox_trace(
        settings=CampaignSandboxSettings(enabled=True, scenario_id="unit_allow_profit"),
        mode_advice=_advice(),
        human_arm_decision=_arm_decision(),
        strategy_contract=_contract(),
        initial_campaign_state=_state(),
        caps=_caps(),
        order_request=_order_request(),
        feature_snapshot=_feature_snapshot(),
        realized_pnl_delta=Decimal("90"),
    )
    dumped = trace.model_dump(mode="json")

    assert dumped["settings"] == {
        "enabled": True,
        "scenario_id": "unit_allow_profit",
        "runtime_effect": "none",
        "trading_permission_effect": "none",
        "external_side_effects_allowed": False,
    }
    assert trace.trade_intent.decision == CampaignDecision.ALLOW
    assert trace.risk_order_plan.decision == CampaignDecision.ALLOW
    assert trace.execution_receipt.status == ExecutionReceiptStatus.SIMULATED_ACCEPTED
    assert trace.position_lifecycle_state.status == PositionLifecycleStatus.REDUCE_REQUIRED
    assert trace.campaign_state.profit_protect_active is True
    assert "no_exchange_api" in trace.safety_assertions
    assert "no_transfer_or_withdrawal_path" in trace.safety_assertions
    assert "owner_handles_withdrawal_outside_system" in trace.safety_assertions


def test_sandbox_settings_reject_external_side_effects():
    with pytest.raises(ValueError, match="forbids external side effects"):
        CampaignSandboxSettings(enabled=True, external_side_effects_allowed=True)


def test_feature_snapshot_rejects_llm_trade_decision_use():
    with pytest.raises(ValueError, match="must not use LLM trade decisions"):
        FeatureSnapshot(
            snapshot_id="snapshot-unsafe",
            strategy_contract_id="SQ02_DOWNSIDE_CONT_V0",
            feature_timestamp_ms=1000,
            conditions={"setup_present": True, "setup_invalidated": False},
            llm_trade_decision_used=True,
        )


def test_feature_snapshot_strategy_mismatch_rejects_trade_intent():
    state, decision = _armed_state()

    intent = build_trade_intent(
        _contract(),
        decision,
        state,
        _feature_snapshot(strategy_contract_id="OTHER_CONTRACT"),
    )

    assert intent.decision == CampaignDecision.REJECT
    assert intent.trigger_reason == "feature_snapshot_strategy_mismatch"


def test_sandbox_scenario_catalog_covers_minimum_verification_matrix():
    catalog = build_campaign_sandbox_scenario_catalog()

    assert set(catalog) == {
        "allow_open_protected",
        "reject_contract_invalidated",
        "reject_order_caps",
        "pause_blocks_session",
        "hard_lock_missing_protection",
        "profit_protect_reduce",
    }
    assert all(scenario.settings.enabled is True for scenario in catalog.values())
    assert all(
        scenario.settings.runtime_effect == "none"
        and scenario.settings.trading_permission_effect == "none"
        and scenario.settings.external_side_effects_allowed is False
        for scenario in catalog.values()
    )


def test_sandbox_scenario_catalog_expected_outcomes_are_stable():
    traces = {
        scenario_id: run_campaign_sandbox_scenario(scenario)
        for scenario_id, scenario in build_campaign_sandbox_scenario_catalog().items()
    }

    assert traces["allow_open_protected"].trade_intent.decision == CampaignDecision.ALLOW
    assert traces["allow_open_protected"].risk_order_plan.decision == CampaignDecision.ALLOW
    assert (
        traces["allow_open_protected"].position_lifecycle_state.status
        == PositionLifecycleStatus.OPEN_PROTECTED
    )

    invalidated = traces["reject_contract_invalidated"]
    assert invalidated.trade_intent.decision == CampaignDecision.REJECT
    assert invalidated.trade_intent.trigger_reason == "contract_invalidated"
    assert invalidated.risk_order_plan.decision == CampaignDecision.REJECT
    assert invalidated.execution_receipt.status == ExecutionReceiptStatus.BLOCKED

    order_caps = traces["reject_order_caps"]
    assert order_caps.trade_intent.decision == CampaignDecision.ALLOW
    assert order_caps.risk_order_plan.decision == CampaignDecision.REJECT
    assert order_caps.risk_order_plan.reasons == [
        "order_loss_cap_exceeded",
        "order_notional_cap_exceeded",
        "order_leverage_cap_exceeded",
    ]

    paused = traces["pause_blocks_session"]
    assert paused.campaign_state.status == CampaignLifecycleStatus.PAUSED
    assert paused.trade_intent.decision == CampaignDecision.REJECT
    assert "campaign_paused" in paused.risk_order_plan.reasons

    hard_locked = traces["hard_lock_missing_protection"]
    assert hard_locked.campaign_state.status == CampaignLifecycleStatus.HARD_LOCKED
    assert hard_locked.position_lifecycle_state.status == PositionLifecycleStatus.CLOSE_REQUIRED
    assert hard_locked.position_lifecycle_state.hard_lock_required is True

    profit = traces["profit_protect_reduce"]
    assert profit.campaign_state.profit_protect_active is True
    assert profit.position_lifecycle_state.status == PositionLifecycleStatus.REDUCE_REQUIRED
    assert not hasattr(profit, "withdrawal_instruction")

    for trace in traces.values():
        dumped = trace.model_dump(mode="json")
        assert dumped["settings"]["runtime_effect"] == "none"
        assert dumped["settings"]["trading_permission_effect"] == "none"
        assert dumped["settings"]["external_side_effects_allowed"] is False
        assert "no_exchange_api" in dumped["safety_assertions"]
        assert "no_order_side_effect" in dumped["safety_assertions"]


def test_sandbox_trace_invariants_pass_for_all_catalog_scenarios():
    for scenario in build_campaign_sandbox_scenario_catalog().values():
        trace = run_campaign_sandbox_scenario(scenario)
        report = evaluate_campaign_sandbox_trace_invariants(trace)

        assert report.status == CampaignInvariantStatus.PASS
        assert report.scenario_id == scenario.scenario_id
        assert report.violations == []
        assert "runtime_effect_none" in report.checks_passed
        assert "trading_permission_effect_none" in report.checks_passed
        assert "trace_safety_assertions_complete" in report.checks_passed


def test_sandbox_trace_invariants_fail_when_contract_is_not_disabled():
    trace = run_campaign_sandbox_scenario(
        build_campaign_sandbox_scenario_catalog()["allow_open_protected"]
    )
    unsafe_trace = trace.model_copy(
        update={
            "strategy_contract": trace.strategy_contract.model_copy(
                update={"disabled_by_default": False}
            )
        }
    )

    report = evaluate_campaign_sandbox_trace_invariants(unsafe_trace)

    assert report.status == CampaignInvariantStatus.FAIL
    assert report.violations == ["strategy_contract_not_disabled_by_default"]


def test_sandbox_trace_invariants_fail_when_profit_protect_loses_reduce_requirement():
    trace = run_campaign_sandbox_scenario(
        build_campaign_sandbox_scenario_catalog()["profit_protect_reduce"]
    )
    unsafe_trace = trace.model_copy(
        update={
            "position_lifecycle_state": trace.position_lifecycle_state.model_copy(
                update={"reduce_or_close_required": False}
            )
        }
    )

    report = evaluate_campaign_sandbox_trace_invariants(unsafe_trace)

    assert report.status == CampaignInvariantStatus.FAIL
    assert report.violations == ["profit_protect_without_reduce_or_close_requirement"]
