# Research Evidence Index — H0 → H6

> **生成时间**: 2026-04-28
> **作用**: 对 H0–H6 研究链已关闭/已结论项做证据归档索引，供后续决策参考
> **约束**: 本文档只读整理，不提出新实验，不评价新策略
> **基线参照**: ETH 1h LONG-only, EMA50, MTF 4h EMA60, TP=[1.0R, 3.5R], BE=False, BNB9 成本

---

## 一、已关闭方向总览

| # | 假设 | Verdict | 关闭日期 | 失败模式一句话 |
|---|------|---------|----------|----------------|
| H0 | EMA250/EMA200 coarse regime gate | **CLOSED** | 2026-04-28 | 粗分类无法区分趋势质量；2023 bull regime 下 LONG 同样亏损 |
| H1 | SHORT-only mirror baseline | **NOT ENTERED** | 2026-04-28 | SHORT 仅 2023 优于 LONG，3yr 累计远劣于 LONG，不可镜像 |
| H2 | 0.382 limit entry proxy | **CLOSED** | 2026-04-28 | 入场改善仅 0.31%；2024 missed 56% winners；与趋势跟踪逻辑矛盾 |
| H3 | Dynamic risk geometry / env-adaptive exit | **CLOSED** | 2026-04-28 | 环境分类前提（H3a）不成立，方向整体关闭 |
| H3a | Entry-feature follow-through prediction | **CLOSED** | 2026-04-28 | 特征有统计区分度，但绝对水平重叠导致无法设有效阈值 |
| H5a/H5b | Engulfing smoke test / PnL proxy | **CLOSED** | 2026-04-28 | 信号过密；完整撮合下 3yr PnL 均为负；reach rate ≠ PnL |
| H6a | Donchian 20-bar breakout LONG proxy | **CLOSED** | 2026-04-28 | 信号过频 + 紧止损 = whipsaw 死亡组合；3yr PnL = -17,305 |
| Fixed TP2 down | 固定 TP2 下调 | **CLOSED** | prior | 4 种出场变体全部恶化；好年份同步受损 |
| BE=True | Breakeven move-to-entry | **CLOSED** | prior | 3yr PnL 恶化 -2,715；过早结束仓位，减少趋势捕获 |
| Direct ETH→BTC/SOL transfer | ETH baseline 直接迁移 | **CLOSED** (via H5) | 2026-04-28 | BTC 3/4yr 失效；SOL 适配年份不足；各品种趋势特征不同 |

---

## 二、H0: EMA250/EMA200 Coarse Regime Gate

### Hypothesis
在日线级别用 EMA250/EMA200 判断 bull/bear regime，bear regime 下不许开 LONG，可压缩 2023 亏损。

### Verdict
**CLOSED — 不通过**

### Key Metrics

| 实验 | 2023 PnL | 2024 PnL | 2025 PnL |
|------|----------|----------|----------|
| E0 (无 gate) | -3,924 | +8,501 | +4,490 |
| E1 (EMA250 bull-only) | -4,617 | +4,652 | +3,725 |
| E2 (EMA250+bull slope) | -3,514 | +3,125 | +3,247 |
| E3 (EMA200 bull-only) | -4,368 | +4,652 | +3,931 |
| E4 (EMA250 shadow) | -4,617 | +4,652 | +3,725 |

E4 Shadow Tracking（bear regime 下虚拟 LONG 表现）：2023 WR=29.4%, 2024 WR=50.0%, 2025 WR=29.4% — bear LONG 并非完全无效。

### Failure Mode
粗粒度 EMA 分型无法区分趋势质量。gate 的主要效果是减少交易次数，而非改善收益质量。2023 bull regime 下 LONG 同样亏损。

### Artifact Paths
- `docs/planning/2026-04-28-market-regime-experiment-results.md` (v1)
- `docs/planning/2026-04-28-market-regime-experiment-results-v2.md` (v2, 含反前瞻修正)
- `docs/planning/2026-04-28-market-regime-experiment-assessment.md`
- `reports/research/market_regime_experiments_2026-04-28.json`
- `reports/research/market_regime_experiments_2026-04-28-v2.json`
- `scripts/run_market_regime_experiments.py`
- `scripts/run_market_regime_experiments_v2.py`

### Status
**CLOSED** — 粗 regime gate 方向不再碰。

---

## 三、H1: SHORT-Only Baseline Check

### Hypothesis
当前 ETH 1h Pinbar + EMA/MTF 框架下，SHORT-only 可能存在独立 alpha 痕迹。

### Verdict
**NOT ENTERED — 弱通过但不进入主线**

### Key Metrics

| 指标 | 2023 LONG | 2023 SHORT | 2024 LONG | 2024 SHORT | 2025 LONG | 2025 SHORT |
|------|-----------|------------|-----------|------------|-----------|------------|
| PnL | -3,924 | -3,286 | +8,501 | +135 | +4,490 | -366 |
| Trades | 62 | 37 | 70 | 44 | 68 | 47 |
| WR | 16.1% | 8.1% | 32.9% | 29.5% | 30.9% | 14.9% |

3yr 累计: SHORT = -3,517 vs LONG = +9,067

### Failure Mode
SHORT 仅在 2023 优于 LONG（+638），2024/2025 灾难性。TP2 达成率 SHORT 远低于 LONG（5.9-18.6% vs 11.8-20.7%）。加密市场长期偏多，SHORT 参数不宜镜像 LONG。

### Artifact Paths
- `docs/planning/2026-04-28-short-only-baseline-check.md`
- `reports/research/short_only_baseline_check_2026-04-28.json`
- `scripts/run_short_only_baseline_check.py`

### Status
**NOT ENTERED** — 不进入主线，不做独立 SHORT 参数搜索。

---

## 四、H2: Pinbar 0.382 Limit-Entry Proxy

### Hypothesis
当前"下一根 K 市价入场"存在追价问题；改为信号 K 区间 0.382 回撤挂单可能改善入场价格、止损距离和收益质量。

### Verdict
**CLOSED — 不通过**

### Key Metrics

| 指标 | E0 基线 | E1 (wait=5) | E2 (wait=8) |
|------|---------|-------------|-------------|
| 2023 PnL | -3,924 | -12 | +19 |
| 2024 PnL | +8,501 | -2,822 | -217 |
| Avg Entry Improve | — | 0.312% | 0.313% |
| Avg Stop Dist Change | — | -54.9% | -54.7% |
| Fill Rate | — | 80.7% | 83.9% |

### Failure Mode
入场改善仅 0.31%（微不足道）；2023 改善真实原因是止损距离缩小 55%，不是入场价更好。2024 missed 56% winners（9 笔），系统性错过趋势入场。0.382 limit entry 与趋势跟踪逻辑矛盾：趋势延续时价格不回撤到 0.382。

### Artifact Paths
- `docs/planning/2026-04-28-pinbar-limit-entry-proxy.md`
- `reports/research/pinbar_limit_entry_proxy_2026-04-28.json`
- `scripts/run_pinbar_limit_entry_proxy.py`

### Status
**CLOSED** — 固定改入场方式与趋势跟踪策略矛盾，不再碰。

---

## 五、H3: Dynamic Risk Geometry / Exit-Structure Hypothesis

### Hypothesis
2023 的亏损可以通过"环境自适应的退出结构"压缩——好环境保留 TP=[1.0, 3.5]，坏环境更快兑现（TP2 下调至 2.0R 或 1.5R），不改变入场方式。

### Verdict
**CLOSED — 方向关闭**（H3a 前提不成立）

### Supporting Evidence Chain
1. MFE 低（1.65% vs 3.10%）→ 2023 的问题是 follow-through 不足，不是入场价太差
2. MAE 正常（2.41% vs 2.27%）→ 止损机制正常工作
3. H2 入场改善仅 0.31% → 改入场不是解决方向
4. 固定 TP2 下调已证伪：4 种出场变体全部恶化（backtest-parameters.md L539）
5. BE=True 已证伪：3yr PnL 恶化 -2,715（backtest-parameters.md L537）

### Failure Mode
动态 TP2 的前提是"能正确识别好/坏环境"。H0 证明粗分类不行，H3a 证明特征分类也不行——绝对水平重叠导致无法设阈值。

### Artifact Paths
- `docs/planning/2026-04-28-h3-dynamic-risk-geometry-hypothesis.md`

### Status
**CLOSED** — 前提（环境分类）不成立，H3b 不建议启动。

---

## 六、H3a: Entry-Feature Follow-Through Prediction

### Hypothesis
入场前可观测特征（EMA slope、price_dist_ema、volatility 等）能预测低 MFE / 低 follow-through，从而实现环境分类 + 动态退出。

### Verdict
**CLOSED — 不通过**

### Key Metrics
- 5 个特征有 ≥20pp high_ft_pct spread（price_dist_ema_1h 最佳，27.9pp）
- 但跨年绝对水平重叠：2023 B3 HFT=45% vs 2024 B1 HFT=50%
- Skip-B1 过滤器：2023 改善 +19/+156，2024 恶化 -6,539/-6,395

### 2023 悖论（核心发现）
高 FT 桶在 2023 PnL 反而更差（B3=-1,339 vs B1=-19），因为 2023 的"高 FT"绝对水平仍不够支撑 TP2=3.5R。特征能区分同一年内的相对好坏，但无法区分跨年的绝对环境差异。

### Failure Mode
与 H0/H2 失败模式完全一致：固定阈值无法区分跨年环境差异。统计显著 ≠ 交易可用。

### Artifact Paths
- `docs/planning/2026-04-28-h3a-followthrough-feature-check.md`
- `reports/research/h3a_followthrough_feature_check_2026-04-28.json`
- `scripts/run_h3a_followthrough_feature_check.py`

### Status
**CLOSED** — H3 动态退出方向整体关闭。

---

## 七、H4: ETH Baseline OOS Check

### Hypothesis
ETH 1h LONG-only 当前基线在样本外区间（2022、2026 Q1）是否仍表现为"有边界但非失效"。

### Verdict
**PASSED — 基线维持**

### Key Metrics

| 区间 | PnL | Trades | WR | Sharpe | MaxDD% | 分类 |
|------|-----|--------|-----|--------|--------|------|
| 2022 (OOS) | +69 | 51 | 19.6% | 0.006 | 9.3% | 边界 |
| 2023 (IS) | -3,924 | 62 | 16.1% | -0.230 | 58.1% | 失效 |
| 2024 (IS) | +8,501 | 70 | 32.9% | 0.251 | 18.1% | 适配 |
| 2025 (IS) | +4,490 | 68 | 30.9% | 0.214 | 12.1% | 适配 |
| 2026 Q1 (OOS) | +821 | 4 | 50.0% | 0.808 | 0.2% | 适配 |

5yr 累计 PnL: +9,957 USDT | 3 适配 / 1 边界 / 1 失效

### Positive Finding
2022 更像 2024/2025（适配）而非 2023（失效），2026 Q1 延续有效性。基线定义为"有边界但非失效"成立。5 区间累计正收益 +9,957。

### Artifact Paths
- `docs/planning/2026-04-28-eth-baseline-oos-check.md`
- `reports/research/eth_baseline_oos_check_2026-04-28.json`
- `scripts/run_eth_baseline_oos_check.py`
- `docs/planning/2026-04-28-eth-baseline-2023-rescue-research-closure.md`（研究链收口文档）

### Status
**PASSED** — 基线维持，不修改。

---

## 八、H5: Multi-Symbol Baseline Transfer

### Hypothesis
ETH 1h LONG-only 基线能否迁移到 BTC/SOL/BNB，形成低相关、不同步失效的候选子策略。

### Verdict
**CLOSED — 不通过**

### Key Metrics

| 品种 | 2022 | 2023 | 2024 | 2025 | 4yr PnL |
|------|------|------|------|------|---------|
| ETH | +69 | -3,924 | +8,501 | +4,490 | +9,136 |
| BTC | -3,566 | -3,619 | -3,425 | +9,463 | -1,147 |
| SOL | -496 | +274 | +1,339 | -1,310 | -194 |
| BNB | +107 | — | — | — | +107 |

与 ETH 年度 PnL 相关性：BTC=0.214, SOL=0.199（低相关但各品种在不同年份各自失败）

### Failure Mode
低相关 ≠ 有用。低相关性的本质不是"对冲"，而是"各自在不同年份失效"。ETH 的 TP2 达成率（20.7%/19.1%）在好年份远高于 BTC（9.8%/21.1%）和 SOL（14.6%/12.6%），说明 ETH 基线结构是为 ETH 趋势特征量身定制的。

### Artifact Paths
- `docs/planning/2026-04-28-multi-symbol-baseline-transfer.md`
- `reports/research/multi_symbol_baseline_transfer_2026-04-28.json`
- `scripts/run_multi_symbol_baseline_transfer.py`

### Status
**CLOSED** — ETH 基线不直接迁移。BTC/SOL/BNB 不进入候选池。

---

## 九、H5a/H5b: Engulfing Smoke Test / PnL Proxy

### Hypothesis
Engulfing 形态在完整 MTF 配置下能否产生有效信号并转化为正收益。

### Verdict
**CLOSED — 不通过**（H5a 工程验证通过，H5b PnL 不通过）

### Key Metrics (H5b, Research 口径)

| 实验 | 2023 PnL | 2024 PnL | 2025 PnL | 3yr PnL | Trades |
|------|----------|----------|----------|---------|--------|
| E0 Pinbar LONG (对照) | -5,185 | +6,730 | +3,422 | +4,967 | 254 |
| E1 Engulfing LONG | -5,049 | -3,880 | -992 | -9,921 | 708 |
| E2 Engulfing SHORT | -3,883 | -315 | -3,454 | -7,652 | 653 |
| E3 Engulfing L/S | -6,971 | -4,063 | -4,106 | -15,140 | 1,361 |

### Failure Mode
1. 信号过密（3yr 2,153 fired signals），过滤后仍有大量噪声交易
2. H5a reach rate（+1R 76.8%, +3.5R 38.1%）在完整撮合下无法转化为 PnL
3. SHORT 没有形成有效补充，LONG+SHORT 组合放大亏损
4. 继续加过滤器容易进入过拟合路径

### Artifact Paths
- `docs/planning/2026-04-28-h5a-engulfing-smoke-test.md`
- `docs/planning/2026-04-28-h5b-engulfing-pnl-proxy.md`
- `scripts/run_engulfing_smoke_test.py`
- `scripts/run_engulfing_smoke_test_v2.py`
- `scripts/run_engulfing_pnl_proxy.py`
- `scripts/run_engulfing_signal_quality_slice.py`
- `scripts/verify_engulfing_smoke.py`

### Status
**CLOSED** — Engulfing 不进入主线，不做参数搜索，不做 ATR 优化。下一轮策略扩展应转向不同策略家族。

---

## 十、H6a: Donchian 20-Bar Breakout LONG Proxy

### Hypothesis
Donchian 20-bar 收盘突破 LONG-only 在 ETH 1h 上有基础 alpha 痕迹。

### Verdict
**CLOSED — 不进入参数搜索**

### Key Metrics

| 年份 | PnL | Trades | WR | MaxDD |
|------|-----|--------|-----|-------|
| 2022 | -7,891 | 606 | 36.3% | 82.0% |
| 2023 | -3,435 | 436 | 38.3% | 64.3% |
| 2024 | +504 | 225 | 37.3% | 65.4% |
| 2025 | -6,483 | 31 | 19.4% | 74.0% |

3yr (2023-2025): PnL = -17,305 | 1,292 trades | WR=36.7% | MaxDD=74.0%

### Failure Mode
信号过频 + 紧止损 = whipsaw 死亡组合。年均 424 笔交易（vs Pinbar 67 笔），费用侵蚀严重（2022 年费用 $1,795）。20-bar 1h 通道太窄，无法过滤 ETH 噪音。与 Pinbar 本质差异：Pinbar "逆小顺大"，Donchian "顺大顺小"。

### Artifact Paths
- `docs/planning/2026-04-28-h6a-donchian-breakout-proxy.md`
- `reports/research/donchian_h6a_proxy_2026-04-28.json`
- `scripts/run_donchian_h6a_proxy.py`

### Status
**CLOSED** — 不进入 H6b OOS / SHORT shadow，不进入参数搜索。

---

## 十一、仍保留价值的工程/研究资产

### 1. kline_history 支持

**来源**: H5a Engulfing smoke test 开发过程中修复
**价值**: Backtester 现已支持 `detect_with_history()`，多 K 线策略研究基础设施被解锁
**影响范围**: 任何需要前序 K 线数据的策略（Engulfing、Donchian 等）均可直接使用
**路径**: `src/domain/strategy_engine.py:746-753`

### 2. MTF Anti-Lookahead Alignment

**来源**: H0 Market Regime v2 修正 + H5a MTF 对齐
**价值**: 严格使用 `close_time <= signal_time` 避免前瞻偏差，已成为所有 research-only 脚本的标准模式
**核心模式**:
- `close_time = kl.timestamp + period_ms`（不使用 open timestamp）
- `candle_close_time <= entry_timestamp_ms`（只用已收盘 K 线）
- **路径**: `src/application/backtester.py:1101`，以及所有 research scripts

### 3. OOS Baseline Evidence

**来源**: H4 ETH Baseline OOS Check
**价值**: 5yr（2022-2026Q1）全面验证，累计 PnL +9,957，年份分类 3 适配/1 边界/1 失效
**用途**: 作为策略进入实盘/观察期的准入证据（Sim-1 Admission Review 已引用）
**路径**: `docs/planning/2026-04-28-eth-baseline-oos-check.md`

### 4. H5/H6 Negative Results as Boundary Evidence

**来源**: H5 Multi-Symbol Transfer + H6a Donchian
**价值**: 明确划定 ETH 基线的适用边界——不适用于 BTC/SOL/BNB 直接迁移，Donchian 类突破策略在 ETH 1h 上不适用
**用途**: 防止后续重复验证已关闭方向；为策略组合设计提供边界约束

---

## 十二、不能再重复踩的坑

### 1. `runtime_overrides` 不能传 `max_total_exposure`

**来源**: H5b Engulfing PnL Proxy 实验
**问题**: 第一次脚本试跑时 `max_total_exposure` 被错误放入 `BacktestRuntimeOverrides`，实际未生效（日志显示 `max=0.8`）
**正确做法**: 通过 `BacktestRequest.risk_overrides=RiskConfig(...)` 传入
**后果**: 若未注意，实验会以错误风险口径运行，结论无效

### 2. MTF 缺 4h trend 数据会导致假 0 signals

**来源**: H5a Engulfing smoke test
**问题**: 脚本传入空 `higher_tf_trends` dict → MTF filter 返回 `passed=False` → 0 信号触发
**教训**: 信号密度 = 0 不代表策略无效，可能只是数据依赖未满足。需先确认数据完整性再下结论。

### 3. Reach Rate 不等于 PnL

**来源**: H5a → H5b 对比
**问题**: H5a-v2.1 +1R reach rate 76.8%, +3.5R 38.1% 看起来健康，但 H5b 完整撮合后 3yr PnL 均为负
**教训**: reach rate 只能说明"有后续波动"，不能等同于策略正期望。真实交易链中的入场、止损、成本、持仓重叠、敞口限制和信号密度共同决定收益。

### 4. 低相关不等于组合有效

**来源**: H5 Multi-Symbol Transfer
**问题**: BTC/SOL 与 ETH 年度 PnL 相关性低（0.214/0.199），但低相关来自"各自在不同年份各自失败"，而非"一个失败时另一个盈利"
**教训**: 组合有效性的判断需看失效同步性（co-loss），不是简单的相关系数。4yr 累计只有 ETH 净正收益。

### 5. 信号多不等于 alpha

**来源**: H5a Engulfing / H6a Donchian
**问题**: Engulfing 年均 ~700 signals, Donchian 年均 ~648 signals，远高于 Pinbar ~67 signals，但收益更差
**教训**: 高信号密度意味着更高的费用侵蚀、更多噪声交易、更难管理的持仓重叠。策略质量 ≠ 信号数量。

---

## 十三、研究链闭合时间线

```
2026-04-28 (同一天完成)
│
├─ H0: Market Regime E0-E4 → CLOSED (v1 + v2 含反前瞻修正)
├─ H1: SHORT-only baseline → NOT ENTERED
├─ H2: 0.382 limit-entry proxy → CLOSED
├─ H3: Dynamic risk geometry → CLOSED (方向关闭)
│   └─ H3a: Entry-feature prediction → CLOSED (前提不成立)
├─ H4: ETH OOS check → PASSED (基线维持)
├─ H5: Multi-symbol transfer → CLOSED
│   ├─ H5a: Engulfing smoke test → CLOSED (工程通过, PnL不通过)
│   └─ H5b: Engulfing PnL proxy → CLOSED
├─ H6a: Donchian 20 breakout → CLOSED
│
└─ 2023 Rescue Research Closure → 综合收口文档已生成
```

---

## 十四、研究层总结判断

**H0–H3a 研究链**统一指向同一结论：

> 2023 ETH LONG Pinbar 亏损（-3,924 USDT）是市场环境不匹配（趋势延续不足），不是参数可调优的。任何固定阈值/参数/过滤器（粗 regime gate、0.382 limit entry、特征过滤）都无法在不损害 2024/2025 收益的前提下压缩 2023 亏损。建议接受 -3,924 为 2024/2025 alpha（+13,091）的固有成本。

**当前基线状态**：
- ETH 1h LONG-only Pinbar + EMA50 + MTF 4h EMA60
- TP=[1.0R, 3.5R], BE=False
- 5yr 累计 PnL: +9,957 USDT
- OOS 验证通过，基线维持，不修改

**已关闭方向不再碰**：粗 regime gate / SHORT mirror / 0.382 limit / fixed TP2 down / BE=True / Engulfing mainline / Donchian 20 LONG / direct ETH→BTC/SOL transfer / H3 动态退出

---

*本文档为只读证据索引，不提出新实验，不修改 runtime 代码。*
