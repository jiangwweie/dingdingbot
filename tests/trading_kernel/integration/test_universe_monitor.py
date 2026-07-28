from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.interfaces.reconciliation_worker import (
    run_reconciliation_worker_once,
)
from tests.trading_kernel.integration.universe_certification_support import (
    MEMBERS,
    NOW_MS,
    RUNTIME_PROFILE_ID,
    RecordingReadonlyCertificationSource,
    worker_request,
)
from tests.trading_kernel.integration.universe_certification_support import (
    certification_engine as _certification_engine,  # noqa: F401
)


@pytest.mark.asyncio
async def test_monitor_appends_only_blocker_changes_and_resolution(
    _certification_engine: AsyncEngine,  # noqa: F811
) -> None:
    """Catches repeated identical blockers producing an unbounded event stream."""

    await _defer_other_member(_certification_engine)
    source = RecordingReadonlyCertificationSource(
        _certification_engine,
        changes={"configured_leverage": 3},
    )
    await _tick(_certification_engine, source, NOW_MS)
    assert await _monitor_counts(_certification_engine) == (
        1,
        1,
    ), await _monitor_rows(_certification_engine)

    await _tick(_certification_engine, source, NOW_MS + 300_000)
    assert await _monitor_counts(_certification_engine) == (1, 1)

    source.changes = {"margin_mode": "isolated"}
    await _tick(_certification_engine, source, NOW_MS + 600_000)
    assert await _monitor_counts(_certification_engine) == (1, 2)

    source.changes = {}
    await _tick(_certification_engine, source, NOW_MS + 900_000)
    async with _certification_engine.connect() as connection:
        monitor = (
            await connection.execute(
                sa.text(
                    "SELECT owner_status, summary, projection_version "
                    "FROM brc_monitor_current "
                    "WHERE summary LIKE 'OWNER_ACTION_REQUIRED:%' "
                    "OR summary = 'instrument_certification:resolved'"
                )
            )
        ).one()
        certification = (
            await connection.execute(
                sa.text(
                    "SELECT status, blocker_code "
                    "FROM brc_instrument_certification_current "
                    "WHERE exchange_instrument_id = :exchange_instrument_id"
                ),
                {"exchange_instrument_id": MEMBERS[0]},
            )
        ).one()

    assert await _monitor_counts(_certification_engine) == (1, 3)
    assert monitor == ("running", "instrument_certification:resolved", 3)
    assert certification == ("eligible", None)


async def _tick(engine, source, now_ms):
    await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(engine),
        object(),
        object(),
        worker_request(now_ms),
        instrument_certification_source=source,
    )


async def _monitor_counts(engine: AsyncEngine) -> tuple[int, int]:
    async with engine.connect() as connection:
        current_count = int(
            (
                await connection.execute(
                    sa.text(
                        "SELECT count(*) FROM brc_monitor_current "
                        "WHERE summary LIKE 'OWNER_ACTION_REQUIRED:%' "
                        "OR summary = 'instrument_certification:resolved'"
                    )
                )
            ).scalar_one()
        )
        event_count = int(
            (
                await connection.execute(
                    sa.text(
                        "SELECT count(*) FROM brc_monitor_events "
                        "WHERE payload ->> 'summary' LIKE 'OWNER_ACTION_REQUIRED:%' "
                        "OR payload ->> 'summary' = 'instrument_certification:resolved'"
                    )
                )
            ).scalar_one()
        )
    return current_count, event_count


async def _monitor_rows(engine: AsyncEngine):
    async with engine.connect() as connection:
        return (
            await connection.execute(
                sa.text(
                    "SELECT monitor_key, owner_status, summary "
                    "FROM brc_monitor_current ORDER BY monitor_key"
                )
            )
        ).all()


async def _defer_other_member(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                """
                INSERT INTO brc_instrument_certification_current (
                    runtime_profile_id,
                    exchange_instrument_id,
                    status,
                    blocker_code,
                    facts_digest,
                    product_rules_digest,
                    configured_leverage,
                    margin_mode,
                    position_mode,
                    observed_at_ms,
                    valid_until_ms,
                    next_check_at_ms,
                    lease_owner,
                    lease_expires_at_ms,
                    projection_version
                )
                VALUES (
                    :runtime_profile_id,
                    :exchange_instrument_id,
                    'temporarily_unavailable',
                    'readonly_facts_unavailable',
                    :facts_digest,
                    NULL,
                    NULL,
                    NULL,
                    NULL,
                    :observed_at_ms,
                    :valid_until_ms,
                    :next_check_at_ms,
                    NULL,
                    NULL,
                    1
                )
                """
            ),
            {
                "exchange_instrument_id": MEMBERS[1],
                "runtime_profile_id": RUNTIME_PROFILE_ID,
                "facts_digest": (
                    "sha256:"
                    "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                ),
                "observed_at_ms": NOW_MS - 1,
                "valid_until_ms": NOW_MS + 1,
                "next_check_at_ms": NOW_MS + 10_000_000,
            },
        )
