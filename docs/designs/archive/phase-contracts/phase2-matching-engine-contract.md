# Phase 2: 撮合引擎 - 接口契约表

**版本**: 1.0
**创建日期**: 2026-03-30
**状态**: 待评审
**关联文档**: `docs/v3/step2.md` - 极端悲观撮合引擎详细设计

---

## 一、核心设计原则

### 1.1 撮合优先级法则

针对同一个 Position 关联的活跃订单，判定顺序必须严格遵循：

| 优先级 | 订单类型 | 说明 |
|--------|----------|------|
| **Top 1** | `STOP_MARKET` / `TRAILING_STOP` | 止损类订单 - 防守至上 |
| **Top 2** | `LIMIT` (OrderRole.TP1) | 止盈类订单 - 限价被动成交 |
| **Top 3** | `MARKET` (OrderRole.ENTRY) | 入场类订单 - 最后判定 |

### 1.2 滑点计算原则

- **无需跳空惩罚**，直接在触发价上加滑点
- 所有计算使用 `decimal.Decimal` 保证金融精度

---

## 二、MockMatchingEngine 类定义

### 2.1 类签名

```python
class MockMatchingEngine:
    """
    极端悲观撮合引擎 - K 线级撮合

    核心职责:
    1. 按优先级排序订单 (SL > TP > ENTRY)
    2. 检查订单触发条件
    3. 计算滑点后的执行价格
    4. 执行仓位和账户同步
    """
```

### 2.2 构造函数

```python
def __init__(
    self,
    slippage_rate: Decimal = Decimal('0.001'),      # 默认 0.1% 滑点
    fee_rate: Decimal = Decimal('0.0004'),          # 默认 0.04% 手续费
)
```

### 2.3 核心方法

```python
def match_orders_for_kline(
    self,
    kline: KlineData,
    active_orders: List[Order],
    positions_map: Dict[str, Position],
    account: Account,
) -> List[Order]:
    """
    K 线级悲观撮合入口

    参数:
    - kline: 当前 K 线数据 (包含 high/low/close/volume)
    - active_orders: 活跃订单列表 (状态为 OPEN)
    - positions_map: {signal_id: Position} 仓位映射表
    - account: 账户快照对象

    返回:
    - 已执行的订单列表 (status=FILLED)

    副作用:
    - 修改订单状态 (OPEN → FILLED)
    - 修改 Position (current_qty, realized_pnl)
    - 修改 Account (total_balance)
    """
```

### 2.4 内部方法

```python
def _sort_orders_by_priority(
    self,
    orders: List[Order],
) -> List[Order]:
    """
    按优先级排序订单

    排序规则:
    1. STOP_MARKET / TRAILING_STOP (优先级最高)
    2. LIMIT + OrderRole.TP1
    3. MARKET + OrderRole.ENTRY (优先级最低)
    """

def _execute_fill(
    self,
    order: Order,
    exec_price: Decimal,
    position: Optional[Position],  # ENTRY 单时 position 可能为 None
    account: Account,
    positions_map: Dict[str, Position],  # 仓位映射表 (ENTRY 单创建新仓位时使用)
    timestamp: int,  # 当前 K 线时间戳 (用于创建新仓位)
) -> None:
    """
    执行订单结算与仓位/账户同步

    参数:
    - order: 待执行的订单
    - exec_price: 执行价格 (已包含滑点)
    - position: 关联的仓位 (ENTRY 单时可为 None)
    - account: 账户快照
    - positions_map: {signal_id: Position} 仓位映射表 (ENTRY 单创建新仓位时使用)
    - timestamp: 当前 K 线时间戳 (用于创建新仓位)

    副作用:
    - order.status = FILLED
    - order.filled_qty = requested_qty
    - order.average_exec_price = exec_price

    # 入场单 (ENTRY): 开仓逻辑
    if order.order_role == OrderRole.ENTRY:
        if position is None:
            # 创建新仓位
            position = Position(...)
            positions_map[signal_id] = position
        position.current_qty += filled_qty
        position.entry_price = exec_price  # 新建仓位
        account.total_balance -= fee_paid  # 只扣除手续费

    # 平仓单 (TP1/SL): 平仓逻辑
    elif order.order_role in [OrderRole.TP1, OrderRole.SL]:
        # 防超卖保护：截断成交数量
        actual_filled = min(filled_qty, position.current_qty)
        position.current_qty -= actual_filled

        # 计算盈亏
        if position.direction == Direction.LONG:
            gross_pnl = (exec_price - position.entry_price) * actual_filled
        else:
            gross_pnl = (position.entry_price - exec_price) * actual_filled

        net_pnl = gross_pnl - fee_paid
        position.realized_pnl += net_pnl
        position.total_fees_paid += fee_paid

        if position.current_qty <= Decimal('0'):
            position.is_closed = True

        account.total_balance += net_pnl  # 盈亏计入账户
    """

    ⚠️ **实现限制说明**:
    - `entry_price` 采用简化处理：直接覆盖而非加权平均
    - 理由：当前回测场景中每次信号只开仓一次，无需处理加仓
    - 未来实盘如需支持加仓，应实现加权平均逻辑：
      ```python
      new_entry_price = (old_entry_price * old_qty + exec_price * new_qty) / (old_qty + new_qty)
      ```

def _cancel_related_orders(
    self,
    signal_id: str,
    active_orders: List[Order],
) -> List[Order]:
    """
    止损触发后，撤销该仓位关联的其他挂单

    参数:
    - signal_id: 信号 ID
    - active_orders: 活跃订单列表

    返回:
    - 被撤销的订单列表
    """
```

---

## 三、触发条件与滑点计算公式

### 3.1 止损单 (STOP_MARKET / TRAILING_STOP)

| 方向 | 触发条件 | 执行价格 |
|------|----------|----------|
| **LONG** | `kline.low <= trigger_price` | `trigger_price * (1 - slippage_rate)` |
| **SHORT** | `kline.high >= trigger_price` | `trigger_price * (1 + slippage_rate)` |

### 3.2 限价止盈单 (LIMIT + OrderRole.TP1)

| 方向 | 触发条件 | 执行价格 |
|------|----------|----------|
| **LONG** | `kline.high >= price` | `price` (限价单无滑点) |
| **SHORT** | `kline.low <= price` | `price` (限价单无滑点) |

### 3.3 入场单 (MARKET + OrderRole.ENTRY)

**核心原则**: 市价单 (MARKET) 无条件立即成交，不检查 trigger_price

| 方向 | 触发条件 | 执行价格 |
|------|----------|----------|
| **LONG** | **无条件触发** (K 线收盘时立即成交) | `kline.open * (1 + slippage_rate)` |
| **SHORT** | **无条件触发** (K 线收盘时立即成交) | `kline.open * (1 - slippage_rate)` |

**说明**:
- MARKET 入场单在 K 线 $T$ 结束时生成，在 K 线 $T+1$ 到来时无条件按开盘价成交
- 滑点方向：买入时向上滑点 (多付钱)，卖出时向下滑点 (少收钱)

---

## 四、数据 Schema 定义

### 4.1 输入 Schema

#### KlineData (复用现有模型)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| symbol | string | 是 | 交易对，如 "BTC/USDT:USDT" |
| timeframe | string | 是 | 周期，如 "15m", "1h" |
| timestamp | int | 是 | 毫秒时间戳 |
| open | DecimalString | 是 | 开盘价 |
| high | DecimalString | 是 | 最高价 |
| low | DecimalString | 是 | 最低价 |
| close | DecimalString | 是 | 收盘价 |
| volume | DecimalString | 是 | 成交量 |
| is_closed | boolean | 是 | K 线是否已收盘 |

#### Order (v3 新模型)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| order_id | string | 是 | 订单 ID (UUID) |
| signal_id | string | 是 | 关联信号 ID |
| type | OrderType | 是 | 订单类型 (MARKET/LIMIT/STOP_MARKET/TRAILING_STOP) |
| role | OrderRole | 是 | 订单角色 (ENTRY/TP1/SL) |
| side | OrderSide | 是 | 买卖方向 (BUY/SELL) |
| direction | Direction | 是 | 仓位方向 (LONG/SHORT) |
| trigger_price | DecimalString | 否 | 触发价格 (止损/止盈单) |
| price | DecimalString | 否 | 限价 (LIMIT 单) |
| requested_qty | DecimalString | 是 | 请求数量 |
| status | OrderStatus | 是 | 订单状态 (OPEN/FILLED/CANCELLED) |
| average_exec_price | DecimalString | 否 | 平均成交价 |
| filled_qty | DecimalString | 否 | 已成交数量 |

#### Position (v3 新模型)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| position_id | string | 是 | 仓位 ID (UUID) |
| signal_id | string | 是 | 关联信号 ID |
| direction | Direction | 是 | 仓位方向 (LONG/SHORT) |
| entry_price | DecimalString | 是 | 开仓均价 (**只读**，永不修改) |
| current_qty | DecimalString | 是 | 当前数量 |
| realized_pnl | DecimalString | 是 | 已实现盈亏 |
| total_fees_paid | DecimalString | 是 | 累计手续费 |
| is_closed | boolean | 是 | 是否已平仓 |

#### Account (v3 新模型)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| account_id | string | 是 | 账户 ID |
| total_balance | DecimalString | 是 | 总余额 |
| available_balance | DecimalString | 是 | 可用余额 |
| unrealized_pnl | DecimalString | 是 | 未实现盈亏 |

### 4.2 输出 Schema

#### 方法返回：List[Order]

已执行的订单列表，每个订单的以下字段被更新：

| 字段 | 类型 | 说明 |
|------|------|------|
| status | OrderStatus | OPEN → FILLED |
| filled_qty | DecimalString | 成交数量 |
| average_exec_price | DecimalString | 执行价格 (含滑点) |

---

## 五、PMSBacktestReport 模型

### 5.1 类定义

```python
class PMSBacktestReport(BaseModel):
    """
    v3 PMS 模式回测报告

    与 v2.0 回测报告的区别:
    - 基于真实仓位管理 (Position 实体)
    - 基于真实订单执行 (Order 实体)
    - 包含手续费和滑点影响
    - 支持多级别止盈统计
    """
```

### 5.2 字段定义

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| strategy_id | string | 是 | 策略 ID |
| strategy_name | string | 是 | 策略名称 |
| backtest_start | int | 是 | 回测开始时间戳 (ms) |
| backtest_end | int | 是 | 回测结束时间戳 (ms) |
| initial_balance | DecimalString | 是 | 初始资金 |
| final_balance | DecimalString | 是 | 最终余额 |
| total_return | DecimalString | 是 | 总收益率 (%) |
| total_trades | int | 是 | 总交易次数 |
| winning_trades | int | 是 | 盈利交易次数 |
| losing_trades | int | 是 | 亏损交易次数 |
| win_rate | DecimalString | 是 | 胜率 (%) |
| total_pnl | DecimalString | 是 | 总盈亏 (USDT) |
| total_fees_paid | DecimalString | 是 | 总手续费 |
| total_slippage_cost | DecimalString | 是 | 总滑点成本 |
| max_drawdown | DecimalString | 是 | 最大回撤 (%) |
| sharpe_ratio | DecimalString | 否 | 夏普比率 |
| positions | List[PositionSummary] | 是 | 仓位历史摘要 |

### 5.3 PositionSummary 子模型

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| position_id | string | 是 | 仓位 ID |
| signal_id | string | 是 | 信号 ID |
| symbol | string | 是 | 交易对 |
| direction | Direction | 是 | 方向 |
| entry_price | DecimalString | 是 | 开仓价 |
| exit_price | DecimalString | 否 | 平仓价 |
| entry_time | int | 是 | 开仓时间 |
| exit_time | int | 否 | 平仓时间 |
| realized_pnl | DecimalString | 是 | 已实现盈亏 |
| exit_reason | string | 否 | 平仓原因 (TP1/SL/TRAILING) |

---

## 六、Backtester 接口扩展

### 6.1 新增参数

**实际实现签名**:
```python
async def run_backtest(
    self,
    request: BacktestRequest,
    account_snapshot: Optional[AccountSnapshot] = None,
    repository = None,
) -> Union[BacktestReport, PMSBacktestReport]:
    """
    运行回测

    参数:
    - request: BacktestRequest 参数对象（包含 mode, initial_balance, slippage_rate, fee_rate 等）
    - account_snapshot: 可选的账户快照（用于回测仓位计算）
    - repository: SignalRepository 实例（用于保存回测信号）

    返回:
    - mode="v2_classic" → BacktestReport (v2.0 信号级统计)
    - mode="v3_pms" → PMSBacktestReport (v3.0 仓位级统计)
    """
```

**BacktestRequest 新增字段** (Phase 2):
| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| mode | Literal["v2_classic", "v3_pms"] | "v2_classic" | 回测模式 |
| initial_balance | Decimal | 10000 | v3_pms 模式初始资金 |
| slippage_rate | Decimal | 0.001 | v3_pms 模式滑点率 |
| fee_rate | Decimal | 0.0004 | v3_pms 模式手续费率 |

---

## 七、错误码定义

| 错误码 | 级别 | 说明 |
|--------|------|------|
| `C-010` | CRITICAL | 撮合引擎初始化失败 |
| `C-011` | CRITICAL | 订单优先级排序异常 |
| `C-012` | CRITICAL | 滑点计算溢出 |
| `W-010` | WARNING | 订单触发但仓位不存在 |
| `W-011` | WARNING | 订单执行后仓位数量为负 |

---

## 八、前端 Props (Phase 6 扩展)

> 当前阶段仅后端 + 测试，前端 Props 定义留空，待 Phase 6 补充。

---

## 九、测试用例清单

### 9.1 单元测试

| 测试 ID | 测试场景 | 预期结果 |
|---------|----------|----------|
| UT-001 | 止损单触发 (LONG) | 按 `low <= trigger` 触发，执行价 = trigger * (1 - slippage) |
| UT-002 | 止损单触发 (SHORT) | 按 `high >= trigger` 触发，执行价 = trigger * (1 + slippage) |
| UT-003 | TP1 限价单触发 (LONG) | 按 `high >= price` 触发，执行价 = price |
| UT-004 | TP1 限价单触发 (SHORT) | 按 `low <= price` 触发，执行价 = price |
| UT-005 | 订单优先级排序 | SL 订单排在 TP 和 ENTRY 之前 |
| UT-006 | _execute_fill 入场单 (ENTRY) | current_qty **增加**，entry_price 设置为 exec_price |
| UT-007 | _execute_fill 平仓单 (TP1/SL) | current_qty **减少**，realized_pnl 正确计算 |
| UT-008 | _execute_fill 开仓 PnL 计算 | ENTRY 单：net_pnl = **-fee_paid** (只扣手续费) |
| UT-009 | _execute_fill 平仓 PnL 计算 | TP/SL 单：net_pnl = gross_pnl - fee_paid |
| UT-010 | 防超卖保护 (requested_qty > current_qty) | filled_qty 被截断为 current_qty，防止仓位变负 |
| UT-011 | 止损后撤销关联订单 | TP1 挂单被撤销 |
| UT-012 | Decimal 精度保护 | 所有金额计算无 float 污染 |
| UT-013 | 边界 case: kline.low == trigger_price | 触发止损 |

### 9.2 集成测试

| 测试 ID | 测试场景 | 预期结果 |
|---------|----------|----------|
| IT-001 | v2/v3 回测对比 - 同一策略 | 结果差异可解释 (滑点/手续费) |
| IT-002 | 多级别止盈回测 | TP1 成交后，剩余仓位继续追踪 |
| IT-003 | 止损 + 止盈同时触发 | 止损优先 (悲观原则) |
| IT-004 | 完整回测流程 | PMSBacktestReport 包含所有字段 |

---

## 十、验收标准

### 10.1 功能验收

- [ ] MockMatchingEngine 类实现完成
- [ ] 订单优先级排序正确 (SL > TP > ENTRY)
- [ ] 滑点计算公式正确
- [ ] _execute_fill 正确更新 Position 和 Account
- [ ] PMSBacktestReport 模型完成
- [ ] Backtester 支持 mode="v3_pms"

### 10.2 测试验收

- [ ] 单元测试覆盖率 ≥ 95%
- [ ] 所有边界 case 测试通过
- [ ] v2/v3 回测对比报告完成

### 10.3 代码质量

- [ ] 领域层纯净 (无 I/O 依赖)
- [ ] 所有金额计算使用 Decimal
- [ ] Code Review 通过

---

## 版本历史

| 版本 | 日期 | 变更说明 |
|------|------|----------|
| 1.0 | 2026-03-30 | 初始版本，基于 step2.md 设计 |
| 1.1 | 2026-03-30 | **修订**: 修正 4 个逻辑硬伤 |
| 1.2 | 2026-03-30 | **修订**: 修复 Reviewer 审查问题 |

### v1.1 修订说明

| 问题 | 修订内容 |
|------|----------|
| **入场单触发逻辑矛盾** | 3.3 节修正：MARKET 入场单无条件按 `kline.open` 成交，不使用 trigger_price |
| **开仓 vs 平仓账本混淆** | 2.4 节修正：_execute_fill 区分 ENTRY (current_qty +=) 和 TP/SL (current_qty -=) |
| **PnL 计算时机错误** | 2.4 节修正：ENTRY 单 net_pnl = -fee_paid，TP/SL 单 net_pnl = gross_pnl - fee_paid |
| **缺少超卖边界测试** | 新增 UT-010：防超卖保护测试 (requested_qty > current_qty 时截断) |

### v1.2 修订说明 (Reviewer 审查修复)

| 问题 | 修订内容 | 等级 |
|------|----------|------|
| **_execute_fill 方法签名不一致** | 2.4 节更新：添加 `positions_map` 和 `timestamp` 参数说明 | L2 |
| **ENTRY 单 entry_price 简化处理** | 2.4 节添加实现限制说明，标注未来加仓场景的加权平均方案 | L2 |
| **run_backtest 方法签名不一致** | 6.1 节更新：反映实际使用 `BacktestRequest` 的设计 | L1 |
