"""Local-only Personal Leveraged Campaign sandbox.

The functions in this module are deterministic local simulations. They do not
read secrets, call exchange APIs, submit/cancel orders, or move funds.
"""

from __future__ import annotations

from decimal import Decimal

from src.domain.models import Direction
from src.domain.personal_campaign import (
    CampaignDecision,
    CampaignInvariantStatus,
    CampaignLifecycleStatus,
    CampaignRiskCaps,
    CampaignSandboxScenario,
    CampaignSandboxSettings,
    CampaignSandboxTrace,
    CampaignState,
    CampaignTraceInvariantReport,
    ExecutionReceipt,
    ExecutionReceiptStatus,
    FeatureSnapshot,
    HumanArmAction,
    HumanArmDecision,
    ModeAdvice,
    ModeDefaultAction,
    PlannedOrder,
    PositionLifecycleState,
    PositionLifecycleStatus,
    PositionProtectionStatus,
    RiskOrderPlan,
    SandboxOrderRequest,
    StrategyContract,
    TradeIntent,
    TradeIntentAction,
)


class PersonalCampaignSandboxDisabled(RuntimeError):
    """Raised when the local sandbox runner is invoked without explicit enablement."""


def apply_human_arm_decision(
    advice: ModeAdvice,
    decision: HumanArmDecision,
    current_state: CampaignState,
) -> CampaignState:
    """Apply Owner arm/pause/reject authority to campaign state."""

    if decision.strategy_contract_id != advice.strategy_contract_id:
        return current_state.model_copy(
            update={
                "status": CampaignLifecycleStatus.PAUSED,
                "active_strategy_contract_id": None,
                "active_session_id": None,
                "invariant_checks": [
                    *current_state.invariant_checks,
                    "reject:strategy_contract_mismatch",
                ],
            }
        )

    if decision.decision == HumanArmAction.ARM:
        return current_state.model_copy(
            update={
                "status": CampaignLifecycleStatus.ARMED,
                "active_strategy_contract_id": decision.strategy_contract_id,
                "active_session_id": decision.session_id,
                "invariant_checks": [
                    *current_state.invariant_checks,
                    f"allow:human_arm:{decision.audit_provenance}",
                ],
            }
        )

    status = CampaignLifecycleStatus.PAUSED
    reason = f"pause:human_{decision.decision.value}:{decision.reason}"
    return current_state.model_copy(
        update={
            "status": status,
            "active_strategy_contract_id": None,
            "active_session_id": None,
            "invariant_checks": [*current_state.invariant_checks, reason],
        }
    )


def build_trade_intent(
    contract: StrategyContract,
    decision: HumanArmDecision,
    campaign_state: CampaignState,
    feature_snapshot: FeatureSnapshot,
) -> TradeIntent:
    """Evaluate deterministic strategy-contract conditions inside an armed session."""

    base = {
        "strategy_contract_id": contract.strategy_contract_id,
        "campaign_id": campaign_state.campaign_id,
        "session_id": decision.session_id,
    }
    if campaign_state.status != CampaignLifecycleStatus.ARMED:
        return TradeIntent(
            **base,
            decision=CampaignDecision.REJECT,
            trigger_reason="campaign_not_armed",
            invalidation_reason=f"campaign_status:{campaign_state.status.value}",
        )
    if campaign_state.active_strategy_contract_id != contract.strategy_contract_id:
        return TradeIntent(
            **base,
            decision=CampaignDecision.REJECT,
            trigger_reason="strategy_not_active_for_campaign",
            invalidation_reason="active_strategy_contract_mismatch",
        )
    if decision.decision != HumanArmAction.ARM:
        return TradeIntent(
            **base,
            decision=CampaignDecision.REJECT,
            trigger_reason="human_gate_not_armed",
            invalidation_reason=f"human_decision:{decision.decision.value}",
        )
    if feature_snapshot.strategy_contract_id != contract.strategy_contract_id:
        return TradeIntent(
            **base,
            decision=CampaignDecision.REJECT,
            trigger_reason="feature_snapshot_strategy_mismatch",
            invalidation_reason=feature_snapshot.strategy_contract_id,
        )
    conditions = feature_snapshot.conditions
    missing_features = [
        key for key in contract.required_feature_snapshot if key not in conditions
    ]
    if missing_features:
        return TradeIntent(
            **base,
            decision=CampaignDecision.REJECT,
            trigger_reason="required_feature_missing",
            invalidation_reason="missing:" + ",".join(missing_features),
        )
    if conditions.get(contract.invalidation_condition_key, False):
        return TradeIntent(
            **base,
            decision=CampaignDecision.REJECT,
            trigger_reason="contract_invalidated",
            invalidation_reason=contract.invalidation_condition_key,
        )
    if not conditions.get(contract.setup_condition_key, False):
        return TradeIntent(
            **base,
            decision=CampaignDecision.REJECT,
            trigger_reason="setup_condition_absent",
            invalidation_reason=contract.setup_condition_key,
        )

    return TradeIntent(
        **base,
        decision=CampaignDecision.ALLOW,
        direction=contract.direction,
        action=contract.entry_action,
        trigger_reason=contract.setup_condition_key,
        evidence_text="deterministic_contract_conditions_satisfied",
    )


def build_risk_order_plan(
    intent: TradeIntent,
    request: SandboxOrderRequest,
    caps: CampaignRiskCaps,
    campaign_state: CampaignState,
) -> RiskOrderPlan:
    """Enforce order, position, and campaign caps before a simulated plan exists."""

    reasons: list[str] = []
    if intent.decision != CampaignDecision.ALLOW:
        reasons.append(f"intent_rejected:{intent.trigger_reason}")
    if campaign_state.status == CampaignLifecycleStatus.HARD_LOCKED:
        reasons.append("campaign_hard_locked")
    if campaign_state.status == CampaignLifecycleStatus.PAUSED:
        reasons.append("campaign_paused")
    if campaign_state.loss_lock:
        reasons.append("campaign_loss_lock")
    if intent.action != TradeIntentAction.ENTER:
        reasons.append(f"unsupported_intent_action:{intent.action.value}")
    if request.max_loss > caps.max_order_loss:
        reasons.append("order_loss_cap_exceeded")
    if request.notional > caps.max_notional:
        reasons.append("order_notional_cap_exceeded")
    if request.leverage > caps.max_leverage:
        reasons.append("order_leverage_cap_exceeded")
    if campaign_state.total_pnl <= -caps.max_campaign_loss:
        reasons.append("campaign_loss_cap_reached")

    if reasons:
        return RiskOrderPlan(
            decision=CampaignDecision.REJECT,
            campaign_id=intent.campaign_id,
            session_id=intent.session_id,
            strategy_contract_id=intent.strategy_contract_id,
            reasons=reasons,
            owner_fixed_caps_used=caps,
        )

    planned_order = PlannedOrder(
        symbol=request.symbol,
        side=intent.direction,
        notional=request.notional,
        leverage=request.leverage,
        max_loss=request.max_loss,
    )
    return RiskOrderPlan(
        decision=CampaignDecision.ALLOW,
        campaign_id=intent.campaign_id,
        session_id=intent.session_id,
        strategy_contract_id=intent.strategy_contract_id,
        reasons=["allow:order_position_campaign_caps_passed"],
        owner_fixed_caps_used=caps,
        planned_order=planned_order,
        protection_requirements=[
            "protective_stop_required",
            "position_lifecycle_monitor_required",
            "campaign_loss_lock_required",
        ],
    )


def simulate_execution_receipt(plan: RiskOrderPlan) -> ExecutionReceipt:
    """Create a local simulated receipt; no order is submitted anywhere."""

    if plan.decision != CampaignDecision.ALLOW:
        return ExecutionReceipt(
            status=ExecutionReceiptStatus.BLOCKED,
            campaign_id=plan.campaign_id,
            session_id=plan.session_id,
            strategy_contract_id=plan.strategy_contract_id,
            acknowledgement="blocked_before_execution",
            lifecycle_status=PositionLifecycleStatus.NO_POSITION,
        )

    return ExecutionReceipt(
        status=ExecutionReceiptStatus.SIMULATED_ACCEPTED,
        campaign_id=plan.campaign_id,
        session_id=plan.session_id,
        strategy_contract_id=plan.strategy_contract_id,
        simulated_order_id=f"sim-{plan.campaign_id}-{plan.session_id}",
        acknowledgement="local_sandbox_acceptance_only",
        reconciliation_reference="local_sandbox_replay_reference",
        protection_status=PositionProtectionStatus.PROTECTED,
        lifecycle_status=PositionLifecycleStatus.OPEN_PROTECTED,
    )


def apply_position_and_campaign_controls(
    receipt: ExecutionReceipt,
    campaign_state: CampaignState,
    caps: CampaignRiskCaps,
    *,
    realized_pnl_delta: Decimal = Decimal("0"),
    unrealized_pnl: Decimal = Decimal("0"),
    protection_missing: bool = False,
) -> tuple[PositionLifecycleState, CampaignState]:
    """Enforce position lifecycle and campaign lifecycle controls."""

    realized_pnl = campaign_state.realized_pnl + realized_pnl_delta
    next_state = campaign_state.model_copy(
        update={
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
        }
    )

    reasons: list[str] = []
    if receipt.status == ExecutionReceiptStatus.BLOCKED:
        reasons.append("receipt_blocked_no_position")
        return (
            PositionLifecycleState(
                campaign_id=receipt.campaign_id,
                session_id=receipt.session_id,
                status=PositionLifecycleStatus.NO_POSITION,
                protection_state=PositionProtectionStatus.NONE,
                reasons=reasons,
            ),
            next_state,
        )

    if protection_missing:
        reasons.append("position_protection_missing")
        locked = next_state.model_copy(
            update={
                "status": CampaignLifecycleStatus.HARD_LOCKED,
                "hard_lock_reason": "position_protection_missing",
                "invariant_checks": [
                    *next_state.invariant_checks,
                    "hard-lock:position_protection_missing",
                ],
            }
        )
        return (
            PositionLifecycleState(
                campaign_id=receipt.campaign_id,
                session_id=receipt.session_id,
                status=PositionLifecycleStatus.CLOSE_REQUIRED,
                protection_state=PositionProtectionStatus.PROTECTION_MISSING,
                reduce_or_close_required=True,
                hard_lock_required=True,
                reasons=reasons,
            ),
            locked,
        )

    if next_state.total_pnl <= -caps.max_campaign_loss:
        reasons.append("campaign_loss_cap_reached")
        locked = next_state.model_copy(
            update={
                "status": CampaignLifecycleStatus.HARD_LOCKED,
                "loss_lock": True,
                "hard_lock_reason": "campaign_loss_cap_reached",
                "invariant_checks": [
                    *next_state.invariant_checks,
                    "hard-lock:campaign_loss_cap_reached",
                ],
            }
        )
        return (
            PositionLifecycleState(
                campaign_id=receipt.campaign_id,
                session_id=receipt.session_id,
                status=PositionLifecycleStatus.HARD_LOCKED,
                protection_state=PositionProtectionStatus.PROTECTED,
                reduce_or_close_required=True,
                hard_lock_required=True,
                reasons=reasons,
            ),
            locked,
        )

    if next_state.total_pnl >= caps.profit_protect_threshold:
        reasons.append("profit_protect_threshold_reached")
        protected = next_state.model_copy(
            update={
                "profit_protect_active": True,
                "invariant_checks": [
                    *next_state.invariant_checks,
                    "profit-protect:threshold_reached",
                ],
            }
        )
        return (
            PositionLifecycleState(
                campaign_id=receipt.campaign_id,
                session_id=receipt.session_id,
                status=PositionLifecycleStatus.REDUCE_REQUIRED,
                protection_state=PositionProtectionStatus.PROTECTED,
                reduce_or_close_required=True,
                reasons=reasons,
            ),
            protected,
        )

    reasons.append("allow:position_open_protected")
    return (
        PositionLifecycleState(
            campaign_id=receipt.campaign_id,
            session_id=receipt.session_id,
            status=PositionLifecycleStatus.OPEN_PROTECTED,
            protection_state=PositionProtectionStatus.PROTECTED,
            reasons=reasons,
        ),
        next_state,
    )


def run_campaign_sandbox_trace(
    *,
    settings: CampaignSandboxSettings | None = None,
    mode_advice: ModeAdvice,
    human_arm_decision: HumanArmDecision,
    strategy_contract: StrategyContract,
    initial_campaign_state: CampaignState,
    caps: CampaignRiskCaps,
    order_request: SandboxOrderRequest,
    feature_snapshot: FeatureSnapshot,
    realized_pnl_delta: Decimal = Decimal("0"),
    unrealized_pnl: Decimal = Decimal("0"),
    protection_missing: bool = False,
) -> CampaignSandboxTrace:
    """Run the full local sandbox chain and return an auditable trace."""

    if settings is None:
        settings = CampaignSandboxSettings()
    if not settings.enabled:
        raise PersonalCampaignSandboxDisabled(
            "personal campaign sandbox is disabled by default; pass enabled=True for local tests"
        )
    if not strategy_contract.disabled_by_default:
        raise ValueError("sandbox strategy contracts must remain disabled_by_default")

    armed_state = apply_human_arm_decision(
        mode_advice,
        human_arm_decision,
        initial_campaign_state,
    )
    trade_intent = build_trade_intent(
        strategy_contract,
        human_arm_decision,
        armed_state,
        feature_snapshot,
    )
    risk_order_plan = build_risk_order_plan(
        trade_intent,
        order_request,
        caps,
        armed_state,
    )
    execution_receipt = simulate_execution_receipt(risk_order_plan)
    position_lifecycle_state, campaign_state = apply_position_and_campaign_controls(
        execution_receipt,
        armed_state,
        caps,
        realized_pnl_delta=realized_pnl_delta,
        unrealized_pnl=unrealized_pnl,
        protection_missing=protection_missing,
    )

    return CampaignSandboxTrace(
        settings=settings,
        mode_advice=mode_advice,
        human_arm_decision=human_arm_decision,
        strategy_contract=strategy_contract,
        trade_intent=trade_intent,
        risk_order_plan=risk_order_plan,
        execution_receipt=execution_receipt,
        position_lifecycle_state=position_lifecycle_state,
        campaign_state=campaign_state,
    )


def run_campaign_sandbox_scenario(
    scenario: CampaignSandboxScenario,
) -> CampaignSandboxTrace:
    """Run a named local scenario through the same guarded trace path."""

    return run_campaign_sandbox_trace(
        settings=scenario.settings,
        mode_advice=scenario.mode_advice,
        human_arm_decision=scenario.human_arm_decision,
        strategy_contract=scenario.strategy_contract,
        initial_campaign_state=scenario.initial_campaign_state,
        caps=scenario.caps,
        order_request=scenario.order_request,
        feature_snapshot=scenario.feature_snapshot,
        realized_pnl_delta=scenario.realized_pnl_delta,
        unrealized_pnl=scenario.unrealized_pnl,
        protection_missing=scenario.protection_missing,
    )


def build_campaign_sandbox_scenario_catalog() -> dict[str, CampaignSandboxScenario]:
    """Build deterministic local scenarios for minimum campaign-chain verification."""

    strategy_contract_id = "SQ02_DOWNSIDE_CONT_V0"
    campaign_id = "campaign-local-001"

    def settings(scenario_id: str) -> CampaignSandboxSettings:
        return CampaignSandboxSettings(enabled=True, scenario_id=scenario_id)

    def advice() -> ModeAdvice:
        return ModeAdvice(
            mode_id="sq02_downside_cont_review",
            strategy_contract_id=strategy_contract_id,
            why="candidate setup deserves Owner review",
            evidence=["closed_bar_setup_packet"],
            caveats=["design_only_no_runtime_candidate"],
            default_action=ModeDefaultAction.OBSERVE,
        )

    def decision(action: HumanArmAction, session_id: str) -> HumanArmDecision:
        return HumanArmDecision(
            decision=action,
            strategy_contract_id=strategy_contract_id,
            campaign_id=campaign_id,
            session_id=session_id,
            allowed_from_ms=1000,
            allowed_until_ms=2000,
            decided_by="owner",
            audit_provenance=f"catalog:{session_id}",
            reason=f"catalog_{action.value}",
        )

    def contract() -> StrategyContract:
        return StrategyContract(
            strategy_contract_id=strategy_contract_id,
            strategy_name="SQ02 downside continuation sandbox skeleton",
            setup_condition_key="setup_present",
            invalidation_condition_key="setup_invalidated",
            direction=Direction.SHORT,
            required_feature_snapshot=["setup_present", "setup_invalidated"],
        )

    def feature_snapshot(
        *,
        snapshot_id: str,
        setup_present: bool,
        setup_invalidated: bool,
    ) -> FeatureSnapshot:
        return FeatureSnapshot(
            snapshot_id=snapshot_id,
            strategy_contract_id=strategy_contract_id,
            feature_timestamp_ms=1000,
            conditions={
                "setup_present": setup_present,
                "setup_invalidated": setup_invalidated,
            },
        )

    def state() -> CampaignState:
        return CampaignState(
            campaign_id=campaign_id,
            capital_bucket=Decimal("1000"),
        )

    def caps() -> CampaignRiskCaps:
        return CampaignRiskCaps(
            risk_capital=Decimal("1000"),
            max_order_loss=Decimal("25"),
            max_campaign_loss=Decimal("100"),
            max_notional=Decimal("500"),
            max_leverage=3,
            profit_protect_threshold=Decimal("80"),
        )

    def order_request(
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

    return {
        "allow_open_protected": CampaignSandboxScenario(
            scenario_id="allow_open_protected",
            description="armed session allows a capped order plan and protected simulated position",
            settings=settings("allow_open_protected"),
            mode_advice=advice(),
            human_arm_decision=decision(HumanArmAction.ARM, "session-allow"),
            strategy_contract=contract(),
            initial_campaign_state=state(),
            caps=caps(),
            order_request=order_request(),
            feature_snapshot=feature_snapshot(
                snapshot_id="snapshot-allow",
                setup_present=True,
                setup_invalidated=False,
            ),
        ),
        "reject_contract_invalidated": CampaignSandboxScenario(
            scenario_id="reject_contract_invalidated",
            description="contract invalidation rejects intent before order planning",
            settings=settings("reject_contract_invalidated"),
            mode_advice=advice(),
            human_arm_decision=decision(HumanArmAction.ARM, "session-invalidated"),
            strategy_contract=contract(),
            initial_campaign_state=state(),
            caps=caps(),
            order_request=order_request(),
            feature_snapshot=feature_snapshot(
                snapshot_id="snapshot-invalidated",
                setup_present=True,
                setup_invalidated=True,
            ),
        ),
        "reject_order_caps": CampaignSandboxScenario(
            scenario_id="reject_order_caps",
            description="owner-fixed order caps reject the plan before simulated execution",
            settings=settings("reject_order_caps"),
            mode_advice=advice(),
            human_arm_decision=decision(HumanArmAction.ARM, "session-order-caps"),
            strategy_contract=contract(),
            initial_campaign_state=state(),
            caps=caps(),
            order_request=order_request(
                max_loss=Decimal("30"),
                notional=Decimal("700"),
                leverage=4,
            ),
            feature_snapshot=feature_snapshot(
                snapshot_id="snapshot-order-caps",
                setup_present=True,
                setup_invalidated=False,
            ),
        ),
        "pause_blocks_session": CampaignSandboxScenario(
            scenario_id="pause_blocks_session",
            description="Owner pause blocks intent and order plan without per-order review",
            settings=settings("pause_blocks_session"),
            mode_advice=advice(),
            human_arm_decision=decision(HumanArmAction.PAUSE, "session-pause"),
            strategy_contract=contract(),
            initial_campaign_state=state(),
            caps=caps(),
            order_request=order_request(),
            feature_snapshot=feature_snapshot(
                snapshot_id="snapshot-pause",
                setup_present=True,
                setup_invalidated=False,
            ),
        ),
        "hard_lock_missing_protection": CampaignSandboxScenario(
            scenario_id="hard_lock_missing_protection",
            description="missing protection forces close requirement and campaign hard-lock",
            settings=settings("hard_lock_missing_protection"),
            mode_advice=advice(),
            human_arm_decision=decision(HumanArmAction.ARM, "session-hard-lock"),
            strategy_contract=contract(),
            initial_campaign_state=state(),
            caps=caps(),
            order_request=order_request(),
            feature_snapshot=feature_snapshot(
                snapshot_id="snapshot-hard-lock",
                setup_present=True,
                setup_invalidated=False,
            ),
            protection_missing=True,
        ),
        "profit_protect_reduce": CampaignSandboxScenario(
            scenario_id="profit_protect_reduce",
            description="profit threshold activates reduction requirement; owner handles withdrawal outside system",
            settings=settings("profit_protect_reduce"),
            mode_advice=advice(),
            human_arm_decision=decision(HumanArmAction.ARM, "session-profit"),
            strategy_contract=contract(),
            initial_campaign_state=state(),
            caps=caps(),
            order_request=order_request(),
            feature_snapshot=feature_snapshot(
                snapshot_id="snapshot-profit",
                setup_present=True,
                setup_invalidated=False,
            ),
            realized_pnl_delta=Decimal("90"),
        ),
    }


def evaluate_campaign_sandbox_trace_invariants(
    trace: CampaignSandboxTrace,
) -> CampaignTraceInvariantReport:
    """Evaluate local safety invariants for a completed sandbox trace."""

    passed: list[str] = []
    violations: list[str] = []

    def require(condition: bool, passed_key: str, violation_key: str) -> None:
        if condition:
            passed.append(passed_key)
        else:
            violations.append(violation_key)

    require(
        trace.settings.runtime_effect == "none",
        "runtime_effect_none",
        "runtime_effect_not_none",
    )
    require(
        trace.settings.trading_permission_effect == "none",
        "trading_permission_effect_none",
        "trading_permission_effect_not_none",
    )
    require(
        trace.settings.external_side_effects_allowed is False,
        "external_side_effects_forbidden",
        "external_side_effects_allowed",
    )
    require(
        trace.strategy_contract.disabled_by_default is True,
        "strategy_contract_disabled_by_default",
        "strategy_contract_not_disabled_by_default",
    )
    require(
        trace.mode_advice.llm_role == "explain_audit_suggest_only",
        "llm_role_explain_audit_suggest_only",
        "llm_role_exceeds_allowed_scope",
    )
    require(
        trace.trade_intent.no_exchange_side_effect is True,
        "trade_intent_has_no_exchange_side_effect",
        "trade_intent_allows_exchange_side_effect",
    )

    if trace.risk_order_plan.decision == CampaignDecision.ALLOW:
        required_protections = {
            "protective_stop_required",
            "position_lifecycle_monitor_required",
            "campaign_loss_lock_required",
        }
        require(
            required_protections.issubset(set(trace.risk_order_plan.protection_requirements)),
            "allowed_plan_has_required_protections",
            "allowed_plan_missing_required_protections",
        )
        require(
            trace.risk_order_plan.planned_order is not None,
            "allowed_plan_has_simulated_order",
            "allowed_plan_missing_simulated_order",
        )
    else:
        require(
            trace.risk_order_plan.planned_order is None,
            "rejected_plan_has_no_simulated_order",
            "rejected_plan_retains_simulated_order",
        )

    if trace.position_lifecycle_state.hard_lock_required:
        require(
            trace.campaign_state.status == CampaignLifecycleStatus.HARD_LOCKED,
            "hard_lock_requirement_locks_campaign",
            "hard_lock_requirement_without_campaign_lock",
        )

    require(
        trace.campaign_state.profit_protect_active is False
        or trace.position_lifecycle_state.reduce_or_close_required is True,
        "profit_protect_requires_reduce_or_close",
        "profit_protect_without_reduce_or_close_requirement",
    )

    expected_safety_assertions = {
        "local_only",
        "no_exchange_api",
        "no_real_account",
        "no_order_side_effect",
        "no_transfer_or_withdrawal_path",
        "owner_handles_withdrawal_outside_system",
        "llm_explain_audit_suggest_only",
    }
    require(
        expected_safety_assertions.issubset(set(trace.safety_assertions)),
        "trace_safety_assertions_complete",
        "trace_safety_assertions_incomplete",
    )

    status = CampaignInvariantStatus.PASS
    if violations:
        status = CampaignInvariantStatus.FAIL
    return CampaignTraceInvariantReport(
        status=status,
        scenario_id=trace.settings.scenario_id,
        checks_passed=passed,
        violations=violations,
    )
