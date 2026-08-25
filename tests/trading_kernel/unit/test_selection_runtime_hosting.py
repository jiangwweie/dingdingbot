from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.trading_kernel.application.coordinate_selection_materialization import (
    AuthorityGapAuditEvaluationRequest,
    AuthorityGapAuditSourceIntegrityError,
)
from src.trading_kernel.application.runtime import (
    observation_process_component_map,
)
from src.trading_kernel.domain.instrument_selection import (
    INTERVAL_MS,
    SOR_LONG_EVENT_SPEC_ID,
    SOR_SHORT_EVENT_SPEC_ID,
)
from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.domain.selection_authority import (
    AuthorityGapAuditKind,
    AuthorityGapScope,
    AuthorityOutcome,
    MaterializationGeneration,
    MaterializationGenerationClaimStatus,
    MaterializationGenerationLeaseClaim,
    MaterializationGenerationState,
    SelectionControl,
    SelectionMode,
    build_pending_authority_gap_audit,
)
from src.trading_kernel.interfaces.authority_gap_audit_source import (
    PublicMarketAuthorityGapAuditSource,
)
from src.trading_kernel.interfaces.readonly_api import (
    SelectionRuntimeReadonlyRequest,
    get_selection_runtime_view,
)
from src.trading_kernel.interfaces.selection_runtime_worker import (
    MaterializationRuntimeStatus,
    SelectionRuntimeRequest,
    SelectionRuntimeStatus,
    current_sor_selection_session_start_ms,
    run_materialization_runtime_once,
    run_selection_runtime_once,
)
from src.trading_kernel.interfaces.worker_process import (
    WorkerProcessLoop,
    run_worker_process_group,
)


def test_observation_process_exposes_three_distinct_logical_component_identities() -> None:
    assert observation_process_component_map() == {
        "selection": "selection_runner",
        "materialization": "materialization_coordinator",
        "observation": "observation_runner",
    }
    assert len(set(observation_process_component_map().values())) == 3


def test_selection_period_is_not_due_before_the_0100_decision_boundary() -> None:
    session_start_ms = 1_800_057_600_000

    assert (
        current_sor_selection_session_start_ms(session_start_ms + 3_599_999)
        is None
    )


@pytest.mark.asyncio
async def test_static_selection_runtime_without_pending_activation_creates_no_job_or_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_start_ms = 1_800_057_600_000
    repository = _SelectionControlRepository(_selection_control())

    async def forbidden_selection(**_kwargs):
        raise AssertionError("Static baseline must not run Selection")

    monkeypatch.setattr(
        "src.trading_kernel.interfaces.selection_runtime_worker."
        "run_instrument_selection_once",
        forbidden_selection,
    )
    result = await run_selection_runtime_once(
        uow_factory=lambda: _SelectionControlUow(repository),
        market_source=SimpleNamespace(),
        request=SelectionRuntimeRequest(
            selection_spec_id="sor-dynamic-selection-v0",
            strategy_group_id="SOR-001",
            worker_id="selection:test",
            now_ms=session_start_ms + 3_600_000,
        ),
        clock_ms=lambda: session_start_ms + 3_600_000,
    )

    assert result.status is SelectionRuntimeStatus.NOT_DUE
    assert result.reason_code == "STATIC_BASELINE_NO_PENDING_DYNAMIC"
    assert repository.calls == [("SOR-001",)]


@pytest.mark.asyncio
async def test_pending_dynamic_selection_runtime_runs_only_for_its_exact_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_start_ms = 1_800_057_600_000
    control = _selection_control().model_copy(
        update={
            "pending_selection_mode": SelectionMode.DYNAMIC_SELECTION,
            "pending_effective_session_start_ms": session_start_ms,
            "pending_authorization_id": "owner-authorization:selection:test",
        }
    )
    repository = _SelectionControlRepository(control)
    calls: list[object] = []

    async def selection(**kwargs):
        calls.append(kwargs["request"])
        return SimpleNamespace(
            outcome="SNAPSHOT_READY",
            selection_job_id="selection-job:test",
            selection_snapshot_id="selection:test",
            reason_code=None,
        )

    monkeypatch.setattr(
        "src.trading_kernel.interfaces.selection_runtime_worker."
        "run_instrument_selection_once",
        selection,
    )
    result = await run_selection_runtime_once(
        uow_factory=lambda: _SelectionControlUow(repository),
        market_source=SimpleNamespace(),
        request=SelectionRuntimeRequest(
            selection_spec_id="sor-dynamic-selection-v0",
            strategy_group_id="SOR-001",
            worker_id="selection:test",
            now_ms=session_start_ms + 3_600_000,
        ),
        clock_ms=lambda: session_start_ms + 3_600_000,
    )

    assert result.status is SelectionRuntimeStatus.SNAPSHOT_READY
    assert result.selection_snapshot_id == "selection:test"
    assert len(calls) == 1
    assert (
        current_sor_selection_session_start_ms(session_start_ms + 3_600_000)
        == session_start_ms
    )


@pytest.mark.asyncio
async def test_shared_os_process_runs_component_loops_independently() -> None:
    materialization_ran = asyncio.Event()
    selection_finished = asyncio.Event()
    calls: list[str] = []

    async def selection_tick() -> _Result:
        calls.append("selection_started")
        await materialization_ran.wait()
        calls.append("selection_finished")
        selection_finished.set()
        return _Result("selection_idle")

    async def materialization_tick() -> _Result:
        calls.append("materialization_ran")
        materialization_ran.set()
        return _Result("materialization_idle")

    async def observation_tick() -> _Result:
        calls.append("observation_ran")
        return _Result("observation_idle")

    await run_worker_process_group(
        (
            WorkerProcessLoop(
                component_id="selection_runner",
                tick=selection_tick,
                poll_interval_ms=5_000,
                idle_statuses=frozenset({"selection_idle"}),
            ),
            WorkerProcessLoop(
                component_id="materialization_coordinator",
                tick=materialization_tick,
                poll_interval_ms=2_000,
                idle_statuses=frozenset({"materialization_idle"}),
            ),
            WorkerProcessLoop(
                component_id="observation_runner",
                tick=observation_tick,
                poll_interval_ms=5_000,
                idle_statuses=frozenset({"observation_idle"}),
            ),
        ),
        run_forever=False,
        idle_log_interval_ms=300_000,
        emit=lambda _value: None,
    )

    assert selection_finished.is_set()
    assert calls.index("materialization_ran") < calls.index("selection_finished")
    assert "observation_ran" in calls


@pytest.mark.asyncio
async def test_public_gap_audit_replays_one_exact_path_for_both_sor_sides() -> None:
    session_start_ms = 1_800_057_600_000
    instrument_id = "binance-usdm:BTCUSDT:perpetual"
    source = _GapMarketSource(
        _sor_candles(
            session_start_ms,
            closes=("100", "100", "100", "100", "100", "102"),
        )
    )
    audit_source = PublicMarketAuthorityGapAuditSource(source, max_concurrency=2)
    request = AuthorityGapAuditEvaluationRequest(
        audit=build_pending_authority_gap_audit(
            authority_gap_audit_id="gap-audit:test",
            selection_spec_id="sor-dynamic-selection-v0",
            session_start_ms=session_start_ms,
            gap_kind=AuthorityGapAuditKind.LATE_PRE_FENCE_CONTINUITY,
            proposed_authority_outcome=AuthorityOutcome.PRE_FENCE_CONTINUITY,
            unauthorized_from_close_time_ms=session_start_ms + 5 * INTERVAL_MS,
            detector_semantic_digest=f"sha256:{'a' * 64}",
            created_at_ms=session_start_ms + 6 * INTERVAL_MS,
        ),
        scopes=(
            AuthorityGapScope(
                event_spec_id=SOR_LONG_EVENT_SPEC_ID,
                exchange_instrument_id=instrument_id,
            ),
            AuthorityGapScope(
                event_spec_id=SOR_SHORT_EVENT_SPEC_ID,
                exchange_instrument_id=instrument_id,
            ),
        ),
        audited_through_close_time_ms=session_start_ms + 6 * INTERVAL_MS,
    )

    results = await audit_source.evaluate_authority_gap(request)

    assert source.calls == [
        (
            instrument_id,
            session_start_ms,
            session_start_ms + 6 * INTERVAL_MS,
            6,
        )
    ]
    by_event = {item.scope.event_spec_id: item for item in results}
    assert (
        by_event[SOR_LONG_EVENT_SPEC_ID].first_natural_trigger_at_ms
        == session_start_ms + 6 * INTERVAL_MS
    )
    assert by_event[SOR_SHORT_EVENT_SPEC_ID].first_natural_trigger_at_ms is None
    assert {item.session_reference for item in results} == {str(session_start_ms)}


@pytest.mark.asyncio
async def test_public_gap_audit_rejects_an_incomplete_session_path() -> None:
    session_start_ms = 1_800_057_600_000
    source = _GapMarketSource(
        _sor_candles(
            session_start_ms,
            closes=("100", "100", "100", "100", "102"),
        )
    )
    audit_source = PublicMarketAuthorityGapAuditSource(source)
    request = AuthorityGapAuditEvaluationRequest(
        audit=build_pending_authority_gap_audit(
            authority_gap_audit_id="gap-audit:test-incomplete",
            selection_spec_id="sor-dynamic-selection-v0",
            session_start_ms=session_start_ms,
            gap_kind=AuthorityGapAuditKind.LATE_PRE_FENCE_CONTINUITY,
            proposed_authority_outcome=AuthorityOutcome.PRE_FENCE_CONTINUITY,
            unauthorized_from_close_time_ms=session_start_ms + 5 * INTERVAL_MS,
            detector_semantic_digest=f"sha256:{'a' * 64}",
            created_at_ms=session_start_ms + 6 * INTERVAL_MS,
        ),
        scopes=(
            AuthorityGapScope(
                event_spec_id=SOR_LONG_EVENT_SPEC_ID,
                exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            ),
        ),
        audited_through_close_time_ms=session_start_ms + 6 * INTERVAL_MS,
    )

    with pytest.raises(RuntimeError, match="complete canonical 15m path"):
        await audit_source.evaluate_authority_gap(request)


@pytest.mark.asyncio
@pytest.mark.parametrize("path_kind", ("duplicate", "future"))
async def test_public_gap_audit_rejects_duplicate_or_future_session_bar(
    path_kind: str,
) -> None:
    session_start_ms = 1_800_057_600_000
    canonical = _sor_candles(
        session_start_ms,
        closes=("100", "100", "100", "100", "100", "102"),
    )
    if path_kind == "duplicate":
        malformed = canonical[:4] + (canonical[3],) + canonical[5:]
    else:
        malformed = canonical[:-1] + (
            canonical[-1].model_copy(
                update={
                    "open_time_ms": canonical[-1].open_time_ms + INTERVAL_MS,
                    "close_time_ms": canonical[-1].close_time_ms + INTERVAL_MS,
                }
            ),
        )
    request = AuthorityGapAuditEvaluationRequest(
        audit=build_pending_authority_gap_audit(
            authority_gap_audit_id=f"gap-audit:test-{path_kind}",
            selection_spec_id="sor-dynamic-selection-v0",
            session_start_ms=session_start_ms,
            gap_kind=AuthorityGapAuditKind.LATE_PRE_FENCE_CONTINUITY,
            proposed_authority_outcome=AuthorityOutcome.PRE_FENCE_CONTINUITY,
            unauthorized_from_close_time_ms=session_start_ms + 5 * INTERVAL_MS,
            detector_semantic_digest=f"sha256:{'a' * 64}",
            created_at_ms=session_start_ms + 6 * INTERVAL_MS,
        ),
        scopes=(
            AuthorityGapScope(
                event_spec_id=SOR_LONG_EVENT_SPEC_ID,
                exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            ),
        ),
        audited_through_close_time_ms=session_start_ms + 6 * INTERVAL_MS,
    )

    with pytest.raises(
        AuthorityGapAuditSourceIntegrityError,
        match="complete canonical 15m path",
    ):
        await PublicMarketAuthorityGapAuditSource(
            _GapMarketSource(malformed)
        ).evaluate_authority_gap(request)


@pytest.mark.asyncio
async def test_materialization_runtime_does_not_advance_a_generation_with_another_live_lease() -> None:
    session_start_ms = 1_800_057_600_000
    generation = MaterializationGeneration(
        materialization_generation_id="generation:leased",
        selection_spec_id="sor-dynamic-selection-v0",
        strategy_group_id="SOR-001",
        strategy_version_id="sgv:SOR-001:v4",
        selection_mode=SelectionMode.DYNAMIC_SELECTION,
        selection_snapshot_id="selection:sor-dynamic-selection-v0:1800057600000",
        rollback_baseline_id=None,
        session_start_ms=session_start_ms,
        previous_long_universe_version_id="universe:long:previous",
        previous_short_universe_version_id="universe:short:previous",
        desired_member_count=2,
        semantic_digest=f"sha256:{'b' * 64}",
        lifecycle_state=MaterializationGenerationState.PENDING,
        fallback_reason_code=None,
        projection_version=1,
        created_at_ms=session_start_ms + 3_600_001,
        desired_at_ms=None,
    )
    repository = _MaterializationLeaseRepository(
        MaterializationGenerationLeaseClaim(
            status=MaterializationGenerationClaimStatus.LEASE_HELD,
            generation=generation,
            lease_owner="materializer:other",
            lease_expires_at_ms=session_start_ms + 3_700_000,
        )
    )

    result = await run_materialization_runtime_once(
        uow_factory=lambda: _MaterializationLeaseUow(repository),
        audit_source=_UnusedAuditSource(),
        request=SelectionRuntimeRequest(
            selection_spec_id="sor-dynamic-selection-v0",
            strategy_group_id="SOR-001",
            worker_id="materializer:this",
            now_ms=session_start_ms + 3_600_100,
        ),
        clock_ms=lambda: session_start_ms + 3_600_100,
    )

    assert result.status is MaterializationRuntimeStatus.WAITING
    assert result.reason_code == "MATERIALIZATION_LEASE_HELD"
    assert repository.releases == []


@pytest.mark.asyncio
async def test_selection_runtime_readonly_uses_only_exact_bounded_keys() -> None:
    repository = _ReadonlySelectionRepository()

    result = await get_selection_runtime_view(
        _ReadonlySelectionUow(repository),
        SelectionRuntimeReadonlyRequest(
            strategy_group_id="SOR-001",
            selection_spec_id="sor-dynamic-selection-v0",
            session_start_ms=1_800_057_600_000,
            release_compatibility_id="release-compatibility:source:target",
        ),
    )

    assert result.strategy_group_id == "SOR-001"
    assert result.selection_spec_id == "sor-dynamic-selection-v0"
    assert result.session_start_ms == 1_800_057_600_000
    assert result.selection_control is None
    assert result.selection_job is None
    assert result.snapshot_disposition is None
    assert result.materialization_generation is None
    assert result.entry_vacuums == ()
    assert result.authority_gap_audits == ()
    assert result.current_authority is None
    assert result.first_eligible_close_time_ms is None
    assert result.release_compatibility_fact is None
    assert repository.calls == [
        ("control", "SOR-001"),
        (
            "job",
            "sor-dynamic-selection-v0",
            1_800_057_600_000,
        ),
        (
            "snapshot",
            "sor-dynamic-selection-v0",
            1_800_057_600_000,
        ),
        (
            "generation",
            "SOR-001",
            "sor-dynamic-selection-v0",
            1_800_057_600_000,
        ),
        (
            "vacuums",
            "SOR-001",
            "sor-dynamic-selection-v0",
            1_800_057_600_000,
            8,
        ),
        (
            "audits",
            "sor-dynamic-selection-v0",
            1_800_057_600_000,
            8,
        ),
        ("authority", "sor-dynamic-selection-v0"),
        (
            "release",
            "release-compatibility:source:target",
        ),
    ]


class _Result:
    def __init__(self, status: str) -> None:
        self.status = status

    def model_dump(self, *, mode: str) -> dict[str, str]:
        assert mode == "json"
        return {"status": self.status}


class _GapMarketSource:
    def __init__(self, candles: tuple[ClosedCandle, ...]) -> None:
        self._candles = candles
        self.calls: list[tuple[str, int | None, int, int]] = []

    async def fetch_closed_candles(self, request):
        self.calls.append(
            (
                request.exchange_instrument_id,
                request.since_ms,
                request.closed_at_ms,
                request.limit,
            )
        )
        return self._candles


def _sor_candles(
    session_start_ms: int,
    *,
    closes: tuple[str, ...],
) -> tuple[ClosedCandle, ...]:
    return tuple(
        ClosedCandle(
            open_time_ms=session_start_ms + index * INTERVAL_MS,
            close_time_ms=session_start_ms + (index + 1) * INTERVAL_MS,
            open=Decimal(100),
            high=Decimal(101) if index < 4 else Decimal(max("101", close)),
            low=Decimal(99),
            close=Decimal(close),
            volume=Decimal(10),
        )
        for index, close in enumerate(closes)
    )


class _MaterializationLeaseRepository:
    def __init__(self, claim: MaterializationGenerationLeaseClaim) -> None:
        self._claim = claim
        self.releases: list[tuple[str, str]] = []

    async def claim_materialization_generation(self, **_kwargs):
        return self._claim

    async def get_current_entry_vacuum(self, **_kwargs):
        return None

    async def release_materialization_generation_lease(
        self,
        *,
        materialization_generation_id: str,
        worker_id: str,
    ) -> None:
        self.releases.append((materialization_generation_id, worker_id))


class _MaterializationLeaseUow:
    def __init__(self, repository: _MaterializationLeaseRepository) -> None:
        self.instrument_selection = repository

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback) -> None:
        return None


class _UnusedAuditSource:
    async def evaluate_authority_gap(self, _request):
        raise AssertionError("leased materialization must not evaluate an audit")


class _ReadonlySelectionRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    async def get_selection_control(self, strategy_group_id: str):
        self.calls.append(("control", strategy_group_id))

    async def get_selection_job(
        self,
        *,
        selection_spec_id: str,
        session_start_ms: int,
    ):
        self.calls.append(("job", selection_spec_id, session_start_ms))

    async def get_snapshot_disposition(
        self,
        *,
        selection_spec_id: str,
        session_start_ms: int,
    ):
        self.calls.append(("snapshot", selection_spec_id, session_start_ms))

    async def get_materialization_generation_for_period(
        self,
        *,
        strategy_group_id: str,
        selection_spec_id: str,
        session_start_ms: int,
    ):
        self.calls.append(
            (
                "generation",
                strategy_group_id,
                selection_spec_id,
                session_start_ms,
            )
        )

    async def list_entry_vacuums_for_period(
        self,
        *,
        strategy_group_id: str,
        selection_spec_id: str,
        session_start_ms: int,
        limit: int,
    ):
        self.calls.append(
            (
                "vacuums",
                strategy_group_id,
                selection_spec_id,
                session_start_ms,
                limit,
            )
        )
        return ()

    async def list_authority_gap_audits_for_period(
        self,
        *,
        selection_spec_id: str,
        session_start_ms: int,
        limit: int,
    ):
        self.calls.append(("audits", selection_spec_id, session_start_ms, limit))
        return ()

    async def get_current_authority_projection(self, selection_spec_id: str):
        self.calls.append(("authority", selection_spec_id))

    async def get_runtime_release_compatibility_fact(
        self,
        release_compatibility_id: str,
    ):
        self.calls.append(("release", release_compatibility_id))


class _ReadonlySelectionUow:
    def __init__(self, repository: _ReadonlySelectionRepository) -> None:
        self.instrument_selection = repository


def _selection_control() -> SelectionControl:
    return SelectionControl(
        strategy_group_id="SOR-001",
        selection_spec_id="sor-dynamic-selection-v0",
        selection_mode=SelectionMode.STATIC_BASELINE,
        pending_selection_mode=None,
        pending_effective_session_start_ms=None,
        pending_authorization_id=None,
        control_version=1,
        rollback_baseline_id="rollback-baseline:SOR-001:pre-dynamic-v0",
        updated_at_ms=1_800_000_000_000,
    )


class _SelectionControlRepository:
    def __init__(self, control: SelectionControl) -> None:
        self._control = control
        self.calls: list[tuple[str]] = []

    async def get_selection_control(self, strategy_group_id: str):
        self.calls.append((strategy_group_id,))
        return self._control


class _SelectionControlUow:
    def __init__(self, repository: _SelectionControlRepository) -> None:
        self.instrument_selection = repository

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback) -> None:
        return None
