# OpenClaw + 盯盘狗 + Claude Code 集成需求文档

> **文档类型**: PRD (Product Requirements Document)
> **创建日期**: 2026-04-03
> **优先级**: P0（最高优先级）
> **预计工期**: 18-24h（2 个 MVP 组合）

---

## 📋 目录

1. [背景与动机](#背景与动机)
2. [核心差异化价值](#核心差异化价值)
3. [MVP 场景定义](#mvp-场景定义)
4. [技术实现方案](#技术实现方案)
5. [验收标准](#验收标准)
6. [风险与依赖](#风险与依赖)

---

## 背景与动机

### 问题背景

用户拥有三个独立系统，各自能力分散，缺少协同：

| 系统 | 当前状态 | 核心能力 | 使用场景 |
|------|---------|---------|---------|
| **OpenClaw** | 独立运行 | 8 个国产模型 + 飞书集成 + Node.js 技能 | AI 对话、远程查询、消息推送 |
| **盯盘狗** | 生产运行 | 信号监控 + 订单执行 + 策略引擎 + 回测系统 | 量化交易自动化 |
| **Claude Code** | 开发辅助 | 开发工作流 + Agent Team + Planning-with-files | 代码开发、Bug 修复、团队协作 |

### 用户痛点

**痛点 1: 缺少移动端交互能力**
- 盯盘狗 Web 前端：需打开电脑访问，移动端体验差
- 币安 app：仅持仓查询，无风险分析、策略调整能力
- 用户需求：随时随地交互式操作（手机飞书）

**痛点 2: 单人决策易疲劳**
- 盯盘狗信号自动执行：无人工确认环节，误判风险
- 已有 webhook 推送：仅通知，无交互能力
- 用户需求：卡片消息 + 一键确认 + AI 对话追问

**痛点 3: 风险信息分散**
- 持仓、订单、账户数据分散在多个 Web 页面
- 币安 app 仅展示持仓，无综合风险分析
- 用户需求：对话式查询风险 + AI 综合分析 + 一键操作

**痛点 4: 已有功能重复**
- ❌ "查看持仓"：币安 app 已有，移动端原生体验更好
- ❌ "信号推送"：盯盘狗 webhook 已有，重复建设浪费

### 核心洞察

**飞书的强交互能力才是真正的差异化价值**：
- ✅ 实时对话：随时随地，无需打开 Web
- ✅ 卡片消息：富媒体展示（按钮、表单、图表、进度条）
- ✅ 群聊协作：多人讨论 + AI 参与 + 决策投票
- ✅ 快捷操作：一键确认/拒绝/执行/回测
- ✅ 历史追溯：搜索历史对话、决策记录
- ✅ 移动端：手机随时随地访问

---

## 核心差异化价值

### 差异化价值公式

```
差异化价值 = (系统 A + 系统 B) - 已有解决方案价值
```

**反例**（无价值场景）：
- OpenClaw 查询持仓 = (OpenClaw 飞书 + 盯盘狗 API) - (币安 app) ≈ **负价值**（多一层转发）

**正例**（高价值场景）：
- 交互式风险问答 = (OpenClaw 风险分析 + 飞书交互) - (币安 app 持仓查询) ≈ **正价值**（新增风险分析能力）

### 核心差异化能力矩阵

| 系统 | 独特能力（不可替代） | 已有能力（可被替代） |
|------|---------------------|---------------------|
| **OpenClaw** | • 8 个国产模型对比决策<br>• 飞书群聊多人协作决策<br>• **卡片消息交互能力** ⭐<br>• Node.js 技能快速执行 | • 查询持仓（币安 app 替代）<br>• 单人对话（Claude Code 替代）<br>• 消息推送（webhook 替代） |
| **盯盘狗** | • 量化策略引擎<br>• Optuna 自动化调参<br>• 回测沙箱系统<br>• **风控预检查能力** ⭐ | • 持仓查询（币安 app 替代）<br>• K 线数据（交易所 API 替代） |
| **Claude Code** | • 完整开发工作流<br>• **代码修改 + 验证能力** ⭐<br>• 跨会话记忆持久化 | • 单模型对话（OpenClaw 替代）<br>• 代码编辑（IDE 替代） |

---

## MVP 场景定义

### MVP-1: 交互式风险问答 ⭐⭐⭐⭐⭐（最高优先级）

**用户故事**：
> 作为交易员，我希望在手机飞书随时查询当前风险状况，以便快速做出风险控制决策。

**核心流程**：
```
用户飞书对话："当前风险如何？"
  ↓
OpenClaw AI 调用盯盘狗 API：
  • GET /api/v3/positions（持仓）
  • GET /api/v3/account/balance（账户）
  • GET /api/v3/account/snapshot（快照）
  ↓
OpenClaw AI 综合分析风险：
  • 持仓风险（仓位、杠杆、未实现盈亏）
  • 市场风险（BTC/ETH 波动率）
  • 资金流向（交易所流入流出）
  ↓
飞书卡片消息：
  ┌─────────────────────────────┐
  │ 风险评级: 中等 ⚠️           │
  │                             │
  │ 持仓风险:                   │
  • BTC 多头仓位 2.3%           │
  • 杠杆 3x（可控）             │
  • 未实现盈亏 +$234            │
  │                             │
  │ 市场风险:                   │
  • BTC 波动率 4.2%（中等）     │
  • 交易所净流入 $12M           │
  │                             │
  │ AI 建议:                    │
  • 降低杠杆至 2x               │
  • 设置止损 $65,800            │
  │                             │
  │ [一键降低杠杆] [设置止损]   │
  └─────────────────────────────┘
  ↓
用户点击"一键降低杠杆" → Claude Code 执行修改
```

**验收标准 (AC)**：
- [ ] AC-1: 飞书对话触发风险查询（"当前风险如何？"）
- [ ] AC-2: OpenClaw 调用盯盘狗 API 获取持仓/账户数据
- [ ] AC-3: 风险综合分析（持仓风险 + 市场风险）
- [ ] AC-4: 飞书卡片消息展示风险评级 + AI 建议
- [ ] AC-5: 卡片按钮"一键降低杠杆"触发操作
- [ ] AC-6: Claude Code 执行杠杆修改 + 验证
- [ ] AC-7: 移动端测试（手机飞书操作）

**RICE 评分**：(5 × 5 × 0.9) / 2 = **11.3** ⭐⭐⭐⭐⭐

**预计工时**：6-8h

---

### MVP-2: 交互式订单确认 ⭐⭐⭐⭐⭐

**用户故事**：
> 作为交易员，我希望盯盘狗信号触发后通过飞书卡片确认执行，以便快速把关避免误判。

**核心流程**：
```
盯盘狗信号触发
  ↓
风控预检查（CapitalProtectionManager）
  ↓
飞书推送卡片消息：
  ┌─────────────────────────────┐
  │ BTC/USDT 多头信号           │
  │ 入场价: $67,234             │
  │ 止损: $65,800 (-2.1%)       │
  │ 止盈: TP1 $69,000 (+2.6%)   │
  │                             │
  │ 风控检查: ✅ 通过            │
  │ 建议仓位: 1.2%              │
  │                             │
  │ AI 分析:                    │
  • EMA 趋势看涨 ✅             │
  • MTF 多周期共振 ✅           │
  • 形态质量 0.85               │
  │                             │
  │ [确认执行] [拒绝] [AI详情]  │
  └─────────────────────────────┘
  ↓
用户点击"确认执行" → 订单执行
用户点击"AI详情" → AI 实时对话分析
用户点击"拒绝" → 记录拒绝原因
```

**验收标准 (AC)**：
- [ ] AC-1: 盯盘狗信号触发飞书卡片推送
- [ ] AC-2: 卡片消息包含信号详情 + 风控预检查 + AI 分析
- [ ] AC-3: 卡片按钮"确认执行"触发订单创建
- [ ] AC-4: 卡片按钮"拒绝"记录拒绝原因
- [ ] AC-5: 卡片按钮"AI详情"触发对话追问
- [ ] AC-6: OpenClaw 接收飞书回调并调用盯盘狗 API
- [ ] AC-7: 移动端测试（手机飞书确认）

**RICE 评分**：(5 × 5 × 0.9) / 4 = **5.6** ⭐⭐⭐

**预计工时**：12-16h

---

## 技术实现方案

### 技术架构

```
┌─────────────┐
│  飞书用户    │
└─────────────┘
      ↓ 对话/卡片按钮
┌─────────────┐
│  OpenClaw   │ ← AI 解析意图 + 多模型分析
│  Gateway    │ ← Node.js 技能执行
└─────────────┘
      ↓ API 调用
┌─────────────┐
│  盯盘狗 API │ ← 持仓/订单/账户数据
│  FastAPI    │ ← 风控预检查
└─────────────┘
      ↓ 回调确认
┌─────────────┐
│ Claude Code │ ← 代码修改 + 验证
│ Agent Team  │ ← 开发 + 测试 + 审查
└─────────────┘
```

### MVP-1 技术方案（交互式风险问答）

**步骤 1: OpenClaw 技能开发**（Node.js）
```javascript
// ~/.openclaw/workspace/skills/dingdingbot-risk-query/scripts/query_risk.js
async function queryRisk() {
  // 1. 调用盯盘狗 API
  const positions = await fetch('http://localhost:8000/api/v3/positions');
  const account = await fetch('http://localhost:8000/api/v3/account/balance');

  // 2. AI 综合分析风险
  const riskAnalysis = await multiModelAnalyze({
    models: ['qwen3-max', 'glm-4.7', 'MiniMax-M2.5'],
    data: { positions, account }
  });

  // 3. 飞书卡片消息
  return {
    card: {
      header: { title: '风险评级: 中等 ⚠️' },
      elements: [
        { tag: 'div', text: '持仓风险...' },
        { tag: 'action', actions: [
          { tag: 'button', text: '一键降低杠杆', value: 'reduce_leverage' },
          { tag: 'button', text: '设置止损', value: 'set_stop_loss' }
        ]}
      ]
    }
  };
}
```

**步骤 2: 飞书卡片按钮回调处理**
```javascript
// 监听飞书卡片按钮点击
async function handleCardAction(action) {
  if (action.value === 'reduce_leverage') {
    // 调用 Claude Code Agent
    await callAgent('backend-dev', {
      task: '修改持仓杠杆至 2x',
      verify: true
    });
  }
}
```

**步骤 3: 盯盘狗 API 扩展**（Python）
```python
# src/interfaces/api.py
@app.get("/api/v3/positions")
async def get_positions():
    """返回当前持仓详情（供 OpenClaw 调用）"""
    positions = await position_manager.get_all_positions()
    return {
        "positions": positions,
        "total_value": sum(p.position_value for p in positions)
    }
```

---

### MVP-2 技术方案（交互式订单确认）

**步骤 1: 盯盘狗信号触发飞书推送**
```python
# src/application/signal_pipeline.py
async def process_signal(signal_result):
    # 1. 风控预检查
    risk_check = await capital_protection.check_order_pre_conditions(signal_result)

    # 2. 推送飞书卡片消息（通过 OpenClaw API）
    await feishu_push_card({
        "signal": signal_result,
        "risk_check": risk_check,
        "ai_analysis": await analyze_signal_quality(signal_result)
    })
```

**步骤 2: OpenClaw 接收飞书回调**
```javascript
// 监听飞书卡片按钮"确认执行"
async function handleOrderConfirm(action) {
  if (action.value === 'confirm_execution') {
    // 调用盯盘狗订单创建 API
    await fetch('http://localhost:8000/api/v3/orders', {
      method: 'POST',
      body: JSON.stringify(action.signal)
    });
  }
}
```

---

## 验收标准

### MVP-1 验收清单

| 验收项 | 测试方法 | 预期结果 |
|--------|---------|---------|
| 飞书对话触发 | 手机飞书输入"当前风险如何？" | OpenClaw AI 响应风险查询 |
| 盯盘狗 API 调用 | OpenClaw 日志确认 API 调用 | 成功获取持仓/账户数据 |
| 风险综合分析 | 卡片消息展示风险评级 | 风险评级 + AI 建议 |
| 卡片按钮操作 | 点击"一键降低杠杆" | Claude Code 执行修改 |
| 移动端测试 | 手机飞书完整流程 | 5 秒内完成风险查询 |

### MVP-2 验收清单

| 验收项 | 测试方法 | 预期结果 |
|--------|---------|---------|
| 信号触发推送 | 盯盘狗信号触发 | 飞书收到卡片消息 |
| 风控预检查 | 卡片展示风控结果 | ✅ 通过或 ❌ 拒绝 |
| AI 分析展示 | 卡片展示多模型分析 | 技术面 + 宏观面 + 风险评级 |
| 一键确认执行 | 点击"确认执行" | 订单成功创建 |
| 拒绝原因记录 | 点击"拒绝" | 记录拒绝原因到数据库 |
| 移动端测试 | 手机飞书确认订单 | 10 秒内完成确认 |

---

## 风险与依赖

### 技术风险

| 风险项 | 影响 | 应对策略 |
|--------|------|----------|
| OpenClaw 飞书集成复杂度 | 中 | 复用已有 feishu plugin，无需重新开发 |
| 盯盘狗 API 认证 | 低 | OpenClaw Gateway token 已配置 |
| Claude Code Agent 调度 | 低 | 已有 Agent Team 编排能力 |
| 移动端卡片渲染 | 低 | 飞书官方支持，无需额外开发 |

### 外部依赖

| 依赖项 | 状态 | 说明 |
|--------|------|------|
| OpenClaw Gateway | ✅ 已配置 | 本地运行，token 认证 |
| 飞书 Bot | ✅ 已创建 | appId/appSecret 已配置 |
| 盯盘狗 API | ✅ 已运行 | FastAPI 端点就绪 |
| Claude Code | ✅ 已就绪 | Agent Team 编排能力 |

### 工时估算

| 任务 | 工时 | 说明 |
|------|------|------|
| **MVP-1** | **6-8h** | OpenClaw 技能开发 + 盯盘狗 API 扩展 + 测试 |
| **MVP-2** | **12-16h** | 盯盘狗信号推送 + OpenClaw 回调处理 + 测试 |
| **总计** | **18-24h** | 2 个 MVP 组合实现 |

---

## 附录

### RICE 评分明细

**MVP-1 评分**：
- Reach (覆盖范围): 5/5（所有交易员高频使用）
- Impact (影响力): 5/5（直接影响资金安全）
- Confidence (信心度): 0.9（技术可行性高）
- Effort (投入成本): 2 人天（6-8h）
- **Priority = (5 × 5 × 0.9) / 2 = 11.3** ⭐⭐⭐⭐⭐

**MVP-2 评分**：
- Reach: 5/5（每个信号都需要确认）
- Impact: 5/5（避免误判执行）
- Confidence: 0.9（技术可行性高）
- Effort: 4 人天（12-16h）
- **Priority = (5 × 5 × 0.9) / 4 = 5.6** ⭐⭐⭐

---

*文档版本: v1.0 | 最后更新: 2026-04-03*