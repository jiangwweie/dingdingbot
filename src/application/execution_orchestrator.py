"""
Execution Orchestrator - 执行编排器

ExecutionOrchestrator MVP 第一步：最小主链

职责：
1. 接收可执行信号
2. 调用 CapitalProtection 做前置检查
3. 创建 ExecutionIntent
4. 调用 OrderLifecycleService 创建本地主单
5. 调用 ExchangeGateway 提交 ENTRY
6. 回填 exchange_order_id
7. 推进本地执行状态

范围控制（这一步不做）：
- 不实现 TP/SL 挂载
- 不实现 entry_filled_unprotected
- 不实现 partial fill 保护逻辑
- 不实现 recovery / circuit breaker
- 不改 API 主链
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, List
import logging

from src.domain.models import (
    SignalResult,
    Order,
    OrderType,
    OrderRole,
    Direction,
    OrderStrategy,
)
from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.application.capital_protection import CapitalProtectionManager
from src.application.order_lifecycle_service import OrderLifecycleService
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.logger import logger


class ExecutionOrchestrator:
    """
    执行编排器

    最小职责：
    1. 信号 -> ExecutionIntent
    2. CapitalProtection 前置检查
    3. OrderLifecycleService 创建本地主单
    4. ExchangeGateway 提交 ENTRY
    5. 回填 exchange_order_id
    """

    def __init__(
        self,
        capital_protection: CapitalProtectionManager,
        order_lifecycle: OrderLifecycleService,
        gateway: ExchangeGateway,
    ):
        """
        初始化执行编排器

        Args:
            capital_protection: 资金保护管理器
            order_lifecycle: 订单生命周期服务
            gateway: 交易所网关
        """
        self._capital_protection = capital_protection
        self._order_lifecycle = order_lifecycle
        self._gateway = gateway

        # MVP 阶段：内存存储 ExecutionIntent
        # 后续可迁移到数据库持久化
        self._intents: Dict[str, ExecutionIntent] = {}

    async def execute_signal(
        self,
        signal: SignalResult,
        strategy: OrderStrategy,
    ) -> ExecutionIntent:
        """
        执行信号

        最小主链：
        1. 创建 ExecutionIntent (pending)
        2. CapitalProtection 前置检查
        3. 创建本地主单
        4. 提交 ENTRY 到交易所
        5. 回填 exchange_order_id
        6. 推进状态

        Args:
            signal: 可执行信号
            strategy: 订单策略

        Returns:
            ExecutionIntent: 执行意图（包含最终状态）
        """
        # 1. 创建 ExecutionIntent
        intent_id = f"intent_{uuid.uuid4().hex[:12]}"
        intent = ExecutionIntent(
            id=intent_id,
            signal=signal,
            status=ExecutionIntentStatus.PENDING,
        )
        self._intents[intent_id] = intent

        logger.info(
            f"[ExecutionOrchestrator] 开始执行信号: "
            f"intent_id={intent_id}, symbol={signal.symbol}, direction={signal.direction}"
        )

        # 2. CapitalProtection 前置检查
        check_result = await self._capital_protection.pre_order_check(
            symbol=signal.symbol,
            order_type=OrderType.MARKET,  # ENTRY 使用市价单
            amount=signal.suggested_position_size,
            price=None,  # 市价单无价格
            trigger_price=None,
            stop_loss=signal.suggested_stop_loss,
        )

        if not check_result.allowed:
            # 拦截：更新 ExecutionIntent 状态
            intent.status = ExecutionIntentStatus.BLOCKED
            intent.blocked_reason = check_result.reason
            intent.blocked_message = check_result.reason_message
            intent.updated_at = int(datetime.now(timezone.utc).timestamp() * 1000)

            logger.warning(
                f"[ExecutionOrchestrator] 信号被拦截: "
                f"intent_id={intent_id}, reason={check_result.reason}, "
                f"message={check_result.reason_message}"
            )

            return intent

        logger.info(
            f"[ExecutionOrchestrator] 前置检查通过: intent_id={intent_id}"
        )

        # 3. 创建本地主单
        try:
            order = await self._order_lifecycle.create_order(
                strategy=strategy,
                signal_id=f"sig_{uuid.uuid4().hex[:12]}",
                symbol=signal.symbol,
                direction=signal.direction,
                total_qty=signal.suggested_position_size,
                initial_sl_rr=Decimal("-1.0"),  # MVP 阶段暂不实现 SL
                tp_targets=[],  # MVP 阶段暂不实现 TP
            )

            logger.info(
                f"[ExecutionOrchestrator] 本地主单创建成功: "
                f"intent_id={intent_id}, order_id={order.id}"
            )

        except Exception as e:
            # 创建订单失败
            intent.status = ExecutionIntentStatus.FAILED
            intent.failed_reason = f"创建本地订单失败: {str(e)}"
            intent.updated_at = int(datetime.now(timezone.utc).timestamp() * 1000)

            logger.error(
                f"[ExecutionOrchestrator] 创建本地订单失败: "
                f"intent_id={intent_id}, error={e}"
            )

            return intent

        # 4. 提交 ENTRY 到交易所
        try:
            # 确定买卖方向
            side = "buy" if signal.direction == Direction.LONG else "sell"

            # 提交市价单
            placement_result = await self._gateway.place_order(
                symbol=signal.symbol,
                order_type="market",
                side=side,
                amount=signal.suggested_position_size,
                price=None,
                trigger_price=None,
                reduce_only=False,
                client_order_id=order.id,  # 使用本地订单 ID 作为客户端订单 ID
            )

            # P1 修复 1: 检查 placement_result.is_success
            if not placement_result.is_success:
                # 提交失败（但未抛异常）
                intent.status = ExecutionIntentStatus.FAILED
                intent.order_id = order.id
                intent.failed_reason = (
                    f"交易所返回失败: {placement_result.error_code} - "
                    f"{placement_result.error_message}"
                )
                intent.updated_at = int(datetime.now(timezone.utc).timestamp() * 1000)

                logger.error(
                    f"[ExecutionOrchestrator] 交易所返回失败: "
                    f"intent_id={intent_id}, order_id={order.id}, "
                    f"error_code={placement_result.error_code}, "
                    f"error_message={placement_result.error_message}"
                )

                return intent

            logger.info(
                f"[ExecutionOrchestrator] 交易所订单提交成功: "
                f"intent_id={intent_id}, exchange_order_id={placement_result.exchange_order_id}, "
                f"status={placement_result.status}"
            )

            # 5. 回填 exchange_order_id
            await self._order_lifecycle.submit_order(
                order.id,
                exchange_order_id=placement_result.exchange_order_id,
            )

            # P1 修复 2: 按 placement_result.status 推进本地订单
            # 不要无条件 confirm_order() -> OPEN
            from src.domain.models import OrderStatus

            if placement_result.status == OrderStatus.OPEN:
                # 订单挂单成功，推进到 OPEN
                await self._order_lifecycle.confirm_order(order.id)

            elif placement_result.status == OrderStatus.FILLED:
                # 市价单直接完全成交
                # 需要先推进到 OPEN，再推进到 FILLED
                await self._order_lifecycle.confirm_order(order.id)
                await self._order_lifecycle.update_order_filled(
                    order.id,
                    filled_qty=placement_result.amount,
                    average_exec_price=placement_result.price or Decimal("0"),
                )

            elif placement_result.status == OrderStatus.PARTIALLY_FILLED:
                # 市价单部分成交
                # 需要先推进到 OPEN，再推进到 PARTIALLY_FILLED
                await self._order_lifecycle.confirm_order(order.id)

                # TODO: OrderPlacementResult 没有 filled_qty 和 average_exec_price 字段
                # 实际场景中，部分成交信息会通过 WebSocket 推送获取
                # 这里暂时无法推进到 PARTIALLY_FILLED，需要等待 WebSocket 推送更新
                logger.warning(
                    f"[ExecutionOrchestrator] 订单部分成交，等待 WebSocket 推送更新成交信息: "
                    f"intent_id={intent_id}, order_id={order.id}, "
                    f"exchange_order_id={placement_result.exchange_order_id}"
                )

            elif placement_result.status in (OrderStatus.CANCELED, OrderStatus.REJECTED):
                # 订单被取消或拒绝
                if placement_result.status == OrderStatus.CANCELED:
                    await self._order_lifecycle.cancel_order(
                        order.id,
                        reason="Exchange canceled the order"
                    )
                else:
                    # REJECTED: 标记为失败
                    intent.status = ExecutionIntentStatus.FAILED
                    intent.order_id = order.id
                    intent.failed_reason = "交易所拒绝订单"
                    intent.updated_at = int(datetime.now(timezone.utc).timestamp() * 1000)

                    logger.error(
                        f"[ExecutionOrchestrator] 交易所拒绝订单: "
                        f"intent_id={intent_id}, order_id={order.id}"
                    )

                    return intent

            else:
                # 其他状态（如 PENDING），记录警告但不推进
                logger.warning(
                    f"[ExecutionOrchestrator] 未处理的订单状态: "
                    f"intent_id={intent_id}, order_id={order.id}, "
                    f"status={placement_result.status}"
                )

            # 更新 ExecutionIntent 状态
            intent.status = ExecutionIntentStatus.COMPLETED
            intent.order_id = order.id
            intent.exchange_order_id = placement_result.exchange_order_id
            intent.updated_at = int(datetime.now(timezone.utc).timestamp() * 1000)

            logger.info(
                f"[ExecutionOrchestrator] 执行完成: "
                f"intent_id={intent_id}, order_id={order.id}, "
                f"exchange_order_id={placement_result.exchange_order_id}, "
                f"final_status={placement_result.status}"
            )

            return intent

        except Exception as e:
            # 提交交易所失败
            intent.status = ExecutionIntentStatus.FAILED
            intent.order_id = order.id
            intent.failed_reason = f"提交交易所失败: {str(e)}"
            intent.updated_at = int(datetime.now(timezone.utc).timestamp() * 1000)

            logger.error(
                f"[ExecutionOrchestrator] 提交交易所失败: "
                f"intent_id={intent_id}, order_id={order.id}, error={e}"
            )

            return intent

    def get_intent(self, intent_id: str) -> Optional[ExecutionIntent]:
        """
        获取执行意图

        Args:
            intent_id: 执行意图 ID

        Returns:
            ExecutionIntent 或 None
        """
        return self._intents.get(intent_id)

    def list_intents(
        self,
        status: Optional[ExecutionIntentStatus] = None,
    ) -> List[ExecutionIntent]:
        """
        列出执行意图

        Args:
            status: 可选的状态过滤

        Returns:
            执行意图列表
        """
        if status:
            return [
                intent for intent in self._intents.values()
                if intent.status == status
            ]
        return list(self._intents.values())
