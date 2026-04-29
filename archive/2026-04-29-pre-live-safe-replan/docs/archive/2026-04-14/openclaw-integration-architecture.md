# OpenClaw 飞书机器人集成技术方案

> **文档类型**: 架构设计文档
> **创建日期**: 2026-04-03
> **测试验证**: 已完成（Webhook @方案失败，确定使用机器人 API 方案）

---

## 📋 目录

1. [测试验证结果](#测试验证结果)
2. [最终技术方案](#最终技术方案)
3. [接口契约](#接口契约)
4. [数据流设计](#数据流设计)
5. [实施步骤](#实施步骤)
6. [风险与依赖](#风险与依赖)

---

## 测试验证结果

### 测试时间
2026-04-03 12:43:28

### 测试方案
通过盯盘狗 webhook 推送消息 @桥田至机器人，验证 OpenClaw 是否能接收事件并响应。

### 测试结果
| 检查项 | 结果 | 说明 |
|--------|------|------|
| 消息发送成功 | ✅ | 飞书群聊收到 2 条测试消息 |
| @机器人成功 | ✅ | "桥田至（桶子）"名字变蓝色/可点击 |
| 机器人自动回复 | ❌ | OpenClaw 未接收事件，无响应 |

### 结论
**飞书安全机制限制**：机器人无法接收自己通过 webhook 发送的消息事件，即使是 @自己。

**技术原因**：
- Webhook 是单向推送，发送者是机器人自己
- 飞书事件订阅只推送"其他用户"发送的消息给机器人
- 机器人发送的消息（包括 webhook）不会触发自己的事件订阅

---

## 最终技术方案

### 方案名称：飞书机器人 API 桥接方案

### 架构图

```
┌─────────────┐
│  盯盘狗      │
│  (Python)   │
│  信号触发    │
└─────────────┘
      ↓ HTTP POST
      ↓ 使用 OpenClaw appId/appSecret
┌─────────────┐
│  飞书 API   │
│  /im/v1/    │
│  messages   │
└─────────────┘
      ↓ 卡片消息
┌─────────────┐
│  飞书群聊    │
│  用户查看    │
└─────────────┘
      ↓ 用户点击按钮
┌─────────────┐
│  飞书服务器  │
│  事件推送    │
└─────────────┘
      ↓ WebSocket
┌─────────────┐
│  OpenClaw   │
│  接收回调    │
│  AI 处理    │
└─────────────┘
      ↓ HTTP POST
┌─────────────┐
│  盯盘狗 API │
│  执行订单    │
└─────────────┘
```

### 核心流程

#### MVP-1: 交互式风险问答

```
用户飞书对话："当前风险如何？"
  ↓
OpenClaw AI 解析意图
  ↓
调用盯盘狗 API：GET /api/v3/positions
  ↓
OpenClaw AI 风险分析（多模型）
  ↓
OpenClaw 调用飞书 API 发送卡片：
  - 风险评级: 中等 ⚠️
  - 持仓风险: BTC 多头 2.3%
  - [一键降低杠杆] [设置止损]
  ↓
用户点击按钮 → OpenClaw WebSocket 接收回调
  ↓
OpenClaw 调用盯盘狗 API 执行操作
```

#### MVP-2: 交互式订单确认

```
盯盘狗信号触发
  ↓
调用飞书机器人 API 发送卡片：
  - BTC/USDT 多头信号
  - 入场价: $67,234
  - [确认执行] [拒绝] [AI详情]
  ↓
用户点击"确认执行" → OpenClaw WebSocket 接收回调
  ↓
OpenClaw 调用盯盘狗 API：POST /api/v3/orders
  ↓
订单创建 → 飞书推送结果卡片
```

---

## 接口契约

### 1. 飞书机器人 API 认证

**获取 tenant_access_token**：
```http
POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal
Content-Type: application/json

{
  "app_id": "cli_a927a4374eb89cef",
  "app_secret": "AuYDNC2VhpenohDq6b6ecfcsCm5vDnrh"
}
```

**响应**：
```json
{
  "code": 0,
  "msg": "ok",
  "tenant_access_token": "t-xxx",
  "expire": 7200
}
```

---

### 2. 发送卡片消息到群聊

**API 端点**：
```http
POST https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id
Authorization: Bearer {tenant_access_token}
Content-Type: application/json

{
  "receive_id": "oc_xxxx",  // 群聊 ID
  "msg_type": "interactive",
  "content": "{卡片JSON}"
}
```

**卡片消息格式**（带按钮）：
```json
{
  "msg_type": "interactive",
  "card": {
    "header": {
      "title": {
        "tag": "plain_text",
        "content": "BTC/USDT 多头信号"
      },
      "template": "blue"
    },
    "elements": [
      {
        "tag": "div",
        "text": {
          "tag": "lark_md",
          "content": "**入场价**: $67,234\n**止损**: $65,800 (-2.1%)\n**止盈**: TP1 $69,000 (+2.6%)"
        }
      },
      {
        "tag": "action",
        "actions": [
          {
            "tag": "button",
            "text": {
              "tag": "plain_text",
              "content": "确认执行"
            },
            "type": "primary",
            "value": {
              "action": "confirm_order",
              "signal_id": "sig_12345",
              "symbol": "BTC/USDT:USDT",
              "entry_price": "67234.00"
            }
          },
          {
            "tag": "button",
            "text": {
              "tag": "plain_text",
              "content": "拒绝"
            },
            "type": "default",
            "value": {
              "action": "reject_order",
              "signal_id": "sig_12345"
            }
          }
        ]
      }
    ]
  }
}
```

---

### 3. OpenClaw 接收卡片按钮回调

**回调事件格式**（飞书推送给 OpenClaw WebSocket）：
```json
{
  "type": "card",
  "action": {
    "value": {
      "action": "confirm_order",
      "signal_id": "sig_12345",
      "symbol": "BTC/USDT:USDT",
      "entry_price": "67234.00"
    }
  },
  "open_id": "ou_xxxx",
  "tenant_key": "xxx",
  "token": "xxx"
}
```

**OpenClaw 处理逻辑**：
```javascript
// OpenClaw 接收卡片按钮回调
if (event.type === 'card' && event.action.value.action === 'confirm_order') {
  const signal = event.action.value;

  // 调用盯盘狗 API 执行订单
  await fetch('http://localhost:8000/api/v3/orders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      symbol: signal.symbol,
      side: 'BUY',
      type: 'LIMIT',
      price: signal.entry_price,
      signal_id: signal.signal_id
    })
  });

  // 回复用户
  await feishu.sendMessage('✅ 订单已执行！');
}
```

---

### 4. 盯盘狗 API 扩展

**新增端点**（供 OpenClaw 调用）：
```python
# src/interfaces/api.py

@app.get("/api/v3/positions")
async def get_positions():
    """返回当前持仓详情"""
    positions = await position_manager.get_all_positions()
    return {
        "positions": [p.dict() for p in positions],
        "total_value": sum(p.position_value for p in positions)
    }


@app.get("/api/v3/account/balance")
async def get_account_balance():
    """返回账户余额"""
    balance = await account_manager.get_balance()
    return {"balance": balance}


@app.get("/api/v3/account/snapshot")
async def get_account_snapshot():
    """返回账户快照"""
    snapshot = await account_manager.get_snapshot()
    return snapshot.dict()
```

---

## 数据流设计

### MVP-1 数据流（风险问答）

```
┌──────────┐
│ 用户飞书  │ "当前风险如何？"
└──────────┘
      ↓
┌──────────┐
│ OpenClaw │ AI 解析意图
│ WebSocket│
└──────────┘
      ↓ GET /api/v3/positions
      ↓ GET /api/v3/account/balance
┌──────────┐
│ 盯盘狗   │ 返回数据
│ FastAPI  │
└──────────┘
      ↓
┌──────────┐
│ OpenClaw │ 多模型分析风险
│ Qwen+GLM │
└──────────┘
      ↓ POST /im/v1/messages
┌──────────┐
│ 飞书 API │ 发送风险卡片
└──────────┘
      ↓
┌──────────┐
│ 飞书群聊 │ 用户查看卡片
└──────────┘
      ↓ 点击按钮
┌──────────┐
│ OpenClaw │ 接收回调
│ WebSocket│
└──────────┘
      ↓ POST /api/v3/orders
┌──────────┐
│ 盯盘狗   │ 执行操作
└──────────┘
```

### MVP-2 数据流（订单确认）

```
┌──────────┐
│ 盯盘狗   │ 信号触发
│ 策略引擎 │
└──────────┘
      ↓ POST /im/v1/messages
┌──────────┐
│ 飞书 API │ 发送订单确认卡片
└──────────┘
      ↓
┌──────────┐
│ 飞书群聊 │ 用户查看卡片
└──────────┘
      ↓ 点击"确认执行"
┌──────────┐
│ OpenClaw │ 接收回调
│ WebSocket│
└──────────┘
      ↓ POST /api/v3/orders
┌──────────┐
│ 盯盘狗   │ 创建订单
│ 订单引擎 │
└──────────┘
      ↓ POST /im/v1/messages
┌──────────┐
│ 飞书 API │ 发送订单结果卡片
└──────────┘
```

---

## 实施步骤

### 步骤 1: 配置飞书机器人权限（0.5h）

**操作**：
1. 登录飞书开放平台：https://open.feishu.cn/
2. 找到应用"桥田至（桶子）"
3. 配置权限：
   - `im:chat` - 获取群聊信息
   - `im:message` - 发送消息
   - `im:message:send_as_bot` - 以机器人身份发送

**验证**：
```bash
# 获取 tenant_access_token
curl -X POST "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal" \
  -H "Content-Type: application/json" \
  -d '{
    "app_id": "cli_a927a4374eb89cef",
    "app_secret": "AuYDNC2VhpenohDq6b6ecfcsCm5vDnrh"
  }'
```

---

### 步骤 2: 获取群聊 ID（0.5h）

**方法 1**：通过 OpenClaw 日志
```bash
# 发送一条消息到群聊，查看 OpenClaw 日志
tail -f ~/.openclaw/logs/agent.log | grep "chat_id\|open_id"
```

**方法 2**：通过飞书 API
```bash
# 获取机器人所在群聊列表
curl -X GET "https://open.feishu.cn/open-apis/im/v1/chats" \
  -H "Authorization: Bearer {tenant_access_token}"
```

---

### 步骤 3: 扩展盯盘狗飞书通知模块（1h）

**文件**：`src/infrastructure/notifier_feishu.py`

**新增方法**：
```python
async def send_signal_card_via_bot_api(
    self,
    signal: SignalResult,
    chat_id: str
) -> bool:
    """通过飞书机器人 API 发送信号确认卡片"""

    # 1. 获取 tenant_access_token
    token = await self._get_tenant_access_token()

    # 2. 构建卡片消息（带按钮）
    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"{signal.symbol} 信号"},
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**入场价**: {signal.entry_price}\n**止损**: {signal.suggested_stop_loss}"
                    }
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "确认执行"},
                            "type": "primary",
                            "value": {
                                "action": "confirm_order",
                                "signal_id": signal.id,
                                "symbol": signal.symbol,
                                "entry_price": str(signal.entry_price)
                            }
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "拒绝"},
                            "type": "default",
                            "value": {
                                "action": "reject_order",
                                "signal_id": signal.id
                            }
                        }
                    ]
                }
            ]
        }
    }

    # 3. 发送卡片
    url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={
                "receive_id": chat_id,
                "msg_type": "interactive",
                "content": json.dumps(card)
            }
        ) as response:
            return response.status == 200


async def _get_tenant_access_token(self) -> str:
    """获取飞书 tenant_access_token"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json={
            "app_id": OPENCLAW_APP_ID,
            "app_secret": OPENCLAW_APP_SECRET
        }) as response:
            result = await response.json()
            return result["tenant_access_token"]
```

---

### 步骤 4: OpenClaw 接收卡片按钮回调（1h）

**文件**：`~/.openclaw/workspace/skills/dingdingbot-order-confirm/SKILL.md`（新建）

**技能定义**：
```markdown
---
name: dingdingbot-order-confirm
description: 盯盘狗订单确认技能 - 接收飞书卡片按钮回调并执行订单
---

# 订单确认技能

## 触发条件
当飞书卡片按钮回调 `action.value.action` 为 `confirm_order` 或 `reject_order` 时触发。

## 执行逻辑

1. 解析回调数据：
   ```javascript
   const signal = event.action.value;
   ```

2. 调用盯盘狗 API：
   ```javascript
   if (signal.action === 'confirm_order') {
     await fetch('http://localhost:8000/api/v3/orders', {
       method: 'POST',
       body: JSON.stringify({
         symbol: signal.symbol,
         side: 'BUY',
         price: signal.entry_price,
         signal_id: signal.signal_id
       })
     });
   }
   ```

3. 回复用户：
   ```javascript
   await feishu.sendMessage('✅ 订单已执行！');
   ```
```

---

### 步骤 5: 移动端测试验证（0.5h）

**测试用例**：
1. 飞书对话"当前风险如何？"
2. 查看卡片消息是否正确展示
3. 点击"一键降低杠杆"按钮
4. 验证操作是否执行成功

---

## 风险与依赖

### 技术风险

| 风险项 | 影响 | 应对策略 |
|--------|------|----------|
| 飞书 API 频率限制 | 中 | 缓存 tenant_access_token（2小时过期） |
| 群聊 ID 获取失败 | 低 | 通过 OpenClaw 日志或飞书 API 查询 |
| OpenClaw WebSocket 断连 | 中 | 实现重连机制（已有） |

### 外部依赖

| 依赖项 | 状态 | 说明 |
|--------|------|------|
| 飞书机器人权限 | ⚠️ 待配置 | 需配置 `im:chat`、`im:message` 权限 |
| 群聊 ID | ⚠️ 待获取 | 需通过 API 或日志获取 |
| 盯盘狗 API | ✅ 已就绪 | FastAPI 端点运行中 |
| OpenClaw WebSocket | ✅ 已就绪 | 飞书插件已配置 |

---

## 工时估算

| 任务 | 工时 | 说明 |
|------|------|------|
| 步骤 1: 配置权限 | 0.5h | 飞书开放平台配置 |
| 步骤 2: 获取群聊 ID | 0.5h | API 查询或日志获取 |
| 步骤 3: 盯盘狗扩展 | 1h | 飞书 API 调用 + 卡片构建 |
| 步骤 4: OpenClaw 技能 | 1h | 回调处理 + API 调用 |
| 步骤 5: 测试验证 | 0.5h | 移动端测试 |
| **总计** | **3.5h** | MVP-1 核心功能 |

---

*文档版本: v1.0 | 最后更新: 2026-04-03*