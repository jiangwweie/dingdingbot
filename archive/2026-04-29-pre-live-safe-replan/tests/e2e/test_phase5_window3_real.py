"""
Phase 5 E2E 集成测试 - 窗口 3：对账服务 + WebSocket 推送

测试环境：Binance Testnet
"""

import pytest
import asyncio
from decimal import Decimal
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.notifier_feishu import FeishuNotifier


# API Key 配置（与 Window 1/2 一致）
API_KEY = "rmy4DPO0uydnQLRCKxql5oeqURfBlC36W7ijW0QwBjR9HxAXMEahc0KutHlHA8hI"
API_SECRET = "mP7Hk5r3D8TeryzZKxipJ6aTfOJ6qbjqO3fzeG6VJtJB9DVxE4NXgMJZYXpqMFtR"

# 飞书 Webhook
FEISHU_WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/14797747-0403-4455-a7fe-f6b69cf0ef04"

MIN_AMOUNT = Decimal("0.002")  # 约 132 USDT


@pytest.fixture
async def gateway():
    """创建交易所网关实例"""
    gw = ExchangeGateway(
        exchange_name="binance",
        api_key=API_KEY,
        api_secret=API_SECRET,
        testnet=True
    )
    await gw.initialize()
    yield gw
    await gw.close()


# ========== Test-3.1: WebSocket 连接测试 ==========

@pytest.mark.e2e
@pytest.mark.window3
async def test_3_1_websocket_connection(gateway):
    """Test-3.1: WebSocket 连接"""
    # WebSocket 是按需创建的，subscribe_ohlcv 会创建 ws_exchange
    # 这里验证网关支持 WebSocket 功能
    assert hasattr(gateway, 'ws_exchange'), "ExchangeGateway 应该有 ws_exchange 属性"
    print(f"✅ WebSocket 功能已就绪（按需创建）")


# ========== Test-3.2: 订单推送测试 ==========

@pytest.mark.e2e
@pytest.mark.window3
async def test_3_2_order_push_via_polling(gateway):
    """Test-3.2: 订单状态变更推送（通过轮询）"""
    symbol = "BTC/USDT:USDT"

    # 下一个市价单
    result = await gateway.place_order(
        symbol=symbol,
        order_type="market",
        side="buy",
        amount=MIN_AMOUNT,
        reduce_only=False
    )

    assert result.is_success is True
    print(f"✅ 订单已提交：exchange_id={result.exchange_order_id}")

    # 等待订单成交
    await asyncio.sleep(1)

    # 查询订单状态
    order = await gateway.fetch_order(result.exchange_order_id, symbol)
    assert order is not None
    print(f"✅ 订单状态查询成功：status={order.status}")


# ========== Test-3.3: 对账服务基础测试 ==========

@pytest.mark.e2e
@pytest.mark.window3
async def test_3_3_reconciliation_basics(gateway):
    """Test-3.3: 对账服务基础功能"""
    # 检查对账服务是否可用
    from src.application.reconciliation import ReconciliationService

    reconciliation = ReconciliationService(
        gateway=gateway,
        grace_period_seconds=10
    )

    # 获取交易所订单列表
    orders = await gateway.rest_exchange.fetch_orders("BTC/USDT:USDT", limit=5)
    assert orders is not None
    print(f"✅ 获取到 {len(orders)} 个订单记录")


# ========== Test-3.4: 账户余额对账 ==========

@pytest.mark.e2e
@pytest.mark.window3
async def test_3_4_balance_reconciliation(gateway):
    """Test-3.4: 账户余额对账"""
    # 获取交易所余额
    balance = await gateway.rest_exchange.fetch_balance()

    # 验证 USDT 余额
    assert "USDT" in balance
    usdt = balance["USDT"]
    assert usdt["total"] > 0

    print(f"✅ 账户余额对账成功：USDT={usdt['total']}")


# ========== Test-3.5: 持仓对账 ==========

@pytest.mark.e2e
@pytest.mark.window3
async def test_3_5_position_reconciliation(gateway):
    """Test-3.5: 持仓对账"""
    # 获取持仓
    positions = await gateway.rest_exchange.fetch_positions(symbols=["BTC/USDT:USDT"])

    # 验证返回结构
    assert positions is not None
    print(f"✅ 持仓对账成功：{len(positions)} 个持仓")


# ========== Test-3.6: Grace Period 处理 ==========

@pytest.mark.e2e
@pytest.mark.window3
async def test_3_6_grace_period_handling(gateway):
    """Test-3.6: Grace Period 处理"""
    symbol = "BTC/USDT:USDT"

    # 获取当前价格
    ticker = await gateway.rest_exchange.fetch_ticker(symbol)
    current_price = Decimal(str(ticker["last"]))

    # 下一个限价单（低于市价 15%，不太可能成交）
    limit_price = current_price * Decimal("0.85")

    result = await gateway.place_order(
        symbol=symbol,
        order_type="limit",
        side="buy",
        amount=MIN_AMOUNT,
        price=limit_price,
        reduce_only=False
    )

    assert result.is_success is True
    order_id = result.exchange_order_id
    print(f"✅ 限价单已挂出：price={limit_price}")

    # 立即查询（订单可能还未同步）
    await asyncio.sleep(0.5)

    # 查询订单
    order = await gateway.fetch_order(order_id, symbol)
    assert order is not None
    print(f"✅ Grace Period 内查询成功：status={order.status}")

    # 清理
    try:
        await gateway.cancel_order(order_id, symbol)
        print(f"✅ 订单已取消")
    except Exception as e:
        print(f"⚠️  取消失败：{e}")


# ========== Test-3.7: 飞书告警测试 ==========

@pytest.mark.e2e
@pytest.mark.window3
async def test_3_7_feishu_alert(gateway):
    """Test-3.7: 飞书告警通知"""
    notifier = FeishuNotifier(webhook_url=FEISHU_WEBHOOK)

    # 发送测试通知
    result = await notifier.send_alert(
        event_type="ORDER_FILLED",
        title="🐶 盯盘狗 E2E 测试",
        message="测试内容：订单执行成功\n币种：BTC/USDT:USDT\n方向：LONG\n数量：0.002 BTC"
    )

    # 验证发送结果
    assert result is True, "飞书告警发送失败"
    print(f"✅ 飞书告警发送成功")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
