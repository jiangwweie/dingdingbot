"""
P1 修复验证脚本

验证场景：
1. PARTIALLY_FILLED 分支结束后，ExecutionIntent 不再是 COMPLETED
2. CANCELED 分支结束后，ExecutionIntent 不再是 COMPLETED
3. 保护单提交流程不再以直接 repository.save() 作为主路径
4. 保护单仍然能正确建立 parent_order_id / oco_group_id / order_role
"""
import asyncio
import tempfile
import os
from decimal import Decimal
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
    OrderRole,
)
from src.application.capital_protection import CapitalProtectionManager
from src.application.order_lifecycle_service import OrderLifecycleService
from src.infrastructure.order_repository import OrderRepository
from src.infrastructure.exchange_gateway import ExchangeGateway


async def test_partially_filled_not_completed():
    """
    验证场景 1：PARTIALLY_FILLED 分支结束后，ExecutionIntent 不再是 COMPLETED
    """
    print("\n=== 验证场景 1：PARTIALLY_FILLED 分支状态 ===")

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

        # Mock place_order() 返回 PARTIALLY_FILLED
        gateway.place_order = AsyncMock(
            return_value=OrderPlacementResult(
                order_id="entry_partial",
                exchange_order_id="binance_partial",
                symbol="BTC/USDT:USDT",
                order_type=OrderType.MARKET,
                direction=Direction.LONG,
                side="buy",
                amount=Decimal("0.01"),
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
            suggested_position_size=Decimal("0.01"),
            current_leverage=10,
            tags=[],
            risk_reward_info="Risk 1% = 100 USDT",
            strategy_name="pinbar",
        )

        strategy = OrderStrategy(
            id="strategy_001",
            name="test_strategy",
        )

        # 执行信号
        intent = await orchestrator.execute_signal(signal, strategy)

        # 验证结果
        print(f"✅ ExecutionIntent 状态: {intent.status}")
        print(f"   订单 ID: {intent.order_id}")
        print(f"   交易所订单 ID: {intent.exchange_order_id}")

        # P1 修复：不应是 COMPLETED
        assert intent.status != ExecutionIntentStatus.COMPLETED, \
            f"不应是 COMPLETED，实际 {intent.status}"

        # 应该是 SUBMITTED（表示已提交但未完成）
        assert intent.status == ExecutionIntentStatus.SUBMITTED, \
            f"期望 SUBMITTED，实际 {intent.status}"

        print("✅ 验证通过: PARTIALLY_FILLED 分支状态正确（SUBMITTED）")

    finally:
        os.unlink(db_path)


async def test_canceled_not_completed():
    """
    验证场景 2：CANCELED 分支结束后，ExecutionIntent 不再是 COMPLETED
    """
    print("\n=== 验证场景 2：CANCELED 分支状态 ===")

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

        # Mock place_order() 返回 CANCELED
        gateway.place_order = AsyncMock(
            return_value=OrderPlacementResult(
                order_id="entry_canceled",
                exchange_order_id="binance_canceled",
                symbol="BTC/USDT:USDT",
                order_type=OrderType.MARKET,
                direction=Direction.LONG,
                side="buy",
                amount=Decimal("0.01"),
                price=Decimal("65000"),
                status=OrderStatus.CANCELED,
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
            suggested_position_size=Decimal("0.01"),
            current_leverage=10,
            tags=[],
            risk_reward_info="Risk 1% = 100 USDT",
            strategy_name="pinbar",
        )

        strategy = OrderStrategy(
            id="strategy_002",
            name="test_strategy",
        )

        # 执行信号
        intent = await orchestrator.execute_signal(signal, strategy)

        # 验证结果
        print(f"✅ ExecutionIntent 状态: {intent.status}")
        print(f"   订单 ID: {intent.order_id}")
        print(f"   失败原因: {intent.failed_reason}")

        # P1 修复：不应是 COMPLETED
        assert intent.status != ExecutionIntentStatus.COMPLETED, \
            f"不应是 COMPLETED，实际 {intent.status}"

        # 应该是 FAILED
        assert intent.status == ExecutionIntentStatus.FAILED, \
            f"期望 FAILED，实际 {intent.status}"

        assert "交易所取消订单" in intent.failed_reason, \
            f"期望包含 '交易所取消订单'，实际 {intent.failed_reason}"

        print("✅ 验证通过: CANCELED 分支状态正确（FAILED）")

    finally:
        os.unlink(db_path)


async def test_protection_uses_lifecycle_service():
    """
    验证场景 3：保护单提交流程使用 OrderLifecycleService 正式链
    """
    print("\n=== 验证场景 3：保护单使用 OrderLifecycleService 正式链 ===")

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
                # ENTRY 订单：返回 FILLED
                return OrderPlacementResult(
                    order_id="entry_123",
                    exchange_order_id="binance_entry_123",
                    symbol=kwargs["symbol"],
                    order_type=OrderType.MARKET,
                    direction=Direction.LONG,
                    side="buy",
                    amount=kwargs["amount"],
                    price=Decimal("65000"),
                    status=OrderStatus.FILLED,
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
            suggested_position_size=Decimal("0.01"),
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

        # 验证结果
        print(f"✅ ExecutionIntent 状态: {intent.status}")

        assert intent.status == ExecutionIntentStatus.COMPLETED, \
            f"期望 COMPLETED，实际 {intent.status}"

        # 查询保护单
        entry_order = await repository.get_order(intent.order_id)
        all_orders = await repository.get_orders_by_signal(entry_order.signal_id)

        tp_orders = [o for o in all_orders if o.order_role == OrderRole.TP1]
        sl_orders = [o for o in all_orders if o.order_role == OrderRole.SL]

        print(f"✅ TP 订单数量: {len(tp_orders)}")
        print(f"✅ SL 订单数量: {len(sl_orders)}")

        assert len(tp_orders) == 1, f"期望 1 个 TP 订单，实际 {len(tp_orders)}"
        assert len(sl_orders) == 1, f"期望 1 个 SL 订单，实际 {len(sl_orders)}"

        # 验证保护单状态（应该是 OPEN，而不是 CREATED）
        tp_order = tp_orders[0]
        sl_order = sl_orders[0]

        print(f"✅ TP 订单状态: {tp_order.status}")
        print(f"✅ SL 订单状态: {sl_order.status}")

        assert tp_order.status == OrderStatus.OPEN, \
            f"期望 TP 订单状态为 OPEN，实际 {tp_order.status}"
        assert sl_order.status == OrderStatus.OPEN, \
            f"期望 SL 订单状态为 OPEN，实际 {sl_order.status}"

        # 验证 exchange_order_id 已回填
        assert tp_order.exchange_order_id is not None, \
            "TP 订单应有 exchange_order_id"
        assert sl_order.exchange_order_id is not None, \
            "SL 订单应有 exchange_order_id"

        print(f"✅ TP exchange_order_id: {tp_order.exchange_order_id}")
        print(f"✅ SL exchange_order_id: {sl_order.exchange_order_id}")

        print("✅ 验证通过: 保护单使用 OrderLifecycleService 正式链")

    finally:
        os.unlink(db_path)


async def test_protection_order_chain_correct():
    """
    验证场景 4：保护单仍然能正确建立 parent_order_id / oco_group_id / order_role
    """
    print("\n=== 验证场景 4：保护单订单链关系正确 ===")

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
                return OrderPlacementResult(
                    order_id="entry_456",
                    exchange_order_id="binance_entry_456",
                    symbol=kwargs["symbol"],
                    order_type=OrderType.MARKET,
                    direction=Direction.LONG,
                    side="buy",
                    amount=kwargs["amount"],
                    price=Decimal("65000"),
                    status=OrderStatus.FILLED,
                )
            else:
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
            suggested_position_size=Decimal("0.01"),
            current_leverage=10,
            tags=[],
            risk_reward_info="Risk 1% = 100 USDT",
            strategy_name="pinbar",
        )

        strategy = OrderStrategy(
            id="strategy_004",
            name="test_strategy",
            tp_levels=2,
            tp_ratios=[Decimal("0.5"), Decimal("0.5")],
            tp_targets=[Decimal("1.0"), Decimal("3.5")],
            initial_stop_loss_rr=Decimal("-1.0"),
        )

        # 执行信号
        intent = await orchestrator.execute_signal(signal, strategy)

        # 查询订单
        entry_order = await repository.get_order(intent.order_id)
        all_orders = await repository.get_orders_by_signal(entry_order.signal_id)

        tp1_order = None
        tp2_order = None
        sl_order = None

        for order in all_orders:
            if order.order_role == OrderRole.TP1:
                tp1_order = order
            elif order.order_role == OrderRole.TP2:
                tp2_order = order
            elif order.order_role == OrderRole.SL:
                sl_order = order

        assert tp1_order is not None, "TP1 订单应存在"
        assert tp2_order is not None, "TP2 订单应存在"
        assert sl_order is not None, "SL 订单应存在"

        # 验证订单链关系
        print(f"✅ ENTRY 订单 ID: {entry_order.id}")
        print(f"✅ TP1 parent_order_id: {tp1_order.parent_order_id}")
        print(f"✅ TP2 parent_order_id: {tp2_order.parent_order_id}")
        print(f"✅ SL parent_order_id: {sl_order.parent_order_id}")

        assert tp1_order.parent_order_id == entry_order.id, \
            "TP1 的 parent_order_id 应为 ENTRY 订单 ID"
        assert tp2_order.parent_order_id == entry_order.id, \
            "TP2 的 parent_order_id 应为 ENTRY 订单 ID"
        assert sl_order.parent_order_id == entry_order.id, \
            "SL 的 parent_order_id 应为 ENTRY 订单 ID"

        # 验证 OCO 组 ID
        expected_oco_group = f"oco_{entry_order.signal_id}"

        print(f"✅ TP1 oco_group_id: {tp1_order.oco_group_id}")
        print(f"✅ TP2 oco_group_id: {tp2_order.oco_group_id}")
        print(f"✅ SL oco_group_id: {sl_order.oco_group_id}")

        assert tp1_order.oco_group_id == expected_oco_group, \
            f"TP1 的 oco_group_id 应为 {expected_oco_group}"
        assert tp2_order.oco_group_id == expected_oco_group, \
            f"TP2 的 oco_group_id 应为 {expected_oco_group}"
        assert sl_order.oco_group_id == expected_oco_group, \
            f"SL 的 oco_group_id 应为 {expected_oco_group}"

        print("✅ 验证通过: 保护单订单链关系正确")

    finally:
        os.unlink(db_path)


async def main():
    """运行所有验证场景"""
    print("=" * 70)
    print("P1 修复验证")
    print("=" * 70)

    try:
        await test_partially_filled_not_completed()
        await test_canceled_not_completed()
        await test_protection_uses_lifecycle_service()
        await test_protection_order_chain_correct()

        print("\n" + "=" * 70)
        print("✅ 所有验证场景通过！")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
