"""Income window, pagination and current-Review revision contract on disposable PG."""

from decimal import Decimal

import pytest

from src.trading_kernel.application.owner_console.models import (
    PerformanceQuery,
    ReviewListQuery,
    TradeListQuery,
)
from src.trading_kernel.application.owner_console.performance import (
    PerformanceSnapshotChanged,
)
from src.trading_kernel.application.owner_console.programmatic_review import (
    build_review_center,
)
from src.trading_kernel.application.owner_console.trades import build_trade_page
from src.trading_kernel.infrastructure.pg_owner_read_repository import (
    PostgresOwnerReadRepository,
    create_owner_read_engine,
    owner_read_transaction,
)
from tests.trading_kernel.integration.owner_console_support import owner_read_dsn
from tests.trading_kernel.support.owner_income import (
    _execute_owner_console_admin,
    _seed_owner_console_trades,
)

__all__ = ["owner_read_dsn"]
WINDOW = {"from_ms": 1800000000000, "to_ms": 1800001000000}


async def test_complete_window_is_independent_of_list_limit_and_revision_checked(
    owner_read_dsn,
):
    await _seed_owner_console_trades(owner_read_dsn)
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as conn:
            repo = PostgresOwnerReadRepository(conn)
            full = await repo.read_performance_summary(PerformanceQuery(**WINDOW))
            again = await repo.read_performance_summary(
                PerformanceQuery(**WINDOW, limit=1)
            )
            first = build_review_center(
                await repo.read_review_center_facts(ReviewListQuery(**WINDOW, limit=1))
            )
            second = build_review_center(
                await repo.read_review_center_facts(
                    ReviewListQuery(**WINDOW, limit=1, cursor=first.next_cursor)
                )
            )
            assert full.sample_count == 4
            assert full.snapshot_id == again.snapshot_id
            assert full.verified_totals.net_pnl.value == Decimal("3.5100")
            assert full.metric_coverage["net_pnl"].available_count == 1
            assert first.items[0].ticket_id != second.items[0].ticket_id
        await _execute_owner_console_admin(
            owner_read_dsn,
            "UPDATE brc_trade_reviews SET metrics=jsonb_set(metrics,'{net_pnl_quote}','\"4.51\"') WHERE review_id='review:y:v2'",
        )
        async with owner_read_transaction(engine) as conn:
            with pytest.raises(PerformanceSnapshotChanged):
                await PostgresOwnerReadRepository(conn).read_performance_summary(
                    PerformanceQuery(**WINDOW, snapshot=full.snapshot_id)
                )
    finally:
        await engine.dispose()


async def test_created_before_window_still_belongs_to_terminal_income_and_unknown_exit_stays_unknown(
    owner_read_dsn,
):
    await _seed_owner_console_trades(owner_read_dsn)
    await _execute_owner_console_admin(
        owner_read_dsn,
        "UPDATE brc_trade_tickets SET created_at_ms=1799000000000 WHERE ticket_id='ticket:y'",
    )
    await _execute_owner_console_admin(
        owner_read_dsn,
        "DELETE FROM brc_trade_events WHERE ticket_id='ticket:y' AND event_type='ExitRequested'",
    )
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as conn:
            repo = PostgresOwnerReadRepository(conn)
            income = await repo.read_performance_summary(PerformanceQuery(**WINDOW))
            trades = build_trade_page(
                await repo.read_trade_page_facts(TradeListQuery(**WINDOW))
            )
            reviews = build_review_center(
                await repo.read_review_center_facts(ReviewListQuery(**WINDOW))
            )
            assert "ticket:y" in {t.ticket_id for t in trades.items} & {
                r.ticket_id for r in reviews.items
            }
            assert income.breakdown["unknown"].verified_totals.net_pnl.value == Decimal(
                "3.5100"
            )
            natural = await repo.read_performance_summary(
                PerformanceQuery(**WINDOW, exit_scope="strategy")
            )
            assert natural.verified_totals.net_pnl.value is None
    finally:
        await engine.dispose()


async def test_owner_and_safety_cause_filter_is_same_for_summary_and_review(
    owner_read_dsn,
):
    await _seed_owner_console_trades(owner_read_dsn)
    await _execute_owner_console_admin(
        owner_read_dsn,
        "UPDATE brc_trade_events SET payload=jsonb_set(payload,'{reason}','\"owner_flatten_all:auth:exact\"') WHERE ticket_id='ticket:y' AND event_type='ExitRequested'",
    )
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as conn:
            repo = PostgresOwnerReadRepository(conn)
            summary = await repo.read_performance_summary(
                PerformanceQuery(**WINDOW, exit_scope="owner")
            )
            page = build_review_center(
                await repo.read_review_center_facts(
                    ReviewListQuery(**WINDOW, exit_scope="owner")
                )
            )
            assert summary.verified_totals.net_pnl.value == Decimal("3.5100")
            assert {i.ticket_id for i in page.items} == {"ticket:y"}
            assert (
                summary.breakdown["strategy"].sample_count
                + summary.breakdown["owner"].sample_count
                + summary.breakdown["safety"].sample_count
                + summary.breakdown["unknown"].sample_count
                == 4
            )
    finally:
        await engine.dispose()


async def test_strategy_matrix_income_and_full_summary_share_identical_population(
    owner_read_dsn,
):
    from src.trading_kernel.application.owner_console.models import StrategySummaryQuery
    from src.trading_kernel.application.owner_console.strategies import (
        build_strategy_page,
    )

    await _seed_owner_console_trades(owner_read_dsn)
    await _execute_owner_console_admin(
        owner_read_dsn,
        "UPDATE brc_trade_tickets SET created_at_ms=1799000000000 WHERE ticket_id='ticket:y'",
    )
    await _execute_owner_console_admin(
        owner_read_dsn,
        "UPDATE brc_trade_tickets SET strategy_version_id='version:' || strategy_group_id",
    )
    await _execute_owner_console_admin(
        owner_read_dsn,
        """
        INSERT INTO brc_strategy_groups(strategy_group_id,display_name,active_version_id,status,updated_at_ms)
        SELECT DISTINCT strategy_group_id,strategy_group_id,strategy_version_id,'active',1800000000000 FROM brc_trade_tickets ON CONFLICT DO NOTHING
    """,
    )
    await _execute_owner_console_admin(
        owner_read_dsn,
        """
        INSERT INTO brc_strategy_versions(strategy_version_id,strategy_group_id,version,semantics,status,created_at_ms)
        SELECT DISTINCT strategy_version_id,strategy_group_id,1,'{}'::jsonb,'retired',1800000000000 FROM brc_trade_tickets ON CONFLICT DO NOTHING
    """,
    )
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as conn:
            repo = PostgresOwnerReadRepository(conn)
            matrix = build_strategy_page(
                await repo.read_strategy_page_facts(
                    StrategySummaryQuery(**WINDOW, view="all")
                )
            )
            summary = await repo.read_performance_summary(
                PerformanceQuery(**WINDOW, view="all")
            )
            assert (
                sum(
                    (
                        i.net_pnl.value
                        for i in matrix.items
                        if i.net_pnl.value is not None
                    ),
                    Decimal(0),
                )
                == summary.verified_totals.net_pnl.value
            )
            assert matrix.performance.snapshot_id == summary.snapshot_id
            assert (
                sum(i.confirmed_review_count for i in matrix.items)
                == summary.confirmed_count
            )
    finally:
        await engine.dispose()


async def test_late_review_update_keeps_profit_on_original_terminal_day(owner_read_dsn):
    from src.trading_kernel.interfaces.owner_console_http.routes._shared import (
        shanghai_day_start_ms,
    )

    await _seed_owner_console_trades(owner_read_dsn)
    await _execute_owner_console_admin(
        owner_read_dsn,
        "UPDATE brc_trade_reviews SET created_at_ms=1800100000000 WHERE review_id='review:y:v2'",
    )
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as conn:
            repo = PostgresOwnerReadRepository(conn)
            original = await repo.read_performance_summary(PerformanceQuery(**WINDOW))
            late = await repo.read_performance_summary(
                PerformanceQuery(from_ms=1800090000000, to_ms=1800110000000)
            )
            assert original.verified_totals.net_pnl.value == Decimal("3.5100")
            assert late.sample_count == 0
            # UTC 16:00 is Shanghai midnight.
            assert shanghai_day_start_ms(1792598400000) == 1792598400000
    finally:
        await engine.dispose()
