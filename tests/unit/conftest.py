"""全局测试夹具 (Fixtures) 和工厂导入

本模块提供所有测试共享的 fixtures 和工厂类导入。
"""
import pytest
import tempfile
import os
from decimal import Decimal
from datetime import datetime, timezone

# 导入所有工厂类
from tests.unit.fixtures.order_factory import OrderFactory
from tests.unit.fixtures.position_factory import PositionFactory
from tests.unit.fixtures.signal_factory import SignalFactory
from tests.unit.fixtures.strategy_factory import StrategyFactory

# 导出工厂类供测试使用
__all__ = [
    'OrderFactory',
    'PositionFactory',
    'SignalFactory',
    'StrategyFactory',
    'temp_db_path',
]


@pytest.fixture
def temp_db_path():
    """创建临时数据库文件路径

    每个测试函数都会获得一个唯一的临时数据库文件路径。
    测试结束后，临时文件会自动清理。

    Yields:
        str: 临时数据库文件路径
    """
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    # 清理临时数据库文件
    if os.path.exists(path):
        os.remove(path)
    # 清理 WAL 和 SHM 文件（SQLite 可能生成）
    for ext in ['-wal', '-shm']:
        ext_path = path + ext
        if os.path.exists(ext_path):
            os.remove(ext_path)


@pytest.fixture
def long_signal():
    """创建一个 LONG 信号的 fixture

    Returns:
        Signal: 看多信号
    """
    return SignalFactory.long_signal()


@pytest.fixture
def short_signal():
    """创建一个 SHORT 信号的 fixture

    Returns:
        Signal: 看空信号
    """
    return SignalFactory.short_signal()


@pytest.fixture
def long_position():
    """创建一个 LONG 仓位的 fixture

    Returns:
        Position: 看多仓位
    """
    return PositionFactory.long_position()


@pytest.fixture
def short_position():
    """创建一个 SHORT 仓位的 fixture

    Returns:
        Position: 看空仓位
    """
    return PositionFactory.short_position()


@pytest.fixture
def entry_order():
    """创建一个 ENTRY 订单的 fixture

    Returns:
        Order: 入场订单
    """
    return OrderFactory.entry_order()


@pytest.fixture
def long_entry_order():
    """创建一个 LONG ENTRY 订单的 fixture

    Returns:
        Order: 看多入场订单
    """
    return OrderFactory.long_entry()


@pytest.fixture
def short_entry_order():
    """创建一个 SHORT ENTRY 订单的 fixture

    Returns:
        Order: 看空入场订单
    """
    return OrderFactory.short_entry()


@pytest.fixture
def single_tp_strategy():
    """创建单 TP 策略的 fixture

    Returns:
        OrderStrategy: 单 TP 策略
    """
    return StrategyFactory.single_tp()


@pytest.fixture
def multi_tp_strategy():
    """创建多 TP 策略的 fixture

    Returns:
        OrderStrategy: 多 TP 策略
    """
    return StrategyFactory.multi_tp()
