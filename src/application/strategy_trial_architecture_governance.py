"""Lightweight strategy-trial architecture governance models.

The models in this module are review and authorization-boundary artifacts only.
They do not create execution intents, grant execution permission, place orders,
start runtime, or call exchange APIs.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.application.strategy_trial_controlled_testnet_carrier import (
    StrategyTrialControlledTestnetCarrier,
    mi001_bnb_long_testnet_carrier,
)


CarrierGovernanceClassification = Literal[
    "generic-ready",
    "carrier-specific by design",
    "should be generalized now",
    "should remain BNB-specific for this sprint",
    "technical debt / later",
]


class StrategyTrialArchitectureClassification(BaseModel):
    concept: str
    current_item: str
    classification: CarrierGovernanceClassification
    decision: str


class StrategyTrialCarrierView(BaseModel):
    model_config = ConfigDict(frozen=True)

    carrier_id: str
    strategy_family: str
    strategy_id: str
    candidate_id: str
    symbol: str
    runtime_symbol: str
    side: Literal["long", "short"]
    execution_mode: Literal["owner_confirm_each_entry"]
    quantity: Decimal = Field(gt=Decimal("0"))
    max_notional: Decimal = Field(gt=Decimal("0"))
    leverage: Decimal = Field(gt=Decimal("0"))
    max_leverage_allowed: Decimal = Field(gt=Decimal("0"))
    protection_plan_type: Literal["single_tp_plus_sl"]
    sizing_mode: Literal["fixed_quantity", "notional_derived"] = "fixed_quantity"
    target_notional_usdt: Decimal | None = None
    strategy_family_order_authority: Literal[False] = False
    carrier_is_order_authority: Literal[False] = False
    live_ready: Literal[False] = False
    auto_execution_ready: Literal[False] = False


class StrategyTrialRiskWarning(BaseModel):
    warning_id: str
    severity: Literal["info", "warning"] = "warning"
    owner_ack_required: bool = True
    acknowledged: bool = False
    blocks_after_ack: Literal[False] = False
    description: str


class StrategyTrialHardBlocker(BaseModel):
    blocker_id: str
    active: bool
    blocks_after_ack: Literal[True] = True
    description: str
    source: str


class OwnerReviewPacket(BaseModel):
    packet_id: str
    carrier: StrategyTrialCarrierView
    testnet_rehearsal_result: Literal["completed_with_valid_protection"]
    testnet_rehearsal_evidence: dict[str, str | bool]
    strategy_warnings: list[StrategyTrialRiskWarning]
    hard_safety_blockers: list[StrategyTrialHardBlocker]
    next_owner_action: Literal["explicit_owner_live_authorization_required"]
    live_authorization_effect: str
    no_execution_permission: Literal[True] = True
    no_order_permission: Literal[True] = True
    no_runtime_start: Literal[True] = True
    live_ready: Literal[False] = False


class BoundedLiveTrialAuthorizationDraft(BaseModel):
    authorization_id: str
    carrier_id: str
    strategy_family: str
    symbol: str
    side: Literal["long", "short"]
    max_notional: Decimal = Field(gt=Decimal("0"))
    quantity: Decimal = Field(gt=Decimal("0"))
    leverage: Decimal = Field(gt=Decimal("0"))
    protection_plan_type: Literal["single_tp_plus_sl"]
    single_use: Literal[True] = True
    expires_at: str
    owner_confirmed: bool = False
    pending_owner_live_authorization: bool = True
    warnings_acknowledged: bool = False
    consumed: Literal[False] = False
    live_ready: Literal[False] = False
    execution_permission_granted: Literal[False] = False
    order_permission_granted: Literal[False] = False
    auto_execution_ready: Literal[False] = False


class MinimalLiveTrialGateRequest(BaseModel):
    carrier_id: str
    symbol: str
    side: Literal["long", "short"]
    requested_notional: Decimal = Field(gt=Decimal("0"))
    protection_plan_type: str
    explicit_owner_live_authorization_exists: bool = False
    warnings_acknowledged: bool = False


class MinimalLiveTrialGateResult(BaseModel):
    can_execute_bounded_live_trial: bool
    final_state: Literal[
        "blocked_missing_owner_live_authorization",
        "blocked_strategy_warning_acknowledgement_required",
        "blocked_by_hard_safety_gate",
        "ready_for_bounded_live_trial_execution",
    ]
    hard_blockers: list[str] = Field(default_factory=list)
    acknowledgement_blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    live_ready: Literal[False] = False
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    execution_permission_granted: Literal[False] = False


class StrategyTrialArchitectureGovernanceResponse(BaseModel):
    generated_from: Literal["strategy_trial_architecture_governance_v1"] = (
        "strategy_trial_architecture_governance_v1"
    )
    final_state: Literal[
        "strategy_trial_architecture_governed",
        "strategy_trial_architecture_governance_blocked_with_explicit_hard_blockers",
    ]
    bnb_state: Literal["bnb_first_carrier_consolidated"]
    owner_review_packet: OwnerReviewPacket
    authorization_draft: BoundedLiveTrialAuthorizationDraft
    minimal_live_trial_gate: MinimalLiveTrialGateResult
    architecture_classification: list[StrategyTrialArchitectureClassification]
    generic_now: list[str]
    carrier_specific_by_design: list[str]
    technical_debt_later: list[str]
    not_live_ready_until_explicit_owner_live_authorization: Literal[True] = True
    not_auto_execution_ready: Literal[True] = True
    no_real_funds: Literal[True] = True
    non_permissions: dict[str, bool] = Field(default_factory=lambda: _non_permissions())


def build_bnb_strategy_trial_architecture_governance(
    *,
    warnings_acknowledged: bool = False,
    explicit_owner_live_authorization_exists: bool = False,
    request: MinimalLiveTrialGateRequest | None = None,
    active_hard_blockers: list[StrategyTrialHardBlocker] | None = None,
) -> StrategyTrialArchitectureGovernanceResponse:
    """Build the Owner-reviewable governance state for BNB as first carrier."""

    carrier = _carrier_view(mi001_bnb_long_testnet_carrier())
    warnings = _strategy_warnings(acknowledged=warnings_acknowledged)
    hard_blockers = list(active_hard_blockers or [])
    authorization = _authorization_draft(
        carrier,
        warnings_acknowledged=warnings_acknowledged,
        owner_confirmed=explicit_owner_live_authorization_exists,
    )
    gate_request = request or MinimalLiveTrialGateRequest(
        carrier_id=carrier.carrier_id,
        symbol=carrier.runtime_symbol,
        side=carrier.side,
        requested_notional=carrier.max_notional,
        protection_plan_type=carrier.protection_plan_type,
        explicit_owner_live_authorization_exists=explicit_owner_live_authorization_exists,
        warnings_acknowledged=warnings_acknowledged,
    )
    gate = evaluate_minimal_live_trial_gate(
        authorization=authorization,
        request=gate_request,
        strategy_warnings=warnings,
        hard_blockers=hard_blockers,
    )
    final_state: Literal[
        "strategy_trial_architecture_governed",
        "strategy_trial_architecture_governance_blocked_with_explicit_hard_blockers",
    ] = (
        "strategy_trial_architecture_governance_blocked_with_explicit_hard_blockers"
        if _active_hard_blocker_ids(hard_blockers)
        else "strategy_trial_architecture_governed"
    )
    return StrategyTrialArchitectureGovernanceResponse(
        final_state=final_state,
        bnb_state="bnb_first_carrier_consolidated",
        owner_review_packet=OwnerReviewPacket(
            packet_id="MI-001-BNB-LONG-owner-live-review-packet-v1",
            carrier=carrier,
            testnet_rehearsal_result="completed_with_valid_protection",
            testnet_rehearsal_evidence=_testnet_rehearsal_evidence(),
            strategy_warnings=warnings,
            hard_safety_blockers=hard_blockers,
            next_owner_action="explicit_owner_live_authorization_required",
            live_authorization_effect=(
                "Owner live authorization may create a single-use bounded "
                "authorization, but it does not place an order by itself."
            ),
        ),
        authorization_draft=authorization,
        minimal_live_trial_gate=gate,
        architecture_classification=_architecture_classification(),
        generic_now=[
            "StrategyFamily is modeled separately from Carrier",
            "Carrier combines strategy family, symbol, side, and risk cap",
            "Strategy warnings are separate from hard safety blockers",
            "Minimal live trial gate evaluates authorization, hard blockers, and scope",
            "BoundedLiveTrialAuthorization draft is carrier-scoped and non-executable",
        ],
        carrier_specific_by_design=[
            "MI-001-BNB-LONG carrier profile",
            "BNB runtime symbol and testnet runtime profile allowlist",
            "0.01 BNB first-carrier quantity",
            "single_tp_plus_sl protection plan instance",
        ],
        technical_debt_later=[
            "Controlled testnet runtime endpoints remain BNB-first allowlisted",
            "Governance response remains a static review packet; Owner trial-flow endpoints persist acknowledgement and draft metadata",
            "Owner Console can consume the governance API before a polished live packet UI",
        ],
    )


def evaluate_minimal_live_trial_gate(
    *,
    authorization: BoundedLiveTrialAuthorizationDraft,
    request: MinimalLiveTrialGateRequest,
    strategy_warnings: list[StrategyTrialRiskWarning] | None = None,
    hard_blockers: list[StrategyTrialHardBlocker] | None = None,
) -> MinimalLiveTrialGateResult:
    """Evaluate the minimal execution gate without creating execution authority."""

    hard: list[str] = []
    ack: list[str] = []
    warnings = [warning.warning_id for warning in strategy_warnings or []]

    if not request.explicit_owner_live_authorization_exists or not authorization.owner_confirmed:
        hard.append("live_authorization_missing")
    if request.carrier_id != authorization.carrier_id:
        hard.append("carrier_mismatch")
    if request.symbol not in {authorization.symbol, _compact_symbol(authorization.symbol)}:
        hard.append("symbol_mismatch")
    if request.side != authorization.side:
        hard.append("side_mismatch")
    if request.requested_notional > authorization.max_notional:
        hard.append("cap_violation")
    if request.protection_plan_type != authorization.protection_plan_type:
        hard.append("protection_not_executable")
    hard.extend(_active_hard_blocker_ids(hard_blockers or []))

    if not request.warnings_acknowledged:
        required = [
            warning.warning_id
            for warning in strategy_warnings or []
            if warning.owner_ack_required and not warning.acknowledged
        ]
        if required:
            ack.append("strategy_risk_acknowledgement_required")

    can_execute = not hard and not ack
    if hard:
        state: Literal[
            "blocked_missing_owner_live_authorization",
            "blocked_strategy_warning_acknowledgement_required",
            "blocked_by_hard_safety_gate",
            "ready_for_bounded_live_trial_execution",
        ] = (
            "blocked_missing_owner_live_authorization"
            if hard == ["live_authorization_missing"]
            else "blocked_by_hard_safety_gate"
        )
    elif ack:
        state = "blocked_strategy_warning_acknowledgement_required"
    else:
        state = "ready_for_bounded_live_trial_execution"
    return MinimalLiveTrialGateResult(
        can_execute_bounded_live_trial=can_execute,
        final_state=state,
        hard_blockers=_dedupe(hard),
        acknowledgement_blockers=ack,
        warnings=warnings,
    )


def _carrier_view(carrier: StrategyTrialControlledTestnetCarrier) -> StrategyTrialCarrierView:
    return StrategyTrialCarrierView(
        carrier_id=carrier.carrier_id,
        strategy_family=carrier.strategy_profile.strategy_id,
        strategy_id=carrier.strategy_profile.strategy_id,
        candidate_id=carrier.strategy_profile.candidate_id,
        symbol=carrier.strategy_profile.symbol,
        runtime_symbol=carrier.runtime_symbol,
        side=carrier.strategy_profile.side,
        execution_mode="owner_confirm_each_entry",
        quantity=carrier.amount_max,
        max_notional=carrier.max_notional,
        leverage=Decimal(str(carrier.leverage)),
        max_leverage_allowed=Decimal("5"),
        protection_plan_type="single_tp_plus_sl",
    )


def _authorization_draft(
    carrier: StrategyTrialCarrierView,
    *,
    warnings_acknowledged: bool,
    owner_confirmed: bool,
) -> BoundedLiveTrialAuthorizationDraft:
    return BoundedLiveTrialAuthorizationDraft(
        authorization_id="MI-001-BNB-LONG-bounded-live-trial-draft-v1",
        carrier_id=carrier.carrier_id,
        strategy_family=carrier.strategy_family,
        symbol=carrier.runtime_symbol,
        side=carrier.side,
        max_notional=carrier.max_notional,
        quantity=carrier.quantity,
        leverage=carrier.leverage,
        protection_plan_type=carrier.protection_plan_type,
        expires_at="pending_owner_live_authorization_plus_24h",
        owner_confirmed=owner_confirmed,
        pending_owner_live_authorization=not owner_confirmed,
        warnings_acknowledged=warnings_acknowledged,
    )


def _strategy_warnings(*, acknowledged: bool) -> list[StrategyTrialRiskWarning]:
    warning_specs = [
        (
            "strategy_not_proven_profitable",
            "BNB carrier evidence is sufficient for Owner review, not proof of durable alpha.",
        ),
        (
            "limited_live_observation_sample",
            "Live read-only observation sample remains small.",
        ),
        (
            "regime_may_be_unfavorable",
            "Current regime may differ from historical high-quality samples.",
        ),
        (
            "forward_review_incomplete",
            "Forward review is evidence for disclosure, not a permanent execution blocker.",
        ),
        (
            "historical_fragility_known",
            "Historical fragility and adverse early path risk must be acknowledged.",
        ),
    ]
    return [
        StrategyTrialRiskWarning(
            warning_id=warning_id,
            acknowledged=acknowledged,
            description=description,
        )
        for warning_id, description in warning_specs
    ]


def _testnet_rehearsal_evidence() -> dict[str, str | bool]:
    return {
        "result": "testnet_rehearsal_completed_with_valid_protection",
        "entry_order_id": "1424453419",
        "entry_filled_quantity": "0.01 BNB",
        "tp_order_id": "1424453440",
        "tp_status": "accepted_then_cleanup_canceled_terminalized",
        "sl_order_id": "1000000092441892",
        "sl_status": "accepted_then_cleanup_canceled",
        "cleanup_close_order_id": "1424454000",
        "final_position_flat": True,
        "final_local_active_bnb_positions": "0",
        "final_local_open_bnb_orders": "0",
        "periodic_reconciliation": "consistent",
        "campaign_id": "brc-0dfc16d54418",
        "campaign_outcome": "ended_manual_stop",
    }


def _architecture_classification() -> list[StrategyTrialArchitectureClassification]:
    return [
        StrategyTrialArchitectureClassification(
            concept="StrategyFamily",
            current_item="MI-001 strategy profile",
            classification="generic-ready",
            decision="Strategy family carries signal logic identity and no order authority.",
        ),
        StrategyTrialArchitectureClassification(
            concept="Carrier",
            current_item="MI-001-BNB-LONG",
            classification="carrier-specific by design",
            decision="BNB is the first concrete carrier instance: family plus symbol, side, and cap.",
        ),
        StrategyTrialArchitectureClassification(
            concept="RiskCapProfile",
            current_item="BNB max notional / position / attempts cap",
            classification="generic-ready",
            decision="Risk cap shape is reusable; values remain carrier-specific.",
        ),
        StrategyTrialArchitectureClassification(
            concept="ProtectionPlan",
            current_item="single_tp_plus_sl",
            classification="generic-ready",
            decision="Protection planner is generic; BNB 0.01 selects the single-TP instance.",
        ),
        StrategyTrialArchitectureClassification(
            concept="ControlledTestnetCarrierPath",
            current_item="BNB allowlisted runtime endpoints",
            classification="should remain BNB-specific for this sprint",
            decision="Keep allowlisted while proving first carrier; generalize only after another carrier is selected.",
        ),
        StrategyTrialArchitectureClassification(
            concept="OwnerRiskDisclosure",
            current_item="strategy warnings",
            classification="should be generalized now",
            decision="Warnings are explicit disclosure artifacts and do not become hard blockers after acknowledgement.",
        ),
        StrategyTrialArchitectureClassification(
            concept="BoundedLiveTrialAuthorization",
            current_item="BNB pending authorization draft",
            classification="should be generalized now",
            decision="Draft authorization is generic, single-use, carrier-scoped, and non-executable until Owner live authorization.",
        ),
        StrategyTrialArchitectureClassification(
            concept="MinimalLiveTrialGate",
            current_item="authorization + hard blockers + scope",
            classification="generic-ready",
            decision="Gate ignores acknowledged strategy warnings and blocks only on live authorization, hard safety, and scope.",
        ),
    ]


def _active_hard_blocker_ids(blockers: list[StrategyTrialHardBlocker]) -> list[str]:
    return [blocker.blocker_id for blocker in blockers if blocker.active]


def _compact_symbol(symbol: str) -> str:
    return symbol.replace("/", "").replace(":USDT", "")


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped


def _non_permissions() -> dict[str, bool]:
    return {
        "no_live_order": True,
        "no_real_funds": True,
        "no_live_exchange_order": True,
        "no_execution_intent": True,
        "no_order_creation": True,
        "no_execution_permission": True,
        "no_runtime_start": True,
        "no_auto_execution": True,
        "no_transfer_or_withdrawal": True,
        "no_credential_change": True,
        "warning_acknowledgement_is_not_live_authorization": True,
        "authorization_draft_is_not_order_permission": True,
    }
