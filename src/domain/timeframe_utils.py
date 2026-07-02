"""
Timeframe utilities for MTF (Multi-Timeframe) alignment.

Core responsibility: Ensure MTF filters use correctly aligned,
closed kline data for trend calculation.
"""
from typing import Dict, Optional, List
from decimal import Decimal

from .models import KlineData, TrendDirection


# MTF 映射默认值（可被用户配置覆盖）
DEFAULT_MTF_MAPPING = {
    "15m": "1h",
    "1h": "4h",
    "4h": "1d",
    "1d": "1w",
}

# 时间周期毫秒数映射（支持所有 CCXT 标准时间框架）
TIMEFRAME_TO_MS = {
    "1m": 60 * 1000,
    "3m": 3 * 60 * 1000,
    "5m": 5 * 60 * 1000,
    "15m": 15 * 60 * 1000,
    "30m": 30 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "2h": 2 * 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "6h": 6 * 60 * 60 * 1000,
    "12h": 12 * 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
    "2d": 2 * 24 * 60 * 60 * 1000,
    "3d": 3 * 24 * 60 * 60 * 1000,
    "1w": 7 * 24 * 60 * 60 * 1000,
    "2w": 2 * 7 * 24 * 60 * 60 * 1000,
    "1M": 30 * 24 * 60 * 60 * 1000,  # 月度 K 线（近似 30 天）
}


def get_higher_timeframe(
    current_timeframe: str,
    mtf_mapping: Optional[Dict[str, str]] = None
) -> Optional[str]:
    """
    Get the higher timeframe for MTF analysis.

    Args:
        current_timeframe: Current kline timeframe (e.g., "15m")
        mtf_mapping: Custom MTF mapping (uses DEFAULT_MTF_MAPPING if None)

    Returns:
        Higher timeframe string, or None if no higher timeframe exists
    """
    # Start with default mapping, then override with custom mapping
    mapping = DEFAULT_MTF_MAPPING.copy()
    if mtf_mapping:
        mapping.update(mtf_mapping)
    return mapping.get(current_timeframe)


def parse_timeframe_to_ms(timeframe: str) -> int:
    """
    Parse timeframe string to milliseconds.

    Args:
        timeframe: Timeframe string (e.g., "15m", "1h", "4h")

    Returns:
        Milliseconds as integer

    Raises:
        ValueError: If timeframe format is invalid
    """
    if timeframe in TIMEFRAME_TO_MS:
        return TIMEFRAME_TO_MS[timeframe]

    # Try to parse custom timeframe (e.g., "2h", "30m")
    try:
        if timeframe.endswith('m'):
            minutes = int(timeframe[:-1])
            return minutes * 60 * 1000
        elif timeframe.endswith('h'):
            hours = int(timeframe[:-1])
            return hours * 60 * 60 * 1000
        elif timeframe.endswith('d'):
            days = int(timeframe[:-1])
            return days * 24 * 60 * 60 * 1000
        elif timeframe.endswith('w'):
            weeks = int(timeframe[:-1])
            return weeks * 7 * 24 * 60 * 60 * 1000
    except ValueError:
        raise ValueError(f"Invalid timeframe format: {timeframe}")

    raise ValueError(f"Invalid timeframe format: {timeframe}")


def get_last_closed_kline_index(
    klines: List[KlineData],
    current_timestamp: int,
    timeframe: str
) -> int:
    """
    Find the index of the last closed kline for MTF analysis.

    A kline is considered "closed" when its end time <= current_timestamp.
    Kline end time = kline.timestamp + period_duration.

    Args:
        klines: List of klines (sorted by timestamp ascending)
        current_timestamp: Current kline's timestamp (milliseconds)
        timeframe: The timeframe of the klines being checked

    Returns:
        Index of the last closed kline, or -1 if none found

    Example:
        current_timestamp = 10:15 (15m kline)
        timeframe = "1h"
        Returns index of 10:00 kline (10:00-11:00 period, closes at 11:00)

        current_timestamp = 11:00 (exactly when 10:00-11:00 kline closes)
        timeframe = "1h"
        Returns index of 10:00 kline (just closed, available for MTF)

        current_timestamp = 10:59 (before 10:00-11:00 kline closes)
        timeframe = "1h"
        Returns index of 09:00 kline (10:00-11:00 not yet closed)
    """
    period_ms = parse_timeframe_to_ms(timeframe)

    best_index = -1
    for i, kline in enumerate(klines):
        # Calculate when this kline ends
        kline_end_time = kline.timestamp + period_ms

        if kline_end_time <= current_timestamp:
            # This kline has closed, it's safe to use for MTF analysis
            best_index = i
        else:
            # This kline hasn't closed yet, and neither do any after it
            # (klines are sorted by timestamp ascending)
            break

    return best_index
