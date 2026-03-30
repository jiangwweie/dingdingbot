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

    # v3.0 PMS mode (Phase 2)
    mode: Literal["v2_classic", "v3_pms"] = Field(
        default="v2_classic",
        description="Backtest mode: 'v2_classic' (signal-level) or 'v3_pms' (position-level with matching engine)"
    )
    initial_balance: Optional[Decimal] = Field(
        default=Decimal('10000'),
        description="Initial balance for v3_pms mode"
    )
    slippage_rate: Optional[Decimal] = Field(
        default=Decimal('0.001'),
        description="Slippage rate for v3_pms mode (default 0.1%)"
    )
    fee_rate: Optional[Decimal] = Field(
        default=Decimal('0.0004'),
        description="Fee rate for v3_pms mode (default 0.04%)"
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
    PENDING = "PENDING"           # 尚未发送到交易所
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


class ReconciliationReport(FinancialModel):
    """
    对账报告响应

    Phase 5: 实盘集成 - 对账服务
    Reference: docs/designs/phase5-contract.md Section 9
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
        description="孤儿订单列表"
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


# Forward reference rebuild
ReconciliationReport.model_rebuild()


# ============================================================
# Phase 5: Capital Protection Models
# ============================================================

class CapitalProtectionConfig(BaseModel):
    """
    资金保护配置

    Phase 5: 实盘集成 - 资金保护管理器
    Reference: docs/designs/phase5-detailed-design.md Section 3.4
    """
    enabled: bool = Field(default=True, description="是否启用资金保护")

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


class OrderCheckResult(BaseModel):
    """
    订单检查结果

    Phase 5: 资金保护检查结果
    Reference: docs/designs/phase5-contract.md Section 10
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
