from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.trading_kernel.application.run_instrument_selection import (
    RunInstrumentSelectionRequest,
    run_instrument_selection_once,
)
from src.trading_kernel.domain.instrument_selection import (
    CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS,
    INTERVAL_MS,
    SelectionJobClaim,
    SelectionKline,
    SelectionMemberState,
    SelectionSourceIntegrityError,
    SelectionSourceWindow,
    build_sor_dynamic_selection_period,
    build_sor_dynamic_selection_spec_v0,
    run_sor_dynamic_selection_v0,
)

SESSION_START_MS = 1_704_067_200_000
SELECTION_SPEC_ID = "sor-dynamic-selection-v0"


def test_selection_core_produces_exact_24_ranked_decisions_deterministically() -> None:
    spec = _spec()
    period = build_sor_dynamic_selection_period(session_start_ms=SESSION_START_MS)
    windows = tuple(
        _window(instrument_id, width=Decimal(index + 1))
        for index, instrument_id in enumerate(
            CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS
        )
    )

    first = run_sor_dynamic_selection_v0(
        spec=spec,
        period=period,
        source_windows=windows,
        decision_at_ms=period.feature_cutoff_at_ms + 1,
        source_observed_at_ms=period.feature_cutoff_at_ms + 1,
        created_at_ms=period.feature_cutoff_at_ms + 2,
    )
    second = run_sor_dynamic_selection_v0(
        spec=spec,
        period=period,
        source_windows=tuple(reversed(windows)),
        decision_at_ms=period.feature_cutoff_at_ms + 100,
        source_observed_at_ms=period.feature_cutoff_at_ms + 90,
        created_at_ms=period.feature_cutoff_at_ms + 101,
    )

    assert first.snapshot.selection_snapshot_id == (
        "selection:sor-dynamic-selection-v0:1704067200000"
    )
    assert len(first.member_decisions) == 24
    assert first.snapshot.ready_count == 24
    assert first.snapshot.selected_count == 7
    assert [item.stable_rank for item in first.member_decisions if item.selected] == [
        1,
        2,
        3,
        4,
        5,
        6,
        7,
    ]
    assert first.snapshot.selection_semantic_digest == (
        second.snapshot.selection_semantic_digest
    )
    assert [item.member_semantic_digest for item in first.member_decisions] == [
        item.member_semantic_digest for item in second.member_decisions
    ]


def test_selection_source_integrity_failure_prevents_partial_rank() -> None:
    period = build_sor_dynamic_selection_period(session_start_ms=SESSION_START_MS)
    windows = tuple(
        _window(instrument_id, width=Decimal(index + 1))
        for index, instrument_id in enumerate(
            CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS[:-1]
        )
    )

    with pytest.raises(SelectionSourceIntegrityError, match="exact 24"):
        run_sor_dynamic_selection_v0(
            spec=_spec(),
            period=period,
            source_windows=windows,
            decision_at_ms=period.feature_cutoff_at_ms,
            source_observed_at_ms=period.feature_cutoff_at_ms,
            created_at_ms=period.feature_cutoff_at_ms,
        )


def test_selection_source_window_rejects_duplicate_or_open_bar() -> None:
    instrument_id = CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS[0]
    valid = _window(instrument_id, width=Decimal(1))

    with pytest.raises(SelectionSourceIntegrityError, match="continuous"):
        SelectionSourceWindow(
            exchange_instrument_id=instrument_id,
            input_window_start_ms=valid.input_window_start_ms,
            feature_cutoff_at_ms=valid.feature_cutoff_at_ms,
            klines=valid.klines[:-1] + (valid.klines[-2],),
        )

    open_bar = valid.klines[-1].model_copy(
        update={
            "open_time_ms": valid.feature_cutoff_at_ms,
            "close_time_ms": valid.feature_cutoff_at_ms + INTERVAL_MS,
        }
    )
    with pytest.raises(SelectionSourceIntegrityError, match="future or open"):
        SelectionSourceWindow(
            exchange_instrument_id=instrument_id,
            input_window_start_ms=valid.input_window_start_ms,
            feature_cutoff_at_ms=valid.feature_cutoff_at_ms,
            klines=valid.klines[:-1] + (open_bar,),
        )


def test_ready_count_below_cap_selects_only_ready_members() -> None:
    period = build_sor_dynamic_selection_period(session_start_ms=SESSION_START_MS)
    windows = tuple(
        _window(
            instrument_id,
            width=Decimal(index + 1),
            quote_volume=(Decimal(300_000) if index < 5 else Decimal(1)),
        )
        for index, instrument_id in enumerate(
            CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS
        )
    )

    result = run_sor_dynamic_selection_v0(
        spec=_spec(),
        period=period,
        source_windows=windows,
        decision_at_ms=period.feature_cutoff_at_ms,
        source_observed_at_ms=period.feature_cutoff_at_ms,
        created_at_ms=period.feature_cutoff_at_ms,
    )

    assert result.snapshot.ready_count == 5
    assert result.snapshot.selected_count == 5
    assert sum(
        item.member_state is SelectionMemberState.SELECTED
        for item in result.member_decisions
    ) == 5
    assert sum(
        item.member_state is SelectionMemberState.INELIGIBLE
        for item in result.member_decisions
    ) == 19


@pytest.mark.asyncio
async def test_runner_performs_all_network_io_outside_transactions() -> None:
    state = _RunnerState()
    source = _RecordingSelectionSource(state=state)

    result = await run_instrument_selection_once(
        uow_factory=lambda: _FakeUow(state),
        market_source=source,
        request=RunInstrumentSelectionRequest(
            selection_spec_id=SELECTION_SPEC_ID,
            session_start_ms=SESSION_START_MS,
            worker_id="selection-worker:test",
        ),
        clock_ms=_Clock(SESSION_START_MS + 60 * 60 * 1000),
    )

    assert result.outcome == "SNAPSHOT_READY"
    assert result.ready_count == 24
    assert len(source.calls) == 24
    assert source.max_active_reads == 6
    assert state.completed_snapshot is not None
    assert state.failure is None
    assert state.max_active_transactions == 1


@pytest.mark.asyncio
async def test_runner_records_whole_attempt_failure_and_zero_snapshot() -> None:
    state = _RunnerState()
    failed_id = CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS[8]
    source = _RecordingSelectionSource(state=state, failed_id=failed_id)

    result = await run_instrument_selection_once(
        uow_factory=lambda: _FakeUow(state),
        market_source=source,
        request=RunInstrumentSelectionRequest(
            selection_spec_id=SELECTION_SPEC_ID,
            session_start_ms=SESSION_START_MS,
            worker_id="selection-worker:test",
        ),
        clock_ms=_Clock(SESSION_START_MS + 60 * 60 * 1000),
    )

    assert result.outcome == "SOURCE_FAILED"
    assert failed_id in str(result.reason_code)
    assert state.completed_snapshot is None
    assert state.failure is not None
    assert state.failure.source_member_count == 23


def _spec():
    return build_sor_dynamic_selection_spec_v0(
        selection_spec_id=SELECTION_SPEC_ID,
        strategy_group_id="SOR-001",
        strategy_version_id="sgv:SOR-001:v4",
        event_spec_ids=(
            "event_spec:SOR-001:SOR-LONG:v4",
            "event_spec:SOR-001:SOR-SHORT:v4",
        ),
        candidate_exchange_instrument_ids=(
            CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS
        ),
        installed_at_ms=SESSION_START_MS,
    )


def _window(
    exchange_instrument_id: str,
    *,
    width: Decimal,
    quote_volume: Decimal = Decimal(300_000),
) -> SelectionSourceWindow:
    start_ms = SESSION_START_MS - 23 * 60 * 60 * 1000
    bars: list[SelectionKline] = []
    for index in range(96):
        open_time_ms = start_ms + index * INTERVAL_MS
        if index >= 92:
            high = Decimal(100) + width / Decimal(2)
            low = Decimal(100) - width / Decimal(2)
        else:
            high = Decimal(101)
            low = Decimal(99)
        bars.append(
            SelectionKline(
                open_time_ms=open_time_ms,
                close_time_ms=open_time_ms + INTERVAL_MS,
                open=Decimal(100),
                high=high,
                low=low,
                close=Decimal(100),
                quote_volume=quote_volume,
            )
        )
    return SelectionSourceWindow(
        exchange_instrument_id=exchange_instrument_id,
        input_window_start_ms=start_ms,
        feature_cutoff_at_ms=SESSION_START_MS + 60 * 60 * 1000,
        klines=tuple(bars),
    )


class _Clock:
    def __init__(self, initial_ms: int) -> None:
        self._current_ms = initial_ms

    def __call__(self) -> int:
        self._current_ms += 1
        return self._current_ms


class _RunnerState:
    def __init__(self) -> None:
        self.active_transactions = 0
        self.max_active_transactions = 0
        self.completed_snapshot = None
        self.failure = None


class _FakeUow:
    def __init__(self, state: _RunnerState) -> None:
        self._state = state
        self.instrument_selection = _FakeSelectionRepository(state)

    async def __aenter__(self):
        self._state.active_transactions += 1
        self._state.max_active_transactions = max(
            self._state.max_active_transactions,
            self._state.active_transactions,
        )
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        self._state.active_transactions -= 1


class _FakeSelectionRepository:
    def __init__(self, state: _RunnerState) -> None:
        self._state = state

    async def get_active_spec(self, selection_spec_id: str):
        assert selection_spec_id == SELECTION_SPEC_ID
        return _spec()

    async def claim_selection_job(self, **kwargs):
        assert self._state.active_transactions == 1
        return SelectionJobClaim(
            selection_job_id=(
                f"selection-job:{SELECTION_SPEC_ID}:{SESSION_START_MS}"
            ),
            selection_spec_id=SELECTION_SPEC_ID,
            session_start_ms=SESSION_START_MS,
            worker_id=kwargs["worker_id"],
            attempt_number=1,
            projection_version=2,
            started_at_ms=kwargs["now_ms"],
            lease_expires_at_ms=(
                kwargs["now_ms"] + kwargs["lease_duration_ms"]
            ),
        )

    async def complete_selection_snapshot(self, **kwargs) -> None:
        assert self._state.active_transactions == 1
        self._state.completed_snapshot = kwargs["computation"]

    async def complete_selection_failure(self, **kwargs) -> None:
        assert self._state.active_transactions == 1
        self._state.failure = SimpleNamespace(**kwargs)


class _RecordingSelectionSource:
    def __init__(
        self,
        *,
        state: _RunnerState,
        failed_id: str | None = None,
    ) -> None:
        self._state = state
        self._failed_id = failed_id
        self.calls: list[str] = []
        self.active_reads = 0
        self.max_active_reads = 0

    async def fetch_selection_klines(self, request):
        assert self._state.active_transactions == 0
        self.calls.append(request.exchange_instrument_id)
        self.active_reads += 1
        self.max_active_reads = max(self.max_active_reads, self.active_reads)
        try:
            await asyncio.sleep(0.001)
            if request.exchange_instrument_id == self._failed_id:
                raise TimeoutError("bounded source timeout")
            return _window(
                request.exchange_instrument_id,
                width=Decimal(
                    CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS.index(
                        request.exchange_instrument_id
                    )
                    + 1
                ),
            ).klines
        finally:
            self.active_reads -= 1
