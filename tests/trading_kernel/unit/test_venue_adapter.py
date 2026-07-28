from __future__ import annotations

from decimal import Decimal
import inspect

from ccxt.base.errors import RequestTimeout
import pytest

from src.trading_kernel.application.certify_universe_instrument import (
    InstrumentCertificationReadRequest,
    InstrumentCertificationTransientFailure,
)
from src.trading_kernel.application.ports import (
    InstrumentCertificationTarget,
    LeverageTruthRequest,
    VenueCommandRequest,
    VenueMutationFailure,
    VenueSetLeverageRequest,
    VenueTruthRequest,
)
from src.trading_kernel.application.runtime_facts import (
    EntryAdmissionSnapshotRequest,
    InstrumentRulesRequest,
    LifecycleFactsRequest,
    PositionSnapshotRequest,
    ReviewEconomicsRequest,
)
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommandKind,
    ExchangeCommandStatus,
    OrderCommandPayload,
    SetLeverageCommandPayload,
)
from src.trading_kernel.domain.identities import NettingDomain
from src.trading_kernel.domain.instrument_certification import (
    classify_instrument_certification,
)
from src.trading_kernel.domain.entry_admission_snapshot import (
    AdmissionOwnership,
    OwnedPositionProjection,
)
from src.trading_kernel.domain.order_attribution import (
    OrderNamespace,
    OrderRole,
    TicketOrderReference,
)
from src.trading_kernel.domain.venue_truth import VenueLookupStatus
from src.trading_kernel.infrastructure.venue_adapter import (
    CcxtVenueAdapter,
    InstrumentCertificationSnapshotContradiction,
    _binance_maintenance_margin_brackets,
    _position_details,
)


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


class InsufficientFunds(Exception):
    pass


class ExchangeError(Exception):
    pass


def test_ccxt_adapter_rejects_retired_venue_symbol_map() -> None:
    assert "venue_symbols" not in inspect.signature(CcxtVenueAdapter).parameters

    with pytest.raises(TypeError, match="venue_symbols"):
        CcxtVenueAdapter(
            exchanges={},
            venue_symbols={},
            clock_ms=lambda: 2_000,
        )


@pytest.mark.asyncio
async def test_ccxt_adapter_rejects_illegal_instrument_before_account_routing() -> None:
    exchange = FakeAsyncExchange()
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        clock_ms=lambda: 2_000,
    )
    request = _request().model_copy(
        update={
            "account_id": "unconfigured-account",
            "exchange_instrument_id": "OP/USDT:USDT",
        }
    )

    with pytest.raises(
        RuntimeError,
        match="canonical Binance USD-M instrument is unavailable",
    ):
        await adapter.execute(request)

    assert exchange.call is None


def test_position_details_requires_liquidation_evidence_for_every_open_row() -> None:
    quantity, average_entry_price, liquidation_price = _position_details(
        [
            {
                "symbol": "BTC/USDT:USDT",
                "contracts": "0.01",
                "entryPrice": "59000",
                "side": "long",
                "liquidationPrice": "57000",
                "info": {"positionSide": "LONG"},
            },
            {
                "symbol": "BTC/USDT:USDT",
                "contracts": "0.01",
                "entryPrice": "61000",
                "side": "long",
                "info": {"positionSide": "LONG"},
            },
        ],
        expected_symbol="BTC/USDT:USDT",
        position_side="long",
    )

    assert quantity == Decimal("0.02")
    assert average_entry_price == Decimal("60000")
    assert liquidation_price is None


class RejectingExchange:
    async def create_order(self, *args, **kwargs):
        raise InsufficientFunds("sensitive venue message")


class TimingOutExchange:
    async def create_order(self, *args, **kwargs):
        raise TimeoutError("network outcome unknown")


class CancelExchange:
    def __init__(self) -> None:
        self.cancel_call = None

    async def create_order(self, *args, **kwargs):
        raise AssertionError("cancel must not create an order")

    async def cancel_order(self, order_id, symbol, params):
        self.cancel_call = (order_id, symbol, params)
        return {
            "id": order_id,
            "status": "canceled",
            "clientOrderId": "brc-stop-1",
        }


class ConditionalCancelExchange:
    def __init__(self) -> None:
        self.cancel_calls: list[tuple[object, object, object]] = []

    async def cancel_order(self, order_id, symbol, params):
        self.cancel_calls.append((order_id, symbol, params))
        if not params.get("conditional"):
            raise OrderNotFound("regular order namespace has no target")
        return {
            "id": order_id,
            "status": "canceled",
            "clientOrderId": "brc-stop-1",
        }


class RejectingCancelExchange:
    async def cancel_order(self, *args, **kwargs):
        raise InsufficientFunds("sensitive venue message")


class TimingOutCancelExchange:
    async def cancel_order(self, *args, **kwargs):
        raise TimeoutError("network outcome unknown")


class LeverageMutationExchange:
    def __init__(self) -> None:
        self.set_call = None
        self.position_risk_calls: list[dict[str, object]] = []

    async def create_order(self, *args, **kwargs):
        raise AssertionError("SET_LEVERAGE must not create an order")

    async def set_leverage(self, leverage, symbol, params):
        self.set_call = (leverage, symbol, params)
        return {"leverage": leverage}

    async def fetch_positions(self, symbols, params):
        del symbols, params
        raise AssertionError("leverage read-back must include flat position sides")

    async def fapiPrivateV2GetPositionRisk(self, params):
        self.position_risk_calls.append(dict(params))
        assert params == {"symbol": "BTCUSDT"}
        return [
            {
                "symbol": "BTCUSDT",
                "positionAmt": "0",
                "leverage": "4",
                "positionSide": "LONG",
            },
            {
                "symbol": "BTCUSDT",
                "positionAmt": "0",
                "leverage": "4",
                "positionSide": "SHORT",
            },
        ]

    async def fetch_open_orders(self, symbol, since, limit, params):
        assert symbol == "BTC/USDT:USDT"
        assert since is None
        assert limit == 100
        assert params in ({"conditional": False}, {"conditional": True})
        return []


class CodedLeverageFailureExchange(LeverageMutationExchange):
    async def set_leverage(self, leverage, symbol, params):
        del leverage, symbol, params
        raise ExchangeError(
            'binanceusdm {"code":-4164,"msg":"configuration rejected"}'
        )


class OrderNotFound(Exception):
    pass


class TruthExchange:
    def __init__(self, *, visible: bool) -> None:
        self.visible = visible
        self.calls: list[str] = []
        self.fill_params: dict[str, object] | None = None

    async def fetch_order(self, order_id, symbol, params):
        self.calls.append("order")
        if not self.visible:
            raise OrderNotFound("not visible")
        return {
            "id": "venue-order-1",
            "clientOrderId": params["origClientOrderId"],
            "symbol": symbol,
            "status": "open",
            "side": "buy",
            "amount": "0.001",
            "reduceOnly": False,
            "info": {"positionSide": "LONG"},
        }

    async def fetch_positions(self, symbols, params):
        self.calls.append("positions")
        return [
            {
                "symbol": symbols[0],
                "contracts": "0",
                "info": {"positionSide": params["positionSide"]},
            }
        ]

    async def fetch_my_trades(self, symbol, since, limit, params):
        self.fill_params = dict(params)
        self.calls.append("fills")
        return []

    async def fetch_open_orders(self, symbol, since, limit, params):
        self.calls.append(
            "conditional" if params.get("conditional") else "regular"
        )
        return []


class CancelTruthExchange(TruthExchange):
    def __init__(
        self,
        *,
        visible: bool,
        target_in_open: bool = False,
        terminal: bool = False,
    ) -> None:
        super().__init__(visible=visible)
        self.order_lookup = None
        self.target_in_open = target_in_open
        self.terminal = terminal

    async def fetch_order(self, order_id, symbol, params):
        self.calls.append("order")
        self.order_lookup = (order_id, symbol, params)
        if not self.visible:
            raise OrderNotFound("not visible")
        return {
            "id": order_id,
            "clientOrderId": "brc-original-stop",
            "symbol": symbol,
            "status": "canceled" if self.terminal else "open",
            "side": "sell",
            "amount": "0.001",
            "reduceOnly": True,
            "info": {"positionSide": "LONG"},
        }

    async def fetch_open_orders(self, symbol, since, limit, params):
        self.calls.append(
            "conditional" if params.get("conditional") else "regular"
        )
        if self.target_in_open and params.get("conditional"):
            return [
                {
                    "id": "stop-order-1",
                    "clientOrderId": "brc-original-stop",
                    "symbol": symbol,
                    "side": "sell",
                    "amount": "0.001",
                    "reduceOnly": True,
                    "info": {"positionSide": "LONG"},
                }
            ]
        return []


class ActionFactsExchange:
    async def fetch_ticker(self, symbol):
        return {"symbol": symbol, "last": "60000"}

    async def fetch_order_book(self, symbol, limit):
        assert symbol == "BTC/USDT:USDT"
        assert limit == 5
        return {
            "symbol": symbol,
            "bids": [["59999.9", "1"]],
            "asks": [["60000.1", "1"]],
        }

    async def fetch_balance(self, params):
        assert params == {"type": "future"}
        return {
            "total": {"USDT": "1200"},
            "free": {"USDT": "800"},
        }

    async def fetch_position_mode(self, symbol, params):
        assert symbol == "BTC/USDT:USDT"
        assert params == {}
        return {"hedged": True}

    async def fetch_positions(self, symbols, params):
        assert params == {"positionSide": "LONG"}
        return [
            {
                "symbol": symbols[0],
                "contracts": "0.01",
                "entryPrice": "59000",
                "side": "long",
                "info": {"positionSide": "LONG"},
            },
            {
                "symbol": symbols[0],
                "contracts": "0.02",
                "entryPrice": "61000",
                "side": "short",
                "info": {"positionSide": "SHORT"},
            },
        ]

    async def fetch_open_orders(self, symbol, since, limit, params):
        assert symbol == "BTC/USDT:USDT"
        del since, limit
        return [
            {
                "id": f"order-{params['conditional']}-long",
                "clientOrderId": f"brc-{params['conditional']}-long",
                "symbol": symbol,
                "reduceOnly": True,
                "info": {"positionSide": "LONG"},
            },
            {
                "id": f"order-{params['conditional']}-short",
                "clientOrderId": f"brc-{params['conditional']}-short",
                "symbol": symbol,
                "reduceOnly": True,
                "info": {"positionSide": "SHORT"},
            },
        ]


class OneWayActionFactsExchange(ActionFactsExchange):
    async def fetch_position_mode(self, symbol, params):
        assert symbol == "BTC/USDT:USDT"
        assert params == {}
        return {"hedged": False}


class AdmissionSnapshotExchange:
    def __init__(self) -> None:
        self.markets_loaded = False
        self.position_calls: list[tuple[list[str], dict[str, object]]] = []
        self.position_risk_calls: list[dict[str, object]] = []
        self.order_calls: list[tuple[str | None, dict[str, object]]] = []

    async def load_markets(self, reload):
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


class InstrumentRulesExchange:
    def __init__(self) -> None:
        self.loaded = False

    async def load_markets(self, reload):
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


class InstrumentRulesWithoutMarketLeverageExchange(InstrumentRulesExchange):
    def market(self, symbol):
        market = super().market(symbol)
        market["limits"] = {}
        return market


class InstrumentCertificationExchange(InstrumentRulesExchange):
    def __init__(self) -> None:
        super().__init__()
        self.mutations: list[str] = []

    def market(self, symbol):
        market = super().market(symbol)
        market["active"] = True
        market["info"]["status"] = "TRADING"
        return market

    async def fetch_position_mode(self, symbol, params):
        assert symbol == "BTC/USDT:USDT"
        assert params == {}
        return {"hedged": True}

    async def fapiPrivateV2GetPositionRisk(self, params):
        assert params == {"symbol": "BTCUSDT"}
        return [
            {
                "symbol": "BTCUSDT",
                "positionAmt": "0.01",
                "entryPrice": "60000",
                "leverage": "5",
                "marginType": "cross",
                "positionSide": "LONG",
            },
            {
                "symbol": "BTCUSDT",
                "positionAmt": "0",
                "entryPrice": "0",
                "leverage": "5",
                "marginType": "cross",
                "positionSide": "SHORT",
            },
        ]

    async def fetch_open_orders(self, symbol, since, limit, params):
        assert symbol == "BTC/USDT:USDT"
        assert since is None
        assert limit == 100
        if params == {"conditional": False}:
            return []
        assert params == {"conditional": True}
        return [
            {
                "id": "owned-stop-1",
                "clientOrderId": "brc-owned-stop",
                "symbol": symbol,
                "side": "sell",
                "amount": "0.01",
                "reduceOnly": True,
                "info": {"positionSide": "LONG"},
            }
        ]

    async def set_leverage(self, *args, **kwargs):
        del args, kwargs
        self.mutations.append("set_leverage")
        raise AssertionError("readonly certification cannot mutate leverage")

    async def set_margin_mode(self, *args, **kwargs):
        del args, kwargs
        self.mutations.append("set_margin_mode")
        raise AssertionError("readonly certification cannot mutate margin mode")

    async def set_position_mode(self, *args, **kwargs):
        del args, kwargs
        self.mutations.append("set_position_mode")
        raise AssertionError("readonly certification cannot mutate position mode")


class MissingOrderRuleCertificationExchange(InstrumentCertificationExchange):
    def market(self, symbol):
        market = super().market(symbol)
        market["info"]["filters"] = [
            row
            for row in market["info"]["filters"]
            if row["filterType"] not in {"MIN_NOTIONAL", "NOTIONAL"}
        ]
        return market


class InvalidOrderRuleCertificationExchange(InstrumentCertificationExchange):
    def market(self, symbol):
        market = super().market(symbol)
        for row in market["info"]["filters"]:
            if row["filterType"] == "MIN_NOTIONAL":
                row["notional"] = "0"
        return market


class MissingCanonicalFilterWithNormalizedFallbackExchange(
    InstrumentCertificationExchange
):
    def __init__(self, *, missing_filter_type: str) -> None:
        super().__init__()
        self.missing_filter_type = missing_filter_type

    def market(self, symbol):
        market = super().market(symbol)
        market["precision"] = {
            "amount": "0.001",
            "price": "0.1",
        }
        market["limits"].update(
            {
                "amount": {"min": "0.001"},
                "cost": {"min": "5"},
            }
        )
        market["info"]["filters"] = [
            row
            for row in market["info"]["filters"]
            if row["filterType"] != self.missing_filter_type
        ]
        return market


class TransientCertificationExchange(InstrumentCertificationExchange):
    async def fetch_position_mode(self, symbol, params):
        del symbol, params
        raise RequestTimeout("venue request timed out")


class LifecycleFactsExchange:
    def __init__(self) -> None:
        self.tp1_order_calls: list[tuple[object, str, dict[str, object]]] = []

    async def fetch_positions(self, symbols, params):
        return [
            {
                "symbol": symbols[0],
                "contracts": "0.005",
                "entryPrice": "60000",
                "info": {"positionSide": params["positionSide"]},
            }
        ]

    async def fetch_my_trades(self, symbol, since, limit, params):
        del symbol, since, limit
        order_id = params["orderId"]
        if order_id == "venue-entry-1":
            return [
                {
                    "orderId": order_id,
                    "id": "trade-entry-1",
                    "amount": "0.01",
                    "price": "60000",
                    "fee": {"cost": "0.4", "currency": "USDT"},
                    "timestamp": 1_100,
                    "info": {
                        "positionSide": "LONG",
                        "commission": "0.4",
                        "commissionAsset": "USDT",
                    },
                }
            ]
        return [
            {
                # Binance user-trade payloads do not reliably carry the parent
                # order client id. TP1 lifecycle truth must use the exact order.
                "orderId": order_id,
                "id": "trade-exit-1",
                "amount": "0.005",
                "price": "61000",
                "fee": {"cost": "0.15", "currency": "USDT"},
                "timestamp": 1_100,
                "info": {
                    "positionSide": "LONG",
                    "commission": "0.15",
                    "commissionAsset": "USDT",
                },
            }
        ]

    async def fetch_order(self, order_id, symbol, params):
        self.tp1_order_calls.append((order_id, symbol, dict(params)))
        return {
            "id": order_id,
            "symbol": symbol,
            "status": "closed",
            "filled": "0.005",
            "average": "61000",
            "info": {
                "executedQty": "0.005",
                "avgPrice": "61000",
            },
        }

    async def fetch_ohlcv(self, symbol, timeframe, since, limit):
        del symbol, timeframe, since
        return [
            [
                1_000 + index * 900_000,
                "60000",
                str(60010 + index),
                str(59990 + index),
                str(60000 + index),
                "10",
            ]
            for index in range(limit)
        ]


class IncompleteLastLifecycleFactsExchange(LifecycleFactsExchange):
    def __init__(self) -> None:
        super().__init__()
        self.ohlcv_limit: int | None = None

    async def fetch_ohlcv(self, symbol, timeframe, since, limit):
        del symbol, timeframe, since
        self.ohlcv_limit = limit
        latest_open_time_ms = 20_000_000
        return [
            [
                latest_open_time_ms - (limit - 1 - index) * 900_000,
                "60000",
                str(60010 + index),
                str(59990 + index),
                str(60000 + index),
                "10",
            ]
            for index in range(limit)
        ]


class BnbLifecycleFactsExchange(LifecycleFactsExchange):
    async def fetch_my_trades(self, symbol, since, limit, params):
        rows = await super().fetch_my_trades(symbol, since, limit, params)
        for row in rows:
            row["fee"] = {"cost": "0.01", "currency": "BNB"}
            row["info"]["commission"] = "0.01"
            row["info"]["commissionAsset"] = "BNB"
        return rows

class ReviewEconomicsExchange:
    def __init__(self, *, include_fee: bool = True) -> None:
        self.include_fee = include_fee
        self.trade_calls: list[tuple[str, int | None, int, dict[str, object]]] = []
        self.funding_calls: list[dict[str, object]] = []

    async def fetch_my_trades(self, symbol, since, limit, params):
        assert symbol == "BTC/USDT:USDT"
        assert since == 1_000
        assert limit == 100
        self.trade_calls.append((symbol, since, limit, dict(params)))
        fee = {"cost": "0.1", "currency": "USDT"}
        rows = [
            {
                "id": "trade-entry",
                "orderId": "venue-entry-1",
                "amount": "1",
                "price": "100",
                "fee": fee if self.include_fee else None,
                "timestamp": 1_100,
                "info": {
                    "positionSide": "LONG",
                    "commission": "0.1",
                    "commissionAsset": "USDT",
                },
            },
            {
                "id": "trade-tp1",
                "orderId": "venue-tp1-1",
                "amount": "0.5",
                "price": "110",
                "fee": {"cost": "0.05", "currency": "USDT"},
                "timestamp": 2_000,
                "info": {
                    "positionSide": "LONG",
                    "commission": "0.05",
                    "commissionAsset": "USDT",
                },
            },
            {
                "id": "trade-runner",
                "orderId": "venue-runner-actual-1",
                "amount": "0.5",
                "price": "120",
                "fee": {"cost": "0.05", "currency": "USDT"},
                "timestamp": 3_000,
                "info": {
                    "positionSide": "LONG",
                    "commission": "0.05",
                    "commissionAsset": "USDT",
                },
            },
            {
                "id": "unrelated-trade",
                "orderId": "manual-order",
                "amount": "10",
                "price": "1",
                "fee": {"cost": "1", "currency": "USDT"},
                "timestamp": 2_500,
                "info": {
                    "positionSide": "LONG",
                    "commission": "1",
                    "commissionAsset": "USDT",
                },
            },
        ]
        if not self.include_fee:
            for row in rows:
                row["info"].pop("commission", None)
                row["info"].pop("commissionAsset", None)
        order_id = str(params.get("orderId") or "")
        return [row for row in rows if row["orderId"] == order_id]

    async def fapiPrivateGetAlgoOrder(self, params):
        assert params == {"algoId": "venue-runner-algo-1"}
        return {
            "algoId": "venue-runner-algo-1",
            "clientAlgoId": "brc-runner-1",
            "actualOrderId": "venue-runner-actual-1",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "positionSide": "LONG",
            "type": "STOP_MARKET",
            "actualQty": "0.5",
            "status": "FINISHED",
        }

    async def fapiPrivateGetIncome(self, params):
        self.funding_calls.append(dict(params))
        return [
            {
                "tranId": "funding-1",
                "incomeType": "FUNDING_FEE",
                "symbol": "BTCUSDT",
                "income": "-0.3",
                "asset": "USDT",
                "time": 2_500,
            }
        ]


class BnbReviewEconomicsExchange(ReviewEconomicsExchange):
    def __init__(self) -> None:
        super().__init__()
        self.index_snapshot_calls: list[dict[str, object]] = []

    async def fetch_my_trades(self, symbol, since, limit, params):
        rows = await super().fetch_my_trades(symbol, since, limit, params)
        for row in rows:
            row["fee"] = {"cost": "0.01", "currency": "BNB"}
            row["info"]["commission"] = "0.01"
            row["info"]["commissionAsset"] = "BNB"
        return rows

    async def fapiPublicGetPremiumIndex(self, params):
        self.index_snapshot_calls.append(dict(params))
        return {"symbol": "BNBUSDT", "indexPrice": "600", "time": 4_000}


class WrongOrderReviewEconomicsExchange(ReviewEconomicsExchange):
    async def fetch_my_trades(self, symbol, since, limit, params):
        rows = await super().fetch_my_trades(symbol, since, limit, params)
        return [
            *rows,
            {
                "id": "wrong-order-trade",
                "orderId": "manual-order",
                "amount": "0.5",
                "price": "120",
                "fee": {"cost": "0.05", "currency": "USDT"},
                "timestamp": 3_000,
                "info": {"positionSide": "LONG"},
            },
        ]


class InvalidRawFeeReviewEconomicsExchange(ReviewEconomicsExchange):
    def __init__(self, *, fee: object) -> None:
        super().__init__()
        self._fee = fee

    async def fetch_my_trades(self, symbol, since, limit, params):
        rows = await super().fetch_my_trades(symbol, since, limit, params)
        for row in rows:
            row["fee"] = self._fee
            if isinstance(self._fee, dict):
                row["info"]["commission"] = self._fee.get("cost")
                if "currency" in self._fee:
                    row["info"]["commissionAsset"] = self._fee["currency"]
                else:
                    row["info"].pop("commissionAsset", None)
        return rows


class FeeDiscountCapabilityExchange:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def fapiPrivateGetFeeBurn(self, params):
        self.calls.append(("fee_burn", dict(params)))
        return {"feeBurn": True}

    async def fetch_balance(self, params):
        self.calls.append(("balance", dict(params)))
        return {"total": {"BNB": "0.02"}}

@pytest.mark.asyncio
async def test_ccxt_adapter_sends_explicit_hedge_side_and_client_identity() -> None:
    exchange = FakeAsyncExchange()
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        clock_ms=lambda: 2_000,
    )

    result = await adapter.execute(_request())

    assert result.status is ExchangeCommandStatus.ACCEPTED
    assert result.exchange_order_id == "venue-order-1"
    assert exchange.call == (
        "BTC/USDT:USDT",
        "market",
        "buy",
        Decimal("0.001"),
        None,
        {
            "newClientOrderId": "brc-entry-1",
            "positionSide": "LONG",
        },
    )


@pytest.mark.asyncio
async def test_ccxt_adapter_submits_tp1_limit_with_gtx_time_in_force() -> None:
    exchange = FakeAsyncExchange()
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        clock_ms=lambda: 2_000,
    )
    request = _request().model_copy(
        update={
            "command_id": "command:tp1-1",
            "kind": ExchangeCommandKind.TAKE_PROFIT,
            "venue_client_order_id": "brc-tp1-1",
            "payload": OrderCommandPayload(
                side="sell",
                quantity=Decimal("0.001"),
                order_type="limit",
                reduce_only=True,
                limit_price=Decimal("60100"),
                time_in_force="GTX",
            ),
        }
    )

    await adapter.execute(request)

    assert exchange.call is not None
    assert exchange.call[-1] == {
        "newClientOrderId": "brc-tp1-1",
        "positionSide": "LONG",
        "timeInForce": "GTX",
    }


@pytest.mark.asyncio
async def test_ccxt_adapter_sets_leverage_then_reads_back_without_creating_order() -> None:
    exchange = LeverageMutationExchange()
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        clock_ms=lambda: 2_000,
    )

    result = await adapter.set_leverage(
        VenueSetLeverageRequest(
            command_id="command:leverage-1",
            venue_id="binance-usdm",
            account_id="experiment-1",
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            payload=SetLeverageCommandPayload(
                desired_leverage=4,
                owner_policy_version=1,
                entry_admission_snapshot_digest="sha256:" + "1" * 64,
                leverage_fact_digest="sha256:" + "2" * 64,
            ),
            deadline_at_ms=30_000,
        )
    )

    assert exchange.set_call == (4, "BTC/USDT:USDT", {})
    assert result.exchange_configured_leverage == 4
    assert result.leverage_verified_at_ms == 2_000
    assert result.leverage_verification_digest.startswith("sha256:")
    assert exchange.position_risk_calls == [{"symbol": "BTCUSDT"}]


@pytest.mark.asyncio
async def test_ccxt_adapter_preserves_only_exchange_code_for_leverage_failure() -> None:
    adapter = CcxtVenueAdapter(
        exchanges={
            ("binance-usdm", "experiment-1"): CodedLeverageFailureExchange()
        },
        clock_ms=lambda: 2_000,
    )

    with pytest.raises(VenueMutationFailure, match="exchange_code_-4164"):
        await adapter.set_leverage(
            VenueSetLeverageRequest(
                command_id="command:leverage-1",
                venue_id="binance-usdm",
                account_id="experiment-1",
                exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
                payload=SetLeverageCommandPayload(
                    desired_leverage=4,
                    owner_policy_version=1,
                    entry_admission_snapshot_digest="sha256:" + "1" * 64,
                    leverage_fact_digest="sha256:" + "2" * 64,
                ),
                deadline_at_ms=30_000,
            )
        )


@pytest.mark.asyncio
async def test_ccxt_adapter_recovers_flat_leverage_truth_from_position_risk() -> None:
    exchange = LeverageMutationExchange()
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        clock_ms=lambda: 2_000,
    )

    truth = await adapter.read_configured_leverage(
        LeverageTruthRequest(
            command_id="command:leverage-1",
            venue_id="binance-usdm",
            account_id="experiment-1",
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            desired_leverage=4,
            observed_at_ms=2_000,
        )
    )

    assert truth.exchange_configured_leverage == 4
    assert truth.long_position_quantity == Decimal("0")
    assert truth.short_position_quantity == Decimal("0")
    assert exchange.position_risk_calls == [{"symbol": "BTCUSDT"}]


@pytest.mark.asyncio
async def test_ccxt_adapter_freezes_one_account_wide_admission_snapshot() -> None:
    exchange = AdmissionSnapshotExchange()
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        settlement_assets={
            ("binance-usdm", "binance-usdm:SOLUSDT:perpetual"): "USDT"
        },
        clock_ms=lambda: 2_000,
    )

    snapshot = await adapter.read_entry_admission_snapshot(
        EntryAdmissionSnapshotRequest(
            venue_id="binance-usdm",
            account_id="experiment-1",
            exchange_instrument_id="binance-usdm:SOLUSDT:perpetual",
            observed_at_ms=2_000,
            valid_for_ms=5_000,
        )
    )

    assert snapshot.position_mode == "independent_sides"
    assert snapshot.margin_mode == "cross"
    assert snapshot.total_wallet_balance == Decimal("1200")
    assert snapshot.total_margin_balance == Decimal("1198")
    assert snapshot.total_initial_margin == Decimal("250")
    assert snapshot.total_maintenance_margin == Decimal("13")
    assert snapshot.available_margin == Decimal("948")
    assert snapshot.best_bid_price == Decimal("99.9")
    assert snapshot.best_ask_price == Decimal("100.1")
    assert snapshot.instrument_facts_for(
        "binance-usdm:SOLUSDT:perpetual"
    ).mark_price == Decimal("100")
    assert snapshot.instrument_facts_for(
        "binance-usdm:SOLUSDT:perpetual"
    ).configured_leverage == 4
    assert {(row.exchange_instrument_id, row.position_side) for row in snapshot.positions} == {
        ("binance-usdm:SOLUSDT:perpetual", "long"),
        ("binance-usdm:SOLUSDT:perpetual", "short"),
        ("binance-usdm:BTCUSDT:perpetual", "long"),
    }
    assert {order.exchange_order_id for order in snapshot.open_orders} == {
        "regular-btc-order",
        "conditional-btc-order",
    }
    assert exchange.position_calls == [([], {})]
    assert exchange.position_risk_calls == [{"symbol": "SOLUSDT"}]
    assert exchange.order_calls == [
        (None, {"conditional": False}),
        (None, {"conditional": True}),
    ]
    assert snapshot.valid_until_ms == 7_000


@pytest.mark.asyncio
async def test_ccxt_adapter_derives_account_wide_binance_instrument_ids_without_map() -> None:
    exchange = AdmissionSnapshotExchange()
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        clock_ms=lambda: 2_000,
    )

    snapshot = await adapter.read_entry_admission_snapshot(
        EntryAdmissionSnapshotRequest(
            venue_id="binance-usdm",
            account_id="experiment-1",
            exchange_instrument_id="binance-usdm:SOLUSDT:perpetual",
            observed_at_ms=2_000,
            valid_for_ms=5_000,
        )
    )

    assert {
        (row.exchange_instrument_id, row.position_side)
        for row in snapshot.positions
    } == {
        ("binance-usdm:SOLUSDT:perpetual", "long"),
        ("binance-usdm:SOLUSDT:perpetual", "short"),
        ("binance-usdm:BTCUSDT:perpetual", "long"),
    }
    assert {
        order.exchange_instrument_id for order in snapshot.open_orders
    } == {"binance-usdm:BTCUSDT:perpetual"}


@pytest.mark.asyncio
async def test_ccxt_adapter_rejects_non_usdt_account_wide_symbol_without_fabricating_identity() -> None:
    exchange = AdmissionSnapshotExchange()

    async def malformed_positions(symbols, params):
        del symbols, params
        return [
            {
                "symbol": "BTC/USDC:USDC",
                "contracts": "0.01",
                "entryPrice": "60000",
                "side": "long",
                "info": {
                    "positionSide": "LONG",
                    "marginType": "cross",
                    "leverage": "3",
                    "markPrice": "60100",
                },
            }
        ]

    exchange.fetch_positions = malformed_positions
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        clock_ms=lambda: 2_000,
    )

    with pytest.raises(RuntimeError, match="canonical Binance USD-M instrument"):
        await adapter.read_entry_admission_snapshot(
            EntryAdmissionSnapshotRequest(
                venue_id="binance-usdm",
                account_id="experiment-1",
                exchange_instrument_id="binance-usdm:SOLUSDT:perpetual",
                observed_at_ms=2_000,
                valid_for_ms=5_000,
            )
        )


@pytest.mark.asyncio
async def test_ccxt_adapter_admits_flat_requested_instrument_from_position_risk() -> None:
    exchange = AdmissionSnapshotExchange()

    async def flat_target_position_risk(params):
        exchange.position_risk_calls.append(dict(params))
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
                "positionAmt": "0.000",
                "markPrice": "100",
                "leverage": "4",
                "marginType": "cross",
                "positionSide": "SHORT",
            },
        ]

    exchange.fapiPrivateV2GetPositionRisk = flat_target_position_risk
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        settlement_assets={
            ("binance-usdm", "binance-usdm:SOLUSDT:perpetual"): "USDT"
        },
        clock_ms=lambda: 2_000,
    )

    snapshot = await adapter.read_entry_admission_snapshot(
        EntryAdmissionSnapshotRequest(
            venue_id="binance-usdm",
            account_id="experiment-1",
            exchange_instrument_id="binance-usdm:SOLUSDT:perpetual",
            observed_at_ms=2_000,
            valid_for_ms=5_000,
        )
    )

    assert snapshot.instrument_facts_for(
        "binance-usdm:SOLUSDT:perpetual"
    ).configured_leverage == 4
    assert {
        (row.exchange_instrument_id, row.position_side, row.quantity)
        for row in snapshot.positions
    } == {
        ("binance-usdm:SOLUSDT:perpetual", "long", Decimal("0")),
        ("binance-usdm:SOLUSDT:perpetual", "short", Decimal("0")),
        ("binance-usdm:BTCUSDT:perpetual", "long", Decimal("0.01")),
    }


@pytest.mark.asyncio
async def test_ccxt_adapter_reads_typed_leverage_and_maintenance_rules() -> None:
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): InstrumentRulesExchange()},
        clock_ms=lambda: 2_000,
    )

    facts = await adapter.read_instrument_rules(
        InstrumentRulesRequest(
            venue_id="binance-usdm",
            account_id="experiment-1",
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            observed_at_ms=2_000,
            valid_for_ms=5_000,
        )
    )

    assert facts.exchange_max_leverage == 20
    assert tuple(item.bracket_id for item in facts.maintenance_margin_brackets) == (
        "binance-usdm:BTCUSDT:1",
        "binance-usdm:BTCUSDT:2",
    )
    assert facts.maintenance_margin_brackets[1].maintenance_amount == Decimal("50")
    assert facts.maintenance_margin_brackets_digest.startswith("sha256:")


@pytest.mark.asyncio
async def test_ccxt_adapter_uses_bracket_leverage_when_market_limit_is_absent() -> None:
    adapter = CcxtVenueAdapter(
        exchanges={
            ("binance-usdm", "experiment-1"): (
                InstrumentRulesWithoutMarketLeverageExchange()
            )
        },
        clock_ms=lambda: 2_000,
    )

    facts = await adapter.read_instrument_rules(
        InstrumentRulesRequest(
            venue_id="binance-usdm",
            account_id="experiment-1",
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            observed_at_ms=2_000,
            valid_for_ms=5_000,
        )
    )

    assert facts.exchange_max_leverage == 20


@pytest.mark.asyncio
async def test_ccxt_adapter_certification_is_readonly_and_retains_brc_owned_exposure() -> None:
    exchange = InstrumentCertificationExchange()
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        clock_ms=lambda: 2_000,
    )

    snapshot = await adapter.read_instrument_certification(
        _certification_read_request(owned_quantity=Decimal("0.01"))
    )

    assert snapshot.facts.product_status == "trading"
    assert snapshot.facts.position_mode == "independent_sides"
    assert snapshot.facts.margin_mode == "cross"
    assert snapshot.facts.configured_leverage == 5
    assert snapshot.facts.unowned_position_qty == 0
    assert snapshot.facts.unowned_open_order_count == 0
    assert exchange.mutations == []


@pytest.mark.asyncio
async def test_ccxt_adapter_certification_classifies_venue_quantity_above_projection_as_unowned() -> None:
    exchange = InstrumentCertificationExchange()
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        clock_ms=lambda: 2_000,
    )

    snapshot = await adapter.read_instrument_certification(
        _certification_read_request(owned_quantity=Decimal("0.001"))
    )
    decision = classify_instrument_certification(
        snapshot.facts,
        required_leverage=5,
        required_margin_mode="cross",
        valid_for_ms=60_000,
    )

    assert snapshot.facts.unowned_position_qty == Decimal("0.009")
    assert decision.status == "owner_action_required"
    assert decision.blocker_code == "unowned_position"
    assert exchange.mutations == []


@pytest.mark.asyncio
async def test_ccxt_adapter_certification_rejects_projected_quantity_above_venue() -> None:
    adapter = CcxtVenueAdapter(
        exchanges={
            ("binance-usdm", "experiment-1"): InstrumentCertificationExchange()
        },
        clock_ms=lambda: 2_000,
    )

    with pytest.raises(
        InstrumentCertificationSnapshotContradiction,
        match="projected_position_exceeds_venue",
    ):
        await adapter.read_instrument_certification(
            _certification_read_request(owned_quantity=Decimal("0.02"))
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exchange_type",
    (
        MissingOrderRuleCertificationExchange,
        InvalidOrderRuleCertificationExchange,
    ),
)
async def test_ccxt_adapter_certification_preserves_missing_order_rule_as_raw_fact(
    exchange_type,
) -> None:
    exchange = exchange_type()
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        clock_ms=lambda: 2_000,
    )

    snapshot = await adapter.read_instrument_certification(
        _certification_read_request(owned_quantity=Decimal("0.01"))
    )
    decision = classify_instrument_certification(
        snapshot.facts,
        required_leverage=5,
        required_margin_mode="cross",
        valid_for_ms=60_000,
    )

    assert snapshot.facts.min_notional is None
    assert snapshot.instrument_rules is None
    assert decision.status == "owner_action_required"
    assert decision.blocker_code == "missing_order_rule"
    assert exchange.mutations == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("missing_filter_type", "missing_fact_names"),
    (
        ("LOT_SIZE", ("step_size", "min_qty")),
        ("PRICE_FILTER", ("tick_size",)),
        ("MIN_NOTIONAL", ("min_notional",)),
    ),
)
async def test_ccxt_adapter_certification_never_falls_back_from_missing_raw_filter(
    missing_filter_type,
    missing_fact_names,
) -> None:
    exchange = MissingCanonicalFilterWithNormalizedFallbackExchange(
        missing_filter_type=missing_filter_type
    )
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        clock_ms=lambda: 2_000,
    )

    snapshot = await adapter.read_instrument_certification(
        _certification_read_request(owned_quantity=Decimal("0.01"))
    )
    decision = classify_instrument_certification(
        snapshot.facts,
        required_leverage=5,
        required_margin_mode="cross",
        valid_for_ms=60_000,
    )

    assert all(
        getattr(snapshot.facts, fact_name) is None
        for fact_name in missing_fact_names
    )
    assert snapshot.instrument_rules is None
    assert decision.status == "owner_action_required"
    assert decision.blocker_code == "missing_order_rule"
    assert exchange.mutations == []


@pytest.mark.asyncio
async def test_ccxt_adapter_maps_explicit_network_failure_to_transient() -> None:
    adapter = CcxtVenueAdapter(
        exchanges={
            ("binance-usdm", "experiment-1"): TransientCertificationExchange()
        },
        clock_ms=lambda: 2_000,
    )

    with pytest.raises(
        InstrumentCertificationTransientFailure,
        match="readonly Venue/network failure",
    ):
        await adapter.read_instrument_certification(
            _certification_read_request(owned_quantity=Decimal("0.01"))
        )


def _certification_read_request(
    *,
    owned_quantity: Decimal,
) -> InstrumentCertificationReadRequest:
    domain = NettingDomain(
        venue_id="binance-usdm",
        account_id="experiment-1",
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side="long",
    )
    return InstrumentCertificationReadRequest(
        target=InstrumentCertificationTarget(
            runtime_profile_id="profile:main",
            venue_id="binance-usdm",
            account_id="experiment-1",
            universe_version_id="universe:event:v1",
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            lease_owner="reconciliation-worker",
            lease_expires_at_ms=62_000,
        ),
        ownership=AdmissionOwnership(
            owned_position_domain_keys=(domain.key(),),
            owned_position_projections=(
                OwnedPositionProjection(
                    netting_domain_key=domain.key(),
                    quantity=owned_quantity,
                ),
            ),
            owned_exchange_order_ids=("owned-stop-1",),
        ),
        observed_at_ms=2_000,
        valid_for_ms=60_000,
    )


def test_binance_rules_accept_a_finite_final_maintenance_tier() -> None:
    brackets, maximum_leverage = _binance_maintenance_margin_brackets(
        [
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
                        "notionalCap": "250000",
                        "maintMarginRatio": "0.005",
                        "cum": "50",
                    },
                ],
            }
        ],
        venue_id="binance-usdm",
        market_id="BTCUSDT",
    )

    assert maximum_leverage == 20
    assert brackets[-1].notional_cap == Decimal("250000")


@pytest.mark.asyncio
async def test_ccxt_adapter_builds_position_snapshot_for_exact_netting_domain() -> None:
    adapter = CcxtVenueAdapter(
        exchanges={
            ("binance-usdm", "experiment-1"): ActionFactsExchange()
        },
        clock_ms=lambda: 2_000,
    )
    domain = NettingDomain(
        venue_id="binance-usdm",
        account_id="experiment-1",
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side="long",
    )

    snapshot = await adapter.read_position_snapshot(
        PositionSnapshotRequest(
            ticket_id="ticket-1",
            netting_domain=domain,
            observed_at_ms=2_000,
        )
    )

    assert snapshot.netting_domain == domain
    assert snapshot.quantity == Decimal("0.01")
    assert snapshot.average_entry_price == Decimal("59000")
    assert snapshot.liquidation_price is None
    assert {order.exchange_order_id for order in snapshot.open_orders} == {
        "order-False-long",
        "order-True-long",
    }
    assert all(order.position_side == "long" for order in snapshot.open_orders)


@pytest.mark.asyncio
async def test_ccxt_adapter_builds_tp1_fee_and_runner_market_facts() -> None:
    adapter = CcxtVenueAdapter(
        exchanges={
            ("binance-usdm", "experiment-1"): LifecycleFactsExchange()
        },
        settlement_assets={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): "USDT"
        },
        taker_fee_rates={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): Decimal("0.0005")
        },
        clock_ms=lambda: 20_000_000,
    )
    request = LifecycleFactsRequest(
        ticket_id="ticket-1",
        netting_domain=NettingDomain(
            venue_id="binance-usdm",
            account_id="experiment-1",
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            position_side="long",
        ),
        event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
        timeframe="15m",
        entry_quantity=Decimal("0.01"),
        expected_position_quantity=Decimal("0.005"),
        entry_order_reference=_entry_order_reference(),
        tp1_exchange_order_id="venue-tp1-1",
        entered_at_ms=1_000,
        price_tick=Decimal("0.1"),
        structure_window_bars=4,
        atr_period=14,
        runner_market_required=True,
        observed_at_ms=20_000_000,
    )

    facts = await adapter.read_lifecycle_facts(request)

    assert facts.position_quantity == Decimal("0.005")
    assert facts.tp1_filled_quantity == Decimal("0.005")
    assert facts.tp1_average_fill_price == Decimal("61000")
    exchange = adapter._exchanges[("binance-usdm", "experiment-1")]
    assert isinstance(exchange, LifecycleFactsExchange)
    assert exchange.tp1_order_calls == [
        ("venue-tp1-1", "BTC/USDT:USDT", {})
    ]
    assert facts.allocated_entry_fee_quote == Decimal("0.20")
    assert facts.exit_taker_fee_rate == Decimal("0.0005")
    assert facts.price_tick == Decimal("0.1")
    assert facts.market_facts is not None
    assert facts.market_facts.is_final_closed_candle is True
    assert facts.market_facts.structure_reference == Decimal("60002")
    assert facts.market_facts.atr > 0


@pytest.mark.asyncio
async def test_ccxt_adapter_keeps_runner_window_after_dropping_open_candle() -> None:
    exchange = IncompleteLastLifecycleFactsExchange()
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        settlement_assets={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): "USDT"
        },
        taker_fee_rates={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): Decimal("0.0005")
        },
        clock_ms=lambda: 20_000_000,
    )
    request = LifecycleFactsRequest(
        ticket_id="ticket-1",
        netting_domain=NettingDomain(
            venue_id="binance-usdm",
            account_id="experiment-1",
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            position_side="long",
        ),
        event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
        timeframe="15m",
        entry_quantity=Decimal("0.01"),
        expected_position_quantity=Decimal("0.005"),
        entry_order_reference=_entry_order_reference(),
        tp1_exchange_order_id=None,
        entered_at_ms=1_000,
        price_tick=Decimal("0.1"),
        structure_window_bars=4,
        atr_period=14,
        runner_market_required=True,
        observed_at_ms=20_000_000,
    )

    facts = await adapter.read_lifecycle_facts(request)

    assert exchange.ohlcv_limit == 16
    assert facts.market_facts is not None
    assert facts.market_facts.is_final_closed_candle is True


@pytest.mark.asyncio
async def test_ccxt_adapter_uses_conservative_taker_bound_for_bnb_lifecycle_fee() -> None:
    adapter = CcxtVenueAdapter(
        exchanges={
            ("binance-usdm", "experiment-1"): BnbLifecycleFactsExchange()
        },
        settlement_assets={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): "USDT"
        },
        taker_fee_rates={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): Decimal("0.0005")
        },
        clock_ms=lambda: 20_000_000,
    )
    request = LifecycleFactsRequest(
        ticket_id="ticket-1",
        netting_domain=NettingDomain(
            venue_id="binance-usdm",
            account_id="experiment-1",
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            position_side="long",
        ),
        event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
        timeframe="15m",
        entry_quantity=Decimal("0.01"),
        expected_position_quantity=Decimal("0.005"),
        entry_order_reference=_entry_order_reference(),
        tp1_exchange_order_id=None,
        entered_at_ms=1_000,
        price_tick=Decimal("0.1"),
        structure_window_bars=4,
        atr_period=14,
        runner_market_required=False,
        observed_at_ms=20_000_000,
    )

    facts = await adapter.read_lifecycle_facts(request)

    assert facts.allocated_entry_fee_quote == Decimal("0.15")


@pytest.mark.asyncio
async def test_ccxt_adapter_builds_exact_ticket_bound_review_economics_facts() -> None:
    exchange = ReviewEconomicsExchange()
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        settlement_assets={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): "USDT"
        },
        clock_ms=lambda: 4_000,
    )

    facts = await adapter.read_review_economics(_review_request())

    assert [fill.exchange_trade_id for fill in facts.entry_fills] == [
        "trade-entry"
    ]
    assert [fill.exchange_trade_id for fill in facts.exit_fills] == [
        "trade-tp1",
        "trade-runner",
    ]
    assert facts.funding_quote == Decimal("-0.3")
    assert facts.funding_unavailable_reason is None
    assert [call[3] for call in exchange.trade_calls] == [
        {"orderId": "venue-entry-1"},
        {"orderId": "venue-tp1-1"},
        {"orderId": "venue-runner-actual-1"},
    ]
    assert exchange.funding_calls == [
        {
            "symbol": "BTCUSDT",
            "incomeType": "FUNDING_FEE",
            "startTime": 1_000,
            "endTime": 3_500,
            "limit": 1000,
        }
    ]


@pytest.mark.asyncio
async def test_ccxt_adapter_values_all_bnb_review_fees_from_one_index_snapshot() -> None:
    exchange = BnbReviewEconomicsExchange()
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        settlement_assets={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): "USDT"
        },
        clock_ms=lambda: 4_000,
    )

    facts = await adapter.read_review_economics(_review_request())

    assert facts.entry_fills[0].fee.native.asset == "BNB"
    assert facts.entry_fills[0].fee.usdt_value == Decimal("6.00")
    assert facts.entry_fills[0].fee.evidence.price_pair == "BNBUSDT"
    assert facts.entry_fills[0].fee.evidence.method == (
        "binance_usdm_bnbusdt_review_index_snapshot"
    )
    assert exchange.index_snapshot_calls == [{"symbol": "BNBUSDT"}]


@pytest.mark.asyncio
async def test_ccxt_adapter_reads_bnb_fee_capability_with_readonly_calls_only() -> None:
    exchange = FeeDiscountCapabilityExchange()
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        clock_ms=lambda: 4_000,
    )

    facts = await adapter.read_fee_discount_capability(observed_at_ms=4_000)

    assert facts.fee_burn_enabled is True
    assert facts.bnb_futures_wallet_balance == Decimal("0.02")
    assert facts.source == "binance_usdm_readonly"
    assert exchange.calls == [
        ("fee_burn", {}),
        ("balance", {"type": "future"}),
    ]


@pytest.mark.asyncio
async def test_ccxt_adapter_marks_funding_unavailable_for_overlapping_exposure() -> None:
    exchange = ReviewEconomicsExchange()
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        settlement_assets={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): "USDT"
        },
        clock_ms=lambda: 4_000,
    )

    facts = await adapter.read_review_economics(
        _review_request().model_copy(update={"funding_attribution_exact": False})
    )

    assert facts.funding_quote is None
    assert facts.funding_unavailable_reason == "overlapping_instrument_exposure"
    assert exchange.funding_calls == []


@pytest.mark.asyncio
async def test_ccxt_adapter_rejects_review_fill_without_exact_fee() -> None:
    exchange = ReviewEconomicsExchange(include_fee=False)
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        settlement_assets={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): "USDT"
        },
        clock_ms=lambda: 4_000,
    )

    with pytest.raises(RuntimeError, match="commission"):
        await adapter.read_review_economics(_review_request())


@pytest.mark.asyncio
async def test_ccxt_adapter_rejects_any_trade_row_that_differs_from_requested_order_id() -> None:
    adapter = CcxtVenueAdapter(
        exchanges={
            ("binance-usdm", "experiment-1"): WrongOrderReviewEconomicsExchange()
        },
        settlement_assets={
            ("binance-usdm", "binance-usdm:BTCUSDT:perpetual"): "USDT"
        },
        clock_ms=lambda: 4_000,
    )

    with pytest.raises(RuntimeError, match="order id"):
        await adapter.read_review_economics(_review_request())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fee",
    [
        {"cost": "0.01"},
        {"cost": "-0.01", "currency": "USDT"},
        {"cost": "-0.00001", "currency": "BNB"},
    ],
)
async def test_ccxt_adapter_rejects_missing_or_negative_raw_fee_asset_and_amount(
    fee: object,
) -> None:
    adapter = CcxtVenueAdapter(
        exchanges={
            ("binance-usdm", "experiment-1"): InvalidRawFeeReviewEconomicsExchange(
                fee=fee
            )
        },
        settlement_assets={
            ("binance-usdm", "binance-usdm:BTCUSDT:perpetual"): "USDT"
        },
        clock_ms=lambda: 4_000,
    )

    with pytest.raises(RuntimeError, match="commission"):
        await adapter.read_review_economics(_review_request())


@pytest.mark.asyncio
async def test_ccxt_adapter_classifies_only_authoritative_rejection() -> None:
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): RejectingExchange()},
        clock_ms=lambda: 2_000,
    )

    result = await adapter.execute(_request())

    assert result.status is ExchangeCommandStatus.REJECTED
    assert result.reason == "venue_rejected:InsufficientFunds"
    assert "sensitive" not in result.reason


@pytest.mark.asyncio
async def test_ccxt_adapter_propagates_unknown_network_outcome() -> None:
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): TimingOutExchange()},
        clock_ms=lambda: 2_000,
    )

    with pytest.raises(TimeoutError):
        await adapter.execute(_request())


@pytest.mark.asyncio
async def test_ccxt_adapter_cancels_exact_exchange_order_without_creating_order() -> None:
    exchange = CancelExchange()
    adapter = _cancel_adapter(exchange)

    result = await adapter.execute(_cancel_request())

    assert result.status is ExchangeCommandStatus.ACCEPTED
    assert result.exchange_order_id == "stop-order-1"
    assert exchange.cancel_call == (
        "stop-order-1",
        "BTC/USDT:USDT",
        {"positionSide": "LONG", "conditional": False},
    )


@pytest.mark.asyncio
async def test_ccxt_adapter_cancels_conditional_order_in_its_exact_namespace() -> None:
    exchange = ConditionalCancelExchange()
    adapter = _cancel_adapter(exchange)

    result = await adapter.execute(
        _cancel_request(order_namespace="conditional", purpose="runner_old_stop")
    )

    assert result.status is ExchangeCommandStatus.ACCEPTED
    assert result.exchange_order_id == "stop-order-1"
    assert exchange.cancel_calls == [
        (
            "stop-order-1",
            "BTC/USDT:USDT",
            {"positionSide": "LONG", "conditional": True},
        ),
    ]


@pytest.mark.asyncio
async def test_ccxt_adapter_classifies_authoritative_cancel_rejection() -> None:
    result = await _cancel_adapter(RejectingCancelExchange()).execute(
        _cancel_request()
    )

    assert result.status is ExchangeCommandStatus.REJECTED
    assert result.reason == "venue_rejected:InsufficientFunds"
    assert "sensitive" not in result.reason


@pytest.mark.asyncio
async def test_ccxt_adapter_propagates_unknown_cancel_outcome() -> None:
    with pytest.raises(TimeoutError):
        await _cancel_adapter(TimingOutCancelExchange()).execute(_cancel_request())


@pytest.mark.asyncio
async def test_ccxt_adapter_reads_complete_visible_command_truth() -> None:
    exchange = TruthExchange(visible=True)
    adapter = _cancel_adapter(exchange)

    truth = await adapter.lookup_command_truth(_truth_request())

    assert truth.lookup_status is VenueLookupStatus.VISIBLE
    assert truth.order is not None
    assert truth.order.exchange_order_id == "venue-order-1"
    assert truth.order.exchange_instrument_id == (
        "binance-usdm:BTCUSDT:perpetual"
    )
    assert truth.order.position_side == "long"
    assert truth.order.quantity == Decimal("0.001")
    assert exchange.fill_params == {"orderId": "venue-order-1"}
    assert exchange.calls == [
        "order",
        "positions",
        "regular",
        "conditional",
        "fills",
    ]


@pytest.mark.asyncio
async def test_ccxt_adapter_proves_absence_only_after_all_truth_surfaces() -> None:
    exchange = TruthExchange(visible=False)
    adapter = _cancel_adapter(exchange)

    truth = await adapter.lookup_command_truth(_truth_request())

    assert truth.lookup_status is VenueLookupStatus.ABSENT
    assert truth.order is None
    assert truth.position_quantity == 0
    assert truth.matching_fill_quantity == 0
    assert exchange.calls == [
        "order",
        "positions",
        "regular",
        "conditional",
    ]


@pytest.mark.asyncio
async def test_cancel_truth_looks_up_exact_target_order_not_cancel_command_identity() -> None:
    exchange = CancelTruthExchange(visible=True)
    adapter = _cancel_adapter(exchange)

    truth = await adapter.lookup_command_truth(_cancel_truth_request())

    assert truth.lookup_status is VenueLookupStatus.VISIBLE
    assert truth.order is not None
    assert truth.order.exchange_order_id == "stop-order-1"
    assert truth.order.venue_client_order_id == "brc-original-stop"
    assert exchange.order_lookup == (
        "stop-order-1",
        "BTC/USDT:USDT",
        {"positionSide": "LONG", "conditional": False},
    )


@pytest.mark.asyncio
async def test_cancel_truth_does_not_claim_absence_when_target_is_still_open() -> None:
    exchange = CancelTruthExchange(visible=False, target_in_open=True)
    adapter = _cancel_adapter(exchange)

    truth = await adapter.lookup_command_truth(
        _cancel_truth_request(
            order_namespace="conditional",
            purpose="runner_old_stop",
        )
    )

    assert truth.lookup_status is VenueLookupStatus.VISIBLE
    assert truth.order is not None
    assert truth.order.exchange_order_id == "stop-order-1"


@pytest.mark.asyncio
async def test_cancel_truth_marks_historical_terminal_target_as_not_open() -> None:
    exchange = CancelTruthExchange(visible=True, terminal=True)
    adapter = _cancel_adapter(exchange)

    truth = await adapter.lookup_command_truth(_cancel_truth_request())

    assert truth.lookup_status is VenueLookupStatus.VISIBLE
    assert truth.order is not None
    assert truth.order.exchange_order_id == "stop-order-1"
    assert truth.order.is_open is False


def _request() -> VenueCommandRequest:
    return VenueCommandRequest(
        command_id="command:entry-1",
        kind=ExchangeCommandKind.ENTRY,
        venue_id="binance-usdm",
        account_id="experiment-1",
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side="long",
        venue_client_order_id="brc-entry-1",
        payload=OrderCommandPayload(
            side="buy",
            quantity=Decimal("0.001"),
            order_type="market",
            reduce_only=False,
        ),
        deadline_at_ms=10_000,
    )


def _cancel_adapter(exchange) -> CcxtVenueAdapter:
    return CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        clock_ms=lambda: 2_000,
    )


def _cancel_request(
    *,
    order_namespace: str = "regular",
    purpose: str = "reconciliation_cleanup",
) -> VenueCommandRequest:
    return VenueCommandRequest(
        command_id="command:cancel-stop-1",
        kind=ExchangeCommandKind.CANCEL_ORDER,
        venue_id="binance-usdm",
        account_id="experiment-1",
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side="long",
        venue_client_order_id="brc-cancel-stop-1",
        payload=CancelCommandPayload(
            exchange_order_id="stop-order-1",
            order_namespace=order_namespace,
            purpose=purpose,
        ),
        deadline_at_ms=10_000,
    )


def _truth_request() -> VenueTruthRequest:
    request = _request()
    return VenueTruthRequest(
        command_id=request.command_id,
        kind=request.kind,
        venue_id=request.venue_id,
        account_id=request.account_id,
        exchange_instrument_id=request.exchange_instrument_id,
        position_side=request.position_side,
        venue_client_order_id=request.venue_client_order_id,
        payload=request.payload,
        observed_at_ms=2_000,
    )


def _cancel_truth_request(
    *,
    order_namespace: str = "regular",
    purpose: str = "reconciliation_cleanup",
) -> VenueTruthRequest:
    request = _cancel_request(
        order_namespace=order_namespace,
        purpose=purpose,
    )
    return VenueTruthRequest(
        command_id=request.command_id,
        kind=request.kind,
        venue_id=request.venue_id,
        account_id=request.account_id,
        exchange_instrument_id=request.exchange_instrument_id,
        position_side=request.position_side,
        venue_client_order_id=request.venue_client_order_id,
        payload=request.payload,
        observed_at_ms=2_000,
    )


def _review_request() -> ReviewEconomicsRequest:
    return ReviewEconomicsRequest(
        ticket_id="ticket-1",
        netting_domain=NettingDomain(
            venue_id="binance-usdm",
            account_id="experiment-1",
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            position_side="long",
        ),
        expected_entry_quantity=Decimal("1"),
        entry_order_reference=_entry_order_reference(),
        exit_order_references=(
            TicketOrderReference(
                command_id="command:tp1-1",
                command_kind=ExchangeCommandKind.TAKE_PROFIT,
                role=OrderRole.EXIT,
                namespace=OrderNamespace.REGULAR,
                venue_client_order_id="brc-tp1-1",
                submitted_exchange_order_id="venue-tp1-1",
            ),
            TicketOrderReference(
                command_id="command:runner-1",
                command_kind=ExchangeCommandKind.EXIT,
                role=OrderRole.EXIT,
                namespace=OrderNamespace.CONDITIONAL,
                venue_client_order_id="brc-runner-1",
                submitted_exchange_order_id="venue-runner-algo-1",
                conditional_expectation={
                    "exchange_instrument_id": "binance-usdm:BTCUSDT:perpetual",
                    "position_side": "long",
                    "side": "sell",
                    "order_type": "stop_market",
                    "quantity": Decimal("0.5"),
                },
            ),
        ),
        entry_time_ms=1_000,
        exit_time_ms=3_500,
        funding_attribution_exact=True,
        observed_at_ms=4_000,
    )


def _entry_order_reference() -> TicketOrderReference:
    return TicketOrderReference(
        command_id="command:entry-1",
        command_kind=ExchangeCommandKind.ENTRY,
        role=OrderRole.ENTRY,
        namespace=OrderNamespace.REGULAR,
        venue_client_order_id="brc-entry-1",
        submitted_exchange_order_id="venue-entry-1",
    )
