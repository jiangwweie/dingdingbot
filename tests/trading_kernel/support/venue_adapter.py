"""Minimal exchange fake shared by adapter integration tests."""

from __future__ import annotations

from collections.abc import Mapping


class FakeAsyncExchange:
    def __init__(self) -> None:
        self.call = None

    async def create_order(self, symbol, order_type, side, amount, price, params):
        self.call = (symbol, order_type, side, amount, price, params)
        return {
            "id": "venue-order-1",
            "status": "open",
            "clientOrderId": params["newClientOrderId"],
        }

    def load_markets(self, reload: bool = False) -> object:
        del reload
        return {}

    def market(self, symbol: str) -> Mapping[str, object]:
        raise AssertionError(f"unexpected market lookup for {symbol}")

    async def set_leverage(
        self, leverage: int, symbol: str, params: Mapping[str, object]
    ):
        del leverage, symbol, params
        raise AssertionError("unexpected leverage mutation")

    async def cancel_order(
        self, order_id: str, symbol: str, params: Mapping[str, object]
    ):
        del order_id, symbol, params
        raise AssertionError("unexpected order cancellation")

    async def fetch_order(
        self, order_id: object, symbol: str, params: Mapping[str, object]
    ):
        del order_id, symbol, params
        raise AssertionError("unexpected order lookup")

    async def fetch_positions(self, symbols: list[str], params: Mapping[str, object]):
        del symbols, params
        raise AssertionError("unexpected position lookup")

    async def fapiPrivateV2GetPositionRisk(self, params: Mapping[str, object]):
        del params
        raise AssertionError("unexpected position-risk lookup")

    async def fapiPublicGetPremiumIndex(self, params: Mapping[str, object]):
        del params
        raise AssertionError("unexpected premium-index lookup")

    async def fapiPrivateV2GetAccount(self, params: Mapping[str, object]):
        del params
        raise AssertionError("unexpected account lookup")

    async def fetch_my_trades(
        self, symbol: str, since: object, limit: int, params: Mapping[str, object]
    ):
        del symbol, since, limit, params
        raise AssertionError("unexpected trade lookup")

    async def fetch_open_orders(
        self,
        symbol: str | None,
        since: object,
        limit: int,
        params: Mapping[str, object],
    ):
        del symbol, since, limit, params
        raise AssertionError("unexpected open-order lookup")

    async def fetch_order_book(self, symbol: str, limit: int):
        del symbol, limit
        raise AssertionError("unexpected order-book lookup")

    async def fetch_balance(self, params: Mapping[str, object]):
        del params
        raise AssertionError("unexpected balance lookup")

    async def fetch_position_mode(self, symbol: str, params: Mapping[str, object]):
        del symbol, params
        raise AssertionError("unexpected position-mode lookup")

    async def fetch_ohlcv(self, symbol: str, timeframe: str, since: object, limit: int):
        del symbol, timeframe, since, limit
        raise AssertionError("unexpected candle lookup")

    async def close(self) -> object:
        return None


class AdmissionSnapshotExchange(FakeAsyncExchange):
    def __init__(self) -> None:
        self.markets_loaded = False
        self.position_calls: list[tuple[list[str], dict[str, object]]] = []
        self.position_risk_calls: list[dict[str, object]] = []
        self.order_calls: list[tuple[str | None, dict[str, object]]] = []

    def load_markets(self, reload: bool = False) -> object:
        assert reload is False
        self.markets_loaded = True
        return {}

    async def fetch_order_book(self, symbol, limit):
        assert symbol == "SOL/USDT:USDT"
        assert limit == 5
        return {"bids": [["99.9", "1"]], "asks": [["100.1", "1"]]}

    async def fetch_balance(self, params):
        assert params == {"type": "future"}
        return {
            "info": {
                "totalWalletBalance": "1200",
                "totalMarginBalance": "1198",
                "totalInitialMargin": "250",
                "totalMaintMargin": "13",
                "availableBalance": "948",
            }
        }

    async def fapiPrivateV2GetAccount(self, params):
        assert params == {}
        return {
            "multiAssetsMargin": False,
            "totalWalletBalance": "1200",
            "totalMarginBalance": "1198",
            "totalInitialMargin": "250",
            "totalMaintMargin": "13",
            "availableBalance": "948",
            "positions": [
                {
                    "symbol": "SOLUSDT",
                    "positionSide": "LONG",
                    "positionAmt": "0",
                    "entryPrice": "0",
                    "unrealizedProfit": "0",
                    "maintMargin": "0",
                },
                {
                    "symbol": "SOLUSDT",
                    "positionSide": "SHORT",
                    "positionAmt": "-0.25",
                    "entryPrice": "101",
                    "unrealizedProfit": "0.25",
                    "maintMargin": "1",
                },
                {
                    "symbol": "BTCUSDT",
                    "positionSide": "LONG",
                    "positionAmt": "0.01",
                    "entryPrice": "60000",
                    "unrealizedProfit": "1",
                    "maintMargin": "3",
                },
            ],
        }

    async def fetch_position_mode(self, symbol, params):
        assert self.markets_loaded is True
        assert symbol == "SOL/USDT:USDT"
        assert params == {}
        return {"hedged": True}

    async def fetch_positions(self, symbols, params):
        self.position_calls.append((list(symbols), dict(params)))
        return [
            {
                "symbol": "SOL/USDT:USDT",
                "contracts": "0.25",
                "entryPrice": "101",
                "side": "short",
                "info": {
                    "positionSide": "SHORT",
                    "marginType": "cross",
                    "leverage": "4",
                    "markPrice": "100",
                },
            },
            {
                "symbol": "BTC/USDT:USDT",
                "contracts": "0.01",
                "entryPrice": "60000",
                "side": "long",
                "info": {
                    "positionSide": "LONG",
                    "marginType": "cross",
                    "leverage": "3",
                    "markPrice": "60100",
                },
            },
        ]

    async def fapiPrivateV2GetPositionRisk(self, params):
        self.position_risk_calls.append(dict(params))
        assert params == {"symbol": "SOLUSDT"}
        return [
            {
                "symbol": "SOLUSDT",
                "positionAmt": "0.000",
                "markPrice": "100",
                "leverage": "4",
                "marginType": "cross",
                "positionSide": "LONG",
            },
            {
                "symbol": "SOLUSDT",
                "positionAmt": "-0.250",
                "entryPrice": "101",
                "markPrice": "100",
                "leverage": "4",
                "marginType": "cross",
                "positionSide": "SHORT",
            },
        ]

    async def fetch_open_orders(self, symbol, since, limit, params):
        del since
        assert symbol is None
        assert limit == 1_000
        self.order_calls.append((symbol, dict(params)))
        suffix = "conditional" if params["conditional"] else "regular"
        return [
            {
                "id": f"{suffix}-btc-order",
                "clientOrderId": None,
                "symbol": "BTC/USDT:USDT",
                "reduceOnly": False,
                "info": {"positionSide": "LONG"},
            }
        ]


class InstrumentRulesExchange(FakeAsyncExchange):
    def __init__(self) -> None:
        self.loaded = False

    def load_markets(self, reload: bool = False) -> object:
        assert reload is False
        self.loaded = True
        return {}

    def market(self, symbol):
        assert self.loaded is True
        assert symbol == "BTC/USDT:USDT"
        return {
            "info": {
                "filters": [
                    {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                    {"filterType": "PRICE_FILTER", "tickSize": "0.1"},
                    {"filterType": "MIN_NOTIONAL", "notional": "5"},
                ]
            },
            "limits": {"leverage": {"max": 20}},
        }

    async def fapiPrivateGetLeverageBracket(self, params):
        assert params == {"symbol": "BTCUSDT"}
        return [
            {
                "symbol": "BTCUSDT",
                "brackets": [
                    {
                        "bracket": 1,
                        "initialLeverage": 20,
                        "notionalFloor": "0",
                        "notionalCap": "50000",
                        "maintMarginRatio": "0.004",
                        "cum": "0",
                    },
                    {
                        "bracket": 2,
                        "initialLeverage": 10,
                        "notionalFloor": "50000",
                        "notionalCap": "0",
                        "maintMarginRatio": "0.005",
                        "cum": "50",
                    },
                ],
            }
        ]
