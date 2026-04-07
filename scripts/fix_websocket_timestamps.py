#!/usr/bin/env python3
"""
数据修复脚本：修复WebSocket信号的错误kline_timestamp

问题：WebSocket信号记录的kline_timestamp是下一根K线的开盘时间
修复：向前调整一个周期（15m = 15分钟，1h = 1小时等）

使用方法：
    python scripts/fix_websocket_timestamps.py --dry-run  # 预览修复
    python scripts/fix_websocket_timestamps.py --execute  # 执行修复
"""

import asyncio
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infrastructure.signal_repository import SignalRepository
from src.infrastructure.logger import logger


async def fix_websocket_timestamps(dry_run: bool = True):
    """
    修复WebSocket信号的kline_timestamp

    Args:
        dry_run: True=仅预览，False=执行修复
    """
    repo = SignalRepository(db_path="data/signals-prod.db")

    try:
        await repo.initialize()

        # 查询所有WebSocket信号（source='live'）
        signals = await repo.get_signals(source='live', limit=10000)

        print(f"\n=== 找到 {len(signals)} 条WebSocket信号 ===\n")

        if not signals:
            print("没有WebSocket信号需要修复")
            return

        # 时间周期映射（毫秒）
        timeframe_map = {
            "1m": 1 * 60 * 1000,
            "5m": 5 * 60 * 1000,
            "15m": 15 * 60 * 1000,
            "30m": 30 * 60 * 1000,
            "1h": 60 * 60 * 1000,
            "4h": 4 * 60 * 60 * 1000,
            "1d": 24 * 60 * 60 * 1000,
        }

        fixed_count = 0
        preview_data = []

        for signal in signals:
            signal_id = signal['id']
            kline_ts = signal.get('kline_timestamp')
            timeframe = signal['timeframe']

            if not kline_ts or kline_ts == 0:
                continue

            # 计算正确的时间戳
            timeframe_ms = timeframe_map.get(timeframe, 60 * 60 * 1000)
            correct_ts = kline_ts - timeframe_ms

            # 时间转换（用于显示）
            old_time = datetime.utcfromtimestamp(kline_ts / 1000)
            new_time = datetime.utcfromtimestamp(correct_ts / 1000)

            preview_data.append({
                'id': signal_id,
                'symbol': signal['symbol'],
                'timeframe': timeframe,
                'old_ts': kline_ts,
                'new_ts': correct_ts,
                'old_time': old_time.strftime('%Y-%m-%d %H:%M:%S UTC'),
                'new_time': new_time.strftime('%Y-%m-%d %H:%M:%S UTC'),
            })

            if not dry_run:
                # 执行修复
                await repo.update_signal_timestamp(signal_id, correct_ts)
                fixed_count += 1

        # 显示预览
        print("前10条预览：\n")
        print(f"{'ID':<6} {'Symbol':<20} {'TF':<6} {'旧时间戳':<20} {'新时间戳':<20} {'时间差'}")
        print("-" * 100)

        for item in preview_data[:10]:
            diff = (item['old_ts'] - item['new_ts']) / 60000  # 分钟
            print(f"{item['id']:<6} {item['symbol']:<20} {item['timeframe']:<6} "
                  f"{item['old_time']:<20} {item['new_time']:<20} {diff}分钟")

        if len(preview_data) > 10:
            print(f"\n... 还有 {len(preview_data) - 10} 条记录未显示")

        print("\n" + "=" * 100)

        if dry_run:
            print(f"✅ 预览完成，共 {len(preview_data)} 条记录需要修复")
            print("\n执行修复请运行:")
            print("  python scripts/fix_websocket_timestamps.py --execute")
        else:
            print(f"✅ 修复完成！共修复 {fixed_count} 条记录")

    finally:
        await repo.close()


async def main():
    parser = argparse.ArgumentParser(description='修复WebSocket信号的时间戳')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不执行修复')
    parser.add_argument('--execute', action='store_true', help='执行修复')

    args = parser.parse_args()

    if args.execute:
        print("⚠️  即将执行数据修复...")
        await fix_websocket_timestamps(dry_run=False)
    else:
        print("🔍 预览模式（dry-run）...")
        await fix_websocket_timestamps(dry_run=True)


if __name__ == "__main__":
    asyncio.run(main())