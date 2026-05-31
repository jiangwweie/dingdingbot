#!/usr/bin/env python3
"""Run one cron-ready read-only MI/CPM strategy-group observation cycle.

The command reads only closed market candles, writes observe-only evidence to
PG, and never starts runtime, creates execution intents, grants permissions, or
touches order paths.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    load_dotenv(REPO_ROOT / ".env")
    load_dotenv(REPO_ROOT / ".env.local", override=True)


async def _run(args: argparse.Namespace) -> int:
    from src.application.strategy_group_readonly_observation_scheduler import (
        run_scheduled_readonly_observation_once,
    )

    result = await run_scheduled_readonly_observation_once(source_name=args.source)
    payload = result.model_dump(mode="json")
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            "scheduled_readonly_strategy_group_observation_v0 "
            f"source={result.market_source} sink={result.sink} "
            f"inserted={result.inserted_count} skipped_duplicate={result.skipped_duplicate_count} "
            f"failed={result.failed_count}"
        )
        for item in result.candidate_results:
            print(
                f"- {item.candidate_id} {item.symbol} {item.side} "
                f"signal={item.signal_type} bar={item.market_bar_timestamp_ms} "
                f"action={item.action} record={item.record_id}"
            )
    return 1 if result.failed_count else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        choices=["live_market", "local_sqlite_fallback"],
        default="live_market",
        help="Closed-candle read-only market source.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON for cron/log capture.")
    args = parser.parse_args()
    _load_env()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
