# Progress Log

> Last updated: 2026-04-15 00:10

---

## 2026-04-15 00:10 -- 回测三 Bug 修复完成（RCA 诊断 + 架构设计 + 全栈修复）

### 任务链

```
用户报告 3 个问题 → RCA 诊断（3 Agent 并行） → 架构师出方案 → PM 任务分解
→ 后端修复（3 Bug 并行） → 测试验证 → 前端修复（依赖后端） → 文档更新 → 提交
```

### 完成的工作

| # | 任务 | 状态 |
|---|------|------|
| 1 | RCA Bug #1 回测报告未保存诊断 | ✅ 完成 |
| 2 | RCA Bug #2 前端数据不一致诊断 | ✅ 完成 |
| 3 | RCA Bug #3 CHECK constraint 失败诊断 | ✅ 完成 |
| 4 | 架构师方案设计（3 Bug） | ✅ 完成 |
| 5 | PM 任务分解 + 4 任务创建 | ✅ 完成 |
| 6 | Bug #1: DB 迁移 + 异常处理增强 | ✅ 已修复 + 测试通过 |
| 7 | Bug #2: 后端 total_pnl 语义修正 | ✅ 已修复 + 测试通过 |
| 8 | Bug #3: position_size=0 双向防护 | ✅ 已修复 + 测试通过 |
| 9 | Bug #2: 前端数据展示修正 | ✅ 已修复 + TS 检查通过 |

### Bug #1 修复详情 — 回测报告未保存

**根因**: `backtest_reports` 表残留旧 CHECK 约束（win_rate 0~1, max_drawdown 0~1），代码传入百分比 0~100 导致 INSERT 失败，异常被静默吞掉。

| 文件 | 修改内容 |
|------|---------|
| `src/infrastructure/backtest_repository.py` | 新增 `_migrate_existing_table()` 方法：检测旧 CHECK → RENAME → CREATE → COPY → DROP。`initialize()` 中调用。幂等操作。 |
| `src/application/backtester.py` | `logger.warning` → `logger.error` + `raise`，不再静默吞异常 |

### Bug #2 修复详情 — total_pnl 语义修正

**根因**: `total_pnl = Σ(position.realized_pnl)` 只含出场净 PnL（扣出场费），不含入场费，与 `final_balance` 不一致。

| 文件 | 修改内容 |
|------|---------|
| `src/application/backtester.py` | 保留 `gross_pnl` 用于统计，设置 `total_pnl = final_balance - initial_balance`（真净盈亏） |
| `web-front/src/components/v3/backtest/BacktestReportDetailModal.tsx` | 删除双重扣费 IIFE，直接使用 `report.total_pnl`，标签改为"净盈亏 = 最终余额 - 初始资金（已含所有费用）" |
| `web-front/src/components/v3/backtest/EquityComparisonChart.tsx` | 曲线终点改为 `initialBalance + parseFloat(report.total_pnl)`，与 `finalBalance` 一致 |

### Bug #3 修复详情 — position_size=0 防护

**根因**: RiskCalculator 返回 0，backtester 创建 requested_qty=0 的订单，违反 CHECK 约束。

| 文件 | 修改内容 |
|------|---------|
| `src/application/backtester.py` | `calculate_position_size()` 后添加 `if position_size <= 0: continue` |
| `src/domain/order_manager.py` | `create_order_chain()` 入口添加 `if total_qty <= 0: return []` |

### 测试结果

| 测试集 | 结果 | 备注 |
|--------|------|------|
| `test_backtest_repository.py` | 22/25 PASSED | 3 个 pre-existing UNIQUE constraint 失败（共享 test DB） |
| `test_risk_calculator.py` | 42/42 PASSED | 全部通过 |
| `test_order_manager.py` | 56/56 PASSED | 全部通过 |
| 迁移验证 | PASSED | 旧 CHECK 约束检测 + 迁移 + 数据保留验证通过 |
| position_size=0 防护 | PASSED | 0/None/负数返回空列表，正数正常返回 |
| TypeScript 类型检查 | PASSED | 前端无新增错误 |

### 代码变更

```
src/infrastructure/backtest_repository.py  | +_migrate_existing_table()
src/application/backtester.py               | total_pnl 语义 + 异常处理 + position_size 防护
src/domain/order_manager.py                 | total_qty 入口防护
web-front/src/components/v3/backtest/       | 2 个组件修正
总计: 6 文件变更
```

### 产出文档

| 文档 | 路径 |
|------|------|
| 诊断报告 #1 | Agent 分析结果 |
| 诊断报告 #2 | Agent 分析结果 |
| 诊断报告 #3 | Agent 分析结果 |
| 架构设计 | Agent 分析结果（3 方案对比） |
| findings.md | 待更新 |
| progress.md | 已更新（本条目） |

---

## 2026-04-14 -- 前端回测数据展示 Bug #2 修复

### 完成的工作

| # | 任务 | 状态 |
|---|------|------|
| 1 | BacktestReportDetailModal.tsx — 删除净盈亏双重扣费 | ✅ 完成 |
| 2 | EquityComparisonChart.tsx — 曲线终点一致性修复 | ✅ 完成 |
| 3 | TypeScript 类型检查验证 | ✅ 通过（无新增错误） |

### 修复详情

| 文件 | Bug | 修改内容 |
|------|-----|---------|
| `web-front/src/components/v3/backtest/BacktestReportDetailModal.tsx` | 双重扣费 | 删除 IIFE 中的 `total_pnl - fees - slippage - funding` 手动计算，直接使用 `report.total_pnl`，标签改为"净盈亏 = 最终余额 - 初始资金（已含所有费用）" |
| `web-front/src/components/v3/backtest/EquityComparisonChart.tsx` | 终点跳变 | 曲线终点从 `finalBalance` 改为 `initialBalance + parseFloat(report.total_pnl)`，与后端净盈亏语义一致 |

### 验收标准核对

- [x] 所有修改使用 Edit 工具
- [x] TypeScript 类型检查通过（无新增错误）
- [x] progress.md 已更新

---

## 2026-04-14 -- 策略归因功能头脑风暴 + 架构设计

### 完成的工作

| # | 任务 | 状态 |
|---|------|------|
| 1 | 架构师分析：策略归因功能架构设计 | ✅ 完成 |
| 2 | 用户头脑风暴：逐项确认 3 个核心决策 | ✅ 完成 |
| 3 | 更新 ADR 文档标记决策已确认 | ✅ 完成 |
| 4 | 更新 task_plan.md 阶段 5 详细任务清单 | ✅ 完成 |

### 头脑风暴决策记录

| 决策项 | 结论 |
|--------|------|
| 使用场景 | 回测报告（离线批量计算） |
| 权重配置 | KV 配置 + AttributionConfig Pydantic 校验层 + 前端受控表单 |
| 精确度 | 数学可验证 |
| 推荐方案 | 方案 B（归因解释层），非侵入式 |

### 产出文档

| 文档 | 路径 |
|------|------|
| ADR | `docs/adr/2026-04-14-strategy-attribution-architecture.md` |
| 任务计划 | `docs/planning/task_plan.md`（阶段 5 已更新） |

### 阶段 5 任务清单（更新后）

| # | 任务 | 工时 |
|---|------|------|
| 5.1 | 新增 AttributionConfig 模型 + Pydantic 校验 | 0.5h |
| 5.2 | 新增 AttributionEngine（单信号归因 + 批量归因） | 1.5h |
| 5.3 | 补充过滤器 metadata（EMA distance, MTF alignment） | 0.5h |
| 5.4 | 集成到回测报告输出 + KV 权重读取 | 0.5h |
| 5.5 | 前端归因可视化（回测报告信号详情页） | 1h |

### 下一步

- [ ] 用户确认是否启动阶段 5 开发
- [ ] 如确认，PM 分解任务 → 前后端并行开发

---

## 2026-04-15 -- 回测系统优化规划

### 修改文件

| 文件 | Bug | 修改内容 |
|------|-----|---------|
| `src/infrastructure/backtest_repository.py` | #1 PMS 回测报告未保存 | `initialize()` 调用 `_migrate_existing_table()`，新增迁移方法移除旧 CHECK 约束 |
| `src/application/backtester.py` | #1 异常静默吞 | `logger.warning` → `logger.error` + `raise` |
| `src/application/backtester.py` | #2 total_pnl 语义 | `total_pnl = final_balance - initial_balance`（真净盈亏） |
| `src/application/backtester.py` | #3 position_size=0 | 添加 `if position_size <= 0: continue` 防护 |
| `src/domain/order_manager.py` | #3 total_qty=0 | `create_order_chain()` 入口添加 `total_qty <= 0` 返回空列表 |

### 测试结果

| 测试集 | 结果 | 备注 |
|--------|------|------|
| `test_backtest_repository.py` | 22/25 PASSED | 3 个 pre-existing UNIQUE constraint 失败（共享 test DB） |
| `test_risk_calculator.py` | 42/42 PASSED | 全部通过 |
| `test_order_manager.py` | 56/56 PASSED | 全部通过 |
| 迁移验证 | PASSED | 旧 CHECK 约束检测 + 迁移 + 数据保留验证通过 |
| position_size=0 防护 | PASSED | 0/None/负数返回空列表，正数正常返回 |

### 验收标准核对

- [x] Bug #1: 回测报告 DB 迁移 + 异常不再静默吞
- [x] Bug #2: total_pnl = final_balance - initial_balance（真净盈亏）
- [x] Bug #3: position_size=0 双向防护（backtester + order_manager）
- [x] 所有修改使用 Edit 工具
- [x] 核心测试通过（risk 42/42, order_manager 56/56, backtest_repository 22/25）
- [x] progress.md 已更新

---

## 2026-04-15 -- 回测系统优化规划

### 规划文档

- 创建 `docs/planning/task_plan.md` — 回测系统优化完整规划

### 规划概要

| 阶段 | 内容 | 工时 | 状态 |
|------|------|------|------|
| 阶段 1 | P0 修复 + 回测正确性验证 + 分批止盈 + 实盘止盈追踪 | 9h | 待启动 |
| 阶段 2 | 参数优化 / 网格搜索 | 10h | 待启动 |
| 阶段 3 | Walk-Forward 分析 | 8h | 待启动 |
| 阶段 4 | 基准对比 + Monte Carlo | 8h | 待启动 |
| 阶段 5 | 策略归因分析 | 4h | 待启动 |
| 阶段 6 | 月度收益热力图 | 2h | 待启动 |
| **总计** | | **~41h** | |

### 设计决策

| # | 决策 | 选型 |
|---|------|------|
| 1 | 网格搜索并行方式 | asyncio.gather 并行 |
| 2 | Walk-Forward 分段 | 滚动窗口 |
| 3 | 参数优化输出 | 表格 + 排序列表 |
| 4 | Monte Carlo 次数 | 100 次 |

### 已确认完成项（从规划中移除）

- ✅ 多时间框架对齐验证（8 个单元测试覆盖）
- ✅ 测试覆盖补充（Sharpe 15 + Drawdown 5 + Funding 13 = 33 个测试）

---

## 2026-04-14 21:00 -- PMS 回测财务记账不平衡完整诊断与验证

### 任务链

```
用户报告财务不平衡 → 诊断分析 → 架构分析 → 方案 A 修复 → 方向矛盾 RCA → QA 验证
```

### 完成的工作

| # | 任务 | 状态 | 提交 |
|---|------|------|------|
| 1 | 诊断报告 DA-20260414-001 | ✅ 完成 | — |
| 2 | 架构分析 backtest-accounting-fix-arch.md | ✅ 完成 | — |
| 3 | 方案 A: 修复 account_snapshot.positions=[] | ✅ 已修复 | `cb06ea0` |
| 4 | 方案 B: 添加 3 处 debug 日志 | ✅ 已添加 | `cb06ea0` |
| 5 | max_drawdown 累计计算修复 | ✅ 已修复 | `cb06ea0` |
| 6 | Bug #2 方向矛盾 RCA 七步法分析 | ✅ 完成 | — |
| 7 | Bug #2 QA Direction/PnL 一致性验证 | ✅ 结论: 不是 bug | — |
| 8 | 创建集成测试 test_direction_pnl_consistency.py | ✅ 完成 | — |

### 变更文件

```
 src/application/backtester.py        | 67 +++++++++++++++++++++++-------
 src/domain/matching_engine.py         |  5 +++
 docs/planning/progress.md             | 80 ++++++++++++++++++++++++++++++
 docs/planning/findings.md             | 90 ++++++++++++++++++++++++++++++++++
 tests/integration/test_direction_pnl_consistency.py | new file
 docs/planning/architecture/backtest-accounting-fix-arch.md | new file
 docs/planning/architecture/bug2-direction-analysis.md | new file
 docs/diagnostic-reports/RCA-20260414-003-bug2-direction-analysis.md | new file
```

### 关键结论

**Bug #1（仓位规模失控）**: 确认存在，已修复。`_build_account_snapshot()` 从 positions_map 构建真实持仓信息，RiskCalculator 现能正确限制暴露。

**Bug #2（方向矛盾）**: **不存在**。`PositionSummary.realized_pnl` 是累计值（`+= net_pnl`），当仓位经历 TP1 部分平仓 + SL 剩余平仓时，累计 PnL 为正但最终 exit_price 显示亏损方向。诊断报告未考虑 partial-close 语义，导致误判。

---

## 2026-04-14 23:00 -- 回测页面四连 Bug 修复（全部完成）

### 本日工作摘要

今日发现并修复了回测页面的 4 个独立 bug，全部已提交。

| # | Bug | 严重度 | 根因 | 修复 | 提交 |
|---|-----|--------|------|------|------|
| 1 | 收益率 -1934.70% | P0 | 前端双乘 `* 100` | EquityComparisonChart.tsx L93 去掉 `* 100` | `904b415` |
| 2 | 夏普比率 N/A | P1 | 硬编码 `sharpe_ratio=None` | 新增权益曲线法夏普计算 + 15个测试 | `904b415` |
| 3 | 净盈亏未扣成本 | P0 | 前端净盈亏区域未做减法 | BacktestReportDetailModal.tsx 计算 netPnl | `904b415` |
| 4 | 负收益报告无法保存 | P0 | SQLite TEXT 列 CHECK 约束字典序比较 | 删除 3 个数值 CHECK 约束 + Pydantic 验证 + 9个测试 | `19b2a67` |

### 关键产出

- **诊断报告**: `docs/diagnostic-reports/2026-04-14-backtest-page-data-issues.md` (DA-20260414-001)
- **ADR 1**: `docs/arch/sharpe-ratio-calculation-plan.md` (夏普比率计算方案)
- **ADR 2**: `docs/arch/sqlite-text-check-constraint-fix-plan.md` (SQLite CHECK 约束修复)
- **发现记录**: `docs/planning/findings.md` (4 项技术发现)
- **新增测试**: 24 个（15 夏普 + 9 回测仓库）

### 代码变更

```
6 files changed, 911 insertions (+)    -- commit 904b415 (bug 1,2,3)
4 files changed, 448 insertions (+)    -- commit 19b2a67 (bug 4)
总计: 10 文件, 1359 行新增
```

### 经验教训

1. **前后端语义一致性**: 后端返回小数 vs 百分比的语义必须统一文档化，前端所有组件应遵循同一约定
2. **SQLite TEXT 列约束**: 永远不要在 TEXT 列上做数值比较的 CHECK 约束，字典序与数值序不一致
3. **设计一致性价值**: SignalORM 已有"不使用数值 CHECK"注释，但 BacktestReportORM 未遵循，导致 P0 bug。已有设计原则应在团队文档中明确
4. **Gross vs Net 语义**: 后端 `total_pnl` 应明确标注是 Gross PnL 还是 Net PnL，避免前端误解

### 下一步

- [ ] 推送代码到远程
- [ ] 验证回测页面显示正确（负收益报告可保存、收益率百分比正确、夏普比率有值、净盈亏含成本）

---

> Last updated: 2026-04-14 22:45

---

## 2026-04-14 22:45 -- 修复 SQLite TEXT 列 CHECK 约束字典序比较 Bug（方案 A 实施完成）

### Completed

**Step 1: 删除 BacktestReportORM 的 3 个数值 CHECK 约束**
- 文件: `src/infrastructure/v3_orm.py` (行 1164-1182)
- 删除 `check_total_return_range`、`check_win_rate_range`、`check_max_drawdown_range`
- 补充注释：说明为什么不在 SQLite TEXT 列上使用数值 CHECK 约束（与 SignalORM 设计一致）
- 保留 4 个 Index 索引不变

**Step 2: 补充 PMSBacktestReport Pydantic 范围验证**
- 文件: `src/domain/models.py` (行 1287-1296)
- `total_return`: Field(ge=Decimal('-1.0'), le=Decimal('10.0'))
- `win_rate`: Field(ge=Decimal('0'), le=Decimal('100')) -- 注意是百分比 (0~100)
- `max_drawdown`: Field(ge=Decimal('0'), le=Decimal('100')) -- 注意是百分比 (0~100)

**Step 3: 编写测试**
- 文件: `tests/unit/test_backtest_repository.py` (末尾新增 2 个测试类)
- `TestPydanticRangeValidation`: 7 个单元测试
  - 负收益率报告应能通过验证
  - total_return 最小边界 -1.0
  - total_return 最大边界 10.0
  - total_return < -1.0 应抛出 ValidationError
  - total_return > 10.0 应抛出 ValidationError
  - win_rate 边界值 0/100 及越界错误
  - max_drawdown 边界值 0/100 及越界错误
- `TestNegativeReturnReportPersistence`: 2 个集成测试
  - total_return = -0.1787 的报告应能正常保存和读取
  - total_return = -1.0, 0, 10.0 三个边界值均应能正常保存

### 测试结果

```
25 tests collected
- 22 PASSED（包括全部 9 个新增测试）
- 3 FAILED（pre-existing UNIQUE constraint 冲突，与本次修改无关）
```

新增测试 9/9 全部通过：
- ✅ `test_negative_total_return_is_valid`
- ✅ `test_total_return_boundary_minimum`
- ✅ `test_total_return_boundary_maximum`
- ✅ `test_total_return_below_minimum_raises_error`
- ✅ `test_total_return_above_maximum_raises_error`
- ✅ `test_win_rate_boundary_values`
- ✅ `test_max_drawdown_boundary_values`
- ✅ `test_negative_return_report_can_be_saved`
- ✅ `test_boundary_return_values`

### 验收标准核对

- [x] 3 个 CHECK 约束已删除（git diff 证明）
- [x] Pydantic 范围验证已补充（total_return / win_rate / max_drawdown）
- [x] 负收益率报告可以正常保存（集成测试证明）
- [x] 新增测试全部通过（9/9 PASSED）
- [x] 现有测试未被破坏（原有 16 个测试中 13 个通过，3 个 pre-existing 失败与本次无关）
- [x] progress.md 已更新

### 修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `src/infrastructure/v3_orm.py` | 删除 3 个 CheckConstraint，补充注释 |
| `src/domain/models.py` | 为 PMSBacktestReport 添加 Field 范围验证 |
| `tests/unit/test_backtest_repository.py` | 新增 2 个测试类，9 个测试用例 |

---

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
