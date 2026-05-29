# STRATEGY_RESEARCH_HISTORY.md

Last updated: 2026-05-29
Status: research-only snapshot

---

## 1. 总览

| 策略族 | 核心假设 | 时间周期 | 标的 | 最高阶段 | 当前结论 | 是否保留 | 证据强度 |
|---|---|---|---|---|---|---|---|
| Direction A (Trend Breakout) | Donchian20 突破 + EMA60 过滤 → 趋势延续 | 4h | ETH/BTC/SOL | cross-asset diagnostic + P0/P1/P2 | PAUSE_FRAGILE / NON_RUNTIME | 保留为证据档案 | MEDIUM |
| CPM-1 (ETH Pinbar Pullback) | HTF 趋势 + LTF Pinbar 回调入场 → 趋势延续 | 1h | ETH | OOS 2021+2022 | OOS_NEGATIVE, 已暂停 | 保留为已暂停证据 | HIGH（明确否定） |
| Direction C (Volatility Contraction) | 波动收缩后扩张 → 突破方向 | 未确认 | ETH | frozen baseline | INSUFFICIENT_EVIDENCE / PAUSE_THIN_FRAGILE | 保留，待更多证据 | LOW |
| Direction D (Structured Pullback) | 结构化回调/价值区入场 | 未确认 | ETH | frozen baseline | REJECTED_FROZEN_BASELINE | 已拒绝 | HIGH（明确否定） |
| Short-side (4h Breakdown) | 空头突破延续 | 4h | ETH | frozen baseline | REJECTED_FROZEN_BASELINE | 已拒绝 | HIGH（明确否定） |
| VEI (Volatility Expansion) | 波动扩张 + close location + follow-through | 4h | ETH | frozen baseline | PAUSE_FRAGILE（所有正 PnL 来自 Direction A echo） | 保留但降级 | MEDIUM |
| SQ02 (Downside Continuation) | 下行延续 | 未确认 | 未确认 | docs skeleton | design/local-sandbox candidate only | 保留为骨架 | LOW |
| TF-001 (Trend Following) | 趋势跟随 | 未确认 | BTC/ETH | carrier validation | BRC carrier，非 alpha proof | 保留为 carrier | LOW（无独立验证） |
| Broad Smoke Screen (9 variants) | 多种 OHLCV-only 机制 | 1h | BTC/ETH/SOL/BNB | broad screen | 3 个 trial candidate selected | 保留为候选 | LOW（仅 OHLCV） |

---

## 2. 已研究策略族详情

### 2.1 Direction A — Trend Breakout (Donchian20 + EMA60)

#### 核心假设
4h Donchian20 突破做多，EMA60 趋势过滤，趋势延续。

#### 入场逻辑
价格突破 Donchian20 上轨 + EMA60 趋势确认。

#### 出场逻辑
Donchian20 下轨或 EMA60 穿越。

#### 标的范围
ETH/BTC/SOL

#### 时间周期
4h

#### 样本期
全样本（含 2019-2025）

#### 样本外结果
- ETH: 173 trades, PF 1.517, net +3001.66（DIRA-EH-001）
- BTC: 159 trades, PF 1.477, net +2517.17（DIRA-XA-003）
- SOL: 158 trades, PF 1.790, net +4018.80（DIRA-XA-003）

#### 关键诊断结果
- P0: WINNER_EVIDENCE_PARTIALLY_SHARED, PF_CONFIDENCE_INCONCLUSIVE（P0_EVIDENCE_STRENGTH_INCONCLUSIVE）
- P1: ENTRY_ALPHA_PARTIAL (Donchian20 entry contributes but not decisive), SMART_BETA_TIMING
- P2: P2_RISK_SHAPE_IMPROVES_BUT_NON_RUNTIME
- Cross-asset: CROSS_ASSET_SUPPORTS_MECHANISM / NON_RUNTIME

#### 主要问题
- Top-3 removal: ETH/BTC negative, SOL positive but top-5 negative
- 无 pre-observable applicability boundary
- SRR-002 未满足
- P1 结论：不是纯 breakout alpha，更接近 smart beta timing

#### 当前结论
**POSITIVE_CROSS_ASSET_SPARSE_TREND_EVIDENCE / PAUSE_FRAGILE / NON_RUNTIME**

#### 是否值得继续
保留为证据档案和基准。Owner 可选择 Option B (TE-001 full review) 或 C (boundary hypothesis study)，但当前优先级低于 broad smoke screen。

#### 证据来源
- DIRA-EH-001, DIRA-XA-001/002/003
- DIRA-P0-001/002, DIRA-P1-001/002, DIRA-P2-001

#### 待确认事项
- TE-005 2019-Q4 数据不一致是否已解决
- small-live design plan 是否已 Owner 审阅

---

### 2.2 CPM-1 — Crypto Pullback Module v1 (ETH Pinbar Pullback)

#### 核心假设
HTF 趋势完整 + LTF Pinbar 回调结束 → 趋势延续。

#### 入场逻辑
ETH 1h Pinbar pattern + HTF 趋势确认。

#### 出场逻辑
部分止盈（TP1-TP5）+ 止损。

#### 标的范围
ETH/USDT:USDT

#### 时间周期
1h

#### 样本期
2020-2024（backtest）

#### 样本外结果
- 2022 OOS: -971.71 USDT (-9.72%), 61 trades, WR 31.1%, PF 0.624, MaxDD 10.48% — OOS_NEGATIVE
- 2021 OOS: -21.54%, 74 positions, WR 29.5%, PF 0.466, MaxDD 22.18% — OOS_NEGATIVE（worse than 2022）

#### 失败分类
- 2022: 成本主导的不利环境失败（与失败假设一致）
- 2021: 信号级别的有利环境失败（直接挑战盈利假设）
- 2021 gross edge 为负（-573.84 USDT），成本拖累放大但非主因

#### 适用性边界归因
- H1 (ATR filter): 2021 部分有效，2023 无效
- H2 (continuation failure): POST_HOC
- H5 (macro context): 2022 部分可解释，2023 不可解释
- Hurst ~0.50 everywhere（无持久性优势）

#### 当前结论
**CPM_OHLCV_BOUNDARY_ATTRIBUTION_PAUSED_RESEARCH_EVIDENCE_PRESERVED**

#### 是否值得继续
暂停。Option A（暂停）已推荐，Option C（extra-data inspect）保留给未来 Owner 决策。不重启为 runtime candidate。

#### 证据来源
- CPM-OOS-RUN-001 (2022), CPM-OOS-2021-RUN-001 (2021)
- CPM-OOS-FAILURE-CLASSIFY-001
- CPM-ABI-001, CPM-FCX-001, CPM-CPA-001, CPM-CMC-001, CPM-H5RA-001, CPM-CLOSE-001

---

### 2.3 Direction C — Volatility Contraction / Re-expansion

#### 核心假设
波动收缩后方向性扩张。

#### 样本外结果
63 trades, net +2039, PF 1.405, MTM DD 15.01%

#### 当前结论
**INSUFFICIENT_EVIDENCE / PAUSE_THIN_FRAGILE**
- 2021+2022 trade floor missed by 1 trade
- Winner count 10 < 15
- Top-1 = 82.25% of net（极度集中）
- 14.3% overlap with Direction A

#### 证据来源
- MTC-004

---

### 2.4 Direction D — Structured Pullback / Value-Zone Entry

#### 当前结论
**REJECTED_FROZEN_BASELINE**
- 417 trades, 66 winners, net -262.57, PF 0.985
- MTM DD 29.78%
- Top-1 removal: -3021.88
- Direction A overlap 29.50%
- pullback-continuation family 优先级降低

#### 证据来源
- MTC-006

---

### 2.5 Short-side 4h Breakdown Continuation

#### 当前结论
**REJECTED_FROZEN_BASELINE**
- 23 trades, 1 winner, net -1699.88, PF 0.317
- 2021 strongly negative, 2022-2024 no trades, 2025 single-winner concentrated
- 0% Direction A/C overlap

#### 证据来源
- SSD-003

---

### 2.6 VEI — Volatility Expansion / Impulse Participation

#### 核心假设
Bar-level range expansion + close-location + follow-through。

#### 参数
K=1.5, N=20, P=0.75, EMA60, 5-bar hold, 2×ATR14 stop。

#### 样本外结果
118 trades, net +630.49, PF 1.21

#### 当前结论
**PAUSE_FRAGILE**
- Overlap gates passed (A 27.1%, C 2.5%)
- Independent signals net -329.02 PF 0.86
- **All positive PnL from Direction A echo**
- Top-3 removal: -286.85

#### 证据来源
- VEI-001/002/003/004

---

### 2.7 SQ02 — Downside Continuation

#### 当前结论
design/local-sandbox candidate only
- docs-only StrategyContract skeleton
- 无独立回测验证

#### 证据来源
- PLC-SQ02-001

---

### 2.8 TF-001 — Trend Following (BRC Carrier)

#### 当前结论
**carrier_validation_only**
- 用于验证 BRC 完整治理链路
- 非 alpha proof，非 profitability evidence
- TF-001 carrier full-chain smoke 已通过

#### 证据来源
- BRC-R5-001/001A-001E
- strategy-family-map-v0

---

### 2.9 Broad OHLCV Smoke Screen (BRC-R5-003)

#### 9 个变体
TB-001, TB-002, VB-001, PC-001, PC-002, MR-001, RB-001, VI-001, MI-001

#### 标的
BTC, ETH, SOL, BNB × long/short

#### 当前结论
3 个 trial_candidate_with_known_risks:
1. **MI-001 BNB long**: 2683 signals, 72h mean +3.53%, score 4.71
2. **MI-001 SOL long**: 8135 signals, 72h mean +1.95%, score 2.14
3. **VI-001 ETH long**: 1277 signals, 72h mean +1.12%, score 1.00

#### 局限性
- 有意不完整：无成本/滑点/资金费率/清算建模
- 无随机/持有基线
- 无滚动 campaign 破产率
- Owner 尚未审查事件样本

#### 证据来源
- `reports/directional-opportunity-broad-smoke-20260529/`

---

## 3. 失败方向清单

| ID | 策略/假设 | 为什么失败 | 证据 | 是否值得重试 | 重试条件 |
|---|---|---|---|---|---|
| FAIL-001 | CPM-1 ETH Pinbar Pullback | OOS 2021/2022 均为 NEGATIVE；2021 gross edge 为负；2023 continuation failure 不可解释 | CPM-OOS-*, CPM-CLOSE-001 | 仅当 extra-data inspect 有新假设 | 新可观察边界假设 |
| FAIL-002 | Direction D Structured Pullback | PF 0.985, net negative, top-1 依赖 | MTC-006 | 不建议 | — |
| FAIL-003 | Short-side 4h Breakdown | 23 trades, 1 winner, PF 0.317 | SSD-003 | 不建议 | — |
| FAIL-004 | VEI 独立 alpha | 所有正 PnL 来自 Direction A echo | VEI-003 | 不建议作为独立策略 | — |

---

## 4. 保留方向清单

| ID | 方向 | 保留理由 | 当前证据 | 下一步建议 |
|---|---|---|---|---|
| KEEP-001 | Direction A (Trend Breakout) | cross-asset positive sparse trend evidence, PF > 1 | DIRA-XA-003, P0-P2 | Owner 决策：preserve / TE-001 / boundary study |
| KEEP-002 | TF-001 (BRC Carrier) | 适合验证 BRC 治理链路 | BRC-R5-001E | 继续 carrier validation |
| KEEP-003 | MI-001 BNB long (broad smoke) | 最高 smoke screen score | BRC-R5-003 | 补充成本/基线建模 |
| KEEP-004 | MI-001 SOL long (broad smoke) | 第二高 score | BRC-R5-003 | 同上 |
| KEEP-005 | VI-001 ETH long (broad smoke) | 第三高 score | BRC-R5-003 | 同上 |
| KEEP-006 | SQ02 (Downside Continuation) | 设计骨架已存在 | PLC-SQ02-001 | 等待合适时机 |

---

## 5. 不建议短期重复研究的方向

| ID | 方向 | 不建议原因 | 已有证据 |
|---|---|---|---|
| AVOID-001 | CPM-1 参数优化 | OOS 失败非参数问题 | CPM-OOS-FAILURE-CLASSIFY-001 |
| AVOID-002 | Direction D Pullback | REJECTED_FROZEN_BASELINE | MTC-006 |
| AVOID-003 | Short-side Breakdown | REJECTED_FROZEN_BASELINE | SSD-003 |
| AVOID-004 | VEI 作为独立策略 | 无独立 alpha | VEI-003 |
| AVOID-005 | Deep TB-001 year/regime digging | 当前优先级为 broad screening | roadmap-v2 2026-05-29 |
| AVOID-006 | ML/HFT | 当前阶段复杂度过高 | strategy-family-map-v0 |

---

## 6. 重要方法论经验

| ID | 经验 | 来源 | 后续影响 |
|---|---|---|---|
| METH-001 | SRR-002 七项标准是 Level 3 准入门 | SRR-002 | 任何未来策略研究必须满足 |
| METH-002 | 独立 alpha 验证：non-overlapping signals 必须产生 positive net PnL | SRR-002 Sec 3 | VEI-003 因此降级 |
| METH-003 | sparse trend 的 top-winner 依赖是 deployment blocker 而非自动 reject | SRR-002 Sec 4 | Direction A 因此归档而非拒绝 |
| METH-004 | post-hoc continuation proxy 不可作为 pre-observable boundary | CPM-CPA-001 | CPM-1 OHLCV 边界归因停止 |
| METH-005 | 回测 slippage 需要用 unslipped base price 比较 | CPM-BT-METRIC-001 | slippage 计算已修复 |
| METH-006 | mock PnL ≠ 真实收益 | BRC-R0R1-001 | 所有 BRC 证据需标注 mock |
| METH-007 | MTC-001 top-winner concentration 是策略评估框架 | MTC-001 | Direction C/D 因此分类 |
| METH-008 | broad coarse screening 优先于 deep digging | roadmap-v2 2026-05-29 | 当前研究优先级 |
