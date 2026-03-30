"""
Reconciliation Service - 启动对账服务

负责系统启动时同步本地状态与交易所状态。

修复 G-004: 对账"幽灵偏差"问题
- REST API 和 WebSocket 之间存在时差
- 对账差异不立即判定为异常，先加入宽限期
- 宽限期后二次校验，确认是否为真实异常

核心对账流程:
1. 获取本地仓位/订单列表
2. 获取交易所仓位/订单列表
3. 比对差异 → 加入 pending 列表（未确认）
4. 等待 10 秒 Grace Period
5. 二次校验 pending 列表
6. 确认的差异 → 移动到正式列表
7. 消失的差异 → 记录日志（WebSocket 延迟）
"""
import asyncio
import time
from typing import List, Dict, Any, Optional, Tuple
from decimal import Decimal

from src.domain.models import (
    ReconciliationReport,
    PositionMismatch,
    OrderMismatch,
    OrderResponse,
    OrderStatus,
    OrderType,
    OrderRole,
    Direction,
    PositionInfo,
)
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.logger import logger


class PendingPositionItem(Dict[str, Any]):
    """待确认仓位项"""
    pass


class PendingOrderItem(Dict[str, Any]):
    """待确认订单项"""
    pass


class ReconciliationService:
    """
    对账服务：同步本地状态与交易所状态

    核心职责:
    1. 启动时比对本地数据库与交易所状态
    2. 使用 Grace Period 宽限期避免"幽灵偏差"
    3. 处理孤儿订单（无主 TP/SL 订单）
    4. 生成对账报告

    G-004 修复:
    - REST API 和 WebSocket 之间存在时差
    - 对账差异不立即判定为异常，先加入宽限期
    - 宽限期后二次校验，确认是否为真实异常
    """

    def __init__(
        self,
        gateway: ExchangeGateway,
        position_mgr: Optional[Any] = None,  # PositionManager（可选）
        order_mgr: Optional[Any] = None,    # OrderManager（可选）
        grace_period_seconds: int = 10,
    ):
        """
        初始化对账服务

        Args:
            gateway: ExchangeGateway 实例
            position_mgr: PositionManager 实例（可选）
            order_mgr: OrderManager 实例（可选）
            grace_period_seconds: 宽限期秒数（默认 10 秒）
        """
        self._gateway = gateway
        self._position_mgr = position_mgr
        self._order_mgr = order_mgr
        self._grace_period_seconds = grace_period_seconds

    async def run_reconciliation(self, symbol: str) -> ReconciliationReport:
        """
        启动对账服务

        修复 G-004 关键点:
        - REST API 和 WebSocket 之间存在时差
        - 对账差异不立即判定为异常，先加入宽限期
        - 宽限期后二次校验，确认是否为真实异常

        对账流程:
        1. 获取本地仓位/订单列表
        2. 获取交易所仓位/订单列表
        3. 比对差异 → 加入 pending 列表（未确认）
        4. 等待 10 秒 Grace Period
        5. 二次校验 pending 列表
        6. 确认的差异 → 移动到正式列表
        7. 消失的差异 → 记录日志（WebSocket 延迟）

        Args:
            symbol: 币种对，如 "BTC/USDT:USDT"

        Returns:
            ReconciliationReport: 对账报告
        """
        logger.info(f"Starting reconciliation for {symbol}")
        start_time = int(time.time() * 1000)

        # ===== 阶段 1: 获取本地和交易所状态 =====
        local_positions = await self._get_local_positions(symbol)
        exchange_positions = await self._get_exchange_positions(symbol)

        local_orders = await self._get_local_open_orders(symbol)
        exchange_orders = await self._get_exchange_open_orders(symbol)

        logger.info(
            f"Local state: {len(local_positions)} positions, {len(local_orders)} orders"
        )
        logger.info(
            f"Exchange state: {len(exchange_positions)} positions, {len(exchange_orders)} orders"
        )

        # ===== 阶段 2: 比对差异，加入待确认列表 =====
        pending_missing_positions: List[PendingPositionItem] = []
        pending_position_mismatches: List[Dict[str, Any]] = []
        pending_orphan_orders: List[PendingOrderItem] = []
        pending_order_mismatches: List[Dict[str, Any]] = []

        # 仓位对账
        for ex_pos in exchange_positions:
            local_pos = self._find_position(local_positions, ex_pos.symbol)
            if local_pos is None:
                # 交易所有仓位，本地没有 → 加入待确认列表
                pending_missing_positions.append({
                    "position": ex_pos,
                    "found_at": int(time.time() * 1000),
                    "confirmed": False
                })
                logger.warning(
                    f"Pending missing position: {ex_pos.symbol}, "
                    f"exchange_size={ex_pos.size}"
                )
            elif local_pos.size != ex_pos.size:
                # 数量不一致 → 加入待确认列表
                discrepancy = ex_pos.size - local_pos.size
                pending_position_mismatches.append({
                    "symbol": ex_pos.symbol,
                    "local_qty": local_pos.size,
                    "exchange_qty": ex_pos.size,
                    "discrepancy": discrepancy,
                    "found_at": int(time.time() * 1000),
                    "confirmed": False
                })
                logger.warning(
                    f"Pending position mismatch: {ex_pos.symbol}, "
                    f"local_size={local_pos.size}, "
                    f"exchange_size={ex_pos.size}, "
                    f"discrepancy={discrepancy}"
                )

        # 订单对账
        for ex_order in exchange_orders:
            local_order = self._find_order(local_orders, ex_order.exchange_order_id)
            if local_order is None:
                # 孤儿订单 → 加入待确认列表
                pending_orphan_orders.append({
                    "order": ex_order,
                    "found_at": int(time.time() * 1000),
                    "confirmed": False
                })
                logger.warning(
                    f"Pending orphan order: {ex_order.exchange_order_id}, "
                    f"symbol={ex_order.symbol}, status={ex_order.status}"
                )
            elif local_order.status != self._map_exchange_status(ex_order.status):
                # 状态不一致 → 加入待确认列表
                pending_order_mismatches.append({
                    "order_id": ex_order.exchange_order_id,
                    "local_status": local_order.status,
                    "exchange_status": ex_order.status,
                    "found_at": int(time.time() * 1000),
                    "confirmed": False
                })
                logger.warning(
                    f"Pending order mismatch: {ex_order.exchange_order_id}, "
                    f"local_status={local_order.status}, "
                    f"exchange_status={ex_order.status}"
                )

        # ===== 阶段 3: 二次校验（宽限期后）=====
        logger.info(f"Waiting {self._grace_period_seconds}s grace period for secondary verification...")
        await self._verify_pending_items(
            pending_missing_positions,
            pending_position_mismatches,
            pending_orphan_orders,
            pending_order_mismatches,
            symbol,
        )

        # ===== 阶段 4: 将确认的差异移动到正式列表 =====
        missing_positions: List[PositionInfo] = []
        position_mismatches: List[PositionMismatch] = []
        orphan_orders: List[OrderResponse] = []
        order_mismatches: List[OrderMismatch] = []

        # 处理确认的缺失仓位
        for item in pending_missing_positions:
            if item["confirmed"]:
                missing_positions.append(item["position"])
                logger.error(
                    f"CONFIRMED missing position: {item['position'].symbol}, "
                    f"size={item['position'].size}"
                )

        # 处理确认的仓位不匹配
        for item in pending_position_mismatches:
            if item["confirmed"]:
                position_mismatches.append(PositionMismatch(
                    symbol=item["symbol"],
                    local_qty=item["local_qty"],
                    exchange_qty=item["exchange_qty"],
                    discrepancy=item["discrepancy"],
                ))
                logger.error(
                    f"CONFIRMED position mismatch: {item['symbol']}, "
                    f"local_qty={item['local_qty']}, "
                    f"exchange_qty={item['exchange_qty']}"
                )

        # 处理确认的孤儿订单
        for item in pending_orphan_orders:
            if item["confirmed"]:
                orphan_orders.append(self._order_to_response(item["order"]))
                logger.error(
                    f"CONFIRMED orphan order: {item['order'].exchange_order_id}, "
                    f"symbol={item['order'].symbol}"
                )

        # 处理确认的订单不匹配
        for item in pending_order_mismatches:
            if item["confirmed"]:
                order_mismatches.append(OrderMismatch(
                    order_id=item["order_id"],
                    local_status=item["local_status"],
                    exchange_status=item["exchange_status"],
                ))
                logger.error(
                    f"CONFIRMED order mismatch: {item['order_id']}, "
                    f"local_status={item['local_status']}, "
                    f"exchange_status={item['exchange_status']}"
                )

        # ===== 阶段 5: 生成对账报告 =====
        total_discrepancies = (
            len(missing_positions) +
            len(position_mismatches) +
            len(orphan_orders) +
            len(order_mismatches)
        )

        is_consistent = total_discrepancies == 0
        requires_attention = total_discrepancies > 0

        if is_consistent:
            logger.info(f"Reconciliation completed for {symbol}: No discrepancies found")
        else:
            logger.warning(
                f"Reconciliation completed for {symbol}: "
                f"{total_discrepancies} discrepancies found "
                f"({len(missing_positions)} missing positions, "
                f"{len(position_mismatches)} position mismatches, "
                f"{len(orphan_orders)} orphan orders, "
                f"{len(order_mismatches)} order mismatches)"
            )

        return ReconciliationReport(
            symbol=symbol,
            reconciliation_time=int(time.time() * 1000),
            grace_period_seconds=self._grace_period_seconds,
            position_mismatches=position_mismatches,
            missing_positions=missing_positions,
            order_mismatches=order_mismatches,
            orphan_orders=orphan_orders,
            is_consistent=is_consistent,
            total_discrepancies=total_discrepancies,
            requires_attention=requires_attention,
            summary=self._generate_summary(
                missing_positions,
                position_mismatches,
                orphan_orders,
                order_mismatches,
            ),
        )

    async def _verify_pending_items(
        self,
        pending_missing_positions: List[PendingPositionItem],
        pending_position_mismatches: List[Dict[str, Any]],
        pending_orphan_orders: List[PendingOrderItem],
        pending_order_mismatches: List[Dict[str, Any]],
        symbol: str,
    ) -> None:
        """
        二次校验：宽限期后重新检查待确认项目

        G-004 修复核心逻辑:
        1. 等待 10 秒 Grace Period
        2. 重新获取交易所和本地状态
        3. 如果差异仍然存在，确认为真实异常
        4. 如果差异消失，说明是 WebSocket 延迟，记录日志即可

        Args:
            pending_missing_positions: 待确认缺失仓位列表
            pending_position_mismatches: 待确认仓位不匹配列表
            pending_orphan_orders: 待确认孤儿订单列表
            pending_order_mismatches: 待确认订单不匹配列表
            symbol: 币种对
        """
        if not any([
            pending_missing_positions,
            pending_position_mismatches,
            pending_orphan_orders,
            pending_order_mismatches,
        ]):
            # 没有待确认项目，直接返回
            return

        # 等待宽限期
        await asyncio.sleep(self._grace_period_seconds)

        # 重新获取交易所和本地状态
        local_positions = await self._get_local_positions(symbol)
        exchange_positions = await self._get_exchange_positions(symbol)
        local_orders = await self._get_local_open_orders(symbol)
        exchange_orders = await self._get_exchange_open_orders(symbol)

        # 二次校验：缺失仓位
        for item in pending_missing_positions:
            if not item["confirmed"]:
                ex_pos = item["position"]
                local_pos = self._find_position(local_positions, ex_pos.symbol)
                if local_pos is not None:
                    # 差异消失 → WebSocket 延迟
                    logger.info(
                        f"Grace period resolved missing position: {ex_pos.symbol} "
                        f"(was WebSocket delay)"
                    )
                else:
                    # 差异仍然存在 → 确认为真实异常
                    item["confirmed"] = True

        # 二次校验：仓位不匹配
        for item in pending_position_mismatches:
            if not item["confirmed"]:
                local_pos = self._find_position(local_positions, item["symbol"])
                ex_pos = self._find_position(exchange_positions, item["symbol"])
                if local_pos and ex_pos and local_pos.size == ex_pos.size:
                    # 差异消失 → WebSocket 延迟
                    logger.info(
                        f"Grace period resolved position mismatch: {item['symbol']} "
                        f"(was WebSocket delay)"
                    )
                else:
                    # 差异仍然存在 → 确认为真实异常
                    item["confirmed"] = True

        # 二次校验：孤儿订单
        for item in pending_orphan_orders:
            if not item["confirmed"]:
                ex_order = item["order"]
                local_order = self._find_order(local_orders, ex_order.exchange_order_id)
                if local_order is not None:
                    # 差异消失 → WebSocket 延迟
                    logger.info(
                        f"Grace period resolved orphan order: {ex_order.exchange_order_id} "
                        f"(was WebSocket delay)"
                    )
                else:
                    # 差异仍然存在 → 确认为真实异常
                    item["confirmed"] = True

        # 二次校验：订单不匹配
        for item in pending_order_mismatches:
            if not item["confirmed"]:
                local_order = self._find_order_by_id(local_orders, item["order_id"])
                ex_order = self._find_order_by_id(exchange_orders, item["order_id"])
                if local_order and ex_order and local_order.status == self._map_exchange_status(ex_order.status):
                    # 差异消失 → WebSocket 延迟
                    logger.info(
                        f"Grace period resolved order mismatch: {item['order_id']} "
                        f"(was WebSocket delay)"
                    )
                else:
                    # 差异仍然存在 → 确认为真实异常
                    item["confirmed"] = True

    async def handle_orphan_orders(self, orphan_orders: List[OrderResponse]) -> None:
        """
        处理孤儿订单

        策略:
        - 如果是 TP/SL 订单且仓位不存在 → 取消
        - 如果是入场订单 → 保留并创建关联 Signal

        Args:
            orphan_orders: 孤儿订单列表
        """
        if not self._gateway:
            logger.error("Gateway not available, cannot handle orphan orders")
            return

        for order in orphan_orders:
            logger.info(f"Handling orphan order: {order.order_id}, role={order.order_role}")

            try:
                if order.reduce_only:
                    # 平仓单但没有对应仓位 → 取消
                    logger.info(
                        f"Canceling orphan TP/SL order: {order.order_id}, "
                        f"symbol={order.symbol}"
                    )
                    result = await self._gateway.cancel_order(
                        order_id=order.exchange_order_id or order.order_id,
                        symbol=order.symbol,
                    )
                    if result.is_success:
                        logger.info(f"Successfully canceled orphan order: {order.order_id}")
                    else:
                        logger.error(
                            f"Failed to cancel orphan order {order.order_id}: "
                            f"{result.message}"
                        )
                else:
                    # 入场订单 → 保留，创建关联 Signal
                    logger.info(
                        f"Keeping orphan entry order: {order.order_id}, "
                        f"will create关联 Signal"
                    )
                    await self._create_missing_signal(order)

            except Exception as e:
                logger.error(f"Error handling orphan order {order.order_id}: {e}")

    async def _create_missing_signal(self, order: OrderResponse) -> None:
        """
        为孤儿入场订单创建关联 Signal

        Args:
            order: 订单对象
        """
        # TODO: 实现 Signal 创建逻辑
        # 这里需要根据订单信息反推 Signal
        logger.info(
            f"Creating missing signal for orphan order {order.order_id}: "
            f"symbol={order.symbol}, direction={order.direction}"
        )

    # ============================================================
    # Helper Methods
    # ============================================================

    async def _get_local_positions(self, symbol: str) -> List[PositionInfo]:
        """
        获取本地仓位列表

        Args:
            symbol: 币种对

        Returns:
            List[PositionInfo]: 本地仓位列表
        """
        if self._position_mgr:
            try:
                positions = await self._position_mgr.get_open_positions(symbol)
                return [self._orm_position_to_info(pos) for pos in positions]
            except Exception as e:
                logger.error(f"Failed to get local positions: {e}")

        # Fallback: 从 gateway 获取（如果没有 position_mgr）
        snapshot = self._gateway.get_account_snapshot()
        if snapshot and snapshot.positions:
            return [p for p in snapshot.positions if p.symbol == symbol]
        return []

    async def _get_exchange_positions(self, symbol: str) -> List[PositionInfo]:
        """
        获取交易所仓位列表

        Args:
            symbol: 币种对

        Returns:
            List[PositionInfo]: 交易所仓位列表
        """
        try:
            # 使用 REST API 获取最新仓位
            positions = await self._gateway.rest_exchange.fetch_positions([symbol])
            result = []
            for pos in positions:
                if pos.get('contracts') and pos['contracts'] > 0:
                    leverage_val = pos.get('leverage', 1)
                    side = pos.get('side', 'none')
                    # 映射 side 到 Direction
                    direction = Direction.LONG if side == 'long' else Direction.SHORT

                    position = PositionInfo(
                        symbol=pos['symbol'],
                        side=side,
                        size=Decimal(str(pos['contracts'])),
                        entry_price=Decimal(str(pos['entryPrice'])) if pos.get('entryPrice') else Decimal('0'),
                        unrealized_pnl=Decimal(str(pos['unrealizedPnl'])) if pos.get('unrealizedPnl') else Decimal('0'),
                        leverage=int(leverage_val),
                    )
                    result.append(position)

            logger.debug(f"Exchange positions for {symbol}: {len(result)}")
            return result

        except Exception as e:
            logger.error(f"Failed to get exchange positions: {e}")
            return []

    async def _get_local_open_orders(self, symbol: str) -> List[OrderResponse]:
        """
        获取本地未平订单列表

        Args:
            symbol: 币种对

        Returns:
            List[OrderResponse]: 本地订单列表
        """
        # TODO: 从数据库获取本地订单
        # 目前返回空列表
        return []

    async def _get_exchange_open_orders(self, symbol: str) -> List[OrderResponse]:
        """
        获取交易所未平订单列表

        Args:
            symbol: 币种对

        Returns:
            List[OrderResponse]: 交易所订单列表
        """
        try:
            orders = await self._gateway.rest_exchange.fetch_open_orders(symbol)
            result = []
            for order in orders:
                order_resp = self._parse_ccxt_order(order)
                if order_resp:
                    result.append(order_resp)

            logger.debug(f"Exchange open orders for {symbol}: {len(result)}")
            return result

        except Exception as e:
            logger.error(f"Failed to get exchange open orders: {e}")
            return []

    def _find_position(self, positions: List[PositionInfo], symbol: str) -> Optional[PositionInfo]:
        """
        在仓位列表中查找指定币种的仓位

        Args:
            positions: 仓位列表
            symbol: 币种

        Returns:
            PositionInfo 或 None
        """
        for pos in positions:
            if pos.symbol == symbol:
                return pos
        return None

    def _find_order(self, orders: List[OrderResponse], exchange_order_id: str) -> Optional[OrderResponse]:
        """
        在订单列表中查找指定交易所订单 ID 的订单

        Args:
            orders: 订单列表
            exchange_order_id: 交易所订单 ID

        Returns:
            OrderResponse 或 None
        """
        for order in orders:
            if order.exchange_order_id == exchange_order_id:
                return order
        return None

    def _find_order_by_id(self, orders: List[OrderResponse], order_id: str) -> Optional[OrderResponse]:
        """
        在订单列表中查找指定订单 ID 的订单

        Args:
            orders: 订单列表
            order_id: 订单 ID

        Returns:
            OrderResponse 或 None
        """
        for order in orders:
            if order.order_id == order_id:
                return order
        return None

    def _map_exchange_status(self, status: str) -> OrderStatus:
        """
        映射交易所订单状态到内部 OrderStatus

        Args:
            status: 交易所订单状态

        Returns:
            OrderStatus 枚举
        """
        status_mapping = {
            'open': OrderStatus.OPEN,
            'closed': OrderStatus.FILLED,
            'canceled': OrderStatus.CANCELED,
            'rejected': OrderStatus.REJECTED,
            'expired': OrderStatus.EXPIRED,
        }
        return status_mapping.get(status.lower(), OrderStatus.PENDING)

    def _parse_ccxt_order(self, order: Dict[str, Any]) -> Optional[OrderResponse]:
        """
        解析 CCXT 订单为 OrderResponse

        Args:
            order: CCXT 订单数据

        Returns:
            OrderResponse 或 None
        """
        try:
            status = self._map_exchange_status(order.get('status', 'open'))

            # 映射订单类型
            ccxt_type = order.get('type', 'limit')
            order_type = OrderType.LIMIT
            if ccxt_type == 'market':
                order_type = OrderType.MARKET
            elif ccxt_type == 'stop':
                order_type = OrderType.STOP_MARKET
            elif ccxt_type == 'stop limit':
                order_type = OrderType.STOP_LIMIT

            # 映射方向
            side = order.get('side', 'buy')
            reduce_only = order.get('reduceOnly', False)
            direction = self._map_side_to_direction(side, reduce_only)

            # 映射角色
            order_role = OrderRole.ENTRY
            if reduce_only:
                # 根据方向判断是 TP 还是 SL
                order_role = OrderRole.TP1  # 默认止盈

            return OrderResponse(
                order_id=order.get('id', ''),
                exchange_order_id=order.get('id'),
                symbol=order.get('symbol', ''),
                order_type=order_type,
                direction=direction,
                order_role=order_role,
                status=status,
                amount=Decimal(str(order['amount'])) if order.get('amount') else Decimal('0'),
                filled_amount=Decimal(str(order['filled'])) if order.get('filled') else Decimal('0'),
                price=Decimal(str(order['price'])) if order.get('price') else None,
                trigger_price=Decimal(str(order.get('triggerPrice'))) if order.get('triggerPrice') else None,
                average_exec_price=Decimal(str(order['average'])) if order.get('average') else None,
                reduce_only=reduce_only,
                created_at=int(order.get('timestamp', time.time() * 1000)),
                updated_at=int(time.time() * 1000),
            )

        except Exception as e:
            logger.error(f"Failed to parse CCXT order: {e}")
            return None

    def _map_side_to_direction(self, side: str, reduce_only: bool) -> Direction:
        """
        映射 side 到 Direction 枚举

        Args:
            side: "buy" | "sell"
            reduce_only: 是否减仓

        Returns:
            Direction 枚举
        """
        if not reduce_only:
            # 开仓单：buy=LONG, sell=SHORT
            return Direction.LONG if side == 'buy' else Direction.SHORT
        else:
            # 平仓单：buy=SHORT(平空), sell=LONG(平多)
            return Direction.SHORT if side == 'buy' else Direction.LONG

    def _order_to_response(self, order: Any) -> OrderResponse:
        """
        将任意订单对象转换为 OrderResponse

        Args:
            order: 订单对象

        Returns:
            OrderResponse
        """
        if isinstance(order, OrderResponse):
            return order

        # 假设 order 有必要的属性
        return OrderResponse(
            order_id=getattr(order, 'order_id', ''),
            exchange_order_id=getattr(order, 'exchange_order_id', None),
            symbol=getattr(order, 'symbol', ''),
            order_type=getattr(order, 'order_type', OrderType.LIMIT),
            direction=getattr(order, 'direction', Direction.LONG),
            order_role=getattr(order, 'order_role', OrderRole.ENTRY),
            status=getattr(order, 'status', OrderStatus.OPEN),
            amount=getattr(order, 'amount', Decimal('0')),
            filled_amount=getattr(order, 'filled_amount', Decimal('0')),
            price=getattr(order, 'price', None),
            trigger_price=getattr(order, 'trigger_price', None),
            average_exec_price=getattr(order, 'average_exec_price', None),
            reduce_only=getattr(order, 'reduce_only', False),
            created_at=getattr(order, 'created_at', int(time.time() * 1000)),
            updated_at=getattr(order, 'updated_at', int(time.time() * 1000)),
        )

    def _orm_position_to_info(self, pos: Any) -> PositionInfo:
        """
        将 ORM 仓位对象转换为 PositionInfo

        Args:
            pos: ORM 仓位对象

        Returns:
            PositionInfo
        """
        # 如果是 PositionInfo 类型，直接返回
        if isinstance(pos, PositionInfo):
            return pos

        # 假设有必要的属性
        return PositionInfo(
            symbol=getattr(pos, 'symbol', ''),
            side=getattr(pos, 'direction', 'long') if hasattr(pos, 'direction') else 'long',
            size=getattr(pos, 'current_qty', Decimal('0')),
            entry_price=getattr(pos, 'entry_price', Decimal('0')),
            unrealized_pnl=getattr(pos, 'unrealized_pnl', Decimal('0')),
            leverage=getattr(pos, 'leverage', 1),
        )

    def _generate_summary(
        self,
        missing_positions: List[PositionInfo],
        position_mismatches: List[PositionMismatch],
        orphan_orders: List[OrderResponse],
        order_mismatches: List[OrderMismatch],
    ) -> str:
        """
        生成对账结论摘要

        Args:
            missing_positions: 缺失仓位列表
            position_mismatches: 仓位不匹配列表
            orphan_orders: 孤儿订单列表
            order_mismatches: 订单不匹配列表

        Returns:
            str: 对账摘要
        """
        total = (
            len(missing_positions) +
            len(position_mismatches) +
            len(orphan_orders) +
            len(order_mismatches)
        )

        if total == 0:
            return "对账一致，无差异"

        parts = []
        if missing_positions:
            parts.append(f"缺失仓位 {len(missing_positions)} 个")
        if position_mismatches:
            parts.append(f"仓位不匹配 {len(position_mismatches)} 个")
        if orphan_orders:
            parts.append(f"孤儿订单 {len(orphan_orders)} 个")
        if order_mismatches:
            parts.append(f"订单不匹配 {len(order_mismatches)} 个")

        return f"发现 {total} 项差异：" + "，".join(parts)
