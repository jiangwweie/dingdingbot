#!/usr/bin/env python3
"""Run bounded CPM-RO-001 regime-split historical experiments.

Runs four explicit windows:
- 2024-to-now primary current structure
- 2025-to-now recent current structure
- 2021-2023 legacy control
- 2021-to-now full diagnostic

This command writes compact PG reports only. It does not write trial trade
intents, create execution intents, create orders, call live APIs, or update
strategy registry status.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone

from src.application.cpm_historical_experiment_runner import CPMHistoricalExperimentRunner
from src.application.cpm_regime_split_experiment_runner import (
    CPMRegimeSplitExperimentRunner,
    CPMRegimeSplitRunRequest,
)
from src.application.historical_signal_evaluation_service import CPMHistoricalExperimentService
from src.application.historical_signal_input_builder import (
    HistoricalMarketSnapshotBuilder,
    HistoricalStrategyFamilySignalInputBuilder,
)
from src.domain.cpm_historical_evaluator import CPMRO001HistoricalEvaluator
from src.infrastructure.pg_historical_ohlcv_catalog_repository import PgHistoricalOhlcvCatalogRepository
from src.infrastructure.pg_historical_signal_evaluation_repository import (
    PgHistoricalSignalEvaluationRepository,
)
from src.infrastructure.pg_strategy_family_registry_repository import PgStrategyFamilyRegistryRepository


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--end-time-ms", type=int, required=True)
    parser.add_argument("--symbols", default="BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT")
    parser.add_argument("--primary-timeframe", default="1h")
    parser.add_argument("--context-timeframes", default="4h,1d")
    parser.add_argument("--sampling-interval-bars", type=int, default=24)
    parser.add_argument("--sample-limit-per-window", type=int, default=1500)
    parser.add_argument("--sample-limit-per-symbol", type=int, default=None)
    parser.add_argument("--max-total-evaluations", type=int, default=6000)
    parser.add_argument("--run-label", default="cpm_ro001_regime_split_current_structure")
    parser.add_argument(
        "--allow-missing-dataset-catalog",
        action="store_true",
        help="Allow running when catalog metadata is missing; klines still must exist.",
    )
    return parser.parse_args()


async def _main() -> None:
    args = _parse_args()
    registry_repo = PgStrategyFamilyRegistryRepository()
    ohlcv_repo = PgHistoricalOhlcvCatalogRepository()
    eval_repo = PgHistoricalSignalEvaluationRepository()
    await registry_repo.initialize()
    await ohlcv_repo.initialize()
    await eval_repo.initialize()

    now_ms = lambda: int(datetime.now(timezone.utc).timestamp() * 1000)
    market_builder = HistoricalMarketSnapshotBuilder(
        repository=ohlcv_repo,
        primary_lookback=64,
        context_lookback=64,
        atr_period=14,
    )
    experiment_service = CPMHistoricalExperimentService(
        evaluation_repository=eval_repo,
        ohlcv_repository=ohlcv_repo,
        signal_input_builder=HistoricalStrategyFamilySignalInputBuilder(
            market_snapshot_builder=market_builder,
        ),
        evaluator=CPMRO001HistoricalEvaluator(),
        now_ms=now_ms,
    )
    child_runner = CPMHistoricalExperimentRunner(
        registry_repository=registry_repo,
        dataset_repository=ohlcv_repo,
        evaluation_repository=eval_repo,
        experiment_service=experiment_service,
        now_ms=now_ms,
    )
    runner = CPMRegimeSplitExperimentRunner(
        child_runner=child_runner,
        report_repository=eval_repo,
        now_ms=now_ms,
    )
    result = await runner.run(
        CPMRegimeSplitRunRequest(
            symbols=[item.strip() for item in args.symbols.split(",") if item.strip()],
            primary_timeframe=args.primary_timeframe,
            context_timeframes=[
                item.strip() for item in args.context_timeframes.split(",") if item.strip()
            ],
            end_time_ms=args.end_time_ms,
            sampling_interval_bars=args.sampling_interval_bars,
            sample_limit_per_window=args.sample_limit_per_window,
            sample_limit_per_symbol=args.sample_limit_per_symbol,
            max_total_evaluations=args.max_total_evaluations,
            run_label=args.run_label,
            require_registered_datasets=not args.allow_missing_dataset_catalog,
        )
    )
    print(json.dumps(result.comparison_report.model_dump(mode="json"), indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(_main())
