#!/usr/bin/env python3
"""
Sim-0.3.1 受控 K 线触发验证脚本

目标：
- 构造一根满足 pinbar 策略条件的 BTC 15m K 线
- 送入 SignalPipeline
- 验证完整链路到 testnet ENTRY

安全约束：
- 只用于 Sim-0 验证
- 只使用 BTC/USDT:USDT
- 只在 testnet 环境
"""
import asyncio
import sys
import os
from datetime import datetime, timezone
from decimal import Decimal

# 添加项目路径
sys.path.insert(0, '/Users/jiangwei/Documents/final')

# 加载环境变量
from dotenv import load_dotenv
load_dotenv('/Users/jiangwei/Documents/final/.env')

from src.domain.models import KlineData
from src.application.signal_pipeline import SignalPipeline
from src.application.config_manager import load_all_configs
from src.application.capital_protection import CapitalProtectionManager
from src.application.execution_orchestrator import ExecutionOrchestrator
from src.application.order_lifecycle_service import OrderLifecycleService
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.core_repository_factory import (
    create_execution_intent_repository,
    create_order_repository,
)
from src.infrastructure.logger import logger


def create_pinbar_kline() -> KlineData:
    """
    构造一根满足 pinbar 策略条件的 K 线

    Pinbar 条件（看涨）：
    - 长下影线（至少占 K 线高度的 60%）
    - 实体在顶部（上影线短）
    - 收盘价接近最高价

    当前 BTC 价格约 60000-70000 USDT
    """
    now = datetime.now(timezone.utc)
    timestamp = int(now.timestamp() * 1000)

    # 构造看涨 pinbar
    # 假设当前价格约 65000 USDT
    high = Decimal("65000")
    low = Decimal("63000")  # 长下影线
    open_price = Decimal("64800")  # 开盘价接近最高价
    close = Decimal("64900")  # 收盘价接近最高价

    kline = KlineData(
        symbol="BTC/USDT:USDT",
        timeframe="15m",
        timestamp=timestamp,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=Decimal("1000"),
        is_closed=True,  # 关键：K 线已闭合
    )

    return kline


async def main():
    """主验证流程"""
    print("=" * 70)
    print("Sim-0.3.1 受控 K 线触发验证")
    print("=" * 70)
    print()

    # 1. 检查环境配置
    print("步骤 1: 检查环境配置")
    testnet = os.getenv("EXCHANGE_TESTNET")
    exec_backend = os.getenv("CORE_EXECUTION_INTENT_BACKEND")
    order_backend = os.getenv("CORE_ORDER_BACKEND")

    print(f"  EXCHANGE_TESTNET: {testnet}")
    print(f"  CORE_EXECUTION_INTENT_BACKEND: {exec_backend}")
    print(f"  CORE_ORDER_BACKEND: {order_backend}")

    if testnet != "true":
        print("❌ 错误：EXCHANGE_TESTNET 不是 true，拒绝执行")
        return

    print("✅ 环境配置正确")
    print()

    # 2. 加载配置
    print("步骤 2: 加载配置")
    config_manager = load_all_configs()
    print("✅ 配置加载成功")
    print()

    # 3. 构造 K 线
    print("步骤 3: 构造满足 pinbar 条件的 K 线")
    kline = create_pinbar_kline()

    print(f"  symbol: {kline.symbol}")
    print(f"  timeframe: {kline.timeframe}")
    print(f"  timestamp: {kline.timestamp}")
    print(f"  open: {kline.open}")
    print(f"  high: {kline.high}")
    print(f"  low: {kline.low}")
    print(f"  close: {kline.close}")
    print(f"  volume: {kline.volume}")
    print(f"  is_closed: {kline.is_closed}")

    # 计算 pinbar 特征
    body = abs(kline.close - kline.open)
    lower_wick = min(kline.open, kline.close) - kline.low
    upper_wick = kline.high - max(kline.open, kline.close)
    total_range = kline.high - kline.low

    print(f"\n  Pinbar 特征:")
    print(f"    实体: {body}")
    print(f"    下影线: {lower_wick}")
    print(f"    上影线: {upper_wick}")
    print(f"    总高度: {total_range}")
    print(f"    下影线占比: {float(lower_wick / total_range) * 100:.1f}%")
    print(f"    实体占比: {float(body / total_range) * 100:.1f}%")

    print("✅ K 线构造完成")
    print()

    # 4. 初始化组件
    print("步骤 4: 初始化组件")

    # ExchangeGateway
    user_config = await config_manager.get_user_config()
    exchange_cfg = user_config.exchange
    gateway = ExchangeGateway(
        exchange_name=exchange_cfg.name,
        api_key=exchange_cfg.api_key,
        api_secret=exchange_cfg.api_secret,
        testnet=exchange_cfg.testnet,
    )
    await gateway.initialize()
    print("  ✅ ExchangeGateway 初始化成功")

    # OrderRepository
    order_repo = create_order_repository()
    await order_repo.initialize()
    print("  ✅ OrderRepository 初始化成功")

    # ExecutionIntentRepository
    intent_repo = create_execution_intent_repository()
    if intent_repo:
        await intent_repo.initialize()
        print("  ✅ ExecutionIntentRepository 初始化成功")

    # OrderLifecycleService
    order_lifecycle = OrderLifecycleService(repository=order_repo)
    await order_lifecycle.start()
    print("  ✅ OrderLifecycleService 初始化成功")

    # CapitalProtectionManager
    capital_protection = CapitalProtectionManager(
        config=config_manager.build_capital_protection_config(),
        account_service=None,  # 简化，不验证账户
        gateway=gateway,
    )
    print("  ✅ CapitalProtectionManager 初始化成功")

    # ExecutionOrchestrator
    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
        intent_repository=intent_repo,
    )
    print("  ✅ ExecutionOrchestrator 初始化成功")

    # SignalPipeline
    pipeline = SignalPipeline(
        config_manager=config_manager,
        risk_config=config_manager.build_capital_protection_config(),
        notification_service=None,  # 简化，不发送通知
        signal_repository=None,  # 简化，不保存信号
        orchestrator=orchestrator,
    )
    print("  ✅ SignalPipeline 初始化成功")

    print()

    # 5. 触发 K 线处理
    print("步骤 5: 触发 K 线处理")
    print(f"  调用 SignalPipeline.process_kline()...")

    try:
        await pipeline.process_kline(kline)
        print("  ✅ K 线处理完成")
    except Exception as e:
        print(f"  ❌ K 线处理失败: {e}")
        import traceback
        traceback.print_exc()

    print()

    # 6. 检查结果
    print("步骤 6: 检查结果")

    # 检查 ExecutionIntent
    intents = orchestrator._intents
    print(f"  ExecutionIntent 数量: {len(intents)}")

    if intents:
        for intent_id, intent in intents.items():
            print(f"\n  ✅ ExecutionIntent 创建成功:")
            print(f"    intent_id: {intent_id}")
            print(f"    status: {intent.status}")
            print(f"    signal.symbol: {intent.signal.symbol if intent.signal else 'N/A'}")
            print(f"    signal.direction: {intent.signal.direction if intent.signal else 'N/A'}")
            print(f"    signal.entry_price: {intent.signal.entry_price if intent.signal else 'N/A'}")
            print(f"    order_id: {intent.order_id if intent.order_id else 'N/A'}")
    else:
        print("  ⚠️ 未创建 ExecutionIntent（可能策略条件未满足或过滤器未通过）")

    print()

    # 清理
    print("步骤 7: 清理资源")
    await gateway.close()
    await order_lifecycle.stop()
    if intent_repo:
        await intent_repo.close()
    print("  ✅ 资源清理完成")

    print()
    print("=" * 70)
    print("验证完成")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
