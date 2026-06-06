from __future__ import annotations

from decimal import Decimal

import pytest

from src.application.owner_trial_flow import BoundedLiveTrialAuthorization
from src.application.protection_price_planner import (
    ExchangeGatewayProtectionPriceSource,
    ProtectionExchangeFilters,
    ProtectionPlannerConfig,
    ProtectionPlannerService,
    ProtectionPricePlanRecord,
    ProtectionPriceSourceUnavailable,
    StaticProtectionPriceSource,
)


class MemoryProtectionPlanRepository:
    def __init__(self) -> None:
        self.records: list[ProtectionPricePlanRecord] = []

    async def save_plan(self, plan: ProtectionPricePlanRecord) -> ProtectionPricePlanRecord:
        self.records.append(plan)
        return plan

    async def latest_valid_plan(self, authorization_id: str, *, phase=None):
        matches = [
            item
            for item in self.records
            if item.authorization_id == authorization_id
            and item.status == "valid"
            and (phase is None or item.phase == phase)
        ]
        return matches[-1] if matches else None


class FakeReadOnlyGateway:
    def __init__(self, *, price_precision) -> None:
        self.price_precision = price_precision
        self.write_calls: list[str] = []

    async def fetch_ticker_price(self, symbol: str) -> Decimal:
        assert symbol == "BNB/USDT:USDT"
        return Decimal("600.12")

    async def get_market_info(self, symbol: str) -> dict:
        assert symbol == "BNB/USDT:USDT"
        return {
            "min_quantity": Decimal("0.01"),
            "step_size": Decimal("0.01"),
            "min_notional": Decimal("5"),
            "price_precision": self.price_precision,
        }


def _authorization(**patch) -> BoundedLiveTrialAuthorization:
    payload = {
        "authorization_id": "auth-test",
        "draft_id": "draft-test",
        "carrier_id": "MI-001-BNB-LONG",
        "strategy_family_id": "MI-001",
        "symbol": "BNB/USDT:USDT",
        "side": "long",
        "max_notional": Decimal("20"),
        "quantity": Decimal("0.01"),
        "leverage": Decimal("1"),
        "protection_plan_type": "single_tp_plus_sl",
        "owner_live_authorized_by": "owner",
        "owner_live_authorized_at_ms": 1,
        "linked_acknowledgement_id": "ack-test",
        "source_draft_id": "draft-test",
        "created_at_ms": 1,
        "updated_at_ms": 1,
    }
    payload.update(patch)
    return BoundedLiveTrialAuthorization(**payload)


def _filters(**patch) -> ProtectionExchangeFilters:
    payload = {
        "min_amount": Decimal("0.01"),
        "amount_step": Decimal("0.01"),
        "min_notional": Decimal("5"),
        "min_notional_source": "test",
        "tick_size": Decimal("0.1"),
    }
    payload.update(patch)
    return ProtectionExchangeFilters(**payload)


@pytest.mark.asyncio
async def test_missing_price_source_blocks_before_plan_creation():
    repo = MemoryProtectionPlanRepository()
    service = ProtectionPlannerService(repository=repo)

    with pytest.raises(ProtectionPriceSourceUnavailable) as exc_info:
        await service.ensure_pre_entry_plan(_authorization())

    assert str(exc_info.value) == "protection_price_source_missing"
    assert repo.records == []


@pytest.mark.asyncio
async def test_valid_price_snapshot_persists_pre_entry_plan_with_rounding():
    repo = MemoryProtectionPlanRepository()
    service = ProtectionPlannerService(
        repository=repo,
        price_source=StaticProtectionPriceSource(
            reference_price=Decimal("600.12"),
            filters=_filters(),
            source_ref="unit-static",
        ),
    )

    plan = await service.ensure_pre_entry_plan(_authorization())

    assert plan.status == "valid"
    assert plan.phase == "pre_entry_reference"
    assert plan.reference_price == Decimal("600.12")
    assert plan.tp_price == Decimal("606.1")
    assert plan.sl_price == Decimal("594.1")
    assert plan.tp_quantity == Decimal("0.01")
    assert plan.sl_quantity == Decimal("0.01")
    assert plan.rounding["tp_rounding"] == "tick_floor"
    assert plan.filters["tick_size"] == "0.1"
    assert repo.records == [plan]


@pytest.mark.asyncio
async def test_quantity_storage_noise_is_normalized_before_step_validation():
    repo = MemoryProtectionPlanRepository()
    service = ProtectionPlannerService(
        repository=repo,
        price_source=StaticProtectionPriceSource(
            reference_price=Decimal("100.12"),
            filters=_filters(
                min_amount=Decimal("0.1"),
                amount_step=Decimal("0.1"),
                tick_size=Decimal("0.01"),
            ),
        ),
    )

    plan = await service.ensure_pre_entry_plan(
        _authorization(
            carrier_id="TF-001-live-readonly-v0",
            strategy_family_id="TF-001-live-readonly-v0",
            symbol="SOL/USDT:USDT",
            quantity=Decimal("0.100000000000000006"),
        )
    )

    assert plan.status == "valid"
    assert plan.quantity == Decimal("0.1")
    assert plan.tp_quantity == Decimal("0.1")
    assert plan.sl_quantity == Decimal("0.1")


@pytest.mark.asyncio
async def test_exchange_price_source_accepts_tick_size_style_price_precision():
    repo = MemoryProtectionPlanRepository()
    gateway = FakeReadOnlyGateway(price_precision=Decimal("0.01"))
    service = ProtectionPlannerService(
        repository=repo,
        price_source=ExchangeGatewayProtectionPriceSource(gateway=gateway),
    )

    plan = await service.ensure_pre_entry_plan(_authorization())

    assert plan.status == "valid"
    assert plan.tick_size == Decimal("0.01")
    assert plan.tp_price == Decimal("606.12")
    assert plan.sl_price == Decimal("594.11")
    assert plan.filters["tick_size"] == "0.01"
    assert plan.filters["price_precision"] is None
    assert gateway.write_calls == []


@pytest.mark.asyncio
async def test_exchange_price_source_keeps_integer_price_precision_metadata():
    repo = MemoryProtectionPlanRepository()
    gateway = FakeReadOnlyGateway(price_precision=2)
    service = ProtectionPlannerService(
        repository=repo,
        price_source=ExchangeGatewayProtectionPriceSource(gateway=gateway),
    )

    plan = await service.ensure_pre_entry_plan(_authorization())

    assert plan.status == "valid"
    assert plan.tick_size == Decimal("0.01")
    assert plan.filters["price_precision"] == "2"


@pytest.mark.asyncio
async def test_fill_based_plan_uses_actual_avg_fill_price():
    repo = MemoryProtectionPlanRepository()
    service = ProtectionPlannerService(
        repository=repo,
        price_source=StaticProtectionPriceSource(reference_price=Decimal("600"), filters=_filters()),
    )

    plan = await service.create_fill_based_plan(
        _authorization(),
        fill_price=Decimal("601.23"),
        filters=_filters(tick_size=Decimal("0.01")),
        source_ref="entry_order:avg_fill",
    )

    assert plan.phase == "post_entry_fill"
    assert plan.fill_price == Decimal("601.23")
    assert plan.reference_price is None
    assert plan.tp_price == Decimal("607.24")
    assert plan.sl_price == Decimal("595.21")
    assert plan.price_source_type == "exchange_order_fill_avg"
    assert plan.source_ref == "entry_order:avg_fill"


@pytest.mark.asyncio
async def test_filter_failure_blocks_unprotectable_quantity():
    repo = MemoryProtectionPlanRepository()
    service = ProtectionPlannerService(
        repository=repo,
        price_source=StaticProtectionPriceSource(
            reference_price=Decimal("600"),
            filters=_filters(min_amount=Decimal("0.02")),
        ),
    )

    with pytest.raises(ProtectionPriceSourceUnavailable) as exc_info:
        await service.ensure_pre_entry_plan(_authorization())

    assert str(exc_info.value) == "entry_quantity_cannot_create_valid_sl"
    assert repo.records[0].status == "blocked"
    assert repo.records[0].blockers == ["entry_quantity_cannot_create_valid_sl"]


@pytest.mark.asyncio
async def test_wrong_carrier_or_symbol_is_rejected():
    repo = MemoryProtectionPlanRepository()
    service = ProtectionPlannerService(
        repository=repo,
        price_source=StaticProtectionPriceSource(reference_price=Decimal("600"), filters=_filters()),
    )

    with pytest.raises(ProtectionPriceSourceUnavailable) as exc_info:
        await service.ensure_pre_entry_plan(_authorization(symbol="SOL/USDT:USDT"))

    assert str(exc_info.value) == "protection_planner_scope_mismatch"


@pytest.mark.asyncio
async def test_planner_accepts_non_bnb_carrier_when_configured():
    repo = MemoryProtectionPlanRepository()
    custom_config = ProtectionPlannerConfig(
        carrier_id="GENERIC-TEST-LONG",
        symbol="TEST/USDT:USDT",
        side="long",
        stop_loss_fraction=Decimal("0.02"),
        tp_targets_pct=(Decimal("2.0"),),
        tp_ratios=(Decimal("1.0"),),
    )
    service = ProtectionPlannerService(
        repository=repo,
        price_source=StaticProtectionPriceSource(
            reference_price=Decimal("10.11"),
            filters=_filters(min_notional=Decimal("0.01")),
        ),
        configs={custom_config.carrier_id: custom_config},
    )

    plan = await service.ensure_pre_entry_plan(
        _authorization(
            carrier_id="GENERIC-TEST-LONG",
            symbol="TEST/USDT:USDT",
            strategy_family_id="GENERIC",
            max_notional=Decimal("1"),
        )
    )

    assert plan.carrier_id == "GENERIC-TEST-LONG"
    assert plan.tp_price == Decimal("10.3")
    assert plan.sl_price == Decimal("9.9")
