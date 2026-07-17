import inspect
from types import SimpleNamespace

from scripts import preview_ticket_exit_policy_adoption
from src.application.action_time.exchange_snapshot_provider import (
    fetch_resolved_ticket_bound_exchange_snapshot,
)
from src.interfaces import api_trading_console
from src.infrastructure.exchange_gateway import ExchangeGateway
from tests.unit.test_ticket_bound_exchange_snapshot_provider import _scope


class _NarrowSnapshotGateway:
    runtime_account_id = "owner-subaccount-runtime-v0"
    runtime_exchange_id = "binance_usdm"

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def fetch_ticket_lifecycle_snapshot(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "open_orders": [],
            "recent_fills": [],
            "positions": [
                {
                    "symbol": "ETH/USDT:USDT",
                    "size": "0",
                    "position_side": "",
                }
            ],
            "funding_result": {"rows": [], "error": None},
            "conditional_result": {"rows": [], "error": None},
            "account_exposure_result": {
                "status": "ready",
                "account_id": "owner-subaccount-runtime-v0",
                "exchange_id": "binance_usdm",
                "account_margin_balance": "100",
                "gross_open_position_notional": "0",
                "effective_account_exposure_leverage": "0",
                "observed_at_ms": 2_000,
                "blockers": [],
            },
            "commission_rate": {
                "symbol": "ETHUSDT",
                "maker_commission_rate": "0.0002",
                "taker_commission_rate": "0.0005",
            },
            "market_rule": {
                "exchange_market_id": "ETHUSDT",
                "price_tick": "0.1",
                "quantity_step": "0.001",
                "min_notional": "5",
                "source": "binance_usdm_public_exchange_info",
            },
            "exchange_request_count": 7,
        }

    async def fetch_all_open_orders(self, _symbol: str):
        raise AssertionError("legacy market-loading order read must not run")

    async def fetch_my_trades(self, _symbol: str, limit: int = 50):
        raise AssertionError("legacy market-loading trade read must not run")

    async def fetch_position_rows(self, _symbol: str):
        raise AssertionError("legacy market-loading position read must not run")


async def test_snapshot_prefers_one_narrow_ticket_lifecycle_gateway_boundary():
    gateway = _NarrowSnapshotGateway()

    payload = await fetch_resolved_ticket_bound_exchange_snapshot(
        scope=_scope(),
        snapshot_identity="protection-1",
        gateway=gateway,
        timeout_seconds=1,
        recent_fill_limit=50,
        funding_start_time_ms=1_000,
        funding_end_time_ms=2_000,
        conditional_parent_order_ids=["algo-1"],
        now_ms=2_000,
    )

    assert payload["status"] == "snapshot_ready"
    assert payload["exchange_request_count"] == 7
    assert gateway.calls == [
        {
            "exchange_symbol": "ETH/USDT:USDT",
            "exchange_market_id": "ETHUSDT",
            "recent_fill_limit": 50,
            "funding_start_time_ms": 1_000,
            "funding_end_time_ms": 2_000,
            "conditional_parent_order_ids": ["algo-1"],
        }
    ]
    assert payload["snapshot"]["exchange_write_called"] is False
    assert payload["snapshot"]["commission_rate"]["taker_commission_rate"] == (
        "0.0005"
    )
    assert payload["snapshot"]["market_rule"]["price_tick"] == "0.1"


class _LifecycleReadonlyGateway:
    def __init__(self, **_kwargs) -> None:
        self.events: list[str] = []

    async def initialize(self) -> None:
        raise AssertionError("full load_markets initialization must not run")

    async def initialize_lifecycle_readonly(self) -> None:
        self.events.append("initialize_lifecycle_readonly")

    async def check_api_key_permissions(self) -> None:
        self.events.append("check_api_key_permissions")

    async def close(self) -> None:
        self.events.append("close")


for _method_name in (
    "place_order",
    "cancel_order",
    "fetch_open_orders",
    "fetch_order",
    "fetch_positions",
    "fetch_my_trades",
    "fetch_ticker_price",
    "get_market_info",
):
    setattr(_LifecycleReadonlyGateway, _method_name, lambda self: None)


async def test_runtime_binding_uses_readonly_lifecycle_initialization(monkeypatch):
    expected_env = {
        "TRADING_ENV": "live",
        "EXCHANGE_TESTNET": "false",
        "BRC_EXECUTION_PERMISSION_MAX": "order_allowed",
        "RUNTIME_CONTROL_API_ENABLED": "false",
        "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
        "RUNTIME_EXCHANGE_SUBMIT_GATEWAY_BINDING_ENABLED": "true",
        "BRC_RUNTIME_EXCHANGE_ACCOUNT_ID": "owner-subaccount-runtime-v0",
        "BRC_RUNTIME_EXCHANGE_ID": "binance_usdm",
        "EXCHANGE_API_KEY": "test-key",
        "EXCHANGE_API_SECRET": "test-secret",
        "EXCHANGE_NAME": "binance",
    }
    for key, value in expected_env.items():
        monkeypatch.setenv(key, value)
    api_module = SimpleNamespace(_runtime_exchange_submit_gateway=None)

    binding = await api_trading_console._runtime_exchange_submit_gateway_binding(
        api_module,
        gateway_factory=_LifecycleReadonlyGateway,
        lifecycle_readonly=True,
    )

    assert binding["status"] == "ready"
    assert binding["gateway"].events == [
        "initialize_lifecycle_readonly",
        "check_api_key_permissions",
    ]


def test_adoption_preview_uses_lightweight_gateway_binding():
    source = inspect.getsource(
        preview_ticket_exit_policy_adoption.build_fresh_adoption_eligibility
    )

    assert "src.infrastructure.runtime_exchange_gateway_binding" in source
    assert "src.interfaces" not in source


async def test_binance_narrow_snapshot_uses_raw_ticket_scoped_reads_only():
    class _RawBinance:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        async def fapiPrivateV3GetPositionRisk(self, params):
            self.calls.append(("position", params))
            return [
                {
                    "symbol": "ETHUSDT",
                    "positionSide": "BOTH",
                    "positionAmt": "2",
                    "entryPrice": "100",
                    "markPrice": "105",
                    "unRealizedProfit": "10",
                    "liquidationPrice": "50",
                }
            ]

        async def fapiPrivateGetOpenOrders(self, params):
            self.calls.append(("orders", params))
            return [
                {
                    "orderId": 11,
                    "clientOrderId": "tp1",
                    "symbol": "ETHUSDT",
                    "side": "SELL",
                    "positionSide": "BOTH",
                    "origQty": "1",
                    "executedQty": "0",
                    "price": "110",
                    "status": "NEW",
                    "type": "LIMIT",
                    "reduceOnly": True,
                }
            ]

        async def fapiPrivateGetOpenAlgoOrders(self, params):
            self.calls.append(("algo_orders", params))
            return [
                {
                    "algoId": 12,
                    "clientAlgoId": "sl",
                    "symbol": "ETHUSDT",
                    "side": "SELL",
                    "positionSide": "BOTH",
                    "quantity": "2",
                    "triggerPrice": "95",
                    "algoStatus": "NEW",
                    "orderType": "STOP_MARKET",
                    "reduceOnly": True,
                }
            ]

        async def fapiPrivateGetUserTrades(self, params):
            self.calls.append(("trades", params))
            return [
                {
                    "id": 13,
                    "orderId": 11,
                    "symbol": "ETHUSDT",
                    "side": "SELL",
                    "positionSide": "BOTH",
                    "qty": "1",
                    "price": "110",
                    "commission": "0.01",
                    "commissionAsset": "USDT",
                    "time": 1_900,
                    "maker": True,
                }
            ]

        async def fapiPrivateV3GetAccount(self, params=None):
            self.calls.append(("account", params or {}))
            return {
                "totalMarginBalance": "100",
                "positions": [{"symbol": "ETHUSDT", "notional": "210"}],
            }

        async def fapiPrivateGetCommissionRate(self, params):
            self.calls.append(("commission_rate", params))
            return {
                "symbol": "ETHUSDT",
                "makerCommissionRate": "0.0002",
                "takerCommissionRate": "0.0005",
            }

        async def fapiPublicGetExchangeInfo(self, params):
            self.calls.append(("exchange_info", params))
            return {
                "symbols": [
                    {
                        "symbol": "ETHUSDT",
                        "status": "TRADING",
                        "quoteAsset": "USDT",
                        "marginAsset": "USDT",
                        "filters": [
                            {"filterType": "PRICE_FILTER", "tickSize": "0.1"},
                            {"filterType": "LOT_SIZE", "stepSize": "0.001"},
                            {"filterType": "MIN_NOTIONAL", "notional": "5"},
                        ],
                    }
                ]
            }

        async def fapiPrivateGetIncome(self, params):
            self.calls.append(("funding", params))
            return []

        async def fapiPrivateGetAlgoOrder(self, params):
            self.calls.append(("lineage", params))
            return {
                "algoId": 12,
                "actualOrderId": 14,
                "clientAlgoId": "sl",
                "algoStatus": "FINISHED",
            }

    raw = _RawBinance()
    gateway = ExchangeGateway.__new__(ExchangeGateway)
    gateway.exchange_name = "binance"
    gateway.rest_exchange = raw
    gateway.runtime_account_id = "owner-subaccount-runtime-v0"
    gateway.runtime_exchange_id = "binance_usdm"

    snapshot = await gateway.fetch_ticket_lifecycle_snapshot(
        exchange_symbol="ETH/USDT:USDT",
        exchange_market_id="ETHUSDT",
        recent_fill_limit=50,
        funding_start_time_ms=1_000,
        funding_end_time_ms=2_000,
        conditional_parent_order_ids=["12"],
    )

    assert snapshot["exchange_request_count"] == 9
    assert snapshot["positions"][0]["symbol"] == "ETH/USDT:USDT"
    assert snapshot["positions"][0]["size"] == "2"
    assert snapshot["open_orders"][0]["id"] == "11"
    assert snapshot["open_orders"][1]["id"] == "12"
    assert snapshot["recent_fills"][0]["id"] == "13"
    assert snapshot["account_exposure_result"][
        "effective_account_exposure_leverage"
    ] == "2.1"
    assert snapshot["commission_rate"] == {
        "symbol": "ETHUSDT",
        "maker_commission_rate": "0.0002",
        "taker_commission_rate": "0.0005",
    }
    assert snapshot["market_rule"] == {
        "exchange_market_id": "ETHUSDT",
        "quote_asset": "USDT",
        "settle_asset": "USDT",
        "price_tick": "0.1",
        "quantity_step": "0.001",
        "min_notional": "5",
        "source": "binance_usdm_public_exchange_info",
    }
    assert {name for name, _params in raw.calls} == {
        "position",
        "orders",
        "algo_orders",
        "trades",
        "account",
        "commission_rate",
        "exchange_info",
        "funding",
        "lineage",
    }


async def test_exact_entry_trade_recovery_uses_raw_market_id_from_id_and_local_order_filter():
    class _RawBinance:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def fapiPrivateGetUserTrades(self, params):
            self.calls.append(dict(params))
            if params.get("fromId") == 100:
                return [
                    {
                        "id": 100,
                        "orderId": 999,
                        "symbol": "ETHUSDT",
                        "qty": "1",
                        "price": "99",
                        "commission": "0.01",
                        "commissionAsset": "USDT",
                        "time": 1_000,
                    },
                    {
                        "id": 101,
                        "orderId": 42,
                        "symbol": "ETHUSDT",
                        "qty": "1",
                        "price": "100",
                        "commission": "0.01",
                        "commissionAsset": "USDT",
                        "time": 1_001,
                    },
                ]
            return [
                {
                    "id": 102,
                    "orderId": 42,
                    "symbol": "ETHUSDT",
                    "qty": "2",
                    "price": "101",
                    "commission": "0.02",
                    "commissionAsset": "USDT",
                    "time": 1_002,
                }
            ]

    raw = _RawBinance()
    gateway = ExchangeGateway.__new__(ExchangeGateway)
    gateway.exchange_name = "binance"
    gateway.rest_exchange = raw

    result = await gateway.fetch_order_trades_exact(
        exchange_market_id="ETHUSDT",
        exchange_order_id="42",
        entry_order_created_at_ms=1_000,
        entry_order_terminal_at_ms=1_002,
        first_durable_trade_id=100,
        page_limit=2,
        max_pages=2,
        timeout_seconds=1,
    )

    assert result["status"] == "complete"
    assert result["state"] == "FROM_ID_WITH_WINDOW_END_GUARD"
    assert [row["id"] for row in result["trades"]] == [101, 102]
    assert raw.calls == [
        {"symbol": "ETHUSDT", "fromId": 100, "limit": 2},
        {"symbol": "ETHUSDT", "fromId": 102, "limit": 2},
    ]
    assert all("orderId" not in params for params in raw.calls)


async def test_exact_entry_trade_recovery_advances_nonfull_time_windows_and_fails_closed_on_cursor_regression():
    window_ms = 7 * 24 * 60 * 60 * 1000

    class _WindowedRawBinance:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def fapiPrivateGetUserTrades(self, params):
            self.calls.append(dict(params))
            if params["startTime"] == 1:
                return [
                    {
                        "id": 1,
                        "orderId": 9,
                        "symbol": "ETHUSDT",
                        "qty": "1",
                        "price": "100",
                        "commission": "0.01",
                        "commissionAsset": "USDT",
                        "time": 1,
                    }
                ]
            return [
                {
                    "id": 2,
                    "orderId": 42,
                    "symbol": "ETHUSDT",
                    "qty": "2",
                    "price": "101",
                    "commission": "0.02",
                    "commissionAsset": "USDT",
                    "time": window_ms + 2,
                }
            ]

    gateway = ExchangeGateway.__new__(ExchangeGateway)
    gateway.exchange_name = "binance"
    raw = _WindowedRawBinance()
    gateway.rest_exchange = raw
    complete = await gateway.fetch_order_trades_exact(
        exchange_market_id="ETHUSDT",
        exchange_order_id="42",
        entry_order_created_at_ms=1,
        entry_order_terminal_at_ms=window_ms + 2,
        page_limit=2,
        max_pages=2,
        timeout_seconds=1,
    )

    assert complete["status"] == "complete"
    assert complete["state"] == "TIME_WINDOW"
    assert [row["id"] for row in complete["trades"]] == [2]
    assert raw.calls == [
        {"symbol": "ETHUSDT", "limit": 2, "startTime": 1, "endTime": window_ms},
        {
            "symbol": "ETHUSDT",
            "limit": 2,
            "startTime": window_ms + 1,
            "endTime": window_ms + 2,
        },
    ]

    class _NonMonotonicRawBinance:
        async def fapiPrivateGetUserTrades(self, _params):
            return [
                {"id": 2, "orderId": 42, "symbol": "ETHUSDT", "time": 1},
                {"id": 1, "orderId": 42, "symbol": "ETHUSDT", "time": 1},
            ]

    gateway.rest_exchange = _NonMonotonicRawBinance()
    incomplete = await gateway.fetch_order_trades_exact(
        exchange_market_id="ETHUSDT",
        exchange_order_id="42",
        entry_order_created_at_ms=1,
        entry_order_terminal_at_ms=1,
        page_limit=2,
        max_pages=2,
        timeout_seconds=1,
    )

    assert incomplete["status"] == "incomplete"
    assert incomplete["first_blocker"] == "entry_fill_history_incomplete"
