"""
PostgreSQL Core Models - 核心 PG ORM 模型

双轨迁移阶段仅覆盖核心表：
- orders
- execution_intents
- positions
- execution_recovery_tasks

注意：
- 这是新增实现，不替换现有 SQLite 表结构
- 当前模型以 db_scripts 中的 PG 基线为准
- 在迁移期内，PG 只承接核心执行链真源
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BIGINT,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


class PGCoreBase(DeclarativeBase):
    """PG 核心表专用 Declarative Base。"""


class PGOrderORM(PGCoreBase):
    """PG 版核心订单表。"""

    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    signal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    order_type: Mapped[str] = mapped_column(String(32), nullable=False)
    order_role: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 8), nullable=True)
    trigger_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 8), nullable=True)
    requested_qty: Mapped[Decimal] = mapped_column(Numeric(30, 8), nullable=False)
    filled_qty: Mapped[Decimal] = mapped_column(
        Numeric(30, 8),
        nullable=False,
        default=Decimal("0"),
    )
    average_exec_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 8), nullable=True)
    reduce_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    parent_order_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("orders.id", deferrable=True, initially="DEFERRED"),
        nullable=True,
    )
    oco_group_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    exit_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    exchange_order_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    filled_at: Mapped[Optional[int]] = mapped_column(BIGINT, nullable=True)
    created_at: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    updated_at: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)

    __table_args__ = (
        CheckConstraint("direction IN ('LONG', 'SHORT')", name="ck_orders_direction"),
        CheckConstraint(
            "order_type IN ('MARKET', 'LIMIT', 'STOP_MARKET', 'STOP_LIMIT', 'TRAILING_STOP')",
            name="ck_orders_order_type",
        ),
        CheckConstraint(
            "order_role IN ('ENTRY', 'SL', 'TP1', 'TP2', 'TP3', 'TP4', 'TP5')",
            name="ck_orders_order_role",
        ),
        CheckConstraint(
            "status IN ('CREATED', 'SUBMITTED', 'PENDING', 'OPEN', "
            "'PARTIALLY_FILLED', 'FILLED', 'CANCELED', 'REJECTED', 'EXPIRED')",
            name="ck_orders_status",
        ),
        CheckConstraint("requested_qty > 0", name="ck_orders_requested_qty_positive"),
        CheckConstraint(
            "filled_qty >= 0 AND filled_qty <= requested_qty",
            name="ck_orders_filled_qty_range",
        ),
        Index("idx_orders_signal_id", "signal_id"),
        Index("idx_orders_symbol", "symbol"),
        Index("idx_orders_status", "status"),
        Index("idx_orders_parent_order_id", "parent_order_id"),
        Index("idx_orders_oco_group_id", "oco_group_id"),
        Index("idx_orders_created_at", "created_at"),
        Index("idx_orders_symbol_status", "symbol", "status"),
        Index("idx_orders_parent_role", "parent_order_id", "order_role"),
    )


class PGExecutionIntentORM(PGCoreBase):
    """PG 版执行意图表。"""

    __tablename__ = "execution_intents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    signal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    order_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    exchange_order_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    blocked_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    blocked_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    failed_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    signal_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    strategy_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    updated_at: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'blocked', 'submitted', 'failed', "
            "'protecting', 'partially_protected', 'completed')",
            name="ck_execution_intents_status",
        ),
        Index("idx_execution_intents_status", "status"),
        Index("idx_execution_intents_symbol", "symbol"),
        Index("idx_execution_intents_created_at", "created_at"),
    )


class PGPositionORM(PGCoreBase):
    """PG 版核心仓位表。"""

    __tablename__ = "positions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    signal_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(30, 8), nullable=False)
    entry_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 8), nullable=True)
    mark_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 8), nullable=True)
    leverage: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    unrealized_pnl: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 8), nullable=True)
    realized_pnl: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 8), nullable=True)
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    opened_at: Mapped[int] = mapped_column(BIGINT, nullable=False)
    closed_at: Mapped[Optional[int]] = mapped_column(BIGINT, nullable=True)
    updated_at: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    position_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint("direction IN ('LONG', 'SHORT')", name="ck_positions_direction"),
        CheckConstraint("quantity >= 0", name="ck_positions_quantity_non_negative"),
        CheckConstraint(
            "leverage IS NULL OR leverage > 0",
            name="ck_positions_leverage_positive",
        ),
        Index("idx_positions_symbol", "symbol"),
        Index("idx_positions_is_closed", "is_closed"),
        Index("idx_positions_signal_id", "signal_id"),
        Index("idx_positions_updated_at", "updated_at"),
    )


Index(
    "uq_orders_exchange_order_id",
    PGOrderORM.exchange_order_id,
    unique=True,
    postgresql_where=PGOrderORM.exchange_order_id.is_not(None),
)
Index(
    "uq_execution_intents_order_id",
    PGExecutionIntentORM.order_id,
    unique=True,
    postgresql_where=PGExecutionIntentORM.order_id.is_not(None),
)
Index(
    "uq_execution_intents_exchange_order_id",
    PGExecutionIntentORM.exchange_order_id,
    unique=True,
    postgresql_where=PGExecutionIntentORM.exchange_order_id.is_not(None),
)


class PGExecutionRecoveryTaskORM(PGCoreBase):
    """PG 版执行恢复任务表。"""

    __tablename__ = "execution_recovery_tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    intent_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("execution_intents.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    related_order_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    related_exchange_order_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    recovery_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[Optional[int]] = mapped_column(BIGINT, nullable=True)
    context_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    updated_at: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    resolved_at: Mapped[Optional[int]] = mapped_column(BIGINT, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "recovery_type IN ('replace_sl_failed')",
            name="ck_execution_recovery_tasks_recovery_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'retrying', 'resolved', 'failed')",
            name="ck_execution_recovery_tasks_status",
        ),
        CheckConstraint("retry_count >= 0", name="ck_execution_recovery_tasks_retry_count_non_negative"),
        Index("idx_execution_recovery_tasks_status_created", "status", "created_at"),
        Index("idx_execution_recovery_tasks_symbol_status", "symbol", "status"),
        Index("idx_execution_recovery_tasks_intent_id", "intent_id"),
        Index("idx_execution_recovery_tasks_next_retry_at", "next_retry_at"),
    )


class PGSignalORM(PGCoreBase):
    """PG 版 live signal 表。"""

    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    signal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(30, 8), nullable=False)
    stop_loss: Mapped[Decimal] = mapped_column(Numeric(30, 8), nullable=False)
    position_size: Mapped[Decimal] = mapped_column(Numeric(30, 8), nullable=False)
    leverage: Mapped[int] = mapped_column(Integer, nullable=False)
    tags_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    risk_info: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    take_profit_1: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 8), nullable=True)
    closed_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pnl_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 8), nullable=True)
    kline_timestamp: Mapped[Optional[int]] = mapped_column(BIGINT, nullable=True)
    strategy_name: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    score: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="live")
    pattern_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    ema_trend: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    mtf_status: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    superseded_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    opposing_signal_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    opposing_signal_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)

    __table_args__ = (
        CheckConstraint("direction IN ('LONG', 'SHORT')", name="ck_signals_direction"),
        CheckConstraint("entry_price > 0", name="ck_signals_entry_price_positive"),
        CheckConstraint("stop_loss > 0", name="ck_signals_stop_loss_positive"),
        CheckConstraint("position_size > 0", name="ck_signals_position_size_positive"),
        CheckConstraint("leverage > 0", name="ck_signals_leverage_positive"),
        Index("idx_signals_symbol", "symbol"),
        Index("idx_signals_created_at", "created_at"),
        Index("idx_signals_status", "status"),
        Index("idx_signals_symbol_timeframe_status", "symbol", "timeframe", "status"),
        Index("idx_signals_source", "source"),
    )


Index("uq_signals_signal_id", PGSignalORM.signal_id, unique=True)


class PGSignalTakeProfitORM(PGCoreBase):
    """PG 版 signal take profit 表。"""

    __tablename__ = "signal_take_profits"

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    signal_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("signals.signal_id", ondelete="CASCADE"),
        nullable=False,
    )
    tp_id: Mapped[str] = mapped_column(String(16), nullable=False)
    position_ratio: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    risk_reward: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    price_level: Mapped[Decimal] = mapped_column(Numeric(30, 8), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    filled_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pnl_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 8), nullable=True)

    __table_args__ = (
        CheckConstraint("position_ratio >= 0", name="ck_signal_take_profits_position_ratio_non_negative"),
        CheckConstraint("risk_reward >= 0", name="ck_signal_take_profits_risk_reward_non_negative"),
        CheckConstraint("price_level > 0", name="ck_signal_take_profits_price_level_positive"),
        Index("idx_signal_take_profits_signal_id", "signal_id"),
        Index("idx_signal_take_profits_status", "status"),
    )
