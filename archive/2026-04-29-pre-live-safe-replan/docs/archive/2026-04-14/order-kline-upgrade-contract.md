# 订单详情页 K 线渲染 - TradingView 升级 (方案 C) - 接口契约表

> **创建日期**: 2026-04-02
> **版本**: v1.0
> **状态**: ✅ 后端已完成

---

## 1. 需求背景

**核心需求**: 订单的入场、出场、止盈、止损的**时间必须与实际 K 线时间精确对齐**，复原交易场景

**当前状态**:
- 信号详情页已使用 TradingView Lightweight Charts（可复用代码）
- 订单详情页使用 Recharts 折线图（待升级）

**参考实现**: `gemimi-web-front/src/components/SignalDetailsDrawer.tsx`

---

## 2. 接口设计

### 2.1 后端 API 扩展 ✅ 已完成

**端点**: `GET /api/v3/orders/{order_id}/klines`

**变更**: 新增 `include_chain` 参数，返回完整订单链数据

#### 请求参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `order_id` | string (路径) | ✅ | - | 系统订单 ID |
| `symbol` | string (查询) | ✅ | - | 币种对（用于交易所路由） |
| `include_chain` | boolean (查询) | ❌ | `true` | 是否返回关联订单链（TP/SL 子订单） |

#### 响应体 Schema

```typescript
{
  order: {
    order_id: string;              // 系统订单 ID
    exchange_order_id?: string;    // 交易所订单 ID
    symbol: string;                // 币种对
    order_type: OrderType;         // 订单类型
    order_role: OrderRole;         // 订单角色
    direction: Direction;          // 方向
    status: OrderStatus;           // 订单状态
    quantity: string;              // 订单数量 (Decimal 字符串)
    filled_qty: string;            // 已成交数量
    price?: string;                // 限价单价格
    trigger_price?: string;        // 条件单触发价
    average_exec_price?: string;   // 平均成交价
    filled_at?: number;            // 成交时间 (毫秒时间戳)
    created_at: number;            // 创建时间 (毫秒时间戳)
  };
  timeframe: string;               // K 线周期，如 "15m", "1h"
  klines: number[][];              // [[timestamp_ms, open, high, low, close, volume], ...]
  order_chain?: {                  // 订单链数据 (仅当 include_chain=true 时返回)
    entry: OrderChainItem;         // 入场订单
    take_profits: OrderChainItem[]; // 止盈订单列表
    stop_loss?: OrderChainItem;    // 止损订单
  };
}
```

#### `OrderChainItem` 定义

```typescript
interface OrderChainItem {
  order_id: string;           // 订单 ID
  order_role: OrderRole;      // 订单角色 (ENTRY/TP1/TP2/SL 等)
  direction: Direction;       // 方向
  price: string;              // 订单价格
  filled_qty: string;         // 成交数量
  average_exec_price?: string; // 平均成交价
  status: OrderStatus;        // 订单状态
  filled_at?: number;         // 成交时间 (毫秒时间戳)
  created_at: number;         // 创建时间
  exit_reason?: string;       // 平仓原因 (仅平仓单)
}
```

---

### 2.2 前端组件升级

**组件**: `gemimi-web-front/src/components/v3/OrderDetailsDrawer.tsx`

**变更**: 从 Recharts 升级为 TradingView Lightweight Charts

#### 核心功能需求

1. **TradingView 蜡烛图渲染**
   - 复用 `SignalDetailsDrawer.tsx` 的图表实现
   - 支持本地时区时间戳转换
   - 支持交互式十字光标

2. **订单链时间线可视化**
   - 使用 `SeriesMarker` 显示订单事件
   - 入场订单：箭头标记（绿色/红色）
   - 止盈/止损订单：圆形标记
   - 水平价格线：入场价、止盈价、止损价

3. **悬停 Tooltip**
   - 显示 K 线 OHLC 数据
   - 显示订单事件信息

---

## 3. 时间对齐核心逻辑

### 3.1 后端：K 线范围计算

```python
# 收集订单链中所有时间戳
timestamps = []
if order.filled_at:
    timestamps.append(order.filled_at)
else:
    timestamps.append(order.created_at)

# 如果 include_chain=true，收集子订单时间戳
if include_chain and order_chain:
    for child in order_chain:
        if child.filled_at:
            timestamps.append(child.filled_at)

# 计算时间范围
min_time = min(timestamps)
max_time = max(timestamps)

# 扩展范围：前后各多取 20 根 K 线
timeframe_ms = BacktestConfig.get_timeframe_ms(timeframe)
since = min_time - (20 * timeframe_ms)
limit = int((max_time - since) / timeframe_ms) + 40

# 获取 K 线数据
ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)
```

### 3.2 前端：时间戳转换与标记

```typescript
// 时区转换
const tzOffsetMs = new Date().getTimezoneOffset() * 60 * 1000;

// K 线数据转换
const klineData: CandlestickData[] = klines.map((k) => ({
  time: ((k[0] - tzOffsetMs) / 1000) as UTCTimestamp,
  open: k[1],
  high: k[2],
  low: k[3],
  close: k[4],
}));

// 订单标记
const markers: SeriesMarker[] = orderChain
  .filter(o => o.filled_at)
  .map(order => ({
    time: ((order.filled_at! - tzOffsetMs) / 1000) as UTCTimestamp,
    position: order.order_role === 'ENTRY' 
      ? (order.direction === 'LONG' ? 'belowBar' : 'aboveBar')
      : (order.direction === 'LONG' ? 'aboveBar' : 'belowBar'),
    color: getOrderRoleColor(order.order_role),
    shape: order.order_role === 'ENTRY' ? 'arrowUp' : 'circle',
    text: getOrderRoleLabel(order.order_role),
  }));
```

---

## 4. 颜色与样式规范

### 4.1 Apple Design 颜色

```typescript
const APPLE_GREEN = '#34C759';   // 涨/做多
const APPLE_RED = '#FF3B30';     // 跌/做空
const APPLE_GRAY = '#86868B';    // 中性/文本
const APPLE_BLUE = '#007AFF';    // 入场价/高亮
```

### 4.2 订单角色颜色

| 订单角色 | 颜色 | 说明 |
|----------|------|------|
| ENTRY (LONG) | `APPLE_GREEN` | 做多入场 |
| ENTRY (SHORT) | `APPLE_RED` | 做空入场 |
| TP1-5 | `APPLE_GREEN` | 止盈 |
| SL | `APPLE_RED` | 止损 |

### 4.3 水平价格线样式

| 价格类型 | 颜色 | 线型 | 说明 |
|----------|------|------|------|
| 入场价 | `APPLE_BLUE` | 点线 (style: 3) | 2px 宽度 |
| 止盈价 | `APPLE_GREEN` | 虚线 (style: 2) | 1px 宽度 |
| 止损价 | `APPLE_RED` | 虚线 (style: 2) | 1px 宽度 |

---

## 5. 数据流

```
┌─────────────────────────────────────────────────────────────────────────┐
│  前端：OrderDetailsDrawer.tsx                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  1. 用户打开订单详情                                             │    │
│  │  2. 调用 fetchOrderKlineContext(orderId, symbol, includeChain)   │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  后端：GET /api/v3/orders/{order_id}/klines                             │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  1. 从订单仓库获取主订单                                         │    │
│  │  2. 如果 include_chain=true，查询子订单链                        │    │
│  │  3. 计算 K 线范围 (覆盖完整交易生命周期)                          │    │
│  │  4. 从交易所获取 K 线数据                                         │    │
│  │  5. 返回 { order, order_chain, klines }                          │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  前端：TradingView 图表渲染                                             │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  1. 解析 K 线数据为 CandlestickData[]                            │    │
│  │  2. 创建蜡烛图系列                                               │    │
│  │  3. 创建订单标记 (SeriesMarker)                                  │    │
│  │  4. 创建水平价格线 (PriceLine)                                   │    │
│  │  5. 适配内容范围                                                 │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 6. 测试验收标准

### 6.1 后端测试

- [ ] 订单链查询 API 单元测试
- [ ] K 线范围计算准确性测试
- [ ] `include_chain` 参数覆盖测试
- [ ] 404 错误处理（订单不存在）

### 6.2 前端测试

- [ ] TradingView 图表渲染测试
- [ ] 订单标记位置准确性测试
- [ ] 水平价格线对齐测试
- [ ] 时区转换正确性测试
- [ ] 响应式布局测试

### 6.3 集成测试

- [ ] 订单时间线对齐验证
- [ ] 完整交易场景复原测试
- [ ] E2E 流程测试

---

## 7. 任务分解

### 后端任务 (3h) ✅ 已完成

| ID | 任务 | 负责人 | 状态 |
|----|------|--------|------|
| B1 | 扩展 `GET /api/v3/orders/{order_id}/klines` 接口 | 后端 | ✅ |
| B2 | 新增 `include_chain` 参数处理 | 后端 | ✅ |
| B3 | 实现订单链查询逻辑（通过 `parent_order_id`） | 后端 | ✅ |
| B4 | 动态计算 K 线范围 | 后端 | ✅ |
| B5 | 编写单元测试 | QA | ✅ |

**实现详情**:

1. **API 端点** (`src/interfaces/api.py:3786-3965`):
   - 新增 `include_chain: bool = Query(default=True)` 参数
   - 返回结构扩展：`{ order, timeframe, klines, order_chain? }`
   - K 线范围动态计算，覆盖完整订单链生命周期

2. **订单仓库方法** (`src/infrastructure/order_repository.py:689-768`):
   - `get_order_chain_by_order_id(order_id)` - 查询订单链
   - 支持从 ENTRY 或子订单查询完整链条
   - 按 `created_at` 升序返回

3. **单元测试**:
   - `test_order_repository.py`: T4-006 ~ T4-009 (订单链查询测试)
   - `test_order_klines_api.py`: UT-OKA-001 ~ UT-OKA-007 (API 端点测试)

### 前端任务 (3h)

| ID | 任务 | 负责人 | 状态 |
|----|------|--------|------|
| F1 | 将 OrderDetailsDrawer 升级为 TradingView 蜡烛图 | 前端 | ⏳ |
| F2 | 复用 SignalDetailsDrawer 的图表实现 | 前端 | ⏳ |
| F3 | 实现订单链时间线可视化（箭头 + 水平线） | 前端 | ⏳ |
| F4 | 实现悬停 Tooltip | 前端 | ⏳ |
| F5 | 编写组件测试 | QA | ⏳ |

---

## 8. 参考文件

- `gemimi-web-front/src/components/SignalDetailsDrawer.tsx` - TradingView 实现参考
- `src/interfaces/api.py:3786-3965` - K 线 API 实现
- `src/infrastructure/order_repository.py:689-768` - 订单链查询方法
- `docs/designs/phase6-v3-api-contract.md` - v3 API 契约
- `docs/products/p1-tasks-analysis-brief.md` - 产品需求文档

---

*契约表版本：v1.1*
*最后更新：2026-04-02*
*后端实现完成，待前端升级*
