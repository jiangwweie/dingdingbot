from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.exceptions import InvalidOrderError
from src.infrastructure.exchange_gateway import ExchangeGateway


SYMBOL = "ETH/USDT:USDT"


def _gateway(rest_exchange) -> ExchangeGateway:
    gateway = ExchangeGateway.__new__(ExchangeGateway)
    gateway.exchange_name = "binance"
    gateway.rest_exchange = rest_exchange
    return gateway


class _PositionRest:
    def __init__(self, rows):
        self.rows = rows

    async def fetch_positions(self):
        return self.rows


@pytest.mark.asyncio
async def test_complete_position_rows_preserve_zero_and_position_side():
    gateway = _gateway(
        _PositionRest(
            [
                {
                    "symbol": SYMBOL,
                    "side": "long",
                    "contracts": 0,
                    "info": {"positionSide": "LONG"},
                },
                {
                    "symbol": SYMBOL,
                    "side": "short",
                    "contracts": "0.25",
                    "info": {"positionSide": "SHORT"},
                },
                {
                    "symbol": "BTC/USDT:USDT",
                    "side": "long",
                    "contracts": "1",
                    "info": {"positionSide": "LONG"},
                },
            ]
        )
    )

    rows = await gateway.fetch_position_rows(SYMBOL)

    assert [(row["position_side"], row["size"]) for row in rows] == [
        ("LONG", "0"),
        ("SHORT", "0.25"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row",
    [
        None,
        {"symbol": SYMBOL},
        {"symbol": "", "contracts": "0"},
        {"symbol": SYMBOL, "contracts": "not-a-number"},
    ],
)
async def test_complete_position_rows_reject_malformed_target_truth(row):
    gateway = _gateway(_PositionRest([row]))

    with pytest.raises(RuntimeError, match="exchange_position"):
        await gateway.fetch_position_rows(SYMBOL)


class _LeverageRest:
    def __init__(self, *, open_qty: str = "0", readback: int | None = 7):
        self.open_qty = open_qty
        self.readback = readback
        self.configured = 2
        self.events: list[str] = []

    async def fetch_positions(self):
        self.events.append("fetch_positions")
        leverage = self.configured if self.readback is not None else None
        return [
            {
                "symbol": SYMBOL,
                "side": "long",
                "contracts": self.open_qty,
                "leverage": leverage,
                "info": {"positionSide": "BOTH", "leverage": leverage},
            }
        ]

    async def set_leverage(self, leverage, symbol):
        self.events.append(f"set_leverage:{leverage}:{symbol}")
        if self.readback == leverage:
            self.configured = leverage
        return {"leverage": leverage}

    async def create_order(self, **kwargs):
        self.events.append("create_order")
        return {"id": "entry-1", "status": "open", "filled": "0"}


@pytest.mark.asyncio
async def test_entry_leverage_is_set_then_read_back_before_create_order():
    rest = _LeverageRest(readback=7)
    gateway = _gateway(rest)

    result = await gateway.place_order(
        symbol=SYMBOL,
        order_type="market",
        side="buy",
        amount=Decimal("0.01"),
        desired_leverage=7,
    )

    assert rest.events == [
        "fetch_positions",
        f"set_leverage:7:{SYMBOL}",
        "fetch_positions",
        "create_order",
    ]
    assert result.selected_leverage == 7
    assert result.exchange_configured_initial_leverage == 7


@pytest.mark.asyncio
@pytest.mark.parametrize("readback", [None, 5])
async def test_missing_or_mismatched_leverage_readback_blocks_entry(readback):
    rest = _LeverageRest(readback=readback)
    gateway = _gateway(rest)

    with pytest.raises(InvalidOrderError, match="leverage"):
        await gateway.place_order(
            symbol=SYMBOL,
            order_type="market",
            side="buy",
            amount=Decimal("0.01"),
            desired_leverage=7,
        )

    assert "create_order" not in rest.events


@pytest.mark.asyncio
async def test_open_exact_position_blocks_leverage_mutation_and_entry():
    rest = _LeverageRest(open_qty="0.25", readback=7)
    gateway = _gateway(rest)

    with pytest.raises(InvalidOrderError, match="open_position"):
        await gateway.place_order(
            symbol=SYMBOL,
            order_type="market",
            side="buy",
            amount=Decimal("0.01"),
            desired_leverage=7,
        )

    assert rest.events == ["fetch_positions"]


class _ExposureRest:
    def __init__(self, *, margin_balance: str | None):
        self.margin_balance = margin_balance

    async def fetch_balance(self):
        return {
            "info": {"totalMarginBalance": self.margin_balance},
            "total": {"USDT": self.margin_balance},
        }

    async def fetch_positions(self):
        return [
            {
                "symbol": SYMBOL,
                "contracts": "0.25",
                "markPrice": "2000",
                "contractSize": "1",
            },
            {
                "symbol": "BTC/USDT:USDT",
                "contracts": "0.01",
                "markPrice": "60000",
                "contractSize": "1",
            },
            {
                "symbol": "SOL/USDT:USDT",
                "contracts": "0",
                "markPrice": "150",
                "contractSize": "1",
            },
        ]


@pytest.mark.asyncio
async def test_account_exposure_uses_cross_margin_gross_open_notional_decimal():
    gateway = _gateway(_ExposureRest(margin_balance="100"))

    snapshot = await gateway.fetch_account_exposure_snapshot()

    assert snapshot["status"] == "ready"
    assert snapshot["account_margin_balance"] == "100"
    assert snapshot["gross_open_position_notional"] == "1100.00"
    assert snapshot["effective_account_exposure_leverage"] == "11.00"
    assert snapshot["blockers"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("margin_balance", [None, "0"])
async def test_account_exposure_keeps_effective_leverage_null_without_margin_balance(
    margin_balance,
):
    gateway = _gateway(_ExposureRest(margin_balance=margin_balance))

    snapshot = await gateway.fetch_account_exposure_snapshot()

    assert snapshot["effective_account_exposure_leverage"] is None
    assert snapshot["blockers"] == ["account_margin_balance_missing_or_zero"]
