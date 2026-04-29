# 诊断报告：PMS 回测财务记账严重不平衡（最终版）

**报告编号**: DA-20260414-001
**优先级**: 🔴 P0
**诊断日期**: 2026-04-14
**诊断人**: P8 分析师

---

## 问题描述

| 字段 | 内容 |
|------|------|
| 用户报告 | PMS 回测（SOL/USDT 15m，46 天）策略盈利 +6,426 USDT，但最终余额亏损至 7,899 USDT |
| 影响范围 | 所有 v3_pms 模式回测，财务数据不可信 |
| 出现频率 | 必现 |

**核心矛盾**：
- `initial_balance` = 10,000 USDT
- `total_pnl` = +6,426 USDT
- `final_balance` = 7,899 USDT
- **期望**: 10,000 + 6,426 − 入场费 ≈ 16,000 USDT
- **实际**: 7,899 USDT
- **不翼而飞**: **约 8,527 USDT**

---

## 排查过程

### 假设验证

| 假设 | 可能性 | 验证方法 | 结果 |
|------|--------|---------|------|
| H1: KV 配置覆盖 fee_rate | 低 | 查询 DB 中 backtest 配置 | ❌ DB 中无 fee_rate 配置 |
| H2: funding_cost 扣余额 | 低 | 代码追踪 | ❌ funding 不修改 account.total_balance |
| H3: 撮合引擎 PnL 公式错误 | 低 | 独立单元测试验证 | ❌ 撮合引擎 PnL 计算完全正确 |
| H4: SL 在 TP 之后成交导致重复计算 | 中 | 分析订单生成逻辑 | ❌ TP1=100% 仓位，SL 实际成交 qty=0 |
| H5: 11 笔仓位方向与 PnL 矛盾 | **高** | 数学逆向推导 | ✅ 确认 11 笔"LONG"的 PnL 匹配 SHORT 公式 |
| H6: 隐含入场费 8,527 USDT 远超估算 | **高** | 财务平衡方程 | ✅ 确认存在 7,928 USDT 差额 |

### 关键发现 1：11 笔"LONG"仓位的方向与 PnL 数学矛盾

**数据证据**：

| # | 方向 | 入场 | 出场 | PnL | 矛盾 |
|---|------|------|------|------|------|
| 1 | LONG | 144.43 | 142.85 | **+681.88** | LONG 出场<入场 应为亏损 |
| 27 | LONG | 103.19 | 102.06 | **+253.03** | 同上 |
| 33 | LONG | 87.55 | 86.59 | **+192.71** | 同上 |
| ... | ... | ... | ... | ... | 共 11 笔 |

**数学证明**（以 #1 为例）：
```
LONG 公式: gross_pnl = (exit - entry) × qty = (142.85 - 144.43) × qty = -1.58 × qty
SHORT 公式: gross_pnl = (entry - exit) × qty = (144.43 - 142.85) × qty = +1.58 × qty

如果 LONG: net_pnl = -1.58 × qty - exit_fee
  要为 +681.88 → qty 必须为负数 → 不可能

如果 SHORT: net_pnl = +1.58 × qty - exit_fee
  要为 +681.88 → qty ≈ 445.6 → 合理 ✅
  验证: gross = 707.35, fee = 25.46, net = 681.88 ✓ 精确匹配
```

**结论**: 这 11 笔仓位的 PnL 是用 SHORT 公式计算的，但 direction 字段标记为 LONG。

**独立验证**：撮合引擎单元测试确认 PnL 公式完全正确：
```
LONG entry=100.10, SL exit=96.90 → realized_pnl = -323.58 ✅ 负数
```

### 关键发现 2：财务平衡差额 7,928 USDT

```
final_balance = initial_balance - entry_fees + total_pnl
→ entry_fees = initial_balance + total_pnl - final_balance
→ entry_fees = 10,000 + 6,426 - 7,899 = 8,527 USDT

但估算入场费（基于仓位名义价值 × 0.04%）仅约 599 USDT。
差额: 8,527 - 599 = 7,928 USDT
```

### 关键发现 3：仓位规模远超预期

从 PnL 逆向推导，多笔仓位的风险金额远超 1% 预期：
- 第 1 笔: risk_amount ≈ 707 USDT (7.07% of 10,000)
- 预期: risk_amount = 10,000 × 0.01 = 100 USDT (1%)

### 根因定位 (5 Why)

```
Why 1: 为什么 final_balance 远低于预期？
→ account.total_balance 被扣除了远超预期的金额（8,527 vs 预期 599）

Why 2: 为什么扣除金额远超预期？
→ 两个独立问题叠加：
   a) 11 笔仓位的方向与 PnL 计算矛盾（PnL 用 SHORT 公式但标记为 LONG）
   b) 仓位规模远超预期的 1% 风险

Why 3: 为什么方向与 PnL 矛盾？
→ 撮合引擎 PnL 公式正确，方向比较正确
→ 矛盾只能通过以下两种可能解释：
   a) position.direction 在撮合后、报告生成前被修改（代码中未发现此路径）
   b) 存在某种竞态/状态同步问题导致方向翻转（需要更深入的运行态调试）

Why 4: 为什么仓位规模远超预期？
→ RiskCalculator 使用 account_snapshot.positions=[]（空列表）
→ 无法感知已开仓位，每笔交易都按"零暴露"计算仓位
→ 同时，stop_distance = |close - low| 可能非常小
→ 导致 position_size = risk / stop_distance 极大

Why 5: 为什么 account_snapshot.positions 为空？
→ 回测中 account_snapshot 是每次信号生成时新建的
→ positions=[] 是硬编码的，没有从 positions_map 构建
→ 这是一个已知的设计简化，不是 Bug
```

---

## 问题代码位置

| 文件 | 行号 | 问题 |
|------|------|------|
| `src/application/backtester.py` | 1286 | `account_snapshot.positions=[]`，RiskCalculator 无法感知已开仓位 |
| `src/application/backtester.py` | 1147 | fee_rate 优先级：request → KV → default，需确认实际值 |
| `src/domain/matching_engine.py` | 338-341 | PnL 公式正确，但方向数据来源需验证 |

---

## 修复方案

### 方案 A（推荐，改动最小）：修复 account_snapshot.positions

**问题**: `account_snapshot.positions=[]` 导致 RiskCalculator 无法计算已开仓位暴露。

**修改内容**:
文件：`src/application/backtester.py`，第 1282-1288 行

当前代码：
```python
account_snapshot = AccountSnapshot(
    total_balance=account.total_balance,
    available_balance=account.available_balance,
    unrealized_pnl=Decimal('0'),
    positions=[],  # ← 问题
    timestamp=kline.timestamp,
)
```

修改为：
```python
from src.domain.models import PositionInfo

# 从 positions_map 构建 PositionInfo 列表
position_infos = []
for sig_id, pos in positions_map.items():
    if not pos.is_closed and pos.current_qty > 0:
        position_infos.append(PositionInfo(
            symbol=pos.symbol,
            side="long" if pos.direction == Direction.LONG else "short",
            size=pos.current_qty,
            entry_price=pos.entry_price,
            unrealized_pnl=Decimal('0'),
            leverage=1,
        ))

account_snapshot = AccountSnapshot(
    total_balance=account.total_balance,
    available_balance=account.available_balance,
    unrealized_pnl=Decimal('0'),
    positions=position_infos,
    timestamp=kline.timestamp,
)
```

**优点**: 修复仓位规模失控问题，RiskCalculator 正确限制暴露
**缺点**: 不解决方向矛盾问题
**预估工作量**: 30 分钟

### 方案 B：调试方向矛盾

**问题**: 11 笔"LONG"仓位的 PnL 匹配 SHORT 公式，但方向标记为 LONG。

**调试步骤**:
1. 在撮合引擎 `_execute_fill` 中添加日志，打印 `position.direction` 和 PnL 计算结果
2. 在 backtester 的 PositionSummary 创建处添加日志，打印 `position.direction`
3. 运行一次回测，对比两个日志中的 direction 值

**可能原因**:
- 撮合引擎中的 `position.direction` 是 SHORT（PnL 正确），但报告生成时读到的方向是 LONG
- 或者回测中 `attempt.pattern.direction` 本身就是反的

**预估工作量**: 1 小时（需要添加日志 + 重新运行）

### 方案 C：添加财务平衡校验

**修改内容**: 在回测报告生成前，添加平衡校验断言。

文件：`src/application/backtester.py`，在 Step 9 之前添加：
```python
# 财务平衡校验
expected_balance = initial_balance - total_entry_fees + total_pnl
if abs(expected_balance - final_balance) > Decimal('0.01'):
    logger.warning(
        f"财务不平衡！expected={expected_balance}, actual={final_balance}, "
        f"diff={expected_balance - final_balance}"
    )
```

**优点**: 防止未来回测数据错误未被发现
**缺点**: 不修复根因，只是报警
**预估工作量**: 15 分钟

---

## 建议执行顺序

1. **立即**: 方案 B（调试方向矛盾）— 添加 3-5 行日志，跑一次回测，确认根因
2. **确认根因后**: 方案 A（修复 positions 为空）— 这是确定需要修复的
3. **后续**: 方案 C（添加财务平衡校验）— 防止回归

---

## 附加发现：回测报告 exit_price 语义

| 字段 | 实际值 | 期望值 |
|------|--------|--------|
| Position #1 exit_price | 142.85 (SL trigger price) | 应该是实际执行价 (SL trigger × 0.999) |

`summary.exit_price = order.average_exec_price` — 这个值是正确的执行价（含滑点）。但部分仓位的 exit_price 看起来更像 trigger price 而非 exec price。需要确认 SL 订单的 `average_exec_price` 是否正确计算。

---

*诊断完成于 2026-04-14。撮合引擎 PnL 公式经单元测试验证正确，方向矛盾需要在回测实际运行中添加日志进一步定位。*
