#!/usr/bin/env python3
"""1D Spot Trend Robustness Diagnostic backtest.

Frozen rule (from one-day-spot-trend-vs-buy-hold-benchmark.md):
- Entry: daily close > highest close of prior 20 closed daily bars
- Entry execution: next daily open + 0.1% entry slippage
- Initial stop: previous 20 closed daily bar low (signal bar excluded)
- Exit: fully closed daily candle closes below EMA60
- Exit execution: next daily open - 0.1% exit slippage
- Costs: 0.1% fee per side, 0.1% entry slippage, 0.1% exit slippage
- Long-only, no leverage, no funding (spot proxy)
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

DB_V3 = os.path.join(os.path.dirname(__file__), "..", "data", "v3_dev.db")
DB_MARKET = os.path.join(os.path.dirname(__file__), "..", "data", "backtests", "market_data.db")

FEE_RATE = 0.001  # 0.1% per side
ENTRY_SLIP = 0.001
EXIT_SLIP = 0.001
DONCHIAN_LEN = 20
EMA_LEN = 60
INITIAL_CAPITAL = 30000.0


def load_daily_klines(symbol: str, db_path: str) -> list[dict]:
    """Load daily klines from a database, returning sorted list of dicts."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT timestamp, open, high, low, close, volume "
        "FROM klines WHERE symbol=? AND timeframe='1d' AND is_closed=1 "
        "ORDER BY timestamp",
        (symbol,),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        result.append({
            "ts": r["timestamp"],
            "dt": datetime.fromtimestamp(r["timestamp"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "volume": float(r["volume"]),
        })
    return result


def load_all_daily(symbol: str) -> list[dict]:
    """Load daily klines, trying market_data.db first, then v3_dev.db."""
    rows = load_daily_klines(symbol, DB_MARKET)
    if len(rows) >= 365:
        return rows
    rows_v3 = load_daily_klines(symbol, DB_V3)
    if len(rows_v3) > len(rows):
        return rows_v3
    return rows


def ema(values: list[float], period: int) -> list[float | None]:
    """Compute EMA over a list of values. Returns None for insufficient warmup."""
    result = [None] * len(values)
    if len(values) < period:
        return result
    seed = sum(values[:period]) / period
    result[period - 1] = seed
    k = 2.0 / (period + 1)
    for i in range(period, len(values)):
        result[i] = values[i] * k + result[i - 1] * (1 - k)
    return result


def run_1d_spot_trend(klines: list[dict], initial_capital: float = INITIAL_CAPITAL) -> dict:
    """Run the frozen 1D spot trend backtest on daily klines.

    Signal logic:
    - Signal on bar i-1: closes[i-1] > max(closes[i-1-20 : i-1])
    - Entry on bar i: open[i] with slippage + fee
    - Stop: min(lows[i-1-20 : i-1]) (signal bar excluded)
    - Exit: when bar i-1 close < ema60[i-1], exit on bar i open
    """
    n = len(klines)
    if n < EMA_LEN + DONCHIAN_LEN + 5:
        return {"error": "insufficient data", "bars": n}

    closes = [k["close"] for k in klines]
    opens = [k["open"] for k in klines]
    lows = [k["low"] for k in klines]

    ema60 = ema(closes, EMA_LEN)

    capital = initial_capital
    position = 0.0
    entry_price = 0.0
    stop_price = 0.0
    in_position = False
    pending_entry_date = None

    completed_trades = []
    equity_curve = []
    peak_capital = initial_capital
    max_dd = 0.0
    time_in_market_bars = 0

    start_bar = EMA_LEN + DONCHIAN_LEN

    for i in range(start_bar, n):
        bar = klines[i]
        dt = bar["dt"]
        o, h, l, c = bar["open"], bar["high"], bar["low"], bar["close"]

        # --- EXIT CHECK (on bar i, based on bar i-1's close) ---
        if in_position:
            exited = False
            # EMA60 close-break exit: bar i-1's close < ema60[i-1]
            if ema60[i - 1] is not None and closes[i - 1] < ema60[i - 1]:
                exit_price = o * (1 - EXIT_SLIP) * (1 - FEE_RATE)
                pnl = (exit_price - entry_price) * position
                capital += position * exit_price
                completed_trades.append({
                    "entry_date": pending_entry_date or dt,
                    "exit_date": dt,
                    "entry_price": round(entry_price, 8),
                    "exit_price": round(exit_price, 8),
                    "pnl": round(pnl, 2),
                    "exit_reason": "ema60_close_break",
                })
                position = 0.0
                in_position = False
                exited = True

            # Initial stop check (if not already exited)
            if not exited and l <= stop_price:
                exit_price = stop_price * (1 - EXIT_SLIP) * (1 - FEE_RATE)
                pnl = (exit_price - entry_price) * position
                capital += position * exit_price
                completed_trades.append({
                    "entry_date": pending_entry_date or dt,
                    "exit_date": dt,
                    "entry_price": round(entry_price, 8),
                    "exit_price": round(exit_price, 8),
                    "pnl": round(pnl, 2),
                    "exit_reason": "initial_stop",
                })
                position = 0.0
                in_position = False

        # --- ENTRY CHECK (on bar i, based on bar i-1's close) ---
        if not in_position and i >= 1:
            # Signal: bar i-1's close > highest close of bars [i-1-20, i-1)
            if i - 1 >= DONCHIAN_LEN:
                lookback = closes[i - 1 - DONCHIAN_LEN : i - 1]
                if len(lookback) == DONCHIAN_LEN:
                    highest_prior = max(lookback)
                    if closes[i - 1] > highest_prior:
                        # Enter at bar i's open
                        entry_price = o * (1 + ENTRY_SLIP) * (1 + FEE_RATE)
                        units = capital / entry_price
                        position = units
                        capital = 0.0
                        in_position = True
                        pending_entry_date = dt

                        # Stop: min of lows[i-1-20 : i-1) (signal bar i-1 excluded)
                        stop_lookback = lows[i - 1 - DONCHIAN_LEN : i - 1]
                        stop_price = min(stop_lookback) if stop_lookback else l * 0.95

        # Track equity
        mtm = position * c if in_position else capital
        equity_curve.append({"dt": dt, "equity": mtm})
        if mtm > peak_capital:
            peak_capital = mtm
        dd = (peak_capital - mtm) / peak_capital if peak_capital > 0 else 0
        if dd > max_dd:
            max_dd = dd
        if in_position:
            time_in_market_bars += 1

    # Close remaining position at last bar's close
    if in_position and n > 0:
        last_close = closes[-1] * (1 - EXIT_SLIP) * (1 - FEE_RATE)
        pnl = (last_close - entry_price) * position
        capital += position * last_close
        completed_trades.append({
            "entry_date": pending_entry_date or klines[-1]["dt"],
            "exit_date": klines[-1]["dt"],
            "entry_price": round(entry_price, 8),
            "exit_price": round(last_close, 8),
            "pnl": round(pnl, 2),
            "exit_reason": "end_of_data",
        })
        position = 0.0

    # Compute metrics
    winners = [t for t in completed_trades if t["pnl"] > 0]
    losers = [t for t in completed_trades if t["pnl"] <= 0]
    gross_profit = sum(t["pnl"] for t in winners)
    gross_loss = abs(sum(t["pnl"] for t in losers))
    net_pnl = sum(t["pnl"] for t in completed_trades)
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    total_bars = n - start_bar
    time_pct = time_in_market_bars / total_bars if total_bars > 0 else 0

    sorted_trades = sorted(completed_trades, key=lambda t: t["pnl"], reverse=True)
    top1_pnl = sorted_trades[0]["pnl"] if len(sorted_trades) >= 1 else 0
    top3_pnl = sum(t["pnl"] for t in sorted_trades[:3])
    top5_pnl = sum(t["pnl"] for t in sorted_trades[:5])

    # CAGR and Calmar
    years_span = (klines[-1]["ts"] - klines[start_bar]["ts"]) / (365.25 * 24 * 3600 * 1000)
    cagr = ((initial_capital + net_pnl) / initial_capital) ** (1 / years_span) - 1 if years_span > 0 else 0
    calmar = cagr / max_dd if max_dd > 0 else float("inf")

    return {
        "trades": len(completed_trades),
        "winners": len(winners),
        "losers": len(losers),
        "win_rate": round(len(winners) / len(completed_trades), 4) if completed_trades else 0,
        "net_pnl": round(net_pnl, 2),
        "return_pct": round(net_pnl / initial_capital, 4),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "pf": round(pf, 3),
        "max_dd_pct": round(max_dd, 4),
        "cagr": round(cagr, 4),
        "calmar": round(calmar, 3),
        "time_in_market_pct": round(time_pct, 4),
        "top1_pnl": round(top1_pnl, 2),
        "top3_pnl": round(top3_pnl, 2),
        "top5_pnl": round(top5_pnl, 2),
        "top1_pct_of_net": round(top1_pnl / net_pnl, 4) if net_pnl > 0 else None,
        "top3_pct_of_net": round(top3_pnl / net_pnl, 4) if net_pnl > 0 else None,
        "top5_pct_of_net": round(top5_pnl / net_pnl, 4) if net_pnl > 0 else None,
        "ex_top1_net": round(net_pnl - top1_pnl, 2),
        "ex_top3_net": round(net_pnl - top3_pnl, 2),
        "ex_top5_net": round(net_pnl - top5_pnl, 2),
        "capital_final": round(capital, 2),
        "bars": n,
        "start_date": klines[start_bar]["dt"],
        "end_date": klines[-1]["dt"],
        "trades_detail": completed_trades,
    }


def run_buy_and_hold(klines: list[dict], initial_capital: float = INITIAL_CAPITAL) -> dict:
    """Simple buy-and-hold benchmark."""
    if len(klines) < 2:
        return {"error": "insufficient data"}
    entry_price = klines[0]["open"] * (1 + ENTRY_SLIP) * (1 + FEE_RATE)
    exit_price = klines[-1]["close"] * (1 - EXIT_SLIP) * (1 - FEE_RATE)
    units = initial_capital / entry_price
    final = units * exit_price
    net = final - initial_capital

    peak = initial_capital
    max_dd = 0.0
    for k in klines:
        mtm = units * k["close"]
        if mtm > peak:
            peak = mtm
        dd = (peak - mtm) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    years_span = (klines[-1]["ts"] - klines[0]["ts"]) / (365.25 * 24 * 3600 * 1000)
    cagr = (final / initial_capital) ** (1 / years_span) - 1 if years_span > 0 else 0
    calmar = cagr / max_dd if max_dd > 0 else float("inf")

    return {
        "net_pnl": round(net, 2),
        "return_pct": round(net / initial_capital, 4),
        "max_dd_pct": round(max_dd, 4),
        "cagr": round(cagr, 4),
        "calmar": round(calmar, 3),
        "capital_final": round(final, 2),
        "start_date": klines[0]["dt"],
        "end_date": klines[-1]["dt"],
    }


def filter_by_date(klines: list[dict], start: str, end: str) -> list[dict]:
    return [k for k in klines if start <= k["dt"] <= end]


def yearly_breakdown(klines: list[dict]) -> dict:
    years = {}
    for k in klines:
        y = k["dt"][:4]
        years.setdefault(y, []).append(k)
    return years


def make_basket(labels: list[str], per_asset: dict, period_key: str, capital: float = INITIAL_CAPITAL) -> dict:
    """Compute equal-weight basket metrics from per-asset results."""
    n_assets = len(labels)
    sub_cap = capital / n_assets
    total_net = 0.0
    total_trades = 0
    total_winners = 0
    all_ok = True
    for label in labels:
        r = per_asset.get(label, {})
        pr = r.get(period_key, {})
        if "return_pct" in pr:
            total_net += sub_cap * pr["return_pct"]
            total_trades += pr.get("trades", 0)
            total_winners += pr.get("winners", 0)
        else:
            all_ok = False
    if not all_ok:
        return {"error": "missing data for one or more assets"}
    return {
        "net_pnl": round(total_net, 2),
        "return_pct": round(total_net / capital, 4),
        "trades": total_trades,
        "winners": total_winners,
    }


def make_basket_yearly(labels: list[str], per_asset: dict, capital: float = INITIAL_CAPITAL) -> dict:
    """Compute equal-weight basket yearly metrics."""
    n_assets = len(labels)
    sub_cap = capital / n_assets
    result = {}
    for year in ["2021", "2022", "2023", "2024", "2025"]:
        total_net = 0.0
        total_trades = 0
        has_data = False
        for label in labels:
            r = per_asset.get(label, {})
            yr = r.get("yearly", {}).get(year, {}).get("trend", {})
            if "return_pct" in yr:
                total_net += sub_cap * yr["return_pct"]
                total_trades += yr.get("trades", 0)
                has_data = True
        if has_data:
            result[year] = {
                "net_pnl": round(total_net, 2),
                "return_pct": round(total_net / capital, 4),
                "trades": total_trades,
            }
    return result


def main():
    symbols = {"BTC": "BTC/USDT:USDT", "ETH": "ETH/USDT:USDT", "SOL": "SOL/USDT:USDT"}

    IS_START, IS_END = "2021-01-01", "2023-12-31"
    OOS_START, OOS_END = "2024-01-01", "2025-12-31"
    FW_START, FW_END = "2021-01-01", "2025-12-31"

    all_data = {}
    for label, sym in symbols.items():
        rows = load_all_daily(sym)
        all_data[label] = rows
        print(f"{label}: {len(rows)} bars, {rows[0]['dt'] if rows else 'N/A'} to {rows[-1]['dt'] if rows else 'N/A'}")

    results = {}

    for label in ["BTC", "ETH", "SOL"]:
        klines = all_data[label]
        data_start = klines[0]["dt"] if klines else "N/A"
        data_end = klines[-1]["dt"] if klines else "N/A"

        fw = filter_by_date(klines, FW_START, FW_END)
        is_data = filter_by_date(klines, IS_START, IS_END)
        oos_data = filter_by_date(klines, OOS_START, OOS_END)

        print(f"\n=== {label} ===")
        print(f"  Data: {data_start} to {data_end} ({len(klines)} bars)")
        print(f"  FW 2021-2025: {len(fw)} bars")
        print(f"  IS 2021-2023: {len(is_data)} bars")
        print(f"  OOS 2024-2025: {len(oos_data)} bars")

        r = {"data_start": data_start, "data_end": data_end, "bars_total": len(klines)}

        min_bars = EMA_LEN + DONCHIAN_LEN + 5

        if len(fw) >= min_bars:
            r["full_window"] = run_1d_spot_trend(fw)
            r["buy_hold_fw"] = run_buy_and_hold(fw)
        else:
            r["full_window"] = {"error": f"insufficient: {len(fw)} bars"}

        if len(is_data) >= min_bars:
            r["is"] = run_1d_spot_trend(is_data)
            r["buy_hold_is"] = run_buy_and_hold(is_data)
        else:
            r["is"] = {"error": f"insufficient: {len(is_data)} bars"}

        if len(oos_data) >= min_bars:
            r["oos"] = run_1d_spot_trend(oos_data)
            r["buy_hold_oos"] = run_buy_and_hold(oos_data)
        else:
            r["oos"] = {"error": f"insufficient: {len(oos_data)} bars"}

        # Yearly
        yearly = yearly_breakdown(klines)
        r["yearly"] = {}
        for year, yklines in sorted(yearly.items()):
            yi = int(year)
            if 2021 <= yi <= 2025 and len(yklines) >= min_bars:
                r["yearly"][year] = {
                    "trend": run_1d_spot_trend(yklines),
                    "buy_hold": run_buy_and_hold(yklines),
                }

        results[label] = r

    # Baskets
    for basket_name, basket_labels in [("BTC+ETH", ["BTC", "ETH"]), ("BTC+ETH+SOL", ["BTC", "ETH", "SOL"])]:
        br = {}
        br["full_window"] = make_basket(basket_labels, results, "full_window")
        br["is"] = make_basket(basket_labels, results, "is")
        br["oos"] = make_basket(basket_labels, results, "oos")
        br["yearly"] = make_basket_yearly(basket_labels, results)

        # Buy-and-hold baskets
        fw_klines = {l: filter_by_date(all_data[l], FW_START, FW_END) for l in basket_labels}
        is_klines = {l: filter_by_date(all_data[l], IS_START, IS_END) for l in basket_labels}
        oos_klines = {l: filter_by_date(all_data[l], OOS_START, OOS_END) for l in basket_labels}

        sub_cap = INITIAL_CAPITAL / len(basket_labels)

        def bh_basket_simple(klines_dict):
            total_net_pnl = 0.0
            for l in basket_labels:
                kl = klines_dict.get(l, [])
                if len(kl) >= 2:
                    bh = run_buy_and_hold(kl)
                    # Each asset gets sub_cap of the total capital
                    total_net_pnl += sub_cap * bh["return_pct"]
            return {
                "net_pnl": round(total_net_pnl, 2),
                "return_pct": round(total_net_pnl / INITIAL_CAPITAL, 4),
            }

        br["buy_hold_fw"] = bh_basket_simple(fw_klines)
        br["buy_hold_is"] = bh_basket_simple(is_klines)
        br["buy_hold_oos"] = bh_basket_simple(oos_klines)

        results[basket_name] = br

    # Ex-SOL alias
    results["ex_SOL"] = results["BTC+ETH"]
    results["ex_SOL_bh_fw"] = results["BTC+ETH"]["buy_hold_fw"]

    # Clean for JSON
    def clean(obj):
        if isinstance(obj, dict):
            return {k: clean(v) for k, v in obj.items() if k != "trades_detail"}
        elif isinstance(obj, list):
            return [clean(x) for x in obj]
        return obj

    out_dir = os.path.join(os.path.dirname(__file__), "..", "reports", "one-day-spot-trend-robustness")
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(out_dir, "results.json"), "w") as f:
        json.dump(clean(results), f, indent=2, default=str)

    with open(os.path.join(out_dir, "results_full.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)

    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for key in ["BTC", "ETH", "SOL", "BTC+ETH", "BTC+ETH+SOL"]:
        r = results[key]
        print(f"\n--- {key} ---")
        for period in ["full_window", "is", "oos"]:
            pr = r.get(period, {})
            if "error" in pr:
                print(f"  {period}: {pr['error']}")
            else:
                print(f"  {period}: trades={pr.get('trades')}, net={pr.get('net_pnl')}, "
                      f"ret={pr.get('return_pct')}, dd={pr.get('max_dd_pct')}, "
                      f"pf={pr.get('pf')}, winrate={pr.get('win_rate')}")
        yr = r.get("yearly", {})
        if yr:
            for y in sorted(yr.keys()):
                yt = yr[y].get("trend", yr[y])
                print(f"  {y}: net={yt.get('net_pnl')}, ret={yt.get('return_pct')}")

    print(f"\nResults saved to {out_dir}")


if __name__ == "__main__":
    main()
