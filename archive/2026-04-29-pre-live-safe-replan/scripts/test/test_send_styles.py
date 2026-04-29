#!/usr/bin/env python3
"""
Test script to send Feishu notifications with style C and D.

Usage:
    python3 scripts/test_send_styles.py
"""
import json
import sqlite3
from decimal import Decimal
from typing import Optional, Dict, Any

import sys
sys.path.insert(0, '/Users/jiangwei/Documents/dingdingbot')

from src.domain.models import SignalResult, Direction
from src.infrastructure.notifier import (
    format_signal_message_style_c,
    format_signal_message_style_d,
    NotificationService,
    FeishuWebhook,
)


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
        print("未找到 PENDING 信号")
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
    tags = json.loads(signal_dict.get('tags_json', '[]'))
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


def get_webhook_url() -> Optional[str]:
    """Read Feishu webhook URL from config."""
    import yaml
    with open('config/user.yaml', 'r') as f:
        config = yaml.safe_load(f)

    for channel in config.get('notification', {}).get('channels', []):
        if channel.get('type') == 'feishu':
            return channel.get('webhook_url')

    return None


async def send_styles(signal: SignalResult, webhook_url: str):
    """Send both style C and D notifications."""
    # Style C
    print("\n发送样式 C...")
    service = NotificationService()
    service.add_channel(FeishuWebhook(webhook_url))
    message_c = format_signal_message_style_c(signal)
    await service._broadcast(message_c)
    await service.close()
    print("样式 C 已发送")

    # Style D
    print("发送样式 D...")
    service = NotificationService()
    service.add_channel(FeishuWebhook(webhook_url))
    message_d = format_signal_message_style_d(signal)
    await service._broadcast(message_d)
    await service.close()
    print("样式 D 已发送")


def main():
    print("=" * 60)
    print("读取数据库中最新的 PENDING 信号...")
    print("=" * 60)

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

    signal = build_signal_result(signal_dict)

    # Show preview
    print("=" * 60)
    print("样式 C 预览:")
    print("=" * 60)
    print(format_signal_message_style_c(signal))

    print("=" * 60)
    print("样式 D 预览:")
    print("=" * 60)
    print(format_signal_message_style_d(signal))
    print("=" * 60)

    # Get webhook
    webhook_url = get_webhook_url()
    if not webhook_url:
        print("错误：未找到飞书 webhook URL")
        return

    print(f"\n飞书 webhook: {webhook_url[:30]}...")

    import asyncio
    asyncio.run(send_styles(signal, webhook_url))

    print()
    print("=" * 60)
    print("发送完成！请在飞书中查看两种风格的效果")
    print("=" * 60)


if __name__ == '__main__':
    main()
