#!/usr/bin/env python3
"""滑点对比测试 — 悲观(0.1%) vs 真实(0.02%)"""
import asyncio, sys, os, sqlite3, json
from datetime import datetime
from decimal import Decimal
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = "data/v3_dev.db"
OUT_FILE = "/tmp/slippage_compare_result.json"

SLIPPAGE_CONFIGS = [
    {"id": "pessimistic", "slippage": Decimal("0.001"),  "tp_slippage": Decimal("0.0005"), "fee": Decimal("0.0004"),  "label": "悲观(0.1%/0.05%/0.04%)"},
    {"id": "realistic",   "slippage": Decimal("0.0002"), "tp_slippage": Decimal("0.0002"), "fee": Decimal("0.0004"),  "label": "真实(0.02%/0.02%/0.04%)"},
    {"id": "bnb9",        "slippage": Decimal("0.0001"), "tp_slippage": Decimal("0"),      "fee": Decimal("0.000405"),"label": "BNB9折(0.01%/0%/0.0405%)"},
]

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]

YEARS = [
    ("2023", "2023-01-01", "2024-01-01"),
    ("2024", "2024-01-01", "2025-01-01"),
    ("2025", "2025-01-01", "2026-01-01"),
]

MIN_DISTANCE = 0.005
MAX_ATR_RATIO = 0.010


async def run_one(symbol, start, end, slippage, tp_slippage, fee):
    """跑单个币种"""
    from src.infrastructure.historical_data_repository import HistoricalDataRepository
    from src.infrastructure.config_entry_repository import ConfigEntryRepository
    from src.application.backtester import Backtester
    from src.domain.models import BacktestRequest, OrderStrategy
    from src.application.config_manager import ConfigManager

    cm = ConfigManager(DB_PATH)
    await cm.initialize_from_db()
    repo = ConfigEntryRepository(DB_PATH)
    await repo.initialize()
    cm.set_config_entry_repository(repo)

    # 写 KV：关闭 TTP / Trailing Exit / BE=OFF
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    ts = int(datetime.now().timestamp() * 1000)
    for k, v, t in [
        ("backtest.tp_trailing_enabled", "false", "boolean"),
        ("backtest.trailing_exit_enabled", "false", "boolean"),
        ("backtest.breakeven_enabled", "false", "boolean"),
    ]:
        cur.execute("INSERT OR REPLACE INTO config_entries_v2 (config_key,config_value,value_type,version,updated_at,profile_name) VALUES(?,?,?,?,?,?)",
                    (k, v, t, "v1.0.0", ts, "default"))
    conn.commit()
    conn.close()

    filters = [
        {"type": "ema_trend", "enabled": True, "params": {"min_distance_pct": MIN_DISTANCE}},
        {"type": "mtf", "enabled": True, "params": {}},
        {"type": "atr", "enabled": True, "params": {
            "period": 14,
            "min_atr_ratio": 0.001,
            "max_atr_ratio": MAX_ATR_RATIO,
        }},
    ]

    strategies = [{
        "name": "pinbar",
        "triggers": [{"type": "pinbar", "enabled": True}],
        "filters": filters,
    }]

    data_repo = HistoricalDataRepository(DB_PATH)
    await data_repo.initialize()
    bt = Backtester(None, data_repository=data_repo, config_manager=cm)

    st = int(datetime.strptime(start, "%Y-%m-%d").timestamp() * 1000)
    et = int(datetime.strptime(end, "%Y-%m-%d").timestamp() * 1000)

    req = BacktestRequest(
        symbol=symbol, timeframe="1h", limit=30000,
        start_time=st, end_time=et,
        strategies=strategies,
        slippage_rate=slippage,
        tp_slippage_rate=tp_slippage,
        fee_rate=fee,
        order_strategy=OrderStrategy(
            id="sweep", name="Sweep", tp_levels=2,
            tp_ratios=[0.6, 0.4], tp_targets=[1.0, 2.5],
            initial_stop_loss_rr=-1.0,
            trailing_stop_enabled=False, oco_enabled=True,
        ),
        mode="v3_pms",
    )
    report = await bt.run_backtest(req)
    await data_repo.close()

    return {
        "trades": report.total_trades,
        "win_rate": float(report.win_rate),
        "pnl": float(report.total_pnl),
    }


async def main():
    all_results = {}

    for year_label, start, end in YEARS:
        print(f"\n{'#'*60}")
        print(f"#  {year_label} ({start} ~ {end})")
        print(f"{'#'*60}")

        year_data = {}
        for sl_cfg in SLIPPAGE_CONFIGS:
            cfg_id = sl_cfg["id"]
            print(f"\n  {sl_cfg['label']}:")
            cfg_data = {}
            for symbol in SYMBOLS:
                sym_short = symbol.split("/")[0]
                print(f"    {sym_short} ...", end=" ", flush=True)
                r = await run_one(symbol, start, end, sl_cfg["slippage"], sl_cfg["tp_slippage"], sl_cfg["fee"])
                print(f"trades={r['trades']} wr={r['win_rate']:.1%} pnl={r['pnl']:.2f}")
                cfg_data[sym_short] = r
            year_data[cfg_id] = {"config": sl_cfg, "symbols": cfg_data}
        all_results[year_label] = year_data

    # 汇总
    print(f"\n{'='*100}")
    print(f"  滑点对比 — 悲观(0.1%/0.05%) vs 真实(0.02%/0.02%) (Group 2: ATR=1%, BE=OFF)")
    print(f"{'='*100}")

    for cfg_id, label in [("pessimistic", "悲观 0.1%/0.05%/0.04%"), ("realistic", "真实 0.02%/0.02%/0.04%"), ("bnb9", "BNB9折 0.01%/0%/0.0405%")]:
        print(f"\n  --- {label} ---")
        header = f"  {'年份':<6} {'BTC PnL':<12} {'ETH PnL':<12} {'SOL PnL':<12} {'总PnL':<12} {'总Trades':<10}"
        print(header)
        print("  " + "-" * (len(header) - 2))
        for year_label in [y[0] for y in YEARS]:
            syms = all_results.get(year_label, {}).get(cfg_id, {}).get("symbols", {})
            btc = syms.get("BTC", {}).get("pnl", 0)
            eth = syms.get("ETH", {}).get("pnl", 0)
            sol = syms.get("SOL", {}).get("pnl", 0)
            total = btc + eth + sol
            trades = sum(s.get("trades", 0) for s in syms.values())
            print(f"  {year_label:<6} {btc:<12.2f} {eth:<12.2f} {sol:<12.2f} {total:<12.2f} {trades:<10}")

        total_btc = sum(all_results.get(y[0], {}).get(cfg_id, {}).get("symbols", {}).get("BTC", {}).get("pnl", 0) for y in YEARS)
        total_eth = sum(all_results.get(y[0], {}).get(cfg_id, {}).get("symbols", {}).get("ETH", {}).get("pnl", 0) for y in YEARS)
        total_sol = sum(all_results.get(y[0], {}).get(cfg_id, {}).get("symbols", {}).get("SOL", {}).get("pnl", 0) for y in YEARS)
        total_all = total_btc + total_eth + total_sol
        total_trades = sum(sum(all_results.get(y[0], {}).get(cfg_id, {}).get("symbols", {}).get(s.split("/")[0], {}).get("trades", 0) for s in SYMBOLS) for y in YEARS)
        print(f"  {'合计':<6} {total_btc:<12.2f} {total_eth:<12.2f} {total_sol:<12.2f} {total_all:<12.2f} {total_trades:<10}")

    # 逐项对比
    print(f"\n  --- 滑点改善 Δ (真实 - 悲观) ---")
    header = f"  {'年份':<6} {'BTC Δ':<12} {'ETH Δ':<12} {'SOL Δ':<12} {'总 Δ':<12}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for year_label in [y[0] for y in YEARS]:
        diffs = {}
        for sym in ["BTC", "ETH", "SOL"]:
            p = all_results.get(year_label, {}).get("pessimistic", {}).get("symbols", {}).get(sym, {}).get("pnl", 0)
            r = all_results.get(year_label, {}).get("realistic", {}).get("symbols", {}).get(sym, {}).get("pnl", 0)
            diffs[sym] = r - p
        total_diff = sum(diffs.values())
        print(f"  {year_label:<6} {diffs['BTC']:<+12.2f} {diffs['ETH']:<+12.2f} {diffs['SOL']:<+12.2f} {total_diff:<+12.2f}")

    # 3年累计
    for sym in ["BTC", "ETH", "SOL"]:
        p_total = sum(all_results.get(y[0], {}).get("pessimistic", {}).get("symbols", {}).get(sym, {}).get("pnl", 0) for y in YEARS)
        r_total = sum(all_results.get(y[0], {}).get("realistic", {}).get("symbols", {}).get(sym, {}).get("pnl", 0) for y in YEARS)
        diffs[sym] = r_total - p_total
    total_diff = sum(diffs.values())
    print(f"  {'合计':<6} {diffs['BTC']:<+12.2f} {diffs['ETH']:<+12.2f} {diffs['SOL']:<+12.2f} {total_diff:<+12.2f}")

    with open(OUT_FILE, "w") as f:
        json.dump(all_results, f, indent=2, default=float)
    print(f"\n结果已保存: {OUT_FILE}")

asyncio.run(main())
