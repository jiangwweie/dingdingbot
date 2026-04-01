"""
单元测试：ReconciliationService 对账服务

测试覆盖:
1. 仓位对账逻辑
2. 订单对账逻辑
3. Grace Period 宽限期验证（G-004 修复）
4. 孤儿订单处理策略
5. 二次校验逻辑
6. 对账报告生成
"""
import asyncio
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch, call
import time

from src.application.reconciliation import ReconciliationService
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
from src.infrastructure.exchange_gateway import OrderCancelResult


# ============================================================
# 测试辅助函数
# ============================================================

def create_sample_position(
    symbol="BTC/USDT:USDT",
    side="long",
    current_qty=Decimal("0.1"),
    entry_price=Decimal("70000"),
    unrealized_pnl=Decimal("500"),
    leverage=10,
):
    """创建示例仓位"""
    return PositionInfo(
        symbol=symbol,
        side=side,
        size=current_qty,
        entry_price=entry_price,
        unrealized_pnl=unrealized_pnl,
        leverage=leverage,
    )


def create_sample_order(
    order_id="order_001",
    exchange_order_id="ex_order_001",
    symbol="BTC/USDT:USDT",
    order_type=OrderType.LIMIT,
    direction=Direction.LONG,
    order_role=OrderRole.ENTRY,
    status=OrderStatus.OPEN,
    amount=Decimal("0.1"),
    filled_amount=Decimal("0"),
    price=Decimal("70000"),
    reduce_only=False,
):
    """创建示例订单"""
    return OrderResponse(
        order_id=order_id,
        exchange_order_id=exchange_order_id,
        symbol=symbol,
        order_type=order_type,
        direction=direction,
        order_role=order_role,
        status=status,
        amount=amount,
        filled_amount=filled_amount,
        price=price,
        trigger_price=None,
        average_exec_price=None,
        reduce_only=reduce_only,
        created_at=int(time.time() * 1000),
        updated_at=int(time.time() * 1000),
    )


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_gateway():
    """创建模拟 ExchangeGateway"""
    gateway = AsyncMock()
    gateway.rest_exchange = AsyncMock()
    gateway.get_account_snapshot = MagicMock(return_value=None)
    return gateway


@pytest.fixture
def mock_position_mgr():
    """创建模拟 PositionManager"""
    return AsyncMock()


@pytest.fixture
def reconciliation_service(mock_gateway, mock_position_mgr):
    """创建 ReconciliationService 实例"""
    return ReconciliationService(
        gateway=mock_gateway,
        position_mgr=mock_position_mgr,
        grace_period_seconds=10,  # 缩短用于测试
    )


# ============================================================
# 测试：仓位对账逻辑
# ============================================================

@pytest.mark.asyncio
async def test_reconciliation_no_discrepancies(reconciliation_service, mock_gateway, mock_position_mgr):
    """测试：本地和交易所状态完全一致"""
    # 准备数据
    local_positions = [
        create_sample_position(symbol="BTC/USDT:USDT", current_qty=Decimal("0.1")),
    ]
    exchange_positions = [
        create_sample_position(symbol="BTC/USDT:USDT", current_qty=Decimal("0.1")),
    ]

    mock_position_mgr.get_open_positions = AsyncMock(return_value=local_positions)
    mock_gateway.rest_exchange.fetch_positions = AsyncMock(return_value=[
        {
            'symbol': 'BTC/USDT:USDT',
            'contracts': 0.1,
            'side': 'long',
            'entryPrice': 70000,
            'unrealizedPnl': 500,
            'leverage': 10,
        }
    ])
    mock_gateway.rest_exchange.fetch_open_orders = AsyncMock(return_value=[])

    # 执行
    report = await reconciliation_service.run_reconciliation("BTC/USDT:USDT")

    # 验证
    assert report.is_consistent is True
    assert report.total_discrepancies == 0
    assert report.requires_attention is False
    assert len(report.missing_positions) == 0
    assert len(report.position_mismatches) == 0
    assert len(report.orphan_orders) == 0
    assert len(report.order_mismatches) == 0


@pytest.mark.asyncio
async def test_reconciliation_missing_position(reconciliation_service, mock_gateway, mock_position_mgr):
    """测试：交易所有仓位但本地没有（缺失仓位）"""
    # 准备数据：本地无仓位，交易所有仓位
    mock_position_mgr.get_open_positions = AsyncMock(return_value=[])
    mock_gateway.rest_exchange.fetch_positions = AsyncMock(return_value=[
        {
            'symbol': 'BTC/USDT:USDT',
            'contracts': 0.1,
            'side': 'long',
            'entryPrice': 70000,
            'unrealizedPnl': 500,
            'leverage': 10,
        }
    ])
    mock_gateway.rest_exchange.fetch_open_orders = AsyncMock(return_value=[])

    # 执行（使用较短的宽限期）
    reconciliation_service._grace_period_seconds = 0  # 测试时跳过等待
    report = await reconciliation_service.run_reconciliation("BTC/USDT:USDT")

    # 验证
    assert report.is_consistent is False
    assert report.total_discrepancies == 1
    assert len(report.missing_positions) == 1
    assert report.missing_positions[0].symbol == "BTC/USDT:USDT"


@pytest.mark.asyncio
async def test_reconciliation_position_mismatch(reconciliation_service, mock_gateway, mock_position_mgr):
    """测试：仓位数量不匹配"""
    # 准备数据：本地和交易所仓位数量不一致
    local_positions = [
        create_sample_position(symbol="BTC/USDT:USDT", current_qty=Decimal("0.1")),
    ]
    mock_position_mgr.get_open_positions = AsyncMock(return_value=local_positions)
    mock_gateway.rest_exchange.fetch_positions = AsyncMock(return_value=[
        {
            'symbol': 'BTC/USDT:USDT',
            'contracts': 0.15,  # 数量不一致
            'side': 'long',
            'entryPrice': 70000,
            'unrealizedPnl': 500,
            'leverage': 10,
        }
    ])
    mock_gateway.rest_exchange.fetch_open_orders = AsyncMock(return_value=[])

    # 执行
    reconciliation_service._grace_period_seconds = 0
    report = await reconciliation_service.run_reconciliation("BTC/USDT:USDT")

    # 验证
    assert report.is_consistent is False
    assert report.total_discrepancies == 1
    assert len(report.position_mismatches) == 1
    assert report.position_mismatches[0].local_qty == Decimal("0.1")
    assert report.position_mismatches[0].exchange_qty == Decimal("0.15")
    assert report.position_mismatches[0].discrepancy == Decimal("0.05")


# ============================================================
# 测试：订单对账逻辑
# ============================================================

@pytest.mark.asyncio
async def test_reconciliation_orphan_order(reconciliation_service, mock_gateway, mock_position_mgr):
    """测试：孤儿订单（交易所有订单但本地没有）"""
    mock_position_mgr.get_open_positions = AsyncMock(return_value=[])
    mock_gateway.rest_exchange.fetch_positions = AsyncMock(return_value=[])
    mock_gateway.rest_exchange.fetch_open_orders = AsyncMock(return_value=[
        {
            'id': 'ex_order_001',
            'symbol': 'BTC/USDT:USDT',
            'type': 'limit',
            'side': 'buy',
            'amount': 0.1,
            'price': 70000,
            'filled': 0,
            'status': 'open',
            'timestamp': int(time.time() * 1000),
        }
    ])

    # 执行
    reconciliation_service._grace_period_seconds = 0
    report = await reconciliation_service.run_reconciliation("BTC/USDT:USDT")

    # 验证
    assert report.is_consistent is False
    assert report.total_discrepancies == 1
    assert len(report.orphan_orders) == 1
    assert report.orphan_orders[0].exchange_order_id == "ex_order_001"


@pytest.mark.asyncio
async def test_reconciliation_order_status_mismatch(reconciliation_service, mock_gateway, mock_position_mgr):
    """测试：订单状态不一致"""
    # 这个测试需要更复杂的设置，暂时跳过
    pass


# ============================================================
# 测试：Grace Period 宽限期机制（G-004 修复）
# ============================================================

@pytest.mark.asyncio
async def test_grace_period_resolves_websocket_delay(reconciliation_service, mock_gateway, mock_position_mgr):
    """测试：宽限期解决 WebSocket 延迟导致的幽灵偏差"""
    # 准备数据：初始状态不一致
    local_positions_initial = []
    exchange_positions_initial = [
        {
            'symbol': 'BTC/USDT:USDT',
            'contracts': 0.1,
            'side': 'long',
            'entryPrice': 70000,
            'unrealizedPnl': 500,
            'leverage': 10,
        }
    ]

    # 宽限期后状态一致（WebSocket 延迟消失）
    local_positions_after = [
        create_sample_position(symbol="BTC/USDT:USDT", current_qty=Decimal("0.1")),
    ]
    exchange_positions_after = exchange_positions_initial

    # 配置 mock - 使用 side_effect 来模拟两次调用返回不同的结果
    call_count = {'positions': 0}

    async def get_positions_side_effect(*args):
        call_count['positions'] += 1
        if call_count['positions'] <= 1:
            # 第一次调用（初始状态）- 返回空列表
            return local_positions_initial
        else:
            # 第二次调用（宽限期后）- 返回有数据的列表
            return local_positions_after

    async def fetch_positions_side_effect(symbols):
        # 始终返回交易所仓位
        return exchange_positions_initial

    mock_position_mgr.get_open_positions = AsyncMock(side_effect=get_positions_side_effect)
    mock_gateway.rest_exchange.fetch_positions = AsyncMock(side_effect=fetch_positions_side_effect)
    mock_gateway.rest_exchange.fetch_open_orders = AsyncMock(return_value=[])

    # 执行
    reconciliation_service._grace_period_seconds = 0  # 跳过等待
    report = await reconciliation_service.run_reconciliation("BTC/USDT:USDT")

    # 验证：差异应该被解决（因为第二次调用时本地有了仓位）
    assert report.is_consistent is True
    assert report.total_discrepancies == 0


@pytest.mark.asyncio
async def test_grace_period_confirms_real_discrepancy(reconciliation_service, mock_gateway, mock_position_mgr):
    """测试：宽限期后确认真实差异"""
    # 准备数据：始终不一致
    local_positions = []
    exchange_positions = [
        {
            'symbol': 'BTC/USDT:USDT',
            'contracts': 0.1,
            'side': 'long',
            'entryPrice': 70000,
            'unrealizedPnl': 500,
            'leverage': 10,
        }
    ]

    mock_position_mgr.get_open_positions = AsyncMock(return_value=local_positions)
    mock_gateway.rest_exchange.fetch_positions = AsyncMock(return_value=exchange_positions)
    mock_gateway.rest_exchange.fetch_open_orders = AsyncMock(return_value=[])

    # 执行
    reconciliation_service._grace_period_seconds = 0
    report = await reconciliation_service.run_reconciliation("BTC/USDT:USDT")

    # 验证：差异应该被确认
    assert report.is_consistent is False
    assert report.total_discrepancies == 1
    assert len(report.missing_positions) == 1


# ============================================================
# 测试：孤儿订单处理
# ============================================================

@pytest.mark.asyncio
async def test_handle_orphan_orders_cancel_reduce_only(reconciliation_service, mock_gateway):
    """测试：处理孤儿订单 - 取消减仓订单（TP/SL）"""
    orphan_orders = [
        create_sample_order(
            order_id="orphan_001",
            exchange_order_id="ex_orphan_001",
            order_role=OrderRole.TP1,
            reduce_only=True,
        )
    ]

    mock_gateway.cancel_order = AsyncMock(return_value=OrderCancelResult(
        order_id="ex_orphan_001",
        symbol="BTC/USDT:USDT",
        status=OrderStatus.CANCELED,
        message="Order canceled successfully",
    ))

    # 执行
    await reconciliation_service.handle_orphan_orders(orphan_orders)

    # 验证
    mock_gateway.cancel_order.assert_called_once_with(
        order_id="ex_orphan_001",
        symbol="BTC/USDT:USDT",
    )


@pytest.mark.asyncio
async def test_handle_orphan_orders_keep_entry_order(reconciliation_service, mock_gateway):
    """测试：处理孤儿订单 - 保留入场订单"""
    orphan_orders = [
        create_sample_order(
            order_id="orphan_001",
            exchange_order_id="ex_orphan_001",
            order_role=OrderRole.ENTRY,
            reduce_only=False,
        )
    ]

    # 执行
    await reconciliation_service.handle_orphan_orders(orphan_orders)

    # 验证：应该调用_create_missing_signal
    assert mock_gateway.cancel_order.call_count == 0


# ============================================================
# 测试：P5-011 孤儿订单宽限期处理
# ============================================================

@pytest.mark.asyncio
async def test_handle_orphan_orders_pending_tp_sl_with_grace_period(reconciliation_service, mock_gateway, mock_position_mgr):
    """测试：P5-011 - TP/SL 孤儿订单进入待确认列表，等待宽限期后二次校验"""
    orphan_orders = [
        create_sample_order(
            order_id="tp_001",
            exchange_order_id="ex_tp_001",
            order_role=OrderRole.TP1,
            reduce_only=True,
        )
    ]
    
    # Mock 本地仓位列表 - 第一次为空，第二次返回仓位（模拟仓位出现）
    reconciliation_service._get_local_positions = AsyncMock(return_value=[
        create_sample_position(symbol="BTC/USDT:USDT")
    ])
    
    # Mock cancel_order 返回成功
    from src.domain.models import OrderCancelResult
    mock_gateway.cancel_order = AsyncMock(return_value=OrderCancelResult(
        order_id="tp_001",
        exchange_order_id="ex_tp_001",
        symbol="BTC/USDT:USDT",
    ))
    
    # 执行
    with patch('asyncio.sleep', new=AsyncMock()) as mock_sleep:
        await reconciliation_service.handle_orphan_orders(orphan_orders)
    
    # 验证：订单应该从待确认列表中移除（因为仓位出现了，被保留）
    assert "tp_001" not in reconciliation_service._pending_orphan_orders
    
    # 验证：等待了宽限期
    mock_sleep.assert_called_once_with(10)
    
    # 验证：没有调用 cancel_order（因为仓位出现了）
    mock_gateway.cancel_order.assert_not_called()


@pytest.mark.asyncio
async def test_verify_pending_orphan_orders_position_appears(reconciliation_service, mock_gateway):
    """测试：P5-011 - 宽限期后仓位出现，保留订单（WebSocket 延迟）"""
    # 设置待确认订单
    order = create_sample_order(
        order_id="tp_001",
        exchange_order_id="ex_tp_001",
        order_role=OrderRole.TP1,
        reduce_only=True,
        symbol="BTC/USDT:USDT",
    )
    reconciliation_service._pending_orphan_orders["tp_001"] = {
        "order": order,
        "found_at": int(time.time() * 1000),
        "confirmed": False,
    }
    
    # Mock 本地仓位列表（仓位已存在）
    reconciliation_service._get_local_positions = AsyncMock(return_value=[
        create_sample_position(symbol="BTC/USDT:USDT")
    ])
    
    # 执行
    await reconciliation_service._verify_pending_orphan_orders()
    
    # 验证：订单应该从待确认列表中移除（因为仓位出现了）
    assert "tp_001" not in reconciliation_service._pending_orphan_orders
    
    # 验证：没有调用 cancel_order
    mock_gateway.cancel_order.assert_not_called()


@pytest.mark.asyncio
async def test_verify_pending_orphan_orders_position_still_missing(reconciliation_service, mock_gateway):
    """测试：P5-011 - 宽限期后仓位仍不存在，撤销订单"""
    # 设置待确认订单
    order = create_sample_order(
        order_id="tp_001",
        exchange_order_id="ex_tp_001",
        order_role=OrderRole.TP1,
        reduce_only=True,
        symbol="BTC/USDT:USDT",
    )
    reconciliation_service._pending_orphan_orders["tp_001"] = {
        "order": order,
        "found_at": int(time.time() * 1000),
        "confirmed": False,
    }
    
    # Mock 本地仓位列表为空（仓位不存在）
    reconciliation_service._get_local_positions = AsyncMock(return_value=[])
    
    # Mock cancel_order 返回成功
    mock_gateway.cancel_order = AsyncMock(return_value=OrderCancelResult(
        order_id="tp_001",
        exchange_order_id="ex_tp_001",
        symbol="BTC/USDT:USDT",
    ))
    
    # 执行
    await reconciliation_service._verify_pending_orphan_orders()
    
    # 验证：订单应该从待确认列表中移除
    assert "tp_001" not in reconciliation_service._pending_orphan_orders
    
    # 验证：调用了 cancel_order
    mock_gateway.cancel_order.assert_called_once_with(
        order_id="ex_tp_001",
        symbol="BTC/USDT:USDT",
    )


@pytest.mark.asyncio
async def test_verify_pending_orphan_orders_multiple_orders(reconciliation_service, mock_gateway):
    """测试：P5-011 - 处理多个待确认订单，部分撤销部分保留"""
    # 设置多个待确认订单
    order1 = create_sample_order(
        order_id="tp_001",
        exchange_order_id="ex_tp_001",
        order_role=OrderRole.TP1,
        reduce_only=True,
        symbol="BTC/USDT:USDT",
    )
    order2 = create_sample_order(
        order_id="tp_002",
        exchange_order_id="ex_tp_002",
        order_role=OrderRole.TP2,
        reduce_only=True,
        symbol="ETH/USDT:USDT",
    )
    reconciliation_service._pending_orphan_orders = {
        "tp_001": {
            "order": order1,
            "found_at": int(time.time() * 1000),
            "confirmed": False,
        },
        "tp_002": {
            "order": order2,
            "found_at": int(time.time() * 1000),
            "confirmed": False,
        },
    }
    
    # Mock 本地仓位列表 - BTC 仓位存在，ETH 仓位不存在
    reconciliation_service._get_local_positions = AsyncMock(return_value=[
        create_sample_position(symbol="BTC/USDT:USDT"),
    ])
    
    # Mock cancel_order 返回成功
    mock_gateway.cancel_order = AsyncMock(return_value=OrderCancelResult(
        order_id="tp_002",
        exchange_order_id="ex_tp_002",
        symbol="ETH/USDT:USDT",
    ))
    
    # 执行
    await reconciliation_service._verify_pending_orphan_orders()
    
    # 验证：BTC 订单应该保留（从待确认列表中移除），ETH 订单应该被撤销
    assert "tp_001" not in reconciliation_service._pending_orphan_orders  # 保留了
    assert "tp_002" not in reconciliation_service._pending_orphan_orders  # 撤销了
    
    # 验证：只调用了 ETH 订单的 cancel_order
    mock_gateway.cancel_order.assert_called_once_with(
        order_id="ex_tp_002",
        symbol="ETH/USDT:USDT",
    )


# ============================================================
# 测试：二次校验逻辑
# ============================================================

@pytest.mark.asyncio
async def test_verify_pending_items_confirms_discrepancy(reconciliation_service):
    """测试：二次校验确认差异"""
    pending_missing_positions = [
        {
            "position": create_sample_position(),
            "found_at": int(time.time() * 1000),
            "confirmed": False,
        }
    ]

    # Mock 二次校验时仍然找不到本地仓位
    reconciliation_service._get_local_positions = AsyncMock(return_value=[])
    reconciliation_service._get_exchange_positions = AsyncMock(return_value=[
        create_sample_position()
    ])
    reconciliation_service._get_local_open_orders = AsyncMock(return_value=[])
    reconciliation_service._get_exchange_open_orders = AsyncMock(return_value=[])

    # 执行
    await reconciliation_service._verify_pending_items(
        pending_missing_positions,
        [],
        [],
        [],
        "BTC/USDT:USDT",
    )

    # 验证：差异应该被确认
    assert pending_missing_positions[0]["confirmed"] is True


@pytest.mark.asyncio
async def test_verify_pending_items_resolves_discrepancy(reconciliation_service):
    """测试：二次校验解决差异（WebSocket 延迟）"""
    pending_missing_positions = [
        {
            "position": create_sample_position(),
            "found_at": int(time.time() * 1000),
            "confirmed": False,
        }
    ]

    # Mock 二次校验时找到了本地仓位（差异消失）
    reconciliation_service._get_local_positions = AsyncMock(return_value=[
        create_sample_position()
    ])
    reconciliation_service._get_exchange_positions = AsyncMock(return_value=[
        create_sample_position()
    ])
    reconciliation_service._get_local_open_orders = AsyncMock(return_value=[])
    reconciliation_service._get_exchange_open_orders = AsyncMock(return_value=[])

    # 执行
    await reconciliation_service._verify_pending_items(
        pending_missing_positions,
        [],
        [],
        [],
        "BTC/USDT:USDT",
    )

    # 验证：差异应该被解决（未确认）
    assert pending_missing_positions[0]["confirmed"] is False


# ============================================================
# 测试：对账报告生成
# ============================================================

@pytest.mark.asyncio
async def test_reconciliation_report_summary(reconciliation_service, mock_gateway, mock_position_mgr):
    """测试：对账报告摘要生成"""
    mock_position_mgr.get_open_positions = AsyncMock(return_value=[])
    mock_gateway.rest_exchange.fetch_positions = AsyncMock(return_value=[
        {
            'symbol': 'BTC/USDT:USDT',
            'contracts': 0.1,
            'side': 'long',
            'entryPrice': 70000,
            'unrealizedPnl': 500,
            'leverage': 10,
        }
    ])
    mock_gateway.rest_exchange.fetch_open_orders = AsyncMock(return_value=[])

    # 执行
    reconciliation_service._grace_period_seconds = 0
    report = await reconciliation_service.run_reconciliation("BTC/USDT:USDT")

    # 验证摘要
    assert "缺失仓位" in report.summary
    assert "1" in report.summary


@pytest.mark.asyncio
async def test_reconciliation_report_contains_metadata(reconciliation_service, mock_gateway, mock_position_mgr):
    """测试：对账报告包含元数据"""
    mock_position_mgr.get_open_positions = AsyncMock(return_value=[])
    mock_gateway.rest_exchange.fetch_positions = AsyncMock(return_value=[])
    mock_gateway.rest_exchange.fetch_open_orders = AsyncMock(return_value=[])

    # 执行
    reconciliation_service._grace_period_seconds = 0
    report = await reconciliation_service.run_reconciliation("BTC/USDT:USDT")

    # 验证元数据
    assert report.symbol == "BTC/USDT:USDT"
    assert report.reconciliation_time > 0
    assert report.grace_period_seconds == 0
    assert report.is_consistent is True
    assert report.requires_attention is False


# ============================================================
# 测试：边界情况
# ============================================================

@pytest.mark.asyncio
async def test_reconciliation_with_no_position_manager(reconciliation_service, mock_gateway):
    """测试：没有 PositionManager 时的降级处理"""
    reconciliation_service._position_mgr = None
    mock_gateway.get_account_snapshot = MagicMock(return_value=None)
    mock_gateway.rest_exchange.fetch_positions = AsyncMock(return_value=[])
    mock_gateway.rest_exchange.fetch_open_orders = AsyncMock(return_value=[])

    # 执行
    reconciliation_service._grace_period_seconds = 0
    report = await reconciliation_service.run_reconciliation("BTC/USDT:USDT")

    # 验证
    assert report.is_consistent is True


@pytest.mark.asyncio
async def test_reconciliation_multiple_symbols(reconciliation_service, mock_gateway, mock_position_mgr):
    """测试：多币种对账"""
    local_positions = [
        create_sample_position(symbol="BTC/USDT:USDT", current_qty=Decimal("0.1")),
        create_sample_position(symbol="ETH/USDT:USDT", current_qty=Decimal("1.0")),
    ]
    mock_position_mgr.get_open_positions = AsyncMock(return_value=local_positions)
    mock_gateway.rest_exchange.fetch_positions = AsyncMock(return_value=[
        {
            'symbol': 'BTC/USDT:USDT',
            'contracts': 0.1,
            'side': 'long',
            'entryPrice': 70000,
            'unrealizedPnl': 500,
            'leverage': 10,
        },
        {
            'symbol': 'ETH/USDT:USDT',
            'contracts': 1.0,
            'side': 'long',
            'entryPrice': 3500,
            'unrealizedPnl': 100,
            'leverage': 10,
        },
    ])
    mock_gateway.rest_exchange.fetch_open_orders = AsyncMock(return_value=[])

    # 执行
    reconciliation_service._grace_period_seconds = 0
    report = await reconciliation_service.run_reconciliation("ALL")

    # 验证
    assert report.is_consistent is True
    assert report.total_discrepancies == 0


# ============================================================
# P0-003: 幽灵订单和孤儿订单处理测试
# ============================================================

@pytest.mark.asyncio
async def test_p003_detect_ghost_orders(reconciliation_service, mock_gateway):
    """P0-003 测试：检测幽灵订单（DB 有但交易所无）"""
    # 准备数据：本地有订单，交易所无订单
    local_orders = [
        create_sample_order(
            order_id="local_001",
            exchange_order_id="ex_local_001",
            status=OrderStatus.OPEN,
        )
    ]
    exchange_orders = []  # 交易所无订单

    # 执行幽灵订单检测
    ghost_orders = await reconciliation_service._detect_ghost_orders(local_orders, exchange_orders)

    # 验证
    assert len(ghost_orders) == 1
    assert ghost_orders[0].order_id == "ex_local_001"
    assert ghost_orders[0].symbol == "BTC/USDT:USDT"
    assert ghost_orders[0].action_taken == "MARKED_CANCELLED"


@pytest.mark.asyncio
async def test_p003_ghost_orders_excludes_non_pending(reconciliation_service, mock_gateway):
    """P0-003 测试：非 PENDING/OPEN 状态的订单不视为幽灵订单"""
    # 准备数据：本地订单已 CANCELLED
    local_orders = [
        create_sample_order(
            order_id="local_001",
            exchange_order_id="ex_local_001",
            status=OrderStatus.CANCELED,  # 已取消
        )
    ]
    exchange_orders = []

    # 执行检测
    ghost_orders = await reconciliation_service._detect_ghost_orders(local_orders, exchange_orders)

    # 验证：已取消的订单不应被视为幽灵订单
    assert len(ghost_orders) == 0


@pytest.mark.asyncio
async def test_p003_process_orphan_orders_import_entry_order(reconciliation_service, mock_gateway):
    """P0-003 测试：处理孤儿订单 - 导入入场订单"""
    orphan_orders = [
        create_sample_order(
            order_id="orphan_entry_001",
            exchange_order_id="ex_orphan_001",
            order_role=OrderRole.ENTRY,
            reduce_only=False,
        )
    ]

    # 执行处理
    imported, canceled = await reconciliation_service._process_orphan_orders(orphan_orders, "BTC/USDT:USDT")

    # 验证：入场订单应该被导入
    assert len(imported) == 1
    assert len(canceled) == 0
    assert imported[0].order_id == "ex_orphan_001"
    assert imported[0].action_taken == "IMPORTED_TO_DB"


@pytest.mark.asyncio
async def test_p003_process_orphan_orders_cancel_tp_order(reconciliation_service, mock_gateway):
    """P0-003 测试：处理孤儿订单 - 撤销 TP 订单"""
    # Mock cancel_order 返回成功
    from src.domain.models import OrderCancelResult
    mock_gateway.cancel_order = AsyncMock(return_value=OrderCancelResult(
        order_id="ex_tp_001",
        exchange_order_id="ex_tp_001",
        symbol="BTC/USDT:USDT",
    ))

    orphan_orders = [
        create_sample_order(
            order_id="orphan_tp_001",
            exchange_order_id="ex_tp_001",
            order_role=OrderRole.TP1,
            reduce_only=True,
        )
    ]

    # 执行处理
    imported, canceled = await reconciliation_service._process_orphan_orders(orphan_orders, "BTC/USDT:USDT")

    # 验证：TP 订单应该被撤销
    assert len(imported) == 0
    assert len(canceled) == 1
    assert canceled[0].order_id == "ex_tp_001"
    assert canceled[0].action_taken == "CANCELLED"
    mock_gateway.cancel_order.assert_called_once_with(
        order_id="ex_tp_001",
        symbol="BTC/USDT:USDT",
    )


@pytest.mark.asyncio
async def test_p003_process_orphan_orders_cancel_sl_order(reconciliation_service, mock_gateway):
    """P0-003 测试：处理孤儿订单 - 撤销 SL 订单"""
    from src.domain.models import OrderCancelResult
    mock_gateway.cancel_order = AsyncMock(return_value=OrderCancelResult(
        order_id="ex_sl_001",
        exchange_order_id="ex_sl_001",
        symbol="BTC/USDT:USDT",
    ))

    orphan_orders = [
        create_sample_order(
            order_id="orphan_sl_001",
            exchange_order_id="ex_sl_001",
            order_role=OrderRole.SL,
            reduce_only=True,
        )
    ]

    # 执行处理
    imported, canceled = await reconciliation_service._process_orphan_orders(orphan_orders, "BTC/USDT:USDT")

    # 验证：SL 订单应该被撤销
    assert len(imported) == 0
    assert len(canceled) == 1
    assert canceled[0].order_id == "ex_sl_001"
    assert canceled[0].action_taken == "CANCELLED"


@pytest.mark.asyncio
async def test_p003_process_orphan_orders_mixed(reconciliation_service, mock_gateway):
    """P0-003 测试：处理混合孤儿订单（部分导入，部分撤销）"""
    from src.domain.models import OrderCancelResult
    mock_gateway.cancel_order = AsyncMock(return_value=OrderCancelResult(
        order_id="ex_tp_001",
        symbol="BTC/USDT:USDT",
    ))

    orphan_orders = [
        create_sample_order(
            order_id="orphan_entry_001",
            exchange_order_id="ex_entry_001",
            order_role=OrderRole.ENTRY,
            reduce_only=False,
        ),
        create_sample_order(
            order_id="orphan_tp_001",
            exchange_order_id="ex_tp_001",
            order_role=OrderRole.TP1,
            reduce_only=True,
        ),
    ]

    # 执行处理
    imported, canceled = await reconciliation_service._process_orphan_orders(orphan_orders, "BTC/USDT:USDT")

    # 验证：入场订单导入，TP 订单撤销
    assert len(imported) == 1
    assert len(canceled) == 1
    assert imported[0].order_id == "ex_entry_001"
    assert imported[0].action_taken == "IMPORTED_TO_DB"
    assert canceled[0].order_id == "ex_tp_001"
    assert canceled[0].action_taken == "CANCELLED"


@pytest.mark.asyncio
async def test_p003_reconciliation_report_includes_ghost_orders(reconciliation_service, mock_gateway, mock_position_mgr):
    """P0-003 测试：对账报告包含幽灵订单"""
    # 准备数据
    local_orders = [
        create_sample_order(
            order_id="local_001",
            exchange_order_id="ex_local_001",
            status=OrderStatus.OPEN,
        )
    ]
    mock_position_mgr.get_open_positions = AsyncMock(return_value=[])
    mock_gateway.rest_exchange.fetch_positions = AsyncMock(return_value=[])
    mock_gateway.rest_exchange.fetch_open_orders = AsyncMock(return_value=[])

    # Mock _get_local_open_orders 返回本地订单
    reconciliation_service._get_local_open_orders = AsyncMock(return_value=local_orders)

    # 执行（跳过宽限期）
    reconciliation_service._grace_period_seconds = 0
    report = await reconciliation_service.run_reconciliation("BTC/USDT:USDT")

    # 验证
    assert len(report.ghost_orders) == 1
    assert report.ghost_orders[0].order_id == "ex_local_001"
    assert "幽灵订单" in report.summary


@pytest.mark.asyncio
async def test_p003_reconciliation_report_includes_canceled_orphans(reconciliation_service, mock_gateway, mock_position_mgr):
    """P0-003 测试：对账报告包含撤销的孤儿订单"""
    from src.domain.models import OrderCancelResult

    # 准备数据：交易所有 TP 订单，本地无
    mock_position_mgr.get_open_positions = AsyncMock(return_value=[])
    mock_gateway.rest_exchange.fetch_positions = AsyncMock(return_value=[])
    mock_gateway.rest_exchange.fetch_open_orders = AsyncMock(return_value=[
        {
            'id': 'ex_tp_001',
            'symbol': 'BTC/USDT:USDT',
            'type': 'stop',
            'side': 'sell',
            'amount': 0.1,
            'price': 75000,
            'filled': 0,
            'status': 'open',
            'reduceOnly': True,
            'timestamp': int(time.time() * 1000),
        }
    ])
    mock_gateway.cancel_order = AsyncMock(return_value=OrderCancelResult(
        order_id="ex_tp_001",
        symbol="BTC/USDT:USDT",
    ))

    # Mock _get_local_open_orders 返回空列表
    reconciliation_service._get_local_open_orders = AsyncMock(return_value=[])

    # 执行（跳过宽限期）
    reconciliation_service._grace_period_seconds = 0
    report = await reconciliation_service.run_reconciliation("BTC/USDT:USDT")

    # 验证
    assert len(report.canceled_orphan_orders) == 1
    assert report.canceled_orphan_orders[0].order_id == "ex_tp_001"
    assert "撤销孤儿订单" in report.summary
