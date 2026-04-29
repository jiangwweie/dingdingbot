#!/usr/bin/env python3
"""
Task 2: Pinbar 集成测试 - 真实 K 线数据验证

从 SQLite 数据库读取真实 K 线数据，运行 Pinbar 策略检测，
统计信号指标、模拟胜率、跨品种/周期对比。

用法:
    python3 tests/integration/test_pinbar_backtest.py \\
        --symbol BTC/USDT:USDT \\
        --timeframes 15m 1h 4h \\
        --db-path data/v3_dev.db
"""
import argparse
import sqlite3
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.domain.models import KlineData, Direction, TrendDirection
from src.domain.strategy_engine import (
    PinbarStrategy, PinbarConfig, StrategyRunner,
    EmaTrendFilter, MtfFilter, StrategyConfig
)


# ============================================================
# Data Loading
# ============================================================
def load_klines_from_db(db_path: str, symbol: str, timeframe: str) -> List[KlineData]:
    """从 SQLite 加载 K 线数据"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT timestamp, open, high, low, close, volume, is_closed "
        "FROM klines WHERE symbol=? AND timeframe=? ORDER BY timestamp",
        (symbol, timeframe)
    )
    rows = cursor.fetchall()
    conn.close()

    klines = []
    for row in rows:
        klines.append(KlineData(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=row[0],
            open=Decimal(str(row[1])),
            high=Decimal(str(row[2])),
            low=Decimal(str(row[3])),
            close=Decimal(str(row[4])),
            volume=Decimal(str(row[5])),
            is_closed=bool(row[6]),
        ))
    return klines


def load_higher_tf_klines(
    db_path: str, symbol: str, higher_tf: str,
    main_klines: List[KlineData]
) -> List[KlineData]:
    """加载高级别周期 K 线（仅到主周期最后一个时间戳）"""
    if not main_klines:
        return []
    end_ts = main_klines[-1].timestamp
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT timestamp, open, high, low, close, volume, is_closed "
        "FROM klines WHERE symbol=? AND timeframe=? AND timestamp<=? ORDER BY timestamp",
        (symbol, higher_tf, end_ts)
    )
    rows = cursor.fetchall()
    conn.close()

    return [
        KlineData(
            symbol=symbol, timeframe=higher_tf, timestamp=row[0],
            open=Decimal(str(row[1])), high=Decimal(str(row[2])),
            low=Decimal(str(row[3])), close=Decimal(str(row[4])),
            volume=Decimal(str(row[5])), is_closed=bool(row[6]),
        )
        for row in rows
    ]


# ============================================================
# Win Rate Simulation
# ============================================================
def simulate_outcome(
    all_klines: List[KlineData],
    signal_index: int,
    direction: Direction,
    entry_price: Decimal,
    stop_loss: Decimal,
    risk_reward_ratio: Decimal = Decimal("2"),
) -> Tuple[str, Decimal, int]:
    """
    模拟单笔信号结果

    Returns:
        (exit_reason, exit_price, bars_to_exit)
    """
    # 止盈目标
    if direction == Direction.LONG:
        take_profit = entry_price + (entry_price - stop_loss) * risk_reward_ratio
    else:
        take_profit = entry_price - (stop_loss - entry_price) * risk_reward_ratio

    for i in range(signal_index + 1, len(all_klines)):
        kline = all_klines[i]
        if direction == Direction.LONG:
            # LONG: 先触及止盈=WIN, 先触及止损=LOSS
            if kline.high >= take_profit:
                return ("WIN", take_profit, i - signal_index)
            if kline.low <= stop_loss:
                return ("LOSS", stop_loss, i - signal_index)
        else:
            # SHORT: 先触及止盈=WIN, 先触及止损=LOSS
            if kline.low <= take_profit:
                return ("WIN", take_profit, i - signal_index)
            if kline.high >= stop_loss:
                return ("LOSS", stop_loss, i - signal_index)

    return ("UNRESOLVED", entry_price, len(all_klines) - signal_index - 1)


# ============================================================
# Statistics Collection
# ============================================================
@dataclass
class SignalRecord:
    timestamp: int
    direction: str
    score: float
    entry_price: Decimal
    stop_loss: Decimal
    exit_reason: str
    exit_price: Decimal
    bars_to_exit: int
    pnl_ratio: float
    wick_ratio: float
    body_ratio: float


@dataclass
class TimeframeResult:
    symbol: str
    timeframe: str
    total_klines: int = 0
    pinbar_detected: int = 0
    signals_fired: int = 0
    filtered_out: int = 0
    long_signals: int = 0
    short_signals: int = 0
    ema_filtered: int = 0
    mtf_filtered: int = 0
    min_wave_filtered: int = 0
    filter_reasons: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    score_distribution: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    wins: int = 0
    losses: int = 0
    unresolved: int = 0
    total_pnl: Decimal = Decimal("0")
    avg_gain: float = 0.0
    avg_loss: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0

    time_range_start: int = 0
    time_range_end: int = 0

    signals: List[SignalRecord] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        resolved = self.wins + self.losses
        return (self.wins / resolved * 100) if resolved > 0 else 0.0

    @property
    def profit_factor(self) -> float:
        """盈亏比 = 平均盈利 / 平均亏损"""
        if self.avg_loss > 0:
            return self.avg_gain / self.avg_loss
        return 0.0

    @property
    def signal_rate(self) -> float:
        return (self.signals_fired / self.total_klines * 100) if self.total_klines > 0 else 0.0

    @property
    def pinbar_rate(self) -> float:
        return (self.pinbar_detected / self.total_klines * 100) if self.total_klines > 0 else 0.0


def classify_score(score: float) -> str:
    if score >= 0.8:
        return "0.8-1.0 (高)"
    elif score >= 0.6:
        return "0.6-0.8 (中高)"
    elif score >= 0.4:
        return "0.4-0.6 (中)"
    else:
        return "0.0-0.4 (低)"


def run_single_timeframe(
    db_path: str, symbol: str, timeframe: str,
    ema_period: int = 60,
    enable_ema: bool = True,
    enable_mtf: bool = True,
) -> TimeframeResult:
    """运行单一品种+周期的回测"""
    result = TimeframeResult(symbol=symbol, timeframe=timeframe)

    # 加载数据
    klines = load_klines_from_db(db_path, symbol, timeframe)
    if not klines:
        return result

    result.total_klines = len(klines)
    result.time_range_start = klines[0].timestamp
    result.time_range_end = klines[-1].timestamp

    # 加载高级别周期 K 线（用于 MTF）
    mtf_filter_obj = None
    higher_tf_klines = []
    if enable_mtf:
        mtf_mapping = {"15m": "1h", "1h": "4h", "4h": "1d", "1d": "1w"}
        higher_tf = mtf_mapping.get(timeframe)
        if higher_tf:
            higher_tf_klines = load_higher_tf_klines(db_path, symbol, higher_tf, klines)

    # 构建策略
    pinbar_config = PinbarConfig(
        min_wick_ratio=Decimal("0.6"),
        max_body_ratio=Decimal("0.3"),
        body_position_tolerance=Decimal("0.1"),
    )
    pinbar_strategy = PinbarStrategy(pinbar_config)

    filters = []
    if enable_ema:
        filters.append(EmaTrendFilter(period=ema_period, enabled=True))

    mtf_filter_obj = MtfFilter(enabled=enable_mtf)

    runner = StrategyRunner(
        strategies=[pinbar_strategy],
        filters=filters,
        mtf_filter=mtf_filter_obj,
    )

    # 运行逐根 K 线回测
    consecutive_wins = 0
    consecutive_losses = 0
    all_gains = []
    all_losses = []

    for i, kline in enumerate(klines):
        # 更新状态
        runner.update_state(kline)

        # 获取高级别周期趋势
        higher_tf_trends: Dict[str, TrendDirection] = {}
        if higher_tf_klines:
            cutoff = kline.timestamp
            valid_htf = [k for k in higher_tf_klines if k.timestamp <= cutoff]
            if valid_htf:
                latest_htf = valid_htf[-1]
                # 计算 EMA 趋势（简单判断）
                if len(valid_htf) >= ema_period:
                    ema_values = []
                    for hk in valid_htf[-ema_period:]:
                        ema_values.append(hk.close)
                    if ema_values:
                        ema = sum(ema_values, Decimal(0)) / len(ema_values)
                        higher_tf_trends[higher_tf] = (
                            TrendDirection.BULLISH if latest_htf.close > ema else TrendDirection.BEARISH
                        )

        # 当前周期 EMA 趋势
        current_trend = None
        if enable_ema and i >= ema_period:
            # 简化：用最近 ema_period 根 K 线收盘均价做趋势判断
            recent_closes = [klines[j].close for j in range(max(0, i - ema_period + 1), i + 1)]
            if recent_closes:
                ema = sum(recent_closes, Decimal(0)) / len(recent_closes)
                current_trend = (
                    TrendDirection.BULLISH if kline.close > ema else TrendDirection.BEARISH
                )

        # 运行策略
        attempts = runner.run_all(
            kline,
            higher_tf_trends=higher_tf_trends,
            current_trend=current_trend,
            kline_history=klines[max(0, i-2):i],
        )

        for attempt in attempts:
            if attempt.pattern is None:
                continue

            result.pinbar_detected += 1

            if attempt.final_result == "FILTERED":
                result.filtered_out += 1
                for filter_name, filter_result in attempt.filter_results:
                    if not filter_result.passed:
                        result.filter_reasons[filter_result.reason] += 1
                        if filter_name == "ema_trend":
                            result.ema_filtered += 1
                        elif filter_name == "mtf":
                            result.mtf_filtered += 1
                continue

            if attempt.final_result == "SIGNAL_FIRED":
                result.signals_fired += 1
                if attempt.pattern.direction == Direction.LONG:
                    result.long_signals += 1
                    stop_loss = kline.low
                else:
                    result.short_signals += 1
                    stop_loss = kline.high

                # 评分分布
                score_bucket = classify_score(attempt.pattern.score)
                result.score_distribution[score_bucket] += 1

                # 模拟出场
                exit_reason, exit_price, bars = simulate_outcome(
                    klines, i, attempt.pattern.direction,
                    kline.close, stop_loss,
                )

                # 计算盈亏比
                if attempt.pattern.direction == Direction.LONG:
                    pnl = (exit_price - kline.close) / kline.close * 100
                else:
                    pnl = (kline.close - exit_price) / kline.close * 100

                record = SignalRecord(
                    timestamp=kline.timestamp,
                    direction=attempt.pattern.direction.value,
                    score=attempt.pattern.score,
                    entry_price=kline.close,
                    stop_loss=stop_loss,
                    exit_reason=exit_reason,
                    exit_price=exit_price,
                    bars_to_exit=bars,
                    pnl_ratio=float(pnl),
                    wick_ratio=attempt.pattern.details.get("wick_ratio", 0),
                    body_ratio=attempt.pattern.details.get("body_ratio", 0),
                )
                result.signals.append(record)

                if exit_reason == "WIN":
                    result.wins += 1
                    result.total_pnl += Decimal(str(pnl))
                    all_gains.append(abs(float(pnl)))
                    consecutive_wins += 1
                    consecutive_losses = 0
                    result.max_consecutive_wins = max(result.max_consecutive_wins, consecutive_wins)
                elif exit_reason == "LOSS":
                    result.losses += 1
                    result.total_pnl += Decimal(str(pnl))
                    all_losses.append(abs(float(pnl)))
                    consecutive_losses += 1
                    consecutive_wins = 0
                    result.max_consecutive_losses = max(result.max_consecutive_losses, consecutive_losses)
                else:
                    result.unresolved += 1

    # 计算汇总
    if all_gains:
        result.avg_gain = sum(all_gains) / len(all_gains)
    if all_losses:
        result.avg_loss = sum(all_losses) / len(all_losses)

    return result


# ============================================================
# Report Generation
# ============================================================
def print_timeframe_report(result: TimeframeResult):
    """打印单一品种+周期的报告"""
    print("\n" + "=" * 70)
    print(f"  {result.symbol}  {result.timeframe}")
    print("=" * 70)

    # 时间范围
    if result.total_klines > 0:
        start = datetime.fromtimestamp(result.time_range_start / 1000, tz=timezone.utc)
        end = datetime.fromtimestamp(result.time_range_end / 1000, tz=timezone.utc)
        print(f"  时间范围: {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}")

    # 基础统计
    print(f"\n  【信号统计】")
    print(f"    总 K 线数:        {result.total_klines:,}")
    print(f"    Pinbar 识别数:    {result.pinbar_detected:,}  ({result.pinbar_rate:.1f}%)")
    print(f"    信号触发数:       {result.signals_fired:,}  ({result.signal_rate:.1f}%)")
    print(f"    被过滤器拦截:     {result.filtered_out:,}")
    print(f"      - EMA 过滤:     {result.ema_filtered:,}")
    print(f"      - MTF 过滤:     {result.mtf_filtered:,}")
    print(f"    做多信号:         {result.long_signals:,}")
    print(f"    做空信号:         {result.short_signals:,}")

    # 过滤器拒绝原因 TOP 5
    if result.filter_reasons:
        print(f"\n  【过滤器拒绝原因 TOP 5】")
        sorted_reasons = sorted(result.filter_reasons.items(), key=lambda x: x[1], reverse=True)
        for reason, count in sorted_reasons[:5]:
            print(f"    {reason:30s}  {count:,}")

    # 胜率与盈亏
    resolved = result.wins + result.losses
    print(f"\n  【模拟胜率与盈亏】(已出场 {resolved} 笔, 未出场 {result.unresolved} 笔)")
    print(f"    胜方次数:         {result.wins:,}")
    print(f"    输方次数:         {result.losses:,}")
    print(f"    胜率:             {result.win_rate:.1f}%")
    print(f"    平均盈利:         {result.avg_gain:.2f}%")
    print(f"    平均亏损:         {result.avg_loss:.2f}%")
    print(f"    盈亏比:           {result.profit_factor:.2f}")
    print(f"    最大连胜:         {result.max_consecutive_wins}")
    print(f"    最大连亏:         {result.max_consecutive_losses}")
    print(f"    累计盈亏:         {result.total_pnl:.2f}%")

    # 评分分布
    if result.score_distribution:
        print(f"\n  【形态评分分布】")
        for bucket in ["0.0-0.4 (低)", "0.4-0.6 (中)", "0.6-0.8 (中高)", "0.8-1.0 (高)"]:
            count = result.score_distribution.get(bucket, 0)
            bar = "█" * (count // max(1, count)) if count > 0 else ""
            print(f"    {bucket:15s}  {count:>4,}  {bar}")

    # 评分 vs 胜率交叉分析
    if result.signals:
        print(f"\n  【评分 vs 胜率】")
        score_buckets = {"0.0-0.4 (低)": [], "0.4-0.6 (中)": [], "0.6-0.8 (中高)": [], "0.8-1.0 (高)": []}
        for sig in result.signals:
            if sig.exit_reason in ("WIN", "LOSS"):
                bucket = classify_score(sig.score)
                score_buckets[bucket].append(sig.exit_reason == "WIN")

        for bucket in ["0.0-0.4 (低)", "0.4-0.6 (中)", "0.6-0.8 (中高)", "0.8-1.0 (高)"]:
            outcomes = score_buckets[bucket]
            if outcomes:
                wr = sum(1 for x in outcomes if x) / len(outcomes) * 100
                print(f"    {bucket:15s}  胜率 {wr:.1f}% ({len(outcomes)} 笔)")


def print_summary_table(all_results: List[TimeframeResult]):
    """打印汇总表"""
    print("\n" + "=" * 120)
    print("  跨品种/跨周期汇总表")
    print("=" * 120)
    print(f"  {'品种':20s} {'周期':6s} {'K线数':>8s} {'Pinbar':>7s} {'信号':>6s} {'胜率':>6s} "
          f"{'盈亏比':>6s} {'累计盈亏':>8s} {'最大连胜':>5s} {'最大连亏':>5s}")
    print("-" * 120)

    for r in all_results:
        print(f"  {r.symbol:20s} {r.timeframe:6s} {r.total_klines:>8,} {r.pinbar_detected:>7,} "
              f"{r.signals_fired:>6,} {r.win_rate:>5.1f}% {r.profit_factor:>6.2f} "
              f"{r.total_pnl:>7.2f}% {r.max_consecutive_wins:>5d} {r.max_consecutive_losses:>5d}")

    print("=" * 120)

    # 找出最优组合
    resolved_results = [r for r in all_results if (r.wins + r.losses) > 0]
    if resolved_results:
        best_wr = max(resolved_results, key=lambda x: x.win_rate)
        best_pf = max(resolved_results, key=lambda x: x.profit_factor)
        best_pnl = max(resolved_results, key=lambda x: x.total_pnl)

        print(f"\n  【最优组合】")
        print(f"    最高胜率:   {best_wr.symbol} {best_wr.timeframe}  胜率 {best_wr.win_rate:.1f}%")
        print(f"    最高盈亏比: {best_pf.symbol} {best_pf.timeframe}  盈亏比 {best_pf.profit_factor:.2f}")
        print(f"    最高累计盈亏: {best_pnl.symbol} {best_pnl.timeframe}  累计盈亏 {best_pnl.total_pnl:.2f}%")


# ============================================================
# Main
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="Pinbar 集成测试 - 真实 K 线数据验证")
    parser.add_argument("--symbol", required=True, help="品种，如 BTC/USDT:USDT")
    parser.add_argument("--timeframes", nargs="+", default=["15m", "1h", "4h"], help="周期列表")
    parser.add_argument("--db-path", default="data/v3_dev.db", help="数据库路径")
    parser.add_argument("--ema-period", type=int, default=60, help="EMA 周期")
    parser.add_argument("--no-ema", action="store_true", help="禁用 EMA 过滤")
    parser.add_argument("--no-mtf", action="store_true", help="禁用 MTF 过滤")
    args = parser.parse_args()

    db_path = Path(__file__).parent.parent.parent / args.db_path
    if not db_path.exists():
        print(f"错误：数据库文件不存在: {db_path}")
        sys.exit(1)

    print("=" * 70)
    print("  Pinbar 集成测试 - 真实 K 线数据验证")
    print("=" * 70)
    print(f"  品种: {args.symbol}")
    print(f"  周期: {', '.join(args.timeframes)}")
    print(f"  数据库: {db_path}")
    print(f"  EMA 周期: {args.ema_period}")
    print(f"  EMA 过滤: {'禁用' if args.no_ema else '启用'}")
    print(f"  MTF 过滤: {'禁用' if args.no_mtf else '启用'}")

    all_results = []
    for tf in args.timeframes:
        print(f"\n  正在回测 {args.symbol} {tf}...")
        start_time = time.time()

        result = run_single_timeframe(
            str(db_path), args.symbol, tf,
            ema_period=args.ema_period,
            enable_ema=not args.no_ema,
            enable_mtf=not args.no_mtf,
        )

        elapsed = time.time() - start_time
        print(f"  完成 ({elapsed:.1f}s) - {result.total_klines:,} 根 K 线, {result.signals_fired} 个信号")

        print_timeframe_report(result)
        all_results.append(result)

    # 汇总
    print_summary_table(all_results)

    return all_results


if __name__ == "__main__":
    main()
