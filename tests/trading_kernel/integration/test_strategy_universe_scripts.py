from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
from collections.abc import AsyncGenerator
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from scripts.trading_kernel.certify_readonly import _certify
from src.trading_kernel.infrastructure.pg_models import (
    instrument_certification_current,
    monitor_current,
    runtime_scopes_current,
    strategy_universe_current,
    strategy_universe_versions,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RUNTIME_PROFILE_ID,
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import (
    CURRENT_SCHEMA_REVISION,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIGURE_SCRIPT = REPO_ROOT / "scripts/trading_kernel/configure_strategy_universe.py"
STATUS_SCRIPT = REPO_ROOT / "scripts/trading_kernel/read_strategy_universe_status.py"
ADMIN_DSN = os.getenv(
    "BRC_TEST_POSTGRES_ADMIN_URL",
    "postgresql://dingdingbot:dingdingbot_dev@127.0.0.1:5432/postgres",
)
SAFE_DATABASE = re.compile(r"^brc_kernel_test_[a-f0-9]{12}$")
CANONICAL_EVENT_SPEC_ID = "event_spec:SOR-001:SOR-LONG:v4"
NOW_MS = 1_800_001_000_000


@pytest_asyncio.fixture
async def script_database_url() -> AsyncGenerator[str, None]:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    await admin.execute(f'CREATE DATABASE "{database_name}"')
    database_url = _database_url(database_name)
    engine: AsyncEngine | None = None
    try:
        _run_alembic(database_url, "upgrade", "head")
        engine = create_async_engine(database_url)
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id="sensitive-account-id",
                    runtime_commit="task-12-local-test",
                    schema_revision=CURRENT_SCHEMA_REVISION,
                    seeded_at_ms=NOW_MS - 1_000,
                ),
            )
        yield database_url
    finally:
        if engine is not None:
            await engine.dispose()
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            database_name,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await admin.close()


@pytest.mark.asyncio
async def test_configure_cli_installs_only_one_warming_universe(
    script_database_url: str,
    tmp_path: Path,
) -> None:
    """Catches direct activation, file output, or bypass of the install use case."""

    completed = _run_configure(
        script_database_url,
        tmp_path,
        event_id="SOR-LONG",
        runtime_profile_id=RUNTIME_PROFILE_ID,
        instruments=("SOLUSDT", "BTCUSDT"),
    )

    assert completed.returncode == 0, completed.stderr
    lines = completed.stdout.splitlines()
    assert lines[0] == "status=installed"
    assert lines[1] == f"event_spec_id={CANONICAL_EVENT_SPEC_ID}"
    assert re.fullmatch(r"universe_version_id=universe:[0-9a-f]{24}:v1", lines[2])
    assert re.fullmatch(r"semantic_digest=sha256:[0-9a-f]{64}", lines[3])
    assert lines[4:] == ["lifecycle_state=warming", "member_count=2"]
    assert completed.stderr == ""
    assert tuple(tmp_path.iterdir()) == ()

    engine = create_async_engine(script_database_url)
    try:
        async with engine.connect() as connection:
            version = (
                await connection.execute(
                    sa.select(
                        strategy_universe_versions.c.lifecycle_state,
                        strategy_universe_versions.c.event_spec_id,
                    )
                )
            ).one()
            current_count = int(
                (
                    await connection.execute(
                        sa.select(sa.func.count()).select_from(
                            strategy_universe_current
                        )
                    )
                ).scalar_one()
            )
            scope_rows = tuple(
                (
                    await connection.execute(
                        sa.select(
                            runtime_scopes_current.c.exchange_instrument_id,
                            runtime_scopes_current.c.lifecycle_state,
                            runtime_scopes_current.c.observation_enabled,
                            runtime_scopes_current.c.entry_enabled,
                        ).order_by(runtime_scopes_current.c.exchange_instrument_id)
                    )
                ).all()
            )
            downstream_counts = tuple(
                int(value)
                for value in (
                    await connection.execute(
                        sa.text(
                            "SELECT "
                            "(SELECT count(*) FROM brc_signal_events), "
                            "(SELECT count(*) FROM brc_capacity_claims), "
                            "(SELECT count(*) FROM brc_trade_tickets), "
                            "(SELECT count(*) FROM brc_exchange_commands)"
                        )
                    )
                ).one()
            )
    finally:
        await engine.dispose()

    assert version == ("warming", CANONICAL_EVENT_SPEC_ID)
    assert current_count == 0
    assert scope_rows == (
        ("binance-usdm:BTCUSDT:perpetual", "warming", True, False),
        ("binance-usdm:SOLUSDT:perpetual", "warming", True, False),
    )
    assert downstream_counts == (0, 0, 0, 0)


@pytest.mark.asyncio
async def test_readonly_certification_accepts_only_structurally_consistent_universe(
    script_database_url: str,
    tmp_path: Path,
) -> None:
    """Catches treating every configured Scope as a certification failure."""

    configured = _run_configure(
        script_database_url,
        tmp_path,
        event_id="SOR-LONG",
        runtime_profile_id=RUNTIME_PROFILE_ID,
        instruments=("SOLUSDT", "BTCUSDT"),
    )
    assert configured.returncode == 0, configured.stderr

    coherent = await _certify(script_database_url, require_flat=True)

    engine = create_async_engine(script_database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                sa.delete(runtime_scopes_current).where(
                    runtime_scopes_current.c.exchange_instrument_id
                    == "binance-usdm:SOLUSDT:perpetual"
                )
            )
        inconsistent = await _certify(script_database_url, require_flat=True)
    finally:
        await engine.dispose()

    assert coherent["status"] == "pass"
    coherent_universe = coherent["strategy_universe"]
    assert isinstance(coherent_universe, dict)
    assert {
        key: coherent_universe[key]
        for key in (
            "version_count",
            "current_count",
            "member_count",
            "scope_count",
            "integrity_violation_count",
            "scope_lifecycle_counts",
            "temporarily_unavailable_certification_count",
            "shadow_pending_count",
            "active_current_count",
            "warming_count",
        )
    } == {
        "version_count": 1,
        "current_count": 0,
        "member_count": 2,
        "scope_count": 2,
        "integrity_violation_count": 0,
        "scope_lifecycle_counts": {
            "active": 0,
            "warming": 2,
            "retired": 0,
        },
        "temporarily_unavailable_certification_count": 0,
        "shadow_pending_count": 0,
        "active_current_count": 0,
        "warming_count": 1,
    }
    assert coherent_universe["identity_status"] == "fail"
    assert coherent_universe["deployment_stage"] == "invalid"
    assert coherent_universe["active_manifest"] == []
    assert len(coherent_universe["warming_manifest"]) == 1
    assert inconsistent["status"] == "fail"
    inconsistent_universe = inconsistent["strategy_universe"]
    assert isinstance(inconsistent_universe, dict)
    assert inconsistent_universe["integrity_violation_count"] == 1


@pytest.mark.asyncio
async def test_configure_cli_rejects_unknown_event_and_profile_without_rows(
    script_database_url: str,
    tmp_path: Path,
) -> None:
    """Catches guessed Event/Profile identities or partially persisted installs."""

    unknown_event = _run_configure(
        script_database_url,
        tmp_path,
        event_id="UNKNOWN-LONG",
        runtime_profile_id=RUNTIME_PROFILE_ID,
        instruments=("BTCUSDT",),
    )
    unknown_profile = _run_configure(
        script_database_url,
        tmp_path,
        event_id="SOR-LONG",
        runtime_profile_id="unknown-profile",
        instruments=("BTCUSDT",),
    )

    assert unknown_event.returncode == 2
    assert unknown_event.stdout == ""
    assert unknown_event.stderr == "error=EVENT_AUTHORITY_CONFLICT\n"
    assert unknown_profile.returncode == 2
    assert unknown_profile.stdout == ""
    assert unknown_profile.stderr == "error=RUNTIME_PROFILE_AUTHORITY_CONFLICT\n"
    assert tuple(tmp_path.iterdir()) == ()

    engine = create_async_engine(script_database_url)
    try:
        async with engine.connect() as connection:
            version_count = int(
                (
                    await connection.execute(
                        sa.select(sa.func.count()).select_from(
                            strategy_universe_versions
                        )
                    )
                ).scalar_one()
            )
    finally:
        await engine.dispose()
    assert version_count == 0


@pytest.mark.asyncio
async def test_read_status_is_readonly_bounded_and_redacts_sensitive_state(
    script_database_url: str,
    tmp_path: Path,
) -> None:
    """Catches account/credential/payload leakage or status-side state mutation."""

    configured = _run_configure(
        script_database_url,
        tmp_path,
        event_id="SOR-LONG",
        runtime_profile_id=RUNTIME_PROFILE_ID,
        instruments=("BTCUSDT", "SOLUSDT"),
    )
    assert configured.returncode == 0, configured.stderr

    engine = create_async_engine(script_database_url)
    try:
        async with engine.begin() as connection:
            version_id = str(
                (
                    await connection.execute(
                        sa.select(strategy_universe_versions.c.universe_version_id)
                    )
                ).scalar_one()
            )
            await connection.execute(
                sa.insert(instrument_certification_current).values(
                    runtime_profile_id=RUNTIME_PROFILE_ID,
                    exchange_instrument_id=("binance-usdm:BTCUSDT:perpetual"),
                    status="owner_action_required",
                    blocker_code="configured_leverage_mismatch",
                    facts_digest="sha256:" + ("b" * 64),
                    product_rules_digest=None,
                    configured_leverage=3,
                    margin_mode="cross",
                    position_mode="independent_sides",
                    observed_at_ms=NOW_MS,
                    valid_until_ms=NOW_MS + 300_000,
                    next_check_at_ms=NOW_MS + 300_000,
                    lease_owner=None,
                    lease_expires_at_ms=None,
                    projection_version=1,
                )
            )
            await connection.execute(
                sa.update(runtime_scopes_current)
                .where(
                    runtime_scopes_current.c.exchange_instrument_id
                    == "binance-usdm:SOLUSDT:perpetual"
                )
                .values(
                    warm_closed_bar_time_ms=NOW_MS,
                    warm_completed_at_ms=NOW_MS,
                    warm_readiness_digest="sha256:" + ("c" * 64),
                    warm_valid_until_ms=NOW_MS + 300_000,
                )
            )
            await connection.execute(
                sa.insert(monitor_current).values(
                    monitor_key=(
                        f"strategy-universe:{version_id}:binance-usdm:BTCUSDT:perpetual"
                    ),
                    owner_status="needs_intervention",
                    summary=(
                        "api_key=SECRET venue_payload={full:true} "
                        "account=sensitive-account-id"
                    ),
                    intervention="credential=SECRET",
                    ticket_id=None,
                    incident_id=None,
                    updated_at_ms=NOW_MS,
                    projection_version=1,
                )
            )
            before_counts = await _mutable_counts(connection)

        completed = await asyncio.to_thread(
            subprocess.run,
            [
                sys.executable,
                str(STATUS_SCRIPT),
                "--database-url",
                script_database_url,
                "--runtime-profile-id",
                RUNTIME_PROFILE_ID,
                "--event-spec-id",
                "SOR-LONG",
            ],
            cwd=tmp_path,
            check=False,
            capture_output=True,
            text=True,
        )

        async with engine.connect() as connection:
            after_counts = await _mutable_counts(connection)
    finally:
        await engine.dispose()

    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    assert completed.stdout.splitlines() == [
        f"runtime_profile_id={RUNTIME_PROFILE_ID}",
        "universe_count=1",
        (
            "universe event_id=SOR-LONG "
            f"event_spec_id={CANONICAL_EVENT_SPEC_ID} "
            f"version_id={version_id} lifecycle=warming "
            "current_generation=none"
        ),
        (
            "member instrument=binance-usdm:BTCUSDT:perpetual "
            "certification=owner_action_required warm=not_ready "
            "monitor=needs_intervention "
            "blocker=configured_leverage_mismatch"
        ),
        (
            "member instrument=binance-usdm:SOLUSDT:perpetual "
            "certification=missing warm=ready monitor=none blocker=none"
        ),
    ]
    assert "SECRET" not in completed.stdout
    assert "sensitive-account-id" not in completed.stdout
    assert "venue_payload" not in completed.stdout
    assert "postgresql" not in completed.stdout
    assert before_counts == after_counts
    assert tuple(tmp_path.iterdir()) == ()

    engine = create_async_engine(script_database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                sa.update(instrument_certification_current)
                .where(
                    instrument_certification_current.c.exchange_instrument_id
                    == "binance-usdm:BTCUSDT:perpetual"
                )
                .values(blocker_code="credential=SECRET")
            )
        corrupt_blocker = await asyncio.to_thread(
            subprocess.run,
            [
                sys.executable,
                str(STATUS_SCRIPT),
                "--database-url",
                script_database_url,
                "--runtime-profile-id",
                RUNTIME_PROFILE_ID,
                "--event-spec-id",
                "SOR-LONG",
            ],
            cwd=tmp_path,
            check=False,
            capture_output=True,
            text=True,
        )
        async with engine.begin() as connection:
            await connection.execute(
                sa.update(instrument_certification_current)
                .where(
                    instrument_certification_current.c.exchange_instrument_id
                    == "binance-usdm:BTCUSDT:perpetual"
                )
                .values(blocker_code="configured_leverage_mismatch")
            )
    finally:
        await engine.dispose()
    assert corrupt_blocker.returncode == 1
    assert corrupt_blocker.stdout == ""
    assert corrupt_blocker.stderr == "error=operation_failed\n"
    assert "SECRET" not in corrupt_blocker.stderr

    engine = create_async_engine(script_database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                sa.update(monitor_current).values(owner_status="credential=SECRET")
            )
        corrupt_status = await asyncio.to_thread(
            subprocess.run,
            [
                sys.executable,
                str(STATUS_SCRIPT),
                "--database-url",
                script_database_url,
                "--runtime-profile-id",
                RUNTIME_PROFILE_ID,
                "--event-spec-id",
                "SOR-LONG",
            ],
            cwd=tmp_path,
            check=False,
            capture_output=True,
            text=True,
        )
    finally:
        await engine.dispose()
    assert corrupt_status.returncode == 1
    assert corrupt_status.stdout == ""
    assert corrupt_status.stderr == "error=operation_failed\n"
    assert "SECRET" not in corrupt_status.stderr


@pytest.mark.asyncio
async def test_read_status_displays_active_current_generation(
    script_database_url: str,
    tmp_path: Path,
) -> None:
    """Catches an active status that omits or guesses the current CAS generation."""

    configured = _run_configure(
        script_database_url,
        tmp_path,
        event_id="SOR-LONG",
        runtime_profile_id=RUNTIME_PROFILE_ID,
        instruments=("BTCUSDT",),
    )
    assert configured.returncode == 0, configured.stderr

    engine = create_async_engine(script_database_url)
    try:
        async with engine.begin() as connection:
            version = (
                (await connection.execute(sa.select(strategy_universe_versions)))
                .mappings()
                .one()
            )
            await connection.execute(
                sa.update(runtime_scopes_current).values(
                    lifecycle_state="active",
                    observation_enabled=True,
                    entry_enabled=True,
                    scope_version=2,
                    warm_closed_bar_time_ms=NOW_MS,
                    warm_completed_at_ms=NOW_MS,
                    warm_readiness_digest="sha256:" + ("c" * 64),
                    warm_valid_until_ms=NOW_MS + 300_000,
                    updated_at_ms=NOW_MS + 1,
                )
            )
            await connection.execute(
                sa.update(strategy_universe_versions).values(
                    lifecycle_state="active",
                    activated_at_ms=NOW_MS + 1,
                )
            )
            await connection.execute(
                sa.insert(strategy_universe_current).values(
                    event_spec_id=CANONICAL_EVENT_SPEC_ID,
                    universe_version_id=version["universe_version_id"],
                    semantic_digest=version["semantic_digest"],
                    lifecycle_state="active",
                    activation_generation=7,
                    activated_at_ms=NOW_MS + 1,
                )
            )

        completed = await asyncio.to_thread(
            subprocess.run,
            [
                sys.executable,
                str(STATUS_SCRIPT),
                "--database-url",
                script_database_url,
                "--runtime-profile-id",
                RUNTIME_PROFILE_ID,
            ],
            cwd=tmp_path,
            check=False,
            capture_output=True,
            text=True,
        )
    finally:
        await engine.dispose()

    assert completed.returncode == 0, completed.stderr
    assert "lifecycle=active current_generation=7" in completed.stdout
    assert "member instrument=binance-usdm:BTCUSDT:perpetual" in completed.stdout
    assert tuple(tmp_path.iterdir()) == ()


async def _mutable_counts(
    connection: sa.ext.asyncio.AsyncConnection,
) -> tuple[int, ...]:
    return tuple(
        int(value)
        for value in (
            await connection.execute(
                sa.text(
                    "SELECT "
                    "(SELECT count(*) FROM brc_strategy_universe_versions), "
                    "(SELECT count(*) FROM brc_strategy_universe_members), "
                    "(SELECT count(*) FROM brc_runtime_scopes_current), "
                    "(SELECT count(*) FROM brc_instrument_certification_current), "
                    "(SELECT count(*) FROM brc_monitor_current), "
                    "(SELECT count(*) FROM brc_monitor_events)"
                )
            )
        ).one()
    )


def _run_configure(
    database_url: str,
    cwd: Path,
    *,
    event_id: str,
    runtime_profile_id: str,
    instruments: tuple[str, ...],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(CONFIGURE_SCRIPT),
            "--database-url",
            database_url,
            "--runtime-profile-id",
            runtime_profile_id,
            "--event-spec-id",
            event_id,
            "--installed-at-ms",
            str(NOW_MS),
            *(
                argument
                for instrument in instruments
                for argument in ("--instrument", instrument)
            ),
        ],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def _database_url(database_name: str) -> str:
    base = ADMIN_DSN.rsplit("/", 1)[0]
    return (
        f"{base.replace('postgresql://', 'postgresql+asyncpg://', 1)}/{database_name}"
    )


def _run_alembic(database_url: str, *args: str) -> None:
    env = {**os.environ, "TRADING_KERNEL_DATABASE_URL": database_url}
    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "migrations/trading_kernel/alembic.ini",
            *args,
        ],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
