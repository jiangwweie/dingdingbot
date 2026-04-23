"""
PG Execution Recovery Repository - PostgreSQL 执行恢复任务仓库

职责：
1. 管理 execution_recovery_tasks 表
2. 提供最小方法集：create/get/list_active/mark_resolved/mark_retrying/mark_failed/delete
3. 不搞大而全，只做当前恢复链会用到的方法
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.pg_models import PGExecutionRecoveryTaskORM
from src.infrastructure.database import init_pg_core_db
from src.infrastructure.logger import logger


class PgExecutionRecoveryRepository:
    """PG 执行恢复任务仓库。"""

    def __init__(self, session_maker: async_sessionmaker[AsyncSession]):
        """
        初始化仓库。

        Args:
            session_maker: async_sessionmaker 实例
        """
        self._session_maker = session_maker

    async def initialize(self) -> None:
        """
        初始化仓库。

        确保表结构已创建。
        """
        await init_pg_core_db()
        logger.info("PgExecutionRecoveryRepository initialized")

    async def close(self) -> None:
        """关闭仓库（当前为空实现，session 由外部管理）。"""
        logger.info("PgExecutionRecoveryRepository closed")

    async def create_task(
        self,
        task_id: str,
        intent_id: str,
        symbol: str,
        recovery_type: str,
        related_order_id: Optional[str] = None,
        related_exchange_order_id: Optional[str] = None,
        error_message: Optional[str] = None,
        context_payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        创建恢复任务。

        Args:
            task_id: 任务 ID
            intent_id: 关联的执行意图 ID
            symbol: 交易对
            recovery_type: 恢复类型（如 'replace_sl_failed'）
            related_order_id: 关联订单 ID（可选）
            related_exchange_order_id: 关联交易所订单 ID（可选）
            error_message: 错误信息（可选）
            context_payload: 上下文载荷（可选）
        """
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        task = PGExecutionRecoveryTaskORM(
            id=task_id,
            intent_id=intent_id,
            related_order_id=related_order_id,
            related_exchange_order_id=related_exchange_order_id,
            symbol=symbol,
            recovery_type=recovery_type,
            status="pending",
            error_message=error_message,
            retry_count=0,
            next_retry_at=None,
            context_payload=context_payload,
            created_at=now_ms,
            updated_at=now_ms,
            resolved_at=None,
        )

        async with self._session_maker() as session:
            session.add(task)
            await session.commit()

        logger.info(
            f"Created recovery task: id={task_id}, intent_id={intent_id}, "
            f"recovery_type={recovery_type}, symbol={symbol}"
        )

    async def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取恢复任务。

        Args:
            task_id: 任务 ID

        Returns:
            任务字典，不存在返回 None
        """
        async with self._session_maker() as session:
            result = await session.execute(
                select(PGExecutionRecoveryTaskORM).where(PGExecutionRecoveryTaskORM.id == task_id)
            )
            task = result.scalar_one_or_none()

            if not task:
                return None

            return self._orm_to_dict(task)

    async def get_by_intent_id(self, intent_id: str) -> Optional[Dict[str, Any]]:
        """
        按执行意图 ID 获取恢复任务。

        Args:
            intent_id: 执行意图 ID

        Returns:
            任务字典，不存在返回 None
        """
        async with self._session_maker() as session:
            result = await session.execute(
                select(PGExecutionRecoveryTaskORM).where(PGExecutionRecoveryTaskORM.intent_id == intent_id)
            )
            task = result.scalar_one_or_none()

            if not task:
                return None

            return self._orm_to_dict(task)

    async def list_active(self, now_ms: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        列出活跃恢复任务。

        语义：status in ('pending','retrying') 且 next_retry_at is null or <= now_ms

        Args:
            now_ms: 当前时间戳（毫秒），不传则使用当前时间

        Returns:
            活跃任务列表
        """
        if now_ms is None:
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        async with self._session_maker() as session:
            result = await session.execute(
                select(PGExecutionRecoveryTaskORM).where(
                    and_(
                        PGExecutionRecoveryTaskORM.status.in_(["pending", "retrying"]),
                        (PGExecutionRecoveryTaskORM.next_retry_at.is_(None))
                        | (PGExecutionRecoveryTaskORM.next_retry_at <= now_ms),
                    )
                )
            )
            tasks = result.scalars().all()

            return [self._orm_to_dict(task) for task in tasks]

    async def mark_resolved(
        self,
        task_id: str,
        resolved_at: int,
        error_message: Optional[str] = None,
    ) -> None:
        """
        标记任务为已解决。

        Args:
            task_id: 任务 ID
            resolved_at: 解决时间戳（毫秒）
            error_message: 错误信息（可选）
        """
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        async with self._session_maker() as session:
            result = await session.execute(
                select(PGExecutionRecoveryTaskORM).where(PGExecutionRecoveryTaskORM.id == task_id)
            )
            task = result.scalar_one_or_none()

            if not task:
                logger.warning(f"Task not found: id={task_id}")
                return

            task.status = "resolved"
            task.resolved_at = resolved_at
            task.updated_at = now_ms

            if error_message:
                task.error_message = error_message

            await session.commit()

        logger.info(f"Marked task resolved: id={task_id}")

    async def mark_retrying(
        self,
        task_id: str,
        retry_count: int,
        next_retry_at: int,
        error_message: Optional[str] = None,
    ) -> None:
        """
        标记任务为重试中。

        Args:
            task_id: 任务 ID
            retry_count: 重试次数
            next_retry_at: 下次重试时间戳（毫秒）
            error_message: 错误信息（可选）
        """
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        async with self._session_maker() as session:
            result = await session.execute(
                select(PGExecutionRecoveryTaskORM).where(PGExecutionRecoveryTaskORM.id == task_id)
            )
            task = result.scalar_one_or_none()

            if not task:
                logger.warning(f"Task not found: id={task_id}")
                return

            task.status = "retrying"
            task.retry_count = retry_count
            task.next_retry_at = next_retry_at
            task.updated_at = now_ms

            if error_message:
                task.error_message = error_message

            await session.commit()

        logger.info(
            f"Marked task retrying: id={task_id}, retry_count={retry_count}, "
            f"next_retry_at={next_retry_at}"
        )

    async def mark_failed(self, task_id: str, error_message: Optional[str] = None) -> None:
        """
        标记任务为最终失败。

        Args:
            task_id: 任务 ID
            error_message: 错误信息（可选）
        """
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        async with self._session_maker() as session:
            result = await session.execute(
                select(PGExecutionRecoveryTaskORM).where(PGExecutionRecoveryTaskORM.id == task_id)
            )
            task = result.scalar_one_or_none()

            if not task:
                logger.warning(f"Task not found: id={task_id}")
                return

            task.status = "failed"
            task.updated_at = now_ms

            if error_message:
                task.error_message = error_message

            await session.commit()

        logger.info(f"Marked task failed: id={task_id}")

    async def delete(self, task_id: str) -> None:
        """
        删除任务（仅保留最小能力，后续脚本可能用）。

        Args:
            task_id: 任务 ID
        """
        async with self._session_maker() as session:
            result = await session.execute(
                select(PGExecutionRecoveryTaskORM).where(PGExecutionRecoveryTaskORM.id == task_id)
            )
            task = result.scalar_one_or_none()

            if not task:
                logger.warning(f"Task not found: id={task_id}")
                return

            await session.delete(task)
            await session.commit()

        logger.info(f"Deleted task: id={task_id}")

    def _orm_to_dict(self, task: PGExecutionRecoveryTaskORM) -> Dict[str, Any]:
        """ORM 对象转字典。"""
        return {
            "id": task.id,
            "intent_id": task.intent_id,
            "related_order_id": task.related_order_id,
            "related_exchange_order_id": task.related_exchange_order_id,
            "symbol": task.symbol,
            "recovery_type": task.recovery_type,
            "status": task.status,
            "error_message": task.error_message,
            "retry_count": task.retry_count,
            "next_retry_at": task.next_retry_at,
            "context_payload": task.context_payload,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "resolved_at": task.resolved_at,
        }
