"""
PostgreSQL Core Models - 核心 PG ORM 模型

双轨迁移阶段仅覆盖核心表：
- orders
- execution_intents
- positions

注意：
- 这是新增实现，不替换现有 SQLite 表结构
- 不依赖 signals/config/backtest 等旧表
- 在迁移期内，PG 只承接核心执行链真源
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class PGCoreBase(DeclarativeBase):
    """PG 核心表专用 Declarative Base。"""


class DecimalString(TypeDecorator):
    """Decimal <-> String 映射，避免金融数值精度损失。"""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Optional[Decimal], dialect) -> Optional[str]:
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value: Optional[str], dialect) -> Optional[Decimal]:
        if value is None:
            return None
        return Decimal(value)


DecimalField = DecimalString


class PGOrderORM(PGCoreBase):
    """PG 版核心订单表。"""

    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    signal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange_order_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    order_type: Mapped[str] = mapped_column(String(32), nullable=False)
    order_role: Mapped[str] = mapped_column(String(16), nullable=False)
    price: Mapped[Optional[Decimal]] = mapped_column(DecimalField(64), nullable=True)
    trigger_price: Mapped[Optional[Decimal]] = mapped_column(DecimalField(64), nullable=True)
    requested_qty: Mapped[Decimal] = mapped_column(DecimalField(64), nullable=False)
    filled_qty: Mapped[Decimal] = mapped_column(DecimalField(64), nullable=False, default=Decimal("0"))
    average_exec_price: Mapped[Optional[Decimal]] = mapped_column(DecimalField(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    reduce_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    parent_order_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    oco_group_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    exit_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    filled_at: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000),
    )
    updated_at: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000),
    )

    __table_args__ = (
        CheckConstraint("requested_qty > 0", name="pg_check_requested_qty_positive"),
        CheckConstraint("filled_qty >= 0", name="pg_check_filled_qty_non_negative"),
        Index("pg_idx_orders_signal_id", "signal_id"),
        Index("pg_idx_orders_exchange_order_id", "exchange_order_id"),
        Index("pg_idx_orders_status", "status"),
        Index("pg_idx_orders_parent_order_id", "parent_order_id"),
    )


class PGExecutionIntentORM(PGCoreBase):
    """PG 版执行意图表。"""

    __tablename__ = "execution_intents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    signal_json: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    order_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    exchange_order_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    blocked_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    blocked_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    failed_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000),
    )
    updated_at: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000),
    )

    __table_args__ = (
        Index("pg_idx_execution_intents_status", "status"),
        Index("pg_idx_execution_intents_order_id", "order_id"),
        Index("pg_idx_execution_intents_exchange_order_id", "exchange_order_id"),
    )


class PGPositionORM(PGCoreBase):
    """PG 版核心仓位表。"""

    __tablename__ = "positions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    signal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(DecimalField(64), nullable=False)
    current_qty: Mapped[Decimal] = mapped_column(DecimalField(64), nullable=False)
    watermark_price: Mapped[Optional[Decimal]] = mapped_column(DecimalField(64), nullable=True)
    realized_pnl: Mapped[Decimal] = mapped_column(DecimalField(64), nullable=False, default=Decimal("0"))
    total_fees_paid: Mapped[Decimal] = mapped_column(DecimalField(64), nullable=False, default=Decimal("0"))
    total_funding_paid: Mapped[Decimal] = mapped_column(DecimalField(64), nullable=False, default=Decimal("0"))
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000),
    )
    updated_at: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000),
    )

    __table_args__ = (
        CheckConstraint("current_qty >= 0", name="pg_check_position_qty_non_negative"),
        Index("pg_idx_positions_signal_id", "signal_id"),
        Index("pg_idx_positions_symbol", "symbol"),
        Index("pg_idx_positions_is_closed", "is_closed"),
    )
