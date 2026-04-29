#!/usr/bin/env python3
"""
P0-7: Execution Recovery Management Script

最小运维脚本，用于管理 pending_recovery。

使用方式：
    python scripts/manage_execution_recovery.py list-pending
    python scripts/manage_execution_recovery.py clear-pending --order-id <order_id>

注意：
    此脚本直接读取 SQLite 真源（data/pending_recovery.db），
    可以在独立进程下运行，无需依赖 main.py 进程内状态。
"""
import argparse
import sys
import asyncio
import os
from typing import Optional

# 添加项目根目录到 sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)


async def main():
    parser = argparse.ArgumentParser(
        description="Execution Recovery Management Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # list-pending
    subparsers.add_parser(
        "list-pending",
        help="List all pending recovery records"
    )

    # clear-pending
    clear_pending_parser = subparsers.add_parser(
        "clear-pending",
        help="Clear pending recovery record by order_id"
    )
    clear_pending_parser.add_argument(
        "--order-id",
        required=True,
        help="Order ID to clear"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # 初始化 repository
    from src.infrastructure.pending_recovery_repository import PendingRecoveryRepository

    repo = PendingRecoveryRepository()
    try:
        await repo.initialize()

        # 执行命令
        if args.command == "list-pending":
            await list_pending(repo)
        elif args.command == "clear-pending":
            await clear_pending(repo, args.order_id)
        else:
            print(f"Error: Unknown command: {args.command}")
            sys.exit(1)

    finally:
        await repo.close()


async def list_pending(repo):
    """列出所有 pending_recovery 记录"""
    records = await repo.list_all()

    if not records:
        print("No pending recovery records")
        return

    print(f"Total: {len(records)} pending recovery record(s)\n")
    for i, record in enumerate(records, 1):
        print(f"[{i}] order_id: {record['order_id']}")
        print(f"    exchange_order_id: {record.get('exchange_order_id', 'N/A')}")
        print(f"    symbol: {record.get('symbol', 'N/A')}")
        print(f"    error: {record.get('error', 'N/A')}")
        print(f"    created_at: {record.get('created_at', 'N/A')}")
        print()


async def clear_pending(repo, order_id: str):
    """清除指定的 pending_recovery 记录"""
    # 检查是否存在
    existing = await repo.get(order_id)
    if existing is None:
        print(f"Error: Pending recovery not found: {order_id}")
        sys.exit(1)

    # 清除
    await repo.delete(order_id)
    print(f"✓ Pending recovery cleared: {order_id}")


if __name__ == "__main__":
    asyncio.run(main())
