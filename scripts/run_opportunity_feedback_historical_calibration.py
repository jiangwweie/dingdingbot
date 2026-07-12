#!/usr/bin/env python3
"""Run manual PG-owned OFC historical calibration and print stdout JSON."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from pathlib import Path
import sys
import time
from typing import Any, Sequence

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pg_dsn import is_sync_postgres_dsn, normalize_sync_postgres_dsn  # noqa: E402
from src.application.opportunity_feedback_historical_replay import (  # noqa: E402
    HistoricalReplayScope,
    build_historical_replay_scopes,
    run_opportunity_feedback_historical_replay,
)
from src.infrastructure.binance_usdm_historical_candle_source import (  # noqa: E402
    BinanceUsdMPublicHistoricalCandleSource,
)


DAY_MS = 86_400_000
HISTORICAL_DAYS = 365
WARMUP_DAYS = 10


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if not args.database_url:
        print("ERROR: PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    if not is_sync_postgres_dsn(args.database_url):
        print("ERROR: a synchronous PostgreSQL PG_DATABASE_URL is required", file=sys.stderr)
        return 2

    engine = sa.create_engine(
        normalize_sync_postgres_dsn(args.database_url),
        pool_pre_ping=True,
    )
    try:
        with engine.connect() as conn:
            conn.execute(sa.text("SET TRANSACTION READ ONLY"))
            scopes = _load_pg_scopes(conn)
            conn.rollback()
    finally:
        engine.dispose()

    source = BinanceUsdMPublicHistoricalCandleSource(
        timeout_seconds=args.timeout_seconds,
        page_limit=args.page_limit,
    )
    start_time_ms = max(
        0,
        args.as_of_ms - (HISTORICAL_DAYS + WARMUP_DAYS) * DAY_MS,
    )
    candles = _fetch_candle_series(
        source=source,
        series=_required_candle_series(scopes),
        start_time_ms=start_time_ms,
        end_time_ms=args.as_of_ms,
        max_workers=args.max_workers,
    )
    result = run_opportunity_feedback_historical_replay(
        scopes=scopes,
        candles_by_symbol_timeframe=candles,
        as_of_ms=args.as_of_ms,
    )
    print(result.model_dump_json(indent=2))
    return 0


def _load_pg_scopes(conn: sa.engine.Connection) -> list[HistoricalReplayScope]:
    event_specs = list(
        conn.execute(
            sa.text("SELECT * FROM brc_strategy_side_event_specs WHERE status = 'current'")
        ).mappings()
    )
    candidate_scopes = list(
        conn.execute(
            sa.text("SELECT * FROM brc_strategy_group_candidate_scope WHERE status = 'active'")
        ).mappings()
    )
    bindings = list(
        conn.execute(
            sa.text("SELECT * FROM brc_candidate_scope_event_bindings WHERE status = 'active'")
        ).mappings()
    )
    event_fact_rows = list(
        conn.execute(
            sa.text("SELECT * FROM brc_strategy_event_required_facts WHERE status = 'current'")
        ).mappings()
    )
    runtime_rows = list(
        conn.execute(
            sa.text(
                """
                SELECT strategy_family_id, strategy_family_version_id, updated_at_ms
                FROM strategy_runtime_instances
                WHERE status = 'active'
                ORDER BY strategy_family_id, updated_at_ms DESC
                """
            )
        ).mappings()
    )
    versions_by_group: dict[str, set[str]] = {}
    for row in runtime_rows:
        versions_by_group.setdefault(str(row["strategy_family_id"]), set()).add(
            str(row["strategy_family_version_id"])
        )
    evaluator_versions: dict[str, str] = {}
    needed_groups = {str(row["strategy_group_id"]) for row in event_specs}
    for group_id in sorted(needed_groups):
        versions = versions_by_group.get(group_id, set())
        if len(versions) != 1:
            raise RuntimeError(
                f"active_runtime_evaluator_version_not_unique:{group_id}:{sorted(versions)}"
            )
        evaluator_versions[group_id] = next(iter(versions))
    scopes = build_historical_replay_scopes(
        event_specs=event_specs,
        candidate_scopes=candidate_scopes,
        bindings=bindings,
        event_fact_rows=event_fact_rows,
        evaluator_versions=evaluator_versions,
    )
    if len(scopes) != 22 or len({scope.event_spec.event_spec_id for scope in scopes}) != 6:
        raise RuntimeError(
            f"historical_replay_scope_not_current_22x6:{len(scopes)}:"
            f"{len({scope.event_spec.event_spec_id for scope in scopes})}"
        )
    return scopes


def _required_candle_series(
    scopes: Sequence[HistoricalReplayScope],
) -> tuple[tuple[str, str], ...]:
    series: set[tuple[str, str]] = set()
    for scope in scopes:
        if scope.event_spec.timeframe == "1h":
            series.add((scope.symbol, "1h"))
            series.add((scope.symbol, "4h"))
        elif scope.event_spec.timeframe == "15m":
            series.add((scope.symbol, "15m"))
        else:
            raise ValueError(
                f"unsupported_historical_timeframe:{scope.event_spec.timeframe}"
            )
    return tuple(sorted(series))


def _fetch_candle_series(
    *,
    source: BinanceUsdMPublicHistoricalCandleSource,
    series: Sequence[tuple[str, str]],
    start_time_ms: int,
    end_time_ms: int,
    max_workers: int,
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    results: dict[tuple[str, str], list[dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                source.fetch_closed_candles,
                symbol=symbol,
                timeframe=timeframe,
                start_time_ms=start_time_ms,
                end_time_ms=end_time_ms,
            ): (symbol, timeframe)
            for symbol, timeframe in series
        }
        for future in as_completed(futures):
            key = futures[future]
            rows = future.result()
            if not rows:
                raise RuntimeError(f"historical_candles_empty:{key[0]}:{key[1]}")
            results[key] = rows
    return results


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run one manual 90/365-day OFC historical calibration from PG current "
            "scope and Binance USD-M public closed candles. Prints stdout only."
        )
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("PG_DATABASE_URL", ""),
    )
    parser.add_argument(
        "--as-of-ms",
        type=int,
        default=int(time.time() * 1000),
    )
    parser.add_argument("--max-workers", type=int, default=4, choices=range(1, 9))
    parser.add_argument("--timeout-seconds", type=float, default=15)
    parser.add_argument("--page-limit", type=int, default=1000)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
