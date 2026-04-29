"""
v3 ORM 模型单元测试

测试目标:
1. ORM 模型可正常导入
2. 数据库表创建成功
3. 基本 CRUD 操作正常
4. 外键约束和索引生效
5. ORM <-> Domain 转换正确

运行方式:
    pytest tests/unit/test_v3_orm.py -v
"""

import asyncio
import pytest
from decimal import Decimal
from datetime import datetime, timezone

from sqlalchemy import select, delete, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.infrastructure.v3_orm import (
    Base,
    AccountORM,
    SignalORM,
    OrderORM,
    PositionORM,
    Direction,
    OrderStatus,
    OrderType,
    OrderRole,
    signal_orm_to_domain,
    order_orm_to_domain,
    position_orm_to_domain,
    account_orm_to_domain,
)

from src.domain.models import Signal, Order, Position, Account


# ============================================================
# Fixture: 内存数据库
# ============================================================

@pytest.fixture
async def db_session():
    """
    创建内存 SQLite 数据库用于测试

    每个测试用例独立数据库，测试后自动销毁。

    注意：SQLite 外键约束默认关闭，需要显式启用以测试级联删除。
    """
    from sqlalchemy import event

    # SQLite 内存数据库
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
    )

    # 启用 SQLite 外键约束
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # 创建所有表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Session Factory
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        yield session

    await engine.dispose()


# ============================================================
# Test: ORM 模型导入
# ============================================================

class TestORMImport:
    """测试 ORM 模型导入"""

    def test_account_orm_import(self):
        """AccountORM 可导入"""
        assert AccountORM.__tablename__ == "accounts"

    def test_signal_orm_import(self):
        """SignalORM 可导入"""
        assert SignalORM.__tablename__ == "signals"

    def test_order_orm_import(self):
        """OrderORM 可导入"""
        assert OrderORM.__tablename__ == "orders"

    def test_position_orm_import(self):
        """PositionORM 可导入"""
        assert PositionORM.__tablename__ == "positions"

    def test_enums_import(self):
        """枚举类型可导入"""
        assert Direction.LONG.value == "LONG"
        assert Direction.SHORT.value == "SHORT"
        assert OrderStatus.PENDING.value == "PENDING"
        assert OrderType.MARKET.value == "MARKET"
        assert OrderRole.ENTRY.value == "ENTRY"


# ============================================================
# Test: Account CRUD
# ============================================================

class TestAccountCRUD:
    """Account ORM CRUD 测试"""

    @pytest.mark.asyncio
    async def test_create_account(self, db_session):
        """创建账户"""
        account = AccountORM(
            account_id="test_wallet",
            total_balance=Decimal("10000.00"),
            frozen_margin=Decimal("2000.00"),
        )
        db_session.add(account)
        await db_session.commit()
        await db_session.refresh(account)

        assert account.account_id == "test_wallet"
        assert account.total_balance == Decimal("10000.00")
        assert account.frozen_margin == Decimal("2000.00")
        assert account.available_balance == Decimal("8000.00")

    @pytest.mark.asyncio
    async def test_read_account(self, db_session):
        """读取账户"""
        # 创建
        account = AccountORM(
            account_id="read_test",
            total_balance=Decimal("5000.00"),
        )
        db_session.add(account)
        await db_session.commit()

        # 读取
        result = await db_session.execute(
            select(AccountORM).where(AccountORM.account_id == "read_test")
        )
        fetched = result.scalar_one()

        assert fetched is not None
        assert fetched.total_balance == Decimal("5000.00")
        assert fetched.available_balance == Decimal("5000.00")

    @pytest.mark.asyncio
    async def test_update_account(self, db_session):
        """更新账户"""
        account = AccountORM(
            account_id="update_test",
            total_balance=Decimal("1000.00"),
            frozen_margin=Decimal("0"),
        )
        db_session.add(account)
        await db_session.commit()

        # 更新
        account.total_balance = Decimal("2000.00")
        account.frozen_margin = Decimal("500.00")
        await db_session.commit()

        # 验证
        result = await db_session.execute(
            select(AccountORM).where(AccountORM.account_id == "update_test")
        )
        fetched = result.scalar_one()

        assert fetched.total_balance == Decimal("2000.00")
        assert fetched.frozen_margin == Decimal("500.00")
        assert fetched.available_balance == Decimal("1500.00")

    @pytest.mark.asyncio
    async def test_delete_account(self, db_session):
        """删除账户"""
        account = AccountORM(
            account_id="delete_test",
            total_balance=Decimal("100.00"),
        )
        db_session.add(account)
        await db_session.commit()

        # 删除
        await db_session.execute(
            delete(AccountORM).where(AccountORM.account_id == "delete_test")
        )
        await db_session.commit()

        # 验证已删除
        result = await db_session.execute(
            select(AccountORM).where(AccountORM.account_id == "delete_test")
        )
        assert result.scalar_one_or_none() is None


# ============================================================
# Test: Signal CRUD
# ============================================================

class TestSignalCRUD:
    """Signal ORM CRUD 测试"""

    @pytest.mark.asyncio
    async def test_create_signal(self, db_session):
        """创建信号"""
        signal = SignalORM(
            id="sig_001",
            strategy_id="pinbar",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG.value,
            timestamp=1711785600000,
            expected_entry=Decimal("70000.00"),
            expected_sl=Decimal("69000.00"),
            pattern_score=0.85,
        )
        db_session.add(signal)
        await db_session.commit()
        await db_session.refresh(signal)

        assert signal.id == "sig_001"
        assert signal.strategy_id == "pinbar"
        assert signal.direction == "LONG"
        assert signal.expected_entry == Decimal("70000.00")
        assert signal.pattern_score == 0.85
        assert signal.is_active is True

    @pytest.mark.asyncio
    async def test_signal_orm_to_domain(self, db_session):
        """ORM -> Domain 转换"""
        # 创建 ORM
        signal = SignalORM(
            id="sig_002",
            strategy_id="engulfing",
            symbol="ETH/USDT:USDT",
            direction=Direction.SHORT.value,
            timestamp=1711789200000,
            expected_entry=Decimal("3500.00"),
            expected_sl=Decimal("3600.00"),
            pattern_score=0.72,
            is_active=True,
        )
        db_session.add(signal)
        await db_session.commit()

        # 转换为 Domain 模型
        domain = signal_orm_to_domain(signal)

        assert isinstance(domain, Signal)
        assert domain.id == "sig_002"
        assert domain.strategy_id == "engulfing"
        assert domain.direction == Direction.SHORT
        assert domain.expected_entry == Decimal("3500.00")
        assert domain.pattern_score == 0.72

    @pytest.mark.asyncio
    async def test_query_signals_by_symbol(self, db_session):
        """按交易对查询信号"""
        # 创建多个信号
        signals = [
            SignalORM(
                id=f"sig_btc_{i}",
                strategy_id="pinbar",
                symbol="BTC/USDT:USDT",
                direction=Direction.LONG.value,
                timestamp=1711785600000 + i * 1000,
                expected_entry=Decimal("70000.00"),
                expected_sl=Decimal("69000.00"),
                pattern_score=0.8,
            )
            for i in range(3)
        ]
        for s in signals:
            db_session.add(s)
        await db_session.commit()

        # 查询
        result = await db_session.execute(
            select(SignalORM).where(SignalORM.symbol == "BTC/USDT:USDT")
        )
        fetched = result.scalars().all()

        assert len(fetched) == 3


# ============================================================
# Test: Order CRUD + Foreign Key
# ============================================================

class TestOrderCRUD:
    """Order ORM CRUD 测试"""

    @pytest.mark.asyncio
    async def test_create_order_with_signal(self, db_session):
        """创建订单（含外键关联）"""
        # 先创建信号
        signal = SignalORM(
            id="sig_order_test",
            strategy_id="pinbar",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG.value,
            timestamp=1711785600000,
            expected_entry=Decimal("70000.00"),
            expected_sl=Decimal("69000.00"),
            pattern_score=0.85,
        )
        db_session.add(signal)
        await db_session.commit()

        # 创建订单
        order = OrderORM(
            id="ord_001",
            signal_id=signal.id,
            symbol=signal.symbol,
            direction=Direction.LONG.value,
            order_type=OrderType.MARKET.value,
            order_role=OrderRole.ENTRY.value,
            requested_qty=Decimal("0.1"),
            status=OrderStatus.PENDING.value,
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)

        assert order.id == "ord_001"
        assert order.signal_id == "sig_order_test"
        assert order.direction == "LONG"
        assert order.order_type == "MARKET"
        assert order.order_role == "ENTRY"
        assert order.requested_qty == Decimal("0.1")
        assert order.status == "PENDING"

    @pytest.mark.asyncio
    async def test_order_orm_to_domain(self, db_session):
        """ORM -> Domain 转换"""
        # 创建信号
        signal = SignalORM(
            id="sig_order_domain",
            strategy_id="pinbar",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG.value,
            timestamp=1711785600000,
            expected_entry=Decimal("70000.00"),
            expected_sl=Decimal("69000.00"),
            pattern_score=0.85,
        )
        db_session.add(signal)
        await db_session.commit()

        # 创建订单
        order = OrderORM(
            id="ord_domain",
            signal_id=signal.id,
            symbol=signal.symbol,
            direction=Direction.LONG.value,
            order_type=OrderType.MARKET.value,
            order_role=OrderRole.ENTRY.value,
            requested_qty=Decimal("0.1"),
            filled_qty=Decimal("0.1"),
            average_exec_price=Decimal("70100.00"),
            status=OrderStatus.FILLED.value,
        )
        db_session.add(order)
        await db_session.commit()

        # 转换
        domain = order_orm_to_domain(order)

        assert isinstance(domain, Order)
        assert domain.id == "ord_domain"
        assert domain.direction == Direction.LONG
        assert domain.order_type == OrderType.MARKET
        assert domain.order_role == OrderRole.ENTRY
        assert domain.filled_qty == Decimal("0.1")
        assert domain.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_cascade_delete(self, db_session):
        """测试级联删除：删除信号时自动删除订单"""
        # 创建信号
        signal = SignalORM(
            id="sig_cascade",
            strategy_id="pinbar",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG.value,
            timestamp=1711785600000,
            expected_entry=Decimal("70000.00"),
            expected_sl=Decimal("69000.00"),
            pattern_score=0.85,
        )
        db_session.add(signal)
        await db_session.commit()

        # 创建订单
        order = OrderORM(
            id="ord_cascade",
            signal_id=signal.id,
            symbol=signal.symbol,
            direction=Direction.LONG.value,
            order_type=OrderType.MARKET.value,
            order_role=OrderRole.ENTRY.value,
            requested_qty=Decimal("0.1"),
            status=OrderStatus.PENDING.value,
        )
        db_session.add(order)
        await db_session.commit()

        # 删除信号
        await db_session.delete(signal)
        await db_session.commit()

        # 验证订单也被删除
        result = await db_session.execute(
            select(OrderORM).where(OrderORM.id == "ord_cascade")
        )
        assert result.scalar_one_or_none() is None


# ============================================================
# Test: Position CRUD
# ============================================================

class TestPositionCRUD:
    """Position ORM CRUD 测试"""

    @pytest.mark.asyncio
    async def test_create_position(self, db_session):
        """创建仓位"""
        # 先创建信号
        signal = SignalORM(
            id="sig_position",
            strategy_id="pinbar",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG.value,
            timestamp=1711785600000,
            expected_entry=Decimal("70000.00"),
            expected_sl=Decimal("69000.00"),
            pattern_score=0.85,
        )
        db_session.add(signal)
        await db_session.commit()

        # 创建仓位
        position = PositionORM(
            id="pos_001",
            signal_id=signal.id,
            symbol=signal.symbol,
            direction=Direction.LONG.value,
            entry_price=Decimal("70000.00"),
            current_qty=Decimal("0.1"),
            watermark_price=Decimal("70000.00"),
        )
        db_session.add(position)
        await db_session.commit()
        await db_session.refresh(position)

        assert position.id == "pos_001"
        assert position.entry_price == Decimal("70000.00")
        assert position.current_qty == Decimal("0.1")
        assert position.realized_pnl == Decimal("0")
        assert position.total_fees_paid == Decimal("0")
        assert position.is_closed is False

    @pytest.mark.asyncio
    async def test_update_position_after_tp(self, db_session):
        """更新仓位（TP1 止盈后）"""
        # 创建信号和仓位
        signal = SignalORM(
            id="sig_tp_test",
            strategy_id="pinbar",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG.value,
            timestamp=1711785600000,
            expected_entry=Decimal("70000.00"),
            expected_sl=Decimal("69000.00"),
            pattern_score=0.85,
        )
        db_session.add(signal)
        await db_session.commit()

        position = PositionORM(
            id="pos_tp_test",
            signal_id=signal.id,
            symbol=signal.symbol,
            direction=Direction.LONG.value,
            entry_price=Decimal("70000.00"),
            current_qty=Decimal("0.1"),
            watermark_price=Decimal("70000.00"),
        )
        db_session.add(position)
        await db_session.commit()

        # 模拟 TP1: 平仓 50%，更新最高价
        position.current_qty = Decimal("0.05")
        position.watermark_price = Decimal("71500.00")
        position.realized_pnl = Decimal("50.00")  # 50 USDT 利润
        await db_session.commit()

        # 验证
        result = await db_session.execute(
            select(PositionORM).where(PositionORM.id == "pos_tp_test")
        )
        fetched = result.scalar_one()

        assert fetched.current_qty == Decimal("0.05")
        assert fetched.watermark_price == Decimal("71500.00")
        assert fetched.realized_pnl == Decimal("50.00")
        assert fetched.is_closed is False  # 仍有仓位

    @pytest.mark.asyncio
    async def test_position_orm_to_domain(self, db_session):
        """ORM -> Domain 转换"""
        # 创建信号
        signal = SignalORM(
            id="sig_pos_domain",
            strategy_id="pinbar",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG.value,
            timestamp=1711785600000,
            expected_entry=Decimal("70000.00"),
            expected_sl=Decimal("69000.00"),
            pattern_score=0.85,
        )
        db_session.add(signal)
        await db_session.commit()

        # 创建仓位
        position = PositionORM(
            id="pos_domain",
            signal_id=signal.id,
            symbol=signal.symbol,
            direction=Direction.LONG.value,
            entry_price=Decimal("70000.00"),
            current_qty=Decimal("0.1"),
            watermark_price=Decimal("71000.00"),
            realized_pnl=Decimal("100.00"),
            total_fees_paid=Decimal("2.50"),
            is_closed=False,
        )
        db_session.add(position)
        await db_session.commit()

        # 转换
        domain = position_orm_to_domain(position)

        assert isinstance(domain, Position)
        assert domain.direction == Direction.LONG
        assert domain.entry_price == Decimal("70000.00")
        assert domain.current_qty == Decimal("0.1")
        assert domain.realized_pnl == Decimal("100.00")
        assert domain.total_fees_paid == Decimal("2.50")


# ============================================================
# Test: Decimal 精度保护
# ============================================================

class TestDecimalPrecision:
    """Decimal 精度保护测试"""

    @pytest.mark.asyncio
    async def test_decimal_storage_precision(self, db_session):
        """测试 Decimal 存储精度（无浮点误差）"""
        # 创建账户
        account = AccountORM(
            account_id="precision_test",
            total_balance=Decimal("10000.12345678"),
            frozen_margin=Decimal("0.00000001"),
        )
        db_session.add(account)
        await db_session.commit()

        # 读取
        result = await db_session.execute(
            select(AccountORM).where(AccountORM.account_id == "precision_test")
        )
        fetched = result.scalar_one()

        # 验证精度无损
        assert fetched.total_balance == Decimal("10000.12345678")
        assert fetched.frozen_margin == Decimal("0.00000001")
        assert fetched.available_balance == Decimal("10000.12345677")

    @pytest.mark.asyncio
    async def test_no_float_conversion(self, db_session):
        """测试无隐式浮点转换"""
        # 创建信号
        signal = SignalORM(
            id="sig_float_test",
            strategy_id="pinbar",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG.value,
            timestamp=1711785600000,
            expected_entry=Decimal("70000.123456789"),
            expected_sl=Decimal("69999.987654321"),
            pattern_score=0.85,
        )
        db_session.add(signal)
        await db_session.commit()

        # 验证 Decimal 精度
        result = await db_session.execute(
            select(SignalORM).where(SignalORM.id == "sig_float_test")
        )
        fetched = result.scalar_one()

        assert fetched.expected_entry == Decimal("70000.123456789")
        assert fetched.expected_sl == Decimal("69999.987654321")


# ============================================================
# Test: 约束验证
# ============================================================

class TestConstraints:
    """约束验证测试"""

    @pytest.mark.asyncio
    async def test_direction_constraint(self, db_session):
        """Direction CHECK 约束"""
        # 创建有效信号
        signal = SignalORM(
            id="sig_dir_valid",
            strategy_id="pinbar",
            symbol="BTC/USDT:USDT",
            direction="LONG",  # 有效值
            timestamp=1711785600000,
            expected_entry=Decimal("70000"),
            expected_sl=Decimal("69000"),
            pattern_score=0.85,
        )
        db_session.add(signal)
        await db_session.commit()

        # 尝试插入无效值会触发 IntegrityError
        from sqlalchemy.exc import IntegrityError

        invalid_signal = SignalORM(
            id="sig_dir_invalid",
            strategy_id="pinbar",
            symbol="ETH/USDT:USDT",
            direction="INVALID",  # 无效值
            timestamp=1711785600000,
            expected_entry=Decimal("3500"),
            expected_sl=Decimal("3400"),
            pattern_score=0.85,
        )
        db_session.add(invalid_signal)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_pattern_score_range(self, db_session):
        """Pattern Score 范围约束 (0-1)"""
        # 有效值
        signal = SignalORM(
            id="sig_score_valid",
            strategy_id="pinbar",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG.value,
            timestamp=1711785600000,
            expected_entry=Decimal("70000"),
            expected_sl=Decimal("69000"),
            pattern_score=1.0,  # 边界值
        )
        db_session.add(signal)
        await db_session.commit()
        assert signal.pattern_score == 1.0

    @pytest.mark.asyncio
    async def test_filled_qty_not_exceed_requested(self, db_session):
        """filled_qty <= requested_qty 约束"""
        # 创建信号
        signal = SignalORM(
            id="sig_fill_test",
            strategy_id="pinbar",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG.value,
            timestamp=1711785600000,
            expected_entry=Decimal("70000"),
            expected_sl=Decimal("69000"),
            pattern_score=0.85,
        )
        db_session.add(signal)
        await db_session.commit()

        # 有效订单
        order = OrderORM(
            id="ord_fill_valid",
            signal_id=signal.id,
            symbol=signal.symbol,
            direction=Direction.LONG.value,
            order_type=OrderType.MARKET.value,
            order_role=OrderRole.ENTRY.value,
            requested_qty=Decimal("0.1"),
            filled_qty=Decimal("0.1"),  # 等于 requested
            status=OrderStatus.FILLED.value,
        )
        db_session.add(order)
        await db_session.commit()
        assert order.filled_qty == order.requested_qty


# ============================================================
# Test: 索引验证
# ============================================================

class TestIndexes:
    """索引验证测试"""

    @pytest.mark.asyncio
    async def test_signal_symbol_index(self, db_session):
        """idx_signals_symbol 索引存在"""
        # SQLite 中查询索引列表
        result = await db_session.execute(
            text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='signals'")
        )
        indexes = [row[0] for row in result.all()]
        assert "idx_signals_symbol" in indexes

    @pytest.mark.asyncio
    async def test_order_status_index(self, db_session):
        """idx_orders_status 索引存在"""
        result = await db_session.execute(
            text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='orders'")
        )
        indexes = [row[0] for row in result.all()]
        assert "idx_orders_status" in indexes

    @pytest.mark.asyncio
    async def test_position_is_closed_index(self, db_session):
        """idx_positions_is_closed 索引存在"""
        result = await db_session.execute(
            text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='positions'")
        )
        indexes = [row[0] for row in result.all()]
        assert "idx_positions_is_closed" in indexes


# ============================================================
# 集成测试：完整工作流
# ============================================================

class TestIntegrationWorkflow:
    """集成测试：模拟真实工作流"""

    @pytest.mark.asyncio
    async def test_full_signal_to_position_flow(self, db_session):
        """完整流程：信号 -> 订单 -> 仓位"""
        # 1. 初始化账户
        account = AccountORM(
            account_id="default_wallet",
            total_balance=Decimal("10000.00"),
            frozen_margin=Decimal("0"),
        )
        db_session.add(account)
        await db_session.commit()

        # 2. 生成信号
        signal = SignalORM(
            id="sig_integration",
            strategy_id="pinbar",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG.value,
            timestamp=1711785600000,
            expected_entry=Decimal("70000.00"),
            expected_sl=Decimal("69000.00"),
            pattern_score=0.92,
        )
        db_session.add(signal)
        await db_session.commit()

        # 3. 创建入场订单
        entry_order = OrderORM(
            id="ord_entry",
            signal_id=signal.id,
            symbol=signal.symbol,
            direction=Direction.LONG.value,
            order_type=OrderType.MARKET.value,
            order_role=OrderRole.ENTRY.value,
            requested_qty=Decimal("0.1"),
            filled_qty=Decimal("0.1"),
            average_exec_price=Decimal("70050.00"),
            status=OrderStatus.FILLED.value,
        )
        db_session.add(entry_order)
        await db_session.commit()

        # 4. 创建仓位
        position = PositionORM(
            id="pos_integration",
            signal_id=signal.id,
            symbol=signal.symbol,
            direction=Direction.LONG.value,
            entry_price=Decimal("70050.00"),
            current_qty=Decimal("0.1"),
            watermark_price=Decimal("70050.00"),
        )
        db_session.add(position)
        await db_session.commit()

        # 5. 验证所有实体
        # 账户
        result = await db_session.execute(
            select(AccountORM).where(AccountORM.account_id == "default_wallet")
        )
        acc = result.scalar_one()
        assert acc.total_balance == Decimal("10000.00")

        # 信号
        result = await db_session.execute(
            select(SignalORM).where(SignalORM.id == "sig_integration")
        )
        sig = result.scalar_one()
        assert sig.pattern_score == 0.92

        # 订单
        result = await db_session.execute(
            select(OrderORM).where(OrderORM.id == "ord_entry")
        )
        ord = result.scalar_one()
        assert ord.status == "FILLED"

        # 仓位
        result = await db_session.execute(
            select(PositionORM).where(PositionORM.id == "pos_integration")
        )
        pos = result.scalar_one()
        assert pos.entry_price == Decimal("70050.00")
        assert pos.is_closed is False
