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
8. P0-2: 熔断机制与待恢复记录管理
9. P0-6: pending_recovery / circuit_breaker 告警通知

范围控制（这一步不做）：
- 不实现 TP/SL 挂载（已在 MVP-Protected-Position 实现）
- 不实现 entry_filled_unprotected
- 不实现 partial fill 保护逻辑（已在 MVP-Protected-Position-Step2 实现）
- 不改 API 主链
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, List, Any, Callable

from src.domain.models import (
    SignalResult,
    Order,
    OrderType,
    OrderRole,
    Direction,
    OrderStrategy,
    OrderStatus,
)
from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.application.capital_protection import CapitalProtectionManager
from src.application.order_lifecycle_service import OrderLifecycleService
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.logger import logger
from src.infrastructure.repository_ports import ExecutionIntentRepositoryPort


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
        intent_repository: Optional[ExecutionIntentRepositoryPort] = None,
        notifier: Optional[Callable[[str, str], Any]] = None,  # P0-6: 可选告警回调
        pending_recovery_repository: Optional[Any] = None,  # P0-7: 可选 pending_recovery 持久化
    ):
        """
        初始化执行编排器

        Args:
            capital_protection: 资金保护管理器
            order_lifecycle: 订单生命周期服务
            gateway: 交易所网关
            intent_repository: 执行意图仓储（可选，未提供时退回内存态）
            notifier: P0-6 告警回调函数（可选），签名 async (title: str, message: str) -> None
            pending_recovery_repository: P0-7 pending_recovery 持久化仓储（可选）
        """
        self._capital_protection = capital_protection
        self._order_lifecycle = order_lifecycle
        self._gateway = gateway
        self._intent_repository = intent_repository
        self._notifier = notifier  # P0-6: 保存告警回调
        self._pending_recovery_repository = pending_recovery_repository  # P0-7: 保存持久化仓储

        # 热缓存：当 PG 仓储可用时，内存仅用于当前进程快速回读与回退。
        self._intents: Dict[str, ExecutionIntent] = {}

        # P0-2：熔断机制 + 待恢复记录
        self._circuit_breaker_symbols: set = set()  # 熔断的 symbol 集合
        self._pending_recovery: Dict[str, Dict[str, Any]] = {}  # order_id -> error info

        # MVP-Protected-Position-Step2: 注册 ENTRY 部分成交回调
        self._order_lifecycle.set_entry_partially_filled_callback(
            self._handle_entry_partially_filled
        )

    async def _save_intent(self, intent: ExecutionIntent) -> None:
        """保存执行意图到本地缓存，并按需持久化到仓储。"""
        self._intents[intent.id] = intent
        if self._intent_repository is not None:
            await self._intent_repository.save(intent)

    def _cache_intent(self, intent: ExecutionIntent) -> ExecutionIntent:
        """将 ExecutionIntent 写入热缓存并返回自身。"""
        self._intents[intent.id] = intent
        return intent

    async def _load_intent(self, intent_id: str) -> Optional[ExecutionIntent]:
        """按意图 ID 获取执行意图，优先仓储，回退本地缓存。"""
        if self._intent_repository is not None:
            intent = await self._intent_repository.get(intent_id)
            if intent is not None:
                return self._cache_intent(intent)

        return self._intents.get(intent_id)

    async def _load_intent_by_signal_id(self, signal_id: str) -> Optional[ExecutionIntent]:
        """按信号 ID 获取执行意图，优先仓储，回退本地缓存。"""
        if self._intent_repository is not None:
            intent = await self._intent_repository.get_by_signal_id(signal_id)
            if intent is not None:
                return self._cache_intent(intent)

        for stored_intent in self._intents.values():
            if stored_intent.signal_id == signal_id:
                return stored_intent
        return None

    async def _load_intent_by_order_id(self, order_id: str) -> Optional[ExecutionIntent]:
        """按订单 ID 获取执行意图，优先仓储，回退本地缓存。"""
        if self._intent_repository is not None:
            intent = await self._intent_repository.get_by_order_id(order_id)
            if intent is not None:
                return self._cache_intent(intent)

        for stored_intent in self._intents.values():
            if stored_intent.order_id == order_id:
                return stored_intent
        return None

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
        signal_id = f"sig_{uuid.uuid4().hex[:12]}"
        # P1 修复：深拷贝 strategy，确保 intent 内的快照不受原对象后续修改影响
        # 这样 partial-fill 回调读取的是创建意图时的策略内容，而非变更后的配置
        strategy_snapshot = strategy.model_copy(deep=True) if strategy else None
        intent = ExecutionIntent(
            id=intent_id,
            signal_id=signal_id,
            signal=signal,
            status=ExecutionIntentStatus.PENDING,
            strategy=strategy_snapshot,
        )
        await self._save_intent(intent)

        logger.info(
            f"[ExecutionOrchestrator] 开始执行信号: "
            f"intent_id={intent_id}, symbol={signal.symbol}, direction={signal.direction}"
        )

        # P0-3：熔断检查（在 CapitalProtection 前置检查前）
        if self.is_symbol_blocked(signal.symbol):
            intent.status = ExecutionIntentStatus.BLOCKED
            intent.blocked_reason = "CIRCUIT_BREAKER"
            intent.blocked_message = f"symbol 熔断中，拒绝新信号: {signal.symbol}"
            intent.updated_at = int(datetime.now(timezone.utc).timestamp() * 1000)

            logger.warning(
                f"[ExecutionOrchestrator] 信号被熔断拦截: "
                f"intent_id={intent_id}, symbol={signal.symbol}"
            )

            await self._save_intent(intent)
            return intent

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

            await self._save_intent(intent)
            return intent

        logger.info(
            f"[ExecutionOrchestrator] 前置检查通过: intent_id={intent_id}"
        )

        # 3. 创建本地主单
        try:
            order = await self._order_lifecycle.create_order(
                strategy=strategy,
                signal_id=signal_id,
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

            await self._save_intent(intent)
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

                await self._save_intent(intent)
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

                # MVP-Protected-Position: ENTRY 成交后挂载保护单
                logger.info(
                    f"[ExecutionOrchestrator] ENTRY 成交，开始挂载保护单: "
                    f"intent_id={intent_id}, order_id={order.id}"
                )

                # 更新状态为 PROTECTING
                intent.status = ExecutionIntentStatus.PROTECTING
                intent.order_id = order.id
                intent.exchange_order_id = placement_result.exchange_order_id
                intent.updated_at = int(datetime.now(timezone.utc).timestamp() * 1000)

                # 从数据库重新加载订单（获取最新的 average_exec_price）
                entry_order_filled = await self._order_lifecycle._repository.get_order(order.id)

                # 挂载保护单
                protection_result = await self._mount_protection_orders(
                    intent=intent,
                    entry_order=entry_order_filled,
                    signal=signal,
                    strategy=strategy,
                )

                if protection_result["success"]:
                    # 所有保护单成功
                    intent.status = ExecutionIntentStatus.COMPLETED
                    logger.info(
                        f"[ExecutionOrchestrator] 保护单挂载成功: "
                        f"intent_id={intent_id}, "
                        f"tp_orders={len(protection_result['tp_orders'])}, "
                        f"sl_order={protection_result['sl_order']}"
                    )
                else:
                    # 保护单部分失败
                    intent.status = ExecutionIntentStatus.FAILED
                    intent.failed_reason = f"保护单挂载失败: {protection_result['error']}"
                    logger.error(
                        f"[ExecutionOrchestrator] 保护单挂载失败: "
                        f"intent_id={intent_id}, error={protection_result['error']}"
                    )

                await self._save_intent(intent)
                return intent

            elif placement_result.status == OrderStatus.PARTIALLY_FILLED:
                # P1-5 修复：禁止落盘"PARTIALLY_FILLED 但 filled_qty=0"的自相矛盾订单事实
                # 场景：ExchangeGateway.place_order() 返回 status=PARTIALLY_FILLED，但缺少真实成交数量/均价
                # 正确做法：本地主单停留在 OPEN（已确认挂单），等待 WebSocket/启动对账推进真实 PARTIALLY_FILLED/FILLED
                await self._order_lifecycle.confirm_order(order.id)

                # 注意：不调用 update_order_partially_filled(filled_qty=0)
                # 原因：OrderPlacementResult 没有 filled_qty 和 average_exec_price 字段
                # 使用默认值 0 会伪造"部分成交但成交量为 0"的自相矛盾事实
                # 正确流程：等待 WebSocket 推送真实成交信息后再推进状态

                logger.info(
                    f"[ExecutionOrchestrator] 订单已提交（交易所返回部分成交状态，等待 WebSocket 推送真实成交信息）: "
                    f"intent_id={intent_id}, order_id={order.id}, "
                    f"exchange_order_id={placement_result.exchange_order_id}"
                )

                # P1 修复：部分成交不应标记为 COMPLETED
                # 当前阶段：订单部分成交，尚未完全受保护
                # 使用 SUBMITTED 表示已提交但未完成
                intent.status = ExecutionIntentStatus.SUBMITTED
                intent.order_id = order.id
                intent.exchange_order_id = placement_result.exchange_order_id
                intent.updated_at = int(datetime.now(timezone.utc).timestamp() * 1000)

                logger.info(
                    f"[ExecutionOrchestrator] 执行意图状态: SUBMITTED（部分成交，等待后续处理）"
                )

                await self._save_intent(intent)
                return intent  # P1-1 修复：必须 return，避免落入通用尾部覆盖状态

            elif placement_result.status in (OrderStatus.CANCELED, OrderStatus.REJECTED):
                # 订单被取消或拒绝
                if placement_result.status == OrderStatus.CANCELED:
                    await self._order_lifecycle.cancel_order(
                        order.id,
                        reason="Exchange canceled the order"
                    )

                    # P1 修复：订单被取消，标记为失败
                    intent.status = ExecutionIntentStatus.FAILED
                    intent.order_id = order.id
                    intent.failed_reason = "交易所取消订单"
                    intent.updated_at = int(datetime.now(timezone.utc).timestamp() * 1000)

                    logger.error(
                        f"[ExecutionOrchestrator] 交易所取消订单: "
                        f"intent_id={intent_id}, order_id={order.id}"
                    )

                    await self._save_intent(intent)
                    return intent  # P1-1 修复：必须 return，避免落入通用尾部覆盖状态

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

                    await self._save_intent(intent)
                    return intent  # P1-1 修复：必须 return，避免落入通用尾部覆盖状态

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

            await self._save_intent(intent)
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

            await self._save_intent(intent)
            return intent

    async def _mount_protection_orders(
        self,
        intent: ExecutionIntent,
        entry_order: Order,
        signal: SignalResult,
        strategy: OrderStrategy,
    ) -> Dict[str, Any]:
        """
        挂载保护单（TP/SL）

        MVP-Protected-Position: ENTRY 成交后自动挂载保护单

        Args:
            intent: 执行意图
            entry_order: ENTRY 订单（已成交）
            signal: 信号
            strategy: 订单策略

        Returns:
            Dict[str, Any]: 挂载结果
                - success: 是否全部成功
                - tp_orders: TP 订单列表
                - sl_order: SL 订单（或 None）
                - error: 错误信息（如果失败）
        """
        from src.domain.order_manager import OrderManager
        from src.domain.models import Position

        try:
            # 创建临时 Position 对象（用于生成 TP/SL 订单）
            position = Position(
                id=f"pos_{entry_order.signal_id}",
                signal_id=entry_order.signal_id,
                symbol=entry_order.symbol,
                direction=entry_order.direction,
                entry_price=entry_order.average_exec_price or entry_order.price,
                current_qty=entry_order.filled_qty,
            )

            positions_map = {entry_order.signal_id: position}

            # 使用 OrderManager 生成 TP/SL 订单
            order_manager = OrderManager()
            protection_orders = order_manager._generate_tp_sl_orders(
                filled_entry=entry_order,
                positions_map=positions_map,
                strategy=strategy,
                tp_targets=strategy.tp_targets if strategy else None,
            )

            logger.info(
                f"[ExecutionOrchestrator] 生成保护单: "
                f"intent_id={intent.id}, "
                f"总计={len(protection_orders)} 个"
            )

            # 提交保护单到交易所
            tp_orders = []
            sl_order = None
            failed_orders = []

            for prot_order in protection_orders:
                try:
                    # 修改订单状态为 CREATED（OrderManager 生成的订单状态是 OPEN）
                    prot_order.status = OrderStatus.CREATED

                    # P1 修复：使用 OrderLifecycleService 正式链保存订单
                    # 而不是直接调用 repository.save()
                    await self._order_lifecycle._repository.save(prot_order)

                    # 创建状态机（触发审计日志和变更通知）
                    self._order_lifecycle._get_or_create_state_machine(prot_order)

                    # 提交到交易所
                    side = "sell" if entry_order.direction == Direction.LONG else "buy"

                    placement_result = await self._gateway.place_order(
                        symbol=prot_order.symbol,
                        order_type="limit" if prot_order.order_type == OrderType.LIMIT else "stop_market",
                        side=side,
                        amount=prot_order.requested_qty,
                        price=prot_order.price,
                        trigger_price=prot_order.trigger_price,
                        reduce_only=True,  # 保护单必须设置 reduce_only
                        client_order_id=prot_order.id,
                    )

                    if placement_result.is_success:
                        # P1 修复：使用 OrderLifecycleService 正式链提交订单
                        # 1. 回填 exchange_order_id
                        await self._order_lifecycle.submit_order(
                            prot_order.id,
                            exchange_order_id=placement_result.exchange_order_id,
                        )

                        # 2. 推进到 OPEN 状态
                        await self._order_lifecycle.confirm_order(prot_order.id)

                        if prot_order.order_role in [OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5]:
                            tp_orders.append(prot_order)
                        elif prot_order.order_role == OrderRole.SL:
                            sl_order = prot_order

                        logger.info(
                            f"[ExecutionOrchestrator] 保护单提交成功: "
                            f"order_id={prot_order.id}, "
                            f"role={prot_order.order_role}, "
                            f"exchange_order_id={placement_result.exchange_order_id}"
                        )
                    else:
                        # 提交失败
                        failed_orders.append({
                            "order": prot_order,
                            "error": f"{placement_result.error_code}: {placement_result.error_message}",
                        })
                        logger.error(
                            f"[ExecutionOrchestrator] 保护单提交失败: "
                            f"order_id={prot_order.id}, "
                            f"role={prot_order.order_role}, "
                            f"error={placement_result.error_code}"
                        )

                except Exception as e:
                    failed_orders.append({
                        "order": prot_order,
                        "error": str(e),
                    })
                    logger.error(
                        f"[ExecutionOrchestrator] 保护单提交异常: "
                        f"order_id={prot_order.id}, "
                        f"role={prot_order.order_role}, "
                        f"error={e}"
                    )

            # 判断是否全部成功
            if failed_orders:
                return {
                    "success": False,
                    "tp_orders": tp_orders,
                    "sl_order": sl_order,
                    "error": f"{len(failed_orders)} 个保护单失败: " + "; ".join(
                        f"{f['order'].order_role}: {f['error']}" for f in failed_orders
                    ),
                }
            else:
                return {
                    "success": True,
                    "tp_orders": tp_orders,
                    "sl_order": sl_order,
                    "error": None,
                }

        except Exception as e:
            logger.error(
                f"[ExecutionOrchestrator] 挂载保护单异常: "
                f"intent_id={intent.id}, error={e}"
            )
            return {
                "success": False,
                "tp_orders": [],
                "sl_order": None,
                "error": str(e),
            }

    async def _handle_entry_partially_filled(
        self,
        entry_order: Order,
    ) -> None:
        """
        处理 ENTRY 部分成交后的保护单挂载（增量补挂机制）

        核心逻辑：
        1. 计算 filled_qty_total（ENTRY 已成交量）
        2. 计算 protected_qty_total（已存在保护单覆盖的数量）
        3. delta_qty = filled_qty_total - protected_qty_total
        4. 只有 delta_qty > 0 时，才为新增成交量补挂 TP/SL

        幂等保证：
        - 相同 filled_qty 的重复回调，delta_qty = 0，直接返回
        - 已存在保护单不修改、不撤单，只补缺口

        Args:
            entry_order: ENTRY 订单（已部分成交）
        """
        from src.domain.order_manager import OrderManager
        from src.domain.models import Position

        logger.info(
            f"[ExecutionOrchestrator] 开始处理 ENTRY 部分成交: "
            f"order_id={entry_order.id}, filled_qty={entry_order.filled_qty}, "
            f"average_exec_price={entry_order.average_exec_price}"
        )

        # P1-2 修复：使用 repo-first 查找对应的 ExecutionIntent
        intent = await self._load_intent_by_order_id(entry_order.id)

        if not intent:
            logger.warning(
                f"[ExecutionOrchestrator] 未找到对应的 ExecutionIntent: "
                f"order_id={entry_order.id}"
            )
            return

        # 获取当前 ENTRY 的所有子保护单
        all_orders = await self._order_lifecycle._repository.get_orders_by_signal(
            entry_order.signal_id
        )

        existing_protection_orders = [
            o for o in all_orders
            if o.parent_order_id == entry_order.id
            and o.order_role in [OrderRole.SL, OrderRole.TP1, OrderRole.TP2,
                                  OrderRole.TP3, OrderRole.TP4, OrderRole.TP5]
        ]

        # P1 修复：只统计"仍然有效"的保护单
        # 可计入的状态：SUBMITTED, OPEN, PARTIALLY_FILLED, FILLED
        # 不计入的状态：CREATED（尚未提交）, CANCELED, REJECTED, EXPIRED
        # FILLED 计入理由：已成交的保护单已完成保护职责，其 requested_qty 已生效
        valid_protection_statuses = {
            OrderStatus.SUBMITTED,
            OrderStatus.OPEN,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
        }
        valid_protection_orders = [
            o for o in existing_protection_orders
            if o.status in valid_protection_statuses
        ]

        # P1-6 修复：识别已有有效 SL，保证单一 SL 覆盖全仓
        sl_orders = [o for o in valid_protection_orders if o.order_role == OrderRole.SL]
        tp_orders = [o for o in valid_protection_orders if o.order_role != OrderRole.SL]

        # P1-6 止血：如果存在多张有效 SL，报错并返回（不在本任务修复历史脏数据）
        if len(sl_orders) > 1:
            logger.error(
                f"[ExecutionOrchestrator] 检测到多张有效 SL 订单（违反单一 SL 约束）: "
                f"order_id={entry_order.id}, sl_count={len(sl_orders)}, "
                f"sl_order_ids={[o.id for o in sl_orders]}"
            )
            return

        # 计算 protected_qty_total：已保护数量
        # P1-6 修复：使用 SL 订单的 requested_qty（单一 SL 覆盖全仓）
        if sl_orders:
            # SL 订单的 requested_qty 作为主口径
            protected_qty_total = sl_orders[0].requested_qty
        elif tp_orders:
            # 没有 SL 时，用 TP 订单的 requested_qty 总和作为兜底
            protected_qty_total = sum(
                (o.requested_qty for o in tp_orders),
                Decimal("0")
            )
        else:
            protected_qty_total = Decimal("0")

        # 计算 delta_qty：新增成交量
        filled_qty_total = entry_order.filled_qty
        delta_qty = filled_qty_total - protected_qty_total

        logger.info(
            f"[ExecutionOrchestrator] 增量补挂计算: "
            f"filled_qty_total={filled_qty_total}, "
            f"protected_qty_total={protected_qty_total}, "
            f"delta_qty={delta_qty}"
        )

        # 幂等判断：delta_qty <= 0 时直接返回，不补挂
        if delta_qty <= Decimal("0"):
            logger.info(
                f"[ExecutionOrchestrator] 无新增成交量，跳过补挂: "
                f"order_id={entry_order.id}, delta_qty={delta_qty}"
            )
            return

        # 为新增成交量补挂保护单
        try:
            # P1-3 修复：检查 intent.strategy，严禁退化默认 exit
            if intent.strategy is None:
                logger.warning(
                    f"[ExecutionOrchestrator] intent 无策略快照，跳过保护单生成: "
                    f"intent_id={intent.id}, order_id={entry_order.id}"
                )
                return

            # 创建临时 Position 对象（用于生成保护单）
            # 注意：current_qty 使用 delta_qty，只为新增部分生成保护单
            position = Position(
                id=f"pos_{entry_order.signal_id}",
                signal_id=entry_order.signal_id,
                symbol=entry_order.symbol,
                direction=entry_order.direction,
                entry_price=entry_order.average_exec_price or entry_order.price,
                current_qty=delta_qty,  # 只为新增成交量生成保护单
            )

            positions_map = {entry_order.signal_id: position}

            # 创建临时 ENTRY 订单对象（用于生成保护单）
            # 只包含新增成交量部分
            # P1 修复：price 使用 average_exec_price or price fallback，保留原有语义
            entry_price_anchor = entry_order.average_exec_price or entry_order.price
            delta_entry = Order(
                id=entry_order.id,
                signal_id=entry_order.signal_id,
                symbol=entry_order.symbol,
                direction=entry_order.direction,
                order_type=entry_order.order_type,
                order_role=entry_order.order_role,
                requested_qty=delta_qty,
                filled_qty=delta_qty,
                average_exec_price=entry_order.average_exec_price,
                price=entry_price_anchor,
                created_at=entry_order.created_at,
                updated_at=entry_order.updated_at,
            )

            # 使用 OrderManager 生成保护单
            # P1-3 修复：必须使用 intent.strategy（已在上文检查非空）
            order_manager = OrderManager()
            all_protection_orders = order_manager._generate_tp_sl_orders(
                filled_entry=delta_entry,
                positions_map=positions_map,
                strategy=intent.strategy,  # 使用 intent 中冻结的 strategy snapshot
                tp_targets=intent.strategy.tp_targets,  # P1-3 修复：必须从 strategy 获取
            )

            # P1-6 修复：分离 TP 和 SL 订单
            # 只为 delta_qty 生成 TP 订单，SL 单独处理（保证单一 SL 覆盖全仓）
            tp_orders_to_submit = [o for o in all_protection_orders if o.order_role != OrderRole.SL]
            sl_order_generated = next((o for o in all_protection_orders if o.order_role == OrderRole.SL), None)

            logger.info(
                f"[ExecutionOrchestrator] 生成增量保护单: "
                f"intent_id={intent.id}, "
                f"TP 订单={len(tp_orders_to_submit)} 个, "
                f"SL 订单={'有' if sl_order_generated else '无'}, "
                f"delta_qty={delta_qty}"
            )

            # P0-1 修复：处理 SL 订单（撤旧挂新，保证交易所侧覆盖全仓）
            if sl_orders:
                # 已有 SL：撤掉旧 SL（交易所 + 本地），创建新 SL 覆盖全仓
                existing_sl = sl_orders[0]

                # P0-1：撤销交易所侧旧 SL
                if existing_sl.exchange_order_id:
                    try:
                        await self._gateway.cancel_order(
                            exchange_order_id=existing_sl.exchange_order_id,
                            symbol=existing_sl.symbol,
                        )
                        logger.info(
                            f"[ExecutionOrchestrator] 已撤销交易所侧旧 SL: "
                            f"order_id={existing_sl.id}, "
                            f"exchange_order_id={existing_sl.exchange_order_id}"
                        )
                    except Exception as e:
                        logger.error(
                            f"[ExecutionOrchestrator] 撤销交易所侧旧 SL 失败，停止继续动作: "
                            f"order_id={existing_sl.id}, "
                            f"exchange_order_id={existing_sl.exchange_order_id}, "
                            f"symbol={existing_sl.symbol}, error={e}",
                            exc_info=True
                        )

                        # P0-2：标记待恢复
                        self._pending_recovery[existing_sl.id] = {
                            "order_id": existing_sl.id,
                            "exchange_order_id": existing_sl.exchange_order_id,
                            "symbol": existing_sl.symbol,
                            "error": str(e),
                            "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
                        }

                        # P0-7：持久化到 repository（如果可用）
                        if self._pending_recovery_repository is not None:
                            try:
                                await self._pending_recovery_repository.save(
                                    self._pending_recovery[existing_sl.id]
                                )
                            except Exception as repo_error:
                                logger.error(
                                    f"[ExecutionOrchestrator] 持久化 pending_recovery 失败: "
                                    f"error={repo_error}",
                                    exc_info=True
                                )

                        # P0-2：触发熔断（该 symbol）
                        self._circuit_breaker_symbols.add(existing_sl.symbol)
                        logger.error(
                            f"[ExecutionOrchestrator] 已触发熔断: symbol={existing_sl.symbol}, "
                            f"待恢复订单={existing_sl.id}"
                        )

                        # P0-6：发送告警通知
                        if self._notifier:
                            try:
                                title = "[P0] Pending Recovery Triggered"
                                message = (
                                    f"symbol={existing_sl.symbol}\n"
                                    f"order_id={existing_sl.id}\n"
                                    f"exchange_order_id={existing_sl.exchange_order_id}\n"
                                    f"error={str(e)}\n"
                                    f"action=circuit_breaker_triggered"
                                )
                                await self._notifier(title, message)
                                logger.info(f"[ExecutionOrchestrator] P0-6 告警已发送: {title}")
                            except Exception as notify_error:
                                logger.error(
                                    f"[ExecutionOrchestrator] P0-6 告警发送失败（不影响主流程）: "
                                    f"error={notify_error}",
                                    exc_info=True
                                )

                        # P0-2：停止继续动作（不撤销本地 SL，不创建新 SL）
                        return

                # P0-1：撤销本地旧 SL
                try:
                    await self._order_lifecycle.cancel_order(
                        existing_sl.id,
                        reason="P0: replace SL to cover increased fill"
                    )
                    logger.info(
                        f"[ExecutionOrchestrator] 已撤销本地旧 SL: "
                        f"order_id={existing_sl.id}"
                    )
                except Exception as e:
                    logger.error(
                        f"[ExecutionOrchestrator] 撤销本地旧 SL 失败: "
                        f"order_id={existing_sl.id}, error={e}",
                        exc_info=True
                    )

                # P0-1：创建新 SL（数量=filled_qty_total，覆盖全仓）
                if sl_order_generated:
                    sl_order_generated.requested_qty = filled_qty_total
                    tp_orders_to_submit.append(sl_order_generated)
                    logger.info(
                        f"[ExecutionOrchestrator] 创建新 SL 订单（替换旧 SL）: "
                        f"order_id={sl_order_generated.id}, "
                        f"qty={filled_qty_total}（覆盖全仓）"
                    )

            elif sl_order_generated:
                # 没有 SL：创建新的 SL（数量=filled_qty_total）
                sl_order_generated.requested_qty = filled_qty_total  # 覆盖全仓
                tp_orders_to_submit.append(sl_order_generated)  # 加入提交列表
                logger.info(
                    f"[ExecutionOrchestrator] 创建新 SL 订单: "
                    f"order_id={sl_order_generated.id}, "
                    f"qty={filled_qty_total}（覆盖全仓）"
                )

            # 提交保护单到交易所（只提交 TP 订单 + 可能的新 SL）
            for prot_order in tp_orders_to_submit:
                try:
                    # 设置 parent_order_id，关联到 ENTRY
                    prot_order.parent_order_id = entry_order.id

                    # 修改订单状态为 CREATED
                    prot_order.status = OrderStatus.CREATED

                    # 使用 OrderLifecycleService 正式链保存订单
                    await self._order_lifecycle._repository.save(prot_order)

                    # 创建状态机
                    self._order_lifecycle._get_or_create_state_machine(prot_order)

                    # 提交到交易所
                    side = "sell" if entry_order.direction == Direction.LONG else "buy"

                    placement_result = await self._gateway.place_order(
                        symbol=prot_order.symbol,
                        order_type="limit" if prot_order.order_type == OrderType.LIMIT else "stop_market",
                        side=side,
                        amount=prot_order.requested_qty,
                        price=prot_order.price,
                        trigger_price=prot_order.trigger_price,
                        reduce_only=True,
                        client_order_id=prot_order.id,
                    )

                    if placement_result.is_success:
                        # 使用 OrderLifecycleService 正式链提交订单
                        await self._order_lifecycle.submit_order(
                            prot_order.id,
                            exchange_order_id=placement_result.exchange_order_id,
                        )

                        await self._order_lifecycle.confirm_order(prot_order.id)

                        logger.info(
                            f"[ExecutionOrchestrator] 增量保护单提交成功: "
                            f"order_id={prot_order.id}, "
                            f"role={prot_order.order_role}, "
                            f"exchange_order_id={placement_result.exchange_order_id}, "
                            f"amount={prot_order.requested_qty}"
                        )
                    else:
                        logger.error(
                            f"[ExecutionOrchestrator] 增量保护单提交失败: "
                            f"order_id={prot_order.id}, "
                            f"role={prot_order.order_role}, "
                            f"error={placement_result.error_code}"
                        )

                except Exception as e:
                    logger.error(
                        f"[ExecutionOrchestrator] 增量保护单提交异常: "
                        f"order_id={prot_order.id}, "
                        f"role={prot_order.order_role}, "
                        f"error={e}",
                        exc_info=True
                    )

            # 更新 ExecutionIntent 状态为 PARTIALLY_PROTECTED
            intent.status = ExecutionIntentStatus.PARTIALLY_PROTECTED
            intent.updated_at = int(datetime.now(timezone.utc).timestamp() * 1000)

            logger.info(
                f"[ExecutionOrchestrator] ENTRY 部分成交增量保护单挂载完成: "
                f"intent_id={intent.id}, status={intent.status}, "
                f"delta_qty={delta_qty}"
            )
            await self._save_intent(intent)

        except Exception as e:
            logger.error(
                f"[ExecutionOrchestrator] 增量保护单挂载异常: "
                f"intent_id={intent.id}, error={e}",
                exc_info=True
            )

    async def get_intent(self, intent_id: str) -> Optional[ExecutionIntent]:
        """
        获取执行意图

        Args:
            intent_id: 执行意图 ID

        Returns:
            ExecutionIntent 或 None
        """
        return await self._load_intent(intent_id)

    async def list_intents(
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
        if self._intent_repository is not None:
            intents = await self._intent_repository.list(status=status)
            for intent in intents:
                self._cache_intent(intent)
            return intents

        if status:
            return [
                intent for intent in self._intents.values()
                if intent.status == status
            ]
        return list(self._intents.values())

    def is_symbol_blocked(self, symbol: str) -> bool:
        """
        P0-2：检查 symbol 是否被熔断

        Args:
            symbol: 交易对符号

        Returns:
            True 表示被熔断，False 表示正常
        """
        return symbol in self._circuit_breaker_symbols

    def get_pending_recovery(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        P0-2/P0-7：获取待恢复记录

        Args:
            order_id: 订单 ID

        Returns:
            待恢复记录，不存在返回 None

        Note:
            优先从 repository 读取（如果可用），回填内存缓存
        """
        # P0-7：优先从 repository 读取
        if self._pending_recovery_repository is not None:
            # 注意：repository 是异步的，但这个方法是同步的
            # 这里我们返回内存缓存，调用者应该先调用 _sync_pending_recovery_from_repo()
            # 或者在启动时从 repository 加载到内存
            pass

        return self._pending_recovery.get(order_id)

    def clear_circuit_breaker(self, symbol: str) -> None:
        """
        P0-2：清除 symbol 的熔断状态

        Args:
            symbol: 交易对符号
        """
        self._circuit_breaker_symbols.discard(symbol)
        logger.info(f"[ExecutionOrchestrator] 已清除熔断: symbol={symbol}")

    async def clear_pending_recovery_async(self, order_id: str) -> None:
        """
        P0-7：清除待恢复记录（异步版本，同时删除 repository）

        Args:
            order_id: 订单 ID
        """
        # P0-7：从 repository 删除（如果可用）
        if self._pending_recovery_repository is not None:
            try:
                await self._pending_recovery_repository.delete(order_id)
            except Exception as e:
                logger.error(
                    f"[ExecutionOrchestrator] 从 repository 删除 pending_recovery 失败: "
                    f"order_id={order_id}, error={e}",
                    exc_info=True
                )

        # 删除内存缓存
        if order_id in self._pending_recovery:
            del self._pending_recovery[order_id]
            logger.info(f"[ExecutionOrchestrator] 已清除待恢复记录: order_id={order_id}")

    def clear_pending_recovery(self, order_id: str) -> None:
        """
        P0-2：清除待恢复记录（同步版本，只删除内存）

        Args:
            order_id: 订单 ID

        Note:
            这是同步版本，只删除内存缓存。
            如果需要同时删除 repository，请使用 clear_pending_recovery_async()
        """
        if order_id in self._pending_recovery:
            del self._pending_recovery[order_id]
            logger.info(f"[ExecutionOrchestrator] 已清除待恢复记录: order_id={order_id}")

    async def list_pending_recovery_async(self) -> List[Dict[str, Any]]:
        """
        P0-7：列出所有待恢复记录（异步版本，从 repository 读取）

        Returns:
            待恢复记录列表，每条记录包含 order_id, exchange_order_id, symbol, error 等字段
        """
        # P0-7：优先从 repository 读取
        if self._pending_recovery_repository is not None:
            try:
                records = await self._pending_recovery_repository.list_all()
                # 回填内存缓存
                for record in records:
                    self._pending_recovery[record["order_id"]] = record
                return records
            except Exception as e:
                logger.error(
                    f"[ExecutionOrchestrator] 从 repository 读取 pending_recovery 失败: "
                    f"error={e}",
                    exc_info=True
                )
                # 回退到内存

        # 回退到内存
        result = []
        for order_id, info in self._pending_recovery.items():
            record = {
                "order_id": order_id,
                "exchange_order_id": info.get("exchange_order_id"),
                "symbol": info.get("symbol"),
                "error": info.get("error"),
            }
            result.append(record)
        return result

    def list_pending_recovery(self) -> List[Dict[str, Any]]:
        """
        P0-4：列出所有待恢复记录（只读，同步版本）

        Returns:
            待恢复记录列表，每条记录包含 order_id, exchange_order_id, symbol, error 等字段

        Note:
            这是同步版本，只返回内存缓存。
            如果需要从 repository 读取，请使用 list_pending_recovery_async()
        """
        result = []
        for order_id, info in self._pending_recovery.items():
            record = {
                "order_id": order_id,
                "exchange_order_id": info.get("exchange_order_id"),
                "symbol": info.get("symbol"),
                "error": info.get("error"),
            }
            result.append(record)
        return result

    def list_circuit_breaker_symbols(self) -> List[str]:
        """
        P0-7：列出所有熔断的 symbol（只读）

        Returns:
            排序后的 symbol 列表
        """
        return sorted(list(self._circuit_breaker_symbols))
