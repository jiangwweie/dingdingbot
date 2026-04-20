#!/usr/bin/env python3
"""ATR + EMA Distance 二维度参数扫描"""
import asyncio, sys, os, sqlite3, json
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = "data/v3_dev.db"
OUT_FILE = "/tmp/sweep_atr_distance_result.json"

SWEEP_CONFIGS = [
    {"id": 1, "min_distance_pct": 0.005, "max_atr_ratio": None,    "label": "基准"},
    {"id": 2, "min_distance_pct": 0.005, "max_atr_ratio": 0.010,   "label": "纯ATR锚点"},
    {"id": 7, "min_distance_pct": 0.015, "max_atr_ratio": 0.010,   "label": "强EMA+ATR"},
]

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
START = "2025-01-01"
END = "2026-01-01"
DATASET = "oos2"

async def run_one(symbol, start, end, cfg):
    """跑单组配置"""
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

    # 构建策略配置
    filters = [
        {"type": "ema_trend", "enabled": True, "params": {"min_distance_pct": cfg["min_distance_pct"]}},
        {"type": "mtf", "enabled": True, "params": {}},
    ]
    if cfg["max_atr_ratio"] is not None:
        filters.append({"type": "atr", "enabled": True, "params": {
            "period": 14,
            "min_atr_ratio": 0.001,
            "max_atr_ratio": cfg["max_atr_ratio"],
        }})

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

    req = BacktestRequest(
        symbol=symbol, timeframe="1h", limit=30000,
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
    for cfg in SWEEP_CONFIGS:
        cfg_id = cfg["id"]
        print(f"\n{'='*60}")
        print(f"  组 {cfg_id}: {cfg['label']} (distance={cfg['min_distance_pct']}, atr={cfg['max_atr_ratio']})")
        print(f"{'='*60}")
        all_results[cfg_id] = {"config": cfg, "symbols": {}}
        for symbol in SYMBOLS:
            sym_short = symbol.split("/")[0]
            print(f"  {sym_short} ...", end=" ", flush=True)
            r = await run_one(symbol, START, END, cfg)
            print(f"trades={r['trades']} wr={r['win_rate']:.1%} pnl={r['pnl']:.2f}")
            all_results[cfg_id]["symbols"][sym_short] = r

    # 汇总表
    print(f"\n{'='*80}")
    print(f"  汇总 — 验证集 2024 (OOS)")
    print(f"{'='*80}")
    header = f"{'组':<4} {'配置':<25} {'BTC PnL':<12} {'ETH PnL':<12} {'SOL PnL':<12} {'总PnL':<12} {'总Trades':<10}"
    print(header)
    print("-" * len(header))
    for cfg_id, data in all_results.items():
        cfg = data["config"]
        syms = data["symbols"]
        btc = syms.get("BTC", {}).get("pnl", 0)
        eth = syms.get("ETH", {}).get("pnl", 0)
        sol = syms.get("SOL", {}).get("pnl", 0)
        total = btc + eth + sol
        trades = sum(s.get("trades", 0) for s in syms.values())
        label = f"d={cfg['min_distance_pct']},atr={cfg['max_atr_ratio']}"
        print(f"{cfg_id:<4} {label:<25} {btc:<12.2f} {eth:<12.2f} {sol:<12.2f} {total:<12.2f} {trades:<10}")

    with open(OUT_FILE, "w") as f:
        json.dump(all_results, f, indent=2, default=float)
    print(f"\n结果已保存: {OUT_FILE}")

asyncio.run(main())
