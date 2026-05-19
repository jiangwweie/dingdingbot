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

P0-003: 完善重启对账流程
- 幽灵订单处理：DB 有但交易所无 → 标记为 CANCELLED
- 孤儿订单处理：交易所有但 DB 无 → 导入 DB 或撤销
- 对账报告生成：记录差异订单和处理动作
- 并发锁机制：防止多个对账任务同时运行
"""
import asyncio
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from decimal import Decimal

from src.domain.models import (
    ReconciliationReport,
    ReconciliationType,
    PositionMismatch,
    OrderMismatch,
    OrderResponse,
    OrderStatus,
    OrderType,
    OrderRole,
    Direction,
    PositionInfo,
    GhostOrder,
    ImportedOrder,
)
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.logger import logger
from src.infrastructure.reconciliation_repository import ReconciliationRepository
from src.application.reconciliation_lock import ReconciliationLock, ReconciliationLockError
from src.application.protection_health_monitor import (
    PROTECTION_EXCHANGE_POSITION_UNTRACKED,
    PROTECTION_LOCAL_SL_MISSING_ON_EXCHANGE,
    PROTECTION_MISSING_EXCHANGE_SL,
    PROTECTION_ORPHAN_REDUCE_ONLY_ORDER,
)


class PendingPositionItem(Dict[str, Any]):
    """待确认仓位项"""
    pass


class PendingOrderItem(Dict[str, Any]):
    """待确认订单项"""
    pass


@dataclass
class ReconciliationMismatch:
    """Read-only reconciliation mismatch for LS-003a."""

    symbol: str
    mismatch_type: str
    severity: str
    reason: str
    local_ref: Optional[str] = None
    exchange_ref: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReconciliationReadModelResult:
    """Minimal runtime reconciliation read model result.

    LS-003a is report-only: these results must not block, repair, cancel, or
    mutate runtime state.
    """

    symbol: str
    checked_at: int
    mismatches: List[ReconciliationMismatch] = field(default_factory=list)

    @property
    def is_consistent(self) -> bool:
        return not self.mismatches

    @property
    def severe_count(self) -> int:
        return sum(1 for item in self.mismatches if item.severity in {"SEVERE", "CRITICAL"})

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.mismatches if item.severity == "WARNING")


class ReconciliationService:
    """
    对账服务：同步本地状态与交易所状态

    核心职责:
    1. 启动时比对本地数据库与交易所状态
    2. 使用 Grace Period 宽限期避免"幽灵偏差"
    3. 处理孤儿订单（无主 TP/SL 订单）
    4. 生成对账报告并持久化

    G-004 修复:
    - REST API 和 WebSocket 之间存在时差
    - 对账差异不立即判定为异常，先加入宽限期
    - 宽限期后二次校验，确认是否为真实异常

    P5-011 修复:
    - 孤儿订单立即撤销可能误删刚建好仓位的保护伞
    - TP/SL 孤儿单先放入 pending_orphan_orders 列表等待 10 秒
    - 10 秒后二次校验，确认仓位仍不存在再撤销

    P0-003 增强:
    - 并发锁机制防止多个对账任务同时运行
    - 对账报告持久化到数据库
    """

    def __init__(
        self,
        gateway: ExchangeGateway,
        position_mgr: Optional[Any] = None,  # PositionManager（可选）
        order_mgr: Optional[Any] = None,    # OrderManager（可选）
        order_repository: Optional[Any] = None,  # OrderRepository（可选，用于 P0-003）
        reconciliation_repository: Optional[ReconciliationRepository] = None,  # ReconciliationRepository（可选）
        lock: Optional[ReconciliationLock] = None,  # ReconciliationLock（可选）
        grace_period_seconds: int = 10,
    ):
        """
        初始化对账服务

        Args:
            gateway: ExchangeGateway 实例
            position_mgr: PositionManager 实例（可选）
            order_mgr: OrderManager 实例（可选）
            order_repository: OrderRepository 实例（可选，用于 P0-003 订单持久化）
            reconciliation_repository: ReconciliationRepository 实例（可选，用于对账报告持久化）
            lock: ReconciliationLock 实例（可选，用于并发控制）
            grace_period_seconds: 宽限期秒数（默认 10 秒）
        """
        self._gateway = gateway
        self._position_mgr = position_mgr
        self._order_mgr = order_mgr
        self._order_repository = order_repository
        self._reconciliation_repository = reconciliation_repository
        self._lock = lock
        self._grace_period_seconds = grace_period_seconds
        self._pending_orphan_orders: Dict[str, Dict[str, Any]] = {}  # order_id -> {order, found_at, confirmed}

    async def build_read_model(self, symbol: str) -> ReconciliationReadModelResult:
        """Build a read-only reconciliation snapshot for LS-003a.

        This path only discovers and reports mismatches. It does not reuse the
        startup reconciliation action path that may mark, import, cancel, block,
        or otherwise mutate runtime state.
        """
        checked_at = int(time.time() * 1000)
        mismatches: List[ReconciliationMismatch] = []

        try:
            local_positions = await self._get_local_active_positions_for_read_model(symbol)
            local_orders = await self._get_local_open_orders(symbol)
        except Exception as exc:
            mismatches.append(
                ReconciliationMismatch(
                    symbol=symbol,
                    mismatch_type="local_state_fetch_failed",
                    severity="SEVERE",
                    local_ref=None,
                    exchange_ref=None,
                    reason="Failed to fetch local reconciliation state.",
                    metadata={"error": str(exc)},
                )
            )
            return ReconciliationReadModelResult(
                symbol=symbol,
                checked_at=checked_at,
                mismatches=mismatches,
            )

        try:
            exchange_positions = await self._fetch_exchange_positions_for_read_model(symbol)
            exchange_orders = await self._fetch_exchange_open_orders_for_read_model(symbol)
        except Exception as exc:
            mismatches.append(
                ReconciliationMismatch(
                    symbol=symbol,
                    mismatch_type="exchange_state_fetch_failed",
                    severity="SEVERE",
                    local_ref=None,
                    exchange_ref=None,
                    reason="Failed to fetch exchange reconciliation state.",
                    metadata={"error": str(exc)},
                )
            )
            return ReconciliationReadModelResult(
                symbol=symbol,
                checked_at=checked_at,
                mismatches=mismatches,
            )

        mismatches.extend(
            self._compare_positions_for_read_model(
                symbol,
                local_positions,
                exchange_positions,
            )
        )
        mismatches.extend(
            self._compare_orders_for_read_model(symbol, local_orders, exchange_orders)
        )
        mismatches.extend(
            self._check_protection_coverage_for_read_model(
                symbol,
                local_positions,
                local_orders,
            )
        )
        mismatches.extend(
            self._check_exchange_native_protection_for_read_model(
                symbol,
                local_positions,
                exchange_positions,
                local_orders,
                exchange_orders,
            )
        )

        return ReconciliationReadModelResult(
            symbol=symbol,
            checked_at=checked_at,
            mismatches=mismatches,
        )

    async def run_reconciliation(
        self,
        symbol: str,
        reconciliation_type: ReconciliationType = ReconciliationType.STARTUP,
        use_lock: bool = True,
    ) -> ReconciliationReport:
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

        P0-003 增强:
        - 使用并发锁防止多个对账任务同时运行
        - 对账报告持久化到数据库

        Args:
            symbol: 币种对，如 "BTC/USDT:USDT"
            reconciliation_type: 对账类型（startup/daily/manual）
            use_lock: 是否使用锁机制（默认 True）

        Returns:
            ReconciliationReport: 对账报告

        Raises:
            ReconciliationLockError: 获取锁失败
        """
        logger.info(f"Starting reconciliation for {symbol} (type={reconciliation_type.value})")
        start_time = int(time.time() * 1000)

        # ===== 阶段 0: 获取锁（如果需要） =====
        if use_lock and self._lock:
            lock_name = f"reconciliation_{symbol.replace('/', '_').replace(':', '_')}"
            async with self._lock.acquire(lock_name, f"reconciliation_{symbol}"):
                logger.info(f"已获取对账锁 {lock_name}，开始执行对账...")
                return await self._execute_reconciliation(
                    symbol, reconciliation_type, start_time
                )
        else:
            return await self._execute_reconciliation(
                symbol, reconciliation_type, start_time
            )

    async def _execute_reconciliation(
        self,
        symbol: str,
        reconciliation_type: ReconciliationType,
        start_time: int,
    ) -> ReconciliationReport:
        """
        执行对账逻辑（内部方法）

        Args:
            symbol: 币种对
            reconciliation_type: 对账类型
            start_time: 开始时间戳

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

        # P0-003: 幽灵订单和导入订单列表
        ghost_orders: List[GhostOrder] = []
        imported_orders: List[ImportedOrder] = []
        canceled_orphan_orders: List[ImportedOrder] = []

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
                order = self._order_to_response(item["order"])
                orphan_orders.append(order)
                logger.error(
                    f"CONFIRMED orphan order: {order.order_id}, "
                    f"symbol={order.symbol}"
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

        # ===== 阶段 4.5: P0-003 幽灵订单和孤儿订单处理 =====
        # 检测幽灵订单（DB 有但交易所无）
        ghost_orders = await self._detect_ghost_orders(local_orders, exchange_orders)

        # 处理孤儿订单（交易所有但 DB 无）
        imported_orders, canceled_orphan_orders = await self._process_orphan_orders(
            orphan_orders, symbol
        )

        # ===== 阶段 5: 生成对账报告 =====
        total_discrepancies = (
            len(missing_positions) +
            len(position_mismatches) +
            len(orphan_orders) +
            len(order_mismatches) +
            len(ghost_orders) +
            len(imported_orders) +
            len(canceled_orphan_orders)
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
                f"{len(order_mismatches)} order mismatches, "
                f"{len(ghost_orders)} ghost orders, "
                f"{len(imported_orders)} imported orders, "
                f"{len(canceled_orphan_orders)} canceled orphan orders)"
            )

        report = ReconciliationReport(
            symbol=symbol,
            reconciliation_time=int(time.time() * 1000),
            grace_period_seconds=self._grace_period_seconds,
            position_mismatches=position_mismatches,
            missing_positions=missing_positions,
            order_mismatches=order_mismatches,
            orphan_orders=orphan_orders,
            ghost_orders=ghost_orders,
            imported_orders=imported_orders,
            canceled_orphan_orders=canceled_orphan_orders,
            is_consistent=is_consistent,
            total_discrepancies=total_discrepancies,
            requires_attention=requires_attention,
            summary=self._generate_summary(
                missing_positions,
                position_mismatches,
                orphan_orders,
                order_mismatches,
                ghost_orders,
                imported_orders,
                canceled_orphan_orders,
            ),
        )

        # ===== 阶段 6: P0-003 对账报告持久化 =====
        if self._reconciliation_repository:
            try:
                await self._reconciliation_repository.save_report(report, reconciliation_type)
                logger.info(f"对账报告已持久化：report_id={report.reconciliation_time}")
            except Exception as e:
                logger.error(f"对账报告持久化失败：{e}")

        return report

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

        策略 (P5-011 修复):
        - 如果是 TP/SL 订单且仓位不存在 → 先放入 pending_orphan_orders 等待 10 秒
        - 10 秒后二次校验，如果仓位仍不存在 → 取消订单
        - 如果是入场订单 → 保留并创建关联 Signal

        Args:
            orphan_orders: 孤儿订单列表
        """
        if not self._gateway:
            logger.error("Gateway not available, cannot handle orphan orders")
            return

        current_time = int(time.time() * 1000)

        for order in orphan_orders:
            logger.info(f"Handling orphan order: {order.order_id}, role={order.order_role}")

            try:
                if order.reduce_only:
                    # TP/SL 平仓单但没有对应仓位 → 先放入待确认列表，等待 10 秒后二次校验
                    logger.info(
                        f"Pending orphan TP/SL order: {order.order_id}, "
                        f"symbol={order.symbol} - waiting {self._grace_period_seconds}s grace period"
                    )
                    self._pending_orphan_orders[order.order_id] = {
                        "order": order,
                        "found_at": current_time,
                        "confirmed": False,
                    }
                else:
                    # 入场订单 → 保留，创建关联 Signal
                    logger.info(
                        f"Keeping orphan entry order: {order.order_id}, "
                        f"will create 关联 Signal"
                    )
                    await self._create_missing_signal(order)

            except Exception as e:
                logger.error(f"Error handling orphan order {order.order_id}: {e}")

        # 如果有待确认的孤儿订单，等待宽限期后二次校验
        if self._pending_orphan_orders:
            logger.info(
                f"Waiting {self._grace_period_seconds}s grace period for "
                f"{len(self._pending_orphan_orders)} pending orphan orders..."
            )
            await self._verify_pending_orphan_orders()

    async def _verify_pending_orphan_orders(self) -> None:
        """
        二次校验待确认孤儿订单

        P5-011 修复核心逻辑:
        1. 等待宽限期（10 秒）
        2. 重新获取本地仓位列表
        3. 如果仓位已存在 → 差异消失，保留订单（WebSocket 延迟）
        4. 如果仓位仍不存在 → 确认真实异常，执行撤销
        """
        # 等待宽限期
        await asyncio.sleep(self._grace_period_seconds)

        # 二次校验每个待确认订单
        orders_to_remove = []
        for order_id, item in list(self._pending_orphan_orders.items()):
            if item["confirmed"]:
                # 已经确认过的，跳过
                continue

            order = item["order"]
            # 检查仓位是否存在
            local_positions = await self._get_local_positions(order.symbol)
            position_exists = any(pos.symbol == order.symbol for pos in local_positions)

            if position_exists:
                # 仓位出现了 → 差异消失，保留订单
                logger.info(
                    f"Grace period resolved: position now exists for orphan order {order_id} "
                    f"(was WebSocket delay) - keeping order"
                )
                orders_to_remove.append(order_id)
            else:
                # 仓位仍不存在 → 确认真实异常，执行撤销
                logger.warning(
                    f"Grace period expired: position still missing for orphan order {order_id} - canceling"
                )
                await self._cancel_orphan_order(order)
                orders_to_remove.append(order_id)

        # 移除已处理的订单
        for order_id in orders_to_remove:
            del self._pending_orphan_orders[order_id]

    async def _cancel_orphan_order(self, order: OrderResponse) -> None:
        """
        撤销孤儿订单

        Args:
            order: 订单对象
        """
        try:
            logger.info(
                f"Canceling confirmed orphan TP/SL order: {order.order_id}, "
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
        except Exception as e:
            logger.error(f"Error canceling orphan order {order.order_id}: {e}")

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
    # P0-003: 幽灵订单和孤儿订单处理
    # ============================================================

    async def _detect_ghost_orders(
        self,
        local_orders: List[OrderResponse],
        exchange_orders: List[OrderResponse],
    ) -> List[GhostOrder]:
        """
        检测幽灵订单（P0-003）

        幽灵订单：DB 有但交易所无
        检测条件：订单在 DB 中状态为 PENDING/NEW，但交易所查询不到
        处理逻辑：标记为 CANCELLED，记录对账报告

        Args:
            local_orders: 本地订单列表
            exchange_orders: 交易所订单列表

        Returns:
            List[GhostOrder]: 幽灵订单列表
        """
        ghost_orders = []
        current_time = int(time.time() * 1000)

        # 构建交易所订单 ID 集合
        exchange_order_ids = {
            order.exchange_order_id or order.order_id
            for order in exchange_orders
        }

        # 检测幽灵订单
        for local_order in local_orders:
            order_id = local_order.exchange_order_id or local_order.order_id
            if order_id not in exchange_order_ids:
                # 订单在本地存在但在交易所不存在
                if local_order.status in [OrderStatus.PENDING, OrderStatus.OPEN]:
                    logger.warning(
                        f"Ghost order detected: {order_id}, "
                        f"symbol={local_order.symbol}, "
                        f"local_status={local_order.status}"
                    )

                    ghost_orders.append(GhostOrder(
                        order_id=order_id,
                        symbol=local_order.symbol,
                        local_status=local_order.status,
                        detected_at=current_time,
                        action_taken="MARKED_CANCELLED",
                    ))

                    # 标记为 CANCELLED（如果有 order_repository）
                    if self._order_repository:
                        try:
                            await self._order_repository.mark_order_cancelled(order_id)
                            logger.info(f"Ghost order {order_id} marked as CANCELLED in DB")
                        except Exception as e:
                            logger.error(f"Failed to mark ghost order {order_id} as CANCELLED: {e}")

        return ghost_orders

    async def _process_orphan_orders(
        self,
        orphan_orders: List[OrderResponse],
        symbol: str,
    ) -> Tuple[List[ImportedOrder], List[ImportedOrder]]:
        """
        处理孤儿订单（P0-003）

        孤儿订单：交易所有但 DB 无
        检测条件：交易所有活跃挂单，但 DB 中无记录
        处理逻辑：
        - 入场订单 (ENTRY) → 导入 DB 并创建关联 Signal
        - TP/SL 订单 (reduce_only=True) → 撤销并记录（因为仓位不存在）

        Args:
            orphan_orders: 孤儿订单列表
            symbol: 币种对

        Returns:
            (imported_orders, canceled_orphan_orders)
        """
        imported_orders = []
        canceled_orphan_orders = []
        current_time = int(time.time() * 1000)

        for order in orphan_orders:
            order_id = order.exchange_order_id or order.order_id
            logger.info(
                f"Processing orphan order: {order_id}, "
                f"symbol={order.symbol}, "
                f"role={order.order_role}, "
                f"reduce_only={order.reduce_only}"
            )

            try:
                if order.reduce_only or order.order_role in [OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5, OrderRole.SL]:
                    # TP/SL 订单：仓位不存在，撤销订单
                    logger.warning(
                        f"Orphan TP/SL order {order_id} has no position - canceling"
                    )

                    # 尝试撤销订单
                    cancel_result = await self._gateway.cancel_order(
                        order_id=order_id,
                        symbol=order.symbol,
                    )

                    canceled_orphan_orders.append(ImportedOrder(
                        order_id=order_id,
                        exchange_order_id=order.exchange_order_id or order_id,
                        symbol=order.symbol,
                        order_type=order.order_type,
                        direction=order.direction,
                        order_role=order.order_role,
                        status=OrderStatus.CANCELED if cancel_result.is_success else order.status,
                        amount=order.amount,
                        price=order.price,
                        trigger_price=order.trigger_price,
                        reduce_only=True,
                        imported_at=current_time,
                        action_taken="CANCELLED",
                    ))

                    if cancel_result.is_success:
                        logger.info(f"Successfully canceled orphan TP/SL order: {order_id}")
                    else:
                        logger.error(f"Failed to cancel orphan TP/SL order {order_id}: {cancel_result.message if hasattr(cancel_result, 'message') else 'Unknown error'}")
                else:
                    # 入场订单：导入 DB
                    logger.info(
                        f"Importing orphan entry order {order_id} to DB"
                    )

                    # 如果有 order_repository，导入订单
                    if self._order_repository:
                        try:
                            # TODO: 实现 order_repository.import_order() 方法
                            # await self._order_repository.import_order(order)
                            logger.warning(f"order_repository.import_order() not implemented yet")
                        except Exception as e:
                            logger.error(f"Failed to import orphan order {order_id}: {e}")

                    imported_orders.append(ImportedOrder(
                        order_id=order_id,
                        exchange_order_id=order.exchange_order_id or order_id,
                        symbol=order.symbol,
                        order_type=order.order_type,
                        direction=order.direction,
                        order_role=order.order_role,
                        status=order.status,
                        amount=order.amount,
                        price=order.price,
                        trigger_price=order.trigger_price,
                        reduce_only=order.reduce_only,
                        imported_at=current_time,
                        action_taken="IMPORTED_TO_DB",
                    ))

                    # 创建关联 Signal
                    await self._create_missing_signal(order)

            except Exception as e:
                logger.error(f"Error processing orphan order {order_id}: {e}")

        return imported_orders, canceled_orphan_orders

    # ============================================================
    # Helper Methods
    # ============================================================

    async def _get_local_active_positions_for_read_model(self, symbol: str) -> List[PositionInfo]:
        """Fetch local active positions without falling back to exchange snapshots."""
        if self._position_mgr is None:
            return []

        try:
            if hasattr(self._position_mgr, "get_open_positions"):
                positions = await self._position_mgr.get_open_positions(symbol)
            elif hasattr(self._position_mgr, "list_active"):
                positions = await self._position_mgr.list_active(symbol=symbol)
            else:
                return []
            return [self._orm_position_to_info(pos) for pos in positions]
        except Exception as e:
            logger.error(f"Failed to get local read-model positions: {e}")
            raise

    async def _fetch_exchange_positions_for_read_model(self, symbol: str) -> List[PositionInfo]:
        """Fetch exchange positions for read-only reconciliation."""
        if hasattr(self._gateway, "fetch_positions"):
            return await self._gateway.fetch_positions(symbol)
        return await self._get_exchange_positions(symbol)

    async def _fetch_exchange_open_orders_for_read_model(self, symbol: str) -> List[OrderResponse]:
        """Fetch exchange open orders for read-only reconciliation."""
        if hasattr(self._gateway, "fetch_open_orders"):
            orders = await self._gateway.fetch_open_orders(symbol)
        else:
            orders = await self._gateway.rest_exchange.fetch_open_orders(symbol)

        result = []
        for order in orders:
            order_resp = self._parse_ccxt_order(order)
            if order_resp:
                result.append(order_resp)
        return result

    def _compare_positions_for_read_model(
        self,
        symbol: str,
        local_positions: List[PositionInfo],
        exchange_positions: List[PositionInfo],
    ) -> List[ReconciliationMismatch]:
        mismatches: List[ReconciliationMismatch] = []
        tolerance = Decimal("0.00000001")
        local_qty = sum((pos.size for pos in local_positions), Decimal("0"))
        exchange_qty = sum((pos.size for pos in exchange_positions), Decimal("0"))

        if local_qty > 0 and exchange_qty == 0:
            mismatches.append(
                ReconciliationMismatch(
                    symbol=symbol,
                    mismatch_type="local_position_missing_on_exchange",
                    severity="SEVERE",
                    local_ref=symbol,
                    exchange_ref=None,
                    reason="Local active position exists but exchange has no active position.",
                    metadata={"local_qty": str(local_qty), "exchange_qty": str(exchange_qty)},
                )
            )
        elif exchange_qty > 0 and local_qty == 0:
            mismatches.append(
                ReconciliationMismatch(
                    symbol=symbol,
                    mismatch_type="exchange_position_missing_locally",
                    severity="SEVERE",
                    local_ref=None,
                    exchange_ref=symbol,
                    reason="Exchange active position exists but local runtime has no active position.",
                    metadata={"local_qty": str(local_qty), "exchange_qty": str(exchange_qty)},
                )
            )
        elif abs(local_qty - exchange_qty) > tolerance:
            mismatches.append(
                ReconciliationMismatch(
                    symbol=symbol,
                    mismatch_type="position_qty_mismatch",
                    severity="WARNING",
                    local_ref=symbol,
                    exchange_ref=symbol,
                    reason="Local active position quantity differs from exchange quantity.",
                    metadata={
                        "local_qty": str(local_qty),
                        "exchange_qty": str(exchange_qty),
                        "tolerance": str(tolerance),
                    },
                )
            )

        return mismatches

    def _check_exchange_native_protection_for_read_model(
        self,
        symbol: str,
        local_positions: List[PositionInfo],
        exchange_positions: List[PositionInfo],
        local_orders: List[OrderResponse],
        exchange_orders: List[OrderResponse],
    ) -> List[ReconciliationMismatch]:
        """Detect critical exchange-native protection gaps without mutating state."""
        mismatches: List[ReconciliationMismatch] = []
        local_qty = sum((pos.size for pos in local_positions), Decimal("0"))
        exchange_qty = sum((pos.size for pos in exchange_positions), Decimal("0"))
        local_position = local_positions[0] if local_positions else None
        exchange_position = exchange_positions[0] if exchange_positions else None

        exchange_native_sl_orders = [
            order for order in exchange_orders if self._is_exchange_native_sl_order(order)
        ]
        reduce_only_exit_orders = [
            order for order in exchange_orders if self._is_reduce_only_exit_order(order)
        ]
        local_sl_orders = [
            order for order in local_orders
            if order.symbol == symbol and order.order_role == OrderRole.SL
        ]

        if local_qty > 0 and exchange_qty > 0 and not exchange_native_sl_orders:
            mismatches.append(
                self._protection_mismatch(
                    symbol=symbol,
                    mismatch_type="protection_missing_exchange_sl",
                    reason_code=PROTECTION_MISSING_EXCHANGE_SL,
                    local_ref=symbol,
                    exchange_ref=symbol,
                    local_position=local_position,
                    exchange_position=exchange_position,
                    reason="Local and exchange positions exist but no exchange-native reduce-only SL was found.",
                    manual_recovery="Verify position exposure and mount or restore exchange-native SL before clearing the block.",
                )
            )

        if exchange_qty > 0 and local_qty == 0:
            mismatches.append(
                self._protection_mismatch(
                    symbol=symbol,
                    mismatch_type="protection_exchange_position_untracked",
                    reason_code=PROTECTION_EXCHANGE_POSITION_UNTRACKED,
                    local_ref=None,
                    exchange_ref=symbol,
                    exchange_position=exchange_position,
                    reason="Exchange active position exists but local runtime has no active position.",
                    manual_recovery="Import or reconcile the exchange position into local state, or manually resolve exposure before clearing the block.",
                )
            )

        for local_sl in local_sl_orders:
            matching_exchange_sl = self._find_matching_exchange_protection_order(
                local_sl,
                exchange_native_sl_orders,
            )
            if matching_exchange_sl is None:
                mismatches.append(
                    self._protection_mismatch(
                        symbol=symbol,
                        mismatch_type="protection_local_sl_missing_on_exchange",
                        reason_code=PROTECTION_LOCAL_SL_MISSING_ON_EXCHANGE,
                        local_ref=local_sl.order_id,
                        exchange_ref=local_sl.exchange_order_id,
                        local_position=local_position,
                        exchange_position=exchange_position,
                        local_order=local_sl,
                        reason="Local active SL record was not found in exchange open orders.",
                        manual_recovery="Verify local SL record and exchange open orders; remount or reconcile manually before clearing the block.",
                    )
                )

        for exchange_order in reduce_only_exit_orders:
            matching_local_order = self._find_matching_local_order(exchange_order, local_orders)
            if local_qty == 0 or matching_local_order is None:
                mismatches.append(
                    self._protection_mismatch(
                        symbol=symbol,
                        mismatch_type="protection_orphan_reduce_only_order",
                        reason_code=PROTECTION_ORPHAN_REDUCE_ONLY_ORDER,
                        local_ref=matching_local_order.order_id if matching_local_order else None,
                        exchange_ref=exchange_order.exchange_order_id or exchange_order.order_id,
                        local_position=local_position,
                        exchange_position=exchange_position,
                        local_order=matching_local_order,
                        exchange_order=exchange_order,
                        reason="Exchange reduce-only SL/TP order has no matching local active position or order chain.",
                        manual_recovery="Inspect the reduce-only order and local order chain; cancel or reconcile manually before clearing the block.",
                    )
                )

        return mismatches

    def _protection_mismatch(
        self,
        *,
        symbol: str,
        mismatch_type: str,
        reason_code: str,
        reason: str,
        local_ref: Optional[str],
        exchange_ref: Optional[str],
        manual_recovery: str,
        local_position: Optional[PositionInfo] = None,
        exchange_position: Optional[PositionInfo] = None,
        local_order: Optional[OrderResponse] = None,
        exchange_order: Optional[OrderResponse] = None,
    ) -> ReconciliationMismatch:
        metadata: Dict[str, Any] = {
            "protection_reason_code": reason_code,
            "manual_recovery": manual_recovery,
            "local_position_id": local_ref if local_position is not None else None,
            "exchange_position_qty": str(exchange_position.size) if exchange_position is not None else None,
            "position_side": getattr(exchange_position or local_position, "side", None),
            "local_order_id": local_order.order_id if local_order is not None else local_ref,
            "exchange_order_id": (
                (exchange_order.exchange_order_id or exchange_order.order_id)
                if exchange_order is not None
                else exchange_ref
            ),
            "reduce_only": exchange_order.reduce_only if exchange_order is not None else None,
            "order_role": local_order.order_role.value if local_order is not None else None,
            "exchange_order_type": exchange_order.order_type.value if exchange_order is not None else None,
        }
        return ReconciliationMismatch(
            symbol=symbol,
            mismatch_type=mismatch_type,
            severity="CRITICAL",
            reason=reason_code,
            local_ref=local_ref,
            exchange_ref=exchange_ref,
            metadata={key: value for key, value in metadata.items() if value is not None},
        )

    def _is_exchange_native_sl_order(self, order: OrderResponse) -> bool:
        if not order.reduce_only:
            return False
        if order.order_role == OrderRole.SL:
            return True
        if order.order_type in {OrderType.STOP_MARKET, OrderType.STOP_LIMIT, OrderType.TRAILING_STOP}:
            return True
        return order.trigger_price is not None

    def _is_reduce_only_exit_order(self, order: OrderResponse) -> bool:
        """Return True for exchange orders that may be exit protection.

        This is intentionally conservative for protection-health detection:
        role-marked TP/SL orders are treated as exit protection even if an
        adapter failed to expose reduceOnly. The monitor only blocks new
        entries and does not mutate or cancel the order.
        """
        return order.reduce_only or order.order_role in {
            OrderRole.SL,
            OrderRole.TP1,
            OrderRole.TP2,
            OrderRole.TP3,
            OrderRole.TP4,
            OrderRole.TP5,
        }

    def _find_matching_exchange_protection_order(
        self,
        local_order: OrderResponse,
        exchange_orders: List[OrderResponse],
    ) -> Optional[OrderResponse]:
        local_refs = {local_order.exchange_order_id, local_order.order_id} - {None, ""}
        for exchange_order in exchange_orders:
            exchange_refs = {exchange_order.exchange_order_id, exchange_order.order_id} - {None, ""}
            if local_refs & exchange_refs:
                return exchange_order
        return None

    def _find_matching_local_order(
        self,
        exchange_order: OrderResponse,
        local_orders: List[OrderResponse],
    ) -> Optional[OrderResponse]:
        exchange_refs = {exchange_order.exchange_order_id, exchange_order.order_id} - {None, ""}
        for local_order in local_orders:
            local_refs = {local_order.exchange_order_id, local_order.order_id} - {None, ""}
            if local_refs & exchange_refs:
                return local_order
        return None

    def _compare_orders_for_read_model(
        self,
        symbol: str,
        local_orders: List[OrderResponse],
        exchange_orders: List[OrderResponse],
    ) -> List[ReconciliationMismatch]:
        mismatches: List[ReconciliationMismatch] = []
        tolerance = Decimal("0.00000001")
        local_by_exchange_id = {
            order.exchange_order_id: order
            for order in local_orders
            if order.exchange_order_id
        }
        exchange_by_id = {
            order.exchange_order_id or order.order_id: order
            for order in exchange_orders
            if order.exchange_order_id or order.order_id
        }

        for local_order in local_orders:
            local_exchange_ref = local_order.exchange_order_id or local_order.order_id
            exchange_order = exchange_by_id.get(local_exchange_ref)
            if exchange_order is None:
                mismatches.append(
                    ReconciliationMismatch(
                        symbol=symbol,
                        mismatch_type="local_order_missing_on_exchange",
                        severity="WARNING",
                        local_ref=local_order.order_id,
                        exchange_ref=local_order.exchange_order_id,
                        reason="Local open order was not found in exchange open orders.",
                        metadata={
                            "order_role": local_order.order_role.value,
                            "local_status": local_order.status.value,
                        },
                    )
                )
                continue

            if local_order.status != exchange_order.status:
                mismatches.append(
                    ReconciliationMismatch(
                        symbol=symbol,
                        mismatch_type="order_status_mismatch",
                        severity="WARNING",
                        local_ref=local_order.order_id,
                        exchange_ref=exchange_order.exchange_order_id,
                        reason="Local order status differs from exchange order status.",
                        metadata={
                            "local_status": local_order.status.value,
                            "exchange_status": exchange_order.status.value,
                        },
                    )
                )

            if abs(local_order.amount - exchange_order.amount) > tolerance:
                mismatches.append(
                    ReconciliationMismatch(
                        symbol=symbol,
                        mismatch_type="order_qty_mismatch",
                        severity="WARNING",
                        local_ref=local_order.order_id,
                        exchange_ref=exchange_order.exchange_order_id,
                        reason="Local order quantity differs from exchange order quantity.",
                        metadata={
                            "local_qty": str(local_order.amount),
                            "exchange_qty": str(exchange_order.amount),
                            "tolerance": str(tolerance),
                        },
                    )
                )

        for exchange_order in exchange_orders:
            exchange_ref = exchange_order.exchange_order_id or exchange_order.order_id
            if exchange_ref not in local_by_exchange_id:
                mismatches.append(
                    ReconciliationMismatch(
                        symbol=symbol,
                        mismatch_type="exchange_order_missing_locally",
                        severity="WARNING",
                        local_ref=None,
                        exchange_ref=exchange_ref,
                        reason="Exchange open order was not found in local open orders.",
                        metadata={
                            "order_role": exchange_order.order_role.value,
                            "exchange_status": exchange_order.status.value,
                        },
                    )
                )

        return mismatches

    def _check_protection_coverage_for_read_model(
        self,
        symbol: str,
        local_positions: List[PositionInfo],
        local_orders: List[OrderResponse],
    ) -> List[ReconciliationMismatch]:
        mismatches: List[ReconciliationMismatch] = []
        if not local_positions:
            return mismatches

        open_orders = [order for order in local_orders if order.symbol == symbol]
        sl_orders = [order for order in open_orders if order.order_role == OrderRole.SL]
        tp_orders = [
            order
            for order in open_orders
            if order.order_role
            in {OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5}
        ]

        if not sl_orders and not tp_orders:
            mismatches.append(
                ReconciliationMismatch(
                    symbol=symbol,
                    mismatch_type="missing_any_protection",
                    severity="SEVERE",
                    local_ref=symbol,
                    exchange_ref=None,
                    reason="Local active position has no open SL or TP protection orders.",
                    metadata={"association_scope": "symbol_role_v0"},
                )
            )
        elif not sl_orders:
            mismatches.append(
                ReconciliationMismatch(
                    symbol=symbol,
                    mismatch_type="missing_sl_protection",
                    severity="SEVERE",
                    local_ref=symbol,
                    exchange_ref=None,
                    reason="Local active position has no open SL protection order.",
                    metadata={"association_scope": "symbol_role_v0"},
                )
            )
        elif not tp_orders:
            mismatches.append(
                ReconciliationMismatch(
                    symbol=symbol,
                    mismatch_type="missing_tp_protection",
                    severity="WARNING",
                    local_ref=symbol,
                    exchange_ref=None,
                    reason="Local active position has SL protection but no TP protection order.",
                    metadata={
                        "association_scope": "symbol_role_v0",
                        "expected_min_tp_count": 1,
                    },
                )
            )

        return mismatches

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
        if self._order_repository is None:
            return []

        active_statuses = {
            OrderStatus.SUBMITTED,
            OrderStatus.OPEN,
            OrderStatus.PARTIALLY_FILLED,
        }
        orders_by_id: Dict[str, Any] = {}

        try:
            if hasattr(self._order_repository, "get_open_orders"):
                for order in await self._order_repository.get_open_orders(symbol):
                    if getattr(order, "status", None) in active_statuses:
                        orders_by_id[getattr(order, "id", getattr(order, "order_id", ""))] = order

            if hasattr(self._order_repository, "get_orders_by_status"):
                for status in active_statuses:
                    for order in await self._order_repository.get_orders_by_status(status, symbol):
                        orders_by_id[getattr(order, "id", getattr(order, "order_id", ""))] = order

            result = [
                self._order_to_response(order)
                for order in orders_by_id.values()
            ]
            logger.debug(f"Local open orders for {symbol}: {len(result)}")
            return result
        except Exception as e:
            logger.error(f"Failed to get local open orders: {e}")
            raise

    async def _get_exchange_open_orders(self, symbol: str) -> List[OrderResponse]:
        """
        获取交易所未平订单列表

        Args:
            symbol: 币种对

        Returns:
            List[OrderResponse]: 交易所订单列表
        """
        try:
            if hasattr(self._gateway, "fetch_open_orders"):
                orders = await self._gateway.fetch_open_orders(symbol)
            else:
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
            ccxt_type = str(order.get('type', 'limit')).lower()
            order_type = OrderType.LIMIT
            if ccxt_type == 'market':
                order_type = OrderType.MARKET
            elif ccxt_type in {'stop', 'stop_market', 'stop market', 'stop_loss', 'stop_loss_market'}:
                order_type = OrderType.STOP_MARKET
            elif ccxt_type in {'stop limit', 'stop_limit', 'stop_loss_limit'}:
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
                if (
                    order_type in {OrderType.STOP_MARKET, OrderType.STOP_LIMIT}
                    or order.get('triggerPrice')
                    or order.get('stopPrice')
                ):
                    order_role = OrderRole.SL

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
                trigger_price=(
                    Decimal(str(order.get('triggerPrice') or order.get('stopPrice')))
                    if (order.get('triggerPrice') or order.get('stopPrice'))
                    else None
                ),
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
            order_id=getattr(order, 'order_id', getattr(order, 'id', '')),
            exchange_order_id=getattr(order, 'exchange_order_id', None),
            symbol=getattr(order, 'symbol', ''),
            order_type=getattr(order, 'order_type', OrderType.LIMIT),
            direction=getattr(order, 'direction', Direction.LONG),
            order_role=getattr(order, 'order_role', OrderRole.ENTRY),
            status=getattr(order, 'status', OrderStatus.OPEN),
            amount=getattr(order, 'amount', getattr(order, 'requested_qty', Decimal('0'))),
            filled_amount=getattr(order, 'filled_amount', getattr(order, 'filled_qty', Decimal('0'))),
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
        ghost_orders: List[GhostOrder] = None,
        imported_orders: List[ImportedOrder] = None,
        canceled_orphan_orders: List[ImportedOrder] = None,
    ) -> str:
        """
        生成对账结论摘要

        Args:
            missing_positions: 缺失仓位列表
            position_mismatches: 仓位不匹配列表
            orphan_orders: 孤儿订单列表
            order_mismatches: 订单不匹配列表
            ghost_orders: 幽灵订单列表（P0-003）
            imported_orders: 导入订单列表（P0-003）
            canceled_orphan_orders: 撤销的孤儿订单列表（P0-003）

        Returns:
            str: 对账摘要
        """
        ghost_orders = ghost_orders or []
        imported_orders = imported_orders or []
        canceled_orphan_orders = canceled_orphan_orders or []

        total = (
            len(missing_positions) +
            len(position_mismatches) +
            len(orphan_orders) +
            len(order_mismatches) +
            len(ghost_orders) +
            len(imported_orders) +
            len(canceled_orphan_orders)
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
        if ghost_orders:
            parts.append(f"幽灵订单 {len(ghost_orders)} 个 (已标记 CANCELLED)")
        if imported_orders:
            parts.append(f"导入订单 {len(imported_orders)} 个")
        if canceled_orphan_orders:
            parts.append(f"撤销孤儿订单 {len(canceled_orphan_orders)} 个")

        return f"发现 {total} 项差异：" + "，".join(parts)
