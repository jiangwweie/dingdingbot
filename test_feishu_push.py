#!/usr/bin/env python3
"""
从数据库读取一条信号数据，模拟推送到飞书
"""
import asyncio
import sqlite3
import sys
import os
from decimal import Decimal

# Add project root to path
sys.path.insert(0, '/Users/jiangwei/Documents/dingdingbot')

from src.domain.models import SignalResult, Direction
from src.infrastructure.notifier import NotificationService, FeishuWebhook, format_signal_message
from src.infrastructure.logger import logger


def fetch_signal_from_db():
    """Fetch one signal from database"""
    conn = sqlite3.connect('/Users/jiangwei/Documents/dingdingbot/data/signals.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get one active/pending signal
    cursor.execute("""
        SELECT * FROM signals 
        WHERE status IN ('active', 'pending', 'PENDING', 'ACTIVE')
        ORDER BY created_at DESC 
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
    return row


async def main():
    # Fetch signal from database
    row = fetch_signal_from_db()
    
    if not row:
        print("❌ 未找到信号数据")
        return
    
    print("✅ 从数据库读取信号:")
    print(f"   币种：{row['symbol']}")
    print(f"   周期：{row['timeframe']}")
    print(f"   方向：{row['direction']}")
    print(f"   入场价：{row['entry_price']}")
    print(f"   止损：{row['stop_loss']}")
    print(f"   仓位：{row['position_size']}")
    print(f"   策略：{row['strategy_name']}")
    print(f"   评分：{row['score']}")
    print(f"   标签：{row['tags_json']}")
    print()
    
    # Construct SignalResult object
    direction = Direction.LONG if row['direction'] == 'long' else Direction.SHORT
    
    # Parse tags from JSON
    import json
    tags = json.loads(row['tags_json']) if row['tags_json'] else []
    
    # Build take_profit_levels if available (S6-3)
    take_profit_levels = []
    if row['take_profit_1']:
        take_profit_levels.append({
            "id": "TP1",
            "price": row['take_profit_1'],
            "position_ratio": 0.5,
            "risk_reward": 1.0
        })
    
    signal = SignalResult(
        signal_id=row['signal_id'] or 'test-001',
        symbol=row['symbol'],
        timeframe=row['timeframe'],
        direction=direction,
        entry_price=Decimal(row['entry_price']),
        suggested_stop_loss=Decimal(row['stop_loss']),
        suggested_position_size=Decimal(row['position_size']),
        current_leverage=row['leverage'],
        tags=tags,
        risk_reward_info=row['risk_info'],
        strategy_name=row['strategy_name'] or 'unknown',
        score=float(row['score']) if row['score'] else 0.0,
        take_profit_levels=take_profit_levels,  # Pass empty list if no TP levels
    )
    
    # Format message
    message = format_signal_message(signal)
    
    print("📋 生成的消息内容:")
    print("=" * 60)
    print(message)
    print("=" * 60)
    print()
    
    # Send to Feishu (if configured)
    # Check if webhook URL is configured in user.yaml
    import yaml
    try:
        with open('/Users/jiangwei/Documents/dingdingbot/config/user.yaml', 'r', encoding='utf-8') as f:
            user_config = yaml.safe_load(f)
        
        channels = user_config.get('notification', {}).get('channels', [])
        feishu_webhook = None
        for ch in channels:
            if ch.get('type') == 'feishu':
                feishu_webhook = ch.get('webhook_url')
                break
        
        if feishu_webhook:
            print("🚀 正在发送到飞书...")
            service = NotificationService()
            service.add_channel(FeishuWebhook(feishu_webhook))
            await service.send_signal(signal)
            print("✅ 发送完成!")
        else:
            print("⚠️ 飞书 webhook 未配置，跳过实际发送")
            print("   请在 config/user.yaml 中配置 notification.channels")
            
    except Exception as e:
        print(f"❌ 发送失败：{e}")


if __name__ == '__main__':
    asyncio.run(main())
