"""Execute immutable historical seed code in disposable migration fixtures only."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tarfile
import tempfile
from functools import cache
from pathlib import Path

from sqlalchemy.engine import make_url

from tests.trading_kernel.support.postgres import SAFE_TEST_DATABASE

SOURCE_COMMIT = "dbe62a32c4ae74d3fd82c58a33196c6dc6f81357"
REPO_ROOT = Path(__file__).resolve().parents[3]


@cache
def _source_checkout() -> tempfile.TemporaryDirectory[str]:
    directory = tempfile.TemporaryDirectory(prefix="brc-frozen-seed-")
    archive = subprocess.run(
        ("git", "archive", SOURCE_COMMIT, "src", "scripts/trading_kernel", "migrations/trading_kernel"),
        cwd=REPO_ROOT, check=True, capture_output=True,
    )
    with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as bundle:
        bundle.extractall(directory.name, filter="data")
    return directory


def run_frozen_seed(database_url: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    """No new-code old-schema reader, fallback or compatibility adapter is installed."""
    if SAFE_TEST_DATABASE.fullmatch(make_url(database_url).database or "") is None:
        raise ValueError("frozen source execution requires a disposable test database")
    destination = _source_checkout().name
    return subprocess.run(
        (sys.executable, "scripts/trading_kernel/seed_runtime_authority.py", "--database-url", database_url, *arguments),
        cwd=destination, env={**os.environ, "PYTHONPATH": destination},
        capture_output=True, text=True, check=False, timeout=30,
    )


def arm_frozen_source(database_url: str, *, at_ms: int) -> None:
    result = run_frozen_seed(database_url, "arm-acceptance", "--now-ms", str(at_ms))
    assert result.returncode == 0, result.stderr[-4000:]


async def pause_sor_for_capacity_release(engine, *, at_ms: int) -> None:
    from sqlalchemy import text

    from src.trading_kernel.application.owner_control import (
        ControlMutationRequest,
        set_strategy_entry_state,
    )
    from src.trading_kernel.domain.owner_control import StrategyEntryState
    from src.trading_kernel.infrastructure.pg_unit_of_work import (
        PostgresKernelUnitOfWork,
    )
    from src.trading_kernel.infrastructure.runtime_identity import (
        CURRENT_SCHEMA_REVISION,
    )

    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == CURRENT_SCHEMA_REVISION
    async with PostgresKernelUnitOfWork(engine) as uow:
        control = await uow.owner_controls.get_strategy_control("SOR-001")
        assert control is not None
        await set_strategy_entry_state(
            uow, strategy_group_id="SOR-001", target_state=StrategyEntryState.PAUSED,
            request=ControlMutationRequest(expected_version=control.control_version, reason="owner_retired_sor",
                idempotency_key="source-fixture:sor-retired", owner_identity="test-owner", now_ms=at_ms),
            authentication_strength="session",
        )
