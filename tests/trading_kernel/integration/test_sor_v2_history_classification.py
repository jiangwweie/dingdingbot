from __future__ import annotations

import importlib
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

from src.trading_kernel.infrastructure.pg_models import (
    exchange_commands,
    signal_events,
    trade_aggregates,
    trade_events,
    trade_reviews,
    trade_tickets,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from tests.trading_kernel.integration.test_issue_ticket import (
    ADMIN_DSN,
    SAFE_DATABASE,
    _database_url,
)
from tests.trading_kernel.integration.test_sor_v3_compatible_migration import (
    V4_REVISION,
    _run_migration,
    _seed_v4_history,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_sor_v2_history_classification_cli_is_bounded_and_file_free(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(
                REPO_ROOT
                / "scripts"
                / "trading_kernel"
                / "classify_sor_v2_history.py"
            ),
            "--help",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--ticket-id" in result.stdout
    assert "--classification" in result.stdout
    assert list(tmp_path.rglob("*")) == []


@pytest_asyncio.fixture
async def history_engine() -> AsyncGenerator[AsyncEngine, None]:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    await admin.execute(f'CREATE DATABASE "{database_name}"')
    database_url = _database_url(database_name)
    result = _run_migration(database_url, "upgrade", V4_REVISION)
    assert result.returncode == 0, result.stderr[-4000:]
    engine = create_async_engine(database_url)
    try:
        await _seed_v4_history(engine)
        result = _run_migration(database_url, "upgrade", "head")
        assert result.returncode == 0, result.stderr[-4000:]
        await _prepare_terminal_review_authority(engine)
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


@pytest.mark.asyncio
async def test_sor_v2_classification_appends_exact_review_revisions_only(
    history_engine: AsyncEngine,
) -> None:
    try:
        classification = importlib.import_module(
            "src.trading_kernel.application.classify_sor_v2_history"
        )
    except ModuleNotFoundError:
        pytest.fail("SOR v2 history classification application is missing")

    before = await _lineage_snapshot(history_engine)
    async with PostgresKernelUnitOfWork(history_engine) as uow:
        bnb = await classification.classify_sor_v2_history(
            uow,
            classification.ClassifySorV2HistoryRequest(
                ticket_id="ticket-v2-1",
                classification=(
                    classification.SorV2HistoryClassification.RIGHT_TAIL_UNVERIFIED
                ),
                classified_at_ms=4_000,
            ),
        )
    async with PostgresKernelUnitOfWork(history_engine) as uow:
        invalid = await classification.classify_sor_v2_history(
            uow,
            classification.ClassifySorV2HistoryRequest(
                ticket_id="ticket-v2-2",
                classification=(
                    classification.SorV2HistoryClassification.INVALID_PERSISTENT_STATE
                ),
                classified_at_ms=4_100,
            ),
        )
    async with PostgresKernelUnitOfWork(history_engine) as uow:
        repeated = await classification.classify_sor_v2_history(
            uow,
            classification.ClassifySorV2HistoryRequest(
                ticket_id="ticket-v2-2",
                classification=(
                    classification.SorV2HistoryClassification.INVALID_PERSISTENT_STATE
                ),
                classified_at_ms=4_200,
            ),
        )

    after = await _lineage_snapshot(history_engine)
    assert bnb.status.value == "revised"
    assert invalid.status.value == "revised"
    assert repeated.status.value == "already_classified"
    assert repeated.review_id == invalid.review_id
    assert after["signals"] == before["signals"]
    assert after["tickets"] == before["tickets"]
    assert after["commands"] == before["commands"]
    assert len(after["reviews"]) == len(before["reviews"]) + 2
    assert len(after["events"]) == len(before["events"]) + 2

    bnb_review = after["current_reviews"]["ticket-v2-1"]
    invalid_review = after["current_reviews"]["ticket-v2-2"]
    assert bnb_review["revision"] == 2
    assert bnb_review["supersedes_review_id"] == "review-v2-1"
    assert bnb_review["outcome"] == "closed"
    assert bnb_review["metrics"] == {"net_pnl_quote": "1"}
    assert bnb_review["decision_impact"] == {
        "entry_semantics": "unverified_against_sor_v3_edge",
        "evidence_scope": [
            "lifecycle",
            "tp1_transition",
            "break_even",
            "structural_runner",
            "right_tail",
        ],
        "entry_alpha_inclusion": "excluded_until_candle_reconstruction",
    }
    assert invalid_review["revision"] == 2
    assert invalid_review["supersedes_review_id"] == "review-v2-2"
    assert invalid_review["outcome"] == "closed"
    assert invalid_review["metrics"] == {"net_pnl_quote": "-1"}
    assert invalid_review["decision_impact"] == {
        "entry_semantics": "invalid_sor_v2_persistent_state",
        "entry_alpha_inclusion": "excluded",
        "execution_evidence": "retained",
        "lifecycle_evidence": "retained",
        "economics_evidence": "retained",
    }


@pytest.mark.asyncio
async def test_sor_v2_classification_refuses_conflicting_reclassification(
    history_engine: AsyncEngine,
) -> None:
    classification = importlib.import_module(
        "src.trading_kernel.application.classify_sor_v2_history"
    )
    async with PostgresKernelUnitOfWork(history_engine) as uow:
        first = await classification.classify_sor_v2_history(
            uow,
            classification.ClassifySorV2HistoryRequest(
                ticket_id="ticket-v2-2",
                classification=(
                    classification.SorV2HistoryClassification.INVALID_PERSISTENT_STATE
                ),
                classified_at_ms=4_100,
            ),
        )

    with pytest.raises(ValueError, match="different classification"):
        async with PostgresKernelUnitOfWork(history_engine) as uow:
            await classification.classify_sor_v2_history(
                uow,
                classification.ClassifySorV2HistoryRequest(
                    ticket_id="ticket-v2-2",
                    classification=(
                        classification.SorV2HistoryClassification.RIGHT_TAIL_UNVERIFIED
                    ),
                    classified_at_ms=4_200,
                ),
            )

    async with history_engine.connect() as connection:
        reviews = (
            await connection.execute(
                sa.select(
                    trade_reviews.c.review_id,
                    trade_reviews.c.revision,
                )
                .where(trade_reviews.c.ticket_id == "ticket-v2-2")
                .order_by(trade_reviews.c.revision)
            )
        ).all()
    assert reviews == [("review-v2-2", 1), (first.review_id, 2)]


@pytest.mark.asyncio
async def test_sor_v2_classification_requires_ticket_and_aggregate_terminal_truth(
    history_engine: AsyncEngine,
) -> None:
    classification = importlib.import_module(
        "src.trading_kernel.application.classify_sor_v2_history"
    )
    async with history_engine.begin() as connection:
        await connection.execute(
            sa.update(trade_tickets)
            .where(trade_tickets.c.ticket_id == "ticket-v2-2")
            .values(status="issued", terminal_at_ms=None)
        )

    with pytest.raises(ValueError, match="terminal Ticket"):
        async with PostgresKernelUnitOfWork(history_engine) as uow:
            await classification.classify_sor_v2_history(
                uow,
                classification.ClassifySorV2HistoryRequest(
                    ticket_id="ticket-v2-2",
                    classification=(
                        classification.SorV2HistoryClassification.INVALID_PERSISTENT_STATE
                    ),
                    classified_at_ms=4_100,
                ),
            )


@pytest.mark.asyncio
async def test_sor_v2_classification_requires_monotonic_review_time(
    history_engine: AsyncEngine,
) -> None:
    classification = importlib.import_module(
        "src.trading_kernel.application.classify_sor_v2_history"
    )

    with pytest.raises(ValueError, match="later than the current Review"):
        async with PostgresKernelUnitOfWork(history_engine) as uow:
            await classification.classify_sor_v2_history(
                uow,
                classification.ClassifySorV2HistoryRequest(
                    ticket_id="ticket-v2-2",
                    classification=(
                        classification.SorV2HistoryClassification.INVALID_PERSISTENT_STATE
                    ),
                    classified_at_ms=3_600,
                ),
            )


async def _prepare_terminal_review_authority(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.update(trade_tickets)
            .where(trade_tickets.c.ticket_id == "ticket-v2-2")
            .values(status="terminal", terminal_at_ms=3_500)
        )
        await connection.execute(
            sa.insert(trade_reviews).values(
                review_id="review-v2-2",
                ticket_id="ticket-v2-2",
                revision=1,
                supersedes_review_id=None,
                outcome="closed",
                metrics={"net_pnl_quote": "-1"},
                decision_impact={},
                created_at_ms=3_600,
            )
        )
        await connection.execute(
            sa.insert(trade_aggregates),
            [
                _terminal_aggregate_values(
                    ticket_id="ticket-v2-1",
                    review_id="review-v2-1",
                    updated_at_ms=3_100,
                ),
                _terminal_aggregate_values(
                    ticket_id="ticket-v2-2",
                    review_id="review-v2-2",
                    updated_at_ms=3_600,
                ),
            ],
        )


def _terminal_aggregate_values(
    *,
    ticket_id: str,
    review_id: str,
    updated_at_ms: int,
) -> dict[str, object]:
    return {
        "ticket_id": ticket_id,
        "status": "terminal",
        "version": 10,
        "last_event_sequence": 10,
        "entry_lane_held": False,
        "position_qty": 0,
        "protected_qty": 0,
        "tp1_target_qty": 0,
        "tp1_filled_qty": 0,
        "review_id": review_id,
        "lifecycle_due_at_ms": None,
        "reconciliation_due_at_ms": None,
        "updated_at_ms": updated_at_ms,
    }


async def _lineage_snapshot(engine: AsyncEngine) -> dict[str, object]:
    async with engine.connect() as connection:
        signals = tuple(
            tuple(row)
            for row in (
                await connection.execute(
                    sa.select(
                        signal_events.c.signal_event_id,
                        signal_events.c.exposure_episode_id,
                    ).order_by(signal_events.c.signal_event_id)
                )
            ).all()
        )
        tickets = tuple(
            tuple(row)
            for row in (
                await connection.execute(
                    sa.select(
                        trade_tickets.c.ticket_id,
                        trade_tickets.c.signal_event_id,
                        trade_tickets.c.exposure_episode_id,
                    ).order_by(trade_tickets.c.ticket_id)
                )
            ).all()
        )
        commands = tuple(
            tuple(row)
            for row in (
                await connection.execute(
                    sa.select(
                        exchange_commands.c.command_id,
                        exchange_commands.c.status,
                    ).order_by(exchange_commands.c.command_id)
                )
            ).all()
        )
        reviews = tuple(
            dict(row)
            for row in (
                await connection.execute(
                    sa.select(trade_reviews).order_by(
                        trade_reviews.c.ticket_id,
                        trade_reviews.c.revision,
                    )
                )
            ).mappings()
        )
        current_reviews = {
            str(row["ticket_id"]): dict(row)
            for row in (
                await connection.execute(
                    sa.select(trade_reviews)
                    .join(
                        trade_aggregates,
                        trade_aggregates.c.review_id == trade_reviews.c.review_id,
                    )
                    .order_by(trade_reviews.c.ticket_id)
                )
            ).mappings()
        }
        events = tuple(
            tuple(row)
            for row in (
                await connection.execute(
                    sa.select(
                        trade_events.c.event_id,
                        trade_events.c.ticket_id,
                        trade_events.c.sequence,
                        trade_events.c.event_type,
                    ).order_by(
                        trade_events.c.ticket_id,
                        trade_events.c.sequence,
                    )
                )
            ).all()
        )
    return {
        "signals": signals,
        "tickets": tickets,
        "commands": commands,
        "reviews": reviews,
        "current_reviews": current_reviews,
        "events": events,
    }
