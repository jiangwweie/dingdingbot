from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.trading_kernel.application.market_ports import SelectionKlineRequest
from src.trading_kernel.application.run_instrument_selection import (
    RunInstrumentSelectionRequest,
    run_instrument_selection_once,
)
from src.trading_kernel.domain.instrument_selection import (
    CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS,
    INTERVAL_MS,
    SelectionJobClaim,
    SelectionKline,
    SelectionSourceWindow,
    build_sor_dynamic_selection_period,
    build_sor_dynamic_selection_spec_v0,
    run_sor_dynamic_selection_v0,
)
from src.trading_kernel.infrastructure.pg_instrument_selection_repository import (
    PostgresInstrumentSelectionRepository,
    SelectionJobConflict,
)
from src.trading_kernel.infrastructure.pg_models import (
    instrument_selection_attempts,
    instrument_selection_jobs_current,
    instrument_selection_member_decisions,
    instrument_selection_snapshots,
    instrument_selection_spec_events,
    instrument_selection_spec_members,
    instrument_selection_specs,
    instruments,
    sor_dynamic_selection_specs_v0,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION

SESSION_START_MS = 1_704_067_200_000
SELECTION_SPEC_ID = "sor-dynamic-selection-v0"
ALGORITHM_DIGEST = (
    "sha256:a2c0d5d809a54b90564086f4eab230726a16fdb5524a1ce8f29f48ad659cfb10"
)


@pytest.mark.asyncio
async def test_runner_commits_snapshot_attempt_and_exact_24_members_atomically(
    head_template_engine,
) -> None:
    await _seed_selection_authority(head_template_engine)
    source = _SelectionSource()

    result = await run_instrument_selection_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        market_source=source,
        request=RunInstrumentSelectionRequest(
            selection_spec_id=SELECTION_SPEC_ID,
            session_start_ms=SESSION_START_MS,
            worker_id="selection-worker:integration",
        ),
        clock_ms=_Clock(SESSION_START_MS + 60 * 60 * 1000),
    )

    async with head_template_engine.connect() as connection:
        job = (
            (await connection.execute(sa.select(instrument_selection_jobs_current)))
            .mappings()
            .one()
        )
        attempt = (
            (await connection.execute(sa.select(instrument_selection_attempts)))
            .mappings()
            .one()
        )
        snapshot = (
            (await connection.execute(sa.select(instrument_selection_snapshots)))
            .mappings()
            .one()
        )
        decisions = (
            (
                await connection.execute(
                    sa.select(instrument_selection_member_decisions).order_by(
                        instrument_selection_member_decisions.c.exchange_instrument_id
                    )
                )
            )
            .mappings()
            .all()
        )

    assert result.outcome == "SNAPSHOT_READY"
    assert len(source.calls) == 24
    assert job["state"] == "SNAPSHOT_READY"
    assert attempt["outcome"] == "SNAPSHOT_READY"
    assert attempt["source_member_count"] == 24
    assert snapshot["selection_spec_id"] == SELECTION_SPEC_ID
    assert snapshot["candidate_count"] == 24
    assert snapshot["selected_count"] == 7
    assert len(decisions) == 24
    assert sum(bool(item["selected"]) for item in decisions) == 7
    assert Decimal(decisions[0]["pre_or_width_atr14"]) == Decimal("0.5")

    second = await run_instrument_selection_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        market_source=source,
        request=RunInstrumentSelectionRequest(
            selection_spec_id=SELECTION_SPEC_ID,
            session_start_ms=SESSION_START_MS,
            worker_id="selection-worker:integration:rerun",
        ),
        clock_ms=_Clock(SESSION_START_MS + 2 * 60 * 60 * 1000),
    )

    assert second.outcome == "ALREADY_READY"
    assert second.selection_snapshot_id == result.selection_snapshot_id
    assert len(source.calls) == 24

    period = build_sor_dynamic_selection_period(session_start_ms=SESSION_START_MS)
    spec = build_sor_dynamic_selection_spec_v0(
        selection_spec_id=SELECTION_SPEC_ID,
        strategy_group_id="SOR-001",
        strategy_version_id="sgv:SOR-001:v4",
        event_spec_ids=(
            "event_spec:SOR-001:SOR-LONG:v4",
            "event_spec:SOR-001:SOR-SHORT:v4",
        ),
        candidate_exchange_instrument_ids=(CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS),
        installed_at_ms=SESSION_START_MS,
    )
    replay_windows: list[SelectionSourceWindow] = []
    for instrument_id in CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS:
        replay_windows.append(
            SelectionSourceWindow(
                exchange_instrument_id=instrument_id,
                input_window_start_ms=SESSION_START_MS - 23 * 60 * 60 * 1000,
                feature_cutoff_at_ms=period.feature_cutoff_at_ms,
                klines=await source.fetch_selection_klines(
                    SelectionKlineRequest(
                        exchange_instrument_id=instrument_id,
                        input_window_start_ms=(SESSION_START_MS - 23 * 60 * 60 * 1000),
                        feature_cutoff_at_ms=period.feature_cutoff_at_ms,
                    )
                ),
            )
        )
    windows = tuple(replay_windows)
    computation = run_sor_dynamic_selection_v0(
        spec=spec,
        period=period,
        source_windows=windows,
        decision_at_ms=period.feature_cutoff_at_ms,
        source_observed_at_ms=period.feature_cutoff_at_ms,
        created_at_ms=period.feature_cutoff_at_ms,
    )
    replay_claim = SelectionJobClaim(
        selection_job_id=f"selection-job:{SELECTION_SPEC_ID}:{SESSION_START_MS}",
        selection_spec_id=SELECTION_SPEC_ID,
        session_start_ms=SESSION_START_MS,
        worker_id="selection-worker:replay",
        attempt_number=1,
        projection_version=2,
        started_at_ms=period.feature_cutoff_at_ms,
        lease_expires_at_ms=period.feature_cutoff_at_ms + 1,
    )
    async with head_template_engine.begin() as connection:
        repository = PostgresInstrumentSelectionRepository(connection)
        await repository.complete_selection_snapshot(
            claim=replay_claim,
            computation=computation,
            completed_at_ms=period.feature_cutoff_at_ms,
        )
        with pytest.raises(SelectionJobConflict, match="digest conflicts"):
            await repository.complete_selection_snapshot(
                claim=replay_claim,
                computation=computation.model_copy(
                    update={
                        "snapshot": computation.snapshot.model_copy(
                            update={"selection_semantic_digest": "sha256:" + "f" * 64}
                        )
                    }
                ),
                completed_at_ms=period.feature_cutoff_at_ms,
            )


@pytest.mark.asyncio
async def test_one_missing_candidate_persists_failure_and_zero_snapshot(
    head_template_engine,
) -> None:
    await _seed_selection_authority(head_template_engine)
    failed_id = CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS[-1]
    source = _SelectionSource(failed_id=failed_id)

    result = await run_instrument_selection_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        market_source=source,
        request=RunInstrumentSelectionRequest(
            selection_spec_id=SELECTION_SPEC_ID,
            session_start_ms=SESSION_START_MS,
            worker_id="selection-worker:failure",
        ),
        clock_ms=_Clock(SESSION_START_MS + 60 * 60 * 1000),
    )

    async with head_template_engine.connect() as connection:
        job_state = await connection.scalar(
            sa.select(instrument_selection_jobs_current.c.state)
        )
        attempt = (
            (await connection.execute(sa.select(instrument_selection_attempts)))
            .mappings()
            .one()
        )
        snapshot_count = int(
            await connection.scalar(
                sa.select(sa.func.count()).select_from(instrument_selection_snapshots)
            )
            or 0
        )
        decision_count = int(
            await connection.scalar(
                sa.select(sa.func.count()).select_from(
                    instrument_selection_member_decisions
                )
            )
            or 0
        )

    assert result.outcome == "SOURCE_FAILED"
    assert failed_id in str(result.reason_code)
    assert job_state == "SOURCE_FAILED"
    assert attempt["outcome"] == "SOURCE_FAILED"
    assert attempt["source_member_count"] == 23
    assert snapshot_count == 0
    assert decision_count == 0


async def _seed_selection_authority(engine) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        await seed_runtime_authority(
            uow,
            RuntimeAuthoritySeedRequest(
                account_id="selection-runner-test",
                runtime_commit="selection-runner-test",
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=SESSION_START_MS,
            ),
        )
    async with engine.begin() as connection:
        await connection.execute(
            pg_insert(instruments).on_conflict_do_nothing(),
            [
                {
                    "exchange_instrument_id": instrument_id,
                    "venue_id": "binance-usdm",
                    "asset_class": "crypto",
                    "venue_symbol": instrument_id.split(":")[1],
                    "contract_kind": "perpetual",
                    "status": "pending_certification",
                }
                for instrument_id in CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS
            ],
        )
        await connection.execute(
            sa.insert(instrument_selection_specs).values(
                selection_spec_id=SELECTION_SPEC_ID,
                strategy_group_id="SOR-001",
                strategy_version_id="sgv:SOR-001:v4",
                selection_version=1,
                selection_kind="sor_dynamic_v0",
                algorithm_semantic_digest=ALGORITHM_DIGEST,
                status="active",
                installed_at_ms=SESSION_START_MS,
            )
        )
        await connection.execute(
            sa.insert(sor_dynamic_selection_specs_v0).values(
                selection_spec_id=SELECTION_SPEC_ID,
                decision_offset_utc_seconds=3600,
                feature_cutoff_offset_utc_seconds=3600,
                eligibility_not_before_offset_utc_seconds=4500,
                valid_until_next_decision_offset_seconds=86400,
                candidate_count=24,
                selected_count_max=7,
                near_count_max=7,
                activity_floor_quote_usdt=Decimal(20_000_000),
                materialization_timeout_seconds=1800,
            )
        )
        await connection.execute(
            sa.insert(instrument_selection_spec_events),
            [
                {
                    "selection_spec_id": SELECTION_SPEC_ID,
                    "event_spec_id": "event_spec:SOR-001:SOR-LONG:v4",
                    "position_side": "long",
                },
                {
                    "selection_spec_id": SELECTION_SPEC_ID,
                    "event_spec_id": "event_spec:SOR-001:SOR-SHORT:v4",
                    "position_side": "short",
                },
            ],
        )
        await connection.execute(
            sa.insert(instrument_selection_spec_members),
            [
                {
                    "selection_spec_id": SELECTION_SPEC_ID,
                    "exchange_instrument_id": instrument_id,
                }
                for instrument_id in CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS
            ],
        )


class _Clock:
    def __init__(self, initial_ms: int) -> None:
        self._now_ms = initial_ms

    def __call__(self) -> int:
        self._now_ms += 1
        return self._now_ms


class _SelectionSource:
    def __init__(self, *, failed_id: str | None = None) -> None:
        self._failed_id = failed_id
        self.calls: list[str] = []

    async def fetch_selection_klines(self, request):
        self.calls.append(request.exchange_instrument_id)
        if request.exchange_instrument_id == self._failed_id:
            raise TimeoutError("bounded source timeout")
        instrument_index = CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS.index(
            request.exchange_instrument_id
        )
        width = Decimal(instrument_index + 1)
        result: list[SelectionKline] = []
        for index in range(96):
            open_time_ms = request.input_window_start_ms + index * INTERVAL_MS
            high = Decimal(101)
            low = Decimal(99)
            if index >= 92:
                high = Decimal(100) + width / Decimal(2)
                low = Decimal(100) - width / Decimal(2)
            result.append(
                SelectionKline(
                    open_time_ms=open_time_ms,
                    close_time_ms=open_time_ms + INTERVAL_MS,
                    open=Decimal(100),
                    high=high,
                    low=low,
                    close=Decimal(100),
                    quote_volume=Decimal(300_000),
                )
            )
        return tuple(result)
