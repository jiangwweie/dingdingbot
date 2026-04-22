"""
启动对账最小版验证脚本

验证场景：
1. 本地订单状态落后于交易所（例如本地 OPEN，交易所已 FILLED）
2. 待恢复订单存在于 _pending_recovery_orders，对账成功后清除标记
3. 某笔订单对账失败（例如交易所查不到 / 网络异常），不中断整轮启动对账
"""
import asyncio
import tempfile
import os
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.application.startup_reconciliation_service import StartupReconciliationService
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.order_repository import OrderRepository
from src.application.order_lifecycle_service import OrderLifecycleService
from src.domain.models import (
    Order,
    OrderStatus,
    OrderType,
    OrderRole,
    Direction,
    OrderPlacementResult,
    OrderStrategy,
)


async def test_local_state_behind_exchange():
    """
    验证场景 1：本地订单状态落后于交易所

    场景：
    - 本地订单状态：OPEN
    - 交易所状态：FILLED
    - 启动对账后本地状态被正确推进
    """
    print("\n=== 验证场景 1：本地订单状态落后于交易所 ===")

    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    try:
        # 初始化组件
        repository = OrderRepository(db_path)
        await repository.initialize()
        lifecycle = OrderLifecycleService(repository)
        await lifecycle.start()

        gateway = ExchangeGateway(
            exchange_name="binance",
            api_key="test_key",
            api_secret="test_secret",
            testnet=True,
        )

        # 创建本地订单（状态为 OPEN）
        strategy = OrderStrategy(id="strategy_001", name="test_strategy")
        local_order = await lifecycle.create_order(
            strategy=strategy,
            signal_id="sig_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal("0.01"),
            initial_sl_rr=Decimal("-1.0"),
            tp_targets=[],
        )

        # 提交订单（获得 exchange_order_id）
        exchange_order_id = "binance_123"
        await lifecycle.submit_order(local_order.id, exchange_order_id=exchange_order_id)
        await lifecycle.confirm_order(local_order.id)

        print(f"✅ 本地订单创建成功:")
        print(f"   本地订单 ID: {local_order.id}")
        print(f"   交易所订单 ID: {exchange_order_id}")
        print(f"   本地状态: OPEN")

        # Mock fetch_order() 返回 FILLED 状态
        async def mock_fetch_order(exchange_order_id: str, symbol: str):
            return OrderPlacementResult(
                order_id=exchange_order_id,
                exchange_order_id=exchange_order_id,
                symbol=symbol,
                order_type=OrderType.MARKET,
                direction=Direction.LONG,
                side="buy",
                amount=Decimal("0.01"),
                price=Decimal("65000"),
                status=OrderStatus.FILLED,
            )

        gateway.fetch_order = mock_fetch_order

        # 创建启动对账服务
        service = StartupReconciliationService(
            gateway=gateway,
            repository=repository,
            lifecycle=lifecycle,
        )

        # 执行启动对账
        summary = await service.run_startup_reconciliation()

        print(f"\n✅ 对账结果:")
        print(f"   候选订单: {summary['total_candidates']} 个")
        print(f"   对账成功: {summary['success_count']} 个")
        print(f"   对账失败: {summary['failure_count']} 个")

        # 验证本地订单状态已推进
        updated_order = await repository.get_order(local_order.id)
        print(f"\n✅ 本地订单最终状态: {updated_order.status}")

        assert updated_order.status == OrderStatus.FILLED, \
            f"期望 FILLED，实际 {updated_order.status}"

        print("✅ 验证通过: 本地订单状态已正确推进")

    finally:
        os.unlink(db_path)


async def test_pending_recovery_order_cleared():
    """
    验证场景 2：待恢复订单对账成功后清除标记

    场景：
    - 订单在 _pending_recovery_orders 中
    - 对账成功后，标记被清除
    """
    print("\n=== 验证场景 2：待恢复订单对账成功后清除标记 ===")

    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    try:
        repository = OrderRepository(db_path)
        await repository.initialize()
        lifecycle = OrderLifecycleService(repository)
        await lifecycle.start()

        gateway = ExchangeGateway(
            exchange_name="binance",
            api_key="test_key",
            api_secret="test_secret",
            testnet=True,
        )

        # 创建本地订单
        strategy = OrderStrategy(id="strategy_002", name="test_strategy")
        local_order = await lifecycle.create_order(
            strategy=strategy,
            signal_id="sig_002",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal("0.02"),
            initial_sl_rr=Decimal("-1.0"),
            tp_targets=[],
        )

        exchange_order_id = "binance_456"
        await lifecycle.submit_order(local_order.id, exchange_order_id=exchange_order_id)
        await lifecycle.confirm_order(local_order.id)

        print(f"✅ 本地订单创建成功: exchange_order_id={exchange_order_id}")

        # 模拟订单在待恢复列表中
        gateway._pending_recovery_orders[exchange_order_id] = {
            "order": local_order,
            "error": "模拟 WS 回调失败",
            "failed_at": 1000,
        }

        print(f"✅ 订单已加入待恢复列表: {exchange_order_id}")

        # Mock fetch_order() 返回 FILLED 状态
        async def mock_fetch_order(exchange_order_id: str, symbol: str):
            return OrderPlacementResult(
                order_id=exchange_order_id,
                exchange_order_id=exchange_order_id,
                symbol=symbol,
                order_type=OrderType.MARKET,
                direction=Direction.LONG,
                side="buy",
                amount=Decimal("0.02"),
                price=Decimal("65000"),
                status=OrderStatus.FILLED,
            )

        gateway.fetch_order = mock_fetch_order

        # 创建启动对账服务
        service = StartupReconciliationService(
            gateway=gateway,
            repository=repository,
            lifecycle=lifecycle,
        )

        # 执行启动对账
        summary = await service.run_startup_reconciliation()

        print(f"\n✅ 对账结果:")
        print(f"   清除待恢复标记: {summary['recovery_cleared_count']} 个")

        # 验证待恢复标记已清除
        pending_orders = gateway.get_pending_recovery_orders()
        print(f"\n✅ 待恢复订单列表: {list(pending_orders.keys())}")

        assert exchange_order_id not in pending_orders, \
            f"期望 {exchange_order_id} 已从待恢复列表清除"

        print("✅ 验证通过: 待恢复标记已清除")

    finally:
        os.unlink(db_path)


async def test_reconciliation_failure_not_interrupt():
    """
    验证场景 3：某笔订单对账失败，不中断整轮启动对账

    场景：
    - 3 笔订单
    - 第 2 笔对账失败（交易所查不到）
    - 第 3 笔仍然继续处理
    """
    print("\n=== 验证场景 3：某笔订单对账失败，不中断整轮启动对账 ===")

    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    try:
        repository = OrderRepository(db_path)
        await repository.initialize()
        lifecycle = OrderLifecycleService(repository)
        await lifecycle.start()

        gateway = ExchangeGateway(
            exchange_name="binance",
            api_key="test_key",
            api_secret="test_secret",
            testnet=True,
        )

        # 创建 3 笔本地订单
        strategy = OrderStrategy(id="strategy_003", name="test_strategy")

        orders = []
        for i in range(1, 4):
            order = await lifecycle.create_order(
                strategy=strategy,
                signal_id=f"sig_00{i}",
                symbol="BTC/USDT:USDT",
                direction=Direction.LONG,
                total_qty=Decimal("0.01"),
                initial_sl_rr=Decimal("-1.0"),
                tp_targets=[],
            )

            exchange_order_id = f"binance_{i}"
            await lifecycle.submit_order(order.id, exchange_order_id=exchange_order_id)
            await lifecycle.confirm_order(order.id)

            orders.append((order, exchange_order_id))

        print(f"✅ 创建 3 笔本地订单")

        # Mock fetch_order() - 第 2 笔失败
        call_count = 0

        async def mock_fetch_order(exchange_order_id: str, symbol: str):
            nonlocal call_count
            call_count += 1

            if exchange_order_id == "binance_2":
                # 第 2 笔订单对账失败
                raise Exception("模拟对账失败：交易所查不到订单")

            # 第 1 笔和第 3 笔成功
            return OrderPlacementResult(
                order_id=exchange_order_id,
                exchange_order_id=exchange_order_id,
                symbol=symbol,
                order_type=OrderType.MARKET,
                direction=Direction.LONG,
                side="buy",
                amount=Decimal("0.01"),
                price=Decimal("65000"),
                status=OrderStatus.FILLED,
            )

        gateway.fetch_order = mock_fetch_order

        # 创建启动对账服务
        service = StartupReconciliationService(
            gateway=gateway,
            repository=repository,
            lifecycle=lifecycle,
        )

        # 执行启动对账
        summary = await service.run_startup_reconciliation()

        print(f"\n✅ 对账结果:")
        print(f"   候选订单: {summary['total_candidates']} 个")
        print(f"   对账成功: {summary['success_count']} 个")
        print(f"   对账失败: {summary['failure_count']} 个")

        # 验证结果
        assert summary['total_candidates'] == 3, \
            f"期望 3 个候选订单，实际 {summary['total_candidates']}"
        assert summary['success_count'] == 2, \
            f"期望 2 个成功，实际 {summary['success_count']}"
        assert summary['failure_count'] == 1, \
            f"期望 1 个失败，实际 {summary['failure_count']}"

        # 验证第 1 笔和第 3 笔订单状态已推进
        order_1 = await repository.get_order(orders[0][0].id)
        order_3 = await repository.get_order(orders[2][0].id)

        assert order_1.status == OrderStatus.FILLED, \
            f"期望第 1 笔订单 FILLED，实际 {order_1.status}"
        assert order_3.status == OrderStatus.FILLED, \
            f"期望第 3 笔订单 FILLED，实际 {order_3.status}"

        print("✅ 验证通过: 第 2 笔失败未中断整轮对账，第 1 笔和第 3 笔成功")

    finally:
        os.unlink(db_path)


async def main():
    """运行所有验证场景"""
    print("=" * 70)
    print("启动对账最小版验证")
    print("=" * 70)

    try:
        await test_local_state_behind_exchange()
        await test_pending_recovery_order_cleared()
        await test_reconciliation_failure_not_interrupt()

        print("\n" + "=" * 70)
        print("✅ 所有验证场景通过！")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
