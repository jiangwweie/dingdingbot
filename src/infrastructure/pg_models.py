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

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BIGINT,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    JSON,
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
            "order_role IN ('ENTRY', 'EXIT', 'SL', 'TP1', 'TP2', 'TP3', 'TP4', 'TP5')",
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


class PGDailyRiskStatsAggregateORM(PGCoreBase):
    """PG daily risk stats aggregate for one UTC risk day."""

    __tablename__ = "daily_risk_stats_aggregates"

    scope_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    stats_date: Mapped[date] = mapped_column(Date, primary_key=True)
    realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(38, 18),
        nullable=False,
        default=Decimal("0"),
    )
    trade_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_event_key: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        CheckConstraint("trade_count >= 0", name="ck_daily_risk_stats_trade_count_non_negative"),
        Index("idx_daily_risk_stats_aggregates_scope_updated", "scope_key", "updated_at"),
    )


class PGDailyRiskStatsEventORM(PGCoreBase):
    """PG daily risk stats idempotency ledger."""

    __tablename__ = "daily_risk_stats_events"

    event_key: Mapped[str] = mapped_column(String(256), primary_key=True)
    scope_key: Mapped[str] = mapped_column(String(128), nullable=False)
    stats_date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="exit_projection")
    position_id: Mapped[str] = mapped_column(String(64), nullable=False)
    signal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    exit_order_id: Mapped[str] = mapped_column(String(64), nullable=False)
    delta_exit_qty: Mapped[Decimal] = mapped_column(
        Numeric(38, 18),
        nullable=False,
        default=Decimal("0"),
    )
    delta_realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(38, 18),
        nullable=False,
        default=Decimal("0"),
    )
    trade_count_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        CheckConstraint("source = 'exit_projection'", name="ck_daily_risk_stats_source"),
        CheckConstraint("trade_count_delta IN (0, 1)", name="ck_daily_risk_stats_trade_count_delta"),
        CheckConstraint("delta_exit_qty >= 0", name="ck_daily_risk_stats_delta_exit_qty_non_negative"),
        Index("idx_daily_risk_stats_events_scope_date_created", "scope_key", "stats_date", "created_at"),
        Index("idx_daily_risk_stats_events_position_exit", "position_id", "exit_order_id"),
    )


class PGGlobalKillSwitchStateORM(PGCoreBase):
    """Single-row global kill switch state for stopping new entries."""

    __tablename__ = "global_kill_switch_state"

    state_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False, default="system")
    updated_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)

    __table_args__ = (
        CheckConstraint("state_key = 'global'", name="ck_global_kill_switch_state_key"),
        Index("idx_global_kill_switch_updated_at", "updated_at_ms"),
    )


class PGRuntimeCampaignStateORM(PGCoreBase):
    """Single-row/multi-scope campaign state for runtime entry control."""

    __tablename__ = "runtime_campaign_state"

    scope_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="observe")
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False, default="system")
    updated_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    active_strategy_contract_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    active_session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('observe', 'armed', 'paused', 'profit_protect', "
            "'loss_locked', 'hard_locked', 'closed')",
            name="ck_runtime_campaign_state_status",
        ),
        Index("idx_runtime_campaign_state_updated_at", "updated_at_ms"),
    )


class PGRuntimeCampaignStateTransitionORM(PGCoreBase):
    """Append-only campaign state transition ledger."""

    __tablename__ = "runtime_campaign_state_transitions"

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    scope_key: Mapped[str] = mapped_column(String(128), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_status: Mapped[str] = mapped_column(String(32), nullable=False)
    target_status: Mapped[str] = mapped_column(String(32), nullable=False)
    next_status: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rule_reason_code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    active_strategy_contract_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    active_session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(
        "metadata",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)

    __table_args__ = (
        CheckConstraint(
            "previous_status IN ('observe', 'armed', 'paused', 'profit_protect', "
            "'loss_locked', 'hard_locked', 'closed')",
            name="ck_runtime_campaign_state_transitions_previous_status",
        ),
        CheckConstraint(
            "target_status IN ('observe', 'armed', 'paused', 'profit_protect', "
            "'loss_locked', 'hard_locked', 'closed')",
            name="ck_runtime_campaign_state_transitions_target_status",
        ),
        CheckConstraint(
            "next_status IN ('observe', 'armed', 'paused', 'profit_protect', "
            "'loss_locked', 'hard_locked', 'closed')",
            name="ck_runtime_campaign_state_transitions_next_status",
        ),
        Index(
            "uq_runtime_campaign_state_transitions_scope_seq",
            "scope_key",
            "sequence_number",
            unique=True,
        ),
        Index(
            "idx_runtime_campaign_state_transitions_scope_time",
            "scope_key",
            "occurred_at_ms",
        ),
        Index(
            "idx_runtime_campaign_state_transitions_trigger",
            "trigger",
        ),
    )


class PGBrcCampaignORM(PGCoreBase):
    """Current Bounded Risk Campaign snapshot."""

    __tablename__ = "brc_campaigns"

    campaign_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    current_playbook_id: Mapped[str] = mapped_column(String(128), nullable=False)
    bucket_json: Mapped[dict] = mapped_column(
        "bucket",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    risk_envelope_json: Mapped[dict] = mapped_column(
        "risk_envelope",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False, default=Decimal("0"))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts_json: Mapped[list] = mapped_column(
        "attempts",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    outcome: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(
        "metadata",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False)
    updated_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False)
    finalized_at_ms: Mapped[Optional[int]] = mapped_column(BIGINT, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('observe', 'active', 'profit_protect', 'loss_locked', 'ended')",
            name="ck_brc_campaigns_status",
        ),
        CheckConstraint("realized_pnl = realized_pnl", name="ck_brc_campaigns_realized_pnl_not_nan"),
        CheckConstraint("attempt_count >= 0", name="ck_brc_campaigns_attempt_count_nonnegative"),
        Index("idx_brc_campaigns_status_updated", "status", "updated_at_ms"),
    )


class PGBrcPlaybookSwitchDecisionORM(PGCoreBase):
    """Append-only BRC playbook switch decision log."""

    __tablename__ = "brc_playbook_switch_decisions"

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    switch_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    previous_playbook_id: Mapped[str] = mapped_column(String(128), nullable=False)
    new_playbook_id: Mapped[str] = mapped_column(String(128), nullable=False)
    decision_result: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_category: Mapped[str] = mapped_column(String(128), nullable=False)
    reason_text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_refs_json: Mapped[list] = mapped_column(
        "evidence_refs",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    risk_change_direction: Mapped[str] = mapped_column(String(32), nullable=False)
    campaign_pnl_at_switch: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    attempt_count_at_switch: Mapped[int] = mapped_column(Integer, nullable=False)
    campaign_status_at_switch: Mapped[str] = mapped_column(String(32), nullable=False)
    blocked_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    inferred_fields_json: Mapped[dict] = mapped_column(
        "inferred_fields",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    decided_by: Mapped[str] = mapped_column(String(128), nullable=False, default="owner")
    switched_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False)
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)

    __table_args__ = (
        CheckConstraint(
            "decision_result IN ('allowed', 'blocked', 'review_required')",
            name="ck_brc_switch_decisions_result",
        ),
        Index(
            "uq_brc_switch_decisions_campaign_seq",
            "campaign_id",
            "sequence_number",
            unique=True,
        ),
        Index("idx_brc_switch_decisions_campaign_time", "campaign_id", "switched_at_ms"),
    )


class PGBrcCampaignEventORM(PGCoreBase):
    """Append-only BRC campaign event ledger."""

    __tablename__ = "brc_campaign_events"

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    attempt_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(
        "metadata",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    occurred_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False)
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)

    __table_args__ = (
        Index("uq_brc_campaign_events_campaign_seq", "campaign_id", "sequence_number", unique=True),
        Index("idx_brc_campaign_events_campaign_time", "campaign_id", "occurred_at_ms"),
        Index("idx_brc_campaign_events_type", "event_type"),
    )


class PGBrcMockPnlEventORM(PGCoreBase):
    """Append-only mock PnL events for BRC acceptance rehearsals."""

    __tablename__ = "brc_mock_pnl_events"

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    cumulative_pnl: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    triggered_state: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    occurred_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False)
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)

    __table_args__ = (
        CheckConstraint("source IN ('testnet_mock')", name="ck_brc_mock_pnl_events_source"),
        CheckConstraint("amount != 0", name="ck_brc_mock_pnl_events_amount_nonzero"),
        Index("uq_brc_mock_pnl_events_campaign_seq", "campaign_id", "sequence_number", unique=True),
        Index("idx_brc_mock_pnl_events_campaign_time", "campaign_id", "occurred_at_ms"),
    )


class PGBrcOperatorActionORM(PGCoreBase):
    """Persisted BRC operator plan/run ledger."""

    __tablename__ = "brc_operator_actions"

    action_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    campaign_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    plan_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    draft_action: Mapped[str] = mapped_column(String(64), nullable=False)
    http_method: Mapped[str] = mapped_column(String(16), nullable=False)
    endpoint_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    executable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmation_phrase_id: Mapped[str] = mapped_column(String(128), nullable=False)
    confirmation_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    confirmation_matched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmed_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    decision_result: Mapped[str] = mapped_column(String(32), nullable=False)
    blocked_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    plan_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False)
    result_json: Mapped[Optional[dict]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    result_summary_json: Mapped[Optional[dict]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    mutation_executed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    withdrawal_executed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    live_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    executed_at_ms: Mapped[Optional[int]] = mapped_column(BIGINT, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "draft_action IN ('read_review_packet', 'read_next_eligibility', 'read_evidence', 'unknown')",
            name="ck_brc_operator_actions_draft_action",
        ),
        CheckConstraint(
            "decision_result IN ('planned', 'executed', 'blocked')",
            name="ck_brc_operator_actions_decision_result",
        ),
        CheckConstraint("mutation_executed = false", name="ck_brc_operator_actions_no_mutation"),
        CheckConstraint("withdrawal_executed = false", name="ck_brc_operator_actions_no_withdrawal"),
        CheckConstraint("live_ready = false", name="ck_brc_operator_actions_no_live"),
        Index("idx_brc_operator_actions_campaign_time", "campaign_id", "created_at_ms"),
        Index("idx_brc_operator_actions_decision_time", "decision_result", "created_at_ms"),
    )


class PGBrcReviewDecisionORM(PGCoreBase):
    """Persisted Owner review decisions for BRC campaigns."""

    __tablename__ = "brc_review_decisions"

    review_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_action_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    decision: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_text: Mapped[str] = mapped_column(Text, nullable=False)
    next_recommended_task: Mapped[str] = mapped_column(String(256), nullable=False)
    testnet_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    real_live_authorized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    withdrawal_authorized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    strategy_execution_authorized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, default="owner")
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    metadata_json: Mapped[dict] = mapped_column(
        "metadata",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )

    __table_args__ = (
        CheckConstraint(
            "decision IN ('accepted', 'needs_followup', 'next_campaign_blocked', 'testnet_rehearsal_authorized')",
            name="ck_brc_review_decisions_decision",
        ),
        CheckConstraint("testnet_only = true", name="ck_brc_review_decisions_testnet_only"),
        CheckConstraint("real_live_authorized = false", name="ck_brc_review_decisions_no_live"),
        CheckConstraint("withdrawal_authorized = false", name="ck_brc_review_decisions_no_withdrawal"),
        CheckConstraint(
            "strategy_execution_authorized = false",
            name="ck_brc_review_decisions_no_strategy_execution",
        ),
        Index("idx_brc_review_decisions_campaign_time", "campaign_id", "created_at_ms"),
        Index("idx_brc_review_decisions_decision_time", "decision", "created_at_ms"),
    )


class PGBrcLlmIntentORM(PGCoreBase):
    """Persisted normalized BRC LLM intent ledger."""

    __tablename__ = "brc_llm_intents"

    intent_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    workflow_run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    reason_text: Mapped[str] = mapped_column(Text, nullable=False)
    provider_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_response_summary: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    decision_result: Mapped[str] = mapped_column(String(32), nullable=False)
    blocked_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    live_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        CheckConstraint(
            "action IN ('read_review_packet', 'read_next_eligibility', 'read_evidence', "
            "'request_testnet_rehearsal', 'unknown')",
            name="ck_brc_llm_intents_action",
        ),
        CheckConstraint(
            "decision_result IN ('planned', 'executed', 'blocked')",
            name="ck_brc_llm_intents_decision_result",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_brc_llm_intents_confidence"),
        CheckConstraint("live_ready = false", name="ck_brc_llm_intents_no_live"),
        Index("idx_brc_llm_intents_workflow", "workflow_run_id"),
        Index("idx_brc_llm_intents_action_time", "action", "created_at_ms"),
    )


class PGBrcWorkflowRunORM(PGCoreBase):
    """Persisted BRC LangGraph operator workflow run."""

    __tablename__ = "brc_workflow_runs"

    workflow_run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    llm_intent_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    confirmation_phrase_id: Mapped[str] = mapped_column(String(128), nullable=False)
    confirmation_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    confirmation_matched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmed_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    blocked_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_json: Mapped[Optional[dict]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    result_summary_json: Mapped[Optional[dict]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    workflow_state_json: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    langgraph_checkpoint_ref: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    mutation_executed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    withdrawal_executed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    live_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    updated_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    completed_at_ms: Mapped[Optional[int]] = mapped_column(BIGINT, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "action IN ('read_review_packet', 'read_next_eligibility', 'read_evidence', "
            "'request_testnet_rehearsal', 'unknown')",
            name="ck_brc_workflow_runs_action",
        ),
        CheckConstraint(
            "status IN ('awaiting_confirmation', 'running', 'completed', 'blocked', 'failed')",
            name="ck_brc_workflow_runs_status",
        ),
        CheckConstraint("withdrawal_executed = false", name="ck_brc_workflow_runs_no_withdrawal"),
        CheckConstraint("live_ready = false", name="ck_brc_workflow_runs_no_live"),
        Index("idx_brc_workflow_runs_status_time", "status", "created_at_ms"),
        Index("idx_brc_workflow_runs_action_time", "action", "created_at_ms"),
    )


class PGBrcOperationORM(PGCoreBase):
    """BRC Owner Console operation ledger."""

    __tablename__ = "brc_operations"

    operation_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    operation_type: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, default="ui")
    source_ref: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    input_params_json: Mapped[dict] = mapped_column(
        "input_params",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    current_preflight_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    confirmed_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    confirmed_at_ms: Mapped[Optional[int]] = mapped_column(BIGINT, nullable=True)
    executed_at_ms: Mapped[Optional[int]] = mapped_column(BIGINT, nullable=True)
    result_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    result_summary_json: Mapped[dict] = mapped_column(
        "result_summary",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    created_audit_refs_json: Mapped[list] = mapped_column(
        "created_audit_refs",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'awaiting_confirmation', 'executing', 'executed', "
            "'blocked', 'failed', 'cancelled', 'expired', 'noop')",
            name="ck_brc_operations_status",
        ),
        CheckConstraint(
            "result_status IS NULL OR result_status IN "
            "('executed', 'blocked', 'failed', 'cancelled', 'expired', 'noop')",
            name="ck_brc_operations_result_status",
        ),
        CheckConstraint("operation_type NOT IN ('withdrawal', 'transfer')", name="ck_brc_operations_no_withdrawal_transfer"),
        Index("idx_brc_operations_type_time", "operation_type", "requested_at_ms"),
        Index("idx_brc_operations_status_time", "status", "requested_at_ms"),
    )


class PGBrcPreflightSnapshotORM(PGCoreBase):
    """Persisted BRC operation preflight snapshot."""

    __tablename__ = "brc_preflight_snapshots"

    preflight_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    operation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    operation_type: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False)
    expires_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False)
    current_state_snapshot_json: Mapped[dict] = mapped_column(
        "current_state_snapshot",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    target_state_json: Mapped[dict] = mapped_column(
        "target_state",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    account_snapshot_json: Mapped[dict] = mapped_column(
        "account_snapshot",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    order_snapshot_json: Mapped[dict] = mapped_column(
        "order_snapshot",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    runtime_snapshot_json: Mapped[dict] = mapped_column(
        "runtime_snapshot",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    campaign_snapshot_json: Mapped[dict] = mapped_column(
        "campaign_snapshot",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    playbook_snapshot_json: Mapped[dict] = mapped_column(
        "playbook_snapshot",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    risk_result_json: Mapped[dict] = mapped_column(
        "risk_result",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    warnings_json: Mapped[list] = mapped_column(
        "warnings",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    blockers_json: Mapped[list] = mapped_column(
        "blockers",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    confirmation_requirement_json: Mapped[dict] = mapped_column(
        "confirmation_requirement",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    snapshot_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    before_json: Mapped[dict] = mapped_column(
        "before",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    after_json: Mapped[dict] = mapped_column(
        "after",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )

    __table_args__ = (
        CheckConstraint(
            "decision IN ('allow', 'warn', 'block', 'unavailable', 'expired')",
            name="ck_brc_preflight_snapshots_decision",
        ),
        Index("idx_brc_preflight_operation_time", "operation_id", "created_at_ms"),
        Index("idx_brc_preflight_expires", "expires_at_ms"),
        Index("uq_brc_preflight_idempotency", "operation_id", "idempotency_key", unique=True),
    )


class PGBrcExecutionResultORM(PGCoreBase):
    """Persisted unified result envelope for BRC operations."""

    __tablename__ = "brc_execution_results"

    operation_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    preflight_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    rechecked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    recheck_result_json: Mapped[dict] = mapped_column(
        "recheck_result",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    adapter_result_json: Mapped[dict] = mapped_column(
        "adapter_result",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    blocked_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    failed_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_summary_json: Mapped[dict] = mapped_column(
        "result_summary",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    audit_refs_json: Mapped[list] = mapped_column(
        "audit_refs",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    campaign_refs_json: Mapped[list] = mapped_column(
        "campaign_refs",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    review_refs_json: Mapped[list] = mapped_column(
        "review_refs",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    final_state_snapshot_json: Mapped[dict] = mapped_column(
        "final_state_snapshot",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    occurred_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('executed', 'blocked', 'failed', 'cancelled', 'expired', 'noop')",
            name="ck_brc_execution_results_status",
        ),
        Index("idx_brc_execution_results_status_time", "status", "occurred_at_ms"),
    )


class PGBrcStrategyFamilyORM(PGCoreBase):
    """PG-backed strategy family registry for BRC admission."""

    __tablename__ = "brc_strategy_families"

    strategy_family_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    family_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    owner: Mapped[str] = mapped_column(String(128), nullable=False, default="owner")
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    updated_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'intake', 'parked', 'rejected')",
            name="ck_brc_strategy_families_status",
        ),
        Index("idx_brc_strategy_families_status_time", "status", "updated_at_ms"),
    )


class PGBrcStrategyFamilyVersionORM(PGCoreBase):
    """Version-pinned strategy family facts for admission decisions."""

    __tablename__ = "brc_strategy_family_versions"

    strategy_family_version_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    strategy_family_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False, default="")
    market_structure: Mapped[str] = mapped_column(Text, nullable=False, default="")
    entry_logic_family: Mapped[str] = mapped_column(Text, nullable=False, default="")
    exit_logic_family: Mapped[str] = mapped_column(Text, nullable=False, default="")
    risk_model: Mapped[str] = mapped_column(Text, nullable=False, default="")
    supported_symbols_json: Mapped[list] = mapped_column(
        "supported_symbols",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    supported_timeframes_json: Mapped[list] = mapped_column(
        "supported_timeframes",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    required_data_json: Mapped[list] = mapped_column(
        "required_data",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    required_execution_capabilities_json: Mapped[list] = mapped_column(
        "required_execution_capabilities",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    known_failure_modes_json: Mapped[list] = mapped_column(
        "known_failure_modes",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    regime_contract_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    safeguards_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    degradation_policy_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    playbook_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    playbook_catalog_snapshot_json: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, default="owner")
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_brc_strategy_family_versions_version"),
        Index(
            "uq_brc_strategy_family_versions_family_version",
            "strategy_family_id",
            "version",
            unique=True,
        ),
        Index("idx_brc_strategy_family_versions_family", "strategy_family_id"),
    )


class PGBrcStrategyFamilyRegistryORM(PGCoreBase):
    """Metadata-only strategy family registry for read-only observation."""

    __tablename__ = "brc_strategy_family_registry"

    family_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    version_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    family_name: Mapped[str] = mapped_column(String(256), nullable=False)
    family_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False, default="")
    alpha_claim: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    carrier_validation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supported_symbols_json: Mapped[list] = mapped_column(
        "supported_symbols",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    primary_timeframe: Mapped[str] = mapped_column(String(32), nullable=False)
    context_timeframes_json: Mapped[list] = mapped_column(
        "context_timeframes",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    input_requirements_json: Mapped[list] = mapped_column(
        "input_requirements",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    allowed_signal_types_json: Mapped[list] = mapped_column(
        "allowed_signal_types",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    reason_code_taxonomy_json: Mapped[dict] = mapped_column(
        "reason_code_taxonomy",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    review_metrics_json: Mapped[list] = mapped_column(
        "review_metrics",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    known_failure_modes_json: Mapped[list] = mapped_column(
        "known_failure_modes",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    evidence_requirements_json: Mapped[list] = mapped_column(
        "evidence_requirements",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    updated_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)

    __table_args__ = (
        CheckConstraint(
            "status IN ('registered_hypothesis_only', 'active_observation_candidate', "
            "'live_readonly_observation', 'parked', 'retired')",
            name="ck_brc_strategy_family_registry_status",
        ),
        CheckConstraint(
            "family_type IN ('trend_following', 'volatility_breakout', "
            "'pullback_continuation', 'event_driven_discretionary', "
            "'funding_oi_dislocation', 'unknown')",
            name="ck_brc_strategy_family_registry_type",
        ),
        Index("idx_brc_strategy_family_registry_family", "family_id"),
        Index("idx_brc_strategy_family_registry_status", "status", "updated_at_ms"),
        Index("idx_brc_strategy_family_registry_type", "family_type"),
    )


class PGBrcStrategyFamilyPlaybookORM(PGCoreBase):
    """Metadata-only strategy family playbook registry."""

    __tablename__ = "brc_strategy_family_playbooks"

    playbook_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    family_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version_id: Mapped[str] = mapped_column(String(128), nullable=False)
    playbook_name: Mapped[str] = mapped_column(String(256), nullable=False)
    playbook_status: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol_universe_json: Mapped[list] = mapped_column(
        "symbol_universe",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    primary_timeframe: Mapped[str] = mapped_column(String(32), nullable=False)
    context_timeframes_json: Mapped[list] = mapped_column(
        "context_timeframes",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    signal_contract_version: Mapped[str] = mapped_column(String(128), nullable=False)
    allowed_signal_types_json: Mapped[list] = mapped_column(
        "allowed_signal_types",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    review_windows_json: Mapped[list] = mapped_column(
        "review_windows",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    review_metrics_json: Mapped[list] = mapped_column(
        "review_metrics",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    input_requirements_json: Mapped[list] = mapped_column(
        "input_requirements",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    evidence_requirements_json: Mapped[list] = mapped_column(
        "evidence_requirements",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    parameter_profile_json: Mapped[dict] = mapped_column(
        "parameter_profile",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    updated_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)

    __table_args__ = (
        CheckConstraint(
            "playbook_status IN ('registered_hypothesis_only', 'active_observation_candidate', "
            "'live_readonly_observation', 'parked', 'retired')",
            name="ck_brc_strategy_family_playbooks_status",
        ),
        Index("idx_brc_strategy_family_playbooks_family", "family_id", "version_id"),
        Index("idx_brc_strategy_family_playbooks_status", "playbook_status", "updated_at_ms"),
    )


class PGBrcHistoricalOhlcvDatasetORM(PGCoreBase):
    """Catalog of historical OHLCV datasets available for BRC research."""

    __tablename__ = "brc_historical_ohlcv_datasets"

    dataset_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    market: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(32), nullable=False)
    start_time_ms: Mapped[int] = mapped_column(BIGINT, nullable=False)
    end_time_ms: Mapped[int] = mapped_column(BIGINT, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    storage_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    data_quality_status: Mapped[str] = mapped_column(String(64), nullable=False)
    missing_intervals_json: Mapped[list] = mapped_column(
        "missing_intervals",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    updated_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    __table_args__ = (
        CheckConstraint("end_time_ms >= start_time_ms", name="ck_brc_historical_ohlcv_time_range"),
        CheckConstraint("row_count >= 0", name="ck_brc_historical_ohlcv_row_count"),
        CheckConstraint(
            "storage_kind IN ('pg_table', 'local_file', 'external_ref')",
            name="ck_brc_historical_ohlcv_storage_kind",
        ),
        CheckConstraint(
            "data_quality_status IN ('ok', 'degraded', 'invalid', 'unknown')",
            name="ck_brc_historical_ohlcv_quality",
        ),
        Index("idx_brc_historical_ohlcv_symbol_tf", "symbol", "timeframe"),
        Index("idx_brc_historical_ohlcv_source_market", "source", "market"),
        Index("idx_brc_historical_ohlcv_time_range", "start_time_ms", "end_time_ms"),
    )


class PGBrcHistoricalResearchSamplingRunORM(PGCoreBase):
    """Historical input-construction sampling run metadata."""

    __tablename__ = "brc_historical_research_sampling_runs"

    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    strategy_family_id: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy_family_version_id: Mapped[str] = mapped_column(String(128), nullable=False)
    playbook_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    dataset_ids_json: Mapped[list] = mapped_column(
        "dataset_ids",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    symbols_json: Mapped[list] = mapped_column(
        "symbols",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    primary_timeframe: Mapped[str] = mapped_column(String(32), nullable=False)
    context_timeframes_json: Mapped[list] = mapped_column(
        "context_timeframes",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    start_time_ms: Mapped[int] = mapped_column(BIGINT, nullable=False)
    end_time_ms: Mapped[int] = mapped_column(BIGINT, nullable=False)
    sampling_method: Mapped[str] = mapped_column(String(64), nullable=False)
    sampling_interval_bars: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    summary_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    updated_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    __table_args__ = (
        CheckConstraint("end_time_ms >= start_time_ms", name="ck_brc_hist_sampling_runs_time_range"),
        CheckConstraint("sampling_interval_bars >= 1", name="ck_brc_hist_sampling_runs_interval"),
        CheckConstraint("sample_limit >= 1", name="ck_brc_hist_sampling_runs_sample_limit"),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_brc_hist_sampling_runs_status",
        ),
        Index("idx_brc_hist_sampling_runs_strategy", "strategy_family_id", "created_at_ms"),
        Index("idx_brc_hist_sampling_runs_status", "status", "updated_at_ms"),
    )


class PGBrcHistoricalResearchSamplingPointORM(PGCoreBase):
    """Compact data-quality point result for historical input-construction sampling."""

    __tablename__ = "brc_historical_research_sampling_points"

    point_id: Mapped[str] = mapped_column(String(192), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    timestamp_ms: Mapped[int] = mapped_column(BIGINT, nullable=False)
    primary_timeframe: Mapped[str] = mapped_column(String(32), nullable=False)
    context_timeframes_json: Mapped[list] = mapped_column(
        "context_timeframes",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    point_status: Mapped[str] = mapped_column(String(32), nullable=False)
    market_snapshot_status: Mapped[str] = mapped_column(String(32), nullable=False)
    signal_input_status: Mapped[str] = mapped_column(String(32), nullable=False)
    data_quality_status: Mapped[str] = mapped_column(String(32), nullable=False)
    missing_fields_json: Mapped[list] = mapped_column(
        "missing_fields",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    stale_fields_json: Mapped[list] = mapped_column(
        "stale_fields",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    warnings_json: Mapped[list] = mapped_column(
        "warnings",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    atr_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    candle_context_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    input_contract_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)

    __table_args__ = (
        CheckConstraint(
            "point_status IN ('ok', 'degraded', 'invalid')",
            name="ck_brc_hist_sampling_points_status",
        ),
        CheckConstraint(
            "market_snapshot_status IN ('ok', 'degraded', 'invalid')",
            name="ck_brc_hist_sampling_points_market_status",
        ),
        CheckConstraint(
            "signal_input_status IN ('ok', 'degraded', 'invalid')",
            name="ck_brc_hist_sampling_points_input_status",
        ),
        CheckConstraint(
            "data_quality_status IN ('ok', 'degraded', 'invalid')",
            name="ck_brc_hist_sampling_points_quality_status",
        ),
        Index("idx_brc_hist_sampling_points_run", "run_id", "timestamp_ms"),
        Index("idx_brc_hist_sampling_points_symbol_time", "symbol", "timestamp_ms"),
        Index("idx_brc_hist_sampling_points_status", "point_status"),
    )


class PGBrcHistoricalSignalEvaluationRunORM(PGCoreBase):
    """Historical CPM/signal evaluation experiment run metadata."""

    __tablename__ = "brc_historical_signal_evaluation_runs"

    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    strategy_family_id: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy_family_version_id: Mapped[str] = mapped_column(String(128), nullable=False)
    playbook_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    symbols_json: Mapped[list] = mapped_column(
        "symbols",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    primary_timeframe: Mapped[str] = mapped_column(String(32), nullable=False)
    context_timeframes_json: Mapped[list] = mapped_column(
        "context_timeframes",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    start_time_ms: Mapped[int] = mapped_column(BIGINT, nullable=False)
    end_time_ms: Mapped[int] = mapped_column(BIGINT, nullable=False)
    sampling_method: Mapped[str] = mapped_column(String(64), nullable=False)
    sampling_interval_bars: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    summary_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    owner_report_json: Mapped[dict] = mapped_column(
        "owner_report",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    updated_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    __table_args__ = (
        CheckConstraint("end_time_ms >= start_time_ms", name="ck_brc_hist_signal_eval_runs_time_range"),
        CheckConstraint("sampling_interval_bars >= 1", name="ck_brc_hist_signal_eval_runs_interval"),
        CheckConstraint("sample_limit >= 1", name="ck_brc_hist_signal_eval_runs_sample_limit"),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_brc_hist_signal_eval_runs_status",
        ),
        Index("idx_brc_hist_signal_eval_runs_strategy", "strategy_family_id", "created_at_ms"),
        Index("idx_brc_hist_signal_eval_runs_status", "status", "updated_at_ms"),
    )


class PGBrcHistoricalSignalOutputORM(PGCoreBase):
    """Compact historical StrategyFamilySignalOutput summary."""

    __tablename__ = "brc_historical_signal_outputs"

    signal_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    evaluation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy_family_id: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    timestamp_ms: Mapped[int] = mapped_column(BIGINT, nullable=False)
    timeframe: Mapped[str] = mapped_column(String(32), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    reason_codes_json: Mapped[list] = mapped_column(
        "reason_codes",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    data_quality_status: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_payload_json: Mapped[dict] = mapped_column(
        "evidence_payload",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    review_plan_json: Mapped[dict] = mapped_column(
        "review_plan",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    not_order: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    not_execution_intent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)

    __table_args__ = (
        CheckConstraint(
            "signal_type IN ('no_action', 'would_enter', 'would_exit', 'would_reduce', 'would_cancel', 'invalid')",
            name="ck_brc_hist_signal_outputs_type",
        ),
        CheckConstraint("side IN ('long', 'short', 'none')", name="ck_brc_hist_signal_outputs_side"),
        CheckConstraint(
            "data_quality_status IN ('ok', 'degraded', 'invalid')",
            name="ck_brc_hist_signal_outputs_quality",
        ),
        CheckConstraint("not_order IS TRUE", name="ck_brc_hist_signal_outputs_not_order"),
        CheckConstraint("not_execution_intent IS TRUE", name="ck_brc_hist_signal_outputs_not_exec_intent"),
        Index("idx_brc_hist_signal_outputs_run", "run_id", "timestamp_ms"),
        Index("idx_brc_hist_signal_outputs_symbol", "symbol", "timestamp_ms"),
        Index("idx_brc_hist_signal_outputs_type", "signal_type", "side"),
    )


class PGBrcStrategyGroupObservationORM(PGCoreBase):
    """Durable read-only strategy group observation evidence."""

    __tablename__ = "brc_strategy_group_observations"

    observation_id: Mapped[str] = mapped_column(String(192), primary_key=True)
    observed_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False)
    strategy_group_id: Mapped[str] = mapped_column(String(128), nullable=False)
    candidate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    side: Mapped[str] = mapped_column(String(32), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    reason_codes_json: Mapped[list] = mapped_column(
        "reason_codes",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    evidence_payload_json: Mapped[dict] = mapped_column(
        "evidence_payload",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    signal_snapshot_json: Mapped[dict] = mapped_column(
        "signal_snapshot",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    invalidation_conditions_json: Mapped[list] = mapped_column(
        "invalidation_conditions",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    human_summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    market_source: Mapped[str] = mapped_column(String(128), nullable=False)
    market_bar_timestamp_ms: Mapped[int] = mapped_column(BIGINT, nullable=False)
    market_bar_close: Mapped[Optional[Decimal]] = mapped_column(Numeric(36, 18), nullable=True)
    review_windows_json: Mapped[list] = mapped_column(
        "review_windows",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    review_status_json: Mapped[dict] = mapped_column(
        "review_status",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    input_refs_json: Mapped[dict] = mapped_column(
        "input_refs",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    not_order: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    not_execution_intent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    no_execution_permission: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    no_order_permission: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    no_runtime_start: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)

    __table_args__ = (
        CheckConstraint(
            "signal_type IN ('no_action', 'would_enter', 'invalid')",
            name="ck_brc_strategy_group_observations_signal_type",
        ),
        CheckConstraint("side IN ('long', 'short', 'none')", name="ck_brc_strategy_group_observations_side"),
        CheckConstraint("not_order IS TRUE", name="ck_brc_strategy_group_observations_not_order"),
        CheckConstraint(
            "not_execution_intent IS TRUE",
            name="ck_brc_strategy_group_observations_not_exec_intent",
        ),
        CheckConstraint(
            "no_execution_permission IS TRUE",
            name="ck_brc_strategy_group_observations_no_exec_permission",
        ),
        CheckConstraint(
            "no_order_permission IS TRUE",
            name="ck_brc_strategy_group_observations_no_order_permission",
        ),
        CheckConstraint("no_runtime_start IS TRUE", name="ck_brc_strategy_group_observations_no_runtime"),
        Index("idx_brc_strategy_group_observations_candidate", "candidate_id", "observed_at_ms"),
        Index("idx_brc_strategy_group_observations_group", "strategy_group_id", "observed_at_ms"),
        Index("idx_brc_strategy_group_observations_symbol", "symbol", "observed_at_ms"),
        Index("idx_brc_strategy_group_observations_signal", "signal_type", "side"),
    )


class PGBrcHistoricalForwardOutcomeORM(PGCoreBase):
    """Compact forward outcome review for historical would-enter signals."""

    __tablename__ = "brc_historical_forward_outcomes"

    outcome_id: Mapped[str] = mapped_column(String(192), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    signal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    timestamp_ms: Mapped[int] = mapped_column(BIGINT, nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    window_label: Mapped[str] = mapped_column(String(32), nullable=False)
    bars_ahead: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    mfe_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    mae_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    time_to_mfe_bars: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    time_to_mae_bars: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pain_before_profit_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    profit_giveback_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    follow_through: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    invalidation_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    return_time_curve_json: Mapped[list] = mapped_column(
        "return_time_curve",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)

    __table_args__ = (
        CheckConstraint("side IN ('long', 'short')", name="ck_brc_hist_forward_outcomes_side"),
        CheckConstraint(
            "status IN ('complete', 'incomplete', 'invalid')",
            name="ck_brc_hist_forward_outcomes_status",
        ),
        CheckConstraint("bars_ahead >= 1", name="ck_brc_hist_forward_outcomes_bars"),
        Index("idx_brc_hist_forward_outcomes_run", "run_id", "window_label"),
        Index("idx_brc_hist_forward_outcomes_signal", "signal_id"),
        Index("idx_brc_hist_forward_outcomes_symbol", "symbol", "timestamp_ms"),
    )


class PGBrcHistoricalRegimeSplitReportORM(PGCoreBase):
    """Compact cross-window regime-split comparison report."""

    __tablename__ = "brc_historical_regime_split_reports"

    comparison_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    strategy_family_id: Mapped[str] = mapped_column(String(128), nullable=False)
    child_run_ids_json: Mapped[dict] = mapped_column(
        "child_run_ids",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    weighted_owner_verdict: Mapped[str] = mapped_column(String(64), nullable=False)
    report_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)

    __table_args__ = (
        CheckConstraint(
            "weighted_owner_verdict IN ('continue', 'park', 'needs_refinement', 'regime_dependent_continue')",
            name="ck_brc_hist_regime_split_reports_verdict",
        ),
        Index("idx_brc_hist_regime_split_reports_strategy", "strategy_family_id", "created_at_ms"),
        Index("idx_brc_hist_regime_split_reports_verdict", "weighted_owner_verdict"),
    )


class PGBrcAdmissionRuleConfigORM(PGCoreBase):
    """Versioned admission rule config; YAML is not the production source."""

    __tablename__ = "brc_admission_rule_configs"

    admission_rule_config_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    config_key: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    rule_details_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    system_boundaries_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    relaxable_safeguards_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, default="system")

    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_brc_admission_rule_configs_version"),
        CheckConstraint(
            "status IN ('active', 'superseded', 'disabled')",
            name="ck_brc_admission_rule_configs_status",
        ),
        Index(
            "uq_brc_admission_rule_configs_key_version",
            "config_key",
            "version",
            unique=True,
        ),
        Index("idx_brc_admission_rule_configs_status_time", "status", "created_at_ms"),
    )


class PGBrcAdmissionEvidencePacketORM(PGCoreBase):
    """Evidence packet pinned into admission evaluation."""

    __tablename__ = "brc_admission_evidence_packets"

    evidence_packet_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    strategy_family_version_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    mandatory_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, default="owner")

    __table_args__ = (
        Index("idx_brc_admission_evidence_packets_version", "strategy_family_version_id"),
        Index("idx_brc_admission_evidence_packets_time", "created_at_ms"),
    )


class PGBrcOwnerMarketRegimeInputORM(PGCoreBase):
    """Owner market regime input pinned into admission evaluation."""

    __tablename__ = "brc_owner_market_regime_inputs"

    owner_market_regime_input_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    current_regime: Mapped[str] = mapped_column(String(128), nullable=False)
    confidence: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    market_facts_snapshot_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, default="owner")

    __table_args__ = (
        Index("idx_brc_owner_market_regime_inputs_time", "created_at_ms"),
    )


class PGBrcAdmissionRequestORM(PGCoreBase):
    """Admission request with version-pinned inputs."""

    __tablename__ = "brc_admission_requests"

    admission_request_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    strategy_family_version_id: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence_packet_id: Mapped[str] = mapped_column(String(128), nullable=False)
    owner_market_regime_input_id: Mapped[str] = mapped_column(String(128), nullable=False)
    trial_env: Mapped[str] = mapped_column(String(16), nullable=False)
    trial_stage: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_execution_mode: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    requested_risk_profile: Mapped[str] = mapped_column(String(64), nullable=False, default="micro")
    admission_rule_config_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    account_facts_snapshot_ref: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    account_facts_snapshot_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    playbook_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    playbook_catalog_snapshot_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False, default="owner")

    __table_args__ = (
        CheckConstraint("trial_env IN ('testnet', 'live')", name="ck_brc_admission_requests_trial_env"),
        CheckConstraint(
            "trial_stage IN ('development_validation', 'funded_validation')",
            name="ck_brc_admission_requests_trial_stage",
        ),
        CheckConstraint(
            "requested_execution_mode IS NULL OR requested_execution_mode IN "
            "('auto_within_budget', 'owner_confirm_each_entry', 'observe_only', 'no_entry')",
            name="ck_brc_admission_requests_execution_mode",
        ),
        Index("idx_brc_admission_requests_version_time", "strategy_family_version_id", "created_at_ms"),
        Index("idx_brc_admission_requests_env_stage", "trial_env", "trial_stage"),
    )


class PGBrcTrialConstraintSnapshotORM(PGCoreBase):
    """Risk/Capital adapter output snapshot for trial installation."""

    __tablename__ = "brc_trial_constraint_snapshots"

    trial_constraint_snapshot_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    admission_request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_profile: Mapped[str] = mapped_column(String(64), nullable=False, default="micro")
    risk_policy_version: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    constraints_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    risk_policy_snapshot_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    adapter_result_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    expires_at_ms: Mapped[Optional[int]] = mapped_column(BIGINT, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_risk_capital_resolution', 'installable', 'installed', 'expired', 'invalidated')",
            name="ck_brc_trial_constraint_snapshots_status",
        ),
        Index("idx_brc_trial_constraint_snapshots_request_time", "admission_request_id", "created_at_ms"),
        Index("idx_brc_trial_constraint_snapshots_status_time", "status", "created_at_ms"),
    )


class PGBrcAdmissionDecisionORM(PGCoreBase):
    """Admission decision pinned to all facts and constraint snapshot."""

    __tablename__ = "brc_admission_decisions"

    admission_decision_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    admission_request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    decision: Mapped[str] = mapped_column(String(64), nullable=False)
    trial_env: Mapped[str] = mapped_column(String(16), nullable=False)
    trial_stage: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_family_version_id: Mapped[str] = mapped_column(String(128), nullable=False)
    playbook_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    playbook_catalog_snapshot_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    owner_market_regime_input_id: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence_packet_id: Mapped[str] = mapped_column(String(128), nullable=False)
    admission_rule_config_id: Mapped[str] = mapped_column(String(128), nullable=False)
    trial_constraint_snapshot_id: Mapped[str] = mapped_column(String(128), nullable=False)
    risk_profile: Mapped[str] = mapped_column(String(64), nullable=False, default="micro")
    execution_mode: Mapped[str] = mapped_column(String(64), nullable=False)
    degradation_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    risk_intent_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    degradation_intent_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    blockers_json: Mapped[list] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=list)
    warnings_json: Mapped[list] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=list)
    risk_disclosure_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    known_gaps_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    constraints_snapshot_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    owner_risk_acceptance_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    expires_at_ms: Mapped[Optional[int]] = mapped_column(BIGINT, nullable=True)
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)

    __table_args__ = (
        CheckConstraint(
            "decision IN ('admit', 'admit_with_constraints', 'reject', 'park')",
            name="ck_brc_admission_decisions_decision",
        ),
        CheckConstraint("trial_env IN ('testnet', 'live')", name="ck_brc_admission_decisions_trial_env"),
        CheckConstraint(
            "trial_stage IN ('development_validation', 'funded_validation')",
            name="ck_brc_admission_decisions_trial_stage",
        ),
        CheckConstraint(
            "execution_mode IN ('auto_within_budget', 'owner_confirm_each_entry', 'observe_only', 'no_entry')",
            name="ck_brc_admission_decisions_execution_mode",
        ),
        Index("idx_brc_admission_decisions_request_time", "admission_request_id", "created_at_ms"),
        Index("idx_brc_admission_decisions_decision_time", "decision", "created_at_ms"),
    )


class PGBrcOwnerRiskAcceptanceORM(PGCoreBase):
    """Owner risk acceptance for funded validation."""

    __tablename__ = "brc_owner_risk_acceptances"

    owner_risk_acceptance_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    admission_request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    admission_decision_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    strategy_family_version_id: Mapped[str] = mapped_column(String(128), nullable=False)
    trial_env: Mapped[str] = mapped_column(String(16), nullable=False)
    trial_stage: Mapped[str] = mapped_column(String(64), nullable=False)
    account_facts_snapshot_ref: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    risk_profile: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_policy_snapshot_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    constraint_snapshot_id: Mapped[str] = mapped_column(String(128), nullable=False)
    risk_disclosure_snapshot_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    known_gaps_snapshot_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    owner_rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    confirmation_phrase: Mapped[str] = mapped_column(String(128), nullable=False)
    confirmation_marker: Mapped[str] = mapped_column(String(128), nullable=False)
    confirmed_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False)
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, default="owner")

    __table_args__ = (
        CheckConstraint("trial_env IN ('testnet', 'live')", name="ck_brc_owner_risk_acceptances_trial_env"),
        CheckConstraint(
            "trial_stage IN ('development_validation', 'funded_validation')",
            name="ck_brc_owner_risk_acceptances_trial_stage",
        ),
        Index("idx_brc_owner_risk_acceptances_request_time", "admission_request_id", "created_at_ms"),
        Index("idx_brc_owner_risk_acceptances_constraint", "constraint_snapshot_id"),
    )


class PGBrcAdmissionAuditLogORM(PGCoreBase):
    """Append-only admission audit log."""

    __tablename__ = "brc_admission_audit_log"

    audit_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    ref_type: Mapped[str] = mapped_column(String(128), nullable=False)
    ref_id: Mapped[str] = mapped_column(String(128), nullable=False)
    admission_request_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    admission_decision_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="system")
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)

    __table_args__ = (
        Index("idx_brc_admission_audit_log_ref", "ref_type", "ref_id"),
        Index("idx_brc_admission_audit_log_request_time", "admission_request_id", "created_at_ms"),
        Index("idx_brc_admission_audit_log_time", "created_at_ms"),
    )


class PGBrcAdmissionTrialBindingORM(PGCoreBase):
    """Admission-to-future-trial binding reservation.

    This is a planning/carrier-binding fact only. The reserved states must not
    imply campaign creation, runtime installation, or order execution.
    """

    __tablename__ = "brc_admission_trial_bindings"

    binding_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    admission_decision_id: Mapped[str] = mapped_column(String(128), nullable=False)
    owner_risk_acceptance_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    trial_constraint_snapshot_id: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy_family_version_id: Mapped[str] = mapped_column(String(128), nullable=False)
    playbook_id: Mapped[str] = mapped_column(String(128), nullable=False)
    playbook_catalog_snapshot_json: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    trial_env: Mapped[str] = mapped_column(String(16), nullable=False)
    trial_stage: Mapped[str] = mapped_column(String(64), nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(64), nullable=False)
    binding_status: Mapped[str] = mapped_column(String(64), nullable=False)
    campaign_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    runtime_carrier_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_by_operation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by_preflight_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    updated_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    invalidated_at_ms: Mapped[Optional[int]] = mapped_column(BIGINT, nullable=True)
    invalidation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("trial_env IN ('testnet', 'live')", name="ck_brc_admission_trial_bindings_trial_env"),
        CheckConstraint(
            "trial_stage IN ('development_validation', 'funded_validation')",
            name="ck_brc_admission_trial_bindings_trial_stage",
        ),
        CheckConstraint(
            "execution_mode IN ('auto_within_budget', 'owner_confirm_each_entry', 'observe_only', 'no_entry')",
            name="ck_brc_admission_trial_bindings_execution_mode",
        ),
        CheckConstraint(
            "binding_status IN ('planned', 'binding_reserved', 'cancelled', 'expired', "
            "'invalidated', 'campaign_created', 'runtime_constraints_installed', "
            "'runtime_installed')",
            name="ck_brc_admission_trial_bindings_status",
        ),
        CheckConstraint(
            "(binding_status NOT IN ('planned', 'binding_reserved')) "
            "OR (campaign_id IS NULL AND runtime_carrier_id IS NULL)",
            name="ck_brc_admission_trial_bindings_reserved_no_runtime",
        ),
        Index(
            "idx_brc_admission_trial_bindings_decision_status",
            "admission_decision_id",
            "binding_status",
        ),
        Index("idx_brc_admission_trial_bindings_operation", "created_by_operation_id"),
        Index("idx_brc_admission_trial_bindings_status_time", "binding_status", "created_at_ms"),
    )


class PGBrcTrialTradeIntentORM(PGCoreBase):
    """Non-executable trial trade intent evidence ledger.

    Rows in this table are not orders and must not feed order execution.
    """

    __tablename__ = "brc_trial_trade_intents"

    intent_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(String(128), nullable=False)
    binding_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    admission_decision_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    strategy_family_version_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    playbook_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    execution_mode: Mapped[str] = mapped_column(String(64), nullable=False)
    intended_action: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    side: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    signal_snapshot_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    market_snapshot_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    risk_snapshot_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    not_executed_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)
    created_by_operation_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    audit_refs_json: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint(
            "execution_mode IN ('auto_within_budget', 'owner_confirm_each_entry', 'observe_only', 'no_entry')",
            name="ck_brc_trial_trade_intents_execution_mode",
        ),
        CheckConstraint(
            "intended_action IN ('entry', 'increase', 'exit', 'reduce', 'hold', 'unknown')",
            name="ck_brc_trial_trade_intents_intended_action",
        ),
        CheckConstraint(
            "decision IN ('recorded', 'blocked', 'unavailable')",
            name="ck_brc_trial_trade_intents_decision",
        ),
        Index("idx_brc_trial_trade_intents_campaign_time", "campaign_id", "created_at_ms"),
        Index("idx_brc_trial_trade_intents_binding_time", "binding_id", "created_at_ms"),
        Index("idx_brc_trial_trade_intents_decision_time", "decision", "created_at_ms"),
        Index("idx_brc_trial_trade_intents_operation", "created_by_operation_id"),
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


class PGReconciliationReadModelReportORM(PGCoreBase):
    """PG periodic reconciliation read model report table."""

    __tablename__ = "reconciliation_read_model_reports"

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    report_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    checked_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False)
    is_consistent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    severe_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_fetch_failure: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fetch_failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)

    __table_args__ = (
        Index("idx_reconciliation_read_model_reports_symbol_time", "symbol", "checked_at_ms"),
        Index("idx_reconciliation_read_model_reports_consistent", "is_consistent"),
        Index("idx_reconciliation_read_model_reports_time", "checked_at_ms"),
    )


class PGReconciliationReadModelMismatchORM(PGCoreBase):
    """PG periodic reconciliation read model mismatch detail table."""

    __tablename__ = "reconciliation_read_model_mismatches"

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    report_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("reconciliation_read_model_reports.report_id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    mismatch_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    local_ref: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    exchange_ref: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(
        "metadata",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    created_at: Mapped[int] = mapped_column(BIGINT, nullable=False, default=_now_ms)

    __table_args__ = (
        Index("idx_reconciliation_read_model_mismatches_report", "report_id"),
        Index("idx_reconciliation_read_model_mismatches_type", "mismatch_type"),
        Index("idx_reconciliation_read_model_mismatches_severity", "severity"),
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
