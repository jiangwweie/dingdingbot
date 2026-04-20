#!/usr/bin/env python3
"""3币种×2年 BE=ON/OFF 逐个串行跑，结果写文件"""
import asyncio, sys, os, sqlite3, json
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB = "data/v3_dev.db"
OUT = "/tmp/breakeven_all_results.json"

async def run_one(symbol, start, end, be_on):
    from src.infrastructure.historical_data_repository import HistoricalDataRepository
    from src.infrastructure.config_entry_repository import ConfigEntryRepository
    from src.application.backtester import Backtester
    from src.domain.models import BacktestRequest, OrderStrategy
    from src.application.config_manager import ConfigManager

    cm = ConfigManager(DB)
    await cm.initialize_from_db()
    repo = ConfigEntryRepository(DB)
    await repo.initialize()
    cm.set_config_entry_repository(repo)
    ConfigManager.set_instance(cm)

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    ts = int(datetime.now().timestamp() * 1000)
    for k, v, t in [
        ("backtest.tp_trailing_enabled", "false", "boolean"),
        ("backtest.trailing_exit_enabled", "false", "boolean"),
        ("backtest.breakeven_enabled", "true" if be_on else "false", "boolean"),
    ]:
        c.execute("INSERT OR REPLACE INTO config_entries_v2 (config_key,config_value,value_type,version,updated_at,profile_name) VALUES(?,?,?,?,?,?)",
                  (k, v, t, "v1.0.0", ts, "default"))
    conn.commit()
    conn.close()

    dr = HistoricalDataRepository(DB)
    await dr.initialize()
    bt = Backtester(None, data_repository=dr)
    st = int(datetime.strptime(start, "%Y-%m-%d").timestamp() * 1000)
    et = int(datetime.strptime(end, "%Y-%m-%d").timestamp() * 1000)
    req = BacktestRequest(
        symbol=symbol, timeframe="1h", limit=30000,
        start_time=st, end_time=et,
        strategies=[{"name": "pinbar", "triggers": [{"type": "pinbar", "enabled": True}],
                     "filters": [{"type": "ema_trend", "enabled": True, "params": {"min_distance_pct": 0.005}},
                                 {"type": "mtf", "enabled": True, "params": {}}]}],
        order_strategy=OrderStrategy(id="t", name="T", tp_levels=2, tp_ratios=[0.6, 0.4],
                                     tp_targets=[1.0, 2.5], initial_stop_loss_rr=-1.0,
                                     trailing_stop_enabled=True, oco_enabled=True),
        mode="v3_pms")
    report = await bt.run_backtest(req)
    await dr.close()

    es = {}
    for e in (getattr(report, "close_events", None) or []):
        r = e.exit_reason or e.event_type
        es[r] = es.get(r, 0) + 1
    return {"trades": report.total_trades, "win_rate": float(report.win_rate),
            "pnl": float(report.total_pnl), "exit_stats": es}

async def main():
    cases = [
        ("BTC/USDT:USDT", "2023-01-01", "2024-01-01"),
        ("BTC/USDT:USDT", "2024-01-01", "2025-01-01"),
        ("ETH/USDT:USDT", "2023-01-01", "2024-01-01"),
        ("ETH/USDT:USDT", "2024-01-01", "2025-01-01"),
        ("SOL/USDT:USDT", "2023-01-01", "2024-01-01"),
        ("SOL/USDT:USDT", "2024-01-01", "2025-01-01"),
    ]

    all_results = []
    for i, (symbol, start, end) in enumerate(cases):
        coin = symbol.split("/")[0]
        year = start[:4]

        # 写进度文件
        with open("/tmp/breakeven_progress.txt", "a") as f:
            f.write(f"[{i+1}/6] {coin} {year} BE=ON starting...\n")

        b = await run_one(symbol, start, end, True)

        with open("/tmp/breakeven_progress.txt", "a") as f:
            f.write(f"[{i+1}/6] {coin} {year} BE=OFF starting...\n")

        e = await run_one(symbol, start, end, False)

        rec = {
            "coin": coin, "year": year,
            "on": b, "off": e,
            "pnl_diff": e["pnl"] - b["pnl"],
            "sl_diff": e["exit_stats"].get("SL", 0) - b["exit_stats"].get("SL", 0),
            "tp2_diff": e["exit_stats"].get("TP2", 0) - b["exit_stats"].get("TP2", 0),
            "be_count": b["exit_stats"].get("BREAKEVEN_STOP", 0),
        }
        all_results.append(rec)

        with open("/tmp/breakeven_progress.txt", "a") as f:
            f.write(f"[{i+1}/6] {coin} {year} DONE: diff={rec['pnl_diff']:+.2f}\n")

        # 每完成一个就写结果文件
        with open(OUT, "w") as f:
            json.dump(all_results, f, indent=2, default=float)

    print("ALL DONE")
    print(json.dumps(all_results, indent=2, default=float))

asyncio.run(main())
