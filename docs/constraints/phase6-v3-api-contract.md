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

#### 2.1.1 请求体 (`OrderRequest`) - 字段约束

| 字段 | 类型 | 必填 | 默认值 | 约束/格式 | 说明 |
|------|------|------|--------|-----------|------|
| `symbol` | string | ✅ 必填 | - | 模式：`^[A-Z]+/[A-Z]+:[A-Z]+$` | 币种对，如 `BTC/USDT:USDT` |
| `order_type` | OrderType | ✅ 必填 | - | 枚举：`MARKET`/`LIMIT`/`STOP_MARKET`/`STOP_LIMIT` | 订单类型 |
| `order_role` | OrderRole | ✅ 必填 | - | 枚举：`ENTRY`/`TP1`/`TP2`/`TP3`/`TP4`/`TP5`/`SL` | 订单角色 |
| `direction` | Direction | ✅ 必填 | - | 枚举：`LONG`/`SHORT` | 方向 |
| `quantity` | string | ✅ 必填 | - | 正则：`^\d+(\.\d+)?$`, 最小值：`0.001` | 数量（Decimal 字符串） |
| `price` | string | ⚠️ 条件必填 | - | 正则：`^\d+(\.\d+)?$` | 限价单价格（`order_type=LIMIT` 或 `STOP_LIMIT` 时必填） |
| `trigger_price` | string | ⚠️ 条件必填 | - | 正则：`^\d+(\.\d+)?$` | 条件单触发价（`order_type=STOP_MARKET` 或 `STOP_LIMIT` 时必填） |
| `reduce_only` | boolean | ❌ 可选 | `false` | - | 仅减仓（平仓单必须设为 `true`） |
| `client_order_id` | string | ❌ 可选 | - | 最大长度：36 | 客户端订单 ID（UUID 格式） |
| `strategy_name` | string | ❌ 可选 | - | 最大长度：64 | 关联策略名称 |
| `signal_id` | string | ❌ 可选 | - | UUID 格式 | 关联信号 ID |

**条件必填规则**:
```
IF order_type IN ("LIMIT", "STOP_LIMIT") THEN price 必填
IF order_type IN ("STOP_MARKET", "STOP_LIMIT") THEN trigger_price 必填
IF order_role IN ("TP1", "TP2", "TP3", "TP4", "TP5", "SL") THEN reduce_only 必须为 true
```

**请求体示例**:
```json
{
  "symbol": "BTC/USDT:USDT",
  "order_type": "MARKET",
  "order_role": "ENTRY",
  "direction": "LONG",
  "quantity": "0.01",
  "reduce_only": false,
  "strategy_name": "01pinbar-ema60",
  "signal_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

#### 2.1.2 响应体 (`OrderResponse`) - 字段约束

| 字段 | 类型 | 必填 | 可为空 | 格式 | 说明 |
|------|------|------|--------|------|------|
| `order_id` | string | ✅ | ❌ | UUID | 系统订单 ID |
| `exchange_order_id` | string | ❌ | ✅ | - | 交易所订单 ID（下单成功后返回） |
| `symbol` | string | ✅ | ❌ | - | 币种对 |
| `order_type` | OrderType | ✅ | ❌ | 枚举 | 订单类型 |
| `order_role` | OrderRole | ✅ | ❌ | 枚举 | 订单角色 |
| `direction` | Direction | ✅ | ❌ | 枚举 | 方向 |
| `quantity` | string | ✅ | ❌ | Decimal | 订单数量 |
| `price` | string | ❌ | ✅ | Decimal | 限价单价格 |
| `trigger_price` | string | ❌ | ✅ | Decimal | 条件单触发价 |
| `average_exec_price` | string | ❌ | ✅ | Decimal | 平均成交价（成交后返回） |
| `filled_qty` | string | ✅ | ❌ | Decimal | 已成交数量（默认 `0`） |
| `remaining_qty` | string | ✅ | ❌ | Decimal | 剩余数量 |
| `status` | OrderStatus | ✅ | ❌ | 枚举 | 订单状态 |
| `reduce_only` | boolean | ✅ | ❌ | - | 是否仅减仓 |
| `client_order_id` | string | ❌ | ✅ | UUID | 客户端订单 ID |
| `strategy_name` | string | ❌ | ✅ | - | 关联策略名称 |
| `signal_id` | string | ❌ | ✅ | UUID | 关联信号 ID |
| `fee_paid` | string | ❌ | ✅ | Decimal | 已支付手续费 |
| `fee_currency` | string | ❌ | ✅ | - | 手续费币种 |
| `created_at` | number | ✅ | ❌ | 毫秒时间戳 | 创建时间 |
| `updated_at` | number | ✅ | ❌ | 毫秒时间戳 | 更新时间 |
| `filled_at` | number | ❌ | ✅ | 毫秒时间戳 | 成交时间 |

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

#### 2.2.1 路径参数

| 字段 | 类型 | 必填 | 格式 | 说明 |
|------|------|------|------|------|
| `order_id` | string | ✅ | UUID | 系统订单 ID |

#### 2.2.2 查询参数

| 字段 | 类型 | 必填 | 格式 | 说明 |
|------|------|------|------|------|
| `symbol` | string | ✅ | - | 币种对（用于交易所路由） |

#### 2.2.3 响应体 (`OrderCancelResponse`) - 字段约束

| 字段 | 类型 | 必填 | 可为空 | 格式 | 说明 |
|------|------|------|--------|------|------|
| `order_id` | string | ✅ | ❌ | UUID | 系统订单 ID |
| `exchange_order_id` | string | ❌ | ✅ | - | 交易所订单 ID（如已同步） |
| `status` | string | ✅ | ❌ | 枚举：`CANCELED`/`REJECTED` | 取消结果状态 |
| `message` | string | ❌ | ✅ | 最大长度：500 | 拒绝原因（当 `status=REJECTED` 时） |
| `canceled_at` | number | ✅ | ❌ | 毫秒时间戳 | 取消时间 |

**响应示例**:
```json
{
  "order_id": "550e8400-e29b-41d4-a716-446655440000",
  "exchange_order_id": "12345678",
  "status": "CANCELED",
  "canceled_at": 1743494400000
}
```

---

### 2.3 订单列表

**端点**: `GET /api/v3/orders`

#### 2.3.1 查询参数

| 字段 | 类型 | 必填 | 默认值 | 约束 | 说明 |
|------|------|------|--------|------|------|
| `symbol` | string | ❌ | - | - | 币种对过滤 |
| `status` | OrderStatus | ❌ | - | 枚举 | 状态过滤 |
| `order_role` | OrderRole | ❌ | - | 枚举 | 角色过滤 |
| `strategy_name` | string | ❌ | - | 最大 64 字符 | 策略名称过滤 |
| `limit` | number | ❌ | `100` | `1-500` | 返回数量限制 |
| `offset` | number | ❌ | `0` | `≥0` | 偏移量 |

#### 2.3.2 响应体 (`OrdersResponse`) - 字段约束

| 字段 | 类型 | 必填 | 格式 | 说明 |
|------|------|------|------|------|
| `items` | OrderResponse[] | ✅ | 数组 | 订单列表 |
| `total` | number | ✅ | 整数 | 总记录数 |
| `limit` | number | ✅ | 整数 | 当前限制数 |
| `offset` | number | ✅ | 整数 | 当前偏移量 |

---

### 2.4 持仓列表

**端点**: `GET /api/v3/positions`

#### 2.4.1 查询参数

| 字段 | 类型 | 必填 | 默认值 | 约束 | 说明 |
|------|------|------|--------|------|------|
| `symbol` | string | ❌ | - | - | 币种对过滤 |
| `is_closed` | boolean | ❌ | `false` | - | 是否查询已平仓 |
| `limit` | number | ❌ | `100` | `1-500` | 返回数量限制 |
| `offset` | number | ❌ | `0` | `≥0` | 偏移量 |

#### 2.4.2 响应体 (`PositionsResponse`) - 字段约束

| 字段 | 类型 | 必填 | 格式 | 说明 |
|------|------|------|------|------|
| `items` | PositionInfo[] | ✅ | 数组 | 持仓列表 |
| `total` | number | ✅ | 整数 | 总记录数 |

**`PositionInfo` 字段约束**:

| 字段 | 类型 | 必填 | 可为空 | 格式 | 说明 |
|------|------|------|--------|------|------|
| `position_id` | string | ✅ | ❌ | UUID | 仓位 ID |
| `symbol` | string | ✅ | ❌ | - | 币种对 |
| `direction` | Direction | ✅ | ❌ | 枚举 | 方向 |
| `entry_price` | string | ✅ | ❌ | Decimal | 入场价 |
| `current_qty` | string | ✅ | ❌ | Decimal | 当前数量 |
| `original_qty` | string | ✅ | ❌ | Decimal | 原始数量 |
| `unrealized_pnl` | string | ✅ | ❌ | Decimal | 未实现盈亏 |
| `realized_pnl` | string | ✅ | ❌ | Decimal | 已实现盈亏 |
| `liquidation_price` | string | ❌ | ✅ | Decimal | 强平价 |
| `leverage` | number | ✅ | ❌ | 整数 | 杠杆倍数 |
| `margin_mode` | string | ✅ | ❌ | `cross`/`isolated` | 保证金模式 |
| `total_fees_paid` | string | ✅ | ❌ | Decimal | 累计手续费 |
| `entry_time` | number | ✅ | ❌ | 毫秒时间戳 | 入场时间 |
| `closed_at` | number | ❌ | ✅ | 毫秒时间戳 | 平仓时间 |
| `is_closed` | boolean | ✅ | ❌ | - | 是否已平仓 |
| `strategy_name` | string | ❌ | ✅ | - | 关联策略名称 |
| `signal_id` | string | ❌ | ✅ | UUID | 关联信号 ID |
| `take_profit_orders` | OrderInfo[] | ✅ | ❌ | 数组 | TP 订单链 |
| `stop_loss_order` | OrderInfo | ❌ | ✅ | 对象 | SL 订单 |
| `tags` | Tag[] | ✅ | ❌ | 数组 | 动态标签 |

---

### 2.5 账户余额

**端点**: `GET /api/v3/account/balance`

#### 2.5.1 响应体 (`AccountBalance`) - 字段约束

| 字段 | 类型 | 必填 | 可为空 | 格式 | 说明 |
|------|------|------|--------|------|------|
| `total_balance` | string | ✅ | ❌ | Decimal | 总余额 |
| `available_balance` | string | ✅ | ❌ | Decimal | 可用余额 |
| `unrealized_pnl` | string | ✅ | ❌ | Decimal | 未实现盈亏 |
| `total_equity` | string | ✅ | ❌ | Decimal | 总权益 |
| `currency` | string | ✅ | ❌ | - | 币种（`USDT`） |
| `timestamp` | number | ✅ | ❌ | 毫秒时间戳 | 快照时间 |

---

### 2.6 资金保护检查

**端点**: `POST /api/v3/orders/check`

#### 2.6.1 请求体 (`OrderCheckRequest`) - 字段约束

| 字段 | 类型 | 必填 | 可为空 | 格式 | 说明 |
|------|------|------|--------|------|------|
| `symbol` | string | ✅ | ❌ | - | 币种对 |
| `order_type` | OrderType | ✅ | ❌ | 枚举 | 订单类型 |
| `quantity` | string | ✅ | ❌ | Decimal | 数量 |
| `price` | string | ❌ | ✅ | Decimal | 限价单价格 |
| `trigger_price` | string | ❌ | ✅ | Decimal | 条件单触发价 |
| `stop_loss` | string | ❌ | ✅ | Decimal | 建议止损价 |

#### 2.6.2 响应体 (`CapitalProtectionCheckResult`) - 字段约束

| 字段 | 类型 | 必填 | 格式 | 说明 |
|------|------|------|------|------|
| `allowed` | boolean | ✅ | - | 是否允许下单 |
| `reason` | string | ❌ | - | 拒绝原因（当 `allowed=false`） |
| `checks` | CheckResults | ✅ | 对象 | 各项检查结果 |

**`CheckResults` 字段约束**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `single_trade_limit` | SingleTradeCheck | ✅ | 单笔交易限制检查 |
| `position_limit` | PositionLimitCheck | ✅ | 仓位限制检查 |
| `daily_loss_limit` | DailyLossCheck | ✅ | 每日亏损限制检查 |
| `daily_trade_count` | TradeCountCheck | ✅ | 每日交易次数检查 |
| `min_balance` | MinBalanceCheck | ✅ | 最低余额检查 |

**各检查项通用字段**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `passed` | boolean | ✅ | 是否通过 |
| `max_allowed` | string | ❌ | 最大允许值 |
| `current_value` | string | ❌ | 当前值 |

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

## 3. Pydantic 模型验证规则

### 3.1 OrderRequest 验证器

```python
# src/domain/models.py

class OrderRequest(FinancialModel):
    symbol: str = Field(
        ...,
        pattern=r'^[A-Z]+/[A-Z]+:[A-Z]+$',
        description="币种对"
    )
    order_type: OrderType = Field(..., description="订单类型")
    order_role: OrderRole = Field(..., description="订单角色")
    direction: Direction = Field(..., description="方向")
    quantity: Decimal = Field(
        ...,
        gt=0,
        decimal_places=8,
        description="数量"
    )
    price: Optional[Decimal] = Field(
        None,
        gt=0,
        decimal_places=8,
        description="限价单价格"
    )
    trigger_price: Optional[Decimal] = Field(
        None,
        gt=0,
        decimal_places=8,
        description="条件单触发价"
    )
    reduce_only: bool = Field(default=False, description="仅减仓")
    client_order_id: Optional[str] = Field(
        None,
        max_length=36,
        description="客户端订单 ID (UUID)"
    )
    strategy_name: Optional[str] = Field(
        None,
        max_length=64,
        description="策略名称"
    )
    signal_id: Optional[str] = Field(
        None,
        description="关联信号 ID (UUID)"
    )

    @model_validator(mode='after')
    def validate_order_fields(self) -> 'OrderRequest':
        """订单字段条件验证"""
        # LIMIT 或 STOP_LIMIT 订单必须有价格
        if self.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT):
            if self.price is None:
                raise ValueError('price 字段在 LIMIT/STOP_LIMIT 订单中必填')

        # STOP_MARKET 或 STOP_LIMIT 订单必须有 trigger_price
        if self.order_type in (OrderType.STOP_MARKET, OrderType.STOP_LIMIT):
            if self.trigger_price is None:
                raise ValueError('trigger_price 字段在 STOP_MARKET/STOP_LIMIT 订单中必填')

        # 止盈止损订单必须设置 reduce_only=true
        if self.order_role in (OrderRole.TP1, OrderRole.TP2, OrderRole.TP3,
                                OrderRole.TP4, OrderRole.TP5, OrderRole.SL):
            if not self.reduce_only:
                raise ValueError('TP/SL 订单必须设置 reduce_only=true')

        return self
```

### 3.2 字段约束汇总

| 字段 | 验证规则 | 错误消息 |
|------|----------|----------|
| `symbol` | `pattern='^[A-Z]+/[A-Z]+:[A-Z]+$'` | "币种对格式不正确" |
| `quantity` | `gt=0`, `decimal_places=8` | "数量必须为正数" |
| `price` | `gt=0`, `decimal_places=8` (条件必填) | "LIMIT 订单必须有价格" |
| `trigger_price` | `gt=0`, `decimal_places=8` (条件必填) | "STOP 订单必须有 trigger_price" |
| `client_order_id` | `max_length=36` | "客户端订单 ID 超长" |
| `strategy_name` | `max_length=64` | "策略名称超长" |
| `reduce_only` | 必须为 `true` (当 `order_role=TP/SL`) | "TP/SL 订单必须设置 reduce_only=true" |

---

## 4. 枚举定义（与后端对齐）

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
