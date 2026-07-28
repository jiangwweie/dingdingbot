from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4

import asyncpg
import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_DSN = os.getenv(
    "BRC_TEST_POSTGRES_ADMIN_URL",
    "postgresql://dingdingbot:dingdingbot_dev@127.0.0.1:5432/postgres",
)
SAFE_DATABASE = re.compile(r"^brc_kernel_test_[a-f0-9]{12}$")
DIGEST_A = f"sha256:{'a' * 64}"
DIGEST_B = f"sha256:{'b' * 64}"


@pytest.mark.asyncio
async def test_postgres_enforces_strategy_universe_authority_constraints() -> None:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        database_url = _database_url(database_name)
        _run_alembic(database_url, "upgrade", "head")
        conn = await asyncpg.connect(database_url.replace("+asyncpg", ""))
        try:
            await _seed_instruments(conn, 12)
            await conn.execute(
                """
                INSERT INTO brc_strategy_universe_versions (
                    universe_version_id,
                    strategy_group_id,
                    event_spec_id,
                    universe_version,
                    semantic_digest,
                    lifecycle_state,
                    installed_at_ms
                ) VALUES ('uni-a', 'sg-a', 'event-a', 1, $1, 'warming', 1000)
                """,
                DIGEST_A,
            )

            await _assert_unique_violation(
                conn,
                """
                INSERT INTO brc_strategy_universe_versions (
                    universe_version_id, strategy_group_id, event_spec_id,
                    universe_version, semantic_digest, lifecycle_state,
                    installed_at_ms, activated_at_ms, retired_at_ms
                ) VALUES (
                    'uni-event-version-duplicate', 'sg-a', 'event-a',
                    1, $1, 'retired', 1001, 1002, 1003
                )
                """,
                DIGEST_B,
            )
            await _assert_unique_violation(
                conn,
                """
                INSERT INTO brc_strategy_universe_versions (
                    universe_version_id, strategy_group_id, event_spec_id,
                    universe_version, semantic_digest, lifecycle_state,
                    installed_at_ms, activated_at_ms
                ) VALUES (
                    'uni-current-digest-duplicate', 'sg-a', 'event-a',
                    2, $1, 'active', 1002, 1003
                )
                """,
                DIGEST_A,
            )
            await _assert_unique_violation(
                conn,
                """
                INSERT INTO brc_strategy_universe_versions (
                    universe_version_id, strategy_group_id, event_spec_id,
                    universe_version, semantic_digest, lifecycle_state,
                    installed_at_ms
                ) VALUES (
                    'uni-second-warming', 'sg-b', 'event-b',
                    1, $1, 'warming', 1003
                )
                """,
                DIGEST_B,
            )

            await conn.execute(
                """
                INSERT INTO brc_strategy_universe_versions (
                    universe_version_id, strategy_group_id, event_spec_id,
                    universe_version, semantic_digest, lifecycle_state,
                    installed_at_ms, activated_at_ms, retired_at_ms
                ) VALUES (
                    'uni-retired-same-digest', 'sg-a', 'event-a',
                    2, $1, 'retired', 1004, 1005, 1006
                )
                """,
                DIGEST_A,
            )

            await conn.execute(
                """
                INSERT INTO brc_strategy_universe_members (
                    universe_version_id, exchange_instrument_id
                ) VALUES ('uni-a', 'binance-usdm:T00USDT:perpetual')
                """
            )
            await _assert_unique_violation(
                conn,
                """
                INSERT INTO brc_strategy_universe_members (
                    universe_version_id, exchange_instrument_id
                ) VALUES ('uni-a', 'binance-usdm:T00USDT:perpetual')
                """,
            )
            await _assert_foreign_key_violation(
                conn,
                """
                INSERT INTO brc_strategy_universe_members (
                    universe_version_id, exchange_instrument_id
                ) VALUES ('uni-a', 'binance-usdm:MISSINGUSDT:perpetual')
                """,
            )
            for index in range(1, 10):
                await conn.execute(
                    """
                    INSERT INTO brc_strategy_universe_members (
                        universe_version_id, exchange_instrument_id
                    ) VALUES ('uni-a', $1)
                    """,
                    f"binance-usdm:T{index:02d}USDT:perpetual",
                )
            await _assert_check_violation(
                conn,
                """
                INSERT INTO brc_strategy_universe_members (
                    universe_version_id, exchange_instrument_id
                ) VALUES ('uni-a', 'binance-usdm:T10USDT:perpetual')
                """,
            )

            await conn.execute(
                """
                UPDATE brc_strategy_universe_versions
                SET lifecycle_state = 'active', activated_at_ms = 1050
                WHERE universe_version_id = 'uni-a'
                """
            )
            await conn.execute(
                """
                INSERT INTO brc_strategy_universe_current (
                    event_spec_id, universe_version_id, semantic_digest,
                    activation_generation, activated_at_ms
                ) VALUES ('event-a', 'uni-a', $1, 1, 1100)
                """,
                DIGEST_A,
            )
            await _assert_unique_violation(
                conn,
                """
                INSERT INTO brc_strategy_universe_current (
                    event_spec_id, universe_version_id, semantic_digest,
                    activation_generation, activated_at_ms
                ) VALUES ('event-a', 'uni-retired-same-digest', $1, 2, 1200)
                """,
                DIGEST_A,
            )
        finally:
            await conn.close()
    finally:
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            database_name,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await admin.close()


@pytest.mark.asyncio
async def test_postgres_enforces_runtime_scope_permissions_and_lineage() -> None:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        database_url = _database_url(database_name)
        _run_alembic(database_url, "upgrade", "head")
        conn = await asyncpg.connect(database_url.replace("+asyncpg", ""))
        try:
            await _seed_instruments(conn, 1)
            await conn.execute(
                """
                INSERT INTO brc_strategy_universe_versions (
                    universe_version_id, strategy_group_id, event_spec_id,
                    universe_version, semantic_digest, lifecycle_state,
                    installed_at_ms
                ) VALUES ('uni-a', 'sg-a', 'event-a', 1, $1, 'warming', 1000)
                """,
                DIGEST_A,
            )
            await conn.execute(
                """
                INSERT INTO brc_strategy_universe_members (
                    universe_version_id, exchange_instrument_id
                ) VALUES ('uni-a', 'binance-usdm:T00USDT:perpetual')
                """
            )
            await _insert_scope(
                conn,
                scope_id="scope-warming",
                lifecycle_state="warming",
                observation_enabled=True,
                entry_enabled=False,
            )
            await conn.execute(
                """
                INSERT INTO brc_runtime_scopes_current (
                    runtime_scope_id, strategy_group_id, strategy_version_id,
                    event_spec_id, runtime_profile_id, owner_policy_id,
                    exchange_instrument_id, position_side, universe_version_id,
                    lifecycle_state, observation_enabled, entry_enabled,
                    scope_version, warm_ready_at_ms, warm_readiness_digest,
                    warm_valid_until_ms, updated_at_ms
                ) VALUES (
                    'scope-active', 'sg-a', 'sv-a', 'event-a', 'profile-b',
                    'policy-a', 'binance-usdm:T00USDT:perpetual', 'long',
                    'uni-a', 'active', true, true, 1, 1000, $1, 2000, 1000
                )
                """,
                DIGEST_A,
            )
            await conn.execute(
                """
                INSERT INTO brc_runtime_scopes_current (
                    runtime_scope_id, strategy_group_id, strategy_version_id,
                    event_spec_id, runtime_profile_id, owner_policy_id,
                    exchange_instrument_id, position_side, universe_version_id,
                    lifecycle_state, observation_enabled, entry_enabled,
                    scope_version, updated_at_ms
                ) VALUES (
                    'scope-retired', 'sg-a', 'sv-a', 'event-a', 'profile-c',
                    'policy-a', 'binance-usdm:T00USDT:perpetual', 'long',
                    'uni-a', 'retired', false, false, 1, 1000
                )
                """
            )
            await _assert_check_violation(
                conn,
                _scope_sql(),
                "scope-warming-entry",
                "warming",
                True,
                True,
            )
            await _assert_check_violation(
                conn,
                _scope_sql(),
                "scope-active-no-observation",
                "active",
                False,
                True,
            )
            await _assert_check_violation(
                conn,
                _scope_sql(),
                "scope-retired-observation",
                "retired",
                True,
                False,
            )

            for table_name, required_columns in {
                "brc_signal_events": {
                    "universe_version_id",
                    "universe_semantic_digest",
                },
                "brc_capacity_claims": {
                    "universe_version_id",
                    "universe_semantic_digest",
                },
                "brc_trade_tickets": {
                    "universe_version_id",
                    "universe_semantic_digest",
                },
            }.items():
                nullable = await conn.fetch(
                    """
                    SELECT column_name, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = $1
                      AND column_name = ANY($2::text[])
                    """,
                    table_name,
                    list(required_columns),
                )
                assert {
                    str(row["column_name"])
                    for row in nullable
                    if row["is_nullable"] == "NO"
                } == required_columns
        finally:
            await conn.close()
    finally:
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            database_name,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await admin.close()


async def _seed_instruments(conn: asyncpg.Connection, count: int) -> None:
    for index in range(count):
        await conn.execute(
            """
            INSERT INTO brc_instruments (
                exchange_instrument_id, venue_id, asset_class,
                venue_symbol, contract_kind, status
            ) VALUES ($1, 'binance-usdm', 'crypto', $2, 'perpetual', $3)
            """,
            f"binance-usdm:T{index:02d}USDT:perpetual",
            f"T{index:02d}USDT",
            "pending_certification" if index == 0 else "active",
        )


async def _insert_scope(
    conn: asyncpg.Connection,
    *,
    scope_id: str,
    lifecycle_state: str,
    observation_enabled: bool,
    entry_enabled: bool,
) -> None:
    await conn.execute(
        _scope_sql(),
        scope_id,
        lifecycle_state,
        observation_enabled,
        entry_enabled,
    )


def _scope_sql() -> str:
    return """
        INSERT INTO brc_runtime_scopes_current (
            runtime_scope_id, strategy_group_id, strategy_version_id,
            event_spec_id, runtime_profile_id, owner_policy_id,
            exchange_instrument_id, position_side, universe_version_id,
            lifecycle_state, observation_enabled, entry_enabled,
            scope_version, updated_at_ms
        ) VALUES (
            $1, 'sg-a', 'sv-a', 'event-a', 'profile-a', 'policy-a',
            'binance-usdm:T00USDT:perpetual', 'long', 'uni-a',
            $2, $3, $4, 1, 1000
        )
    """


async def _assert_unique_violation(
    conn: asyncpg.Connection,
    sql: str,
    *args: object,
) -> None:
    async with conn.transaction():
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(sql, *args)


async def _assert_foreign_key_violation(
    conn: asyncpg.Connection,
    sql: str,
    *args: object,
) -> None:
    async with conn.transaction():
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await conn.execute(sql, *args)


async def _assert_check_violation(
    conn: asyncpg.Connection,
    sql: str,
    *args: object,
) -> None:
    async with conn.transaction():
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(sql, *args)


def _database_url(database_name: str) -> str:
    if SAFE_DATABASE.fullmatch(database_name) is None:
        raise ValueError("unsafe kernel test database name")
    base = ADMIN_DSN.rsplit("/", 1)[0]
    return f"{base.replace('postgresql://', 'postgresql+asyncpg://', 1)}/{database_name}"


def _run_alembic(database_url: str, *args: str) -> None:
    env = {**os.environ, "TRADING_KERNEL_DATABASE_URL": database_url}
    result = subprocess.run(
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
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-4000:]
