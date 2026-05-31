#!/usr/bin/env python3
"""Calculate and persist forward reviews for BNB live case #001.

This command reads a PG observation row and public Binance USD-M closed klines,
writes observe-only forward review evidence to PG, and never starts runtime,
creates execution intents, grants permissions, or touches order paths.
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

DEFAULT_BNB_CASE_OBSERVATION_ID = "MI-001-BNB-LONG:mi001-5bb8b1c1b14437d7bddbacab:1780196400000"


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    load_dotenv(REPO_ROOT / ".env")
    load_dotenv(REPO_ROOT / ".env.local", override=True)


async def _run(args: argparse.Namespace) -> int:
    from src.application.strategy_group_forward_review import calculate_forward_reviews_for_observation
    from src.infrastructure.binance_public_kline_market_source import BinancePublicKlineMarketSource
    from src.infrastructure.pg_strategy_group_forward_review_repository import PgStrategyGroupForwardReviewRepository
    from src.infrastructure.pg_strategy_group_observation_repository import PgStrategyGroupObservationRepository

    observation_repo = PgStrategyGroupObservationRepository()
    review_repo = PgStrategyGroupForwardReviewRepository()
    await observation_repo.initialize()
    await review_repo.initialize()

    observation = await observation_repo.get(args.observation_id)
    if observation is None:
        raise SystemExit(f"observation not found: {args.observation_id}")

    market_source = BinancePublicKlineMarketSource()
    reviews = calculate_forward_reviews_for_observation(
        observation,
        market_source=market_source,
        windows=["1h", "4h", "12h", "24h", "72h"],
    )
    recorded = await review_repo.record_many(reviews)
    payload = {
        "observation_id": observation.record_id,
        "candidate_id": observation.candidate_id,
        "signal_type": observation.signal_type,
        "market_bar_timestamp_ms": observation.market_bar_timestamp_ms,
        "source": getattr(market_source, "source_id", "binance_usdm_public_klines_read_only"),
        "reviews": [review.model_dump(mode="json") for review in recorded],
        "non_permissions": {
            "no_trial_start": True,
            "no_execution_intent": True,
            "no_order_permission": True,
            "no_runtime_start": True,
            "no_exchange_write": True,
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--observation-id",
        default=DEFAULT_BNB_CASE_OBSERVATION_ID,
        help="PG observation row to review.",
    )
    args = parser.parse_args()
    _load_env()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
