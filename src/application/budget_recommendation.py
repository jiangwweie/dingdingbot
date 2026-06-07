"""Read-only account-capacity and budget-envelope recommendation contracts."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


DEFAULT_ALLOWED_SYMBOLS = ["SOL/USDT:USDT", "ETH/USDT:USDT"]
DEFAULT_ALLOWED_SIDES = ["long"]
DEFAULT_REVIEW_REQUIREMENT = "owner_confirmation_required_before_final_gate"
DEFAULT_PROTECTION_MODE = "single_tp_plus_sl"


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
    examples = _budget_examples(envelope=envelope)
    blockers = _dedupe_blockers([*capacity.blockers, *envelope.blockers])
    warnings = _dedupe([*capacity.warnings, *envelope.warnings])
    missing_facts = _missing_account_facts(capacity)
    return BudgetRecommendation(
        account_capacity=capacity,
        risk_tier=tier,
        budget_envelope=envelope,
        examples=examples,
        missing_facts=missing_facts,
        warnings=warnings,
        blockers=blockers,
        owner_confirmation_requirement=(
            "Owner must confirm exact symbol, side, quantity, max_notional, leverage, "
            "max_attempts, protection mode, and review requirement before any final gate."
        ),
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


def _money(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return _format_decimal(value.quantize(Decimal("0.01"), rounding=ROUND_DOWN))


def _format_decimal(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text == "-0" else text


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
