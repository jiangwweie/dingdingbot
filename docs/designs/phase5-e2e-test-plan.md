# Phase 5 E2E 集成测试计划

**创建日期**: 2026-03-31
**执行环境**: Binance Testnet
**状态**: 🔄 执行中

---

## 一、测试目标

验证 Phase 5 实盘集成核心功能在 Binance Testnet 的端到端表现：
1. 订单执行（下单/取消/查询）
2. 资金保护（单笔/每日/仓位限制）
3. DCA 分批建仓策略
4. 对账服务
5. WebSocket 订单推送
6. 飞书告警通知

---

## 二、测试环境配置

### 2.1 环境变量

```bash
# .env
EXCHANGE_NAME=binance
EXCHANGE_TESTNET=true
EXCHANGE_API_KEY=8o5IHB2Q2qG57m6sSNQ31plRwoiMjFhPopTszKrGVFSpQPvPOWlQ6Uf77cPm3bnC
EXCHANGE_API_SECRET=Hcm9pzHD5spZCwCYVBMm0VBsC3Ux6zR6kpN63dwyuzLsRYC4oqRKSy6P3twDE936

DATABASE_URL=sqlite+aiosqlite:///./data/v3_dev.db

FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/4d9badfa-7566-42e4-9c3c-15f6435aafb7

CAPITAL_PROTECTION_ENABLED=true
SINGLE_TRADE_MAX_LOSS_PERCENT=2.0
DAILY_MAX_LOSS_PERCENT=5.0
```

### 2.2 测试币种

| 币种 | 交易对 | 说明 |
|------|--------|------|
| BTC | BTC/USDT:USDT | 主测试币种 |
| ETH | ETH/USDT:USDT | 辅助测试币种 |

### 2.3 测试配置

```yaml
# config/test-e2e.yaml
exchange:
  name: binance
  testnet: true
  
e2e_test:
  symbol: "BTC/USDT:USDT"
  amount: 0.001  # 测试用量
  direction: "LONG"
  order_type: "MARKET"
```

---

## 三、测试窗口分配

### 窗口 1：订单执行 + 资金保护

| 测试项 | 说明 | 预期结果 |
|--------|------|----------|
| **Test-1.1** | 市价单下单 | 订单成功创建并成交 |
| **Test-1.2** | 限价单下单 | 订单成功挂单 |
| **Test-1.3** | 取消订单 | 订单成功取消 |
| **Test-1.4** | 查询订单状态 | 返回正确状态 |
| **Test-1.5** | 单笔损失限制 | 超限订单被拒绝 |
| **Test-1.6** | 每日损失限制 | 超限订单被拒绝 |
| **Test-1.7** | 仓位限制 | 超限订单被拒绝 |

**测试文件**: `tests/e2e/test_phase5_window1.py`

---

### 窗口 2：DCA + 持仓管理

| 测试项 | 说明 | 预期结果 |
|--------|------|----------|
| **Test-2.1** | DCA 两批建仓 | 第一批市价单成交 |
| **Test-2.2** | DCA 限价单挂单 | 第 2-N 批限价单成功挂出 |
| **Test-2.3** | DCA 平均成本计算 | 平均成本正确 |
| **Test-2.4** | 持仓状态追踪 | 数据库持仓状态正确 |
| **Test-2.5** | 止盈订单链 | TP1-TP5 订单正确创建 |
| **Test-2.6** | 止损订单 | SL 订单正确创建 |
| **Test-2.7** | 平仓流程 | 持仓正确关闭 |

**测试文件**: `tests/e2e/test_phase5_window2.py`

---

### 窗口 3：对账服务 + WebSocket 推送

| 测试项 | 说明 | 预期结果 |
|--------|------|----------|
| **Test-3.1** | WebSocket 连接 | 成功连接 Binance Testnet WS |
| **Test-3.2** | 订单推送监听 | 订单状态变更实时推送 |
| **Test-3.3** | 启动对账服务 | 对账任务成功启动 |
| **Test-3.4** | 持仓对账 | 交易所 vs 数据库一致性检查 |
| **Test-3.5** | 订单对账 | 订单状态一致性检查 |
| **Test-3.6** | Grace Period | 10 秒宽限期处理 WebSocket 延迟 |
| **Test-3.7** | 飞书告警 | 订单事件触发通知 |

**测试文件**: `tests/e2e/test_phase5_window3.py`

---

## 四、执行步骤

### 步骤 1：环境准备

```bash
# 1. 创建 .env 文件
cp .env.example .env
# 编辑 .env 填入 API 密钥和配置

# 2. 安装依赖
pip install -r requirements.txt

# 3. 确认数据库已迁移
python scripts/migrate_db.py upgrade head

# 4. 验证 API 密钥可用
python scripts/verify_api_key.py
```

### 步骤 2：运行单元测试（前置验证）

```bash
# 确认 Phase 5 单元测试通过
pytest tests/unit/test_phase5_models.py tests/unit/test_phase5_integration.py tests/integration/test_phase5_api.py -v
```

**预期**: 89/89 通过 (100%)

### 步骤 3：执行 E2E 测试

```bash
# 窗口 1：订单执行 + 资金保护
pytest tests/e2e/test_phase5_window1.py -v

# 窗口 2：DCA + 持仓管理
pytest tests/e2e/test_phase5_window2.py -v

# 窗口 3：对账服务 + WebSocket 推送
pytest tests/e2e/test_phase5_window3.py -v
```

---

## 五、验收标准

| 窗口 | 通过标准 |
|------|----------|
| 窗口 1 | 7/7 测试通过，资金保护触发正确 |
| 窗口 2 | 7/7 测试通过，DCA 策略执行正确 |
| 窗口 3 | 7/7 测试通过，WebSocket 推送实时 |

**总体要求**: 21/21 测试通过 (100%)

---

## 六、风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 测试网 API 不稳定 | 测试失败 | 重试机制 + 手动验证 |
| 测试网资金不足 | 下单失败 | 使用最小测试用量 (0.001 BTC) |
| WebSocket 连接超时 | 推送延迟 | 30 秒超时 + 自动重连 |
| 飞书 Webhook 限流 | 通知失败 | 降级到日志记录 |

---

## 七、测试结果记录

### 执行日期：2026-03-31

| 窗口 | 测试数 | 通过 | 失败 | 状态 |
|------|--------|------|------|------|
| 窗口 1 | 7 | - | - | ⏳ 待执行 |
| 窗口 2 | 7 | - | - | ⏳ 待执行 |
| 窗口 3 | 7 | - | - | ⏳ 待执行 |

**总计**: 0/21 完成

---

## 八、问题追踪

| 编号 | 问题描述 | 严重性 | 状态 | 解决方案 |
|------|----------|--------|------|----------|
| - | - | - | - | - |

---

*Phase 5 E2E 集成测试计划 v1.0*
