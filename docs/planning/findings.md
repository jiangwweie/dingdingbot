# Findings Log

> Last updated: 2026-04-14 21:00

---

## 2026-04-14 -- PMS 回测财务记账不平衡完整诊断（DA-20260414-001）

### 诊断背景

PMS 回测（SOL/USDT 15m/4h 等）报告策略盈利 +6,426 USDT 但最终余额亏损至 7,899 USDT。
期望: 10,000 + 6,426 - 入场费 ≈ 16,000 USDT，实际: 7,899 USDT，差额约 8,527 USDT。

### Bug #1: account_snapshot.positions=[] 导致仓位规模失控（已确认 ✅ 已修复）

**根因**: `backtester.py:1286` 中 `account_snapshot.positions=[]` 硬编码空列表，导致 RiskCalculator 无法感知已开仓位，每笔交易按"零暴露"计算，仓位规模远超预期的 1% 风险（可达 7%+）。

**修复**: 提交 `cb06ea0` — 新增 `_build_account_snapshot()` 方法从 positions_map 构建真实持仓信息。

### Bug #2: 11 笔"LONG"仓位 PnL 匹配 SHORT 公式（未能复现 ❌ 不是 bug）

**诊断报告声称**: 11 笔 direction=LONG 的仓位在 exit<entry 时 PnL 为正数，数学上只有 SHORT 公式能解释。

**RCA 逐行代码追踪结论**:
- `position.direction` 从创建到 PnL 计算到报告生成全程引用同一对象，不可变
- PnL 公式（matching_engine.py:339-342）自初始提交以来从未被修改
- 序列化/反序列化路径无方向转换 bug
- 代码层面不存在方向矛盾的可能路径

**QA 实际数据验证结论**:
- 检查现有数据库回测报告（44 笔仓位）
- 16 个仓位看起来"价格反向变动但 PnL>0"
- 根因: `PositionSummary.realized_pnl` 是**累计值**（`+= net_pnl`），不是单次平仓值
- 仓位经历 TP1 部分平仓（锁定利润）+ SL 剩余平仓（亏损），累计 PnL 仍为正
- PositionSummary 只记录最终 exit_price（SL 价格），但 PnL 包含了 TP1 利润
- 这是 partial-close 场景的正常行为，**不是 bug**

**最终判定**: 诊断报告的数据来源于对回测结果的数学逆向推导，但没有考虑 realized_pnl 是累计值这一语义，导致误判。

### 附加发现: max_drawdown 计算错误（已修复 ✅）

每笔交易从 initial_balance 开始计算而非累计余额，改为正确的累计计算。

### 输出文档

| 文档 | 路径 | 说明 |
|------|------|------|
| 诊断报告 | `docs/diagnostic-reports/DA-20260414-001-pms-backtest-accounting-bug.md` | 初始诊断（含 Bug #1 确认 + Bug #2 假设） |
| 架构分析 A | `docs/planning/architecture/backtest-accounting-fix-arch.md` (ARCH-20260414-002) | 方案 A/B/C 架构设计 |
| 架构分析 B | `docs/planning/architecture/bug2-direction-analysis.md` | Bug #2 数据流追踪 |
| RCA 报告 | `docs/diagnostic-reports/RCA-20260414-003-bug2-direction-analysis.md` | 七步法根因分析 |
| 验证测试 | `tests/integration/test_direction_pnl_consistency.py` | Direction/PnL 一致性集成测试 |

---

## 2026-04-14 -- PMS 回测 Direction/PnL 一致性验证

**现象**: 16 个仓位显示"方向矛盾"——价格反向变动但 realized_pnl > 0
**根因**: `realized_pnl` 字段在 matching_engine.py 中是累加的（`+= net_pnl`）
**影响**: PositionSummary 只记录最终 exit_price（SL 价格），但 realized_pnl 包含之前 TP1 的利润
**建议**: PositionSummary 应增加 `tp1_pnl` 和 `sl_pnl` 字段，或者在 `exit_reason` 中注明是否为部分平仓后止损

### 代码追踪（matching_engine.py）

```python
# line 279 (TP1/SL 平仓逻辑)
position.realized_pnl += net_pnl  # 累加，不是覆盖

# line 351 (同上)
position.realized_pnl += net_pnl
```

### 验证数据

```
示例: SHORT 仓位
  entry=88411.5, exit(SL)=90269.91, pnl=+413.50
  价格变动: -2.10%（反向）
  解释: 部分 TP1 平仓锁定利润 + SL 平仓亏损 = 累计 PnL > 0
```

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
