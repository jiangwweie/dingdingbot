#!/usr/bin/env python3
"""全币种 BE=ON vs OFF 回测对比"""
import asyncio, sys, os, sqlite3, json
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB = "data/v3_dev.db"
OUT = "/tmp/all_breakeven_result.json"

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
    bt = Backtester(None, data_repository=dr, config_manager=cm)
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
    for e in (getattr(report,"close_events",None) or []):
        r = e.exit_reason or e.event_type
        es[r] = es.get(r,0)+1
    return {"trades":report.total_trades,"win_rate":float(report.win_rate),
            "pnl":float(report.total_pnl),"exit_stats":es}

async def main():
    symbols = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
    start = sys.argv[1] if len(sys.argv)>1 else "2023-01-01"
    end = sys.argv[2] if len(sys.argv)>2 else "2025-01-01"

    results = {}
    for symbol in symbols:
        sym = symbol.split("/")[0]
        print(f"=== {sym} BE=ON ===")
        b = await run_one(symbol, start, end, True)
        print(f"  trades={b['trades']} wr={b['win_rate']:.1%} pnl={b['pnl']:.2f} exits={b['exit_stats']}")

        print(f"=== {sym} BE=OFF ===")
        e = await run_one(symbol, start, end, False)
        print(f"  trades={e['trades']} wr={e['win_rate']:.1%} pnl={e['pnl']:.2f} exits={e['exit_stats']}")

        diff = e['pnl'] - b['pnl']
        print(f"  DIFF: pnl={diff:+.2f} sl={e['exit_stats'].get('SL',0)-b['exit_stats'].get('SL',0):+d} tp2={e['exit_stats'].get('TP2',0)-b['exit_stats'].get('TP2',0):+d}")
        print()
        results[sym] = {"baseline":b, "experiment":e, "pnl_diff":diff}

    with open(OUT,"w") as f:
        json.dump(results,f,indent=2,default=float)
    print(f"结果已保存: {OUT}")

asyncio.run(main())