#!/usr/bin/env python3
"""TE-005: Download and import pre-2021 ETHUSDT UM monthly klines.

Downloads from Binance Vision, parses CSV, inserts into local SQLite.
Symbol mapping: ETHUSDT -> ETH/USDT:USDT
All historical rows marked is_closed=True.
Duplicate handling: ON CONFLICT (symbol, timeframe, timestamp) DO NOTHING.
"""
import csv
import io
import os
import sys
import zipfile
from datetime import datetime, timezone

import requests

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "v3_dev.db"))
DOWNLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "te005_downloads"))
BASE_URL = "https://data.binance.vision/data/futures/um/monthly/klines/ETHUSDT"
S3_BASE_URL = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision/data/futures/um/monthly/klines/ETHUSDT"

# Target months: 2019-09 through 2020-12
MONTHS = []
for year in [2019, 2020]:
    start_m = 9 if year == 2019 else 1
    end_m = 12
    for m in range(start_m, end_m + 1):
        MONTHS.append(f"{year}-{m:02d}")

TIMEFRAMES = ["1h", "4h"]

# Binance Vision CSV column order
# 0: open_time, 1: open, 2: high, 3: low, 4: close, 5: volume,
# 6: close_time, 7: quote_volume, 8: trades, 9: taker_buy_base_volume,
# 10: taker_buy_quote_volume, 11: ignore
CSV_OPEN_TIME = 0
CSV_OPEN = 1
CSV_HIGH = 2
CSV_LOW = 3
CSV_CLOSE = 4
CSV_VOLUME = 5
CSV_CLOSE_TIME = 6
CSV_QUOTE_VOLUME = 7
CSV_TRADES = 8

SYMBOL = "ETH/USDT:USDT"


def download_monthly(tf: str, month: str) -> str | None:
    """Download a monthly kline ZIP file. Returns local path or None."""
    filename = f"ETHUSDT-{tf}-{month}.zip"
    local_path = os.path.join(DOWNLOAD_DIR, filename)

    if os.path.exists(local_path):
        print(f"  [SKIP] Already downloaded: {filename}")
        return local_path

    # Try CDN URL first, fall back to S3 direct URL
    urls = [
        f"{BASE_URL}/{tf}/{filename}",
        f"{S3_BASE_URL}/{tf}/{filename}",
    ]

    for url in urls:
        print(f"  [GET] {url}")
        resp = requests.get(url, timeout=60)
        if resp.status_code == 200 and len(resp.content) > 1000:
            # Verify it's a valid ZIP (not an XML error page)
            if resp.content[:2] == b'PK':
                with open(local_path, "wb") as f:
                    f.write(resp.content)
                print(f"  [OK] Saved {filename} ({len(resp.content):,} bytes)")
                return local_path
            else:
                print(f"  [SKIP] Response is not a valid ZIP (starts with {resp.content[:20]})")
                continue
        else:
            print(f"  [FAIL] HTTP {resp.status_code} for {filename}")

    print(f"  [FAIL] Could not download {filename} from any source")
    return None


def parse_zip(zip_path: str) -> list[dict]:
    """Parse a Binance Vision monthly kline ZIP file into row dicts."""
    rows = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if not name.endswith(".csv"):
                continue
            with zf.open(name) as csvfile:
                reader = csv.reader(io.TextIOWrapper(csvfile, "utf-8"))
                for row in reader:
                    if len(row) < 9:
                        continue
                    open_time_ms = int(row[CSV_OPEN_TIME])
                    rows.append({
                        "symbol": SYMBOL,
                        "timeframe": None,  # set by caller
                        "timestamp": open_time_ms,
                        "open": row[CSV_OPEN],
                        "high": row[CSV_HIGH],
                        "low": row[CSV_LOW],
                        "close": row[CSV_CLOSE],
                        "volume": row[CSV_VOLUME],
                        "is_closed": 1,
                        "created_at": int(datetime.now(timezone.utc).timestamp() * 1000),
                    })
    return rows


def import_rows(rows: list[dict], timeframe: str) -> int:
    """Insert rows into SQLite. Returns count of inserted rows."""
    import sqlite3

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    inserted = 0
    for r in rows:
        r["timeframe"] = timeframe
        try:
            cur.execute("""
                INSERT INTO klines (symbol, timeframe, timestamp, open, high, low, close, volume, is_closed, created_at)
                VALUES (:symbol, :timeframe, :timestamp, :open, :high, :low, :close, :volume, :is_closed, :created_at)
                ON CONFLICT (symbol, timeframe, timestamp) DO NOTHING
            """, r)
            if cur.rowcount > 0:
                inserted += 1
        except Exception as e:
            print(f"  [ERR] Insert failed for ts={r['timestamp']}: {e}")
            conn.rollback()
            raise

    conn.commit()
    conn.close()
    return inserted


def main():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    total_inserted = 0
    download_log = []

    for tf in TIMEFRAMES:
        print(f"\n=== Timeframe: {tf} ===")
        for month in MONTHS:
            print(f"\nMonth: {month}")
            zip_path = download_monthly(tf, month)
            if zip_path is None:
                download_log.append((tf, month, "DOWNLOAD_FAILED", 0, 0))
                continue

            rows = parse_zip(zip_path)
            print(f"  Parsed {len(rows)} rows from {month}")
            if not rows:
                download_log.append((tf, month, "EMPTY_FILE", 0, 0))
                continue

            inserted = import_rows(rows, tf)
            print(f"  Inserted {inserted}/{len(rows)} rows")
            total_inserted += inserted
            download_log.append((tf, month, "OK", len(rows), inserted))

    print(f"\n=== Import Complete ===")
    print(f"Total inserted: {total_inserted}")
    print(f"\nDownload/Import Log:")
    print(f"{'TF':<4} {'Month':<10} {'Status':<18} {'Parsed':>8} {'Inserted':>8}")
    print("-" * 52)
    for tf, month, status, parsed, inserted in download_log:
        print(f"{tf:<4} {month:<10} {status:<18} {parsed:>8} {inserted:>8}")

    # Verify
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for tf in TIMEFRAMES:
        cur.execute("""
            SELECT COUNT(*), MIN(timestamp), MAX(timestamp)
            FROM klines
            WHERE symbol = ? AND timeframe = ? AND timestamp < 1609459200000
        """, (SYMBOL, tf))
        cnt, min_ts, max_ts = cur.fetchone()
        min_dt = datetime.fromtimestamp(min_ts / 1000, tz=timezone.utc).isoformat() if min_ts else "N/A"
        max_dt = datetime.fromtimestamp(max_ts / 1000, tz=timezone.utc).isoformat() if max_ts else "N/A"
        print(f"\nPost-import {tf}: {cnt} rows, {min_dt} to {max_dt}")
    conn.close()


if __name__ == "__main__":
    main()
