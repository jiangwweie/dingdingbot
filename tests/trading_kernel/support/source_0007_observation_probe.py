"""Isolated exact-0007 producer probe for the local migration parity test.

Run only with the archived 0007 ``src`` package on ``PYTHONPATH`` against a
disposable PostgreSQL database. This is not a runtime compatibility adapter.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from src.trading_kernel.application.observe_strategy_scope import (
    ObservationRequest,
    observe_strategy_scope,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.unit.detectors.fixtures import (
    mi_flat_snapshot,
    mi_long_snapshot,
    mpg_flat_snapshot,
    mpg_long_snapshot,
)


async def _run(database_url: str, scope_id: str, group: str, first_close_ms: int) -> dict[str, object]:
    engine = create_async_engine(database_url)
    try:
        results = []
        market_reads = []
        episode_transitions = []
        for offset, triggered in ((1, False), (2, True)):
            template = (
                (mpg_long_snapshot if triggered else mpg_flat_snapshot)()
                if group == "MPG-001"
                else (mi_long_snapshot if triggered else mi_flat_snapshot)()
            )
            close_ms = first_close_ms + offset * 3_600_000
            delta = close_ms - template.trigger_candle_close_time_ms

            class ClosedMarket:
                def __init__(self, market_template, shift_ms):
                    self.template = market_template
                    self.shift_ms = shift_ms

                async def fetch_closed_candles(self, request):
                    candles = self.template.candles_1h if request.timeframe == "1h" else self.template.candles_4h
                    response = tuple(c.model_copy(update={
                        "open_time_ms": c.open_time_ms + self.shift_ms,
                        "close_time_ms": c.close_time_ms + self.shift_ms,
                    }) for c in candles)
                    market_reads.append({
                        "request": request.model_dump(mode="json"),
                        "response": [c.model_dump(mode="json") for c in response],
                    })
                    return response

            result = await observe_strategy_scope(
                lambda: PostgresKernelUnitOfWork(engine), ClosedMarket(template, delta),
                ObservationRequest(
                    runtime_scope_id=scope_id,
                    runtime_commit="a" * 40,
                    schema_revision="0007_exit_profile_authority_v1",
                    trigger_candle_close_time_ms=close_ms,
                    attempted_at_ms=close_ms + 1,
                ),
            )
            results.append(result.model_dump(mode="json"))
            async with engine.connect() as conn:
                current_episode = (await conn.execute(sa.text(
                    "SELECT * FROM brc_exposure_episode_current ORDER BY episode_domain_key"
                ))).mappings().one()
                episode_transitions.append({
                    key: _json_value(value) for key, value in current_episode.items()
                })
        async with engine.connect() as conn:
            episode = (await conn.execute(sa.text(
                "SELECT * FROM brc_exposure_episode_current ORDER BY episode_domain_key"
            ))).mappings().one()
            signals = (await conn.execute(sa.text(
                "SELECT signal_event_id, exposure_episode_id, occurred_at_ms, fact_digest "
                "FROM brc_signal_events ORDER BY signal_event_id"
            ))).mappings().all()
            comparisons = (await conn.execute(sa.text(
                "SELECT closed_bar_time_ms, member_set_digest, projection "
                "FROM brc_comparative_projection_current ORDER BY closed_bar_time_ms"
            ))).mappings().all()
            return {
                "results": results,
                "market_reads": market_reads,
                "episode_transitions": episode_transitions,
                "comparisons": [{key: _json_value(value) for key, value in row.items()} for row in comparisons],
                "episode": {key: _json_value(value) for key, value in episode.items()},
                "signals": [{key: _json_value(value) for key, value in row.items()} for row in signals],
            }
    finally:
        await engine.dispose()


def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--scope-id", required=True)
    parser.add_argument("--group", choices=("MPG-001", "MI-001"), required=True)
    parser.add_argument("--first-close-ms", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(_run(
        args.database_url, args.scope_id, args.group, args.first_close_ms,
    )), sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
