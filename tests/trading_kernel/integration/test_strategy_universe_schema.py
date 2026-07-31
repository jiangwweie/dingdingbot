from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
from pathlib import Path
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
DIGEST_C = f"sha256:{'c' * 64}"


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
            new_rejections: dict[str, bool] = {}
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
            new_rejections["instrument_identity_update"] = await _is_rejected_by(
                conn,
                asyncpg.CheckViolationError,
                """
                UPDATE brc_instruments
                SET venue_symbol = 'T00USD'
                WHERE exchange_instrument_id =
                    'binance-usdm:T00USDT:perpetual'
                """,
            )
            await conn.execute(
                """
                INSERT INTO brc_instruments (
                    exchange_instrument_id, venue_id, asset_class,
                    venue_symbol, contract_kind, status
                ) VALUES
                    (
                        'binance-usdm:ETHUSD:perpetual',
                        'binance-usdm', 'crypto', 'ETHUSD',
                        'perpetual', 'active'
                    ),
                    (
                        'kraken:ETHUSDT:perpetual',
                        'kraken', 'crypto', 'ETHUSDT',
                        'perpetual', 'active'
                    ),
                    (
                        'binance-usdm:AAPLUSDT:perpetual',
                        'binance-usdm', 'equity', 'AAPLUSDT',
                        'perpetual', 'active'
                    ),
                    (
                        'binance-usdm:SPOTUSDT:perpetual',
                        'binance-usdm', 'crypto', 'SPOTUSDT',
                        'spot', 'active'
                    )
                """
            )
            new_rejections["non_crypto_member"] = await _is_rejected_by(
                conn,
                asyncpg.CheckViolationError,
                """
                INSERT INTO brc_strategy_universe_members (
                    universe_version_id, exchange_instrument_id
                ) VALUES ('uni-a', 'binance-usdm:ETHUSD:perpetual')
                """,
            )
            new_rejections["wrong_venue_member"] = await _is_rejected_by(
                conn,
                asyncpg.CheckViolationError,
                """
                INSERT INTO brc_strategy_universe_members (
                    universe_version_id, exchange_instrument_id
                ) VALUES ('uni-a', 'kraken:ETHUSDT:perpetual')
                """,
            )
            new_rejections["wrong_asset_class_member"] = await _is_rejected_by(
                conn,
                asyncpg.CheckViolationError,
                """
                INSERT INTO brc_strategy_universe_members (
                    universe_version_id, exchange_instrument_id
                ) VALUES ('uni-a', 'binance-usdm:AAPLUSDT:perpetual')
                """,
            )
            new_rejections["wrong_contract_member"] = await _is_rejected_by(
                conn,
                asyncpg.CheckViolationError,
                """
                INSERT INTO brc_strategy_universe_members (
                    universe_version_id, exchange_instrument_id
                ) VALUES ('uni-a', 'binance-usdm:SPOTUSDT:perpetual')
                """,
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
            new_rejections["eleventh_member"] = await _is_rejected_by(
                conn,
                asyncpg.CheckViolationError,
                """
                INSERT INTO brc_strategy_universe_members (
                    universe_version_id, exchange_instrument_id
                ) VALUES ('uni-a', 'binance-usdm:T10USDT:perpetual')
                """,
            )
            await conn.execute(
                """
                INSERT INTO brc_strategy_universe_versions (
                    universe_version_id, strategy_group_id, event_spec_id,
                    universe_version, semantic_digest, lifecycle_state,
                    installed_at_ms, activated_at_ms, retired_at_ms
                ) VALUES (
                    'uni-update-source', 'sg-source', 'event-source',
                    1, $1, 'retired', 1000, 1001, 1002
                )
                """,
                DIGEST_C,
            )
            await conn.execute(
                """
                INSERT INTO brc_strategy_universe_members (
                    universe_version_id, exchange_instrument_id
                ) VALUES ('uni-update-source', 'binance-usdm:T10USDT:perpetual')
                """
            )
            new_rejections["member_update"] = await _is_rejected_by(
                conn,
                asyncpg.CheckViolationError,
                """
                UPDATE brc_strategy_universe_members
                SET universe_version_id = 'uni-a'
                WHERE universe_version_id = 'uni-update-source'
                  AND exchange_instrument_id =
                      'binance-usdm:T10USDT:perpetual'
                """,
            )

            new_rejections["warming_current"] = await _is_rejected_by(
                conn,
                asyncpg.ForeignKeyViolationError,
                """
                INSERT INTO brc_strategy_universe_current (
                    event_spec_id, universe_version_id, semantic_digest,
                    activation_generation, activated_at_ms
                ) VALUES ('event-a', 'uni-a', $1, 1, 1040)
                """,
                DIGEST_A,
            )
            new_rejections["retired_current"] = await _is_rejected_by(
                conn,
                asyncpg.ForeignKeyViolationError,
                """
                INSERT INTO brc_strategy_universe_current (
                    event_spec_id, universe_version_id, semantic_digest,
                    activation_generation, activated_at_ms
                ) VALUES (
                    'event-a', 'uni-retired-same-digest', $1, 1, 1040
                )
                """,
                DIGEST_A,
            )
            await conn.execute(
                """
                UPDATE brc_strategy_universe_versions
                SET lifecycle_state = 'active', activated_at_ms = 1050
                WHERE universe_version_id = 'uni-a'
                """
            )
            new_rejections["wrong_current_event"] = await _is_rejected_by(
                conn,
                asyncpg.ForeignKeyViolationError,
                """
                INSERT INTO brc_strategy_universe_current (
                    event_spec_id, universe_version_id, semantic_digest,
                    activation_generation, activated_at_ms
                ) VALUES ('event-wrong', 'uni-a', $1, 1, 1060)
                """,
                DIGEST_A,
            )
            new_rejections["wrong_current_digest"] = await _is_rejected_by(
                conn,
                asyncpg.ForeignKeyViolationError,
                """
                INSERT INTO brc_strategy_universe_current (
                    event_spec_id, universe_version_id, semantic_digest,
                    activation_generation, activated_at_ms
                ) VALUES ('event-other', 'uni-a', $1, 1, 1060)
                """,
                DIGEST_B,
            )
            new_rejections["wrong_signal_digest"] = await _is_rejected_by(
                conn,
                asyncpg.ForeignKeyViolationError,
                """
                INSERT INTO brc_signal_events (
                    signal_event_id, exposure_episode_id,
                    runtime_scope_id, runtime_scope_version,
                    strategy_group_id, strategy_version_id, event_spec_id,
                    universe_version_id, universe_semantic_digest,
                    exchange_instrument_id, position_side, fact_digest,
                    occurred_at_ms, observed_at_ms, expires_at_ms
                ) VALUES (
                    'signal-wrong-digest', 'episode-wrong-digest',
                    'scope-a', 1, 'sg-a', 'sv-a',
                    'event-a', 'uni-a', $1,
                    'binance-usdm:T00USDT:perpetual', 'long', $2,
                    1000, 1100, 2000
                )
                """,
                DIGEST_B,
                DIGEST_C,
            )
            assert new_rejections == {
                "eleventh_member": True,
                "instrument_identity_update": True,
                "member_update": True,
                "non_crypto_member": True,
                "retired_current": True,
                "warming_current": True,
                "wrong_asset_class_member": True,
                "wrong_contract_member": True,
                "wrong_current_digest": True,
                "wrong_current_event": True,
                "wrong_signal_digest": True,
                "wrong_venue_member": True,
            }
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
            lifecycle_rejections: dict[str, bool] = {}
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
            lifecycle_rejections["active_scope_on_warming"] = (
                await _is_rejected_by(
                    conn,
                    asyncpg.ForeignKeyViolationError,
                    """
                    INSERT INTO brc_runtime_scopes_current (
                        runtime_scope_id, strategy_group_id, strategy_version_id,
                        event_spec_id, runtime_profile_id, owner_policy_id,
                        exchange_instrument_id, position_side,
                        universe_version_id, universe_semantic_digest,
                        lifecycle_state, observation_enabled, entry_enabled,
                        scope_version, warm_closed_bar_time_ms, warm_completed_at_ms, warm_readiness_digest,
                        warm_valid_until_ms, updated_at_ms
                    ) VALUES (
                        'scope-active', 'sg-a', 'sv-a', 'event-a', 'profile-b',
                        'policy-a', 'binance-usdm:T00USDT:perpetual', 'long',
                        'uni-a', $1, 'active', true, true, 1, 1000, 1000, $2,
                        2000, 1000
                    )
                    """,
                    DIGEST_A,
                    DIGEST_A,
                )
            )
            lifecycle_rejections["retired_scope_on_warming"] = (
                await _is_rejected_by(
                    conn,
                    asyncpg.ForeignKeyViolationError,
                    """
                    INSERT INTO brc_runtime_scopes_current (
                        runtime_scope_id, strategy_group_id, strategy_version_id,
                        event_spec_id, runtime_profile_id, owner_policy_id,
                        exchange_instrument_id, position_side,
                        universe_version_id, universe_semantic_digest,
                        lifecycle_state, observation_enabled, entry_enabled,
                        scope_version, updated_at_ms
                    ) VALUES (
                        'scope-retired', 'sg-a', 'sv-a', 'event-a', 'profile-c',
                        'policy-a', 'binance-usdm:T00USDT:perpetual', 'long',
                        'uni-a', $1, 'retired', false, false, 1, 1000
                    )
                    """,
                    DIGEST_A,
                )
            )
            lifecycle_rejections["wrong_scope_digest"] = await _is_rejected_by(
                conn,
                asyncpg.ForeignKeyViolationError,
                """
                INSERT INTO brc_runtime_scopes_current (
                    runtime_scope_id, strategy_group_id, strategy_version_id,
                    event_spec_id, runtime_profile_id, owner_policy_id,
                    exchange_instrument_id, position_side, universe_version_id,
                    universe_semantic_digest, lifecycle_state,
                    observation_enabled, entry_enabled,
                    scope_version, updated_at_ms
                ) VALUES (
                    'scope-wrong-digest', 'sg-a', 'sv-a', 'event-a',
                    'profile-d', 'policy-a',
                    'binance-usdm:T00USDT:perpetual', 'long', 'uni-a',
                    $1, 'warming', true, false, 1, 1000
                )
                """,
                DIGEST_B,
            )
            assert lifecycle_rejections == {
                "active_scope_on_warming": True,
                "retired_scope_on_warming": True,
                "wrong_scope_digest": True,
            }
            await _assert_check_violation(
                conn,
                _scope_sql(),
                "scope-warming-entry",
                "warming",
                True,
                True,
                DIGEST_A,
            )
            await _assert_check_violation(
                conn,
                _scope_sql(),
                "scope-active-no-observation",
                "active",
                False,
                True,
                DIGEST_A,
            )
            await _assert_check_violation(
                conn,
                _scope_sql(),
                "scope-retired-observation",
                "retired",
                True,
                False,
                DIGEST_A,
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


@pytest.mark.asyncio
async def test_parallel_member_inserts_cannot_cross_ten_member_limit() -> None:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    first: asyncpg.Connection | None = None
    second: asyncpg.Connection | None = None
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        database_url = _database_url(database_name)
        _run_alembic(database_url, "upgrade", "head")
        asyncpg_url = database_url.replace("+asyncpg", "")
        first = await asyncpg.connect(asyncpg_url)
        second = await asyncpg.connect(asyncpg_url)
        await _seed_instruments(first, 11)
        await first.execute(
            """
            INSERT INTO brc_strategy_universe_versions (
                universe_version_id, strategy_group_id, event_spec_id,
                universe_version, semantic_digest, lifecycle_state,
                installed_at_ms, activated_at_ms
            ) VALUES ('uni-parallel', 'sg-a', 'event-a', 1, $1, 'active',
                      1000, 1001)
            """,
            DIGEST_A,
        )
        for index in range(9):
            await first.execute(
                """
                INSERT INTO brc_strategy_universe_members (
                    universe_version_id, exchange_instrument_id
                ) VALUES ('uni-parallel', $1)
                """,
                f"binance-usdm:T{index:02d}USDT:perpetual",
            )

        first_tx = first.transaction()
        await first_tx.start()
        await first.execute(
            """
            INSERT INTO brc_strategy_universe_members (
                universe_version_id, exchange_instrument_id
            ) VALUES ('uni-parallel', 'binance-usdm:T09USDT:perpetual')
            """
        )
        second_insert = asyncio.create_task(
            second.execute(
                """
                INSERT INTO brc_strategy_universe_members (
                    universe_version_id, exchange_instrument_id
                ) VALUES ('uni-parallel', 'binance-usdm:T10USDT:perpetual')
                """
            )
        )
        await asyncio.sleep(0.1)
        assert second_insert.done() is False
        await first_tx.commit()
        with pytest.raises(asyncpg.CheckViolationError):
            await second_insert
    finally:
        if second is not None:
            await second.close()
        if first is not None:
            await first.close()
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
        DIGEST_A,
    )


def _scope_sql() -> str:
    return """
        INSERT INTO brc_runtime_scopes_current (
            runtime_scope_id, strategy_group_id, strategy_version_id,
            event_spec_id, runtime_profile_id, owner_policy_id,
            exchange_instrument_id, position_side, universe_version_id,
            universe_semantic_digest, lifecycle_state,
            observation_enabled, entry_enabled,
            scope_version, updated_at_ms
        ) VALUES (
            $1, 'sg-a', 'sv-a', 'event-a', 'profile-a', 'policy-a',
            'binance-usdm:T00USDT:perpetual', 'long', 'uni-a',
            $5, $2, $3, $4, 1, 1000
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


async def _is_rejected_by(
    conn: asyncpg.Connection,
    exception_type: type[Exception],
    sql: str,
    *args: object,
) -> bool:
    transaction = conn.transaction()
    await transaction.start()
    try:
        await conn.execute(sql, *args)
        await conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
    except exception_type:
        return True
    finally:
        await transaction.rollback()
    return False


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
