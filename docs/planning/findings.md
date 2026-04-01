# 研究发现

> **说明**: 本文件记录有长期参考价值的技术发现、架构决策和踩坑记录。临时性发现已归档。

---

## 📑 目录

1. [P1/P2 问题修复技术细节](#p1p2-问题修复技术细节)
2. [P0-003/004 资金安全加固](#p0-003004-资金安全加固)
3. [Phase 6 前端架构](#phase-6-前端架构)
4. [API 契约与端点](#api-契约与端点)

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

## 历史发现归档

以下主题的技术发现已归档至 `archive/` 目录：
- P6-005: 账户净值曲线可视化
- P6-006: PMS 回测报告组件
- P6-007: 多级别止盈可视化
- Phase 6 详细架构分析

---

*最后更新：2026-04-01*
