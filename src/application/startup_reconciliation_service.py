"""
Startup Reconciliation Service - 启动对账最小版

职责：
1. 程序启动时执行一次性对账
2. 扫描本地未完成订单（SUBMITTED / OPEN / PARTIALLY_FILLED）
3. 读取交易所 WS 失败恢复队列（_pending_recovery_orders）
4. 通过 REST API 查询交易所真实状态
5. 推进本地订单状态
6. 清除恢复队列标记
7. 扫描 PG recovery tasks 并推进状态

范围控制：
- 不做定期对账
- 不做 30s 超时查询
- 不做 TP/SL 挂载
- 不做 recovery_required
- 不做 API 改造
- 不做数据库迁移
- 不做全量仓位对账
"""
import asyncio
import time
from typing import List, Dict, Any, Optional
from decimal import Decimal

from src.domain.models import Order, OrderStatus
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.order_repository import OrderRepository
from src.application.order_lifecycle_service import OrderLifecycleService
from src.application.recovery_retry_policy import (
    should_retry,
    calculate_next_retry_at,
    MAX_RECOVERY_RETRY_COUNT,
)
from src.infrastructure.logger import logger


class StartupReconciliationService:
    """
    启动对账服务（最小版）

    核心职责：
    1. 启动时扫描本地未完成订单
    2. 查询交易所真实状态
    3. 推进本地订单状态
    4. 清除待恢复标记
    """

    def __init__(
        self,
        gateway: ExchangeGateway,
        repository: OrderRepository,
        lifecycle: OrderLifecycleService,
        orchestrator: Optional[Any] = None,  # P0-4：可选注入 ExecutionOrchestrator
        execution_recovery_repository: Optional[Any] = None,  # PG 正式恢复表
    ):
        """
        初始化启动对账服务

        Args:
            gateway: ExchangeGateway 实例
            repository: OrderRepository 实例
            lifecycle: OrderLifecycleService 实例
            orchestrator: ExecutionOrchestrator 实例（可选，用于 breaker 管理）
            execution_recovery_repository: PG 正式恢复表仓储（可选）
        """
        self._gateway = gateway
        self._repository = repository
        self._lifecycle = lifecycle
        self._orchestrator = orchestrator
        self._execution_recovery_repository = execution_recovery_repository

    async def run_startup_reconciliation(self) -> Dict[str, Any]:
        """
        执行启动对账

        对账流程：
        1. 扫描本地未完成订单（SUBMITTED / OPEN / PARTIALLY_FILLED）
        2. 读取交易所 WS 失败恢复队列（_pending_recovery_orders）
        3. 对每笔候选订单：
           - 通过 fetch_order() 查询交易所真实状态
           - 用 update_order_from_exchange() 推进本地状态
           - 如果在恢复队列，清除标记
        4. 扫描 PG recovery tasks 并推进状态

        Returns:
            Dict[str, Any]: 对账结果摘要
        """
        logger.info("=" * 70)
        logger.info("启动对账服务开始执行")
        logger.info("=" * 70)

        start_time = int(time.time() * 1000)

        # ===== 阶段 1: 扫描候选订单 =====
        candidate_orders: List[Order] = []

        # 1.1 扫描本地未完成订单
        submitted_orders = await self._repository.get_orders_by_status(OrderStatus.SUBMITTED)
        open_orders = await self._repository.get_orders_by_status(OrderStatus.OPEN)
        partially_filled_orders = await self._repository.get_orders_by_status(OrderStatus.PARTIALLY_FILLED)

        candidate_orders.extend(submitted_orders)
        candidate_orders.extend(open_orders)
        candidate_orders.extend(partially_filled_orders)

        logger.info(
            f"扫描本地未完成订单: "
            f"SUBMITTED={len(submitted_orders)}, "
            f"OPEN={len(open_orders)}, "
            f"PARTIALLY_FILLED={len(partially_filled_orders)}, "
            f"总计={len(candidate_orders)}"
        )

        # 1.2 读取待恢复订单
        pending_recovery_orders = self._gateway.get_pending_recovery_orders()
        pending_order_ids = list(pending_recovery_orders.keys())

        logger.info(f"读取待恢复订单: 总计={len(pending_order_ids)}")

        # 合并候选订单（去重）
        # 待恢复订单可能已经在候选列表中，也可能不在（例如已标记为 FILLED）
        all_candidate_ids = {order.exchange_order_id for order in candidate_orders if order.exchange_order_id}
        all_candidate_ids.update(pending_order_ids)

        logger.info(f"合并候选订单（去重）: 总计={len(all_candidate_ids)}")

        # ===== 阶段 2: 执行对账 =====
        success_count = 0
        failure_count = 0
        recovery_cleared_count = 0

        # P0-4：记录已成功对账的订单 ID（用于跳过 phase 2.5 的重复对账）
        successfully_reconciled_order_ids: set = set()

        for exchange_order_id in all_candidate_ids:
            # 查找本地订单对象
            local_order = None
            for order in candidate_orders:
                if order.exchange_order_id == exchange_order_id:
                    local_order = order
                    break

            # 如果在待恢复列表，取出订单对象
            if exchange_order_id in pending_recovery_orders:
                pending_info = pending_recovery_orders[exchange_order_id]
                if not local_order:
                    local_order = pending_info.get("order")

            if not local_order:
                logger.warning(
                    f"跳过订单: exchange_order_id={exchange_order_id}, "
                    f"本地订单对象不存在"
                )
                continue

            # 执行对账
            try:
                logger.info(
                    f"对账订单: exchange_order_id={exchange_order_id}, "
                    f"symbol={local_order.symbol}, "
                    f"本地状态={local_order.status}"
                )

                # 查询交易所真实状态
                exchange_order_result = await self._gateway.fetch_order(
                    exchange_order_id,
                    local_order.symbol
                )

                # 构建 Order 对象（用于 update_order_from_exchange）
                exchange_order = Order(
                    id=exchange_order_id,
                    signal_id=local_order.signal_id,
                    exchange_order_id=exchange_order_id,
                    symbol=local_order.symbol,
                    direction=local_order.direction,
                    order_type=local_order.order_type,
                    order_role=local_order.order_role,
                    requested_qty=exchange_order_result.amount,
                    filled_qty=exchange_order_result.amount,  # fetch_order 返回的 amount 是已成交数量
                    average_exec_price=exchange_order_result.price or Decimal("0"),
                    status=exchange_order_result.status,
                    created_at=local_order.created_at,
                    updated_at=int(time.time() * 1000),
                )

                # 推进本地订单状态
                updated_order = await self._lifecycle.update_order_from_exchange(exchange_order)

                logger.info(
                    f"✅ 对账成功: exchange_order_id={exchange_order_id}, "
                    f"本地状态={local_order.status} -> {updated_order.status}"
                )

                success_count += 1

                # P0-4：记录已成功对账的订单 ID
                successfully_reconciled_order_ids.add(local_order.id)

                # 如果在待恢复列表，清除标记
                if exchange_order_id in pending_recovery_orders:
                    self._gateway.clear_pending_recovery_order(exchange_order_id)
                    recovery_cleared_count += 1
                    logger.info(f"✅ 清除待恢复标记: exchange_order_id={exchange_order_id}")

            except Exception as e:
                logger.error(
                    f"❌ 对账失败: exchange_order_id={exchange_order_id}, "
                    f"error={e}"
                )
                failure_count += 1
                # 继续处理后续订单（不中断整轮对账）


        # ===== 阶段 2.6: PG recovery task 扫描 =====
        pg_recovery_resolved_count = 0
        pg_recovery_retrying_count = 0
        pg_recovery_failed_count = 0

        if self._execution_recovery_repository:
            try:
                active_tasks = await self._execution_recovery_repository.list_active()
                logger.info(f"PG recovery: 读取活跃任务: 总计={len(active_tasks)}")

                for task in active_tasks:
                    task_id = task["id"]
                    recovery_type = task["recovery_type"]
                    intent_id = task["intent_id"]
                    related_order_id = task.get("related_order_id")
                    related_exchange_order_id = task.get("related_exchange_order_id")
                    symbol = task.get("symbol")
                    retry_count = task.get("retry_count", 0)

                    # 第一版只处理 replace_sl_failed
                    if recovery_type != "replace_sl_failed":
                        logger.info(
                            f"PG recovery: 跳过不支持的恢复类型: "
                            f"task_id={task_id}, recovery_type={recovery_type}"
                        )
                        continue

                    logger.info(
                        f"PG recovery: 处理任务: task_id={task_id}, "
                        f"intent_id={intent_id}, symbol={symbol}, retry_count={retry_count}"
                    )

                    # 查询关联订单状态
                    if related_order_id:
                        local_order = await self._repository.get_order(related_order_id)
                    else:
                        local_order = None

                    # 判断是否已自然收敛（订单终态）
                    terminal_statuses = {
                        OrderStatus.CANCELED,
                        OrderStatus.FILLED,
                        OrderStatus.REJECTED,
                        OrderStatus.EXPIRED,
                    }

                    if local_order and local_order.status in terminal_statuses:
                        # 订单已终态，可安全结束恢复任务
                        now_ms = int(time.time() * 1000)
                        await self._execution_recovery_repository.mark_resolved(
                            task_id=task_id,
                            resolved_at=now_ms,
                            error_message="订单已自然收敛至终态",
                        )
                        pg_recovery_resolved_count += 1
                        logger.info(
                            f"PG recovery: ✅ 标记已解决: task_id={task_id}, "
                            f"order_status={local_order.status}"
                        )
                    else:
                        # 订单未终态，检查重试次数
                        if not should_retry(retry_count):
                            # 达到最大重试次数，标记失败
                            await self._execution_recovery_repository.mark_failed(
                                task_id=task_id,
                                error_message=f"达到最大重试次数 {MAX_RECOVERY_RETRY_COUNT}",
                            )
                            pg_recovery_failed_count += 1
                            logger.warning(
                                f"PG recovery: ❌ 标记失败: task_id={task_id}, "
                                f"retry_count={retry_count}, max_retries={MAX_RECOVERY_RETRY_COUNT}"
                            )
                        else:
                            # 标记重试中，使用指数退避策略
                            now_ms = int(time.time() * 1000)
                            next_retry_at = calculate_next_retry_at(now_ms, retry_count)
                            new_retry_count = retry_count + 1

                            await self._execution_recovery_repository.mark_retrying(
                                task_id=task_id,
                                retry_count=new_retry_count,
                                next_retry_at=next_retry_at,
                            )
                            pg_recovery_retrying_count += 1
                            logger.info(
                                f"PG recovery: ⏸️ 标记重试中: task_id={task_id}, "
                                f"retry_count={new_retry_count}, next_retry_at={next_retry_at}"
                            )

            except Exception as e:
                logger.error(
                    f"PG recovery: 扫描失败: error={e}",
                    exc_info=True
                )


        # ===== 阶段 3: 生成对账摘要 =====
        end_time = int(time.time() * 1000)
        duration_ms = end_time - start_time

        summary = {
            "total_candidates": len(all_candidate_ids),
            "success_count": success_count,
            "failure_count": failure_count,
            "recovery_cleared_count": recovery_cleared_count,
            "duration_ms": duration_ms,
            "pg_recovery_resolved_count": pg_recovery_resolved_count,
            "pg_recovery_retrying_count": pg_recovery_retrying_count,
            "pg_recovery_failed_count": pg_recovery_failed_count,
        }

        logger.info("=" * 70)
        logger.info("启动对账服务执行完成")
        logger.info(f"候选订单: {summary['total_candidates']} 个")
        logger.info(f"对账成功: {summary['success_count']} 个")
        logger.info(f"对账失败: {summary['failure_count']} 个")
        logger.info(f"清除待恢复标记: {summary['recovery_cleared_count']} 个")
        logger.info(f"PG recovery: 已解决: {summary['pg_recovery_resolved_count']} 个")
        logger.info(f"PG recovery: 重试中: {summary['pg_recovery_retrying_count']} 个")
        logger.info(f"PG recovery: 已失败: {summary['pg_recovery_failed_count']} 个")
        logger.info(f"执行耗时: {summary['duration_ms']} ms")
        logger.info("=" * 70)

        return summary