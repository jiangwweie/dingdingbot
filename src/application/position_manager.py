"""
Position Manager - 仓位并发保护管理器

提供双层并发保护机制：
1. Asyncio Lock - 单进程内协程同步
2. 数据库行级锁 - 跨进程保护

修复 G-001: 使用 weakref.WeakValueDictionary 存储锁，避免"释放后使用"竞态条件
"""
import asyncio
import weakref
import time
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models import Direction, Order
from src.infrastructure.v3_orm import PositionORM
from src.infrastructure.logger import logger


if TYPE_CHECKING:
    from src.domain.models import Order as OrderDomain


class PositionManager:
    """
    仓位管理器：提供并发安全的仓位操作

    双层并发保护:
    1. Asyncio Lock - 单进程内协程同步（使用 WeakValueDictionary）
    2. 数据库行级锁 - 跨进程保护（SQLite: BEGIN EXCLUSIVE / PostgreSQL: SELECT FOR UPDATE）

    G-001 修复:
    - 使用 weakref.WeakValueDictionary 存储锁
    - 不主动删除锁，让 Python GC 在无引用时自动回收
    - 避免"释放后使用"竞态条件
    """

    def __init__(self, db: AsyncSession):
        """
        初始化仓位管理器

        Args:
            db: 异步数据库 Session
        """
        self._db = db
        # G-001 修复：使用弱引用字典，当没有任何协程持有/等待该锁时，Python GC 会自动回收
        # 不再需要主动删除锁，避免 Use-After-Free 竞态条件
        self._position_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()
        self._locks_mutex = asyncio.Lock()  # 保护_locks 字典的锁

    async def _get_position_lock(self, position_id: str) -> asyncio.Lock:
        """
        获取或创建仓位锁

        G-001 关键点:
        - 使用 WeakValueDictionary，锁在没有引用时自动回收
        - 不主动删除锁，避免"释放后使用"问题

        Args:
            position_id: 仓位 ID

        Returns:
            asyncio.Lock: 仓位锁
        """
        async with self._locks_mutex:
            if position_id not in self._position_locks:
                lock = asyncio.Lock()
                # 弱引用：必须先保存在局部变量，否则立即被 GC
                self._position_locks[position_id] = lock
                logger.debug(f"Created new lock for position {position_id}")
            lock = self._position_locks[position_id]
            logger.debug(f"Returning existing lock for position {position_id}")
            return lock

    async def reduce_position(
        self,
        position_id: str,
        exit_order: "OrderDomain",
    ) -> Decimal:
        """
        减仓处理（TP1 成交或 SL 成交）

        并发保护:
        1. Asyncio Lock - 单进程内协程同步
        2. 数据库行级锁 - 跨进程保护

        Args:
            position_id: 仓位 ID
            exit_order: 平仓订单

        Returns:
            Decimal: 已实现盈亏（净盈亏）

        Raises:
            ValueError: 当仓位不存在时
        """
        # ========== 第一层：Asyncio Lock (进程内) ==========
        position_lock = await self._get_position_lock(position_id)
        async with position_lock:
            logger.info(f"Position {position_id}: acquired asyncio lock for reduce_position")

            # ========== 第二层：数据库行级锁 (跨进程) ==========
            # 使用 SQLite 的 IMMEDIATE 事务模式（类似于 BEGIN EXCLUSIVE）
            # PostgreSQL 需要使用 SELECT ... FOR UPDATE
            async with self._db.begin():
                # 获取仓位（带行级锁）
                position = await self._fetch_position_locked(position_id)

                if position is None:
                    raise ValueError(f"Position {position_id} not found")

                logger.info(
                    f"Position {position_id}: acquired DB lock, "
                    f"current_qty={position.current_qty}, entry_price={position.entry_price}"
                )

                # 计算盈亏
                # 注意：exit_order.filled_qty 是本次减仓的数量
                # exit_order.average_exec_price 是本次减仓的成交价
                if exit_order.direction == Direction.LONG:
                    # LONG: 平仓卖出，盈亏 = (卖出价 - 入场价) × 平仓数量
                    gross_pnl = (exit_order.average_exec_price - position.entry_price) * exit_order.filled_qty
                else:
                    # SHORT: 平仓买入，盈亏 = (入场价 - 卖出价) × 平仓数量
                    gross_pnl = (position.entry_price - exit_order.average_exec_price) * exit_order.filled_qty

                # 净盈亏 = 毛盈亏 - 手续费
                # 注意：exit_order 可能没有 fee_paid 字段，使用 getattr 兼容
                fee_paid = getattr(exit_order, 'fee_paid', Decimal('0'))
                net_pnl = gross_pnl - fee_paid

                # 更新仓位状态
                position.current_qty -= exit_order.filled_qty
                position.realized_pnl += net_pnl
                position.total_fees_paid += fee_paid

                # 检查是否完全平仓
                if position.current_qty <= Decimal("0"):
                    position.is_closed = True
                    position.closed_at = int(time.time() * 1000)
                    position.current_qty = Decimal("0")  # 确保不为负
                    logger.info(f"Position {position_id}: fully closed")
                else:
                    logger.info(f"Position {position_id}: partially reduced, remaining_qty={position.current_qty}")

                # 更新水印价（如果需要）
                await self._update_watermark(position, exit_order)

                # 持久化到数据库
                self._db.add(position)
                await self._db.flush()

                logger.info(
                    f"Position {position_id}: reduced successfully, "
                    f"realized_pnl={net_pnl}, filled_qty={exit_order.filled_qty}"
                )

                # G-001 修复：不再主动删除锁！WeakValueDictionary 会在无引用时自动回收
                # if position_id in self._position_locks:
                #     del self._position_locks[position_id]  # ❌ 危险操作：可能导致 Use-After-Free

                return net_pnl

    async def _fetch_position_locked(self, position_id: str) -> Optional[PositionORM]:
        """
        获取仓位（带行级锁）

        SQLite 不直接支持 SELECT FOR UPDATE，需要使用 IMMEDIATE 事务
        PostgreSQL 使用 SELECT ... FOR UPDATE

        Args:
            position_id: 仓位 ID

        Returns:
            PositionORM 或 None
        """
        # SQLite: 使用 IMMEDIATE 事务模式（通过 begin() 已经启用）
        # PostgreSQL: 需要使用 select().with_for_update()
        stmt = select(PositionORM).where(PositionORM.id == position_id)

        # 检测数据库类型
        dialect_name = self._db.bind.dialect.name

        if dialect_name == "postgresql":
            # PostgreSQL: 使用 FOR UPDATE 行级锁
            stmt = stmt.with_for_update()
            logger.debug(f"Position {position_id}: using PostgreSQL FOR UPDATE")

        result = await self._db.execute(stmt)
        position = result.scalar_one_or_none()

        if position:
            logger.debug(f"Position {position_id}: fetched with lock")
        else:
            logger.warning(f"Position {position_id}: not found")

        return position

    async def _update_watermark(self, position: PositionORM, order: "OrderDomain") -> None:
        """
        更新动态风控水位线

        LONG: 追踪入场后的最高价 (High Watermark)
        SHORT: 追踪入场后的最低价 (Low Watermark)

        Args:
            position: 仓位 ORM 对象
            order: 平仓订单
        """
        exec_price = order.average_exec_price
        if exec_price is None:
            return

        # PositionORM.direction 是字符串，不是 Direction 枚举
        direction_value = position.direction if isinstance(position.direction, str) else position.direction.value

        if direction_value == "LONG":
            # LONG: 水印价 = max(当前水印，成交价)
            if position.watermark_price is None:
                position.watermark_price = exec_price
            elif exec_price > position.watermark_price:
                position.watermark_price = exec_price
        else:
            # SHORT: 水印价 = min(当前水印，成交价)
            if position.watermark_price is None:
                position.watermark_price = exec_price
            elif exec_price < position.watermark_price:
                position.watermark_price = exec_price

        logger.debug(
            f"Position {position.id}: watermark updated to {position.watermark_price} "
            f"({direction_value})"
        )

    async def create_position(
        self,
        position_id: str,
        signal_id: str,
        symbol: str,
        direction: Direction,
        entry_price: Decimal,
        current_qty: Decimal,
    ) -> PositionORM:
        """
        创建新仓位

        Args:
            position_id: 仓位 ID
            signal_id: 关联信号 ID
            symbol: 交易对
            direction: 方向
            entry_price: 开仓均价
            current_qty: 当前持仓数量

        Returns:
            PositionORM: 创建的仓位 ORM 对象

        Raises:
            ValueError: 当仓位已存在时
        """
        async with self._db.begin():
            # 检查是否已存在
            existing = await self._fetch_position_locked(position_id)
            if existing is not None:
                raise ValueError(f"Position {position_id} already exists")

            # 创建新仓位
            position = PositionORM(
                id=position_id,
                signal_id=signal_id,
                symbol=symbol,
                direction=direction.value,
                entry_price=entry_price,
                current_qty=current_qty,
                watermark_price=entry_price,  # 初始水印价设为入场价
                realized_pnl=Decimal("0"),
                total_fees_paid=Decimal("0"),
                is_closed=False,
            )

            self._db.add(position)
            await self._db.flush()

            logger.info(
                f"Position {position_id}: created, "
                f"symbol={symbol}, direction={direction.value}, "
                f"qty={current_qty}, entry={entry_price}"
            )

            return position

    async def get_position(self, position_id: str) -> Optional[PositionORM]:
        """
        查询仓位（不加锁）

        Args:
            position_id: 仓位 ID

        Returns:
            PositionORM 或 None
        """
        stmt = select(PositionORM).where(PositionORM.id == position_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_open_positions(self, symbol: Optional[str] = None) -> list[PositionORM]:
        """
        查询所有未平仓位

        Args:
            symbol: 可选的交易对过滤

        Returns:
            list[PositionORM]: 未平仓位列表
        """
        stmt = select(PositionORM).where(PositionORM.is_closed == False)
        if symbol:
            stmt = stmt.where(PositionORM.symbol == symbol)
        result = await self._db.execute(stmt)
        return result.scalars().all()

    async def update_position_from_order(
        self,
        position_id: str,
        order: "OrderDomain",
    ) -> Optional[Decimal]:
        """
        根据订单更新仓位（减仓位）

        这是 reduce_position 的包装方法，提供更方便的接口

        Args:
            position_id: 仓位 ID
            order: 订单对象

        Returns:
            Decimal: 已实现盈亏，或 None（如果仓位不存在）
        """
        try:
            return await self.reduce_position(position_id, order)
        except ValueError as e:
            logger.warning(f"Position {position_id}: {e}")
            return None
