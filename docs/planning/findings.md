# 研究发现

> **说明**: 本文件记录有长期参考价值的技术发现、架构决策和踩坑记录。临时性发现已归档。

---

## 📑 目录

1. [Phase 7 回测数据本地化架构](#phase-7-回测数据本地化架构)
2. [BTC 历史数据导入记录](#btc-历史数据导入记录)
3. [P1/P2 问题修复技术细节](#p1p2-问题修复技术细节)
4. [P0-003/004 资金安全加固](#p0-003004-资金安全加固)
5. [Phase 6 前端架构](#phase-6-前端架构)
6. [API 契约与端点](#api-契约与端点)

---

## Phase 7 回测数据本地化架构

### 核心设计定调 (2026-04-02)

**技术选型**:
| 层次 | 选型 | 理由 |
|------|------|------|
| **回测引擎** | 自研 MockMatchingEngine | 与 v3.0 实盘逻辑 100% 一致性 |
| **K 线存储** | SQLite | 统一技术栈、事务支持、数据量小 (150MB) |
| **读取策略** | 本地优先 + 自动补充 | 用户透明，首次缓存，后续 50x 加速 |

**为什么不使用 Parquet**:
- 数据量小 (150MB) → 无需列式存储优势
- 技术栈统一 → 与现有 SQLAlchemy ORM 一致
- 事务支持 → ACID 完整性，幂等写入

**数据流架构**:
```
Backtester → HistoricalDataRepository → SQLite (本地优先)
                                      ↓
                              ExchangeGateway (自动补充)
```

**预期性能提升**:
- 单次回测 (15m, 1 个月): 5s → 0.1s (50x)
- Optuna 调参 (100 trial): 2 小时 → 2 分钟 (60x)

详细设计文档：`docs/superpowers/specs/2026-04-02-backtest-data-localization-design.md`

---

## BTC 历史数据导入记录

### 导入汇总 (2026-04-02)

| 指标 | 结果 |
|------|------|
| **处理文件数** | 296 个 ZIP ✅ |
| **失败** | 0 ❌ |
| **总导入行数** | 285,877 行 |
| **数据库大小** | 56 MB |
| **时间跨度** | 2020-01 → 2026-02 (75 个月) |

**分周期统计**:
| 周期 | 记录数 | 说明 |
|------|--------|------|
| 15m | 216,096 | 主力回测周期 |
| 1h | 54,024 | MTF 过滤用 |
| 4h | 13,506 | MTF 过滤用 |
| 1d | 2,251 | 大周期趋势 |

**ETL 工具**:
- `scripts/etl/validate_csv.py` - CSV 验证工具
- `scripts/etl/etl_converter.py` - ETL 转换工具
- 支持：单个转换、ZIP 解压转换、批量转换

**数据库路径**: `data/backtests/market_data.db`

---

## P1/P2 问题修复技术细节

### P1-1: trigger_price 零值风险

**根本原因**: Python 的 falsy 判断陷阱

```python
# 问题代码
current_trigger = sl_order.trigger_price or position.entry_price

# 问题场景
sl_order.trigger_price = Decimal("0")  # 假设为 0
# current_trigger 会错误地使用 position.entry_price
```

**修复要点**:
- 显式 `is not None` 判断，避免 falsy 陷阱
- Decimal("0") 是合法的 trigger_price 值（虽然业务上不应该）

---

### P1-2: STOP_LIMIT 订单缺少价格偏差检查

**根本原因**: 订单类型判断不完整

```python
# 问题代码 (仅检查 LIMIT)
if order_type == OrderType.LIMIT and price is not None:
    price_check, ticker_price, deviation = await self._check_price_reasonability(...)
```

**修复要点**:
- STOP_LIMIT 订单的限价单部分同样需要价格合理性检查
- 使用 `in (OrderType.LIMIT, OrderType.STOP_LIMIT)` 判断

---

### P1-3: trigger_price 字段应从 CCXT 响应提取

**根本原因**: CCXT 字段映射不完整

**修复要点**:
- 多字段回退解析，适配不同交易所
- 使用 Decimal 精度转换

---

### P2-1: 魔法数字配置化

**优化方案**:
```python
class RiskManagerConfig(BaseModel):
    trailing_percent: Decimal = Decimal("0.02")
    step_threshold: Decimal = Decimal("0.005")
    breakeven_threshold: Decimal = Decimal("0.01")
```

**收益**: 支持配置管理、回测调优

---

### P2-2: 类常量移到配置文件

**优化方案**:
```yaml
# config/core.yaml
capital_protection:
  min_notional:
    binance: 5      # Binance 5 USDT
    bybit: 2        # Bybit 2 USDT
    okx: 5          # OKX 5 USDT
  price_deviation_threshold: "0.10"
  extreme_price_deviation_threshold: "0.20"
```

**收益**: 多交易所适配性提升

---

## P0-003/004 资金安全加固

### P0-004: 订单参数合理性检查

#### 1. 最小名义价值检查

**实现位置**: `src/application/capital_protection.py::_check_min_notional()`

**Binance 规则**:
- NOTIONAL: 名义价值 ≥ 5 USDT (部分币种 100 USDT)
- 公式：`notional_value = quantity * price`

**检查逻辑**:
```python
def _check_min_notional(
    self,
    quantity: Decimal,
    price: Decimal,
) -> tuple[bool, Decimal]:
    notional_value = quantity * price
    passed = notional_value >= self.MIN_NOTIONAL  # 5 USDT
    return passed, notional_value
```

**失败处理**: 拒绝订单，记录 W 级日志

---

#### 2. 价格合理性检查

**实现位置**: `src/application/capital_protection.py::_check_price_reasonability()`

**检查逻辑**:
```python
async def _check_price_reasonability(
    self,
    symbol: str,
    order_price: Decimal,
) -> tuple[bool, Decimal, Decimal]:
    ticker_price = await self._gateway.fetch_ticker_price(symbol)
    deviation = abs(order_price - ticker_price) / ticker_price
    
    # 正常行情：≤10%，极端行情：≤20%
    threshold = self.EXTREME_PRICE_DEVIATION_THRESHOLD if is_extreme else self.PRICE_DEVIATION_THRESHOLD
    passed = deviation <= threshold
    return passed, ticker_price, deviation
```

---

## Phase 6 前端架构

### 前端 API 调用层 (`web-front/src/lib/api.ts`)

**订单管理**:
```typescript
// POST /api/v3/orders (开仓)
async function createOrder(payload: OrderRequest): Promise<OrderResponse>

// GET /api/v3/orders (查询订单列表)
async function fetchOrders(params?: QueryParams): Promise<Order[]>

// POST /api/v3/orders/{id}/cancel (取消订单)
async function cancelOrder(orderId: string): Promise<OrderResponse>
```

**仓位管理**:
```typescript
// GET /api/v3/positions
async function fetchPositions(symbol?: string): Promise<PositionResponse>

// POST /api/v3/positions/{position_id}/close
async function closePosition(positionId: string): Promise<OrderResponse>
```

**账户管理**:
```typescript
// GET /api/v3/account/balance
async function fetchAccountBalance(): Promise<AccountResponse>

// GET /api/v3/account/snapshot
async function fetchAccountSnapshot(): Promise<AccountSnapshot>
```

---

## P0-005 Binance Testnet 验证 (2026-04-01)

### 验证结果：通过 ✅

**测试环境**: Binance Testnet  
**测试范围**: 订单执行、DCA、持仓管理、对账服务、WebSocket 推送

### 修复的问题

| 问题 | 修复文件 | 说明 |
|------|----------|------|
| 订单 ID 混淆 | `exchange_gateway.py` | `cancel_order` 和 `fetch_order` 使用 `exchange_order_id` 而非内部 UUID |
| leverage None 处理 | `exchange_gateway.py` | `int(leverage_val) if leverage_val is not None else 1` |
| cancel_order 参数 | `exchange_gateway.py` | 修复参数命名问题 |

### 对账服务发现

- **孤儿订单处理**: 发现 7 个孤儿订单 (交易所有 DB 无)
- **处理逻辑**: 导入 orphan entry order → 创建 missing signal
- **幽灵订单**: 无发现 (DB 有交易所无)

### WebSocket 验证

- ✅ 连接建立成功
- ✅ 订单状态实时更新
- ✅ 重连机制正常 (指数退避：1s → 2s → 4s → 8s → 16s → 32s)

---

## Phase 6 前端组件检查 (2026-04-01)

### 组件完成度：100%

| 组件 | 文件 | 状态 |
|------|------|------|
| 仓位管理页面 | `web-front/src/pages/Positions.tsx` | ✅ |
| 订单管理页面 | `web-front/src/pages/Orders.tsx` | ✅ |
| 回测报告组件 | `web-front/src/pages/PMSBacktest.tsx` | ✅ |
| 账户页面 | `web-front/src/pages/Account.tsx` | ✅ |
| 止盈可视化 | `TPChainDisplay.tsx` + `SLOrderDisplay.tsx` | ✅ |

### 发现的小问题

| 问题 | 优先级 | 修复建议 |
|------|--------|----------|
| Orders.tsx 日期筛选未传递给 API | P1 | 在 `fetchOrders` URL 参数中添加 `startDate`/`endDate` |
| Positions.tsx 类型一致性 | P3 | 验证 `totalUnrealizedPnl` 类型匹配 |

---

## Phase 6 E2E 测试验证 (2026-04-01)

### 测试结果：80/103 通过 (77.7%)

- **通过**: 80 (77.7%)
- **跳过**: 23 (22.3%) - 因 window 标记过滤
- **失败**: 0

### 核心功能验证状态

| 模块 | 测试数 | 状态 |
|------|--------|------|
| 回测服务 | 11 | ✅ |
| 配置验证 | 15 | ✅ |
| 真实交易所 API | 19 | ✅ |
| 完整业务链 | 9 | ✅ |
| 动态规则 | 10 | ✅ |

### 建议修复

在 `pytest.ini` 中注册自定义标记 (`window1`/`window2`/`window3`/`window4`/`e2e`)

---

## 历史发现归档

以下主题的技术发现已归档至 `archive/` 目录：
- P6-005: 账户净值曲线可视化
- P6-006: PMS 回测报告组件
- P6-007: 多级别止盈可视化
- Phase 6 详细架构分析

---

*最后更新：2026-04-01*
