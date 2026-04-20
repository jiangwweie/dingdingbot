#!/usr/bin/env python3
"""BTC 4h 时间周期测试 — Group 2 基础配置"""
import asyncio, sys, os, sqlite3, json
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = "data/v3_dev.db"
OUT_FILE = "/tmp/btc_4h_result.json"

# BTC=4h, ETH/SOL=1h 对照
CONFIGS = [
    {"id": "btc_4h", "symbols": [
        {"symbol": "BTC/USDT:USDT", "timeframe": "4h"},
        {"symbol": "ETH/USDT:USDT", "timeframe": "1h"},
        {"symbol": "SOL/USDT:USDT", "timeframe": "1h"},
    ], "label": "BTC-4h Group2"},
    {"id": "baseline", "symbols": [
        {"symbol": "BTC/USDT:USDT", "timeframe": "1h"},
        {"symbol": "ETH/USDT:USDT", "timeframe": "1h"},
        {"symbol": "SOL/USDT:USDT", "timeframe": "1h"},
    ], "label": "全部1h 基线"},
]

YEARS = [
    ("2023", "2023-01-01", "2024-01-01"),
    ("2024", "2024-01-01", "2025-01-01"),
    ("2025", "2025-01-01", "2026-01-01"),
]

MIN_DISTANCE = 0.005
MAX_ATR_RATIO = 0.010


async def run_one(symbol, timeframe, start, end):
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
    ConfigManager.set_instance(cm)

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

    # 策略配置：EMA + MTF + ATR
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
    bt = Backtester(None, data_repository=data_repo)

    st = int(datetime.strptime(start, "%Y-%m-%d").timestamp() * 1000)
    et = int(datetime.strptime(end, "%Y-%m-%d").timestamp() * 1000)

    # 4h 用 limit=8000, 1h 用 limit=30000
    limit = 8000 if timeframe == "4h" else 30000

    req = BacktestRequest(
        symbol=symbol, timeframe=timeframe, limit=limit,
        start_time=st, end_time=et,
        strategies=strategies,
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
        for cfg in CONFIGS:
            cfg_id = cfg["id"]
            print(f"\n  {cfg['label']}:")
            cfg_data = {}
            for sym_cfg in cfg["symbols"]:
                sym_short = sym_cfg["symbol"].split("/")[0]
                tf = sym_cfg["timeframe"]
                print(f"    {sym_short}({tf}) ...", end=" ", flush=True)
                r = await run_one(sym_cfg["symbol"], tf, start, end)
                print(f"trades={r['trades']} wr={r['win_rate']:.1%} pnl={r['pnl']:.2f}")
                cfg_data[sym_short] = r
            year_data[cfg_id] = {"config": cfg, "symbols": cfg_data}
        all_results[year_label] = year_data

    # 汇总表
    print(f"\n{'='*90}")
    print(f"  汇总 — BTC 4h vs 全部1h (Group 2: ATR=1%, BE=OFF)")
    print(f"{'='*90}")

    for cfg_id, label in [("baseline", "全部1h 基线"), ("btc_4h", "BTC-4h Group2")]:
        print(f"\n  --- {label} ---")
        header = f"  {'年份':<6} {'BTC PnL':<12} {'BTC WR':<10} {'ETH PnL':<12} {'SOL PnL':<12} {'总PnL':<12} {'总Trades':<10}"
        print(header)
        print("  " + "-" * (len(header) - 2))
        for year_label in [y[0] for y in YEARS]:
            syms = all_results.get(year_label, {}).get(cfg_id, {}).get("symbols", {})
            btc = syms.get("BTC", {}).get("pnl", 0)
            btc_wr = syms.get("BTC", {}).get("win_rate", 0)
            eth = syms.get("ETH", {}).get("pnl", 0)
            sol = syms.get("SOL", {}).get("pnl", 0)
            total = btc + eth + sol
            trades = sum(s.get("trades", 0) for s in syms.values())
            print(f"  {year_label:<6} {btc:<12.2f} {btc_wr:<10.1%} {eth:<12.2f} {sol:<12.2f} {total:<12.2f} {trades:<10}")

        # 3年累计
        total_btc = sum(all_results.get(y[0], {}).get(cfg_id, {}).get("symbols", {}).get("BTC", {}).get("pnl", 0) for y in YEARS)
        total_eth = sum(all_results.get(y[0], {}).get(cfg_id, {}).get("symbols", {}).get("ETH", {}).get("pnl", 0) for y in YEARS)
        total_sol = sum(all_results.get(y[0], {}).get(cfg_id, {}).get("symbols", {}).get("SOL", {}).get("pnl", 0) for y in YEARS)
        total_all = total_btc + total_eth + total_sol
        total_trades = sum(sum(all_results.get(y[0], {}).get(cfg_id, {}).get("symbols", {}).get(s.split("/")[0], {}).get("trades", 0) for s in ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]) for y in YEARS)
        print(f"  {'合计':<6} {total_btc:<12.2f} {'':10} {total_eth:<12.2f} {total_sol:<12.2f} {total_all:<12.2f} {total_trades:<10}")

    # 直接对比
    print(f"\n  --- BTC 对比 ---")
    print(f"  {'年份':<6} {'BTC 1h':<12} {'BTC 4h':<12} {'Δ':<12}")
    print(f"  {'-'*42}")
    for year_label in [y[0] for y in YEARS]:
        r1h = all_results.get(year_label, {}).get("baseline", {}).get("symbols", {}).get("BTC", {}).get("pnl", 0)
        r4h = all_results.get(year_label, {}).get("btc_4h", {}).get("symbols", {}).get("BTC", {}).get("pnl", 0)
        delta = r4h - r1h
        sign = "+" if delta >= 0 else ""
        print(f"  {year_label:<6} {r1h:<12.2f} {r4h:<12.2f} {sign}{delta:<11.2f}")

    r1h_total = sum(all_results.get(y[0], {}).get("baseline", {}).get("symbols", {}).get("BTC", {}).get("pnl", 0) for y in YEARS)
    r4h_total = sum(all_results.get(y[0], {}).get("btc_4h", {}).get("symbols", {}).get("BTC", {}).get("pnl", 0) for y in YEARS)
    delta_total = r4h_total - r1h_total
    sign = "+" if delta_total >= 0 else ""
    print(f"  {'合计':<6} {r1h_total:<12.2f} {r4h_total:<12.2f} {sign}{delta_total:<11.2f}")

    with open(OUT_FILE, "w") as f:
        json.dump(all_results, f, indent=2, default=float)
    print(f"\n结果已保存: {OUT_FILE}")

asyncio.run(main())
