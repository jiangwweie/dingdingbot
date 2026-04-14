# Findings Log

> Last updated: 2026-04-14 23:00

---

## 2026-04-14 -- 回测页面四连 Bug 修复

### 发现 1: 前端收益率百分比双乘

**文件**: `web-front/src/components/v3/backtest/EquityComparisonChart.tsx:93,110`

第 93 行已经 `* 100` 转成百分比，第 110 行又 `* 100` 显示，导致 -19.35% 显示为 -1934.70%。

**根因**: 前端不同组件对后端返回值的语义理解不一致。`BacktestOverviewCards.tsx` 正确地将小数 `* 100` 显示，但 `EquityComparisonChart.tsx` 自己先转了百分比又乘了一次。

**教训**: 后端返回小数 vs 百分比的语义必须统一并在团队文档中明确，前端所有组件应遵循同一约定。

---

### 发现 2: 夏普比率硬编码 None

**文件**: `src/application/backtester.py:1472`

`sharpe_ratio=None` 硬编码，`PMSBacktestReport` 模型预留了字段但从未实现计算逻辑。

**决策**: 采用权益曲线法（方案 B），而非逐笔 PnL 法（方案 A）。理由：回测通常有数百 K 线数据点充足，统计稳定性远优于可能只有几笔交易的逐笔法。年化因子基于 K 线周期精确计算。

---

### 发现 3: SQLite TEXT 列 CHECK 约束字典序比较

**文件**: `src/infrastructure/v3_orm.py:1167`

**这是最严重的 bug**。`total_return` 列类型是 TEXT（存储 Decimal 字符串），CHECK 约束做字典序比较：
```
'-0.17' >= '-1.0'  →  False  (字典序: '0' < '1')
```
导致所有负收益的回测报告 INSERT 被拒绝，数据库中只有全零的旧记录。

**影响范围**: 全量扫描发现 7 处 DecimalString 列的数值 CHECK 约束有潜在问题，1 处已触发（P0）。

**设计决策**: 删除所有 DecimalString 列的数值比较 CHECK 约束，改用 Pydantic 应用层验证。与 `SignalORM` 已有设计完全一致（该模型已有注释明确说明不使用数值 CHECK 约束）。

**为什么不用 CAST(... AS REAL)**:
- 引入浮点精度问题，与 "Decimal everywhere" 原则矛盾
- 每次 INSERT/UPDATE 都要 CAST 转换，有运行时开销
- 极端 Decimal 值可能超出 REAL 范围

**为什么不迁移为 REAL**:
- 金融计算不能用 REAL，精度丢失不可接受
- 需要数据库迁移，风险高

---

### 发现 4: 净盈亏语义混淆

**文件**: `web-front/src/components/v3/backtest/BacktestReportDetailModal.tsx:196-210`

"净盈亏计算"区域文字说明是"总盈亏 - 手续费 - 滑点 - 资金费用"，但实际只显示 `report.total_pnl`，没有做减法。

**根因**: 后端 `total_pnl` 注释是"总盈亏"，但实际是毛盈亏（Gross PnL），没有明确区分 Gross vs Net。前端直接展示导致用户误解。
