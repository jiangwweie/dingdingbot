---
title: EVENTSPEC_INSTRUMENT_FIT_RESEARCH_OVERVIEW
status: CURRENT_RESEARCH_OVERVIEW
date: 2026-08-23
last_verified: 2026-09-06
phase: P3-X
production_authority: NONE
---

# EventSpec × Instrument Fit Research Overview

## Decision

当前研究方向从 **静态 Symbol 选择** 收敛为 **EventSpec-aware Dynamic Selection**。

第一轮冻结研究提供了两项边界清晰的证据结论：

1. 同一个 **Crypto SOR v4** 在不同 Instrument 上观察到历史横截面差异；
2. 当前冻结方法没有观察到固定 Symbol 排名的稳定样本外延续。

因此项目不维护静态“好币名单”。SOR Historical Replay通过冻结定量Gate后，完成了
SOR Dynamic Selection V0设计和实现。随后的Multi-Strategy Stage-2/2.1、Stage-3与最后一次
Stage-3.1研究已经结束；Owner接受带provenance note的独立复核，授权进入
**Generic Multi-Strategy Dynamic Selection V1详细设计**。进一步Feature研究关闭，
新Generic实现及生产activation均未授权。

```text
Strategy Thesis
-> Point-in-Time Instrument State
-> Coarse Qualification
-> Dynamic Selection
-> Historical Replay
-> Production detailed design
-> Golden parity + production certification
-> separately approved small-capital activation
```

## Current Multi-Strategy Design Input

| Strategy | Frozen Selector | Entry / Retain | Independent review boundary |
| --- | --- | --- | --- |
| SOR | Existing Dynamic V0 | 7 / 7 | 保持原Decimal Golden、时钟、执行与恢复语义 |
| CPM | Absolute Directional Efficiency V1 | 16 / 16 | capture 62.6%，`TOP16_FALLBACK_CAPTURE_BELOW_FLOOR`；未证明质量改善 |
| MPG | Persistent Leadership Score V1 | 12 / 16 | 有区分度；Outcome偏弱但样本稀疏；名单实际可为12..16 |
| MI | Positive Impulse Recency V0 | 16 / 16 | capture 86.7%；SPARSE |
| BRF2 | Residual Extension V0 | 16 / 16 | capture 74.4%，`TOP16_FALLBACK_CAPTURE_BELOW_FLOOR`；基本中性 |

来源：[Stage-3.1冻结报告](https://github.com/jiangwweie/dingdingbot/blob/f65d72fa92580de4b8c0323f4106d5975b97f4eb/research/semantic_dynamic_selection_stage3_1/artifacts/STAGE3_1_FINAL_SEMANTIC_REVISION_REPORT.md)、
Owner提供的独立复核与
[追加provenance amendment](https://github.com/jiangwweie/dingdingbot/blob/42957b2091b988c53d6e03cb24639c17c54229b5/research/semantic_dynamic_selection_stage3_1/STAGE3_1_PROVENANCE_AMENDMENT.md)。
Top16 fallback来自pre-result correction，不是原Protocol文本独自推出；原报告、Protocol、
manifest和全部研究结果保持不变，不重跑Replay。

当前设计：
[Generic Multi-Strategy Dynamic Selection V1](2026-09-06-generic-multi-strategy-dynamic-selection-v1-design.md)。
状态为 **DESIGN_REVIEW_REQUIRED / implementation_authority=NONE / production_authority=NONE**。
各策略独立STATIC/DYNAMIC；MPG/MI固定Comparison24与动态Tradable集合分离。
Event-time Context Forward Shadow保留辅助研究定位，不作为此生产选币设计的前置实现。

以下SOR研究证据和P3-X表是已完成路线的历史记录；部署与当前控制事实只由
`docs/current/MAIN_CONTROL_ROADMAP.md`拥有，不从历史阶段授权文字推导实时权限。

## Known Evidence

### Frozen study identity

| Item | Verified fact |
| --- | --- |
| Study | **`SOR-INSTRUMENT-EFFECT-v1`** |
| Scope | **24** Binance USDⓈ-M perpetual Instruments |
| Main sample | **36,577** SOR Events; complete-day rate **100%** |
| Source parity | 研究包匹配其声明的源码快照；当前 `SORDetector` 完整文件哈希仍一致，Registry/Exit Policy 因后续 TradFi 扩展而完整文件哈希变化，Crypto SOR v4 语义需在 V0 执行前重新认证 |
| Archive | `sor_instrument_effect_v1_results.tgz` |
| Archive SHA-256 | `d5947191abe392553ba8bccddc6ba0d5c691af511d663100cfbbecd0866f0ea2` |

来源：冻结研究产物 `study_manifest.json`、`source_semantic_check.json`、
`headline.json` 与归档 SHA-256。

当前 tracked code 对比显示，完整 Registry/Exit Policy 文件的差异来自后续
`SOR-US-EQ-PERP-001` 合约和退出策略加入；Crypto `SOR-001` v4 的 Event、Stop、Reclaim、
Session 和 96-bar 语义未观察到变化。该人工 Diff 是继续研究的依据，不等于复用旧哈希
即可认证当前实现。P3-X.1 必须重新导入当前 `evaluate_strategy_snapshot()` 并冻结本次
运行的 exact source digest。（来源：当前 tracked code、冻结研究包
`EXPECTED_SOURCE_HASHES` 与 `source_semantic_check.json`）

### Instrument identity result

| Evidence | Result | Meaning |
| --- | ---: | --- |
| Clustered Symbol Wald | `p = 0.03296` | 历史 Instrument 结果存在横截面差异 |
| Within-day permutation | `p = 0.02249` | 差异不能完全由同日市场环境解释 |
| OOS top-bottom Tail3 gap | **-0.15 pct** | 固定历史排名没有形成未来优势 |
| OOS gap 95% CI | **[-0.89 pct, +0.59 pct]** | 无稳定正向分离 |
| Positive OOS folds | **37.5%** | 排名方向多数 Fold 不持续 |
| Adjacent half-year rank rho | **0.02** | 相邻半年 Symbol 排名近似不相关 |

冻结结论是：

```text
IN_SAMPLE_HETEROGENEITY_BUT_WEAK_PERSISTENCE
```

来源：`decision.json`、`rolling_oos_bootstrap.json`、
`within_day_symbol_permutation.json`、`halfyear_rank_stability.csv`。

### Geometry result

原研究的 Trigger-time **OR Width / ATR14** 与 policy-attainable `+3R` 路径呈单调下降：

| OR/ATR cohort | Tail3 rate |
| --- | ---: |
| 最窄四分位 | **约 13.7%** |
| 第二四分位 | **约 10.9%** |
| 第三四分位 | **约 8.9%** |
| 最宽四分位 | **约 5.5%** |

这支持 **Compression → Expansion** 的 SOR Selection Thesis，但不直接授权生产阈值。
原指标在 Trigger 时计算，已经包含 OR 后的 K 线信息；V0 必须改用 `UTC 01:00` 已知的
**Pre-trigger OR Width / ATR**，防止未来信息泄漏。

来源：`events.csv.gz`、冻结研究程序的 ATR14 定义与分位数复核。

### Dynamic Selection V0 Replay result

冻结 V0 Replay 已全部通过原 Decision Contract：

| Evidence | Dynamic | Comparison | Result |
| --- | ---: | ---: | ---: |
| Tail3 / 100 directional slot-days | **9.841** | Static **7.931** | **+24.1%** |
| Random 7 envelope | **9.841** | P75 **8.117** / Max **8.384** | Dynamic above all 100 |
| Selection gradient | **9.841** | Near **8.295** / Not Selected **6.177** | Ordered |
| Complete 90-day blocks | — | — | **9 / 10** positive |
| Direction lift | LONG **+19.0%** | SHORT **+29.0%** | Both positive |
| Tail3 / Trigger | **11.76%** | Static **9.78%** | **+20.2%** |

上表保留独立Replay原始research provenance。DS-00已确认其Feature arithmetic使用binary64；
批准的生产Golden按`Decimal(precision=38, ROUND_HALF_EVEN)`冻结后，7个相等OR/ATR cohort边界
不再受float rounding noise影响，Dynamic Tail3从`1,324`修正为`1,323`。该修正不改变Feature、
Activity floor、Top N、Candidate Panel或Outcome，完整差异由Implementation Plan的DS-00 manifest
拥有。

正式 Replay decision 是 `ADVANCE_TO_FORWARD_SHADOW`；Owner 随后明确把该动作升级为“直接
进入生产详细设计”，这属于后续路线决策，不改写 Replay 原始结论。（来源：Owner 提供的
`/Users/jiangwei/Downloads/REPORT.md`，SHA-256
`de8edc672552097ad6f9e3988e08254f75b46d33433ad2cd12fd1e56de59a298`）

## Analysis

### What the evidence supports

基于上述事实，当前最合理的研究对象不是：

> 哪几个币长期最好。

而是：

> 在同一个 UTC Session 开始时，哪些 Instrument 的当前状态更符合 SOR 的价格结构。

这使第一版可以保持简单、可解释：

```text
Tradeability / data qualification
-> Activity minimum
-> lower Pre-trigger OR Width / ATR priority
-> SELECTED / NEAR_THRESHOLD / NOT_SELECTED
```

### What remains unproved

当前仍未证明：

- Dynamic Selection 能提高真实净收益；
- Activity、Pre-session Extension 或市场 Regime 具有增量预测力；
- 每日 Dynamic Universe 能否长期满足 **01:14 运行 SLO**，并在超时时可靠保持交易真空；
- Crypto `SOR-001` 应恢复 ENTRY。

Historical Replay 仍是 **Development Evidence**，不被重新描述为独立未来样本或真实净收益。
Owner 已选择以小资金、原风险边界的正式生产实验获取下一层证据；这项路线变更不自动
恢复 Crypto Strategy、不提高风险，也不免除 Golden parity、Migration、runtime timing、
explicit fallback 和 rollback certification。

## Product Concepts

### Source Integrity, Qualification, Selection, Dynamic Universe

| Concept | Answers | Does not mean |
| --- | --- | --- |
| **Source Integrity** | 固定 Panel 的Point-in-Time窗口是否全部完整可信 | 缺数据的member可被静默排除后继续Rank |
| **Qualification** | Source完整后Instrument是否满足最低产品、Activity和几何条件 | 相对排名靠后就是不可交易 |
| **Selection** | 在有限名额下，当前谁更符合某个 EventSpec | 风险批准、Ticket 准入或订单授权 |
| **Dynamic Universe** | 如何承载已批准的 Selection 结果 | 原地修改 Active Universe 或绕过 Warming |

V0 使用以下互斥状态：

```text
INELIGIBLE
SELECTED
NEAR_THRESHOLD
NOT_SELECTED
```

Historical Replay 的 `EMPTY` 是固定 7-slot 对照语义，不是第五个成员状态。Owner 后续冻结
的生产语义是：`Ready=1..7` 全部 Selected，`Ready=0` 记录 **`VALID_EMPTY`**，整个周期无新
交易且不 fallback previous；该运行决策不回写 Historical Replay。

### Earlier SOR-stage strategy theses (historical)

| Strategy | Selection Thesis | First candidate features |
| --- | --- | --- |
| **SOR** | Compression → Expansion | OR/ATR、Activity、Pre-session Extension |
| **CPM** | Trend → Healthy Pullback → Continuation | Trend efficiency、Pullback depth、formal R geometry |
| **BRF2** | Extension → Rejection → Failure | Rally extension、relative strength、HTF persistence |

上表是SOR阶段的早期研究方向，不是新Generic算法参数。当前冻结算法由本文件开头的
Multi-Strategy表和Stage-3.1 evidence定义；新设计必须将稳定 **ComparisonUniverse**
与可交易 **StrategyUniverse** 分开，避免缩小比较集合改变 `rank == 1`。

## Architecture Boundary

已完成研究层的有效范围是：

```text
Owner Allowed Research Panel
∩ Point-in-Time Qualification
-> SelectionSnapshot
-> exact SOR v4 Historical Replay
```

已完成SOR V0生产设计的范围是（新Generic扩展见当前设计链接）：

```text
Selection Plane
Binance public data
-> full-panel source integrity
-> immutable SelectionSnapshot + exact 24 decisions
-> SNAPSHOT_READY -> END

========== PostgreSQL handoff ==========

Runtime Materialization Plane
-> open PRE_FENCE_CONTINUITY for exact current pair before Selection outcome
-> Selection failure only appends continuity reason
-> VALID_EMPTY / ordinary NO_CHANGE / Desired generation
-> Strategy Entry Vacuum + unfinished ENTRY drain
-> Authority Gap Audit + first_eligible_close_time
-> serial LONG/SHORT warming to staged
-> atomic pair activation or gated post-fence FALLBACK_PREVIOUS
-> immutable SelectionSessionAuthority

Deployment Plane
-> recover durable authority and complete independently
-> pending materialization continues in background

Observation -> StrategySignal
```

Selection逻辑位于 **StrategySignal之前**。StrategyUniverse仍唯一拥有member set；
SelectionSessionAuthority拥有time-bounded ENTRY permission；Strategy Entry Vacuum在Signal、
Admission/Ticket和dispatch FinalGate重复阻断新ENTRY。Admission继续只负责账户、风险、容量、
Policy与Netting Domain，不承载Alpha选择。研究文件、CSV、Parquet、Markdown和本地缓存都
没有生产权威。Selection Runner、Materialization Coordinator和Observation Runner使用独立
application entry point与DB lease；V0不强制新增第五个systemd Worker。每个已经处于Dynamic
mode的Session都在Selection结果前从exact current pair建立`PRE_FENCE_CONTINUITY`，并持续到普通
`NO_CHANGE`替换或Vacuum commit；Selection failure只追加reason。任何未连续覆盖eligible close的
Authority都必须先持久化COMPLETE/fresh Gap Audit结果，Vacuum activation/fallback使用exact
`previous ∪ desired` AuditSet，late continuity/普通`NO_CHANGE`使用current pair。Authority冻结
`first_eligible_close_time_ms`，使audit与Observation close范围不重叠；Pause Resume同成员也必须
drain、audit并解析Pause Vacuum后提交新的`NO_CHANGE`。Generation只冻结两个target及expected
digest，不预分配Universe ID或复制Dynamic selected members；actual Universe创建transaction直接
写唯一Generation FK，不创建第二linkage table、direct Snapshot FK或rollback member副本。
首次Static-to-Dynamic尝试保留Static authority直至首个Dynamic outcome。Release compatibility
fact只作为现有Release Certification manifest的薄投影，不形成第二套发布系统。

实施澄清固定为：`session_start_ms=D 00:00`只拥有SOR identity，Selection/Authority Period从
`D 01:00`decision boundary开始；首次post-fence失败复用transition-scoped
`FALLBACK_PREVIOUS + STATIC_BASELINE`并保持mode Static；`VALID_EMPTY`只从commit向前阻止new
ENTRY，不追溯撤销此前合法Ticket/fill或protected lifecycle。

## SOR Phase History

| Phase | Scope | Production effect |
| --- | --- | --- |
| **P3-X.0 — Instrument Effect** | 已完成固定面板敏感度研究 | None |
| **P3-X.1 — Dynamic Selection V0 Replay** | 已完成；全部冻结定量 Gate 通过 | None |
| **P3-X.2 — Production design** | 三Plane ownership/DB handoff、generic Selection facts、独立leases、Selection-Period continuity Authority、SelectionSessionAuthority、Entry Vacuum、source failure、通用Authority Gap Audit、`first_eligible_close_time_ms`、`VALID_EMPTY/NO_CHANGE/SUPERSEDED`、Pause Resume、unfinished ENTRY drain、双腿partial-retained、唯一Generation→Universe linkage、serial warming、atomic switch、first Dynamic activation特例、post-fence fallback、thin release compatibility projection | **DESIGN_APPROVED**；Production Design已完成，不单独授权实现；`production_authority=NONE` |
| **P3-X.3 — Implementation/certification** | **DS-00至DS-10本地实现与证据包已完成**；Decimal Golden/Core parity、serial warming、atomic pair activation、supersession/fallback、四个new-ENTRY边界Authority lineage、independent runtime hosting/recovery、Owner Pause、Owner Dynamic activation boundary、24-Candidate readonly audit、exact release fact和zero-runtime-side-effect postflight已经闭合 | `PLAN_APPROVED / LOCAL_IMPLEMENTATION_COMPLETE / production_authority=NONE`；exact candidate由clean-HEAD R4 manifest认证；下一Gate为独立软件部署复核 |
| **P3-X.4 — Small-capital activation** | Owner 单独授权 Dynamic mode；原风险边界 | Production Instrument eligibility changes |
| **P3-X.5 — Productization** | API、前端、版本治理和后续策略复用 | Deferred |

## Explicit Non-Goals

- 静态“好币名单”；
- AI 选币或 Owner 盘感二次排序；
- 综合 Fit Score、机器学习、因子平台或全市场 Research Service；
- 第一版历史全市场 Point-in-Time Universe 重建；
- 为架构纯洁性强制新增第五个systemd Worker、第二执行链或文件型生产权威；
- 原地修改 Active StrategyUniverse；
- 通过研究结果自动恢复 Crypto SOR、提高风险、杠杆、并发或资金；
- 把 Path R、MFE/MAE 或 Shadow 结果称为真实 PnL；
- 在 SOR v4 内加入 Re-entry。当前 `session_reference` 身份使同一 Symbol、Side、
  Session 的再次突破成为同一 Episode；Re-entry 必须作为新 StrategyVersion 单独研究。

## Current Next Step

**复核Generic Multi-Strategy Dynamic Selection V1详细设计**：

```text
2026-09-06-generic-multi-strategy-dynamic-selection-v1-design.md
```

冻结当前状态：

```text
STAGE3_1_REVIEW = ACCEPTED_WITH_PROVENANCE_NOTE
further_feature_research = CLOSED
generic_design_status = DESIGN_REVIEW_REQUIRED
generic_selection_design_authority = ALLOWED_FOR_ELIGIBLE_STRATEGIES
generic_selection_implementation_authority = NONE
production_dynamic_activation_authority = NONE
```

Generic设计复核通过后编写并复核Implementation Plan，再授权相应实施范围。
SOR已有DS-00至DS-10设计、Golden、实现与修复作为基线继续保留，不重新开启该研究。
生产修复进入dev，研究分支保持独立，详细设计相对dev仅产生文档差异。
