# 验证测试：飞书 Webhook @机器人触发事件订阅

**测试目的**: 验证盯盘狗 webhook 推送消息时 @桥田至机器人，是否能触发 OpenClaw 的事件订阅和回调

**测试时间**: 2026-04-03

---

## 测试方案

### 飞书 @机制说明

飞书支持两种 @方式：

1. **富文本 @**（推荐）：使用 `<at user_id="ou_xxx">名字</at>` 标签
2. **纯文本 @**：直接 `@名字`（不够可靠）

### 测试步骤

**步骤 1**: 获取桥田至机器人的 `user_id` 或 `open_id`

```bash
# 通过飞书 API 获取机器人信息
curl -X GET "https://open.feishu.cn/open-apis/bot/v3/info" \
  -H "Authorization: Bearer {tenant_access_token}"
```

**步骤 2**: 盯盘狗 webhook 推送测试

修改 `notifier_feishu.py`，添加 @机器人：

```python
# src/infrastructure/notifier_feishu.py 测试代码
async def test_mention_bot():
    """测试 @机器人"""

    # 方式 1: 使用富文本 @（推荐）
    card = {
        "msg_type": "interactive",
        "card": {
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "测试信号 @桥田至（桶子）\n入场价: $67,234"
                    }
                }
            ]
        }
    }

    # 方式 2: 使用 rich_text（更可靠）
    card_with_rich_text = {
        "msg_type": "interactive",
        "card": {
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "测试信号 <at user_id=\"ou_xxx\">桥田至（桶子）</at>\n入场价: $67,234"
                    }
                }
            ]
        }
    }

    await _send_payload(card)
```

**步骤 3**: OpenClaw 监听事件订阅

检查 OpenClaw 是否能接收到被 @的事件：

```javascript
// OpenClaw 应该能接收到类似这样的事件：
{
  "type": "message",
  "msg_type": "text",
  "content": "@桥田至（桶子） 测试信号",
  "mentions": [
    {
      "key": "@桥田至（桶子）",
      "id": {
        "open_id": "ou_xxx",
        "user_id": "ou_xxx"
      },
      "name": "桥田至（桶子）",
      "tenant_key": "xxx"
    }
  ]
}
```

---

## 预期结果

### ✅ 成功场景

1. 盯盘狗 webhook 推送消息 → 群聊显示 "测试信号 @桥田至（桶子）"
2. OpenClaw WebSocket 接收到 `message` 事件，包含 `mentions` 字段
3. OpenClaw AI 解析事件，触发技能执行

### ❌ 失败场景

1. Webhook 推送的消息，OpenClaw 无法接收（因为 webhook 是单向推送）
2. 只有机器人主动发送的消息，OpenClaw 才能接收

---

## 关键问题

**核心问题**: 飞书 webhook 推送的消息，@机器人后，机器人能否通过 WebSocket 接收到事件？

**可能的结果**:
- ✅ **可能成功**: 飞书会将 @事件推送给机器人，即使是 webhook 消息
- ❌ **可能失败**: Webhook 是单向推送，机器人无法接收自己的消息事件

---

## 立即测试

让我帮您编写测试代码，立即验证这个方案。