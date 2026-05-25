from __future__ import annotations

from decimal import Decimal

import pytest

from src.application.account_risk_service import AccountRiskService, AccountRiskState
from src.domain.models import PositionInfo


SYMBOL = "ETH/USDT:USDT"


class _AccountService:
    def __init__(self, balance=Decimal("1000"), *, fail: bool = False) -> None:
        self.balance = balance
        self.fail = fail

    async def get_balance(self):
        if self.fail:
            raise RuntimeError("balance unavailable")
        return self.balance


class _Gateway:
    def __init__(self, positions=None, *, fail: bool = False) -> None:
        self.positions = positions or []
        self.fail = fail

    async def fetch_positions(self, symbol: str):
        if self.fail:
            raise RuntimeError("positions unavailable")
        return [pos for pos in self.positions if pos.symbol == symbol]


def _position(
    *,
    side: str = "long",
    mark: str = "100",
    liquidation: str | None = "80",
) -> PositionInfo:
    return PositionInfo(
        symbol=SYMBOL,
        side=side,
        size=Decimal("1"),
        entry_price=Decimal("100"),
        mark_price=Decimal(mark),
        unrealized_pnl=Decimal("0"),
        leverage=5,
        liquidation_price=Decimal(liquidation) if liquidation is not None else None,
    )


@pytest.mark.asyncio
async def test_flat_account_allows_new_entry():
    service = AccountRiskService(gateway=_Gateway([]), account_service=_AccountService())

    assessment = await service.evaluate_new_entry(SYMBOL)

    assert assessment.allowed_new_entry
    assert assessment.state == AccountRiskState.HEALTHY
    assert assessment.reason == "ACCOUNT_HEALTHY_FLAT"


@pytest.mark.asyncio
async def test_missing_balance_blocks_fail_closed():
    service = AccountRiskService(
        gateway=_Gateway([]),
        account_service=_AccountService(fail=True),
    )

    assessment = await service.evaluate_new_entry(SYMBOL)

    assert not assessment.allowed_new_entry
    assert assessment.state == AccountRiskState.UNKNOWN
    assert assessment.reason == "ACCOUNT_BALANCE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_missing_liquidation_price_blocks_as_degraded():
    service = AccountRiskService(
        gateway=_Gateway([_position(liquidation=None)]),
        account_service=_AccountService(),
    )

    assessment = await service.evaluate_new_entry(SYMBOL)

    assert not assessment.allowed_new_entry
    assert assessment.state == AccountRiskState.DEGRADED
    assert assessment.reason == "LIQUIDATION_PRICE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_liquidation_distance_thresholds_are_side_aware():
    degraded = AccountRiskService(
        gateway=_Gateway([_position(side="short", mark="100", liquidation="108")]),
        account_service=_AccountService(),
    )
    critical = AccountRiskService(
        gateway=_Gateway([_position(side="long", mark="100", liquidation="97")]),
        account_service=_AccountService(),
    )
    healthy = AccountRiskService(
        gateway=_Gateway([_position(side="long", mark="100", liquidation="70")]),
        account_service=_AccountService(),
    )

    degraded_assessment = await degraded.evaluate_new_entry(SYMBOL)
    critical_assessment = await critical.evaluate_new_entry(SYMBOL)
    healthy_assessment = await healthy.evaluate_new_entry(SYMBOL)

    assert degraded_assessment.reason == "LIQUIDATION_DISTANCE_DEGRADED"
    assert not degraded_assessment.allowed_new_entry
    assert critical_assessment.reason == "LIQUIDATION_DISTANCE_CRITICAL"
    assert not critical_assessment.allowed_new_entry
    assert healthy_assessment.reason == "ACCOUNT_HEALTHY_POSITION"
    assert healthy_assessment.allowed_new_entry
