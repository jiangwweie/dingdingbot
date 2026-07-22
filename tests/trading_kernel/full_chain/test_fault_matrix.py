from __future__ import annotations

from decimal import Decimal
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.trading_kernel.application.dispatch_exchange_command import (
    DispatchCommandRequest,
    DispatchCommandStatus,
    dispatch_one_command,
)
from src.trading_kernel.application.issue_ticket import IssueTicketStatus, issue_ticket
from src.trading_kernel.application.ports import VenueCommandRequest
from src.trading_kernel.application.reconcile_ticket import (
    ReconcileTicketRequest,
    ReconcileTicketStatus,
    reconcile_ticket,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommandResult,
    ExchangeCommandStatus,
)
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.infrastructure.pg_models import owner_policy_current
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from tests.trading_kernel.unit.test_ticket import _ticket
from tests.trading_kernel.integration.test_issue_ticket import _issue_request


REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_DSN = os.getenv(
    "BRC_TEST_POSTGRES_ADMIN_URL",
    "postgresql://dingdingbot:dingdingbot_dev@127.0.0.1:5432/postgres",
)
SAFE_DATABASE = re.compile(r"^brc_kernel_test_[a-f0-9]{12}$")


@pytest_asyncio.fixture
async def fault_engine() -> AsyncEngine:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    await admin.execute(f'CREATE DATABASE "{database_name}"')
    database_url = _database_url(database_name)
    _run_alembic(database_url, "upgrade", "head")
    engine = create_async_engine(database_url)
    try:
        yield engine
    finally:
        await engine.dispose()
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            database_name,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await admin.close()


class AcceptingFaultVenue:
    def __init__(self) -> None:
        self.calls: list[VenueCommandRequest] = []

    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        self.calls.append(request)
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=2_000 + len(self.calls),
            exchange_order_id=(
                request.payload.exchange_order_id
                if isinstance(request.payload, CancelCommandPayload)
                else f"venue-{request.kind.value}-{len(self.calls)}"
            ),
        )


@pytest.mark.asyncio
async def test_partial_fill_cancels_remainder_before_controlled_flatten(
    fault_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    venue = AcceptingFaultVenue()
    await _seed_policy(fault_engine)
    async with PostgresKernelUnitOfWork(fault_engine) as uow:
        issued = await issue_ticket(
            uow,
            _issue_request(
                ticket=ticket,
                now_ms=1_001,
                claim_owner="issuer-1",
            ),
        )
    assert issued.status is IssueTicketStatus.ISSUED
    entry = await _dispatch(fault_engine, venue, ticket.identity.ticket_id, 1_100)
    assert entry.status is DispatchCommandStatus.ACCEPTED

    async with PostgresKernelUnitOfWork(fault_engine) as uow:
        partial = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=Decimal("0.0004"),
                    average_entry_price=Decimal("60000"),
                    observed_at_ms=1_200,
                ),
            ),
        )

    assert partial.status is ReconcileTicketStatus.PARTIAL_FILL_INCIDENT
    async with PostgresKernelUnitOfWork(fault_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
        lane = await uow.entry_admission.get_global_lane()
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.PARTIAL_FILL_INCIDENT
    assert aggregate.position_qty == Decimal("0.0004")
    assert incident is not None
    assert incident.incident_kind == "unsupported_partial_entry_fill"
    assert lane is not None and lane.status == "claimed"
    assert reservation is not None and reservation.status == "active"
    assert [command.kind.value for command in commands] == [
        "entry",
        "cancel_order",
    ]
    assert isinstance(commands[-1].payload, CancelCommandPayload)
    assert commands[-1].payload.exchange_order_id == aggregate.entry_exchange_order_id

    cancelled = await _dispatch(
        fault_engine,
        venue,
        ticket.identity.ticket_id,
        1_300,
    )
    assert cancelled.status is DispatchCommandStatus.ACCEPTED
    async with PostgresKernelUnitOfWork(fault_engine) as uow:
        after_cancel = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    assert after_cancel is not None
    assert after_cancel.status is AggregateStatus.CONTROLLED_FLATTEN_PENDING
    assert [command.kind.value for command in commands] == [
        "entry",
        "cancel_order",
        "controlled_flatten",
    ]

    flattened = await _dispatch(
        fault_engine,
        venue,
        ticket.identity.ticket_id,
        1_400,
    )
    assert flattened.status is DispatchCommandStatus.ACCEPTED
    async with PostgresKernelUnitOfWork(fault_engine) as uow:
        flat_recorded = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity="0",
                    average_entry_price=None,
                    open_orders=(),
                    observed_at_ms=1_500,
                ),
            ),
        )
    assert flat_recorded.status is ReconcileTicketStatus.POSITION_FLAT_RECORDED
    async with PostgresKernelUnitOfWork(fault_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        lane = await uow.entry_admission.get_global_lane()
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.RECONCILIATION_PENDING
    assert aggregate.position_qty == 0
    assert lane is not None and lane.status == "idle"
    assert reservation is not None and reservation.status == "active"


@pytest.mark.asyncio
async def test_readonly_certification_prints_json_without_report_files(
    fault_engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    async with PostgresKernelUnitOfWork(fault_engine) as uow:
        await seed_runtime_authority(
            uow,
            RuntimeAuthoritySeedRequest(
                account_id="subaccount-main",
                runtime_commit="a" * 40,
                schema_revision="0001_initial",
                seeded_at_ms=1_000,
            ),
        )
    database_url = fault_engine.url.render_as_string(hide_password=False)
    before = sorted(path.name for path in tmp_path.iterdir())

    result = subprocess.run(
        [
            sys.executable,
            "scripts/trading_kernel/certify_readonly.py",
            "--database-url",
            database_url,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema"] == "brc.trading_kernel.readonly_certification.v1"
    assert payload["status"] == "pass"
    assert payload["alembic_revision"] == "0001_initial"
    assert payload["checks"]["integrity_orphans"] == 0
    assert payload["checks"]["legacy_execution_tables"] == 0
    assert sorted(path.name for path in tmp_path.iterdir()) == before


@pytest.mark.asyncio
async def test_schema_verifier_accepts_only_clean_baseline(
    fault_engine: AsyncEngine,
) -> None:
    database_url = fault_engine.url.render_as_string(hide_password=False)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/trading_kernel/verify_schema.py",
            "--database-url",
            database_url,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema"] == "brc.trading_kernel.schema_verification.v1"
    assert payload["status"] == "pass"
    assert payload["alembic_revision"] == "0001_initial"
    assert payload["missing_tables"] == []
    assert payload["unexpected_tables"] == []


def test_runtime_hot_paths_use_exact_ids_without_schema_reflection() -> None:
    runtime_source = (
        REPO_ROOT / "src/trading_kernel/application/runtime.py"
    ).read_text(encoding="utf-8")
    repository_source = (
        REPO_ROOT / "src/trading_kernel/infrastructure/pg_repositories.py"
    ).read_text(encoding="utf-8")
    kernel_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (REPO_ROOT / "src/trading_kernel").rglob("*.py")
    )

    assert "brc_trade_events" not in runtime_source
    assert "trade_events" not in runtime_source
    assert "exchange_commands.c.command_id == command_id" in repository_source
    assert "trade_aggregates.c.ticket_id == ticket_id" in repository_source
    assert "exchange_commands.c.ticket_id == ticket_id" in repository_source
    assert ".limit(1)" in repository_source
    for forbidden in (
        "metadata.reflect(",
        ".reflect(",
        "autoload_with=",
        "get_table_names(",
        "information_schema.tables",
    ):
        assert forbidden not in kernel_source


async def _dispatch(
    engine: AsyncEngine,
    venue: AcceptingFaultVenue,
    ticket_id: str,
    now_ms: int,
):
    return await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine),
        venue,
        DispatchCommandRequest(
            worker_id=f"worker-{now_ms}",
            ticket_id=ticket_id,
            now_ms=now_ms,
            lease_until_ms=now_ms + 5_000,
            timeout_seconds=1,
        ),
    )


async def _seed_policy(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(owner_policy_current).values(
                owner_policy_id="policy-main",
                policy_version=7,
                enabled=True,
                real_submit_enabled=True,
                max_concurrent_tickets=2,
                max_gross_notional="1000",
                target_leverage="5",
                scope={},
                updated_at_ms=1_000,
            )
        )


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
