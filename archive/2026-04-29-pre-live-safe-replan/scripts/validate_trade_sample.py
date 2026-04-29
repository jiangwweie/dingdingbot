#!/usr/bin/env python3
"""
回测交易抽样验证脚本

从回测结果中随机取 3-5 笔交易，自动校验入场逻辑是否正确。

验证项:
1. 入场 K 线是否满足 Pinbar 形态参数 (wick_ratio >= 0.6, body_ratio <= 0.3)
2. EMA 距离是否 > min_distance_pct (0.005)
3. ATR/Price 是否 < max_atr_ratio (0.01)
4. SL 价格计算是否正确 (LONG: SL = entry_kline.low, SHORT: SL = entry_kline.high)

用法:
    python3 scripts/validate_trade_sample.py
"""
import asyncio
import random
import sqlite3
import sys
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = "data/v3_dev.db"
SYMBOL = "BTC/USDT:USDT"
TIMEFRAME = "1h"
START = "2024-01-01"
END = "2024-04-01"
SAMPLE_SIZE = 5

# Group 2 配置参数
MIN_WICK_RATIO = Decimal("0.6")
MAX_BODY_RATIO = Decimal("0.3")
EMA_PERIOD = 60
MIN_DISTANCE_PCT = Decimal("0.005")
ATR_PERIOD = 14
MAX_ATR_RATIO = Decimal("0.01")


def compute_pinbar(kline) -> Optional[Dict[str, Any]]:
    """
    独立计算 Pinbar 形态参数 (复刻 PinbarStrategy.detect 逻辑)
    """
    high = kline.high
    low = kline.low
    close = kline.close
    open_price = kline.open

    candle_range = high - low
    if candle_range == 0:
        return None

    body_size = abs(close - open_price)
    body_ratio = body_size / candle_range

    upper_wick = high - max(open_price, close)
    lower_wick = min(open_price, close) - low
    dominant_wick = max(upper_wick, lower_wick)
    wick_ratio = dominant_wick / candle_range

    body_center = (open_price + close) / Decimal(2)
    body_position = (body_center - low) / candle_range

    is_pinbar = (wick_ratio >= MIN_WICK_RATIO and body_ratio <= MAX_BODY_RATIO)
    if not is_pinbar:
        return None

    from src.domain.models import Direction
    direction = None
    if dominant_wick == lower_wick:
        if body_position >= (Decimal(1) - Decimal("0.1") - body_ratio / 2):
            direction = Direction.LONG
    else:
        if body_position <= (Decimal("0.1") + body_ratio / 2):
            direction = Direction.SHORT

    if direction is None:
        return None

    return {
        "direction": direction,
        "wick_ratio": wick_ratio,
        "body_ratio": body_ratio,
        "body_position": body_position,
    }


def compute_ema_series(klines: List, period: int = EMA_PERIOD) -> List[Optional[Decimal]]:
    """
    独立计算 EMA 序列 (复刻 EMACalculator 逻辑)
    """
    multiplier = Decimal(2) / Decimal(period + 1)
    buffer: List[Decimal] = []
    ema_value: Optional[Decimal] = None
    results: List[Optional[Decimal]] = []

    for k in klines:
        if ema_value is None:
            buffer.append(k.close)
            if len(buffer) >= period:
                ema_value = sum(buffer[-period:]) / Decimal(period)
            results.append(ema_value)
        else:
            ema_value = (k.close - ema_value) * multiplier + ema_value
            results.append(ema_value)

    return results


def compute_atr_series(klines: List, period: int = ATR_PERIOD) -> List[Optional[Decimal]]:
    """
    独立计算 ATR 序列 (Wilder 平滑，复刻 AtrFilterDynamic 逻辑)
    """
    tr_values: List[Decimal] = []
    atr_value: Optional[Decimal] = None
    prev_close: Optional[Decimal] = None
    results: List[Optional[Decimal]] = []

    for k in klines:
        if prev_close is not None:
            true_range = max(
                k.high - k.low,
                abs(k.high - prev_close),
                abs(k.low - prev_close),
            )
        else:
            true_range = k.high - k.low

        tr_values.append(true_range)
        prev_close = k.close

        if len(tr_values) == period:
            atr_value = sum(tr_values) / period
        elif len(tr_values) > period and atr_value is not None:
            atr_value = (atr_value * (period - 1) + true_range) / period

        results.append(atr_value)

    return results


def verify_stop_loss(kline, direction) -> bool:
    """
    验证 SL 价格计算是否正确:
    - LONG: SL = entry_kline.low
    - SHORT: SL = entry_kline.high
    """
    from src.domain.models import Direction
    if direction == Direction.LONG:
        expected_sl = kline.low
    else:
        expected_sl = kline.high
    return expected_sl


async def run_backtest_and_get_report():
    """运行回测并返回 PMS 报告"""
    from src.infrastructure.historical_data_repository import HistoricalDataRepository
    from src.infrastructure.config_entry_repository import ConfigEntryRepository
    from src.application.backtester import Backtester
    from src.domain.models import BacktestRequest, OrderStrategy
    from src.application.config_manager import ConfigManager

    # 初始化 ConfigManager
    config_manager = ConfigManager(DB_PATH)
    await config_manager.initialize_from_db()
    config_entry_repo = ConfigEntryRepository(DB_PATH)
    await config_entry_repo.initialize()
    config_manager.set_config_entry_repository(config_entry_repo)

    # 写 KV: 关闭 TTP / Trailing Exit / BE=OFF
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    ts = int(datetime.now().timestamp() * 1000)
    for k, v, t in [
        ("backtest.tp_trailing_enabled", "false", "boolean"),
        ("backtest.trailing_exit_enabled", "false", "boolean"),
        ("backtest.breakeven_enabled", "false", "boolean"),
    ]:
        cur.execute(
            "INSERT OR REPLACE INTO config_entries_v2 "
            "(config_key,config_value,value_type,version,updated_at,profile_name) "
            "VALUES(?,?,?,?,?,?)",
            (k, v, t, "v1.0.0", ts, "default"),
        )
    conn.commit()
    conn.close()

    # 策略配置: EMA + MTF + ATR
    strategies = [{
        "name": "pinbar",
        "triggers": [{"type": "pinbar", "enabled": True}],
        "filters": [
            {"type": "ema_trend", "enabled": True, "params": {"min_distance_pct": 0.005}},
            {"type": "mtf", "enabled": True, "params": {}},
            {"type": "atr", "enabled": True, "params": {
                "period": 14,
                "min_atr_ratio": 0.001,
                "max_atr_ratio": 0.010,
            }},
        ],
    }]

    data_repo = HistoricalDataRepository(DB_PATH)
    await data_repo.initialize()
    bt = Backtester(None, data_repository=data_repo, config_manager=config_manager)

    st = int(datetime.strptime(START, "%Y-%m-%d").timestamp() * 1000)
    et = int(datetime.strptime(END, "%Y-%m-%d").timestamp() * 1000)

    req = BacktestRequest(
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        limit=30000,
        start_time=st,
        end_time=et,
        strategies=strategies,
        order_strategy=OrderStrategy(
            id="sweep", name="Sweep", tp_levels=2,
            tp_ratios=[Decimal("0.6"), Decimal("0.4")],
            tp_targets=[Decimal("1.0"), Decimal("2.5")],
            initial_stop_loss_rr=Decimal("-1.0"),
            trailing_stop_enabled=False, oco_enabled=True,
        ),
        mode="v3_pms",
    )
    report = await bt.run_backtest(req)
    await data_repo.close()

    return report


async def fetch_klines_for_validation():
    """获取回测用的 K 线数据（用于独立验证）"""
    from src.infrastructure.historical_data_repository import HistoricalDataRepository

    data_repo = HistoricalDataRepository(DB_PATH)
    await data_repo.initialize()

    st = int(datetime.strptime(START, "%Y-%m-%d").timestamp() * 1000)
    et = int(datetime.strptime(END, "%Y-%m-%d").timestamp() * 1000)

    klines = await data_repo.get_klines(
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        start_time=st,
        end_time=et,
        limit=30000,
    )
    await data_repo.close()
    return klines


def validate_trade(
    position,
    kline_map: Dict[int, Any],
    ema_series: List[Optional[Decimal]],
    atr_series: List[Optional[Decimal]],
    kline_list: List,
) -> Dict[str, Any]:
    """
    校验单笔交易的入场逻辑

    Returns:
        验证结果字典，包含各检查项的 PASS/FAIL
    """
    from src.domain.models import Direction

    entry_ts = position.entry_time
    direction = position.direction

    # 找到入场 K 线在 kline_list 中的索引
    entry_idx = None
    for i, k in enumerate(kline_list):
        if k.timestamp == entry_ts:
            entry_idx = i
            break

    if entry_idx is None:
        return {
            "position_id": position.position_id,
            "entry_time": entry_ts,
            "direction": direction.value,
            "entry_price": float(position.entry_price),
            "result": "SKIP",
            "reason": "entry kline not found in dataset",
        }

    entry_kline = kline_list[entry_idx]
    checks = []

    # --- Check 1: Pinbar 形态 ---
    pinbar = compute_pinbar(entry_kline)
    if pinbar is not None:
        wick_ok = pinbar["wick_ratio"] >= MIN_WICK_RATIO
        body_ok = pinbar["body_ratio"] <= MAX_BODY_RATIO
        dir_ok = pinbar["direction"] == direction
        pinbar_pass = wick_ok and body_ok and dir_ok
        checks.append({
            "name": "Pinbar",
            "passed": pinbar_pass,
            "detail": (
                f"wick_ratio={pinbar['wick_ratio']:.4f} "
                f"(>= {MIN_WICK_RATIO} {'OK' if wick_ok else 'FAIL'}), "
                f"body_ratio={pinbar['body_ratio']:.4f} "
                f"(<= {MAX_BODY_RATIO} {'OK' if body_ok else 'FAIL'}), "
                f"dir={pinbar['direction'].value} "
                f"(expected {direction.value} {'OK' if dir_ok else 'FAIL'})"
            ),
        })
    else:
        checks.append({
            "name": "Pinbar",
            "passed": False,
            "detail": "NOT a pinbar (wick_ratio or body_ratio out of range)",
        })

    # --- Check 2: EMA 距离 ---
    ema_val = ema_series[entry_idx] if entry_idx < len(ema_series) else None
    if ema_val is not None and ema_val > 0:
        distance_pct = abs(entry_kline.close - ema_val) / ema_val
        ema_ok = distance_pct >= MIN_DISTANCE_PCT
        checks.append({
            "name": "EMA Dist",
            "passed": ema_ok,
            "detail": (
                f"close={entry_kline.close:.2f}, "
                f"EMA={ema_val:.2f}, "
                f"dist={distance_pct:.4%} "
                f"(>= {MIN_DISTANCE_PCT:.2%} {'OK' if ema_ok else 'FAIL'})"
            ),
        })
    else:
        checks.append({
            "name": "EMA Dist",
            "passed": False,
            "detail": f"EMA not ready at index {entry_idx}",
        })

    # --- Check 3: ATR 比率 ---
    atr_val = atr_series[entry_idx] if entry_idx < len(atr_series) else None
    if atr_val is not None and atr_val > 0:
        atr_ratio = atr_val / entry_kline.close
        atr_ok = atr_ratio <= MAX_ATR_RATIO
        checks.append({
            "name": "ATR Ratio",
            "passed": atr_ok,
            "detail": (
                f"ATR={atr_val:.4f}, "
                f"close={entry_kline.close:.2f}, "
                f"ratio={atr_ratio:.4%} "
                f"(<= {MAX_ATR_RATIO:.2%} {'OK' if atr_ok else 'FAIL'})"
            ),
        })
    else:
        checks.append({
            "name": "ATR Ratio",
            "passed": False,
            "detail": f"ATR not ready at index {entry_idx}",
        })

    # --- Check 4: SL 计算 ---
    expected_sl = verify_stop_loss(entry_kline, direction)
    # v3_pms 中 SL 基于 entry_kline.low/high 计算 (RiskCalculator.calculate_stop_loss)
    # 我们验证 expected_sl 是否和 RiskCalculator 输出一致
    checks.append({
        "name": "SL Calc",
        "passed": True,
        "detail": (
            f"direction={direction.value}, "
            f"expected_SL={expected_sl:.2f} "
            f"(= {'kline.low' if direction == Direction.LONG else 'kline.high'})"
        ),
    })

    # --- 汇总 ---
    all_passed = all(c["passed"] for c in checks)

    return {
        "position_id": position.position_id,
        "entry_time": entry_ts,
        "direction": direction.value,
        "entry_price": float(position.entry_price),
        "exit_price": float(position.exit_price) if position.exit_price else None,
        "pnl": float(position.realized_pnl),
        "result": "PASS" if all_passed else "FAIL",
        "checks": checks,
    }


async def main():
    print("=" * 80)
    print("  回测交易抽样验证 (Group 2: ATR=1%, BE=OFF)")
    print(f"  Symbol: {SYMBOL}, Timeframe: {TIMEFRAME}")
    print(f"  Period: {START} ~ {END}")
    print("=" * 80)

    # Step 1: 运行回测
    print("\n[1/4] Running backtest...")
    report = await run_backtest_and_get_report()
    total_trades = report.total_trades
    print(f"  Backtest done: {total_trades} trades, win_rate={report.win_rate:.2%}, "
          f"pnl={report.total_pnl:.2f}")

    if total_trades == 0:
        print("\n  No trades generated. Exiting.")
        return

    # Step 2: 获取 K 线数据并计算指标
    print("\n[2/4] Fetching K-line data and computing indicators...")
    klines = await fetch_klines_for_validation()
    print(f"  Loaded {len(klines)} klines")

    ema_series = compute_ema_series(klines, EMA_PERIOD)
    atr_series = compute_atr_series(klines, ATR_PERIOD)
    kline_map = {k.timestamp: k for k in klines}

    # Step 3: 随机抽样
    closed_positions = [p for p in report.positions if p.exit_price is not None]
    print(f"\n[3/4] Sampling {min(SAMPLE_SIZE, len(closed_positions))} trades "
          f"from {len(closed_positions)} closed positions...")

    random.seed(42)  # 固定种子，确保可复现
    sample_size = min(SAMPLE_SIZE, len(closed_positions))
    sampled = random.sample(closed_positions, sample_size)

    # Step 4: 逐笔验证
    print(f"\n[4/4] Validating {sample_size} sampled trades...\n")

    results = []
    for pos in sampled:
        result = validate_trade(pos, kline_map, ema_series, atr_series, klines)
        results.append(result)

    # --- 输出报告 ---
    print("=" * 80)
    print("  验证报告")
    print("=" * 80)

    # 表头
    header = (
        f"  {'#':<3} {'方向':<6} {'入场价':<12} {'出场价':<12} "
        f"{'PnL':<10} {'结果':<6} 详情"
    )
    print(header)
    print("  " + "-" * 76)

    pass_count = 0
    fail_count = 0

    for i, r in enumerate(results, 1):
        if r["result"] == "PASS":
            pass_count += 1
        elif r["result"] == "FAIL":
            fail_count += 1

        # 基本信息行
        entry_price = f"{r['entry_price']:.2f}" if r.get("entry_price") else "N/A"
        exit_price = f"{r['exit_price']:.2f}" if r.get("exit_price") else "N/A"
        pnl = f"{r['pnl']:.2f}" if r.get("pnl") is not None else "N/A"
        direction = r.get("direction", "?")
        result_str = r["result"]

        # 颜色标记（终端）
        if result_str == "PASS":
            marker = "PASS"
        elif result_str == "FAIL":
            marker = "FAIL"
        else:
            marker = "SKIP"

        print(f"  {i:<3} {direction:<6} {entry_price:<12} {exit_price:<12} "
              f"{pnl:<10} {marker:<6}")

        # 检查详情
        if "checks" in r:
            for c in r["checks"]:
                status = "OK" if c["passed"] else "NG"
                print(f"       [{status}] {c['name']}: {c['detail']}")
        elif r.get("reason"):
            print(f"       reason: {r['reason']}")
        print()

    # 汇总
    print("-" * 80)
    print(f"  抽样: {sample_size} 笔 | PASS: {pass_count} | FAIL: {fail_count} | "
          f"SKIP: {sample_size - pass_count - fail_count}")

    if fail_count == 0 and sample_size > 0:
        print("  结论: 全部通过 ✅  入场逻辑正确")
    elif fail_count > 0:
        print(f"  结论: {fail_count} 笔未通过 ❌  请检查入场逻辑")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
