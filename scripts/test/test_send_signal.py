#!/usr/bin/env python3
"""
Test script to send Feishu notification from database signal.

Usage:
    python3 scripts/test_send_signal.py
"""
import asyncio
import json
import sqlite3
from decimal import Decimal
from typing import Optional, List, Dict, Any

# Add parent directory to path
import sys
sys.path.insert(0, '/Users/jiangwei/Documents/dingdingbot')

from src.domain.models import SignalResult, Direction
from src.infrastructure.notifier import NotificationService, FeishuWebhook, format_signal_message


def get_latest_signal() -> Optional[Dict[str, Any]]:
    """Get latest PENDING signal from database."""
    conn = sqlite3.connect('data/signals.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT * FROM signals
        WHERE status = 'PENDING'
        ORDER BY created_at DESC
        LIMIT 1
    ''')
    row = cursor.fetchone()

    if not row:
        print("No PENDING signals found")
        conn.close()
        return None

    signal_dict = dict(row)

    # Fetch take profit levels
    cursor.execute('''
        SELECT tp_id, price_level, position_ratio, risk_reward, status
        FROM signal_take_profits
        WHERE signal_id = ?
        ORDER BY tp_id
    ''', (row['id'],))
    tp_rows = cursor.fetchall()

    signal_dict['take_profit_levels'] = [
        {
            'tp_id': tp['tp_id'],
            'price_level': tp['price_level'],
            'position_ratio': tp['position_ratio'],
            'risk_reward': tp['risk_reward'],
            'status': tp['status'],
        }
        for tp in tp_rows
    ]

    conn.close()
    return signal_dict


def build_signal_result(signal_dict: Dict[str, Any]) -> SignalResult:
    """Convert database row to SignalResult object."""
    # Parse tags from JSON
    tags = json.loads(signal_dict.get('tags_json', '[]'))

    # Build take_profit_levels
    take_profit_levels = signal_dict.get('take_profit_levels', [])

    return SignalResult(
        symbol=signal_dict['symbol'],
        timeframe=signal_dict['timeframe'],
        direction=Direction(signal_dict['direction']),
        entry_price=Decimal(signal_dict['entry_price']),
        suggested_stop_loss=Decimal(signal_dict['stop_loss']),
        suggested_position_size=Decimal(signal_dict['position_size']),
        current_leverage=signal_dict['leverage'],
        tags=tags,
        risk_reward_info=signal_dict.get('risk_info', ''),
        strategy_name=signal_dict.get('strategy_name', ''),
        score=signal_dict.get('score', 0.0),
        take_profit_levels=take_profit_levels,
    )


async def send_test_signal():
    """Send test signal notification to Feishu."""
    print("=" * 60)
    print("读取数据库中最新的 PENDING 信号...")
    print("=" * 60)

    # Get signal from database
    signal_dict = get_latest_signal()
    if not signal_dict:
        print("错误：未找到信号")
        return

    print(f"信号 ID: {signal_dict['id']}")
    print(f"币种：{signal_dict['symbol']}")
    print(f"周期：{signal_dict['timeframe']}")
    print(f"方向：{signal_dict['direction']}")
    print(f"评分：{signal_dict['score']:.2f}")
    print()

    # Build SignalResult
    signal = build_signal_result(signal_dict)

    # Format message
    message = format_signal_message(signal)

    print("=" * 60)
    print("生成的消息内容:")
    print("=" * 60)
    print(message)
    print("=" * 60)
    print()

    # Read Feishu webhook URL from config
    import yaml
    with open('config/user.yaml', 'r') as f:
        config = yaml.safe_load(f)

    webhook_url = None
    for channel in config.get('notification', {}).get('channels', []):
        if channel.get('type') == 'feishu':
            webhook_url = channel.get('webhook_url')
            break

    if not webhook_url:
        print("错误：未在 config/user.yaml 中找到飞书 webhook URL")
        return

    # Ask for confirmation
    print(f"飞书 webhook: {webhook_url[:30]}...")
    print()
    response = input("是否发送到飞书？(y/n): ").strip().lower()

    if response != 'y':
        print("已取消发送")
        return

    # Send notification
    print()
    print("正在发送到飞书...")

    service = NotificationService()
    service.add_channel(FeishuWebhook(webhook_url))

    await service.send_signal(signal)

    await service.close()

    print()
    print("=" * 60)
    print("发送完成!")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(send_test_signal())
