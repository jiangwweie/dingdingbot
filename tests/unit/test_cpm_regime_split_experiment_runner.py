from __future__ import annotations

import asyncio
import importlib.util
import inspect as py_inspect
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.cpm_historical_experiment_runner import (
    CPMHistoricalExperimentRunRequest,
    CPMHistoricalExperimentRunResult,
)
from src.application.cpm_regime_split_experiment_runner import (
    CPMRegimeSplitExperimentRunner,
    CPMRegimeSplitRunRequest,
    build_cpm_regime_windows,
)
from src.domain.cpm_historical_evaluator import CPM_FAMILY_ID
from src.domain.historical_signal_evaluation import (
    HistoricalExperimentVerdict,
    HistoricalRegimeSplitComparisonReport,
    HistoricalRegimeWindowReport,
    HistoricalSignalEvaluationOwnerReport,
    HistoricalSignalEvaluationSummary,
    build_regime_split_comparison_report,
)
from src.infrastructure.pg_historical_signal_evaluation_repository import (
    PgHistoricalSignalEvaluationRepository,
)
from src.infrastructure.pg_models import PGBrcHistoricalRegimeSplitReportORM


START_2021_MS = 1609459200000
START_2024_MS = 1704067200000
START_2025_MS = 1735689600000
END_2023_MS = 1704067199999
END_MS = 1779926400000
NOW_MS = 1770000000000


@pytest_asyncio.fixture()
async def regime_repo():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(PGBrcHistoricalRegimeSplitReportORM.__table__.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PgHistoricalSignalEvaluationRepository(session_maker=session_maker)
    finally:
        await engine.dispose()


class FakeChildRunner:
    def __init__(self, verdicts: dict[str, HistoricalExperimentVerdict]) -> None:
        self.verdicts = verdicts
        self.requests: list[CPMHistoricalExperimentRunRequest] = []

    async def run(self, request: CPMHistoricalExperimentRunRequest) -> CPMHistoricalExperimentRunResult:
        self.requests.append(request)
        suffix = request.run_label.split("-")[-1]
        window_name = {
            "primary2024": "primary_current_structure_2024_to_now",
            "recent2025": "recent_current_structure_2025_to_now",
            "legacy2021": "legacy_control_2021_to_2023",
            "full2021": "full_diagnostic_2021_to_now",
        }[suffix]
        verdict = self.verdicts[window_name]
        run_id = f"run-{suffix}"
        return CPMHistoricalExperimentRunResult(
            run_id=run_id,
            dataset_ids=[],
            summary=_summary(run_id, verdict),
            owner_report=_owner_report(run_id, verdict),
        )


def _summary(run_id: str, verdict: HistoricalExperimentVerdict) -> HistoricalSignalEvaluationSummary:
    would_enter = 4 if verdict == HistoricalExperimentVerdict.CONTINUE else 1 if verdict == HistoricalExperimentVerdict.NEEDS_REFINEMENT else 0
    total = 10
    return HistoricalSignalEvaluationSummary(
        run_id=run_id,
        total_evaluations=total,
        signal_counts_by_type={
            "invalid": 0,
            "no_action": total - would_enter,
            "would_enter": would_enter,
        },
        would_enter_count=would_enter,
        would_enter_ratio=Decimal(would_enter) / Decimal(total),
        invalid_ratio=Decimal("0"),
        by_symbol={"BTCUSDT": total},
        by_year={"2025": total},
        by_side={"none": total - would_enter, "long": would_enter},
        by_data_quality={"degraded": total},
        forward_by_window={},
        incomplete_outcome_count=0,
        suggested_verdict=verdict,
        notes="test summary",
    )


def _owner_report(run_id: str, verdict: HistoricalExperimentVerdict) -> HistoricalSignalEvaluationOwnerReport:
    ratio = Decimal("2") if verdict == HistoricalExperimentVerdict.CONTINUE else Decimal("0.5")
    return HistoricalSignalEvaluationOwnerReport(
        run_id=run_id,
        strategy_family_id=CPM_FAMILY_ID,
        symbols=["BTCUSDT"],
        total_evaluations=10,
        invalid_count=0,
        no_action_count=6,
        would_enter_count=4,
        would_enter_ratio=Decimal("0.4"),
        symbol_breakdown={"BTCUSDT": {"invalid": 0, "no_action": 6, "would_enter": 4}},
        data_quality_breakdown={"degraded": 10},
        forward_outcome_by_window={
            "4h": {
                "mean_mfe_pct": Decimal("2"),
                "mean_abs_mae_pct": Decimal("1"),
                "mfe_mae_ratio": ratio,
                "follow_through_rate": Decimal("0.75"),
                "invalidation_hit_rate": Decimal("0.25"),
            }
        },
        return_time_curve_summary={"4h": [{"bar": 1, "mean_return_pct": Decimal("0.5"), "sample_count": 4}]},
        advisory_verdict=verdict,
        verdict_reasons=[f"{verdict.value} test reason"],
        notes="test owner report; not alpha proof",
    )


def _window_report(
    name: str,
    verdict: HistoricalExperimentVerdict,
    *,
    decision_weight: str = "high",
) -> HistoricalRegimeWindowReport:
    return HistoricalRegimeWindowReport(
        window_name=name,
        window_role=name,
        decision_weight=decision_weight,
        start_time_ms=START_2024_MS,
        end_time_ms=END_MS,
        run_id=f"run-{name}",
        owner_report=_owner_report(f"run-{name}", verdict),
    )


def _comparison(
    *,
    primary: HistoricalExperimentVerdict,
    recent: HistoricalExperimentVerdict,
    legacy: HistoricalExperimentVerdict,
    full: HistoricalExperimentVerdict,
) -> HistoricalRegimeSplitComparisonReport:
    return build_regime_split_comparison_report(
        comparison_id="cmp-test",
        strategy_family_id=CPM_FAMILY_ID,
        window_reports=[
            _window_report("primary_current_structure_2024_to_now", primary, decision_weight="high"),
            _window_report("recent_current_structure_2025_to_now", recent, decision_weight="high"),
            _window_report("legacy_control_2021_to_2023", legacy, decision_weight="low"),
            _window_report("full_diagnostic_2021_to_now", full, decision_weight="diagnostic_only"),
        ],
        created_at_ms=NOW_MS,
    )


def test_regime_window_construction():
    windows = build_cpm_regime_windows(END_MS)
    by_name = {window.window_name: window for window in windows}

    assert by_name["primary_current_structure_2024_to_now"].start_time_ms == START_2024_MS
    assert by_name["primary_current_structure_2024_to_now"].end_time_ms == END_MS
    assert by_name["primary_current_structure_2024_to_now"].decision_weight == "high"
    assert by_name["recent_current_structure_2025_to_now"].start_time_ms == START_2025_MS
    assert by_name["legacy_control_2021_to_2023"].start_time_ms == START_2021_MS
    assert by_name["legacy_control_2021_to_2023"].end_time_ms == END_2023_MS
    assert by_name["legacy_control_2021_to_2023"].decision_weight == "low"
    assert by_name["full_diagnostic_2021_to_now"].start_time_ms == START_2021_MS
    assert by_name["full_diagnostic_2021_to_now"].decision_weight == "diagnostic_only"


def test_weighted_decision_strong_current_weak_legacy_is_regime_dependent_continue():
    report = _comparison(
        primary=HistoricalExperimentVerdict.CONTINUE,
        recent=HistoricalExperimentVerdict.CONTINUE,
        legacy=HistoricalExperimentVerdict.PARK,
        full=HistoricalExperimentVerdict.PARK,
    )

    assert report.weighted_owner_verdict == HistoricalExperimentVerdict.REGIME_DEPENDENT_CONTINUE
    assert "low-weight" in " ".join(report.weighted_verdict_reasons)


def test_weighted_decision_weak_current_strong_legacy_does_not_continue():
    report = _comparison(
        primary=HistoricalExperimentVerdict.PARK,
        recent=HistoricalExperimentVerdict.PARK,
        legacy=HistoricalExperimentVerdict.CONTINUE,
        full=HistoricalExperimentVerdict.CONTINUE,
    )

    assert report.weighted_owner_verdict == HistoricalExperimentVerdict.PARK
    assert "does not override" in " ".join(report.weighted_verdict_reasons)


def test_weighted_decision_mixed_current_improving_recent_needs_refinement():
    report = _comparison(
        primary=HistoricalExperimentVerdict.NEEDS_REFINEMENT,
        recent=HistoricalExperimentVerdict.CONTINUE,
        legacy=HistoricalExperimentVerdict.PARK,
        full=HistoricalExperimentVerdict.PARK,
    )

    assert report.weighted_owner_verdict == HistoricalExperimentVerdict.NEEDS_REFINEMENT


def test_weighted_decision_strong_all_windows_continue_but_not_alpha_proof():
    report = _comparison(
        primary=HistoricalExperimentVerdict.CONTINUE,
        recent=HistoricalExperimentVerdict.CONTINUE,
        legacy=HistoricalExperimentVerdict.CONTINUE,
        full=HistoricalExperimentVerdict.CONTINUE,
    )

    assert report.weighted_owner_verdict == HistoricalExperimentVerdict.CONTINUE
    assert "not alpha proof" in " ".join(report.warnings).lower()


def test_regime_split_request_enforces_boundedness_and_whitelists():
    with pytest.raises(ValueError, match="unsupported symbols"):
        CPMRegimeSplitRunRequest(symbols=["DOGE/USDT:USDT"], end_time_ms=END_MS)
    with pytest.raises(ValueError, match="primary_timeframe=1h"):
        CPMRegimeSplitRunRequest(primary_timeframe="5m", end_time_ms=END_MS)
    with pytest.raises(ValueError, match="unsupported context timeframes"):
        CPMRegimeSplitRunRequest(context_timeframes=["15m"], end_time_ms=END_MS)
    with pytest.raises(ValueError, match="planned evaluations"):
        CPMRegimeSplitRunRequest(
            symbols=["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"],
            end_time_ms=END_MS,
            sample_limit_per_window=12,
            max_total_evaluations=15,
        )


def test_migration_creates_regime_split_report_table():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-05-28-027_create_historical_regime_split_reports.py"
    )
    spec = importlib.util.spec_from_file_location("historical_regime_split_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async def _migrate() -> set[str]:
        async with engine.begin() as conn:
            def upgrade(sync_conn):
                old_op = migration.op
                migration.op = Operations(MigrationContext.configure(sync_conn))
                try:
                    migration.upgrade()
                    return set(inspect(sync_conn).get_table_names())
                finally:
                    migration.op = old_op

            return await conn.run_sync(upgrade)

    tables = asyncio.run(_migrate())
    asyncio.run(engine.dispose())

    assert "brc_historical_regime_split_reports" in tables


@pytest.mark.asyncio
async def test_regime_split_report_repository_round_trip(regime_repo):
    report = _comparison(
        primary=HistoricalExperimentVerdict.CONTINUE,
        recent=HistoricalExperimentVerdict.CONTINUE,
        legacy=HistoricalExperimentVerdict.PARK,
        full=HistoricalExperimentVerdict.PARK,
    )

    saved = await regime_repo.save_regime_split_report(report)
    fetched = await regime_repo.get_regime_split_report(report.comparison_id)

    assert saved.weighted_owner_verdict == HistoricalExperimentVerdict.REGIME_DEPENDENT_CONTINUE
    assert fetched is not None
    assert fetched.child_run_ids_by_window_name["primary_current_structure_2024_to_now"]
    assert fetched.weighted_owner_verdict == HistoricalExperimentVerdict.REGIME_DEPENDENT_CONTINUE


@pytest.mark.asyncio
async def test_regime_split_runner_runs_four_windows_and_persists_comparison(regime_repo):
    child = FakeChildRunner(
        {
            "primary_current_structure_2024_to_now": HistoricalExperimentVerdict.CONTINUE,
            "recent_current_structure_2025_to_now": HistoricalExperimentVerdict.CONTINUE,
            "legacy_control_2021_to_2023": HistoricalExperimentVerdict.PARK,
            "full_diagnostic_2021_to_now": HistoricalExperimentVerdict.PARK,
        }
    )
    runner = CPMRegimeSplitExperimentRunner(
        child_runner=child,  # type: ignore[arg-type]
        report_repository=regime_repo,
        now_ms=lambda: NOW_MS,
    )

    result = await runner.run(
        CPMRegimeSplitRunRequest(
            symbols=["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"],
            end_time_ms=END_MS,
            sample_limit_per_window=12,
            max_total_evaluations=48,
            require_registered_datasets=False,
        )
    )
    persisted = await regime_repo.get_regime_split_report(result.comparison_id)

    assert len(child.requests) == 4
    assert all(request.sample_limit == 4 for request in child.requests)
    assert result.comparison_report.weighted_owner_verdict == HistoricalExperimentVerdict.REGIME_DEPENDENT_CONTINUE
    assert persisted is not None
    assert persisted.child_run_ids_by_window_name == result.comparison_report.child_run_ids_by_window_name


def test_regime_split_runner_exposes_no_execution_order_or_router_methods():
    forbidden_terms = [
        "execution_intent",
        "trial_trade_intent",
        "order",
        "router",
        "route",
        "cancel",
        "close",
        "flatten",
        "sizing",
        "leverage",
        "venue",
    ]
    public_methods = [
        name
        for name, value in py_inspect.getmembers(CPMRegimeSplitExperimentRunner, predicate=py_inspect.isfunction)
        if not name.startswith("_")
    ]
    assert public_methods == ["run"]
    for method_name in public_methods:
        assert all(term not in method_name for term in forbidden_terms)


def test_regime_split_report_contains_no_forbidden_execution_fields():
    report = _comparison(
        primary=HistoricalExperimentVerdict.CONTINUE,
        recent=HistoricalExperimentVerdict.CONTINUE,
        legacy=HistoricalExperimentVerdict.PARK,
        full=HistoricalExperimentVerdict.PARK,
    )

    forbidden = {
        "quantity",
        "notional",
        "leverage",
        "order_type",
        "client_order_id",
        "venue",
        "reduce_only",
        "router_target",
        "cancel_instruction",
        "close_instruction",
        "flatten_instruction",
    }

    def contains_forbidden(value: Any) -> bool:
        if isinstance(value, dict):
            return any(str(key) in forbidden or contains_forbidden(nested) for key, nested in value.items())
        if isinstance(value, list):
            return any(contains_forbidden(item) for item in value)
        return False

    assert not contains_forbidden(report.model_dump(mode="json"))
