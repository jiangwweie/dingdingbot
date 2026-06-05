"""PG-backed protection price source and TP/SL planner.

This module contains no exchange writes and creates no execution intent or
order. It turns an auditable reference/fill price plus exchange filters into a
single TP + SL protection plan.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from src.application.owner_action_carrier_catalog import (
    BNB_OWNER_ACTION_CARRIER_ID,
    TREND_OWNER_ACTION_CARRIER_ID,
)
from src.application.owner_trial_flow import BoundedLiveTrialAuthorization
from src.application.protection_order_planner import plan_precision_aware_protection_orders


PROTECTION_PLANNER_VERSION = "single_tp_plus_sl_fill_v1"
ProtectionPlanPhase = Literal["pre_entry_reference", "post_entry_fill"]
ProtectionPlanStatus = Literal["valid", "blocked"]


class ProtectionExchangeFilters(BaseModel):
    model_config = ConfigDict(frozen=True)

    min_amount: Decimal | None = None
    amount_step: Decimal | None = None
    min_notional: Decimal | None = None
    min_notional_source: str | None = None
    tick_size: Decimal | None = None
    price_precision: int | None = None


class ProtectionPriceSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    authorization_id: str
    carrier_id: str
    symbol: str
    side: Literal["long", "short"]
    reference_price: Decimal
    price_source_type: str
    source_ref: str | None = None
    observed_at_ms: int
    filters: ProtectionExchangeFilters


class ProtectionPlannerConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    carrier_id: str
    symbol: str
    side: Literal["long", "short"]
    protection_plan_type: Literal["single_tp_plus_sl"] = "single_tp_plus_sl"
    stop_loss_fraction: Decimal = Field(default=Decimal("0.01"), gt=Decimal("0"))
    tp_targets_pct: tuple[Decimal, ...] = (Decimal("1.0"),)
    tp_ratios: tuple[Decimal, ...] = (Decimal("1.0"),)
    planner_version: str = PROTECTION_PLANNER_VERSION


class ProtectionPricePlanRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    plan_id: str
    authorization_id: str
    carrier_id: str
    symbol: str
    side: Literal["long", "short"]
    phase: ProtectionPlanPhase
    status: ProtectionPlanStatus
    planner_version: str
    price_source_type: str
    reference_price: Decimal | None = None
    fill_price: Decimal | None = None
    quantity: Decimal
    tp_price: Decimal | None = None
    sl_price: Decimal | None = None
    tp_quantity: Decimal | None = None
    sl_quantity: Decimal | None = None
    tick_size: Decimal | None = None
    amount_step: Decimal | None = None
    min_amount: Decimal | None = None
    min_notional: Decimal | None = None
    rounding: dict[str, str] = Field(default_factory=dict)
    filters: dict[str, str | None] = Field(default_factory=dict)
    blockers: list[str] = Field(default_factory=list)
    computed_at_ms: int
    source_ref: str | None = None


class ProtectionPriceSource(Protocol):
    async def read_snapshot(
        self,
        authorization: BoundedLiveTrialAuthorization,
    ) -> ProtectionPriceSnapshot:
        ...


class ProtectionPricePlanRepository(Protocol):
    async def save_plan(self, plan: ProtectionPricePlanRecord) -> ProtectionPricePlanRecord:
        ...

    async def latest_valid_plan(
        self,
        authorization_id: str,
        *,
        phase: ProtectionPlanPhase | None = None,
    ) -> ProtectionPricePlanRecord | None:
        ...


class ProtectionPriceSourceUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class StaticProtectionPriceSource:
    """Deterministic read-only source for tests and controlled metadata repair."""

    reference_price: Decimal
    filters: ProtectionExchangeFilters
    price_source_type: str = "static_read_only_test_price"
    source_ref: str | None = None

    async def read_snapshot(
        self,
        authorization: BoundedLiveTrialAuthorization,
    ) -> ProtectionPriceSnapshot:
        return ProtectionPriceSnapshot(
            authorization_id=authorization.authorization_id,
            carrier_id=authorization.carrier_id,
            symbol=authorization.symbol,
            side=authorization.side,
            reference_price=self.reference_price,
            price_source_type=self.price_source_type,
            source_ref=self.source_ref,
            observed_at_ms=_now_ms(),
            filters=self.filters,
        )


@dataclass(frozen=True)
class ExchangeGatewayProtectionPriceSource:
    """Read-only exchange gateway source.

    It only calls ticker/market-info reads. It never calls create/cancel/order
    methods.
    """

    gateway: object | None
    price_source_type: str = "exchange_read_only_ticker"

    async def read_snapshot(
        self,
        authorization: BoundedLiveTrialAuthorization,
    ) -> ProtectionPriceSnapshot:
        if self.gateway is None or not hasattr(self.gateway, "fetch_ticker_price"):
            raise ProtectionPriceSourceUnavailable("protection_price_source_missing")
        reference_price = await self.gateway.fetch_ticker_price(authorization.symbol)
        filters = await _read_filters(self.gateway, authorization.symbol)
        return ProtectionPriceSnapshot(
            authorization_id=authorization.authorization_id,
            carrier_id=authorization.carrier_id,
            symbol=authorization.symbol,
            side=authorization.side,
            reference_price=Decimal(str(reference_price)),
            price_source_type=self.price_source_type,
            source_ref=f"gateway:{type(self.gateway).__name__}:fetch_ticker_price",
            observed_at_ms=_now_ms(),
            filters=filters,
        )


class ProtectionPlannerService:
    def __init__(
        self,
        *,
        repository: ProtectionPricePlanRepository,
        price_source: ProtectionPriceSource | None = None,
        configs: dict[str, ProtectionPlannerConfig] | None = None,
    ) -> None:
        self._repository = repository
        self._price_source = price_source
        self._configs = configs or default_protection_planner_configs()

    async def ensure_pre_entry_plan(
        self,
        authorization: BoundedLiveTrialAuthorization,
    ) -> ProtectionPricePlanRecord:
        existing = await self._repository.latest_valid_plan(
            authorization.authorization_id,
            phase="pre_entry_reference",
        )
        if existing is not None:
            return existing
        if self._price_source is None:
            raise ProtectionPriceSourceUnavailable("protection_price_source_missing")
        snapshot = await self._price_source.read_snapshot(authorization)
        plan = self.build_pre_entry_plan(authorization, snapshot=snapshot)
        await self._repository.save_plan(plan)
        if plan.status != "valid":
            raise ProtectionPriceSourceUnavailable(plan.blockers[0] if plan.blockers else "protection_plan_blocked")
        return plan

    async def create_fill_based_plan(
        self,
        authorization: BoundedLiveTrialAuthorization,
        *,
        fill_price: Decimal,
        filters: ProtectionExchangeFilters,
        price_source_type: str = "exchange_order_fill_avg",
        source_ref: str | None = None,
    ) -> ProtectionPricePlanRecord:
        config = self._config_for(authorization)
        plan = build_single_tp_sl_plan(
            authorization=authorization,
            config=config,
            phase="post_entry_fill",
            price_source_type=price_source_type,
            base_price=Decimal(str(fill_price)),
            filters=filters,
            source_ref=source_ref,
        )
        return await self._repository.save_plan(plan)

    def build_pre_entry_plan(
        self,
        authorization: BoundedLiveTrialAuthorization,
        *,
        snapshot: ProtectionPriceSnapshot,
    ) -> ProtectionPricePlanRecord:
        config = self._config_for(authorization)
        if snapshot.authorization_id != authorization.authorization_id:
            return _blocked_plan(
                authorization,
                config=config,
                phase="pre_entry_reference",
                price_source_type=snapshot.price_source_type,
                blocker="protection_snapshot_authorization_mismatch",
                reference_price=snapshot.reference_price,
                filters=snapshot.filters,
                source_ref=snapshot.source_ref,
            )
        return build_single_tp_sl_plan(
            authorization=authorization,
            config=config,
            phase="pre_entry_reference",
            price_source_type=snapshot.price_source_type,
            base_price=snapshot.reference_price,
            filters=snapshot.filters,
            source_ref=snapshot.source_ref,
        )

    def _config_for(self, authorization: BoundedLiveTrialAuthorization) -> ProtectionPlannerConfig:
        config = self._configs.get(authorization.carrier_id)
        if config is None:
            raise ProtectionPriceSourceUnavailable("protection_planner_config_missing")
        if (
            config.symbol != authorization.symbol
            or config.side != authorization.side
            or config.protection_plan_type != authorization.protection_plan_type
        ):
            raise ProtectionPriceSourceUnavailable("protection_planner_scope_mismatch")
        return config


def default_protection_planner_configs() -> dict[str, ProtectionPlannerConfig]:
    configs = [
        ProtectionPlannerConfig(
            carrier_id=BNB_OWNER_ACTION_CARRIER_ID,
            symbol="BNB/USDT:USDT",
            side="long",
            stop_loss_fraction=Decimal("0.01"),
            tp_targets_pct=(Decimal("1.0"),),
            tp_ratios=(Decimal("1.0"),),
        ),
        ProtectionPlannerConfig(
            carrier_id=TREND_OWNER_ACTION_CARRIER_ID,
            symbol="SOL/USDT:USDT",
            side="long",
            stop_loss_fraction=Decimal("0.01"),
            tp_targets_pct=(Decimal("1.0"),),
            tp_ratios=(Decimal("1.0"),),
        ),
    ]
    return {config.carrier_id: config for config in configs}


def build_single_tp_sl_plan(
    *,
    authorization: BoundedLiveTrialAuthorization,
    config: ProtectionPlannerConfig,
    phase: ProtectionPlanPhase,
    price_source_type: str,
    base_price: Decimal,
    filters: ProtectionExchangeFilters,
    source_ref: str | None = None,
) -> ProtectionPricePlanRecord:
    scope_blocker = _scope_blocker(authorization, config)
    if scope_blocker:
        return _blocked_plan(
            authorization,
            config=config,
            phase=phase,
            price_source_type=price_source_type,
            blocker=scope_blocker,
            reference_price=base_price if phase == "pre_entry_reference" else None,
            fill_price=base_price if phase == "post_entry_fill" else None,
            filters=filters,
            source_ref=source_ref,
        )
    quantity_plan = plan_precision_aware_protection_orders(
        entry_quantity=authorization.quantity,
        entry_price=base_price,
        min_amount=filters.min_amount,
        amount_step=filters.amount_step,
        min_notional=filters.min_notional,
        min_notional_source=filters.min_notional_source,
        intended_tp_ratios=config.tp_ratios,
        intended_tp_targets=config.tp_targets_pct,
        allow_sl_only=False,
    )
    if quantity_plan.status != "valid" or quantity_plan.planned_sl_quantity is None:
        return _blocked_plan(
            authorization,
            config=config,
            phase=phase,
            price_source_type=price_source_type,
            blocker=quantity_plan.blocked_reason or "protection_quantity_plan_blocked",
            reference_price=base_price if phase == "pre_entry_reference" else None,
            fill_price=base_price if phase == "post_entry_fill" else None,
            filters=filters,
            source_ref=source_ref,
        )
    tp_target = (quantity_plan.tp_targets or config.tp_targets_pct)[0]
    if authorization.side == "long":
        raw_tp = base_price * (Decimal("1") + (tp_target / Decimal("100")))
        raw_sl = base_price * (Decimal("1") - config.stop_loss_fraction)
        tp_price = _round_price(raw_tp, filters.tick_size, "down")
        sl_price = _round_price(raw_sl, filters.tick_size, "down")
    else:
        raw_tp = base_price * (Decimal("1") - (tp_target / Decimal("100")))
        raw_sl = base_price * (Decimal("1") + config.stop_loss_fraction)
        tp_price = _round_price(raw_tp, filters.tick_size, "up")
        sl_price = _round_price(raw_sl, filters.tick_size, "up")
    return ProtectionPricePlanRecord(
        plan_id=f"prot-plan-{uuid.uuid4().hex}",
        authorization_id=authorization.authorization_id,
        carrier_id=authorization.carrier_id,
        symbol=authorization.symbol,
        side=authorization.side,
        phase=phase,
        status="valid",
        planner_version=config.planner_version,
        price_source_type=price_source_type,
        reference_price=base_price if phase == "pre_entry_reference" else None,
        fill_price=base_price if phase == "post_entry_fill" else None,
        quantity=authorization.quantity,
        tp_price=tp_price,
        sl_price=sl_price,
        tp_quantity=quantity_plan.planned_tp_quantities[0],
        sl_quantity=quantity_plan.planned_sl_quantity,
        tick_size=filters.tick_size,
        amount_step=filters.amount_step,
        min_amount=filters.min_amount,
        min_notional=filters.min_notional,
        rounding={
            "tp_raw": str(raw_tp),
            "sl_raw": str(raw_sl),
            "tp_rounding": "tick_floor" if authorization.side == "long" else "tick_ceiling",
            "sl_rounding": "tick_floor" if authorization.side == "long" else "tick_ceiling",
        },
        filters=_filters_json(filters),
        computed_at_ms=_now_ms(),
        source_ref=source_ref,
    )


def _blocked_plan(
    authorization: BoundedLiveTrialAuthorization,
    *,
    config: ProtectionPlannerConfig,
    phase: ProtectionPlanPhase,
    price_source_type: str,
    blocker: str,
    filters: ProtectionExchangeFilters,
    reference_price: Decimal | None = None,
    fill_price: Decimal | None = None,
    source_ref: str | None = None,
) -> ProtectionPricePlanRecord:
    return ProtectionPricePlanRecord(
        plan_id=f"prot-plan-{uuid.uuid4().hex}",
        authorization_id=authorization.authorization_id,
        carrier_id=authorization.carrier_id,
        symbol=authorization.symbol,
        side=authorization.side,
        phase=phase,
        status="blocked",
        planner_version=config.planner_version,
        price_source_type=price_source_type,
        reference_price=reference_price,
        fill_price=fill_price,
        quantity=authorization.quantity,
        tick_size=filters.tick_size,
        amount_step=filters.amount_step,
        min_amount=filters.min_amount,
        min_notional=filters.min_notional,
        filters=_filters_json(filters),
        blockers=[blocker],
        computed_at_ms=_now_ms(),
        source_ref=source_ref,
    )


async def _read_filters(gateway: object, symbol: str) -> ProtectionExchangeFilters:
    if not hasattr(gateway, "get_market_info"):
        return ProtectionExchangeFilters()
    info = await gateway.get_market_info(symbol)
    return ProtectionExchangeFilters(
        min_amount=_decimal_or_none(info.get("min_quantity")),
        amount_step=_decimal_or_none(info.get("step_size")),
        min_notional=_decimal_or_none(info.get("min_notional")),
        min_notional_source="exchange_market_info",
        tick_size=_tick_from_market_info(info),
        price_precision=_price_precision_or_none(info.get("price_precision")),
    )


def _scope_blocker(
    authorization: BoundedLiveTrialAuthorization,
    config: ProtectionPlannerConfig,
) -> str | None:
    if authorization.carrier_id != config.carrier_id:
        return "protection_carrier_mismatch"
    if authorization.symbol != config.symbol:
        return "protection_symbol_mismatch"
    if authorization.side != config.side:
        return "protection_side_mismatch"
    if authorization.protection_plan_type != config.protection_plan_type:
        return "protection_plan_type_mismatch"
    return None


def _round_price(price: Decimal, tick_size: Decimal | None, direction: Literal["down", "up"]) -> Decimal:
    if tick_size is None or tick_size <= 0:
        return price
    rounding = ROUND_FLOOR if direction == "down" else ROUND_CEILING
    units = (price / tick_size).to_integral_value(rounding=rounding)
    return units * tick_size


def _tick_from_market_info(info: dict) -> Decimal | None:
    tick = info.get("tick_size") or info.get("tickSize")
    if tick is not None:
        return Decimal(str(tick))
    precision = info.get("price_precision")
    if precision is None:
        return None
    try:
        precision_decimal = Decimal(str(precision))
    except Exception:
        return None
    if precision_decimal <= 0:
        return None
    if precision_decimal == precision_decimal.to_integral_value():
        return Decimal("1").scaleb(-int(precision_decimal))
    return precision_decimal


def _price_precision_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        precision_decimal = Decimal(str(value))
    except Exception:
        return None
    if precision_decimal < 0:
        return None
    if precision_decimal == precision_decimal.to_integral_value():
        return int(precision_decimal)
    return None


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    decimal = Decimal(str(value))
    return decimal if decimal > 0 else None


def _filters_json(filters: ProtectionExchangeFilters) -> dict[str, str | None]:
    return {
        "min_amount": str(filters.min_amount) if filters.min_amount is not None else None,
        "amount_step": str(filters.amount_step) if filters.amount_step is not None else None,
        "min_notional": str(filters.min_notional) if filters.min_notional is not None else None,
        "min_notional_source": filters.min_notional_source,
        "tick_size": str(filters.tick_size) if filters.tick_size is not None else None,
        "price_precision": str(filters.price_precision) if filters.price_precision is not None else None,
    }


def _now_ms() -> int:
    return int(time.time() * 1000)
