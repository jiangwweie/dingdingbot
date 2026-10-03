"""Run the frozen 0007 full-chain test against one disposable source database."""

from __future__ import annotations

import argparse
import asyncio
import json

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from tests.trading_kernel.full_chain.test_ticket_lifecycle import (
    test_one_ticket_reaches_protected_exit_settlement_and_terminal_review,
)


async def _run(database_url: str) -> dict[str, object]:
    engine = create_async_engine(database_url)
    try:
        await test_one_ticket_reaches_protected_exit_settlement_and_terminal_review(engine)
        async with engine.connect() as conn:
            row = (await conn.execute(sa.text(
                "SELECT t.ticket_id,t.status AS ticket_status,a.status AS aggregate_status "
                "FROM brc_trade_tickets t JOIN brc_trade_aggregates a USING(ticket_id)"
            ))).mappings().one()
            return {
                **dict(row),
                "command_count": await conn.scalar(sa.text(
                    "SELECT count(*) FROM brc_exchange_commands WHERE ticket_id=:ticket"
                ), {"ticket":row["ticket_id"]}),
                "review_count": await conn.scalar(sa.text(
                    "SELECT count(*) FROM brc_trade_reviews WHERE ticket_id=:ticket"
                ), {"ticket":row["ticket_id"]}),
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
