#!/usr/bin/env python3
"""TE-005 QA: Comprehensive QA checks on imported pre-2021 ETH kline data."""
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from decimal import Decimal

DB_PATH = "data/v3_dev.db"
SYMBOL = "ETH/USDT:USDT"
PRE2021_MS = 1609459200000  # 2021-01-01 00:00:00 UTC

# Contract launch: 2019-09-25 08:00:00 UTC
CONTRACT_LAUNCH_MS = 1569398400000


def get_conn():
    return sqlite3.connect(DB_PATH)


def ts_to_dt(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def qa_candle_count(cur):
    """5.1 Candle count: expected vs actual."""
    print("\n=== QA 5.1: Candle Count ===")
    results = {}

    for tf in ["1h", "4h"]:
        interval_ms = 3600000 if tf == "1h" else 14400000
        candles_per_day = 86400000 // interval_ms

        cur.execute("""
            SELECT MIN(timestamp), MAX(timestamp), COUNT(*)
            FROM klines
            WHERE symbol = ? AND timeframe = ? AND timestamp < ?
        """, (SYMBOL, tf, PRE2021_MS))
        min_ts, max_ts, actual = cur.fetchone()

        if min_ts is None:
            print(f"  {tf}: NO DATA")
            results[tf] = {"actual": 0, "expected": 0, "delta": 0}
            continue

        # Expected: from first candle to last candle, inclusive
        span_ms = max_ts - min_ts
        expected = (span_ms // interval_ms) + 1
        delta = expected - actual

        print(f"  {tf}:")
        print(f"    Range: {ts_to_dt(min_ts)} to {ts_to_dt(max_ts)}")
        print(f"    Expected: {expected}, Actual: {actual}, Delta: {delta}")
        results[tf] = {"actual": actual, "expected": expected, "delta": delta,
                        "min_ts": min_ts, "max_ts": max_ts}

    return results


def qa_missing_timestamps(cur):
    """5.2 Missing timestamps."""
    print("\n=== QA 5.2: Missing Timestamps ===")
    results = {}

    for tf in ["1h", "4h"]:
        interval_ms = 3600000 if tf == "1h" else 14400000

        cur.execute("""
            SELECT timestamp FROM klines
            WHERE symbol = ? AND timeframe = ? AND timestamp < ?
            ORDER BY timestamp
        """, (SYMBOL, tf, PRE2021_MS))
        rows = cur.fetchall()
        if not rows:
            print(f"  {tf}: NO DATA")
            results[tf] = {"missing_count": 0, "missing": []}
            continue

        existing = set(r[0] for r in rows)
        min_ts = rows[0][0]
        max_ts = rows[-1][0]

        # Align start to interval boundary
        start = min_ts
        missing = []
        ts = start
        while ts <= max_ts:
            if ts not in existing:
                missing.append(ts)
            ts += interval_ms

        print(f"  {tf}:")
        print(f"    Missing timestamps: {len(missing)}")
        if missing:
            # Classify gaps
            gaps = []
            gap_start = None
            for i, m in enumerate(missing):
                if gap_start is None:
                    gap_start = m
                if i + 1 >= len(missing) or missing[i + 1] - m != interval_ms:
                    gap_end = m
                    gap_len = ((gap_end - gap_start) // interval_ms) + 1
                    gaps.append({
                        "start": ts_to_dt(gap_start).isoformat(),
                        "end": ts_to_dt(gap_end).isoformat(),
                        "candles": gap_len,
                    })
                    gap_start = None

            print(f"    Gap count: {len(gaps)}")
            for g in gaps:
                print(f"      {g['start']} to {g['end']} ({g['candles']} candles)")
        results[tf] = {"missing_count": len(missing), "missing": missing, "gaps": gaps if missing else []}

    return results


def qa_duplicates(cur):
    """5.3 Duplicates."""
    print("\n=== QA 5.3: Duplicates ===")
    results = {}

    for tf in ["1h", "4h"]:
        cur.execute("""
            SELECT timestamp, COUNT(*) as cnt
            FROM klines
            WHERE symbol = ? AND timeframe = ? AND timestamp < ?
            GROUP BY timestamp
            HAVING cnt > 1
        """, (SYMBOL, tf, PRE2021_MS))
        dupes = cur.fetchall()
        print(f"  {tf}: {len(dupes)} duplicate timestamps")
        if dupes:
            for ts, cnt in dupes[:10]:
                print(f"    ts={ts_to_dt(ts).isoformat()} count={cnt}")
        results[tf] = {"duplicate_count": len(dupes), "duplicates": dupes}

    return results


def qa_unexpected_intervals(cur):
    """5.4 Unexpected intervals."""
    print("\n=== QA 5.4: Unexpected Intervals ===")
    results = {}

    for tf in ["1h", "4h"]:
        expected_interval = 3600000 if tf == "1h" else 14400000

        cur.execute("""
            SELECT a.timestamp, b.timestamp, (b.timestamp - a.timestamp) as diff
            FROM klines a
            JOIN klines b ON a.symbol = b.symbol AND a.timeframe = b.timeframe
                AND b.timestamp > a.timestamp
            WHERE a.symbol = ? AND a.timeframe = ? AND a.timestamp < ?
                AND b.timestamp < ?
            ORDER BY a.timestamp
            LIMIT 1
        """, (SYMBOL, tf, PRE2021_MS, PRE2021_MS))

        # Better approach: get all timestamps sorted, check consecutive diffs
        cur.execute("""
            SELECT timestamp FROM klines
            WHERE symbol = ? AND timeframe = ? AND timestamp < ?
            ORDER BY timestamp
        """, (SYMBOL, tf, PRE2021_MS))
        rows = cur.fetchall()
        if len(rows) < 2:
            print(f"  {tf}: Not enough data")
            results[tf] = {"anomaly_count": 0, "anomalies": []}
            continue

        anomalies = []
        for i in range(1, len(rows)):
            diff = rows[i][0] - rows[i - 1][0]
            if diff != expected_interval:
                anomalies.append({
                    "prev": ts_to_dt(rows[i - 1][0]).isoformat(),
                    "next": ts_to_dt(rows[i][0]).isoformat(),
                    "diff_hours": diff / 3600000,
                })

        print(f"  {tf}: {len(anomalies)} unexpected intervals")
        for a in anomalies[:20]:
            print(f"    {a['prev']} -> {a['next']} (diff={a['diff_hours']}h)")
        results[tf] = {"anomaly_count": len(anomalies), "anomalies": anomalies}

    return results


def qa_is_closed(cur):
    """5.5 is_closed coverage."""
    print("\n=== QA 5.5: is_closed ===")
    results = {}

    for tf in ["1h", "4h"]:
        cur.execute("""
            SELECT COUNT(*) FROM klines
            WHERE symbol = ? AND timeframe = ? AND timestamp < ?
                AND is_closed != 1
        """, (SYMBOL, tf, PRE2021_MS))
        violations = cur.fetchone()[0]
        print(f"  {tf}: {violations} rows with is_closed != True")
        results[tf] = {"violations": violations}

    return results


def qa_ohlc_validity(cur):
    """5.6 OHLC validity."""
    print("\n=== QA 5.6: OHLC Validity ===")
    results = {}

    for tf in ["1h", "4h"]:
        # high >= low
        cur.execute("""
            SELECT COUNT(*) FROM klines
            WHERE symbol = ? AND timeframe = ? AND timestamp < ?
                AND CAST(high AS REAL) < CAST(low AS REAL)
        """, (SYMBOL, tf, PRE2021_MS))
        high_low_violations = cur.fetchone()[0]

        # open/close within range
        cur.execute("""
            SELECT COUNT(*) FROM klines
            WHERE symbol = ? AND timeframe = ? AND timestamp < ?
                AND (CAST(open AS REAL) < CAST(low AS REAL)
                     OR CAST(open AS REAL) > CAST(high AS REAL)
                     OR CAST(close AS REAL) < CAST(low AS REAL)
                     OR CAST(close AS REAL) > CAST(high AS REAL))
        """, (SYMBOL, tf, PRE2021_MS))
        range_violations = cur.fetchone()[0]

        # positive prices
        cur.execute("""
            SELECT COUNT(*) FROM klines
            WHERE symbol = ? AND timeframe = ? AND timestamp < ?
                AND (CAST(open AS REAL) <= 0 OR CAST(high AS REAL) <= 0
                     OR CAST(low AS REAL) <= 0 OR CAST(close AS REAL) <= 0)
        """, (SYMBOL, tf, PRE2021_MS))
        positive_violations = cur.fetchone()[0]

        # non-negative volume
        cur.execute("""
            SELECT COUNT(*) FROM klines
            WHERE symbol = ? AND timeframe = ? AND timestamp < ?
                AND CAST(volume AS REAL) < 0
        """, (SYMBOL, tf, PRE2021_MS))
        volume_violations = cur.fetchone()[0]

        total = sum([high_low_violations, range_violations, positive_violations, volume_violations])
        print(f"  {tf}:")
        print(f"    high < low: {high_low_violations}")
        print(f"    open/close out of range: {range_violations}")
        print(f"    non-positive prices: {positive_violations}")
        print(f"    negative volume: {volume_violations}")
        print(f"    Total OHLC violations: {total}")
        results[tf] = {
            "high_low_violations": high_low_violations,
            "range_violations": range_violations,
            "positive_violations": positive_violations,
            "volume_violations": volume_violations,
            "total_violations": total,
        }

    return results


def qa_symbol_mapping(cur):
    """5.7 Symbol mapping."""
    print("\n=== QA 5.7: Symbol Mapping ===")
    cur.execute("""
        SELECT DISTINCT symbol FROM klines
        WHERE timestamp < ? AND timeframe IN ('1h', '4h')
            AND symbol LIKE '%ETH%'
    """, (PRE2021_MS,))
    symbols = [r[0] for r in cur.fetchall()]
    print(f"  ETH symbols in pre-2021 data: {symbols}")
    correct = SYMBOL in symbols
    wrong = [s for s in symbols if s != SYMBOL]
    print(f"  Correct symbol present: {correct}")
    if wrong:
        print(f"  Unexpected symbols: {wrong}")
    return {"symbols": symbols, "correct": correct, "wrong": wrong}


def qa_1h_4h_alignment(cur):
    """5.8 1h/4h alignment."""
    print("\n=== QA 5.8: 1h/4h Alignment ===")
    results = {}

    # Every 4h timestamp must align to a 1h timestamp that is a multiple of 4h from UTC midnight
    cur.execute("""
        SELECT timestamp FROM klines
        WHERE symbol = ? AND timeframe = '4h' AND timestamp < ?
        ORDER BY timestamp
    """, (SYMBOL, PRE2021_MS))
    four_h_rows = cur.fetchall()

    misaligned = []
    for (ts,) in four_h_rows:
        # 4h timestamps should be at 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC
        hour = (ts // 3600000) % 24
        if hour % 4 != 0:
            misaligned.append(ts_to_dt(ts).isoformat())

    print(f"  4h timestamps not aligned to 4h boundary: {len(misaligned)}")
    for m in misaligned[:10]:
        print(f"    {m}")

    # For every 4h candle, the corresponding four 1h candles must exist
    missing_1h = []
    for (ts_4h,) in four_h_rows:
        for offset in range(4):
            ts_1h = ts_4h + offset * 3600000
            cur.execute("""
                SELECT COUNT(*) FROM klines
                WHERE symbol = ? AND timeframe = '1h' AND timestamp = ?
            """, (SYMBOL, ts_1h))
            if cur.fetchone()[0] == 0:
                missing_1h.append(ts_to_dt(ts_1h).isoformat())

    print(f"  1h candles missing for 4h alignment: {len(missing_1h)}")
    for m in missing_1h[:10]:
        print(f"    {m}")

    results = {
        "misaligned_4h": len(misaligned),
        "missing_1h_for_4h": len(missing_1h),
        "misaligned_list": misaligned[:20],
        "missing_1h_list": missing_1h[:20],
    }
    return results


def qa_warmup(cur):
    """5.9 Indicator warmup."""
    print("\n=== QA 5.9: Indicator Warmup ===")
    # EMA60 on 4h needs 60 candles = 10 days
    # Donchian20 on 4h needs 20 candles ≈ 3.3 days
    # Combined: EMA60 dominates, need 60 4h candles before first signal

    cur.execute("""
        SELECT timestamp FROM klines
        WHERE symbol = ? AND timeframe = '4h' AND timestamp < ?
        ORDER BY timestamp
        LIMIT 1
    """, (SYMBOL, PRE2021_MS))
    first_4h = cur.fetchone()
    if first_4h is None:
        print("  No 4h data available")
        return {"first_signal_dt": None, "warmup_sufficient": False}

    first_ts = first_4h[0]
    # First evaluable signal = first_ts + 60 * 4h
    warmup_ms = 60 * 14400000  # 60 * 4h in ms
    first_signal_ts = first_ts + warmup_ms
    first_signal_dt = ts_to_dt(first_signal_ts)

    # Check we have 60 4h candles from start
    cur.execute("""
        SELECT COUNT(*) FROM klines
        WHERE symbol = ? AND timeframe = '4h' AND timestamp < ?
            AND timestamp <= ?
    """, (SYMBOL, PRE2021_MS, first_signal_ts))
    candles_before_signal = cur.fetchone()[0]

    warmup_sufficient = candles_before_signal >= 60

    print(f"  First 4h candle: {ts_to_dt(first_ts).isoformat()}")
    print(f"  First evaluable signal (after EMA60 warmup): {first_signal_dt.isoformat()}")
    print(f"  4h candles before first signal: {candles_before_signal}")
    print(f"  Warmup sufficient (>=60): {warmup_sufficient}")

    return {
        "first_4h_candle": ts_to_dt(first_ts).isoformat(),
        "first_signal_dt": first_signal_dt.isoformat(),
        "candles_before_signal": candles_before_signal,
        "warmup_sufficient": warmup_sufficient,
    }


def qa_partial_2019_09(cur):
    """Partial 2019-09 handling."""
    print("\n=== QA: Partial 2019-09 ===")
    # Contract launched 2019-09-25 08:00:00 UTC
    cur.execute("""
        SELECT timestamp FROM klines
        WHERE symbol = ? AND timeframe = '1h' AND timestamp < ?
            AND timestamp >= 1569273600000 AND timestamp < 1569792000000
        ORDER BY timestamp
    """, (SYMBOL, PRE2021_MS))
    sept_rows = cur.fetchall()

    if sept_rows:
        first_ts = sept_rows[0][0]
        last_ts = sept_rows[-1][0]
        print(f"  2019-09 1h data: {len(sept_rows)} rows")
        print(f"  First: {ts_to_dt(first_ts).isoformat()}")
        print(f"  Last: {ts_to_dt(last_ts).isoformat()}")
        print(f"  Contract launch: 2019-09-25T08:00:00+00:00")
        # Check if first candle aligns with contract launch
        first_dt = ts_to_dt(first_ts)
        if first_dt.day >= 25:
            print(f"  2019-09 is a partial month starting {first_dt.strftime('%Y-%m-%d')}")
        else:
            print(f"  WARNING: 2019-09 data starts before contract launch date")
    else:
        print("  No 2019-09 data found")

    return {
        "sept_rows": len(sept_rows) if sept_rows else 0,
        "first_ts": ts_to_dt(sept_rows[0][0]).isoformat() if sept_rows else None,
        "last_ts": ts_to_dt(sept_rows[-1][0]).isoformat() if sept_rows else None,
    }


def main():
    conn = get_conn()
    cur = conn.cursor()

    print("=" * 60)
    print("TE-005 QA Report - Pre-2021 ETH 1h/4h Data")
    print("=" * 60)

    r1 = qa_candle_count(cur)
    r2 = qa_missing_timestamps(cur)
    r3 = qa_duplicates(cur)
    r4 = qa_unexpected_intervals(cur)
    r5 = qa_is_closed(cur)
    r6 = qa_ohlc_validity(cur)
    r7 = qa_symbol_mapping(cur)
    r8 = qa_1h_4h_alignment(cur)
    r9 = qa_warmup(cur)
    r10 = qa_partial_2019_09(cur)

    # Overall QA pass/fail
    print("\n" + "=" * 60)
    print("QA SUMMARY")
    print("=" * 60)

    all_pass = True
    for tf in ["1h", "4h"]:
        print(f"\n  {tf}:")
        c = r1[tf]
        print(f"    Candle count: expected={c['expected']}, actual={c['actual']}, delta={c['delta']} {'PASS' if c['delta'] == 0 else 'FAIL'}")
        if c['delta'] != 0:
            all_pass = False
        m = r2[tf]
        print(f"    Missing timestamps: {m['missing_count']} {'PASS' if m['missing_count'] == 0 else 'FAIL'}")
        if m['missing_count'] > 0:
            all_pass = False
        d = r3[tf]
        print(f"    Duplicates: {d['duplicate_count']} {'PASS' if d['duplicate_count'] == 0 else 'FAIL'}")
        if d['duplicate_count'] > 0:
            all_pass = False
        u = r4[tf]
        print(f"    Unexpected intervals: {u['anomaly_count']} {'PASS' if u['anomaly_count'] == 0 else 'FAIL'}")
        if u['anomaly_count'] > 0:
            all_pass = False
        ic = r5[tf]
        print(f"    is_closed violations: {ic['violations']} {'PASS' if ic['violations'] == 0 else 'FAIL'}")
        if ic['violations'] > 0:
            all_pass = False
        ohlc = r6[tf]
        print(f"    OHLC violations: {ohlc['total_violations']} {'PASS' if ohlc['total_violations'] == 0 else 'FAIL'}")
        if ohlc['total_violations'] > 0:
            all_pass = False

    print(f"\n  Symbol mapping: {'PASS' if r7['correct'] else 'FAIL'}")
    if not r7['correct']:
        all_pass = False
    print(f"  1h/4h alignment: misaligned_4h={r8['misaligned_4h']}, missing_1h={r8['missing_1h_for_4h']} {'PASS' if r8['misaligned_4h'] == 0 and r8['missing_1h_for_4h'] == 0 else 'FAIL'}")
    if r8['misaligned_4h'] > 0 or r8['missing_1h_for_4h'] > 0:
        all_pass = False
    print(f"  Warmup sufficient: {'PASS' if r9['warmup_sufficient'] else 'FAIL'}")
    if not r9['warmup_sufficient']:
        all_pass = False

    print(f"\n  OVERALL: {'ALL QA CHECKS PASSED' if all_pass else 'SOME QA CHECKS FAILED'}")

    conn.close()


if __name__ == "__main__":
    main()
