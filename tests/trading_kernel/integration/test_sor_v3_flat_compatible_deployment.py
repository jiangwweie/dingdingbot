from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from migrations.trading_kernel import v4_schema
from scripts.trading_kernel.verify_schema import (
    _verify_compatible_source,
    _verify_preservation,
)
from tests.trading_kernel.integration.test_sor_v3_compatible_migration import (
    HEAD_REVISION,
    V4_REVISION,
    _run_migration,
    _seed_v4_history,
    compatible_migration_engine,
)

__all__ = ["compatible_migration_engine"]


async def test_v4_manifest_is_identical_after_compatible_upgrade(
    compatible_migration_engine: AsyncEngine,
) -> None:
    engine = compatible_migration_engine
    await _seed_v4_history(engine)
    database_url = engine.url.render_as_string(hide_password=False)

    source = await _verify_compatible_source(database_url, V4_REVISION)
    digest = str(source["preservation_manifest"]["digest"])
    result = _run_migration(database_url, "upgrade", "head")
    assert result.returncode == 0, result.stderr[-4000:]

    target = await _verify_preservation(
        database_url,
        source_revision=V4_REVISION,
        expected_digest=digest,
    )

    assert target["status"] == "pass"
    assert target["alembic_revision"] == HEAD_REVISION
    assert target["preservation_manifest"] == source["preservation_manifest"]


async def test_source_gate_reports_every_runtime_residue_without_mutation(
    compatible_migration_engine: AsyncEngine,
) -> None:
    engine = compatible_migration_engine
    await _seed_v4_history(engine)
    async with engine.begin() as connection:
        await connection.execute(
            sa.delete(v4_schema.trade_reviews).where(
                v4_schema.trade_reviews.c.ticket_id == "ticket-v2-1"
            )
        )
        await connection.execute(
            sa.insert(v4_schema.positions_current).values(
                netting_domain_key="domain-v2-2",
                ticket_id="ticket-v2-2",
                venue_id="binance-usdm",
                account_id="account-main",
                exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
                position_side="long",
                quantity=1,
                average_entry_price=100,
                venue_reported_liquidation_price=None,
                venue_reported_liquidation_observation_status="unavailable",
                observed_at_ms=2_200,
                projection_version=1,
            )
        )
    database_url = engine.url.render_as_string(hide_password=False)

    source = await _verify_compatible_source(database_url, V4_REVISION)

    assert source["status"] == "fail"
    assert source["migration_gate"] == {
        "active_tickets": 1,
        "non_flat_positions": 1,
        "active_reservations": 1,
        "active_domains": 1,
        "unreviewed_terminal_tickets": 1,
        "unresolved_commands": 1,
        "open_incidents": 1,
    }
    async with engine.connect() as connection:
        assert await connection.scalar(
            sa.text("SELECT version_num FROM alembic_version")
        ) == V4_REVISION


async def test_preservation_verification_detects_one_changed_v4_value(
    compatible_migration_engine: AsyncEngine,
) -> None:
    engine = compatible_migration_engine
    await _seed_v4_history(engine)
    database_url = engine.url.render_as_string(hide_password=False)
    source = await _verify_compatible_source(database_url, V4_REVISION)
    digest = str(source["preservation_manifest"]["digest"])
    result = _run_migration(database_url, "upgrade", "head")
    assert result.returncode == 0, result.stderr[-4000:]

    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "UPDATE brc_trade_tickets SET status = 'tampered' "
                "WHERE ticket_id = 'ticket-v2-1'"
            )
        )

    target = await _verify_preservation(
        database_url,
        source_revision=V4_REVISION,
        expected_digest=digest,
    )

    assert target["status"] == "fail"
    assert target["preservation_manifest"]["digest"] != digest
