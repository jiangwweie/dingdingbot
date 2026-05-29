#!/usr/bin/env python3
"""Run a bounded CPM-RO-001 historical experiment against registered PG data.

This command writes compact historical signal/output review rows to PG. It does
not write trial trade intents, create execution intents, create orders, call
live APIs, or update strategy registry status.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone

from src.application.cpm_historical_experiment_runner import (
    CPMHistoricalExperimentRunRequest,
    CPMHistoricalExperimentRunner,
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
    parser.add_argument("--start-time-ms", type=int, required=True)
    parser.add_argument("--end-time-ms", type=int, required=True)
    parser.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    parser.add_argument("--primary-timeframe", default="1h")
    parser.add_argument("--context-timeframes", default="4h,1d")
    parser.add_argument("--sampling-interval-bars", type=int, default=24)
    parser.add_argument("--sample-limit", type=int, default=500)
    parser.add_argument("--run-label", default="cpm-ro-001-historical")
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
        now_ms=lambda: int(datetime.now(timezone.utc).timestamp() * 1000),
    )
    runner = CPMHistoricalExperimentRunner(
        registry_repository=registry_repo,
        dataset_repository=ohlcv_repo,
        evaluation_repository=eval_repo,
        experiment_service=experiment_service,
        now_ms=lambda: int(datetime.now(timezone.utc).timestamp() * 1000),
    )
    result = await runner.run(
        CPMHistoricalExperimentRunRequest(
            symbols=[item.strip() for item in args.symbols.split(",") if item.strip()],
            primary_timeframe=args.primary_timeframe,
            context_timeframes=[
                item.strip() for item in args.context_timeframes.split(",") if item.strip()
            ],
            start_time_ms=args.start_time_ms,
            end_time_ms=args.end_time_ms,
            sampling_interval_bars=args.sampling_interval_bars,
            sample_limit=args.sample_limit,
            run_label=args.run_label,
            require_registered_datasets=not args.allow_missing_dataset_catalog,
        )
    )
    print(json.dumps(result.owner_report.model_dump(mode="json"), indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(_main())
