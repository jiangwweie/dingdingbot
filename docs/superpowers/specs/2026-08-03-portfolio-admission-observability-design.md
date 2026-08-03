# Portfolio Admission Observability 合并修复设计

> 日期：2026-08-03
> 状态：APPROVED_FOR_IMPLEMENTATION
> 适用范围：Tokyo Trading Kernel，当前 `0002_sor_v3_strategy_group_capacity` 之后的前向版本

## 1. 决策

本轮形成一个合并发布候选，统一解决四个相互依赖的 P1：

1. **Episode Identity / Re-arm**：连续成立的同一策略结构只拥有一个 Exposure Episode；只有明确重新武装后才允许产生下一 Episode。
2. **AdmissionDecision / Shadow Outcome**：每个最终获得或失去准入资格的 Signal 都有不可变准入证据；被组合约束拒绝的有效机会获得只读固定窗口结果。
3. **Policy v4**：采用单 Ticket `2%`、账户总止损风险 `6%`、最多 `3` 个 Ticket，以及 `50%` 最小有效仓位比例。
4. **Exposure Family / Directional Risk**：策略族和方向风险成为 Capacity admission 的版本化 Policy 语义。

本轮同时包含已经完成但尚未部署的：

- P0 Reconciliation certification contradiction 隔离修复；
- 过期 `candidate_ready` Readiness 投影收敛修复。

最终只形成一个新的精确 Release Commit。旧提交 `8462fe37cc9498dce3e68ea806d4a626688ca25b` 不再作为独立部署目标。

## 2. 已知客观事实

### 2.1 当前 Signal Identity

当前 Signal producer 在没有 `identity_reference` Fact 时使用 `occurred_at_ms` 构造 Episode。CPM、MPG、MI、BRF2 没有 identity Fact，因此连续小时触发会成为不同 Episode。SOR v3 使用 Session 起点作为 identity Fact，同一 Session recross 已经保持一个 Episode。

### 2.2 当前 Arbitration

当前候选稳定排序为：

```text
Owner Policy priority
-> occurred_at_ms
-> observed_at_ms
-> signal_event_id
```

所有现有 StrategyGroup 使用相同 Owner priority。到达顺序因此能够决定真实资金样本。

### 2.3 当前 Capacity

当前 Policy 为：

```text
max_concurrent_tickets = 3
max_strategy_group_concurrent_tickets = 2
max_ticket_stop_risk_fraction = 0.03
max_gross_stop_risk_fraction = 0.06
max_ticket_initial_margin_fraction = 0.45
max_gross_initial_margin_utilization = 0.90
```

这允许前两个 Ticket 接近各使用 3% 风险，第三个 Ticket 只能得到剩余预算。

### 2.4 当前架构硬边界

```text
Observation
-> StrategySignal
-> Readiness/Authority
-> CapacityClaim
-> immutable Ticket
-> durable Exchange Command
-> protected lifecycle
-> reconciliation
-> settlement
-> review
```

- 一个 Exposure Episode 最多拥有一个 Ticket；
- 新 ENTRY 全局串行；
- 一个 Netting Domain 最多一个 Active Ticket；
- Strategy 逻辑止于 StrategySignal；
- 交易所网络写入只能来自 durable Exchange Command；
- Schema 只能在全平、停止、前向、保存历史的条件下升级。

## 3. 方案比较

### 3.1 Episode Identity

| 方案 | 优点 | 缺点 | 决策 |
|---|---|---|---|
| 直接使用保护参考价作为 Episode ID | 改动小 | 滚动窗口会移动参考价；同一结构仍可能被拆成多个 Episode | 拒绝 |
| 固定时间桶 | 简单、确定 | 时间桶不是策略结构，桶边界会人为创造或合并机会 | 拒绝 |
| **Rising-Edge Episode Projection** | 连续 true 保持同一 Episode；false 后再次 true 才产生新 Episode；Live/Replay 可一致 | 需要一个 PostgreSQL current projection | **采用** |

### 3.2 Shadow Outcome

| 方案 | 优点 | 缺点 | 决策 |
|---|---|---|---|
| 创建 shadow Ticket 并模拟完整 Lifecycle | 看似接近真实交易 | 污染 Ticket/Command 权威，容易被误读为真实持仓 | 拒绝 |
| 完整反事实成交、手续费、资金费和 Runner 模拟 | 信息丰富 | 假设过多，首版复杂度和误导风险高 | 拒绝 |
| **固定窗口 MFE/MAE Observation** | 只读、可复现、能比较被拒绝机会质量 | 不代表完整策略净收益 | **采用** |

### 3.3 Policy 与组合限制

| 方案 | 单 Ticket 风险 | 总风险 | 并发 | 判断 |
|---|---:|---:|---:|---|
| 保留 3% / 6% / 3 | 3% | 6% | 3 | 保留残余小仓位问题 |
| 3% / 9% / 3 | 3% | 9% | 3 | 扩大资本风险，拒绝 |
| **2% / 6% / 3** | **2%** | **6%** | **3** | 不扩大总风险并改善三槽位统计意义，采用 |

## 4. Episode Identity 与 Re-arm

### 4.1 Registry 所有权

`RegisteredStrategyContract` 新增：

```text
episode_policy: "rising_edge" | "session_reference"
exposure_family: ExposureFamily
shadow_horizon_bars: positive int
```

策略语义如下：

| Event | 新版本 | Episode Policy | Re-arm 条件 | Exposure Family | Shadow 窗口 |
|---|---|---|---|---|---:|
| CPM-LONG | v3 | rising_edge | 一个有效闭合 1h Observation 为 NOT_TRIGGERED 后，后续首次 TRIGGERED | long_continuation | 24 根 1h |
| MPG-LONG | v3 | rising_edge | 同上 | long_continuation | 24 根 1h |
| MI-LONG | v3 | rising_edge | 同上 | long_continuation | 24 根 1h |
| BRF2-SHORT | v3 | rising_edge | 同上 | rally_failure_short | 24 根 1h |
| SOR-LONG | v4 | session_reference | 新 Session 的 `session_start_ms_v3` | opening_range | 到冻结 Session 结束 |
| SOR-SHORT | v4 | session_reference | 新 Session 的 `session_start_ms_v3` | opening_range | 到冻结 Session 结束 |

无效 Observation、市场超时、Registry 不一致和 Warming 不得重新武装 Episode。

### 4.2 Current Projection

新增 `brc_exposure_episode_current`：

```text
episode_domain_key PK
event_spec_id
exchange_instrument_id
position_side
episode_policy
state = armed | triggered
exposure_episode_id nullable
triggered_at_ms nullable
rearmed_at_ms nullable
last_observed_at_ms
projection_version
```

`episode_domain_key` 由 `event_spec_id + exchange_instrument_id + position_side` 构造。Universe replacement 不重置同一 Event 版本的连续 Episode；Strategy/Event 版本变化天然形成新的 domain。

### 4.3 原子状态转换

在 Observation 已完成网络读取和纯 detector 计算后，用一个短事务完成：

```text
lock exact Episode projection
-> upsert current Facts
-> apply NOT_TRIGGERED/TRIGGERED transition
-> optional append StrategySignal
-> update Readiness
-> commit
```

规则：

1. `armed + TRIGGERED`：创建新 Episode ID，状态变为 `triggered`；
2. `triggered + TRIGGERED`：复用当前 Episode ID，Signal identity 因 Episode 相同而去重；
3. `triggered + NOT_TRIGGERED`：状态变为 `armed`，清空当前 Episode ID；
4. `armed + NOT_TRIGGERED`：保持 `armed`；
5. `session_reference`：继续使用 identity Fact，不依赖 rising-edge projection。

## 5. AdmissionDecision

### 5.1 定义

新增 frozen `AdmissionDecision`，它是一个 Signal 的最终准入证据，不是 CapacityClaim、Ticket 或 Review。

稳定结果：

```text
admitted
rejected
```

每个 `signal_event_id` 最多一条最终 AdmissionDecision。

### 5.2 必须冻结的证据

```text
admission_decision_id
signal_event_id / exposure_episode_id
strategy_group_id / strategy_version_id / event_spec_id
universe_version_id / universe_semantic_digest
runtime_profile_id / runtime_scope_id / runtime_scope_version
owner_policy_id / owner_policy_version
venue_id / account_id / instrument / side
exposure_family
candidate_rank / candidate_count / candidate_set_digest
candidate_set_summary
active Ticket / Family / direction usage
remaining slot / gross risk / directional risk / margin
decision_status
first_blocker
binding_constraint
capacity_claim_id nullable
ticket_id nullable
entry_admission_snapshot_digest nullable
decision_digest
decided_at_ms
```

候选集合最多 64 条，摘要使用稳定排序后的必要 identity，不保存无界历史或行情数据。

### 5.3 事务规则

- admitted Decision 必须和 CapacityClaim、Ticket、Reservation、Netting Domain hold、Aggregate、TicketIssued Event、ENTRY Command 在同一 PostgreSQL 事务提交；
- rejected Decision 必须和 Readiness terminal blocker 在同一事务提交；
- Decision 冲突、重复或持久化失败时整个事务失败；
- rejected Decision 永远不创建 Exchange Command；
- action facts 在网络读取前失败时，记录 `observation_unavailable` Decision，但不创建 Shadow Outcome。

## 6. Shadow Outcome

### 6.1 语义边界

首版名称固定为：

```text
fixed_horizon_excursion_v1
```

它只回答：以准入时冻结的参考入场价和 Initial Stop 距离为 1R，在固定闭合 K 线窗口内，市场最大有利和最大不利价格移动是多少。

它不表示：

- 实际成交；
- 可实现净利润；
- 手续费、Funding 或滑点后的结果；
- TP1、Break-Even、Runner 的完整反事实 Lifecycle；
- 应当人工替换真实仓位。

### 6.2 创建条件

只有同时满足以下条件的 rejected Decision 创建 pending Shadow Outcome：

1. Signal、Policy、Scope 和 instrument rules 有效；
2. action-time admission snapshot 有效；
3. 参考 entry 和 stop 可以确定；
4. first blocker 属于组合/容量约束：
   - `budget_exhausted`；
   - `exposure_family_capacity_exhausted`；
   - `directional_risk_exhausted`；
   - `active_netting_domain`；
5. 没有 Ticket 或 Exchange Command。

### 6.3 数据模型

新增 `brc_shadow_outcomes_current`：

```text
shadow_outcome_id PK
admission_decision_id UNIQUE
status = pending | claimed | completed | unavailable
evaluation_kind
exchange_instrument_id
position_side
timeframe
entry_reference_price
initial_stop_price
initial_risk_per_unit
horizon_start_ms
horizon_end_ms
claim_owner nullable
lease_until_ms nullable
max_favorable_price nullable
max_adverse_price nullable
mfe_r nullable
mae_r nullable
observed_through_ms nullable
completion_reason nullable
projection_version
created_at_ms / completed_at_ms nullable
```

### 6.4 Runtime 所有权

**Observation Worker** 拥有 Shadow Outcome cadence，因为它已经拥有 public closed-market source。

每次 tick：

1. 优先处理正常 due Strategy Scope；
2. 没有正常 Observation work 时，最多 claim 一个到期 Shadow Outcome；
3. 网络读取在事务外；
4. 最多读取 24 根 1h 或 96 根 15m 闭合 K 线；
5. 用短事务完成 terminal projection；
6. 失败释放为可重试状态或在不可恢复的 identity/data 问题下标记 unavailable。

正常 Strategy Observation 永远优先，Shadow 不得造成信号采集饥饿。

## 7. Policy v4 与 Exposure Family

### 7.1 Policy v4

```text
max_concurrent_tickets = 3
max_ticket_stop_risk_fraction = 0.02
max_gross_stop_risk_fraction = 0.06
max_ticket_initial_margin_fraction = 0.30
max_gross_initial_margin_utilization = 0.90
min_materialization_ratio = 0.50
directional_stop_risk_limit_fraction = 0.04
max_leverage = 10
supported_margin_mode = cross
```

固定 exchange leverage 继续为 `5x`，本轮不产生 leverage mutation。

### 7.2 Family limits

```text
long_continuation = 1
opening_range = 2
rally_failure_short = 1
```

Family mapping 属于 Registry Event；Family limit 属于 Owner Policy。不得通过 symbol、side 或 StrategyGroup 字符串在 Entry Worker 中临时猜测。

### 7.3 Capacity 顺序

Capacity admission 的第一拒绝原因按以下顺序稳定：

1. Signal / Scope / Policy / action facts；
2. account mode 与 runtime incident；
3. Netting Domain；
4. account concurrent Ticket ceiling；
5. Exposure Family ceiling；
6. directional stop-risk ceiling；
7. instrument / protection / liquidation stress；
8. gross risk 和 margin；
9. minimum materialization；
10. CapacityClaim freeze。

`minimum materialization` 的计算为：

```text
minimum_stop_risk_budget
= wallet_balance
* max_ticket_stop_risk_fraction
* min_materialization_ratio
```

最终可用 planned stop-risk budget 小于该值时：

```text
first_blocker = budget_exhausted
binding_constraint = minimum_materialization_ratio
```

### 7.4 冻结 lineage

CapacityClaim 和 Ticket 新增：

```text
exposure_family
active_family_ticket_count_at_claim
family_ticket_limit
directional_risk_at_stop_at_claim
directional_stop_risk_limit_fraction
min_materialization_ratio
minimum_stop_risk_budget
```

历史 Ticket 通过 EventSpec 的确定映射回填 Family；历史风险和 Policy 数值不重写。

## 8. Schema 与迁移

新 head：

```text
0001_trading_kernel_baseline_v4
-> 0002_sor_v3_strategy_group_capacity
-> 0003_portfolio_admission_observability
```

`0003` 必须：

1. 新增 Episode、AdmissionDecision、Shadow Outcome 表；
2. 扩展 EventSpec、Owner Policy、CapacityClaim 和 Ticket；
3. 以确定映射回填所有历史 Event/Ticket Family；
4. 安装 CPM/MPG/MI/BRF2 v3 与 SOR v4 Registry/ExitPolicy rows，保留现有非 SOR v2 和 SOR v3 历史；
5. 将 Policy 单调升级到 v4，并保持 `new_entry_submit_enabled=false`；
6. 不重写历史 Signal、Episode、Claim、Ticket、Command、Settlement 或 Review；
7. 从 source `0002` 计算保存清单，升级后逐列验证 source 数据完全一致；
8. 禁止 downgrade、dual write、old-schema reader 和 schema fallback。

新版本 Active Universe bootstrap 在安全 workers 启动后进行，Entry 继续 fenced。现有非 SOR v2 与 SOR v3 Universe 退役，新 v3/v4 Universe 激活后才能通过 Promotion。

## 9. 部署与恢复

### 9.1 部署前硬门禁

- 零 Active Ticket；
- 内部与交易所零非平 Position；
- 零 open/residual order；
- 零 Active Budget Reservation 和 Netting Domain；
- 零 unresolved Exchange Command；
- 零 open Incident；
- 所有终态 Ticket 的 Settlement 和 Review 完成；
- Entry stopped、disabled 且 write fence 存在。

### 9.2 部署步骤

```text
certify exact 0002 source
-> stop all old workers
-> recheck flatness
-> compute 0002 preservation manifest
-> upgrade to exact 0003
-> verify preservation manifest
-> install Registry vNext and Policy v4 with ENTRY disabled
-> rotate exact runtime identity
-> start Observation/Lifecycle/Reconciliation
-> bootstrap and activate exact six Universes
-> readonly postflight
-> keep Entry stopped/disabled and write-fenced
```

部署命令不得传 `--enable-entry`。

### 9.3 失败姿态

- 在切换 Schema 前失败：保持旧版本和 Entry fence；
- 在 `0003` 迁移后失败：保持 Entry fenced，使用目标版本 fix-forward；
- 不允许把 `0002` worker 重启到 `0003`；
- 不允许 Schema downgrade；
- Shadow projector 失败不影响 Lifecycle/Reconciliation safety work。

## 10. 性能边界

| 项目 | 上限 |
|---|---:|
| Arbitration candidates | 64 |
| Active Tickets queried for Family/direction | 3 |
| Shadow jobs claimed per idle Observation tick | 1 |
| 1h Shadow candles | 24 |
| 15m Shadow candles | 96 |
| Runtime JSON/Markdown files | 0 |

所有运行查询使用 exact key 或 bounded actionable selector，禁止全历史扫描。

## 11. 明确不在本轮范围

- Funding 归属修复；
- Incident 质量归并；
- Regime 自动调权；
- 基于历史收益的动态策略评分；
- 自动平仓轮动或替换已持仓 Ticket；
- 资本、杠杆、instrument 或市场范围扩大；
- CPM 或其他 StrategyGroup 扩张。

## 12. 完成定义

本轮工程完成需要同时满足：

1. Episode rising-edge 与 SOR Session identity 的 Live/Replay 测试通过；
2. 每个 admitted/rejected Signal 有唯一、不可变 AdmissionDecision；
3. Shadow Outcome 只读、bounded、不会创建交易权威；
4. 2% / 6% / 3、Family、direction 和 minimum materialization 都有纯 domain 与 PostgreSQL 证据；
5. 昨夜时序 Replay 得到预期三槽位结果；
6. `0002 -> 0003` 空库、生产形状保存迁移和拒绝 downgrade 通过；
7. 全量 pytest、Ruff、Mypy、architecture audit、runtime file-I/O audit 和 `git diff --check` 通过；
8. 形成新的精确 Release Commit；
9. 自动部署监控只允许部署该新 Commit，且部署后 Entry 仍关闭。
