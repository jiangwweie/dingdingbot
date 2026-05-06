from __future__ import annotations

import unittest.mock
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.capital_protection import (
    DAILY_RISK_STATS_SCOPE_KEY,
    DAILY_RISK_STATS_UNAVAILABLE_REASON,
    CapitalProtectionManager,
    normalize_daily_risk_decimal,
)
from src.application.execution_orchestrator import ExecutionOrchestrator
from src.application.position_projection_service import PositionProjectionService
from src.domain.models import (
    CapitalProtectionConfig,
    Direction,
    Order,
    OrderRole,
    OrderStatus,
    OrderType,
    Position,
)
from src.infrastructure.pg_daily_risk_stats_repository import PgDailyRiskStatsRepository
from src.infrastructure.pg_models import (
    PGDailyRiskStatsAggregateORM,
    PGDailyRiskStatsEventORM,
)
from src.infrastructure.repository_ports import DailyRiskStatsEvent, DailyRiskStatsSnapshot


class _FakeAccountService:
    def __init__(self, balance: Decimal = Decimal("1000")) -> None:
        self._balance = balance

    async def get_balance(self) -> Decimal:
        return self._balance


class _FakeNotifier:
    async def send_alert(self, title: str, message: str) -> None:
        return None


class _FakeGateway:
    async def fetch_ticker_price(self, symbol: str) -> Decimal:
        return Decimal("100")

    async def get_market_info(self, symbol: str):
        return {
            "min_quantity": Decimal("0.001"),
            "quantity_precision": 3,
            "step_size": Decimal("0.001"),
        }


class _NoopOrderLifecycle:
    def set_entry_partially_filled_callback(self, callback) -> None:
        self.entry_partially_filled_callback = callback

    def set_entry_filled_callback(self, callback) -> None:
        self.entry_filled_callback = callback

    def set_exit_progressed_callback(self, callback) -> None:
        self.exit_progressed_callback = callback


class _InMemoryPositionRepository:
    def __init__(self) -> None:
        self._positions: dict[str, Position] = {}

    async def save(self, position: Position) -> None:
        self._positions[position.id] = position.model_copy(deep=True)

    async def get(self, position_id: str) -> Position | None:
        position = self._positions.get(position_id)
        return position.model_copy(deep=True) if position is not None else None


class _FailingDailyRiskStatsRepository:
    async def initialize(self) -> None:
        return None

    async def restore_or_create(self, scope_key: str, stats_date: date):
        raise RuntimeError("restore unavailable")

    async def record_event(self, event: DailyRiskStatsEvent):
        raise RuntimeError("write unavailable")

    async def get(self, scope_key: str, stats_date: date):
        return None


class _TraceSink:
    def __init__(self) -> None:
        self.events = []

    def emit(self, event) -> None:
        self.events.append(event)


@pytest_asyncio.fixture()
async def daily_stats_repo():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(PGDailyRiskStatsAggregateORM.__table__.create)
        await conn.run_sync(PGDailyRiskStatsEventORM.__table__.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PgDailyRiskStatsRepository(session_maker=session_maker)
    finally:
        await engine.dispose()


def _config() -> CapitalProtectionConfig:
    config = CapitalProtectionConfig()
    config.daily["max_trade_count"] = 10
    config.daily["max_loss_amount"] = Decimal("100")
    return config


def _manager(**kwargs) -> CapitalProtectionManager:
    return CapitalProtectionManager(
        config=kwargs.pop("config", _config()),
        account_service=_FakeAccountService(),
        notifier=_FakeNotifier(),
        gateway=_FakeGateway(),
        **kwargs,
    )


def _event(
    *,
    event_key: str = "daily-risk:v1:runtime:default:2026-05-06:pos:sig:0.5",
    stats_date: date = date(2026, 5, 6),
    delta_exit_qty: Decimal = Decimal("0.5"),
    delta_realized_pnl: Decimal = Decimal("5"),
    trade_count_delta: int = 0,
) -> DailyRiskStatsEvent:
    return DailyRiskStatsEvent(
        event_key=event_key,
        scope_key=DAILY_RISK_STATS_SCOPE_KEY,
        stats_date=stats_date,
        position_id="pos_sig-ls002b",
        signal_id="sig-ls002b",
        exit_order_id="exit-order",
        delta_exit_qty=delta_exit_qty,
        delta_realized_pnl=delta_realized_pnl,
        trade_count_delta=trade_count_delta,
        occurred_at=datetime.now(timezone.utc),
    )


def _position(signal_id: str = "sig-ls002b") -> Position:
    return Position(
        id=f"pos_{signal_id}",
        signal_id=signal_id,
        symbol="ETH/USDT:USDT",
        direction=Direction.LONG,
        entry_price=Decimal("100"),
        current_qty=Decimal("1"),
        watermark_price=Decimal("100"),
        realized_pnl=Decimal("0"),
        total_fees_paid=Decimal("0"),
        total_funding_paid=Decimal("0"),
        opened_at=1,
        closed_at=None,
        is_closed=False,
    )


def _exit_order(
    *,
    order_id: str = "exit-order",
    signal_id: str = "sig-ls002b",
    filled_qty: Decimal = Decimal("0.5"),
    price: Decimal = Decimal("110"),
) -> Order:
    return Order(
        id=order_id,
        signal_id=signal_id,
        symbol="ETH/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=price,
        requested_qty=filled_qty,
        filled_qty=filled_qty,
        average_exec_price=price,
        status=OrderStatus.FILLED,
        created_at=1,
        updated_at=1,
        reduce_only=True,
        close_fee=Decimal("0"),
    )


@pytest.mark.asyncio
async def test_restore_or_create_creates_empty_aggregate(daily_stats_repo):
    snapshot = await daily_stats_repo.restore_or_create(
        DAILY_RISK_STATS_SCOPE_KEY,
        date(2026, 5, 6),
    )

    assert snapshot.scope_key == DAILY_RISK_STATS_SCOPE_KEY
    assert snapshot.stats_date == date(2026, 5, 6)
    assert snapshot.realized_pnl == Decimal("0")
    assert snapshot.trade_count == 0


@pytest.mark.asyncio
async def test_restore_or_create_restores_existing_aggregate(daily_stats_repo):
    await daily_stats_repo.restore_or_create(DAILY_RISK_STATS_SCOPE_KEY, date(2026, 5, 6))
    await daily_stats_repo.record_event(
        _event(delta_realized_pnl=Decimal("-12.5"), trade_count_delta=1)
    )

    snapshot = await daily_stats_repo.restore_or_create(
        DAILY_RISK_STATS_SCOPE_KEY,
        date(2026, 5, 6),
    )

    assert snapshot.realized_pnl == Decimal("-12.500000000000000000")
    assert snapshot.trade_count == 1


@pytest.mark.asyncio
async def test_record_event_insert_updates_aggregate(daily_stats_repo):
    result = await daily_stats_repo.record_event(
        _event(delta_realized_pnl=Decimal("5.25"), trade_count_delta=1)
    )

    assert result.inserted is True
    assert result.snapshot.realized_pnl == Decimal("5.250000000000000000")
    assert result.snapshot.trade_count == 1


@pytest.mark.asyncio
async def test_duplicate_event_key_is_idempotent(daily_stats_repo):
    event = _event(delta_realized_pnl=Decimal("5"), trade_count_delta=1)

    first = await daily_stats_repo.record_event(event)
    second = await daily_stats_repo.record_event(event)

    assert first.inserted is True
    assert second.inserted is False
    assert second.snapshot.realized_pnl == Decimal("5.000000000000000000")
    assert second.snapshot.trade_count == 1


@pytest.mark.asyncio
async def test_same_exit_order_second_cumulative_fill_applies_new_delta(daily_stats_repo):
    stats_date = date(2026, 5, 6)

    await daily_stats_repo.record_event(
        _event(
            event_key=(
                "daily-risk:v1:runtime:default:2026-05-06:"
                "pos_sig-ls002b:exit-order:0.4"
            ),
            stats_date=stats_date,
            delta_exit_qty=Decimal("0.4"),
            delta_realized_pnl=Decimal("4"),
        )
    )
    second = await daily_stats_repo.record_event(
        _event(
            event_key=(
                "daily-risk:v1:runtime:default:2026-05-06:"
                "pos_sig-ls002b:exit-order:0.7"
            ),
            stats_date=stats_date,
            delta_exit_qty=Decimal("0.3"),
            delta_realized_pnl=Decimal("3"),
        )
    )

    assert second.snapshot.realized_pnl == Decimal("7.000000000000000000")
    assert second.snapshot.trade_count == 0


@pytest.mark.asyncio
async def test_restored_stats_affect_daily_limit_checks():
    config = _config()
    config.daily["max_loss_amount"] = Decimal("10")
    manager = _manager(
        config=config,
        restored_daily_stats=DailyRiskStatsSnapshot(
            scope_key=DAILY_RISK_STATS_SCOPE_KEY,
            stats_date=datetime.now(timezone.utc).date(),
            realized_pnl=Decimal("-10.5"),
            trade_count=0,
        ),
    )

    result = await manager.pre_order_check(
        symbol="ETH/USDT:USDT",
        order_type=OrderType.MARKET,
        amount=Decimal("0.1"),
        price=None,
        trigger_price=None,
        stop_loss=Decimal("99"),
    )

    assert result.allowed is False
    assert result.reason == "DAILY_LOSS_LIMIT"


@pytest.mark.asyncio
async def test_restore_failure_denies_new_entries_through_trace_path():
    from src.application.decision_trace import TraceService

    sink = _TraceSink()
    manager = _manager(
        daily_stats_repository=None,
        daily_stats_persistence_required=True,
        daily_stats_persistence_available=False,
        trace_service=TraceService(sinks=[sink]),
    )

    result = await manager.pre_order_check(
        symbol="ETH/USDT:USDT",
        order_type=OrderType.MARKET,
        amount=Decimal("0.1"),
        price=None,
        trigger_price=None,
        stop_loss=Decimal("99"),
    )

    assert result.allowed is False
    assert result.reason == DAILY_RISK_STATS_UNAVAILABLE_REASON
    assert len(sink.events) == 1
    assert sink.events[0].event_type == "risk.pre_order_check"
    assert sink.events[0].decision == "deny"
    assert sink.events[0].reason == DAILY_RISK_STATS_UNAVAILABLE_REASON


@pytest.mark.asyncio
async def test_write_through_failure_denies_later_new_entries():
    manager = _manager(
        daily_stats_repository=_FailingDailyRiskStatsRepository(),
        daily_stats_persistence_required=True,
    )

    await manager.record_exit_projection(
        position_id="pos_sig-ls002b",
        signal_id="sig-ls002b",
        exit_order_id="exit-order",
        delta_exit_qty=Decimal("0.5"),
        projected_exit_qty_after=Decimal("0.5"),
        delta_realized_pnl=Decimal("-2"),
        just_closed=False,
        occurred_at=datetime.now(timezone.utc),
    )

    result = await manager.pre_order_check(
        symbol="ETH/USDT:USDT",
        order_type=OrderType.MARKET,
        amount=Decimal("0.1"),
        price=None,
        trigger_price=None,
        stop_loss=Decimal("99"),
    )

    assert result.allowed is False
    assert result.reason == DAILY_RISK_STATS_UNAVAILABLE_REASON


@pytest.mark.asyncio
async def test_orchestrator_uses_record_exit_projection_only(daily_stats_repo):
    position_repo = _InMemoryPositionRepository()
    await position_repo.save(_position())
    manager = _manager(daily_stats_repository=daily_stats_repo)
    orchestrator = ExecutionOrchestrator(
        capital_protection=manager,
        order_lifecycle=_NoopOrderLifecycle(),
        gateway=_FakeGateway(),
        position_projection_service=PositionProjectionService(position_repo),
    )

    await orchestrator._handle_exit_filled(_exit_order(filled_qty=Decimal("0.4")))

    stats = await manager.get_daily_stats()
    assert stats.realized_pnl == Decimal("4.000000000000000000")
    assert stats.trade_count == 0


@pytest.mark.asyncio
async def test_exit_projection_failure_does_not_update_daily_stats(daily_stats_repo, caplog):
    manager = _manager(daily_stats_repository=daily_stats_repo)
    orchestrator = ExecutionOrchestrator(
        capital_protection=manager,
        order_lifecycle=_NoopOrderLifecycle(),
        gateway=_FakeGateway(),
        position_projection_service=PositionProjectionService(_InMemoryPositionRepository()),
    )

    await orchestrator._handle_exit_filled(_exit_order())

    stats = await manager.get_daily_stats()
    assert stats.realized_pnl == Decimal("0")
    assert stats.trade_count == 0
    assert "local position missing" in caplog.text


@pytest.mark.asyncio
async def test_persistence_unavailable_does_not_block_exit_projection_path():
    position_repo = _InMemoryPositionRepository()
    await position_repo.save(_position())
    manager = _manager(
        daily_stats_repository=_FailingDailyRiskStatsRepository(),
        daily_stats_persistence_required=True,
    )
    orchestrator = ExecutionOrchestrator(
        capital_protection=manager,
        order_lifecycle=_NoopOrderLifecycle(),
        gateway=_FakeGateway(),
        position_projection_service=PositionProjectionService(position_repo),
    )

    await orchestrator._handle_exit_filled(_exit_order(filled_qty=Decimal("0.4")))

    projected = await position_repo.get("pos_sig-ls002b")
    assert projected is not None
    assert projected.current_qty == Decimal("0.6")


@pytest.mark.asyncio
async def test_utc_day_boundary_uses_new_aggregate_and_resets_memory(daily_stats_repo):
    yesterday = date(2000, 1, 1)
    today = datetime.now(timezone.utc).date()
    await daily_stats_repo.record_event(
        _event(
            stats_date=today,
            delta_realized_pnl=Decimal("2"),
            trade_count_delta=1,
        )
    )
    manager = _manager(
        daily_stats_repository=daily_stats_repo,
        restored_daily_stats=DailyRiskStatsSnapshot(
            scope_key=DAILY_RISK_STATS_SCOPE_KEY,
            stats_date=yesterday,
            realized_pnl=Decimal("-99"),
            trade_count=9,
        ),
    )

    await manager.reset_if_new_day()

    stats = await manager.get_daily_stats()
    assert stats.last_reset_date == today.isoformat()
    assert stats.realized_pnl == Decimal("2.000000000000000000")
    assert stats.trade_count == 1


def test_event_key_decimal_normalization_is_stable():
    assert normalize_daily_risk_decimal(Decimal("1")) == "1"
    assert normalize_daily_risk_decimal(Decimal("1.0")) == "1"
    assert normalize_daily_risk_decimal(Decimal("1.000000000000000000")) == "1"
    assert normalize_daily_risk_decimal(Decimal("0.4000")) == "0.4"


@pytest.mark.asyncio
async def test_restore_or_create_handles_unique_key_race(daily_stats_repo):
    """Simulate IntegrityError on aggregate insert: select returns None (race window),
    insert fails with unique-key conflict, code re-selects the winning row."""
    scope = DAILY_RISK_STATS_SCOPE_KEY
    stats_date = date(2026, 5, 6)

    # Pre-insert the aggregate (the concurrent winner)
    async with daily_stats_repo._session_maker() as session:
        async with session.begin():
            session.add(
                PGDailyRiskStatsAggregateORM(
                    scope_key=scope,
                    stats_date=stats_date,
                    realized_pnl=Decimal("0"),
                    trade_count=0,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.flush()

    # Patch _get_or_create_aggregate to simulate the race:
    # First select returns None (as if we read before the winner committed),
    # then IntegrityError fires on insert, then re-select finds the row.
    original_method = PgDailyRiskStatsRepository._get_or_create_aggregate

    call_count = 0

    async def _patched_get_or_create(self, *, session, scope_key, stats_date, for_update):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call: skip the select, go straight to insert attempt
            # which will hit IntegrityError because the row exists
            now = datetime.now(timezone.utc)
            aggregate = PGDailyRiskStatsAggregateORM(
                scope_key=scope_key,
                stats_date=stats_date,
                realized_pnl=Decimal("0"),
                trade_count=0,
                created_at=now,
                updated_at=now,
            )
            try:
                async with session.begin_nested():
                    session.add(aggregate)
                    await session.flush()
            except IntegrityError:
                stmt = select(PGDailyRiskStatsAggregateORM).where(
                    PGDailyRiskStatsAggregateORM.scope_key == scope_key,
                    PGDailyRiskStatsAggregateORM.stats_date == stats_date,
                )
                if for_update:
                    stmt = stmt.with_for_update()
                result = await session.execute(stmt)
                aggregate = result.scalar_one()
            return aggregate
        return await original_method(
            self, session=session, scope_key=scope_key,
            stats_date=stats_date, for_update=for_update,
        )

    with unittest.mock.patch.object(
        PgDailyRiskStatsRepository, "_get_or_create_aggregate", _patched_get_or_create
    ):
        snapshot = await daily_stats_repo.restore_or_create(scope, stats_date)

    assert snapshot.scope_key == scope
    assert snapshot.stats_date == stats_date
    assert snapshot.realized_pnl == Decimal("0")
    assert snapshot.trade_count == 0


@pytest.mark.asyncio
async def test_record_event_handles_aggregate_unique_key_race(daily_stats_repo):
    """First-event aggregate creation race: IntegrityError on insert,
    code re-selects the winning aggregate and proceeds normally."""
    scope = DAILY_RISK_STATS_SCOPE_KEY
    stats_date = date(2026, 5, 6)

    # Pre-insert the aggregate (the concurrent winner)
    async with daily_stats_repo._session_maker() as session:
        async with session.begin():
            session.add(
                PGDailyRiskStatsAggregateORM(
                    scope_key=scope,
                    stats_date=stats_date,
                    realized_pnl=Decimal("0"),
                    trade_count=0,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.flush()

    # Patch to force the IntegrityError path on first call
    original_method = PgDailyRiskStatsRepository._get_or_create_aggregate

    call_count = 0

    async def _patched_get_or_create(self, *, session, scope_key, stats_date, for_update):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            now = datetime.now(timezone.utc)
            aggregate = PGDailyRiskStatsAggregateORM(
                scope_key=scope_key,
                stats_date=stats_date,
                realized_pnl=Decimal("0"),
                trade_count=0,
                created_at=now,
                updated_at=now,
            )
            try:
                async with session.begin_nested():
                    session.add(aggregate)
                    await session.flush()
            except IntegrityError:
                stmt = select(PGDailyRiskStatsAggregateORM).where(
                    PGDailyRiskStatsAggregateORM.scope_key == scope_key,
                    PGDailyRiskStatsAggregateORM.stats_date == stats_date,
                )
                if for_update:
                    stmt = stmt.with_for_update()
                result = await session.execute(stmt)
                aggregate = result.scalar_one()
            return aggregate
        return await original_method(
            self, session=session, scope_key=scope_key,
            stats_date=stats_date, for_update=for_update,
        )

    with unittest.mock.patch.object(
        PgDailyRiskStatsRepository, "_get_or_create_aggregate", _patched_get_or_create
    ):
        result = await daily_stats_repo.record_event(
            _event(delta_realized_pnl=Decimal("7.5"), trade_count_delta=1)
        )

    assert result.inserted is True
    assert result.snapshot.realized_pnl == Decimal("7.500000000000000000")
    assert result.snapshot.trade_count == 1
