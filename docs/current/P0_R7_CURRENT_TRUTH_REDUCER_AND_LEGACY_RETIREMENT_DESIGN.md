---
title: P0_R7_CURRENT_TRUTH_REDUCER_AND_LEGACY_RETIREMENT_DESIGN
status: IMPLEMENTATION_IN_PROGRESS
authority: docs/current/P0_R7_CURRENT_TRUTH_REDUCER_AND_LEGACY_RETIREMENT_DESIGN.md
program_id: P0-ACH-R7
parent_design: docs/current/P0_MULTI_POSITION_END_TO_END_EXECUTION_CONVERGENCE_DESIGN.md
baseline_commit: 54169ca341a11c56354c9980194a53ff0d51d38b
target_state: current_truth_converged_and_legacy_runtime_paths_unreachable
schema_change_expected: false
owner_policy_change: none
exchange_write_authority: unchanged
production_deploy: out_of_scope_until_owner_confirmation
implementation_started_at: 2026-07-20
---

# P0-R7 Current Truth Reducer 与历史路径退役设计补充

## 1. 设计结论

### 1.1 核心决策

R7 采用 **共享纯函数 Current Truth Reducer + 各 Projection 薄适配器 + 单一 Incident Projector + 删除旧路径**。

目标运行形态为：

```text
one bounded PG read snapshot
-> aggregate semantic adapters
-> CurrentTruthBundle
-> Candidate / Tradeability / Daily / Goal / Ops adapters
-> one incident transition projector
-> server monitor notification
```

禁止继续使用：

```text
Candidate 自己选状态
+ Goal 自己重算 Candidate
+ Daily 自己重算 blocker
+ Monitor 自己判断生命周期事故
+ Forensics 自己维护另一套 current 状态集合
+ repair CLI 直接修改 current projection
```

R7 不新增万能业务 Aggregate，不把所有生命周期状态塞进一个数据库枚举，也不引入第二套 Current 表。共享 reducer 只统一：

1. **当前性**；
2. **终态性**；
3. **运行相关性**；
4. **阶段位置**；
5. **第一阻断**；
6. **Incident 身份与恢复**；
7. **Owner 是否需要操作**。

各 Aggregate 的合法状态转换仍由 Signal、Invocation、Ticket、Command、Lifecycle 自己负责。

### 1.2 Schema Truth Gate 结论

当前 R7 **默认不需要新 migration**。现有 schema 已能承载设计需要：

| 能力 | 现有载体 |
| --- | --- |
| Projection run 与输入 lineage | `brc_projection_runs` |
| Projection 唯一写入者 | `brc_current_projection_ownership` |
| 每 lane 当前 readiness | `brc_pretrade_readiness_rows` |
| Candidate / Daily / Goal / Tradeability current payload | `brc_control_read_model_snapshots` |
| Goal current 摘要 | `brc_goal_status_current` |
| Runtime incident | `brc_runtime_incidents` |
| Recovery run | `brc_recovery_runs` |
| Monitor run 与通知去重 | `brc_server_monitor_runs`、`brc_server_monitor_notifications` |

`bundle_run_id`、语义 fingerprint、source high-watermark 和 incident fingerprint 优先放入现有 JSONB lineage/details 或由稳定主键表达。只有真实 PostgreSQL 性能证明现有主键和索引无法满足 bounded current 查询时，才重新进入 Schema Truth Gate。

## 2. 已知客观事实

以下结论来自当前 tracked code，基线为 **`54169ca3`**。

| 事实 | 当前代码证据 | 影响 |
| --- | --- | --- |
| Candidate Pool 维护自己的 blocker/status/owner 映射 | `src/application/readmodels/strategy_live_candidate_pool.py` | 与其他消费者发生语义漂移 |
| Candidate Pool 仍包含 `_select_action_time_row()` 和 read-model `_arbitration()` | 同上 | Read model 仍在做类似选择决策，而不是只反映 PG 仲裁结果 |
| Daily Table 会再次构建 Candidate Pool | `src/application/readmodels/daily_live_enablement_table.py` | 同一 projection cadence 重复重计算 |
| Goal Status 会再次构建 Candidate Pool，并维护独立状态集合 | `src/application/readmodels/strategygroup_runtime_goal_status.py` | `first_blocker`、Owner 状态和 current 判定可能漂移 |
| Current publisher 单轮实际重复构建 Candidate 语义 | `scripts/publish_runtime_control_current_projections.py` | CPU 增加，且一致性依赖事后 validator |
| Current publisher 的 watermark 主要是 table count 与 artifact hash | 同上 | 无法直接证明所有消费者使用完全相同的 source high-watermark |
| Server Monitor 重新构建 Candidate 和 Goal，并维护独立事故状态集合 | `scripts/run_tokyo_runtime_server_monitor.py` | Monitor 可能与已发布 Current Projection 得出不同结论 |
| Forensics 独立维护 process/lifecycle 顺序和分类 | `src/application/runtime_signal_forensics.py` | 当前窗口结论可能与 Goal/Monitor 不一致 |
| Repository 维护 `OPEN_REAL_LANE_STATUSES` 和多组 `is_current_*` | `src/infrastructure/runtime_control_state_repository.py` | Current 语义仍未完全进入共享内核 |
| Refresh Sequence 仍有 `_action_time_continuation_identity()` 全局 latest Ticket/Lane/Promotion 选择 | `scripts/run_server_product_state_refresh_sequence.py` | continuation 仍可能依赖 `LIMIT 1` 隐式选择 |
| Refresh Sequence 仍保留 stdout process outcome parser | 同上 | 非 Invocation continuation 仍可进入旧协议 |
| Process outcome 仍允许 `legacy_unscoped` 写入 | `src/application/runtime_process_outcome.py` | 新生产事实仍可能缺少完整 lane identity |
| 手工 repair 工具仍能修改 core Order/Position projection | `scripts/reconcile_terminal_core_order_projection.py`、`scripts/recover_runtime_exchange_*_projection.py` | Current truth 存在正式 projector 之外的写入入口 |
| Runtime Health API 仍从进程对象、gateway 和 recovery repo 独立拼装状态，并包含 placeholder | `src/application/readmodels/runtime_health.py` | 它不是 PG Current Truth，不能继续作为 Owner 交易状态来源 |

来源：上述 tracked code、`RUNTIME_CONTROL_STATE_DB_ARCHITECTURE.md`、`RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md`。

## 3. 基于事实的架构判断

### 3.1 根因不是缺少更多状态表

当前主要问题不是数据库没有状态，而是**同一批 PG 事实被多个消费者重复解释**：

```text
PG facts
-> Candidate interpretation A
-> Daily interpretation B
-> Goal interpretation C
-> Monitor interpretation D
-> Forensics interpretation E
```

现有 parity validator 只能在结果产生后发现部分不一致，不能从结构上阻止新增消费者复制另一套状态集合。

### 3.2 R7 必须先替换语义所有权，再删除入口

直接删除 legacy runner、global Ticket、repair mutator，而不先建立共享 reducer，会产生两个风险：

1. 删除后剩余消费者仍按不同规则解释 `active`、`terminal`、`outcome_unknown` 和历史 warning；
2. 某个被删 repair 路径实际仍承担未被正式 projector 吸收的状态修复职责。

因此正确顺序是：

```text
freeze current behavior
-> establish shared semantic reduction
-> cut every current consumer to shared output
-> move required repair semantics into formal projector/reconciliation
-> prove old production reachability = 0
-> delete old code and tests
```

## 4. 方案比较

| 方案 | 架构效果 | 性能 | 维护成本 | 决策 |
| --- | --- | --- | --- | --- |
| 保留现有 builders，仅增加 parity tests | 继续多套解释 | 重复重算不变 | 状态集合继续增长 | 拒绝 |
| 新增专用 `brc_operational_current` 表 | Current 查询直接 | 读取快 | 需要 migration，并可能形成新聚合表 | 暂不采用 |
| **共享纯 reducer，现有 Current Projection 薄适配** | **一个语义内核，多个产品视图** | **单轮只 reduce 一次** | **删除重复集合和 legacy 入口** | **采用** |

## 5. Current Truth 核心模型

### 5.1 CurrentTruthBundle

R7 新增纯应用层模型 **`CurrentTruthBundle`**。它是一次 bounded PG snapshot 的确定性计算结果，不是数据库业务 Aggregate，不授予交易权限。

```text
CurrentTruthBundle
  bundle_run_id
  runtime_head
  read_now_ms
  input_watermark
  lane_decisions[]
  trade_decisions[]
  account_decision
  incident_decisions[]
  system_summary
```

必须满足：

1. 输入只来自同一个数据库 transaction/snapshot；
2. 所有时间判断使用同一个 `read_now_ms`；
3. 所有下游 projection 使用同一个 `bundle_run_id` 与 `input_watermark`；
4. reducer 无数据库写入、无网络、无文件 I/O、无 FinalGate、无 Operation Layer、无 exchange write；
5. 相同输入必须得到 byte-stable 的语义输出和 fingerprint。

### 5.2 LaneOperationalDecision

每个当前候选 lane 只产生一条 **`LaneOperationalDecision`**：

```text
lane_identity
stage_reached
runtime_semantic_state
current_object_refs
first_blocker
blocker_class
blocker_owner
next_system_action
owner_action_required
current_issue
historical_warnings[]
semantic_fingerprint
```

`current_object_refs` 必须保存最近的精确身份：

```text
signal_event_id
action_time_invocation_id
promotion_candidate_id
action_time_lane_input_id
ticket_id
operation_submit_command_id
protected_submit_attempt_id
exposure_episode_id
lifecycle_run_id
```

禁止通过 StrategyGroup、symbol、side 或“最新记录”补全缺失身份。

### 5.3 TradeOperationalDecision

每个 Ticket/ExposureEpisode 产生独立 **`TradeOperationalDecision`**：

```text
ticket_id
exposure_episode_id
netting_domain_key
phase
state
protection_state
reconciliation_state
capacity_held
first_blocker
next_system_action
owner_action_required
semantic_fingerprint
```

两个不同 instrument Ticket 必须产生两条互不覆盖的 decision。一个 Ticket 的 recovery、runner、final exit 或 release 不得改变另一条 decision。

### 5.4 Aggregate Semantic Adapters

共享内核不直接读取松散 dict。每个 Aggregate 只有一个 typed adapter：

| Aggregate | Adapter 责任 |
| --- | --- |
| Signal | fresh/current/terminal 与 immutable event identity |
| Invocation | selected/terminal/expired/rejected 与 exact Signal binding |
| Promotion | arbitration result 与 terminal disposition |
| Lane | current real-submit lane 与 exact Invocation/Promotion binding |
| Ticket | pre-submit/submitted/terminal 与 expiry |
| Exchange Command | prepared/dispatching/outcome_unknown/terminal |
| Exposure/Capacity | capacity-held/releasable 与 exact ownership |
| Lifecycle | phase/protection/reconciliation/control/terminal |
| Process Outcome | latest same-process same-lane blocking authority |
| Coverage/Facts | current/fresh/computed/satisfied/invalid |

这些 adapter 将 aggregate-specific 状态映射到现有 `RuntimeSemanticState`，但不把所有数据库 status 合并成一个全局 enum。

## 6. Current 与 Historical 的分界

### 6.1 Current Issue

满足任一条件即为当前运行问题：

1. `outcome_unknown` 尚未被权威对账解决；
2. active Ticket/ExposureEpisode 缺少保护或 reconciliation mismatch；
3. 最新 same-process + exact-lane outcome 是 blocking；
4. 当前 coverage/fact/scope/policy 无法支撑 lane；
5. 交易所仓位、挂单、容量或 NettingDomain hold 仍未释放；
6. formal recovery 尚未成功并被更新 watermark 证明。

### 6.2 Historical Warning

满足以下条件的旧错误只能进入 `historical_warnings`：

1. 对应 Signal/Invocation/Ticket/Lifecycle 已 terminal；
2. 没有 unresolved command、position、order、protection、capacity 或 incident；
3. 存在更新的同 identity 成功结果或明确 terminal closure；
4. 旧错误不再影响当前 Tradeability、Runtime Safety 或 Owner action。

禁止通过简单过滤历史行制造假健康。只要旧事件仍留下未解决机械效果，它就必须被提升成当前 Incident，而不是降级为 historical warning。

## 7. 第一阻断优先级

同一 lane 或 Ticket 存在多个问题时，Reducer 使用以下稳定优先级：

| 优先级 | 类别 | 示例 |
| ---: | --- | --- |
| 1 | **Authority / hard safety** | wrong account、scope mismatch、FinalGate/Operation Layer bypass risk |
| 2 | **Unknown external outcome** | exchange command `outcome_unknown` |
| 3 | **Active exposure safety** | unprotected position、live orphan order、reconciliation mismatch |
| 4 | **Capacity / NettingDomain** | 2/2、same-domain conflict、unresolved hold |
| 5 | **Action-Time chain** | Invocation/Ticket/fact/handoff missing or expired |
| 6 | **Observation engineering** | coverage、detector、watcher、fact mapping failure |
| 7 | **Computed market condition** | `computed_not_satisfied` |
| 8 | **Validated market wait** | `market_wait_validated` |

同优先级按以下稳定顺序：

```text
phase order
-> exact source event time
-> observed/updated time
-> stable object identity
```

数据库返回顺序不得影响 first blocker。

## 8. Owner Action 映射

`owner_action_required=true` 只允许由共享 reducer 的 typed mapping 产生。

| 状态 | Owner action | 系统行为 |
| --- | ---: | --- |
| Detector/watcher/fact/projector 工程故障 | 否 | 系统修复或恢复 |
| 可重试 protection/runner/reconciliation | 否 | 正式 recovery 自动处理 |
| `outcome_unknown` | 通常否 | 系统先对账并保持 fail-closed |
| Owner policy/capital/profile/scope 缺失 | 是 | 请求一个明确政策决定 |
| 自动恢复耗尽且需要暂停/风险调整 | 是 | 显示 `需要介入` |
| 已完成或健康等待机会 | 否 | 安静运行 |

下游 Candidate、Goal、Ops、Monitor 不得再自行根据字符串后缀、label 或本地集合推断 Owner action。

## 9. Incident 与恢复模型

### 9.1 Incident Fingerprint

Incident 使用稳定语义 fingerprint，不使用 watcher tick、projection run 或通知发送时间：

```text
scope_kind
+ scope_identity
+ phase
+ blocker_family
+ authority_object_ref
```

示例：

```text
ticket|ticket-123|protected|protection_missing|exposure-456
lane|lane-key|selection|action_time_ticket_missing|invocation-789
system|tokyo-runtime|observation|watcher_service_failed|brc-runtime-signal-watcher.service
```

`incident_fingerprint` 写入现有 `details` JSONB；`incident_id` 使用
`fingerprint + episode_opening_source_watermark` 的 hash。重复 tick 更新同一 open
episode 的 details/last evidence，不创建通知风暴；已经关闭后再次发生时，以新的
opening watermark 创建新的 incident episode，从而允许新的通知和独立恢复。

### 9.2 Recovery Rule

只有以下条件同时满足才关闭 incident：

1. 同一 scope/authority identity 出现更新的成功事实；
2. 成功事实 watermark 晚于 incident opening watermark；
3. mechanical effect 已清除；
4. reducer 不再产生同一 fingerprint；
5. recovery transition exactly once。

“服务重新启动”“下一轮没查到错误”“signal 过期”均不是 recovery 证明。

### 9.3 Notification Rule

Server Monitor 只消费 reducer/projector 产生的 incident decision：

```text
incident opened/materially worsened -> notify
same fingerprint unchanged -> suppress
incident recovered -> one recovery notification when policy allows
historical warning only -> quiet
```

Monitor 不再重新解释 lifecycle status、process outcome 或 Candidate blocker。

## 10. Current Projection 唯一写入者矩阵

| Current Surface | 唯一语义来源 | Sole writer | 禁止路径 |
| --- | --- | --- | --- |
| Per-lane readiness | `CurrentTruthBundle.lane_decisions` | `pg_candidate_pool_projector` | Candidate builder 重算 first blocker |
| Candidate Pool snapshot | 同上 | `pg_candidate_pool_projector` | readmodel 自行仲裁 action-time row |
| Tradeability Decision | 同上 | `pg_tradeability_projector` | 独立重建 Candidate Pool |
| Daily Table | 同上 | `pg_daily_table_projector` | 独立 market-wait checklist 与 blocker priority |
| Goal Status | lane + trade + account decisions | `pg_goal_status_projector` | 独立 status tuple、latest Ticket 推断 |
| Runtime Safety State | exact Ticket-bound safety facts | `pg_runtime_safety_projector` | Current reducer 升级 submit authority |
| Lifecycle Current | exact Ticket/Exposure lifecycle | ticket-bound lifecycle reducer | repair CLI 直接改 current lifecycle |
| Runtime Incident Current | reducer incident decisions | `pg_operational_incident_projector` | Monitor/Goal 各自开关 incident |
| Server Monitor Current | Current bundle + incidents + systemd | `pg_server_monitor_projector` | 重建 Candidate/Goal/lifecycle blocker |
| Owner Notification Current | incident transition | server monitor notification projector | watcher 或 lifecycle 直接发 Owner 通知 |

同一个 OS 进程可以调用多个 sole-writer service；“唯一写入者”指唯一代码责任与语义算法，不是必须只有一个物理进程。

## 11. Projection Bundle 与 Watermark

### 11.1 Bundle Run

一次 projection refresh 生成一个共同 **`bundle_run_id`**：

```text
current_bundle:<read_now_ms>:<source_digest>
```

各 `brc_projection_runs.projection_run_id` 保持唯一：

```text
<bundle_run_id>:candidate_pool
<bundle_run_id>:tradeability_decision
<bundle_run_id>:daily_live_enablement_table
<bundle_run_id>:goal_status
```

共同 `bundle_run_id` 写入现有 `input_watermark` JSONB，不新增列。

### 11.2 Exact Input Watermark

Watermark 不再只保存 table count。至少包含：

```text
runtime_head
read_now_ms
candidate_scope max(updated_at/id)
coverage max(last_tick_at/id)
facts max(observed_at/id)
signal max(created_at/id)
invocation max(updated_at/id)
promotion/lane/ticket max(updated_at/id)
command/lifecycle/incident max(updated_at/id)
account exposure/budget source watermark
```

所有 current projection payload 必须引用同一 watermark digest。

## 12. Read Model 行为调整

### 12.1 Candidate Pool

Candidate Pool 只做产品形状映射：

```text
LaneOperationalDecision -> Candidate row
```

必须删除：

- `_select_action_time_row()` 的业务选择职责；
- read-model `_arbitration()`；
- 通过 StrategyGroup priority 人工选择 action-time winner；
- 本地 first blocker 和 blocker owner 决策集合。

Promotion/Lane 必须完全反映 PG Action-Time arbitration 结果。

### 12.2 Tradeability、Daily 与 Goal

三个 surface 不再调用 Candidate builder。它们接收同一个 `CurrentTruthBundle`：

- Tradeability：每 StrategyGroup 聚合 lane decisions；
- Daily：每 StrategyGroup 选择最接近 action-time 的展示 lane；
- Goal：聚合当前 active trade、incident 和 lane chain position；
- 展示排序可以不同，但 first blocker、owner、next action 不能不同。

### 12.3 Runtime Health 与 Ops

现有 `RuntimeHealthReadModel` 的进程/gateway 健康事实可以保留为 **Machine Health 输入**，但其交易状态判断逻辑必须删除。`signal_pipeline=PASSED` placeholder 必须删除。

最终 Runtime Health 为：

```text
CurrentTruthBundle system summary
+ machine health facts
+ current incidents
```

Machine Health 不得把健康进程推导成 `market_wait_validated` 或 live-submit readiness。

### 12.4 Forensics

Forensics 保留历史 lineage 查询，但使用同一 semantic adapters：

1. current-window 查询优先引用当前 incident/current decisions；
2. historical query 从 append-only lineage 重放；
3. `_first()` 依赖输入顺序的 lineage 选择被禁止；
4. exact ID、typed lane identity 和稳定时间排序共同决定对象；
5. historical warning 不得覆盖当前 unresolved incident。

## 13. Action-Time Continuation 收敛

### 13.1 目标

R7 删除 `_action_time_continuation_identity()` 的全局 latest Ticket/Lane/Promotion 选择职责。

唯一合法 continuation 来源：

```text
selected ActionTimeInvocation
-> exact lane
-> exact Ticket
```

规则：

1. 0 个 continuation：进入 bounded Signal arbitration；
2. 1 个 continuation：typed coordinator 以 exact Invocation/Ticket 继续；
3. 多于 1 个 current real-submit continuation：hard safety incident，禁止任选一条；
4. Promotion 没有 selected Invocation 不得作为 continuation identity；
5. production path 禁止 `legacy_unscoped` process outcome；
6. subprocess/stdout parser 仅在测试替换完成前存在，R7 完成前删除。

## 14. Repair Mutator 正式化与删除

### 14.1 Terminal Core Order Projection

`project_terminal_ticket_bound_orders_to_core()` 的有效语义迁入正式 lifecycle finalizer/reconciliation transaction：

```text
terminal protection truth
+ flat position truth
+ exact local/exchange order identity
-> core order terminal projection
-> audit event
```

完成后删除 `scripts/reconcile_terminal_core_order_projection.py`，不保留 apply CLI。

### 14.2 Submit/Close Projection Recovery

`runtime_exchange_submit_projection_recovery` 与 `runtime_exchange_close_projection_recovery` 的有效逻辑迁入正式 reconciliation service：

```text
durable command / ticket identity
-> read-only exchange truth
-> deterministic projection reconcile
-> incident transition
```

迁移后删除：

- `scripts/recover_runtime_exchange_submit_projection.py`；
- `scripts/recover_runtime_exchange_close_projection.py`；
- 仅服务于上述 CLI 的 application/domain recovery 类型；
- 对应 legacy tests。

历史执行记录保留在 PG audit 和 git history，不保留 current repair 入口。

## 15. Legacy Exit Policy 边界

新 Ticket 必须 version-bound。`legacy_unbound` 只允许：

1. 历史 terminal Ticket 的只读解释；
2. archive/forensics；
3. migration compatibility test。

生产 Runner、Finalizer、Current Reducer 和新 Ticket path 不得接受 `legacy_unbound`。若部署前存在 active `legacy_unbound` Ticket，R7 停止并转入 exact lifecycle resolution，不允许通过 fallback 继续。

## 16. 性能与运行成本

| Surface | Cadence | 目标成本 |
| --- | --- | --- |
| Watcher current publish | 每 **3 分钟** watcher tick 后 | 读取 bounded current rows；reduce 一次；publish p95 ≤ 3s、p99 ≤ 6s |
| Action-Time refresh | material change 时 | 共用 30s global deadline；reducer 不做网络 I/O |
| Lifecycle maintenance | 每 **30 秒** | 仅 semantic fingerprint 变化时触发 current/incident publish |
| Server Monitor | 每 **10 分钟** | 读取 current bundle/incident + systemd；不重建 Candidate/Goal |
| Forensics | manual/read-only | limit ≤ 1000；允许历史查询但禁止进入生产 cadence |

硬约束：

1. no-signal tick 创建 **0 个 JSON/MD 文件**；
2. Current publisher 不再全表 delete + insert 所有 readiness rows；它对规范化 row 计算 semantic fingerprint，以现有 `source_watermark` 保存 `bundle_digest:row_digest`，只 upsert changed rows，并 bounded 删除已退出 active scope 的 current projection row；
3. 每轮 PG 写入上限为当前 **22 lane** 的变化行、4 个 current snapshots、1 个 Goal row 和 material incident transitions；
4. 无变化 lifecycle tick 不写新的 business/current rows；
5. Monitor 不运行重型 builders；
6. 所有 PG/API/subprocess 操作保持 timeout-bounded；R7 目标生产 path 删除 subprocess business protocol。

## 17. 故障与回滚

### 17.1 Reducer 失败

Reducer 失败时：

- 不覆盖上一条成功 Current bundle；
- lane-bound reducer/publisher failure 写 typed process outcome；system/global projection failure 写 `brc_runtime_incidents` 或 `brc_server_monitor_runs`，不新增 `legacy_unscoped` process outcome；
- Monitor 显示 `temporarily_unavailable` 或 `monitor_refresh_needed`；
- 不把失败解释为 market wait；
- 不授予 submit authority。

### 17.2 Cutover 回滚

在旧路径删除前，可 code-revert 到前一切片。旧路径删除并激活新 writer 后，只允许 forward-fix，禁止恢复：

- read-model arbitration；
- global latest continuation；
- stdout business protocol；
- repair apply CLI；
- multiple current writers。

任何回滚不得影响已有仓位的 protection/reconciliation。必要时关闭 new entry，生命周期服务继续运行。

## 18. 完成定义

R7 只有同时满足以下条件才完成：

1. 同一 PG snapshot 在 Candidate、Tradeability、Daily、Goal、Ops、Monitor 和 current-window Forensics 中得到相同 first blocker；
2. 所有 current surface 引用同一 `bundle_run_id` 和 source watermark digest；
3. `outcome_unknown`、缺保护和未解决 hold 始终 current 且占用容量；
4. terminal historical warning 不再触发 current blocker 或 Owner action；
5. recovery 只发生一次，且必须由更新成功 watermark 证明；
6. 两个不同 instrument Ticket 各自拥有独立 current decision 与 incident scope；
7. Candidate/Goal/Monitor 不再自行维护 duplicate terminal/active/owner-action 集合；
8. readmodel 不再选择 promotion/action-time winner；
9. production Action-Time continuation 不再使用 global latest 或 stdout protocol；
10. repair mutator 的有效语义进入正式 lifecycle/reconciliation，旧 CLI production reachability 为 0；
11. 新 Ticket production path 对 `legacy_unbound` reachability 为 0；
12. file-I/O audit `performance_risk.status=clear`、`frequent_report_write=0`；
13. PostgreSQL consumer parity、incident recovery、notification dedupe 和 performance tests 全部通过；
14. 没有 FinalGate、Operation Layer、exchange write、策略参数、风险预算、profile 或 sizing authority 变化。

## 19. Chain Position

```text
chain_position: action_time_boundary
strategy_group_id: five active StrategyGroups
symbol: 22 active candidate lanes
stage: r7_current_truth_reducer_design_complete
first_blocker: current_semantics_are_recomputed_by_multiple_consumers_and_legacy_continuation_repair_paths_remain_reachable
evidence: tracked code at 54169ca3; Candidate/Daily/Goal/Monitor/Forensics maintain separate current interpretations, while refresh continuation and repair CLIs remain present
next_action: after Owner implementation confirmation, execute P0-MP-R7-0 reachability freeze, then build the shared CurrentTruthBundle reducer before deleting any path
stop_condition: all current consumers share one bundle/watermark, old paths have zero production reachability, and PostgreSQL parity/recovery/performance certification passes
owner_action_required: true_for_r7_implementation_confirmation_only
signal_event_id: none_design_stage
promotion_candidate_id: none_design_stage
action_time_lane_input_id: none_design_stage
ticket_id: none_design_stage
authority_boundary: design only; no production deployment, migration apply, FinalGate or Operation Layer bypass, exchange write, policy/profile/sizing change, or destructive production cleanup
```
