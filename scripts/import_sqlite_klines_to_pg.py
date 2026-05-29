#!/usr/bin/env python3
"""One-shot import of SQLite v3_dev.db klines into Docker PG dingdingbot.klines.

Idempotent: uses ON CONFLICT DO NOTHING. Reads in batches of 10k rows.
"""

from __future__ import annotations

import asyncio
import sqlite3
import time

import asyncpg

SQLITE_PATH = "data/v3_dev.db"
PG_DSN = "postgresql://dingdingbot:dingdingbot_dev@localhost:5432/dingdingbot"
BATCH_SIZE = 10_000

SELECT_SQL = """
SELECT symbol, timeframe, timestamp, open, high, low, close, volume, is_closed, created_at
FROM klines
ORDER BY symbol, timeframe, timestamp
"""

INSERT_SQL = """
INSERT INTO klines (symbol, timeframe, timestamp, open, high, low, close, volume, is_closed, created_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
ON CONFLICT (symbol, timeframe, timestamp) DO NOTHING
"""


async def main() -> None:
    # Read all rows from SQLite
    print(f"Reading from SQLite: {SQLITE_PATH}")
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(SELECT_SQL)

    # Connect to PG
    print(f"Connecting to PG: {PG_DSN.split('@')[1]}")
    pg = await asyncpg.connect(PG_DSN)

    # Confirm PG klines is empty
    pg_count = await pg.fetchval("SELECT COUNT(*) FROM klines")
    print(f"PG klines current rows: {pg_count}")
    if pg_count > 0:
        print(f"WARNING: PG already has {pg_count} rows. Will skip duplicates via ON CONFLICT.")

    total_inserted = 0
    total_skipped = 0
    batch_num = 0
    start_time = time.time()

    while True:
        rows = cur.fetchmany(BATCH_SIZE)
        if not rows:
            break

        batch_num += 1
        records = [
            (
                r["symbol"],           # $1
                r["timeframe"],        # $2
                r["timestamp"],        # $3 - BIGINT
                r["open"],             # $4 - TEXT in sqlite, numeric in pg
                r["high"],             # $5
                r["low"],              # $6
                r["close"],            # $7
                r["volume"],           # $8
                bool(r["is_closed"]),  # $9
                r["created_at"],       # $10 - BIGINT
            )
            for r in rows
        ]

        # Execute batch
        async with pg.transaction():
            result = await pg.executemany(INSERT_SQL, records)

        batch_size = len(records)
        total_inserted += batch_size
        elapsed = time.time() - start_time
        rate = total_inserted / elapsed if elapsed > 0 else 0
        print(f"  Batch {batch_num}: {batch_size} rows processed "
              f"({total_inserted} total, {rate:.0f} rows/s)")

    conn.close()

    # Final verification
    final_count = await pg.fetchval("SELECT COUNT(*) FROM klines")
    elapsed = time.time() - start_time

    print(f"\n{'='*60}")
    print(f"Import complete in {elapsed:.1f}s")
    print(f"SQLite rows read: {total_inserted}")
    print(f"PG klines final count: {final_count}")

    # Per symbol/timeframe breakdown
    print(f"\nPG coverage by symbol/timeframe:")
    breakdown = await pg.fetch("""
        SELECT symbol, timeframe, COUNT(*) as rows,
               MIN(timestamp) as min_ts, MAX(timestamp) as max_ts
        FROM klines
        GROUP BY symbol, timeframe
        ORDER BY symbol, timeframe
    """)
    for row in breakdown:
        print(f"  {row['symbol']:20s} {row['timeframe']:4s} "
              f"{row['rows']:>8,} rows  "
              f"{row['min_ts']} -> {row['max_ts']}")

    await pg.close()


if __name__ == "__main__":
    asyncio.run(main())
