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
