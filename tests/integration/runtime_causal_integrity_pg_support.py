"""Disposable PostgreSQL support for P0-RCI integration certification."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from decimal import Decimal
import os
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine, URL, make_url

from src.application.action_time.exchange_command import (
    claim_next_exchange_command,
)
from src.application.action_time.exchange_command_worker import (
    run_one_ticket_bound_exchange_command,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ADMIN_URL = (
    "postgresql+psycopg://dingdingbot:dingdingbot_dev@127.0.0.1:5432/postgres"
)
_SAFE_DATABASE_NAME = re.compile(r"^brc_rci_test_[a-f0-9]{12}$")


class FakeExchangeLedgerGateway:
    """Test-only external side-effect ledger durable across worker death."""

    runtime_account_id = "owner-subaccount-runtime-v0"
    runtime_exchange_id = "binance_usdm"

    def __init__(
        self,
        database_url: str,
        *,
        caller_label: str,
        accepted_event: Any | None = None,
        hold_event: Any | None = None,
    ) -> None:
        self._engine = sa.create_engine(database_url)
        self._caller_label = caller_label
        self._accepted_event = accepted_event
        self._hold_event = hold_event

    async def place_order(
        self,
        *,
        client_order_id: str,
        amount: Decimal,
        **kwargs: Any,
    ) -> Any:
        del kwargs
        with self._engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO brc_rci_fake_exchange_attempts "
                    "(client_order_id, caller_label, amount) "
                    "VALUES (:client_order_id, :caller_label, :amount)"
                ),
                {
                    "client_order_id": client_order_id,
                    "caller_label": self._caller_label,
                    "amount": str(amount),
                },
            )
            conn.execute(
                sa.text(
                    "INSERT INTO brc_rci_fake_exchange_orders "
                    "(client_order_id, amount) "
                    "VALUES (:client_order_id, :amount) "
                    "ON CONFLICT (client_order_id) DO NOTHING"
                ),
                {"client_order_id": client_order_id, "amount": str(amount)},
            )
        if self._accepted_event is not None:
            self._accepted_event.set()
        if self._hold_event is not None:
            await asyncio.to_thread(self._hold_event.wait, 30)
        return SimpleNamespace(
            is_success=True,
            exchange_order_id=f"fake-{client_order_id}",
            filled_qty=amount,
            average_exec_price=Decimal("2000"),
            exchange_order_status="FILLED",
        )

    async def cancel_order(self, **kwargs: Any) -> Any:
        raise AssertionError(f"unexpected_cancel:{kwargs}")


def claim_then_hold_process(
    database_url: str,
    *,
    claimed_event: Any,
    hold_event: Any,
    now_ms: int,
    lease_ms: int,
) -> None:
    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as conn:
            claimed = claim_next_exchange_command(
                conn,
                claim_owner="rci-claim-crash-worker",
                now_ms=now_ms,
                lease_ms=lease_ms,
                command_sources=("protected_submit",),
            )
        if not claimed:
            raise RuntimeError("rci_claim_process_found_no_command")
        claimed_event.set()
        hold_event.wait(30)
    finally:
        engine.dispose()


def run_fake_exchange_worker_process(
    database_url: str,
    *,
    worker_id: str,
    caller_label: str,
    now_ms: int,
    lease_ms: int,
    start_event: Any | None = None,
    accepted_event: Any | None = None,
    hold_event: Any | None = None,
) -> None:
    if start_event is not None and not start_event.wait(30):
        raise RuntimeError("rci_worker_start_timeout")
    engine = sa.create_engine(database_url)
    gateway = FakeExchangeLedgerGateway(
        database_url,
        caller_label=caller_label,
        accepted_event=accepted_event,
        hold_event=hold_event,
    )
    try:
        asyncio.run(
            run_one_ticket_bound_exchange_command(
                engine,
                gateway=gateway,
                worker_id=worker_id,
                now_ms=now_ms,
                lease_ms=lease_ms,
                command_sources=("protected_submit",),
            )
        )
    finally:
        engine.dispose()


def _database_name() -> str:
    return f"brc_rci_test_{uuid4().hex[:12]}"


def _validated_database_name(value: str) -> str:
    if _SAFE_DATABASE_NAME.fullmatch(value) is None:
        raise ValueError("unsafe_rci_database_name")
    return value


def _database_url(admin_url: URL, database_name: str) -> URL:
    return admin_url.set(database=_validated_database_name(database_name))


def _admin_engine(admin_url: URL) -> Engine:
    if admin_url.get_backend_name() != "postgresql":
        raise RuntimeError("BRC_TEST_POSTGRES_ADMIN_URL_must_be_postgresql")
    return sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")


def _create_database(
    admin_engine: Engine,
    database_name: str,
    *,
    template_name: str | None = None,
) -> None:
    name = _validated_database_name(database_name)
    template_clause = (
        f' TEMPLATE "{_validated_database_name(template_name)}"'
        if template_name is not None
        else ""
    )
    with admin_engine.connect() as conn:
        conn.exec_driver_sql(f'CREATE DATABASE "{name}"{template_clause}')


def _drop_database(admin_engine: Engine, database_name: str) -> None:
    name = _validated_database_name(database_name)
    with admin_engine.connect() as conn:
        conn.execute(
            sa.text(
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity "
                "WHERE datname = :database_name "
                "AND pid <> pg_backend_pid()"
            ),
            {"database_name": name},
        )
        conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}"')


def _run_checked(
    command: list[str],
    *,
    env: dict[str, str],
    failure_code: str,
) -> None:
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"{failure_code}:{completed.stderr[-2000:]}")


def _migrate(database_url: URL) -> None:
    env = os.environ.copy()
    env["PG_DATABASE_URL"] = database_url.render_as_string(
        hide_password=False
    )
    _run_checked(
        [sys.executable, "-m", "alembic", "upgrade", "106"],
        env=env,
        failure_code="rci_alembic_upgrade_106_failed",
    )
    _run_checked(
        [
            sys.executable,
            "scripts/seed_runtime_control_state_foundation.py",
            "--apply",
            "--migration-baseline-revision",
            "106",
        ],
        env=env,
        failure_code="rci_migration_baseline_seed_failed",
    )
    _run_checked(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=env,
        failure_code="rci_alembic_upgrade_head_failed",
    )
    _run_checked(
        [
            sys.executable,
            "scripts/seed_runtime_control_state_foundation.py",
            "--apply",
        ],
        env=env,
        failure_code="rci_current_authority_seed_failed",
    )


@pytest.fixture(scope="session")
def postgres_certification_template() -> Iterator[tuple[URL, str]]:
    admin_url = make_url(
        os.environ.get("BRC_TEST_POSTGRES_ADMIN_URL", DEFAULT_ADMIN_URL)
    )
    admin_engine = _admin_engine(admin_url)
    template_name = _database_name()
    template_url = _database_url(admin_url, template_name)
    _create_database(admin_engine, template_name)
    try:
        _migrate(template_url)
        yield admin_url, template_name
    finally:
        _drop_database(admin_engine, template_name)
        admin_engine.dispose()


@pytest.fixture()
def postgres_certification_engine(
    postgres_certification_template: tuple[URL, str],
) -> Iterator[Engine]:
    admin_url, template_name = postgres_certification_template
    admin_engine = _admin_engine(admin_url)
    database_name = _database_name()
    _create_database(
        admin_engine,
        database_name,
        template_name=template_name,
    )
    engine = sa.create_engine(_database_url(admin_url, database_name))
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "CREATE TABLE brc_rci_fake_exchange_attempts ("
                    "attempt_id BIGSERIAL PRIMARY KEY, "
                    "client_order_id TEXT NOT NULL, "
                    "caller_label TEXT NOT NULL, "
                    "amount NUMERIC NOT NULL)"
                )
            )
            conn.execute(
                sa.text(
                    "CREATE TABLE brc_rci_fake_exchange_orders ("
                    "client_order_id TEXT PRIMARY KEY, "
                    "amount NUMERIC NOT NULL)"
                )
            )
        yield engine
    finally:
        engine.dispose()
        _drop_database(admin_engine, database_name)
        admin_engine.dispose()
