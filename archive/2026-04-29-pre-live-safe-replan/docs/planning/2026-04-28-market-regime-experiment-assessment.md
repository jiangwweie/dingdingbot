# Market Regime 实验支持度评估 + 实验矩阵 + SHORT 研究时机分析

> **日期**: 2026-04-28
> **性质**: 只读分析，不改代码，服务策略研究决策
> **输入**: 仓库内代码 + 文档 + 脚本证据

---

## 任务 1：上层 Market Regime 实验支持度评估

### A. 当前已具备的支持能力

**1. 回测链已有 regime 参数槽位（旧版）**

`BacktestConfig` 和 `BacktestRequest` 中已预留了 regime 相关字段：
- `regime_ema_period: int = 200`（`src/domain/models.py:49`）
- `regime_adx_period: int = 14`（`src/domain/models.py:50`）
- `regime_adx_threshold: float = 25.0`（`src/domain/models.py:51`）

这些字段定义了"价格 > EMA200 + ADX > 阈值 = trending regime"的语义。但**这些字段存在于旧版 BacktestConfig（pandas-vectorized 版本），不在当前 v3_pms 回测引擎的 `BacktestRuntimeOverrides` 或 `ResolvedBacktestParams` 中**。

**2. EMA 计算器支持任意周期**

`EMACalculator`（`src/domain/indicators.py:149`）接受任意 `period` 参数，无上限限制。EMA250 完全可以计算。已有 `bulk_update` 方法用于预热。

**3. 1d 数据接入能力已存在**

`HistoricalDataRepository` 支持 `1d` timeframe（`src/infrastructure/historical_data_repository.py` 中 `"1d": 1440` 映射）。`Backtester._parse_timeframe` 也支持 `1d`（`src/application/backtester.py:851`）。`test_minimal_regime_filter.py` 脚本已实际加载了 1d 数据并计算 EMA60。

**4. MTF mapping 已包含 1h→4h→1d 链**

`MtfFilterDynamic.MTF_MAPPING`（`src/domain/filter_factory.py:326-331`）和 `BACKTEST_PARAM_DEFAULTS.mtf_mapping`（`src/domain/models.py:2755-2760`）都定义了 `{"1h": "4h", "4h": "1d"}` 链。这意味着 1d 数据在 MTF 体系中已经是"可到达"的时间框架。

**5. EMA trend filter 已有 direction-aware 逻辑**

`EmaTrendFilterDynamic.check()`（`src/domain/filter_factory.py:166-312`）根据 `pattern.direction` 区分 LONG/SHORT：
- LONG + BULLISH trend → pass
- SHORT + BEARISH trend → pass

这与"日线 EMA250 之上才允许 LONG"的语义高度一致。

**6. 已有外部 gating 研究原型**

`scripts/test_minimal_regime_filter.py` 已实现了"1d close > EMA60 才允许 1h LONG"的外部 gating 实验。它展示了完整的研究层工作流：跑主线回测 → 加载 1d 数据 → 计算 regime → 过滤仓位 → 比较 proxy metrics。

**7. StrategyRunner / DynamicStrategyRun 支持 filter chain 扩展**

`StrategyRunner`（`src/domain/strategy_engine.py:458`）和 `DynamicStrategyRun`（`src/domain/strategy_engine.py:641`）都支持在 filter chain 中插入新 filter。`FilterFactory._registry`（`src/domain/filter_factory.py:720-729`）支持注册新 filter 类型。

**8. 已有 attribution / diagnostics 机制**

`TraceEvent`（`src/domain/filter_factory.py:23-43`）记录 `expected` vs `actual`，`metadata` 包含 `trend_direction`、`distance_pct`、`ema_value` 等归因字段。`SignalAttempt` 记录每个 filter 的 pass/fail 和 reason。

**9. allowed_directions 已有全局控制**

`BacktestRuntimeOverrides.allowed_directions`（`src/domain/models.py:2675`）和 `BASELINE_RUNTIME_OVERRIDES`（`src/application/research_control_plane.py:42`）已设置 `["LONG"]`。但这是**全局开关**，不是按 regime 条件切换的。

---

### B. 最小可行实现路径

**路径：研究层外部 gating（与 `test_minimal_regime_filter.py` 同模式）**

这是当前最接近的复用点，改动最小：

1. **复用 `EMACalculator`**：用 `EMACalculator(period=250)` 计算 1d EMA250
2. **复用 `HistoricalDataRepository`**：加载 1d K 线数据
3. **复用 `Backtester` + `BacktestRuntimeOverrides`**：跑主线回测
4. **复用 `compute_proxy_metrics`**：计算过滤后的 proxy PnL / Sharpe / MaxDD
5. **新增 regime 判断逻辑**：`1d_close > EMA250` → bull regime → 允许 LONG entry

具体步骤：
- 写一个新的研究脚本（类似 `test_minimal_regime_filter.py`），将 EMA period 从 60 改为 250
- 对每个仓位，检查 entry_time 对应的上一根已闭合 1d K 线的 close 是否 > 1d EMA250
- 保留仓位或剔除仓位，计算 proxy metrics
- 对比 2023/2024/2025 分年结果

**不需要修改回测引擎、不需要新增 filter、不需要修改 BacktestRuntimeOverrides**。

---

### C. 当前缺口

**1. BacktestRuntimeOverrides 没有 regime 参数**

当前 `BacktestRuntimeOverrides`（`src/domain/models.py:2650-2682`）没有 `regime_ema_period`、`regime_timeframe`、`regime_gate_type` 等字段。如果要把 regime gate 正式纳入回测引擎，需要新增这些字段。

**2. ResolvedBacktestParams 没有 regime 参数**

`ResolvedBacktestParams`（`src/domain/models.py:2685-2723`）也没有 regime 相关字段。这意味着 v3_pms 回测引擎无法通过参数注入来启用 regime filter。

**3. v3_pms 回测引擎没有 regime filter 挂点**

当前 v3_pms 回测引擎的 filter chain 是：`[ema_trend] + [mtf] + [atr]`（可选）。没有"regime gate"这个挂点。旧版 BacktestConfig 有 `regime_filter`，但那是 pandas-vectorized 版本的，不在当前引擎中。

**4. allowed_directions 是全局开关，不支持 regime 条件切换**

`allowed_directions=["LONG"]` 是整个回测期间的全局配置。无法表达"bull regime 时 LONG，bear regime 时不开"的语义。

**5. 研究层 proxy metrics 不等于 true equity curve**

`test_minimal_regime_filter.py` 的 `compute_proxy_metrics` 计算的是仓位级 PnL 累加，不是真正的 equity curve（因为剔除仓位后，资金利用率不同，后续仓位的 position sizing 也会变化）。这是研究层 proxy，不是引擎级正式回测。

**6. 没有 regime attribution 机制**

当前 `backtest_attributions` 表（`src/infrastructure/backtest_repository.py:164-173`）没有 regime 维度。无法在正式回测结果中记录"这个信号在 bull/bear regime 下分别表现如何"。

---

### D. 不建议的实现方式

**1. 不建议把 regime filter 硬塞进当前 v3_pms 回测引擎**

理由：当前引擎的 filter chain 是基于 `StrategyRunner` / `DynamicStrategyRun` 的实时信号处理架构，regime gate 是"入场前外部条件判断"，不是"形态检测后的 filter check"。语义层级不同。硬塞会混淆"信号质量 filter"和"市场环境 gate"。

**2. 不建议修改 `allowed_directions` 为动态值**

`allowed_directions` 是回测配置参数，应该在回测开始前确定。让它随 regime 动态切换意味着引擎需要实时判断 regime 状态，这改变了引擎的语义模型。

**3. 不建议在 MTF filter 中叠加 regime 逻辑**

MTF filter 的语义是"高周期趋势方向是否与信号方向一致"。regime gate 的语义是"当前市场状态是否允许开仓"。两者不是同一层判断。叠加会让 MTF filter 承担不属于它的职责。

**4. 不建议直接修改 sim1_eth_runtime 冻结主线**

已有文档明确约束（`docs/planning/2026-04-25-eth-baseline-market-regime-boundary-analysis.md:299-303`）：研究链不反向污染 runtime。regime 实验应保持在研究层。

---

## 任务 2：Market Regime 边界实验矩阵设计

### A. 实验目的

验证以下假设：
1. 2023 LONG-only 失效是否可以通过上层牛熊分型显著改善（减少亏损幅度）
2. LONG-only 是否应该只在 bull regime 下开仓
3. bear regime 下是"空仓"更合理，还是值得后续单独研究 SHORT
4. regime gate 是否只是"少交易"（减少暴露），还是能"改善收益质量"（提高 win rate / Sharpe）

### B. 实验矩阵

| 编号 | 实验名称 | Regime 定义 | Regime 为 bull 时 | Regime 为 bear 时 |
|------|----------|------------|-------------------|-------------------|
| **E0** | 基线对照 | 无 regime gate | LONG-only 全时段 | LONG-only 全时段 |
| **E1** | daily EMA250 bull-only | 1d close > EMA(250) | 允许 LONG | 不开仓（空仓） |
| **E2** | daily EMA250 + slope | 1d close > EMA(250) AND EMA(250) slope > 0 | 允许 LONG | 不开仓 |
| **E3** | daily EMA200 bull-only | 1d close > EMA(200) | 允许 LONG | 不开仓 |
| **E4** | daily EMA250 bull/bear-flat | 1d close > EMA(250) | 允许 LONG | 不开仓，但记录"如果开 LONG 会怎样"（shadow tracking） |

**补充说明**：
- E4 的 shadow tracking 不影响真实 PnL，只用于回答"bear regime 下 LONG 的实际表现"，为后续 SHORT 研究提供对照
- E2 的 slope > 0 定义：EMA(250) 当前值 > EMA(250) 5 根前值（1d 级别 5 天前），表示趋势正在向上，而非刚从下方穿越

### C. 每组固定参数与可变参数

**固定参数（所有实验共用，与冻结基线一致）**：

| 参数 | 值 | 来源 |
|------|-----|------|
| symbol | ETH/USDT:USDT | `BASELINE_RUNTIME_OVERRIDES` |
| timeframe | 1h | `BASELINE_RUNTIME_OVERRIDES` |
| direction | LONG-only | `BASELINE_RUNTIME_OVERRIDES.allowed_directions=["LONG"]` |
| ema_period | 50 | `BASELINE_RUNTIME_OVERRIDES.ema_period=50` |
| min_distance_pct | 0.005 | `BASELINE_RUNTIME_OVERRIDES` |
| tp_ratios | [0.5, 0.5] | `BASELINE_RUNTIME_OVERRIDES` |
| tp_targets | [1.0, 3.5] | `BASELINE_RUNTIME_OVERRIDES` |
| breakeven_enabled | False | `BASELINE_RUNTIME_OVERRIDES` |
| mtf_mapping | {"1h": "4h"} | 基线 profile |
| mtf_ema_period | 60 | 基线 profile |
| pinbar | wick=0.6, body=0.3, pos=0.1 | 基线 profile |
| costs | BNB9 slippage/fee | 研究脚本约定 |

**可变参数（每组唯一差异）**：

| 实验 | 可变参数 | 值 |
|------|----------|-----|
| E0 | regime gate | None（无 gate） |
| E1 | regime_ema_period | 250 |
| E1 | regime_timeframe | 1d |
| E1 | regime_condition | close > EMA |
| E2 | regime_ema_period | 250 |
| E2 | regime_timeframe | 1d |
| E2 | regime_condition | close > EMA AND EMA_slope > 0 |
| E3 | regime_ema_period | 200 |
| E3 | regime_timeframe | 1d |
| E3 | regime_condition | close > EMA |
| E4 | regime_ema_period | 250 |
| E4 | regime_timeframe | 1d |
| E4 | regime_condition | close > EMA |
| E4 | shadow_tracking | True（bear regime 下记录虚拟 LONG 结果） |

### D. 判定标准

**每组实验必须报告的指标**：

| 指标 | 2023 | 2024 | 2025 | 全期 |
|------|------|------|------|------|
| PnL (USDT) | ✅ | ✅ | ✅ | ✅ |
| Trades | ✅ | ✅ | ✅ | ✅ |
| Win Rate | ✅ | ✅ | ✅ | ✅ |
| Sharpe (proxy) | ✅ | ✅ | ✅ | ✅ |
| MaxDD (proxy) | ✅ | ✅ | ✅ | ✅ |
| MFE avg | ✅ | ✅ | ✅ | - |
| MAE avg | ✅ | ✅ | ✅ | - |
| +1R reach rate | ✅ | ✅ | ✅ | - |
| +2R reach rate | ✅ | ✅ | ✅ | - |
| +3.5R reach rate | ✅ | ✅ | ✅ | - |
| first-touch (先到+0.5R vs 先到-0.5R) | ✅ | ✅ | ✅ | - |
| regime bull/bear 交易日占比 | ✅ | ✅ | ✅ | ✅ |

**判定逻辑**：

1. **是否显著减少 2023 亏损**：
   - 2023 PnL 改善幅度 > 50% 基线亏损（即从 -3583 改善到 > -1791）→ 显著
   - 2023 PnL 改善幅度 < 30% 基线亏损 → 不显著
   - 介于两者之间 → 需要更多证据

2. **是否尽量保住 2024/2025 收益**：
   - 2024 PnL 下降 < 20%（基线 +5952，实验 > +4761）→ 保住
   - 2024 PnL 下降 > 40% → 代价过大
   - 2025 同理（基线 +4399，实验 > +3519）

3. **是"少交易"还是"改善收益质量"**：
   - 如果 win rate 提升 > 5% 且 trades 下降 < 30% → 改善质量
   - 如果 win rate 不变且 trades 大幅下降 → 只是少交易
   - 如果 Sharpe 提升 > 0.5 且 trades 下降 < 40% → 改善质量

4. **是否值得进入下一轮 SHORT 研究**：
   - E4 shadow tracking 显示 bear regime 下 LONG 的 win rate < 20% → SHORT 有独立研究价值
   - E4 shadow tracking 显示 bear regime 下 LONG 的 win rate > 30% → SHORT 可能只是镜像，研究价值有限

### E. 下一步研究分叉条件

**分叉 A：regime gate 有效 → 进入 regime 正式化**
- 条件：至少一组实验满足"2023 显著改善 + 2024/2025 保住"
- 下一步：将 regime gate 正式纳入回测引擎（新增 BacktestRuntimeOverrides 字段 + regime filter）
- 不进入 SHORT 研究

**分叉 B：regime gate 只是少交易 → 继续探索更精细的 regime 定义**
- 条件：所有实验都只是减少 trades，win rate / Sharpe 没有实质改善
- 下一步：尝试更精细的 regime 定义（如 EMA slope + ADX + volatility contraction）
- 不进入 SHORT 研究

**分叉 C：regime gate 有效且 bear regime 下 LONG 确实无效 → 开启 SHORT 独立研究线**
- 条件：E4 shadow tracking 证明 bear regime 下 LONG win rate < 20%
- 下一步：先完成 regime gate 正式化，再开启 SHORT 独立参数研究
- SHORT 不镜像 LONG 参数，需要独立参数搜索

**分叉 D：regime gate 无效（2024/2025 代价过大）→ 放弃 regime gate，接受策略有适用边界**
- 条件：所有实验导致 2024/2025 PnL 下降 > 40%
- 下一步：不加 regime gate，接受"这条策略只在 bull market 下适用"的事实，转向策略组合研究
- 不进入 SHORT 研究

---

## 任务 3：SHORT 独立研究线启动时机评估

### A. 现有证据支持度

**1. LONG-only 失效边界来自 bear/sideways regime — 证据充分**

- `docs/planning/2023-failure-attribution-report.md`：2023 全年仅 1 月盈利，2-7 月连续亏损 Win Rate=0%，归因排序第一是"趋势环境不适配"
- `docs/planning/2026-04-25-eth-baseline-market-regime-boundary-analysis.md`：结论"2023 并不是否定 Pinbar 本身，而是否定 LONG-only + regime mismatch"
- 2023 MFE 更低、MAE 不恶化、+1R/+2R/+3.5R 可达率显著更低 → 说明不是"进场后大幅逆行"，而是"向上空间不足"

**2. SHORT 值得作为独立研究对象 — 证据间接，尚不充分**

- 当前没有 SHORT 回测数据（`allowed_directions=["LONG"]` 是冻结基线）
- `docs/analysis/eth-1h-oos-failure-analysis.md` 提到旧基线（ema=111）中 SHORT 侧亏损 -1744 吃掉 LONG 利润 +1502，但这用的是旧参数和"both"模式，不是独立 SHORT 参数线
- 没有专门针对 bear regime 的 SHORT 回测实验
- E4 shadow tracking（如果执行）可以提供间接证据

**结论**：LONG-only 失效边界来自 regime mismatch 的证据充分（9/10），但 SHORT 是否值得独立研究的证据尚不充分（3/10），需要 regime 实验结果来补充。

### B. SHORT 是否应视为新策略物种

**是的，SHORT 应被视为新策略物种，不应默认镜像 LONG 参数。**

理由：

| 参数 | LONG 基线值 | 是否应镜像 | 原因 |
|------|------------|-----------|------|
| ema_period | 50 | **不应镜像** | SHORT 在 bear regime 下，EMA 的语义是"价格 < EMA = 确认下行"。bear regime 波动结构不同，最优 EMA period 可能不同 |
| min_distance_pct | 0.005 | **不应镜像** | bear regime 的 EMA 距离分布与 bull regime 不同，需要独立搜索 |
| mtf filter | 1h→4h | **可共用框架** | MTF 验证逻辑（高周期趋势方向一致）对 SHORT 同样适用，但 mtf_ema_period 可能不同 |
| pinbar 几何 | wick=0.6, body=0.3, pos=0.1 | **可共用** | Pinbar 形态检测是 color-agnostic 的，几何参数不依赖方向 |
| tp_ratios | [0.5, 0.5] | **不应镜像** | bear regime 下趋势延续空间可能更短，TP 分配可能需要更保守（如 [0.6, 0.4]） |
| tp_targets | [1.0, 3.5] | **不应镜像** | bear regime 的 follow-through 可能更短，TP2 target 可能需要降低（如 [1.0, 2.5]） |
| breakeven | False | **需要独立验证** | bear regime 下 BE 是否有价值需要实验 |
| risk / exposure | 1% / 1.0x | **不应镜像** | SHORT 在 bear regime 下的风险特征不同（下行趋势可能更剧烈），需要独立风控参数 |
| trailing stop | False | **需要独立验证** | bear regime 下 trailing 是否更有价值 |

**核心论点**：LONG 和 SHORT 虽然共享 Pinbar 形态检测和 MTF 框架，但它们面对的市场结构完全不同（bull = 趋势延续 vs bear = 趋势加速/震荡反弹）。参数不应默认镜像。

### C. 推荐研究顺序

**推荐顺序 C：先验证 regime gate，再开 SHORT 独立参数线**

理由：

1. **regime gate 是前置条件**：如果 regime gate 无效（bull-only 不能改善 2023），那么 SHORT 研究的前提就不成立——我们不知道 bear regime 是否真的与 LONG regime 有本质差异
2. **regime gate 验证成本低**：研究层外部 gating 脚本即可，不需要修改引擎
3. **SHORT 研究成本高**：需要独立参数搜索（ema、distance、tp、risk），至少需要一轮 Optuna 搜索
4. **regime gate 结果决定 SHORT 是否值得**：E4 shadow tracking 可以告诉我们 bear regime 下 LONG 的实际 win rate，这是 SHORT 研究是否有价值的关键证据

具体顺序：
```
Step 1: 执行 E0-E4 regime 实验矩阵（研究层，不改引擎）
Step 2: 分析 E4 shadow tracking → 判断 bear regime 下 LONG 是否确实无效
Step 3: 如果 bear regime 下 LONG win rate < 20% → 开启 SHORT 独立参数研究线
Step 4: SHORT 独立参数搜索（ema、distance、tp、risk 各自搜索）
Step 5: SHORT + regime gate 组合验证（bear regime 下 SHORT-only）
```

**不推荐顺序 A（先做 bull-only / bear-flat）**：这其实就是 E1 实验，是 Step 1 的一部分，不是独立的研究顺序。

**不推荐顺序 B（直接做 bull-long / bear-short）**：这跳过了 regime gate 验证，直接假设 SHORT 在 bear regime 下有效。没有证据支持这个假设。

### D. 当前不建议直接做的事

**1. 不建议现在就开 SHORT 独立参数搜索**

理由：regime gate 实验尚未执行，不知道 bear regime 下 LONG 的实际表现。SHORT 研究的前提是"bear regime 下 LONG 确实无效"，这个前提需要先验证。

**2. 不建议把 SHORT 参数默认镜像 LONG**

理由：如 B 部分分析，至少 ema_period、min_distance_pct、tp_ratios、tp_targets、risk 参数不应镜像。默认镜像会产生虚假的"SHORT 也亏损"结论。

**3. 不建议在 sim1_eth_runtime 中加入 SHORT**

理由：当前 Sim-1 是 LONG-only 冻结观察期。加入 SHORT 会改变 runtime 语义，违反"研究链不反向污染 runtime"的约束。

**4. 不建议用"both"模式跑回测来评估 SHORT**

理由：`allowed_directions=["both"]` 会让 LONG 和 SHORT 在同一回测中竞争资金，无法独立评估 SHORT 的表现。SHORT 需要独立的 SHORT-only 回测。

**5. 不建议把 SHORT 研究和 regime gate 研究合并为一个大任务**

理由：两者依赖关系明确（regime gate → SHORT），合并会导致任务过大、无法分步验证。应该先完成 regime gate 实验，再根据结果决定是否开启 SHORT 研究线。

---

## 总结

| 维度 | 结论 |
|------|------|
| 回测链支持 regime 实验 | **研究层已具备**（外部 gating 脚本模式），**引擎层尚不具备**（无 regime 参数/挂点） |
| 最小可行路径 | 复用 `test_minimal_regime_filter.py` 模式，EMA period 从 60 改为 250，不改引擎 |
| 实验矩阵 | E0-E4 共 5 组，核心差异是 regime 定义（EMA250/EMA200/EMA250+slope/shadow tracking） |
| SHORT 研究时机 | **不应现在开启**，应先完成 regime gate 实验，再根据 E4 shadow tracking 结果决定 |
| SHORT 参数策略 | **不应镜像 LONG**，至少 6 个参数需要独立搜索 |
| 推荐研究顺序 | C：regime gate → shadow tracking → SHORT 独立参数线 |
