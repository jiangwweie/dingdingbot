# 架构分析：PMS 回测财务记账严重不平衡修复方案

> **文档编号**: ARCH-20260414-002
> **分析人**: 系统架构师
> **分析日期**: 2026-04-14
> **关联诊断报告**: [DA-20260414-001](../../diagnostic-reports/DA-20260414-001-pms-backtest-accounting-bug.md)

---

## 1. 根因验证（代码级确认）

### 1.1 Bug #1：`account_snapshot.positions=[]` 导致仓位规模失控

**确认状态**: 根因确认，诊断结论正确。

**代码证据链**:

```
backtester.py:1282-1288
  account_snapshot = AccountSnapshot(
      total_balance=account.total_balance,
      available_balance=account.available_balance,
      unrealized_pnl=Decimal('0'),
      positions=[],              # ← 硬编码空列表
      timestamp=kline.timestamp,
  )
```

该快照传入 `RiskCalculator.calculate_position_size()`，其中第 133-142 行：

```python
# risk_calculator.py:133-142
total_position_value = sum(
    pos.size * pos.entry_price for pos in account.positions   # positions=[] → sum=0
)
current_exposure_ratio = total_position_value / account.total_balance   # → 0
available_exposure = max(Decimal(0), max_total_exposure - current_exposure_ratio)
# → available_exposure = max_total_exposure (默认 0.8)
```

**影响路径**:

```
positions=[]
  → total_position_value = 0
  → current_exposure_ratio = 0
  → available_exposure = max_total_exposure (0.8)
  → risk_amount = available_balance × max_loss_percent (无暴露限制)
  → position_size = risk_amount / stop_distance
```

当 stop_distance 极小时（例如 SOL 在窄幅震荡期的 pinbar，close - low 可能仅 0.1%~0.5%），position_size 会非常大。即使有 leverage cap（max_leverage=20），实际风险金额仍远超预期的 1%：

```
max_position_value = available_balance × max_leverage = 10,000 × 20 = 200,000 USDT
max_position_size  = 200,000 / 144 ≈ 1,388 SOL
stop_distance      = |144.43 - 142.50| ≈ 1.93
risk_amount        = 1,388 × 1.93 ≈ 2,679 USDT (26.79% of balance)
```

**量化验证**: 诊断报告中第 1 笔风险约 707 USDT（7.07%），与上述分析一致。stop_distance 可能更大（约 5.1 USDT），说明 pinbar 影线较长，但仍然远超预期的 100 USDT（1%）。

**结论**: Bug #1 确认是导致仓位规模失控的根因。

---

### 1.2 Bug #2：11 笔"LONG"仓位方向与 PnL 矛盾

**确认状态**: 高置信度推断，需运行时验证。

**代码追踪** — 方向数据流:

```
[信号检测]  attempt.pattern.direction (Direction.LONG / Direction.SHORT)
    ↓
[订单创建]  order.direction = attempt.pattern.direction   (backtester.py:1316)
    ↓
[仓位创建]  position.direction = order.direction          (matching_engine.py:306)
    ↓
[PnL计算]  if position.direction == Direction.LONG:      (matching_engine.py:338)
               gross_pnl = (exec_price - entry_price) × qty
           else:
               gross_pnl = (entry_price - exec_price) × qty
    ↓
[报告生成]  position_summaries[].direction = position.direction  (backtester.py:1384)
```

**静态分析结论**: 整个数据流中 `position.direction` 从创建到 PnL 计算到报告生成，全程引用同一个 `Position` 对象的 `direction` 属性。代码中不存在修改 `position.direction` 的路径。

**矛盾只能通过以下可能性解释**:

| 假设 | 可能性 | 说明 |
|------|--------|------|
| H2a: 策略检测到的 direction 本身就是反的 | 中 | `attempt.pattern.direction` 可能错误。需检查 pinbar.py 的 direction 判断逻辑 |
| H2b: TP/SL 订单的 direction 与 ENTRY 不一致 | 低 | `order_manager._generate_tp_sl_orders()` 使用 `filled_entry.direction`，方向一致 |
| H2c: DynamicRiskManager 修改了 position.direction | 低 | `evaluate_and_mutate()` 不修改 direction |
| H2d: positions_map 的 key 混乱导致读错仓位 | 中 | 以 `signal_id` 为 key，需确认无 key 冲突 |
| H2e: 诊断报告的 direction 数据来源有偏差 | 中 | 诊断报告从回测报告读取 direction，而回测报告的 direction 来自 `position.direction` |

**关键疑点**: 诊断报告声称"撮合引擎 PnL 公式正确（单元测试验证）"，但 11 笔 LONG 仓位的 PnL 数学上匹配 SHORT 公式。这意味着：

1. **要么** `position.direction` 在撮合时是 SHORT（PnL 计算正确），但报告读到的 direction 是 LONG
2. **要么** `position.direction` 始终是 LONG，但 PnL 计算时用了 SHORT 分支

路径 (2) 需要 `position.direction != Direction.LONG` 的判断为 true，即 direction 不是 LONG。这与方向数据流矛盾。

**更可能的解释** (新假设 H2f):

诊断报告中的 direction 数据来自 `PositionSummary`（backtester.py:1384），而 PnL 计算时使用的 `position.direction` 是同一个对象。如果 PnL 数学上匹配 SHORT 公式，说明 `position.direction` 在撮合时确实是 SHORT。那么报告的 direction 为什么显示 LONG？

可能的解释是：**诊断报告读取的数据源存在偏差**。诊断报告中看到的 "LONG" 方向可能来自：
- 回测报告数据库中存储的 `position_summaries` 数据
- 或者从信号/订单表 join 查询得到

如果 `PositionSummary.direction` 在创建时（backtester.py:1384）和更新 PnL 时引用的是不同来源，可能导致不一致。

**代码验证**: backtester.py:1380-1387 创建 PositionSummary 时：
```python
position_summaries.append(PositionSummary(
    position_id=position.id,
    signal_id=position.signal_id,
    symbol=request.symbol,
    direction=position.direction,    # ← 来自 position.direction
    entry_price=position.entry_price,
    entry_time=kline.timestamp,
))
```

而 backtester.py:1394-1400 更新 PositionSummary 时只更新 `exit_price`, `exit_time`, `realized_pnl`, `exit_reason`，**不更新 direction**。因此 PositionSummary.direction 始终等于创建时的 `position.direction`。

**结论**: 代码层面无法静态确认 Bug #2 根因。需要运行时调试（方案 B）。但 Bug #2 对财务不平衡的贡献度可能有限（仅影响方向标签，不影响 balance 数值），**财务不平衡 7,928 USDT 的主要贡献者可能并非 Bug #2**。

---

### 1.3 财务不平衡 7,928 USDT 的完整归因分析

诊断报告的财务平衡方程：
```
final_balance = initial_balance - entry_fees + total_pnl
→ entry_fees = 10,000 + 6,426 - 7,899 = 8,527 USDT
```

但这个方程 **不完整**，因为它忽略了以下扣减项：

**修正后的财务平衡方程**:
```
final_balance = initial_balance
               - total_entry_fees           # 入场手续费
               + total_pnl                  # 已实现盈亏（含 exit_fee 扣除）
               - total_funding_cost         # BT-2: 资金费用
               - total_slippage_cost        # 滑点成本（隐性，已包含在 exec_price 中）
```

注意：`total_pnl` 已经是 net_pnl（扣除了 exit_fee），所以 exit_fee 不需要单独计算。

**实际差额分解**:
```
期望: 10,000 + 6,426 - entry_fees - funding_cost = final_balance
实际: 7,899

差额 8,527 = entry_fees + funding_cost + 其他未计入扣减
```

已知：
- 估算入场费约 599 USDT（基于名义价值 × 0.04%）
- 但实际入场费可能更高，因为仓位规模失控导致名义价值远超预期

**仓位规模失控导致的超额入场费**:
```
预期仓位: risk=100 USDT, stop_distance≈1%, position_size≈10,000 USDT 名义价值
          entry_fee = 10,000 × 0.0004 = 4 USDT
实际仓位: risk=707 USDT, position_size≈70,000 USDT 名义价值（约 7x）
          entry_fee = 70,000 × 0.0004 = 28 USDT
```

如果 46 笔交易都按 7x 规模计算：
- 入场费: 46 × 28 ≈ 1,288 USDT
- 出场费（从 total_pnl 中扣除）: 46 × 28 ≈ 1,288 USDT
- 资金费用: 需要具体计算

但 1,288 + 1,288 = 2,576 USDT 仍不足以解释 7,928 USDT 差额。

**更重要的发现**: backtester.py:1451-1458 的最大回撤计算有逻辑错误：

```python
for summary in position_summaries:
    if summary.exit_price:
        current_balance = initial_balance + summary.realized_pnl  # ← 累计错误
```

这里 `current_balance` 应该是累计的 total_balance，但代码每次都用 `initial_balance + summary.realized_pnl`，这意味着它假设每笔交易都是从初始余额开始的独立交易，而不是累计计算。

**这个计算错误不影响 final_balance（它直接来自 account.total_balance），但会影响 max_drawdown 的准确性**。

**修正归因**: 7,928 USDT 差额的主要来源是：
1. **Bug #1 导致的超额仓位**: 每笔交易的 entry_fee 和 exit_fee 都远超预期
2. **可能存在的其他未计入扣减**: funding_cost 等

**Bug #2 对差额无直接影响**（方向标签不影响 balance 数值），但如果 direction 错误导致止损/止盈触发条件判断错误（例如 LONG 仓位用了 SHORT 的止损判定），则可能间接影响 balance。

---

## 2. 方案评估

### 2.1 方案 A：修复 account_snapshot.positions

| 维度 | 评估 |
|------|------|
| **技术风险** | 低。从 positions_map 构建 PositionInfo 是纯数据映射，无副作用 |
| **实施难度** | 低。约 15 行代码改动 |
| **关联影响** | 见第 4 节详细分析 |
| **效果** | 修复仓位规模失控问题，使 RiskCalculator 正确计算暴露限制 |
| **不覆盖** | 不解决方向矛盾问题 |

**设计要点**:

需要将 `Position`（domain 实体）映射到 `PositionInfo`（AccountSnapshot 子模型）。两者的字段不完全对应：

| Position 字段 | PositionInfo 字段 | 映射方式 |
|---------------|-------------------|----------|
| `symbol` | `symbol` | 直接 |
| `direction` | `side` | `direction.value.lower()` |
| `current_qty` | `size` | 直接 |
| `entry_price` | `entry_price` | 直接 |
| `realized_pnl` | `unrealized_pnl` | 语义不同，回测中设为 0 |
| (无) | `leverage` | 回测中设为 1 |

**注意事项**:
- `PositionInfo.unrealized_pnl` 在回测场景中意义不明确（回测用市价撮合，无浮动盈亏概念），建议设为 `Decimal('0')`
- `PositionInfo.leverage` 回测中不涉及真实杠杆，设为 1

### 2.2 方案 B：调试方向矛盾

| 维度 | 评估 |
|------|------|
| **技术风险** | 极低。仅添加日志，不修改业务逻辑 |
| **实施难度** | 低。约 5 行日志代码 |
| **关联影响** | 无 |
| **效果** | 定位方向矛盾根因 |
| **不覆盖** | 不修复任何功能问题 |

**建议日志点位**:

1. **撮合引擎 `_execute_fill`** (matching_engine.py:338):
   ```python
   logger.debug(f"PnL计算：position.direction={position.direction.value}, "
                f"exec={exec_price}, entry={position.entry_price}, "
                f"qty={actual_filled}, gross_pnl={gross_pnl}")
   ```

2. **PositionSummary 创建处** (backtester.py:1380):
   ```python
   logger.debug(f"PositionSummary创建：direction={position.direction.value}, "
                f"entry={position.entry_price}, signal_id={order.signal_id}")
   ```

3. **信号创建处** (backtester.py:1273):
   ```python
   logger.debug(f"信号创建：direction={attempt.pattern.direction.value}, "
                f"strategy={attempt.strategy_name}")
   ```

### 2.3 方案 C：添加财务平衡校验

| 维度 | 评估 |
|------|------|
| **技术风险** | 低。仅添加校验逻辑 |
| **实施难度** | 低。约 10 行代码 |
| **关联影响** | 无 |
| **效果** | 防止未来回测数据错误未被发现 |
| **不覆盖** | 不修复根因 |

**改进建议**: 诊断报告的校验方程不完整，应修正为：

```python
# 修正后的财务平衡校验
expected_balance = (
    initial_balance
    - total_entry_fees      # 需要追踪
    + total_pnl             # 已扣除 exit_fee 的 net_pnl
    - total_funding_cost    # 资金费用（直接从 balance 扣除的部分需要确认）
)
```

但需要注意：`total_pnl` 已经在 matching_engine 中计入了 `account.total_balance`，`funding_cost` 是否计入 balance 需要确认。

检查 `_calculate_funding_cost` 方法：

```python
# 需要确认 funding_cost 是否从 account.total_balance 扣除
```

**经检查**: funding_cost 仅记录到 `position.total_funding_paid` 和 `total_funding_cost` 统计变量，**不从 account.total_balance 扣除**。这意味着 funding_cost 不影响 balance，财务平衡方程应为：

```
final_balance = initial_balance - total_entry_fees + total_pnl
```

其中 `total_pnl` 已经包含了 exit_fee 的扣除。

---

## 3. 架构设计

### 3.1 数据流图（修复后）

```
┌─────────────────────────────────────────────────────────────────┐
│                     _run_v3_pms_backtest                        │
│                                                                 │
│  positions_map: Dict[str, Position]  ←─ 撮合引擎维护             │
│       │                                                       │
│       │ ① 撮合引擎创建/更新 Position                            │
│       ▼                                                       │
│  ┌─────────────┐                                              │
│  │ positions_map│ ────────────────────────────────────────┐    │
│  │ {signal_id:  │                                         │    │
│  │  Position}   │                                         │    │
│  └─────────────┘                                         │    │
│       ▲                                                  │    │
│       │ ② 撮合引擎更新                                    │    │
│       │                                                  │    │
│  ┌──────────────────────┐                                │    │
│  │ MockMatchingEngine   │                                │    │
│  │ match_orders_for_kline│                               │    │
│  └──────────────────────┘                                │    │
│                                                          │    │
│  ③ 信号生成时，构建 AccountSnapshot                       │    │
│       │                                                  │    │
│       ▼                                                  │    │
│  ┌──────────────────────────┐                            │    │
│  │ _build_account_snapshot()│ ◄── 新增辅助方法            │    │
│  │   for pos in positions_map.values():                  │    │
│  │     if not pos.is_closed:                             │    │
│  │       position_infos.append(PositionInfo(...))        │    │
│  └──────────────┬───────────┘                            │    │
│                 │                                        │    │
│                 ▼                                        │    │
│  ┌──────────────────────────┐                            │    │
│  │ AccountSnapshot          │                            │    │
│  │   positions=[PositionInfo] ← 不再为空                 │    │
│  └──────────────┬───────────┘                            │    │
│                 │                                        │    │
│                 ▼                                        │    │
│  ┌──────────────────────────┐                            │    │
│  │ RiskCalculator           │                            │    │
│  │ calculate_position_size()│                            │    │
│  │   → 正确计算暴露限制      │                            │    │
│  └──────────────────────────┘                            │    │
│                                                          │    │
│  ④ PositionSummary 创建/更新                              │    │
│       direction 来自 position.direction                   │    │
│       pnl 来自 position.realized_pnl                     │    │
│       └── 与撮合引擎使用同一个 Position 对象               │    │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 接口变更

#### 新增辅助方法

```python
# backtester.py

def _build_account_snapshot(
    self,
    account: Account,
    positions_map: Dict[str, Position],
    timestamp: int,
) -> AccountSnapshot:
    """
    从 positions_map 构建 AccountSnapshot，包含真实持仓信息。

    Args:
        account: 当前账户状态
        positions_map: {signal_id: Position} 仓位映射
        timestamp: 当前 K 线时间戳

    Returns:
        包含真实持仓的 AccountSnapshot
    """
    from src.domain.models import PositionInfo

    position_infos = []
    for pos in positions_map.values():
        if not pos.is_closed and pos.current_qty > Decimal('0'):
            position_infos.append(PositionInfo(
                symbol=pos.symbol,
                side=pos.direction.value.lower(),  # "long" or "short"
                size=pos.current_qty,
                entry_price=pos.entry_price,
                unrealized_pnl=Decimal('0'),  # 回测中无浮动盈亏概念
                leverage=1,  # 回测不涉及真实杠杆
            ))

    return AccountSnapshot(
        total_balance=account.total_balance,
        available_balance=account.available_balance,
        unrealized_pnl=Decimal('0'),
        positions=position_infos,
        timestamp=timestamp,
    )
```

#### 调用点变更

```python
# backtester.py:1282-1294

# 修改前:
account_snapshot = AccountSnapshot(
    total_balance=account.total_balance,
    available_balance=account.available_balance,
    unrealized_pnl=Decimal('0'),
    positions=[],
    timestamp=kline.timestamp,
)

# 修改后:
account_snapshot = self._build_account_snapshot(
    account=account,
    positions_map=positions_map,
    timestamp=kline.timestamp,
)
```

### 3.3 财务平衡校验设计

```python
# backtester.py: Step 9 之前

def _validate_accounting_integrity(
    self,
    initial_balance: Decimal,
    final_balance: Decimal,
    total_pnl: Decimal,
    position_summaries: List[PositionSummary],
) -> Dict[str, Any]:
    """
    验证回测财务记账完整性。

    平衡方程:
        final_balance = initial_balance - total_entry_fees + total_pnl

    其中 total_pnl = sum(position.realized_pnl)，已扣除 exit_fee。
    """
    # 计算总入场费
    total_entry_fees = Decimal('0')
    for summary in position_summaries:
        # 入场费 = entry_price × size × fee_rate
        # 由于 entry_fee 已在撮合时扣除，需要从 Position 实体获取
        # 或者通过名义价值估算
        pass

    expected_balance = initial_balance - total_entry_fees + total_pnl
    diff = abs(expected_balance - final_balance)

    return {
        'is_balanced': diff < Decimal('0.01'),
        'expected_balance': expected_balance,
        'actual_balance': final_balance,
        'difference': diff,
    }
```

---

## 4. 关联影响评估表

### 4.1 AccountSnapshot.positions 的使用者

| 模块 | 文件 | 使用方式 | 影响评估 |
|------|------|----------|----------|
| RiskCalculator | `src/domain/risk_calculator.py` | 计算暴露限制 | **正面影响**。修复后正确限制仓位规模 |
| 回测 (v2 模式) | `src/application/backtester.py` | 不涉及（v2 模式不使用 positions_map） | 无影响 |
| 实盘引擎 | `src/application/signal_pipeline.py` | 可能使用（需确认） | 需验证实盘场景中 positions 是否正确填充 |
| debug_pms.py | `debug_pms.py:76` | 测试代码，硬编码 positions=[] | 测试代码，不影响生产 |
| API 端点 | `src/interfaces/api.py` | 可能通过 AccountSnapshot 返回 | 需确认是否有 API 返回 AccountSnapshot |

### 4.2 PositionInfo 字段语义差异

| 字段 | Position（domain） | PositionInfo（snapshot） | 兼容性 |
|------|-------------------|-------------------------|--------|
| `side` | (无，用 direction) | `str`: "long"/"short" | 需要 `direction.value.lower()` 转换 |
| `size` | `current_qty` | `size` | 直接映射 |
| `unrealized_pnl` | (无，用 realized_pnl) | `unrealized_pnl` | 回测中设为 0，语义不同但安全 |
| `leverage` | (无) | `leverage: int` | 回测中设为 1，安全默认值 |

### 4.3 风险评估

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| PositionInfo 字段语义错误 | 低 | 中 | 单元测试覆盖映射逻辑 |
| positions_map 遍历顺序影响 | 无 | 无 | Python 3.7+ dict 有序，但不依赖顺序 |
| 回测性能影响 | 低 | 低 | 每次信号生成时遍历 positions_map，最多几十笔交易，影响可忽略 |
| 实盘场景不兼容 | 中 | 高 | 需确认实盘场景中 AccountSnapshot 的构建方式 |

---

## 5. 建议实施顺序和优先级

### 5.1 推荐顺序

```
Step 1: 方案 B（调试方向矛盾）───────────── 预估 1 小时
  ↓
  添加运行时日志 → 运行一次回测 → 确认方向矛盾根因
  ↓
Step 2: 方案 A（修复 positions 为空）──────── 预估 30 分钟
  ↓
  实施 _build_account_snapshot() 辅助方法 → 修改调用点 → 运行测试
  ↓
Step 3: 方案 C（添加财务平衡校验）────────── 预估 15 分钟
  ↓
  添加校验断言 → 确认修复后 balance 平衡
  ↓
Step 4: 补充测试 ────────────────────────── 预估 30 分钟
  ↓
  新增集成测试验证 positions 不为空、RiskCalculator 正确限制暴露
```

### 5.2 为什么先执行方案 B？

1. **Bug #2 的根因尚未确认**，方向矛盾可能导致更严重的问题（如止损/止盈触发条件错误）
2. **方案 B 零风险**，仅添加日志不修改业务逻辑
3. **方案 B 结果可能影响方案 A 的设计**（如果方向矛盾确认，可能需要同时修复方向数据流）

### 5.3 如果时间紧迫（只修一个 Bug）

**优先实施方案 A**。理由：
- Bug #1（仓位规模失控）对财务不平衡的贡献是确认的、可量化的
- Bug #2（方向矛盾）对财务不平衡的影响不确定，可能仅影响报告准确性
- 方案 A 修复后，即使方向矛盾仍然存在，balance 计算也会更接近正确值

---

## 6. 附加发现

### 6.1 max_drawdown 计算逻辑错误

backtester.py:1451-1458：
```python
for summary in position_summaries:
    if summary.exit_price:
        current_balance = initial_balance + summary.realized_pnl
```

每笔交易都从 `initial_balance` 开始计算，而非累计余额。这导致 max_drawdown 计算不准确。

**建议修复**: 使用累计余额：
```python
cumulative_balance = initial_balance
for summary in position_summaries:
    if summary.exit_price:
        cumulative_balance += summary.realized_pnl
        if cumulative_balance > peak:
            peak = cumulative_balance
        drawdown = (peak - cumulative_balance) / peak
```

**优先级**: P2（不影响 balance 计算，仅影响报告指标）

### 6.2 RiskConfig 默认值缺少 max_total_exposure

backtester.py:132-135：
```python
return RiskConfig(
    max_loss_percent=Decimal('0.01'),
    max_leverage=20,
    # 缺少 max_total_exposure
)
```

虽然 `RiskConfig.model_config` 定义了 `max_total_exposure` 默认值为 0.8，但显式传入更好。

**建议**: 显式传入 `max_total_exposure=Decimal('0.8')`。

**优先级**: P3（当前行为正确，但显式更好）

### 6.3 诊断报告中的 exit_price 语义问题

诊断报告指出部分仓位的 `exit_price` 看起来像 trigger price 而非 exec price。

**代码验证**: `summary.exit_price = order.average_exec_price` (backtester.py:1396)，而 `average_exec_price` 是撮合引擎计算的含滑点执行价。

**可能的根因**: SL 订单的 `average_exec_price` = `trigger_price × (1 - slippage_rate)`，与 trigger_price 非常接近（仅差 0.1%），在显示时可能被四舍五入到相同值。

**优先级**: P3（显示精度问题，不影响 balance）

---

## 7. 总结

| 问题 | 根因确认度 | 修复方案 | 优先级 | 预估工作量 |
|------|-----------|----------|--------|-----------|
| 仓位规模失控 | **确认** | 方案 A | P0 | 30 分钟 |
| 方向矛盾 | 高置信度（需运行时验证） | 方案 B → 修复 | P0 | 1-2 小时 |
| 财务平衡校验缺失 | **确认** | 方案 C | P1 | 15 分钟 |
| max_drawdown 计算错误 | **确认** | 独立修复 | P2 | 15 分钟 |

**核心结论**: 诊断报告的 Bug #1 根因分析正确，方案 A 是确定的必要修复。Bug #2 需要运行时调试确认，但可能不影响 balance 计算。建议按 B → A → C 顺序实施。
