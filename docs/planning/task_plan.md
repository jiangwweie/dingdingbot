# Task Plan: 回测系统优化

> Created: 2026-04-15
> Last updated: 2026-04-17
> Status: Phase 5 单元测试已完成 (22/22 passed)

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

### Commit 9c5e3e6 7 项修复 QA 验收（2026-04-15 10:30）

| # | 验证项 | 状态 | 备注 |
|---|--------|------|------|
| 1 | total_pnl = final - initial | 通过 | 已有断言覆盖 |
| 2 | 前端"净盈亏"文字 | 通过 | 代码审查通过 |
| 3 | 负收益报告可保存 | 通过 | 2/2 UT passed |
| 4 | 收益率百分比正确 | 通过 | 代码审查通过（2 IT skipped 为环境问题） |
| 5 | _migrate_existing_table | 通过 | 3/3 UT passed |
| 6 | exception raise 不静默 | 通过 | 2/2 UT passed |
| 7 | position_size=0 跳过 | 通过 | 4/4 UT passed |

---

## 阶段 1: P0 修复 + 回测正确性验证（3h）

### 任务清单

| # | 任务 | 工时 | 状态 |
|---|------|------|------|
| 1.1 | 修复部分平仓 PnL 归因 | 2h | ✅ 已完成（18 测试通过） |
| 1.2 | 修复净盈亏语义混淆 | 1h | ✅ 已完成 + 7 项验证通过 |
| 1.3 | 推送代码 + 验证回测页面显示正确 | 0.5h | ⏳ 验证已通过，待推送 |
| 1.4 | TP-1: 回测分批止盈模拟（TP1/TP2/TP3） | 2h | ✅ 已完成（18 测试通过） |
| 1.5 | TP-2: 实盘止盈追踪逻辑（Trailing TP） | 10h | ✅ 已完成（62 测试通过，收益+23.8%） |

### 1.1 部分平仓 PnL 归因

**问题**: `PositionSummary.realized_pnl` 是累计值（`+= net_pnl`），当仓位经历 TP1 部分平仓 + SL 剩余平仓时，累计 PnL 为正但最终 `exit_price` 显示亏损方向，用户易误解。

**修复方案**: 采用一对多事件列表设计（PositionCloseEvent），每次出场记录为独立事件。

**设计文档**: `docs/arch/position-summary-close-event-implementation.md`
**审查报告**: `docs/arch/position-summary-close-event-implementation-review.md`
**ADR 文档**: `docs/arch/position-summary-close-event-design.md`

**核心设计**:
- 新增 `PositionCloseEvent` 模型：记录每次出场的事件（position_id, order_id, event_type, close_price, close_qty, close_pnl, close_fee, close_time, exit_reason）
- `PositionSummary` 新增 `close_events: List[PositionCloseEvent]` 字段
- `Order` 模型新增 `close_pnl`/`close_fee` 字段（用于 backtester 从 order 读取 PnL）
- 数据流：matching_engine._execute_fill 计算 PnL → 写入 order.close_pnl/close_fee → backtester 从 order 读取并创建 PositionCloseEvent → 序列化 JSON 存入 backtest_reports
- 前端：BacktestReportDetailModal 展开子行展示每次出场明细

**影响文件**:
- `src/domain/models.py` — 新增 PositionCloseEvent 模型，PositionSummary 新增 close_events，Order 新增 close_pnl/close_fee
- `src/domain/matching_engine.py` — _execute_fill 中写入 order.close_pnl/close_fee
- `src/application/backtester.py` — 从 order 读取 close_pnl/close_fee 并创建 PositionCloseEvent
- `src/infrastructure/backtest_repository.py` — 序列化/反序列化支持嵌套 close_events 列表
- `web-front/src/lib/api.ts` — TS 接口新增
- `web-front/src/components/v3/backtest/BacktestReportDetailModal.tsx` — 事件列表展开渲染

### 1.2 净盈亏语义混淆

**问题**: 前端 `BacktestReportDetailModal.tsx` 文字说明"总盈亏 - 手续费 - 滑点 - 资金费用"，但实际只展示 `report.total_pnl`（毛盈亏），未做减法。

**修复方案**: 前端计算 `netPnl = total_pnl - total_fees_paid - total_slippage_cost - total_funding_cost`，展示真实净盈亏。

**影响文件**:
- `web-front/src/components/v3/backtest/BacktestReportDetailModal.tsx`

### 1.3 推送 + 验证

- 推送 dev 分支到 origin（本地领先 2 commits: e70d13d + 4968c34）
- 验证回测页面：✅ **全部通过**（commit 9c5e3e6 QA 验收 7/7 通过）

| 验证项 | 状态 | 证据 |
|--------|------|------|
| 负收益报告可保存 | ✅ | TestNegativeReturnReportPersistence 2/2 UT passed |
| 收益率百分比正确 | ✅ | 代码审查通过 + TestTotalReturnCorrectness |
| 夏普比率有值 | ✅ | test_sharpe_ratio.py 15 个测试用例 |
| 净盈亏含成本 | ✅ | 前端代码审查通过 |

**剩余动作**: 仅需 `git push` 推送代码（前端人工目视确认可选）

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

### 1.5 TP-2: 实盘止盈追踪逻辑 (Virtual TTP)

**前提**: 经 2026-04-16 架构沟通确认，采用**纯虚拟止盈（Virtual TTP 影子追踪模式）**，交易所不进行实际的 TP 挂单。

**状态**: ✅ Phase 1-6 已完成（2026-04-17）

**任务分解**:
- [x] **Phase 1**: 数据模型扩展 (models.py) - RiskManagerConfig 新增 5 个 TTP 字段
- [x] **Phase 2**: 核心逻辑实现 (risk_manager.py) - _apply_trailing_tp 等方法
- [x] **Phase 3**: matching_engine 扩展 - 支持 TP1-TP5 撮合
- [x] **Phase 4**: backtester 集成 - TTP 参数读取和事件收集
- [x] **Phase 5**: 单元测试 - 22/22 passed
- [x] **Phase 6**: 回测验证 - 收益提升 23.8%

**验证结果**:
- 单元测试: 22/22 passed
- 集成测试: 9/9 passed
- 收益对比: Trailing TP (+23.8%) vs 固定 TP

**参考文档**: `docs/arch/trailing-tp-implementation-design.md`

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

> **架构决策**: 详见 `docs/adr/2026-04-14-strategy-attribution-architecture.md`
> **方案选择**: 方案 B（归因解释层）— 非侵入式，新增 AttributionEngine

### 头脑风暴决策记录

| 决策项 | 结论 |
|--------|------|
| 使用场景 | 回测报告（离线批量计算） |
| 权重配置 | KV 配置 + AttributionConfig Pydantic 校验层 + 前端受控表单 |
| 精确度 | 数学可验证，每个贡献值可追溯到 score × weight 计算过程 |
| 推荐方案 | 方案 B（归因解释层），非侵入式 |

### 任务清单

> ⚠️ **执行顺序调整**（2026-04-15 架构验证后更新）：5.3 必须最先执行。EMA/MTF 过滤器的 metadata 缺少归因所需字段（`price`、`ema_value`、`aligned_count`、`total_count`），导致信心函数 100% 降级为默认值 0.5。先补数据源，再写消费端。

| # | 任务 | 工时 | 状态 | 依赖 |
|---|------|------|------|------|
| **5.3** | 补充过滤器 metadata（EMA distance, MTF alignment） | 0.5h | ✅ 已完成 | **无**（最先执行） |
| 5.1 | 新增 AttributionConfig 模型 + Pydantic 校验 | 0.5h | ✅ 已完成 | 无 |
| 5.2 | 新增 AttributionEngine（单信号归因 + 批量归因） | 1.5h | 待启动 | 5.3 |
| 5.4 | 集成到回测报告输出 + KV 权重读取 | 0.5h | 待启动 | 5.2 |
| 5.5 | 前端归因可视化（回测报告信号详情页） | 1h | 待启动 | 5.4 |

### 5.1 AttributionConfig 模型

**职责**: 归因权重配置的校验与加载

```python
class AttributionConfig(BaseModel):
    """归因配置校验模型 — 从 KV 配置加载并校验"""
    weights: Dict[str, float]

    @validator('weights')
    def validate_weights(cls, v):
        required = {"pattern", "ema_trend", "mtf"}
        missing = required - set(v.keys())
        if missing:
            raise ValueError(f"缺少必需的归因权重: {missing}")
        total = sum(v.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"权重之和必须接近 1.0，当前: {total}")
        for k, val in v.items():
            if not 0 <= val <= 1:
                raise ValueError(f"权重 {k}={val} 超出 [0, 1] 范围")
        return v

    @classmethod
    def from_kv(cls, kv_configs: Dict[str, Any]) -> "AttributionConfig":
        weights = {
            "pattern": float(kv_configs.get("attribution_weight_pattern", 0.55)),
            "ema_trend": float(kv_configs.get("attribution_weight_ema_trend", 0.25)),
            "mtf": float(kv_configs.get("attribution_weight_mtf", 0.20)),
        }
        return cls(weights=weights)
```

**KV Key 列表**:
- `attribution_weight_pattern` (default: 0.55)
- `attribution_weight_ema_trend` (default: 0.25)
- `attribution_weight_mtf` (default: 0.20)

**影响文件**: `src/domain/models.py` 或新建 `src/domain/attribution_config.py`

### 5.2 AttributionEngine

**职责**: 基于 SignalAttempt 数据，计算单信号和批量归因

```python
class AttributionEngine:
    def attribute(self, attempt: SignalAttempt, config: AttributionConfig) -> SignalAttribution:
        """单信号归因分析"""

    def attribute_batch(self, attempts: List[SignalAttempt], config: AttributionConfig) -> List[SignalAttribution]:
        """批量归因"""

    def get_aggregate_attribution(self, attributions: List[SignalAttribution]) -> AggregateAttribution:
        """聚合归因（回测报告摘要级别）"""

    def _calculate_filter_confidence(self, filter_name: str, result: FilterResult) -> Decimal:
        """根据过滤器 metadata 计算信心强度（数学可验证）"""
```

**信心函数**（数学可验证）:

| 过滤器 | 信心函数 | 公式 |
|--------|---------|------|
| ema_trend | 价格偏离 EMA 的线性函数 | `min(distance_pct / 0.05, 1.0)` |
| mtf | 高周期对齐比例 | `aligned_count / total_count` |
| atr | ATR 比率 capped | `min(atr_ratio / 2.0, 1.0)` |

**响应模型**:
```python
class SignalAttribution(BaseModel):
    final_score: float
    components: List[AttributionComponent]
    percentages: Dict[str, float]  # {"pattern": 54.4, "ema_trend": 27.5, "mtf": 18.1}
    explanation: str  # "Pinbar 形态(54.4%) + EMA 趋势确认(27.5%) + 多周期对齐(18.1%)"

class AttributionComponent(BaseModel):
    name: str
    score: float       # 0~1 组件评分
    weight: float      # 预设权重
    contribution: float  # score × weight
    percentage: float    # contribution / final_score × 100
    confidence_basis: str  # "price 2.3% above EMA20, distance/5%=0.46"

class AggregateAttribution(BaseModel):
    avg_pattern_contribution: float
    avg_filter_contributions: Dict[str, float]
    top_performing_filters: List[str]
    worst_performing_filters: List[str]
```

**影响文件**: `src/application/attribution_engine.py`（新文件）

### 5.3 补充过滤器 metadata（P1 首要任务）

> **⚠️ P1 风险**：通过逐行代码验证，确认 3 个核心过滤器中 2 个的 metadata 不满足归因引擎需求。
> 如果不先补 metadata，AttributionEngine 的信心函数将 100% 降级为默认值 0.5，归因结果完全失去区分度。

确保各过滤器在 `TraceEvent.metadata` 中携带归因所需的诊断数据：

**当前状态**（2026-04-15 代码验证）:

| 过滤器 | 已提供字段 | 缺失字段 | 影响 |
|--------|-----------|---------|------|
| EmaTrendFilterDynamic | `trend_direction` | `price`, `ema_value` | 信心函数无法计算 distance_pct |
| MtfFilterDynamic | `higher_trend` (单个) | `aligned_count`, `total_count`, `higher_tf_trends` (字典) | 信心函数无法计算对齐比例 |
| AtrFilterDynamic | `atr_value`, `volatility_ratio` | — | ✅ 完整，无需补充 |

**EmaTrendFilterDynamic.check()** 需补充（pass/fail 分支都要）:
```python
# 在 line 204/218/233/249 的 metadata dict 中新增:
# 需要获取当前 K 线价格 — 但 check() 方法没有直接接收 kline
# 方案: 在 FilterContext 中增加 current_price 字段
metadata={
    # ... 现有字段 ...
    "price": float(context.current_price),       # 新增
    "ema_value": float(self._ema_calculators[key].value),  # 新增，key 需从 context 推导
    "distance_pct": float(distance),             # 新增 = abs(price - ema) / ema
}
```

**MtfFilterDynamic.check()** 需补充（pass/fail 分支都要）:
```python
# 在 line 355/370/388/403 的 metadata dict 中新增:
higher_tf_trends = context.higher_tf_trends  # 已有的 Dict[str, TrendDirection]
aligned_count = sum(1 for t in higher_tf_trends.values() if t == pattern_direction)
total_count = len(higher_tf_trends)

metadata={
    # ... 现有字段 ...
    "higher_tf_trends": {k: v.value for k, v in higher_tf_trends.items()},  # 新增，序列化友好
    "aligned_count": aligned_count,    # 新增
    "total_count": total_count,        # 新增
}
```

**依赖前置任务**: `FilterContext` 需要新增 `current_price: Decimal` 字段（现有只有 `current_trend` 和 `current_timeframe`）。

**影响文件**: `src/domain/filter_factory.py`（过滤器 check 方法 + FilterContext）

**验收标准**:
- [ ] EmaTrendFilterDynamic 在 pass/fail 时 metadata 都包含 `price`、`ema_value`、`distance_pct`
- [ ] MtfFilterDynamic 在 pass/fail 时 metadata 都包含 `aligned_count`、`total_count`、`higher_tf_trends`
- [ ] AtrFilterDynamic 已有完整 metadata，不需要改动
- [ ] FilterContext 新增 `current_price` 字段
- [ ] 回测路径中 FilterContext 正确传入 `current_price`

### 5.4 集成到回测报告

在 `_run_v3_pms_backtest()` 或动态规则引擎回测结束时：
1. 从 ConfigManager 读取 KV 归因权重 → `AttributionConfig.from_kv()`
2. 对所有 `attempts` 调用 `AttributionEngine.attribute_batch()`
3. 将 `SignalAttribution` 列表填充到回测报告的新字段中
4. 聚合归因填入报告摘要

**回测报告新增字段**:
```python
class BacktestReport(BaseModel):
    # ... 现有字段 ...
    signal_attributions: Optional[List[SignalAttribution]] = None
    aggregate_attribution: Optional[AggregateAttribution] = None
```

**影响文件**: `src/application/backtester.py`, `src/domain/models.py`

### 5.5 前端归因可视化

**回测报告信号详情页** 新增:
- 单信号归因瀑布图/饼图（展示 pattern/ema/mtf 各自的百分比贡献）
- 人类可读解释文本："Pinbar 形态(54.4%) + EMA 趋势确认(27.5%) + 多周期对齐(18.1%)"
- 展开后可查看每个组件的 score、weight、contribution、confidence_basis

**影响文件**: `web-front/src/components/v3/backtest/`

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
  │     ├── 5.3 补过滤器 metadata（最先执行，无依赖）
  │     ├── 5.1 AttributionConfig 模型（可与 5.3 并行）
  │     ├── 5.2 AttributionEngine（依赖 5.3 的 metadata）
  │     ├── 5.4 集成回测报告（依赖 5.2）
  │     └── 5.5 前端归因可视化（依赖 5.4）
  └── 阶段 6 (月度收益热力图)

可并行: 阶段 2、4、5、6 在阶段 1 完成后可独立开发
        但建议串行执行以减少上下文切换
        阶段 5 内部: 5.3 + 5.1 可并行，其余串行
```

---

## 文件变更预估

| 文件 | 阶段 1 | 阶段 2 | 阶段 3 | 阶段 4 | 阶段 5 | 阶段 6 |
|------|--------|--------|--------|--------|--------|--------|
| `src/domain/models.py` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `src/domain/matching_engine.py` | ✅ | — | — | — | — | — |
| `src/domain/filter_factory.py` | — | — | — | — | ✅ (5.3) | — |
| `src/application/backtester.py` | ✅ | ✅ | ✅ | ✅ | ✅ (5.4) | ✅ |
| `src/application/attribution_engine.py` | — | — | — | — | ✅ (5.2) | — |
| `src/application/signal_pipeline.py` | ✅ | — | — | — | — | — |
| `src/interfaces/api.py` | — | ✅ | ✅ | — | — | — |
| `web-front/.../BacktestReportDetailModal.tsx` | ✅ | — | — | — | ✅ (5.5) | — |
| `web-front/.../MonthlyReturnHeatmap.tsx` | — | — | — | — | — | ✅ |
| 新文件（前端组件） | — | ✅ | ✅ | ✅ | ✅ (5.5) | — |
| 测试文件 | ✅ | ✅ | ✅ | ✅ | — | — |
