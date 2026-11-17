"""Minimal exchange fake shared by adapter integration tests."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal


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


class OwnerContinuationExchange:
    """Protocol-shaped readonly close/stop facts, with no exchange write API."""

    def __init__(self, *, quantity, stop_price, stop_id='stop-remaining', stop_client='stop-client', entry_id='venue-entry-1', now_ms=20000000):
        self.quantity, self.stop_price = str(quantity), str(stop_price)
        self.stop_id, self.stop_client, self.entry_id = stop_id, stop_client, entry_id
        self.now_ms = now_ms
        self.stop_reads = 0
        self.stop_changes = {}
        self.contract_fault = None
        self.latest_close = '60000'

    async def fetch_ohlcv(self,symbol,timeframe,since,limit):
        period=3600000 if timeframe=='1h' else 900000
        last_close=self.now_ms//period*period
        return [[last_close-(limit-i)*period,'60000',str(max(Decimal(60100),Decimal(self.latest_close))),str(min(Decimal(59900),Decimal(self.latest_close))),self.latest_close,'10'] for i in range(limit)]

    async def fetch_positions(self, symbols, params):
        return [{'symbol':symbols[0],'contracts':self.quantity,'entryPrice':'60000',
                 'markPrice':'63000','info':{'positionSide':params['positionSide']}}]

    async def fetch_my_trades(self, symbol, since, limit, params):
        assert params['orderId']==self.entry_id
        return [{'id':'entry-fill','order':self.entry_id,'amount':str(Decimal(self.quantity)*2),
                 'price':'60000','fee':{'cost':'.01','currency':'USDT'},'timestamp':2000,
                 'info':{'positionSide':'LONG','commission':'.01','commissionAsset':'USDT'}}]

    async def fapiPublicV2GetTickerPrice(self, params):
        assert params=={'symbol':'BTCUSDT'}
        if self.contract_fault=='timeout':raise TimeoutError('test condition price timeout')
        if self.contract_fault=='stale':return {'symbol':'BTCUSDT','price':'62000','time':1}
        if self.contract_fault=='invalid':return {'symbol':'BTCUSDT','price':'NaN','time':self.now_ms}
        return {'symbol':'BTCUSDT','price':'62000','time':self.now_ms}

    async def fetch_open_orders(self, symbol, since, limit, params):
        assert params=={'conditional':True}
        self.stop_reads+=1
        raw={'algoId':self.stop_id,'clientAlgoId':self.stop_client,'algoStatus':'NEW',
            'symbol':'BTCUSDT','side':'SELL','positionSide':'LONG','orderType':'STOP_MARKET',
            'quantity':self.quantity,'price':'0','triggerPrice':self.stop_price,'timeInForce':'GTC',
            'reduceOnly':False,'closePosition':False,'workingType':'CONTRACT_PRICE','priceProtect':False,
            'priceMatch':'NONE','selfTradePreventionMode':'NONE','goodTillDate':0,
            'createTime':3000,'updateTime':3000,**self.stop_changes}
        return [{'id':self.stop_id,'clientOrderId':self.stop_client,'symbol':symbol,
                 'side':'sell','amount':self.quantity,'reduceOnly':False,'info':raw}]
