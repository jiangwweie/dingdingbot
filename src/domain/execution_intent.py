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
from typing import Optional
from enum import Enum

from pydantic import BaseModel, Field

from src.domain.models import SignalResult, Order, OrderStrategy


class ExecutionIntentStatus(str, Enum):
    """执行意图状态"""
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

    记录信号到订单的执行意图和状态
    """
    id: str = Field(..., description="执行意图 ID")
    signal: SignalResult = Field(..., description="原始信号")
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

    model_config = {"use_enum_values": True}
