from types import SimpleNamespace

import pytest

from scripts.trading_kernel import certify_readonly as certification
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION


@pytest.mark.asyncio
async def test_readonly_feed_uses_actual_read_time_not_pre_connection_start(
    head_template_engine, monkeypatch
):
    e = head_template_engine
    async with PostgresKernelUnitOfWork(e) as u:
        await seed_runtime_authority(
            u,
            RuntimeAuthoritySeedRequest(
                account_id="clock-account",
                runtime_commit="a" * 40,
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=1000,
            ),
        )
        scope = "brc-app-manual-v1:binance-usdm:clock-account"
        await u.management.start_feed(
            scope_key=scope,
            epoch_id="clock-epoch",
            worker_id="receiver",
            runtime_commit="a" * 40,
            now_ms=1500,
        )
        await u.management.persist_stream_batch(
            scope_key=scope,
            epoch_id="clock-epoch",
            events=[],
            connected_at_ms=1500,
            now_ms=1500,
        )
    # The receiver can commit after certifier startup but before its RR snapshot.
    readings = iter([1.0, 2.0])
    monkeypatch.setattr(
        certification, "time", SimpleNamespace(time=lambda: next(readings))
    )
    result = await certification._certify(
        e.url.render_as_string(hide_password=False), require_flat=True
    )
    assert result["management_feed_pass"] is True
    # Explicit replay time keeps strict as-of semantics, including future rejection.
    result = await certification._certify(
        e.url.render_as_string(hide_password=False), require_flat=True, now_ms=1000
    )
    assert result["management_feed_pass"] is False


async def test_integrity_pass_does_not_hide_management_trading_blocker(
    head_template_engine,
):
    e = head_template_engine
    async with PostgresKernelUnitOfWork(e) as u:
        await seed_runtime_authority(
            u,
            RuntimeAuthoritySeedRequest(
                account_id="feed-gap-account",
                runtime_commit="a" * 40,
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=1000,
            ),
        )
        scope = "brc-app-manual-v1:binance-usdm:feed-gap-account"
        await u.management.start_feed(
            scope_key=scope,
            epoch_id="gap-epoch",
            worker_id="receiver",
            runtime_commit="a" * 40,
            now_ms=1500,
        )
        await u.management.persist_stream_batch(
            scope_key=scope,
            epoch_id="gap-epoch",
            events=[],
            connected_at_ms=1500,
            now_ms=1500,
        )
        await u.management.persist_stream_batch(
            scope_key=scope,
            epoch_id="gap-epoch",
            events=[],
            connected_at_ms=1500,
            now_ms=1600,
            gap_reason="management_stream_protocol_invalid",
        )
    result = await certification._certify(
        e.url.render_as_string(hide_password=False), require_flat=True, now_ms=1700
    )
    assert result["status"] == "pass" and result["database_integrity_pass"]
    assert (
        result["entry_recovery_ready"] is False
        and result["management_feed_pass"] is False
    )
    assert (
        result["management_feed"]["blocker_code"]
        == "management_stream_protocol_invalid"
    )
    assert result["management_feed"]["blocked_since_ms"] == 1600
