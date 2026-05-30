#!/usr/bin/env python3
"""Import local Binance UM futures kline zip files into local SQLite klines.

Research-only local data repair helper. It reads already-downloaded public
Binance data zip files and upserts OHLCV rows into the local SQLite `klines`
table. It does not call exchange APIs, does not connect to PG, and does not
touch runtime, execution, order, or account state.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path
from zipfile import ZipFile


SYMBOL_MAP = {
    "BNBUSDT": "BNB/USDT:USDT",
    "SOLUSDT": "SOL/USDT:USDT",
    "ETHUSDT": "ETH/USDT:USDT",
    "BTCUSDT": "BTC/USDT:USDT",
}


def main() -> int:
    args = _parse_args()
    zip_dir = Path(args.zip_dir)
    sqlite_db = Path(args.sqlite_db)
    if not zip_dir.exists():
        raise SystemExit(f"zip dir not found: {zip_dir}")
    if not sqlite_db.exists():
        raise SystemExit(f"sqlite db not found: {sqlite_db}")

    zip_paths = sorted(zip_dir.glob(f"{args.exchange_symbol}-{args.timeframe}-*.zip"))
    if not zip_paths:
        raise SystemExit(f"no zip files matched {args.exchange_symbol}-{args.timeframe}-*.zip in {zip_dir}")

    symbol = SYMBOL_MAP.get(args.exchange_symbol, args.symbol)
    if not symbol:
        raise SystemExit("--symbol is required for unknown exchange symbol")

    connection = sqlite3.connect(sqlite_db)
    try:
        before = _count(connection, symbol=symbol, timeframe=args.timeframe)
        inserted_or_replaced = 0
        for path in zip_paths:
            inserted_or_replaced += _import_zip(
                connection,
                path=path,
                symbol=symbol,
                timeframe=args.timeframe,
            )
        connection.commit()
        after = _count(connection, symbol=symbol, timeframe=args.timeframe)
    finally:
        connection.close()

    print(f"symbol={symbol}")
    print(f"timeframe={args.timeframe}")
    print(f"zip_files={len(zip_paths)}")
    print(f"rows_before={before}")
    print(f"rows_processed={inserted_or_replaced}")
    print(f"rows_after={after}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip-dir", required=True)
    parser.add_argument("--sqlite-db", default="data/v3_dev.db")
    parser.add_argument("--exchange-symbol", default="BNBUSDT")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--timeframe", default="1h")
    return parser.parse_args()


def _import_zip(
    connection: sqlite3.Connection,
    *,
    path: Path,
    symbol: str,
    timeframe: str,
) -> int:
    processed = 0
    with ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.endswith(".csv"):
                continue
            with archive.open(name) as raw:
                text = (line.decode("utf-8") for line in raw)
                reader = csv.DictReader(text)
                rows = [
                    (
                        symbol,
                        timeframe,
                        int(row["open_time"]),
                        row["open"],
                        row["high"],
                        row["low"],
                        row["close"],
                        row["volume"],
                        1,
                        int(row["open_time"]),
                    )
                    for row in reader
                ]
            connection.executemany(
                """
                INSERT OR REPLACE INTO klines (
                    symbol, timeframe, timestamp, open, high, low, close,
                    volume, is_closed, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            processed += len(rows)
    return processed


def _count(connection: sqlite3.Connection, *, symbol: str, timeframe: str) -> int:
    return int(
        connection.execute(
            "SELECT COUNT(*) FROM klines WHERE symbol = ? AND timeframe = ?",
            (symbol, timeframe),
        ).fetchone()[0]
    )


if __name__ == "__main__":
    raise SystemExit(main())
