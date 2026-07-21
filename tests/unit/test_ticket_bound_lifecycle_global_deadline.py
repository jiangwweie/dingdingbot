from __future__ import annotations

# ruff: noqa: F401, F811

import asyncio
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from scripts import run_ticket_bound_lifecycle_maintenance_once as lifecycle_cli
from src.application.action_time import exchange_command_worker
from src.infrastructure.binance_usdm_account_risk_snapshot import FullAccountRiskSnapshot
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_protected_submit_attempt import (
    _create_ready_protected_submit,
    _prepare_real_submit,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


def test_cli_global_deadline_defaults_below_systemd_timeout():
    args = lifecycle_cli._parse_args(["--database-url", "postgresql://unit"])

    assert args.global_deadline_seconds == 28.0
    assert args.global_deadline_seconds < 35.0


def test_expired_global_deadline_blocks_next_stage(monkeypatch):
    monkeypatch.setattr(lifecycle_cli.time, "monotonic", lambda: 100.0)

    with pytest.raises(
        TimeoutError,
        match="lifecycle_global_deadline_exceeded:exchange_snapshot",
    ):
        lifecycle_cli._remaining_seconds(100.0, "exchange_snapshot")


@pytest.mark.asyncio
async def test_awaitable_is_cancelled_when_global_deadline_expires(monkeypatch):
    monkeypatch.setattr(lifecycle_cli.time, "monotonic", lambda: 100.0)
    coroutine = asyncio.sleep(0)
    try:
        with pytest.raises(TimeoutError):
            await lifecycle_cli._await_before_deadline(
                coroutine,
                deadline_at=100.0,
                stage="durable_exchange_command",
            )
    finally:
        coroutine.close()


@pytest.mark.asyncio
async def test_entry_drain_uses_the_invocation_absolute_deadline_without_resetting_budget(
    monkeypatch,
    pg_control_connection,
):
    """ENTRY can consume the invocation budget; the SL drain cannot renew it."""

    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.commit()
    clock = {"now": 100.0}

    class DeadlineConsumingGateway:
        runtime_account_id = "owner-subaccount-runtime-v0"
        runtime_exchange_id = "binance_usdm"

        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def place_order(self, **kwargs):
            self.calls.append(dict(kwargs))
            if kwargs["order_type"] == "market":
                clock["now"] = 109.999
            return SimpleNamespace(
                is_success=True,
                exchange_order_id=f"exchange-{kwargs['client_order_id']}",
                filled_qty=kwargs["amount"],
                average_exec_price=Decimal("2000"),
                exchange_order_status="FILLED",
            )

    monkeypatch.setattr(
        exchange_command_worker.time,
        "monotonic",
        lambda: clock["now"],
    )
    gateway = DeadlineConsumingGateway()
    result = await exchange_command_worker.run_one_ticket_bound_exchange_command(
        pg_control_connection.engine,
        gateway=gateway,
        worker_id="absolute-deadline-worker",
        now_ms=NOW_MS + 5000,
        command_sources=("protected_submit",),
        dispatch_timeout_seconds=10.0,
        absolute_deadline_at=110.0,
        drain_initial_protection=True,
    )

    assert result["order_role"] == "ENTRY"
    assert result["initial_protection_complete"] is False
    assert [call["order_type"] for call in gateway.calls] == ["market"]
    assert pg_control_connection.execute(
        text(
            "SELECT command_state FROM brc_ticket_bound_exchange_commands "
            "WHERE order_role = 'SL'"
        )
    ).scalar_one() == "prepared"


def test_gateway_probe_owns_durable_protected_submit_command_source(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)

    assert (
        lifecycle_cli._prepared_or_unknown_command_exists(pg_control_connection)
        is True
    )

    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_exchange_commands "
            "SET command_source = 'protection_recovery' "
            "WHERE order_role = 'SL'"
        )
    )

    assert (
        lifecycle_cli._prepared_or_unknown_command_exists(pg_control_connection)
        is True
    )


def test_active_account_risk_scope_requires_matching_active_policy(
    monkeypatch,
):
    class _Policies:
        c = SimpleNamespace(
            account_id="account_id",
            runtime_profile_id="runtime_profile_id",
            activation_state="activation_state",
        )

    class _Conn:
        def execute(self, _query):
            return SimpleNamespace(
                mappings=lambda: [
                    {
                        "account_id": "account-1",
                        "runtime_profile_id": "profile-1",
                    }
                ]
            )

    monkeypatch.setattr(lifecycle_cli.sa, "inspect", lambda _conn: SimpleNamespace(has_table=lambda _name: True))
    monkeypatch.setattr(lifecycle_cli.sa, "Table", lambda *_args, **_kwargs: _Policies())
    monkeypatch.setattr(lifecycle_cli.sa, "select", lambda *_args: SimpleNamespace(where=lambda *_args: object()))
    scopes = lifecycle_cli._active_account_risk_scopes(
        _Conn(),
        prepared_scopes=[
            {
                "scope": SimpleNamespace(
                    ticket_id="ticket-1",
                    account_id="account-1",
                    runtime_profile_id="profile-1",
                    exchange_id="binance_usdm",
                )
            },
            {
                "scope": SimpleNamespace(
                    ticket_id="ticket-2",
                    account_id="account-1",
                    runtime_profile_id="profile-other",
                    exchange_id="binance_usdm",
                )
            },
        ],
    )

    assert scopes == {
        "account_risk_scope:account-1:profile-1": (
            "account-1",
            "profile-1",
            "binance_usdm",
        ),
        "ticket-1": ("account-1", "profile-1", "binance_usdm"),
    }


@pytest.mark.asyncio
async def test_account_risk_snapshot_prefetch_deduplicates_account_reads(monkeypatch):
    calls: list[tuple[str, str]] = []

    async def fake_fetch(**kwargs):
        calls.append((kwargs["account_id"], kwargs["exchange_id"]))
        return _account_snapshot(kwargs["account_id"], kwargs["exchange_id"])

    monkeypatch.setattr(lifecycle_cli, "_fetch_account_risk_snapshot", fake_fetch)
    snapshots = await lifecycle_cli._prefetch_account_risk_snapshots(
        {
            "ticket-a": ("account-1", "profile-1", "binance_usdm"),
            "ticket-b": ("account-1", "profile-1", "binance_usdm"),
        },
        env_file=Path("/nonexistent"),
        base_url="https://example.invalid",
        timeout_seconds=1.0,
    )

    assert calls == [("account-1", "binance_usdm")]
    assert snapshots["ticket-a"] is snapshots["ticket-b"]
    assert snapshots["ticket-a"].account_id == "account-1"


def _account_snapshot(account_id: str, exchange_id: str) -> FullAccountRiskSnapshot:
    return FullAccountRiskSnapshot(
        snapshot_ready=True,
        account_id=account_id,
        exchange_id=exchange_id,
        total_wallet_balance=Decimal("600"),
        available_balance=Decimal("500"),
        exchange_total_initial_margin=Decimal("100"),
        can_trade=True,
        position_mode="one_way",
        source_snapshot_id="snapshot-1",
        observed_at_ms=1_752_480_000_000,
        valid_until_ms=1_752_480_060_000,
    )
