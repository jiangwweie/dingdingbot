"""Read-only account-capacity and budget-envelope recommendation contracts."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


DEFAULT_ALLOWED_SYMBOLS = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
    "BNB/USDT:USDT",
]
DEFAULT_ALLOWED_SIDES = ["long"]
DEFAULT_REVIEW_REQUIREMENT = "owner_confirmation_required_before_final_gate"
DEFAULT_PROTECTION_MODE = "single_tp_plus_sl"
DEFAULT_SYMBOL_REASONS = {
    "BTC/USDT:USDT": "highest-liquidity benchmark symbol for cautious Owner review",
    "ETH/USDT:USDT": "default mean-reversion/range example with broad liquidity",
    "SOL/USDT:USDT": "current trend carrier example; higher volatility requires tighter Owner review",
    "BNB/USDT:USDT": "historical BNB action-account context; not a default MR carrier unless supported",
}


class BudgetRecommendationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BlockerRecord(BudgetRecommendationModel):
    id: str
    stage: str
    path: str
    evidence: str
    severity: Literal["hard_blocker", "warning", "deferred"]
    bridge: str
    retry_condition: str


class AccountCapacity(BudgetRecommendationModel):
    status: Literal["available", "degraded", "blocked"]
    account_equity: Optional[str] = None
    available_balance: Optional[str] = None
    margin_facts: dict[str, Any] = Field(default_factory=dict)
    current_exposure_notional: Optional[str] = None
    open_order_notional: Optional[str] = None
    max_usable_notional: Optional[str] = None
    freshness: dict[str, Any] = Field(default_factory=dict)
    source: str
    blockers: list[BlockerRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    action_allowed: Literal[False] = False
    grants_trading_permission: Literal[False] = False


class RiskTier(BudgetRecommendationModel):
    tier: Literal["tiny", "small", "custom"]
    status: Literal["defaulted", "owner_selected", "custom_requires_owner_values"]
    budget_fraction_of_capacity: str
    max_total_budget: Optional[str] = None
    max_notional_per_action: Optional[str] = None
    max_daily_loss: Optional[str] = None
    max_active_positions: int
    max_attempts: int
    max_leverage: str
    allowed_symbols: list[str] = Field(default_factory=list)
    allowed_sides: list[str] = Field(default_factory=list)
    review_requirement: str = DEFAULT_REVIEW_REQUIREMENT
    owner_confirmation_required: Literal[True] = True
    action_allowed: Literal[False] = False


class BudgetEnvelope(BudgetRecommendationModel):
    envelope_id: str = "budget-envelope:read-only-recommendation"
    status: Literal["available", "degraded_missing_account_facts", "blocked_no_capacity"]
    total_budget: Optional[str] = None
    max_notional_per_action: Optional[str] = None
    max_daily_loss: Optional[str] = None
    max_active_positions: int
    max_attempts: int
    max_leverage: str
    allowed_symbols: list[str] = Field(default_factory=list)
    allowed_sides: list[str] = Field(default_factory=list)
    review_requirement: str
    sizing_source: Literal["account_capacity_and_risk_tier"]
    owner_confirmation_requirement: str
    blockers: list[BlockerRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    not_authorization: Literal[True] = True
    not_execution_permission: Literal[True] = True
    grants_trading_permission: Literal[False] = False
    may_execute_live: Literal[False] = False
    frontend_action_enabled: Literal[False] = False
    action_allowed: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class SymbolRecommendation(BudgetRecommendationModel):
    symbol: str
    status: Literal["recommended", "selectable", "warning", "blocked"]
    suitability: Literal["default_example", "suitable", "conditional", "blocked"]
    reason: str
    owner_preferred: bool = False
    warnings: list[str] = Field(default_factory=list)
    blockers: list[BlockerRecord] = Field(default_factory=list)
    action_allowed: Literal[False] = False
    grants_trading_permission: Literal[False] = False


class OwnerBudgetSelection(BudgetRecommendationModel):
    status: Literal[
        "not_provided",
        "within_recommendation",
        "warning_owner_review_required",
        "blocked_by_budget_policy",
    ]
    selected_symbol: Optional[str] = None
    selected_side: Optional[str] = None
    selected_quantity: Optional[str] = None
    selected_target_notional_usdt: Optional[str] = None
    selected_max_notional: Optional[str] = None
    selected_leverage: Optional[str] = None
    selected_max_attempts: Optional[int] = None
    selected_protection_mode: Optional[str] = None
    selected_review_requirement: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    blockers: list[BlockerRecord] = Field(default_factory=list)
    owner_confirmation_required: Literal[True] = True
    action_allowed: Literal[False] = False
    grants_trading_permission: Literal[False] = False


class BudgetedActionSizing(BudgetRecommendationModel):
    family: str
    strategy_family_id: str
    carrier_id: str
    symbol: str
    side: str
    sizing_status: Literal["recommended_owner_review_required", "degraded_missing_capacity"]
    budget_envelope_ref: str
    recommended_quantity: Optional[str] = None
    recommended_max_notional: Optional[str] = None
    max_attempts: int
    leverage: str
    protection_mode: str = DEFAULT_PROTECTION_MODE
    review_requirement: str = DEFAULT_REVIEW_REQUIREMENT
    warnings: list[str] = Field(default_factory=list)
    hard_blockers: list[str] = Field(default_factory=list)
    owner_confirmation_required: Literal[True] = True
    action_allowed: Literal[False] = False
    backend_actionable: Literal[False] = False
    frontend_action_enabled: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False


class BudgetRecommendationExample(BudgetRecommendationModel):
    family: str
    strategy_family_id: str
    carrier_id: str
    proposal_kind: Literal["trend_sol", "mean_reversion_eth", "volatility_proposal"]
    action_candidate_sizing: BudgetedActionSizing
    generic_action_spec_sizing: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)
    blockers: list[BlockerRecord] = Field(default_factory=list)
    action_allowed: Literal[False] = False


class BudgetRecommendation(BudgetRecommendationModel):
    account_capacity: AccountCapacity
    risk_tier: RiskTier
    budget_envelope: BudgetEnvelope
    recommended_symbols: list[SymbolRecommendation]
    owner_selection: OwnerBudgetSelection
    examples: list[BudgetRecommendationExample]
    missing_facts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blockers: list[BlockerRecord] = Field(default_factory=list)
    owner_confirmation_requirement: str
    budgeted_autonomy_enabled: Literal[False] = False
    action_allowed: Literal[False] = False
    grants_trading_permission: Literal[False] = False
    may_execute_live: Literal[False] = False
    frontend_action_enabled: Literal[False] = False
    no_action_guarantee: dict[str, bool] = Field(
        default_factory=lambda: {
            "creates_authorization": False,
            "creates_execution_intent": False,
            "places_order": False,
            "starts_runtime": False,
            "grants_auto_execution": False,
            "mutates_pg": False,
        }
    )


def build_budget_recommendation(
    *,
    account_summary: dict[str, Any],
    positions: list[dict[str, Any]],
    open_orders: list[dict[str, Any]],
    freshness: dict[str, Any],
    risk_tier: str = "tiny",
    allowed_symbols: Optional[list[str]] = None,
    allowed_sides: Optional[list[str]] = None,
    custom: Optional[dict[str, Any]] = None,
    owner_selection: Optional[dict[str, Any]] = None,
) -> BudgetRecommendation:
    symbols = list(allowed_symbols or DEFAULT_ALLOWED_SYMBOLS)
    sides = list(allowed_sides or DEFAULT_ALLOWED_SIDES)
    capacity = build_account_capacity(
        account_summary=account_summary,
        positions=positions,
        open_orders=open_orders,
        freshness=freshness,
    )
    tier = build_risk_tier(
        risk_tier=risk_tier,
        allowed_symbols=symbols,
        allowed_sides=sides,
        custom=custom or {},
    )
    envelope = build_budget_envelope(capacity=capacity, risk_tier=tier)
    symbol_recommendations = build_symbol_recommendations(
        allowed_symbols=symbols,
        owner_symbol=(
            (owner_selection or {}).get("symbol")
            or (owner_selection or {}).get("symbol_preference")
        ),
    )
    owner_budget_selection = build_owner_budget_selection(
        envelope=envelope,
        owner_selection=owner_selection or {},
    )
    examples = _budget_examples(envelope=envelope)
    blockers = _dedupe_blockers(
        [*capacity.blockers, *envelope.blockers, *owner_budget_selection.blockers]
    )
    warnings = _dedupe(
        [*capacity.warnings, *envelope.warnings, *owner_budget_selection.warnings]
    )
    missing_facts = _missing_account_facts(capacity)
    return BudgetRecommendation(
        account_capacity=capacity,
        risk_tier=tier,
        budget_envelope=envelope,
        recommended_symbols=symbol_recommendations,
        owner_selection=owner_budget_selection,
        examples=examples,
        missing_facts=missing_facts,
        warnings=warnings,
        blockers=blockers,
        owner_confirmation_requirement=(
            "Owner must confirm exact symbol, side, quantity, max_notional, leverage, "
            "max_attempts, protection mode, and review requirement before any final gate."
        ),
    )


def build_symbol_recommendations(
    *,
    allowed_symbols: list[str],
    owner_symbol: Optional[Any] = None,
) -> list[SymbolRecommendation]:
    normalized_owner_symbol = _normalize_symbol(owner_symbol)
    recommendations: list[SymbolRecommendation] = []
    for symbol in DEFAULT_ALLOWED_SYMBOLS:
        blockers: list[BlockerRecord] = []
        warnings: list[str] = []
        if symbol not in allowed_symbols:
            blockers.append(
                BlockerRecord(
                    id=f"BUDGET-SYMBOL-{_symbol_code(symbol)}-NOT-ALLOWED",
                    stage="SymbolRecommendation",
                    path="TradingConsole -> BudgetEnvelope -> SymbolRecommendation",
                    evidence=f"{symbol} is outside the current budget allowed_symbols list.",
                    severity="hard_blocker",
                    bridge="blocked_symbol_recommendation",
                    retry_condition="Owner selects a symbol in BudgetEnvelope.allowed_symbols or updates allowed scope through governance.",
                )
            )
        if symbol in {"SOL/USDT:USDT", "BNB/USDT:USDT"}:
            warnings.append("higher idiosyncratic risk; Owner review required before any final gate")
        status: Literal["recommended", "selectable", "warning", "blocked"]
        suitability: Literal["default_example", "suitable", "conditional", "blocked"]
        if blockers:
            status = "blocked"
            suitability = "blocked"
        elif symbol == "ETH/USDT:USDT":
            status = "recommended"
            suitability = "default_example"
        elif warnings:
            status = "warning"
            suitability = "conditional"
        else:
            status = "selectable"
            suitability = "suitable"
        recommendations.append(
            SymbolRecommendation(
                symbol=symbol,
                status=status,
                suitability=suitability,
                reason=DEFAULT_SYMBOL_REASONS.get(symbol, "Owner-selectable symbol for review."),
                owner_preferred=normalized_owner_symbol == symbol,
                warnings=warnings,
                blockers=blockers,
            )
        )
    return recommendations


def build_owner_budget_selection(
    *,
    envelope: BudgetEnvelope,
    owner_selection: dict[str, Any],
) -> OwnerBudgetSelection:
    selected_symbol = _normalize_symbol(
        owner_selection.get("symbol") or owner_selection.get("symbol_preference")
    )
    selected_side = _normalize_side(owner_selection.get("side"))
    selected_quantity = _format_optional_decimal(_decimal(owner_selection.get("quantity")))
    selected_target_notional = _money(_decimal(owner_selection.get("target_notional_usdt")))
    selected_max_notional = _money(_decimal(owner_selection.get("max_notional")))
    selected_leverage = _format_optional_decimal(_decimal(owner_selection.get("leverage")))
    selected_max_attempts = _optional_int(owner_selection.get("max_attempts"))
    selected_protection_mode = _optional_text(owner_selection.get("protection_mode"))
    selected_review_requirement = _optional_text(owner_selection.get("review_requirement"))
    has_selection = any(
        value is not None
        for value in [
            selected_symbol,
            selected_side,
            selected_quantity,
            selected_target_notional,
            selected_max_notional,
            selected_leverage,
            selected_max_attempts,
            selected_protection_mode,
            selected_review_requirement,
        ]
    )
    if not has_selection:
        return OwnerBudgetSelection(status="not_provided")
    blockers: list[BlockerRecord] = []
    warnings: list[str] = []
    if selected_symbol and selected_symbol not in envelope.allowed_symbols:
        blockers.append(
            _owner_selection_blocker(
                blocker_id="BUDGET-OWNER-SELECTION-SYMBOL",
                evidence=f"Owner selected {selected_symbol}, outside BudgetEnvelope.allowed_symbols.",
                retry_condition="Choose a BudgetEnvelope.allowed_symbols value or update budget policy through governance.",
            )
        )
    if selected_side and selected_side not in envelope.allowed_sides:
        blockers.append(
            _owner_selection_blocker(
                blocker_id="BUDGET-OWNER-SELECTION-SIDE",
                evidence=f"Owner selected {selected_side}, outside BudgetEnvelope.allowed_sides.",
                retry_condition="Choose an allowed side or update budget policy through governance.",
            )
        )
    envelope_max_notional = _decimal(envelope.max_notional_per_action)
    owner_max_notional = _decimal(selected_max_notional)
    if (
        owner_max_notional is not None
        and envelope_max_notional is not None
        and owner_max_notional > envelope_max_notional
    ):
        blockers.append(
            _owner_selection_blocker(
                blocker_id="BUDGET-OWNER-SELECTION-MAX-NOTIONAL",
                evidence=(
                    f"Owner selected max_notional {selected_max_notional}, above "
                    f"BudgetEnvelope.max_notional_per_action {envelope.max_notional_per_action}."
                ),
                retry_condition="Lower max_notional or regenerate a valid BudgetEnvelope after fresh account facts.",
            )
        )
    owner_leverage = _decimal(selected_leverage)
    envelope_leverage = _decimal(envelope.max_leverage)
    if owner_leverage is not None and envelope_leverage is not None and owner_leverage > envelope_leverage:
        blockers.append(
            _owner_selection_blocker(
                blocker_id="BUDGET-OWNER-SELECTION-LEVERAGE",
                evidence=f"Owner selected leverage {selected_leverage}, above BudgetEnvelope.max_leverage {envelope.max_leverage}.",
                retry_condition="Lower leverage or update risk tier through governance.",
            )
        )
    if selected_max_attempts is not None and selected_max_attempts > envelope.max_attempts:
        blockers.append(
            _owner_selection_blocker(
                blocker_id="BUDGET-OWNER-SELECTION-MAX-ATTEMPTS",
                evidence=(
                    f"Owner selected max_attempts {selected_max_attempts}, above "
                    f"BudgetEnvelope.max_attempts {envelope.max_attempts}."
                ),
                retry_condition="Lower max_attempts or update risk tier through governance.",
            )
        )
    if selected_protection_mode and selected_protection_mode != DEFAULT_PROTECTION_MODE:
        blockers.append(
            _owner_selection_blocker(
                blocker_id="BUDGET-OWNER-SELECTION-PROTECTION",
                evidence=f"Owner selected protection_mode {selected_protection_mode}; current template requires {DEFAULT_PROTECTION_MODE}.",
                retry_condition="Use single_tp_plus_sl or add a reviewed protection template.",
            )
        )
    if selected_max_notional is None:
        warnings.append("Owner max_notional is not selected; FinalGate must fail closed before any action.")
    if selected_quantity is None and selected_target_notional is None:
        warnings.append("Owner quantity or target_notional_usdt is not selected; FinalGate must fail closed before any action.")
    if blockers:
        status: Literal[
            "not_provided",
            "within_recommendation",
            "warning_owner_review_required",
            "blocked_by_budget_policy",
        ] = "blocked_by_budget_policy"
    elif warnings:
        status = "warning_owner_review_required"
    else:
        status = "within_recommendation"
    return OwnerBudgetSelection(
        status=status,
        selected_symbol=selected_symbol,
        selected_side=selected_side,
        selected_quantity=selected_quantity,
        selected_target_notional_usdt=selected_target_notional,
        selected_max_notional=selected_max_notional,
        selected_leverage=selected_leverage,
        selected_max_attempts=selected_max_attempts,
        selected_protection_mode=selected_protection_mode,
        selected_review_requirement=selected_review_requirement,
        warnings=warnings,
        blockers=blockers,
    )


def build_account_capacity(
    *,
    account_summary: dict[str, Any],
    positions: list[dict[str, Any]],
    open_orders: list[dict[str, Any]],
    freshness: dict[str, Any],
) -> AccountCapacity:
    blockers: list[BlockerRecord] = []
    warnings: list[str] = []
    status = str(account_summary.get("status") or "not_available")
    equity = _decimal(account_summary.get("total_balance"))
    available = _decimal(account_summary.get("available_balance"))
    if status != "available" or equity is None or available is None:
        blockers.append(
            BlockerRecord(
                id="BUDGET-ACCOUNT-CAPACITY-ACCOUNT-FACTS",
                stage="AccountCapacity",
                path="TradingConsole -> AccountCapacity",
                evidence="Readable account equity and available balance are missing.",
                severity="hard_blocker",
                bridge="degraded_budget_recommendation_contract",
                retry_condition="Rerun with readable fresh account facts from the official read-only account path.",
            )
        )
    if freshness.get("freshness_status") in {"degraded", "not_live_connected"}:
        blockers.append(
            BlockerRecord(
                id="BUDGET-ACCOUNT-CAPACITY-FRESHNESS",
                stage="AccountCapacity",
                path="TradingConsole -> AccountCapacity",
                evidence=f"Account facts freshness is {freshness.get('freshness_status')}.",
                severity="hard_blocker",
                bridge="degraded_budget_recommendation_contract",
                retry_condition="Rerun after fresh account, exposure, and open-order reads are available.",
            )
        )
    exposure = _sum_position_notional(positions)
    open_order_notional = _sum_order_notional(open_orders)
    max_usable = None
    if equity is not None and available is not None:
        gross_capacity = min(equity * Decimal("0.15"), available * Decimal("0.30"))
        max_usable = max(Decimal("0"), gross_capacity - exposure - open_order_notional)
        if max_usable <= Decimal("0"):
            blockers.append(
                BlockerRecord(
                    id="BUDGET-ACCOUNT-CAPACITY-NO-HEADROOM",
                    stage="AccountCapacity",
                    path="AccountCapacity -> BudgetEnvelope",
                    evidence="Current exposure/open-order reserve consumes conservative account capacity.",
                    severity="hard_blocker",
                    bridge="blocked_budget_envelope",
                    retry_condition="Existing exposure/open orders are cleared or account facts show positive conservative headroom.",
                )
            )
    if exposure > Decimal("0"):
        warnings.append("current exposure reduces recommended usable budget")
    if open_order_notional > Decimal("0"):
        warnings.append("open orders reduce recommended usable budget")
    return AccountCapacity(
        status="available" if not blockers else ("blocked" if max_usable == Decimal("0") else "degraded"),
        account_equity=_money(equity),
        available_balance=_money(available),
        margin_facts={
            "available_margin": account_summary.get("available_balance"),
            "wallet_equity": account_summary.get("total_balance"),
            "unrealized_pnl": account_summary.get("unrealized_pnl"),
            "positions_count": account_summary.get("positions_count"),
            "margin_mode": account_summary.get("margin_mode") or "not_available",
        },
        current_exposure_notional=_money(exposure),
        open_order_notional=_money(open_order_notional),
        max_usable_notional=_money(max_usable),
        freshness=dict(freshness),
        source="trading_console_account_snapshot_and_read_models",
        blockers=blockers,
        warnings=warnings,
    )


def build_risk_tier(
    *,
    risk_tier: str,
    allowed_symbols: list[str],
    allowed_sides: list[str],
    custom: dict[str, Any],
) -> RiskTier:
    normalized = str(risk_tier or "tiny").strip().lower().replace("-", "_")
    if normalized not in {"tiny", "small", "custom"}:
        normalized = "tiny"
    if normalized == "small":
        return RiskTier(
            tier="small",
            status="owner_selected",
            budget_fraction_of_capacity="0.50",
            max_total_budget="50",
            max_notional_per_action="25",
            max_daily_loss="2",
            max_active_positions=1,
            max_attempts=1,
            max_leverage="1",
            allowed_symbols=allowed_symbols,
            allowed_sides=allowed_sides,
        )
    if normalized == "custom":
        return RiskTier(
            tier="custom",
            status=(
                "owner_selected"
                if custom.get("total_budget") or custom.get("max_notional_per_action")
                else "custom_requires_owner_values"
            ),
            budget_fraction_of_capacity=_format_decimal(_decimal(custom.get("capacity_fraction")) or Decimal("0.25")),
            max_total_budget=_money(_decimal(custom.get("total_budget"))),
            max_notional_per_action=_money(_decimal(custom.get("max_notional_per_action"))),
            max_daily_loss=_money(_decimal(custom.get("max_daily_loss"))),
            max_active_positions=int(custom.get("max_active_positions") or 1),
            max_attempts=int(custom.get("max_attempts") or 1),
            max_leverage=_format_decimal(_decimal(custom.get("max_leverage")) or Decimal("1")),
            allowed_symbols=allowed_symbols,
            allowed_sides=allowed_sides,
        )
    return RiskTier(
        tier="tiny",
        status="defaulted" if not risk_tier else "owner_selected",
        budget_fraction_of_capacity="0.25",
        max_total_budget="20",
        max_notional_per_action="20",
        max_daily_loss="1",
        max_active_positions=1,
        max_attempts=1,
        max_leverage="1",
        allowed_symbols=allowed_symbols,
        allowed_sides=allowed_sides,
    )


def build_budget_envelope(*, capacity: AccountCapacity, risk_tier: RiskTier) -> BudgetEnvelope:
    blockers = list(capacity.blockers)
    capacity_value = _decimal(capacity.max_usable_notional)
    tier_budget_cap = _decimal(risk_tier.max_total_budget)
    per_action_cap = _decimal(risk_tier.max_notional_per_action)
    daily_loss_cap = _decimal(risk_tier.max_daily_loss)
    total_budget = None
    max_per_action = None
    if capacity_value is not None and capacity_value > Decimal("0"):
        risk_fraction = _decimal(risk_tier.budget_fraction_of_capacity) or Decimal("0")
        total_budget = capacity_value * risk_fraction
        if tier_budget_cap is not None:
            total_budget = min(total_budget, tier_budget_cap)
        if total_budget <= Decimal("0"):
            blockers.append(
                BlockerRecord(
                    id="BUDGET-ENVELOPE-NO-USABLE-BUDGET",
                    stage="BudgetEnvelope",
                    path="AccountCapacity -> RiskTier -> BudgetEnvelope",
                    evidence="Risk tier and account capacity produce no positive usable budget.",
                    severity="hard_blocker",
                    bridge="blocked_budget_envelope",
                    retry_condition="Readable positive capacity and a non-zero risk tier budget are available.",
                )
            )
        else:
            max_per_action = total_budget
            if per_action_cap is not None:
                max_per_action = min(max_per_action, per_action_cap)
    status: Literal["available", "degraded_missing_account_facts", "blocked_no_capacity"]
    if total_budget is None:
        status = "degraded_missing_account_facts"
    elif total_budget <= Decimal("0") or any(item.id == "BUDGET-ACCOUNT-CAPACITY-NO-HEADROOM" for item in blockers):
        status = "blocked_no_capacity"
    else:
        status = "available"
    warnings = [
        "budget recommendation is not permission to trade",
        "weak strategy evidence requires Owner review",
        "fee/funding/slippage are incomplete and must be reviewed before final gate",
        "non-core read-model degradation is warning unless it affects live-action hard gates",
    ]
    return BudgetEnvelope(
        status=status,
        total_budget=_money(total_budget),
        max_notional_per_action=_money(max_per_action),
        max_daily_loss=_money(daily_loss_cap),
        max_active_positions=risk_tier.max_active_positions,
        max_attempts=risk_tier.max_attempts,
        max_leverage=risk_tier.max_leverage,
        allowed_symbols=list(risk_tier.allowed_symbols),
        allowed_sides=list(risk_tier.allowed_sides),
        review_requirement=risk_tier.review_requirement,
        sizing_source="account_capacity_and_risk_tier",
        owner_confirmation_requirement=(
            "BudgetEnvelope can prefill suggested sizing only; Owner must confirm exact scope."
        ),
        blockers=blockers,
        warnings=warnings,
    )


def apply_budget_envelope_to_generic_action_specs(
    specs: list[dict[str, Any]],
    envelope: BudgetEnvelope | dict[str, Any],
) -> list[dict[str, Any]]:
    envelope_payload = envelope.model_dump(mode="json") if isinstance(envelope, BudgetEnvelope) else dict(envelope)
    result: list[dict[str, Any]] = []
    for spec in specs:
        item = dict(spec)
        item["budget_envelope_ref"] = envelope_payload.get("envelope_id")
        item["sizing_source"] = "budget_envelope_recommendation"
        item["recommended_quantity"] = item.get("quantity")
        item["recommended_max_notional"] = envelope_payload.get("max_notional_per_action")
        item["recommended_total_budget"] = envelope_payload.get("total_budget")
        item["budget_owner_confirmation_required"] = True
        item["budget_recommendation_status"] = envelope_payload.get("status")
        if envelope_payload.get("max_notional_per_action") and not item.get("max_notional"):
            item["max_notional"] = envelope_payload.get("max_notional_per_action")
        if envelope_payload.get("max_leverage") and not item.get("leverage"):
            item["leverage"] = envelope_payload.get("max_leverage")
        if envelope_payload.get("max_attempts") and not item.get("max_attempts"):
            item["max_attempts"] = envelope_payload.get("max_attempts")
        if envelope_payload.get("review_requirement") and not item.get("review_requirement"):
            item["review_requirement"] = envelope_payload.get("review_requirement")
        result.append(item)
    return result


def apply_budget_envelope_to_action_candidates(
    candidates: list[dict[str, Any]],
    envelope: BudgetEnvelope | dict[str, Any],
) -> list[dict[str, Any]]:
    envelope_payload = envelope.model_dump(mode="json") if isinstance(envelope, BudgetEnvelope) else dict(envelope)
    result: list[dict[str, Any]] = []
    for candidate in candidates:
        item = dict(candidate)
        item["budget_envelope_ref"] = envelope_payload.get("envelope_id")
        item["recommended_sizing"] = {
            "status": envelope_payload.get("status"),
            "max_notional_per_action": envelope_payload.get("max_notional_per_action"),
            "max_attempts": envelope_payload.get("max_attempts"),
            "max_leverage": envelope_payload.get("max_leverage"),
            "review_requirement": envelope_payload.get("review_requirement"),
            "owner_confirmation_required": True,
            "action_allowed": False,
        }
        result.append(item)
    return result


def _budget_examples(*, envelope: BudgetEnvelope) -> list[BudgetRecommendationExample]:
    rows = [
        ("Trend", "TF-001-live-readonly-v0", "TF-001-live-readonly-v0", "trend_sol", "SOL/USDT:USDT", "long"),
        ("Mean reversion", "MR-001-live-readonly-v0", "MR-001-live-readonly-v0", "mean_reversion_eth", "ETH/USDT:USDT", "long"),
        ("Volatility expansion", "VB-001-live-readonly-v0", "VB-001-live-readonly-v0", "volatility_proposal", "ETH/USDT:USDT", "long"),
    ]
    examples: list[BudgetRecommendationExample] = []
    for family, strategy_family_id, carrier_id, kind, symbol, side in rows:
        sizing = _action_sizing(
            family=family,
            strategy_family_id=strategy_family_id,
            carrier_id=carrier_id,
            symbol=symbol,
            side=side,
            envelope=envelope,
        )
        generic = {
            "family": family,
            "strategy_family_id": strategy_family_id,
            "carrier_id": carrier_id,
            "symbol": symbol,
            "side": side,
            "quantity": sizing.recommended_quantity,
            "max_notional": sizing.recommended_max_notional,
            "leverage": sizing.leverage,
            "max_attempts": sizing.max_attempts,
            "protection_mode": sizing.protection_mode,
            "review_requirement": sizing.review_requirement,
            "budget_envelope_ref": sizing.budget_envelope_ref,
            "sizing_source": "budget_envelope_recommendation",
            "owner_confirmation_required": True,
            "may_execute_live": False,
            "frontend_action_enabled": False,
            "places_order": False,
        }
        examples.append(
            BudgetRecommendationExample(
                family=family,
                strategy_family_id=strategy_family_id,
                carrier_id=carrier_id,
                proposal_kind=kind,  # type: ignore[arg-type]
                action_candidate_sizing=sizing,
                generic_action_spec_sizing=generic,
                warnings=list(envelope.warnings),
                blockers=list(envelope.blockers),
            )
        )
    return examples


def _action_sizing(
    *,
    family: str,
    strategy_family_id: str,
    carrier_id: str,
    symbol: str,
    side: str,
    envelope: BudgetEnvelope,
) -> BudgetedActionSizing:
    recommended_notional = _decimal(envelope.max_notional_per_action)
    hard_blockers = [item.id for item in envelope.blockers if item.severity == "hard_blocker"]
    return BudgetedActionSizing(
        family=family,
        strategy_family_id=strategy_family_id,
        carrier_id=carrier_id,
        symbol=symbol,
        side=side,
        sizing_status=(
            "recommended_owner_review_required"
            if recommended_notional is not None and recommended_notional > Decimal("0")
            else "degraded_missing_capacity"
        ),
        budget_envelope_ref=envelope.envelope_id,
        recommended_quantity=None,
        recommended_max_notional=_money(recommended_notional),
        max_attempts=envelope.max_attempts,
        leverage=envelope.max_leverage,
        review_requirement=envelope.review_requirement,
        warnings=list(envelope.warnings),
        hard_blockers=hard_blockers,
    )


def _sum_position_notional(positions: list[dict[str, Any]]) -> Decimal:
    total = Decimal("0")
    for item in positions:
        qty = abs(_decimal(item.get("quantity")) or Decimal("0"))
        price = _decimal(item.get("mark_price")) or _decimal(item.get("entry_price")) or Decimal("0")
        total += qty * price
    return total


def _sum_order_notional(orders: list[dict[str, Any]]) -> Decimal:
    total = Decimal("0")
    for item in orders:
        qty = abs(_decimal(item.get("requested_qty")) or Decimal("0"))
        price = (
            _decimal(item.get("price"))
            or _decimal(item.get("trigger_price"))
            or _decimal(item.get("average_exec_price"))
            or Decimal("0")
        )
        total += qty * price
    return total


def _missing_account_facts(capacity: AccountCapacity) -> list[str]:
    missing: list[str] = []
    if capacity.account_equity is None:
        missing.append("account_equity")
    if capacity.available_balance is None:
        missing.append("available_balance")
    if capacity.max_usable_notional is None:
        missing.append("max_usable_notional")
    if capacity.freshness.get("freshness_status") in {"degraded", "not_live_connected"}:
        missing.append("fresh_account_facts")
    return _dedupe(missing)


def _decimal(value: Any) -> Optional[Decimal]:
    if value is None or value == "" or value == "not_available":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _format_optional_decimal(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return _format_decimal(value)


def _money(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return _format_decimal(value.quantize(Decimal("0.01"), rounding=ROUND_DOWN))


def _format_decimal(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text == "-0" else text


def _normalize_symbol(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    aliases = {
        "BTC": "BTC/USDT:USDT",
        "BTCUSDT": "BTC/USDT:USDT",
        "BTC/USDT": "BTC/USDT:USDT",
        "ETH": "ETH/USDT:USDT",
        "ETHUSDT": "ETH/USDT:USDT",
        "ETH/USDT": "ETH/USDT:USDT",
        "SOL": "SOL/USDT:USDT",
        "SOLUSDT": "SOL/USDT:USDT",
        "SOL/USDT": "SOL/USDT:USDT",
        "BNB": "BNB/USDT:USDT",
        "BNBUSDT": "BNB/USDT:USDT",
        "BNB/USDT": "BNB/USDT:USDT",
    }
    return aliases.get(text, text)


def _symbol_code(symbol: str) -> str:
    return symbol.split("/", maxsplit=1)[0].replace(":", "_").replace("-", "_")


def _normalize_side(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"long", "buy"}:
        return "long"
    if text in {"short", "sell"}:
        return "short"
    return text or None


def _optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _owner_selection_blocker(
    *,
    blocker_id: str,
    evidence: str,
    retry_condition: str,
) -> BlockerRecord:
    return BlockerRecord(
        id=blocker_id,
        stage="OwnerBudgetSelection",
        path="TradingConsole -> OwnerSelection -> BudgetEnvelope",
        evidence=evidence,
        severity="hard_blocker",
        bridge="owner_selection_budget_policy_validation",
        retry_condition=retry_condition,
    )


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _dedupe_blockers(items: list[BlockerRecord]) -> list[BlockerRecord]:
    seen: set[str] = set()
    result: list[BlockerRecord] = []
    for item in items:
        if item.id in seen:
            continue
        seen.add(item.id)
        result.append(item)
    return result
