"""
Strategy Engine - Pinbar detection, EMA filtering, MTF validation.
Pure business logic, no external dependencies allowed.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Dict, List, Tuple, Any
from enum import Enum

from .models import (
    KlineData,
    Direction,
    TrendDirection,
    MtfStatus,
    PatternResult,
    FilterResult,
    SignalAttempt,
)
from .indicators import EMACalculator, EMACache
from .filter_factory import FilterBase, FilterContext, TraceEvent, FilterFactory, AtrFilterDynamic
from src.infrastructure.logger import logger


# ============================================================
# Pinbar Configuration
# ============================================================
class PinbarConfig:
    """Configuration for Pinbar geometric pattern detection."""

    def __init__(
        self,
        min_wick_ratio: Decimal = Decimal("0.6"),
        max_body_ratio: Decimal = Decimal("0.3"),
        body_position_tolerance: Decimal = Decimal("0.1"),
    ):
        """
        Initialize Pinbar configuration.

        Args:
            min_wick_ratio: Minimum ratio of dominant wick to total candle range
            max_body_ratio: Maximum ratio of body to total candle range
            body_position_tolerance: Tolerance for body position within candle
        """
        self.min_wick_ratio = Decimal(min_wick_ratio)
        self.max_body_ratio = Decimal(max_body_ratio)
        self.body_position_tolerance = Decimal(body_position_tolerance)

        # Validate configuration
        if not (Decimal(0) < self.min_wick_ratio <= Decimal(1)):
            raise ValueError(f"min_wick_ratio must be in (0, 1], got {self.min_wick_ratio}")
        if not (Decimal(0) <= self.max_body_ratio < Decimal(1)):
            raise ValueError(f"max_body_ratio must be in [0, 1), got {self.max_body_ratio}")
        if not (Decimal(0) <= self.body_position_tolerance < Decimal("0.5")):
            raise ValueError(
                f"body_position_tolerance must be in [0, 0.5), "
                f"got {self.body_position_tolerance}"
            )


# ============================================================
# Pinbar Detection Result
# ============================================================
class PinbarResult:
    """Result of Pinbar pattern detection."""

    def __init__(
        self,
        is_pinbar: bool,
        direction: Optional[Direction],
        wick_ratio: Decimal,
        body_ratio: Decimal,
    ):
        self.is_pinbar = is_pinbar
        self.direction = direction  # LONG for bullish, SHORT for bearish, None if not pinbar
        self.wick_ratio = wick_ratio
        self.body_ratio = body_ratio


# ============================================================
# Strategy Configuration
# ============================================================
class StrategyConfig:
    """Complete strategy configuration."""

    def __init__(
        self,
        pinbar_config: PinbarConfig,
        trend_filter_enabled: bool = True,
        mtf_validation_enabled: bool = True,
        ema_period: int = 60,
    ):
        self.pinbar_config = pinbar_config
        self.trend_filter_enabled = trend_filter_enabled
        self.mtf_validation_enabled = mtf_validation_enabled
        self.ema_period = ema_period


# ============================================================
# ABC Interfaces
# ============================================================
class Strategy(ABC):
    """策略接口：负责从 K 线中识别交易形态"""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def detect(self, kline: KlineData) -> Optional[PatternResult]:
        ...


class Filter(ABC):
    """过滤器接口：对已识别的形态进行逻辑判断"""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def check(self, pattern: PatternResult, context: FilterContext) -> FilterResult:
        ...

    def update(self, kline: KlineData, symbol: str, timeframe: str) -> None:
        """每根 K 线都调用，供有状态的过滤器（如 EMA）更新内部状态"""
        pass


# ============================================================
# Pattern Strategy Base Class - Unified Scoring
# ============================================================
class PatternStrategy(Strategy):
    """
    Base class for pattern-based strategies (Pinbar, Engulfing, etc.).

    Provides unified scoring formula that all pattern strategies inherit:
    score = pattern_ratio × 0.7 + min(atr_ratio, 2.0) × 0.3

    This ensures fair comparison within the same strategy type.
    """

    def calculate_score(
        self,
        pattern_ratio: Decimal,  # 形态质量比例 (0~1)
        atr_ratio: Optional[Decimal] = None,  # ATR 倍数 (可选)
    ) -> float:
        """
        统一评分公式（所有形态策略共用）

        Args:
            pattern_ratio: 形态质量比例（0~1），如 Pinbar 的 wick_ratio
            atr_ratio: ATR 倍数（可选），candle_range / ATR

        Returns:
            最终评分（0~1）
        """
        base_score = float(pattern_ratio)

        if atr_ratio and atr_ratio > 0:
            # ATR 加分（波幅质量），上限 2 倍
            atr_bonus = min(float(atr_ratio), 2.0) * 0.3
            score = base_score * 0.7 + atr_bonus
        else:
            score = base_score

        return min(score, 1.0)


# ============================================================
# PinbarStrategy Implementation
# ============================================================
class PinbarStrategy(PatternStrategy):
    """Pinbar strategy implementation."""

    # S6-4-4: 最小波幅检查（防止极小波幅 K 线产生异常信号）
    MIN_CANDLE_RANGE = Decimal("0.0001")  # 最小波幅 0.0001

    def __init__(self, config: PinbarConfig):
        self._config = config

    @property
    def name(self) -> str:
        return "pinbar"

    def detect(self, kline: KlineData, atr_value: Optional[Decimal] = None) -> Optional[PatternResult]:
        """
        Detect Pinbar geometric pattern on a single K-line.

        Color-agnostic: works for both bullish and bearish candles.

        Bullish Pinbar: Long lower wick, body positioned at top
        Bearish Pinbar: Long upper wick, body positioned at bottom

        Args:
            kline: K-line data to analyze
            atr_value: Optional ATR value for dynamic minimum range check

        Returns:
            PatternResult if Pinbar detected, None otherwise
        """
        cfg = self._config

        high = kline.high
        low = kline.low
        close = kline.close
        open_price = kline.open

        # Calculate candle range
        candle_range = high - low

        # S6-4-4: 添加最小波幅检查（防止极小波幅 K 线产生异常信号）
        if candle_range == Decimal(0):
            return None

        # ✅ P0 修复：动态最小波幅检查
        # 如果有 ATR → min_range = atr * 0.1（动态阈值）
        # 如果无 ATR → min_range = 0.5（固定后备值）
        if atr_value and atr_value > 0:
            min_required_range = atr_value * Decimal("0.1")  # ATR 的 10%
            logger.debug(
                f"[PINBAR_MIN_RANGE] {kline.symbol} {kline.timeframe}: "
                f"range={candle_range}, min={min_required_range} (atr={atr_value})"
            )
        else:
            min_required_range = Decimal("0.5")  # 固定后备值

        if candle_range < min_required_range:
            # 波幅太小，跳过
            logger.debug(
                f"[PINBAR_RANGE_TOO_SMALL] {kline.symbol} {kline.timeframe}: "
                f"range={candle_range} < min={min_required_range} (atr={atr_value})"
            )
            return None

        # Calculate body size
        body_size = abs(close - open_price)
        body_ratio = body_size / candle_range

        # Calculate upper and lower wicks
        upper_wick = high - max(open_price, close)
        lower_wick = min(open_price, close) - low

        # Determine dominant wick and calculate ratio
        dominant_wick = max(upper_wick, lower_wick)
        wick_ratio = dominant_wick / candle_range

        # Check if it meets Pinbar criteria
        is_pinbar = (
            wick_ratio >= cfg.min_wick_ratio
            and body_ratio <= cfg.max_body_ratio
        )

        if not is_pinbar:
            return None

        # Determine direction based on dominant wick position
        # Bullish: long lower wick, body at top
        # Bearish: long upper wick, body at bottom

        # Calculate body position (0 = bottom of candle, 1 = top of candle)
        body_center = (open_price + close) / Decimal(2)
        body_position = (body_center - low) / candle_range

        direction = None
        if dominant_wick == lower_wick:
            # Lower wick is dominant - potential bullish pinbar
            # Body should be positioned in upper portion of candle
            if body_position >= (Decimal(1) - cfg.body_position_tolerance - body_ratio / 2):
                direction = Direction.LONG
        else:
            # Upper wick is dominant - potential bearish pinbar
            # Body should be positioned in lower portion of candle
            if body_position <= (cfg.body_position_tolerance + body_ratio / 2):
                direction = Direction.SHORT

        if direction is None:
            return None

        # Calculate score using unified formula from PatternStrategy base class
        # score = pattern_ratio × 0.7 + min(atr_ratio, 2.0) × 0.3
        pattern_ratio = wick_ratio  # Pinbar 使用影线占比作为形态质量

        if atr_value and atr_value > 0:
            candle_range = kline.high - kline.low
            atr_ratio = candle_range / atr_value
            score = self.calculate_score(pattern_ratio, atr_ratio)
        else:
            # Fallback to legacy scoring when ATR not available
            score = float(pattern_ratio)

        return PatternResult(
            strategy_name="pinbar",
            direction=direction,
            score=score,
            details={
                "wick_ratio": float(wick_ratio),
                "body_ratio": float(body_ratio),
                "body_position": float(body_position),
            },
        )


# ============================================================
# EmaTrendFilter Implementation
# ============================================================
class EmaTrendFilter(Filter):
    """EMA trend filter implementation."""

    def __init__(self, period: int, enabled: bool):
        self._period = period
        self._enabled = enabled
        self._ema_calculators: Dict[str, EMACalculator] = {}  # key: "symbol:timeframe"

    @property
    def name(self) -> str:
        return "ema_trend"

    def update(self, kline: KlineData, symbol: str, timeframe: str) -> None:
        """更新 EMA 状态（每根 K 线都调用）"""
        key = f"{symbol}:{timeframe}"
        if key not in self._ema_calculators:
            self._ema_calculators[key] = EMACalculator(self._period)
        self._ema_calculators[key].update(kline.close)

    def get_trend(self, kline: KlineData, symbol: str, timeframe: str) -> Optional[TrendDirection]:
        """获取当前 EMA 趋势（供外部兼容调用）"""
        key = f"{symbol}:{timeframe}"
        if key not in self._ema_calculators:
            return None
        ema = self._ema_calculators[key].value
        if ema is None:
            return None
        return TrendDirection.BULLISH if kline.close > ema else TrendDirection.BEARISH

    def check(self, pattern: PatternResult, context: FilterContext) -> FilterResult:
        if not self._enabled:
            return FilterResult(passed=True, reason="trend_filter_disabled")

        current_trend = context.current_trend
        if current_trend is None:
            return FilterResult(passed=False, reason="ema_data_not_ready")

        # Check if pattern direction matches trend
        if pattern.direction == Direction.LONG:
            if current_trend == TrendDirection.BULLISH:
                return FilterResult(passed=True, reason="trend_match")
            else:
                return FilterResult(passed=False, reason="bearish_trend_blocks_long")
        else:  # SHORT
            if current_trend == TrendDirection.BEARISH:
                return FilterResult(passed=True, reason="trend_match")
            else:
                return FilterResult(passed=False, reason="bullish_trend_blocks_short")


# ============================================================
# MtfFilter Implementation
# ============================================================
class MtfFilter(Filter):
    """Multi-timeframe filter implementation."""

    # Hardcoded MTF mapping: lower timeframe -> higher timeframe
    MTF_MAPPING = {
        "15m": "1h",
        "1h": "4h",
        "4h": "1d",
        "1d": "1w",
    }

    def __init__(self, enabled: bool, timeframe_map: Optional[Dict[str, str]] = None):
        self._enabled = enabled
        self._timeframe_map = timeframe_map or self.MTF_MAPPING

    @property
    def name(self) -> str:
        return "mtf"

    def check(self, pattern: PatternResult, context: FilterContext) -> FilterResult:
        if not self._enabled:
            return FilterResult(passed=True, reason="mtf_disabled")

        # Get higher timeframe trend from context
        # We need to know which higher timeframe to check - this is determined by the kline
        # but we don't have kline here. The caller should pass the correct higher_tf_trend.
        # For this implementation, we check all higher timeframe trends in context
        # and let the caller determine which one applies.

        # The context.higher_tf_trends contains {timeframe: TrendDirection}
        # We need to find if any of the higher timeframe trends conflict with pattern direction

        # For now, we return passed and let the caller handle MTF validation
        # This is a simplification - the real logic should be in StrategyRunner
        return FilterResult(passed=True, reason="mtf_passed")

    def check_with_timeframe(
        self,
        pattern: PatternResult,
        current_timeframe: str,
        higher_tf_trends: Dict[str, TrendDirection],
    ) -> FilterResult:
        """Check MTF validation for a specific timeframe."""
        if not self._enabled:
            return FilterResult(passed=True, reason="mtf_disabled")

        higher_tf = self.MTF_MAPPING.get(current_timeframe)
        if higher_tf is None:
            # No higher timeframe available (e.g., 1w)
            return FilterResult(passed=True, reason="no_higher_timeframe")

        higher_tf_trend = higher_tf_trends.get(higher_tf)
        if higher_tf_trend is None:
            return FilterResult(passed=False, reason="higher_tf_data_unavailable")

        # Check if signal direction matches higher timeframe trend
        if pattern.direction == Direction.LONG:
            if higher_tf_trend == TrendDirection.BULLISH:
                return FilterResult(passed=True, reason="mtf_confirmed_bullish")
            else:
                return FilterResult(passed=False, reason="mtf_rejected_bearish_higher_tf")
        else:  # SHORT
            if higher_tf_trend == TrendDirection.BEARISH:
                return FilterResult(passed=True, reason="mtf_confirmed_bearish")
            else:
                return FilterResult(passed=False, reason="mtf_rejected_bullish_higher_tf")


# ============================================================
# StrategyRunner Implementation
# ============================================================
class StrategyRunner:
    """编排策略与过滤链，返回完整的 SignalAttempt 列表（支持多策略并发）"""

    def __init__(
        self,
        strategies: List[Strategy],
        filters: List[Filter],
        mtf_filter: Optional[MtfFilter] = None,
    ):
        self._strategies = strategies
        self._filters = filters
        self._mtf_filter = mtf_filter

    def update_state(self, kline: KlineData) -> None:
        """每根 K 线到来时更新所有有状态过滤器（必须在 run_all() 之前调用）"""
        for f in self._filters:
            f.update(kline, kline.symbol, kline.timeframe)

    def run_all(
        self,
        kline: KlineData,
        higher_tf_trends: Dict[str, TrendDirection],
        current_trend: Optional[TrendDirection] = None,
        kline_history: Optional[List[KlineData]] = None,
    ) -> List[SignalAttempt]:
        """
        运行所有策略，返回 SignalAttempt 列表。

        Args:
            kline: 当前 K 线数据
            higher_tf_trends: 高周期趋势字典
            current_trend: 当前周期 EMA 趋势
            kline_history: K 线历史列表（供需要多根 K 线的策略使用，如 Engulfing）

        Returns:
            List[SignalAttempt] - 每个策略一个尝试记录
        """
        attempts = []

        for strategy in self._strategies:
            # 检测策略形态
            pattern = None

            # 检查策略是否需要 K 线历史（如 EngulfingStrategy）
            if hasattr(strategy, 'detect_with_history') and kline_history:
                pattern = strategy.detect_with_history(kline, kline_history)
            elif hasattr(strategy, 'detect'):
                # 标准 detect 方法
                pattern = strategy.detect(kline)

            if pattern is None:
                attempts.append(SignalAttempt(
                    strategy_name=strategy.name,
                    pattern=None,
                    filter_results=[],
                    final_result="NO_PATTERN",
                    kline_timestamp=kline.timestamp,
                ))
                continue

            context = FilterContext(
                higher_tf_trends=higher_tf_trends,
                current_trend=current_trend,
            )

            filter_results = []
            passed_all_filters = True

            for f in self._filters:
                result = f.check(pattern, context)
                filter_results.append((f.name, result))
                if not result.passed:
                    passed_all_filters = False
                    break

            if not passed_all_filters:
                attempts.append(SignalAttempt(
                    strategy_name=strategy.name,
                    pattern=pattern,
                    filter_results=filter_results,
                    final_result="FILTERED",
                    kline_timestamp=kline.timestamp,
                ))
                continue

            # MTF validation (special handling since it needs timeframe info)
            if self._mtf_filter:
                mtf_result = self._mtf_filter.check_with_timeframe(
                    pattern, kline.timeframe, higher_tf_trends
                )
                filter_results.append((self._mtf_filter.name, mtf_result))
                if not mtf_result.passed:
                    attempts.append(SignalAttempt(
                        strategy_name=strategy.name,
                        pattern=pattern,
                        filter_results=filter_results,
                        final_result="FILTERED",
                        kline_timestamp=kline.timestamp,
                    ))
                    continue

            attempts.append(SignalAttempt(
                strategy_name=strategy.name,
                pattern=pattern,
                filter_results=filter_results,
                final_result="SIGNAL_FIRED",
                kline_timestamp=kline.timestamp,
            ))

        return attempts

    def run(
        self,
        kline: KlineData,
        higher_tf_trends: Dict[str, TrendDirection],
        current_trend: Optional[TrendDirection] = None,
    ) -> SignalAttempt:
        """运行所有策略和过滤器，返回第一个 SIGNAL_FIRED 的 Attempt（兼容旧接口）"""
        attempts = self.run_all(kline, higher_tf_trends, current_trend)

        # 返回第一个 SIGNAL_FIRED 的 attempt
        for attempt in attempts:
            if attempt.final_result == "SIGNAL_FIRED":
                return attempt

        # 如果没有 SIGNAL_FIRED，返回第一个 attempt
        return attempts[0] if attempts else SignalAttempt(
            strategy_name="unknown",
            pattern=None,
            filter_results=[],
            final_result="NO_PATTERN",
            kline_timestamp=kline.timestamp,
        )


# ============================================================
# Dynamic Strategy Runner - For Rule Engine (Phase K)
# ============================================================
class StrategyWithFilters:
    """
    A strategy definition with its attached filter chain.

    This is the runtime representation of StrategyDefinition from config.
    """

    def __init__(self, name: str, strategy: Strategy, filters: List[FilterBase], is_global: bool = True, apply_to: List[str] = None):
        self.name = name
        self.strategy = strategy
        self.filters = filters  # Ordered filter chain
        self.is_global = is_global
        self.apply_to = apply_to or []

    def update_state(self, kline: KlineData) -> None:
        """Update state of all stateful filters."""
        for f in self.filters:
            if f.is_stateful:
                f.update_state(kline, kline.symbol, kline.timeframe)

    def check_filters(
        self,
        pattern: PatternResult,
        context: FilterContext,
    ) -> Tuple[bool, List[Tuple[str, TraceEvent]]]:
        """
        Check pattern against all filters with short-circuit evaluation.

        Returns:
            Tuple of (passed_all_filters, list of (filter_name, TraceEvent))
        """
        results = []

        for f in self.filters:
            event = f.check(pattern, context)
            results.append((f.name, event))

            # Short-circuit: stop on first failure
            if not event.passed:
                return False, results

        return True, results


class DynamicStrategyRunner:
    """
    Strategy runner for the dynamic rule engine.

    Key features:
    1. Supports multiple strategies with independent filter chains
    2. Short-circuit evaluation for CPU efficiency
    3. Precise TraceEvent tracking for debugging
    4. Clean separation of state update vs. pattern checking
    5. S4-3: Shared EMA cache across strategies for memory efficiency
    """

    def __init__(
        self,
        strategies: List[StrategyWithFilters],
        ema_cache: Optional[EMACache] = None,
    ):
        """
        Initialize with list of strategy+filter combinations.

        Args:
            strategies: List of StrategyWithFilters instances
            ema_cache: Optional shared EMA cache (S4-3)
        """
        self._strategies = strategies
        self._ema_cache = ema_cache or EMACache()

    def update_state(self, kline: KlineData) -> None:
        """
        Update state of ALL stateful filters across ALL strategies.

        Must be called for every kline BEFORE run_all().
        """
        for strat in self._strategies:
            strat.update_state(kline)

    def _get_atr_for_kline(self, kline: KlineData) -> Optional[Decimal]:
        """
        S6-2-2: Get ATR value for the current kline from any ATR filter.

        Searches through all strategies' filters for an ATR filter and
        returns its current ATR value.

        Args:
            kline: Current K-line data

        Returns:
            ATR value if available, None otherwise
        """
        for strat in self._strategies:
            for f in strat.filters:
                if isinstance(f, AtrFilterDynamic):
                    atr = f._get_atr(kline.symbol, kline.timeframe)
                    if atr is not None:
                        return atr
        return None

    def run_all(
        self,
        kline: KlineData,
        higher_tf_trends: Dict[str, TrendDirection],
        current_trend: Optional[TrendDirection] = None,
        kline_history: Optional[List[KlineData]] = None,
    ) -> List[SignalAttempt]:
        """
        Run all strategies with their filter chains.

        Flow:
        1. For each strategy, detect pattern
        2. If pattern detected, run filter chain with short-circuit
        3. Record attempt with full trace

        Args:
            kline: Current K-line
            higher_tf_trends: Higher timeframe trends for MTF
            current_trend: Current timeframe trend (optional, will auto-detect if not provided)
            kline_history: Optional history for multi-candle strategies

        Returns:
            List of SignalAttempt records
        """
        attempts = []

        # Fallback Mechanism: Filter strategies scoped to this kline
        symbol_tf_key = f"{kline.symbol}:{kline.timeframe}"
        active_strats = []

        for strat in self._strategies:
            if not strat.is_global and symbol_tf_key not in strat.apply_to:
                continue
            active_strats.append(strat)

        if not active_strats:
            # Vacuum state: no strategies apply to this kline's environment.
            # We already updated states (EMA) in update_state(), so we just return empty.
            return attempts

        # S6-2-2: Get ATR value for scoring (from ATR filter if available)
        atr_value = self._get_atr_for_kline(kline)

        for strat in active_strats:
            # Detect pattern
            pattern = None

            # S6-2-2: Pass atr_value to detect() if strategy supports it
            if hasattr(strat.strategy, 'detect_with_history') and kline_history:
                # Check if detect_with_history supports atr_value parameter
                import inspect
                sig = inspect.signature(strat.strategy.detect_with_history)
                if 'atr_value' in sig.parameters:
                    pattern = strat.strategy.detect_with_history(kline, kline_history, atr_value)
                else:
                    pattern = strat.strategy.detect_with_history(kline, kline_history)
            elif hasattr(strat.strategy, 'detect'):
                # Check if detect supports atr_value parameter
                import inspect
                sig = inspect.signature(strat.strategy.detect)
                if 'atr_value' in sig.parameters:
                    pattern = strat.strategy.detect(kline, atr_value=atr_value)
                else:
                    pattern = strat.strategy.detect(kline)

            if pattern is None:
                attempts.append(SignalAttempt(
                    strategy_name=strat.name,
                    pattern=None,
                    filter_results=[],
                    final_result="NO_PATTERN",
                    kline_timestamp=kline.timestamp,
                ))
                continue

            # Build filter context
            # Priority 1: Use current_trend parameter if provided
            # Priority 2: Auto-detect from first stateful filter (usually EMA)
            effective_current_trend = current_trend
            if effective_current_trend is None:
                for f in strat.filters:
                    if f.is_stateful:
                        effective_current_trend = f.get_current_trend(kline, kline.symbol, kline.timeframe)
                        if effective_current_trend is not None:
                            break

            context = FilterContext(
                higher_tf_trends=higher_tf_trends,
                current_trend=effective_current_trend,
                current_timeframe=kline.timeframe,
                kline=kline,
            )

            # Run filter chain with short-circuit
            passed_all, filter_events = strat.check_filters(pattern, context)

            # Convert TraceEvents to FilterResults for backward compatibility
            filter_results = [
                (name, event.to_filter_result())
                for name, event in filter_events
            ]

            if passed_all:
                attempts.append(SignalAttempt(
                    strategy_name=strat.name,
                    pattern=pattern,
                    filter_results=filter_results,
                    final_result="SIGNAL_FIRED",
                    kline_timestamp=kline.timestamp,
                ))
            else:
                attempts.append(SignalAttempt(
                    strategy_name=strat.name,
                    pattern=pattern,
                    filter_results=filter_results,
                    final_result="FILTERED",
                    kline_timestamp=kline.timestamp,
                ))

        return attempts

    def run(
        self,
        kline: KlineData,
        higher_tf_trends: Dict[str, TrendDirection],
        current_trend: Optional[TrendDirection] = None,
    ) -> SignalAttempt:
        """
        Run all strategies, return first SIGNAL_FIRED attempt.

        Legacy compatibility method.
        """
        attempts = self.run_all(kline, higher_tf_trends, current_trend)

        for attempt in attempts:
            if attempt.final_result == "SIGNAL_FIRED":
                return attempt

        return attempts[0] if attempts else SignalAttempt(
            strategy_name="unknown",
            pattern=None,
            filter_results=[],
            final_result="NO_PATTERN",
            kline_timestamp=kline.timestamp,
        )


# ============================================================
# Strategy Engine (Legacy Compatibility Layer)
# ============================================================
class StrategyEngine:
    """
    Main strategy engine for signal detection.

    Implements:
    1. Pinbar geometric pattern detection (color-agnostic)
    2. EMA60 same-timeframe trend filter
    3. MTF (Multi-Timeframe) hierarchical validation
    4. Four-combination logic gate for final signal

    Note: This is now a compatibility wrapper around the new Strategy/Filter architecture.
    """

    # Hardcoded MTF mapping: lower timeframe -> higher timeframe
    MTF_MAPPING = {
        "15m": "1h",
        "1h": "4h",
        "4h": "1d",
        "1d": "1w",
    }

    def __init__(self, config: StrategyConfig):
        """
        Initialize strategy engine.

        Args:
            config: Strategy configuration
        """
        self.config = config

        # Create new architecture components
        self._pinbar_strategy = PinbarStrategy(config.pinbar_config)
        from .strategies.engulfing_strategy import EngulfingStrategy
        self._engulfing_strategy = EngulfingStrategy()
        self._ema_filter = EmaTrendFilter(period=config.ema_period, enabled=config.trend_filter_enabled)
        self._mtf_filter = MtfFilter(enabled=config.mtf_validation_enabled)
        self._runner = StrategyRunner(
            strategies=[self._pinbar_strategy, self._engulfing_strategy],
            filters=[self._ema_filter],
            mtf_filter=self._mtf_filter,
        )

    def detect_pinbar(self, kline: KlineData) -> PinbarResult:
        """
        Detect Pinbar geometric pattern on a single K-line.

        Color-agnostic: works for both bullish and bearish candles.

        Bullish Pinbar: Long lower wick, body positioned at top
        Bearish Pinbar: Long upper wick, body positioned at bottom

        Args:
            kline: K-line data to analyze

        Returns:
            PinbarResult with detection outcome
        """
        # Use the new PinbarStrategy for detection
        pattern_result = self._pinbar_strategy.detect(kline)

        if pattern_result is None:
            # No pinbar detected - need to calculate ratios for backward compatibility
            high = kline.high
            low = kline.low
            close = kline.close
            open_price = kline.open

            candle_range = high - low
            if candle_range == Decimal(0):
                return PinbarResult(is_pinbar=False, direction=None, wick_ratio=Decimal(0), body_ratio=Decimal(0))

            body_size = abs(close - open_price)
            body_ratio = body_size / candle_range
            upper_wick = high - max(open_price, close)
            lower_wick = min(open_price, close) - low
            dominant_wick = max(upper_wick, lower_wick)
            wick_ratio = dominant_wick / candle_range

            return PinbarResult(is_pinbar=False, direction=None, wick_ratio=wick_ratio, body_ratio=body_ratio)

        # Convert PatternResult to PinbarResult for backward compatibility
        # We need to recalculate wick_ratio and body_ratio from details
        details = pattern_result.details
        wick_ratio = Decimal(str(details.get("wick_ratio", 0)))
        body_ratio = Decimal(str(details.get("body_ratio", 0)))

        return PinbarResult(
            is_pinbar=True,
            direction=pattern_result.direction,
            wick_ratio=wick_ratio,
            body_ratio=body_ratio,
        )

    def get_ema_trend(
        self, kline: KlineData, symbol: str, timeframe: str
    ) -> Optional[TrendDirection]:
        """
        Update EMA and determine trend direction.

        Price above EMA60 -> BULLISH (only LONG signals allowed)
        Price below EMA60 -> BEARISH (only SHORT signals allowed)

        Args:
            kline: Current K-line data
            symbol: Trading pair symbol
            timeframe: Timeframe string

        Returns:
            TrendDirection or None if EMA not ready
        """
        # Update the new EMA filter
        self._ema_filter.update(kline, symbol, timeframe)

        # Use new filter for trend calculation
        return self._ema_filter.get_trend(kline, symbol, timeframe)

    def check_trend_filter(
        self,
        pinbar_direction: Direction,
        ema_trend: TrendDirection,
    ) -> bool:
        """
        Check if pinbar direction matches EMA trend filter.

        When trend_filter_enabled=True:
        - Price above EMA (BULLISH) -> only LONG signals
        - Price below EMA (BEARISH) -> only SHORT signals

        Args:
            pinbar_direction: Detected Pinbar direction
            ema_trend: Current EMA trend direction

        Returns:
            True if signal direction matches trend, False otherwise
        """
        if not self.config.trend_filter_enabled:
            return True  # Filter disabled, always pass

        if pinbar_direction == Direction.LONG:
            return ema_trend == TrendDirection.BULLISH
        else:  # SHORT
            return ema_trend == TrendDirection.BEARISH

    def get_higher_timeframe(self, timeframe: str) -> Optional[str]:
        """Get the higher timeframe for MTF validation."""
        return self.MTF_MAPPING.get(timeframe)

    def validate_mtf(
        self,
        timeframe: str,
        pinbar_direction: Direction,
        higher_tf_trend: Optional[TrendDirection],
    ) -> MtfStatus:
        """
        Validate signal against higher timeframe trend.

        Validation chain: 15m -> 1h, 1h -> 4h, 4h -> 1d, 1d -> 1w

        Args:
            timeframe: Current signal timeframe
            pinbar_direction: Detected Pinbar direction
            higher_tf_trend: Pre-calculated higher timeframe EMA trend direction

        Returns:
            MtfStatus: CONFIRMED, REJECTED, UNAVAILABLE, or DISABLED
        """
        if not self.config.mtf_validation_enabled:
            return MtfStatus.DISABLED

        higher_tf = self.get_higher_timeframe(timeframe)
        if higher_tf is None:
            # No higher timeframe available (e.g., 1w)
            return MtfStatus.CONFIRMED

        if higher_tf_trend is None:
            return MtfStatus.UNAVAILABLE

        # Check if signal direction matches higher timeframe trend
        if pinbar_direction == Direction.LONG:
            return MtfStatus.CONFIRMED if higher_tf_trend == TrendDirection.BULLISH else MtfStatus.REJECTED
        else:  # SHORT
            return MtfStatus.CONFIRMED if higher_tf_trend == TrendDirection.BEARISH else MtfStatus.REJECTED

    def process_signal(
        self,
        kline: KlineData,
        higher_tf_trends: Optional[Dict[str, TrendDirection]] = None,
    ) -> Optional[Direction]:
        """
        Process a K-line and return signal direction if valid.

        Implements the four-combination logic gate:
        signal_valid = (
            pinbar_detected
            and (not trend_filter_enabled or trend_direction_match)
            and (not mtf_validation_enabled or mtf_status == CONFIRMED)
        )

        Args:
            kline: Current K-line data
            higher_tf_trends: Optional dict of {timeframe: TrendDirection} for MTF validation

        Returns:
            Direction if signal is valid, None otherwise
        """
        # Use the new StrategyRunner
        attempt = self.run_with_attempt(kline, higher_tf_trends or {})
        # Only return direction if signal actually fired
        if attempt.final_result == "SIGNAL_FIRED":
            return attempt.direction
        return None

    def run_with_attempt(
        self,
        kline: KlineData,
        higher_tf_trends: Dict[str, TrendDirection],
    ) -> SignalAttempt:
        """旧接口：返回单个 SignalAttempt（兼容 legacy 代码）"""
        # Update EMA state first
        self._ema_filter.update(kline, kline.symbol, kline.timeframe)

        # Get current trend
        current_trend = self._ema_filter.get_trend(kline, kline.symbol, kline.timeframe)

        # Run the strategy runner
        return self._runner.run(kline, higher_tf_trends, current_trend)

    def run_all_with_attempt(
        self,
        kline: KlineData,
        higher_tf_trends: Dict[str, TrendDirection],
        kline_history: Optional[List[KlineData]] = None,
    ) -> List[SignalAttempt]:
        """新接口：返回完整的 SignalAttempt 列表，供 signal_pipeline 使用"""
        # Update EMA state first
        self._ema_filter.update(kline, kline.symbol, kline.timeframe)

        # Get current trend
        current_trend = self._ema_filter.get_trend(kline, kline.symbol, kline.timeframe)

        # Run the strategy runner with all strategies
        return self._runner.run_all(kline, higher_tf_trends, current_trend, kline_history)


# ============================================================
# Factory Function - Create DynamicStrategyRunner from Config
# ============================================================
def create_dynamic_runner(
    strategy_definitions: List[Any],
    core_config: Optional[Any] = None,
) -> DynamicStrategyRunner:
    """
    Create a DynamicStrategyRunner from strategy definitions.

    优先使用 logic_tree 字段（新格式），如果不存在则回退到旧字段。

    Args:
        strategy_definitions: List of StrategyDefinition from config
        core_config: Optional CoreConfig for default parameters

    Returns:
        DynamicStrategyRunner ready for execution
    """
    strategies_with_filters = []

    for strat_def in strategy_definitions:
        # 优先使用 logic_tree 字段（新格式）
        logic_tree = getattr(strat_def, "logic_tree", None)

        if logic_tree is not None:
            # 新格式：从 logic_tree 提取 triggers 和 filters
            triggers = strat_def.get_triggers_from_logic_tree()
            filters_config = strat_def.get_filters_from_logic_tree()
        else:
            # 旧格式：使用 triggers/filters 字段
            triggers = getattr(strat_def, "triggers", [])
            if not triggers:
                # Fallback to legacy trigger
                legacy_trigger = getattr(strat_def, "trigger", None)
                if legacy_trigger:
                    triggers = [legacy_trigger]
            filters_config = getattr(strat_def, "filters", [])

        if not triggers:
            continue

        # Extract environment scope
        is_global = getattr(strat_def, "is_global", True)
        apply_to = getattr(strat_def, "apply_to", [])

        # Create filter chain from config
        filters = FilterFactory.create_chain(filters_config)

        # Handle OR logic by expanding to multiple independent runners
        # (AND logic for morphological patterns is rare, treated as OR for now)
        for idx, trigger in enumerate(triggers):
            if not getattr(trigger, "enabled", True):
                continue

            strategy = None
            if trigger.type == "pinbar":
                from src.domain.strategy_engine import PinbarStrategy, PinbarConfig
                from decimal import Decimal
                pinbar_cfg = core_config.pinbar_defaults if core_config else None
                config = PinbarConfig(
                    min_wick_ratio=Decimal(str(trigger.params.get("min_wick_ratio", getattr(pinbar_cfg, "min_wick_ratio", "0.6")))),
                    max_body_ratio=Decimal(str(trigger.params.get("max_body_ratio", getattr(pinbar_cfg, "max_body_ratio", "0.3")))),
                    body_position_tolerance=Decimal(str(trigger.params.get("body_position_tolerance", getattr(pinbar_cfg, "body_position_tolerance", "0.1")))),
                )
                strategy = PinbarStrategy(config)
            elif trigger.type == "engulfing":
                from src.domain.strategies.engulfing_strategy import EngulfingStrategy
                strategy = EngulfingStrategy()
            else:
                continue

            # Ensure unique names if expanded
            strat_name = strat_def.name if len(triggers) == 1 else f"{strat_def.name}_{trigger.type}"

            wrapped = StrategyWithFilters(
                name=strat_name,
                strategy=strategy,
                filters=filters,
                is_global=is_global,
                apply_to=apply_to
            )
            strategies_with_filters.append(wrapped)

    # S4-3: Create shared EMA cache for all strategies
    # This allows multiple strategies to share the same EMA instances,
    # reducing memory usage and computation overhead
    return DynamicStrategyRunner(strategies_with_filters)

