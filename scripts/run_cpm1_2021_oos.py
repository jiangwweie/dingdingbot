"""
CPM-OOS-2021-RUN-001: 2021 Full-year OOS Backtest Runner

Frozen baseline: CPM-1 (backtest_eth_baseline)
Period: 2021-01-01 00:00:00 UTC to 2021-12-31 23:59:59 UTC
Mode: v3_pms (position-level with MockMatchingEngine)
Engine: Must include CPM-BT-METRIC-001 slippage tracking fix (commit >= 196bf2d)

This script is a read-only inspect + run artifact. It does NOT modify:
- runtime profile
- strategy parameters
- risk rules
- live-safe code
- execution / order / reconciliation runtime path
"""
import asyncio
import json
import sys
import os
import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from src.domain.models import BacktestRequest, BacktestRuntimeOverrides
from src.application.backtest_config import BACKTEST_ETH_BASELINE_PROFILE


async def main():
    # ── Pre-run metadata ──
    commit_hash = os.popen('git rev-parse HEAD').read().strip()
    print(f"Commit hash: {commit_hash}")

    # Config profile hash (SHA-256 of serialized frozen baseline)
    profile_dict = BACKTEST_ETH_BASELINE_PROFILE.model_dump(mode="json")
    profile_json = json.dumps(profile_dict, sort_keys=True, separators=(',', ':'))
    config_profile_hash = hashlib.sha256(profile_json.encode()).hexdigest()
    print(f"Config profile hash: {config_profile_hash}")
    print(f"Profile name: {BACKTEST_ETH_BASELINE_PROFILE.name}")
    print(f"Profile version: {BACKTEST_ETH_BASELINE_PROFILE.version}")

    # ── 2021 time window ──
    start_time_ms = 1609459200000  # 2021-01-01 00:00:00 UTC
    end_time_ms = 1640995199000    # 2021-12-31 23:59:59 UTC

    start_dt = datetime.fromtimestamp(start_time_ms / 1000, tz=timezone.utc)
    end_dt = datetime.fromtimestamp(end_time_ms / 1000, tz=timezone.utc)
    print(f"Period: {start_dt.isoformat()} to {end_dt.isoformat()}")

    # ── Frozen baseline runtime overrides ──
    # Must match BACKTEST_ETH_BASELINE_PROFILE exactly
    runtime_overrides = BacktestRuntimeOverrides(
        max_atr_ratio=Decimal("0.01"),
        min_distance_pct=Decimal("0.005"),
        ema_period=50,
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.0"), Decimal("3.5")],
        breakeven_enabled=False,
        allowed_directions=["LONG"],
        same_bar_policy="pessimistic",
    )

    # ── Backtest request ──
    request = BacktestRequest(
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        start_time=start_time_ms,
        end_time=end_time_ms,
        limit=9000,
        mode="v3_pms",
        initial_balance=Decimal("10000"),
        slippage_rate=Decimal("0.001"),
        fee_rate=Decimal("0.0004"),
        tp_slippage_rate=Decimal("0.0005"),
        funding_rate_enabled=True,
    )

    print(f"\nRequest summary:")
    print(f"  Symbol: {request.symbol}")
    print(f"  Timeframe: {request.timeframe}")
    print(f"  Mode: {request.mode}")
    print(f"  Initial balance: {request.initial_balance}")
    print(f"  Slippage rate: {request.slippage_rate}")
    print(f"  Fee rate: {request.fee_rate}")
    print(f"  TP slippage rate: {request.tp_slippage_rate}")
    print(f"  Funding enabled: {request.funding_rate_enabled}")
    print(f"  Same-bar policy: {runtime_overrides.same_bar_policy}")

    # ── Initialize infrastructure ──
    from src.infrastructure.exchange_gateway import ExchangeGateway
    from src.infrastructure.historical_data_repository import HistoricalDataRepository
    from src.application.backtester import Backtester

    # Create anonymous gateway (no API keys needed for historical data)
    gateway = ExchangeGateway(
        exchange_name="binance",
        api_key="",
        api_secret="",
        testnet=False,
    )

    # Initialize historical data repository (SQLite local-first)
    data_repo = HistoricalDataRepository()
    await data_repo.initialize()

    # Create backtester
    bt = Backtester(gateway, data_repository=data_repo)

    print("\nRunning 2021 OOS backtest...")
    report = await bt.run_backtest(request, runtime_overrides=runtime_overrides)

    # ── Extract results ──
    print(f"\n=== 2021 OOS RESULTS ===")
    print(f"  Total PnL: {report.total_pnl}")
    print(f"  Max Drawdown: {report.max_drawdown}")
    print(f"  Win Rate: {report.win_rate}")
    print(f"  Sharpe Ratio: {report.sharpe_ratio}")
    print(f"  Sortino Ratio: {report.sortino_ratio}")
    print(f"  Total Trades: {report.total_trades}")
    print(f"  Winning Trades: {report.winning_trades}")
    print(f"  Losing Trades: {report.losing_trades}")
    print(f"  Total Fees: {report.total_fees_paid}")
    print(f"  Total Slippage: {report.total_slippage_cost}")
    print(f"  Total Funding: {report.total_funding_cost}")
    print(f"  Initial Balance: {report.initial_balance}")
    print(f"  Final Balance: {report.final_balance}")
    print(f"  Total Return: {report.total_return}")

    # Compute profit factor from positions
    total_profit = sum(p.realized_pnl for p in report.positions if p.realized_pnl > 0)
    total_loss = abs(sum(p.realized_pnl for p in report.positions if p.realized_pnl < 0))
    profit_factor = total_profit / total_loss if total_loss > 0 else None
    print(f"  Profit Factor: {profit_factor}")

    # ── Save artifacts ──
    artifact_dir = Path("reports/oos_runs/cpm1_2021_oos")
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Save full report
    report_dict = report.model_dump(mode="json") if hasattr(report, 'model_dump') else {}
    # Add computed profit_factor
    report_dict["profit_factor_computed"] = str(profit_factor) if profit_factor else None
    with open(artifact_dir / "result.json", "w") as f:
        json.dump(report_dict, f, indent=2, default=str)

    # Save metadata
    metadata = {
        "task_id": "CPM-OOS-2021-RUN-001",
        "period": {
            "start_utc": start_dt.isoformat(),
            "end_utc": end_dt.isoformat(),
            "full_year_2021": True,
        },
        "engine_version": "v3_pms_mock_matching_engine",
        "commit_hash": commit_hash,
        "config_profile_hash": config_profile_hash,
        "profile_name": BACKTEST_ETH_BASELINE_PROFILE.name,
        "profile_version": BACKTEST_ETH_BASELINE_PROFILE.version,
        "frozen_baseline": {
            "asset": "ETH/USDT:USDT",
            "primary_timeframe": "1h",
            "mtf_timeframe": "4h",
            "direction": "LONG-only",
            "trigger": "pinbar (min_wick_ratio=0.6, max_body_ratio=0.3, body_position_tolerance=0.1)",
            "trend_filter": "EMA50 + min_distance_pct=0.005",
            "mtf_filter": "4h EMA60 confirmation",
            "atr_filter": "disabled",
            "exit": "TP1 1.0R 50%, TP2 3.5R 50%, SL -1.0R, BE off, trailing off",
        },
        "cost_model": {
            "fee_rate": "0.0004 (Binance default)",
            "slippage_rate": "0.001",
            "tp_slippage_rate": "0.0005",
            "fee_source": "Binance USDT-M perpetual default",
        },
        "funding_model": {
            "enabled": True,
            "rate": "0.0001 per 8h (constant approximation)",
            "source": "Default KV config (backtest.funding_rate)",
            "caveat": "Constant rate approximation; real funding varies with market conditions",
        },
        "same_bar_policy": {
            "policy": "pessimistic",
            "description": "SL > TP > ENTRY priority; SL always processed first in same-bar conflicts",
        },
        "data_source": {
            "database": "data/v3_dev.db (SQLite)",
        },
        "legacy_naming_mapping": {
            "pinbar_trigger": "CPM-1 frozen trigger (PinbarStrategy with min_wick_ratio=0.6, max_body_ratio=0.3, body_position_tolerance=0.1)",
            "ema_filter": "EmaTrendFilterDynamic period=50, min_distance_pct=0.005",
            "mtf_filter": "MtfFilterDynamic 4h EMA60",
        },
        "affects_runtime_automatically": False,
    }
    with open(artifact_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\nArtifacts saved to: {artifact_dir}")
    print(f"  result.json")
    print(f"  metadata.json")

    # Close gateway
    if hasattr(gateway, 'close'):
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())
