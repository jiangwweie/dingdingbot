from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
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
async def test_clean_alembic_baseline_upgrades_and_downgrades_postgres() -> None:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        database_url = _database_url(database_name)
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
                },
                "aggregate_checks": {
                    "ck_brc_trade_aggregates_position_nonnegative",
                    "ck_brc_trade_aggregates_protection_nonnegative",
                    "ck_brc_trade_aggregates_sequence_positive",
                    "ck_brc_trade_aggregates_tp1_filled_nonnegative",
                    "ck_brc_trade_aggregates_tp1_target_nonnegative",
                    "ck_brc_trade_aggregates_version_positive",
                },
            }
        finally:
            await engine.dispose()

        _run_alembic(database_url, "downgrade", "base")
        engine = create_async_engine(database_url)
        try:
            async with engine.connect() as conn:
                tables = await conn.run_sync(
                    lambda sync_conn: set(
                        __import__("sqlalchemy").inspect(sync_conn).get_table_names()
                    )
                )
            assert tables == {"alembic_version"}
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

    return set(inspector.get_table_names()), {
        "ticket_uniques": unique_names("brc_trade_tickets"),
        "command_uniques": unique_names("brc_exchange_commands"),
        "command_checks": check_names("brc_exchange_commands"),
        "event_uniques": unique_names("brc_trade_events"),
        "ticket_checks": check_names("brc_trade_tickets"),
        "aggregate_checks": check_names("brc_trade_aggregates"),
    }
