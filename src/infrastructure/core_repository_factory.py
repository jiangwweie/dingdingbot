"""
Core Repository Factory - 核心仓储实现选择器

双轨迁移阶段统一在这里根据环境变量选择 SQLite / PostgreSQL 实现，
避免应用层直接分支具体仓储类型。
"""

from __future__ import annotations

from typing import Optional

from src.infrastructure.hybrid_signal_repository import HybridSignalRepository
from src.infrastructure.database import get_core_backend_settings
from src.infrastructure.order_repository import OrderRepository
from src.infrastructure.pg_execution_intent_repository import PgExecutionIntentRepository
from src.infrastructure.pg_order_repository import PgOrderRepository
from src.infrastructure.pg_position_repository import PgPositionRepository
from src.infrastructure.repository_ports import (
    ExecutionIntentRepositoryPort,
    OrderRepositoryPort,
    PositionRepositoryPort,
)


def create_order_repository() -> OrderRepositoryPort:
    """按配置创建核心订单仓储。"""
    backend = get_core_backend_settings()["order"]
    if backend == "postgres":
        return PgOrderRepository()
    return OrderRepository()


def create_pg_order_repository() -> OrderRepositoryPort:
    """显式创建 PG 订单仓储。"""
    return PgOrderRepository()


def create_runtime_order_repository() -> OrderRepositoryPort:
    """为 runtime execution 主链显式创建 PG 订单仓储。"""
    return create_pg_order_repository()


def create_execution_intent_repository() -> Optional[ExecutionIntentRepositoryPort]:
    """按配置创建执行意图仓储。

    SQLite 链路暂时保留 orchestrator 内存态作为旧实现，因此返回 None。
    """
    backend = get_core_backend_settings()["execution_intent"]
    if backend == "postgres":
        return PgExecutionIntentRepository()
    return None


def create_position_repository() -> Optional[PositionRepositoryPort]:
    """按配置创建仓位仓储。

    第一阶段仅为 PG 核心表迁移预留装配入口。
    """
    backend = get_core_backend_settings()["position"]
    if backend == "postgres":
        return PgPositionRepository()
    return None


def create_pg_position_repository() -> PositionRepositoryPort:
    """显式创建 PG 仓位仓储。"""
    return PgPositionRepository()


def create_runtime_position_repository() -> PositionRepositoryPort:
    """为 runtime execution 主链显式创建 PG 仓位仓储。"""
    return create_pg_position_repository()


def create_runtime_signal_repository() -> HybridSignalRepository:
    """为 runtime signal 主链创建混合仓储。

    - live signals / take profits -> PG
    - attempts / config snapshots / backtest helpers -> SQLite
    """
    return HybridSignalRepository()
