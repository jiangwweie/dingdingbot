"""
v3 数据库迁移测试

验证 Alembic 迁移文件正确性：
- T3-A: orders 表补充字段迁移 (004)
- T3-B: backtest_reports 表创建迁移 (005)

测试覆盖:
1. 迁移链完整性验证
2. orders 表新增字段验证
3. backtest_reports 表结构验证
4. 外键约束和索引验证
5. ORM 模型同步验证
"""

import pytest
import sqlite3
import tempfile
import subprocess
import os
from pathlib import Path
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.infrastructure.v3_orm import (
    Base,
    OrderORM,
    BacktestReportORM,
    SignalORM,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def migrated_db(tmp_path):
    """创建临时数据库并运行 Alembic 迁移"""
    db_path = tmp_path / "test_migrations.db"

    # 保存原始 alembic.ini
    alembic_ini_path = Path('/Users/jiangwei/Documents/dingdingbot/alembic.ini')
    original_content = alembic_ini_path.read_text()

    try:
        # 临时修改 alembic.ini 指向测试数据库
        modified_content = original_content.replace(
            'sqlalchemy.url = sqlite:///./data/v3_dev.db',
            f'sqlalchemy.url = sqlite:///{db_path}'
        )
        alembic_ini_path.write_text(modified_content)

        # 运行迁移
        env = os.environ.copy()
        env['PYTHONPATH'] = '/Users/jiangwei/Documents/dingdingbot'

        result = subprocess.run(
            ['/Users/jiangwei/Library/Python/3.9/bin/alembic', 'upgrade', 'head'],
            cwd='/Users/jiangwei/Documents/dingdingbot',
            env=env,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            pytest.fail(f"Alembic migration failed: {result.stderr}")

        # 返回数据库路径（使用同步连接测试）
        yield str(db_path)
    finally:
        # 恢复 alembic.ini
        alembic_ini_path.write_text(original_content)


@pytest.fixture
async def async_db_session(migrated_db):
    """创建异步数据库会话"""
    db_url = f"sqlite+aiosqlite:///{migrated_db}"
    engine = create_async_engine(
        db_url,
        echo=False,
        connect_args={"check_same_thread": False},
    )

    from sqlalchemy.ext.asyncio import async_sessionmaker
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with async_session_maker() as session:
        yield session
        await session.rollback()

    await engine.dispose()


# ============================================================
# T3-A: orders 表补充字段迁移测试
# ============================================================

class TestT3A_OrdersBacktestFields:
    """T3-A: orders 表补充字段迁移测试"""

    def test_orders_table_has_filled_at_column(self, migrated_db):
        """验证 orders 表有 filled_at 字段"""
        conn = sqlite3.connect(migrated_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(orders)")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()

        assert "filled_at" in columns, "orders 表应该包含 filled_at 字段"

    def test_orders_table_has_parent_order_id_column(self, migrated_db):
        """验证 orders 表有 parent_order_id 字段"""
        conn = sqlite3.connect(migrated_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(orders)")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()

        assert "parent_order_id" in columns, "orders 表应该包含 parent_order_id 字段"

    def test_orders_orm_model_has_backtest_fields(self):
        """验证 OrderORM 模型有回测相关字段"""
        assert hasattr(OrderORM, "filled_at"), "OrderORM 应该有 filled_at 属性"
        assert hasattr(OrderORM, "parent_order_id"), "OrderORM 应该有 parent_order_id 属性"

    def test_order_parent_order_foreign_key(self, migrated_db):
        """验证 parent_order_id 外键约束"""
        conn = sqlite3.connect(migrated_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_key_list(orders)")
        fks = cursor.fetchall()
        conn.close()

        # 查找 parent_order_id 的外键约束
        parent_order_fk = None
        for fk in fks:
            if fk[3] == "parent_order_id":  # from 列
                parent_order_fk = fk
                break

        assert parent_order_fk is not None, "应该有 parent_order_id 的外键约束"
        assert parent_order_fk[2] == "orders", "外键应该引用 orders 表"
        assert parent_order_fk[4] == "id", "外键应该引用 id 列"

    def test_order_parent_order_index(self, migrated_db):
        """验证 parent_order_id 索引"""
        conn = sqlite3.connect(migrated_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='orders'")
        indexes = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert "idx_orders_parent_order_id" in indexes, "应该有 idx_orders_parent_order_id 索引"


# ============================================================
# T3-B: backtest_reports 表创建迁移测试
# ============================================================

class TestT3B_BacktestReportsTable:
    """T3-B: backtest_reports 表创建迁移测试"""

    def test_backtest_reports_table_exists(self, migrated_db):
        """验证 backtest_reports 表存在"""
        conn = sqlite3.connect(migrated_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='backtest_reports'")
        exists = cursor.fetchone() is not None
        conn.close()

        assert exists, "backtest_reports 表应该存在"

    def test_backtest_reports_table_structure(self, migrated_db):
        """验证 backtest_reports 表结构"""
        conn = sqlite3.connect(migrated_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(backtest_reports)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        conn.close()

        # 检查必需字段
        required_columns = [
            "id",
            "strategy_id",
            "strategy_name",
            "strategy_version",
            "strategy_snapshot",
            "parameters_hash",
            "symbol",
            "timeframe",
            "backtest_start",
            "backtest_end",
            "created_at",
            "initial_balance",
            "final_balance",
            "total_return",
            "total_trades",
            "winning_trades",
            "losing_trades",
            "win_rate",
            "total_pnl",
            "total_fees_paid",
            "total_slippage_cost",
            "max_drawdown",
            "positions_summary",
            "monthly_returns",
        ]

        for col_name in required_columns:
            assert col_name in columns, f"backtest_reports 表应该包含 {col_name} 字段"

    def test_backtest_reports_primary_key(self, migrated_db):
        """验证 backtest_reports 主键约束"""
        conn = sqlite3.connect(migrated_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(backtest_reports)")
        pk = None
        for row in cursor.fetchall():
            if row[5] == 1:  # pk 列
                pk = row[1]
                break
        conn.close()

        assert pk == "id", "backtest_reports 表的主键应该是 id"

    def test_backtest_reports_foreign_key(self, migrated_db):
        """验证 backtest_reports 外键约束"""
        conn = sqlite3.connect(migrated_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_key_list(backtest_reports)")
        fks = cursor.fetchall()
        conn.close()

        # 查找 strategy_id 的外键约束
        strategy_fk = None
        for fk in fks:
            if fk[3] == "strategy_id":
                strategy_fk = fk
                break

        assert strategy_fk is not None, "应该有 strategy_id 的外键约束"
        assert strategy_fk[2] == "signals", "外键应该引用 signals 表"
        assert strategy_fk[4] == "id", "外键应该引用 id 列"

    def test_backtest_reports_indexes(self, migrated_db):
        """验证 backtest_reports 表索引"""
        conn = sqlite3.connect(migrated_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='backtest_reports'")
        indexes = [row[0] for row in cursor.fetchall()]
        conn.close()

        required_indexes = [
            "idx_backtest_reports_strategy_id",
            "idx_backtest_reports_symbol",
            "idx_backtest_reports_parameters_hash",
            "idx_backtest_reports_created_at",
        ]

        for idx in required_indexes:
            assert idx in indexes, f"应该有 {idx} 索引"

    def test_backtest_report_orm_model_exists(self):
        """验证 BacktestReportORM 模型存在"""
        assert BacktestReportORM is not None, "BacktestReportORM 类应该存在"
        assert hasattr(BacktestReportORM, "__tablename__"), "BacktestReportORM 应该有 __tablename__"
        assert BacktestReportORM.__tablename__ == "backtest_reports", "表名应该是 backtest_reports"

    def test_backtest_report_orm_fields(self):
        """验证 BacktestReportORM 模型字段"""
        required_fields = [
            "id",
            "strategy_id",
            "strategy_name",
            "strategy_version",
            "strategy_snapshot",
            "parameters_hash",
            "symbol",
            "timeframe",
            "backtest_start",
            "backtest_end",
            "created_at",
            "initial_balance",
            "final_balance",
            "total_return",
            "total_trades",
            "winning_trades",
            "losing_trades",
            "win_rate",
            "total_pnl",
            "total_fees_paid",
            "total_slippage_cost",
            "max_drawdown",
            "positions_summary",
            "monthly_returns",
        ]

        for field in required_fields:
            assert hasattr(BacktestReportORM, field), f"BacktestReportORM 应该有 {field} 字段"


# ============================================================
# 集成测试：完整 CRUD 操作
# ============================================================

class TestMigrationIntegration:
    """迁移集成测试"""

    @pytest.mark.asyncio
    async def test_create_and_read_order_with_backtest_fields(self, async_db_session):
        """测试创建和读取带有回测字段的订单"""
        # 创建测试信号
        signal = SignalORM(
            id="test_signal_001",
            strategy_id="pinbar",
            symbol="BTC/USDT:USDT",
            direction="LONG",
            timestamp=1711785600000,
            expected_entry=Decimal("70000"),
            expected_sl=Decimal("69000"),
            pattern_score=0.85,
        )
        async_db_session.add(signal)
        await async_db_session.commit()

        # 创建订单（带 filled_at 和 parent_order_id）
        order = OrderORM(
            id="test_order_001",
            signal_id="test_signal_001",
            symbol="BTC/USDT:USDT",
            direction="LONG",
            order_type="MARKET",
            order_role="ENTRY",
            requested_qty=Decimal("0.1"),
            filled_qty=Decimal("0.1"),
            average_exec_price=Decimal("70000"),
            status="FILLED",
            filled_at=1711785660000,  # 新增字段
            parent_order_id=None,  # 新增字段
        )
        async_db_session.add(order)
        await async_db_session.commit()

        # 读取订单
        result = await async_db_session.execute(
            select(OrderORM).where(OrderORM.id == "test_order_001")
        )
        retrieved_order = result.scalar_one()

        assert retrieved_order is not None
        assert retrieved_order.filled_at == 1711785660000
        assert retrieved_order.parent_order_id is None

    @pytest.mark.asyncio
    async def test_create_and_read_backtest_report(self, async_db_session):
        """测试创建和读取回测报告"""
        import json

        # 创建测试信号（作为策略）
        signal = SignalORM(
            id="test_strategy_001",
            strategy_id="pinbar",
            symbol="BTC/USDT:USDT",
            direction="LONG",
            timestamp=1711785600000,
            expected_entry=Decimal("70000"),
            expected_sl=Decimal("69000"),
            pattern_score=0.85,
        )
        async_db_session.add(signal)
        await async_db_session.commit()

        # 创建回测报告
        strategy_snapshot = json.dumps({
            "id": "pinbar",
            "name": "Pinbar 策略",
            "version": "1.0.0",
            "triggers": [{"type": "pinbar", "params": {}}],
        })

        report = BacktestReportORM(
            id="bt_report_001",
            strategy_id="test_strategy_001",
            strategy_name="Pinbar 策略",
            strategy_version="1.0.0",
            strategy_snapshot=strategy_snapshot,
            parameters_hash="abc123def456",
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            backtest_start=1711700000000,
            backtest_end=1711800000000,
            initial_balance=Decimal("10000"),
            final_balance=Decimal("12000"),
            total_return=Decimal("0.2"),
            total_trades=50,
            winning_trades=30,
            losing_trades=20,
            win_rate=Decimal("0.6"),
            total_pnl=Decimal("2000"),
            total_fees_paid=Decimal("50"),
            total_slippage_cost=Decimal("10"),
            max_drawdown=Decimal("0.15"),
            positions_summary=json.dumps({"total_positions": 50}),
            monthly_returns=json.dumps({"2024-03": "0.2"}),
        )
        async_db_session.add(report)
        await async_db_session.commit()

        # 读取回测报告
        result = await async_db_session.execute(
            select(BacktestReportORM).where(BacktestReportORM.id == "bt_report_001")
        )
        retrieved_report = result.scalar_one()

        assert retrieved_report is not None
        assert retrieved_report.strategy_name == "Pinbar 策略"
        assert retrieved_report.total_return == Decimal("0.2")
        assert retrieved_report.win_rate == Decimal("0.6")
        assert retrieved_report.max_drawdown == Decimal("0.15")


# ============================================================
# 迁移链完整性测试
# ============================================================

class TestMigrationChain:
    """迁移链完整性测试"""

    def test_alembic_version_in_migrated_db(self, migrated_db):
        """验证 Alembic 版本表"""
        conn = sqlite3.connect(migrated_db)
        cursor = conn.cursor()

        # 检查 alembic_version 表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'")
        exists = cursor.fetchone() is not None

        assert exists, "应该有 alembic_version 表"

        cursor.execute("SELECT version_num FROM alembic_version")
        version = cursor.fetchone()

        assert version is not None, "应该有版本记录"
        assert version[0] == "005", f"当前版本应该是 005，实际是 {version[0]}"

        conn.close()


# ============================================================
# 运行测试
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])
