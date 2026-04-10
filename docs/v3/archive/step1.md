为了完美契合当前系统中全面使用 Pydantic v2 进行类型验证和 decimal.Decimal 保证金融精度的严格规范，我为你设计了以下核心数据模型。

这套模型既能作为内存中的数据结构支撑向量化/流式回测，也能作为未来对接 SQLite/SQLAlchemy 实体映射的蓝本。

1. 核心枚举值定义 (Vocabulary)
统一状态机的词汇表是第一步，所有状态必须与 CCXT 和真实交易所（Binance/OKX/Bybit）的底层语义对齐。

Python
from enum import Enum

class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"

class OrderStatus(str, Enum):
    PENDING = "PENDING"          # 尚未发送到交易所 (回测/等待触发阶段)
    OPEN = "OPEN"                # 挂单中 (对应 CCXT 的 'open')
    PARTIALLY_FILLED = "PARTIALLY_FILLED" # 部分成交
    FILLED = "FILLED"            # 完全成交 (对应 CCXT 的 'closed')
    CANCELED = "CANCELED"        # 已撤销
    REJECTED = "REJECTED"        # 交易所拒单

class OrderType(str, Enum):
    MARKET = "MARKET"            # 市价单 (立刻吃单)
    LIMIT = "LIMIT"              # 限价单 (排队挂单，用于 TP1)
    STOP_MARKET = "STOP_MARKET"  # 条件市价单 (用于止损)
    TRAILING_STOP = "TRAILING_STOP"# 移动止损单

class OrderRole(str, Enum):
    ENTRY = "ENTRY"              # 负责入场开仓
    TP1 = "TP1"                  # 负责第一目标位止盈
    SL = "SL"                    # 负责防守打损或移动止盈
2. Pydantic v2 核心实体模型设计
这里我们将 Signal、Order 和 Position 进行了物理隔离。

Python
from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal
from typing import Optional, List
from datetime import datetime

class FinancialModel(BaseModel):
    """基类：统一定义十进制配置，拒绝隐式浮点数转换"""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")


class Account(FinancialModel):
    """资产账户：代替原本单纯的增减逻辑"""
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
    strategy_id: str             # 触发该信号的策略名称 (如: 01pinbar-ema60)
    symbol: str
    direction: Direction
    timestamp: int               # 信号生成的 K 线时间戳
    
    # 策略的初始意图
    expected_entry: Decimal      # 预期入场价
    expected_sl: Decimal         # 预期初始止损
    pattern_score: float         # 形态评分
    
    # 信号层的生命周期 (仅表示该策略逻辑是否还在被追踪)
    is_active: bool = True 


class Order(FinancialModel):
    """
    执行层：与交易所真实交互的物理凭证
    """
    id: str
    signal_id: str               # 关联的外键：属于哪个信号触发的动作
    exchange_order_id: Optional[str] = None  # 真实 API 返回的单号 (实盘强依赖对账核心)
    
    symbol: str
    direction: Direction         # 订单买卖方向 (平多单这里就是 SHORT)
    order_type: OrderType
    order_role: OrderRole        # ENTRY, TP1, 或 SL
    
    # 价格与数量体系 (极其关键)
    price: Optional[Decimal] = None          # 限价单的挂单价格
    trigger_price: Optional[Decimal] = None  # 条件单的触发价格 (止损/移动止盈使用)
    
    requested_qty: Decimal       # 计划委托数量
    filled_qty: Decimal = Field(default=Decimal('0')) # 真实成交数量 (应对 Partial Fill)
    average_exec_price: Optional[Decimal] = None      # 真实成交均价 (用于算滑点)
    
    status: OrderStatus = OrderStatus.PENDING
    created_at: int
    updated_at: int
    
    # 平仓附加属性
    exit_reason: Optional[str] = None # 用于统计: INITIAL_SL, BREAKEVEN_STOP, TRAILING_PROFIT


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
    
    # 动态风控水位线 (供回测引擎/实盘网关判断是否要修改底层 Order)
    highest_price_since_entry: Decimal 
    
    # 业绩追踪
    realized_pnl: Decimal = Field(default=Decimal('0'), description="已实现盈亏(落袋为安)")
    total_fees_paid: Decimal = Field(default=Decimal('0'), description="累计支付的手续费")
    
    is_closed: bool = False      # current_qty 归零时标记为 True
3. 模型设计里的 3 个“避坑”细节
看完代码，你可能注意到了这几个故意为之的设计：

Order 表里区分了 price 和 trigger_price：
这是高度还原币安 API 的结果。如果是限价止盈 (TP1)，你有 price 但没有 trigger；如果是极值止损 (SL)，你有 trigger_price，但 price 可以为空（触发后按市价吃单）。

Order 表里的 requested_qty 和 filled_qty：
防患于未然。如果 TP1 要平仓 0.5 个 BTC，但盘口深度不够只成交了 0.2 个，系统状态机就不会乱，因为 Position 会根据真实返回的 filled_qty 去精准扣减体积。

Position 里存了 realized_pnl：
当 TP1 (50%) 触发时，这 50% 赚的钱会立刻被计算并累加进这个字段。这样即便最后剩下的尾仓被打回原点（推保护损），你依然能从这笔 Position 记录里看到它真实赚到了钱，方便后续的数据导出与 Python 分析。