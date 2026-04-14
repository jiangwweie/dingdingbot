# v3.0 核心模型 - 接口契约表

> **创建日期**: 2026-03-30
> **任务 ID**: Phase 1
> **Coordinator**: Team Coordinator

---

## 1. 概述

本契约表定义 v3.0 迁移 Phase 1（模型筑基）的核心数据模型，作为后续 Phase 2-6 开发的 SSOT。

**核心实体**:
- `Account` - 资产账户
- `Signal` - 策略信号
- `Order` - 交易订单
- `Position` - 核心仓位

**枚举类型**:
- `Direction` - 方向（LONG/SHORT）
- `OrderStatus` - 订单状态
- `OrderType` - 订单类型
- `OrderRole` - 订单角色

---

## 2. 枚举类型定义

### 2.1 Direction

| 值 | 说明 |
|------|------|
| `LONG` | 做多 |
| `SHORT` | 做空 |

### 2.2 OrderStatus

| 值 | 说明 | CCXT 对应 |
|------|------|----------|
| `PENDING` | 尚未发送到交易所 | - |
| `OPEN` | 挂单中 | `open` |
| `PARTIALLY_FILLED` | 部分成交 | `partially_filled` |
| `FILLED` | 完全成交 | `closed` |
| `CANCELED` | 已撤销 | `canceled` |
| `REJECTED` | 交易所拒单 | `rejected` |

### 2.3 OrderType

| 值 | 说明 | 使用场景 |
|------|------|---------|
| `MARKET` | 市价单 | 入场 |
| `LIMIT` | 限价单 | TP1 止盈 |
| `STOP_MARKET` | 条件市价单 | 初始止损 |
| `TRAILING_STOP` | 移动止损单 | Trailing 止盈 |

### 2.4 OrderRole

| 值 | 说明 |
|------|------|
| `ENTRY` | 入场开仓 |
| `TP1` | 第一目标位止盈（50%） |
| `SL` | 止损单（初始/移动） |

---

## 3. 核心模型定义

### 3.1 Account（资产账户）

```python
class Account(FinancialModel):
    account_id: str = "default_wallet"
    total_balance: Decimal = Field(default=Decimal('0'), description="钱包总余额")
    frozen_margin: Decimal = Field(default=Decimal('0'), description="冻结保证金")

    @property
    def available_balance(self) -> Decimal:
        return self.total_balance - self.frozen_margin
```

| 字段 | 类型 | 必填 | 默认值 | 说明 | TypeScript 类型 |
|------|------|------|--------|------|----------------|
| `account_id` | string | 是 | "default_wallet" | 账户 ID | string |
| `total_balance` | Decimal | 是 | 0 | 钱包总余额 | string |
| `frozen_margin` | Decimal | 是 | 0 | 冻结保证金 | string |
| `available_balance` | Decimal | 计算属性 | - | 可用余额 | string |

---

### 3.2 Signal（策略信号）

```python
class Signal(FinancialModel):
    id: str
    strategy_id: str
    symbol: str
    direction: Direction
    timestamp: int
    expected_entry: Decimal
    expected_sl: Decimal
    pattern_score: float
    is_active: bool = True
```

| 字段 | 类型 | 必填 | 说明 | TypeScript 类型 |
|------|------|------|------|----------------|
| `id` | string | 是 | 信号 ID | string |
| `strategy_id` | string | 是 | 触发策略名称 | string |
| `symbol` | string | 是 | 交易对 | string |
| `direction` | Direction | 是 | LONG/SHORT | "LONG" \| "SHORT" |
| `timestamp` | integer | 是 | 信号生成时间戳 | number |
| `expected_entry` | Decimal | 是 | 预期入场价 | string |
| `expected_sl` | Decimal | 是 | 预期止损价 | string |
| `pattern_score` | float | 是 | 形态评分 (0-1) | number |
| `is_active` | boolean | 是 | 信号是否活跃 | boolean |

---

### 3.3 Order（交易订单）

```python
class Order(FinancialModel):
    id: str
    signal_id: str
    exchange_order_id: Optional[str]
    symbol: str
    direction: Direction
    order_type: OrderType
    order_role: OrderRole
    price: Optional[Decimal]
    trigger_price: Optional[Decimal]
    requested_qty: Decimal
    filled_qty: Decimal = Decimal('0')
    average_exec_price: Optional[Decimal]
    status: OrderStatus = OrderStatus.PENDING
    created_at: int
    updated_at: int
    exit_reason: Optional[str]
```

| 字段 | 类型 | 必填 | 默认值 | 说明 | TypeScript 类型 |
|------|------|------|--------|------|----------------|
| `id` | string | 是 | - | 订单 ID | string |
| `signal_id` | string | 是 | - | 所属信号 ID | string |
| `exchange_order_id` | string | 否 | null | 交易所订单号 | string \| null |
| `symbol` | string | 是 | - | 交易对 | string |
| `direction` | Direction | 是 | - | 订单方向 | "LONG" \| "SHORT" |
| `order_type` | OrderType | 是 | - | 订单类型 | OrderType |
| `order_role` | OrderRole | 是 | - | 订单角色 | OrderRole |
| `price` | Decimal | 否 | null | 限价单价格 | string \| null |
| `trigger_price` | Decimal | 否 | null | 条件单触发价 | string \| null |
| `requested_qty` | Decimal | 是 | - | 委托数量 | string |
| `filled_qty` | Decimal | 是 | 0 | 成交数量 | string |
| `average_exec_price` | Decimal | 否 | null | 成交均价 | string \| null |
| `status` | OrderStatus | 是 | PENDING | 订单状态 | OrderStatus |
| `created_at` | integer | 是 | - | 创建时间戳 | number |
| `updated_at` | integer | 是 | - | 更新时间戳 | number |
| `exit_reason` | string | 否 | null | 出局原因 | string \| null |

---

### 3.4 Position（核心仓位）

```python
class Position(FinancialModel):
    id: str
    signal_id: str
    symbol: str
    direction: Direction
    entry_price: Decimal
    current_qty: Decimal
    highest_price_since_entry: Decimal
    realized_pnl: Decimal = Decimal('0')
    total_fees_paid: Decimal = Decimal('0')
    is_closed: bool = False
```

| 字段 | 类型 | 必填 | 默认值 | 说明 | TypeScript 类型 |
|------|------|------|--------|------|----------------|
| `id` | string | 是 | - | 仓位 ID | string |
| `signal_id` | string | 是 | - | 所属信号 ID | string |
| `symbol` | string | 是 | - | 交易对 | string |
| `direction` | Direction | 是 | - | 仓位方向 | "LONG" \| "SHORT" |
| `entry_price` | Decimal | 是 | - | 开仓均价（固定不变） | string |
| `current_qty` | Decimal | 是 | - | 当前持仓数量 | string |
| `highest_price_since_entry` | Decimal | 是 | - | 入场后最高价 | string |
| `realized_pnl` | Decimal | 是 | 0 | 已实现盈亏 | string |
| `total_fees_paid` | Decimal | 是 | 0 | 累计手续费 | string |
| `is_closed` | boolean | 是 | false | 是否已平仓 | boolean |

---

## 4. 数据库 Schema（SQLite/PostgreSQL）

### 4.1 表结构

```sql
-- accounts 表
CREATE TABLE accounts (
    account_id TEXT PRIMARY KEY,
    total_balance TEXT NOT NULL DEFAULT '0',
    frozen_margin TEXT NOT NULL DEFAULT '0',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

-- signals 表（扩展现有表）
CREATE TABLE signals (
    id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('LONG', 'SHORT')),
    timestamp INTEGER NOT NULL,
    expected_entry TEXT NOT NULL,
    expected_sl TEXT NOT NULL,
    pattern_score REAL NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

-- orders 表（新增）
CREATE TABLE orders (
    id TEXT PRIMARY KEY,
    signal_id TEXT NOT NULL REFERENCES signals(id),
    exchange_order_id TEXT,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('LONG', 'SHORT')),
    order_type TEXT NOT NULL,
    order_role TEXT NOT NULL,
    price TEXT,
    trigger_price TEXT,
    requested_qty TEXT NOT NULL,
    filled_qty TEXT NOT NULL DEFAULT '0',
    average_exec_price TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING',
    exit_reason TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

-- positions 表（新增）
CREATE TABLE positions (
    id TEXT PRIMARY KEY,
    signal_id TEXT NOT NULL REFERENCES signals(id),
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('LONG', 'SHORT')),
    entry_price TEXT NOT NULL,
    current_qty TEXT NOT NULL,
    highest_price_since_entry TEXT NOT NULL,
    realized_pnl TEXT NOT NULL DEFAULT '0',
    total_fees_paid TEXT NOT NULL DEFAULT '0',
    is_closed INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
```

### 4.2 索引设计

```sql
-- orders 表索引
CREATE INDEX idx_orders_signal_id ON orders(signal_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_symbol ON orders(symbol);

-- positions 表索引
CREATE INDEX idx_positions_signal_id ON positions(signal_id);
CREATE INDEX idx_positions_is_closed ON positions(is_closed);
CREATE INDEX idx_positions_symbol ON positions(symbol);

-- signals 表索引（现有）
CREATE INDEX idx_signals_symbol ON signals(symbol);
CREATE INDEX idx_signals_timestamp ON signals(timestamp);
```

---

## 5. API 端点预留（Phase 4+ 实现）

| 端点 | 方法 | 说明 | 阶段 |
|------|------|------|------|
| `/api/v3/accounts/{id}` | GET | 获取账户信息 | Phase 5 |
| `/api/v3/positions` | GET | 获取持仓列表 | Phase 5 |
| `/api/v3/positions/{id}` | GET | 获取持仓详情 | Phase 5 |
| `/api/v3/orders` | GET | 获取订单列表 | Phase 5 |
| `/api/v3/signals/{id}` | GET | 获取信号详情 | Phase 4 |

---

## 6. 类型对齐检查

### 6.1 后端 Pydantic Schema

```python
# src/domain/models.py
from __future__ import annotations
from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal
from typing import Optional, List
from enum import Enum

class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"

class OrderStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"

class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"
    TRAILING_STOP = "TRAILING_STOP"

class OrderRole(str, Enum):
    ENTRY = "ENTRY"
    TP1 = "TP1"
    SL = "SL"

class FinancialModel(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

class Account(FinancialModel):
    account_id: str = "default_wallet"
    total_balance: Decimal = Decimal('0')
    frozen_margin: Decimal = Decimal('0')

class Signal(FinancialModel):
    id: str
    strategy_id: str
    symbol: str
    direction: Direction
    timestamp: int
    expected_entry: Decimal
    expected_sl: Decimal
    pattern_score: float
    is_active: bool = True

class Order(FinancialModel):
    id: str
    signal_id: str
    exchange_order_id: Optional[str] = None
    symbol: str
    direction: Direction
    order_type: OrderType
    order_role: OrderRole
    price: Optional[Decimal] = None
    trigger_price: Optional[Decimal] = None
    requested_qty: Decimal
    filled_qty: Decimal = Decimal('0')
    average_exec_price: Optional[Decimal] = None
    status: OrderStatus = OrderStatus.PENDING
    created_at: int
    updated_at: int
    exit_reason: Optional[str] = None

class Position(FinancialModel):
    id: str
    signal_id: str
    symbol: str
    direction: Direction
    entry_price: Decimal
    current_qty: Decimal
    highest_price_since_entry: Decimal
    realized_pnl: Decimal = Decimal('0')
    total_fees_paid: Decimal = Decimal('0')
    is_closed: bool = False
```

### 6.2 前端 TypeScript 类型

```typescript
// web-front/src/types/v3-models.ts

export type Direction = 'LONG' | 'SHORT';

export type OrderStatus =
  | 'PENDING'
  | 'OPEN'
  | 'PARTIALLY_FILLED'
  | 'FILLED'
  | 'CANCELED'
  | 'REJECTED';

export type OrderType =
  | 'MARKET'
  | 'LIMIT'
  | 'STOP_MARKET'
  | 'TRAILING_STOP';

export type OrderRole = 'ENTRY' | 'TP1' | 'SL';

export interface Account {
  account_id: string;
  total_balance: string;
  frozen_margin: string;
  available_balance: string;
}

export interface Signal {
  id: string;
  strategy_id: string;
  symbol: string;
  direction: Direction;
  timestamp: number;
  expected_entry: string;
  expected_sl: string;
  pattern_score: number;
  is_active: boolean;
}

export interface Order {
  id: string;
  signal_id: string;
  exchange_order_id: string | null;
  symbol: string;
  direction: Direction;
  order_type: OrderType;
  order_role: OrderRole;
  price: string | null;
  trigger_price: string | null;
  requested_qty: string;
  filled_qty: string;
  average_exec_price: string | null;
  status: OrderStatus;
  created_at: number;
  updated_at: number;
  exit_reason: string | null;
}

export interface Position {
  id: string;
  signal_id: string;
  symbol: string;
  direction: Direction;
  entry_price: string;
  current_qty: string;
  highest_price_since_entry: string;
  realized_pnl: string;
  total_fees_paid: string;
  is_closed: boolean;
}
```

### 6.3 对齐检查表

| 字段 | 后端类型 | 前端类型 | 是否一致 |
|------|----------|----------|----------|
| Direction | `Direction` enum | `"LONG" \| "SHORT"` | ✅ |
| OrderStatus | `OrderStatus` enum | union type | ✅ |
| OrderType | `OrderType` enum | union type | ✅ |
| OrderRole | `OrderRole` enum | union type | ✅ |
| Decimal | `Decimal` | `string` | ✅ JSON 序列化 |
| all fields | Pydantic | TypeScript interface | ✅ |

---

## 7. 数据库迁移脚本

### 7.1 Alembic 迁移：001_unify_direction_enum.py

```python
"""统一 Direction 枚举为大写

Revision ID: 001
Create Date: 2026-05-01

"""
from alembic import op

def upgrade():
    # signals 表
    op.execute("UPDATE signals SET direction = UPPER(direction) WHERE direction IN ('long', 'short')")

    # signal_attempts 表
    op.execute("UPDATE signal_attempts SET direction = UPPER(direction) WHERE direction IN ('long', 'short')")

    # 添加检查约束
    op.execute("ALTER TABLE signals ADD CONSTRAINT check_direction CHECK (direction IN ('LONG', 'SHORT'))")

def downgrade():
    op.execute("UPDATE signals SET direction = LOWER(direction)")
    op.execute("UPDATE signal_attempts SET direction = LOWER(direction)")
```

### 7.2 SQLite 迁移：002_create_orders_positions.sql

```sql
-- 创建 orders 表
CREATE TABLE orders (
    id TEXT PRIMARY KEY,
    signal_id TEXT NOT NULL REFERENCES signals(id),
    exchange_order_id TEXT,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('LONG', 'SHORT')),
    order_type TEXT NOT NULL,
    order_role TEXT NOT NULL,
    price TEXT,
    trigger_price TEXT,
    requested_qty TEXT NOT NULL,
    filled_qty TEXT NOT NULL DEFAULT '0',
    average_exec_price TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING',
    exit_reason TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

-- 创建 positions 表
CREATE TABLE positions (
    id TEXT PRIMARY KEY,
    signal_id TEXT NOT NULL REFERENCES signals(id),
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('LONG', 'SHORT')),
    entry_price TEXT NOT NULL,
    current_qty TEXT NOT NULL,
    highest_price_since_entry TEXT NOT NULL,
    realized_pnl TEXT NOT NULL DEFAULT '0',
    total_fees_paid TEXT NOT NULL DEFAULT '0',
    is_closed INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

-- 创建索引
CREATE INDEX idx_orders_signal_id ON orders(signal_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_positions_is_closed ON positions(is_closed);
```

---

## 8. 审查签字

| 角色 | 姓名 | 日期 | 签字 |
|------|------|------|------|
| Coordinator | - | - | - |
| Backend Dev | - | - | - |
| Frontend Dev | - | - | - |
| QA Tester | - | - | - |
| Code Reviewer | - | - | - |

---

## 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|------|------|----------|--------|
| v1.0 | 2026-03-30 | 初始版本 | Coordinator |

---

*本契约表作为 v3.0 迁移 Phase 1 的 SSOT，后续所有开发、审查、测试均以此为准。*
