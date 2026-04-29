# Phase 5: 实盘集成 - 接口契约表

> **创建日期**: 2026-03-30
> **任务 ID**: Phase-5
> **版本**: v1.1
> **状态**: ✅ 已完成（与代码实现对齐）
> **最后更新**: 2026-03-31 - 更新 OrderRole 枚举为 v3.0 PMS 精细定义

---

## 1. API 端点定义

| 端点 | 方法 | 说明 | 负责人 |
|------|------|------|--------|
| `/api/orders` | POST | 下单（支持 MARKET/LIMIT/STOP_MARKET） | Backend |
| `/api/orders/{order_id}` | DELETE | 取消订单 | Backend |
| `/api/orders/{order_id}` | GET | 查询订单状态 | Backend |
| `/api/positions` | GET | 查询持仓列表 | Backend |
| `/api/account` | GET | 查询账户信息 | Backend |
| `/api/reconciliation` | POST | 启动对账服务 | Backend |

---

## 2. 请求 Schema

### 2.1 请求头（Headers）

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| Content-Type | string | 是 | application/json | - |
| Authorization | string | 否 | - | API Key（如需要） |

---

## 3. 核心模型定义

### 3.1 Direction 枚举（与 v3 对齐）

```python
# src/domain/models.py

from enum import Enum

class Direction(str, Enum):
    LONG = "LONG"   # 做多/开多
    SHORT = "SHORT" # 做空/开空
```

### 3.2 OrderStatus 枚举（与 v3 对齐）

```python
# src/domain/models.py

from enum import Enum

class OrderStatus(str, Enum):
    PENDING = "PENDING"       # 待成交
    OPEN = "OPEN"             # 已挂单
    FILLED = "FILLED"         # 已成交
    CANCELED = "CANCELED"     # 已取消
    REJECTED = "REJECTED"     # 已拒绝
    EXPIRED = "EXPIRED"       # 已过期
    PARTIALLY_FILLED = "PARTIALLY_FILLED"  # 部分成交
```

### 3.3 OrderType 枚举

```python
# src/domain/models.py

from enum import Enum

class OrderType(str, Enum):
    MARKET = "MARKET"           # 市价单
    LIMIT = "LIMIT"             # 限价单
    STOP_MARKET = "STOP_MARKET" # 条件市价单
    STOP_LIMIT = "STOP_LIMIT"   # 条件限价单
```

### 3.4 OrderRole 枚举（与 v3.0 PMS 对齐）

```python
# src/domain/models.py

from enum import Enum

class OrderRole(str, Enum):
    ENTRY = "ENTRY"               # 入场开仓
    TP1 = "TP1"                   # 第一目标位止盈（首笔止盈）
    TP2 = "TP2"                   # 第二目标位止盈
    TP3 = "TP3"                   # 第三目标位止盈
    TP4 = "TP4"                   # 第四目标位止盈
    TP5 = "TP5"                   # 第五目标位止盈
    SL = "SL"                     # 止损单
```

**说明**: v3.0 PMS 系统采用精细订单角色定义，支持多级别止盈订单链管理。与简化版 `OPEN/CLOSE` 分类不同，此设计允许：
- 区分开仓订单 (`ENTRY`) 和各种平仓订单 (`TP1-5`, `SL`)
- 支持多 TP 策略（最多 5 个止盈级别）
- 精确追踪每个订单的仓位管理职责

---

## 4. 下单接口契约

### 4.1 请求体（POST /api/orders）

```python
# src/domain/models.py

from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field

class OrderRequest(BaseModel):
    """下单请求"""
    symbol: str = Field(..., description="币种对，如 'BTC/USDT:USDT'")
    order_type: OrderType = Field(..., description="订单类型")
    direction: Direction = Field(..., description="方向（LONG/SHORT）")
    role: OrderRole = Field(..., description="角色（ENTRY/TP1/TP2/TP3/TP4/TP5/SL）")
    amount: Decimal = Field(..., gt=0, description="数量（正数）")
    price: Optional[Decimal] = Field(None, gt=0, description="限价单价格（LIMIT 订单必填）")
    trigger_price: Optional[Decimal] = Field(None, gt=0, description="条件单触发价（STOP 订单必填）")
    reduce_only: bool = Field(default=False, description="是否仅减仓（平仓单必须为 True）")
    client_order_id: Optional[str] = Field(None, max_length=64, description="客户端订单 ID")
    strategy_name: Optional[str] = Field(None, max_length=64, description="策略名称")
    stop_loss: Optional[Decimal] = Field(None, gt=0, description="止损价格")
    take_profit: Optional[Decimal] = Field(None, gt=0, description="止盈价格")
```

| 字段 | 类型 | 必填 | 默认值 | 说明 | 前端对应字段 |
|------|------|------|--------|------|--------------|
| `symbol` | string | 是 | - | 币种对 | `symbol` |
| `order_type` | string | 是 | - | 订单类型 (MARKET/LIMIT/STOP_MARKET/STOP_LIMIT) | `orderType` |
| `direction` | string | 是 | - | 方向 (LONG/SHORT) | `direction` |
| `role` | string | 是 | - | 角色 (ENTRY/TP1/TP2/TP3/TP4/TP5/SL) | `role` |
| `amount` | number | 是 | - | 数量（Decimal 精度） | `amount` |
| `price` | number | 条件必填 | null | 限价单价格 | `price` |
| `trigger_price` | number | 条件必填 | null | 条件单触发价 | `triggerPrice` |
| `reduce_only` | boolean | 否 | false | 是否仅减仓 | `reduceOnly` |
| `client_order_id` | string | 否 | null | 客户端订单 ID | `clientOrderId` |
| `strategy_name` | string | 否 | null | 策略名称 | `strategyName` |
| `stop_loss` | number | 否 | null | 止损价格 | `stopLoss` |
| `take_profit` | number | 否 | null | 止盈价格 | `takeProfit` |

**约束条件**:
- `order_type == LIMIT` 或 `order_type == STOP_LIMIT` 时，`price` 必填
- `order_type == STOP_MARKET` 或 `order_type == STOP_LIMIT` 时，`trigger_price` 必填
- `role` 为 `TP1/TP2/TP3/TP4/TP5/SL` 时，`reduce_only` 必须为 `true`（平仓单）

### 4.2 响应 Schema（POST /api/orders）

```python
# src/domain/models.py

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

class OrderResponse(BaseModel):
    """订单响应"""
    order_id: str = Field(..., description="系统订单 ID")
    exchange_order_id: Optional[str] = Field(None, description="交易所订单 ID")
    symbol: str = Field(..., description="币种对")
    order_type: OrderType = Field(..., description="订单类型")
    direction: Direction = Field(..., description="方向")
    role: OrderRole = Field(..., description="角色")
    status: OrderStatus = Field(..., description="订单状态")
    amount: Decimal = Field(..., description="订单数量")
    filled_amount: Decimal = Field(default=Decimal("0"), description="已成交数量")
    price: Optional[Decimal] = Field(None, description="限价单价格")
    trigger_price: Optional[Decimal] = Field(None, description="条件单触发价")
    average_exec_price: Optional[Decimal] = Field(None, description="平均成交价")
    reduce_only: bool = Field(..., description="是否仅减仓")
    client_order_id: Optional[str] = Field(None, description="客户端订单 ID")
    strategy_name: Optional[str] = Field(None, description="策略名称")
    stop_loss: Optional[Decimal] = Field(None, description="止损价格")
    take_profit: Optional[Decimal] = Field(None, description="止盈价格")
    created_at: int = Field(..., description="创建时间戳（毫秒）")
    updated_at: int = Field(..., description="更新时间戳（毫秒）")
    fee_paid: Decimal = Field(default=Decimal("0"), description="已支付手续费")
    tags: List[dict] = Field(default_factory=list, description="动态标签列表")
```

| 字段 | 类型 | 必填 | 说明 | TypeScript 类型 |
|------|------|------|------|-----------------|
| `order_id` | string | 是 | 系统订单 ID | `string` |
| `exchange_order_id` | string | 否 | 交易所订单 ID | `string \| null` |
| `symbol` | string | 是 | 币种对 | `string` |
| `order_type` | string | 是 | 订单类型 | `OrderType` |
| `direction` | string | 是 | 方向 | `Direction` |
| `role` | string | 是 | 角色 | `OrderRole` |
| `status` | string | 是 | 订单状态 | `OrderStatus` |
| `amount` | number | 是 | 订单数量 | `string` (Decimal) |
| `filled_amount` | number | 是 | 已成交数量 | `string` (Decimal) |
| `price` | number | 否 | 限价单价格 | `string \| null` |
| `trigger_price` | number | 否 | 条件单触发价 | `string \| null` |
| `average_exec_price` | number | 否 | 平均成交价 | `string \| null` |
| `reduce_only` | boolean | 是 | 是否仅减仓 | `boolean` |
| `client_order_id` | string | 否 | 客户端订单 ID | `string \| null` |
| `strategy_name` | string | 否 | 策略名称 | `string \| null` |
| `stop_loss` | number | 否 | 止损价格 | `string \| null` |
| `take_profit` | number | 否 | 止盈价格 | `string \| null` |
| `created_at` | number | 是 | 创建时间戳 | `number` |
| `updated_at` | number | 是 | 更新时间戳 | `number` |
| `fee_paid` | number | 是 | 已支付手续费 | `string` (Decimal) |
| `tags` | array | 是 | 动态标签列表 | `Tag[]` |

### 4.3 错误响应（POST /api/orders）

| 错误码 | HTTP 状态码 | 说明 | 前端处理方式 |
|--------|-------------|------|--------------|
| `F-010` | 400 | 保证金不足 | toast 错误提示 |
| `F-011` | 400 | 订单参数错误（如 LIMIT 单无价格） | toast 错误提示，检查表单 |
| `F-003` | 400 | 必填配置缺失 | toast 错误提示 |
| `F-004` | 503 | 交易所初始化失败 | toast 错误提示，检查连接 |
| `C-010` | 429 | API 频率限制 | 指数退避重试 |
| `W-001` | 500 | 内部服务器错误 | toast 错误提示 |

---

## 5. 取消订单接口契约

### 5.1 路径参数（DELETE /api/orders/{order_id}）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `order_id` | string | 是 | 系统订单 ID |

### 5.2 查询参数（DELETE /api/orders/{order_id}）

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `symbol` | string | 是 | - | 币种对 |

### 5.3 响应 Schema（DELETE /api/orders/{order_id}）

```python
# src/domain/models.py

class OrderCancelResponse(BaseModel):
    """取消订单响应"""
    order_id: str = Field(..., description="系统订单 ID")
    exchange_order_id: Optional[str] = Field(None, description="交易所订单 ID")
    symbol: str = Field(..., description="币种对")
    status: OrderStatus = Field(..., description="取消后状态")
    canceled_at: int = Field(..., description="取消时间戳（毫秒）")
    message: str = Field(..., description="取消结果说明")
```

| 字段 | 类型 | 必填 | 说明 | TypeScript 类型 |
|------|------|------|------|-----------------|
| `order_id` | string | 是 | 系统订单 ID | `string` |
| `exchange_order_id` | string | 否 | 交易所订单 ID | `string \| null` |
| `symbol` | string | 是 | 币种对 | `string` |
| `status` | string | 是 | 取消后状态 | `OrderStatus` |
| `canceled_at` | number | 是 | 取消时间戳 | `number` |
| `message` | string | 是 | 取消结果说明 | `string` |

### 5.4 错误响应（DELETE /api/orders/{order_id}）

| 错误码 | HTTP 状态码 | 说明 | 前端处理方式 |
|--------|-------------|------|--------------|
| `F-012` | 404 | 订单不存在 | toast 错误提示 |
| `F-013` | 400 | 订单已成交（无法取消） | toast 错误提示 |
| `C-010` | 429 | API 频率限制 | 指数退避重试 |

---

## 6. 查询订单接口契约

### 6.1 路径参数（GET /api/orders/{order_id}）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `order_id` | string | 是 | 系统订单 ID |

### 6.2 查询参数（GET /api/orders/{order_id}）

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `symbol` | string | 是 | - | 币种对 |

### 6.3 响应 Schema（GET /api/orders/{order_id}）

响应体同 **OrderResponse**（见 4.2 节）

### 6.4 错误响应（GET /api/orders/{order_id}）

| 错误码 | HTTP 状态码 | 说明 | 前端处理方式 |
|--------|-------------|------|--------------|
| `F-012` | 404 | 订单不存在 | toast 错误提示 |

---

## 7. 查询持仓接口契约

### 7.1 查询参数（GET /api/positions）

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `symbol` | string | 否 | null | 币种对过滤（可选） |
| `include_closed` | boolean | 否 | false | 是否包含已平仓位 |

### 7.2 响应 Schema（GET /api/positions）

```python
# src/domain/models.py

class PositionInfo(BaseModel):
    """持仓信息"""
    position_id: str = Field(..., description="系统持仓 ID")
    symbol: str = Field(..., description="币种对")
    direction: Direction = Field(..., description="方向")
    current_qty: Decimal = Field(..., description="当前数量")
    entry_price: Decimal = Field(..., description="开仓均价")
    mark_price: Optional[Decimal] = Field(None, description="标记价格")
    unrealized_pnl: Decimal = Field(default=Decimal("0"), description="未实现盈亏")
    realized_pnl: Decimal = Field(default=Decimal("0"), description="已实现盈亏")
    liquidation_price: Optional[Decimal] = Field(None, description="强平价")
    leverage: int = Field(..., description="杠杆倍数")
    margin_mode: str = Field(default="CROSS", description="保证金模式（CROSS/ISOLATED）")
    is_closed: bool = Field(default=False, description="是否已平仓")
    opened_at: int = Field(..., description="开仓时间戳（毫秒）")
    closed_at: Optional[int] = Field(None, description="平仓时间戳（毫秒）")
    total_fees_paid: Decimal = Field(default=Decimal("0"), description="累计手续费")
    strategy_name: Optional[str] = Field(None, description="策略名称")
    stop_loss: Optional[Decimal] = Field(None, description="止损价格")
    take_profit: Optional[Decimal] = Field(None, description="止盈价格")
    tags: List[dict] = Field(default_factory=list, description="动态标签列表")


class PositionResponse(BaseModel):
    """持仓列表响应"""
    positions: List[PositionInfo] = Field(..., description="持仓列表")
    total_unrealized_pnl: Decimal = Field(..., description="总未实现盈亏")
    total_realized_pnl: Decimal = Field(..., description="总已实现盈亏")
    total_margin_used: Decimal = Field(..., description="总占用保证金")
    account_equity: Optional[Decimal] = Field(None, description="账户权益")
```

| 字段（PositionInfo） | 类型 | 必填 | 说明 | TypeScript 类型 |
|---------------------|------|------|------|-----------------|
| `position_id` | string | 是 | 系统持仓 ID | `string` |
| `symbol` | string | 是 | 币种对 | `string` |
| `direction` | string | 是 | 方向 | `Direction` |
| `current_qty` | number | 是 | 当前数量 | `string` (Decimal) |
| `entry_price` | number | 是 | 开仓均价 | `string` (Decimal) |
| `mark_price` | number | 否 | 标记价格 | `string \| null` |
| `unrealized_pnl` | number | 是 | 未实现盈亏 | `string` (Decimal) |
| `realized_pnl` | number | 是 | 已实现盈亏 | `string` (Decimal) |
| `liquidation_price` | number | 否 | 强平价 | `string \| null` |
| `leverage` | number | 是 | 杠杆倍数 | `number` |
| `margin_mode` | string | 是 | 保证金模式 | `"CROSS" \| "ISOLATED"` |
| `is_closed` | boolean | 是 | 是否已平仓 | `boolean` |
| `opened_at` | number | 是 | 开仓时间戳 | `number` |
| `closed_at` | number | 否 | 平仓时间戳 | `number \| null` |
| `total_fees_paid` | number | 是 | 累计手续费 | `string` (Decimal) |
| `strategy_name` | string | 否 | 策略名称 | `string \| null` |
| `stop_loss` | number | 否 | 止损价格 | `string \| null` |
| `take_profit` | number | 否 | 止盈价格 | `string \| null` |
| `tags` | array | 是 | 动态标签列表 | `Tag[]` |

### 7.3 错误响应（GET /api/positions）

| 错误码 | HTTP 状态码 | 说明 | 前端处理方式 |
|--------|-------------|------|--------------|
| `F-004` | 503 | 交易所初始化失败 | toast 错误提示 |
| `C-010` | 429 | API 频率限制 | 指数退避重试 |

---

## 8. 查询账户接口契约

### 8.1 请求参数（GET /api/account）

无参数

### 8.2 响应 Schema（GET /api/account）

```python
# src/domain/models.py

class AccountBalance(BaseModel):
    """账户余额信息"""
    currency: str = Field(..., description="币种，如 'USDT'")
    total_balance: Decimal = Field(..., description="总余额")
    available_balance: Decimal = Field(..., description="可用余额")
    frozen_balance: Decimal = Field(..., description="冻结余额")
    unrealized_pnl: Decimal = Field(default=Decimal("0"), description="未实现盈亏")


class AccountResponse(BaseModel):
    """账户信息响应"""
    exchange: str = Field(..., description="交易所名称")
    account_type: str = Field(..., description="账户类型（FUTURES/SPOT/MARGIN）")
    balances: List[AccountBalance] = Field(..., description="各币种余额")
    total_equity: Decimal = Field(..., description="总权益（USDT）")
    total_margin_balance: Decimal = Field(..., description="总保证金余额")
    total_wallet_balance: Decimal = Field(..., description="总钱包余额")
    total_unrealized_pnl: Decimal = Field(..., description="总未实现盈亏")
    available_balance: Decimal = Field(..., description="可用余额（开仓用）")
    total_margin_used: Decimal = Field(..., description="已用保证金")
    account_leverage: int = Field(..., description="账户最大杠杆")
    last_updated: int = Field(..., description="最后更新时间戳（毫秒）")
```

| 字段 | 类型 | 必填 | 说明 | TypeScript 类型 |
|------|------|------|------|-----------------|
| `exchange` | string | 是 | 交易所名称 | `string` |
| `account_type` | string | 是 | 账户类型 | `"FUTURES" \| "SPOT" \| "MARGIN"` |
| `balances` | array | 是 | 各币种余额列表 | `AccountBalance[]` |
| `total_equity` | number | 是 | 总权益 | `string` (Decimal) |
| `total_margin_balance` | number | 是 | 总保证金余额 | `string` (Decimal) |
| `total_wallet_balance` | number | 是 | 总钱包余额 | `string` (Decimal) |
| `total_unrealized_pnl` | number | 是 | 总未实现盈亏 | `string` (Decimal) |
| `available_balance` | number | 是 | 可用余额 | `string` (Decimal) |
| `total_margin_used` | number | 是 | 已用保证金 | `string` (Decimal) |
| `account_leverage` | number | 是 | 账户最大杠杆 | `number` |
| `last_updated` | number | 是 | 最后更新时间戳 | `number` |

### 8.3 错误响应（GET /api/account）

| 错误码 | HTTP 状态码 | 说明 | 前端处理方式 |
|--------|-------------|------|--------------|
| `F-004` | 503 | 交易所初始化失败 | toast 错误提示 |
| `C-010` | 429 | API 频率限制 | 指数退避重试 |

---

## 9. 对账服务接口契约

### 9.1 请求体（POST /api/reconciliation）

```python
# src/domain/models.py

class ReconciliationRequest(BaseModel):
    """对账请求"""
    symbol: str = Field(..., description="币种对")
    full_check: bool = Field(default=False, description="是否全量检查（包含宽限期二次校验）")
```

| 字段 | 类型 | 必填 | 默认值 | 说明 | 前端对应字段 |
|------|------|------|--------|------|--------------|
| `symbol` | string | 是 | - | 币种对 | `symbol` |
| `full_check` | boolean | 否 | false | 是否全量检查 | `fullCheck` |

### 9.2 响应 Schema（POST /api/reconciliation）

```python
# src/domain/models.py

class PositionMismatch(BaseModel):
    """仓位不匹配记录"""
    symbol: str = Field(..., description="币种对")
    local_qty: Decimal = Field(..., description="本地记录数量")
    exchange_qty: Decimal = Field(..., description="交易所记录数量")
    discrepancy: Decimal = Field(..., description="差异数量")


class OrderMismatch(BaseModel):
    """订单不匹配记录"""
    order_id: str = Field(..., description="订单 ID")
    local_status: OrderStatus = Field(..., description="本地状态")
    exchange_status: str = Field(..., description="交易所状态")


class ReconciliationReport(BaseModel):
    """对账报告响应"""
    symbol: str = Field(..., description="币种对")
    reconciliation_time: int = Field(..., description="对账时间戳（毫秒）")
    grace_period_seconds: int = Field(..., description="宽限期秒数")

    # 仓位差异
    position_mismatches: List[PositionMismatch] = Field(default_factory=list, description="仓位不匹配列表")
    missing_positions: List[PositionInfo] = Field(default_factory=list, description="本地缺失的仓位")

    # 订单差异
    order_mismatches: List[OrderMismatch] = Field(default_factory=list, description="订单不匹配列表")
    orphan_orders: List[OrderResponse] = Field(default_factory=list, description="孤儿订单列表")

    # 对账结论
    is_consistent: bool = Field(..., description="是否一致（无差异）")
    total_discrepancies: int = Field(..., description="总差异数")
    requires_attention: bool = Field(..., description="是否需要人工介入")
    summary: str = Field(..., description="对账结论摘要")
```

| 字段 | 类型 | 必填 | 说明 | TypeScript 类型 |
|------|------|------|------|-----------------|
| `symbol` | string | 是 | 币种对 | `string` |
| `reconciliation_time` | number | 是 | 对账时间戳 | `number` |
| `grace_period_seconds` | number | 是 | 宽限期秒数 | `number` |
| `position_mismatches` | array | 是 | 仓位不匹配列表 | `PositionMismatch[]` |
| `missing_positions` | array | 是 | 本地缺失的仓位 | `PositionInfo[]` |
| `order_mismatches` | array | 是 | 订单不匹配列表 | `OrderMismatch[]` |
| `orphan_orders` | array | 是 | 孤儿订单列表 | `OrderResponse[]` |
| `is_consistent` | boolean | 是 | 是否一致 | `boolean` |
| `total_discrepancies` | number | 是 | 总差异数 | `number` |
| `requires_attention` | boolean | 是 | 是否需要人工介入 | `boolean` |
| `summary` | string | 是 | 对账结论摘要 | `string` |

### 9.3 错误响应（POST /api/reconciliation）

| 错误码 | HTTP 状态码 | 说明 | 前端处理方式 |
|--------|-------------|------|--------------|
| `F-004` | 503 | 交易所初始化失败 | toast 错误提示 |
| `C-010` | 429 | API 频率限制 | 指数退避重试 |

---

## 10. 资本保护检查契约

### 10.1 资本保护检查结果

```python
# src/domain/models.py

class CapitalProtectionCheckResult(BaseModel):
    """资本保护检查结果"""
    allowed: bool = Field(..., description="是否允许下单")
    reason: Optional[str] = Field(None, description="拒绝原因代码")
    reason_message: Optional[str] = Field(None, description="拒绝原因人类可读描述")

    # 详细检查结果
    single_trade_check: Optional[bool] = Field(None, description="单笔交易检查是否通过")
    position_limit_check: Optional[bool] = Field(None, description="仓位限制检查是否通过")
    daily_loss_check: Optional[bool] = Field(None, description="每日亏损检查是否通过")
    daily_count_check: Optional[bool] = Field(None, description="每日次数检查是否通过")
    balance_check: Optional[bool] = Field(None, description="余额检查是否通过")

    # 详细数据
    estimated_loss: Optional[Decimal] = Field(None, description="预计损失（USDT）")
    max_allowed_loss: Optional[Decimal] = Field(None, description="最大允许损失（USDT）")
    position_value: Optional[Decimal] = Field(None, description="仓位价值（USDT）")
    max_allowed_position: Optional[Decimal] = Field(None, description="最大允许仓位（USDT）")
    daily_pnl: Optional[Decimal] = Field(None, description="当日盈亏（USDT）")
    daily_trade_count: Optional[int] = Field(None, description="当日交易次数")
    available_balance: Optional[Decimal] = Field(None, description="可用余额（USDT）")
    min_required_balance: Optional[Decimal] = Field(None, description="最低保留余额（USDT）")
```

| 字段 | 类型 | 必填 | 说明 | TypeScript 类型 |
|------|------|------|------|-----------------|
| `allowed` | boolean | 是 | 是否允许下单 | `boolean` |
| `reason` | string | 否 | 拒绝原因代码 | `string \| null` |
| `reason_message` | string | 否 | 拒绝原因描述 | `string \| null` |
| `single_trade_check` | boolean | 否 | 单笔交易检查 | `boolean \| null` |
| `position_limit_check` | boolean | 否 | 仓位限制检查 | `boolean \| null` |
| `daily_loss_check` | boolean | 否 | 每日亏损检查 | `boolean \| null` |
| `daily_count_check` | boolean | 否 | 每日次数检查 | `boolean \| null` |
| `balance_check` | boolean | 否 | 余额检查 | `boolean \| null` |
| `estimated_loss` | number | 否 | 预计损失 | `string \| null` |
| `max_allowed_loss` | number | 否 | 最大允许损失 | `string \| null` |
| `position_value` | number | 否 | 仓位价值 | `string \| null` |
| `max_allowed_position` | number | 否 | 最大允许仓位 | `string \| null` |
| `daily_pnl` | number | 否 | 当日盈亏 | `string \| null` |
| `daily_trade_count` | number | 否 | 当日交易次数 | `number \| null` |
| `available_balance` | number | 否 | 可用余额 | `string \| null` |
| `min_required_balance` | number | 否 | 最低保留余额 | `string \| null` |

### 10.2 拒绝原因代码表

| 原因代码 | HTTP 状态码 | 说明 |
|----------|-------------|------|
| `SINGLE_TRADE_LOSS_LIMIT` | 400 | 单笔交易损失超限 |
| `POSITION_LIMIT` | 400 | 仓位占比超限 |
| `DAILY_LOSS_LIMIT` | 400 | 每日亏损超限 |
| `DAILY_TRADE_COUNT_LIMIT` | 400 | 每日交易次数超限 |
| `INSUFFICIENT_BALANCE` | 400 | 账户余额不足 |
| `CANNOT_ESTIMATE_MARKET_PRICE` | 400 | 无法获取市价预估 |
| `MISSING_PRICE` | 400 | 限价单缺少价格参数 |

---

## 11. 错误码系统扩展

### 11.1 FATAL 错误（F 系列）

| 错误码 | 说明 | 触发场景 | 处理方式 |
|--------|------|----------|----------|
| `F-001` | API Key 有交易权限 | 启动时权限校验 | 立即退出，检查 API 权限 |
| `F-002` | API Key 有提现权限 | 启动时权限校验 | 立即退出，检查 API 权限 |
| `F-003` | 必填配置缺失 | 配置加载失败 | 检查配置文件 |
| `F-004` | 交易所初始化失败 | 交易所连接失败 | 检查网络/密钥 |
| `F-010` | 保证金不足 | 下单前资本保护检查 | 充值或减仓 |
| `F-011` | 订单参数错误 | 下单参数验证失败 | 修正参数后重试 |
| `F-012` | 订单不存在 | 查询/取消不存在的订单 | 检查订单 ID |
| `F-013` | 订单已成交 | 取消已成交订单 | 无法取消，可平仓 |

### 11.2 CRITICAL 错误（C 系列）

| 错误码 | 说明 | 触发场景 | 处理方式 |
|--------|------|----------|----------|
| `C-001` | WebSocket 重连超限 | WS 断连超过最大重试次数 | 告警，检查网络 |
| `C-002` | 资产轮询连续失败 | 连续 N 次获取资产失败 | 告警，手动对账 |
| `C-010` | API 频率限制 | 触发交易所限流 | 指数退避重试 |

### 11.3 WARNING 错误（W 系列）

| 错误码 | 说明 | 触发场景 | 处理方式 |
|--------|------|----------|----------|
| `W-001` | K 线数据质量异常 | high < low 等数据异常 | 记录日志，忽略该 K 线 |
| `W-002` | 数据延迟超限 | 数据延迟超过阈值 | 记录日志，继续处理 |

---

## 12. TypeScript 类型定义（前端）

```typescript
// gemimi-web-front/src/types/order.ts

export enum Direction {
  LONG = "LONG",
  SHORT = "SHORT",
}

export enum OrderType {
  MARKET = "MARKET",
  LIMIT = "LIMIT",
  STOP_MARKET = "STOP_MARKET",
  STOP_LIMIT = "STOP_LIMIT",
}

export enum OrderRole {
  OPEN = "OPEN",
  CLOSE = "CLOSE",
}

export enum OrderStatus {
  PENDING = "PENDING",
  OPEN = "OPEN",
  FILLED = "FILLED",
  CANCELED = "CANCELED",
  REJECTED = "REJECTED",
  EXPIRED = "EXPIRED",
  PARTIALLY_FILLED = "PARTIALLY_FILLED",
}

export interface Tag {
  name: string;
  value: string;
}

export interface OrderRequest {
  symbol: string;
  order_type: OrderType;
  direction: Direction;
  role: OrderRole;
  amount: string; // Decimal as string
  price?: string;
  trigger_price?: string;
  reduce_only: boolean;
  client_order_id?: string;
  strategy_name?: string;
  stop_loss?: string;
  take_profit?: string;
}

export interface OrderResponse {
  order_id: string;
  exchange_order_id: string | null;
  symbol: string;
  order_type: OrderType;
  direction: Direction;
  role: OrderRole;
  status: OrderStatus;
  amount: string;
  filled_amount: string;
  price: string | null;
  trigger_price: string | null;
  average_exec_price: string | null;
  reduce_only: boolean;
  client_order_id: string | null;
  strategy_name: string | null;
  stop_loss: string | null;
  take_profit: string | null;
  created_at: number;
  updated_at: number;
  fee_paid: string;
  tags: Tag[];
}

export interface OrderCancelResponse {
  order_id: string;
  exchange_order_id: string | null;
  symbol: string;
  status: OrderStatus;
  canceled_at: number;
  message: string;
}

export interface PositionInfo {
  position_id: string;
  symbol: string;
  direction: Direction;
  current_qty: string;
  entry_price: string;
  mark_price: string | null;
  unrealized_pnl: string;
  realized_pnl: string;
  liquidation_price: string | null;
  leverage: number;
  margin_mode: "CROSS" | "ISOLATED";
  is_closed: boolean;
  opened_at: number;
  closed_at: number | null;
  total_fees_paid: string;
  strategy_name: string | null;
  stop_loss: string | null;
  take_profit: string | null;
  tags: Tag[];
}

export interface PositionResponse {
  positions: PositionInfo[];
  total_unrealized_pnl: string;
  total_realized_pnl: string;
  total_margin_used: string;
  account_equity: string | null;
}

export interface AccountBalance {
  currency: string;
  total_balance: string;
  available_balance: string;
  frozen_balance: string;
  unrealized_pnl: string;
}

export interface AccountResponse {
  exchange: string;
  account_type: "FUTURES" | "SPOT" | "MARGIN";
  balances: AccountBalance[];
  total_equity: string;
  total_margin_balance: string;
  total_wallet_balance: string;
  total_unrealized_pnl: string;
  available_balance: string;
  total_margin_used: string;
  account_leverage: number;
  last_updated: number;
}

export interface ReconciliationRequest {
  symbol: string;
  full_check?: boolean;
}

export interface PositionMismatch {
  symbol: string;
  local_qty: string;
  exchange_qty: string;
  discrepancy: string;
}

export interface OrderMismatch {
  order_id: string;
  local_status: OrderStatus;
  exchange_status: string;
}

export interface ReconciliationReport {
  symbol: string;
  reconciliation_time: number;
  grace_period_seconds: number;
  position_mismatches: PositionMismatch[];
  missing_positions: PositionInfo[];
  order_mismatches: OrderMismatch[];
  orphan_orders: OrderResponse[];
  is_consistent: boolean;
  total_discrepancies: number;
  requires_attention: boolean;
  summary: string;
}

export interface CapitalProtectionCheckResult {
  allowed: boolean;
  reason: string | null;
  reason_message: string | null;
  single_trade_check: boolean | null;
  position_limit_check: boolean | null;
  daily_loss_check: boolean | null;
  daily_count_check: boolean | null;
  balance_check: boolean | null;
  estimated_loss: string | null;
  max_allowed_loss: string | null;
  position_value: string | null;
  max_allowed_position: string | null;
  daily_pnl: string | null;
  daily_trade_count: number | null;
  available_balance: string | null;
  min_required_balance: string | null;
}
```

---

## 13. 类型对齐检查

### 13.1 后端 Pydantic Schema 位置

| 模型 | 文件路径 |
|------|----------|
| `Direction`, `OrderType`, `OrderStatus`, `OrderRole` | `src/domain/models.py` |
| `OrderRequest`, `OrderResponse`, `OrderCancelResponse` | `src/domain/models.py` |
| `PositionInfo`, `PositionResponse` | `src/domain/models.py` |
| `AccountBalance`, `AccountResponse` | `src/domain/models.py` |
| `ReconciliationRequest`, `ReconciliationReport` | `src/domain/models.py` |
| `CapitalProtectionCheckResult` | `src/domain/models.py` |

### 13.2 前端 TypeScript 类型位置

| 类型 | 文件路径 |
|------|----------|
| 所有类型 | `gemimi-web-front/src/types/order.ts` |

### 13.3 对齐检查表

| 字段 | 后端类型 | 前端类型 | 是否一致 |
|------|----------|----------|----------|
| `Direction` | `str, Enum` | `enum Direction` | ✅ |
| `OrderType` | `str, Enum` | `enum OrderType` | ✅ |
| `OrderStatus` | `str, Enum` | `enum OrderStatus` | ✅ |
| `OrderRole` | `str, Enum` | `enum OrderRole` | ✅ |
| `Decimal` | `decimal.Decimal` | `string` | ✅ (Decimal 序列化后为字符串) |
| `timestamp` | `int` | `number` | ✅ |
| `List[T]` | `list` | `T[]` | ✅ |
| `Optional[T]` | `T | None` | `T \| null` | ✅ |

---

## 14. 审查签字

| 角色 | 姓名 | 日期 | 签字 |
|------|------|------|------|
| Coordinator | | | |
| Backend Dev | | | |
| Frontend Dev | | | |
| QA Tester | | | |
| Code Reviewer | | | |

---

## 15. 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|------|------|----------|--------|
| v1.0 | 2026-03-30 | 初始版本 | |

---

## 附录 A：下单参数验证逻辑

```python
# src/application/order_validator.py

async def validate_order_request(request: OrderRequest) -> ValidationResult:
    """
    验证下单请求

    验证顺序:
    1. 基础参数验证（Pydantic 自动完成）
    2. 条件必填验证（LIMIT 需要 price，STOP 需要 trigger_price）
    3. 角色约束验证（CLOSE 必须 reduce_only=True）
    4. 资本保护验证（调用 CapitalProtectionManager）
    5. 交易所参数验证（最小数量、价格精度等）
    """

    # 2. 条件必填验证
    if request.order_type == OrderType.LIMIT and request.price is None:
        return ValidationResult(
            valid=False,
            error_code="F-011",
            error_message="LIMIT 订单必须指定价格"
        )

    if request.order_type == OrderType.STOP_MARKET and request.trigger_price is None:
        return ValidationResult(
            valid=False,
            error_code="F-011",
            error_message="STOP_MARKET 订单必须指定触发价"
        )

    # 3. 角色约束验证
    if request.role == OrderRole.CLOSE and not request.reduce_only:
        return ValidationResult(
            valid=False,
            error_code="F-011",
            error_message="平仓单必须设置 reduce_only=True"
        )

    # 4. 资本保护验证
    protection_result = await capital_protection.pre_order_check(
        symbol=request.symbol,
        order_type=request.order_type,
        amount=request.amount,
        price=request.price,
        trigger_price=request.trigger_price,
        stop_loss=request.stop_loss or Decimal("0"),
    )

    if not protection_result.allowed:
        return ValidationResult(
            valid=False,
            error_code=protection_result.reason,
            error_message=protection_result.reason_message
        )

    return ValidationResult(valid=True)
```

---

## 附录 B：订单状态机

```
                    ┌─────────────┐
                    │   PENDING   │ (创建订单)
                    └──────┬──────┘
                           │
            ┌──────────────┼──────────────┐
            │              │              │
            ▼              ▼              ▼
    ┌───────────────┐ ┌──────────┐  ┌───────────┐
    │    REJECTED   │ │   OPEN   │  │  EXPIRED  │
    │  (拒绝/失败)   │ │ (已挂单)  │  │  (过期)   │
    └───────────────┘ └────┬─────┘  └───────────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
    ┌───────────────────┐    │    ┌───────────┐
    │   PARTIALLY_FILLED│    │    │ CANCELED  │
    │    (部分成交)      │    │    │  (取消)   │
    └─────────┬─────────┘    │    └───────────┘
              │              │
              └──────────────┘
                     │
                     ▼
              ┌─────────────┐
              │    FILLED   │
              │   (已成交)   │
              └─────────────┘
```

---

**契约表创建完成**。此文档作为 Phase 5 实盘集成的 SSOT（唯一事实来源），后续开发、审查、测试均以此为准。
