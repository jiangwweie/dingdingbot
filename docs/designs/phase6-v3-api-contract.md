# Phase 6: v3.0 API 契约表

> **创建日期**: 2026-03-31
> **版本**: v1.0
> **状态**: 📝 设计中

---

## 1. API 端点定义

| 端点 | 方法 | 说明 | 请求体 | 响应 | 优先级 |
|------|------|------|--------|------|--------|
| `/api/v3/orders` | POST | 创建订单 | OrderRequest | OrderResponse | P0 |
| `/api/v3/orders` | GET | 查询订单列表 | - | OrdersResponse | P0 |
| `/api/v3/orders/{id}` | GET | 查询订单详情 | - | OrderResponse | P0 |
| `/api/v3/orders/{id}` | DELETE | 取消订单 | - | OrderCancelResponse | P0 |
| `/api/v3/orders/check` | POST | 下单前资金保护检查 | OrderCheckRequest | CapitalProtectionCheckResult | P1 |
| `/api/v3/positions` | GET | 查询持仓列表 | - | PositionsResponse | P0 |
| `/api/v3/positions/{id}` | GET | 查询持仓详情 | - | PositionInfo | P1 |
| `/api/v3/positions/{id}/close` | POST | 平仓 | ClosePositionRequest | OrderResponse | P1 |
| `/api/v3/account/balance` | GET | 查询账户余额 | - | AccountBalance | P0 |
| `/api/v3/account/snapshot` | GET | 查询账户快照 | - | AccountSnapshot | P1 |
| `/api/v3/reconciliation` | POST | 启动对账服务 | ReconciliationRequest | ReconciliationReport | P2 |

---

## 2. 请求/响应 Schema

### 2.1 订单创建

**端点**: `POST /api/v3/orders`

**请求体** (`OrderRequest`):
```typescript
{
  symbol: string;                    // "BTC/USDT:USDT"
  order_type: OrderType;             // "MARKET" | "LIMIT" | "STOP_MARKET" | "STOP_LIMIT"
  order_role: OrderRole;             // "ENTRY" | "TP1" | "TP2" | "TP3" | "TP4" | "TP5" | "SL"
  direction: Direction;              // "LONG" | "SHORT"
  quantity: string;                  // Decimal 字符串
  price?: string;                    // 限价单价格（可选）
  trigger_price?: string;            // 条件单触发价（可选）
  reduce_only?: boolean;             // 默认 false
  client_order_id?: string;          // 客户端订单 ID
  strategy_name?: string;            // 关联策略名称
  signal_id?: string;                // 关联信号 ID
}
```

**响应** (`OrderResponse`):
```typescript
{
  order_id: string;
  exchange_order_id?: string;
  symbol: string;
  order_type: OrderType;
  order_role: OrderRole;
  direction: Direction;
  quantity: string;
  price?: string;
  trigger_price?: string;
  average_exec_price?: string;
  filled_qty: string;
  remaining_qty: string;
  status: OrderStatus;
  reduce_only: boolean;
  client_order_id?: string;
  strategy_name?: string;
  signal_id?: string;
  fee_paid?: string;
  fee_currency?: string;
  created_at: number;                // 毫秒时间戳
  updated_at: number;
  filled_at?: number;
}
```

**错误响应**:
| HTTP 状态码 | 错误码 | 说明 |
|------------|--------|------|
| 400 | F-011 | 订单参数错误 |
| 400 | CAPITAL_CHECK_FAILED | 资金保护检查失败 |
| 402 | F-010 | 保证金不足 |
| 404 | ORDER_NOT_FOUND | 订单不存在 |
| 429 | C-010 | API 频率限制 |

---

### 2.2 订单取消

**端点**: `DELETE /api/v3/orders/{order_id}`

**路径参数**:
| 字段 | 类型 | 说明 |
|------|------|------|
| order_id | string | 系统订单 ID |

**查询参数**:
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| symbol | string | 是 | 币种对 |

**响应** (`OrderCancelResponse`):
```typescript
{
  order_id: string;
  exchange_order_id?: string;
  status: "CANCELED" | "REJECTED";
  message?: string;
  canceled_at: number;
}
```

---

### 2.3 订单列表

**端点**: `GET /api/v3/orders`

**查询参数**:
| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| symbol | string | - | 币种对过滤 |
| status | OrderStatus | - | 状态过滤 |
| order_role | OrderRole | - | 角色过滤 |
| strategy_name | string | - | 策略名称过滤 |
| limit | number | 100 | 返回数量限制 |
| offset | number | 0 | 偏移量 |

**响应** (`OrdersResponse`):
```typescript
{
  items: OrderResponse[];
  total: number;
  limit: number;
  offset: number;
}
```

---

### 2.4 持仓列表

**端点**: `GET /api/v3/positions`

**查询参数**:
| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| symbol | string | - | 币种对过滤 |
| is_closed | boolean | false | 是否查询已平仓 |
| limit | number | 100 | 返回数量限制 |

**响应** (`PositionsResponse`):
```typescript
{
  items: PositionInfo[];
  total: number;
}
```

**`PositionInfo`**:
```typescript
{
  position_id: string;
  symbol: string;
  direction: Direction;
  entry_price: string;
  current_qty: string;
  original_qty: string;
  unrealized_pnl: string;
  realized_pnl: string;
  liquidation_price?: string;
  leverage: number;
  margin_mode: string;              // "cross" | "isolated"
  total_fees_paid: string;
  entry_time: number;
  closed_at?: number;
  is_closed: boolean;
  strategy_name?: string;
  signal_id?: string;
  take_profit_orders: OrderInfo[];  // TP1-TP5 订单链
  stop_loss_order?: OrderInfo;      // SL 订单
  tags: Tag[];
}
```

---

### 2.5 账户余额

**端点**: `GET /api/v3/account/balance`

**响应** (`AccountBalance`):
```typescript
{
  total_balance: string;
  available_balance: string;
  unrealized_pnl: string;
  total_equity: string;
  currency: string;                 // "USDT"
  timestamp: number;
}
```

---

### 2.6 账户快照

**端点**: `GET /api/v3/account/snapshot`

**响应** (`AccountSnapshot`):
```typescript
{
  snapshot_id: string;
  total_balance: string;
  available_balance: string;
  used_margin: string;
  unrealized_pnl: string;
  total_equity: string;
  positions: PositionSummary[];
  currency: string;
  timestamp: number;
}
```

---

### 2.7 资金保护检查

**端点**: `POST /api/v3/orders/check`

**请求体** (`OrderCheckRequest`):
```typescript
{
  symbol: string;
  order_type: OrderType;
  quantity: string;
  price?: string;
  trigger_price?: string;
  stop_loss?: string;               // 建议止损价
}
```

**响应** (`CapitalProtectionCheckResult`):
```typescript
{
  allowed: boolean;
  reason?: string;
  checks: {
    single_trade_limit: { passed: boolean; max_loss: string; estimated_loss: string };
    position_limit: { passed: boolean; max_position: string; position_value: string };
    daily_loss_limit: { passed: boolean; daily_max_loss: string; daily_pnl: string };
    daily_trade_count: { passed: boolean; max_count: number; current_count: number };
    min_balance: { passed: boolean; min_balance: string; current_balance: string };
  };
}
```

---

### 2.8 对账服务

**端点**: `POST /api/v3/reconciliation`

**请求体** (`ReconciliationRequest`):
```typescript
{
  symbol: string;
}
```

**响应** (`ReconciliationReport`):
```typescript
{
  report_id: string;
  generated_at: number;
  symbol: string;

  // 仓位对账
  missing_positions: PositionInfo[];
  position_mismatches: PositionMismatch[];

  // 订单对账
  orphan_orders: OrderInfo[];
  order_mismatches: OrderMismatch[];

  // 资产对账
  balance_difference: string;

  // 待确认项目（宽限期内）
  pending_items: PendingItem[];
}
```

---

## 3. 枚举定义（与后端对齐）

### 3.1 Direction

```typescript
enum Direction {
  LONG = "LONG",
  SHORT = "SHORT"
}
```

### 3.2 OrderType

```typescript
enum OrderType {
  MARKET = "MARKET",
  LIMIT = "LIMIT",
  STOP_MARKET = "STOP_MARKET",
  STOP_LIMIT = "STOP_LIMIT"
}
```

### 3.3 OrderRole

```typescript
enum OrderRole {
  ENTRY = "ENTRY",
  TP1 = "TP1",
  TP2 = "TP2",
  TP3 = "TP3",
  TP4 = "TP4",
  TP5 = "TP5",
  SL = "SL"
}
```

### 3.4 OrderStatus

```typescript
enum OrderStatus {
  PENDING = "PENDING",
  OPEN = "OPEN",
  FILLED = "FILLED",
  CANCELED = "CANCELED",
  REJECTED = "REJECTED",
  EXPIRED = "EXPIRED",
  PARTIALLY_FILLED = "PARTIALLY_FILLED"
}
```

---

## 4. 前端 TypeScript 类型

**文件**: `web-front/src/types/order.ts`

```typescript
// 与后端 Pydantic 模型对齐
```

---

## 5. 技术决策

### 5.1 Decimal 精度处理

- **后端**: Python `decimal.Decimal`
- **前端**: 字符串传输，使用 `Decimal` 类解析
- **理由**: 避免浮点数精度丢失

### 5.2 时间戳格式

- **格式**: 毫秒时间戳 (int64)
- **理由**: 前端直接使用 `Date.now()` 兼容

### 5.3 订单角色精细定义

- **决策**: 使用 `ENTRY/TP1-5/SL` 而非 `OPEN/CLOSE`
- **理由**: 支持 v3.0 PMS 多级别止盈策略

---

## 6. 依赖注入

**API 层依赖**:
```python
def get_v3_dependencies():
    return {
        "exchange_gateway": _exchange_gateway,
        "position_manager": _position_manager,
        "capital_protection": _capital_protection,
        "reconciliation_service": _reconciliation_service,
    }
```

---

## 7. 验收标准

- [ ] 所有端点实现与契约表一致
- [ ] 请求/响应 Schema 与前端类型对齐
- [ ] 错误码统一使用 F-0xx, C-0xx
- [ ] 敏感信息日志脱敏
- [ ] 单元测试覆盖率 ≥ 80%

---

*契约表版本：v1.0*
*最后更新：2026-03-31*
