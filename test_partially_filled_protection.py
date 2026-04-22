"""
受保护持仓闭环 MVP 第二步验证脚本

验证场景：
1. ENTRY 部分成交后，基于已成交数量挂载最小保护单
2. 成交数量不足/信息不足时，不伪造保护单数量
3. 订单链正确（parent_order_id / oco_group_id / order_role）
"""
import asyncio
import tempfile
import os
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from src.application.execution_orchestrator import ExecutionOrchestrator
from src.domain.execution_intent import ExecutionIntentStatus
from src.domain.models import (
    SignalResult,
    Direction,
    OrderStrategy,
    OrderCheckResult,
    OrderPlacementResult,
    OrderType,
    OrderStatus,
    Order,
    OrderRole,
)
from src.application.capital_protection import CapitalProtectionManager
from src.application.order_lifecycle_service import OrderLifecycleService
from src.infrastructure.order_repository import OrderRepository
from src.infrastructure.exchange_gateway import ExchangeGateway


async def test_partially_filled_protection():
    """
    验证场景 1：ENTRY 部分成交后，基于已成交数量挂载最小保护单
    """
    print("\n=== 验证场景 1：ENTRY 部分成交后挂载保护单 ===")

    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    try:
        repository = OrderRepository(db_path)
        await repository.initialize()
        order_lifecycle = OrderLifecycleService(repository)
        await order_lifecycle.start()

        capital_protection = MagicMock(spec=CapitalProtectionManager)
        capital_protection.pre_order_check = AsyncMock(
            return_value=OrderCheckResult(
                allowed=True,
                reason=None,
                reason_message="所有检查通过",
            )
        )

        gateway = MagicMock(spec=ExchangeGateway)

        # Mock place_order() - ENTRY 部分成交
        call_count = 0

        async def mock_place_order(**kwargs):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # ENTRY 订单：返回 PARTIALLY_FILLED（同步返回无成交信息）
                return OrderPlacementResult(
                    order_id="entry_partial",
                    exchange_order_id="binance_entry_partial",
                    symbol=kwargs["symbol"],
                    order_type=OrderType.MARKET,
                    direction=Direction.LONG,
                    side="buy",
                    amount=kwargs["amount"],
                    price=Decimal("65000"),
                    status=OrderStatus.PARTIALLY_FILLED,
                )
            else:
                # 保护单：返回 OPEN
                return OrderPlacementResult(
                    order_id=f"prot_{call_count}",
                    exchange_order_id=f"binance_prot_{call_count}",
                    symbol=kwargs["symbol"],
                    order_type=OrderType.LIMIT,
                    direction=Direction.LONG,
                    side="sell",
                    amount=kwargs["amount"],
                    price=kwargs.get("price"),
                    status=OrderStatus.OPEN,
                )

        gateway.place_order = mock_place_order

        orchestrator = ExecutionOrchestrator(
            capital_protection=capital_protection,
            order_lifecycle=order_lifecycle,
            gateway=gateway,
        )

        signal = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            direction=Direction.LONG,
            entry_price=Decimal("65000"),
            suggested_stop_loss=Decimal("64000"),
            suggested_position_size=Decimal("0.02"),  # 总数量
            current_leverage=10,
            tags=[],
            risk_reward_info="Risk 1% = 100 USDT",
            strategy_name="pinbar",
        )

        strategy = OrderStrategy(
            id="strategy_001",
            name="test_strategy",
            tp_levels=1,
            tp_ratios=[Decimal("1.0")],
            tp_targets=[Decimal("1.5")],
            initial_stop_loss_rr=Decimal("-1.0"),
        )

        # 执行信号
        intent = await orchestrator.execute_signal(signal, strategy)

        # 验证初始状态
        print(f"✅ ExecutionIntent 初始状态: {intent.status}")
        assert intent.status == ExecutionIntentStatus.SUBMITTED, \
            f"期望 SUBMITTED，实际 {intent.status}"

        # 模拟 WebSocket 推送：ENTRY 部分成交（真实成交信息）
        entry_order = await repository.get_order(intent.order_id)

        # 模拟部分成交：已成交 0.01 BTC（总数量 0.02）
        filled_qty = Decimal("0.01")
        average_exec_price = Decimal("65000")

        # 创建交易所推送的订单对象
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        exchange_order = Order(
            id="binance_entry_partial",
            exchange_order_id="binance_entry_partial",
            signal_id=entry_order.signal_id,
            symbol=entry_order.symbol,
            direction=entry_order.direction,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=entry_order.requested_qty,
            filled_qty=filled_qty,
            average_exec_price=average_exec_price,
            status=OrderStatus.PARTIALLY_FILLED,
            created_at=current_time,
            updated_at=current_time,
        )

        # 触发 WebSocket 回写
        await order_lifecycle.update_order_from_exchange(exchange_order)

        # 验证保护单已挂载
        all_orders = await repository.get_orders_by_signal(entry_order.signal_id)

        tp_orders = [o for o in all_orders if o.order_role == OrderRole.TP1]
        sl_orders = [o for o in all_orders if o.order_role == OrderRole.SL]

        print(f"✅ TP 订单数量: {len(tp_orders)}")
        print(f"✅ SL 订单数量: {len(sl_orders)}")

        assert len(tp_orders) == 1, f"期望 1 个 TP 订单，实际 {len(tp_orders)}"
        assert len(sl_orders) == 1, f"期望 1 个 SL 订单，实际 {len(sl_orders)}"

        # 验证保护单数量（基于已成交数量）
        tp_order = tp_orders[0]
        sl_order = sl_orders[0]

        print(f"✅ TP 订单数量: {tp_order.requested_qty}")
        print(f"✅ SL 订单数量: {sl_order.requested_qty}")

        assert tp_order.requested_qty == filled_qty, \
            f"TP 订单数量应为 {filled_qty}，实际 {tp_order.requested_qty}"
        assert sl_order.requested_qty == filled_qty, \
            f"SL 订单数量应为 {filled_qty}，实际 {sl_order.requested_qty}"

        # 验证 ExecutionIntent 状态
        print(f"✅ ExecutionIntent 最终状态: {intent.status}")
        assert intent.status == ExecutionIntentStatus.PARTIALLY_PROTECTED, \
            f"期望 PARTIALLY_PROTECTED，实际 {intent.status}"

        print("✅ 验证通过: ENTRY 部分成交后挂载保护单")

    finally:
        os.unlink(db_path)


async def test_insufficient_fill_info():
    """
    验证场景 2：成交数量不足/信息不足时，不伪造保护单数量
    """
    print("\n=== 验证场景 2：成交信息不足时不挂载保护单 ===")

    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    try:
        repository = OrderRepository(db_path)
        await repository.initialize()
        order_lifecycle = OrderLifecycleService(repository)
        await order_lifecycle.start()

        capital_protection = MagicMock(spec=CapitalProtectionManager)
        capital_protection.pre_order_check = AsyncMock(
            return_value=OrderCheckResult(
                allowed=True,
                reason=None,
                reason_message="所有检查通过",
            )
        )

        gateway = MagicMock(spec=ExchangeGateway)

        # Mock place_order() - ENTRY 部分成交（无成交信息）
        gateway.place_order = AsyncMock(
            return_value=OrderPlacementResult(
                order_id="entry_no_info",
                exchange_order_id="binance_entry_no_info",
                symbol="BTC/USDT:USDT",
                order_type=OrderType.MARKET,
                direction=Direction.LONG,
                side="buy",
                amount=Decimal("0.02"),
                price=Decimal("65000"),
                status=OrderStatus.PARTIALLY_FILLED,
            )
        )

        orchestrator = ExecutionOrchestrator(
            capital_protection=capital_protection,
            order_lifecycle=order_lifecycle,
            gateway=gateway,
        )

        signal = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            direction=Direction.LONG,
            entry_price=Decimal("65000"),
            suggested_stop_loss=Decimal("64000"),
            suggested_position_size=Decimal("0.02"),
            current_leverage=10,
            tags=[],
            risk_reward_info="Risk 1% = 100 USDT",
            strategy_name="pinbar",
        )

        strategy = OrderStrategy(
            id="strategy_002",
            name="test_strategy",
            tp_levels=1,
            tp_ratios=[Decimal("1.0")],
            tp_targets=[Decimal("1.5")],
            initial_stop_loss_rr=Decimal("-1.0"),
        )

        # 执行信号
        intent = await orchestrator.execute_signal(signal, strategy)

        # 验证初始状态
        print(f"✅ ExecutionIntent 初始状态: {intent.status}")
        assert intent.status == ExecutionIntentStatus.SUBMITTED, \
            f"期望 SUBMITTED，实际 {intent.status}"

        # 模拟 WebSocket 推送：成交数量为 0（信息不足）
        entry_order = await repository.get_order(intent.order_id)

        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        exchange_order = Order(
            id="binance_entry_no_info",
            exchange_order_id="binance_entry_no_info",
            signal_id=entry_order.signal_id,
            symbol=entry_order.symbol,
            direction=entry_order.direction,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=entry_order.requested_qty,
            filled_qty=Decimal("0"),  # 成交数量为 0
            average_exec_price=None,
            status=OrderStatus.PARTIALLY_FILLED,
            created_at=current_time,
            updated_at=current_time,
        )

        # 触发 WebSocket 回写
        await order_lifecycle.update_order_from_exchange(exchange_order)

        # 验证没有挂载保护单
        all_orders = await repository.get_orders_by_signal(entry_order.signal_id)

        protection_orders = [
            o for o in all_orders
            if o.parent_order_id == entry_order.id
            and o.order_role in [OrderRole.SL, OrderRole.TP1]
        ]

        print(f"✅ 保护单数量: {len(protection_orders)}")
        assert len(protection_orders) == 0, \
            f"期望 0 个保护单，实际 {len(protection_orders)}"

        # 验证 ExecutionIntent 状态（仍为 SUBMITTED）
        print(f"✅ ExecutionIntent 最终状态: {intent.status}")
        assert intent.status == ExecutionIntentStatus.SUBMITTED, \
            f"期望 SUBMITTED，实际 {intent.status}"

        print("✅ 验证通过: 成交信息不足时不挂载保护单")

    finally:
        os.unlink(db_path)


async def test_protection_order_chain():
    """
    验证场景 3：订单链正确（parent_order_id / oco_group_id / order_role）
    """
    print("\n=== 验证场景 3：保护单订单链正确 ===")

    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    try:
        repository = OrderRepository(db_path)
        await repository.initialize()
        order_lifecycle = OrderLifecycleService(repository)
        await order_lifecycle.start()

        capital_protection = MagicMock(spec=CapitalProtectionManager)
        capital_protection.pre_order_check = AsyncMock(
            return_value=OrderCheckResult(
                allowed=True,
                reason=None,
                reason_message="所有检查通过",
            )
        )

        gateway = MagicMock(spec=ExchangeGateway)

        call_count = 0

        async def mock_place_order(**kwargs):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # ENTRY 订单：返回 PARTIALLY_FILLED
                return OrderPlacementResult(
                    order_id="entry_chain",
                    exchange_order_id="binance_entry_chain",
                    symbol=kwargs["symbol"],
                    order_type=OrderType.MARKET,
                    direction=Direction.LONG,
                    side="buy",
                    amount=kwargs["amount"],
                    price=Decimal("65000"),
                    status=OrderStatus.PARTIALLY_FILLED,
                )
            else:
                # 保护单：返回 OPEN
                return OrderPlacementResult(
                    order_id=f"prot_{call_count}",
                    exchange_order_id=f"binance_prot_{call_count}",
                    symbol=kwargs["symbol"],
                    order_type=OrderType.LIMIT,
                    direction=Direction.LONG,
                    side="sell",
                    amount=kwargs["amount"],
                    price=kwargs.get("price"),
                    status=OrderStatus.OPEN,
                )

        gateway.place_order = mock_place_order

        orchestrator = ExecutionOrchestrator(
            capital_protection=capital_protection,
            order_lifecycle=order_lifecycle,
            gateway=gateway,
        )

        signal = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            direction=Direction.LONG,
            entry_price=Decimal("65000"),
            suggested_stop_loss=Decimal("64000"),
            suggested_position_size=Decimal("0.02"),
            current_leverage=10,
            tags=[],
            risk_reward_info="Risk 1% = 100 USDT",
            strategy_name="pinbar",
        )

        strategy = OrderStrategy(
            id="strategy_003",
            name="test_strategy",
            tp_levels=1,
            tp_ratios=[Decimal("1.0")],
            tp_targets=[Decimal("1.5")],
            initial_stop_loss_rr=Decimal("-1.0"),
        )

        # 执行信号
        intent = await orchestrator.execute_signal(signal, strategy)

        # 模拟 WebSocket 推送：ENTRY 部分成交
        entry_order = await repository.get_order(intent.order_id)

        filled_qty = Decimal("0.015")  # 部分成交
        average_exec_price = Decimal("65000")

        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        exchange_order = Order(
            id="binance_entry_chain",
            exchange_order_id="binance_entry_chain",
            signal_id=entry_order.signal_id,
            symbol=entry_order.symbol,
            direction=entry_order.direction,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=entry_order.requested_qty,
            filled_qty=filled_qty,
            average_exec_price=average_exec_price,
            status=OrderStatus.PARTIALLY_FILLED,
            created_at=current_time,
            updated_at=current_time,
        )

        # 触发 WebSocket 回写
        await order_lifecycle.update_order_from_exchange(exchange_order)

        # 查询保护单
        all_orders = await repository.get_orders_by_signal(entry_order.signal_id)

        tp_order = None
        sl_order = None

        for order in all_orders:
            if order.order_role == OrderRole.TP1:
                tp_order = order
            elif order.order_role == OrderRole.SL:
                sl_order = order

        assert tp_order is not None, "TP 订单应存在"
        assert sl_order is not None, "SL 订单应存在"

        # 验证订单链关系
        print(f"✅ ENTRY 订单 ID: {entry_order.id}")
        print(f"✅ TP parent_order_id: {tp_order.parent_order_id}")
        print(f"✅ SL parent_order_id: {sl_order.parent_order_id}")

        assert tp_order.parent_order_id == entry_order.id, \
            "TP 的 parent_order_id 应为 ENTRY 订单 ID"
        assert sl_order.parent_order_id == entry_order.id, \
            "SL 的 parent_order_id 应为 ENTRY 订单 ID"

        # 验证 OCO 组 ID
        expected_oco_group = f"oco_{entry_order.signal_id}"

        print(f"✅ TP oco_group_id: {tp_order.oco_group_id}")
        print(f"✅ SL oco_group_id: {sl_order.oco_group_id}")

        assert tp_order.oco_group_id == expected_oco_group, \
            f"TP 的 oco_group_id 应为 {expected_oco_group}"
        assert sl_order.oco_group_id == expected_oco_group, \
            f"SL 的 oco_group_id 应为 {expected_oco_group}"

        # 验证订单数量
        print(f"✅ TP 订单数量: {tp_order.requested_qty}")
        print(f"✅ SL 订单数量: {sl_order.requested_qty}")

        assert tp_order.requested_qty == filled_qty, \
            f"TP 订单数量应为 {filled_qty}"
        assert sl_order.requested_qty == filled_qty, \
            f"SL 订单数量应为 {filled_qty}"

        print("✅ 验证通过: 保护单订单链正确")

    finally:
        os.unlink(db_path)


async def main():
    """运行所有验证场景"""
    print("=" * 70)
    print("受保护持仓闭环 MVP 第二步验证")
    print("=" * 70)

    try:
        await test_partially_filled_protection()
        await test_insufficient_fill_info()
        await test_protection_order_chain()

        print("\n" + "=" * 70)
        print("✅ 所有验证场景通过！")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
