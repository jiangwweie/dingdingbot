from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.application.certification_batch import (
    StartCertificationBatchRequest,
    start_certification_batch,
)
from src.trading_kernel.domain.instrument_certification import (
    CertificationBatchStatus,
    build_certification_manifest_digest,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    OWNER_POLICY_ID,
    RUNTIME_PROFILE_ID,
    RuntimeAuthoritySeedRequest,
    build_runtime_seed_identity,
)
from src.trading_kernel.interfaces.reconciliation_worker import (
    ReconciliationWorkerStatus,
    run_reconciliation_worker_once,
)
from tests.trading_kernel.integration.universe_certification_support import (
    MEMBERS,
    NOW_MS,
    RUNTIME_COMMIT,
    SCHEMA_REVISION,
    NoTicketPositionSource,
    NoTicketVenueTruth,
    RecordingReadonlyCertificationSource,
    worker_request,
)
from tests.trading_kernel.integration.universe_certification_support import (
    certification_engine as _certification_engine,  # noqa: F401
)


@pytest.mark.asyncio
async def test_last_member_atomically_completes_exact_release_batch(
    _certification_engine: AsyncEngine,  # noqa: F811
) -> None:
    """Catches deployment counting unrelated current certification rows."""

    seed_identity = build_runtime_seed_identity(
        RuntimeAuthoritySeedRequest(
            account_id="subaccount-certification-test",
            runtime_commit=RUNTIME_COMMIT,
            schema_revision=SCHEMA_REVISION,
            seeded_at_ms=NOW_MS - 10_000,
        )
    )
    request = StartCertificationBatchRequest(
        certification_batch_id="certification-batch:test-release",
        runtime_profile_id=RUNTIME_PROFILE_ID,
        target_commit=RUNTIME_COMMIT,
        target_schema_revision=SCHEMA_REVISION,
        target_seed_identity=seed_identity,
        owner_policy_id=OWNER_POLICY_ID,
        owner_policy_version=1,
        exchange_instrument_ids=MEMBERS,
        started_at_ms=NOW_MS,
        minimum_valid_until_ms=NOW_MS + 50_000,
    )
    async with PostgresKernelUnitOfWork(_certification_engine) as uow:
        started = await start_certification_batch(uow, request)
    assert started.status is CertificationBatchStatus.PENDING
    assert started.manifest_digest == build_certification_manifest_digest(MEMBERS)

    source = RecordingReadonlyCertificationSource(_certification_engine)
    first = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(_certification_engine),
        NoTicketVenueTruth(),
        NoTicketPositionSource(),
        worker_request(NOW_MS),
        instrument_certification_source=source,
    )
    second = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(_certification_engine),
        NoTicketVenueTruth(),
        NoTicketPositionSource(),
        worker_request(NOW_MS),
        instrument_certification_source=source,
    )

    async with _certification_engine.connect() as connection:
        batch = (
            await connection.execute(
                sa.text(
                    "SELECT status, completed_at_ms, valid_until_ms, blocker_code "
                    "FROM brc_instrument_certification_batches "
                    "WHERE certification_batch_id = :batch_id"
                ),
                {"batch_id": request.certification_batch_id},
            )
        ).one()
        members = (
            await connection.execute(
                sa.text(
                    "SELECT exchange_instrument_id, status, facts_digest, "
                    "product_rules_digest FROM "
                    "brc_instrument_certification_batch_members "
                    "WHERE certification_batch_id = :batch_id "
                    "ORDER BY exchange_instrument_id"
                ),
                {"batch_id": request.certification_batch_id},
            )
        ).all()

    assert first.status is ReconciliationWorkerStatus.INSTRUMENT_CERTIFIED
    assert second.status is ReconciliationWorkerStatus.INSTRUMENT_CERTIFIED
    assert batch == ("completed", NOW_MS, NOW_MS + 600_000, None)
    assert [(row[0], row[1]) for row in members] == [
        (instrument_id, "eligible") for instrument_id in MEMBERS
    ]
    assert all(row[2] is not None and row[3] is not None for row in members)
    assert source.mutation_calls == []


@pytest.mark.asyncio
async def test_blocked_batch_is_immutable_and_retry_uses_new_batch(
    _certification_engine: AsyncEngine,  # noqa: F811
) -> None:
    """Catches refreshing current facts by rewriting a failed release proof."""

    seed_identity = build_runtime_seed_identity(
        RuntimeAuthoritySeedRequest(
            account_id="subaccount-certification-test",
            runtime_commit=RUNTIME_COMMIT,
            schema_revision=SCHEMA_REVISION,
            seeded_at_ms=NOW_MS - 10_000,
        )
    )

    def request(batch_id: str, started_at_ms: int) -> StartCertificationBatchRequest:
        return StartCertificationBatchRequest(
            certification_batch_id=batch_id,
            runtime_profile_id=RUNTIME_PROFILE_ID,
            target_commit=RUNTIME_COMMIT,
            target_schema_revision=SCHEMA_REVISION,
            target_seed_identity=seed_identity,
            owner_policy_id=OWNER_POLICY_ID,
            owner_policy_version=1,
            exchange_instrument_ids=MEMBERS,
            started_at_ms=started_at_ms,
            minimum_valid_until_ms=started_at_ms + 50_000,
        )

    async with PostgresKernelUnitOfWork(_certification_engine) as uow:
        await start_certification_batch(
            uow,
            request("certification-batch:blocked", NOW_MS),
        )
    blocked_source = RecordingReadonlyCertificationSource(
        _certification_engine,
        changes={"configured_leverage": 3},
    )
    await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(_certification_engine),
        NoTicketVenueTruth(),
        NoTicketPositionSource(),
        worker_request(NOW_MS),
        instrument_certification_source=blocked_source,
    )

    retry_now_ms = NOW_MS + 300_000
    async with PostgresKernelUnitOfWork(_certification_engine) as uow:
        retried = await start_certification_batch(
            uow,
            request("certification-batch:retry", retry_now_ms),
        )
    assert retried.status is CertificationBatchStatus.PENDING

    healthy_source = RecordingReadonlyCertificationSource(_certification_engine)
    for _ in MEMBERS:
        await run_reconciliation_worker_once(
            lambda: PostgresKernelUnitOfWork(_certification_engine),
            NoTicketVenueTruth(),
            NoTicketPositionSource(),
            worker_request(retry_now_ms),
            instrument_certification_source=healthy_source,
        )

    async with _certification_engine.connect() as connection:
        batches = (
            await connection.execute(
                sa.text(
                    "SELECT certification_batch_id, status, blocker_code "
                    "FROM brc_instrument_certification_batches "
                    "ORDER BY certification_batch_id"
                )
            )
        ).all()

    assert batches == [
        (
            "certification-batch:blocked",
            "blocked",
            "configured_leverage_mismatch",
        ),
        ("certification-batch:retry", "completed", None),
    ]


@pytest.mark.asyncio
async def test_transient_read_leaves_batch_member_pending_for_lease_retry(
    _certification_engine: AsyncEngine,  # noqa: F811
) -> None:
    """Catches a timeout becoming an immutable terminal batch member result."""

    seed_identity = build_runtime_seed_identity(
        RuntimeAuthoritySeedRequest(
            account_id="subaccount-certification-test",
            runtime_commit=RUNTIME_COMMIT,
            schema_revision=SCHEMA_REVISION,
            seeded_at_ms=NOW_MS - 10_000,
        )
    )
    async with PostgresKernelUnitOfWork(_certification_engine) as uow:
        await start_certification_batch(
            uow,
            StartCertificationBatchRequest(
                certification_batch_id="certification-batch:transient",
                runtime_profile_id=RUNTIME_PROFILE_ID,
                target_commit=RUNTIME_COMMIT,
                target_schema_revision=SCHEMA_REVISION,
                target_seed_identity=seed_identity,
                owner_policy_id=OWNER_POLICY_ID,
                owner_policy_version=1,
                exchange_instrument_ids=MEMBERS,
                started_at_ms=NOW_MS,
                minimum_valid_until_ms=NOW_MS + 50_000,
            ),
        )
    await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(_certification_engine),
        NoTicketVenueTruth(),
        NoTicketPositionSource(),
        worker_request(NOW_MS),
        instrument_certification_source=RecordingReadonlyCertificationSource(
            _certification_engine,
            error=TimeoutError("readonly timeout"),
        ),
    )

    async with _certification_engine.connect() as connection:
        batch_status = await connection.scalar(
            sa.text(
                "SELECT status FROM brc_instrument_certification_batches "
                "WHERE certification_batch_id = 'certification-batch:transient'"
            )
        )
        member_statuses = (
            await connection.execute(
                sa.text(
                    "SELECT status FROM brc_instrument_certification_batch_members "
                    "WHERE certification_batch_id = 'certification-batch:transient' "
                    "ORDER BY exchange_instrument_id"
                )
            )
        ).scalars().all()

    assert batch_status == "pending"
    assert member_statuses == ["pending", "pending"]
