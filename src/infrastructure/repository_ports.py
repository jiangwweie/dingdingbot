"""
Repository Protocols - 核心仓储协议定义

用于 SQLite / PostgreSQL 双实现并存阶段的最小接口边界。
本文件只抽取当前核心链路实际需要的方法，不试图一次性覆盖所有旧仓储能力。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
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

    async def update_status(
        self,
        order_id: str,
        status: OrderStatus,
        filled_qty: Optional[Decimal] = None,
        average_exec_price: Optional[Decimal] = None,
        filled_at: Optional[int] = None,
        exchange_order_id: Optional[str] = None,
        exit_reason: Optional[str] = None,
    ) -> None:
        """更新订单状态（部分更新，避免完整 save）。"""
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

    async def get_by_signal_id(self, signal_id: str) -> Optional[ExecutionIntent]:
        ...

    async def get_by_order_id(self, order_id: str) -> Optional[ExecutionIntent]:
        ...

    async def list_unfinished(self) -> List[ExecutionIntent]:
        ...

    async def list(
        self,
        status: Optional[ExecutionIntentStatus] = None,
    ) -> List[ExecutionIntent]:
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
    使用 Any 类型避免领域模型与 ORM 的强耦合，由具体实现自行决定。
    """

    async def initialize(self) -> None:
        ...

    async def close(self) -> None:
        ...

    async def save(self, position: Any) -> None:
        """保存仓位（接收领域模型或 ORM，由实现决定转换）。"""
        ...

    async def get(self, position_id: str) -> Optional[Any]:
        """获取仓位（返回领域模型或 ORM，由实现决定）。"""
        ...

    async def get_by_signal_id(self, signal_id: str) -> List[Any]:
        """按信号 ID 获取仓位列表。"""
        ...

    async def list_active(
        self,
        *,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> List[Any]:
        """列出当前未平仓仓位。"""
        ...


@dataclass(frozen=True)
class DailyRiskStatsSnapshot:
    """Restored aggregate for one UTC daily risk scope."""

    scope_key: str
    stats_date: date
    realized_pnl: Decimal
    trade_count: int


@dataclass(frozen=True)
class DailyRiskStatsEvent:
    """Idempotent daily risk stats accounting event."""

    event_key: str
    scope_key: str
    stats_date: date
    position_id: str
    signal_id: str
    exit_order_id: str
    delta_exit_qty: Decimal
    delta_realized_pnl: Decimal
    trade_count_delta: int
    occurred_at: datetime
    source: str = "exit_projection"


@dataclass(frozen=True)
class DailyRiskStatsWriteResult:
    """Result of an idempotent event-ledger write."""

    snapshot: DailyRiskStatsSnapshot
    inserted: bool


@runtime_checkable
class DailyRiskStatsRepositoryPort(Protocol):
    """PG-backed daily risk stats persistence boundary."""

    async def initialize(self) -> None:
        ...

    async def restore_or_create(
        self,
        scope_key: str,
        stats_date: date,
    ) -> DailyRiskStatsSnapshot:
        ...

    async def record_event(
        self,
        event: DailyRiskStatsEvent,
    ) -> DailyRiskStatsWriteResult:
        ...

    async def get(
        self,
        scope_key: str,
        stats_date: date,
    ) -> Optional[DailyRiskStatsSnapshot]:
        ...


@dataclass(frozen=True)
class GlobalKillSwitchStateSnapshot:
    """Persisted global kill switch state."""

    active: bool
    reason: Optional[str]
    updated_by: str
    updated_at_ms: int
    source: str = "pg"


@runtime_checkable
class GlobalKillSwitchRepositoryPort(Protocol):
    """PG-backed global kill switch persistence boundary."""

    async def initialize(self) -> None:
        ...

    async def get_state(self) -> Optional[GlobalKillSwitchStateSnapshot]:
        ...

    async def set_state(
        self,
        *,
        active: bool,
        reason: Optional[str],
        updated_by: str,
        updated_at_ms: int,
    ) -> GlobalKillSwitchStateSnapshot:
        ...


@dataclass(frozen=True)
class CampaignStateSnapshot:
    """Persisted runtime campaign state."""

    scope_key: str
    status: str
    reason: Optional[str]
    updated_by: str
    updated_at_ms: int
    active_strategy_contract_id: Optional[str] = None
    active_session_id: Optional[str] = None
    source: str = "pg"


@runtime_checkable
class CampaignStateRepositoryPort(Protocol):
    """PG-backed runtime campaign state persistence boundary."""

    async def initialize(self) -> None:
        ...

    async def get_state(self, scope_key: str) -> Optional[CampaignStateSnapshot]:
        ...

    async def set_state(
        self,
        *,
        scope_key: str,
        status: str,
        reason: Optional[str],
        updated_by: str,
        updated_at_ms: int,
        active_strategy_contract_id: Optional[str],
        active_session_id: Optional[str],
    ) -> CampaignStateSnapshot:
        ...


@dataclass(frozen=True)
class ReconciliationReadModelReport:
    """Persisted periodic reconciliation read model report."""

    report_id: str
    symbol: str
    checked_at_ms: int
    is_consistent: bool = True
    total_count: int = 0
    severe_count: int = 0
    warning_count: int = 0
    is_fetch_failure: bool = False
    fetch_failure_reason: Optional[str] = None
    created_at: int = 0


@dataclass(frozen=True)
class ReconciliationReadModelMismatch:
    """Persisted periodic reconciliation read model mismatch detail."""

    report_id: str
    symbol: str
    mismatch_type: str
    severity: str
    reason: str
    local_ref: Optional[str] = None
    exchange_ref: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    created_at: int = 0


@runtime_checkable
class ReconciliationReadModelRepositoryPort(Protocol):
    """PG-backed read-only periodic reconciliation report persistence boundary."""

    async def initialize(self) -> None:
        ...

    async def save_report(
        self,
        report: ReconciliationReadModelReport,
        mismatches: List[ReconciliationReadModelMismatch],
    ) -> None:
        ...

    async def get_recent_reports(
        self,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> List[ReconciliationReadModelReport]:
        ...

    async def get_mismatches(
        self,
        report_id: str,
    ) -> List[ReconciliationReadModelMismatch]:
        ...
