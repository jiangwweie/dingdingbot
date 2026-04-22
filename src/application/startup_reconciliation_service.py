"""
Startup Reconciliation Service - 启动对账最小版

职责：
1. 程序启动时执行一次性对账
2. 扫描本地未完成订单（SUBMITTED / OPEN / PARTIALLY_FILLED）
3. 读取待恢复订单（_pending_recovery_orders）
4. 通过 REST API 查询交易所真实状态
5. 推进本地订单状态
6. 清除待恢复标记

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
    ):
        """
        初始化启动对账服务

        Args:
            gateway: ExchangeGateway 实例
            repository: OrderRepository 实例
            lifecycle: OrderLifecycleService 实例
        """
        self._gateway = gateway
        self._repository = repository
        self._lifecycle = lifecycle

    async def run_startup_reconciliation(self) -> Dict[str, Any]:
        """
        执行启动对账

        对账流程：
        1. 扫描本地未完成订单（SUBMITTED / OPEN / PARTIALLY_FILLED）
        2. 读取待恢复订单（_pending_recovery_orders）
        3. 对每笔候选订单：
           - 通过 fetch_order() 查询交易所真实状态
           - 用 update_order_from_exchange() 推进本地状态
           - 如果在待恢复列表，清除标记

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

        # ===== 阶段 3: 生成对账摘要 =====
        end_time = int(time.time() * 1000)
        duration_ms = end_time - start_time

        summary = {
            "total_candidates": len(all_candidate_ids),
            "success_count": success_count,
            "failure_count": failure_count,
            "recovery_cleared_count": recovery_cleared_count,
            "duration_ms": duration_ms,
        }

        logger.info("=" * 70)
        logger.info("启动对账服务执行完成")
        logger.info(f"候选订单: {summary['total_candidates']} 个")
        logger.info(f"对账成功: {summary['success_count']} 个")
        logger.info(f"对账失败: {summary['failure_count']} 个")
        logger.info(f"清除待恢复标记: {summary['recovery_cleared_count']} 个")
        logger.info(f"执行耗时: {summary['duration_ms']} ms")
        logger.info("=" * 70)

        return summary