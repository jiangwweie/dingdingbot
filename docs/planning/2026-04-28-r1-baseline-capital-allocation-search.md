# R1: Baseline Capital Allocation Search

> **日期**: 2026-04-28
> **性质**: research-only，不改 src，不改 runtime，不提交 git
> **约束**: MaxDD <= 35%

---

## 0. 核心结论（先说结论）

**在 MaxDD <= 35% 约束下：**
- 最高收益：**17749.41 USDT**（exposure=1.0, risk=0.02）
- 最高 Calmar：**244.55**（exposure=1.0, risk=0.02）
- Conservative (MaxDD<=25%)：**17749.41 USDT**（exposure=1.0, risk=0.02）

## 1. 固定策略参数

| 参数 | 值 |
|------|-----|
| Symbol | ETH/USDT:USDT |
| Timeframe | 1h |
| Direction | LONG |
| EMA Period | 50 |
| MTF EMA Period | 60 |
| TP Ratios | [1.0, 3.5] |
| TP Partial Ratios | [0.5, 0.5] |
| Fee Rate | 0.0405% |
| Entry Slippage | 0.0100% |
| Max Leverage | 20 |
| Daily Max Trades | 50 |
| Initial Balance | 10000.0 USDT |

## 2. 搜索参数网格

### 2.1 max_total_exposure

1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0

### 2.2 max_loss_percent

0.50%, 0.75%, 1.00%, 1.25%, 1.50%, 1.75%, 2.00%

**总配置数**: 56

## 3. Baseline 验证（exposure=1.0, risk=1%）

| 指标 | 值 |
|------|-----|
| Total PnL | 4889.77 USDT |
| MaxDD | 0.5% |
| Sharpe | 0.31 |
| Calmar | 90.98 |
| Trades | 186 |

**Yearly Breakdown:**

| Year | PnL | Trades | MaxDD | WR |
|------|-----|--------|-------|-----|
| 2023 | -4277.97 | 55 | 0.00 | 0.0% |
| 2024 | 3687.58 | 62 | 0.00 | 0.0% |
| 2025 | 5480.16 | 69 | 0.00 | 0.0% |

## 4. 最优配置

### 4.1 Total PnL 最高（MaxDD <= 35%）

| 指标 | 值 |
|------|-----|
| max_total_exposure | 1.0 |
| max_loss_percent | 2.00% |
| Total PnL | **17749.41 USDT** |
| Total Return | 177.5% |
| MaxDD | 0.7% |
| Sharpe | 0.51 |
| Calmar | 244.55 |
| Trades | 174 |
| Exposure Rejected | 0 |

**Yearly Breakdown:**

| Year | PnL | Trades | MaxDD | WR |
|------|-----|--------|-------|-----|
| 2023 | -5751.03 | 52 | 0.00 | 0.0% |
| 2024 | 6081.84 | 61 | 0.00 | 0.0% |
| 2025 | 17418.60 | 61 | 0.00 | 0.0% |

### 4.2 Sharpe 最高

| 指标 | 值 |
|------|-----|
| max_total_exposure | 1.0 |
| max_loss_percent | 2.00% |
| Total PnL | 17749.41 USDT |
| Sharpe | **0.51** |
| Calmar | 244.55 |
| MaxDD | 0.7% |

### 4.3 Calmar 最高

| 指标 | 值 |
|------|-----|
| max_total_exposure | 1.0 |
| max_loss_percent | 2.00% |
| Total PnL | 17749.41 USDT |
| Calmar | **244.55** |
| Sharpe | 0.51 |
| MaxDD | 0.7% |

### 4.4 Conservative (MaxDD <= 25%)

| 指标 | 值 |
|------|-----|
| max_total_exposure | 1.0 |
| max_loss_percent | 2.00% |
| Total PnL | **17749.41 USDT** |
| MaxDD | 0.7% |
| Calmar | 244.55 |
| Sharpe | 0.51 |

## 6. 结论与建议

**在 MaxDD <= 35% 约束下，ETH Pinbar baseline 最高收益为 17749.41 USDT（3yr）。**

对应参数：
- max_total_exposure = 1.0
- max_loss_percent = 2.00%

**年度表现：**
- 2023: PnL=-5751.03, MaxDD=0.00
- 2024: PnL=6081.84, MaxDD=0.00
- 2025: PnL=17418.60, MaxDD=0.00

**是否需要 OOS 验证：**
- 当前搜索基于 2023-2025 全量数据，存在过拟合风险
- 建议使用 2026 Q1 作为 OOS 验证区间
- 如果 OOS 表现显著低于预期，应降级到 conservative 配置

**是否建议进入下一轮更细粒度搜索：**
- 如果最优配置位于网格边界（exposure=3.0 或 risk=2.0%），建议扩大搜索范围
- 如果最优配置位于网格内部，建议在最优配置周围进行细粒度搜索

---

*R1 搜索完成时间: 2026-04-28*
*性质: research-only，不改 src，不改 runtime，不提交 git*