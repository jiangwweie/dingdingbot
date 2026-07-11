from __future__ import annotations

import pytest

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
