"""
受保护持仓闭环 MVP 第一步验证脚本

验证场景：
1. 正常场景：ENTRY 成交 -> PROTECTING -> TP1/TP2/SL 全部成功 -> COMPLETED
2. 保护单部分失败：SL 成功、TP1 失败 -> 系统不进入 COMPLETED
3. 订单链正确：TP1/TP2/SL 都能在本地订单链中查到，与 ENTRY 关系明确
"""
import asyncio
import tempfile
import os
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

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


async def test_normal_protection_flow():
    """
    验证场景 1：正常场景

    ENTRY 成交 -> PROTECTING -> TP1/TP2/SL 全部成功 -> COMPLETED
    """
    print("\n=== 验证场景 1：正常场景 ===")

    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    try:
        repository = OrderRepository(db_path)
        await repository.initialize()
        order_lifecycle = OrderLifecycleService(repository)
        await order_lifecycle.start()

        # Mock CapitalProtection
        capital_protection = MagicMock(spec=CapitalProtectionManager)
        capital_protection.pre_order_check = AsyncMock(
            return_value=OrderCheckResult(
                allowed=True,
                reason=None,
                reason_message="所有检查通过",
            )
        )

        # Mock ExchangeGateway
        gateway = MagicMock(spec=ExchangeGateway)

        # Mock place_order() - ENTRY 成交
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

        # 创建 ExecutionOrchestrator
        orchestrator = ExecutionOrchestrator(
            capital_protection=capital_protection,
            order_lifecycle=order_lifecycle,
            gateway=gateway,
        )

        # 创建测试信号
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

        # 创建策略：2 个 TP
        strategy = OrderStrategy(
            id="strategy_001",
            name="test_strategy",
            tp_levels=2,
            tp_ratios=[Decimal("0.5"), Decimal("0.5")],
            tp_targets=[Decimal("1.0"), Decimal("3.5")],
            initial_stop_loss_rr=Decimal("-1.0"),
        )

        # 执行信号
        intent = await orchestrator.execute_signal(signal, strategy)

        # 验证结果
        print(f"✅ ExecutionIntent 状态: {intent.status}")
        print(f"   ENTRY 订单 ID: {intent.order_id}")
        print(f"   交易所订单 ID: {intent.exchange_order_id}")

        assert intent.status == ExecutionIntentStatus.COMPLETED, \
            f"期望 COMPLETED，实际 {intent.status}"

        # 验证订单链
        entry_order = await repository.get_order(intent.order_id)
        print(f"✅ ENTRY 订单状态: {entry_order.status}")
        assert entry_order.status == OrderStatus.FILLED

        # 查询 TP/SL 订单
        all_orders = await repository.get_orders_by_signal(entry_order.signal_id)
        tp_orders = [o for o in all_orders if o.order_role in [OrderRole.TP1, OrderRole.TP2]]
        sl_orders = [o for o in all_orders if o.order_role == OrderRole.SL]

        print(f"✅ TP 订单数量: {len(tp_orders)}")
        print(f"✅ SL 订单数量: {len(sl_orders)}")

        assert len(tp_orders) == 2, f"期望 2 个 TP 订单，实际 {len(tp_orders)}"
        assert len(sl_orders) == 1, f"期望 1 个 SL 订单，实际 {len(sl_orders)}"

        # 验证订单关系
        for tp_order in tp_orders:
            assert tp_order.parent_order_id == entry_order.id, \
                f"TP 订单的 parent_order_id 应为 ENTRY 订单 ID"
            assert tp_order.oco_group_id == f"oco_{entry_order.signal_id}", \
                f"TP 订单的 oco_group_id 应一致"

        for sl_order in sl_orders:
            assert sl_order.parent_order_id == entry_order.id, \
                f"SL 订单的 parent_order_id 应为 ENTRY 订单 ID"
            assert sl_order.oco_group_id == f"oco_{entry_order.signal_id}", \
                f"SL 订单的 oco_group_id 应一致"

        print("✅ 验证通过: 正常场景 - ENTRY 成交后自动挂载 TP/SL")

    finally:
        os.unlink(db_path)


async def test_protection_partial_failure():
    """
    验证场景 2：保护单部分失败

    SL 成功、TP1 失败 -> 系统不进入 COMPLETED
    """
    print("\n=== 验证场景 2：保护单部分失败 ===")

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
            elif call_count == 2:
                # TP1 订单：失败
                return OrderPlacementResult(
                    order_id="tp1_failed",
                    exchange_order_id=None,
                    symbol=kwargs["symbol"],
                    order_type=OrderType.LIMIT,
                    direction=Direction.LONG,
                    side="sell",
                    amount=kwargs["amount"],
                    price=kwargs.get("price"),
                    status=OrderStatus.REJECTED,
                    error_code="INSUFFICIENT_MARGIN",
                    error_message="Insufficient margin for TP1",
                )
            else:
                # SL 订单：成功
                return OrderPlacementResult(
                    order_id=f"sl_{call_count}",
                    exchange_order_id=f"binance_sl_{call_count}",
                    symbol=kwargs["symbol"],
                    order_type=OrderType.STOP_MARKET,
                    direction=Direction.LONG,
                    side="sell",
                    amount=kwargs["amount"],
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
            id="strategy_002",
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
        print(f"   失败原因: {intent.failed_reason}")

        # 系统不应进入 COMPLETED
        assert intent.status == ExecutionIntentStatus.FAILED, \
            f"期望 FAILED，实际 {intent.status}"

        assert "保护单挂载失败" in intent.failed_reason, \
            f"期望包含 '保护单挂载失败'，实际 {intent.failed_reason}"

        print("✅ 验证通过: 保护单部分失败 -> 系统不进入 COMPLETED")

    finally:
        os.unlink(db_path)


async def test_order_chain_relationship():
    """
    验证场景 3：订单链正确

    TP1/TP2/SL 都能在本地订单链中查到，与 ENTRY 关系明确
    """
    print("\n=== 验证场景 3：订单链正确 ===")

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
                    order_id="entry_789",
                    exchange_order_id="binance_entry_789",
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
            tp_levels=2,
            tp_ratios=[Decimal("0.5"), Decimal("0.5")],
            tp_targets=[Decimal("1.0"), Decimal("3.5")],
            initial_stop_loss_rr=Decimal("-1.0"),
        )

        # 执行信号
        intent = await orchestrator.execute_signal(signal, strategy)

        # 从 intent 获取 ENTRY 订单
        entry_order = await repository.get_order(intent.order_id)

        assert entry_order is not None, "ENTRY 订单应存在"

        # 查询所有订单（通过 signal_id）
        all_orders = await repository.get_orders_by_signal(entry_order.signal_id)

        # 查找 TP/SL 订单
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

        # 验证订单存在
        assert tp1_order is not None, "TP1 订单应存在"
        assert tp2_order is not None, "TP2 订单应存在"
        assert sl_order is not None, "SL 订单应存在"

        # 验证订单关系
        print(f"✅ ENTRY 订单 ID: {entry_order.id}")
        print(f"✅ TP1 订单 ID: {tp1_order.id}, parent_order_id: {tp1_order.parent_order_id}")
        print(f"✅ TP2 订单 ID: {tp2_order.id}, parent_order_id: {tp2_order.parent_order_id}")
        print(f"✅ SL 订单 ID: {sl_order.id}, parent_order_id: {sl_order.parent_order_id}")

        assert tp1_order.parent_order_id == entry_order.id, \
            "TP1 的 parent_order_id 应为 ENTRY 订单 ID"
        assert tp2_order.parent_order_id == entry_order.id, \
            "TP2 的 parent_order_id 应为 ENTRY 订单 ID"
        assert sl_order.parent_order_id == entry_order.id, \
            "SL 的 parent_order_id 应为 ENTRY 订单 ID"

        # 验证 OCO 组 ID
        expected_oco_group = f"oco_{entry_order.signal_id}"

        assert tp1_order.oco_group_id == expected_oco_group, \
            f"TP1 的 oco_group_id 应为 {expected_oco_group}"
        assert tp2_order.oco_group_id == expected_oco_group, \
            f"TP2 的 oco_group_id 应为 {expected_oco_group}"
        assert sl_order.oco_group_id == expected_oco_group, \
            f"SL 的 oco_group_id 应为 {expected_oco_group}"

        print("✅ 验证通过: 订单链关系正确")

    finally:
        os.unlink(db_path)


async def main():
    """运行所有验证场景"""
    print("=" * 70)
    print("受保护持仓闭环 MVP 第一步验证")
    print("=" * 70)

    try:
        await test_normal_protection_flow()
        await test_protection_partial_failure()
        await test_order_chain_relationship()

        print("\n" + "=" * 70)
        print("✅ 所有验证场景通过！")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
