from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from scripts import run_ticket_bound_lifecycle_maintenance_once as lifecycle_cli
from src.infrastructure.binance_usdm_account_risk_snapshot import FullAccountRiskSnapshot
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


def test_gateway_probe_owns_only_lifecycle_mutation_command_sources(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)

    assert (
        lifecycle_cli._prepared_or_unknown_command_exists(pg_control_connection)
        is False
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
