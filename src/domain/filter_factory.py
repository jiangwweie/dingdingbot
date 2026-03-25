"""
Filter Factory - Creates filter instances from configuration.

Design Principles:
1. Clear separation between stateful and stateless filters
2. update_state(kline) is called for every kline (state mutation)
3. check(pattern, context) is only called when pattern is detected (pure logic)
4. TraceEvent provides precise failure tracking for debugging
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, Dict, List, Any

from .models import KlineData, Direction, TrendDirection, PatternResult, FilterResult
from .indicators import EMACalculator


# ============================================================
# Trace Event - Precise Failure Tracking
# ============================================================
@dataclass
class TraceEvent:
    """
    High-precision trace event for filter execution.

    Unlike simple FilterResult, this captures expected vs actual values
    for debugging and audit purposes.
    """
    filter_name: str
    passed: bool
    reason: str
    expected: Optional[str] = None      # e.g., "bullish"
    actual: Optional[str] = None        # e.g., "bearish"
    context_data: Dict[str, Any] = field(default_factory=dict)

    def to_filter_result(self) -> FilterResult:
        """Convert to legacy FilterResult for backward compatibility."""
        return FilterResult(passed=self.passed, reason=self.reason)


# ============================================================
# Filter Base Class - Unified Interface
# ============================================================
class FilterBase(ABC):
    """
    Base class for all filters in the dynamic rule engine.

    Lifecycle:
    1. __init__(params): Filter is instantiated from config
    2. update_state(kline): Called for EVERY kline to update internal state
    3. check(pattern, context): Called ONLY when pattern is detected
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique filter identifier (e.g., 'ema_trend', 'mtf')"""
        pass

    @property
    @abstractmethod
    def is_stateful(self) -> bool:
        """Whether this filter maintains internal state"""
        pass

    @abstractmethod
    def update_state(self, kline: KlineData, symbol: str, timeframe: str) -> None:
        """
        Update internal state with new kline data.

        Called for EVERY kline, regardless of whether a pattern was detected.
        Stateless filters can implement this as a no-op.

        Args:
            kline: Current closed K-line
            symbol: Trading symbol
            timeframe: Timeframe
        """
        pass

    @abstractmethod
    def check(self, pattern: PatternResult, context: 'FilterContext') -> TraceEvent:
        """
        Check if pattern passes this filter's criteria.

        Called ONLY when a pattern is detected.

        Args:
            pattern: Detected pattern result
            context: Filter context (higher timeframe trends, etc.)

        Returns:
            TraceEvent with pass/fail and detailed context
        """
        pass

    @abstractmethod
    def get_current_trend(self, kline: KlineData, symbol: str, timeframe: str) -> Optional[TrendDirection]:
        """
        Get current trend value from this filter's state.

        Returns None if data not ready or filter is stateless.
        """
        pass


# ============================================================
# Filter Context - Passed to check()
# ============================================================
@dataclass
class FilterContext:
    """Context passed to filter check() method."""
    higher_tf_trends: Dict[str, TrendDirection]  # {timeframe: TrendDirection}
    current_trend: Optional[TrendDirection] = None  # Current timeframe EMA trend
    current_timeframe: str = ""  # Current timeframe being processed
    kline: Optional[KlineData] = None  # Current K-line (for advanced filters)


# ============================================================
# EMA Trend Filter - Stateful
# ============================================================
class EmaTrendFilterDynamic(FilterBase):
    """
    EMA trend filter implementation for dynamic rule engine.

    Stateful: Maintains EMA calculators per symbol/timeframe.
    """

    def __init__(self, period: int = 60, enabled: bool = True):
        self._period = period
        self._enabled = enabled
        self._ema_calculators: Dict[str, EMACalculator] = {}  # key: "symbol:timeframe"

    @property
    def name(self) -> str:
        return "ema_trend"

    @property
    def is_stateful(self) -> bool:
        return True

    def update_state(self, kline: KlineData, symbol: str, timeframe: str) -> None:
        """Update EMA state for every kline."""
        key = f"{symbol}:{timeframe}"
        if key not in self._ema_calculators:
            self._ema_calculators[key] = EMACalculator(self._period)
        self._ema_calculators[key].update(kline.close)

    def get_current_trend(self, kline: KlineData, symbol: str, timeframe: str) -> Optional[TrendDirection]:
        """Get current EMA trend direction."""
        key = f"{symbol}:{timeframe}"
        if key not in self._ema_calculators:
            return None
        ema = self._ema_calculators[key].value
        if ema is None:
            return None
        return TrendDirection.BULLISH if kline.close > ema else TrendDirection.BEARISH

    def check(self, pattern: PatternResult, context: FilterContext) -> TraceEvent:
        if not self._enabled:
            return TraceEvent(
                filter_name=self.name,
                passed=True,
                reason="filter_disabled"
            )

        current_trend = context.current_trend
        if current_trend is None:
            return TraceEvent(
                filter_name=self.name,
                passed=False,
                reason="ema_data_not_ready",
                expected="valid_ema_trend",
                actual="no_data"
            )

        # Check if pattern direction matches trend
        if pattern.direction == Direction.LONG:
            if current_trend == TrendDirection.BULLISH:
                return TraceEvent(
                    filter_name=self.name,
                    passed=True,
                    reason="trend_match",
                    expected="bullish",
                    actual="bullish"
                )
            else:
                return TraceEvent(
                    filter_name=self.name,
                    passed=False,
                    reason="bearish_trend_blocks_long",
                    expected="bullish",
                    actual="bearish"
                )
        else:  # SHORT
            if current_trend == TrendDirection.BEARISH:
                return TraceEvent(
                    filter_name=self.name,
                    passed=True,
                    reason="trend_match",
                    expected="bearish",
                    actual="bearish"
                )
            else:
                return TraceEvent(
                    filter_name=self.name,
                    passed=False,
                    reason="bullish_trend_blocks_short",
                    expected="bearish",
                    actual="bullish"
                )


# ============================================================
# MTF Filter - Stateless (uses external data)
# ============================================================
class MtfFilterDynamic(FilterBase):
    """
    Multi-timeframe filter implementation for dynamic rule engine.

    Stateless: Relies on externally provided higher timeframe trends.
    """

    # Hardcoded MTF mapping: lower timeframe -> higher timeframe
    MTF_MAPPING = {
        "15m": "1h",
        "1h": "4h",
        "4h": "1d",
        "1d": "1w",
    }

    def __init__(self, enabled: bool = True, timeframe_map: Optional[Dict[str, str]] = None):
        self._enabled = enabled
        self._timeframe_map = timeframe_map or self.MTF_MAPPING

    @property
    def name(self) -> str:
        return "mtf"

    @property
    def is_stateful(self) -> bool:
        return False

    def update_state(self, kline: KlineData, symbol: str, timeframe: str) -> None:
        """No-op: MTF filter is stateless."""
        pass

    def get_current_trend(self, kline: KlineData, symbol: str, timeframe: str) -> Optional[TrendDirection]:
        """No-op: MTF filter doesn't track trend itself."""
        return None

    def check(self, pattern: PatternResult, context: FilterContext) -> TraceEvent:
        if not self._enabled:
            return TraceEvent(
                filter_name=self.name,
                passed=True,
                reason="filter_disabled"
            )

        current_tf = context.current_timeframe
        higher_tf = self._timeframe_map.get(current_tf)

        if higher_tf is None:
            # No higher timeframe available (e.g., 1w)
            return TraceEvent(
                filter_name=self.name,
                passed=True,
                reason="no_higher_timeframe",
                context_data={"current_timeframe": current_tf}
            )

        higher_tf_trend = context.higher_tf_trends.get(higher_tf)
        if higher_tf_trend is None:
            return TraceEvent(
                filter_name=self.name,
                passed=False,
                reason="higher_tf_data_unavailable",
                expected=f"trend_data_for_{higher_tf}",
                actual="no_data",
                context_data={"higher_timeframe": higher_tf}
            )

        # Check if signal direction matches higher timeframe trend
        if pattern.direction == Direction.LONG:
            if higher_tf_trend == TrendDirection.BULLISH:
                return TraceEvent(
                    filter_name=self.name,
                    passed=True,
                    reason="mtf_confirmed_bullish",
                    expected="bullish",
                    actual="bullish",
                    context_data={"higher_timeframe": higher_tf, "higher_trend": higher_tf_trend.value}
                )
            else:
                return TraceEvent(
                    filter_name=self.name,
                    passed=False,
                    reason="mtf_rejected_bearish_higher_tf",
                    expected="bullish",
                    actual="bearish",
                    context_data={"higher_timeframe": higher_tf, "higher_trend": higher_tf_trend.value}
                )
        else:  # SHORT
            if higher_tf_trend == TrendDirection.BEARISH:
                return TraceEvent(
                    filter_name=self.name,
                    passed=True,
                    reason="mtf_confirmed_bearish",
                    expected="bearish",
                    actual="bearish",
                    context_data={"higher_timeframe": higher_tf, "higher_trend": higher_tf_trend.value}
                )
            else:
                return TraceEvent(
                    filter_name=self.name,
                    passed=False,
                    reason="mtf_rejected_bullish_higher_tf",
                    expected="bearish",
                    actual="bullish",
                    context_data={"higher_timeframe": higher_tf, "higher_trend": higher_tf_trend.value}
                )


# ============================================================
# ATR Volatility Filter - Stateful (for future expansion)
# ============================================================
class AtrFilterDynamic(FilterBase):
    """
    ATR volatility filter for filtering out low-volatility noise.

    Stateful: Maintains ATR calculation per symbol/timeframe.
    """

    def __init__(self, period: int = 14, min_atr_ratio: Decimal = Decimal("0.001"), enabled: bool = False):
        self._period = period
        self._min_atr_ratio = min_atr_ratio
        self._enabled = enabled
        self._atr_values: Dict[str, List[Decimal]] = {}  # key: "symbol:timeframe"

    @property
    def name(self) -> str:
        return "atr_volatility"

    @property
    def is_stateful(self) -> bool:
        return True

    def update_state(self, kline: KlineData, symbol: str, timeframe: str) -> None:
        """Update ATR state for every kline."""
        key = f"{symbol}:{timeframe}"
        if key not in self._atr_values:
            self._atr_values[key] = []

        # Calculate true range
        if len(self._atr_values[key]) > 0:
            prev_close = self._atr_values[key][-1] if hasattr(self._atr_values[key][-1], '__float__') else kline.open
        else:
            prev_close = kline.open

        true_range = max(
            kline.high - kline.low,
            abs(kline.high - prev_close),
            abs(kline.low - prev_close)
        )

        self._atr_values[key].append(true_range)

        # Keep only recent values for efficiency
        if len(self._atr_values[key]) > self._period * 2:
            self._atr_values[key] = self._atr_values[key][-self._period:]

    def get_current_trend(self, kline: KlineData, symbol: str, timeframe: str) -> Optional[TrendDirection]:
        """No-op: ATR filter doesn't track trend."""
        return None

    def _get_atr(self, symbol: str, timeframe: str) -> Optional[Decimal]:
        """Get current ATR value."""
        key = f"{symbol}:{timeframe}"
        values = self._atr_values.get(key, [])
        if len(values) < self._period:
            return None

        # Simple average for ATR
        return sum(values[-self._period:]) / len(values[-self._period:])

    def check(self, pattern: PatternResult, context: FilterContext) -> TraceEvent:
        if not self._enabled:
            return TraceEvent(
                filter_name=self.name,
                passed=True,
                reason="filter_disabled"
            )

        # ATR filter not yet fully implemented - placeholder
        # In full implementation, would check if ATR ratio meets minimum threshold
        return TraceEvent(
            filter_name=self.name,
            passed=True,
            reason="atr_threshold_met"
        )


# ============================================================
# Placeholder Filters for newly requested React integrations
# ============================================================
class PlaceholderFilter(FilterBase):
    """Generic placeholder for unimplemented UI filters."""
    def __init__(self, name: str, enabled: bool = True, **kwargs):
        self._name_val = name
        self._enabled = enabled
    
    @property
    def name(self) -> str:
        return self._name_val
        
    @property
    def is_stateful(self) -> bool:
        return False
        
    def update_state(self, kline, symbol, timeframe) -> None:
        pass
        
    def get_current_trend(self, kline, symbol, timeframe):
        return None
        
    def check(self, pattern, context) -> TraceEvent:
        return TraceEvent(filter_name=self.name, passed=True, reason="placeholder_auto_pass")

class FilterFactory:
    """
    Factory for creating filter instances from configuration.

    Usage:
        filter = FilterFactory.create(filter_config)
    """

    # Registry of filter types
    _registry = {
        "ema": EmaTrendFilterDynamic,
        "ema_trend": EmaTrendFilterDynamic,
        "mtf": MtfFilterDynamic,
        "atr": AtrFilterDynamic,
        "volume_surge": lambda **kw: PlaceholderFilter("volume_surge", **kw),
        "volatility_filter": lambda **kw: PlaceholderFilter("volatility_filter", **kw),
        "time_filter": lambda **kw: PlaceholderFilter("time_filter", **kw),
        "price_action": lambda **kw: PlaceholderFilter("price_action", **kw),
    }

    @classmethod
    def create(cls, filter_config: Any) -> FilterBase:
        """
        Create a filter instance from config.

        Args:
            filter_config: FilterConfig Pydantic model or dict with 'type' key

        Returns:
            FilterBase instance

        Raises:
            ValueError: If filter type is unknown
        """
        # Handle unified Pydantic model (FilterConfig)
        if hasattr(filter_config, 'type'):
            filter_type = filter_config.type
            enabled = filter_config.enabled
            params = filter_config.params if hasattr(filter_config, 'params') else filter_config.model_dump()
        else:
            # Handle dict
            filter_type = filter_config.get('type')
            enabled = filter_config.get('enabled', True)
            params = filter_config.get('params', filter_config)

        if filter_type not in cls._registry:
            raise ValueError(f"Unknown filter type: {filter_type}")

        filter_class = cls._registry[filter_type]

        # Extract relevant params based on filter class
        if filter_type in ("ema", "ema_trend"):
            return filter_class(
                period=params.get('period', 60),
                enabled=enabled
            )
        elif filter_type == "mtf":
            return filter_class(
                enabled=enabled,
                timeframe_map=params.get('timeframe_map')
            )
        elif filter_type == "atr":
            return filter_class(
                period=params.get('period', 14),
                min_atr_ratio=params.get('min_atr_ratio', Decimal("0.001")),
                enabled=enabled
            )
        elif filter_type in ["volume_surge", "volatility_filter", "time_filter", "price_action"]:
            return filter_class(enabled=enabled, **params)

        raise ValueError(f"Failed to create filter of type: {filter_type}")

    @classmethod
    def create_chain(cls, filter_configs: List[Any]) -> List[FilterBase]:
        """
        Create a chain of filters from config list.

        Args:
            filter_configs: List of FilterConfig models or dicts

        Returns:
            List of FilterBase instances
        """
        return [cls.create(config) for config in filter_configs]

    @classmethod
    def register_filter(cls, name: str, filter_class: type):
        """
        Register a custom filter type.

        Args:
            name: Filter type name (for discriminator)
            filter_class: Filter class that extends FilterBase
        """
        if not issubclass(filter_class, FilterBase):
            raise TypeError("filter_class must be a subclass of FilterBase")
        cls._registry[name] = filter_class
