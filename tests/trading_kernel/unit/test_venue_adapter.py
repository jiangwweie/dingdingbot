from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.application.ports import VenueCommandRequest, VenueTruthRequest
from src.trading_kernel.application.runtime_facts import (
    ActionTimeFactsRequest,
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
)
from src.trading_kernel.infrastructure.venue_adapter import CcxtVenueAdapter
from src.trading_kernel.domain.venue_truth import VenueLookupStatus
from src.trading_kernel.domain.identities import NettingDomain


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


class RejectingCancelExchange:
    async def cancel_order(self, *args, **kwargs):
        raise InsufficientFunds("sensitive venue message")


class TimingOutCancelExchange:
    async def cancel_order(self, *args, **kwargs):
        raise TimeoutError("network outcome unknown")


class OrderNotFound(Exception):
    pass


class TruthExchange:
    def __init__(self, *, visible: bool) -> None:
        self.visible = visible
        self.calls: list[str] = []

    async def fetch_order(self, order_id, symbol, params):
        self.calls.append("order")
        if not self.visible:
            raise OrderNotFound("not visible")
        return {
            "id": "venue-order-1",
            "clientOrderId": params["origClientOrderId"],
            "symbol": symbol,
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
        self.calls.append("fills")
        return []

    async def fetch_open_orders(self, symbol, since, limit, params):
        self.calls.append(
            "conditional" if params.get("conditional") else "regular"
        )
        return []


class CancelTruthExchange(TruthExchange):
    def __init__(self, *, visible: bool, target_in_open: bool = False) -> None:
        super().__init__(visible=visible)
        self.order_lookup = None
        self.target_in_open = target_in_open

    async def fetch_order(self, order_id, symbol, params):
        self.calls.append("order")
        self.order_lookup = (order_id, symbol, params)
        if not self.visible:
            raise OrderNotFound("not visible")
        return {
            "id": order_id,
            "clientOrderId": "brc-original-stop",
            "symbol": symbol,
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
        self.position_calls: list[tuple[list[str], dict[str, object]]] = []
        self.order_calls: list[tuple[str | None, dict[str, object]]] = []

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

class LifecycleFactsExchange:
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
        client_id = params["clientOrderId"]
        if client_id == "brc-entry-1":
            return [
                {
                    "clientOrderId": client_id,
                    "amount": "0.01",
                    "price": "60000",
                    "fee": {"cost": "0.4", "currency": "USDT"},
                }
            ]
        return [
            {
                "clientOrderId": client_id,
                "amount": "0.005",
                "price": "61000",
                "fee": {"cost": "0.15", "currency": "USDT"},
            }
        ]

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
                "clientOrderId": "brc-entry-1",
                "amount": "1",
                "price": "100",
                "fee": fee if self.include_fee else None,
                "timestamp": 1_100,
                "info": {"positionSide": "LONG"},
            },
            {
                "id": "trade-tp1",
                "clientOrderId": "brc-tp1-1",
                "amount": "0.5",
                "price": "110",
                "fee": {"cost": "0.05", "currency": "USDT"},
                "timestamp": 2_000,
                "info": {"positionSide": "LONG"},
            },
            {
                "id": "trade-runner",
                "clientOrderId": "brc-runner-1",
                "amount": "0.5",
                "price": "120",
                "fee": {"cost": "0.05", "currency": "USDT"},
                "timestamp": 3_000,
                "info": {"positionSide": "LONG"},
            },
            {
                "id": "unrelated-trade",
                "clientOrderId": "manual-order",
                "amount": "10",
                "price": "1",
                "fee": {"cost": "1", "currency": "USDT"},
                "timestamp": 2_500,
                "info": {"positionSide": "LONG"},
            },
        ]
        client_id = str(params.get("clientOrderId") or "")
        return [row for row in rows if row["clientOrderId"] == client_id]

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

@pytest.mark.asyncio
async def test_ccxt_adapter_sends_explicit_hedge_side_and_client_identity() -> None:
    exchange = FakeAsyncExchange()
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        venue_symbols={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): "BTC/USDT:USDT"
        },
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
async def test_ccxt_adapter_builds_exact_hedge_side_action_time_facts() -> None:
    adapter = CcxtVenueAdapter(
        exchanges={
            ("binance-usdm", "experiment-1"): ActionFactsExchange()
        },
        venue_symbols={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): "BTC/USDT:USDT"
        },
        settlement_assets={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): "USDT"
        },
        clock_ms=lambda: 2_000,
    )

    facts = await adapter.read_action_time_facts(
        ActionTimeFactsRequest(
            signal_event_id="signal-1",
            runtime_scope_id="scope-1",
            venue_id="binance-usdm",
            account_id="experiment-1",
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            position_side="long",
            observed_at_ms=2_000,
            valid_for_ms=5_000,
        )
    )

    assert facts.account_position_mode == "independent_sides"
    assert facts.best_bid_price == Decimal("59999.9")
    assert facts.best_ask_price == Decimal("60000.1")
    assert facts.account_equity == Decimal("1200")
    assert facts.available_margin == Decimal("800")
    assert facts.netting_domain_position_qty == Decimal("0.01")
    assert facts.netting_domain_open_order_count == 2
    assert facts.valid_until_ms == 7_000


@pytest.mark.asyncio
async def test_ccxt_adapter_reports_actual_one_way_account_mode() -> None:
    adapter = CcxtVenueAdapter(
        exchanges={
            ("binance-usdm", "experiment-1"): OneWayActionFactsExchange()
        },
        venue_symbols={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): "BTC/USDT:USDT"
        },
        settlement_assets={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): "USDT"
        },
        clock_ms=lambda: 2_000,
    )

    facts = await adapter.read_action_time_facts(
        ActionTimeFactsRequest(
            signal_event_id="signal-1",
            runtime_scope_id="scope-1",
            venue_id="binance-usdm",
            account_id="experiment-1",
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            position_side="long",
            observed_at_ms=2_000,
            valid_for_ms=5_000,
        )
    )

    assert facts.account_position_mode == "one_way"


@pytest.mark.asyncio
async def test_ccxt_adapter_freezes_one_account_wide_admission_snapshot() -> None:
    exchange = AdmissionSnapshotExchange()
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        venue_symbols={
            ("binance-usdm", "SOLUSDT"): "SOL/USDT:USDT",
            ("binance-usdm", "BTCUSDT"): "BTC/USDT:USDT",
        },
        settlement_assets={("binance-usdm", "SOLUSDT"): "USDT"},
        clock_ms=lambda: 2_000,
    )

    snapshot = await adapter.read_entry_admission_snapshot(
        EntryAdmissionSnapshotRequest(
            venue_id="binance-usdm",
            account_id="experiment-1",
            exchange_instrument_id="SOLUSDT",
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
    assert snapshot.instrument_facts_for("SOLUSDT").mark_price == Decimal("100")
    assert snapshot.instrument_facts_for("SOLUSDT").configured_leverage == 4
    assert {(row.exchange_instrument_id, row.position_side) for row in snapshot.positions} == {
        ("SOLUSDT", "short"),
        ("BTCUSDT", "long"),
    }
    assert {order.exchange_order_id for order in snapshot.open_orders} == {
        "regular-btc-order",
        "conditional-btc-order",
    }
    assert exchange.position_calls == [([], {})]
    assert exchange.order_calls == [
        (None, {"conditional": False}),
        (None, {"conditional": True}),
    ]
    assert snapshot.valid_until_ms == 7_000


@pytest.mark.asyncio
async def test_ccxt_adapter_reads_typed_leverage_and_maintenance_rules() -> None:
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): InstrumentRulesExchange()},
        venue_symbols={
            ("binance-usdm", "binance-usdm:BTCUSDT:perpetual"): "BTC/USDT:USDT"
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
    assert tuple(item.bracket_id for item in facts.maintenance_margin_brackets) == (
        "binance-usdm:BTCUSDT:1",
        "binance-usdm:BTCUSDT:2",
    )
    assert facts.maintenance_margin_brackets[1].maintenance_amount == Decimal("50")
    assert facts.maintenance_margin_brackets_digest.startswith("sha256:")


@pytest.mark.asyncio
async def test_ccxt_adapter_builds_position_snapshot_for_exact_netting_domain() -> None:
    adapter = CcxtVenueAdapter(
        exchanges={
            ("binance-usdm", "experiment-1"): ActionFactsExchange()
        },
        venue_symbols={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): "BTC/USDT:USDT"
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
        venue_symbols={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): "BTC/USDT:USDT"
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
        entry_venue_client_order_id="brc-entry-1",
        tp1_venue_client_order_id="brc-tp1-1",
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
    assert facts.allocated_entry_fee_quote == Decimal("0.20")
    assert facts.exit_taker_fee_rate == Decimal("0.0005")
    assert facts.price_tick == Decimal("0.1")
    assert facts.market_facts is not None
    assert facts.market_facts.is_final_closed_candle is True
    assert facts.market_facts.structure_reference == Decimal("60001")
    assert facts.market_facts.atr > 0


@pytest.mark.asyncio
async def test_ccxt_adapter_builds_exact_ticket_bound_review_economics_facts() -> None:
    exchange = ReviewEconomicsExchange()
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        venue_symbols={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): "BTC/USDT:USDT"
        },
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
        {"clientOrderId": "brc-entry-1"},
        {"clientOrderId": "brc-tp1-1"},
        {"clientOrderId": "brc-runner-1"},
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
async def test_ccxt_adapter_marks_funding_unavailable_for_overlapping_exposure() -> None:
    exchange = ReviewEconomicsExchange()
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        venue_symbols={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): "BTC/USDT:USDT"
        },
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
        venue_symbols={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): "BTC/USDT:USDT"
        },
        settlement_assets={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): "USDT"
        },
        clock_ms=lambda: 4_000,
    )

    with pytest.raises(RuntimeError, match="review fill fee is unavailable"):
        await adapter.read_review_economics(_review_request())


@pytest.mark.asyncio
async def test_ccxt_adapter_classifies_only_authoritative_rejection() -> None:
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): RejectingExchange()},
        venue_symbols={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): "BTC/USDT:USDT"
        },
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
        venue_symbols={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): "BTC/USDT:USDT"
        },
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
        {"positionSide": "LONG"},
    )


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
    assert exchange.calls == [
        "order",
        "positions",
        "fills",
        "regular",
        "conditional",
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
        "fills",
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
        {"positionSide": "LONG"},
    )


@pytest.mark.asyncio
async def test_cancel_truth_does_not_claim_absence_when_target_is_still_open() -> None:
    exchange = CancelTruthExchange(visible=False, target_in_open=True)
    adapter = _cancel_adapter(exchange)

    truth = await adapter.lookup_command_truth(_cancel_truth_request())

    assert truth.lookup_status is VenueLookupStatus.VISIBLE
    assert truth.order is not None
    assert truth.order.exchange_order_id == "stop-order-1"


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
        venue_symbols={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): "BTC/USDT:USDT"
        },
        clock_ms=lambda: 2_000,
    )


def _cancel_request() -> VenueCommandRequest:
    return VenueCommandRequest(
        command_id="command:cancel-stop-1",
        kind=ExchangeCommandKind.CANCEL_ORDER,
        venue_id="binance-usdm",
        account_id="experiment-1",
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side="long",
        venue_client_order_id="brc-cancel-stop-1",
        payload=CancelCommandPayload(exchange_order_id="stop-order-1"),
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


def _cancel_truth_request() -> VenueTruthRequest:
    request = _cancel_request()
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
        entry_venue_client_order_id="brc-entry-1",
        exit_venue_client_order_ids=("brc-tp1-1", "brc-runner-1"),
        entry_time_ms=1_000,
        exit_time_ms=3_500,
        funding_attribution_exact=True,
        observed_at_ms=4_000,
    )
