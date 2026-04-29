"""
测试飞书 @机器人触发事件订阅

验证：盯盘狗 webhook 推送消息 @桥田至机器人后，OpenClaw 是否能接收事件
"""
import asyncio
import aiohttp
import json
from datetime import datetime

# 飞书 webhook URL（新的测试 URL）
WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/14797747-0403-4455-a7fe-f6b69cf0ef04"


async def test_mention_bot():
    """测试 @机器人触发事件"""

    print("开始测试飞书 @机器人...")
    print(f"Webhook URL: {WEBHOOK_URL}")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 60)

    # 方式 1: 纯文本 @（简单但不保证可靠）
    test_message_1 = {
        "msg_type": "text",
        "content": {
            "text": "🧪 测试信号 @桥田至（桶子） 请回复确认收到"
        }
    }

    # 方式 2: 富文本 @（推荐，使用 lark_md）
    test_message_2 = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "🧪 飞书 @机器人测试"
                },
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**测试类型**: Webhook 推送 @机器人\n**测试时间**: {time}\n**预期结果**: OpenClaw 接收事件并回复\n\n@桥田至（桶子） 请回复'收到测试'确认".format(
                            time=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        )
                    }
                },
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": "这是一条测试消息，验证 @机器人是否能触发事件订阅"
                        }
                    ]
                }
            ]
        }
    }

    # 方式 3: 使用富文本 <at> 标签（最可靠，但需要知道 open_id）
    # 暂时无法使用，因为不知道桥田至机器人的 open_id

    async with aiohttp.ClientSession() as session:
        # 测试方式 1
        print("\n📤 发送测试消息 1（纯文本 @）...")
        try:
            async with session.post(
                WEBHOOK_URL,
                json=test_message_1,
                headers={"Content-Type": "application/json"},
            ) as response:
                result = await response.json()
                print(f"✅ 发送成功: {result}")
        except Exception as e:
            print(f"❌ 发送失败: {e}")

        await asyncio.sleep(2)  # 等待 2 秒

        # 测试方式 2
        print("\n📤 发送测试消息 2（卡片消息 lark_md @）...")
        try:
            async with session.post(
                WEBHOOK_URL,
                json=test_message_2,
                headers={"Content-Type": "application/json"},
            ) as response:
                result = await response.json()
                print(f"✅ 发送成功: {result}")
        except Exception as e:
            print(f"❌ 发送失败: {e}")

    print("\n" + "=" * 60)
    print("✅ 测试消息已发送！")
    print("\n📋 请检查以下几点：")
    print("1. 飞书群聊是否收到 2 条测试消息？")
    print("2. 桥田至机器人是否被成功 @（名字变蓝/可点击）？")
    print("3. OpenClaw 是否有日志显示接收到事件？")
    print("4. 桥田至机器人是否自动回复？")
    print("\n如果 OpenClaw 接收到事件，说明这个方案可行！🎉")


if __name__ == "__main__":
    asyncio.run(test_mention_bot())