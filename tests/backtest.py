#!/usr/bin/env python3
"""
历史 K 线策略回测脚本

对历史 K 线运行 Pinbar 策略检测，验证策略在历史行情中的表现。

用法:
    python3 scripts/backtest.py \\
      --symbol BTC/USDT:USDT \\
      --timeframe 1h \\
      --limit 500 \\
      [--higher-tf 4h --higher-tf-symbol BTC/USDT:USDT --higher-tf-limit 200]
      [--verbose]
"""
import argparse
import asyncio
import sys
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Dict, Optional, Tuple

# Add project root to path
sys.path.insert(0, '/Users/jiangwei/Documents/final')

import ccxt.async_support as ccxt

from src.application.config_manager import load_all_configs
from src.domain.models import KlineData, Direction, TrendDirection
from src.domain.strategy_engine import (
    StrategyEngine, StrategyConfig, PinbarConfig, PinbarConfig
)


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
# Statistics Collection
# ============================================================
class BacktestStats:
    """Collect and display backtest statistics."""

    def __init__(self):
        self.total_klines = 0
        self.pinbar_count = 0
        self.signal_count = 0
        self.long_count = 0
        self.short_count = 0
        self.filtered_count = 0
        self.ema_filtered = 0
        self.mtf_filtered = 0
        self.warmup_signals = 0  # Signals during EMA warmup period

        self.signals: List[Tuple[KlineData, any]] = []
        self.filtered_details: List[Tuple[KlineData, any, str]] = []

    def record(self, kline: KlineData, attempt, is_warmup: bool):
        """Record a single K-line result."""
        self.total_klines += 1

        if attempt.pattern:
            self.pinbar_count += 1

            if attempt.final_result == "SIGNAL_FIRED":
                self.signal_count += 1
                if attempt.pattern.direction == Direction.LONG:
                    self.long_count += 1
                else:
                    self.short_count += 1
                self.signals.append((kline, attempt))
                if is_warmup:
                    self.warmup_signals += 1
            elif attempt.final_result == "FILTERED":
                self.filtered_count += 1
                # Find which filter rejected it
                for filter_name, filter_result in attempt.filter_results:
                    if not filter_result.passed:
                        if filter_name == "ema_trend":
                            self.ema_filtered += 1
                        elif filter_name == "mtf":
                            self.mtf_filtered += 1
                        if is_warmup or args.verbose:
                            self.filtered_details.append((kline, attempt, filter_name))

    def print_report(self, symbol: str, timeframe: str, klines: List[KlineData]):
        """Print the backtest report."""
        print("\n" + "=" * 60)
        print(f"回测报告：{symbol}  {timeframe}  过去 {self.total_klines} 根 K 线")
        print("=" * 60)

        # Time range
        if klines:
            start_time = datetime.fromtimestamp(klines[0].timestamp / 1000, tz=timezone.utc)
            end_time = datetime.fromtimestamp(klines[-1].timestamp / 1000, tz=timezone.utc)
            print(f"时间范围：{start_time.strftime('%Y-%m-%d %H:%M')} → {end_time.strftime('%Y-%m-%d %H:%M')}")

        # Summary stats
        pinbar_pct = (self.pinbar_count / self.total_klines * 100) if self.total_klines > 0 else 0
        signal_pct = (self.signal_count / self.total_klines * 100) if self.total_klines > 0 else 0

        print(f"总 K 线数：      {self.total_klines}")
        print(f"识别到 Pinbar:   {self.pinbar_count}  ({pinbar_pct:.1f}%)")
        print(f"最终触发信号：     {self.signal_count}  ({signal_pct:.1f}%)")
        print(f"  - 做多信号：    {self.long_count}")
        print(f"  - 做空信号：    {self.short_count}")
        print(f"被过滤：          {self.filtered_count}")
        print(f"  - EMA 过滤：   {self.ema_filtered}")
        print(f"  - MTF 过滤：    {self.mtf_filtered}")

        if self.warmup_signals > 0:
            print(f"\n* 注意：{self.warmup_signals} 个信号出现在 EMA 预热期（前 60 根 K 线），可能不可靠")

        print("=" * 60)

        # Signal details
        if self.signals:
            print("\n信号明细：")
            for kline, attempt in self.signals:
                dt = datetime.fromtimestamp(kline.timestamp / 1000, tz=timezone.utc)
                direction_str = "LONG" if attempt.pattern.direction == Direction.LONG else "SHORT"
                warmup_mark = " *预热期*" if self.signals.index((kline, attempt)) < 60 else ""

                # Calculate stop loss (simplified: use recent low/high)
                stop_loss = kline.low if attempt.pattern.direction == Direction.LONG else kline.high

                print(f"[信号] {dt.strftime('%Y-%m-%d %H:%M')}  {direction_str}  "
                      f"评分：{attempt.pattern.score:.2f}  入场价：{kline.close}  止损：{stop_loss}{warmup_mark}")

        # Filtered details (verbose mode)
        if args.verbose and self.filtered_details:
            print("\nPinbar 被过滤明细：")
            for kline, attempt, filter_name in self.filtered_details[:20]:  # Limit to 20
                dt = datetime.fromtimestamp(kline.timestamp / 1000, tz=timezone.utc)
                direction_str = "LONG" if attempt.pattern and attempt.pattern.direction == Direction.LONG else "SHORT"
                score = attempt.pattern.score if attempt.pattern else 0

                # Find the reason
                reason = "unknown"
                for fn, fr in attempt.filter_results:
                    if fn == filter_name and not fr.passed:
                        reason = fr.reason
                        break

                print(f"[过滤] {dt.strftime('%Y-%m-%d %H:%M')}  {direction_str}  "
                      f"评分：{score:.2f}  被 {filter_name} 拒绝：{reason}")


# ============================================================
# Main Backtest Logic
# ============================================================
async def run_backtest(args):
    """Run the backtest."""
    print("=" * 60)
    print("加密货币信号监测系统 - 历史 K 线回测")
    print("=" * 60)

    # Load configuration
    print("\n加载配置...")
    config_manager = load_all_configs()

    # Build strategy config from core + user config
    core = config_manager.core_config
    user = config_manager.user_config

    # Support both legacy and new active_strategies format
    if user.active_strategies and len(user.active_strategies) > 0:
        # New format: extract EMA and MTF settings from active_strategies
        # For simplicity, use the first active strategy
        first_strategy = user.active_strategies[0]

        # Check if EMA filter is enabled
        trend_filter_enabled = False
        mtf_validation_enabled = False

        if hasattr(first_strategy, 'filters') and first_strategy.filters:
            for f in first_strategy.filters:
                if f.type == 'ema' and f.enabled:
                    trend_filter_enabled = True
                if f.type == 'mtf' and f.enabled:
                    mtf_validation_enabled = True
    elif user.strategy:
        # Legacy format
        trend_filter_enabled = user.strategy.trend_filter_enabled
        mtf_validation_enabled = user.strategy.mtf_validation_enabled
    else:
        # Default to enabled
        trend_filter_enabled = True
        mtf_validation_enabled = True

    pinbar_config = PinbarConfig(
        min_wick_ratio=core.pinbar_defaults.min_wick_ratio,
        max_body_ratio=core.pinbar_defaults.max_body_ratio,
        body_position_tolerance=core.pinbar_defaults.body_position_tolerance,
    )

    strategy_config = StrategyConfig(
        pinbar_config=pinbar_config,
        ema_period=core.ema.period,
        trend_filter_enabled=trend_filter_enabled,
        mtf_validation_enabled=mtf_validation_enabled,
    )

    print(f"  EMA 周期：{core.ema.period}")
    print(f"  趋势过滤：{'启用' if trend_filter_enabled else '禁用'}")
    print(f"  MTF 验证：{'启用' if mtf_validation_enabled else '禁用'}")

    # Initialize exchange
    print("\n初始化交易所连接...")
    exchange = ccxt.binanceusdm({
        'options': {'defaultType': 'swap'},
    })

    try:
        # Fetch historical data
        print("\n拉取历史数据...")
        main_klines = await fetch_historical_klines(
            exchange, args.symbol, args.timeframe, args.limit
        )

        if not main_klines:
            print("错误：未获取到任何 K 线数据")
            return

        # Fetch higher timeframe data if requested
        higher_tf_klines: Optional[List[KlineData]] = None
        higher_tf: Optional[str] = args.higher_tf
        higher_tf_symbol: str = args.higher_tf_symbol or args.symbol

        if higher_tf:
            print(f"\n拉取高级别周期数据：{higher_tf_symbol} {higher_tf}...")
            higher_tf_klines = await fetch_historical_klines(
                exchange, higher_tf_symbol, higher_tf, args.higher_tf_limit
            )

        # Initialize strategy engine
        print("\n初始化策略引擎...")
        engine = StrategyEngine(strategy_config)

        # Run backtest
        print("运行回测...")
        stats = BacktestStats()

        ema_warmup = core.ema.period  # 60 bars

        for i, kline in enumerate(main_klines):
            is_warmup = i < ema_warmup

            # Build higher_tf_trends
            higher_tf_trends: Dict[str, TrendDirection] = {}
            if higher_tf_klines:
                # Find the latest higher TF kline that closed before current kline
                cutoff = kline.timestamp
                valid_htf = [k for k in higher_tf_klines if k.timestamp <= cutoff]
                if valid_htf:
                    latest_htf = valid_htf[-1]
                    # Update EMA and get trend for higher timeframe
                    trend = engine.get_ema_trend(latest_htf, higher_tf_symbol, higher_tf)
                    if trend:
                        higher_tf_trends[higher_tf] = trend

            # Run strategy
            attempt = engine.run_with_attempt(kline, higher_tf_trends)

            # Record result
            stats.record(kline, attempt, is_warmup)

        # Print report
        stats.print_report(args.symbol, args.timeframe, main_klines)

    finally:
        await exchange.close()


# ============================================================
# Entry Point
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="历史 K 线策略回测 - 验证 Pinbar 策略在历史行情中的表现"
    )

    parser.add_argument(
        "--symbol",
        required=True,
        help="主分析币种，如 BTC/USDT:USDT"
    )
    parser.add_argument(
        "--timeframe",
        default="1h",
        help="主分析周期 (默认：1h)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="拉取历史 K 线数量 (默认：500)"
    )
    parser.add_argument(
        "--higher-tf",
        dest="higher_tf",
        help="高级别 MTF 周期（可选，用于 MTF 过滤），如 4h"
    )
    parser.add_argument(
        "--higher-tf-symbol",
        dest="higher_tf_symbol",
        help="高级别周期币种 (默认与主分析币种相同)"
    )
    parser.add_argument(
        "--higher-tf-limit",
        dest="higher_tf_limit",
        type=int,
        default=200,
        help="高级别 K 线数量 (默认：200)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="输出被过滤的 Pinbar 明细"
    )

    args = parser.parse_args()

    try:
        asyncio.run(run_backtest(args))
    except KeyboardInterrupt:
        print("\n回测中断")
        sys.exit(0)
    except Exception as e:
        print(f"\n错误：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
