from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_protection_failure_policy import (
    build_runtime_execution_protection_failure_policy,
)
from src.domain.runtime_execution_submit_idempotency import (
    RuntimeExecutionSubmitIdempotencySnapshot,
    RuntimeExecutionSubmitIdempotencyStatus,
)
from src.domain.runtime_execution_trusted_submit_facts import (
    RuntimeExecutionTrustedFactFreshness,
    RuntimeExecutionTrustedSubmitFactSource,
    RuntimeExecutionTrustedSubmitFactsStatus,
    build_runtime_execution_trusted_submit_facts_snapshot,
)
from src.infrastructure.pg_models import (
    PGRuntimeExecutionProtectionFailurePolicyORM,
    PGRuntimeExecutionSubmitIdempotencySnapshotORM,
    PGRuntimeExecutionTrustedSubmitFactsSnapshotORM,
)
from src.infrastructure.pg_runtime_execution_submit_prerequisite_repositories import (
    PgRuntimeExecutionProtectionFailurePolicyRepository,
    PgRuntimeExecutionSubmitIdempotencyRepository,
    PgRuntimeExecutionTrustedSubmitFactsRepository,
)
from tests.unit.test_runtime_execution_protection_failure_policy import (
    _ready_protection_plan,
)


NOW_MS = 1781100000000


def _semantic_ids() -> BrcSemanticIds:
    return BrcSemanticIds(
        runtime_instance_id="runtime-1",
        trial_binding_id="trial-1",
        strategy_family_id="CPM-001",
        strategy_family_version_id="CPM-001-v0",
        signal_evaluation_id="signal-eval-1",
        order_candidate_id="candidate-1",
    )


def _trusted_source(key: str) -> RuntimeExecutionTrustedSubmitFactSource:
    return RuntimeExecutionTrustedSubmitFactSource(
        key=key,
        source_id=f"{key}-source-1",
        source_type=f"trusted_{key}_readmodel",
        freshness=RuntimeExecutionTrustedFactFreshness.FRESH,
        observed_at_ms=NOW_MS - 100,
        max_age_ms=1_000,
    )


def _trusted_snapshot():
    return build_runtime_execution_trusted_submit_facts_snapshot(
        trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
        execution_intent_id="intent-1",
        runtime_instance_id="runtime-1",
        order_candidate_id="candidate-1",
        semantic_ids=_semantic_ids(),
        symbol="BNB/USDT:USDT",
        side="long",
        account_fact_source=_trusted_source("account_fact"),
        active_position_source=_trusted_source("active_position"),
        open_order_source=_trusted_source("open_order"),
        protection_state_source=_trusted_source("protection_state"),
        market_rule_source=_trusted_source("market_rule"),
        reconciliation_source=_trusted_source("reconciliation"),
        now_ms=NOW_MS,
    )


def _idempotency_snapshot():
    return RuntimeExecutionSubmitIdempotencySnapshot(
        submit_idempotency_policy_id="runtime-submit-idempotency-auth-1",
        authorization_id="auth-1",
        execution_intent_id="intent-1",
        runtime_execution_intent_draft_id="draft-1",
        runtime_instance_id="runtime-1",
        source_type="brc_runtime_order_candidate",
        source_id="candidate-1",
        semantic_ids=_semantic_ids(),
        symbol="BNB/USDT:USDT",
        side="long",
        status=(
            RuntimeExecutionSubmitIdempotencyStatus
            .READY_FOR_NON_EXECUTING_POLICY_CONFIRMATION
        ),
        stable_submit_key="runtime-submit:auth-1",
        replay_lock_key="auth-1",
        created_at_ms=NOW_MS,
    )


@pytest.mark.asyncio
async def test_pg_prerequisite_evidence_repositories_roundtrip():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(PGRuntimeExecutionTrustedSubmitFactsSnapshotORM.__table__.create)
        await conn.run_sync(PGRuntimeExecutionSubmitIdempotencySnapshotORM.__table__.create)
        await conn.run_sync(PGRuntimeExecutionProtectionFailurePolicyORM.__table__.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    trusted_repo = PgRuntimeExecutionTrustedSubmitFactsRepository(
        session_maker=session_maker
    )
    idempotency_repo = PgRuntimeExecutionSubmitIdempotencyRepository(
        session_maker=session_maker
    )
    protection_repo = PgRuntimeExecutionProtectionFailurePolicyRepository(
        session_maker=session_maker
    )
    trusted = _trusted_snapshot()
    idempotency = _idempotency_snapshot()
    protection = build_runtime_execution_protection_failure_policy(
        protection_plan=_ready_protection_plan(),
        now_ms=NOW_MS,
    )

    await trusted_repo.create(trusted)
    await idempotency_repo.create(idempotency)
    await protection_repo.create(protection)
    loaded_trusted = await trusted_repo.get(trusted.trusted_submit_fact_snapshot_id)
    loaded_idempotency = await idempotency_repo.get(
        idempotency.submit_idempotency_policy_id
    )
    loaded_protection = await protection_repo.get(protection.policy_id)

    await engine.dispose()

    assert loaded_trusted == trusted
    assert loaded_idempotency == idempotency
    assert loaded_protection == protection
    assert loaded_trusted.status == (
        RuntimeExecutionTrustedSubmitFactsStatus
        .READY_FOR_FIRST_REAL_SUBMIT_CONFIRMATION
    )
    assert loaded_idempotency.exchange_called is False
    assert loaded_protection.exchange_order_submitted is False


def test_prerequisite_evidence_migration_creates_tables():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-11-072_create_runtime_submit_prerequisite_evidence.py"
    )
    spec = importlib.util.spec_from_file_location(
        "runtime_submit_prerequisite_evidence_migration",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_engine("sqlite:///:memory:")
    connection = engine.connect()
    context = MigrationContext.configure(connection)
    op = Operations(context)
    migration.op = op

    try:
        migration.upgrade()
        inspector = inspect(connection)

        assert "runtime_execution_trusted_submit_fact_snapshots" in (
            inspector.get_table_names()
        )
        assert "runtime_execution_submit_idempotency_snapshots" in (
            inspector.get_table_names()
        )
        assert "runtime_execution_protection_failure_policies" in (
            inspector.get_table_names()
        )
    finally:
        connection.close()
        engine.dispose()
