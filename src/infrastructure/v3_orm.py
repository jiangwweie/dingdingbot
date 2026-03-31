"""
v3.0 SQLAlchemy ORM 模型

实现 Phase 1 核心数据模型的 ORM 映射：
- Account: 资产账户
- Signal: 策略信号
- Order: 交易订单
- Position: 核心仓位

技术栈:
- SQLAlchemy 2.0 async
- Decimal 精度保护（String 存储）
- 异步数据库操作

契约表参考：docs/designs/v3-phase1-models-contract.md
"""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    ForeignKey,
    Index,
    CheckConstraint,
    event,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

from src.domain.models import Direction, OrderStatus, OrderType, OrderRole


# ============================================================
# SQLAlchemy 2.0 风格基类
# ============================================================

class Base(DeclarativeBase):
    """
    SQLAlchemy 声明式基类

    所有 ORM 模型继承此类以注册到统一的 metadata。
    用于 Alembic 迁移脚本自动生成。
    """
    pass


# ============================================================
# 自定义类型：Decimal <-> String 序列化
# ============================================================

from sqlalchemy.types import TypeDecorator


class DecimalString(TypeDecorator):
    """
    Decimal 类型自定义映射：使用 VARCHAR 存储 Decimal 字符串表示

    理由:
    - 避免 FLOAT 精度丢失
    - SQLite 不原生支持 DECIMAL 类型
    - 字符串存储可精确反序列化为 Decimal

    使用场景:
    - 所有金额字段 (price, balance, qty 等)
    - 所有比率字段 (pnl_ratio, score 等除外，使用 REAL)
    """

    impl = String

    cache_ok = True

    def process_bind_param(self, value: Optional[Decimal], dialect) -> Optional[str]:
        """Python -> Database: Decimal -> String"""
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value: Optional[str], dialect) -> Optional[Decimal]:
        """Database -> Python: String -> Decimal"""
        if value is None:
            return None
        return Decimal(value)


# 类型别名：简化字段定义
DecimalField = DecimalString


# ============================================================
# 枚举类型映射
# ============================================================
# 使用 String Column + CheckConstraint 实现枚举约束
# 优点：与 Pydantic 枚举无缝对齐，支持大小写转换

# Direction 枚举约束
DIRECTION_CHECK = CheckConstraint(
    "direction IN ('LONG', 'SHORT')",
    name="check_direction"
)

# OrderStatus 枚举约束
ORDER_STATUS_CHECK = CheckConstraint(
    "status IN ('PENDING', 'OPEN', 'PARTIALLY_FILLED', 'FILLED', 'CANCELED', 'REJECTED', 'EXPIRED')",
    name="check_order_status"
)

# OrderType 枚举约束
ORDER_TYPE_CHECK = CheckConstraint(
    "order_type IN ('MARKET', 'LIMIT', 'STOP_MARKET', 'STOP_LIMIT', 'TRAILING_STOP')",
    name="check_order_type"
)

# OrderRole 枚举约束
ORDER_ROLE_CHECK = CheckConstraint(
    "order_role IN ('ENTRY', 'TP1', 'TP2', 'TP3', 'TP4', 'TP5', 'SL')",
    name="check_order_role"
)


# ============================================================
# Account ORM 模型
# ============================================================

class AccountORM(Base):
    """
    资产账户 ORM 模型

    管理基础本金（可用现金），对应领域模型 Account。

    字段映射:
    - account_id: 账户标识（主键）
    - total_balance: 钱包总余额（String 存储 Decimal）
    - frozen_margin: 冻结保证金（String 存储 Decimal）
    - created_at: 创建时间戳
    - updated_at: 更新时间戳

    计算属性:
    - available_balance = total_balance - frozen_margin

    使用示例:
        >>> async with db.begin():
        ...     account = AccountORM(
        ...         account_id="default_wallet",
        ...         total_balance=Decimal('10000.00'),
        ...         frozen_margin=Decimal('2000.00')
        ...     )
        ...     db.add(account)
        ...     await db.flush()
        ...
        ...     # 可用余额
        ...     available = account.total_balance - account.frozen_margin
    """
    __tablename__ = "accounts"

    # 主键
    account_id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default="default_wallet"
    )

    # 余额字段（Decimal 精度）
    total_balance: Mapped[Decimal] = mapped_column(
        DecimalField(32),
        nullable=False,
        default=Decimal('0')
    )

    frozen_margin: Mapped[Decimal] = mapped_column(
        DecimalField(32),
        nullable=False,
        default=Decimal('0')
    )

    # 审计字段
    created_at: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000)
    )

    updated_at: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000)
    )

    # 表约束
    # 注意：SQLite 对 TEXT 字段使用字典序比较，因此不使用 CHECK 约束进行数值比较
    # 数值验证应在应用层（Pydantic）进行
    __table_args__ = ()

    def __repr__(self) -> str:
        return (
            f"<AccountORM(account_id={self.account_id!r}, "
            f"total_balance={self.total_balance}, "
            f"available={self.available_balance})>"
        )

    @property
    def available_balance(self) -> Decimal:
        """计算属性：可用余额"""
        return self.total_balance - self.frozen_margin


# ============================================================
# Signal ORM 模型
# ============================================================

class SignalORM(Base):
    """
    策略信号 ORM 模型

    意图层：记录策略在某根 K 线发现的机会。
    与领域模型 Signal 对齐。

    字段映射:
    - id: 信号 ID（主键）
    - strategy_id: 触发策略名称
    - symbol: 交易对
    - direction: 方向（LONG/SHORT）
    - timestamp: 信号生成时间戳
    - expected_entry: 预期入场价
    - expected_sl: 预期初始止损
    - pattern_score: 形态评分 (0-1)
    - is_active: 信号是否活跃

    关系:
    - orders: 一对多，关联 OrderORM
    - positions: 一对多，关联 PositionORM

    使用示例:
        >>> signal = SignalORM(
        ...     id="sig_123",
        ...     strategy_id="pinbar",
        ...     symbol="BTC/USDT:USDT",
        ...     direction="LONG",
        ...     timestamp=1711785600000,
        ...     expected_entry=Decimal('70000'),
        ...     expected_sl=Decimal('69000'),
        ...     pattern_score=0.85
        ... )
    """
    __tablename__ = "signals"

    # 主键
    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    # 策略标识
    strategy_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    # 交易对
    symbol: Mapped[str] = mapped_column(
        String(32),
        nullable=False
    )

    # 方向
    direction: Mapped[str] = mapped_column(
        String(16),
        nullable=False
    )

    # 时间戳
    timestamp: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    # 策略意图（价格字段使用 Decimal 精度）
    expected_entry: Mapped[Decimal] = mapped_column(
        DecimalField(32),
        nullable=False
    )

    expected_sl: Mapped[Decimal] = mapped_column(
        DecimalField(32),
        nullable=False
    )

    # 形态评分 (0-1，使用 Float 存储浮点数)
    pattern_score: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )

    # 生命周期
    is_active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False
    )

    # 审计字段
    created_at: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000)
    )

    updated_at: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000)
    )

    # 表约束
    # 注意：SQLite 对 TEXT 字段使用字典序比较，因此不使用 CHECK 约束进行数值比较
    # 数值验证应在应用层（Pydantic）进行
    # 保留枚举 CHECK 约束（字符串字面量比较）
    __table_args__ = (
        DIRECTION_CHECK,
        Index("idx_signals_symbol", "symbol"),
        Index("idx_signals_timestamp", "timestamp"),
        Index("idx_signals_strategy", "strategy_id"),
        Index("idx_signals_is_active", "is_active"),
    )

    # 关系
    if TYPE_CHECKING:
        orders: Mapped[list[OrderORM]] = relationship(
            back_populates="signal",
            cascade="all, delete-orphan"
        )
        positions: Mapped[list[PositionORM]] = relationship(
            back_populates="signal",
            cascade="all, delete-orphan"
        )

    def __repr__(self) -> str:
        return (
            f"<SignalORM(id={self.id!r}, strategy={self.strategy_id!r}, "
            f"symbol={self.symbol!r}, direction={self.direction!r})>"
        )


# ============================================================
# Order ORM 模型
# ============================================================

class OrderORM(Base):
    """
    交易订单 ORM 模型

    执行层：与交易所真实交互的物理凭证。
    与领域模型 Order 对齐。

    字段映射:
    - id: 订单 ID（主键）
    - signal_id: 外键 -> SignalORM.id
    - exchange_order_id: 交易所订单号（可选）
    - symbol: 交易对
    - direction: 方向
    - order_type: 订单类型
    - order_role: 订单角色
    - price: 限价单价格
    - trigger_price: 条件单触发价
    - requested_qty: 委托数量
    - filled_qty: 成交数量
    - average_exec_price: 成交均价
    - status: 订单状态
    - created_at / updated_at: 时间戳
    - exit_reason: 出局原因

    关系:
    - signal: 多对一，关联 SignalORM

    使用示例:
        >>> order = OrderORM(
        ...     id="ord_456",
        ...     signal_id="sig_123",
        ...     symbol="BTC/USDT:USDT",
        ...     direction="LONG",
        ...     order_type="MARKET",
        ...     order_role="ENTRY",
        ...     requested_qty=Decimal('0.1'),
        ...     status="PENDING"
        ... )
    """
    __tablename__ = "orders"

    # 主键
    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    # 外键：所属信号
    signal_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("signals.id", ondelete="CASCADE"),
        nullable=False
    )

    # 交易所订单号
    exchange_order_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True
    )

    # 交易对
    symbol: Mapped[str] = mapped_column(
        String(32),
        nullable=False
    )

    # 方向
    direction: Mapped[str] = mapped_column(
        String(16),
        nullable=False
    )

    # 订单类型
    order_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False
    )

    # 订单角色
    order_role: Mapped[str] = mapped_column(
        String(16),
        nullable=False
    )

    # 价格字段（Decimal 精度）
    price: Mapped[Optional[Decimal]] = mapped_column(
        DecimalField(32),
        nullable=True
    )

    trigger_price: Mapped[Optional[Decimal]] = mapped_column(
        DecimalField(32),
        nullable=True
    )

    # 数量字段
    requested_qty: Mapped[Decimal] = mapped_column(
        DecimalField(32),
        nullable=False
    )

    filled_qty: Mapped[Decimal] = mapped_column(
        DecimalField(32),
        nullable=False,
        default=Decimal('0')
    )

    average_exec_price: Mapped[Optional[Decimal]] = mapped_column(
        DecimalField(32),
        nullable=True
    )

    # 订单状态
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="PENDING"
    )

    # 审计字段
    created_at: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000)
    )

    updated_at: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000)
    )

    # 平仓附加属性
    exit_reason: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True
    )

    # 表约束
    __table_args__ = (
        DIRECTION_CHECK,
        ORDER_STATUS_CHECK,
        ORDER_TYPE_CHECK,
        ORDER_ROLE_CHECK,
        CheckConstraint(
            "requested_qty > 0",
            name="check_requested_qty_positive"
        ),
        CheckConstraint(
            "filled_qty >= 0",
            name="check_filled_qty_non_negative"
        ),
        CheckConstraint(
            "filled_qty <= requested_qty",
            name="check_filled_qty_not_exceed_requested"
        ),
        Index("idx_orders_signal_id", "signal_id"),
        Index("idx_orders_status", "status"),
        Index("idx_orders_symbol", "symbol"),
        Index("idx_orders_exchange_id", "exchange_order_id"),
    )

    # 关系
    if TYPE_CHECKING:
        signal: Mapped[SignalORM] = relationship(
            back_populates="orders"
        )

    def __repr__(self) -> str:
        return (
            f"<OrderORM(id={self.id!r}, signal={self.signal_id!r}, "
            f"symbol={self.symbol!r}, status={self.status!r}, "
            f"filled={self.filled_qty}/{self.requested_qty})>"
        )


# ============================================================
# Position ORM 模型
# ============================================================

class PositionORM(Base):
    """
    核心仓位 ORM 模型

    资产层：PMS 系统的绝对核心，代表当前持有敞口。
    与领域模型 Position 对齐。

    字段映射:
    - id: 仓位 ID（主键）
    - signal_id: 外键 -> SignalORM.id
    - symbol: 交易对
    - direction: 方向
    - entry_price: 开仓均价（固定不变）
    - current_qty: 当前持仓数量
    - watermark_price: 动态风控水位线（LONG: 入场后最高价 / SHORT: 入场后最低价）
    - realized_pnl: 已实现盈亏
    - total_fees_paid: 累计手续费
    - is_closed: 是否已平仓

    关系:
    - signal: 多对一，关联 SignalORM

    业界标准:
    - 被平仓时 entry_price 死咬不变
    - current_qty 归零时 is_closed = True

    使用示例:
        >>> position = PositionORM(
        ...     id="pos_789",
        ...     signal_id="sig_123",
        ...     symbol="BTC/USDT:USDT",
        ...     direction="LONG",
        ...     entry_price=Decimal('70000'),
        ...     current_qty=Decimal('0.1'),
        ...     watermark_price=Decimal('70000')
        ... )
    """
    __tablename__ = "positions"

    # 主键
    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    # 外键：所属信号
    signal_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("signals.id", ondelete="CASCADE"),
        nullable=False
    )

    # 交易对
    symbol: Mapped[str] = mapped_column(
        String(32),
        nullable=False
    )

    # 方向
    direction: Mapped[str] = mapped_column(
        String(16),
        nullable=False
    )

    # 核心资产状态（Decimal 精度）
    entry_price: Mapped[Decimal] = mapped_column(
        DecimalField(32),
        nullable=False
    )

    current_qty: Mapped[Decimal] = mapped_column(
        DecimalField(32),
        nullable=False
    )

    # 动态风控水位线
    # LONG: 追踪入场后的最高价 (High Watermark)
    # SHORT: 追踪入场后的最低价 (Low Watermark)
    watermark_price: Mapped[Decimal] = mapped_column(
        DecimalField(32),
        nullable=True  # 允许为空，初始值为 None
    )

    # 业绩追踪
    realized_pnl: Mapped[Decimal] = mapped_column(
        DecimalField(32),
        nullable=False,
        default=Decimal('0')
    )

    total_fees_paid: Mapped[Decimal] = mapped_column(
        DecimalField(32),
        nullable=False,
        default=Decimal('0')
    )

    # 生命周期
    is_closed: Mapped[bool] = mapped_column(
        default=False,
        nullable=False
    )

    # 审计字段
    created_at: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000)
    )

    updated_at: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000)
    )

    # 表约束
    __table_args__ = (
        DIRECTION_CHECK,
        CheckConstraint(
            "entry_price > 0",
            name="check_entry_price_positive"
        ),
        CheckConstraint(
            "current_qty >= 0",
            name="check_current_qty_non_negative"
        ),
        Index("idx_positions_signal_id", "signal_id"),
        Index("idx_positions_is_closed", "is_closed"),
        Index("idx_positions_symbol", "symbol"),
    )

    # 关系
    if TYPE_CHECKING:
        signal: Mapped[SignalORM] = relationship(
            back_populates="positions"
        )

    def __repr__(self) -> str:
        return (
            f"<PositionORM(id={self.id!r}, symbol={self.symbol!r}, "
            f"direction={self.direction!r}, qty={self.current_qty}, "
            f"entry={self.entry_price}, closed={self.is_closed})>"
        )


# ============================================================
# 辅助函数：与领域模型互转
# ============================================================

def signal_orm_to_domain(orm: SignalORM) -> "src.domain.models.Signal":
    """
    SignalORM -> Signal (领域模型)

    用于从数据库读取后转换为领域层使用的 Pydantic 模型。
    """
    from src.domain.models import Signal

    return Signal(
        id=orm.id,
        strategy_id=orm.strategy_id,
        symbol=orm.symbol,
        direction=Direction(orm.direction),
        timestamp=orm.timestamp,
        expected_entry=orm.expected_entry,
        expected_sl=orm.expected_sl,
        pattern_score=orm.pattern_score,
        is_active=orm.is_active,
    )


def signal_domain_to_orm(domain: "src.domain.models.Signal") -> SignalORM:
    """
    Signal (领域模型) -> SignalORM

    用于将领域层模型持久化到数据库。
    """
    return SignalORM(
        id=domain.id,
        strategy_id=domain.strategy_id,
        symbol=domain.symbol,
        direction=domain.direction.value,
        timestamp=domain.timestamp,
        expected_entry=domain.expected_entry,
        expected_sl=domain.expected_sl,
        pattern_score=domain.pattern_score,
        is_active=domain.is_active,
    )


def order_orm_to_domain(orm: OrderORM) -> "src.domain.models.Order":
    """
    OrderORM -> Order (领域模型)
    """
    from src.domain.models import Order

    return Order(
        id=orm.id,
        signal_id=orm.signal_id,
        exchange_order_id=orm.exchange_order_id,
        symbol=orm.symbol,
        direction=Direction(orm.direction),
        order_type=OrderType(orm.order_type),
        order_role=OrderRole(orm.order_role),
        price=orm.price,
        trigger_price=orm.trigger_price,
        requested_qty=orm.requested_qty,
        filled_qty=orm.filled_qty,
        average_exec_price=orm.average_exec_price,
        status=OrderStatus(orm.status),
        created_at=orm.created_at,
        updated_at=orm.updated_at,
        exit_reason=orm.exit_reason,
    )


def order_domain_to_orm(domain: "src.domain.models.Order") -> OrderORM:
    """
    Order (领域模型) -> OrderORM
    """
    return OrderORM(
        id=domain.id,
        signal_id=domain.signal_id,
        exchange_order_id=domain.exchange_order_id,
        symbol=domain.symbol,
        direction=domain.direction.value,
        order_type=domain.order_type.value,
        order_role=domain.order_role.value,
        price=domain.price,
        trigger_price=domain.trigger_price,
        requested_qty=domain.requested_qty,
        filled_qty=domain.filled_qty,
        average_exec_price=domain.average_exec_price,
        status=domain.status.value,
        created_at=domain.created_at,
        updated_at=domain.updated_at,
        exit_reason=domain.exit_reason,
    )


def position_orm_to_domain(orm: PositionORM) -> "src.domain.models.Position":
    """
    PositionORM -> Position (领域模型)
    """
    from src.domain.models import Position

    return Position(
        id=orm.id,
        signal_id=orm.signal_id,
        symbol=orm.symbol,
        direction=Direction(orm.direction),
        entry_price=orm.entry_price,
        current_qty=orm.current_qty,
        watermark_price=orm.watermark_price,
        realized_pnl=orm.realized_pnl,
        total_fees_paid=orm.total_fees_paid,
        is_closed=orm.is_closed,
    )


def position_domain_to_orm(domain: "src.domain.models.Position") -> PositionORM:
    """
    Position (领域模型) -> PositionORM

    注意：watermark_price 字段语义
    - 领域模型：None 表示"尚未更新"，有值表示"已更新"
    - ORM 模型：nullable=True，允许 NULL 存储
    - 转换策略：保留 None 语义，直接传递 (不填充 entry_price)
    """
    return PositionORM(
        id=domain.id,
        signal_id=domain.signal_id,
        symbol=domain.symbol,
        direction=domain.direction.value,
        entry_price=domain.entry_price,
        current_qty=domain.current_qty,
        watermark_price=domain.watermark_price,  # 直接传递，保留 None 语义
        realized_pnl=domain.realized_pnl,
        total_fees_paid=domain.total_fees_paid,
        is_closed=domain.is_closed,
    )


def account_orm_to_domain(orm: AccountORM) -> "src.domain.models.Account":
    """
    AccountORM -> Account (领域模型)
    """
    from src.domain.models import Account

    return Account(
        account_id=orm.account_id,
        total_balance=orm.total_balance,
        frozen_margin=orm.frozen_margin,
    )


def account_domain_to_orm(domain: "src.domain.models.Account") -> AccountORM:
    """
    Account (领域模型) -> AccountORM
    """
    return AccountORM(
        account_id=domain.account_id,
        total_balance=domain.total_balance,
        frozen_margin=domain.frozen_margin,
    )


# 模块级文档：使用示例
"""
============================================================
v3 ORM 使用示例
============================================================

# 1. 初始化数据库
    from src.infrastructure.database import init_db, get_engine
    from src.infrastructure.v3_orm import Base

    async def setup():
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

# 2. CRUD 示例（使用 AsyncSession）
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select

    async with AsyncSession() as db:
        # Create
        signal = SignalORM(
            id="sig_001",
            strategy_id="pinbar",
            symbol="BTC/USDT:USDT",
            direction="LONG",
            timestamp=1711785600000,
            expected_entry=Decimal('70000'),
            expected_sl=Decimal('69000'),
            pattern_score=0.85
        )
        db.add(signal)
        await db.commit()

        # Read
        result = await db.execute(
            select(SignalORM).where(SignalORM.id == "sig_001")
        )
        signal = result.scalar_one()

        # Update
        signal.is_active = False
        await db.commit()

        # Delete
        await db.delete(signal)
        await db.commit()

# 3. 关联查询（JOIN）
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(SignalORM)
        .options(selectinload(SignalORM.orders))
        .where(SignalORM.id == "sig_001")
    )
    signal = result.scalar_one()
    for order in signal.orders:
        print(order.status)

# 4. 类型转换（ORM <-> Domain）
    from src.infrastructure.v3_orm import signal_orm_to_domain, signal_domain_to_orm

    # ORM -> Domain
    signal_domain = signal_orm_to_domain(signal_orm)

    # Domain -> ORM
    signal_orm = signal_domain_to_orm(signal_domain)
"""
