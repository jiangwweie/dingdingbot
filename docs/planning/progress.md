# Progress Log

> Last updated: 2026-04-14 22:30

---

## 2026-04-14 22:30 -- ADR: SQLite TEXT 列 CHECK 约束字典序比较 Bug 修复

### Completed

**ADR 设计文档**: `docs/arch/sqlite-text-check-constraint-fix-plan.md`
- 编号 ADR-2026-0414-SQLITE-CHECK
- 根因: `BacktestReportORM.total_return` 为 TEXT 列，CHECK 约束做字典序比较，负数被拒绝
- 全量扫描: 7 处 DecimalString 列的数值 CHECK 约束有潜在问题（1 处已触发），9 处枚举 CHECK 约束正确
- 方案对比: A（删除约束+应用层验证）/ B（CAST AS REAL）/ C（迁移为 REAL）/ D（混合方案）
- 推荐方案 A：删除所有 DecimalString 数值 CHECK 约束，与 SignalORM 已有设计一致
- 实施计划: 修改 `v3_orm.py` 3 处约束 + 补充 Pydantic 验证 + 测试，预估 0.5 小时
- 无需数据库迁移，现有数据不受影响
- 关联影响评估: 5 个模块受影响，风险均为低/无

### 验收标准核对

- [x] ADR 文档已写入 `docs/arch/sqlite-text-check-constraint-fix-plan.md`
- [x] 已扫描全部代码找出所有类似约束（7 处数值约束 + 9 处枚举约束）
- [x] 包含 4 个方案对比（A/B/C/D）
- [x] 给出明确推荐（方案 A）和实施步骤
- [x] progress.md 已更新

---

## 2026-04-14 22:00 -- 夏普比率计算实现完成（方案 B - 权益曲线法）

### Completed

**实现**: 按照 ADR `docs/arch/sharpe-ratio-calculation-plan.md` Step 1-4

**Step 1: 主循环添加权益曲线收集**
- 文件: `src/application/backtester.py`
- 添加 `import math`
- 在 state tracking 区域添加 `equity_curve: List[Tuple[int, Decimal]] = []`
- 在主循环末尾（active_orders 清理后）添加 `equity_curve.append((kline.timestamp, account.total_balance))`

**Step 2: 实现 _calculate_sharpe_ratio() 方法**
- 在 Backtester 类中添加 `_calculate_sharpe_ratio(equity_curve, timeframe) -> Optional[Decimal]` 方法
- 核心逻辑：
  - 数据不足（len < 2）返回 None
  - 计算逐期收益率：(curr - prev) / prev（prev=0 时跳过）
  - 计算均值和样本标准差：variance / (n-1)
  - 标准差为 0 返回 Decimal('0')
  - 年化：sharpe * sqrt(bars_per_year[timeframe])
- BARS_PER_YEAR 映射：15m=35040, 1h=8760, 4h=2190, 1d=365, 1w=52
- Decimal 精度：variance 用 max(Decimal('0'), variance) 防负值，math.sqrt() 返回 float 转 Decimal(str(...))

**Step 3: 报告生成时调用**
- 替换 `sharpe_ratio=None` 为 `sharpe_ratio=self._calculate_sharpe_ratio(equity_curve, request.timeframe)`

**Step 4: 单元测试**
- 文件: `tests/unit/test_sharpe_ratio.py`
- 15 个测试用例，覆盖：
  - 数据不足返回 None（3 个场景）
  - 零波动返回 0
  - 稳定上涨返回正夏普
  - 持续下跌返回负夏普
  - 不同 timeframe 年化因子正确（1h/1d/4h/1w/15m）
  - 未知 timeframe 默认 1h
  - 混合收益现实场景
  - Decimal 类型保持
  - 中间权益为 0 跳过该期

### 验收标准核对

- [x] 代码已修改（git diff 证明）
- [x] pytest 测试通过（15/15 passed）
- [x] 现有测试未破坏（32/32 passed）
- [x] 覆盖率合理（15 个测试覆盖所有边界场景）

### 边界检查
- [x] 空值处理：equity_curve 长度 < 2 返回 None
- [x] 除零错误：prev_equity == 0 跳过该期
- [x] 类型安全：variance 用 max(Decimal('0'), ...) 防负值
- [x] 精度转换：math.sqrt() 返回 float 转 Decimal(str(...))

---

## 2026-04-14 21:00 -- ADR: 夏普比率计算方案设计

### Completed

**ADR 设计文档**: `docs/arch/sharpe-ratio-calculation-plan.md`
- 编写完整的夏普比率计算方案 ADR（编号 ADR-2026-0414-SR01）
- 方案对比: 方案 A（逐笔 PnL）vs 方案 B（权益曲线）
- 推荐方案 B：基于权益曲线收益率计算，理由：统计稳定性好、年化准确、行业标准
- 实施计划：4 步，预估 1.5 小时
- 风险点：数据不足处理、Decimal 精度、性能影响、无风险利率假设
- 关联影响评估表：4 个模块受影响

### 验收标准核对

- [x] ADR 文档已写入 `docs/arch/sharpe-ratio-calculation-plan.md`
- [x] 包含至少 2 个方案对比（方案 A 逐笔 PnL vs 方案 B 权益曲线）
- [x] 给出明确推荐和实施步骤（推荐方案 B，4 步实施计划）
- [x] progress.md 已更新

---

## 2026-04-14 18:28 -- 修复两个回测页面前端 Bug

### Completed

**Bug 1: 收益率百分比双乘 bug** (Task #3)
- **File**: `web-front/src/components/v3/backtest/EquityComparisonChart.tsx`
- **Change**: Line 93 removed `* 100` since line 110 already multiplies by 100
- **Before**: `const totalReturn = ((finalBalance - initialBalance) / initialBalance) * 100;`
- **After**: `const totalReturn = (finalBalance - initialBalance) / initialBalance;`
- **Impact**: Display now shows -19.35% instead of -1934.70%

**Bug 3: 净盈亏未扣除成本** (Task #1)
- **File**: `web-front/src/components/v3/backtest/BacktestReportDetailModal.tsx`
- **Change**: Net PnL section now computes `total_pnl - total_fees_paid - total_slippage_cost - total_funding_cost` instead of showing raw `total_pnl`
- **Impact**: Net盈亏 now correctly deducts all costs as the label states

### Verification
- TypeScript type check: No new errors introduced (pre-existing errors in e2e/ and other components unrelated)
- Git diff confirmed both changes
