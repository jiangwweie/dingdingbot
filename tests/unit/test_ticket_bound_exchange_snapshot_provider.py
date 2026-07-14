from src.application.action_time.exchange_scope import TicketBoundExchangeScope
from src.application.action_time.exchange_snapshot_provider import (
    fetch_ticket_bound_exchange_snapshot,
    fetch_resolved_ticket_bound_exchange_snapshot,
)
from src.infrastructure.exchange_gateway import ExchangeGateway
from tests.unit.test_ticket_bound_lifecycle_scheduler import (
    NOW_MS,
    _materialized_exit_protection_set,
    _SchedulerGateway,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


class _Gateway:
    runtime_account_id = "owner-subaccount-runtime-v0"
    runtime_exchange_id = "binance_usdm"

    def __init__(self) -> None:
        self.events: list[str] = []

    async def fetch_all_open_orders(self, symbol: str):
        self.events.append("open_orders")
        return []

    async def fetch_my_trades(self, symbol: str, limit: int = 50):
        self.events.append("trades")
        return []

    async def fetch_position_rows(self, symbol: str):
        self.events.append("positions")
        return [{"symbol": symbol, "size": "0", "side": "long"}]

    async def fetch_funding_income(
        self,
        symbol: str,
        *,
        start_time_ms: int,
        end_time_ms: int,
    ):
        self.events.append("funding")
        return [
            {
                "tranId": "funding-1",
                "symbol": "ETHUSDT",
                "incomeType": "FUNDING_FEE",
                "income": "-0.125",
                "asset": "USDT",
                "time": start_time_ms + 10,
            },
            {
                "tranId": "commission-1",
                "symbol": "ETHUSDT",
                "incomeType": "COMMISSION",
                "income": "-0.01",
                "asset": "USDT",
                "time": start_time_ms + 11,
            },
        ]

    async def fetch_conditional_order_lineage(
        self,
        symbol: str,
        parent_exchange_order_ids: list[str],
    ):
        self.events.append("conditional_lineage")
        assert symbol == "ETH/USDT:USDT"
        assert parent_exchange_order_ids == ["4000001767421460"]
        return [
            {
                "parent_exchange_order_id": "4000001767421460",
                "actual_exchange_order_id": "39574198157",
                "client_order_id": "brc-d8c2da19c7b8338498152eb4cab97088",
                "status": "finished",
            }
        ]


def _scope() -> TicketBoundExchangeScope:
    return TicketBoundExchangeScope(
        ticket_id="ticket-1",
        strategy_group_id="CPM-RO-001",
        runtime_profile_id="profile-1",
        runtime_scope_binding_id="scope-1",
        runtime_scope_status="active",
        account_id="owner-subaccount-runtime-v0",
        canonical_symbol="ETHUSDT",
        exchange_instrument_id="binance_usdm:ETHUSDT",
        exchange_instrument_status="active",
        exchange_id="binance_usdm",
        exchange_symbol="ETH/USDT:USDT",
        asset_class="crypto_perpetual",
        side="long",
        position_mode="one_way",
        position_side=None,
        position_bucket="BOTH",
        netting_domain_key="owner-subaccount-runtime-v0|binance_usdm:ETHUSDT|one_way|BOTH",
        account_mode_snapshot_id="mode-1",
        current_account_mode_snapshot_id="mode-2",
        current_entry_eligible=True,
        current_entry_blockers=[],
    )


async def test_snapshot_reads_and_normalizes_signed_funding_without_exchange_write():
    gateway = _Gateway()

    payload = await fetch_resolved_ticket_bound_exchange_snapshot(
        scope=_scope(),
        snapshot_identity="protection-1",
        gateway=gateway,
        timeout_seconds=1,
        recent_fill_limit=50,
        funding_start_time_ms=1000,
        funding_end_time_ms=2000,
        now_ms=2000,
    )

    assert payload["status"] == "snapshot_ready"
    assert gateway.events == ["open_orders", "trades", "positions", "funding"]
    assert payload["snapshot"]["funding_income"] == [
        {
            "income_id": "funding-1",
            "ticket_id": "ticket-1",
            "symbol": "ETHUSDT",
            "income_type": "FUNDING_FEE",
            "amount": "-0.125",
            "asset": "USDT",
            "timestamp_ms": 1010,
            "attribution_basis": "single_active_position_exact_symbol_time_window",
        }
    ]
    assert payload["snapshot"]["funding_income_available"] is True
    assert payload["snapshot"]["exchange_write_called"] is False


async def test_snapshot_includes_optional_signed_account_exposure_truth():
    class _ExposureGateway(_Gateway):
        async def fetch_account_exposure_snapshot(self):
            self.events.append("account_exposure")
            return {
                "status": "ready",
                "account_id": "owner-subaccount-runtime-v0",
                "exchange_id": "binance_usdm",
                "account_margin_balance": "100",
                "gross_open_position_notional": "250",
                "effective_account_exposure_leverage": "2.5",
                "observed_at_ms": 1999,
                "blockers": [],
            }

    gateway = _ExposureGateway()
    payload = await fetch_resolved_ticket_bound_exchange_snapshot(
        scope=_scope(),
        snapshot_identity="protection-1",
        gateway=gateway,
        timeout_seconds=1,
        recent_fill_limit=50,
        now_ms=2000,
    )

    assert payload["status"] == "snapshot_ready"
    assert payload["snapshot"]["account_exposure"] == {
        "status": "ready",
        "account_id": "owner-subaccount-runtime-v0",
        "exchange_id": "binance_usdm",
        "account_margin_balance": "100",
        "gross_open_position_notional": "250",
        "effective_account_exposure_leverage": "2.5",
        "observed_at_ms": 1999,
        "blockers": [],
    }
    assert payload["snapshot"]["exchange_write_called"] is False


async def test_snapshot_nulls_mismatched_or_stale_effective_leverage_truth():
    class _MismatchedExposureGateway(_Gateway):
        async def fetch_account_exposure_snapshot(self):
            return {
                "status": "ready",
                "account_id": "other-account",
                "exchange_id": "binance_usdm",
                "account_margin_balance": "100",
                "gross_open_position_notional": "250",
                "effective_account_exposure_leverage": "2.5",
                "observed_at_ms": 1,
                "blockers": [],
            }

    payload = await fetch_resolved_ticket_bound_exchange_snapshot(
        scope=_scope(),
        snapshot_identity="protection-1",
        gateway=_MismatchedExposureGateway(),
        timeout_seconds=1,
        recent_fill_limit=50,
        now_ms=40_000,
    )

    exposure = payload["snapshot"]["account_exposure"]
    assert exposure["status"] == "invalid"
    assert exposure["effective_account_exposure_leverage"] is None
    assert exposure["blockers"] == [
        "account_exposure_account_mismatch",
        "account_exposure_snapshot_stale",
    ]


async def test_snapshot_binds_binance_conditional_parent_to_actual_fill():
    gateway = _Gateway()

    async def fetch_my_trades(symbol: str, limit: int = 50):
        gateway.events.append("trades")
        return [
            {
                "order": "39574198157",
                "symbol": symbol,
                "side": "buy",
                "amount": "215",
                "price": "6.482",
                "timestamp": 1783990510789,
            }
        ]

    gateway.fetch_my_trades = fetch_my_trades
    payload = await fetch_resolved_ticket_bound_exchange_snapshot(
        scope=_scope(),
        snapshot_identity="protection-1",
        gateway=gateway,
        timeout_seconds=1,
        recent_fill_limit=50,
        conditional_parent_order_ids=["4000001767421460"],
        now_ms=1783990511000,
    )

    assert payload["status"] == "snapshot_ready"
    assert payload["snapshot"]["conditional_order_lineage"] == [
        {
            "parent_exchange_order_id": "4000001767421460",
            "actual_exchange_order_id": "39574198157",
            "client_order_id": "brc-d8c2da19c7b8338498152eb4cab97088",
            "status": "finished",
        }
    ]
    assert payload["snapshot"]["recent_fills"][0]["exchange_order_id"] == (
        "39574198157"
    )
    assert payload["snapshot"]["recent_fills"][0][
        "parent_exchange_order_id"
    ] == "4000001767421460"
    assert payload["snapshot"]["exchange_write_called"] is False


async def test_binance_gateway_reads_exact_conditional_order_lineage():
    class _RestExchange:
        async def fapiPrivateGetAlgoOrder(self, params):
            assert params == {"algoId": "4000001767421460"}
            return {
                "algoId": 4000001767421460,
                "clientAlgoId": "brc-d8c2da19c7b8338498152eb4cab97088",
                "actualOrderId": "39574198157",
                "symbol": "AVAXUSDT",
                "side": "BUY",
                "positionSide": "SHORT",
                "orderType": "STOP_MARKET",
                "algoStatus": "FINISHED",
                "triggerPrice": "6.4790",
                "quantity": "215",
                "actualQty": "215",
                "triggerTime": 1783990510788,
                "reduceOnly": True,
                "closePosition": False,
            }

    gateway = ExchangeGateway.__new__(ExchangeGateway)
    gateway.exchange_name = "binance"
    gateway.rest_exchange = _RestExchange()

    rows = await gateway.fetch_conditional_order_lineage(
        "AVAX/USDT:USDT",
        ["4000001767421460"],
    )

    assert rows[0]["parent_exchange_order_id"] == "4000001767421460"
    assert rows[0]["actual_exchange_order_id"] == "39574198157"
    assert rows[0]["status"] == "finished"
    assert rows[0]["reduce_only"] is True


async def test_snapshot_keeps_funding_optional_for_existing_gateways():
    gateway = _Gateway()
    gateway.fetch_funding_income = None

    payload = await fetch_resolved_ticket_bound_exchange_snapshot(
        scope=_scope(),
        snapshot_identity="protection-1",
        gateway=gateway,
        timeout_seconds=1,
        recent_fill_limit=50,
        funding_start_time_ms=1000,
        funding_end_time_ms=2000,
        now_ms=2000,
    )

    assert payload["status"] == "snapshot_ready"
    assert payload["snapshot"]["funding_income"] == []
    assert payload["snapshot"]["funding_income_available"] is False


async def test_snapshot_funding_failure_does_not_block_lifecycle_truth():
    gateway = _Gateway()

    async def failed_funding(*_args, **_kwargs):
        raise TimeoutError("funding endpoint timeout")

    gateway.fetch_funding_income = failed_funding

    payload = await fetch_resolved_ticket_bound_exchange_snapshot(
        scope=_scope(),
        snapshot_identity="protection-1",
        gateway=gateway,
        timeout_seconds=1,
        recent_fill_limit=50,
        funding_start_time_ms=1000,
        funding_end_time_ms=2000,
        now_ms=2000,
    )

    assert payload["status"] == "snapshot_ready"
    assert payload["snapshot"]["funding_income"] == []
    assert payload["snapshot"]["funding_income_available"] is False
    assert payload["snapshot"]["funding_income_error"] == "TimeoutError"


async def test_ticket_snapshot_derives_funding_window_from_entry_fill(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    gateway = _SchedulerGateway()
    funding_windows: list[tuple[int, int]] = []

    async def fetch_funding_income(
        symbol: str,
        *,
        start_time_ms: int,
        end_time_ms: int,
    ):
        funding_windows.append((start_time_ms, end_time_ms))
        return [
            {
                "tranId": "funding-entry-window",
                "symbol": "ETHUSDT",
                "incomeType": "FUNDING_FEE",
                "income": "0.05",
                "asset": "USDT",
                "time": start_time_ms,
            }
        ]

    gateway.fetch_funding_income = fetch_funding_income

    payload = await fetch_ticket_bound_exchange_snapshot(
        pg_control_connection,
        exit_protection_set_id=set_id,
        gateway=gateway,
        now_ms=NOW_MS + 10_000,
    )

    assert funding_windows == [(NOW_MS + 6_000, NOW_MS + 10_000)]
    assert payload["snapshot"]["funding_income"][0]["amount"] == "0.05"
