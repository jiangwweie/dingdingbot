from __future__ import annotations

import asyncio

import pytest

from scripts import run_ticket_bound_lifecycle_maintenance_once as lifecycle_cli


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
