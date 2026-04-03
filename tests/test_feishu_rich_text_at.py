"""
测试飞书富文本 @机器人（使用 open_id）

根据 GitHub PR #340 的方案，使用 <at user_id="ou_xxx">名字</at> 格式
"""
import asyncio
import aiohttp
import json
from datetime import datetime

# 飞书 webhook URL
WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/14797747-0403-4455-a7fe-f6b69cf0ef04"

# 桥田至机器人的 open_id（从日志获取）
BOT_OPEN_ID = "ou_af3225e28da15e3f25a3b0a6de64eeb4"


async def test_rich_text_at():
    """测试富文本 @机器人（使用 open_id）"""

    print("开始测试飞书富文本 @机器人（PR #340 方案）...")
    print(f"Webhook URL: {WEBHOOK_URL}")
    print(f"Bot open_id: {BOT_OPEN_ID}")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 60)

    # 方案：富文本 @（使用 <at user_id="ou_xxx">标签）
    test_message = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "🧪 富文本 @机器人测试（PR #340 方案）"
                },
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**测试类型**: Webhook 推送富文本 @\n**测试时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n**机器人**: 牧濑红莉栖\n**Bot open_id**: `{BOT_OPEN_ID}`\n\n<at user_id=\"{BOT_OPEN_ID}\">牧濑红莉栖</at> 请回复'收到富文本测试'确认\n\n**关键验证点**:\n1. 牧濑红莉栖名字是否变蓝/可点击？\n2. OpenClaw 是否接收事件并回复？\n3. 如果回复，说明 bot-relay 功能已启用"
                    }
                },
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": "此方案来自 GitHub PR #340，使用 <at user_id=\"ou_xxx\"> 标签"
                        }
                    ]
                }
            ]
        }
    }

    async with aiohttp.ClientSession() as session:
        print("\n📤 发送富文本 @消息（使用 open_id）...")
        try:
            async with session.post(
                WEBHOOK_URL,
                json=test_message,
                headers={"Content-Type": "application/json"},
            ) as response:
                result = await response.json()
                print(f"✅ 发送成功: {result}")
        except Exception as e:
            print(f"❌ 发送失败: {e}")

    print("\n" + "=" * 60)
    print("✅ 测试消息已发送！")
    print("\n📋 关键检查点：")
    print("1. 飞书群聊是否收到卡片消息？")
    print("2. '桥田至（桶子）'名字是否变蓝/可点击？（验证富文本 @成功）")
    print("3. **OpenClaw 是否自动回复？**（验证 bot-relay 功能）")
    print("\n如果 OpenClaw 自动回复，说明：")
    print("✅ OpenClaw 已集成 PR #340 的 bot-relay 功能")
    print("✅ 我们可以使用 webhook + 富文本 @方案")
    print("✅ 无需调用飞书机器人 API")


if __name__ == "__main__":
    asyncio.run(test_rich_text_at())