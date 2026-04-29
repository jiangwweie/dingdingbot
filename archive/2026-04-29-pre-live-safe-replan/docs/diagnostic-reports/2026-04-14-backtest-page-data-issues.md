# 诊断报告：回测页面三大数据展示异常

**报告编号**: DA-20260414-001
**优先级**: 🔴 P0
**诊断对象**: 回测报告 `rpt_b9cc3fd1-134c-49ce-9720-20631fc75c41_1768320000000_4d960ac2`

---

## 问题描述

| 字段 | 内容 |
|------|------|
| 用户报告 | 1. 初始$10000→最终$8065.30(-1934.70%) 百分比异常<br>2. 夏普比率显示 N/A（数据不足）<br>3. 总盈亏显示 +$1355.19，但实际是亏损的 |
| 影响范围 | 所有 v3 PMS 回测报告的前端展示均受影响 |
| 出现频率 | 100% 复现（每个回测报告都存在） |

---

## 排查过程

### 假设验证

| 假设 | 可能性 | 验证方法 | 结果 |
|------|--------|---------|------|
| H1: 前端百分比显示双乘 bug | 高 | 读 EquityComparisonChart.tsx:93,110 | ✅ 确认 |
| H2: 后端 total_pnl 计算逻辑有缺陷 | 高 | 读 backtester.py:1406 | ✅ 确认（部分） |
| H3: sharpe_ratio 后端硬编码 None | 高 | 读 backtester.py:1472 | ✅ 确认 |
| H4: 数据库序列化/反序列化错误 | 中 | 读 backtest_repository.py | ❌ 排除 |
| H5: 前端 total_pnl 只累加盈利 | 低 | 读 TradeStatisticsTable.tsx | ❌ 排除 |

---

## 根因定位 (5 Why)

### 问题 1: 收益率显示 -1934.70%（应该是 -19.35%）

```
Why 1: 为什么显示 -1934.70%？
→ 前端 EquityComparisonChart.tsx:110 将 totalReturn * 100 后显示

Why 2: totalReturn 的值从哪来？
→ 前端 EquityComparisonChart.tsx:93 自行计算: ((finalBalance - initialBalance) / initialBalance) * 100

Why 3: 这个计算的结果是什么？
→ 当 initial=10000, final=8065.30 时: ((8065.30-10000)/10000)*100 = -19.347

Why 4: 为什么 -19.347 变成了 -1934.70%？
→ 第 110 行又乘以了 100: (totalReturn * 100).toFixed(2) = -1934.70

Why 5: 为什么会双乘？
→ 根本原因：后端 total_return 返回的是小数（-0.19347），但前端
  EquityComparisonChart.tsx:93 已经乘了 100 转成百分比，
  第 110 行再次乘以 100，导致 ×10000 的效果
```

**问题代码位置**: `gemimi-web-front/src/components/v3/backtest/EquityComparisonChart.tsx:93,110`

```tsx
// 第 93 行：已经乘以 100，得到 -19.347
const totalReturn = ((finalBalance - initialBalance) / initialBalance) * 100;

// 第 110 行：再次乘以 100，得到 -1934.70
({totalReturn >= 0 ? '+' : ''}{(totalReturn * 100).toFixed(2)}%)
```

**对比其他组件的正确做法** (`BacktestOverviewCards.tsx:62`):
```tsx
// totalReturn 是小数（0.19347），正确乘以 100 后显示
{(metrics.totalReturn * 100).toFixed(2)}%
```

---

### 问题 2: 夏普比率始终显示 N/A

```
Why 1: 为什么夏普比率显示 N/A？
→ 前端检测到 sharpe_ratio 为 null 时显示 N/A

Why 2: 为什么 sharpe_ratio 为 null？
→ 后端 backtester.py:1472 硬编码 sharpe_ratio=None

Why 3: 为什么不计算夏普比率？
→ 回测引擎缺少基于逐笔收益的标准差计算逻辑

Why 4: 这个功能是否规划过？
→ PMSBacktestReport 模型中定义了 sharpe_ratio: Optional[Decimal] = None，
  说明预留了字段但从未实现计算逻辑
```

**问题代码位置**: `src/application/backtester.py:1472`

```python
sharpe_ratio=None,  # 硬编码，始终为 None
```

---

### 问题 3: 总盈亏显示 +$1355.19（与直觉不符）

```
Why 1: 为什么用户认为 +$1355.19 不正确？
→ 用户期望总盈亏是扣除手续费、滑点、资金费用后的净值

Why 2: 后端 total_pnl 是怎么计算的？
→ backtester.py:1406 total_pnl += position.realized_pnl
  只累加每笔交易的 realized_pnl

Why 3: realized_pnl 是否包含手续费？
→ 需要检查 Position.realized_pnl 的计算方式
  如果 realized_pnl 已经扣除了手续费和滑点，则 total_pnl 是正确的
  如果没有扣除，则 total_pnl 是"毛盈亏"而非"净利润"

Why 4: 前端如何展示？
→ 前端在"成本明细"卡片中分别展示了 total_pnl、total_fees_paid、
  total_slippage_cost、total_funding_cost，但"净盈亏计算"区域
  仍然只显示 total_pnl，并未减去各项成本

Why 5: 语义混淆的根本原因是什么？
→ 后端 total_pnl 的注释是"总盈亏 (USDT)"，但实际是毛盈亏
  (Gross PnL)，没有明确区分 Gross PnL vs Net PnL
  导致用户误认为 +$1355.19 就是最终净利润
```

**问题代码位置**: `src/application/backtester.py:1406` 和 `BacktestReportDetailModal.tsx:196-210`

```python
# backtester.py:1406 — 只累加 realized_pnl（可能未扣除费用）
total_pnl += position.realized_pnl
```

```tsx
// BacktestReportDetailModal.tsx:196-210 — 净盈亏计算区域
// 文字说明是"总盈亏 - 手续费 - 滑点 - 资金费用"
// 但实际显示的还是 report.total_pnl，没有做减法
<p>{formatCurrency(report.total_pnl, true)}</p>
```

---

## 修复方案

### 问题 1 修复方案

#### 方案 A [推荐] — 前端删除多余的 * 100
**修改内容**:
文件：`gemimi-web-front/src/components/v3/backtest/EquityComparisonChart.tsx`，位置：第 93 行

当前代码：
```tsx
const totalReturn = ((finalBalance - initialBalance) / initialBalance) * 100;
```
修改为：
```tsx
const totalReturn = (finalBalance - initialBalance) / initialBalance;
```

**优点**: 改动最小（只改一行），与其他组件（BacktestOverviewCards.tsx）保持一致
**缺点**: 无
**预估工作量**: 5 分钟

#### 方案 B — 后端返回百分比而非小数
**修改内容**:
文件：`src/application/backtester.py`，位置：第 1440 行
将 `total_return = ((final_balance - initial_balance) / initial_balance)` 改为乘以 100
然后前端 EquityComparisonChart.tsx:110 不再乘以 100

**优点/缺点**: 与方案 A 等效，但改动更大（需要改后端+前端多处）
**预估工作量**: 30 分钟

---

### 问题 2 修复方案

#### 方案 A [推荐] — 实现标准夏普比率计算
**修改内容**:
文件：`src/application/backtester.py`，位置：第 1472 行前后

添加夏普比率计算逻辑：
```python
# 基于逐笔 realized_pnl 计算夏普比率
# Sharpe = (Mean(Rp - Rf)) / Std(Rp - Rf)
# 假设无风险利率 Rf = 0
if len(pnl_series) > 1:
    mean_pnl = sum(pnl_series) / len(pnl_series)
    variance = sum((p - mean_pnl) ** 2 for p in pnl_series) / (len(pnl_series) - 1)
    std_pnl = variance.sqrt() if variance > 0 else Decimal('0')
    sharpe_ratio = (mean_pnl / std_pnl) if std_pnl > 0 else Decimal('0')
else:
    sharpe_ratio = None  # 数据不足（至少 2 笔交易）
```

**优点**: 提供真正有用的风险调整收益指标
**缺点**: 需要收集逐笔 PnL 序列（当前位置 summaries 只存了最终 realized_pnl）
**预估工作量**: 2 小时

#### 方案 B — 前端显示"未实现"而非 N/A
**修改内容**: 前端将 "N/A" 改为 "未实现"，并在 tooltip 中说明原因
**预估工作量**: 15 分钟

---

### 问题 3 修复方案

#### 方案 A [推荐] — 前端正确计算净盈亏
**修改内容**:
文件：`gemimi-web-front/src/components/v3/backtest/BacktestReportDetailModal.tsx`，位置：第 196-210 行

当前代码显示的是 `report.total_pnl`，应改为：
```tsx
const netPnl = parseFloat(report.total_pnl) 
             - parseFloat(report.total_fees_paid) 
             - parseFloat(report.total_slippage_cost) 
             - parseFloat(report.total_funding_cost);
```
显示 `netPnl` 而非 `report.total_pnl`

**优点**: 用户看到的是真实的净利润
**缺点**: 前端需要做计算（也可移到后端）

#### 方案 B — 后端新增 net_pnl 字段
**修改内容**:
文件：`src/domain/models.py` — PMSBacktestReport 新增 `net_pnl: Decimal` 字段
文件：`src/application/backtester.py` — 计算并赋值 `net_pnl = total_pnl - total_fees_paid - total_slippage_cost - total_funding_cost`

**优点**: 语义清晰，前后端一致
**缺点**: 需要数据库迁移（新增列）
**预估工作量**: 3 小时

---

## 建议

### 立即修复（P0）
1. **问题 1**（收益率百分比）：采用方案 A，修改 EquityComparisonChart.tsx 第 93 行
2. **问题 3**（净盈亏）：采用方案 A，前端正确计算 netPnl

### 短期优化（P1）
3. **问题 2**（夏普比率）：采用方案 A，实现标准夏普比率计算

### 预防措施
- 回测指标的"小数 vs 百分比"语义应统一：后端统一返回小数（如 -0.19347），前端负责乘以 100 显示
- 建议在 API 层增加指标校验测试，防止前后端语义不一致
