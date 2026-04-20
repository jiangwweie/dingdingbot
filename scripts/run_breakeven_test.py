#!/usr/bin/env python3
"""单币种 BE=ON vs BE=OFF 回测对比"""
import asyncio, sys, os, sqlite3, json
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = "data/v3_dev.db"
OUT_FILE = "/tmp/breakeven_result.json"

async def run_one(symbol, start, end, breakeven_enabled):
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

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    ts = int(datetime.now().timestamp() * 1000)
    for k, v, t in [
        ("backtest.tp_trailing_enabled", "false", "boolean"),
        ("backtest.trailing_exit_enabled", "false", "boolean"),
        ("backtest.breakeven_enabled", "true" if breakeven_enabled else "false", "boolean"),
    ]:
        cur.execute("INSERT OR REPLACE INTO config_entries_v2 (config_key,config_value,value_type,version,updated_at,profile_name) VALUES(?,?,?,?,?,?)",
                    (k,v,t,"v1.0.0",ts,"default"))
    conn.commit()
    conn.close()

    data_repo = HistoricalDataRepository(DB_PATH)
    await data_repo.initialize()
    bt = Backtester(None, data_repository=data_repo)
    st = int(datetime.strptime(start, "%Y-%m-%d").timestamp()*1000)
    et = int(datetime.strptime(end, "%Y-%m-%d").timestamp()*1000)
    req = BacktestRequest(
        symbol=symbol, timeframe="1h", limit=30000,
        start_time=st, end_time=et,
        strategies=[{"name":"pinbar","triggers":[{"type":"pinbar","enabled":True}],
                     "filters":[{"type":"ema_trend","enabled":True,"params":{"min_distance_pct":0.005}},
                                {"type":"mtf","enabled":True,"params":{}}]}],
        order_strategy=OrderStrategy(id="t",name="T",tp_levels=2,tp_ratios=[0.6,0.4],
                                     tp_targets=[1.0,2.5],initial_stop_loss_rr=-1.0,
                                     trailing_stop_enabled=True,oco_enabled=True),
        mode="v3_pms")
    report = await bt.run_backtest(req)
    await data_repo.close()

    es = {}
    for e in (getattr(report,"close_events",None) or []):
        r = e.exit_reason or e.event_type
        es[r] = es.get(r,0)+1
    return {"trades":report.total_trades,"win_rate":float(report.win_rate),
            "pnl":float(report.total_pnl),"exit_stats":es}

async def main():
    symbol = sys.argv[1] if len(sys.argv)>1 else "BTC/USDT:USDT"
    start = sys.argv[2] if len(sys.argv)>2 else "2023-01-01"
    end = sys.argv[3] if len(sys.argv)>3 else "2024-01-01"

    b = await run_one(symbol, start, end, True)
    e = await run_one(symbol, start, end, False)

    result = {"symbol":symbol,"range":f"{start}~{end}",
              "baseline":b,"experiment":e,
              "pnl_diff":e["pnl"]-b["pnl"],
              "sl_diff":e["exit_stats"].get("SL",0)-b["exit_stats"].get("SL",0),
              "tp2_diff":e["exit_stats"].get("TP2",0)-b["exit_stats"].get("TP2",0),
              "be_on":b["exit_stats"].get("BREAKEVEN_STOP",0),
              "be_off":e["exit_stats"].get("BREAKEVEN_STOP",0)}
    with open(OUT_FILE,"w") as f:
        json.dump(result,f,indent=2,default=float)

asyncio.run(main())
