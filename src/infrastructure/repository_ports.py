"""
Repository Protocols - 核心仓储协议定义

用于 SQLite / PostgreSQL 双实现并存阶段的最小接口边界。
本文件只抽取当前核心链路实际需要的方法，不试图一次性覆盖所有旧仓储能力。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, List, Optional, Protocol, runtime_checkable

from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.domain.models import Order, OrderRole, OrderStatus


@runtime_checkable
class OrderRepositoryPort(Protocol):
    """核心订单仓储协议。"""

    async def initialize(self) -> None:
        ...

    async def close(self) -> None:
        ...

    async def save(self, order: Order) -> None:
        ...

    async def save_batch(self, orders: List[Order]) -> None:
        ...

    async def get_order(self, order_id: str) -> Optional[Order]:
        ...

    async def get_order_by_exchange_id(self, exchange_order_id: str) -> Optional[Order]:
        ...

    async def get_orders_by_signal(self, signal_id: str) -> List[Order]:
        ...

    async def get_orders_by_symbol(self, symbol: str, limit: int = 100) -> List[Order]:
        ...

    async def get_orders_by_status(
        self,
        status: OrderStatus,
        symbol: Optional[str] = None,
    ) -> List[Order]:
        ...

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        ...


@runtime_checkable
class ExecutionIntentRepositoryPort(Protocol):
    """执行意图仓储协议。"""

    async def initialize(self) -> None:
        ...

    async def close(self) -> None:
        ...

    async def save(self, intent: ExecutionIntent) -> None:
        ...

    async def get(self, intent_id: str) -> Optional[ExecutionIntent]:
        ...

    async def get_by_order_id(self, order_id: str) -> Optional[ExecutionIntent]:
        ...

    async def list_unfinished(self) -> List[ExecutionIntent]:
        ...

    async def update_status(
        self,
        intent_id: str,
        status: ExecutionIntentStatus,
        *,
        order_id: Optional[str] = None,
        exchange_order_id: Optional[str] = None,
        blocked_reason: Optional[str] = None,
        blocked_message: Optional[str] = None,
        failed_reason: Optional[str] = None,
    ) -> None:
        ...


@runtime_checkable
class PositionRepositoryPort(Protocol):
    """仓位仓储协议。

    第一阶段仅为 PG 核心表骨架预留边界。
    暂不强制绑定领域模型或 ORM 模型，由具体实现自行决定。
    """

    async def initialize(self) -> None:
        ...

    async def close(self) -> None:
        ...

    async def save(self, position: Any) -> None:
        ...

    async def get(self, position_id: str) -> Optional[Any]:
        ...

    async def get_by_signal_id(self, signal_id: str) -> List[Any]:
        ...
