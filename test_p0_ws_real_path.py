"""
P0-WS-Exception-Protection 真实路径验证

目标：
验证 watch_orders() 的真实代码路径上的异常保护

关键改进：
1. Mock ws_exchange.watch_orders() 返回订单
2. 让真实的 ExchangeGateway.watch_orders() 方法执行
3. 验证异常保护在真实代码路径上生效

不再手工复写消费循环，而是走真实方法调用链
"""
import asyncio
import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch, create_autospec
from typing import List, Dict, Any

from src.infrastructure.exchange_gateway import ExchangeGateway
from src.domain.models import (
    Order,
    OrderStatus,
    OrderType,
    OrderRole,
    Direction,
)


async def test_real_watch_orders_path():
    """
    验证场景：真实 watch_orders() 路径上的异常保护

    验证点：
    1. 第 2 笔订单的业务回调抛异常
    2. 第 2 笔进入 _pending_recovery_orders
    3. 第 3 笔仍然继续经过真实消费路径被处理
    """
    print("\n=== 验证场景：真实 watch_orders() 路径上的异常保护 ===")

    # 创建 ExchangeGateway
    gateway = ExchangeGateway(
        exchange_name="binance",
        api_key="test_key",
        api_secret="test_secret",
        testnet=True,
    )

    # 模拟 3 笔订单的原始数据（CCXT 格式）
    raw_orders = [
        {
            "id": "binance_1",
            "clientOrderId": "sig_1",
            "symbol": "BTC/USDT:USDT",
            "type": "market",
            "side": "buy",
            "amount": 0.01,
            "filled": 0.01,
            "remaining": 0,
            "price": None,
            "average": 65000,
            "status": "closed",
            "timestamp": int(time.time() * 1000),
            "reduceOnly": False,
        },
        {
            "id": "binance_2",
            "clientOrderId": "sig_2",
            "symbol": "BTC/USDT:USDT",
            "type": "market",
            "side": "buy",
            "amount": 0.02,
            "filled": 0.02,
            "remaining": 0,
            "price": None,
            "average": 65000,
            "status": "closed",
            "timestamp": int(time.time() * 1000),
            "reduceOnly": False,
        },
        {
            "id": "binance_3",
            "clientOrderId": "sig_3",
            "symbol": "BTC/USDT:USDT",
            "type": "market",
            "side": "buy",
            "amount": 0.03,
            "filled": 0.03,
            "remaining": 0,
            "price": None,
            "average": 65000,
            "status": "closed",
            "timestamp": int(time.time() * 1000),
            "reduceOnly": False,
        },
    ]

    # 记录业务回调执行情况
    callback_results: List[str] = []

    # 定义业务回调（第 2 笔订单抛异常）
    async def business_callback(order: Order):
        callback_results.append(order.exchange_order_id)

        if order.exchange_order_id == "binance_2":
            # 模拟第 2 笔订单回调失败
            raise Exception("模拟业务回调失败：数据库写入异常")

        print(f"✅ 业务回调成功: {order.exchange_order_id}")

    # Mock WebSocket 交换实例
    mock_ws_exchange = MagicMock()

    # Mock load_markets()
    mock_ws_exchange.load_markets = AsyncMock()

    # Mock watch_orders() - 第一次返回订单列表，第二次阻塞（模拟等待新订单）
    call_count = 0

    async def mock_watch_orders(symbol: str):
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            # 第一次调用：返回 3 笔订单
            return raw_orders
        else:
            # 后续调用：阻塞，模拟等待新订单
            # 但我们会在处理完第一批订单后取消任务
            await asyncio.sleep(10)

    mock_ws_exchange.watch_orders = mock_watch_orders

    # Mock close()
    mock_ws_exchange.close = AsyncMock()

    # Mock _create_ws_exchange() 返回 mock 对象
    with patch.object(gateway, '_create_ws_exchange', return_value=mock_ws_exchange):
        # 启动 watch_orders() 任务
        watch_task = asyncio.create_task(
            gateway.watch_orders("BTC/USDT:USDT", business_callback)
        )

        # 等待第一批订单处理完成
        # 通过检查 callback_results 来判断
        max_wait = 5  # 最多等待 5 秒
        start_time = time.time()

        while time.time() - start_time < max_wait:
            if len(callback_results) >= 3:
                # 已处理完 3 笔订单
                break
            await asyncio.sleep(0.1)

        # 取消 watch_orders() 任务（停止监听）
        watch_task.cancel()
        try:
            await watch_task
        except asyncio.CancelledError:
            pass

    # 验证结果
    print("\n验证结果:")
    print(f"✅ 业务回调执行记录: {callback_results}")

    # 验证点 1：3 笔订单都被处理
    assert callback_results == ["binance_1", "binance_2", "binance_3"], \
        f"期望 ['binance_1', 'binance_2', 'binance_3']，实际 {callback_results}"
    print("✅ 验证点 1: 3 笔订单都经过真实消费路径被处理")

    # 验证点 2：第 2 笔订单进入待恢复列表
    pending_orders = gateway.get_pending_recovery_orders()
    print(f"✅ 待恢复订单: {list(pending_orders.keys())}")

    assert "binance_2" in pending_orders, \
        "期望 binance_2 在待恢复订单列表中"
    print("✅ 验证点 2: 第 2 笔订单（回调失败）已标记为待恢复")

    # 验证点 3：待恢复订单包含完整信息
    recovery_info = pending_orders["binance_2"]
    print(f"✅ 待恢复订单详情: error={recovery_info['error']}")

    assert "数据库写入异常" in recovery_info["error"], \
        f"期望包含 '数据库写入异常'，实际 {recovery_info['error']}"
    assert "order" in recovery_info, "期望包含 order 字段"
    assert "failed_at" in recovery_info, "期望包含 failed_at 字段"
    print("✅ 验证点 3: 待恢复订单包含完整信息（order/error/failed_at）")

    # 验证点 4：第 3 笔订单成功处理（消费循环未中断）
    assert "binance_3" in callback_results, \
        "期望 binance_3 在回调执行记录中"
    print("✅ 验证点 4: 第 3 笔订单成功处理（消费循环未中断）")

    print("\n✅ 真实路径验证通过:")
    print("   1. 订单通过 watch_orders() 真实代码路径进入处理")
    print("   2. 第 2 笔订单回调失败被捕获并标记")
    print("   3. 第 3 笔订单继续处理（消费循环未中断）")
    print("   4. 异常保护在真实代码路径上生效")


async def test_global_callback_success_on_business_failure():
    """
    验证场景：业务回调失败时，全局回调仍然成功

    验证点：
    1. 全局回调成功执行
    2. 业务回调失败
    3. 订单仍然进入待恢复列表
    """
    print("\n=== 验证场景：全局回调成功 + 业务回调失败 ===")

    gateway = ExchangeGateway(
        exchange_name="binance",
        api_key="test_key",
        api_secret="test_secret",
        testnet=True,
    )

    # 记录全局回调执行情况
    global_callback_results: List[str] = []
    business_callback_results: List[str] = []

    # 定义全局回调（总是成功）
    async def global_callback(order: Order):
        global_callback_results.append(order.exchange_order_id)
        print(f"✅ 全局回调成功: {order.exchange_order_id}")

    # 设置全局回调
    gateway._global_order_callback = global_callback

    # 定义业务回调（第 2 笔失败）
    async def business_callback(order: Order):
        business_callback_results.append(order.exchange_order_id)

        if order.exchange_order_id == "binance_2":
            raise Exception("业务回调失败")

        print(f"✅ 业务回调成功: {order.exchange_order_id}")

    # 模拟订单数据
    raw_orders = [
        {
            "id": f"binance_{i}",
            "clientOrderId": f"sig_{i}",
            "symbol": "BTC/USDT:USDT",
            "type": "market",
            "side": "buy",
            "amount": 0.01,
            "filled": 0.01,
            "remaining": 0,
            "price": None,
            "average": 65000,
            "status": "closed",
            "timestamp": int(time.time() * 1000),
            "reduceOnly": False,
        }
        for i in [1, 2, 3]
    ]

    # Mock WebSocket
    mock_ws_exchange = MagicMock()
    mock_ws_exchange.load_markets = AsyncMock()

    call_count = 0

    async def mock_watch_orders(symbol: str):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return raw_orders
        else:
            await asyncio.sleep(10)

    mock_ws_exchange.watch_orders = mock_watch_orders
    mock_ws_exchange.close = AsyncMock()

    with patch.object(gateway, '_create_ws_exchange', return_value=mock_ws_exchange):
        watch_task = asyncio.create_task(
            gateway.watch_orders("BTC/USDT:USDT", business_callback)
        )

        # 等待处理完成
        max_wait = 5
        start_time = time.time()

        while time.time() - start_time < max_wait:
            if len(business_callback_results) >= 3:
                break
            await asyncio.sleep(0.1)

        watch_task.cancel()
        try:
            await watch_task
        except asyncio.CancelledError:
            pass

    # 验证结果
    print("\n验证结果:")
    print(f"✅ 全局回调执行记录: {global_callback_results}")
    print(f"✅ 业务回调执行记录: {business_callback_results}")

    # 验证点 1：全局回调成功执行 3 次
    assert global_callback_results == ["binance_1", "binance_2", "binance_3"], \
        f"期望全局回调执行 3 次，实际 {global_callback_results}"
    print("✅ 验证点 1: 全局回调成功执行 3 次")

    # 验证点 2：业务回调执行 3 次（第 2 次失败）
    assert business_callback_results == ["binance_1", "binance_2", "binance_3"], \
        f"期望业务回调执行 3 次，实际 {business_callback_results}"
    print("✅ 验证点 2: 业务回调执行 3 次（第 2 次失败）")

    # 验证点 3：第 2 笔订单在待恢复列表
    pending_orders = gateway.get_pending_recovery_orders()
    assert "binance_2" in pending_orders, \
        "期望 binance_2 在待恢复订单列表中"
    print("✅ 验证点 3: 第 2 笔订单已标记为待恢复")

    print("\n✅ 验证通过: 全局回调成功 + 业务回调失败，订单仍被标记为待恢复")


async def main():
    """运行所有验证场景"""
    print("=" * 70)
    print("P0-WS-Exception-Protection 真实路径验证")
    print("=" * 70)

    try:
        await test_real_watch_orders_path()
        await test_global_callback_success_on_business_failure()

        print("\n" + "=" * 70)
        print("✅ 所有真实路径验证通过！")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
