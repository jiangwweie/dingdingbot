# ETH Baseline 策略研究复盘（2026-04-09 ～ 2026-04-29）

> **目标读者**: 外部量化交易从业者（懂回测、懂风控、懂趋势/反转策略，但完全不了解本项目）
> **性质**: research-only 策略复盘，不涉及代码修改
> **时间范围**: 2026-04-09（研究起点）～ 2026-04-29（当前）

---

## Executive Summary

**核心结论**（10 条要点，2 分钟理解全局）：

1. **策略本体**：ETH/USDT:USDT 1h 周期，LONG-only Pinbar 形态策略，EMA50 趋势过滤 + MTF（多周期趋势确认），TP=[1.0R, 3.5R] 两级止盈。

2. **基线确认**：经过 3 轮参数搜索（EMA、ATR、距离过滤）和跨币种/跨周期验证，**ETH 1h 是唯一可行路径**。BTC/SOL/ETH 4h/15m 全部失败。

3. **年度表现**（BNB9 实盘成本）：
   - 2023: -3,924 USDT（WR=16.1%, Sharpe=-2.63, MaxDD=49.19%）— **失效**
   - 2024: +8,501 USDT（WR=32.3%, Sharpe=1.91, MaxDD=17.39%）— **适配**
   - 2025: +4,490 USDT（WR=31.7%, Sharpe=2.01, MaxDD=11.56%）— **适配**
   - 3yr 累计: +9,067 USDT（Sharpe=0.71）

4. **研究主线**：2023 亏损是市场环境不匹配（regime mismatch），不是参数可调优的。H0→H3a 五次实验穷尽所有合理调整维度，全部失败。

5. **市场诊断**（M0 Strategy Ecology）：
   - Pinbar 是**反趋势策略**，在低斜率、低波动环境赚钱
   - 高波动、近期涨幅大、价格接近 Donchian 通道顶部时系统性亏损
   - 2023 ATR percentile=0.625 vs 2024/25=0.531（2023 波动更高）

6. **Toxic State 过滤**（M1）：
   - 4 个单因子 filter（ema_4h_slope、recent_72h、volatility、donchian_distance）独立通过全部 PASS 标准
   - E1（ema_4h_slope）最优：3yr PnL 从 -2,158 翻正到 +1,314，2023 亏损减少 51.2%

7. **P0 Official 验证失败**：
   - E4（donchian_distance）在正式 Backtester v3_pms 下确认生效，但**过滤过度**
   - 2023 亏损降低 57.9%，但 2024/2025 收益被大量牺牲，3yr PnL 从 +3,789 恶化到 -1,924
   - **判定：FAIL**。E4 是有效风险因子，但不适合作为当前固定硬过滤器

8. **资金参数审计**（R1b）：
   - R1 原报告 MaxDD 严重错误（0.32% vs 实际 32.42%）
   - 在 `MaxDD <= 35%` 约束下，存在 2 组可行配置：
     - exposure=1.25, risk=0.5%: PnL=+2,346, MaxDD=33.74%
     - exposure=1.0, risk=0.5%: PnL=+2,113, MaxDD=32.42%
   - **但这不够"激励"**：用户期待的 2024/2025 高收益被 35% 回撤约束压制

9. **关键踩坑**（12 个方法论风险）：
   - lookahead bias（未来函数）、same-bar entry（同 bar 入场）、kline_history 未传递
   - proxy vs official 口径不一致、reach rate ≠ PnL、low correlation ≠ 组合有效
   - report.max_drawdown 不能直接当真实 MaxDD、风险参数传错入口
   - account_snapshot.positions=[] 导致 exposure cap 失效
   - research 结论不能直接污染 runtime

10. **当前状态**：
    - 基线已冻结，Sim-1 已部署进入自然模拟盘观察
    - 研究主线从"继续救 2023"切换为"定义市场适用边界"
    - E4 应从"硬过滤器"降级为"风险状态标签/仓位降权因子"继续研究

---

## 1. Strategy Background

### 1.1 策略本体是什么

**交易标的**：ETH/USDT:USDT（USDT 本位合约）

**时间周期**：1h（主周期），4h（MTF 辅助周期，用于趋势确认）

**方向**：LONG-only（只做多）

**入场逻辑**：
- **Pinbar 形态检测**（颜色不敏感）：
  - 看涨 Pinbar：长下影线，实体在顶部
  - 参数：min_wick_ratio=0.6, max_body_ratio=0.3, body_position_tolerance=0.1
- **趋势过滤**：
  - EMA50：价格必须在 EMA50 之上（LONG 方向）
  - min_distance_pct=0.005：价格必须脱离 EMA50 至少 0.5%
- **MTF（多周期趋势确认）**：
  - 4h EMA60：高周期 EMA 必须向上（确认大趋势向上）

**出场逻辑**：
- **两级止盈**：
  - TP1: 1.0R（风险回报比 1:1），平仓 50%
  - TP2: 3.5R（风险回报比 1:3.5），平仓剩余 50%
- **止损**：
  - 初始止损：Pinbar 信号 K 线的最低点
  - Breakeven：TP1 成交后，剩余仓位的止损移到入场价（**已禁用**）
- **Trailing Stop**：已禁用

**风控逻辑**：
- 单笔最大损失：1% 账户权益（默认档）或 2%（激进档）
- 最大杠杆：20x
- 最大总敞口：80%（名义价值/账户权益）
- 每日最大交易次数：50
- 每日最大回撤：5%

**成本参数**（BNB9 实盘口径）：
- 入场滑点：0.01%
- 止盈滑点：0%
- 手续费：0.0405%（BNB 9折）

### 1.2 当前基线大致结构

```
策略结构基线：ETH 1h LONG-only
执行结构基线：BE=False, tp=[1.0,3.5], tp_ratios=[0.5,0.5]
过滤结构基线：ema=50, min_distance_pct=0.005, ATR 移除
资金默认基线：max_loss_percent=1.0%
```

**已锁定的关键决策**：
- LONG-only 优于双向（3yr PnL 改善 +175%）
- BE=False 更优（3yr PnL 改善 +47%）
- ATR 过滤器冗余（有无 ATR 结果完全相同）
- EMA50 最优（vs EMA60 系统默认）
- TP=[1.0, 3.5] 最优（vs [1.0, 2.5]）

### 1.3 研究目标是什么

**不是单一目标，而是三条并行线**：

1. **2023 救援线**（已关闭）：
   - 目标：判断 2023 亏损是否可通过参数/规则调整救回
   - 结论：**不能**。H0→H3a 五次实验穷尽所有合理维度，全部失败
   - 判定：2023 是策略适用边界成本，不是下一轮参数搜索目标

2. **市场边界线**（当前主线）：
   - 目标：识别 Pinbar 在什么市场状态下赚钱、什么状态下亏钱
   - 进展：M0 诊断完成，M1 证明单因子 filter 有效，P0 验证 E4 过滤过度
   - 下一步：E4 从"硬过滤器"降级为"风险状态标签/仓位降权因子"

3. **资金参数线**（已部分完成）：
   - 目标：找到风险/收益平衡的资金配置
   - 进展：R1b 审计确认在 `MaxDD <= 35%` 下存在可行配置，但收益不够"激励"
   - 下一步：设计激励型资金上限实验，不再用单一回撤约束压制全部目标

### 1.4 项目当前阶段

**Sim-1 观察期**（2026-04 起）：
- 执行主线 PG 闭环已完成（orders/intents/positions/signals 全部迁移到 PostgreSQL）
- Sim-1 已部署到 Mac mini Docker，进入自然模拟盘观察
- 当前主线：观察与策略研究，不做 runtime 热改
- 研究链：Research Control Plane v1 已落地，支持从前端发起回测任务

**研究阶段**：
- 以 research 为主，不直接动 runtime
- 已经做了大量回测/代理实验/正式引擎验证
- 研究结论必须经过人工审查才能进入 runtime

---

## 2. Timeline（2026-04-09 ～ 2026-04-29）

### 2.1 研究起点：2026-04-09

**背景**：
- v3.0 迁移已完成，执行主线 PG 闭环已确认
- ETH 1h LONG-only 基线已锁定（EMA50, TP=[1.0,3.5]）
- 2023 年亏损 -3,924 USDT，2024/2025 年盈利 +8,501/+4,490

**研究问题**：
- 2023 亏损是参数问题、出场问题、市场状态问题，还是策略边界问题？
- 是否存在参数/规则调整能救回 2023，同时不破坏 2024/2025？

### 2.2 可信起点：2026-04-13

**原因**：回测系统开始正确消费 `risk_overrides`，风险参数链路更可信

**关键修复**：
- `BacktestRequest.risk_overrides` 正确传递到 `RiskCalculator`
- 风控参数（max_loss_percent、max_total_exposure）真正生效
- 之前的搜索结果可能因参数未生效而失真

### 2.3 密集研究主段：2026-04-21 ～ 2026-04-29

#### 2026-04-21: Optuna 窄搜索完成

- **产出**：`docs/planning/2026-04-21-optuna-narrow-search-handoff.md`
- **结果**：EMA50 最优，ATR 移除，min_distance_pct=0.005
- **关键发现**：参数敏感性分层（EMA 高敏感，ATR 不敏感）

#### 2026-04-22: 参数完整清单文档

- **产出**：`docs/planning/backtest-parameters.md`
- **结果**：ETH 1h 为唯一可行路径，BTC/SOL/ETH 4h/15m 全部失败
- **关键发现**：跨币种/跨周期验证完成

#### 2026-04-23: Sim-0 真实链路验证

- **产出**：`docs/reports/2026-04-23-sim-0-real-chain-validation.md`
- **结果**：执行主线 PG 闭环通过，testnet ENTRY/TP/SL 成功
- **关键发现**：真实链路可用，但发现 4 个真实 bug（未 await、缺失均价、PG 外键、attempt Decimal 序列化）

#### 2026-04-25: 策略沟通与架构决策

- **产出**：`docs/planning/2026-04-25-eth-baseline-market-regime-boundary-analysis.md`
- **结果**：不应把 2023 的失效理解为"参数还没调对"，而是 regime mismatch
- **关键决策**：研究优先级从"继续救 2023"切到"定义市场适用边界"

#### 2026-04-26: 执行主线 PG 闭环完成

- **产出**：`docs/planning/2026-04-26-pg-execution-mainline-verification-assets.md`
- **结果**：orders/intents/positions/signals 全部迁移到 PG
- **关键发现**：90 个定向测试通过，真实 PG 集成验证完成

#### 2026-04-27: Sim-1 部署与 Research Control Plane

- **产出**：
  - `docs/planning/architecture/2026-04-27-research-control-plane-v1-plan.md`
  - `docs/planning/2026-04-27-boundary-governance-mainline-plan.md`
- **结果**：Sim-1 已部署到 Mac mini Docker，Research Control Plane v1 后端骨架完成
- **关键决策**：研究链与 runtime 隔离，candidate 进入 runtime 必须人工审查

#### 2026-04-28: 研究链密集产出

**H0→H3a 2023 救援链关闭**：
- **产出**：`docs/planning/2026-04-28-eth-baseline-2023-rescue-research-closure.md`
- **结果**：五次实验（EMA regime gate、SHORT-only、0.382 limit-entry、动态 TP2、特征过滤）全部失败
- **结论**：2023 是策略适用边界成本，不是参数可调优的

**M0 Strategy Ecology Map**：
- **产出**：`docs/planning/2026-04-28-strategy-ecology-map-m0.md`
- **结果**：10 个市场状态特征中 6+ 个有显著解释力
- **关键发现**：Pinbar 是反趋势策略，在高波动、近期涨幅大、接近 Donchian 通道顶部时系统性亏损

**M1 Toxic State Avoidance**：
- **产出**：`docs/planning/2026-04-28-pinbar-toxic-state-avoidance-m1.md`
- **结果**：4 个单因子 filter 独立通过全部 PASS 标准
- **关键发现**：E1（ema_4h_slope）最优，3yr PnL 从 -2,158 翻正到 +1,314

**M1b Parity Check**：
- **产出**：`docs/planning/2026-04-28-pinbar-toxic-state-m1b-parity.md`
- **结果**：E1 在 parity 口径下优势减弱（FAIL），E4 在两个口径下都有效（PASS）
- **关键发现**：proxy 与 official 口径差异巨大（concurrent positions + compounding）

**C1/C2 组合研究**：
- **产出**：
  - `docs/planning/2026-04-28-c1-pinbar-t1-portfolio-proxy.md`
  - `docs/planning/2026-04-28-c2-pinbar-t1-portfolio-parity.md`
- **结果**：组合 PnL↑/DD↓ 成立，但 T1 fragility（Top 3 winners 贡献 108.4%）在 official 口径下变为致命风险
- **判定**：CONDITIONAL FAIL

**M1c E4 Official Check**：
- **产出**：`docs/planning/2026-04-28-m1c-donchian-distance-official-check.md`
- **结果**：E4 在 official/continuous 口径下 PASS，跨三种口径一致
- **关键发现**：E4 是跨口径唯一稳定有效的 toxic filter

#### 2026-04-29: P0/R1b 收口

**P0 Official Validation**：
- **产出**：`docs/planning/2026-04-29-p0-pinbar-e4-official-validation.md`
- **结果**：E4 在正式 Backtester v3_pms 下确认生效，但过滤过度
- **判定**：FAIL。2023 亏损降低 57.9%，但 2024/2025 收益被大量牺牲，3yr PnL 从 +3,789 恶化到 -1,924

**R1b Capital Allocation Audit**：
- **产出**：`docs/planning/2026-04-29-r1b-capital-allocation-audit-v2.md`
- **结果**：R1 原报告 MaxDD 严重错误，但在 `MaxDD <= 35%` 下存在 2 组可行配置
- **关键发现**：35% 回撤约束会压制当前 baseline 的收益想象空间

**P0 risk_calculator.py 修复**：
- **产出**：`docs/planning/2026-04-29-risk-calculator-integration-test.md`
- **结果**：敞口约束逻辑重构完成，三层独立控制（风险/敞口/杠杆）
- **关键修复**：exposure 参数真正生效

---

## 3. Baseline Confirmation Story

### 3.1 为什么会选这条 ETH 1h LONG-only Pinbar baseline

**不是一次性选定，而是逐步收敛**：

1. **跨币种验证**（2026-04-22）：
   - BTC 1h: 2024 全负
   - SOL 1h: 两年皆负
   - ETH 4h: 交易太少（~17/年）
   - ETH 15m: 交易过多（~140/年），信号质量差
   - **结论**：ETH 1h 是唯一可行路径

2. **参数搜索**（2026-04-21）：
   - EMA: 60（系统默认）→ 50（最优）
   - ATR: 0.01（系统默认）→ 移除（冗余）
   - min_distance_pct: 0.005（与系统一致）
   - **结论**：参数已优化，但结构层保持稳定

3. **结构层验证**（2026-04-22）：
   - LONG-only 优于双向（+175% PnL 改善）
   - BE=False 更优（+47% PnL 改善）
   - TP=[1.0, 3.5] 最优（vs [1.0, 2.5]）
   - **结论**：结构层已锁定，不再搜索

### 3.2 关键参数是怎么逐步确认的

**分层验证顺序**（遵循 `backtest-parameters.md` 的优先级分层）：

| 优先级 | 参数 | 验证方法 | 结果 |
|--------|------|----------|------|
| P0 | direction / LONG-only | 对比实验 | LONG-only 优于双向 |
| P0 | breakeven_enabled | 对比实验 | False 更优 |
| P0 | tp_targets | 搜索 + 对比 | [1.0, 3.5] 最优 |
| P0 | tp_ratios | 搜索 + 对比 | [0.5, 0.5] 最优 |
| P1 | ema_period | Optuna 搜索 | 50 最优（vs 60 默认） |
| P1 | min_distance_pct | Optuna 搜索 | 0.005 最优 |
| P3 | max_atr_ratio | 对比实验 | 移除（冗余） |

**关键原则**：
- 先验证"方向和出场"（结构层）
- 再验证"信号过滤"（参数层）
- 最后才碰"仓位和杠杆"（资金层）

### 3.3 哪些参数/结构已经相对冻结

**已冻结**（不再搜索）：
- symbol: ETH/USDT:USDT
- timeframe: 1h
- direction: LONG-only
- breakeven_enabled: False
- tp_targets: [1.0, 3.5]
- tp_ratios: [0.5, 0.5]
- ema_period: 50
- min_distance_pct: 0.005
- max_atr_ratio: None（移除）

**未冻结**（仍在研究）：
- mtf_ema_period: 60（未搜索，沿用系统配置）
- Pinbar 细参数（min_wick_ratio、max_body_ratio、body_position_tolerance）
- 风控参数（max_loss_percent、max_total_exposure）— R1b 已完成初步审计

### 3.4 哪些看起来是 baseline，其实后来被修正过

**EMA period**：
- 系统默认：60
- 搜索结果：50（更优）
- **修正原因**：更快响应趋势

**TP targets**：
- 系统默认：[1.0, 2.5]
- 搜索结果：[1.0, 3.5]（更激进）
- **修正原因**：第二目标更远，捕捉大趋势

**ATR 过滤器**：
- 系统默认：启用（max_atr_ratio=0.01）
- 搜索结果：移除（冗余）
- **修正原因**：有无 ATR 结果完全相同

**max_total_exposure**：
- 系统默认：0.8（80%）
- 发现问题：对合约回测不合理，导致盈利持仓时新信号被阻止
- **修正**：上限从 1 提升到 10（允许 1000%）

### 3.5 为什么最终接受"2023 是适用边界，不继续强行救"的判断

**五次实验穷尽所有合理维度**：

| 假设 | 核心思路 | 判定 | 失败模式 |
|------|---------|------|----------|
| H0 | EMA250/EMA200 粗 regime gate | 不通过 | 粗分类误杀好年份交易 |
| H1 | SHORT-only 镜像参数 | 弱通过 | 仅 2023 有效，3yr 远劣 |
| H2 | 0.382 Fibonacci limit-entry | 不通过 | 与趋势跟踪逻辑矛盾 |
| H3 | 动态风险几何 / 环境自适应退出 | 方向关闭 | 环境分类前提不成立 |
| H3a | 入场前特征预测 follow-through | 不通过 | 绝对水平重叠，无法设阈值 |

**共同失败模式**：
- 任何固定阈值/参数/过滤器都无法区分跨年环境差异
- 2023 的"坏"与 2024/2025 的"好"在特征空间上重叠
- 不存在线性可分的决策边界

**接受理由**：
1. 2024/2025 的 +8,501/+4,490 alpha 是真实的、可复现的
2. 2023 的 -3,924 是该策略在均值回归环境下的固有成本
3. 消除 2023 亏损的所有尝试都会严重损害好年份 alpha
4. 接受 -3,924 比试图消除它更合理（3yr 净收益仍为 +9,067）

---

## 4. Research Branch Review

### 4.1 2023 Rescue / Regime / OOS 研究链

**假设**：2023 亏损是参数问题、出场问题、市场状态问题，还是策略边界问题？

**方法**：五次独立实验（H0→H3a），覆盖所有合理的调整维度

**结果**：

| 实验 | 核心发现 | 判定 |
|------|---------|------|
| H0: EMA regime gate | 粗分类误杀好年份交易，最佳改善仅 +10.5% | 不通过 |
| H1: SHORT-only | 仅 2023 有效，3yr 累计远劣于 LONG | 弱通过，不进入主线 |
| H2: 0.382 limit-entry | 与趋势跟踪逻辑矛盾，系统性 missed winners | 不通过 |
| H3: 动态 TP2 | 环境分类前提不成立（H3a 证明） | 方向关闭 |
| H3a: 特征过滤 | 绝对水平重叠，无法设阈值 | 不通过 |

**结论**：2023 亏损是 market regime mismatch，不是参数可调优的。

**当前状态**：研究链已关闭，接受 2023 为策略适用边界成本。

---

### 4.2 Engulfing（吞没形态）研究链

**假设**：Engulfing 形态能否作为独立入场策略或补充 Pinbar？

**方法**：
- H5a: Engulfing smoke test（信号质量检查）
- H5b: Engulfing PnL proxy（独立撮合回测）

**结果**（未在本次材料中完整呈现，但根据 findings.md）：
- 信号质量：Engulfing 信号数量充足
- 完整收益：不成立（具体原因未详细说明）
- 当前价值：可能只研究出场，不作为独立入场

**结论**：Engulfing 不作为独立入场策略，可能作为出场研究补充。

**当前状态**：暂缓，不继续 Engulfing entry 搜索。

---

### 4.3 Donchian Breakout（唐奇安突破）研究链

**假设**：Donchian 突破能否作为趋势跟随策略补充 Pinbar？

**方法**：
- H6a: Donchian 20-bar LONG-only proxy

**结果**：
- 3yr PnL: **-17,305**（vs Pinbar +9,067）
- 信号过频：年均 648 signals → 424 trades（Pinbar 67 trades）
- WR 36.7%（高于 Pinbar 27.5%）但被 6.3x turnover 和紧止损杀死
- 2025 极端：31 trades, 25 SL, WR 19.4%, MaxDD 74%

**结论**：
- 20-bar 1h 通道太窄，ETH 波动下频繁假突破
- Breakout 家族在 ETH 1h 20-bar 上无 alpha 痕迹
- Pinbar "逆小顺大" 在回调入场，Donchian "顺大顺小" 在突破入场，两者本质不同

**当前状态**：关闭，不进入参数搜索，不进入 H6b。

---

### 4.4 Strategy Ecology / Toxic State 研究链

**假设**：市场状态特征能区分 Pinbar 盈利/亏损状态

**方法**：
- M0: 10 个市场状态特征的 tercile 分桶分析
- M1: 4 个单因子 toxic filter 独立测试
- M1b: Parity check（在官方 Backtester 口径下验证）
- M1c: E4 official/continuous check

**结果**：

**M0 关键发现**：
- 6+ 特征有显著解释力（spread > 5,000 USDT）
- Pinbar 是**反趋势策略**：低斜率、低波动环境赚钱
- 近期涨幅是毒药：72h return 高 → WR 从 18.8% 降到 7.3%
- 高波动杀死 Pinbar：atr_percentile 高 → PnL 从 -1,584 降到 -7,750
- Donchian 距离互补：Pinbar 在通道顶部最差（正是 breakout 入场位）

**M1 关键结果**：
- 4 个单因子 filter 独立通过全部 5 项 PASS 标准
- E1（ema_4h_slope）最优：3yr PnL 从 -2,158 翻正到 +1,314
- E4（donchian_distance）2023 改善最大：亏损减少 71.3%

**M1b 修正**：
- E1 在 parity 口径下 FAIL（2023 loss reduction 仅 15.4%）
- E4 在两个口径下都 PASS（2023 loss reduction 32.6%）

**M1c 跨口径一致性**：
- E4 在三种口径（proxy、parity year-by-year、parity continuous）下均 PASS
- 是跨口径唯一稳定有效的 toxic filter

**结论**：
- Pinbar 亏损来源集中且可识别
- 单因子 regime filter（尤其 E4）是最高效的干预
- 不需要换 entry，不需要复杂多因子模型

**当前状态**：
- E4 已在正式 Backtester 中实现（P0 验证）
- E1 降级为 proxy-only，不进入下一步

---

### 4.5 T1 趋势跟随原型

**假设**：趋势跟随策略能否与 Pinbar（反趋势）互补？

**方法**：
- T1: Donchian 4h + ATR trailing（趋势跟随原型）
- T1-R: 修正版（修复已知 bug）

**结果**：
- 3yr PnL: +2,039（vs Pinbar +9,067）
- 2023: +1,358（Pinbar 为 -3,180）
- **Fragility**：Top 3 winners 贡献 108.4%（移除后净亏 -17.53）
- Correlation (weekly MTM): 0.195（弱正相关，而非预期的负相关）

**结论**：
- T1 是理想的"大趋势收益来源"候选
- 但 fragility 和 correlation 0.195 是风险因素
- 需要 OOS 验证 fragility 是否在样本外更严重

**当前状态**：
- 暂缓组合，先处理 T1 fragility
- 不直接推进 Pinbar(E4) + T1 组合

---

### 4.6 组合研究

**假设**：Pinbar + T1 组合能否降低风险、提升收益？

**方法**：
- C1: Portfolio proxy（Pinbar baseline + T1-R，5 种权重）
- C2: Official parity check（正式 Backtester 口径验证）

**结果**：

**C1 (proxy)**：
- 组合 PnL 和 MaxDD 同时改善
- P60_T40: 3yr PnL +1,077, MaxDD 19.5%（vs Pinbar +435, 33.6%）
- 2023 大幅改善：亏损从 -3,180 降到 -1,365（改善 57%）
- 移除 T1 Top 3 后 P60_T40 仍为 +193（组合不依赖 T1 大赢家）

**C2 (official)**：
- Pinbar continuous PnL 大幅下降：+435 → +75
- Pinbar MaxDD 翻倍：33.6% → 67.94%
- 移除 T1 Top 3 后组合崩塌：P60_T40 从 +861 变为 **-24**
- Correlation 更低：0.050（接近零相关）

**结论**：
- C1 的"组合不依赖 T1 Top 3"结论在 official 口径下**不再成立**
- T1 fragility 在 official compounding 下变为致命风险
- 没有权重组合能同时满足"2023 改善 >=40%"和"移除 T1 Top 3 后不崩"

**当前状态**：CONDITIONAL FAIL，暂缓组合，先解决 T1 fragility。

---

### 4.7 资金参数 / 风险敞口研究

**假设**：在 `MaxDD <= 35%` 约束下，是否存在可行的资金配置？

**方法**：
- R1: Baseline capital allocation search（8 exposures × 7 risks = 56 组）
- R1 audit: 初步审计（3 个配置）
- R1b: 完整审计（56 组配置，对账三种 MaxDD）

**结果**：

**R1 原报告**：
- 最优配置：exposure=1.0, risk=2.0%
- MaxDD: 0.73%（**严重错误**）
- 3yr PnL: +17,749

**R1 audit**：
- 发现 R1 MaxDD 错误
- 重算 realized_curve MaxDD: 38.12%（exposure=1.0, risk=0.5%）
- 结论：所有配置无可行解（**只审计了 3 个配置**）

**R1b 完整审计**：
- R1 原报告 MaxDD 计算完全错误（0.32% vs 实际 32.42%）
- R1 audit 部分错误：只审计 3 个配置，遗漏可行解
- **存在可行配置**（基于 debug_curve）：
  - exposure=1.25, risk=0.5%: PnL=+2,346, MaxDD=33.74%
  - exposure=1.0, risk=0.5%: PnL=+2,113, MaxDD=32.42%

**关键发现**：
- `report.max_drawdown` 是 Backtester 内部指标，**不是真实 MaxDD**
- `debug_curve_max_dd` 是 Backtester 内部 equity curve MaxDD，**推荐使用**
- `realized_curve_max_dd` 是只按平仓计算的 MaxDD，**保守口径**

**结论**：
- 在 `MaxDD <= 35%` 约束下，存在可行配置
- 但收益不够"激励"：+2,346 vs 用户期待的 2024/2025 高收益
- 35% 回撤约束会压制当前 baseline 的收益想象空间

**当前状态**：
- 推荐稳健配置：exposure=1.25, risk=0.5%
- 下一步设计 R2：激励型资金上限实验，不再用单一回撤约束压制全部目标

---

### 4.8 P0 Official Validation

**假设**：E4（donchian_distance）在正式 Backtester v3_pms 下是否有效？

**方法**：
- 使用正式 Backtester v3_pms + dynamic strategy path
- 对比 E0（baseline）vs E1（+E4 filter）

**结果**：
- E4 确认真实生效：`rejection_stats` 中出现 `donchian_distance` 拦截
- 2023 亏损显著降低：-4,516 → -1,901（57.9% loss reduction）
- **但 3yr PnL 显著恶化**：+3,789 → -1,924（-150.8%）
- 2024/2025 收益被大量牺牲：从盈利转为亏损

**判定**：**FAIL**

**原因**：
- E4 是有效风险因子（2023 改善显著）
- 但当前固定阈值 `-0.016809` 过滤过度
- 牺牲了 2024/2025 的主要盈利交易

**结论**：
- E4 应从"硬过滤器"降级为"风险状态标签/仓位降权因子"
- 后续适合测试：
  - 靠近 Donchian high 时降低 `max_loss_percent`
  - 靠近 Donchian high 时缩短持仓或调整 TP
  - 只在特定 regime 下启用 E4

**当前状态**：不直接推进 Pinbar(E4) + T1 组合，先做 P0a（E4 被过滤交易质量切片）。

---

## 5. Methodology Risks / 踩坑地图

### 5.1 Lookahead Bias（未来函数 / 前瞻偏差）

**问题**：在信号检测时使用了未来数据

**会让结果偏向哪里**：虚高收益，实盘无法复现

**怎么发现的**：
- M1c 脚本使用当前 bar 的 high 计算 Donchian 上轨
- 存在轻微信息泄漏

**修正后结论是否改变**：
- 正式实现排除当前 K 线：`historical_highs = window[-(lookback+1):-1]`
- 预热期（< lookback+1 根）安全降级为 `passed=True`
- 结论未改变，但更保守

**以后该如何避免**：
- 所有指标计算必须只使用已完成的前 N 根 K 线
- 排除当前 K 线（`is_closed=False` 的数据）
- 预热期安全降级，不盲目过滤

---

### 5.2 Same-bar Entry（同 bar 入场导致结果虚高）

**问题**：在信号 K 线内立即入场，假设能以开盘价成交

**会让结果偏向哪里**：虚高收益，实盘滑点更大

**怎么发现的**：
- 回测引擎支持 same-bar entry 配置
- 默认行为未明确文档化

**修正后结论是否改变**：
- 已实现 same-bar 撮合可配置
- 每个 signal 只抽签一次（random 逻辑修复）
- 结论未改变，但更接近实盘

**以后该如何避免**：
- 明确 same-bar entry 的语义（开盘价 vs 收盘价）
- 实盘滑点估算必须覆盖 same-bar 场景
- 文档化 same-bar 配置的默认行为

---

### 5.3 kline_history 未传递，导致多 K 线策略失效

**问题**：Backtester 只传递单根 K 线给策略，不传递历史 K 线

**会让结果偏向哪里**：多 K 线策略（如 Engulfing）完全失效

**怎么发现的**：
- Engulfing 策略需要前一根 K 线数据
- Backtester 未传递 `kline_history`

**修正后结论是否改变**：
- 已修复：`b02f959 fix: pass kline history in dynamic backtests`
- 多 K 线策略现在可用

**以后该如何避免**：
- 所有策略必须明确声明是否需要 `kline_history`
- Backtester 必须传递足够的历史数据（至少 N 根，N 由策略声明）
- 单元测试必须覆盖多 K 线场景

---

### 5.4 Proxy 和 Official Engine 口径不一致

**问题**：独立撮合脚本（proxy）与正式 Backtester 结果差异巨大

**会让结果偏向哪里**：proxy 结果不可信，可能误导研究方向

**怎么发现的**：
- M1b parity check：E0 proxy -14,886 vs official +9,066
- C2 parity check：Pinbar proxy +435 vs official +75

**修正后结论是否改变**：
- 根因：concurrent positions + compounding balance
- proxy 是单仓位固定余额，official 支持并发仓位 + 复利
- 结论部分改变：E1 在 proxy 有效但在 parity 下 FAIL

**以后该如何避免**：
- 所有 proxy 实验必须在 parity check 中验证
- 明确 proxy 与 official 的差异（仓位模型、复利、数据源）
- 关键结论必须基于 official 口径

---

### 5.5 Reach Rate（触达率）不能直接代表 PnL（真实收益）

**问题**：信号触达率高不等于收益高

**会让结果偏向哪里**：误判策略质量

**怎么发现的**：
- Donchian 20-bar 信号过频（年均 648 signals）
- 但 3yr PnL = -17,305（vs Pinbar +9,067）

**修正后结论是否改变**：
- 结论已修正：信号密度高不等于 alpha 强
- Donchian 20-bar 关闭

**以后该如何避免**：
- 必须同时报告触达率和收益质量
- 信号过频（> 200/年）需要特别警惕
- 信号过少（< 30/年）统计意义不足

---

### 5.6 Low Correlation（低相关）不等于组合有效

**问题**：两个策略相关性低不等于组合能降低风险

**会让结果偏向哪里**：误判组合价值

**怎么发现的**：
- C1: Pinbar + T1 correlation = 0.195（弱正相关）
- C2: correlation = 0.050（接近零相关）
- 但移除 T1 Top 3 后组合崩塌

**修正后结论是否改变**：
- 结论已修正：低相关不等于组合有效
- T1 fragility 在 official 口径下变为致命风险

**以后该如何避免**：
- 组合研究必须测试"移除 Top N winners"的鲁棒性
- 必须在 official 口径下验证，不能只依赖 proxy
- 明确组合的依赖结构（是否依赖少数大赢家）

---

### 5.7 Signal Density（信号密度高）不等于 Alpha（优势）强

**问题**：信号数量多不等于策略质量高

**会让结果偏向哪里**：误判策略价值

**怎么发现的**：
- Donchian 20-bar: 年均 424 trades
- Pinbar: 年均 67 trades
- 但 Donchian 3yr PnL = -17,305，Pinbar = +9,067

**修正后结论是否改变**：
- 结论已修正：信号密度不等于 alpha 强
- Donchian 20-bar 关闭

**以后该如何避免**：
- 必须同时报告信号数量和收益质量
- 高频策略需要特别警惕交易成本和滑点
- 低频策略需要警惕统计意义不足

---

### 5.8 report.max_drawdown 不能直接当真实 MaxDD

**问题**：Backtester 报告的 `max_drawdown` 字段不是真实最大回撤

**会让结果偏向哪里**：严重低估风险，误导资金配置

**怎么发现的**：
- R1 报告：MaxDD=0.32%（exposure=1.0, risk=0.5%）
- R1b 审计：实际 MaxDD=32.42%（**100 倍差距**）

**修正后结论是否改变**：
- 结论完全改变：R1 原报告完全错误
- R1b 审计确认存在可行配置（基于 debug_curve）

**以后该如何避免**：
- **禁止使用 `report.max_drawdown` 作为真实 MaxDD**
- 必须使用 `report.debug_equity_curve` 计算 MaxDD
- 或从 `positions` 构建 equity curve（正确方法）

---

### 5.9 风险参数传错入口，导致搜索结果全部失真

**问题**：R1 搜索使用 `BacktestRuntimeOverrides` 传递风险参数，但该类不包含这些字段

**会让结果偏向哪里**：所有 168 组配置返回完全相同的结果

**怎么发现的**：
- R1 搜索结果异常：所有配置 PnL 完全相同
- 检查脚本：发现参数注入错误

**修正后结论是否改变**：
- 已修复：使用 `RiskConfig` 传递风险参数
- R2 sanity check 验证通过：参数正确生效

**以后该如何避免**：
- 参数注入必须明确契约（哪些字段可以注入）
- 搜索前必须 sanity check（验证参数生效）
- 结果异常时立即检查参数链路

---

### 5.10 account_snapshot.positions=[] 导致 Exposure Cap（敞口上限）失效

**问题**：回测中 `account_snapshot.positions` 为空，导致敞口计算失效

**会让结果偏向哪里**：仓位规模失控，风险被低估

**怎么发现的**：
- PMS 回测 `account_snapshot.positions=[]`
- 敞口约束未生效

**修正后结论是否改变**：
- 已修复：`cb06ea0 fix(P0): PMS 回测 account_snapshot.positions=[] 导致仓位规模失控`
- 敞口约束现在正确生效

**以后该如何避免**：
- 回测必须正确模拟持仓状态
- 敞口计算必须基于真实持仓，不能假设空仓
- 单元测试必须覆盖持仓状态场景

---

### 5.11 Research 结论不能直接污染 Runtime

**问题**：研究结果直接写入 runtime profile，绕过审查流程

**会让结果偏向哪里**：runtime 被未经验证的结论污染

**怎么发现的**：
- 早期脚本直接修改 `sim1_eth_runtime`
- 绕过人工审查

**修正后结论是否改变**：
- 已修复：
  - 研究脚本使用 `try/finally` 清理全局单例
  - profile switch API 增加 `confirm=true` 门槛
  - Backtester 显式注入 `config_manager`，不再依赖全局单例
  - Optuna 只输出 candidate，不自动应用 runtime

**以后该如何避免**：
- **禁止研究脚本直接修改 runtime profile**
- Candidate 进入 runtime 必须经过人工审查
- 研究链与 runtime 链必须隔离

---

### 5.12 Baseline 结论曾多次因"口径修复"被重估

**问题**：回测引擎 bug 修复后，之前的结论需要重新验证

**会让结果偏向哪里**：结论不稳定，研究浪费

**怎么发现的**：
- M1b parity check：proxy vs official 差异巨大
- R1b 审计：MaxDD 口径错误
- P0 验证：E4 过滤过度

**修正后结论是否改变**：
- 多次结论被重估：
  - E1 从"最优"降级为"proxy-only"
  - R1 从"存在最优配置"到"MaxDD 错误"到"存在可行配置"
  - C1 组合从"不依赖 T1 Top 3"到"依赖致命"

**以后该如何避免**：
- 所有关键结论必须在多个口径下验证
- 明确报告使用的口径（proxy、parity、official）
- 口径修复后必须重新验证受影响的结论

---

## 6. Current Best Understanding

### 6.1 当前最可信的 baseline 是什么

**策略本体**：
- ETH/USDT:USDT 1h LONG-only Pinbar
- EMA50 趋势过滤 + MTF（4h EMA60）
- TP=[1.0R, 3.5R], tp_ratios=[0.5, 0.5], BE=False

**参数配置**：
- ema_period: 50
- min_distance_pct: 0.005
- max_atr_ratio: None（移除）
- mtf_ema_period: 60

**资金配置**（稳健档）：
- max_loss_percent: 0.5%
- max_total_exposure: 1.25
- max_leverage: 20

**性能表现**（BNB9 实盘成本，debug_curve 口径）：
- 3yr PnL: +2,346 USDT
- MaxDD: 33.74%
- 2023: -2,523 USDT
- 2024: +2,856 USDT
- 2025: +2,013 USDT

---

### 6.2 当前 baseline 的优势是什么

1. **2024/2025 真实 alpha**：
   - 两年累计 +13,991 USDT（BNB9 口径）
   - Sharpe > 1.9，MaxDD < 20%
   - 样本外验证（2026 Q1 forward check）优秀

2. **参数已优化**：
   - EMA50 vs 系统默认 EMA60（更快响应趋势）
   - TP=[1.0, 3.5] vs [1.0, 2.5]（更激进捕捉大趋势）
   - ATR 移除（简化逻辑，无性能损失）

3. **跨币种/跨周期验证**：
   - ETH 1h 是唯一可行路径
   - BTC/SOL/ETH 4h/15m 全部失败
   - 结论稳定，不是偶然尖点

4. **市场诊断清晰**：
   - M0 证明 Pinbar 是反趋势策略
   - 在低斜率、低波动环境赚钱
   - 亏损来源集中且可识别

---

### 6.3 当前 baseline 的缺陷/适用边界是什么

1. **2023 失效**：
   - PnL: -3,924 USDT（WR=16.1%, Sharpe=-2.63）
   - 原因：market regime mismatch（高波动、近期涨幅大）
   - 不是参数可调优的

2. **单策略 regime 依赖**：
   - Pinbar 只在特定市场环境有效
   - 高波动、强趋势环境系统性亏损
   - 需要 regime filter 或策略组合

3. **样本外风险**：
   - 当前所有结论基于 2023-2025 IS
   - 需要 2022/2026 OOS 验证
   - Sim-1 自然观察期尚未完成

4. **资金表达受限**：
   - 在 `MaxDD <= 35%` 约束下，收益不够"激励"
   - 2023 亏损年决定了资金上限
   - 无法复现 2024/2025 高收益（+8,501/+4,490）

---

### 6.4 当前最值得保留的研究资产是什么

1. **M0 Strategy Ecology Map**：
   - 10 个市场状态特征的完整诊断
   - Pinbar 盈利/亏损环境的清晰画像
   - 为后续 regime filter 提供理论基础

2. **M1/M1b/M1c Toxic State Filter**：
   - 4 个单因子 filter 的独立验证
   - E4 跨口径唯一稳定有效
   - 为后续"风险状态标签/仓位降权"提供候选

3. **H0→H3a 2023 Rescue 研究链**：
   - 五次实验穷尽所有合理维度
   - 证明 2023 是策略边界，不是参数问题
   - 避免后续继续在错误方向浪费时间

4. **R1b Capital Allocation Audit**：
   - 三种 MaxDD 口径的对账
   - 明确 `report.max_drawdown` 不能直接使用
   - 在 `MaxDD <= 35%` 下找到可行配置

5. **P0 Official Validation**：
   - E4 在正式 Backtester 下的完整验证
   - 证明 E4 是有效风险因子，但当前阈值过滤过度
   - 为后续"风险状态标签"研究提供证据

---

### 6.5 当前已经明确不值得继续深挖的方向是什么

1. **继续救 2023**：
   - H0→H3a 已穷尽所有合理维度
   - 任何固定阈值/参数/过滤器都无法区分跨年环境差异
   - 接受 2023 为策略边界成本

2. **Donchian 20-bar Breakout**：
   - 3yr PnL = -17,305（vs Pinbar +9,067）
   - 信号过频，whipsaw 模式主导
   - ETH 1h 20-bar 通道太窄

3. **SHORT-only 镜像参数**：
   - 仅 2023 有效，3yr 累计远劣于 LONG
   - 独立 SHORT 参数搜索成本高、收益不确定

4. **0.382 Fibonacci Limit-entry**：
   - 与趋势跟踪逻辑矛盾
   - 系统性 missed winners
   - 固定改入场不是解决方向

5. **全参数混合爆搜**：
   - 信号/出场/资金层混搜，结果不可解释
   - 容易把"资金表达结果"误判成"策略本体发现"
   - 违反分层验证原则

---

### 6.6 当前最值得继续的 3 个方向是什么

1. **P0a: E4 被过滤交易质量切片**：
   - 目标：判断 E4 硬过滤是否牺牲了 2024/2025 主要盈利来源
   - 方法：对被 E4 过滤的交易做收益来源切片，按年份拆解
   - 预期：确认 E4 应作为"风险状态标签"还是"仓位降权因子"

2. **R2: 激励型资金上限实验**：
   - 目标：不再用单一 `MaxDD <= 35%` 压制全部目标
   - 方法：设计分年度、分阶段或收益/回撤分层目标
   - 预期：输出"最佳可能性"但明确不同于实盘准入

3. **T1b: T1 Fragility/OOS 复核**：
   - 目标：判断 T1 是否继续作为组合候选
   - 方法：OOS 验证 T1 fragility，测试移除 Top N winners 的鲁棒性
   - 预期：确认 T1 是否值得继续研究，还是放弃组合线

---

### 6.7 现在真正的瓶颈是哪个为主

**答案：市场状态识别（Regime Identification）**

**理由**：

1. **Alpha 本身不是瓶颈**：
   - 2024/2025 的 +8,501/+4,490 alpha 是真实的、可复现的
   - 参数已优化，结构层已稳定

2. **出场结构不是主要瓶颈**：
   - H3 已证明动态 TP2 的前提不成立
   - BE=False 已验证更优
   - 出场结构已相对稳定

3. **组合构建依赖 regime 识别**：
   - C2 证明组合对 T1 fragility 依赖过强
   - 需要先解决 T1 的 regime 适配问题
   - Pinbar + T1 组合的前提是各自 regime 识别清晰

4. **风险资金配置依赖 regime 识别**：
   - R1b 证明 2023 亏损年决定资金上限
   - 如果能识别 2023 的 toxic regime 并跳过，资金上限可以大幅提升
   - E4 是有效风险因子，但当前硬过滤过度

5. **回测可靠性已基本解决**：
   - P0 验证证明正式 Backtester 可用
   - 口径问题已明确（proxy vs official）
   - 关键 bug 已修复（lookahead bias、same-bar entry、kline_history）

**结论**：当前真正的瓶颈是**如何识别 Pinbar 的适用市场环境**，而不是继续调参或换策略。

---

## 7. What An External Quant Would Likely Say

### 7.1 他最可能质疑什么

1. **"你们的 2023 失效分析是否足够深入？"**
   - 质疑点：H0→H3a 是否真的穷尽了所有可能性？
   - 可能建议：是否考虑过更细粒度的市场状态分类（如 HMM、regime switching model）？

2. **"E4 过滤过度是因为阈值选择问题，还是 filter 本身的问题？"**
   - 质疑点：M1c 和 P0 的阈值是否一致？是否尝试过放宽阈值？
   - 可能建议：做阈值敏感性分析，而不是只测试一个固定值

3. **"组合研究中 T1 的 fragility 是否被充分重视？"**
   - 质疑点：Top 3 winners 贡献 108.4% 是非常危险的信号
   - 可能建议：T1 是否值得继续研究，还是应该放弃？

4. **"资金参数搜索的口径是否足够清晰？"**
   - 质疑点：debug_curve vs realized_curve vs mark-to-market，三种口径差异巨大
   - 可能建议：明确审计标准，不要在不同口径间跳跃

5. **"样本外验证是否充分？"**
   - 质疑点：当前所有结论基于 2023-2025 IS，OOS 验证不足
   - 可能建议：2022/2026 Q1 OOS 验证是 P0 优先级

---

### 7.2 他最可能建议你停掉什么

1. **停掉"继续救 2023"的所有尝试**：
   - 理由：H0→H3a 已充分证明 2023 是 regime mismatch
   - 继续调参只会浪费资源，不会改变结论

2. **停掉 Donchian 20-bar Breakout**：
   - 理由：3yr PnL = -17,305，信号过频，whipsaw 模式主导
   - ETH 1h 20-bar 通道太窄，不适合 breakout 策略

3. **停掉 SHORT-only 独立搜索**：
   - 理由：仅 2023 有效，3yr 累计远劣于 LONG
   - 独立参数搜索成本高、收益不确定

4. **停掉全参数混合爆搜**：
   - 理由：结果不可解释，容易误导
   - 违反分层验证原则

5. **停掉"把 E4 直接写入 runtime"**：
   - 理由：P0 已证明 E4 过滤过度
   - 需要先做 P0a（被过滤交易质量切片）

---

### 7.3 他最可能建议你优先做什么

1. **P0: 样本外验证（2022/2026 Q1）**：
   - 理由：当前所有结论基于 IS，OOS 验证是 P0 优先级
   - 方法：用 2022 年数据做 OOS 验证，用 2026 Q1 做 forward check

2. **P0a: E4 被过滤交易质量切片**：
   - 理由：P0 已证明 E4 过滤过度，需要判断是否牺牲了主要盈利来源
   - 方法：对被 E4 过滤的交易做收益来源切片，按年份拆解

3. **Regime Identification 深入研究**：
   - 理由：当前真正的瓶颈是市场状态识别
   - 方法：考虑更细粒度的市场状态分类（如 HMM、regime switching model）

4. **T1 Fragility 深入分析**：
   - 理由：Top 3 winners 贡献 108.4% 是非常危险的信号
   - 方法：OOS 验证 T1 fragility，测试移除 Top N winners 的鲁棒性

5. **明确审计标准**：
   - 理由：三种 MaxDD 口径差异巨大，需要明确标准
   - 方法：统一使用 debug_curve 作为审计标准，或实现真实的 mark-to-market equity curve

---

### 7.4 他会认为你现在最缺哪类证据

1. **样本外验证证据**：
   - 2022 年 OOS 验证
   - 2026 Q1 forward check（目前只有 +777 USDT，样本太小）

2. **E4 阈值敏感性分析**：
   - 当前只测试了一个固定阈值 `-0.016809`
   - 需要放宽阈值重新验证

3. **T1 OOS 验证**：
   - 当前 T1 fragility 基于 IS，OOS 可能更严重

4. **真实 mark-to-market equity curve**：
   - 当前只有 debug_curve 和 realized_curve
   - 缺少每根 K 线计入浮盈浮亏的真实 MTM curve

5. **多品种/多周期组合验证**：
   - 当前只有 ETH 1h 可行
   - 需要验证策略组合是否能降低 regime 依赖

---

### 7.5 如果只能给 3 条专业建议，会是哪 3 条

**建议 1：明确研究主线，不要继续横向扩张**

- **理由**：当前已经做了大量研究（H0→H3a、M0→M1c、C1→C2、R1→R1b、P0），但结论分散
- **建议**：
  - 停掉"继续救 2023"
  - 停掉 Donchian 20-bar
  - 停掉全参数混合爆搜
  - 聚焦在"市场状态识别"和"样本外验证"

**建议 2：E4 应从"硬过滤器"降级为"风险状态标签"**

- **理由**：P0 已证明 E4 过滤过度，但 E4 是有效风险因子
- **建议**：
  - 先做 P0a（被过滤交易质量切片）
  - 测试 E4 作为"仓位降权因子"（靠近 Donchian high 时降低 `max_loss_percent`）
  - 测试 E4 作为"出场调整因子"（靠近 Donchian high 时缩短持仓或调整 TP）
  - 不要直接把 E4 写入 runtime

**建议 3：样本外验证是 P0 优先级**

- **理由**：当前所有结论基于 2023-2025 IS，OOS 验证不足
- **建议**：
  - 用 2022 年数据做 OOS 验证
  - 用 2026 Q1 做 forward check（当前样本太小）
  - 如果 OOS 表现显著低于 IS，需要重新评估策略稳定性
  - 如果 OOS 表现一致，才能考虑实盘部署

---

## 8. Final Recommendation

### 8.1 下一步怎么走（按优先级排序）

**P0（立即执行）**：

1. **P0a: E4 被过滤交易质量切片**（~4h）
   - 目标：判断 E4 硬过滤是否牺牲了 2024/2025 主要盈利来源
   - 方法：对被 E4 过滤的交易做收益来源切片，按年份拆解
   - 产出：`docs/planning/2026-04-29-p0a-e4-skipped-trades-attribution.md`

2. **样本外验证（2022 年）**（~6h）
   - 目标：验证策略在 2022 年的表现
   - 方法：用 2022 年数据跑 official backtest
   - 产出：`docs/planning/2026-04-29-oos-2022-validation.md`

**P1（本周完成）**：

3. **R2: 激励型资金上限实验**（~8h）
   - 目标：不再用单一 `MaxDD <= 35%` 压制全部目标
   - 方法：设计分年度、分阶段或收益/回撤分层目标
   - 产出：`docs/planning/2026-04-29-r2-incentive-capital-allocation.md`

4. **T1b: T1 Fragility/OOS 复核**（~6h）
   - 目标：判断 T1 是否继续作为组合候选
   - 方法：OOS 验证 T1 fragility，测试移除 Top N winners 的鲁棒性
   - 产出：`docs/planning/2026-04-29-t1b-fragility-oos-check.md`

**P2（下周完成）**：

5. **E4 阈值敏感性分析**（~4h）
   - 目标：测试放宽 E4 阈值是否能改善 P0 结果
   - 方法：测试 E4 阈值 = -0.01, -0.005, 0.0
   - 产出：`docs/planning/2026-04-29-e4-threshold-sensitivity.md`

6. **Regime Identification 深入研究**（~12h）
   - 目标：更细粒度的市场状态分类
   - 方法：HMM、regime switching model、或更复杂的特征组合
   - 产出：`docs/planning/2026-04-29-regime-identification-deep-dive.md`

---

### 8.2 值得保留的资产清单

1. **研究文档**：
   - `docs/planning/2026-04-28-eth-baseline-2023-rescue-research-closure.md`（H0→H3a 完整研究链）
   - `docs/planning/2026-04-28-strategy-ecology-map-m0.md`（市场状态诊断）
   - `docs/planning/2026-04-28-pinbar-toxic-state-avoidance-m1.md`（Toxic filter 验证）
   - `docs/planning/2026-04-28-m1c-donchian-distance-official-check.md`（E4 跨口径验证）
   - `docs/planning/2026-04-29-p0-pinbar-e4-official-validation.md`（E4 official 验证）
   - `docs/planning/2026-04-29-r1b-capital-allocation-audit-v2.md`（资金参数审计）
   - `docs/planning/backtest-parameters.md`（参数完整清单）

2. **研究脚本**：
   - `scripts/run_strategy_ecology_m0.py`（M0 市场状态诊断）
   - `scripts/run_pinbar_toxic_state_m1.py`（M1 toxic filter）
   - `scripts/run_m1c_donchian_distance_official_check.py`（M1c E4 official）
   - `scripts/run_p0_pinbar_e4_official.py`（P0 E4 validation）
   - `scripts/run_r1b_capital_allocation_audit_v2.py`（R1b 审计）

3. **研究数据**：
   - `reports/research/strategy_ecology_m0_2026-04-28.json`（M0 完整结果）
   - `reports/research/pinbar_toxic_state_m1_2026-04-28.json`（M1 完整结果）
   - `reports/research/m1c_donchian_distance_official_check_2026-04-28.json`（M1c 完整结果）
   - `reports/research/p0_pinbar_e4_official_validation_2026-04-29.json`（P0 完整结果）
   - `reports/research/r1b_capital_allocation_audit_v2_2026-04-29.json`（R1b 完整结果）

---

### 8.3 以后不能再踩的坑清单

1. **禁止使用 `report.max_drawdown` 作为真实 MaxDD**
2. **禁止研究脚本直接修改 runtime profile**
3. **禁止在未做 parity check 的情况下信任 proxy 结果**
4. **禁止在未做 OOS 验证的情况下信任 IS 结论**
5. **禁止在未做阈值敏感性分析的情况下使用固定阈值**
6. **禁止在未测试移除 Top N winners 的情况下信任组合结果**
7. **禁止在未明确口径的情况下比较不同实验的结果**
8. **禁止在未做 sanity check 的情况下启动大规模搜索**
9. **禁止在未修复 lookahead bias 的情况下使用指标**
10. **禁止在未明确 same-bar entry 语义的情况下比较回测结果**
11. **禁止在未传递 `kline_history` 的情况下测试多 K 线策略**
12. **禁止在未明确审计标准的情况下下结论**

---

### 8.4 当前研究主线

**主线 1：市场状态识别（Regime Identification）**
- 目标：识别 Pinbar 的适用市场环境
- 当前进展：M0 诊断完成，M1 证明单因子 filter 有效，P0 验证 E4 过滤过度
- 下一步：P0a（E4 被过滤交易质量切片）→ E4 阈值敏感性 → Regime Identification 深入研究

**主线 2：样本外验证（OOS Validation）**
- 目标：验证策略在 OOS 的稳定性
- 当前进展：2026 Q1 forward check 优秀（+777 USDT），但样本太小
- 下一步：2022 年 OOS 验证 → 持续观察 Sim-1 自然模拟盘

**主线 3：资金表达优化（Capital Allocation）**
- 目标：在风险可控的前提下最大化收益
- 当前进展：R1b 审计确认在 `MaxDD <= 35%` 下存在可行配置，但收益不够"激励"
- 下一步：R2 激励型资金上限实验 → 分年度/分阶段目标

**暂缓主线**：
- 组合研究（Pinbar + T1）：先解决 T1 fragility
- 新 entry 策略（Engulfing、Donchian）：当前聚焦 Pinbar 优化

---

## 附录：关键术语解释

| 术语 | 解释 |
|------|------|
| **MaxDD** | 最大回撤（Maximum Drawdown），从峰值到谷值的最大跌幅 |
| **OOS** | 样本外（Out-of-Sample），未用于参数搜索的数据 |
| **IS** | 样本内（In-Sample），用于参数搜索的数据 |
| **Regime** | 市场状态/市场环境（如趋势、震荡、高波动、低波动） |
| **Proxy** | 代理实验，独立撮合脚本，不等同正式 Backtester |
| **Parity** | 口径对齐，验证 proxy 与 official 结果是否一致 |
| **Official** | 正式 Backtester v3_pms，支持 concurrent positions + compounding |
| **Fragile** | 脆弱，收益高度依赖少数大单，移除后收益崩塌 |
| **Alpha** | 超额收益，策略相对于基准的优势 |
| **Sharpe** | 夏普比率，风险调整后收益（(收益率 - 无风险利率) / 波动率） |
| **MTM** | Mark-to-Market，按市价计价，每根 K 线计入浮盈浮亏 |
| **Realized Curve** | 只在平仓时更新权益，忽略持仓期间的浮盈浮亏变化 |
| **Debug Curve** | Backtester 内部 equity curve，可能包含浮盈浮亏 |
| **Lookahead Bias** | 未来函数/前瞻偏差，在信号检测时使用了未来数据 |
| **Same-bar Entry** | 同 bar 入场，在信号 K 线内立即入场 |
| **Toxic State** | 有毒状态，策略在该市场环境下系统性亏损 |
| **Filter** | 过滤器，跳过不满足条件的信号 |
| **Regime Filter** | 市场状态过滤器，在特定市场环境下跳过信号 |
| **TP** | Take Profit，止盈 |
| **SL** | Stop Loss，止损 |
| **BE** | Breakeven，保本止损（TP1 成交后，止损移到入场价） |
| **R** | Risk Unit，风险单位（止损距离） |
| **WR** | Win Rate，胜率 |
| **MFE** | Maximum Favorable Excursion，最大顺行幅度 |
| **MAE** | Maximum Adverse Excursion，最大逆行幅度 |
| **EMA** | Exponential Moving Average，指数移动平均线 |
| **MTF** | Multi-Timeframe，多周期（如 1h 主周期 + 4h 辅助周期） |
| **Pinbar** | Pin Bar，长影线形态，趋势反转信号 |
| **Engulfing** | 吞没形态，趋势反转信号 |
| **Donchian** | 唐奇安通道，趋势跟踪指标 |
| **ATR** | Average True Range，平均真实波幅 |
| **Exposure** | 敞口，仓位规模相对于账户权益的倍数 |
| **Leverage** | 杠杆，放大倍数 |
| **BNB9** | BNB 9折手续费，实盘推荐成本口径 |

---

*报告完成时间: 2026-04-29*
*性质: research-only 策略复盘，不涉及代码修改*
*目标读者: 外部量化交易从业者*
