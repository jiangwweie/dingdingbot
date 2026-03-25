"""
Global Pydantic models - shared contract between Dev A (Infrastructure) and Dev B (Domain).
DO NOT modify without architect approval.
"""
from pydantic import BaseModel, Field
from decimal import Decimal
from typing import Optional, List, Dict, Any, Union, Annotated, Literal
from enum import Enum


# ============================================================
# Enum Types
# ============================================================
class Direction(str, Enum):
    """Signal direction"""
    LONG = "long"
    SHORT = "short"


class MtfStatus(str, Enum):
    """MTF validation status"""
    CONFIRMED = "confirmed"     # Higher timeframe trend matches signal direction
    REJECTED = "rejected"       # Higher timeframe trend conflicts with signal
    DISABLED = "disabled"       # MTF feature is disabled
    UNAVAILABLE = "unavailable" # Higher timeframe data not ready yet


class TrendDirection(str, Enum):
    """EMA trend direction relative to price"""
    BULLISH = "bullish"         # Price is above EMA
    BEARISH = "bearish"         # Price is below EMA


# ============================================================
# A -> B : Input Data Models (Infrastructure provides these)
# ============================================================
class KlineData(BaseModel):
    """Single closed K-line (candlestick) data"""
    symbol: str                 # e.g., "BTC/USDT:USDT"
    timeframe: str              # "15m", "1h", "4h", "1d", "1w"
    timestamp: int              # Close timestamp in milliseconds
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal             # Volume in base asset
    is_closed: bool = True


class PositionInfo(BaseModel):
    """Single futures position information"""
    symbol: str
    side: str                   # "long" | "short"
    size: Decimal               # Position size
    entry_price: Decimal
    unrealized_pnl: Decimal
    leverage: int


class AccountSnapshot(BaseModel):
    """Futures account snapshot"""
    total_balance: Decimal       # Total account equity
    available_balance: Decimal   # Available balance for new positions
    unrealized_pnl: Decimal      # Total unrealized PnL
    positions: List[PositionInfo] = Field(default_factory=list)
    timestamp: int               # Snapshot timestamp in milliseconds


# ============================================================
# B -> A : Strategy Output Models (Domain layer provides these)
# ============================================================
class SignalResult(BaseModel):
    """Complete signal output from strategy engine"""
    symbol: str
    timeframe: str
    direction: Direction
    entry_price: Decimal         # Suggested entry price (current close)
    suggested_stop_loss: Decimal # Suggested stop-loss level
    suggested_position_size: Decimal  # Position size after risk calculation
    current_leverage: int        # Actual leverage used
    tags: List[Dict[str, str]] = Field(default_factory=list)  # Dynamic filter tags e.g., [{"name": "EMA", "value": "Bullish"}, {"name": "MTF", "value": "Confirmed"}]
    risk_reward_info: str        # Risk summary (e.g., "Risk 1% = 200 USDT")
    status: str = "PENDING"      # Signal status: PENDING (monitoring), WON (profit), LOST (loss)
    pnl_ratio: float = 0.0       # Profit/Loss ratio (positive for win e.g. 1.5, negative for loss e.g. -1.0)
    kline_timestamp: int = 0     # K-line close timestamp in milliseconds (default 0 for legacy compatibility)
    strategy_name: str = "unknown"  # Strategy name that generated this signal (e.g., "pinbar", "engulfing")
    score: float = 0.0           # Pattern quality score (0.0 ~ 1.0). **NOTE**: This is for UI display and sorting only, NOT for financial calculations. Financial calculations use Decimal exclusively.

    # Legacy fields for backward compatibility (deprecated, will be removed in future)
    ema_trend: Optional[TrendDirection] = None  # Deprecated: use tags instead
    mtf_status: Optional[MtfStatus] = None      # Deprecated: use tags instead


# ============================================================
# Domain Layer Internal Models (for Strategy/Filter abstraction)
# ============================================================
from dataclasses import dataclass as dc_dataclass, field as dc_field


@dc_dataclass
class PatternResult:
    """策略检测到的形态结果"""
    strategy_name: str             # 策略名称，如 "pinbar"
    direction: Direction           # 信号方向
    score: float                   # 0~1，形态质量评分
    details: dict                  # 策略特定的中间计算值（用于诊断）


@dc_dataclass
class FilterResult:
    """单个过滤器的判断结果"""
    passed: bool
    reason: str                    # 通过或拒绝的原因，如 "trend_match" 或 "bearish_trend_blocks_long"


@dc_dataclass
class SignalAttempt:
    """一次完整信号尝试的记录，无论是否最终触发信号"""
    strategy_name: str
    pattern: Optional['PatternResult']              # None 表示未检测到形态
    filter_results: list                             # List[Tuple[str, FilterResult]]
    final_result: str                                # "SIGNAL_FIRED" / "NO_PATTERN" / "FILTERED"
    kline_timestamp: Optional[int] = None            # K-line close timestamp in milliseconds

    @property
    def direction(self) -> Optional[Direction]:
        return self.pattern.direction if self.pattern else None


# ============================================================
# API Request/Response Models (for REST interface)
# ============================================================
class SignalQuery(BaseModel):
    """Query parameters for signals endpoint"""
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    symbol: Optional[str] = None
    direction: Optional[str] = None
    strategy_name: Optional[str] = None
    status: Optional[str] = None  # PENDING, WON, LOST
    start_time: Optional[str] = None  # ISO 8601 or timestamp
    end_time: Optional[str] = None


class SignalDeleteRequest(BaseModel):
    """Delete request for signals endpoint"""
    ids: Optional[List[int]] = None
    delete_all: Optional[bool] = False
    symbol: Optional[str] = None
    direction: Optional[str] = None
    strategy_name: Optional[str] = None
    status: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None


class SignalDeleteResponse(BaseModel):
    """Delete response for signals endpoint"""
    message: str
    deleted_count: int


class AttemptQuery(BaseModel):
    """Query parameters for signal_attempts endpoint"""
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    strategy_name: Optional[str] = None
    final_result: Optional[str] = None  # SIGNAL_FIRED, NO_PATTERN, FILTERED
    filter_stage: Optional[str] = None  # ema_trend, mtf, etc.
    start_time: Optional[str] = None
    end_time: Optional[str] = None


class AttemptDeleteRequest(BaseModel):
    """Delete request for signal_attempts endpoint"""
    ids: Optional[List[int]] = None
    delete_all: Optional[bool] = False
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    strategy_name: Optional[str] = None
    final_result: Optional[str] = None
    filter_stage: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None


class AttemptDeleteResponse(BaseModel):
    """Delete response for signal_attempts endpoint"""
    message: str
    deleted_count: int


# ============================================================
# Backtest Models (for Backtester layer)
# ============================================================
class BacktestRequest(BaseModel):
    """Request model for backtest endpoint"""
    symbol: str = Field(..., description="Trading symbol (e.g., 'BTC/USDT:USDT')")
    timeframe: str = Field(..., description="Timeframe (e.g., '15m', '1h', '4h')")
    start_time: Union[str, int, None] = Field(default=None, description="Start time (ISO 8601 or timestamp)")
    end_time: Union[str, int, None] = Field(default=None, description="End time (ISO 8601 or timestamp)")
    limit: int = Field(default=100, ge=10, le=1000, description="Number of candles to fetch")

    # Legacy parameters (for backward compatibility)
    min_wick_ratio: Optional[Decimal] = Field(default=None, ge=0, le=1, description="Override pinbar min_wick_ratio")
    max_body_ratio: Optional[Decimal] = Field(default=None, ge=0, le=1, description="Override pinbar max_body_ratio")
    body_position_tolerance: Optional[Decimal] = Field(default=None, ge=0, le=0.5, description="Override pinbar body_position_tolerance")
    trend_filter_enabled: Optional[bool] = Field(default=None, description="Override EMA trend filter")
    mtf_validation_enabled: Optional[bool] = Field(default=None, description="Override MTF validation")

    # New dynamic rule engine parameters (Phase K)
    # Using string reference to avoid forward declaration issue
    strategies: Optional[List[Any]] = Field(
        default=None,
        description="Dynamic strategy definitions with filter chains (overrides legacy params)"
    )
    risk_overrides: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Risk config overrides for this backtest"
    )


# ============================================================
# Dynamic Rule Engine Models (Phase K)
# ============================================================
from typing import Union, Literal, Dict, Any, Optional
from pydantic import model_validator


class FilterConfig(BaseModel):
    """Unified dynamic Filter Configuration model."""
    id: str = Field(default_factory=lambda: "")
    type: Literal["ema", "ema_trend", "mtf", "atr", "volume_surge", "volatility_filter", "time_filter", "price_action"] = Field(..., description="Filter type (e.g., 'ema_trend', 'mtf')")
    enabled: bool = Field(default=True, description="Whether this filter is active")
    params: Dict[str, Any] = Field(default_factory=dict, description="Filter parameters")

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy(cls, data: Any) -> Any:
        """Migrate legacy flat parameters into nested params dictionary."""
        if isinstance(data, dict):
            if "params" not in data:
                params = {}
                for k in list(data.keys()):
                    if k not in ("id", "type", "enabled"):
                        params[k] = data.pop(k)
                data["params"] = params
        return data

class TriggerConfig(BaseModel):
    """Trigger pattern configuration"""
    id: str = Field(default_factory=lambda: "")
    type: Literal["pinbar", "engulfing", "doji", "hammer"] = Field(..., description="Trigger pattern type")
    enabled: bool = Field(default=True, description="Whether this trigger is active")
    params: Dict[str, Any] = Field(default_factory=dict, description="Pattern-specific parameters")


class StrategyDefinition(BaseModel):
    """
    Dynamic strategy definition with attached filters.
    """
    id: str = Field(default_factory=lambda: "")
    name: str = Field(..., description="Strategy name (e.g., 'pinbar', 'engulfing')")
    
    # Core pattern triggers (supports multiple with AND/OR logic)
    triggers: List[TriggerConfig] = Field(default_factory=list, description="Core pattern triggers")
    trigger_logic: Literal["AND", "OR"] = Field(default="OR", description="How to combine triggers")
    
    # Legacy trigger (kept for backward compatibility)
    trigger: Optional[TriggerConfig] = Field(default=None, description="The core pattern trigger (legacy)")
    
    filters: List[FilterConfig] = Field(default_factory=list, description="Attached filter chain")
    filter_logic: Literal["AND", "OR"] = Field(default="AND", description="How to combine filter results")
    
    # Environment scope (Fallback Mechanism)
    is_global: bool = Field(default=True, description="Applies to all symbols and timeframes")
    apply_to: List[str] = Field(default_factory=list, description="Specific symbol:timeframe scopes e.g., 'BTC/USDT:USDT:15m'")

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Migrate old single trigger to triggers list
            if "trigger" in data and ("triggers" not in data or not data["triggers"]):
                data["triggers"] = [data["trigger"]]
        return data


class SignalStats(BaseModel):
    """Signal statistics from backtest"""
    total_attempts: int = Field(default=0, description="Total signal attempts")
    signals_fired: int = Field(default=0, description="Number of signals fired")
    no_pattern: int = Field(default=0, description="Number of candles with no pattern")
    filtered_out: int = Field(default=0, description="Number of signals filtered out")

    # Filter stage breakdown
    filtered_by_filters: Dict[str, int] = Field(default_factory=dict, description="Rejections by filter type")

    # Direction breakdown
    long_signals: int = Field(default=0, description="Number of LONG signals")
    short_signals: int = Field(default=0, description="Number of SHORT signals")

    # Strategy breakdown
    by_strategy: Dict[str, int] = Field(default_factory=dict, description="Signals per strategy")


# Legacy RejectReasonStats removed; using Dict directly


class BacktestReport(BaseModel):
    """Complete backtest report"""
    symbol: str
    timeframe: str
    candles_analyzed: int
    start_timestamp: int
    end_timestamp: int

    # Signal statistics
    signal_stats: SignalStats

    # Rejection reason distribution
    reject_reasons: Dict[str, int] = Field(default_factory=dict, description="Distribution of rejection reasons")

    # Simulated win rate (based on stop-loss hit simulation)
    simulated_win_rate: float = Field(default=0.0, description="Simulated win rate (0.0-1.0)")
    simulated_avg_gain: float = Field(default=0.0, description="Average gain on winning trades")
    simulated_avg_loss: float = Field(default=0.0, description="Average loss on losing trades")

    # Raw attempts (optional, can be excluded for large reports)
    attempts: List[Dict[str, Any]] = Field(default_factory=list, description="Detailed attempt records")
