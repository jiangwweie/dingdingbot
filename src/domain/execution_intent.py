"""
Execution Intent - 执行意图模型

ExecutionOrchestrator MVP 第一步：最小执行意图模型

职责：
1. 记录信号到订单的执行意图
2. 跟踪执行状态（pending/blocked/submitted/failed）
3. 关联 SignalResult 和 Order

最小实现：
- 本 MVP 阶段使用内存存储
- 后续可迁移到数据库持久化
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.models import SignalResult, Order, OrderStrategy


class ExecutionIntentStatus(str, Enum):
    """执行意图状态"""
    RECORDED = "recorded"        # 已记录；尚未授权进入提交链路
    LOCAL_ORDERS_REGISTERED = "local_orders_registered"  # 本地 CREATED orders 已注册；尚未提交交易所
    PENDING = "pending"          # 等待执行
    BLOCKED = "blocked"          # 被 CapitalProtection 拦截
    SUBMITTED = "submitted"      # 已提交到交易所
    FAILED = "failed"            # 提交失败
    PROTECTING = "protecting"    # ENTRY 成交，正在挂载保护单（TP/SL）
    PARTIALLY_PROTECTED = "partially_protected"  # ENTRY 部分成交，已对已成交部分挂载保护单
    COMPLETED = "completed"      # 执行完成（订单已创建且保护单已挂载）


class ExecutionIntent(BaseModel):
    """
    执行意图

    记录执行意图和状态。

    Legacy one-shot execution still uses SignalResult. Runtime governance
    intents may instead use source_type/source_id/source_payload without
    projecting an OrderCandidate into a fake SignalResult.
    """
    id: str = Field(..., description="执行意图 ID")
    symbol: Optional[str] = Field(default=None, description="交易标的")
    signal_id: Optional[str] = Field(
        default=None,
        description="Legacy signal ID when source_type is legacy SignalResult.",
    )
    signal: Optional[SignalResult] = Field(
        default=None,
        description="Legacy SignalResult snapshot when applicable.",
    )
    status: ExecutionIntentStatus = Field(
        default=ExecutionIntentStatus.PENDING,
        description="执行状态"
    )

    # Execution semantics snapshot (MVP: in-memory only)
    # Needed so async callbacks (e.g., partial fill) can generate TP/SL
    # using the exact same strategy definition as the original signal.
    strategy: Optional[OrderStrategy] = Field(
        default=None,
        description="订单策略快照（用于后续 TP/SL 保护单生成）",
    )

    # 关联订单（执行成功后填充）
    order_id: Optional[str] = Field(None, description="本地订单 ID")
    exchange_order_id: Optional[str] = Field(None, description="交易所订单 ID")
    authorization_id: Optional[str] = Field(
        None,
        description="Owner bounded live-trial authorization ID, when intent is created from Owner execution.",
    )
    source_type: Optional[str] = Field(
        None,
        description=(
            "Additive source discriminator for intent origin, e.g. "
            "legacy_signal_result, owner_bounded_authorization, or "
            "brc_runtime_order_candidate."
        ),
    )
    source_id: Optional[str] = Field(
        None,
        description="Additive source object ID for the intent origin.",
    )
    source_payload: Optional[dict[str, Any]] = Field(
        None,
        description="Optional source snapshot for non-legacy intent origins.",
    )
    runtime_execution_intent_draft_id: Optional[str] = Field(
        None,
        description="Optional non-executable runtime intent draft audit ID.",
    )
    runtime_instance_id: Optional[str] = Field(
        None,
        description="Optional StrategyRuntimeInstance audit ID; trace metadata only.",
    )
    trial_binding_id: Optional[str] = Field(
        None,
        description="Optional admission trial binding audit ID; trace metadata only.",
    )
    strategy_family_id: Optional[str] = Field(
        None,
        description="Optional strategy family audit ID; trace metadata only.",
    )
    strategy_family_version_id: Optional[str] = Field(
        None,
        description="Optional strategy family version audit ID; trace metadata only.",
    )
    signal_evaluation_id: Optional[str] = Field(
        None,
        description="Optional future SignalEvaluation audit ID; trace metadata only.",
    )
    order_candidate_id: Optional[str] = Field(
        None,
        description="Optional future OrderCandidate audit ID; trace metadata only.",
    )

    @property
    def semantic_ids(self) -> BrcSemanticIds:
        return BrcSemanticIds(
            runtime_instance_id=self.runtime_instance_id,
            trial_binding_id=self.trial_binding_id,
            strategy_family_id=self.strategy_family_id,
            strategy_family_version_id=self.strategy_family_version_id,
            signal_evaluation_id=self.signal_evaluation_id,
            order_candidate_id=self.order_candidate_id,
        )

    # 拦截原因（被 CapitalProtection 拦截时填充）
    blocked_reason: Optional[str] = Field(None, description="拦截原因代码")
    blocked_message: Optional[str] = Field(None, description="拦截原因描述")

    # 失败原因（提交失败时填充）
    failed_reason: Optional[str] = Field(None, description="失败原因")

    # 时间戳
    created_at: int = Field(
        default_factory=lambda: int(datetime.now(timezone.utc).timestamp() * 1000),
        description="创建时间"
    )
    updated_at: int = Field(
        default_factory=lambda: int(datetime.now(timezone.utc).timestamp() * 1000),
        description="更新时间"
    )

    @model_validator(mode="after")
    def _validate_source_shape(self) -> "ExecutionIntent":
        if self.symbol is None and self.signal is not None:
            self.symbol = self.signal.symbol
        if not self.symbol:
            raise ValueError("ExecutionIntent requires symbol")
        if self.signal is not None and not self.signal_id:
            raise ValueError("legacy signal ExecutionIntent requires signal_id")
        if self.signal_id and self.signal is None:
            raise ValueError("signal_id requires signal payload")
        if self.signal is not None and self.signal.symbol != self.symbol:
            raise ValueError("ExecutionIntent symbol must match signal.symbol")
        if self.signal is None:
            if not self.source_type or not self.source_id:
                raise ValueError("source-native ExecutionIntent requires source_type and source_id")
            source_native_statuses = {
                ExecutionIntentStatus.RECORDED,
                ExecutionIntentStatus.RECORDED.value,
                ExecutionIntentStatus.LOCAL_ORDERS_REGISTERED,
                ExecutionIntentStatus.LOCAL_ORDERS_REGISTERED.value,
            }
            if self.status not in source_native_statuses:
                raise ValueError(
                    "source-native ExecutionIntent must be recorded or locally registered"
                )
            if (
                self.status
                in {
                    ExecutionIntentStatus.LOCAL_ORDERS_REGISTERED,
                    ExecutionIntentStatus.LOCAL_ORDERS_REGISTERED.value,
                }
                and self.exchange_order_id is not None
            ):
                raise ValueError(
                    "local_orders_registered ExecutionIntent cannot have exchange_order_id"
                )
        return self

    model_config = {"use_enum_values": True}
