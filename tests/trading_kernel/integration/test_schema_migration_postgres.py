from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from tests.trading_kernel.integration.test_schema_baseline import EXPECTED_TABLES

REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_DSN = os.getenv(
    "BRC_TEST_POSTGRES_ADMIN_URL",
    "postgresql://dingdingbot:dingdingbot_dev@127.0.0.1:5432/postgres",
)
SAFE_DATABASE = re.compile(r"^brc_kernel_test_[a-f0-9]{12}$")


@pytest.mark.asyncio
async def test_clean_alembic_baseline_upgrades_forward_only_postgres() -> None:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        database_url = _database_url(database_name)
        _run_alembic(database_url, "upgrade", "0001")
        _run_alembic(database_url, "upgrade", "head")

        engine = create_async_engine(database_url)
        try:
            async with engine.connect() as conn:
                tables, constraints = await conn.run_sync(_inspect_schema)
            assert tables == EXPECTED_TABLES | {"alembic_version"}
            assert constraints == {
                "ticket_uniques": {
                    "uq_brc_trade_tickets_active_netting_domain_key",
                    "uq_brc_trade_tickets_signal_event_id",
                },
                "command_uniques": {
                    "uq_brc_exchange_commands_idempotency_key",
                    "uq_brc_exchange_commands_ticket_kind_generation",
                    "uq_brc_exchange_commands_venue_client_order_id",
                },
                "command_checks": {
                    "ck_brc_exchange_commands_command_order_identity_shape",
                    "ck_brc_exchange_commands_generation_positive",
                    "ck_brc_exchange_commands_quantity_positive",
                },
                "event_uniques": {"uq_brc_trade_events_ticket_id_sequence"},
                "ticket_checks": {
                    "ck_brc_trade_tickets_selected_leverage_positive",
                    "ck_brc_trade_tickets_notional_positive",
                    "ck_brc_trade_tickets_quantity_positive",
                    "ck_brc_trade_tickets_risk_nonnegative",
                    "ck_brc_trade_tickets_universe_digest_valid",
                },
                "aggregate_checks": {
                    "ck_brc_trade_aggregates_position_nonnegative",
                    "ck_brc_trade_aggregates_protection_nonnegative",
                    "ck_brc_trade_aggregates_sequence_positive",
                    "ck_brc_trade_aggregates_tp1_filled_nonnegative",
                    "ck_brc_trade_aggregates_tp1_target_nonnegative",
                    "ck_brc_trade_aggregates_version_positive",
                },
                "universe_indexes": {
                    "uq_brc_strategy_universe_versions_current_digest",
                    "uq_brc_strategy_universe_versions_event_version",
                    "uq_brc_strategy_universe_versions_global_warming",
                    "uq_brc_universe_versions_identity_digest",
                    "uq_brc_universe_versions_identity_lifecycle",
                },
                "scope_indexes": {
                    "ix_brc_runtime_scopes_current_observation_due",
                    "uq_brc_runtime_scopes_current_universe_identity",
                },
                "certification_indexes": {
                    "ix_brc_instrument_certification_current_due",
                },
                "member_foreign_keys": {
                    "fk_brc_universe_members_instrument",
                    "fk_brc_universe_members_universe_version",
                },
                "current_foreign_keys": {
                    "fk_brc_universe_current_active_identity",
                },
                "scope_foreign_keys": {
                    "fk_brc_runtime_scope_universe_lifecycle",
                    "fk_brc_runtime_scope_universe_member",
                },
                "signal_foreign_keys": {
                    "fk_brc_signal_events_universe_identity",
                },
                "claim_foreign_keys": {
                    "fk_brc_capacity_claims_universe_identity",
                },
                "ticket_foreign_keys": {
                    "fk_brc_trade_tickets_universe_identity",
                },
            }
        finally:
            await engine.dispose()

        result = _run_alembic_result(database_url, "downgrade", "0001")
        assert result.returncode != 0
        assert "forward-only" in result.stderr
        engine = create_async_engine(database_url)
        try:
            async with engine.connect() as conn:
                tables = await conn.run_sync(
                    lambda sync_conn: set(
                        __import__("sqlalchemy").inspect(sync_conn).get_table_names()
                    )
                )
            assert tables == EXPECTED_TABLES | {"alembic_version"}
        finally:
            await engine.dispose()
    finally:
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            database_name,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await admin.close()


@pytest.mark.asyncio
async def test_nonflat_upgrade_fails_before_any_universe_ddl_postgres() -> None:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        database_url = _database_url(database_name)
        _run_alembic(database_url, "upgrade", "0001")
        conn = await asyncpg.connect(database_url.replace("+asyncpg", ""))
        try:
            await conn.execute(
                """
                INSERT INTO brc_entry_lane_current (
                    lane_id, status, version
                ) VALUES ('global-entry', 'available', 1)
                """
            )
        finally:
            await conn.close()

        result = _run_alembic_result(database_url, "upgrade", "head")
        assert result.returncode != 0
        assert "runtime/trade tables must be empty" in result.stderr

        engine = create_async_engine(database_url)
        try:
            async with engine.connect() as conn:
                tables = await conn.run_sync(
                    lambda sync_conn: set(
                        __import__("sqlalchemy").inspect(sync_conn).get_table_names()
                    )
                )
                scope_columns = await conn.run_sync(
                    lambda sync_conn: {
                        row["name"]
                        for row in __import__("sqlalchemy")
                        .inspect(sync_conn)
                        .get_columns("brc_runtime_scopes_current")
                    }
                )
            assert "brc_strategy_universe_versions" not in tables
            assert "enabled" in scope_columns
            assert "observation_enabled" not in scope_columns
        finally:
            await engine.dispose()
    finally:
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            database_name,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await admin.close()


@pytest.mark.asyncio
async def test_flat_preflight_lock_blocks_concurrent_runtime_insert() -> None:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    blocker: asyncpg.Connection | None = None
    writer: asyncpg.Connection | None = None
    migration: asyncio.subprocess.Process | None = None
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        database_url = _database_url(database_name)
        _run_alembic(database_url, "upgrade", "0001")
        asyncpg_url = database_url.replace("+asyncpg", "")
        blocker = await asyncpg.connect(asyncpg_url)
        writer = await asyncpg.connect(asyncpg_url)
        blocker_tx = blocker.transaction()
        await blocker_tx.start()
        await blocker.execute(
            "LOCK TABLE brc_instruments IN ACCESS SHARE MODE"
        )
        migration = await _start_alembic(database_url, "upgrade", "head")
        await _wait_for_instrument_ddl_lock(admin, database_name)

        insert_task = asyncio.create_task(
            writer.execute(
                """
                INSERT INTO brc_entry_lane_current (
                    lane_id, status, version
                ) VALUES ('concurrent-entry', 'available', 1)
                """
            )
        )
        await asyncio.sleep(0.2)
        insert_crossed_preflight = insert_task.done()
        if not insert_task.done():
            insert_task.cancel()
            with suppress(asyncio.CancelledError):
                await insert_task

        await blocker_tx.rollback()
        stdout, stderr = await migration.communicate()
        assert migration.returncode == 0, (stdout + stderr)[-4000:]
        assert insert_crossed_preflight is False
    finally:
        if migration is not None and migration.returncode is None:
            migration.terminate()
            await migration.communicate()
        if writer is not None:
            await writer.close()
        if blocker is not None:
            await blocker.close()
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            database_name,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await admin.close()


def _database_url(database_name: str) -> str:
    if SAFE_DATABASE.fullmatch(database_name) is None:
        raise ValueError("unsafe kernel test database name")
    base = ADMIN_DSN.rsplit("/", 1)[0]
    return f"{base.replace('postgresql://', 'postgresql+asyncpg://', 1)}/{database_name}"


def _run_alembic(database_url: str, *args: str) -> None:
    result = _run_alembic_result(database_url, *args)
    assert result.returncode == 0, result.stderr[-4000:]


def _run_alembic_result(
    database_url: str,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "TRADING_KERNEL_DATABASE_URL": database_url}
    return subprocess.run(
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


async def _start_alembic(
    database_url: str,
    *args: str,
) -> asyncio.subprocess.Process:
    env = {**os.environ, "TRADING_KERNEL_DATABASE_URL": database_url}
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        "-c",
        "migrations/trading_kernel/alembic.ini",
        *args,
        cwd=REPO_ROOT,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


async def _wait_for_instrument_ddl_lock(
    admin: asyncpg.Connection,
    database_name: str,
) -> None:
    for _ in range(100):
        blocked = await admin.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_stat_activity
                WHERE datname = $1
                  AND wait_event_type = 'Lock'
                  AND query ILIKE 'ALTER TABLE brc_instruments%'
            )
            """,
            database_name,
        )
        if blocked:
            return
        await asyncio.sleep(0.02)
    raise AssertionError("migration did not reach blocked instrument DDL")


def _inspect_schema(sync_conn: object) -> tuple[set[str], dict[str, set[str]]]:
    inspector = __import__("sqlalchemy").inspect(sync_conn)

    def unique_names(table_name: str) -> set[str]:
        return {
            row["name"]
            for row in inspector.get_unique_constraints(table_name)
            if row["name"] is not None
        }

    def check_names(table_name: str) -> set[str]:
        return {
            row["name"]
            for row in inspector.get_check_constraints(table_name)
            if row["name"] is not None
        }

    def index_names(table_name: str) -> set[str]:
        return {
            row["name"]
            for row in inspector.get_indexes(table_name)
            if row["name"] is not None
        }

    def foreign_key_names(table_name: str) -> set[str]:
        return {
            row["name"]
            for row in inspector.get_foreign_keys(table_name)
            if row["name"] is not None
        }

    return set(inspector.get_table_names()), {
        "ticket_uniques": unique_names("brc_trade_tickets"),
        "command_uniques": unique_names("brc_exchange_commands"),
        "command_checks": check_names("brc_exchange_commands"),
        "event_uniques": unique_names("brc_trade_events"),
        "ticket_checks": check_names("brc_trade_tickets"),
        "aggregate_checks": check_names("brc_trade_aggregates"),
        "universe_indexes": index_names("brc_strategy_universe_versions"),
        "scope_indexes": index_names("brc_runtime_scopes_current"),
        "certification_indexes": index_names(
            "brc_instrument_certification_current"
        ),
        "member_foreign_keys": foreign_key_names(
            "brc_strategy_universe_members"
        ),
        "current_foreign_keys": foreign_key_names(
            "brc_strategy_universe_current"
        ),
        "scope_foreign_keys": foreign_key_names(
            "brc_runtime_scopes_current"
        ),
        "signal_foreign_keys": foreign_key_names("brc_signal_events"),
        "claim_foreign_keys": foreign_key_names("brc_capacity_claims"),
        "ticket_foreign_keys": foreign_key_names("brc_trade_tickets"),
    }
