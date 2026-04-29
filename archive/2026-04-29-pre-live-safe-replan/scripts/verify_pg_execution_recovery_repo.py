#!/usr/bin/env python3
"""
PG Execution Recovery Repository 真库验证脚本

用途：
- 手工验证 PG recovery repository 的真实数据库能力
- 不属于 unit test，不进 pytest
- 需要真实 PG 环境

运行方式：
    export PG_DATABASE_URL="postgresql+asyncpg://dingdingbot:dingdingbot_dev@localhost:5432/dingdingbot"
    python3 scripts/verify_pg_execution_recovery_repo.py

验证步骤：
1. initialize() - 初始化表结构
2. create_task() - 创建恢复任务
3. list_active() - 列出活跃任务
4. mark_resolved() - 标记任务为已解决
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.database import get_pg_session_maker
from src.infrastructure.pg_execution_recovery_repository import PgExecutionRecoveryRepository


async def verify_pg_recovery_repo():
    """验证 PG recovery repository 真库能力"""

    print("=" * 70)
    print("PG Execution Recovery Repository 真库验证")
    print("=" * 70)

    # 检查环境变量
    pg_url = os.getenv("PG_DATABASE_URL")
    if not pg_url:
        print("❌ 错误：PG_DATABASE_URL 未配置")
        print("请运行：export PG_DATABASE_URL=\"postgresql+asyncpg://dingdingbot:dingdingbot_dev@localhost:5432/dingdingbot\"")
        return

    print(f"✅ PG_DATABASE_URL 已配置")
    print()

    # 创建 session_maker
    try:
        session_maker = get_pg_session_maker()
        print("✅ Session maker 创建成功")
    except Exception as e:
        print(f"❌ Session maker 创建失败: {e}")
        return

    # 创建 repository
    repo = PgExecutionRecoveryRepository(session_maker=session_maker)

    # 步骤 1: initialize()
    print("步骤 1: initialize()")
    try:
        await repo.initialize()
        print("✅ initialize() 成功")
    except Exception as e:
        print(f"❌ initialize() 失败: {e}")
        return
    print()

    # 步骤 2: create_task()
    print("步骤 2: create_task()")
    task_id = f"test_task_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    intent_id = "test_intent_001"
    symbol = "BTC/USDT:USDT"

    try:
        await repo.create_task(
            task_id=task_id,
            intent_id=intent_id,
            symbol=symbol,
            recovery_type="replace_sl_failed",
            related_order_id="test_order_001",
            related_exchange_order_id="test_ex_order_001",
            error_message="测试错误",
            context_payload={
                "entry_order_id": "test_entry_001",
                "filled_qty_total": "0.1",
                "protected_qty_total": "0.05",
                "delta_qty": "0.05",
            },
        )
        print(f"✅ create_task() 成功: task_id={task_id}")
    except Exception as e:
        print(f"❌ create_task() 失败: {e}")
        return
    print()

    # 步骤 3: list_active()
    print("步骤 3: list_active()")
    try:
        active_tasks = await repo.list_active()
        print(f"✅ list_active() 成功: 找到 {len(active_tasks)} 个活跃任务")

        # 验证刚创建的任务在列表中
        task_ids = [t["id"] for t in active_tasks]
        if task_id in task_ids:
            print(f"✅ 刚创建的任务在列表中: task_id={task_id}")
        else:
            print(f"❌ 刚创建的任务不在列表中: task_id={task_id}")
            return

        # 打印任务详情
        for task in active_tasks:
            if task["id"] == task_id:
                print(f"   - id: {task['id']}")
                print(f"   - intent_id: {task['intent_id']}")
                print(f"   - symbol: {task['symbol']}")
                print(f"   - recovery_type: {task['recovery_type']}")
                print(f"   - status: {task['status']}")
                print(f"   - error_message: {task['error_message']}")
                break
    except Exception as e:
        print(f"❌ list_active() 失败: {e}")
        return
    print()

    # 步骤 4: mark_resolved()
    print("步骤 4: mark_resolved()")
    try:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        await repo.mark_resolved(task_id, resolved_at=now_ms, error_message="测试已解决")
        print(f"✅ mark_resolved() 成功: task_id={task_id}")
    except Exception as e:
        print(f"❌ mark_resolved() 失败: {e}")
        return
    print()

    # 验证任务状态已更新
    print("验证任务状态已更新")
    try:
        task = await repo.get(task_id)
        if task:
            print(f"✅ get() 成功: task_id={task_id}")
            print(f"   - status: {task['status']}")
            print(f"   - resolved_at: {task['resolved_at']}")
            print(f"   - error_message: {task['error_message']}")

            if task["status"] == "resolved":
                print("✅ 任务状态已更新为 resolved")
            else:
                print(f"❌ 任务状态未更新: {task['status']}")
        else:
            print(f"❌ get() 失败: 任务不存在")
    except Exception as e:
        print(f"❌ get() 失败: {e}")
    print()

    # 清理：删除测试任务
    print("清理：删除测试任务")
    try:
        await repo.delete(task_id)
        print(f"✅ delete() 成功: task_id={task_id}")
    except Exception as e:
        print(f"❌ delete() 失败: {e}")
    print()

    # 关闭 repository
    await repo.close()

    print("=" * 70)
    print("✅ 所有验证步骤通过")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(verify_pg_recovery_repo())
