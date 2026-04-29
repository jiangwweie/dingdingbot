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
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(36, 18), nullable=True)
    trigger_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(36, 18), nullable=True)
    requested_qty: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    filled_qty: Mapped[Decimal] = mapped_column(
        Numeric(36, 18),
        nullable=False,
        default=Decimal("0"),
    )
    average_exec_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(36, 18), nullable=True)
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
    quantity: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    entry_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(36, 18), nullable=True)
    mark_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(36, 18), nullable=True)
    leverage: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    unrealized_pnl: Mapped[Optional[Decimal]] = mapped_column(Numeric(36, 18), nullable=True)
    realized_pnl: Mapped[Optional[Decimal]] = mapped_column(Numeric(36, 18), nullable=True)
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
Index(
    "uq_positions_active_symbol_direction",
    PGPositionORM.symbol,
    PGPositionORM.direction,
    unique=True,
    postgresql_where=PGPositionORM.is_closed.is_(False),
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
    entry_price: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    stop_loss: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    position_size: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    leverage: Mapped[int] = mapped_column(Integer, nullable=False)
    tags_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    risk_info: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    take_profit_1: Mapped[Optional[Decimal]] = mapped_column(Numeric(36, 18), nullable=True)
    closed_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pnl_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(36, 18), nullable=True)
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
    price_level: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    filled_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pnl_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(36, 18), nullable=True)

    __table_args__ = (
        CheckConstraint("position_ratio >= 0", name="ck_signal_take_profits_position_ratio_non_negative"),
        CheckConstraint("risk_reward >= 0", name="ck_signal_take_profits_risk_reward_non_negative"),
        CheckConstraint("price_level > 0", name="ck_signal_take_profits_price_level_positive"),
        Index("idx_signal_take_profits_signal_id", "signal_id"),
        Index("idx_signal_take_profits_status", "status"),
    )


class PGSignalAttemptORM(PGCoreBase):
    """PG 版 signal attempts 可观测表。"""

    __tablename__ = "signal_attempts"

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    strategy_name: Mapped[str] = mapped_column(String(64), nullable=False)
    direction: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    pattern_score: Mapped[Optional[float]] = mapped_column(Numeric(12, 8), nullable=True)
    final_result: Mapped[str] = mapped_column(String(32), nullable=False)
    filter_stage: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    filter_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False)
    kline_timestamp: Mapped[Optional[int]] = mapped_column(BIGINT, nullable=True)
    evaluation_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trace_tree: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    config_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("idx_signal_attempts_symbol", "symbol"),
        Index("idx_signal_attempts_created_at", "created_at"),
        Index("idx_signal_attempts_final_result", "final_result"),
        Index("idx_signal_attempts_symbol_timeframe", "symbol", "timeframe"),
    )


class PGRuntimeProfileORM(PGCoreBase):
    """PG 版 runtime profiles 表。"""

    __tablename__ = "runtime_profiles"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    profile_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_readonly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[int] = mapped_column(BIGINT, nullable=False)
    updated_at: Mapped[int] = mapped_column(BIGINT, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        Index("idx_runtime_profiles_active", "is_active"),
        Index("idx_runtime_profiles_updated_at", "updated_at"),
    )


class PGConfigEntryORM(PGCoreBase):
    """PG 版 config_entries_v2 KV 表。"""

    __tablename__ = "config_entries_v2"

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    config_key: Mapped[str] = mapped_column(String(256), nullable=False)
    config_value: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="v1.0.0")
    updated_at: Mapped[int] = mapped_column(BIGINT, nullable=False)
    profile_name: Mapped[str] = mapped_column(String(128), nullable=False, default="default")

    __table_args__ = (
        CheckConstraint(
            "value_type IN ('string', 'number', 'boolean', 'json', 'decimal')",
            name="ck_config_entries_v2_value_type",
        ),
        Index("uq_config_entries_v2_profile_key", "profile_name", "config_key", unique=True),
        Index("idx_config_entries_v2_updated_at", "updated_at"),
        Index("idx_config_entries_v2_profile", "profile_name"),
    )


class PGConfigProfileORM(PGCoreBase):
    """PG 版旧配置域 profile 表。"""

    __tablename__ = "config_profiles"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    created_from: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        Index("idx_config_profiles_active", "is_active"),
        Index("idx_config_profiles_created_at", "created_at"),
    )


class PGConfigSnapshotORM(PGCoreBase):
    """PG 版 config snapshots 表。"""

    __tablename__ = "config_snapshot_versions"

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    version: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("idx_config_snapshots_version", "version"),
        Index("idx_config_snapshots_active", "is_active"),
        Index("idx_config_snapshots_created_at", "created_at"),
    )


class PGConfigSnapshotExtendedORM(PGCoreBase):
    """PG 版旧配置域完整快照表。"""

    __tablename__ = "config_snapshots"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    snapshot_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    is_auto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("idx_snapshots_created", "created_at"),
    )


class PGConfigSnapshotEntryORM(PGCoreBase):
    """PG 版 config_entries 表，供旧配置快照/策略参数 API 使用。"""

    __tablename__ = "config_entries"

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    key: Mapped[str] = mapped_column(String(256), nullable=False)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False, default="user")

    __table_args__ = (
        Index("uq_config_entries_category_key", "category", "key", unique=True),
        Index("idx_config_entries_category", "category"),
        Index("idx_config_entries_key", "key"),
    )


class PGResearchJobORM(PGCoreBase):
    """PG 版 Research Control Plane job 表。"""

    __tablename__ = "research_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    spec_ref: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    run_result_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    finished_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False, default="local")
    error_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    progress_pct: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    spec_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        CheckConstraint("kind IN ('backtest')", name="ck_research_jobs_kind"),
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELED')",
            name="ck_research_jobs_status",
        ),
        Index("idx_research_jobs_status_created", "status", "created_at"),
    )


class PGResearchRunResultORM(PGCoreBase):
    """PG 版 Research run result 表。"""

    __tablename__ = "research_run_results"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("research_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    spec_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    summary_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)
    artifact_index: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_profile: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    generated_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint("kind IN ('backtest')", name="ck_research_run_results_kind"),
        Index("idx_research_results_job", "job_id"),
        Index("idx_research_results_generated_at", "generated_at"),
    )


class PGCandidateRecordORM(PGCoreBase):
    """PG 版 candidate records 表。"""

    __tablename__ = "candidate_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_result_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("research_run_results.id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    review_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    applicable_market: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    risks: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    recommendation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'REVIEWED', 'REJECTED', 'RECOMMENDED')",
            name="ck_candidate_records_status",
        ),
        Index("idx_candidate_records_status_updated", "status", "updated_at"),
    )


class PGKlineORM(PGCoreBase):
    """PG 版历史 K 线表。"""

    __tablename__ = "klines"

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    timestamp: Mapped[int] = mapped_column(BIGINT, nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)

    __table_args__ = (
        CheckConstraint("open > 0 AND high > 0 AND low > 0 AND close > 0", name="ck_klines_prices_positive"),
        CheckConstraint("high >= low", name="ck_klines_high_gte_low"),
        CheckConstraint("volume >= 0", name="ck_klines_volume_non_negative"),
        Index("uq_klines_symbol_timeframe_timestamp", "symbol", "timeframe", "timestamp", unique=True),
        Index("idx_klines_symbol_tf_ts", "symbol", "timeframe", "timestamp"),
    )


class PGBacktestReportORM(PGCoreBase):
    """PG 版 backtest reports 表。"""

    __tablename__ = "backtest_reports"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy_name: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(64), nullable=False, default="1.0.0")
    strategy_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    parameters_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    backtest_start: Mapped[int] = mapped_column(BIGINT, nullable=False)
    backtest_end: Mapped[int] = mapped_column(BIGINT, nullable=False)
    created_at: Mapped[int] = mapped_column(BIGINT, nullable=False)
    initial_balance: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    final_balance: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    total_return: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    winning_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    losing_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    win_rate: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False, default=Decimal("0"))
    total_pnl: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False, default=Decimal("0"))
    total_fees_paid: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False, default=Decimal("0"))
    total_slippage_cost: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False, default=Decimal("0"))
    total_funding_cost: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False, default=Decimal("0"))
    max_drawdown: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False, default=Decimal("0"))
    sharpe_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(36, 18), nullable=True)
    positions_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    monthly_returns: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_backtest_reports_strategy_id", "strategy_id"),
        Index("idx_backtest_reports_symbol", "symbol"),
        Index("idx_backtest_reports_timeframe", "timeframe"),
        Index("idx_backtest_reports_created_at", "created_at"),
        Index("idx_backtest_reports_parameters_hash", "parameters_hash"),
    )


class PGPositionCloseEventORM(PGCoreBase):
    """PG 版 backtest position close events 表。"""

    __tablename__ = "position_close_events"

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    report_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("backtest_reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    position_id: Mapped[str] = mapped_column(String(128), nullable=False)
    order_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_category: Mapped[str] = mapped_column(String(64), nullable=False)
    close_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(36, 18), nullable=True)
    close_qty: Mapped[Optional[Decimal]] = mapped_column(Numeric(36, 18), nullable=True)
    close_pnl: Mapped[Optional[Decimal]] = mapped_column(Numeric(36, 18), nullable=True)
    close_fee: Mapped[Optional[Decimal]] = mapped_column(Numeric(36, 18), nullable=True)
    close_time: Mapped[int] = mapped_column(BIGINT, nullable=False)
    exit_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_close_events_report_id", "report_id"),
        Index("idx_close_events_position_id", "position_id"),
    )


class PGBacktestAttributionORM(PGCoreBase):
    """PG 版 backtest attribution 表。"""

    __tablename__ = "backtest_attributions"

    report_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("backtest_reports.id", ondelete="CASCADE"),
        primary_key=True,
    )
    signal_attributions: Mapped[Optional[dict | list]] = mapped_column(JSONB, nullable=True)
    aggregate_attribution: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    analysis_dimensions: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[int] = mapped_column(BIGINT, nullable=False)


class PGOrderAuditLogORM(PGCoreBase):
    """PG 版 order_audit_logs 表。"""

    __tablename__ = "order_audit_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    signal_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    old_status: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    new_status: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[Optional[str]] = mapped_column("metadata", Text, nullable=True)
    created_at: Mapped[int] = mapped_column(BIGINT, nullable=False)

    __table_args__ = (
        Index("idx_order_audit_order_id", "order_id"),
        Index("idx_order_audit_signal_id", "signal_id"),
        Index("idx_order_audit_created_at", "created_at"),
        Index("idx_order_audit_event_type", "event_type"),
    )


class PGReconciliationReportORM(PGCoreBase):
    """PG 版 reconciliation_reports 表。"""

    __tablename__ = "reconciliation_reports"

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    report_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    reconciliation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[int] = mapped_column(BIGINT, nullable=False)
    completed_at: Mapped[Optional[int]] = mapped_column(BIGINT, nullable=True)
    grace_period_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    is_consistent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    total_discrepancies: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ghost_orders_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    orphan_orders_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    position_mismatch_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actions_taken: Mapped[Optional[dict | list]] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    updated_at: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)

    __table_args__ = (
        Index("idx_reports_symbol", "symbol"),
        Index("idx_reports_type", "reconciliation_type"),
        Index("idx_reports_time", "started_at"),
        Index("idx_reports_consistency", "is_consistent"),
    )


class PGReconciliationDetailORM(PGCoreBase):
    """PG 版 reconciliation_details 表。"""

    __tablename__ = "reconciliation_details"

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    report_id: Mapped[str] = mapped_column(String(128), nullable=False)
    discrepancy_type: Mapped[str] = mapped_column(String(64), nullable=False)
    local_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    exchange_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    action_taken: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    action_result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)

    __table_args__ = (
        Index("idx_details_report", "report_id"),
        Index("idx_details_type", "discrepancy_type"),
    )


class PGOptimizationHistoryORM(PGCoreBase):
    """PG 版 optimization_history 表。"""

    __tablename__ = "optimization_history"

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(128), nullable=False)
    trial_number: Mapped[int] = mapped_column(Integer, nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False)
    objective_value: Mapped[Decimal] = mapped_column(Numeric(30, 10), nullable=False)
    total_return: Mapped[Decimal] = mapped_column(Numeric(30, 10), nullable=False, default=Decimal("0"))
    sharpe_ratio: Mapped[Decimal] = mapped_column(Numeric(30, 10), nullable=False, default=Decimal("0"))
    sortino_ratio: Mapped[Decimal] = mapped_column(Numeric(30, 10), nullable=False, default=Decimal("0"))
    max_drawdown: Mapped[Decimal] = mapped_column(Numeric(30, 10), nullable=False, default=Decimal("0"))
    win_rate: Mapped[Decimal] = mapped_column(Numeric(30, 10), nullable=False, default=Decimal("0"))
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_pnl: Mapped[Decimal] = mapped_column(Numeric(30, 10), nullable=False, default=Decimal("0"))
    total_fees: Mapped[Decimal] = mapped_column(Numeric(30, 10), nullable=False, default=Decimal("0"))
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("uq_optimization_history_job_trial", "job_id", "trial_number", unique=True),
        Index("idx_opt_history_job_id", "job_id"),
        Index("idx_opt_history_trial", "job_id", "trial_number"),
    )


# ============================================================
# 旧配置域 ORM 模型（对应 config_repositories.py）
# ============================================================


class PGStrategyConfigORM(PGCoreBase):
    """PG 版策略配置表。"""

    __tablename__ = "strategies"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    trigger_config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    filter_configs: Mapped[list] = mapped_column(JSONB, nullable=False)
    filter_logic: Mapped[str] = mapped_column(String(16), nullable=False, default="AND")
    symbols: Mapped[list] = mapped_column(JSONB, nullable=False)
    timeframes: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        Index("idx_strategies_active", "is_active"),
        Index("idx_strategies_updated", "updated_at"),
    )


class PGRiskConfigORM(PGCoreBase):
    """PG 版风控配置表。"""

    __tablename__ = "risk_configs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default="global")
    max_loss_percent: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    max_leverage: Mapped[int] = mapped_column(Integer, nullable=False)
    max_total_exposure: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4), nullable=True)
    daily_max_trades: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    daily_max_loss: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 8), nullable=True)
    max_position_hold_time: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=240)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class PGSystemConfigORM(PGCoreBase):
    """PG 版系统配置表。"""

    __tablename__ = "system_configs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default="global")
    core_symbols: Mapped[list] = mapped_column(JSONB, nullable=False)
    ema_period: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    mtf_ema_period: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    mtf_mapping: Mapped[dict] = mapped_column(JSONB, nullable=False)
    signal_cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=14400)
    queue_batch_size: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    queue_flush_interval: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False, default=Decimal("5.0"))
    queue_max_size: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    warmup_history_bars: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    atr_filter_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    atr_period: Mapped[int] = mapped_column(Integer, nullable=False, default=14)
    atr_min_ratio: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False, default=Decimal("0.5"))
    restart_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class PGSymbolConfigORM(PGCoreBase):
    """PG 版交易对配置表。"""

    __tablename__ = "symbols"

    symbol: Mapped[str] = mapped_column(String(64), primary_key=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_core: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    min_quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 8), nullable=True)
    price_precision: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    quantity_precision: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class PGNotificationConfigORM(PGCoreBase):
    """PG 版通知配置表。"""

    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    channel_type: Mapped[str] = mapped_column(String(32), nullable=False)
    webhook_url: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_on_signal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_on_order: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_on_error: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class PGConfigHistoryORM(PGCoreBase):
    """PG 版配置变更历史表。"""

    __tablename__ = "config_history"

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    old_values: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    new_values: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    old_full_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    new_full_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    changed_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    changed_at: Mapped[str] = mapped_column(Text, nullable=False)
    change_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_history_entity", "entity_type", "entity_id"),
        Index("idx_history_time", "changed_at"),
    )
