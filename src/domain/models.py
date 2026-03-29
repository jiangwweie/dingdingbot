"""
Global Pydantic models - shared contract between Dev A (Infrastructure) and Dev B (Domain).
DO NOT modify without architect approval.
"""
from pydantic import BaseModel, Field, field_validator
from decimal import Decimal
from typing import Optional, List, Dict, Any, Union, Annotated, Literal
from enum import Enum
from datetime import datetime, timezone


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
# Signal Status Tracking Models (S5-2)
# ============================================================
class SignalStatus(str, Enum):
    """信号状态枚举"""
    GENERATED = "generated"      # 已生成
    PENDING = "pending"          # 等待成交
    FILLED = "filled"            # 已成交
    CANCELLED = "cancelled"      # 已取消
    REJECTED = "rejected"        # 被拒绝


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

    class Config:
        use_enum_values = True


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
