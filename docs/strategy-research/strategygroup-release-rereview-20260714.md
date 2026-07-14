# StrategyGroup Release-Aligned Re-Review — 2026-07-14

Status: **CURRENT_RESEARCH_EVALUATION**

Scope: **strategy research only**

Runtime authority: **none**

As-of: **2026-07-14T23:10:51+08:00**

## 结论摘要

### 核心结论

1. **系统阶段已从“能否完成真实交易链”进入“真实结果校准”**。当前 release 已证明真实 Ticket、成交、保护、终态、通知和 Outcome 事实能够闭环；这证明的是系统执行模型，不等于任何 StrategyGroup 的盈利能力已经成立。（来源：`docs/current/P1_REAL_TRADE_FACT_TRUTH_AND_VENUE_LINEAGE_IMPLEMENTATION_PLAN.md`；Tokyo 只读运行时快照，2026-07-14T23:10:51+08:00）
2. **当前生产组合是 5 个 StrategyGroup、6 个 Event Spec、22 条 active lane**，不是 2026-06-16 研究柜所描述的候选阶段。旧研究柜中的 `MPG-001`、`SOR-001` 以及 2026-06-23 仍被称为 intake candidate 的 `BRF2-001`，都必须按当前 PG/runtime 身份重新解释。（来源：`docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md`）
3. **当前唯一具有终态真实结果样本的是 `SOR-001`**。3 笔已完成真实交易合计净 PnL 为 **-30.8671537 USDT**，合计 **-1.364809518996755571 R**，胜率 **33.33%**；样本量只有 **n=3**，足以触发结果归因，但不足以支持 promotion、downshift、kill 或参数重写。（来源：Tokyo PG/runtime 只读 forensics，2026-07-14T23:10:51+08:00）
4. **当前最大策略组合问题是多头角色重叠，而不是策略数量不足**。`CPM-RO-001`、`MPG-001`、`MI-001` 共同集中在 `SOLUSDT` 与 `AVAXUSDT`，三者合计只覆盖 5 个不同的多头标的；下一轮研究应优先解释它们在相同市场状态下为何由不同 Event Spec 获得或失去优先权。（来源：当前 active runtime event registry；本报告集合交叉分析）
5. **24 项旧研究柜需要压缩为四类资产**：生产中校准、未来 regime option、现有组的支持/分类器、parked vocabulary。继续把所有指标语义都当作独立 StrategyGroup，会增加重复信号、解释冲突和归因成本，而不会自动增加组合边际价值。（来源：`docs/strategy-research/strategy-cabinet/strategy-cabinet.json`；本报告分析）

### 新的研究链位置

```text
chain_position:
  real_trade_outcome_calibration

first_research_blocker:
  live_outcome_sample_insufficient_and_active_role_overlap_unresolved

capability_unlocked:
  release_aligned_strategy_portfolio_rereview

next_research_bottleneck:
  branch_attribution_plus_cross_group_arbitration_evidence
```

## 已知客观事实

### Release 与生产能力事实

- **同步基线**：`release/brc-real-trade-fact-truth-20260714-r0`，tag `brc-real-trade-fact-truth-20260714-r0`，commit `2001644581cccc968ba695d3ff129960db6a7e84`。（来源：当前 git refs 与 release tag）
- **真实交易事实闭环**：release 验收覆盖首笔 SOL 精确经济事实、AVAX 精确 SL lineage、最新 SOL 自动终态 Outcome；条件单 parent/actual child lineage 被保存，未变化的 reconciliation 不重复制造业务事件。（来源：`docs/current/P1_REAL_TRADE_FACT_TRUTH_AND_VENUE_LINEAGE_IMPLEMENTATION_PLAN.md`）
- **生产身份权威**：当前 scope、side、event、policy、RequiredFacts 与 runtime binding 来自 PG current state；旧 handoff JSON、旧 replay JSON 与 Markdown 不是生产输入。（来源：`docs/current/strategy-group-handoffs/main-control-handoff-index.md`）

### 当前 5 个生产 StrategyGroup

| StrategyGroup | 当前事件角色 | 标的与方向 | Event Spec | 90d / 365d evaluator events | 真实终态样本 |
| --- | --- | --- | --- | ---: | ---: |
| **`CPM-RO-001`** | 回撤后 reclaim 的多头延续 | ETH、SOL、AVAX、SUI；long | `CPM-LONG` | 511 / 2,124 | 0 |
| **`MPG-001`** | 动量持续与突破延续 | OP、SOL、AVAX、SUI；long | `MPG-LONG` | 107 / 470 | 0 |
| **`MI-001`** | 12h impulse + relative strength | AVAX、ETH、SOL；long | `MI-LONG` | 224 / 1,400 | 0 |
| **`SOR-001`** | session opening range 突破/跌破 | ETH、SOL、AVAX、BTC；long + short | `SOR-LONG`、`SOR-SHORT` | 581 / 2,381 | 3 |
| **`BRF2-001`** | 弱趋势环境中的 rally failure | BTC、AVAX、ETH；short | `BRF2-SHORT` | 317 / 1,557 | 0 |

以上 90d/365d 数字是跨 scope 的 evaluator events，不是相互独立的盈利交易；它们只能证明长期 opportunity supply 非零，不能证明盈利能力或 Replay/Live parity。（来源：`docs/current/P1_OPPORTUNITY_FEEDBACK_CALIBRATION_DESIGN.md`）

### 当前真实 Outcome 样本

| StrategyGroup | 标的 | 方向 | 终态净 PnL | R multiple | 研究解释边界 |
| --- | --- | --- | ---: | ---: | --- |
| **`SOR-001`** | SOLUSDT | short | +0.7089188 USDT | +0.820507870370370370 | 正样本；尚不能证明 short branch 有 edge |
| **`SOR-001`** | AVAXUSDT | short | -15.6740310 USDT | -1.115589395017793594 | 负样本；需做 session、entry、SL 与成本归因 |
| **`SOR-001`** | SOLUSDT | long | -15.9020415 USDT | -1.069727994349332347 | 负样本；需与 SOL short 的市场结构差异对照 |
| **合计** | 2 个标的 | 2 个方向 | **-30.8671537 USDT** | **-1.364809518996755571** | **n=3，只允许进入校准，不允许下策略终局结论** |

快照时另有一笔 **`SOR-001 + ETHUSDT + long`** 处于 `runner_protected`，尚未形成终态 Outcome，因此不计入上述合计。（来源：Tokyo PG/runtime 只读 forensics，2026-07-14T23:10:51+08:00）

### 当前多头组合的结构重叠

| 对比对象 | 共同标的 | 重叠数量 | 当前可确认的差异 |
| --- | --- | ---: | --- |
| **CPM ∩ MPG** | SOL、AVAX、SUI | 3 | reclaim continuation 对 momentum persistence |
| **CPM ∩ MI** | ETH、SOL、AVAX | 3 | pullback/reclaim 对 12h impulse/relative strength |
| **MPG ∩ MI** | SOL、AVAX | 2 | persistence/breakout 对 impulse selection |
| **CPM ∩ MPG ∩ MI** | SOL、AVAX | 2 | 三个多头 Event Spec 同时可能竞争的核心标的 |

这些是 **scope 与事件语义重叠**，不是已证实的收益相关性。当前证据尚不能声称三组的 realized return correlation、相互替代率或最佳 winner policy。（来源：当前 active runtime event registry；本报告集合交叉分析）

## 基于事实的分析与评论

### 阶段重置

**真实交易发生后，研究的判定单位必须从“回测窗口是否漂亮”升级为“Event Spec 在真实链路中产生了什么结果、为什么”**。当前应同时保留三层结论：

1. **工程层已成立**：系统能从 fresh event 走到真实 Outcome。
2. **策略层未成立**：除 SOR 外没有终态样本；SOR 也只有 n=3。
3. **组合层尚未闭合**：三个主力多头组在 SOL/AVAX 上重叠，但缺少相同时间窗下的 candidate、arbitration、near-miss 与最终结果对照。

因此，新阶段不应因为系统已经成交而继续扩大 live scope，也不应因为首批总结果为负而立即缩小风险、降低杠杆或 kill 策略。研究侧应输出证据和 stage recommendation，Owner policy 与 Runtime Safety State 仍由主系统控制。（来源：`docs/current/STRATEGY_EXPERIMENT_EVALUATION_CONTRACT.md`；`docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`；本报告分析）

### 当前 5 组的新评价

| StrategyGroup | 新研究角色 | 当前评价 | 第一研究动作 | 暂不支持的结论 |
| --- | --- | --- | --- | --- |
| **`SOR-001`** | `current_active_calibration` | 唯一拥有真实终态样本；首批合计为负，但 long/short、SOL/AVAX 混合后不能归因 | 建立 branch × symbol × session × exit-cause 的 Outcome attribution，纳入未终态 ETH long 后再刷新 | 不支持扩 scope、downshift、kill、改 Event Spec 或改风控参数 |
| **`BRF2-001`** | `current_active_counter_regime` | 当前 active 组合中最明确的 rally-failure short 补充角色；历史 opportunity supply 非零，但无真实终态样本 | 对下一笔自然完成 Outcome 做 squeeze facts、rejection quality、保护与退出归因；此前只维护 no-outcome baseline | 不支持因为 0 outcome 推断策略失效，也不支持把研究侧旧 packet 当生产规则 |
| **`CPM-RO-001`** | `current_active_pullback_continuation` | 多头组中 evaluator event supply 最高；与 MPG/MI 在 SOL、AVAX 高度重叠 | 统计同一 closed-candle 邻域内 CPM-only、co-trigger、arbitration-lost 与 near-miss 分布 | 不支持把 2,124 个 365d events 解读为 2,124 笔交易或最高 edge |
| **`MI-001`** | `current_active_impulse_selector` | relative strength 是区别于 CPM/MPG 的关键语义；覆盖范围更窄 | 验证 `relative_strength_confirmed` 是否真正减少与 CPM/MPG 的同质 candidate，而不是只改标签 | 不支持把较少 scope 直接解释成更高选择质量 |
| **`MPG-001`** | `current_active_persistence_selector` | 已从研究 handoff candidate 变为生产 Event Spec；历史 event supply 最低，但旧研究有较强 right-tail 与较深 drawdown 双重证据 | 对齐旧 WPR/MFI/PPO/TSI/MHI/DMI 组合语义与当前 `MPG-LONG` version，明确哪些证据仍适用 | 不支持用旧 MPG composite 报告直接评价当前 versioned Event Spec |

### 当前优先级

| 优先级 | 工作单元 | 为什么现在重要 | 完成信号 |
| --- | --- | --- | --- |
| **P0-A** | SOR 真实 Outcome attribution | 已有唯一真实损益样本，且 long/short 与 symbol 混合 | 每笔 Outcome 可按 branch、symbol、session、exit cause、cost 解释，不改 runtime authority |
| **P0-B** | CPM/MPG/MI co-trigger 与 arbitration 研究 | 三个多头组集中在 SOL/AVAX，组合边际价值尚未证明 | 能区分独有信号、共同信号、near-miss、arbitration loser 与最终 Outcome |
| **P0-C** | MPG 研究语义到当前 Event Spec 的版本对齐 | 旧研究 MPG 是 member composite，当前生产是 `MPG-LONG` | 形成 evidence applicability matrix，明确 retained / stale / incompatible 证据 |
| **P1-A** | BRF2 首批真实结果校准 | active short 组尚无终态样本 | 第一批自然 Outcome 有统一归因模板，不以无样本调参 |
| **P1-B** | FBS/LCF facts-pipeline options | 与现有 OHLCV 主导组差异最大，可能提供未来 regime option | facts availability、no-signal 与失效边界可复现，但仍不授予生产权限 |
| **P2** | TEQ/NLPD/AEB 等跨资产 option | 提供未来市场结构与资产类别选择权 | 产品、session、流动性、历史长度和可执行方向事实成熟 |

## 24 项研究柜重估

### 新分类规则

- **`current_active`**：已进入当前生产 registry，研究任务是版本对齐与真实结果校准。
- **`future_option`**：与当前组合存在明确 regime、事实源或资产类别差异，保留为未来选择权。
- **`support_filter`**：优先服务现有 StrategyGroup 的分类、排序、disable 或归因，不再默认追求独立 StrategyGroup。
- **`parked_vocabulary`**：保留失败、反例或语义词汇，除非出现新的可复现证据，否则不占 active research WIP。

### 完整重估表

| 研究资产 | 旧状态 | 新分类 | 新评价 | 下一动作 |
| --- | --- | --- | --- | --- |
| **MPG-001** | handoff_ready | `current_active` | 已被生产 `MPG-LONG` 吸收；旧 member 证据需做版本适用性审计 | 建 evidence applicability matrix |
| **FBS-001** | handoff_ready_facts_heavy | `future_option` | funding/basis/crowding 与当前价格事件组差异较大，保留价值高 | 收敛 funding、OI、premium、mark、margin 事实链 |
| **TEQ-001** | handoff_ready_low_history_blocked | `future_option` | 跨资产与低历史 option；产品和 session 风险仍是实质边界 | 只做 current product 与 holdout 刷新 |
| **PMR-001** | observe_only_overlay | `future_option` | 金属 regime overlay，不适合作独立主引擎 | 与具体 target pairing 绑定后再评价 |
| **SOR-001** | conditional_observation | `current_active` | 已进入真实 Outcome 校准，旧 conditional 标签过时 | 以真实 branch Outcome 替代旧阶段叙述 |
| **VCB-001** | observe_only | `support_filter` | true/false breakout 更适合作 CPM/MPG/SOR 的过滤证据 | 形成 pre-entry classifier 对照，不独立 promotion |
| **NLPD-001** | observe_only | `future_option` | listing/contract event 是不同市场状态，但幸存者和可执行方向风险高 | 建 cohort、listing age、产品与 side facts |
| **RBR-001** | parked_or_research_vocab | `parked_vocabulary` | 旧 range boundary 语义已弱；未来只通过 RBR2 的新版本复活 | 不再维护旧 RBR promotion 路径 |
| **LCF-001** | facts_pipeline_required | `future_option` | forced-flow 是潜在非同质事实源，策略价值取决于真实 facts pipeline | 先证明 force order、OI、depth 与 no-signal 正确性 |
| **RSR-001** | observe_only_scorer | `support_filter` | scorer 身份明确，可服务 MI/TEQ 的相对强弱归因 | 只做排序稳定性与 anti-lookahead 审计 |
| **MDS-001** | overlay_candidate | `support_filter` | 金属 session mismatch 是 PMR/TEQ/NLPD 的 context，不是独立收益引擎 | 收敛 target-specific tags |
| **SCF-001** | observe_only | `support_filter` | session confluence 可服务 SOR 与跨资产 session 归因 | 对 SOR Outcome 做 session 标签回填研究 |
| **DMI-001** | observe_only | `support_filter` | ADX/DMI 更适合作 MPG/MI 的 directional-quality 特征；名称不得与 `MI-001` 混淆 | 建特征增量与重复度测试 |
| **MASS-001** | observe_only | `parked_vocabulary` | direction context 与稳定性不足，独立组边际价值低 | 仅保留失败样本与 revival condition |
| **EFI-001** | right_tail_candidate | `future_option` | price-volume exhaustion 可能提供 reversal option，但 drawdown 未闭合 | 只保留 regime-specific holdout 研究 |
| **HAT-001** | research_candidate | `support_filter` | 平滑蜡烛更适合作 trend quality 标签，独立信号易受 lag 影响 | 测试对 CPM/MPG false continuation 的解释增量 |
| **LSR-001** | research_candidate | `support_filter` | upper-range rejection 可服务 BRF2/FBF failed-upside family | 与 LSR2/FBF/VCF 合并语义，不单独 promotion |
| **UO-001** | observe_only | `parked_vocabulary` | divergence 证据弱，容易形成事后解释 | 不占 active WIP，等待 materially new evidence |
| **TRIX-001** | right_tail_candidate | `support_filter` | thin-sample zero-cross 可作 persistence 标签，不足以独立成组 | 只做 sample expansion 与 concentration audit |
| **PSAR-001** | right_tail_candidate | `support_filter` | bullish flip burst 可作事件标签，连续 stop-reverse 语义仍弱 | 评估对 CPM/MPG continuation quality 的增量 |
| **ICH-001** | research_candidate | `support_filter` | cloud breakout 可作结构标签，但存在窗口衰减与 component leakage 风险 | 保留 no-future-cloud 审计，不独立 promotion |
| **CCI-001** | research_candidate | `support_filter` | precious-metal +100 failure 更适合作 PMR/BRF 类 context | 并入 asset-role failure 标签研究 |
| **AEB-001** | research_candidate | `future_option` | ATR expansion 在跨资产短窗口有 revival 价值，但 60d/90d 衰减 | 等待跨资产 holdout 与 false-breakout 过滤证据 |
| **STOCH-001** | parked_or_research_vocab | `parked_vocabulary` | whipsaw/range-persistence 适合作反例词汇，不适合 active lane | 仅保留 negative evidence |

以上分类是 **研究 WIP 与资产角色建议**，不会修改 PG registry、Owner policy、Event Spec、leverage、notional、runtime profile 或 execution eligibility。（来源：`docs/strategy-research/strategy-cabinet/strategy-cabinet.json`；本报告分析）

## 2026-06-23 新候选家族的阶段更新

| 候选/家族 | 2026-06-23 解释 | 2026-07-14 新解释 | 处理方式 |
| --- | --- | --- | --- |
| **BRF2-001** | highest-priority short intake candidate | 已成为 `current_active_counter_regime` | 从 admission 研究转为首批真实 Outcome 校准 |
| **RBR2-001** | mean-reversion role asset | `future_option`，但不复活旧 RBR-001 | 保留新版本 range detector 与 stop model 研究 |
| **FBF / LSR2 / VCF** | failed-upside candidates | `support_filter` family | 合并成 BRF2/VCB 的 failed-upside classifier 证据 |
| **BTPC2** | large corpus / disable-facts source | `support_filter` / facts source | 禁止作为 standalone strategy 读取 |
| **DSS / LCF** | derivatives / forced-flow data lanes | `future_option` facts pipeline | 先建设可复现事实，不以小样本下收益结论 |
| **SRD** | session attribution material | `support_filter` | 并入 SOR/SCF session attribution |
| **XFBS** | funding-stress cross-asset route | FBS 版本/路由证据 | 不建立重复 StrategyGroup identity |
| **XTEQ** | low-history cross-asset route | TEQ 版本/路由证据 | 保留 late-US 路由 falsification，不单独 admission |

## 接下来应产出的研究证据

### P0 证据包

1. **SOR Live Outcome Attribution v1**
   - 输入：每个终态 Ticket 的 symbol、side、session、event version、entry、protection、exit cause、fee、funding、net PnL、R。
   - 输出：branch-level 样本表、失败类型、不可归因字段、下一样本停止条件。
   - 边界：不改 SOR Event Spec、风险参数或 runtime scope。
2. **Long-Group Co-Trigger And Arbitration Matrix v1**
   - 输入：CPM/MPG/MI 同一 closed-candle 邻域的 true、near-miss、candidate、arbitration outcome。
   - 输出：独有率、共同触发率、near-miss、arbitration loser 与最终 Outcome。
   - 边界：观察和回放结果不授予 runtime trade/order authority。
3. **MPG Evidence Applicability Matrix v1**
   - 输入：旧 member composite 与当前 versioned `MPG-LONG` 的事实、时点、scope、side、exit 语义。
   - 输出：`retained`、`stale`、`incompatible`、`needs_replay` 四类映射。
   - 边界：旧研究结果不能反向覆盖当前 PG Event Spec。

### 停止规则

- **不继续广泛新增指标策略**，直到上述 P0 证据能回答现有组的独特组合价值。
- **不因 n=3 直接调策略参数**，避免把首批随机路径当作稳定分布。
- **不把无真实 Outcome 的组标为失败**，无样本只表示校准未开始。
- **不把 evaluator event count 当收益排行榜**，event supply 与 realized edge 必须分开。
- **不把研究报告写回运行时权威**，所有生产身份仍以 PG current state 和 versioned Event Spec 为准。

## 非执行边界

```json
{
  "research_only": true,
  "runtime_registry_mutation": false,
  "owner_policy_mutation": false,
  "strategy_parameter_mutation": false,
  "risk_or_sizing_mutation": false,
  "finalgate_input": false,
  "operation_layer_input": false,
  "exchange_write": false,
  "real_order_authority": false
}
```

## 信息来源

### 当前权威来源

1. **生产 StrategyGroup 身份与 lane**：`docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md`。
2. **PG current state 权威边界**：`docs/current/strategy-group-handoffs/main-control-handoff-index.md`。
3. **策略评价合同**：`docs/current/STRATEGY_EXPERIMENT_EVALUATION_CONTRACT.md`。
4. **Owner/runtime 权限边界**：`docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`、`docs/current/AI_AGENT_CONSTRAINTS.md`。
5. **历史 opportunity calibration**：`docs/current/P1_OPPORTUNITY_FEEDBACK_CALIBRATION_DESIGN.md`。
6. **真实交易事实 release 验收**：`docs/current/P1_REAL_TRADE_FACT_TRUTH_AND_VENUE_LINEAGE_IMPLEMENTATION_PLAN.md`。
7. **真实 Outcome 快照**：Tokyo 生产 PG/runtime，只读 `scripts/ops/query_runtime_signal_forensics.py`，as-of `2026-07-14T23:10:51+08:00`。

### 研究来源

1. **24 项 Strategy Cabinet**：`docs/strategy-research/strategy-cabinet/strategy-cabinet.json`，version `2026-06-16-r1`。
2. **新评价口径与 short/cross-asset candidates**：`docs/strategy-research/new-evaluation-mouthpiece-rereview-20260623.md`。
3. **MPG member evidence**：`docs/strategy-research/momentum-persistence-strategy-group/momentum-persistence-strategy-group-summary.md`。

本报告未使用个人社交媒体、论坛账号或自媒体材料作为事实来源；历史研究目录中即使保存过 community intake，也不构成本次结论的事实依据。
