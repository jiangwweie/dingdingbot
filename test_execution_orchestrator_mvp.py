"""
ExecutionOrchestrator MVP 第一步验证脚本

验证场景：
1. 正常提交流程
2. 被 CapitalProtection 拦截
3. 提交交易所失败
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
)
from src.application.capital_protection import CapitalProtectionManager
from src.application.order_lifecycle_service import OrderLifecycleService
from src.infrastructure.order_repository import OrderRepository
from src.infrastructure.exchange_gateway import ExchangeGateway


async def test_normal_flow():
    """场景 1: 正常提交流程"""
    print("\n=== 场景 1: 正常提交流程 ===")

    # 创建临时数据库
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    try:
        # 初始化组件
        repository = OrderRepository(db_path)
        await repository.initialize()
        order_lifecycle = OrderLifecycleService(repository)
        await order_lifecycle.start()

        # Mock CapitalProtection（允许通过）
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
        gateway.place_order = AsyncMock(
            return_value=OrderPlacementResult(
                order_id="local_123",
                exchange_order_id="binance_abc123",
                symbol="BTC/USDT:USDT",
                order_type=OrderType.MARKET,
                direction=Direction.LONG,
                side="buy",
                amount=Decimal("0.01"),
                status=OrderStatus.OPEN,
            )
        )

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

        strategy = OrderStrategy(
            id="strategy_001",
            name="test_strategy",
        )

        # 执行信号
        intent = await orchestrator.execute_signal(signal, strategy)

        # 验证结果
        print(f"✅ ExecutionIntent 创建成功:")
        print(f"   ID: {intent.id}")
        print(f"   状态: {intent.status}")
        print(f"   本地订单 ID: {intent.order_id}")
        print(f"   交易所订单 ID: {intent.exchange_order_id}")

        assert intent.status == ExecutionIntentStatus.COMPLETED, \
            f"期望 COMPLETED，实际 {intent.status}"
        assert intent.order_id is not None, "order_id 不应为 None"
        assert intent.exchange_order_id == "binance_abc123", \
            f"期望 binance_abc123，实际 {intent.exchange_order_id}"

        # 验证调用
        capital_protection.pre_order_check.assert_called_once()
        gateway.place_order.assert_called_once()

        print("✅ 场景 1 验证通过: 正常提交流程")

    finally:
        os.unlink(db_path)


async def test_blocked_by_capital_protection():
    """场景 2: 被 CapitalProtection 拦截"""
    print("\n=== 场景 2: 被 CapitalProtection 拦截 ===")

    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    try:
        repository = OrderRepository(db_path)
        await repository.initialize()
        order_lifecycle = OrderLifecycleService(repository)
        await order_lifecycle.start()

        # Mock CapitalProtection（拦截）
        capital_protection = MagicMock(spec=CapitalProtectionManager)
        capital_protection.pre_order_check = AsyncMock(
            return_value=OrderCheckResult(
                allowed=False,
                reason="DAILY_LOSS_LIMIT",
                reason_message="每日亏损超限：当日已亏损 500 USDT",
            )
        )

        gateway = MagicMock(spec=ExchangeGateway)

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

        strategy = OrderStrategy(id="strategy_002", name="test_strategy")

        # 执行信号
        intent = await orchestrator.execute_signal(signal, strategy)

        # 验证结果
        print(f"✅ ExecutionIntent 状态:")
        print(f"   ID: {intent.id}")
        print(f"   状态: {intent.status}")
        print(f"   拦截原因: {intent.blocked_reason}")
        print(f"   拦截描述: {intent.blocked_message}")

        assert intent.status == ExecutionIntentStatus.BLOCKED, \
            f"期望 BLOCKED，实际 {intent.status}"
        assert intent.blocked_reason == "DAILY_LOSS_LIMIT", \
            f"期望 DAILY_LOSS_LIMIT，实际 {intent.blocked_reason}"
        assert intent.order_id is None, "被拦截时不应创建订单"

        # 验证未调用交易所
        gateway.place_order.assert_not_called()

        print("✅ 场景 2 验证通过: 被 CapitalProtection 拦截")

    finally:
        os.unlink(db_path)


async def test_exchange_submission_failed():
    """场景 3: 提交交易所失败"""
    print("\n=== 场景 3: 提交交易所失败 ===")

    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    try:
        repository = OrderRepository(db_path)
        await repository.initialize()
        order_lifecycle = OrderLifecycleService(repository)
        await order_lifecycle.start()

        # Mock CapitalProtection（允许通过）
        capital_protection = MagicMock(spec=CapitalProtectionManager)
        capital_protection.pre_order_check = AsyncMock(
            return_value=OrderCheckResult(
                allowed=True,
                reason=None,
                reason_message="所有检查通过",
            )
        )

        # Mock ExchangeGateway（抛出异常）
        gateway = MagicMock(spec=ExchangeGateway)
        gateway.place_order = AsyncMock(
            side_effect=Exception("Insufficient margin")
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

        strategy = OrderStrategy(id="strategy_003", name="test_strategy")

        # 执行信号
        intent = await orchestrator.execute_signal(signal, strategy)

        # 验证结果
        print(f"✅ ExecutionIntent 状态:")
        print(f"   ID: {intent.id}")
        print(f"   状态: {intent.status}")
        print(f"   本地订单 ID: {intent.order_id}")
        print(f"   失败原因: {intent.failed_reason}")

        assert intent.status == ExecutionIntentStatus.FAILED, \
            f"期望 FAILED，实际 {intent.status}"
        assert intent.order_id is not None, "本地订单应已创建"
        assert "Insufficient margin" in intent.failed_reason, \
            f"期望包含 'Insufficient margin'，实际 {intent.failed_reason}"

        print("✅ 场景 3 验证通过: 提交交易所失败")

    finally:
        os.unlink(db_path)


async def main():
    """运行所有验证场景"""
    print("=" * 70)
    print("ExecutionOrchestrator MVP 第一步验证")
    print("=" * 70)

    try:
        await test_normal_flow()
        await test_blocked_by_capital_protection()
        await test_exchange_submission_failed()

        print("\n" + "=" * 70)
        print("✅ 所有验证场景通过！")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
