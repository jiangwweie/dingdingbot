# 回测报告 API 契约 (BT-2 资金费用)

**版本**: v1.0  
**创建日期**: 2026-04-07  
**关联任务**: BT-2 资金费用模拟  
**状态**: ✅ 已实现

---

## 1. 接口概述

回测报告 API 已扩展支持资金费用字段，无需前端额外配置，响应数据自动包含。

### 1.1 接口列表

| 接口 | 方法 | 用途 | 资金费用字段 |
|------|------|------|-------------|
| `/api/v3/backtest/reports` | GET | 回测报告列表 | ❌ 列表页暂不展示 |
| `/api/v3/backtest/reports/{id}` | GET | 回测报告详情 | ✅ 详情页展示 |
| `/api/backtest/orders` | POST | 运行 PMS 回测 | ✅ 响应包含 |

---

## 2. 回测报告详情接口

### 2.1 请求

```http
GET /api/v3/backtest/reports/{report_id}
```

**路径参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `report_id` | string | 是 | 回测报告 ID |

### 2.2 响应

```json
{
  "status": "success",
  "report": {
    "strategy_id": "pinbar",
    "strategy_name": "Pinbar Strategy",
    "backtest_start": 1712476800000,
    "backtest_end": 1712563200000,
    "initial_balance": "10000.0000000000",
    "final_balance": "10523.4500000000",
    "total_return": "0.0523450000",
    "total_trades": 15,
    "winning_trades": 9,
    "losing_trades": 6,
    "win_rate": "0.6000000000",
    "total_pnl": "523.4500000000",
    "total_fees_paid": "12.3400000000",
    "total_slippage_cost": "5.6700000000",
    "total_funding_cost": "-2.5000000000",  // ⭐ BT-2 新增字段
    "max_drawdown": "0.0320000000",
    "sharpe_ratio": null,
    "positions": [...]
  }
}
```

### 2.3 新增字段说明

| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| `total_funding_cost` | Decimal (字符串) | 总资金费用<br>• 正值 = 净支付（多头主导）<br>• 负值 = 净收取（空头主导） | `"-2.5000000000"` |

**字段含义**:
- **正值**：回测期间净支付资金费用（通常多头持仓主导）
- **负值**：回测期间净收取资金费用（通常空头持仓主导）
- **零值**：未启用资金费用或持仓时长不足以产生费用

---

## 3. 运行 PMS 回测接口

### 3.1 请求

```http
POST /api/backtest/orders
Content-Type: application/json
```

**请求体**:
```json
{
  "symbol": "BTC/USDT:USDT",
  "timeframe": "1h",
  "limit": 1000,
  "mode": "v3_pms",
  "funding_rate_enabled": true,  // ⭐ 可选：是否启用资金费用（默认 true）
  "initial_balance": "10000",
  "slippage_rate": "0.001",
  "fee_rate": "0.0004",
  "tp_slippage_rate": "0.0005"
}
```

**请求参数**:
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `funding_rate_enabled` | boolean | 否 | `true` | 是否启用资金费用计算 |

### 3.2 响应

```json
{
  "status": "success",
  "report": {
    // ... 同详情接口响应
    "total_funding_cost": "-2.5000000000",
    // ...
  }
}
```

---

## 4. 配置优先级

资金费用配置遵循三级优先级：

```
1. API Request 参数 (funding_rate_enabled)
2. KV 配置 (数据库存储的默认值)
3. Code Defaults (代码硬编码：enabled=true, rate=0.0001)
```

### 4.1 默认配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `funding_rate_enabled` | `true` | 默认开启资金费用计算 |
| `funding_rate` | `0.0001` (0.01%) | 每 8 小时固定费率 |

---

## 5. 前端展示建议

### 5.1 回测报告详情页

**建议位置**: 在"费用统计"区域新增一行

```
┌─────────────────────────────────┐
│ 费用统计                        │
├─────────────────────────────────┤
│ 手续费：12.34 USDT              │
│ 滑点成本：5.67 USDT             │
│ 资金费用：-2.50 USDT  ⭐新增    │  ← 负值显示为绿色（收益）
├─────────────────────────────────┤
│ 总费用：15.51 USDT              │  ← 计算时包含资金费用
└─────────────────────────────────┘
```

**展示规则**:
- 正值显示为红色（成本）
- 负值显示为绿色（收益）
- 零值显示为灰色或隐藏

### 5.2 回测配置表单（可选）

**复选框**:
```
☑ 启用资金费用计算（默认开启）
  说明：按 0.01%/8 小时 计算持仓成本
```

---

## 6. 计算逻辑说明

### 6.1 单根 K 线资金费用

```python
资金费用 = 持仓价值 × 资金费率 × 持仓时长系数

其中:
- 持仓价值 = 入场价格 × 持仓数量
- 资金费率 = 0.0001 (0.01%)
- 持仓时长系数 = 时间周期小时数 / 8
```

### 6.2 时间周期映射

| K 线周期 | 小时数 | 资金费率周期数 |
|----------|--------|---------------|
| 15m | 0.25h | 0.25/8 = 1/32 |
| 1h | 1h | 1/8 |
| 4h | 4h | 4/8 = 1/2 |
| 1d | 24h | 24/8 = 3 |
| 1w | 168h | 168/8 = 21 |

### 6.3 方向处理

| 持仓方向 | 资金费用符号 | 会计处理 |
|----------|-------------|----------|
| LONG (多头) | 正值 | 支付成本 |
| SHORT (空头) | 负值 | 收取收益 |

**示例**:
```
多头持仓 1 BTC，入场价 50000 USDT，1h K 线:
资金费用 = 50000 × 1 × 0.0001 × (1/8) = +0.625 USDT (支付)

空头持仓 1 BTC，入场价 50000 USDT，1h K 线:
资金费用 = -50000 × 1 × 0.0001 × (1/8) = -0.625 USDT (收取)
```

---

## 7. 数据库迁移说明

### 7.1 当前状态

**无需数据库迁移**（列表页暂不展示）

- 回测报告列表接口 (`/api/v3/backtest/reports`) 不返回 `total_funding_cost`
- 回测报告详情接口 (`/api/v3/backtest/reports/{id}`) 通过 `model_dump()` 自动返回

### 7.2 未来扩展（可选）

如需在列表页展示，可添加数据库列：

```sql
-- 添加总资金费用列
ALTER TABLE backtest_reports
ADD COLUMN total_funding_cost DECIMAL(20, 10) DEFAULT 0;

-- 添加索引（可选）
CREATE INDEX idx_backtest_reports_funding_cost
ON backtest_reports(total_funding_cost);
```

---

## 8. 测试验证

### 8.1 单元测试

```bash
# 运行资金费用测试
pytest tests/unit/test_backtester_funding_cost.py -v

# 测试结果
============================== 10 passed in 0.72s ==============================
```

### 8.2 手动测试

**测试步骤**:
1. 运行 PMS 回测：`POST /api/backtest/orders`
2. 查看响应中的 `total_funding_cost` 字段
3. 获取报告详情：`GET /api/v3/backtest/reports/{id}`
4. 验证 `report.total_funding_cost` 字段存在

**测试用例**:
| 场景 | 预期结果 |
|------|----------|
| 多头持仓回测 | `total_funding_cost > 0` |
| 空头持仓回测 | `total_funding_cost < 0` |
| 关闭资金费用 | `total_funding_cost = 0` |

---

## 9. 错误处理

### 9.1 常见错误

| 错误码 | 说明 | 解决方案 |
|--------|------|----------|
| 404 | 回测报告不存在 | 检查 `report_id` 是否正确 |
| 500 | 数据库查询失败 | 检查数据库连接 |

### 9.2 异常响应

```json
{
  "detail": "回测报告不存在"
}
```

---

## 10. 变更记录

| 日期 | 版本 | 变更内容 | 负责人 |
|------|------|----------|--------|
| 2026-04-07 | v1.0 | 初始版本，新增 `total_funding_cost` 字段 | Backend |

---

## 11. 联系支持

如有疑问，请联系后端开发团队或查看：
- ADR-002: `docs/arch/adr-002-funding-rate-simulation.md`
- 实现文档：`docs/tasks/BT-2-funding-cost-implementation-complete.md`

---

*本契约文档由后端团队维护，变更需经架构师审查。*
