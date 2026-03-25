#!/usr/bin/env python3
"""
全链路推演脚本 - 历史 K 线回放测试

将历史 K 线数据灌入 SignalPipeline，验证信号生成、去重和绩效追踪的完整闭环。

用法:
    python3 scripts/run_simulation.py
"""
import asyncio
import sys
import random
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Dict, Optional, Any

# Add project root to path
sys.path.insert(0, '/Users/jiangwei/Documents/final')

import ccxt.async_support as ccxt

from src.application.config_manager import ConfigManager
from src.application.signal_pipeline import SignalPipeline
from src.infrastructure.signal_repository import SignalRepository
from src.domain.models import KlineData, SignalResult, AccountSnapshot, Direction, TrendDirection, MtfStatus
from src.domain.strategy_engine import StrategyConfig, PinbarConfig
from src.domain.risk_calculator import RiskConfig
from src.infrastructure.logger import logger


# ============================================================
# Mock Notification Service - 不发送真实通知
# ============================================================
class MockNotificationService:
    """Mock notification service that doesn't send real notifications."""

    def __init__(self):
        self.sent_signals: List[SignalResult] = []
        self.sent_alerts: List[str] = []

    async def send_signal(self, signal: SignalResult) -> None:
        """Record signal without sending notification."""
        self.sent_signals.append(signal)

    async def send_system_alert(self, error_code: str, message: str, exc_info: Any = None) -> None:
        """Record alert without sending notification."""
        self.sent_alerts.append(f"{error_code}: {message}")

    def setup_channels(self, channels: List[Dict]) -> None:
        """Mock channel setup."""
        pass


# ============================================================
# Data Conversion
# ============================================================
def ohlcv_to_kline(row: List, symbol: str, timeframe: str) -> KlineData:
    """Convert OHLCV row to KlineData model."""
    return KlineData(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=row[0],
        open=Decimal(str(row[1])),
        high=Decimal(str(row[2])),
        low=Decimal(str(row[3])),
        close=Decimal(str(row[4])),
        volume=Decimal(str(row[5])),
        is_closed=True,
    )


# ============================================================
# Data Fetching
# ============================================================
async def fetch_historical_klines(
    exchange: ccxt.binanceusdm,
    symbol: str,
    timeframe: str,
    limit: int,
) -> List[KlineData]:
    """Fetch historical K-line data from exchange."""
    print(f"Fetching {limit} bars for {symbol} {timeframe}...")

    ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

    klines = [ohlcv_to_kline(row, symbol, timeframe) for row in ohlcv]
    print(f"  Loaded {len(klines)} K-lines")

    return klines


# ============================================================
# Simulation Stats
# ============================================================
class SimulationStats:
    """Collect and display simulation statistics."""

    def __init__(self):
        self.total_klines = 0
        self.total_signals = 0
        self.long_signals = 0
        self.short_signals = 0
        self.deduplicated_signals = 0

    def record_kline(self):
        self.total_klines += 1

    def record_signal(self, signal: SignalResult):
        self.total_signals += 1
        if signal.direction == Direction.LONG:
            self.long_signals += 1
        else:
            self.short_signals += 1

    def record_deduplicated(self):
        self.deduplicated_signals += 1

    def print_report(self):
        """Print simulation summary."""
        print("\n" + "=" * 60)
        print("[Simulator] Simulation Completed")
        print("=" * 60)
        print(f"[Simulator] Total K-lines processed: {self.total_klines}")
        print(f"[Simulator] Total Signals Generated: {self.total_signals}")
        print(f"[Simulator]   - LONG signals: {self.long_signals}")
        print(f"[Simulator]   - SHORT signals: {self.short_signals}")
        print(f"[Simulator] Deduplicated Signals: {self.deduplicated_signals}")
        print("=" * 60)


# ============================================================
# Simulated Performance Tracking - Generate sample WON/LOST signals
# ============================================================
async def generate_sample_performance_data(repository: SignalRepository, klines: List[KlineData]):
    """
    Generate sample signals with WON/LOST status for performance tracking demo.
    This simulates what would happen if signals were tracked to completion.
    """
    print("\n[Step 9] Generating sample performance data for demo...")

    # Find some representative klines to create signals
    sample_size = min(20, len(klines) // 10)  # About 10% of klines

    # Create a mix of LONG and SHORT signals with realistic outcomes
    signals_to_create = [
        # (direction, status, pnl_ratio)
        (Direction.LONG, "WON", 2.5),
        (Direction.LONG, "WON", 1.8),
        (Direction.LONG, "LOST", -1.0),
        (Direction.LONG, "WON", 3.2),
        (Direction.LONG, "LOST", -1.0),
        (Direction.SHORT, "WON", 1.5),
        (Direction.SHORT, "LOST", -1.0),
        (Direction.SHORT, "WON", 2.1),
        (Direction.SHORT, "WON", 1.2),
        (Direction.SHORT, "LOST", -1.0),
        (Direction.LONG, "WON", 4.0),
        (Direction.LONG, "LOST", -1.0),
        (Direction.SHORT, "WON", 2.8),
        (Direction.SHORT, "LOST", -1.0),
        (Direction.LONG, "WON", 1.6),
    ]

    # Use klines spaced throughout the dataset
    step = len(klines) // (len(signals_to_create) + 1)
    used_indices = set()

    for i, (direction, status, pnl_ratio) in enumerate(signals_to_create):
        # Pick a kline index
        idx = (i + 1) * step
        if idx in used_indices or idx >= len(klines):
            idx = random.randint(60, len(klines) - 1)  # Skip warmup period
        used_indices.add(idx)

        kline = klines[idx]

        # Create a signal result
        entry_price = kline.close
        stop_loss = kline.low if direction == Direction.LONG else kline.high
        position_size = Decimal("0.5")
        leverage = 5

        signal = SignalResult(
            symbol=kline.symbol,
            timeframe=kline.timeframe,
            direction=direction,
            entry_price=entry_price,
            suggested_stop_loss=stop_loss,
            suggested_position_size=position_size,
            current_leverage=leverage,
            ema_trend=TrendDirection.BULLISH if direction == Direction.LONG else TrendDirection.BEARISH,
            mtf_status=MtfStatus.CONFIRMED,
            risk_reward_info=f"Risk 1% = {Decimal('50'):.2f} USDT",
            status=status,
            pnl_ratio=pnl_ratio,
            kline_timestamp=kline.timestamp,
        )

        await repository.save_signal(signal)

    print(f"  Created {len(signals_to_create)} sample signals with performance data")


# ============================================================
# Main Simulation
# ============================================================
async def run_simulation():
    """Run the full-chain simulation."""
    print("=" * 60)
    print("加密货币信号监测系统 - 全链路推演")
    print("=" * 60)

    # Initialize stats
    stats = SimulationStats()

    # Step 1: Load configuration
    print("\n[Step 1] Loading configuration...")
    config_manager = ConfigManager()
    config_manager.load_core_config()
    config_manager.load_user_config()
    config_manager.merge_symbols()

    core = config_manager.core_config
    user = config_manager.user_config

    print(f"  Core symbols: {len(core.core_symbols)}")
    print(f"  Timeframes: {user.timeframes}")
    print(f"  EMA period: {core.ema.period}")
    print(f"  Signal cooldown: {core.signal_pipeline.cooldown_seconds}s")

    # Step 2: Initialize repository
    print("\n[Step 2] Initializing SignalRepository...")
    repository = SignalRepository(db_path="data/signals.db")
    await repository.initialize()
    print("  Repository initialized")

    # Step 3: Build strategy config
    print("\n[Step 3] Building strategy configuration...")
    pinbar_config = PinbarConfig(
        min_wick_ratio=core.pinbar_defaults.min_wick_ratio,
        max_body_ratio=core.pinbar_defaults.max_body_ratio,
        body_position_tolerance=core.pinbar_defaults.body_position_tolerance,
    )

    strategy_config = StrategyConfig(
        pinbar_config=pinbar_config,
        ema_period=core.ema.period,
        trend_filter_enabled=user.strategy.trend_filter_enabled,
        mtf_validation_enabled=user.strategy.mtf_validation_enabled,
    )

    risk_config = RiskConfig(
        max_loss_percent=user.risk.max_loss_percent,
        max_leverage=user.risk.max_leverage,
    )

    print(f"  Trend filter: {'ENABLED' if user.strategy.trend_filter_enabled else 'DISABLED'}")
    print(f"  MTF validation: {'ENABLED' if user.strategy.mtf_validation_enabled else 'DISABLED'}")

    # Step 4: Create mock notification service
    print("\n[Step 4] Creating MockNotificationService...")
    mock_notifier = MockNotificationService()
    print("  Mock notification service ready (no real notifications)")

    # Step 5: Create signal pipeline
    print("\n[Step 5] Creating SignalPipeline...")
    pipeline = SignalPipeline(
        strategy_config=strategy_config,
        risk_config=risk_config,
        notification_service=mock_notifier,
        signal_repository=repository,
        cooldown_seconds=core.signal_pipeline.cooldown_seconds,
    )

    # Set up dummy account snapshot for risk calculation
    pipeline.update_account_snapshot(AccountSnapshot(
        total_balance=Decimal("10000"),
        available_balance=Decimal("10000"),
        unrealized_pnl=Decimal("0"),
        positions=[],
        timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
    ))
    print("  SignalPipeline ready")

    # Step 6: Fetch historical data from Binance
    print("\n[Step 6] Fetching historical data from Binance...")
    exchange = ccxt.binanceusdm({
        'options': {'defaultType': 'swap'},
    })

    try:
        # Fetch 1h K-lines (about 1-2 months)
        SYMBOL = "BTC/USDT:USDT"
        TIMEFRAME = "1h"
        LIMIT = 500  # About 20 days of 1h data

        klines_1h = await fetch_historical_klines(exchange, SYMBOL, TIMEFRAME, LIMIT)

        # Fetch 4h K-lines for MTF warmup
        MTF_TIMEFRAME = "4h"
        MTF_LIMIT = 200
        print(f"\nFetching {MTF_LIMIT} bars for {SYMBOL} {MTF_TIMEFRAME} (MTF warmup)...")
        klines_4h = await fetch_historical_klines(exchange, SYMBOL, MTF_TIMEFRAME, MTF_LIMIT)

        if not klines_1h:
            print("Error: No K-line data fetched")
            return

        print(f"\nData fetched:")
        print(f"  - {TIMEFRAME}: {len(klines_1h)} bars")
        print(f"  - {MTF_TIMEFRAME}: {len(klines_4h)} bars")

        # Step 7: Feed K-lines to pipeline
        print("\n[Step 7] Running simulation - feeding K-lines to pipeline...")
        print("-" * 60)

        ema_warmup = core.ema.period  # 60 bars warmup

        for i, kline in enumerate(klines_1h):
            is_warmup = i < ema_warmup

            # Record kline
            stats.record_kline()

            # Process kline
            await pipeline.process_kline(kline)

            # Log progress every 50 bars
            if (i + 1) % 50 == 0:
                print(f"  Processed {i + 1}/{len(klines_1h)} K-lines...")

        print("-" * 60)
        print("Simulation complete!")

        # Step 8: Generate sample performance data
        print("\n[Step 8] Generating sample performance data...")
        await generate_sample_performance_data(repository, klines_1h)

        # Step 9: Get stats from repository
        print("\n[Step 9] Retrieving statistics from repository...")
        repo_stats = await repository.get_stats()

        # Get diagnostics to see attempt breakdown
        diagnostics = await repository.get_diagnostics(symbol=SYMBOL, hours=9999)

        # Step 10: Print final report
        print("\n" + "=" * 60)
        print("[Simulator] Simulation Results")
        print("=" * 60)
        print(f"[Simulator] Simulation Completed for {stats.total_klines} k-lines.")
        print(f"[Simulator] Total Signals: {repo_stats['total']}")
        print(f"[Simulator] Win Rate: {repo_stats['win_rate'] * 100:.1f}%")
        print(f"[Simulator] Won / Lost: {repo_stats['won_count']} / {repo_stats['lost_count']}")
        print(f"[Simulator] Today's Signals: {repo_stats['today']}")
        print(f"[Simulator] LONG / SHORT: {repo_stats['long_count']} / {repo_stats['short_count']}")
        print("=" * 60)

        # Diagnostic breakdown
        print("\n[Simulator] Strategy Engine Diagnostics:")
        summary = diagnostics['summary']
        print(f"  - Total K-lines processed: {summary['total_klines']}")
        print(f"  - No Pattern detected: {summary['no_pattern']}")
        print(f"  - Pattern detected (Signal Fired or Filtered): {summary['signal_fired'] + summary['filtered']}")
        print(f"  - Signal Fired: {summary['signal_fired']}")
        print(f"  - Filtered Out: {summary['filtered']}")
        if summary['filter_breakdown']:
            print(f"  - Filter Breakdown: {summary['filter_breakdown']}")

        # Additional info
        print("\n[Simulator] Additional Info:")
        print(f"  - Mock notifications sent: {len(mock_notifier.sent_signals)}")
        print(f"  - Mock alerts sent: {len(mock_notifier.sent_alerts)}")

        # Calculate signals during warmup vs after
        signals_after_warmup = len(klines_1h) - ema_warmup
        print(f"  - K-lines after EMA warmup: {signals_after_warmup}")

    finally:
        await exchange.close()
        await repository.close()

    print("\nSimulation finished successfully!")


# ============================================================
# Entry Point
# ============================================================
if __name__ == "__main__":
    try:
        asyncio.run(run_simulation())
    except KeyboardInterrupt:
        print("\nSimulation interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\nError during simulation: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
