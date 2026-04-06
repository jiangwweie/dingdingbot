"""
Global Pydantic models - shared contract between Dev A (Infrastructure) and Dev B (Domain).
DO NOT modify without architect approval.
"""
import time
from pydantic import BaseModel, Field, field_validator, ConfigDict
from decimal import Decimal
from typing import Optional, List, Dict, Any, Union, Annotated, Literal
from enum import Enum
from datetime import datetime, timezone


# ============================================================
# Enum Types
# ============================================================
class Direction(str, Enum):
    """Signal direction (v3.0 Phase 1: unified uppercase)"""
    LONG = "LONG"
    SHORT = "SHORT"


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
# P0-003: Reconciliation Enum Types
# ============================================================
class ReconciliationType(str, Enum):
    """对账类型"""
    STARTUP = "startup"     # 系统启动时对账
    DAILY = "daily"         # 定期对账
    MANUAL = "manual"       # 手动对账


class DiscrepancyType(str, Enum):
    """差异类型"""
    GHOST_ORDER = "ghost_order"           # 幽灵订单（DB 有但交易所无）
    ORPHAN_ORDER = "orphan_order"         # 孤儿订单（交易所有但 DB 无）
    POSITION_MISMATCH = "position_mismatch"  # 仓位不匹配


class ReconciliationAction(str, Enum):
    """对账处理动作"""
    CANCEL_ORDER = "cancel_order"         # 取消订单
    CREATE_SIGNAL = "create_signal"       # 创建信号
    SYNC_POSITION = "sync_position"       # 同步仓位
    IGNORE = "ignore"                     # 忽略
    MARK_CANCELLED = "mark_cancelled"     # 标记为已取消（幽灵订单）
    IMPORTED_TO_DB = "imported_to_db"     # 导入到数据库（孤儿订单）


# ============================================================
# Signal Status Tracking Models (S5-2)
# ============================================================
class SignalStatus(str, Enum):
    """信号状态枚举"""
    GENERATED = "generated"      # 已生成
    PENDING = "pending"          # 等待成交
    FILLED = "filled"            # 已成交
    CANCELLED = "cancelled"      # 已取消
    REJECTED = "rejected"        # 被拒绝
    # S6-2: Signal covering status
    ACTIVE = "active"            # 当前有效信号
    SUPERSEDED = "superseded"    # 已被更优信号替代


# Note: SignalTrack is defined after SignalResult to avoid forward reference issues


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

    # Multi-level take profit (S6-3)
    take_profit_levels: List[Dict[str, str]] = Field(
        default_factory=list,
        description="多级别止盈列表，结构：[{id, position_ratio, risk_reward, price}, ...]"
    )


# ============================================================
# Signal Status Tracking Models (S5-2, continued)
# ============================================================
class SignalTrack(BaseModel):
    """信号全生命周期跟踪"""
    signal_id: str
    original_signal: SignalResult
    status: SignalStatus
    created_at: int  # 毫秒时间戳
    updated_at: int  # 毫秒时间戳
    filled_price: Optional[Decimal] = None
    filled_at: Optional[int] = None
    reject_reason: Optional[str] = None
    cancel_reason: Optional[str] = None

    model_config = ConfigDict(use_enum_values=True)


# ============================================================
# Risk Configuration Models
# ============================================================
class RiskConfig(BaseModel):
    """Risk management configuration"""
    max_loss_percent: Decimal = Field(..., description="Max loss per trade as % of balance")
    max_leverage: int = Field(..., ge=1, le=125, description="Maximum leverage allowed")
    max_total_exposure: Decimal = Field(
        default=Decimal('0.8'),
        ge=0,
        le=1,
        description="Maximum total exposure as % of balance (e.g., 0.8 = 80%)"
    )
    # Extended fields from database (optional, for future features)
    daily_max_trades: Optional[int] = Field(
        default=None,
        ge=1,
        description="Maximum number of trades per day (optional)"
    )
    daily_max_loss: Optional[Decimal] = Field(
        default=None,
        description="Maximum daily loss amount (optional)"
    )
    max_position_hold_time: Optional[int] = Field(
        default=None,
        ge=1,
        description="Maximum position hold time in minutes (optional)"
    )

    @field_validator('max_loss_percent')
    @classmethod
    def validate_loss_percent(cls, v):
        if v <= 0 or v > Decimal('1'):
            raise ValueError("Max loss percent must be between 0 and 1")
        return v

    @field_validator('max_total_exposure')
    @classmethod
    def validate_total_exposure(cls, v):
        if v < 0 or v > Decimal('1'):
            raise ValueError("Max total exposure must be between 0 and 1")
        return v


# ============================================================
# Strategy Parameter Models (Phase K - Strategy Parameter Configuration)
# ============================================================
class PinbarParams(BaseModel):
    """Pinbar pattern detection parameters."""
    min_wick_ratio: Decimal = Field(
        default=Decimal("0.6"),
        ge=Decimal("0"),
        le=Decimal("1"),
        description="Minimum wick ratio (影线占全长的最低比例)"
    )
    max_body_ratio: Decimal = Field(
        default=Decimal("0.3"),
        ge=Decimal("0"),
        lt=Decimal("1"),
        description="Maximum body ratio (实体占全长的最高比例)"
    )
    body_position_tolerance: Decimal = Field(
        default=Decimal("0.1"),
        ge=Decimal("0"),
        lt=Decimal("0.5"),
        description="Body position tolerance (实体位置偏差容许度)"
    )

    @field_validator('min_wick_ratio')
    @classmethod
    def validate_min_wick_ratio(cls, v):
        if v <= Decimal("0"):
            raise ValueError("min_wick_ratio must be greater than 0")
        return v

    @field_validator('max_body_ratio')
    @classmethod
    def validate_max_body_ratio(cls, v):
        if v < Decimal("0") or v >= Decimal("1"):
            raise ValueError("max_body_ratio must be in [0, 1)")
        return v

    @field_validator('body_position_tolerance')
    @classmethod
    def validate_body_position_tolerance(cls, v):
        if v < Decimal("0") or v >= Decimal("0.5"):
            raise ValueError("body_position_tolerance must be in [0, 0.5)")
        return v


class EngulfingParams(BaseModel):
    """Engulfing pattern detection parameters."""
    max_wick_ratio: Decimal = Field(
        default=Decimal("0.6"),
        ge=Decimal("0"),
        le=Decimal("1"),
        description="Maximum wick ratio for filtering (最大影线比例)"
    )


class EmaParams(BaseModel):
    """EMA trend filter parameters."""
    period: int = Field(
        default=60,
        ge=5,
        le=200,
        description="EMA period (EMA 周期)"
    )


class MtfParams(BaseModel):
    """MTF (Multi-Timeframe) validation parameters."""
    enabled: bool = Field(
        default=True,
        description="Enable MTF validation (是否启用 MTF 校验)"
    )
    ema_period: int = Field(
        default=60,
        ge=5,
        le=200,
        description="EMA period for MTF trend calculation (MTF 趋势计算 EMA 周期)"
    )


class AtrParams(BaseModel):
    """ATR (Average True Range) filter parameters."""
    enabled: bool = Field(
        default=True,
        description="Enable ATR filter (是否启用 ATR 过滤器)"
    )
    period: int = Field(
        default=14,
        ge=5,
        le=50,
        description="ATR calculation period (ATR 计算周期)"
    )
    min_atr_ratio: Decimal = Field(
        default=Decimal("0.5"),
        ge=Decimal("0"),
        le=Decimal("5"),
        description="Minimum ATR ratio (K 线波幅/ATR，低于此值过滤)"
    )


class FilterParams(BaseModel):
    """Generic filter parameters with type discriminator."""
    type: Literal["ema", "ema_trend", "mtf", "atr", "volume_surge", "volatility_filter", "time_filter", "price_action"]
    enabled: bool = Field(default=True, description="Whether this filter is active")
    params: Dict[str, Any] = Field(default_factory=dict, description="Filter-specific parameters")


class StrategyParams(BaseModel):
    """
    Complete strategy parameters configuration.

    This is the main model for strategy parameter configuration API.
    """
    pinbar: PinbarParams = Field(default_factory=PinbarParams, description="Pinbar pattern parameters")
    engulfing: EngulfingParams = Field(default_factory=EngulfingParams, description="Engulfing pattern parameters")
    ema: EmaParams = Field(default_factory=EmaParams, description="EMA trend filter parameters")
    mtf: MtfParams = Field(default_factory=MtfParams, description="MTF validation parameters")
    atr: AtrParams = Field(default_factory=AtrParams, description="ATR filter parameters")
    filters: List[FilterParams] = Field(default_factory=list, description="Additional custom filters")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return self.model_dump(mode='json')

    @classmethod
    def from_config_manager(cls, config_manager: Any) -> "StrategyParams":
        """
        Build StrategyParams from ConfigManager.
        Deprecated: Use from_configs() instead.

        Args:
            config_manager: ConfigManager instance

        Returns:
            StrategyParams instance populated from config
        """
        # R3.1 fix: 使用 get_方法获取配置副本
        core = config_manager.get_core_config()
        user = config_manager.get_user_config()

        # Build pinbar params from core config
        pinbar = PinbarParams(
            min_wick_ratio=core.pinbar_defaults.min_wick_ratio,
            max_body_ratio=core.pinbar_defaults.max_body_ratio,
            body_position_tolerance=core.pinbar_defaults.body_position_tolerance,
        )

        # Build ema params from core config
        ema = EmaParams(period=core.ema.period)

        # Build mtf params from user config
        mtf = MtfParams(
            enabled=user.mtf_ema_period > 0,
            ema_period=user.mtf_ema_period,
        )

        # Default values for others
        engulfing = EngulfingParams()
        atr = AtrParams()

        return cls(
            pinbar=pinbar,
            engulfing=engulfing,
            ema=ema,
            mtf=mtf,
            atr=atr,
            filters=[],
        )

    @classmethod
    def from_configs(cls, core_config: Any, user_config: Any) -> "StrategyParams":
        """
        Build StrategyParams from core and user config objects.

        Args:
            core_config: CoreConfig instance
            user_config: UserConfig instance

        Returns:
            StrategyParams instance populated from config
        """
        # Build pinbar params from core config
        pinbar = PinbarParams(
            min_wick_ratio=core_config.pinbar_defaults.min_wick_ratio,
            max_body_ratio=core_config.pinbar_defaults.max_body_ratio,
            body_position_tolerance=core_config.pinbar_defaults.body_position_tolerance,
        )

        # Build ema params from core config
        ema = EmaParams(period=core_config.ema.period)

        # Build mtf params from user config
        mtf = MtfParams(
            enabled=user_config.mtf_ema_period > 0,
            ema_period=user_config.mtf_ema_period,
        )

        # Default values for others
        engulfing = EngulfingParams()
        atr = AtrParams()

        return cls(
            pinbar=pinbar,
            engulfing=engulfing,
            ema=ema,
            mtf=mtf,
            atr=atr,
            filters=[],
        )


class StrategyParamsUpdate(BaseModel):
    """Request model for updating strategy parameters."""
    pinbar: Optional[PinbarParams] = None
    engulfing: Optional[EngulfingParams] = None
    ema: Optional[EmaParams] = None
    mtf: Optional[MtfParams] = None
    atr: Optional[AtrParams] = None
    filters: Optional[List[FilterParams]] = None


class StrategyParamsPreview(BaseModel):
    """Request/Response model for strategy parameters preview (Dry Run)."""
    old_config: StrategyParams = Field(..., description="Current configuration")
    new_config: StrategyParams = Field(..., description="Proposed configuration")
    changes: List[str] = Field(default_factory=list, description="List of changed fields")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")


# ============================================================
# Multi-Level Take Profit Models (S6-3)
# ============================================================
class TakeProfitLevel(BaseModel):
    """单个止盈级别"""
    id: str = Field(..., description="止盈级别标识，如 TP1, TP2")
    position_ratio: Decimal = Field(..., description="仓位比例 (0.5 = 50%)")
    risk_reward: Decimal = Field(..., description="盈亏比 (1.5 = 1:1.5)")
    price: Decimal = Field(default=Decimal(0), description="计算后的止盈价格")


class TakeProfitConfig(BaseModel):
    """止盈策略配置"""
    enabled: bool = Field(default=True, description="是否启用多级别止盈")
    levels: List[TakeProfitLevel] = Field(
        default_factory=lambda: [
            TakeProfitLevel(id="TP1", position_ratio=Decimal("0.5"), risk_reward=Decimal("1.5")),
            TakeProfitLevel(id="TP2", position_ratio=Decimal("0.5"), risk_reward=Decimal("3.0")),
        ],
        description="止盈级别列表"
    )


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
    metadata: Dict[str, Any] = None  # 详细数据字典，如 candle_range, atr, ratio 等

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dc_dataclass
class SignalAttempt:
    """一次完整信号尝试的记录，无论是否最终触发信号"""
    strategy_name: str
    pattern: Optional['PatternResult']              # None 表示未检测到形态
    filter_results: list                             # List[Tuple[str, FilterResult]]
    final_result: str                                # "SIGNAL_FIRED" / "NO_PATTERN" / "FILTERED"
    kline_timestamp: Optional[int] = None            # K-line close timestamp in milliseconds

    # BT-4 归因分析扩展字段
    _pnl_ratio: Optional[float] = None
    _exit_reason: Optional[str] = None

    @property
    def direction(self) -> Optional[Direction]:
        return self.pattern.direction if self.pattern else None

    @property
    def pnl_ratio(self) -> Optional[float]:
        """盈亏比 (仅 SIGNAL_FIRED 信号)"""
        return self._pnl_ratio

    @property
    def exit_reason(self) -> Optional[str]:
        """出场原因 (仅 SIGNAL_FIRED 信号)"""
        return self._exit_reason


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
    source: Optional[str] = None  # 'live' or 'backtest'


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
    source: Optional[str] = None  # 'live' or 'backtest'


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
    # Using Dict to accept JSON payload, will be deserialized to StrategyDefinition
    strategies: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Dynamic strategy definitions with filter chains (overrides legacy params)"
    )
    risk_overrides: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Risk config overrides for this backtest"
    )

    # v3.0 PMS mode (Phase 2)
    mode: Literal["v2_classic", "v3_pms"] = Field(
        default="v2_classic",
        description="Backtest mode: 'v2_classic' (signal-level) or 'v3_pms' (position-level with matching engine)"
    )
    # T3: Changed defaults to None to support KV config priority (request > KV > code defaults)
    initial_balance: Optional[Decimal] = Field(
        default=None,
        description="Initial balance for v3_pms mode (default: 10000, or from KV config)"
    )
    slippage_rate: Optional[Decimal] = Field(
        default=None,
        description="Slippage rate for v3_pms mode (default: 0.001, or from KV config)"
    )
    fee_rate: Optional[Decimal] = Field(
        default=None,
        description="Fee rate for v3_pms mode (default: 0.0004, or from KV config)"
    )
    tp_slippage_rate: Optional[Decimal] = Field(
        default=None,
        description="Take-profit slippage rate for v3_pms mode (default: 0.0005, or from KV config)"
    )

    # Phase 4: 订单编排
    order_strategy: Optional['OrderStrategy'] = Field(
        default=None,
        description="订单策略配置（用于多级别止盈）"
    )


# ============================================================
# Dynamic Rule Engine Models (Phase K)
# ============================================================
# Import from logic_tree to avoid circular imports
from src.domain.logic_tree import TriggerConfig, FilterConfig
from pydantic import model_validator


class StrategyDefinition(BaseModel):
    """
    Dynamic strategy definition with attached filters.

    支持新旧两种格式：
    - 新格式使用 logic_tree 字段（推荐）
    - 旧格式使用 triggers/filters 字段（已废弃，自动迁移）
    """
    id: str = Field(default_factory=lambda: "")
    name: str = Field(..., description="Strategy name (e.g., 'pinbar', 'engulfing')")

    # ===== 新字段（推荐）=====
    logic_tree: Optional[Union["LogicNode", "LeafNode"]] = Field(
        default=None,
        description="Recursive logic tree (recommended)"
    )

    # ===== 旧字段（已废弃，保留用于向后兼容）=====
    # Core pattern triggers (supports multiple with AND/OR logic)
    triggers: List[TriggerConfig] = Field(default_factory=list, description="Core pattern triggers (deprecated)")
    trigger_logic: Literal["AND", "OR"] = Field(default="OR", description="How to combine triggers (deprecated)")

    # Legacy trigger (kept for backward compatibility)
    trigger: Optional[TriggerConfig] = Field(default=None, description="The core pattern trigger (legacy)")

    filters: List[FilterConfig] = Field(default_factory=list, description="Attached filter chain (deprecated)")
    filter_logic: Literal["AND", "OR"] = Field(default="AND", description="How to combine filter results (deprecated)")

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

    @model_validator(mode="after")
    def migrate_to_logic_tree(self) -> "StrategyDefinition":
        """
        如果 logic_tree 为空且存在旧字段，自动迁移到 logic_tree

        触发 DeprecationWarning 警告
        """
        import warnings

        # 只有在 logic_tree 为空且存在 triggers 时才迁移
        if self.logic_tree is None and (self.triggers or self.trigger):
            warnings.warn(
                f"Strategy '{self.name}' 使用已废弃的 triggers/filters 字段，"
                f"将自动迁移到 logic_tree。请使用 logic_tree 字段。",
                DeprecationWarning,
                stacklevel=2
            )
            self.logic_tree = self._build_from_legacy()
        return self

    def _build_from_legacy(self) -> Union["LogicNode", "LeafNode"]:
        """
        从旧字段构建逻辑树

        构建逻辑：
        1. 单个 trigger → 直接使用 TriggerLeaf
        2. 多个 trigger → 用 trigger_logic 组合
        3. 单个 filter → 直接使用 FilterLeaf
        4. 多个 filter → 用 filter_logic 组合
        5. trigger 组 AND filter 组 → AND 组合
        """
        from src.domain.logic_tree import LogicNode, TriggerLeaf, FilterLeaf

        children = []

        # 构建 trigger 部分
        if self.triggers:
            trigger_leafs = [
                TriggerLeaf(type="trigger", id=t.id or f"trigger_{i}", config=t)
                for i, t in enumerate(self.triggers)
            ]
            if len(trigger_leafs) == 1:
                children.append(trigger_leafs[0])
            else:
                children.append(LogicNode(
                    gate=self.trigger_logic,
                    children=trigger_leafs
                ))

        # 构建 filter 部分
        if self.filters:
            filter_leafs = [
                FilterLeaf(type="filter", id=f.id or f"filter_{i}", config=f)
                for i, f in enumerate(self.filters)
            ]
            if len(filter_leafs) == 1:
                children.append(filter_leafs[0])
            else:
                children.append(LogicNode(
                    gate=self.filter_logic,
                    children=filter_leafs
                ))

        # 合并
        if len(children) == 0:
            raise ValueError(f"Strategy '{self.name}' 必须至少有一个 trigger 或 filter")
        if len(children) == 1:
            return children[0]
        return LogicNode(gate="AND", children=children)

    def get_triggers_from_logic_tree(self) -> List[TriggerConfig]:
        """
        从 logic_tree 中提取所有 Trigger 配置

        用于向后兼容旧的 create_dynamic_runner() 接口

        Returns:
            List[TriggerConfig] - 所有 trigger 配置
        """
        from src.domain.logic_tree import LogicNode, TriggerLeaf

        triggers = []

        def extract(node):
            if isinstance(node, TriggerLeaf):
                triggers.append(node.config)
            elif isinstance(node, LogicNode):
                for child in node.children:
                    extract(child)

        if self.logic_tree:
            extract(self.logic_tree)
        return triggers

    def get_filters_from_logic_tree(self) -> List[FilterConfig]:
        """
        从 logic_tree 中提取所有 Filter 配置

        用于向后兼容旧的 create_dynamic_runner() 接口

        Returns:
            List[FilterConfig] - 所有 filter 配置
        """
        from src.domain.logic_tree import LogicNode, FilterLeaf

        filters = []

        def extract(node):
            if isinstance(node, FilterLeaf):
                filters.append(node.config)
            elif isinstance(node, LogicNode):
                for child in node.children:
                    extract(child)

        if self.logic_tree:
            extract(self.logic_tree)
        return filters


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


# ============================================================
# WebSocket Asset Push Configuration (S5-1)
# ============================================================
class WebSocketAssetConfig(BaseModel):
    """WebSocket 资产推送配置"""
    enabled: bool = Field(default=True, description="是否启用 WebSocket 推送")
    reconnect_delay: float = Field(default=1.0, description="初始重连延迟（秒）")
    max_reconnect_delay: float = Field(default=60.0, description="最大重连延迟（秒）")
    max_reconnect_attempts: int = Field(default=10, description="最大重连尝试次数")
    fallback_to_polling: bool = Field(default=True, description="WebSocket 失败时降级轮询")
    polling_interval: int = Field(default=60, description="轮询间隔（秒）")


# ============================================================
# Config Snapshot Models (for configuration version control)
# ============================================================
class ConfigSnapshot(BaseModel):
    """Configuration snapshot for version control and rollback."""
    id: Optional[int] = None
    version: str = Field(..., description="Version tag, e.g., 'v1.0.0'")
    config_json: str = Field(..., description="Serialized UserConfig JSON")
    description: str = Field(default="", description="Snapshot description")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="Creation timestamp (ISO 8601)")
    created_by: str = Field(default="user", description="Creator identifier")

    # Index fields for quick lookup
    is_active: bool = Field(default=False, description="Whether this snapshot is currently active")


# ============================================================
# Rebuild StrategyDefinition to resolve forward references
# ============================================================
from src.domain.logic_tree import LogicNode, LeafNode
StrategyDefinition.model_rebuild()


# ============================================================
# v3.0 Core Models (Phase 1)
# ============================================================
class FinancialModel(BaseModel):
    """v3 金融模型基类：统一定义十进制配置，拒绝隐式浮点数转换"""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")


# ----- v3.0 枚举类型 -----

class OrderStatus(str, Enum):
    """订单状态（与 CCXT 对齐）"""
    CREATED = "CREATED"           # 订单已创建（本地）
    SUBMITTED = "SUBMITTED"       # 订单已提交到交易所
    PENDING = "PENDING"           # 尚未发送到交易所（保留兼容）
    OPEN = "OPEN"                 # 挂单中
    PARTIALLY_FILLED = "PARTIALLY_FILLED"  # 部分成交
    FILLED = "FILLED"             # 完全成交
    CANCELED = "CANCELED"         # 已撤销
    REJECTED = "REJECTED"         # 交易所拒单
    EXPIRED = "EXPIRED"           # 已过期


class OrderType(str, Enum):
    """订单类型"""
    MARKET = "MARKET"             # 市价单
    LIMIT = "LIMIT"               # 限价单
    STOP_MARKET = "STOP_MARKET"   # 条件市价单
    STOP_LIMIT = "STOP_LIMIT"     # 条件限价单
    TRAILING_STOP = "TRAILING_STOP"  # 移动止损单


class OrderRole(str, Enum):
    """订单角色"""
    ENTRY = "ENTRY"               # 入场开仓
    TP1 = "TP1"                   # 第一目标位止盈
    TP2 = "TP2"                   # 第二目标位止盈
    TP3 = "TP3"                   # 第三目标位止盈
    TP4 = "TP4"                   # 第四目标位止盈
    TP5 = "TP5"                   # 第五目标位止盈
    SL = "SL"                     # 止损单


# ----- v3.0 核心实体模型 -----

class Account(FinancialModel):
    """资产账户：管理基础本金（可用现金）"""
    account_id: str = "default_wallet"
    total_balance: Decimal = Field(default=Decimal('0'), description="钱包总余额 (现金)")
    frozen_margin: Decimal = Field(default=Decimal('0'), description="冻结的开仓保证金")

    @property
    def available_balance(self) -> Decimal:
        return self.total_balance - self.frozen_margin


class Signal(FinancialModel):
    """
    意图层：只负责记录策略在某根 K 线发现的机会
    （它不再承担具体成交盈亏的状态机角色）
    """
    id: str
    strategy_id: str             # 触发该信号的策略名称
    symbol: str
    direction: Direction
    timestamp: int               # 信号生成的 K 线时间戳

    # 策略的初始意图
    expected_entry: Decimal      # 预期入场价
    expected_sl: Decimal         # 预期初始止损
    pattern_score: float         # 形态评分

    # 信号层的生命周期
    is_active: bool = True


class Order(FinancialModel):
    """
    执行层：与交易所真实交互的物理凭证
    """
    id: str
    signal_id: str               # 关联的外键：属于哪个信号触发的动作
    exchange_order_id: Optional[str] = None  # 真实 API 返回的单号
    symbol: str
    direction: Direction
    order_type: OrderType
    order_role: OrderRole

    # 价格与数量体系
    price: Optional[Decimal] = None          # 限价单的挂单价格
    trigger_price: Optional[Decimal] = None  # 条件单的触发价格

    requested_qty: Decimal       # 计划委托数量
    filled_qty: Decimal = Field(default=Decimal('0'))  # 真实成交数量
    average_exec_price: Optional[Decimal] = None       # 真实成交均价

    status: OrderStatus = OrderStatus.PENDING
    created_at: int
    updated_at: int

    # 平仓附加属性
    exit_reason: Optional[str] = None  # 用于统计: INITIAL_SL, BREAKEVEN_STOP, TRAILING_PROFIT

    # Phase 3 Reduce Only 约束
    # 契约表 3.1: 所有平仓单 (TP/SL) 必须携带 reduceOnly=True，防止保证金不足错误
    reduce_only: bool = Field(default=False, description="仅减仓平仓 (实盘约束)")

    # Phase 4 订单编排扩展
    parent_order_id: Optional[str] = None  # 父订单 ID (用于订单链)
    oco_group_id: Optional[str] = None     # OCO 组 ID (同一组的订单互斥)

    # T4 - 订单持久化扩展
    filled_at: Optional[int] = None  # 成交时间戳（毫秒），用于回测记录订单实际成交时间


# ============================================================
# Phase 5: 订单操作结果模型
# ============================================================
class OrderPlacementResult(FinancialModel):
    """
    订单下单结果

    用于 place_order() 方法的返回值
    """
    order_id: str                        # 系统生成的订单 ID
    exchange_order_id: Optional[str] = None  # 交易所返回的订单 ID
    symbol: str
    order_type: OrderType
    direction: Direction
    side: str                            # "buy" | "sell"
    amount: Decimal
    price: Optional[Decimal] = None
    trigger_price: Optional[Decimal] = None
    reduce_only: bool = False
    client_order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.PENDING
    created_at: int = Field(default_factory=lambda: int(time.time() * 1000))

    # 错误信息（当下单失败时）
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def is_success(self) -> bool:
        """是否下单成功"""
        return self.error_code is None


class OrderCancelResult(FinancialModel):
    """
    订单取消结果

    用于 cancel_order() 方法的返回值
    """
    order_id: str                        # 系统订单 ID
    exchange_order_id: Optional[str] = None  # 交易所订单 ID
    symbol: str
    status: OrderStatus = OrderStatus.CANCELED
    canceled_at: int = Field(default_factory=lambda: int(time.time() * 1000))
    message: str = "Order canceled successfully"

    # 错误信息（当取消失败时）
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def is_success(self) -> bool:
        """是否取消成功"""
        return self.error_code is None


class Position(FinancialModel):
    """
    资产层：PMS 系统的绝对核心，代表当前持有敞口
    """
    id: str
    signal_id: str               # 关联是由哪个信号引发的这笔持仓
    symbol: str
    direction: Direction

    # 核心资产状态 (采用业界标准：被平仓时均价死咬不变)
    entry_price: Decimal         # 开仓均价 (一旦 ENTRY 订单成交后，固定不变)
    current_qty: Decimal         # 当前持仓体积 (TP1 触发后会变小)

    # 动态风控水位线
    # LONG: 追踪入场后的最高价 (High Watermark)
    # SHORT: 追踪入场后的最低价 (Low Watermark)
    watermark_price: Optional[Decimal] = None

    # 业绩追踪
    realized_pnl: Decimal = Field(default=Decimal('0'), description="已实现盈亏 (落袋为安)")
    total_fees_paid: Decimal = Field(default=Decimal('0'), description="累计支付的手续费")

    is_closed: bool = False      # current_qty 归零时标记为 True


# ============================================================
# v3.0 Phase 4: 订单编排模型
# ============================================================

class OrderStrategy(FinancialModel):
    """
    订单策略：定义订单编排规则

    核心职责:
    1. 定义止盈级别数量和各级别比例
    2. 定义各级止盈比例
    3. 定义初始止损 RR 倍数
    4. 配置 OCO 和移动止损功能
    """
    id: str = Field(..., description="策略 ID")
    name: str = Field(..., description="策略名称")

    # 止盈级别配置
    tp_levels: int = Field(default=1, ge=1, le=5, description="止盈级别数量 (1-5)")
    tp_ratios: List[Decimal] = Field(default_factory=list, description="各级止盈比例 (总和=1.0)")
    tp_targets: List[Decimal] = Field(default_factory=lambda: [Decimal('1.5')], description="各级 TP 目标 RR 倍数 (如 [1.5, 2.0, 3.0])")

    # 风控配置
    initial_stop_loss_rr: Optional[Decimal] = Field(default=None, description="初始止损 RR 倍数 (如 -1.0 表示亏损 1R)")
    trailing_stop_enabled: bool = Field(default=True, description="是否启用移动止损")

    # OCO 配置
    oco_enabled: bool = Field(default=True, description="是否启用 OCO 逻辑")

    def validate_ratios(self) -> bool:
        """
        验证比例总和是否为 1.0

        返回:
            True: 比例有效
            False: 比例无效
        """
        if not self.tp_ratios:
            return False
        total = sum(self.tp_ratios)
        # 使用 Decimal 精度比较，允许小误差
        return abs(total - Decimal('1.0')) < Decimal('0.0001')

    @field_validator('tp_ratios')
    @classmethod
    def validate_tp_ratios_sum(cls, v):
        """验证 tp_ratios 总和是否接近 1.0"""
        if v and sum(v) != Decimal('1.0'):
            total = sum(v)
            if abs(total - Decimal('1.0')) > Decimal('0.0001'):
                raise ValueError(f"tp_ratios 总和必须为 1.0，当前为 {total}")
        return v

    def get_tp_ratio(self, level: int) -> Decimal:
        """
        获取指定级别的比例

        Args:
            level: TP 级别 (1-based)

        Returns:
            该级别的比例，如果级别超出范围则返回 0
        """
        if level < 1 or level > len(self.tp_ratios):
            return Decimal('0')
        return self.tp_ratios[level - 1]

    def get_tp_target_price(
        self,
        entry_price: Decimal,
        stop_loss: Decimal,
        tp_level: int,
        direction: Direction,
        tp_targets: List[Decimal],
    ) -> Decimal:
        """
        计算 TP 目标价格 (基于实际开仓价)

        公式:
            LONG: tp_price = entry_price + RR × (entry_price - stop_loss)
            SHORT: tp_price = entry_price - RR × (stop_loss - entry_price)

        Args:
            entry_price: 入场价 (实际开仓价)
            stop_loss: 止损价
            tp_level: TP 级别 (1-based)
            direction: 方向
            tp_targets: 各级 TP 目标 (RR 倍数，如 [1.0, 2.0, 3.0])

        Returns:
            TP 目标价格

        Raises:
            ValueError: 当 TP 级别超出范围时
        """
        if tp_level < 1 or tp_level > len(tp_targets):
            raise ValueError(f"TP 级别 {tp_level} 超出范围 (1-{len(tp_targets)})")

        rr_multiple = tp_targets[tp_level - 1]
        price_distance = entry_price - stop_loss

        if direction == Direction.LONG:
            # LONG: tp_price = entry + RR × (entry - sl)
            return entry_price + rr_multiple * price_distance
        else:
            # SHORT: tp_price = entry - RR × (sl - entry)
            # 注意：price_distance = entry_price - stop_loss (可能是负数)
            # 对于 SHORT，sl > entry，所以 sl - entry 是正数
            return entry_price - rr_multiple * (stop_loss - entry_price)


# ============================================================
# v3.0 Phase 2: PMS 回测报告模型
# ============================================================

class PositionSummary(FinancialModel):
    """
    仓位摘要：用于 PMS 回测报告
    """
    position_id: str
    signal_id: str
    symbol: str
    direction: Direction
    entry_price: Decimal
    exit_price: Optional[Decimal] = None  # 平仓价（仅当仓位关闭时）
    entry_time: int              # 开仓时间戳 (ms)
    exit_time: Optional[int] = None  # 平仓时间戳 (ms)
    realized_pnl: Decimal = Field(default=Decimal('0'), description="已实现盈亏")
    exit_reason: Optional[str] = None  # 平仓原因 (TP1/SL/TRAILING)


class PMSBacktestReport(FinancialModel):
    """
    v3.0 PMS 模式回测报告

    与 v2.0 回测报告的区别:
    - 基于真实仓位管理 (Position 实体)
    - 基于真实订单执行 (Order 实体)
    - 包含手续费和滑点影响
    - 支持多级别止盈统计

    字段说明:
    - strategy_id: 策略 ID
    - strategy_name: 策略名称
    - backtest_start/end: 回测时间范围
    - initial_balance: 初始资金
    - final_balance: 最终余额
    - total_return: 总收益率 (%)
    - total_trades: 总交易次数
    - winning_trades: 盈利交易次数
    - losing_trades: 亏损交易次数
    - win_rate: 胜率 (%)
    - total_pnl: 总盈亏 (USDT)
    - total_fees_paid: 总手续费
    - total_slippage_cost: 总滑点成本
    - max_drawdown: 最大回撤 (%)
    - sharpe_ratio: 夏普比率 (可选)
    - positions: 仓位历史摘要列表
    """
    strategy_id: str
    strategy_name: str
    backtest_start: int          # 回测开始时间戳 (ms)
    backtest_end: int            # 回测结束时间戳 (ms)
    initial_balance: Decimal
    final_balance: Decimal
    total_return: Decimal        # 总收益率 (%)
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: Decimal            # 胜率 (%)
    total_pnl: Decimal           # 总盈亏 (USDT)
    total_fees_paid: Decimal     # 总手续费
    total_slippage_cost: Decimal # 总滑点成本
    max_drawdown: Decimal        # 最大回撤 (%)
    sharpe_ratio: Optional[Decimal] = None  # 夏普比率
    positions: List[PositionSummary] = Field(default_factory=list)


# ============================================================
# BT-4: Strategy Attribution Analysis Models
# ============================================================

class AttributionReport(FinancialModel):
    """
    策略归因分析报告

    包含四个维度的归因分析结果：
    - shape_quality: 形态质量归因（B 维度）
    - filter_attribution: 过滤器归因（C 维度）
    - trend_attribution: 市场趋势归因（D 维度）
    - rr_attribution: 盈亏比归因（F 维度）
    """
    version: str = Field(default="1.0.0", description="归因分析报告版本")
    shape_quality: Dict[str, Any] = Field(default_factory=dict, description="形态质量归因")
    filter_attribution: Dict[str, Any] = Field(default_factory=dict, description="过滤器归因")
    trend_attribution: Dict[str, Any] = Field(default_factory=dict, description="市场趋势归因")
    rr_attribution: Dict[str, Any] = Field(default_factory=dict, description="盈亏比归因")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据（分析时间、数据源等）")


# ============================================================
# Phase 5: Reconciliation Models
# ============================================================

class PositionMismatch(FinancialModel):
    """仓位不匹配记录"""
    symbol: str = Field(..., description="币种对")
    local_qty: Decimal = Field(..., description="本地记录数量")
    exchange_qty: Decimal = Field(..., description="交易所记录数量")
    discrepancy: Decimal = Field(..., description="差异数量")


class OrderMismatch(FinancialModel):
    """订单不匹配记录"""
    order_id: str = Field(..., description="订单 ID")
    local_status: OrderStatus = Field(..., description="本地状态")
    exchange_status: str = Field(..., description="交易所状态")


class GhostOrder(FinancialModel):
    """
    幽灵订单：DB 有但交易所无

    P0-003: 完善重启对账流程
    检测条件：订单在 DB 中状态为 PENDING/NEW，但交易所查询不到
    处理逻辑：标记为 CANCELLED，记录对账报告
    """
    order_id: str = Field(..., description="订单 ID")
    symbol: str = Field(..., description="币种对")
    local_status: OrderStatus = Field(..., description="本地记录状态")
    detected_at: int = Field(..., description="检测时间戳（毫秒）")
    action_taken: str = Field(..., description="处理动作：'MARKED_CANCELLED'")


class ImportedOrder(FinancialModel):
    """
    导入订单：交易所有但 DB 无（孤儿订单导入）

    P0-003: 完善重启对账流程
    检测条件：交易所有活跃挂单，但 DB 中无记录
    处理逻辑：导入 DB 并创建关联 Signal
    """
    order_id: str = Field(..., description="订单 ID")
    exchange_order_id: str = Field(..., description="交易所订单 ID")
    symbol: str = Field(..., description="币种对")
    order_type: OrderType
    direction: Direction
    order_role: OrderRole
    status: OrderStatus
    amount: Decimal
    price: Optional[Decimal] = None
    trigger_price: Optional[Decimal] = None
    reduce_only: bool = False
    imported_at: int = Field(..., description="导入时间戳（毫秒）")
    action_taken: str = Field(..., description="处理动作：'IMPORTED_TO_DB' 或 'CANCELLED'")


class ReconciliationReport(FinancialModel):
    """
    对账报告响应

    Phase 5: 实盘集成 - 对账服务
    Reference: docs/designs/phase5-contract.md Section 9

    P0-003 新增:
    - ghost_orders: 幽灵订单列表（DB 有但交易所无）
    - imported_orders: 导入订单列表（孤儿订单导入 DB）
    - canceled_orphan_orders: 撤销的孤儿订单列表
    """
    symbol: str = Field(..., description="币种对")
    reconciliation_time: int = Field(..., description="对账时间戳（毫秒）")
    grace_period_seconds: int = Field(..., description="宽限期秒数")

    # 仓位差异
    position_mismatches: List[PositionMismatch] = Field(
        default_factory=list,
        description="仓位不匹配列表"
    )
    missing_positions: List["PositionInfo"] = Field(
        default_factory=list,
        description="本地缺失的仓位"
    )

    # 订单差异
    order_mismatches: List[OrderMismatch] = Field(
        default_factory=list,
        description="订单不匹配列表"
    )
    orphan_orders: List["OrderResponse"] = Field(
        default_factory=list,
        description="孤儿订单列表（交易所有但 DB 无）"
    )

    # P0-003: 对账处理结果
    ghost_orders: List[GhostOrder] = Field(
        default_factory=list,
        description="幽灵订单列表（DB 有但交易所无，已标记为 CANCELLED）"
    )
    imported_orders: List[ImportedOrder] = Field(
        default_factory=list,
        description="导入订单列表（孤儿订单导入 DB）"
    )
    canceled_orphan_orders: List[ImportedOrder] = Field(
        default_factory=list,
        description="撤销的孤儿订单列表（TP/SL 订单因仓位不存在被撤销）"
    )

    # 对账结论
    is_consistent: bool = Field(..., description="是否一致（无差异）")
    total_discrepancies: int = Field(..., description="总差异数")
    requires_attention: bool = Field(..., description="是否需要人工介入")
    summary: str = Field(..., description="对账结论摘要")


class OrderResponse(FinancialModel):
    """
    订单响应（用于对账报告中的孤儿订单）

    简化版本，仅包含必要字段
    """
    order_id: str
    exchange_order_id: Optional[str] = None
    symbol: str
    order_type: OrderType
    direction: Direction
    order_role: OrderRole
    status: OrderStatus
    amount: Decimal
    filled_amount: Decimal = Field(default=Decimal("0"))
    price: Optional[Decimal] = None
    trigger_price: Optional[Decimal] = None
    average_exec_price: Optional[Decimal] = None
    reduce_only: bool = Field(default=False)
    created_at: int
    updated_at: int


# ============================================================
# Phase 5: 实盘集成 - API 请求/响应模型
# Reference: docs/designs/phase5-contract.md
# ============================================================

class OrderRequest(FinancialModel):
    """
    下单请求模型

    Phase 6: v3.0 API - POST /api/v3/orders 请求体
    Reference: docs/designs/phase6-v3-api-contract.md Section 2.1.1

    约束条件:
    - order_type == LIMIT 时，price 必填
    - order_type == STOP_MARKET 时，trigger_price 必填
    - order_role IN (TP1, TP2, TP3, TP4, TP5, SL) 时，reduce_only 必须为 True
    """
    symbol: str = Field(
        ...,
        pattern=r'^[A-Z]+/[A-Z]+:[A-Z]+$',
        description="币种对，如 'BTC/USDT:USDT'"
    )
    order_type: OrderType = Field(..., description="订单类型 (MARKET/LIMIT/STOP_MARKET/STOP_LIMIT)")
    order_role: OrderRole = Field(..., description="订单角色 (ENTRY/TP1-5/SL)")
    direction: Direction = Field(..., description="方向 (LONG/SHORT)")
    quantity: Decimal = Field(..., gt=0, description="数量（正数）")
    price: Optional[Decimal] = Field(None, gt=0, description="限价单价格（LIMIT 订单必填）")
    trigger_price: Optional[Decimal] = Field(None, gt=0, description="条件单触发价（STOP 订单必填）")
    reduce_only: bool = Field(default=False, description="是否仅减仓（平仓单必须为 True）")
    client_order_id: Optional[str] = Field(None, max_length=36, description="客户端订单 ID (UUID)")
    strategy_name: Optional[str] = Field(None, max_length=64, description="策略名称")
    signal_id: Optional[str] = Field(None, description="关联信号 ID (UUID)")
    stop_loss: Optional[Decimal] = Field(None, gt=0, description="止损价格")
    take_profit: Optional[Decimal] = Field(None, gt=0, description="止盈价格")

    @model_validator(mode='after')
    def validate_order_fields(self) -> 'OrderRequest':
        """订单字段条件验证"""
        # LIMIT 或 STOP_LIMIT 订单必须有价格
        if self.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT):
            if self.price is None:
                raise ValueError('LIMIT/STOP_LIMIT 订单必须指定价格')

        # STOP_MARKET 或 STOP_LIMIT 订单必须有 trigger_price
        if self.order_type in (OrderType.STOP_MARKET, OrderType.STOP_LIMIT):
            if self.trigger_price is None:
                raise ValueError('STOP_MARKET/STOP_LIMIT 订单必须指定触发价')

        # TP/SL 订单必须设置 reduce_only=True
        if self.order_role in (OrderRole.TP1, OrderRole.TP2, OrderRole.TP3,
                                OrderRole.TP4, OrderRole.TP5, OrderRole.SL):
            if not self.reduce_only:
                raise ValueError('TP/SL 订单必须设置 reduce_only=True')

        return self


class OrderResponseFull(FinancialModel):
    """
    订单响应模型（完整版）

    Phase 6: v3.0 API - POST/GET /api/v3/orders 响应体
    Reference: docs/designs/phase6-v3-api-contract.md Section 2.1.2

    注意：此模型与 OrderResponse (简化版) 不同，此模型包含完整的 API 响应字段
    """
    order_id: str = Field(..., description="系统订单 ID")
    exchange_order_id: Optional[str] = Field(None, description="交易所订单 ID")
    symbol: str = Field(..., description="币种对")
    order_type: OrderType = Field(..., description="订单类型")
    order_role: OrderRole = Field(..., description="订单角色")
    direction: Direction = Field(..., description="方向")
    status: OrderStatus = Field(..., description="订单状态")
    quantity: Decimal = Field(..., description="订单数量")
    filled_qty: Decimal = Field(default=Decimal("0"), description="已成交数量")
    remaining_qty: Decimal = Field(default=Decimal("0"), description="剩余数量")
    price: Optional[Decimal] = Field(None, description="限价单价格")
    trigger_price: Optional[Decimal] = Field(None, description="条件单触发价")
    average_exec_price: Optional[Decimal] = Field(None, description="平均成交价")
    reduce_only: bool = Field(..., description="是否仅减仓")
    client_order_id: Optional[str] = Field(None, description="客户端订单 ID")
    strategy_name: Optional[str] = Field(None, description="策略名称")
    signal_id: Optional[str] = Field(None, description="关联信号 ID")
    stop_loss: Optional[Decimal] = Field(None, description="止损价格")
    take_profit: Optional[Decimal] = Field(None, description="止盈价格")
    created_at: int = Field(..., description="创建时间戳（毫秒）")
    updated_at: int = Field(..., description="更新时间戳（毫秒）")
    filled_at: Optional[int] = Field(None, description="成交时间戳（毫秒）")
    fee_paid: Decimal = Field(default=Decimal("0"), description="已支付手续费")
    fee_currency: Optional[str] = Field(None, description="手续费币种")
    tags: List[dict] = Field(default_factory=list, description="动态标签列表")


class OrdersResponse(FinancialModel):
    """
    订单列表分页响应模型

    Phase 6: v3.0 API - GET /api/v3/orders 响应体
    Reference: docs/designs/phase6-v3-api-contract.md Section 2.1.3
    """
    items: List[OrderResponseFull] = Field(..., description="订单列表")
    total: int = Field(..., description="订单总数")
    limit: int = Field(..., description="分页限制数量")
    offset: int = Field(default=0, description="分页偏移量")


class OrderCancelResponse(FinancialModel):
    """
    取消订单响应模型

    Phase 5: 实盘集成 - DELETE /api/orders/{order_id} 响应体
    Reference: docs/designs/phase5-contract.md Section 5.3
    """
    order_id: str = Field(..., description="系统订单 ID")
    exchange_order_id: Optional[str] = Field(None, description="交易所订单 ID")
    symbol: str = Field(..., description="币种对")
    status: OrderStatus = Field(..., description="取消后状态")
    canceled_at: int = Field(..., description="取消时间戳（毫秒）")
    message: str = Field(..., description="取消结果说明")


# ============================================================
# Phase 6 v3.0: 订单管理级联展示功能
# Reference: docs/designs/order-chain-tree-contract.md
# ============================================================

class OrderTreeNode(BaseModel):
    """
    订单树节点模型

    订单管理级联展示功能 - GET /api/v3/orders/tree 响应体
    Reference: docs/designs/order-chain-tree-contract.md Section

    字段说明:
    - order: 订单详情
    - children: 子订单列表（TP1-TP5, SL）
    - level: 层级深度（0=根节点 ENTRY，1=子订单）
    - has_children: 是否有子订单（用于 UI 展示展开图标）
    """
    order: Dict[str, Any] = Field(..., description="订单详情（OrderResponseFull 字典）")
    children: List['OrderTreeNode'] = Field(default_factory=list, description="子订单列表")
    level: int = Field(default=0, description="层级深度")
    has_children: bool = Field(default=False, description="是否有子订单")


class OrderTreeResponse(FinancialModel):
    """
    订单树响应模型

    订单管理级联展示功能 - GET /api/v3/orders/tree 响应体
    Reference: docs/designs/order-chain-tree-contract.md Section

    支持分页加载订单树，前端使用虚拟滚动优化渲染性能
    """
    items: List[OrderTreeNode] = Field(..., description="订单树节点列表")
    total: int = Field(..., description="当前页根订单数")
    total_count: int = Field(..., description="符合条件的总根订单数（用于分页）")
    page: int = Field(..., description="当前页码（从 1 开始）")
    page_size: int = Field(..., description="每页数量")
    metadata: Dict[str, Any] = Field(..., description="元数据（过滤条件、加载时间等）")


class OrderDeleteRequest(BaseModel):
    """
    批量删除订单请求模型

    订单管理级联展示功能 - DELETE /api/v3/orders/batch 请求体
    Reference: docs/designs/order-chain-tree-contract.md Section

    约束条件:
    - order_ids 不能为空
    - order_ids 数量不能超过 100
    """
    order_ids: List[str] = Field(..., max_length=100, description="要删除的订单 ID 列表")
    cancel_on_exchange: bool = Field(default=True, description="是否调用交易所取消接口")
    audit_info: Optional[Dict[str, str]] = Field(None, description="审计信息（operator_id, ip_address, user_agent）")

    @field_validator('order_ids')
    @classmethod
    def validate_order_ids(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError('订单 ID 列表不能为空')
        return v


class OrderDeleteResponse(FinancialModel):
    """
    批量删除订单响应模型

    订单管理级联展示功能 - DELETE /api/v3/orders/batch 响应体
    Reference: docs/designs/order-chain-tree-contract.md Section

    字段说明:
    - deleted_count: 删除的订单总数
    - cancelled_on_exchange: 在交易所成功取消的订单 ID 列表
    - failed_to_cancel: 在交易所取消失败的订单列表（包括原因）
    - deleted_from_db: 从数据库成功删除的订单 ID 列表
    - failed_to_delete: 数据库删除失败的订单列表（包括原因）
    - audit_log_id: 审计日志 ID
    """
    deleted_count: int = Field(..., description="删除的订单总数")
    cancelled_on_exchange: List[str] = Field(default_factory=list, description="在交易所成功取消的订单 ID 列表")
    failed_to_cancel: List[Dict[str, str]] = Field(default_factory=list, description="在交易所取消失败的订单列表")
    deleted_from_db: List[str] = Field(default_factory=list, description="从数据库成功删除的订单 ID 列表")
    failed_to_delete: List[Dict[str, str]] = Field(default_factory=list, description="数据库删除失败的订单列表")
    audit_log_id: Optional[str] = Field(None, description="审计日志 ID")


class PositionInfoV3(FinancialModel):
    """
    持仓信息模型 (v3 API 版本)

    Phase 5: 实盘集成 - GET /api/positions 响应体
    Reference: docs/designs/phase5-contract.md Section 7.2

    注意：此模型与 domain 层的 Position 实体 (line 762) 和 PositionInfo (line 70, legacy) 不同，
    此模型专用于 API 响应序列化，包含更多展示字段
    """
    position_id: str = Field(..., description="系统持仓 ID")
    symbol: str = Field(..., description="币种对")
    direction: Direction = Field(..., description="方向")
    current_qty: Decimal = Field(..., description="当前数量")
    entry_price: Decimal = Field(..., description="开仓均价")
    mark_price: Optional[Decimal] = Field(None, description="标记价格")
    unrealized_pnl: Decimal = Field(default=Decimal("0"), description="未实现盈亏")
    realized_pnl: Decimal = Field(default=Decimal("0"), description="已实现盈亏")
    liquidation_price: Optional[Decimal] = Field(None, description="强平价")
    leverage: int = Field(..., description="杠杆倍数")
    margin_mode: str = Field(default="CROSS", description="保证金模式（CROSS/ISOLATED）")
    is_closed: bool = Field(default=False, description="是否已平仓")
    opened_at: int = Field(..., description="开仓时间戳（毫秒）")
    closed_at: Optional[int] = Field(None, description="平仓时间戳（毫秒）")
    total_fees_paid: Decimal = Field(default=Decimal("0"), description="累计手续费")
    strategy_name: Optional[str] = Field(None, description="策略名称")
    stop_loss: Optional[Decimal] = Field(None, description="止损价格")
    take_profit: Optional[Decimal] = Field(None, description="止盈价格")
    tags: List[dict] = Field(default_factory=list, description="动态标签列表")


class PositionResponse(FinancialModel):
    """
    持仓列表响应模型

    Phase 5: 实盘集成 - GET /api/positions 响应体
    Reference: docs/designs/phase5-contract.md Section 7.2
    """
    positions: List[PositionInfoV3] = Field(..., description="持仓列表")
    total_unrealized_pnl: Decimal = Field(..., description="总未实现盈亏")
    total_realized_pnl: Decimal = Field(..., description="总已实现盈亏")
    total_margin_used: Decimal = Field(..., description="总占用保证金")
    account_equity: Optional[Decimal] = Field(None, description="账户权益")


class AccountBalance(FinancialModel):
    """
    账户余额信息模型

    Phase 5: 实盘集成 - GET /api/account 响应体子模型
    Reference: docs/designs/phase5-contract.md Section 8.2
    """
    currency: str = Field(..., description="币种，如 'USDT'")
    total_balance: Decimal = Field(..., description="总余额")
    available_balance: Decimal = Field(..., description="可用余额")
    frozen_balance: Decimal = Field(..., description="冻结余额")
    unrealized_pnl: Decimal = Field(default=Decimal("0"), description="未实现盈亏")


class AccountResponse(FinancialModel):
    """
    账户信息响应模型

    Phase 5: 实盘集成 - GET /api/account 响应体
    Reference: docs/designs/phase5-contract.md Section 8.2
    """
    exchange: str = Field(..., description="交易所名称")
    account_type: str = Field(..., description="账户类型（FUTURES/SPOT/MARGIN）")
    balances: List[AccountBalance] = Field(..., description="各币种余额")
    total_equity: Decimal = Field(..., description="总权益（USDT）")
    total_margin_balance: Decimal = Field(..., description="总保证金余额")
    total_wallet_balance: Decimal = Field(..., description="总钱包余额")
    total_unrealized_pnl: Decimal = Field(..., description="总未实现盈亏")
    available_balance: Decimal = Field(..., description="可用余额（开仓用）")
    total_margin_used: Decimal = Field(..., description="已用保证金")
    account_leverage: int = Field(..., description="账户最大杠杆")
    last_updated: int = Field(..., description="最后更新时间戳（毫秒）")


class ReconciliationRequest(FinancialModel):
    """
    对账请求模型

    Phase 5: 实盘集成 - POST /api/reconciliation 请求体
    Reference: docs/designs/phase5-contract.md Section 9.1
    """
    symbol: str = Field(..., description="币种对")
    full_check: bool = Field(default=False, description="是否全量检查（包含宽限期二次校验）")


# Forward reference rebuild for models with cross-references
ReconciliationReport.model_rebuild()
PositionResponse.model_rebuild()


# ============================================================
# Phase 5: Capital Protection Models
# ============================================================

class CapitalProtectionConfig(BaseModel):
    """
    资金保护配置

    Phase 5: 实盘集成 - 资金保护管理器
    Reference: docs/designs/phase5-detailed-design.md Section 3.4

    P2-2: 类常量配置化 - 将硬编码的 MIN_NOTIONAL, PRICE_DEVIATION_THRESHOLD 提取到配置类
    """
    enabled: bool = Field(default=True, description="是否启用资金保护")

    # P2-2: 订单参数合理性检查配置（原类常量）
    min_notional: Decimal = Field(
        default=Decimal("5"),
        description="最小名义价值 (默认 5 USDT, Binance 标准)"
    )
    price_deviation_threshold: Decimal = Field(
        default=Decimal("0.10"),
        description="价格偏差阈值 (默认 10%)"
    )
    extreme_price_deviation_threshold: Decimal = Field(
        default=Decimal("0.20"),
        description="极端行情下价格偏差阈值 (默认 20%)"
    )

    # 单笔交易限制
    single_trade: Dict[str, Any] = Field(
        default_factory=lambda: {
            "max_loss_percent": Decimal("2.0"),    # 单笔最大损失 2% of balance
            "max_position_percent": Decimal("20"), # 单次最大仓位 20% of balance
        },
        description="单笔交易限制配置"
    )

    # 每日限制
    daily: Dict[str, Any] = Field(
        default_factory=lambda: {
            "max_loss_percent": Decimal("5.0"),    # 每日最大回撤 5% of balance
            "max_trade_count": 50,                 # 每日最大交易次数
        },
        description="每日限制配置"
    )

    # 账户限制
    account: Dict[str, Any] = Field(
        default_factory=lambda: {
            "min_balance": Decimal("100"),         # 最低余额保留 (USDT)
            "max_leverage": 10,                    # 最大杠杆倍数
        },
        description="账户限制配置"
    )


class DailyTradeStats(BaseModel):
    """
    每日交易统计

    用于追踪当日交易表现，在每日重置时清零
    """
    trade_count: int = Field(default=0, description="当日交易次数")
    realized_pnl: Decimal = Field(default=Decimal("0"), description="当日已实现盈亏 (USDT)")
    last_reset_date: str = Field(default_factory=lambda: datetime.now(timezone.utc).date().isoformat(), description="最后重置日期")


# ============================================================
# P2-1: Risk Manager Configuration
# ============================================================

class RiskManagerConfig(BaseModel):
    """
    动态风控管理器配置

    P2-1: 魔法数字配置化 - 将硬编码的 trailing_percent 和 step_threshold 提取到配置类
    """
    trailing_percent: Decimal = Field(
        default=Decimal('0.02'),
        description="移动止损回撤容忍度 (默认 2%)"
    )
    step_threshold: Decimal = Field(
        default=Decimal('0.005'),
        description="阶梯阈值 (默认 0.5%)"
    )


# ============================================================
# P0-004: 订单参数合理性检查 - 极端行情配置
# ============================================================

class ExtremeVolatilityConfig(BaseModel):
    """
    极端行情配置

    触发条件（满足任一即触发）:
    1. 短时间价格波动超过阈值
    2. 交易量异常放大
    3. 市场深度严重不足

    触发后的行为:
    1. 放宽价格偏差限制（如 10% → 20%）
    2. 暂停价格偏差检查（仅记录警告）
    3. 暂停所有非紧急下单（等待人工确认）
    """
    # ===== 触发条件配置 =====

    enabled: bool = Field(
        default=True,
        description="是否启用极端行情检测"
    )

    # 价格波动阈值（5 分钟内）
    price_volatility_threshold: Decimal = Field(
        default=Decimal("5.0"),  # 5%
        description="5 分钟内价格波动超过此百分比触发极端行情"
    )

    # 价格波动检查时间窗口（秒）
    volatility_window_seconds: int = Field(
        default=300,  # 5 分钟
        description="价格波动检查的时间窗口"
    )

    # 成交量放大阈值（相对于 24 小时均量）
    volume_surge_threshold: Decimal = Field(
        default=Decimal("3.0"),  # 3 倍
        description="当前成交量超过 24 小时均量此倍数触发极端行情"
    )

    # 市场深度不足阈值（买单/卖单差额比例）
    depth_imbalance_threshold: Decimal = Field(
        default=Decimal("0.8"),  # 80%
        description="买卖盘深度差额超过此比例触发极端行情"
    )

    # ===== 触发后行为配置 =====

    # 行为选项：relax(放宽) / pause_check(暂停检查) / pause_all(暂停所有下单)
    action_on_trigger: str = Field(
        default="relax",
        description="触发极端行情后的行为"
    )

    # 放宽后的价格偏差限制
    relaxed_price_deviation: Decimal = Field(
        default=Decimal("20.0"),  # 20%
        description="极端行情下放宽的价格偏差限制"
    )

    # 仅允许 TP/SL 订单（暂停开仓）
    allow_only_tp_sl: bool = Field(
        default=True,
        description="极端行情下仅允许 TP/SL 订单"
    )

    # 通知配置
    notify_on_trigger: bool = Field(
        default=True,
        description="触发极端行情时发送通知"
    )

    # 自动恢复时间（秒）
    auto_recovery_seconds: int = Field(
        default=600,  # 10 分钟
        description="触发后自动恢复正常检查的时间"
    )


class ExtremeVolatilityStatus(BaseModel):
    """极端行情状态"""
    is_extreme: bool = Field(default=False, description="是否处于极端行情")
    triggered_at: Optional[int] = None  # 触发时间戳（毫秒）
    trigger_reason: Optional[str] = None  # 触发原因
    current_volatility: Decimal = Field(
        default=Decimal("0"),
        description="当前波动率"
    )
    recovery_at: Optional[int] = None  # 预计恢复时间戳


class OrderCheckResult(BaseModel):
    """
    订单检查结果

    Phase 5: 资金保护检查结果
    Reference: docs/designs/phase5-contract.md Section 10

    P0-004 新增字段:
    - notional_value: 订单名义价值
    - min_notional: 最小名义价值要求
    - order_price: 订单价格
    - ticker_price: 参考价格
    - price_deviation: 价格偏差
    """
    allowed: bool = Field(..., description="是否允许下单")
    reason: Optional[str] = Field(None, description="拒绝原因代码")
    reason_message: Optional[str] = Field(None, description="拒绝原因人类可读描述")

    # 详细检查结果
    single_trade_check: Optional[bool] = Field(None, description="单笔交易检查是否通过")
    position_limit_check: Optional[bool] = Field(None, description="仓位限制检查是否通过")
    daily_loss_check: Optional[bool] = Field(None, description="每日亏损检查是否通过")
    daily_count_check: Optional[bool] = Field(None, description="每日次数检查是否通过")
    balance_check: Optional[bool] = Field(None, description="余额检查是否通过")

    # 详细数据
    estimated_loss: Optional[Decimal] = Field(None, description="预计损失（USDT）")
    max_allowed_loss: Optional[Decimal] = Field(None, description="最大允许损失（USDT）")
    position_value: Optional[Decimal] = Field(None, description="仓位价值（USDT）")
    max_allowed_position: Optional[Decimal] = Field(None, description="最大允许仓位（USDT）")
    daily_pnl: Optional[Decimal] = Field(None, description="当日盈亏（USDT）")
    daily_trade_count: Optional[int] = Field(None, description="当日交易次数")
    available_balance: Optional[Decimal] = Field(None, description="可用余额（USDT）")
    min_required_balance: Optional[Decimal] = Field(None, description="最低保留余额（USDT）")

    # P0-004: 订单参数合理性检查
    notional_value: Optional[Decimal] = Field(None, description="订单名义价值（USDT）")
    min_notional: Optional[Decimal] = Field(None, description="最小名义价值要求（USDT）")
    order_price: Optional[Decimal] = Field(None, description="订单价格")
    ticker_price: Optional[Decimal] = Field(None, description="参考价格")
    price_deviation: Optional[Decimal] = Field(None, description="价格偏差")

    # P0-004: 数量精度检查
    quantity_precision_check: Optional[bool] = Field(None, description="数量精度检查是否通过")
    min_quantity: Optional[Decimal] = Field(None, description="最小交易量要求")
    required_precision: Optional[int] = Field(None, description="要求的数量精度")
    step_size: Optional[Decimal] = Field(None, description="数量步长")


# ============================================================
# Phase 6: v3.0 API - Additional Models
# ============================================================

class OrderCheckRequest(FinancialModel):
    """
    下单前资金保护检查请求模型

    Phase 6: v3.0 API - POST /api/v3/orders/check 请求体
    Reference: docs/designs/phase6-v3-api-contract.md Section 2.6.1
    """
    symbol: str = Field(..., description="币种对")
    order_type: OrderType = Field(..., description="订单类型")
    quantity: Decimal = Field(..., gt=0, description="订单数量")
    price: Optional[Decimal] = Field(None, gt=0, description="限价单价格")
    trigger_price: Optional[Decimal] = Field(None, gt=0, description="条件单触发价")
    stop_loss: Optional[Decimal] = Field(None, gt=0, description="建议止损价")


class ClosePositionRequest(FinancialModel):
    """
    平仓请求模型

    Phase 6: v3.0 API - POST /api/v3/positions/{id}/close 请求体
    Reference: docs/designs/phase6-v3-api-contract.md Section 2.4
    """
    quantity: Optional[Decimal] = Field(None, gt=0, description="平仓数量（部分平仓时使用）")
    order_type: OrderType = Field(default=OrderType.MARKET, description="平仓订单类型")


# Forward declarations for CapitalProtectionCheckResult
class SingleTradeCheck(BaseModel):
    """单笔交易检查结果"""
    passed: bool = Field(..., description="是否通过")
    max_loss: Optional[Decimal] = Field(None, description="最大允许损失")
    estimated_loss: Optional[Decimal] = Field(None, description="预计损失")


class PositionLimitCheck(BaseModel):
    """仓位限制检查结果"""
    passed: bool = Field(..., description="是否通过")
    max_position: Optional[Decimal] = Field(None, description="最大允许仓位")
    position_value: Optional[Decimal] = Field(None, description="当前仓位价值")


class DailyLossCheck(BaseModel):
    """每日亏损限制检查结果"""
    passed: bool = Field(..., description="是否通过")
    daily_max_loss: Optional[Decimal] = Field(None, description="每日最大允许亏损")
    daily_pnl: Optional[Decimal] = Field(None, description="当日已实现盈亏")


class TradeCountCheck(BaseModel):
    """每日交易次数检查结果"""
    passed: bool = Field(..., description="是否通过")
    max_count: Optional[int] = Field(None, description="每日最大交易次数")
    current_count: Optional[int] = Field(None, description="当前交易次数")


class MinBalanceCheck(BaseModel):
    """最低余额检查结果"""
    passed: bool = Field(..., description="是否通过")
    min_balance: Optional[Decimal] = Field(None, description="最低保留余额")
    current_balance: Optional[Decimal] = Field(None, description="当前可用余额")


class CapitalProtectionCheckResult(BaseModel):
    """
    资金保护检查结果（Phase 6 详细版）

    Phase 6: v3.0 API - POST /api/v3/orders/check 响应体
    Reference: docs/designs/phase6-v3-api-contract.md Section 2.6.2
    """
    allowed: bool = Field(..., description="是否允许下单")
    reason: Optional[str] = Field(None, description="拒绝原因（当 allowed=false）")

    # 各分项检查结果
    single_trade_limit: Optional[SingleTradeCheck] = Field(None, description="单笔交易限制检查")
    position_limit: Optional[PositionLimitCheck] = Field(None, description="仓位限制检查")
    daily_loss_limit: Optional[DailyLossCheck] = Field(None, description="每日亏损限制检查")
    daily_trade_count: Optional[TradeCountCheck] = Field(None, description="每日交易次数检查")
    min_balance: Optional[MinBalanceCheck] = Field(None, description="最低余额检查")


# ============================================================
# API Error Response Models (MIN-001)
# ============================================================
class ErrorResponse(BaseModel):
    """
    统一错误响应模型

    MIN-001: 统一错误响应格式
    Reference: docs/arch/系统开发规范与红线.md - API 错误处理规范

    所有 API 错误响应统一格式：
    - error_code: 错误代码（F-xxx, C-xxx, W-xxx 或 HTTP 状态码）
    - message: 人类可读的错误描述
    """
    error_code: str = Field(..., description="错误代码")
    message: str = Field(..., description="错误描述")

    model_config = ConfigDict(arbitrary_types_allowed=True)


# ============================================================
# Phase 8: 自动化调参 (Optuna 集成) 相关模型
# ============================================================

class ParameterType(str, Enum):
    """参数类型枚举"""
    INT = "int"
    FLOAT = "float"
    CATEGORICAL = "categorical"


class OptunaDirection(str, Enum):
    """Optuna 优化方向"""
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"


class OptimizationObjective(str, Enum):
    """优化目标"""
    SHARPE = "sharpe"  # 夏普比率
    SORTINO = "sortino"  # 索提诺比率
    PNL_DD = "pnl_dd"  # 收益/回撤比
    TOTAL_RETURN = "total_return"  # 总收益
    WIN_RATE = "win_rate"  # 胜率
    MAX_PROFIT = "max_profit"  # 最大单笔盈利


class ParameterDefinition(BaseModel):
    """
    参数定义

    Phase 8: 自动化调参 - 参数空间定义
    Reference: docs/designs/phase8-optimizer-contract.md
    """
    name: str = Field(..., description="参数名称")
    type: ParameterType = Field(..., description="参数类型")

    # 整数参数
    low: Optional[int] = Field(None, description="最小值（整数参数）")
    high: Optional[int] = Field(None, description="最大值（整数参数）")
    step: Optional[int] = Field(1, description="步长（整数参数）")

    # 浮点参数
    low_float: Optional[float] = Field(None, description="最小值（浮点参数）")
    high_float: Optional[float] = Field(None, description="最大值（浮点参数）")

    # 离散参数
    choices: Optional[List[Any]] = Field(None, description="可选值列表（离散参数）")

    # 默认值
    default: Optional[Any] = Field(None, description="默认值")

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ParameterSpace(BaseModel):
    """
    参数空间 - 多个参数定义的聚合

    Phase 8: 自动化调参 - 参数空间定义
    """
    parameters: List[ParameterDefinition] = Field(default_factory=list, description="参数列表")

    def add_parameter(self, param: ParameterDefinition) -> "ParameterSpace":
        """添加参数到参数空间"""
        self.parameters.append(param)
        return self

    model_config = ConfigDict(arbitrary_types_allowed=True)


class OptimizationRequest(BaseModel):
    """
    优化请求

    Phase 8: 自动化调参 - POST /api/optimize 请求体
    Reference: docs/designs/phase8-optimizer-contract.md Section 2.1
    """
    symbol: str = Field(..., description="交易对")
    timeframe: str = Field(..., description="时间周期")
    start_time: Optional[int] = Field(None, description="开始时间戳（毫秒）")
    end_time: Optional[int] = Field(None, description="结束时间戳（毫秒）")
    limit: int = Field(default=100, ge=10, le=1000, description="K 线数量")

    # 优化配置
    objective: OptimizationObjective = Field(default=OptimizationObjective.SHARPE, description="优化目标")
    n_trials: int = Field(default=100, ge=10, le=1000, description="试验次数")
    timeout: Optional[int] = Field(None, ge=60, description="超时时间（秒）")

    # 参数空间
    parameter_space: ParameterSpace = Field(..., description="参数空间定义")

    # 回测配置
    initial_balance: Decimal = Field(default=Decimal("10000"), description="初始资金")
    slippage_rate: Decimal = Field(default=Decimal("0.001"), description="滑点率")
    fee_rate: Decimal = Field(default=Decimal("0.0004"), description="手续费率")

    # 高级模式
    continue_from_last: bool = Field(default=False, description="是否从上次进度继续")

    model_config = ConfigDict(arbitrary_types_allowed=True)


class OptimizationJobStatus(str, Enum):
    """优化任务状态"""
    RUNNING = "running"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"


class OptimizationTrialResult(BaseModel):
    """
    单次试验结果

    Phase 8: 自动化调参 - 试验历史记录
    """
    trial_number: int = Field(..., description="试验编号")
    params: Dict[str, Any] = Field(..., description="参数组合")
    objective_value: float = Field(..., description="目标函数值")

    # 详细指标
    total_return: Optional[Decimal] = Field(None, description="总收益")
    win_rate: Optional[float] = Field(None, description="胜率")
    max_drawdown: Optional[Decimal] = Field(None, description="最大回撤")
    sharpe_ratio: Optional[float] = Field(None, description="夏普比率")
    sortino_ratio: Optional[float] = Field(None, description="索提诺比率")
    pnl_dd_ratio: Optional[float] = Field(None, description="收益/回撤比")

    # 回测统计
    total_trades: int = Field(default=0, description="总交易次数")
    winning_trades: int = Field(default=0, description="盈利交易次数")

    # 时间戳
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="完成时间")

    model_config = ConfigDict(arbitrary_types_allowed=True)


class OptimizationHistory(BaseModel):
    """
    优化历史记录

    Phase 8: 自动化调参 - SQLite 持久化模型
    """
    job_id: str = Field(..., description="任务 ID")
    trial_number: int = Field(..., description="试验编号")
    params_json: str = Field(..., description="参数组合（JSON 字符串）")
    objective_value: float = Field(..., description="目标函数值")
    metrics_json: str = Field(..., description="详细指标（JSON 字符串）")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="创建时间")

    model_config = ConfigDict(arbitrary_types_allowed=True)


class OptimizationJob(BaseModel):
    """
    优化任务

    Phase 8: 自动化调参 - 任务管理
    """
    job_id: str = Field(..., description="任务 ID")
    request: OptimizationRequest = Field(..., description="优化请求")
    status: OptimizationJobStatus = Field(default=OptimizationJobStatus.RUNNING, description="任务状态")

    # 进度追踪
    current_trial: int = Field(default=0, description="当前试验次数")
    total_trials: int = Field(..., description="总试验次数")
    best_trial: Optional[OptimizationTrialResult] = Field(None, description="当前最佳试验")
    best_value: Optional[float] = Field(None, description="当前最佳目标函数值")

    # 时间追踪
    started_at: Optional[datetime] = Field(None, description="开始时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")

    # 错误信息
    error_message: Optional[str] = Field(None, description="错误信息（失败时）")

    # Optuna Study ID（用于断点续研）
    study_id: Optional[str] = Field(None, description="Optuna Study ID")

    model_config = ConfigDict(arbitrary_types_allowed=True)


# ============================================================
# Config Management Models (for Repository layer)
# ============================================================

class SystemConfig(BaseModel):
    """
    System configuration model.

    Contains core system settings that require restart to take effect.
    """
    core_symbols: List[str] = Field(default_factory=list, description="Core trading symbols (protected)")
    ema_period: int = Field(default=60, ge=5, le=200, description="EMA period for trend filter")
    mtf_ema_period: int = Field(default=60, ge=5, le=200, description="MTF EMA period")
    pinbar_min_wick_ratio: Decimal = Field(default=Decimal("0.6"), description="Pinbar min wick ratio")
    pinbar_max_body_ratio: Decimal = Field(default=Decimal("0.3"), description="Pinbar max body ratio")
    pinbar_body_position_tolerance: Decimal = Field(default=Decimal("0.1"), description="Pinbar body position tolerance")
    signal_cooldown_seconds: int = Field(default=14400, ge=60, description="Signal deduplication cooldown")
    backtest_take_profit_slippage_rate: Decimal = Field(default=Decimal("0.0005"), description="Backtest TP slippage")
    # Extended fields from database (optional, for future features)
    queue_batch_size: Optional[int] = Field(
        default=10,
        ge=1,
        description="Queue batch size for async I/O (optional)"
    )
    queue_flush_interval: Optional[Decimal] = Field(
        default=Decimal("5.0"),
        ge=Decimal("0.1"),
        description="Queue flush interval in seconds (optional)"
    )
    queue_max_size: Optional[int] = Field(
        default=1000,
        ge=100,
        description="Queue maximum size (optional)"
    )
    warmup_history_bars: Optional[int] = Field(
        default=100,
        ge=10,
        description="Warmup history bars count (optional)"
    )
    atr_filter_enabled: Optional[bool] = Field(
        default=True,
        description="ATR filter enable switch (optional)"
    )
    atr_period: Optional[int] = Field(
        default=14,
        ge=1,
        description="ATR period (optional)"
    )
    atr_min_ratio: Optional[Decimal] = Field(
        default=Decimal("0.5"),
        ge=Decimal("0"),
        description="ATR minimum ratio (optional)"
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)


class SymbolConfig(BaseModel):
    """
    Symbol configuration model.

    Contains per-symbol settings for trading.
    """
    symbol: str = Field(..., description="Trading symbol (e.g., 'BTC/USDT:USDT')")
    is_active: bool = Field(default=True, description="Whether this symbol is active for trading")
    max_leverage: int = Field(default=10, ge=1, le=125, description="Maximum leverage for this symbol")
    custom_settings: Dict[str, Any] = Field(default_factory=dict, description="Custom per-symbol settings")

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ConfigHistoryEntry(BaseModel):
    """
    Configuration history entry for audit trail.

    Tracks all configuration changes with before/after values.
    """
    id: Optional[int] = None
    entity_type: str = Field(..., description="Entity type: 'strategy', 'risk', 'system', 'symbol', 'notification'")
    entity_id: str = Field(..., description="Entity identifier (strategy_id, symbol, etc.)")
    action: str = Field(..., description="Action: 'create', 'update', 'delete', 'toggle', 'rollback'")
    old_values: str = Field(default="{}", description="Previous values (JSON string)")
    new_values: str = Field(default="{}", description="New values (JSON string)")
    summary: str = Field(..., description="Human-readable summary of the change")
    changed_by: str = Field(default="user", description="Who made the change")
    changed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="Change timestamp (ISO 8601)")

    model_config = ConfigDict(arbitrary_types_allowed=True)


# ============================================================
# ORD-5: Order Audit Log Models (订单审计日志模型)
# ============================================================

class OrderAuditEventType(str, Enum):
    """
    订单审计事件类型（与 ORD-1 状态机对齐）
    """
    ORDER_CREATED = "ORDER_CREATED"           # 订单创建
    ORDER_SUBMITTED = "ORDER_SUBMITTED"       # 订单提交到交易所
    ORDER_CONFIRMED = "ORDER_CONFIRMED"       # 订单确认挂单
    ORDER_PARTIAL_FILLED = "ORDER_PARTIAL_FILLED"  # 部分成交
    ORDER_FILLED = "ORDER_FILLED"             # 完全成交
    ORDER_CANCELED = "ORDER_CANCELED"         # 订单取消
    ORDER_REJECTED = "ORDER_REJECTED"         # 交易所拒单
    ORDER_EXPIRED = "ORDER_EXPIRED"           # 订单过期
    ORDER_UPDATED = "ORDER_UPDATED"           # 订单信息更新


class OrderAuditTriggerSource(str, Enum):
    """
    审计日志触发来源（与 ORD-1 对齐）
    """
    USER = "USER"         # 用户主动操作
    SYSTEM = "SYSTEM"     # 系统自动触发
    EXCHANGE = "EXCHANGE" # 交易所推送


class OrderAuditLog(BaseModel):
    """
    订单审计日志

    记录订单全生命周期的所有事件，用于审计追溯和问题诊断。
    """
    id: str = Field(..., description="审计日志 ID, UUID 格式")
    order_id: str = Field(..., description="订单 ID")
    signal_id: Optional[str] = Field(None, description="关联信号 ID（可选，用于追踪订单链）")
    old_status: Optional[str] = Field(None, description="旧状态（首次创建时为 None）")
    new_status: str = Field(..., description="新状态")
    event_type: OrderAuditEventType = Field(..., description="事件类型")
    triggered_by: OrderAuditTriggerSource = Field(..., description="触发来源")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="元数据（JSON 格式）")
    created_at: int = Field(..., description="创建时间（毫秒时间戳）")

    model_config = ConfigDict(arbitrary_types_allowed=True, use_enum_values=True)


class OrderAuditLogCreate(BaseModel):
    """
    创建审计日志请求模型
    """
    order_id: str = Field(..., description="订单 ID")
    signal_id: Optional[str] = Field(None, description="关联信号 ID")
    old_status: Optional[str] = Field(None, description="旧状态")
    new_status: str = Field(..., description="新状态")
    event_type: OrderAuditEventType = Field(..., description="事件类型")
    triggered_by: OrderAuditTriggerSource = Field(..., description="触发来源")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="元数据")

    model_config = ConfigDict(arbitrary_types_allowed=True, use_enum_values=True)


class OrderAuditLogQuery(BaseModel):
    """
    审计日志查询参数模型
    """
    order_id: Optional[str] = Field(None, description="订单 ID")
    signal_id: Optional[str] = Field(None, description="信号 ID")
    event_type: Optional[OrderAuditEventType] = Field(None, description="事件类型")
    triggered_by: Optional[OrderAuditTriggerSource] = Field(None, description="触发来源")
    start_time: Optional[int] = Field(None, description="开始时间（毫秒时间戳）")
    end_time: Optional[int] = Field(None, description="结束时间（毫秒时间戳）")
    limit: int = Field(default=100, ge=1, le=1000, description="返回数量限制")
    offset: int = Field(default=0, ge=0, description="偏移量")

    model_config = ConfigDict(arbitrary_types_allowed=True, use_enum_values=True)
