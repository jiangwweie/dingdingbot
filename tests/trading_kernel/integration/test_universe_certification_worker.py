from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.interfaces.reconciliation_worker import (
    ReconciliationWorkerStatus,
    run_reconciliation_worker_once,
)
from tests.trading_kernel.integration.universe_certification_support import (
    MEMBERS,
    NOW_MS,
    NoTicketPositionSource,
    NoTicketVenueTruth,
    RecordingReadonlyCertificationSource,
    worker_request,
)
from tests.trading_kernel.integration.universe_certification_support import (
    certification_engine as _certification_engine,  # noqa: F401
)


@pytest.mark.asyncio
async def test_worker_claims_one_target_and_reads_after_claim_transaction_commits(
    _certification_engine: AsyncEngine,  # noqa: F811
) -> None:
    """Catches batch certification or authenticated I/O under a database lock."""

    source = RecordingReadonlyCertificationSource(_certification_engine)

    result = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(_certification_engine),
        NoTicketVenueTruth(),
        NoTicketPositionSource(),
        worker_request(NOW_MS),
        instrument_certification_source=source,
    )

    async with _certification_engine.connect() as connection:
        certifications = (
            await connection.execute(
                sa.text(
                    "SELECT exchange_instrument_id, status, lease_owner "
                    "FROM brc_instrument_certification_current "
                    "ORDER BY exchange_instrument_id"
                )
            )
        ).all()
        instruments = (
            await connection.execute(
                sa.text(
                    "SELECT exchange_instrument_id, status FROM brc_instruments "
                    "ORDER BY exchange_instrument_id"
                )
            )
        ).all()
        universe_state = (
            await connection.execute(
                sa.text(
                    "SELECT lifecycle_state FROM brc_strategy_universe_versions"
                )
            )
        ).scalar_one()
        active_pointer_count = int(
            await connection.scalar(
                sa.text(
                    "SELECT count(*) FROM brc_strategy_universe_current"
                )
            )
            or 0
        )

    assert result.status is ReconciliationWorkerStatus.INSTRUMENT_CERTIFIED
    assert len(source.requests) == 1
    assert certifications == [(MEMBERS[0], "eligible", None)]
    assert instruments == [
        (MEMBERS[0], "active"),
        (MEMBERS[1], "pending_certification"),
    ]
    assert universe_state == "warming"
    assert active_pointer_count == 0
    assert source.mutation_calls == []


@pytest.mark.asyncio
async def test_last_eligible_certification_auto_activates_fully_warmed_universe(
    _certification_engine: AsyncEngine,  # noqa: F811
) -> None:
    """Catches certification persistence stopping before DB-only activation."""

    async with _certification_engine.begin() as connection:
        await connection.execute(
            sa.text(
                "UPDATE brc_runtime_scopes_current "
                "SET warm_closed_bar_time_ms = :warm_closed_bar_time_ms, "
                "warm_completed_at_ms = :warm_completed_at_ms, "
                "warm_readiness_digest = :digest, "
                "warm_valid_until_ms = :valid_until_ms "
                "WHERE lifecycle_state = 'warming'"
            ),
            {
                "warm_closed_bar_time_ms": NOW_MS - 1,
                "warm_completed_at_ms": NOW_MS - 1,
                "digest": "sha256:" + ("d" * 64),
                "valid_until_ms": NOW_MS + 60_000,
            },
        )
    source = RecordingReadonlyCertificationSource(_certification_engine)

    first = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(_certification_engine),
        NoTicketVenueTruth(),
        NoTicketPositionSource(),
        worker_request(NOW_MS),
        instrument_certification_source=source,
    )
    async with _certification_engine.connect() as connection:
        after_first = (
            await connection.execute(
                sa.text(
                    "SELECT lifecycle_state "
                    "FROM brc_strategy_universe_versions"
                )
            )
        ).scalar_one()
        pointer_after_first = int(
            await connection.scalar(
                sa.text(
                    "SELECT count(*) FROM brc_strategy_universe_current"
                )
            )
            or 0
        )

    second = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(_certification_engine),
        NoTicketVenueTruth(),
        NoTicketPositionSource(),
        worker_request(NOW_MS),
        instrument_certification_source=source,
    )
    async with _certification_engine.connect() as connection:
        current = (
            await connection.execute(
                sa.text(
                    "SELECT lifecycle_state, activation_generation "
                    "FROM brc_strategy_universe_current"
                )
            )
        ).one()
        version_state = (
            await connection.execute(
                sa.text(
                    "SELECT lifecycle_state "
                    "FROM brc_strategy_universe_versions"
                )
            )
        ).scalar_one()
        scope_states = (
            await connection.execute(
                sa.text(
                    "SELECT lifecycle_state, observation_enabled, "
                    "entry_enabled "
                    "FROM brc_runtime_scopes_current "
                    "ORDER BY exchange_instrument_id"
                )
            )
        ).all()

    assert first.status is ReconciliationWorkerStatus.INSTRUMENT_CERTIFIED
    assert after_first == "warming"
    assert pointer_after_first == 0
    assert second.status is ReconciliationWorkerStatus.INSTRUMENT_CERTIFIED
    assert current == ("active", 1)
    assert version_state == "active"
    assert scope_states == [
        ("active", True, True),
        ("active", True, True),
    ]
    assert len(source.requests) == len(MEMBERS)
    assert source.mutation_calls == []


@pytest.mark.asyncio
async def test_transient_failure_releases_lease_for_bounded_retry(
    _certification_engine: AsyncEngine,  # noqa: F811
) -> None:
    """Catches timeout claims that remain permanently leased."""

    source = RecordingReadonlyCertificationSource(
        _certification_engine,
        error=TimeoutError("readonly timeout"),
    )

    result = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(_certification_engine),
        NoTicketVenueTruth(),
        NoTicketPositionSource(),
        worker_request(NOW_MS),
        instrument_certification_source=source,
    )

    async with _certification_engine.connect() as connection:
        row = (
            await connection.execute(
                sa.text(
                    "SELECT status, blocker_code, next_check_at_ms, "
                    "lease_owner, lease_expires_at_ms "
                    "FROM brc_instrument_certification_current"
                )
            )
        ).one()

    assert result.status is ReconciliationWorkerStatus.INSTRUMENT_CERTIFIED
    assert row == (
        "temporarily_unavailable",
        "readonly_facts_unavailable",
        NOW_MS + 30_000,
        None,
        None,
    )


@pytest.mark.asyncio
async def test_expired_claims_are_recoverable_after_worker_crash(
    _certification_engine: AsyncEngine,  # noqa: F811
) -> None:
    """Catches a crash after claim leaving certification targets unrecoverable."""

    async with PostgresKernelUnitOfWork(_certification_engine) as uow:
        first = await uow.strategy_universes.claim_due_instrument_certification(
            worker_id="worker-a",
            now_ms=NOW_MS,
            lease_until_ms=NOW_MS + 60_000,
        )
    async with PostgresKernelUnitOfWork(_certification_engine) as uow:
        second = await uow.strategy_universes.claim_due_instrument_certification(
            worker_id="worker-b",
            now_ms=NOW_MS,
            lease_until_ms=NOW_MS + 60_000,
        )
    async with PostgresKernelUnitOfWork(_certification_engine) as uow:
        none_due = await uow.strategy_universes.claim_due_instrument_certification(
            worker_id="worker-c",
            now_ms=NOW_MS + 30_000,
            lease_until_ms=NOW_MS + 90_000,
        )
    async with PostgresKernelUnitOfWork(_certification_engine) as uow:
        recovered = await uow.strategy_universes.claim_due_instrument_certification(
            worker_id="worker-c",
            now_ms=NOW_MS + 60_000,
            lease_until_ms=NOW_MS + 120_000,
        )

    assert first is not None
    assert second is not None
    assert {
        first.exchange_instrument_id,
        second.exchange_instrument_id,
    } == set(MEMBERS)
    assert none_due is None
    assert recovered is not None
    assert recovered.exchange_instrument_id in MEMBERS
