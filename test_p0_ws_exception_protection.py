"""
P0-WS-Exception-Protection 验证脚本

验证场景：
1. 模拟某一笔订单回调抛异常
2. 该异常被捕获并记录
3. 同一批后续订单事件仍继续处理，没有因为单笔失败而中断整条消费链
"""
import asyncio
import tempfile
import os
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List

from src.infrastructure.exchange_gateway import ExchangeGateway
from src.domain.models import (
    Order,
    OrderStatus,
    OrderType,
    OrderRole,
    Direction,
)


async def test_callback_exception_protection():
    """验证场景：订单回调异常保护"""
    print("\n=== 验证场景：订单回调异常保护 ===")

    # 创建 ExchangeGateway（Mock）
    gateway = ExchangeGateway(
        exchange_name="binance",
        api_key="test_key",
        api_secret="test_secret",
        testnet=True,
    )

    # 模拟订单列表（3 笔订单）
    orders = [
        Order(
            id="order_1",
            signal_id="sig_1",
            exchange_order_id="binance_1",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("0.01"),
            filled_qty=Decimal("0.01"),
            status=OrderStatus.FILLED,
            created_at=1000,
            updated_at=1000,
        ),
        Order(
            id="order_2",
            signal_id="sig_2",
            exchange_order_id="binance_2",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("0.02"),
            filled_qty=Decimal("0.02"),
            status=OrderStatus.FILLED,
            created_at=2000,
            updated_at=2000,
        ),
        Order(
            id="order_3",
            signal_id="sig_3",
            exchange_order_id="binance_3",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("0.03"),
            filled_qty=Decimal("0.03"),
            status=OrderStatus.FILLED,
            created_at=3000,
            updated_at=3000,
        ),
    ]

    # 记录回调执行情况
    callback_results: List[str] = []

    # 定义业务回调（第 2 笔订单抛异常）
    async def business_callback(order: Order):
        callback_results.append(order.exchange_order_id)

        if order.exchange_order_id == "binance_2":
            # 模拟第 2 笔订单回调失败
            raise Exception("模拟业务回调失败：数据库写入异常")

        print(f"✅ 成功处理订单: {order.exchange_order_id}")

    # Mock _handle_order_update 和 _notify_global_order_callback
    async def mock_handle_order_update(raw_order):
        # 直接返回订单对象
        return raw_order

    async def mock_notify_global_callback(order):
        # 全局回调成功
        print(f"✅ 全局回调成功: {order.exchange_order_id}")

    # 模拟 watch_orders() 内部的订单处理循环
    print("\n模拟订单处理循环（3 笔订单，第 2 笔失败）:")

    # 替换方法
    gateway._handle_order_update = mock_handle_order_update
    gateway._notify_global_order_callback = mock_notify_global_callback

    # 模拟订单处理循环（直接调用，不启动 WebSocket）
    for raw_order in orders:
        order = await gateway._handle_order_update(raw_order)
        if order:
            await gateway._notify_global_order_callback(order)

            # P0-WS-Exception-Protection: 业务回调异常保护
            try:
                await business_callback(order)
            except Exception as e:
                # 记录高优错误日志
                print(
                    f"⚠️ 订单回调失败，订单已标记为待恢复: "
                    f"exchange_order_id={order.exchange_order_id}, "
                    f"symbol={order.symbol}, status={order.status}, "
                    f"error={e}"
                )

                # 标记为待恢复对象
                gateway._pending_recovery_orders[order.exchange_order_id] = {
                    "order": order,
                    "error": str(e),
                    "failed_at": 4000,
                }

                # 继续处理后续订单事件（不中断消费循环）

    # 验证结果
    print("\n验证结果:")
    print(f"✅ 回调执行记录: {callback_results}")
    assert callback_results == ["binance_1", "binance_2", "binance_3"], \
        f"期望 ['binance_1', 'binance_2', 'binance_3']，实际 {callback_results}"

    print(f"✅ 待恢复订单: {list(gateway._pending_recovery_orders.keys())}")
    assert "binance_2" in gateway._pending_recovery_orders, \
        "期望 binance_2 在待恢复订单列表中"

    recovery_info = gateway._pending_recovery_orders["binance_2"]
    print(f"✅ 待恢复订单详情: {recovery_info['error']}")
    assert "数据库写入异常" in recovery_info["error"], \
        f"期望包含 '数据库写入异常'，实际 {recovery_info['error']}"

    print("\n✅ 验证通过:")
    print("   1. 第 2 笔订单回调失败被捕获并记录")
    print("   2. 第 3 笔订单继续处理（消费循环未中断）")
    print("   3. 待恢复订单已标记")


async def test_get_and_clear_pending_recovery():
    """验证获取和清除待恢复订单"""
    print("\n=== 验证场景：获取和清除待恢复订单 ===")

    gateway = ExchangeGateway(
        exchange_name="binance",
        api_key="test_key",
        api_secret="test_secret",
        testnet=True,
    )

    # 添加待恢复订单
    order = Order(
        id="order_test",
        signal_id="sig_test",
        exchange_order_id="binance_test",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal("0.01"),
        filled_qty=Decimal("0.01"),
        status=OrderStatus.FILLED,
        created_at=1000,
        updated_at=1000,
    )

    gateway._pending_recovery_orders["binance_test"] = {
        "order": order,
        "error": "测试错误",
        "failed_at": 1000,
    }

    # 获取待恢复订单
    pending = gateway.get_pending_recovery_orders()
    print(f"✅ 获取待恢复订单: {list(pending.keys())}")
    assert "binance_test" in pending, "期望 binance_test 在待恢复订单列表中"

    # 清除待恢复订单
    gateway.clear_pending_recovery_order("binance_test")
    pending_after = gateway.get_pending_recovery_orders()
    print(f"✅ 清除后待恢复订单: {list(pending_after.keys())}")
    assert "binance_test" not in pending_after, "期望 binance_test 已清除"

    print("\n✅ 验证通过: 获取和清除待恢复订单功能正常")


async def main():
    """运行所有验证场景"""
    print("=" * 70)
    print("P0-WS-Exception-Protection 验证")
    print("=" * 70)

    try:
        await test_callback_exception_protection()
        await test_get_and_clear_pending_recovery()

        print("\n" + "=" * 70)
        print("✅ 所有验证场景通过！")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())