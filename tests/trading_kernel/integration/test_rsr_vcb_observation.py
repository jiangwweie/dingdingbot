from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.application.activate_strategy_universe import (
    ActivateStrategyUniverseRequest,
    activate_strategy_universe,
)
from src.trading_kernel.application.market_ports import (
    ClosedCandlePage,
    ClosedCandlePageRequest,
)
from src.trading_kernel.application.project_strategy_universe import (
    project_strategy_universe,
)
from src.trading_kernel.application.observe_strategy_scope import (
    ObservationRequest,
    ObservationStatus,
    observe_strategy_scope,
)
from src.trading_kernel.application.observe_ranked_strategy_scope import (
    prepare_ranked_strategy_snapshot,
)
from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.domain.strategy_universe import universe_for_event_spec
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.pg_models import (
    runtime_capabilities_current,
    runtime_scopes_current,
    scope_warm_readiness,
    universe_projection_leases,
)
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    seed_strategy_registry,
)
from src.trading_kernel.infrastructure.strategy_universe_seed import (
    seed_strategy_universes,
)
from tests.trading_kernel.integration.test_strategy_registry_seed import (
    registry_engine,  # noqa: F401
)


EVENT_SPEC_ID = "event_spec:RSRVCB-001:RSRVCB-LONG-15M:v1"


class WindowSource:
    def __init__(
        self,
        windows: dict[tuple[str, str], tuple[ClosedCandle, ...]],
    ) -> None:
        self.windows = windows
        self.calls: list[ClosedCandlePageRequest] = []

    async def fetch_closed_candle_page(
        self,
        request: ClosedCandlePageRequest,
    ) -> ClosedCandlePage:
        self.calls.append(request)
        candles = tuple(
            item
            for item in self.windows[
                (request.exchange_instrument_id, request.timeframe)
            ]
            if item.close_time_ms <= request.before_close_time_ms
        )[-request.page_limit :]
        duration = {
            "15m": 900_000,
            "1h": 3_600_000,
            "4h": 14_400_000,
        }[request.timeframe]
        return ClosedCandlePage(
            exchange_instrument_id=request.exchange_instrument_id,
            timeframe=request.timeframe,
            candles=candles,
            next_before_close_time_ms=(
                None if not candles else candles[0].close_time_ms - duration
            ),
        )


@pytest.mark.asyncio
async def test_projection_is_persisted_once_and_replayed_without_market_io(
    registry_engine: AsyncEngine,  # noqa: F811
) -> None:
    universe = universe_for_event_spec(EVENT_SPEC_ID)
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1_800_000_000_000)
        await seed_strategy_universes(uow, seeded_at_ms=1_800_000_000_000)
    start_1h = 1_700_000_000_000
    start_1h -= start_1h % 3_600_000
    trigger_ms = start_1h + 744 * 3_600_000
    as_of_4h = trigger_ms - trigger_ms % 14_400_000
    start_4h = as_of_4h - 200 * 14_400_000
    windows: dict[tuple[str, str], tuple[ClosedCandle, ...]] = {}
    for index, member in enumerate(universe.members):
        slope = (
            Decimal(index + 2) / Decimal("1000")
            if member in universe.candidate_members
            else Decimal("0.0005")
        )
        windows[(member.exchange_instrument_id, "1h")] = _candles(
            start_ms=start_1h,
            count=744,
            duration_ms=3_600_000,
            slope=slope,
        )
    for member in universe.reference_members:
        windows[(member.exchange_instrument_id, "4h")] = _candles(
            start_ms=start_4h,
            count=200,
            duration_ms=14_400_000,
            slope=Decimal("0.01"),
        )
    source = WindowSource(windows)

    first = await project_strategy_universe(
        lambda: PostgresKernelUnitOfWork(registry_engine),
        source,
        universe_version_id=universe.universe_version_id,
        trigger_time_ms=trigger_ms,
    )
    first_call_count = len(source.calls)
    second = await project_strategy_universe(
        lambda: PostgresKernelUnitOfWork(registry_engine),
        source,
        universe_version_id=universe.universe_version_id,
        trigger_time_ms=trigger_ms,
    )

    assert first == second
    assert first.regime_eligible is True
    assert len(first.members) == 13
    assert len(first.top_two) == 2
    assert first_call_count > 15
    assert len(source.calls) == first_call_count

    async with registry_engine.connect() as connection:
        claim = (
            await connection.execute(
                sa.select(universe_projection_leases)
            )
        ).mappings().one()
    assert claim["claim_status"] == "completed"
    assert claim["claim_owner"] is None


@pytest.mark.asyncio
async def test_projection_failure_is_audited_and_retry_reclaims_lease(
    registry_engine: AsyncEngine,  # noqa: F811
) -> None:
    universe = universe_for_event_spec(EVENT_SPEC_ID)
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1_800_000_000_000)
        await seed_strategy_universes(uow, seeded_at_ms=1_800_000_000_000)
    trigger_ms, windows = _projection_windows(universe)
    missing = dict(windows)
    missing.pop((universe.candidate_members[0].exchange_instrument_id, "1h"))

    with pytest.raises(KeyError):
        await project_strategy_universe(
            lambda: PostgresKernelUnitOfWork(registry_engine),
            WindowSource(missing),
            universe_version_id=universe.universe_version_id,
            trigger_time_ms=trigger_ms,
            claim_owner="worker-crashed",
        )
    async with registry_engine.connect() as connection:
        failed = (
            await connection.execute(sa.select(universe_projection_leases))
        ).mappings().one()
    assert failed["claim_status"] == "failed"
    assert failed["failure_reason"] == "KeyError"

    retried = await project_strategy_universe(
        lambda: PostgresKernelUnitOfWork(registry_engine),
        WindowSource(windows),
        universe_version_id=universe.universe_version_id,
        trigger_time_ms=trigger_ms + 1,
        claim_owner="worker-retry",
    )
    assert retried.as_of_close_time_ms == trigger_ms


@pytest.mark.asyncio
async def test_full_ranked_observation_persists_lineage_duplicate_and_cooldown(
    registry_engine: AsyncEngine,  # noqa: F811
) -> None:
    universe = universe_for_event_spec(EVENT_SPEC_ID)
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1_800_000_000_000)
        await seed_strategy_universes(uow, seeded_at_ms=1_800_000_000_000)
    trigger_hour_ms, windows = _projection_windows(
        universe,
        compressed_top=True,
    )
    await _activate_rsr_universe(
        registry_engine,
        universe=universe,
        activated_at_ms=trigger_hour_ms - 1,
    )
    top_instrument = universe.candidate_members[-1].exchange_instrument_id
    hourly = windows[(top_instrument, "1h")]
    boundary = max(candle.high for candle in hourly[-73:-1])
    first_trigger_ms = trigger_hour_ms + 900_000
    trigger_candles = _trigger_window(
        armed_at_ms=trigger_hour_ms,
        boundary=boundary,
    )
    windows[(top_instrument, "15m")] = trigger_candles
    source = WindowSource(windows)
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        scope = await uow.signals.get_runtime_scope(
            f"scope-rsr:{top_instrument}"
        )
    assert scope is not None
    prepared = await prepare_ranked_strategy_snapshot(
        lambda: PostgresKernelUnitOfWork(registry_engine),
        source,
        scope=scope,
        trigger_close_time_ms=first_trigger_ms,
    )
    assert prepared is not None
    request = ObservationRequest(
        runtime_scope_id=f"scope-rsr:{top_instrument}",
        runtime_commit="kernel-test-head",
        schema_revision="0002_strategy_universe_us_equity",
        trigger_candle_close_time_ms=first_trigger_ms,
    )

    first = await observe_strategy_scope(
        lambda: PostgresKernelUnitOfWork(registry_engine),
        source,
        request,
    )
    replay = await observe_strategy_scope(
        lambda: PostgresKernelUnitOfWork(registry_engine),
        source,
        request,
    )

    assert first.status is ObservationStatus.SIGNAL_CREATED
    assert replay.status is ObservationStatus.DUPLICATE_SIGNAL
    assert first.signal_event_id == replay.signal_event_id
    assert first.signal_event_id is not None
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        signal = await uow.signals.get(first.signal_event_id)
    assert signal is not None
    assert signal.universe_version_id == universe.universe_version_id
    assert signal.universe_digest == universe.semantic_digest()
    assert signal.projection_run_id is not None
    assert signal.armed_structure_id is not None

    second_trigger_ms = trigger_hour_ms + 2_700_000
    windows[(top_instrument, "15m")] = (
        *trigger_candles,
        _candle(
            open_time_ms=first_trigger_ms,
            duration_ms=900_000,
            open_price=boundary - Decimal("0.3"),
            close_price=boundary - Decimal("0.2"),
            quote_volume=Decimal("100"),
        ),
        _candle(
            open_time_ms=first_trigger_ms + 900_000,
            duration_ms=900_000,
            open_price=boundary - Decimal("0.2"),
            close_price=boundary + Decimal("1"),
            quote_volume=Decimal("200"),
        ),
    )
    cooldown = await observe_strategy_scope(
        lambda: PostgresKernelUnitOfWork(registry_engine),
        source,
        request.model_copy(
            update={"trigger_candle_close_time_ms": second_trigger_ms}
        ),
    )
    assert cooldown.status is ObservationStatus.NO_SIGNAL
    assert cooldown.detector_reason == "rsr_vcb_cooldown"


def _candles(
    *,
    start_ms: int,
    count: int,
    duration_ms: int,
    slope: Decimal,
) -> tuple[ClosedCandle, ...]:
    return tuple(
        ClosedCandle(
            open_time_ms=start_ms + index * duration_ms,
            close_time_ms=start_ms + (index + 1) * duration_ms,
            open=Decimal("100") + slope * Decimal(index) - Decimal("0.01"),
            high=Decimal("100") + slope * Decimal(index) + Decimal("0.1"),
            low=Decimal("100") + slope * Decimal(index) - Decimal("0.1"),
            close=Decimal("100") + slope * Decimal(index),
            volume=Decimal("10"),
            quote_volume=(
                Decimal("100")
                if index < count - 24
                else Decimal("120")
            ),
        )
        for index in range(count)
    )


def _projection_windows(
    universe,
    *,
    compressed_top: bool = False,
) -> tuple[int, dict[tuple[str, str], tuple[ClosedCandle, ...]]]:
    start_1h = 1_700_000_000_000
    start_1h -= start_1h % 3_600_000
    trigger_ms = start_1h + 744 * 3_600_000
    as_of_4h = trigger_ms - trigger_ms % 14_400_000
    start_4h = as_of_4h - 200 * 14_400_000
    windows: dict[tuple[str, str], tuple[ClosedCandle, ...]] = {}
    for index, member in enumerate(universe.members):
        slope = (
            Decimal(index + 2) / Decimal("1000")
            if member in universe.candidate_members
            else Decimal("0.0005")
        )
        candles = _candles(
            start_ms=start_1h,
            count=744,
            duration_ms=3_600_000,
            slope=slope,
        )
        if compressed_top and member == universe.candidate_members[-1]:
            candles = _compressed_projection_candles(
                start_ms=start_1h,
                count=744,
            )
        windows[(member.exchange_instrument_id, "1h")] = candles
    for member in universe.reference_members:
        windows[(member.exchange_instrument_id, "4h")] = _candles(
            start_ms=start_4h,
            count=200,
            duration_ms=14_400_000,
            slope=Decimal("0.01"),
        )
    return trigger_ms, windows


def _compressed_projection_candles(
    *,
    start_ms: int,
    count: int,
) -> tuple[ClosedCandle, ...]:
    candles: list[ClosedCandle] = []
    for index in range(count):
        local_index = index - (count - 260)
        if local_index < 0:
            close = Decimal("70") + Decimal(index) * Decimal("0.05")
        elif local_index < 240:
            close = (
                Decimal("100")
                + Decimal(local_index) * Decimal("0.2")
                + (Decimal("4") if local_index % 2 == 0 else Decimal("-4"))
            )
        else:
            close = Decimal("152") + Decimal(local_index - 240) * Decimal("0.02")
        candles.append(
            _candle(
                open_time_ms=start_ms + index * 3_600_000,
                duration_ms=3_600_000,
                open_price=close - Decimal("0.05"),
                close_price=close,
                quote_volume=(
                    Decimal("120")
                    if index >= count - 24
                    else Decimal("100")
                ),
            )
        )
    return tuple(candles)


def _trigger_window(
    *,
    armed_at_ms: int,
    boundary: Decimal,
) -> tuple[ClosedCandle, ...]:
    count = 120
    start_ms = armed_at_ms - (count - 1) * 900_000
    return tuple(
        _candle(
            open_time_ms=start_ms + index * 900_000,
            duration_ms=900_000,
            open_price=(
                boundary - Decimal("0.2")
                if index == count - 1
                else boundary - Decimal("0.6")
            ),
            close_price=(
                boundary + Decimal("1")
                if index == count - 1
                else boundary - Decimal("0.4")
            ),
            quote_volume=(
                Decimal("200")
                if index == count - 1
                else Decimal("100")
            ),
        )
        for index in range(count)
    )


def _candle(
    *,
    open_time_ms: int,
    duration_ms: int,
    open_price: Decimal,
    close_price: Decimal,
    quote_volume: Decimal,
) -> ClosedCandle:
    return ClosedCandle(
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + duration_ms,
        open=open_price,
        high=max(open_price, close_price) + Decimal("0.5"),
        low=min(open_price, close_price) - Decimal("0.5"),
        close=close_price,
        volume=Decimal("10"),
        quote_volume=quote_volume,
    )


async def _activate_rsr_universe(
    engine: AsyncEngine,
    *,
    universe,
    activated_at_ms: int,
) -> None:
    async with engine.begin() as connection:
        for member in universe.candidate_members:
            runtime_scope_id = f"scope-rsr:{member.exchange_instrument_id}"
            await connection.execute(
                sa.insert(runtime_scopes_current).values(
                    runtime_scope_id=runtime_scope_id,
                    strategy_group_id=universe.strategy_group_id,
                    strategy_version_id="sgv:RSRVCB-001:v1",
                    event_spec_id=universe.event_spec_id,
                    runtime_profile_id="profile-rsr-test",
                    owner_policy_id="policy-rsr-test",
                    exchange_instrument_id=member.exchange_instrument_id,
                    position_side="long",
                    enabled=True,
                    universe_version_id=universe.universe_version_id,
                    observation_enabled=True,
                    entry_enabled=False,
                    scope_state="warming",
                    warm_ready_at_ms=activated_at_ms - 1,
                    scope_version=1,
                    updated_at_ms=activated_at_ms - 1,
                )
            )
            await connection.execute(
                sa.insert(scope_warm_readiness).values(
                    runtime_scope_id=runtime_scope_id,
                    universe_version_id=universe.universe_version_id,
                    observation_fact_digest="sha256:" + "1" * 64,
                    product_profile_id="profile:rsr-observation-test",
                    product_profile_digest="sha256:" + "2" * 64,
                    projection_run_id="projection:rsr-observation-test",
                    readiness_digest="sha256:" + "3" * 64,
                    ready_at_ms=activated_at_ms - 1,
                )
            )
        await connection.execute(
            sa.insert(runtime_capabilities_current).values(
                capability_key="strategy_signal_ingest",
                enabled=True,
                certified_commit="kernel-test-head",
                schema_revision="0002_strategy_universe_us_equity",
                certification={},
                updated_at_ms=activated_at_ms - 1,
            )
        )
    async with PostgresKernelUnitOfWork(engine) as uow:
        await activate_strategy_universe(
            uow,
            ActivateStrategyUniverseRequest(
                event_spec_id=universe.event_spec_id,
                universe_version_id=universe.universe_version_id,
                activated_at_ms=activated_at_ms,
            ),
        )
