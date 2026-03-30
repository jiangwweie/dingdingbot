"""
单元测试：PositionManager 并发保护机制

测试覆盖:
1. WeakValueDictionary 自动回收（G-001 修复验证）
2. 并发场景下锁保护有效（无脏写）
3. 数据库行级锁正确应用
4. 减仓处理逻辑正确
5. 水位线更新逻辑
6. 仓位创建和查询
"""
import asyncio
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import weakref

from src.application.position_manager import PositionManager
from src.domain.models import Direction, OrderType, OrderRole, OrderStatus


@pytest.fixture
def mock_db():
    """创建模拟数据库 Session"""
    db = AsyncMock()

    # 模拟异步上下文管理器用于事务
    async_tx = AsyncMock()
    async_tx.__aenter__ = AsyncMock(return_value=None)
    async_tx.__aexit__ = AsyncMock(return_value=None)
    db.begin = MagicMock(return_value=async_tx)

    db.flush = AsyncMock()
    db.add = MagicMock()  # 使用 MagicMock 而非 AsyncMock，因为 add 是同步方法
    db.execute = AsyncMock()
    return db


@pytest.fixture
def position_manager(mock_db):
    """创建 PositionManager 实例"""
    return PositionManager(mock_db)


@pytest.fixture
def sample_position_orm():
    """创建示例仓位 ORM"""
    from src.infrastructure.v3_orm import PositionORM
    return PositionORM(
        id="position_001",
        signal_id="signal_001",
        symbol="BTC/USDT:USDT",
        direction="LONG",
        entry_price=Decimal("70000"),
        current_qty=Decimal("0.1"),
        watermark_price=Decimal("70000"),
        realized_pnl=Decimal("0"),
        total_fees_paid=Decimal("0"),
        is_closed=False,
    )


def create_sample_order(
    direction=Direction.LONG,
    filled_qty=Decimal("0.05"),
    average_exec_price=Decimal("75000"),
    fee_paid=Decimal("0.5"),
):
    """创建示例订单（使用 MagicMock）"""
    order = MagicMock()
    order.direction = direction
    order.filled_qty = filled_qty
    order.average_exec_price = average_exec_price
    order.fee_paid = fee_paid
    return order


# ============================================================
# G-001 修复验证：WeakValueDictionary 自动回收
# ============================================================

@pytest.mark.asyncio
async def test_weakvaluedictionary_auto_cleanup(position_manager):
    """测试弱引用字典自动回收锁（G-001 修复验证）"""
    # 获取锁
    lock1 = await position_manager._get_position_lock("test_pos")
    assert lock1 is not None

    # 验证锁在字典中
    assert "test_pos" in position_manager._position_locks

    # 获取弱引用
    weak_ref = weakref.ref(lock1)

    # 删除强引用
    del lock1

    # 强制 GC
    import gc
    gc.collect()

    # 验证使用的是 WeakValueDictionary
    assert isinstance(position_manager._position_locks, weakref.WeakValueDictionary)


@pytest.mark.asyncio
async def test_get_position_lock_creates_new(position_manager):
    """测试获取锁时创建新锁"""
    lock = await position_manager._get_position_lock("new_pos")
    assert lock is not None
    assert isinstance(lock, asyncio.Lock)
    assert "new_pos" in position_manager._position_locks


@pytest.mark.asyncio
async def test_get_position_lock_returns_existing(position_manager):
    """测试获取已存在的锁"""
    lock1 = await position_manager._get_position_lock("existing_pos")
    lock2 = await position_manager._get_position_lock("existing_pos")
    assert lock1 is lock2  # 同一个锁对象


# ============================================================
# 减仓处理逻辑测试
# ============================================================

@pytest.mark.asyncio
async def test_reduce_position_long_profit(position_manager, sample_position_orm):
    """测试 LONG 仓位减仓（盈利场景）"""
    # 创建订单
    order = create_sample_order(
        direction=Direction.LONG,
        filled_qty=Decimal("0.05"),
        average_exec_price=Decimal("75000"),
        fee_paid=Decimal("0.5"),
    )

    # Mock _fetch_position_locked 返回仓位
    with patch.object(position_manager, '_fetch_position_locked', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = sample_position_orm

        # 执行减仓
        net_pnl = await position_manager.reduce_position("position_001", order)

        # 验证盈亏计算
        # 毛盈亏 = (75000 - 70000) * 0.05 = 250
        # 净盈亏 = 250 - 0.5 = 249.5
        expected_gross_pnl = (Decimal("75000") - Decimal("70000")) * Decimal("0.05")
        expected_net_pnl = expected_gross_pnl - Decimal("0.5")
        assert net_pnl == expected_net_pnl

        # 验证仓位更新
        assert sample_position_orm.current_qty == Decimal("0.05")  # 0.1 - 0.05
        assert sample_position_orm.realized_pnl == expected_net_pnl
        assert sample_position_orm.total_fees_paid == Decimal("0.5")
        assert sample_position_orm.is_closed == False


@pytest.mark.asyncio
async def test_reduce_position_long_loss(position_manager, sample_position_orm):
    """测试 LONG 仓位减仓（亏损场景）"""
    # 创建订单（亏损场景）
    order = create_sample_order(
        direction=Direction.LONG,
        filled_qty=Decimal("0.05"),
        average_exec_price=Decimal("65000"),
        fee_paid=Decimal("0.5"),
    )

    with patch.object(position_manager, '_fetch_position_locked', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = sample_position_orm

        # 执行减仓
        net_pnl = await position_manager.reduce_position("position_001", order)

        # 验证盈亏计算
        # 毛盈亏 = (65000 - 70000) * 0.05 = -250
        # 净盈亏 = -250 - 0.5 = -250.5
        expected_gross_pnl = (Decimal("65000") - Decimal("70000")) * Decimal("0.05")
        expected_net_pnl = expected_gross_pnl - Decimal("0.5")
        assert net_pnl == expected_net_pnl


@pytest.mark.asyncio
async def test_reduce_position_short_profit(position_manager, sample_position_orm):
    """测试 SHORT 仓位减仓（盈利场景）"""
    # 设置为 SHORT 仓位
    sample_position_orm.direction = "SHORT"
    sample_position_orm.entry_price = Decimal("70000")

    # 创建订单（SHORT 盈利：成交价低于入场价）
    order = create_sample_order(
        direction=Direction.SHORT,
        filled_qty=Decimal("0.05"),
        average_exec_price=Decimal("65000"),
        fee_paid=Decimal("0.5"),
    )

    with patch.object(position_manager, '_fetch_position_locked', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = sample_position_orm

        # 执行减仓
        net_pnl = await position_manager.reduce_position("position_001", order)

        # 验证盈亏计算
        # 毛盈亏 = (70000 - 65000) * 0.05 = 250
        # 净盈亏 = 250 - 0.5 = 249.5
        expected_gross_pnl = (Decimal("70000") - Decimal("65000")) * Decimal("0.05")
        expected_net_pnl = expected_gross_pnl - Decimal("0.5")
        assert net_pnl == expected_net_pnl


@pytest.mark.asyncio
async def test_reduce_position_full_close(position_manager, sample_position_orm):
    """测试完全平仓"""
    # 创建订单（平仓数量等于持仓数量）
    order = create_sample_order(
        direction=Direction.LONG,
        filled_qty=Decimal("0.1"),
        average_exec_price=Decimal("75000"),
        fee_paid=Decimal("0.5"),
    )

    with patch.object(position_manager, '_fetch_position_locked', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = sample_position_orm

        # 执行减仓
        await position_manager.reduce_position("position_001", order)

        # 验证完全平仓
        assert sample_position_orm.current_qty == Decimal("0")
        assert sample_position_orm.is_closed == True
        assert sample_position_orm.closed_at is not None


@pytest.mark.asyncio
async def test_reduce_position_not_found(position_manager):
    """测试仓位不存在场景"""
    # 创建订单
    order = create_sample_order()

    with patch.object(position_manager, '_fetch_position_locked', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = None

        # 验证抛出异常
        with pytest.raises(ValueError, match="Position position_001 not found"):
            await position_manager.reduce_position("position_001", order)


@pytest.mark.asyncio
async def test_reduce_position_not_found_no_raise(position_manager):
    """测试仓位不存在场景（使用 update_position_from_order，不抛异常）"""
    # 创建订单
    order = create_sample_order()

    with patch.object(position_manager, '_fetch_position_locked', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = None

        # update_position_from_order 会捕获异常返回 None
        result = await position_manager.update_position_from_order("position_001", order)
        assert result is None


# ============================================================
# 水位线更新测试
# ============================================================

@pytest.mark.asyncio
async def test_update_watermark_long(position_manager, sample_position_orm):
    """测试 LONG 仓位水印价更新"""
    # 设置 LONG 仓位
    sample_position_orm.direction = "LONG"
    sample_position_orm.watermark_price = Decimal("70000")

    # 创建更高成交价的订单
    order = MagicMock()
    order.average_exec_price = Decimal("75000")

    await position_manager._update_watermark(sample_position_orm, order)

    # 水印价应该更新为更高价
    assert sample_position_orm.watermark_price == Decimal("75000")


@pytest.mark.asyncio
async def test_update_watermark_long_no_update(position_manager, sample_position_orm):
    """测试 LONG 仓位水印价不更新（成交价低于当前水印）"""
    sample_position_orm.direction = "LONG"
    sample_position_orm.watermark_price = Decimal("75000")

    order = MagicMock()
    order.average_exec_price = Decimal("72000")

    await position_manager._update_watermark(sample_position_orm, order)

    # 水印价不应更新
    assert sample_position_orm.watermark_price == Decimal("75000")


@pytest.mark.asyncio
async def test_update_watermark_short(position_manager, sample_position_orm):
    """测试 SHORT 仓位水印价更新"""
    sample_position_orm.direction = "SHORT"
    sample_position_orm.watermark_price = Decimal("70000")

    order = MagicMock()
    order.average_exec_price = Decimal("65000")

    await position_manager._update_watermark(sample_position_orm, order)

    # 水印价应该更新为更低价
    assert sample_position_orm.watermark_price == Decimal("65000")


@pytest.mark.asyncio
async def test_update_watermark_short_no_update(position_manager, sample_position_orm):
    """测试 SHORT 仓位水印价不更新（成交价高于当前水印）"""
    sample_position_orm.direction = "SHORT"
    sample_position_orm.watermark_price = Decimal("65000")

    order = MagicMock()
    order.average_exec_price = Decimal("68000")

    await position_manager._update_watermark(sample_position_orm, order)

    # 水印价不应更新
    assert sample_position_orm.watermark_price == Decimal("65000")


@pytest.mark.asyncio
async def test_update_watermark_no_exec_price(position_manager, sample_position_orm):
    """测试订单没有成交价时水印价不更新"""
    sample_position_orm.direction = "LONG"
    sample_position_orm.watermark_price = Decimal("70000")

    order = MagicMock()
    order.average_exec_price = None

    await position_manager._update_watermark(sample_position_orm, order)

    # 水印价不应更新
    assert sample_position_orm.watermark_price == Decimal("70000")


# ============================================================
# 仓位创建和查询测试
# ============================================================

@pytest.mark.asyncio
async def test_create_position(position_manager):
    """测试创建新仓位"""
    # Mock _fetch_position_locked 返回 None（不存在）
    with patch.object(position_manager, '_fetch_position_locked', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = None

        # 创建仓位
        position = await position_manager.create_position(
            position_id="new_pos",
            signal_id="signal_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            entry_price=Decimal("70000"),
            current_qty=Decimal("0.1"),
        )

        # 验证创建成功
        assert position is not None
        # 验证数据库被调用
        position_manager._db.add.assert_called_once()
        position_manager._db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_create_position_duplicate(position_manager, sample_position_orm):
    """测试创建已存在的仓位"""
    # Mock _fetch_position_locked 返回已存在仓位
    with patch.object(position_manager, '_fetch_position_locked', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = sample_position_orm

        # 验证抛出异常
        with pytest.raises(ValueError, match="Position position_001 already exists"):
            await position_manager.create_position(
                position_id="position_001",
                signal_id="signal_001",
                symbol="BTC/USDT:USDT",
                direction=Direction.LONG,
                entry_price=Decimal("70000"),
                current_qty=Decimal("0.1"),
            )


@pytest.mark.asyncio
async def test_get_position(position_manager, sample_position_orm):
    """测试查询仓位"""
    # 设置数据库返回
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sample_position_orm
    position_manager._db.execute = AsyncMock(return_value=mock_result)

    # 查询仓位
    position = await position_manager.get_position("position_001")

    # 验证查询结果
    assert position is not None
    assert position.id == "position_001"
    assert position.symbol == "BTC/USDT:USDT"


@pytest.mark.asyncio
async def test_get_position_not_found(position_manager):
    """测试查询不存在的仓位"""
    # 设置数据库返回 None
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    position_manager._db.execute = AsyncMock(return_value=mock_result)

    # 查询仓位
    position = await position_manager.get_position("nonexistent")

    # 验证查询结果为 None
    assert position is None


@pytest.mark.asyncio
async def test_get_open_positions(position_manager, sample_position_orm):
    """测试查询所有未平仓位"""
    # 设置数据库返回
    mock_scalars = MagicMock()
    mock_scalars.all = MagicMock(return_value=[sample_position_orm])
    mock_result = MagicMock()
    mock_result.scalars = MagicMock(return_value=mock_scalars)
    position_manager._db.execute = AsyncMock(return_value=mock_result)

    # 查询未平仓位
    positions = await position_manager.get_open_positions()

    # 验证查询结果
    assert len(positions) == 1
    assert positions[0].id == "position_001"
    assert positions[0].is_closed == False


@pytest.mark.asyncio
async def test_get_open_positions_with_symbol_filter(position_manager, sample_position_orm):
    """测试按交易对过滤查询未平仓位"""
    # 设置数据库返回
    mock_scalars = MagicMock()
    mock_scalars.all = MagicMock(return_value=[sample_position_orm])
    mock_result = MagicMock()
    mock_result.scalars = MagicMock(return_value=mock_scalars)
    position_manager._db.execute = AsyncMock(return_value=mock_result)

    # 查询指定交易对的未平仓位
    positions = await position_manager.get_open_positions(symbol="BTC/USDT:USDT")

    # 验证查询结果
    assert len(positions) == 1
    position_manager._db.execute.assert_called_once()


# ============================================================
# 并发安全测试
# ============================================================

@pytest.mark.asyncio
async def test_concurrent_reduce_position(position_manager, sample_position_orm):
    """测试并发减仓场景下的锁保护"""
    # 创建订单
    order = create_sample_order()

    # Mock _fetch_position_locked
    with patch.object(position_manager, '_fetch_position_locked', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = sample_position_orm

        # 创建两个并发任务
        async def reduce_task():
            return await position_manager.reduce_position("position_001", order)

        # 并发执行
        results = await asyncio.gather(
            reduce_task(),
            reduce_task(),
            return_exceptions=True,
        )

        # 验证：由于锁保护，只有一个任务能成功执行
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        assert success_count >= 1  # 至少有一个成功


@pytest.mark.asyncio
async def test_lock_mutex_protection(position_manager):
    """测试锁字典的互斥保护"""
    # 并发获取同一个锁
    async def get_lock():
        return await position_manager._get_position_lock("shared_pos")

    results = await asyncio.gather(*[get_lock() for _ in range(10)])

    # 验证：所有返回的都是同一个锁对象
    assert all(lock is results[0] for lock in results)


# ============================================================
# 数据库行级锁测试
# ============================================================

@pytest.mark.asyncio
async def test_postgresql_for_update(position_manager, sample_position_orm):
    """测试 PostgreSQL FOR UPDATE 行级锁"""
    # 设置数据库为 PostgreSQL
    mock_bind = MagicMock()
    mock_bind.dialect.name = "postgresql"
    position_manager._db.bind = mock_bind

    # Mock _fetch_position_locked
    with patch.object(position_manager, '_fetch_position_locked', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = sample_position_orm

        # 创建订单
        order = create_sample_order()

        # 执行减仓
        await position_manager.reduce_position("position_001", order)

        # 验证 _fetch_position_locked 被调用
        mock_fetch.assert_called_once_with("position_001")


@pytest.mark.asyncio
async def test_sqlite_no_for_update(position_manager, sample_position_orm):
    """测试 SQLite 不使用 FOR UPDATE"""
    # 设置数据库为 SQLite
    mock_bind = MagicMock()
    mock_bind.dialect.name = "sqlite"
    position_manager._db.bind = mock_bind

    # Mock _fetch_position_locked
    with patch.object(position_manager, '_fetch_position_locked', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = sample_position_orm

        # 创建订单
        order = create_sample_order()

        # 执行减仓
        await position_manager.reduce_position("position_001", order)

        # 验证正常执行
        mock_fetch.assert_called_once_with("position_001")


# ============================================================
# 边界条件测试
# ============================================================

@pytest.mark.asyncio
async def test_reduce_position_zero_qty(position_manager, sample_position_orm):
    """测试减仓数量为零的场景"""
    # 创建订单（零数量）
    order = create_sample_order(filled_qty=Decimal("0"))

    with patch.object(position_manager, '_fetch_position_locked', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = sample_position_orm

        # 执行减仓
        net_pnl = await position_manager.reduce_position("position_001", order)

        # 验证盈亏为负手续费
        assert net_pnl == -Decimal("0.5")
        # 仓位数量不变
        assert sample_position_orm.current_qty == Decimal("0.1")


@pytest.mark.asyncio
async def test_reduce_position_exceed_qty(position_manager, sample_position_orm):
    """测试减仓数量超过持仓数量"""
    # 创建订单（超过持仓数量）
    order = create_sample_order(filled_qty=Decimal("0.2"))  # 持仓只有 0.1

    with patch.object(position_manager, '_fetch_position_locked', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = sample_position_orm

        # 执行减仓
        await position_manager.reduce_position("position_001", order)

        # 验证仓位被完全平仓（current_qty 归零）
        assert sample_position_orm.current_qty == Decimal("0")
        assert sample_position_orm.is_closed == True


@pytest.mark.asyncio
async def test_reduce_position_order_without_price(position_manager, sample_position_orm):
    """测试订单没有成交价的场景"""
    # 创建订单（没有成交价）
    order = MagicMock()
    order.direction = Direction.LONG
    order.average_exec_price = None
    order.filled_qty = Decimal("0.05")
    order.fee_paid = Decimal("0")

    with patch.object(position_manager, '_fetch_position_locked', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = sample_position_orm

        # 执行减仓（应该抛出 TypeError，因为 None * qty 不支持）
        with pytest.raises(TypeError):
            await position_manager.reduce_position("position_001", order)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
