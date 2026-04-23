#!/usr/bin/env python3
"""
P0-7: Execution Recovery Management Script

最小运维脚本，用于管理 pending_recovery 和 circuit_breaker。

使用方式：
    python scripts/manage_execution_recovery.py list-pending
    python scripts/manage_execution_recovery.py list-breakers
    python scripts/manage_execution_recovery.py clear-pending --order-id <order_id>
    python scripts/manage_execution_recovery.py clear-breaker --symbol <symbol>

注意：
    此脚本必须在 main.py 嵌入模式下运行（即通过 main.py 调用），
    因为需要访问 main.py 中的全局 _execution_orchestrator 对象。
"""
import argparse
import sys
from typing import Optional


def main():
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

    # list-breakers
    subparsers.add_parser(
        "list-breakers",
        help="List all circuit breaker symbols"
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

    # clear-breaker
    clear_breaker_parser = subparsers.add_parser(
        "clear-breaker",
        help="Clear circuit breaker by symbol"
    )
    clear_breaker_parser.add_argument(
        "--symbol",
        required=True,
        help="Symbol to clear (e.g., BTC/USDT:USDT)"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # 导入全局 orchestrator
    try:
        from src.main import _execution_orchestrator
    except ImportError:
        print("Error: Cannot import _execution_orchestrator from src.main")
        print("This script must run inside embedded main process context")
        sys.exit(1)

    if _execution_orchestrator is None:
        print("Error: ExecutionOrchestrator not initialized")
        print("This script must run inside embedded main process context")
        sys.exit(1)

    # 执行命令
    if args.command == "list-pending":
        list_pending(_execution_orchestrator)
    elif args.command == "list-breakers":
        list_breakers(_execution_orchestrator)
    elif args.command == "clear-pending":
        clear_pending(_execution_orchestrator, args.order_id)
    elif args.command == "clear-breaker":
        clear_breaker(_execution_orchestrator, args.symbol)
    else:
        print(f"Error: Unknown command: {args.command}")
        sys.exit(1)


def list_pending(orchestrator):
    """列出所有 pending_recovery 记录"""
    records = orchestrator.list_pending_recovery()

    if not records:
        print("No pending recovery records")
        return

    print(f"Total: {len(records)} pending recovery record(s)\n")
    for i, record in enumerate(records, 1):
        print(f"[{i}] order_id: {record['order_id']}")
        print(f"    exchange_order_id: {record.get('exchange_order_id', 'N/A')}")
        print(f"    symbol: {record.get('symbol', 'N/A')}")
        print(f"    error: {record.get('error', 'N/A')}")
        print()


def list_breakers(orchestrator):
    """列出所有熔断的 symbol"""
    symbols = orchestrator.list_circuit_breaker_symbols()

    if not symbols:
        print("No circuit breaker symbols")
        return

    print(f"Total: {len(symbols)} circuit breaker symbol(s)\n")
    for i, symbol in enumerate(symbols, 1):
        print(f"[{i}] {symbol}")


def clear_pending(orchestrator, order_id: str):
    """清除指定的 pending_recovery 记录"""
    # 检查是否存在
    existing = orchestrator.get_pending_recovery(order_id)
    if existing is None:
        print(f"Error: Pending recovery not found: {order_id}")
        sys.exit(1)

    # 清除
    orchestrator.clear_pending_recovery(order_id)
    print(f"✓ Pending recovery cleared: {order_id}")


def clear_breaker(orchestrator, symbol: str):
    """清除指定 symbol 的熔断状态"""
    # 检查是否存在
    if not orchestrator.is_symbol_blocked(symbol):
        print(f"Error: Symbol not in circuit breaker: {symbol}")
        sys.exit(1)

    # 清除
    orchestrator.clear_circuit_breaker(symbol)
    print(f"✓ Circuit breaker cleared: {symbol}")


if __name__ == "__main__":
    main()
