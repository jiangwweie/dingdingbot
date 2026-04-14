# Task Plan: 回测系统优化

> Created: 2026-04-15
> Last updated: 2026-04-15
> Status: 规划阶段，待启动

---

## 背景

回测功能已基本正常（PMS 回测 + 四连 Bug 修复完成），现需系统性提升回测系统的**正确性**、**参数优化能力**、**策略鲁棒性验证**和**可解释性**。

已有 3 年本地历史数据，足够支撑参数优化和 Walk-Forward 分析。

---

## 设计决策

| # | 决策 | 选型 | 理由 |
|---|------|------|------|
| 1 | 网格搜索并行方式 | **B: asyncio.gather 并行** | 3 年数据 + 参数组合可能上百，串行太慢 |
| 2 | Walk-Forward 分段 | **B: 滚动窗口** | 滚动窗口更稳健，样本利用率更高（如前 6 个月训练，后 1 个月验证，每次滑动 1 个月） |
| 3 | 参数优化输出 | **C: 表格 + 排序列表** | 热力图用表格，快速查看用排序 |
| 4 | Monte Carlo 次数 | **A: 100 次** | 100 次已够看分布，可配上限 |

---

## 阶段总览

| 阶段 | 内容 | 工时 | 依赖 |
|------|------|------|------|
| 阶段 1 | P0 修复 + 回测正确性验证 + 分批止盈 + 实盘止盈追踪 | 9h | 无 |
| 阶段 2 | 参数优化 / 网格搜索 | 10h | 阶段 1 |
| 阶段 3 | Walk-Forward 分析 | 8h | 阶段 1 |
| 阶段 4 | 基准对比 + Monte Carlo | 8h | 阶段 1 |
| 阶段 5 | 策略归因分析 | 4h | 阶段 1 |
| 阶段 6 | 月度收益热力图 | 2h | 阶段 1 |
| **总计** | | **~41h** | |

---

## 阶段 1: P0 修复 + 回测正确性验证（3h）

### 任务清单

| # | 任务 | 工时 | 状态 |
|---|------|------|------|
| 1.1 | 修复部分平仓 PnL 归因 | 2h | 待启动 |
| 1.2 | 修复净盈亏语义混淆 | 1h | 待启动 |
| 1.3 | 推送代码 + 验证回测页面显示正确 | — | 待启动 |
| 1.4 | TP-1: 回测分批止盈模拟（TP1/TP2/TP3） | 2h | 待启动 |
| 1.5 | TP-2: 实盘止盈追踪逻辑（trailing stop） | 4h | 待启动 |

### 1.1 部分平仓 PnL 归因

**问题**: `PositionSummary.realized_pnl` 是累计值（`+= net_pnl`），当仓位经历 TP1 部分平仓 + SL 剩余平仓时，累计 PnL 为正但最终 `exit_price` 显示亏损方向，用户易误解。

**修复方案**:
- `PositionSummary` 新增 `tp1_pnl: Optional[Decimal]` 字段（TP1 部分平仓盈亏）
- `PositionSummary` 新增 `sl_pnl: Optional[Decimal]` 字段（SL 平仓盈亏）
- `exit_reason` 注明是否为部分平仓后止损（如 `"PARTIAL_TP1_THEN_SL"`）
- 前端报告展示拆分盈亏

**影响文件**:
- `src/domain/models.py` — PositionSummary 模型
- `src/domain/matching_engine.py` — TP1/SL 结算时记录分项 PnL
- `src/application/backtester.py` — 报告生成时填充新字段
- `web-front/src/components/v3/backtest/` — 前端展示

### 1.2 净盈亏语义混淆

**问题**: 前端 `BacktestReportDetailModal.tsx` 文字说明"总盈亏 - 手续费 - 滑点 - 资金费用"，但实际只展示 `report.total_pnl`（毛盈亏），未做减法。

**修复方案**: 前端计算 `netPnl = total_pnl - total_fees_paid - total_slippage_cost - total_funding_cost`，展示真实净盈亏。

**影响文件**:
- `web-front/src/components/v3/backtest/BacktestReportDetailModal.tsx`

### 1.3 推送 + 验证

- 推送 dev 分支到 origin（610 个 commit）
- 验证回测页面：负收益报告可保存、收益率百分比正确、夏普比率有值、净盈亏含成本

### 1.4 TP-1: 回测分批止盈模拟

**问题**: 回测中未模拟分批止盈（TP1 部分平仓 + TP2 剩余平仓 + TP3 尾仓），只有 TP1 部分平仓 + SL 剩余平仓。回测结果无法反映真实分批止盈的收益。

**修复方案**:
- `matching_engine.py` 新增 TP2/TP3 触发逻辑
- `PositionSummary` 新增 `tp2_pnl`、`tp3_pnl` 字段
- 回测主循环中按配置的多级止盈比例触发
- 前端报告展示各级止盈盈亏明细

**影响文件**:
- `src/domain/matching_engine.py` — TP2/TP3 触发逻辑
- `src/domain/models.py` — PositionSummary 新增字段
- `src/application/backtester.py` — 回测主循环集成
- 前端报告组件 — 分批止盈明细展示

### 1.5 TP-2: 实盘止盈追踪逻辑

**问题**: 实盘模式下未实现止盈追踪逻辑（trailing stop），无法跟随行情移动止盈价位。

**修复方案**:
- `matching_engine.py` 新增 `update_trailing_tp()` 方法
- 每次 K 线更新时检查最高/最低价是否触发新的更高止盈位
- 支持固定步长（step）和回撤比例（pullback）两种模式
- 实盘信号管道集成止盈更新

**影响文件**:
- `src/domain/matching_engine.py` — trailing TP 逻辑
- `src/application/signal_pipeline.py` — 实盘集成
- 前端配置界面 — trailing TP 参数配置

### 已确认完成项（无需处理）

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 多时间框架对齐 | ✅ 已完成 | `backtester.py:728-771` 严格 `<` 比较，8 个单元测试覆盖 |
| Sharpe Ratio 测试 | ✅ 已完成 | `test_sharpe_ratio.py` 15 个测试用例 |
| Max Drawdown 测试 | ✅ 已完成 | `test_performance_calculator.py` 5 个测试用例 |
| Funding Cost 测试 | ✅ 已完成 | `test_backtester_funding_cost.py` 10 个单元 + 3 个集成测试 |

---

## 阶段 2: 参数优化 / 网格搜索（10h）

### 任务清单

| # | 任务 | 工时 | 状态 |
|---|------|------|------|
| 2.1 | 参数空间配置模型 | 2h | 待启动 |
| 2.2 | 网格搜索引擎（asyncio.gather 并行） | 4h | 待启动 |
| 2.3 | 结果聚合 + 敏感性分析 | 2h | 待启动 |
| 2.4 | 前端热力图/排序展示 | 1h | 待启动 |
| 2.5 | 单元测试 | 1h | 待启动 |

### 2.1 参数空间配置模型

**需求**: 策略暴露参数空间，支持范围配置。

**设计**:
```python
class ParameterSpace(BaseModel):
    param_name: str              # 如 "min_wick_ratio"
    values: list[Decimal]        # 如 [0.5, 0.6, 0.7, 0.8]
    is_categorical: bool         # True = 分类参数, False = 数值参数


class GridSearchRequest(BaseModel):
    symbol: str
    timeframe: str
    start_time: int
    end_time: int
    strategy_id: str
    parameter_spaces: list[ParameterSpace]
    metric: str = "total_return"  # 优化目标指标
```

**影响文件**: `src/domain/models.py`

### 2.2 网格搜索引擎

**设计**:
```python
async def run_grid_search(request: GridSearchRequest) -> GridSearchResult:
    """并行执行所有参数组合的回测"""
    # 1. 生成所有参数组合 (itertools.product)
    # 2. 为每个组合创建 BacktestRequest
    # 3. asyncio.gather 并行执行所有回测
    # 4. 聚合结果，按 metric 排序
```

**关键设计**:
- 并发度控制：使用 `asyncio.Semaphore` 限制同时运行的回测数量（默认 5）
- 进度追踪：每个回测完成后更新进度状态
- 失败容忍：单个参数组合失败不影响其他组合

**影响文件**:
- `src/application/backtester.py` — 新增 run_grid_search 方法
- `src/interfaces/api.py` — 新增网格搜索 API 端点

### 2.3 结果聚合 + 敏感性分析

**输出**:
```python
class GridSearchResult(BaseModel):
    combinations: list[CombinationResult]  # 所有参数组合结果
    best_combination: CombinationResult     # 最优参数组合
    sensitivity: dict[str, SensitivityInfo] # 每个参数的敏感性分析
```

**敏感性分析**: 固定其他参数，单参数变动对目标指标的影响幅度。

### 2.4 前端展示

- 热力图：X 轴 = 参数 A，Y 轴 = 参数 B，颜色 = 目标指标值
- 排序列表：按目标指标降序排列，显示 Top N 参数组合

---

## 阶段 3: Walk-Forward 分析（8h）

### 任务清单

| # | 任务 | 工时 | 状态 |
|---|------|------|------|
| 3.1 | 分段配置模型（滚动窗口） | 1h | 待启动 |
| 3.2 | Walk-Forward 执行器 | 4h | 待启动 |
| 3.3 | 稳定性评估（跨段指标对比） | 2h | 待启动 |
| 3.4 | 前端可视化 | 1h | 待启动 |

### 3.1 分段配置模型

**设计**:
```python
class WalkForwardConfig(BaseModel):
    symbol: str
    timeframe: str
    start_time: int
    end_time: int
    strategy_id: str
    train_months: int = 6       # 训练窗口（月）
    test_months: int = 1        # 验证窗口（月）
    slide_months: int = 1       # 滑动步长（月）
    parameter_spaces: list[ParameterSpace]  # 每段内做参数优化
```

### 3.2 Walk-Forward 执行器

**流程**:
1. 按配置划分训练/验证段
2. 每段内：训练窗口做参数优化 → 最优参数 → 验证窗口跑回测
3. 滑动到下一段，重复
4. 聚合所有验证段的结果

```python
async def run_walk_forward(config: WalkForwardConfig) -> WalkForwardResult:
    """滚动窗口 Walk-Forward 分析"""
    # 1. 生成时间段切片
    # 2. 对每个切片：
    #    a. 训练窗口 run_grid_search → 最优参数
    #    b. 验证窗口用最优参数跑回测
    # 3. 聚合验证结果
```

### 3.3 稳定性评估

**指标**:
- 各验证段收益的标准差（越低越稳定）
- 盈利验证段占比
- 最优参数跨段一致性（参数是否频繁变化）

### 3.4 前端可视化

- 滚动收益曲线（训练段 vs 验证段区分颜色）
- 各验证段关键指标对比表
- 参数稳定性热力图

---

## 阶段 4: 基准对比 + Monte Carlo（8h）

### 任务清单

| # | 任务 | 工时 | 状态 |
|---|------|------|------|
| 4.1 | Buy & Hold 基准收益计算 | 2h | 待启动 |
| 4.2 | Monte Carlo 随机重采样 | 4h | 待启动 |
| 4.3 | 收益分布置信区间 | 1h | 待启动 |
| 4.4 | 前端展示 | 1h | 待启动 |

### 4.1 Buy & Hold 基准

**计算**:
```python
def calculate_buy_hold_return(klines: list[KlineData]) -> Decimal:
    """买入持有基准收益：(最终价格 - 初始价格) / 初始价格"""
    return (klines[-1].close - klines[0].close) / klines[0].close
```

**展示**: 策略收益 vs 基准收益对比，超额收益 = 策略收益 - 基准收益

### 4.2 Monte Carlo 随机重采样

**方法**: Bootstrapping — 从交易序列中有放回地随机抽样，重新生成权益曲线。

```python
async def run_monte_carlo(
    positions: list[PositionSummary],
    n_simulations: int = 100,
) -> MonteCarloResult:
    """Monte Carlo 模拟"""
    # 1. 从交易序列中有放回抽样
    # 2. 重新计算权益曲线和总收益
    # 3. 重复 n 次
    # 4. 统计分布：中位数、5%分位、95%分位等
```

**配置**: `n_simulations` 默认 100，可配上限。

### 4.3 收益分布置信区间

**输出**:
- 收益中位数
- 90% 置信区间（5% ~ 95% 分位）
- 亏损概率（收益 < 0 的模拟占比）
- 实际策略收益在分布中的百分位

### 4.4 前端展示

- 收益分布直方图 + 实际策略收益标记线
- 置信区间展示卡片
- 亏损概率告警

---

## 阶段 5: 策略归因分析（4h）

### 任务清单

| # | 任务 | 工时 | 状态 |
|---|------|------|------|
| 5.1 | 形态质量归因 | 1.5h | 待启动 |
| 5.2 | 过滤器归因 | 1.5h | 待启动 |
| 5.3 | 市场趋势归因 | 0.5h | 待启动 |
| 5.4 | 前端归因可视化 | 0.5h | 待启动 |

### 5.1 形态质量归因

按 Pinbar 评分分组统计：
- B 维度（形态质量）：[0.0-0.3), [0.3-0.6), [0.6-1.0] 三组
- 每组：胜率、平均盈亏、交易次数

### 5.2 过滤器归因

按过滤器拦截率/通过率统计：
- C 维度（过滤器链）：每个过滤器的拦截次数、通过率、通过后的胜率

### 5.3 市场趋势归因

按牛熊市分组统计：
- D 维度（市场趋势）：Bullish / Bearish / Neutral
- 每组：胜率、平均盈亏、交易次数

### 5.4 前端展示

- 三维度归因表格
- 过滤器拦截率柱状图

---

## 阶段 6: 月度收益热力图（2h）

### 任务清单

| # | 任务 | 工时 | 状态 |
|---|------|------|------|
| 6.1 | 后端计算 monthly_returns 填充 | 2h | 待启动 |

### 6.1 后端填充

**问题**: 前端 `MonthlyReturnHeatmap.tsx` 组件已有，但后端 `PMSBacktestReport.monthly_returns` 始终为 `None`。

**修复**: 在 `_run_v3_pms_backtest()` 中按月聚合收益率：

```python
def _calculate_monthly_returns(equity_curve: list[tuple[int, Decimal]]) -> dict[str, Decimal]:
    """按月计算收益率"""
    # 1. 按月分组
    # 2. 每月末权益 / 月初权益 - 1
    # 3. 返回 { "2024-01": 0.05, "2024-02": -0.02, ... }
```

---

## 依赖关系图

```
阶段 1 (P0 修复 + 分批止盈 + 实盘止盈追踪)
  ├── 阶段 2 (参数优化)
  │     └── 阶段 3 (Walk-Forward) — 依赖参数优化的 grid_search
  ├── 阶段 4 (基准对比 + Monte Carlo)
  ├── 阶段 5 (策略归因)
  └── 阶段 6 (月度收益热力图)

可并行: 阶段 2、4、5、6 在阶段 1 完成后可独立开发
        但建议串行执行以减少上下文切换
```

---

## 文件变更预估

| 文件 | 阶段 1 | 阶段 2 | 阶段 3 | 阶段 4 | 阶段 5 | 阶段 6 |
|------|--------|--------|--------|--------|--------|--------|
| `src/domain/models.py` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `src/domain/matching_engine.py` | ✅ | — | — | — | — | — |
| `src/application/backtester.py` | ✅ | ✅ | ✅ | ✅ | — | ✅ |
| `src/application/signal_pipeline.py` | ✅ | — | — | — | — | — |
| `src/interfaces/api.py` | — | ✅ | ✅ | — | — | — |
| `web-front/.../BacktestReportDetailModal.tsx` | ✅ | — | — | — | — | — |
| `web-front/.../MonthlyReturnHeatmap.tsx` | — | — | — | — | — | ✅ |
| 新文件（前端组件） | — | ✅ | ✅ | ✅ | ✅ | — |
| 测试文件 | ✅ | ✅ | ✅ | ✅ | — | — |
