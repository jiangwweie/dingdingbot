"""
PG-1: 最小 PG 连通性验证（验证 ExecutionIntent 走 PG 真源）

验证目标：
1. PgExecutionIntentRepository.initialize() 执行成功（PG core 表创建/可用）
2. save() 写入 ExecutionIntent 到 PG
3. get() / get_by_order_id() 从 PG 读回并验证字段一致

运行方式：
export PG_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/dbname
export CORE_EXECUTION_INTENT_BACKEND=postgres
export CORE_ORDER_BACKEND=sqlite
python scripts/verify_pg_execution_intent_ssot.py
"""
import asyncio
import os
from decimal import Decimal
from datetime import datetime, timezone

from src.domain.models import SignalResult, OrderStrategy, Direction
from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.infrastructure.pg_execution_intent_repository import PgExecutionIntentRepository


async def verify_pg_ssot():
    """验证 PG 作为 ExecutionIntent 的 SSOT"""

    print("=" * 70)
    print("PG-1: 验证 ExecutionIntent 走 PG 真源")
    print("=" * 70)

    # 检查环境变量
    pg_url = os.environ.get("PG_DATABASE_URL")
    intent_backend = os.environ.get("CORE_EXECUTION_INTENT_BACKEND")

    print(f"\n环境变量检查:")
    print(f"  PG_DATABASE_URL: {'✅ 已设置' if pg_url else '❌ 未设置'}")
    print(f"  CORE_EXECUTION_INTENT_BACKEND: {intent_backend or '❌ 未设置'}")

    if not pg_url:
        print("\n❌ 错误: PG_DATABASE_URL 未设置")
        return

    if intent_backend != "postgres":
        print(f"\n⚠️  警告: CORE_EXECUTION_INTENT_BACKEND={intent_backend} (预期: postgres)")

    # 初始化 repository
    print("\n步骤 1: 初始化 PgExecutionIntentRepository...")
    repo = PgExecutionIntentRepository()
    await repo.initialize()
    print("✅ PgExecutionIntentRepository.initialize() 成功")

    # 构造测试数据
    print("\n步骤 2: 构造测试 ExecutionIntent...")
    signal = SignalResult(
        symbol="BTC/USDT:USDT",
        timeframe="15m",
        direction=Direction.LONG,
        entry_price=Decimal("50000"),
        suggested_stop_loss=Decimal("48000"),
        suggested_position_size=Decimal("0.1"),
        current_leverage=1,
        tags=[{"name": "EMA", "value": "Bullish"}],
        risk_reward_info="1R",
        strategy_name="test_strategy",
        score=0.85,
    )

    strategy = OrderStrategy(
        id="test_strategy_001",
        name="Test Strategy",
        tp_levels=2,
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.0"), Decimal("2.0")],
        initial_stop_loss_rr=Decimal("-1.0"),
    )

    intent_id = "intent_pg_test_001"
    order_id = "order_pg_test_001"

    intent = ExecutionIntent(
        id=intent_id,
        signal_id="signal_pg_test_001",
        signal=signal,
        status=ExecutionIntentStatus.SUBMITTED,
        strategy=strategy,
        order_id=order_id,
        exchange_order_id="ex_order_pg_test_001",
    )

    print(f"  intent_id: {intent_id}")
    print(f"  order_id: {order_id}")
    print(f"  status: {intent.status}")
    print(f"  signal.symbol: {signal.symbol}")
    print(f"  strategy.id: {strategy.id}")

    # 写入 PG
    print("\n步骤 3: 写入 ExecutionIntent 到 PG...")
    await repo.save(intent)
    print("✅ save() 成功")

    # 通过 intent_id 读回
    print("\n步骤 4: 通过 get(intent_id) 读回...")
    loaded_intent = await repo.get(intent_id)

    if not loaded_intent:
        print(f"❌ 错误: get({intent_id}) 返回 None")
        return

    print("✅ get() 成功")
    print(f"  loaded_intent.id: {loaded_intent.id}")
    print(f"  loaded_intent.status: {loaded_intent.status}")
    print(f"  loaded_intent.signal.symbol: {loaded_intent.signal.symbol}")
    print(f"  loaded_intent.strategy.id: {loaded_intent.strategy.id if loaded_intent.strategy else 'None'}")

    # 验证字段
    print("\n步骤 5: 验证字段一致性...")
    assert loaded_intent.id == intent_id, f"id 不匹配: {loaded_intent.id} != {intent_id}"
    assert loaded_intent.status == ExecutionIntentStatus.SUBMITTED, f"status 不匹配: {loaded_intent.status}"
    assert loaded_intent.signal.symbol == signal.symbol, f"signal.symbol 不匹配"
    assert loaded_intent.signal.entry_price == signal.entry_price, f"signal.entry_price 不匹配"
    assert loaded_intent.strategy is not None, "strategy 为 None"
    assert loaded_intent.strategy.id == strategy.id, f"strategy.id 不匹配"
    print("✅ 所有字段验证通过")

    # 通过 order_id 读回
    print("\n步骤 6: 通过 get_by_order_id(order_id) 读回...")
    loaded_by_order = await repo.get_by_order_id(order_id)

    if not loaded_by_order:
        print(f"❌ 错误: get_by_order_id({order_id}) 返回 None")
        return

    print("✅ get_by_order_id() 成功")
    assert loaded_by_order.id == intent_id, f"get_by_order_id 返回的 id 不匹配"
    print("✅ get_by_order_id 验证通过")

    # 清理测试数据
    print("\n步骤 7: 清理测试数据...")
    # 注意：这里不删除，保留数据供人工检查
    print("⚠️  测试数据已保留在 PG 中，可手动检查")

    # 关闭连接
    await repo.close()

    print("\n" + "=" * 70)
    print("✅ PG-1 验证完成：ExecutionIntent 成功走 PG 真源")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(verify_pg_ssot())
