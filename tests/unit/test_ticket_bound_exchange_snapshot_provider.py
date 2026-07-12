from src.application.action_time.exchange_scope import TicketBoundExchangeScope
from src.application.action_time.exchange_snapshot_provider import (
    fetch_ticket_bound_exchange_snapshot,
    fetch_resolved_ticket_bound_exchange_snapshot,
)
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
