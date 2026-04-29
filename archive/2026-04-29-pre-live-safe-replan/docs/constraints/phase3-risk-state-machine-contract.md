# Phase 3: 风控状态机 - 接口契约表

**版本**: 1.0
**创建日期**: 2026-03-30
**状态**: 待评审
**关联文档**: `docs/v3/step3.md` - 动态风控状态机详细设计

---

## 一、核心设计原则

### 1.1 触发时机

| 触发类型 | 时机 | 说明 |
|----------|------|------|
| **事件触发** | TP1 订单成交时 | 执行 Breakeven 推保护损 |
| **K 线触发** | 每根 K 线撮合完成后 | 执行 Trailing Stop 追踪 |

### 1.2 状态转移

```
初始状态 → TP1 成交 → Breakeven → Trailing Stop → 完全平仓
   │                        │
   │                        └─→ 阶梯频控保护
   └─→ SL 打损 → 平仓结束
```

### 1.3 核心红线

| 红线 | 说明 |
|------|------|
| **阶梯频控** | 新止损价必须比当前价高出阈值才更新，防止 API 限流 |
| **保护损底线** | LONG: 止损价 ≥ entry_price；SHORT: 止损价 ≤ entry_price |
| **数量对齐** | TP1 成交后，SL 数量必须 = Position.current_qty |
| **Reduce Only 约束** | 所有平仓订单 (TP/SL) 必须携带 reduceOnly=True，防止保证金不足错误 |
| **OCO 逻辑** | 当多个平仓单并存时，一个成交后自动撤销另一个 (模拟交易所 OCO) |

**Reduce Only / OCO 说明**:
- 实盘场景中，TP2 限价单与 SL 追踪单可能同时存在
- 若 TP1 (0.5 BTC) 成交后，仓位剩 0.5 BTC，此时 TP2 (0.5 BTC) 和 SL (0.5 BTC) 并存
- 交易所会认为你想卖出 1 BTC，报 `Insufficient Margin` 错误
- **解决方案**:
  - 实盘网关：所有平仓单必须设置 `reduceOnly=True`
  - 回测沙箱：当一个平仓单触发导致仓位归零时，自动 `CANCELED` 另一个订单

---

## 二、DynamicRiskManager 类定义

### 2.1 类签名

```python
class DynamicRiskManager:
    """
    动态风控状态机

    核心职责:
    1. 监听 TP1 成交事件，执行 Breakeven 推保护损
    2. 每根 K 线追踪高水位线，执行 Trailing Stop
    3. 阶梯频控，防止频繁更新止损单
    """
```

### 2.2 构造函数

```python
def __init__(
    self,
    trailing_percent: Decimal = Decimal('0.02'),     # 移动止损回撤容忍度 (默认 2%)
    step_threshold: Decimal = Decimal('0.005'),      # 阶梯阈值 (默认 0.5%)
)
```

### 2.3 核心方法

```python
def evaluate_and_mutate(
    self,
    kline: KlineData,
    position: Position,
    active_orders: List[Order],
) -> None:
    """
    每根 K 线撮合完成后调用此方法进行风控状态突变

    参数:
    - kline: 当前 K 线数据
    - position: 关联的仓位
    - active_orders: 活跃订单列表

    副作用:
    - 刷新 position.watermark_price (水位线价格)
    - TP1 成交时：修改 SL 单的 requested_qty/trigger_price/order_type
    - Trailing 时：更新 SL 单的 trigger_price
    """
```

### 2.4 内部方法

```python
def _apply_trailing_logic(
    self,
    position: Position,
    sl_order: Order,
) -> None:
    """
    执行带阶梯阈值的移动止盈计算

    参数:
    - position: 关联的仓位
    - sl_order: 止损单

    副作用:
    - 更新 sl_order.trigger_price (满足阶梯条件时)
    """

def _find_order_by_role(
    self,
    orders: List[Order],
    role: OrderRole,
) -> Optional[Order]:
    """
    查找指定角色的订单

    参数:
    - orders: 订单列表
    - role: 订单角色

    返回:
    - 匹配的订单，未找到返回 None
    """
```

---

## 三、触发条件与计算公式

### 3.1 TP1 成交 → Breakeven (推保护损)

**触发条件**: `tp1_order.status == OrderStatus.FILLED` AND `sl_order.order_type != OrderType.TRAILING_STOP`

**执行动作**:

| 动作 | 计算公式 | 说明 |
|------|----------|------|
| **对齐数量** | `sl_order.requested_qty = position.current_qty` | 与剩余仓位对齐 |
| **上移止损** | `sl_order.trigger_price = position.entry_price` | 移至开仓均价 |
| **属性变异** | `sl_order.order_type = OrderType.TRAILING_STOP` | 激活移动追踪 |
| **Reduce Only** | 所有平仓单设置 `reduceOnly=True` | 防止 TP2+SL 并存时保证金不足 |

**⚠️ 实盘约束 - Reduce Only / OCO**:
- TP1 成交后，系统中可能仍存在 TP2 限价单和 SL 追踪单
- 实盘网关必须给所有平仓单设置 `reduceOnly=True`
- 回测沙箱模拟 OCO：当一个平仓单导致仓位归零时，自动撤销另一个

---

### 3.1.1 回测时序声明 (Intra-bar Mutation)

**问题**: 单根 K 线内，TP1 成交后修改的 SL 价格，是否会立即触发？

**示例场景**:
```
K 线：开盘 65000 -> 冲高 68000 (触发 TP1) -> 暴跌 64000 (打穿开仓价 65000) -> 收盘 64500
- 撮合引擎先运行：TP1 被标记为 FILLED
- 风控状态机后运行：SL 价格上移至 65000 (Breakeven)
- 问题：64000 的低点已经打穿 65000，但这根 K 线不会再触发 SL
```

**架构定调**:
- 基于 Phase 2 的**极端悲观撮合原则 (SL 优先)**，逻辑自洽
- 假设：SL 优先于 TP1 发生，所以 TP1 触发时低点已经过去
- **时序声明**: TP1 成交引发的 SL 修改，仅在下一根 K 线 (T+1) 开始生效参与撮合

### 3.2 水位线 (Watermark) 更新

**LONG 仓位**:
```python
if kline.high > position.watermark_price:
    position.watermark_price = kline.high
```

**SHORT 仓位**:
```python
if kline.low < position.watermark_price:
    position.watermark_price = kline.low
```

**字段语义**:
- `watermark_price`: 抽象化的极值价格
  - LONG: 追踪入场后的**最高价** (High Watermark)
  - SHORT: 追踪入场后的**最低价** (Low Watermark)

### 3.3 Trailing Stop 计算

**LONG 仓位**:
```python
# 理论止损价 = 水位线 * (1 - trailing_percent)
theoretical_trigger = position.watermark_price * (Decimal('1') - self.trailing_percent)

# 阶梯判定：新止损价必须比当前价高出 step_threshold
min_required_price = current_trigger * (Decimal('1') + self.step_threshold)

if theoretical_trigger >= min_required_price:
    # 更新止损价，但不低于 entry_price
    sl_order.trigger_price = max(position.entry_price, theoretical_trigger)
```

**SHORT 仓位**:
```python
# 理论止损价 = 水位线 * (1 + trailing_percent)
theoretical_trigger = position.watermark_price * (Decimal('1') + self.trailing_percent)

# 阶梯判定：新止损价必须比当前价低于 step_threshold
min_required_price = current_trigger * (Decimal('1') - self.step_threshold)

if theoretical_trigger <= min_required_price:
    # 更新止损价，但不高于 entry_price
    sl_order.trigger_price = min(position.entry_price, theoretical_trigger)
```

---

## 四、数据 Schema 定义

### 4.1 输入 Schema

#### KlineData (复用现有模型)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| symbol | string | 是 | 交易对 |
| timeframe | string | 是 | 周期 |
| timestamp | int | 是 | 毫秒时间戳 |
| open | Decimal | 是 | 开盘价 |
| high | Decimal | 是 | 最高价 |
| low | Decimal | 是 | 最低价 |
| close | Decimal | 是 | 收盘价 |
| volume | Decimal | 是 | 成交量 |
| is_closed | boolean | 是 | K 线是否已收盘 |

#### Position (v3 模型)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | string | 是 | 仓位 ID |
| signal_id | string | 是 | 关联信号 ID |
| symbol | string | 是 | 交易对 |
| direction | Direction | 是 | 方向 (LONG/SHORT) |
| entry_price | Decimal | 是 | 开仓均价 |
| current_qty | Decimal | 是 | 当前数量 |
| watermark_price | Decimal | 是 | **水位线价格** (LONG: 入场后最高价 / SHORT: 入场后最低价) |
| realized_pnl | Decimal | 是 | 已实现盈亏 |
| is_closed | boolean | 是 | 是否已平仓 |

**字段语义说明**:
- `watermark_price`: 抽象化的极值价格追踪
  - LONG 仓位：追踪入场后的**最高价** (High Watermark)
  - SHORT 仓位：追踪入场后的**最低价** (Low Watermark)

#### Order (v3 模型)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | string | 是 | 订单 ID |
| signal_id | string | 是 | 关联信号 ID |
| order_type | OrderType | 是 | 订单类型 (STOP_MARKET/TRAILING_STOP/LIMIT/MARKET) |
| order_role | OrderRole | 是 | 订单角色 (ENTRY/TP1/SL) |
| direction | Direction | 是 | 方向 |
| requested_qty | Decimal | 是 | 请求数量 |
| trigger_price | Decimal | 否 | 触发价格 |
| price | Decimal | 否 | 限价 |
| status | OrderStatus | 是 | 订单状态 |
| filled_qty | Decimal | 是 | 已成交数量 |

### 4.2 输出 Schema

**方法返回**: `None` (直接修改订单和仓位对象)

**副作用**:
| 对象 | 字段 | 变更条件 |
|------|------|----------|
| Order (SL) | requested_qty | TP1 成交时 |
| Order (SL) | trigger_price | TP1 成交时 或 Trailing 触发时 |
| Order (SL) | order_type | TP1 成交时 → TRAILING_STOP |
| Position | highest_price_since_entry | K 线 high/low 刷新时 |

---

## 五、配置参数

### 5.1 RiskConfig 扩展

```python
class RiskConfig(BaseModel):
    """风控配置"""
    max_loss_percent: Decimal = Field(..., description="每笔交易最大亏损 (% of balance)")
    max_leverage: int = Field(..., ge=1, le=125, description="最大杠杆")

    # Phase 3 新增
    trailing_stop_enabled: bool = Field(default=True, description="是否启用移动止损")
    trailing_percent: Decimal = Field(default=Decimal('0.02'), description="移动止损回撤百分比 (2%)")
    step_threshold: Decimal = Field(default=Decimal('0.005'), description="阶梯阈值 (0.5%)")
```

### 5.2 参数说明

| 参数 | 默认值 | 说明 | 可调范围 |
|------|--------|------|----------|
| `trailing_percent` | 2% | 从最高价回撤 2% 后触发止损 | 0.5% ~ 5% |
| `step_threshold` | 0.5% | 新止损价必须比当前价高 0.5% 才更新 | 0.1% ~ 2% |

---

## 六、错误码定义

| 错误码 | 级别 | 说明 |
|--------|------|------|
| `C-020` | CRITICAL | 风控状态机初始化失败 |
| `C-021` | CRITICAL | Trailing Stop 计算溢出 |
| `W-020` | WARNING | 未找到 SL 订单 (风控裸奔) |
| `W-021` | WARNING | TP1 成交但未找到对应仓位 |
| `W-022` | WARNING | Trailing 计算后止损价低于 entry_price (LONG) |

---

## 七、测试用例清单

### 7.1 单元测试

| 测试 ID | 测试场景 | 预期结果 |
|---------|----------|----------|
| UT-001 | TP1 成交触发 Breakeven | SL 单 qty=current_qty, trigger=entry_price, type=TRAILING_STOP |
| UT-002 | LONG 仓位刷新水位线 | watermark_price 更新为 kline.high |
| UT-003 | SHORT 仓位刷新水位线 | watermark_price 更新为 kline.low |
| UT-004 | Trailing Stop 计算 (LONG) | theoretical_trigger = watermark * (1 - trailing%) |
| UT-005 | Trailing Stop 计算 (SHORT) | theoretical_trigger = watermark * (1 + trailing%) |
| UT-006 | 阶梯频控 - 不满足条件 | trigger_price 不更新 |
| UT-007 | 阶梯频控 - 满足条件 | trigger_price 更新 |
| UT-008 | 保护损底线 (LONG) | trigger_price ≥ entry_price |
| UT-009 | 保护损底线 (SHORT) | trigger_price ≤ entry_price |
| UT-010 | 已平仓仓位不处理 | evaluate_and_mutate 直接返回 |
| UT-011 | 无 SL 订单防御处理 | 直接返回，不抛异常 |
| UT-012 | Decimal 精度保护 | 所有计算无 float 污染 |
| UT-013 | Reduce Only 约束 | 平仓单携带 reduceOnly=True |

### 7.2 集成测试

| 测试 ID | 测试场景 | 预期结果 |
|---------|----------|----------|
| IT-001 | 完整交易流程：开仓 → TP1 → Breakeven → Trailing → 平仓 | 所有状态转移正确 |
| IT-002 | 直接 SL 打损 (无 TP1) | 正常平仓，无 Breakeven |
| IT-003 | 多笔 TP1 分批成交 | SL 数量逐次递减 |
| IT-004 | Trailing 多次触发 | 止损价阶梯式上移 |

---

## 八、与 Backtester 集成

### 8.1 调用时机

```python
for kline in klines:
    # 1. 策略引擎运算，生成信号和订单
    # ...

    # 2. 撮合引擎撮合订单
    mock_matching_engine.match_orders_for_kline(kline, all_active_orders, positions_map, account)

    # 3. 【新增】风控状态机评估与状态突变
    for position in active_positions:
        dynamic_risk_manager.evaluate_and_mutate(kline, position, all_active_orders)

    # 4. 净值采样
```

### 8.2 BacktestRequest 扩展

```python
# 新增字段
trailing_stop_enabled: bool = True
trailing_percent: Decimal = Decimal('0.02')
step_threshold: Decimal = Decimal('0.005')
```

---

## 九、验收标准

### 9.1 功能验收

- [ ] DynamicRiskManager 类实现完成
- [ ] TP1 成交后 Breakeven 逻辑正确
- [ ] Trailing Stop 计算正确
- [ ] 阶梯频控逻辑正确
- [ ] 保护损底线校验正确
- [ ] Reduce Only 约束实现 (实盘网关)
- [ ] OCO 逻辑实现 (回测沙箱)

### 9.2 测试验收

- [ ] 单元测试覆盖率 ≥ 95%
- [ ] 所有边界 case 测试通过
- [ ] 集成测试通过

### 9.3 代码质量

- [ ] 领域层纯净 (无 I/O 依赖)
- [ ] 所有金额计算使用 Decimal
- [ ] Code Review 通过

---

## 十、版本历史

| 版本 | 日期 | 变更说明 |
|------|------|----------|
| 1.0 | 2026-03-30 | 初始版本，基于 step3.md 设计 |
| 1.1 | 2026-03-30 | **修订**: 修复 Reviewer 审查问题 |

### v1.1 修订说明 (Reviewer 审查修复)

| 问题 | 修订内容 | 等级 |
|------|----------|------|
| **highest_price_since_entry 语义灾难** | 重命名为 `watermark_price`，LONG 追踪最高价/SHORT 追踪最低价 | L2 |
| **TP2 存在时的双重冻结问题** | 1.3 节新增 Reduce Only 约束和 OCO 逻辑说明 | L2 |
| **单根 K 线内的突变盲区** | 3.1.1 节新增回测时序声明：TP1 引发的 SL 修改 T+1 生效 | L2 |

---

## 附录 A: 状态转移图

```
┌─────────────────────────────────────────────────────────────────┐
│                    风控状态机状态转移图                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [初始状态]                                                      │
│     │                                                            │
│     │ TP1 成交                                                   │
│     ▼                                                            │
│  [Breakeven] ──────────────────────────────────┐                │
│     │                                          │                │
│     │ SL 类型变为 TRAILING_STOP                │ SL 打损         │
│     ▼                                          ▼                │
│  [Trailing Stop] ──────────────────────→ [平仓结束]             │
│     │                                                            │
│     │ 每根 K 线评估                                               │
│     └────────────────────────────────────────────────────────────┘
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 附录 B: 阶梯频控示意图

```
LONG 仓位 Trailing Stop 阶梯频控示例:

时间    最高价     理论止损价    当前止损价    是否更新
T1      70000      68600         64000         ✓ (68600 > 64000*1.005=64320)
T2      70500      69090         68600         ✓ (69090 > 68600*1.005=68943)
T3      70800      69384         69090         ✗ (69384 < 69090*1.005=69435)
T4      71500      70070         69090         ✓ (70070 > 69090*1.005=69435)

只有当理论止损价比当前止损价高出 step_threshold (0.5%) 时才更新
```
