"""Run frozen 0007 fallback through its official local coordinator test."""

from __future__ import annotations

import argparse
import asyncio
import json

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from tests.trading_kernel.integration.test_selection_materialization_repository import (
    test_fallback_commit_failure_rolls_back_and_retry_is_idempotent,
)


async def _run(database_url: str) -> dict[str, object]:
    engine = create_async_engine(database_url)
    try:
        await test_fallback_commit_failure_rolls_back_and_retry_is_idempotent(engine)
        async with engine.connect() as conn:
            authority = (await conn.execute(sa.text(
                "SELECT selection_authority_id,authority_outcome,semantic_digest "
                "FROM brc_selection_session_authorities WHERE authority_outcome='FALLBACK_PREVIOUS'"
            ))).mappings().one()
            return {
                **dict(authority),
                "gap_audit_count": await conn.scalar(sa.text(
                    "SELECT count(*) FROM brc_selection_authority_gap_audits_current"
                )),
                "generation_count": await conn.scalar(sa.text(
                    "SELECT count(*) FROM brc_strategy_universe_materialization_generations"
                )),
            }
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(_run(args.database_url)), sort_keys=True))


if __name__ == "__main__":
    main()
