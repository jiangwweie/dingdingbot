---
title: P0_ACTION_TIME_INVOCATION_CLAIM_AND_RUNTIME_HEALTH_CONVERGENCE_IMPLEMENTATION_PLAN
status: PROPOSED_IMPLEMENTATION_CONFIRMATION_REQUIRED
authority: docs/current/P0_ACTION_TIME_INVOCATION_CLAIM_AND_RUNTIME_HEALTH_CONVERGENCE_IMPLEMENTATION_PLAN.md
implements: docs/current/P0_ACTION_TIME_INVOCATION_CLAIM_AND_RUNTIME_HEALTH_CONVERGENCE_DESIGN.md
last_verified: 2026-07-20
program_id: P0-ACH
program_name: Schema Truth、Action-Time 与双仓位实盘前置收敛
target_state: multi_position_pre_live_certified
baseline_branch: codex/budget-model-review-20260714
baseline_head: 386cc3d761f17231a6c35d2bc96b347153cbd907
production_head: 386cc3d761f17231a6c35d2bc96b347153cbd907
production_migration_head: 140
planned_migration_set: 141_schema_truth_capability_bundle_candidate_pending_postgresql_certification
owner_policy_change: none
exchange_write_authority: unchanged
real_multi_position_calibration: out_of_scope
---

# P0 Schema Truth、Action-Time 与双仓位实盘前置收敛执行计划

## 1. 执行目标

**本计划把当前系统推进到 `multi_position_pre_live_certified`：代码、Schema、真实 PostgreSQL、并发、恢复、性能和东京 no-exchange-write canary 全部通过，下一步只剩自然信号下的真实多仓位校准。**

本计划解决的是同一问题类，而不是继续分别修补：

- persisted Decimal 与 PG roundtrip；
- 同 tick 多信号丢失；
- Invocation/Process Outcome 悬空；
- occupancy、核心 Order 和 ticket-bound truth 分裂；
- detector current 与 Signal 非原子；
- Candidate/Goal/Monitor/Ops/Forensics 状态漂移；
- Alembic/ORM 双 Schema Authority；
- migration/test/head/restore 基线不可信；
- 双仓位 Claim、保护、runner、release 和 recovery 尚未 whole-chain 认证。

本计划不以“测试绿但生产 schema 不同”、强制 Signal、强制下单、降低风险参数、手工 SQL 或新增兼容 authority 作为完成。

## 2. 当前基线、Before 与 After

### 2.1 当前基线

截至 **2026-07-20 11:44（上海时间）**：

| 项目 | 当前事实 |
| --- | --- |
| **Branch / production head** | `codex/budget-model-review-20260714` / `386cc3d7` |
| **Migration** | `140`，单 root、单 head |
| **Services** | Backend、Watcher、Monitor、Lifecycle timer active |
| **Coverage** | 5 StrategyGroup / 22 current lane / missing coverage 0 |
| **Account state** | 2/2 position slots occupied |
| **Signal window** | 67 Signal / 32 Invocation / 3 Promotion / 3 Lane / 3 Ticket |
| **Submit/lifecycle/outcome** | 1 protected submit attempt / 1 lifecycle run / 0 new live outcome |
| **主要工程缺口** | 35 Invocation missing、24 process outcome missing、2 Ticket expired、1 local Order registration DBAPIError |
| **Migration governance** | Alembic metadata 0 tables、PGCoreBase 96 tables、runtime `create_all()`、head test 136 != 140 |

### 2.2 Live Enablement State Before

```text
chain_position: action_time_boundary
stage: late integration and production hardening
state: single vertical slice exists; multi-signal, dual-position, schema truth, recovery and current projection consistency are not certified
real_submit: existing policy path remains present, but this Program does not use exchange write as an engineering proof
owner_action_required: implementation confirmation only
```

### 2.3 Live Enablement State After

```text
chain_position: action_time_boundary
stage: multi_position_pre_live_certified
state: every signal has an explicit result; Alembic is sole schema owner; 0/1/2 position capacity and release are certified; all projections agree; Tokyo no-write canary passes
real_submit: technically prepared inside existing policy and official gates; natural live calibration remains R1B
owner_action_required: only the later production-calibration decision
```

## 3. Global Authority Model

```text
Owner controls policy.
System executes process.
Tradeability Decision answers can-trade.
Runtime Safety State answers live-submit safety.
Review updates strategy governance.
```

所有 Task 均不得：

- 改变 StrategyGroup、symbol、side、runtime profile、account、notional、leverage、planned risk 或 position cap；
- 绕过 FinalGate、Operation Layer、protection、reconciliation、settlement 或 review；
- 在 unknown exchange outcome、duplicate submit、missing protection 或 identity mismatch 下继续；
- 新增第二 schema、detector-current、notification、order、lifecycle 或 health authority；
- 新增生产 JSON/Markdown/YAML/JSONL current authority；
- forced signal/order、withdrawal、transfer、credential/secret mutation；
- squash、重写或删除 migration `001–140`；
- 用手工 SQL 或 migration 猜测业务终态。

## 4. 执行序列与依赖

| 顺序 | Task | 依赖 | 主要成果 |
| ---: | --- | --- | --- |
| **T00** | Baseline And RED Evidence Freeze | 无 | 冻结生产、Migration、测试和文档漂移 |
| **T01** | Schema Truth Gate | T00 | 决定下一 migration 是否必要及最小 capability bundle |
| **T02** | Single Schema Authority | T01 | Alembic 唯一生产 schema owner，runtime 不建表 |
| **T03** | Runtime Semantic Kernel | T00-T02 | phase/state/terminal/reason/current relevance 统一 |
| **T07** | Detector Current And Projection Ownership | T01-T03 | 先冻结 Signal producer/writer interface；每 lane/candle 一次 decision |
| **T04** | Persisted Decimal And Claim | T01-T03 | canonical hash、INSERT、reload、FinalGate 一致 |
| **T05A** | Signal Intake And Invocation Conservation | T03 + T07 writer interface | 每 Signal 先有 Invocation/process outcome，不触发 private facts/Claim/Ticket |
| **T05B** | Deterministic Arbitration And Winner Claim | T04 + T05A | 同 domain 至多一个 winner，所有 loser 明确终态 |
| **T05C** | Typed Coordinator And Global Deadline Cutover | T05B | typed command/result、逐步剩余预算、旧 stdout/global path 不可达 |
| **T06** | Multi-Position Occupancy And Core Order Convergence | T03 + T05C | 统一 occupancy、独立 Ticket/lifecycle、exact release |
| **T08** | Readmodels、Ops、Forensics And Notification | T05C + T06 + T07 | 所有产品/工程视图共用 Kernel |
| **T09** | Runtime Lifecycle、Legacy Retirement And Retention | T06-T08 | 旧 authority 退出、增长和噪声受控 |
| **T10** | Dual-Position Pre-Live Matrix | T04-T09 | 0→1、1→2、2/2、冲突、runner、release、recovery |
| **T11** | PostgreSQL Schema And Concurrency Certification | T01-T10 | clean/prod upgrade fingerprint 与 full-chain gate |
| **T12** | Restore And Deployment Rehearsal | T11 | shadow restore、forward migration、previous-code readonly/write compatibility class |
| **T13** | Tokyo No-Write Canary | T12 + Owner implementation confirmation | exact SHA/schema/current truth，无 exchange write |

### 4.1 并行边界

- **T00-T03 必须先冻结接口。**
- T04 的 domain tests、T06 的 occupancy fixtures、T07 的 detector fixtures 可以并行准备，但 **T07 必须先冻结 Signal writer interface，T05A 才能完成集成**。
- `promotion_action_time_lane.py`、refresh sequence、runtime repository 和 lifecycle current files 必须串行集成审查。
- T08 只能在 Kernel、Invocation、occupancy 和 detector 输出冻结后接入。
- T11-T13 严格串行。
- 不允许再开一条独立 Schema、FRR 或 Dual-Position medium WIP。

## 5. T00 — Baseline And Production-Shaped RED Evidence Freeze

### 5.1 Task Packet

**Task ID:** `P0-ACH-T00`

**Goal:** 冻结当前东京、PG、Migration graph、测试漂移和多信号/双仓位缺口，使后续修复不可通过改变 fixture 或隐藏 blocker 逃逸。

**Why:** 当前生产已给出 67 个 Signal Event、32 个 Invocation、3 个 Ticket 和 60 个 engineering handoff gap；现有测试仍包含旧 head 和非生产 schema。

**Allowed files:** focused unit/integration tests、只读 audit/probe tests、当前两份 P0-ACH 文档的 Completion Record。

**Forbidden files:** `src/**` 行为实现、migration、deploy apply、production state。

**Requirements:**

1. 冻结 repeating Decimal 的真实 `Numeric(36,18)` case。
2. 冻结同 tick 多 Signal 只有部分 Invocation 的 case。
3. 冻结 Invocation 无 process outcome、Ticket 过期和 local Order registration failure。
4. 冻结 0/2、1/2、2/2 与同 instrument claim fixture。
5. 冻结 Alembic head、metadata、runtime `create_all()` 和测试 schema 漂移。
6. 只读冻结东京 PG role topology：application/migration 的 `session_user/current_user`、masked connection identity ref、database/schema/table/sequence owner、membership/`SET ROLE`、schema CREATE、owner 隐式 ALTER/DROP、default privileges 和是否需要 credential/secret 变化。
7. 冻结 Signal、Ticket、RequiredFacts、systemd 四类最短 deadline 以及 30 秒前后 1ms 的 RED case。
8. 冻结 Candidate/Goal/Monitor/Ops 对同一 snapshot 不一致的 case。
9. gateway 使用 fail-if-called。

**Global Authority Model:** 只固化证据，不创建 runtime、Ticket 或 exchange authority。

**Chain Position:** `action_time_boundary`

**Live Enablement State Before:** 生产缺陷存在，但没有一个统一 RED matrix。

**Live Enablement State After:** 所有目标缺陷均有 production-shaped RED 证据。

**Blocker Removed Or Reclassified:** 将宽泛 `action_time_boundary_not_reproduced` 拆为 schema、Decimal、Invocation、arbitration、occupancy、detector、current relevance、TTL 和 persistence blocker。

**Per-Symbol / Per-Fact Acceptance:** 覆盖 SOR BTC/SOL/ETH/AVAX、BRF2 ETH、CPM SUI 和 22-lane current matrix。

**Stop Condition:** RED 失败原因来自错误 fixture/schema，而不是目标缺陷。

**Capability Unlocked:** Schema Truth Gate 和逐类 RED-GREEN。

**Next Engineering Bottleneck:** Schema authority 与 migration necessity。

**Rehearsal/Simulation Boundary:** disposable PostgreSQL；exchange calls=0。

**Tests:** 仅新增/修正 RED tests；包含 role topology readonly probe 和 deadline matrix，不运行全仓回归。

**Done When:** 所有缺陷以目标 blocker 稳定复现，证据不依赖生成文件。

**Hard Stop:** 用 SQLite、mocked Numeric、下游完整字典或随机 DB order 代替生产形态。

## 6. T01 — Schema Truth Gate

### 6.1 Task Packet

**Task ID:** `P0-ACH-T01`

**Goal:** 建立当前 schema 的机器可读真值，并决定 `planned_migration_set` 是 `none` 还是最小 capability bundle。

**Why:** 现有设计预设 migration 141，但 Alembic metadata、runtime create_all、test schema 和真实 head 尚未一致。

**Allowed files:** `migrations/env.py`、migration graph/schema audit、schema fingerprint helper、migration governance tests、release preparation/probe assertions、只读 PG role topology audit。

**Forbidden files:** 新 migration、业务行为修复、Strategy/Policy seed、production apply。

**Requirements:**

1. 冻结 `001–140` 内容和 checksum。
2. 通过 Alembic API 验证单 root、单 head。
3. inventory Alembic-owned、ORM-only、legacy-unmapped tables。
4. 将 `PGCoreBase.metadata` 与真实模型确定性注册纳入 drift audit，同时建立覆盖 migration-only 表的 managed-schema registry；不得仅把空 metadata 直接替换成不完整 ORM metadata。
5. 比较 fresh `001→140` 与 production-shaped head 140 fingerprint。
6. 对 Decimal、Invocation terminal、Account Budget Current unique identity、detector identity、Netting Domain canonical key、process/notification correlation 和 winner uniqueness 执行 schema-fit matrix。
7. 生成 capability decision：`no_migration_required` 或最小 logical expand/backfill/enforce bundle；bundle manifest 必须包含 capability、affected table、唯一 writer、revision sequence、role decision、previous-code compatibility floor 和 restore/rollback class。
8. 不用 migration 文件数量或排序后的文件名作为 schema identity。
9. 生成 `role_topology_decision`：`existing_roles_sufficient`、`grant_owner_convergence_without_secret_change`、`credential_or_secret_change_required` 或 `role_topology_unknown`。
10. 若需要新 role、credential、secret 或密钥分发变化，立即标记 `blocked_owner`；不得把该变化推迟到 T13 临时处理。
11. 若移除 production `create_all()` 需要补齐 ORM-only production dependency，必须作为 Schema Authority Closure item 在 T01 逐项命名；T02 不得自行扩 scope。

**Global Authority Model:** Gate 只判断 schema capability，不授予业务、policy 或 live authority。

**Chain Position:** `action_time_boundary`

**Live Enablement State Before:** schema truth 由 Alembic、ORM 和手工测试路径共同暗示。

**Live Enablement State After:** schema head、fingerprint、metadata 和 migration necessity 有一个结论。

**Blocker Removed Or Reclassified:** `schema_authority_unverified` → `no_migration_required` 或 exact capability gap。

**Per-Symbol / Per-Fact Acceptance:** 账户/Signal/Invocation/Ticket/lifecycle/current tables 全部进入 inventory；不按某个 StrategyGroup 特判。

**Stop Condition:** clean/prod schema 不等价、旧 revision checksum 漂移或存在无法归属的生产表。

**Capability Unlocked:** Single Schema Authority 与正确 migration planning。

**Next Engineering Bottleneck:** runtime `create_all()` 和 application role DDL。

**Rehearsal/Simulation Boundary:** 本地/disposable PG，只读生产 fingerprint。

**Tests:** revision graph、metadata registration、schema introspection、fingerprint equivalence、dynamic head。

**Done When:** `planned_migration_set` 和 `role_topology_decision` 均被证据决定，旧 revision 不再可变。

**Hard Stop:** 为满足文档编号而创建空 migration，或修改 `001–140`。

## 7. T02 — Single Schema Authority

### 7.1 Task Packet

**Task ID:** `P0-ACH-T02`

**Goal:** 让 Alembic 成为唯一生产 Schema Authority；ORM 只描述映射，repository initialize 只验证 capability。

**Why:** production runtime `create_all()` 会让数据库在未执行 migration 时静默补表，破坏升级和测试可信度。

**Allowed files:** `src/infrastructure/database.py`、`src/infrastructure/pg_models.py`、`migrations/env.py`、repository initialization helper、startup/schema capability checks、T01 批准的 Schema-Authority capability migration(s)、相关 tests/deploy preflight 和 application-role grant plan。

**Forbidden files:** 业务表随意重命名、全量 ORM 重写、生产 role apply、交易路径功能变化。

**Requirements:**

1. production runtime 路径不调用 `Base.metadata.create_all()` 或 `PGCoreBase.metadata.create_all()`。
2. PostgreSQL integration/concurrency/restore/release certification 一律使用 `alembic upgrade head`；helper 只允许纯单元测试或不声称 schema parity 的 fixture。
3. repository initialize 只验证连接、head、required table/column/capability。
4. migration/deploy identity 与 application identity 的 SQL/部署计划分离；application identity 不具备 schema DDL、managed object ownership 或可绕过的 membership/`SET ROLE`/default privilege。
5. startup 失败必须输出 masked、typed schema blocker。
6. release manifest 统一记录 commit、Alembic head、graph checksum、capability set、schema fingerprint。
7. 删除硬编码 `136/138` 和手工 migration 清单的认证作用。
8. 若生产依赖的 ORM-only table/column 被 T01 证明存在，先用批准的 capability migration 补齐，再移除 `create_all()`。
9. 只有 `role_topology_decision` 为 `existing_roles_sufficient` 或 `grant_owner_convergence_without_secret_change` 时，才准备 T13 grant/revoke/owner convergence apply；否则保持 `blocked_owner`。
10. previous release 兼容性不在本 Task 假设为 write-compatible；T12 必须单独分类 readonly/write compatibility。

**Global Authority Model:** Schema capability 不授予 runtime submit authority。

**Chain Position:** `action_time_boundary`

**Live Enablement State Before:** runtime 可能补建 production table。

**Live Enablement State After:** 未经 migration 的 schema 差异会在 startup/preflight fail closed。

**Blocker Removed Or Reclassified:** `dual_schema_authority`、`migration_head_test_stale`。

**Per-Symbol / Per-Fact Acceptance:** 全部 PG current tables 同一规则；不允许 Strategy-specific create fallback。

**Stop Condition:** 任一 production repository 仍依赖自动建表；或生产角色拓扑未知/需要未获授权的新 credential/secret，此时以 `blocked_owner` 退出生产推进。

**Capability Unlocked:** 后续 RED-GREEN 运行在可信 schema 上。

**Next Engineering Bottleneck:** Runtime Semantic Kernel。

**Rehearsal/Simulation Boundary:** disposable PG、startup test；无 production privilege mutation。

**Tests:** clean startup、missing schema fail、wrong head fail、unit-only helper boundary、真实 Alembic bootstrap、release manifest single source。

**Done When:** production `create_all()` 调用为 0，Schema drift 可机器检测。

**Hard Stop:** 保留“migration 失败时 create_all fallback”。

## 8. T03 — Runtime Semantic Kernel

### 8.1 Task Packet

**Task ID:** `P0-ACH-T03`

**Goal:** 建立共享 phase/state/terminal/reason/current-relevance 语义，并确定 Invocation 是否需要最小 schema primitive。

**Why:** 当前 lifecycle、Attempt、Invocation、Ops 和 readmodel 分别维护 active/terminal 状态集合，已经出现漂移。

**Allowed files:** 新增纯 domain semantic module、`src/application/action_time/action_time_invocation.py`、`process_outcome_relevance.py`、typed reducer contracts、focused tests；T01 批准的 conditional migration files。

**Forbidden files:** 把所有 Aggregate 合并成万能状态机、为每个 reason 增加 DB status、exchange mutation。

**Requirements:**

1. 定义稳定 `phase/state/terminal_kind/reason_code`。
2. 提供 active、terminal、current、operationally relevant predicate。
3. 定义合法 transition 和不可回退终态。
4. Invocation 优先复用 `closed_at_ms`、Ticket 和 process outcome；只有缺少可索引稳定 primitive 时才使用 T01 批准的 migration。
5. 任何新 DB CHECK 只约束稳定维度，不枚举高频 blocker reason。
6. lifecycle、Attempt、Invocation 和 readmodel 保留独立 Aggregate 边界。

**Global Authority Model:** Kernel 统一解释，不升级任何交易 authority。

**Chain Position:** `action_time_boundary`

**Live Enablement State Before:** 同一行在不同 consumer 中可能同时 active 和 terminal。

**Live Enablement State After:** 所有 consumer 使用同一 semantic contract。

**Blocker Removed Or Reclassified:** `runtime_state_semantics_diverged`、`expired_invocation_unclosed` 问题类。

**Per-Symbol / Per-Fact Acceptance:** current/historical Attempt、Invocation、Ticket 和 lifecycle fixture 均得到一致结果。

**Stop Condition:** 需要猜测未知 exchange/Ticket lineage，或 reason 被强制写入频繁变化 CHECK。

**Capability Unlocked:** Decimal、Invocation、health 和 notification 共用稳定语义。

**Next Engineering Bottleneck:** Persisted Decimal/Claim。

**Rehearsal/Simulation Boundary:** pure domain + PG fixture；无 network。

**Tests:** transition table、terminal irreversibility、expiry、unknown outcome、current relevance parity。

**Done When:** 重复 status literal 被删除或委托给 Kernel，T00 semantic RED 转绿。

**Hard Stop:** 通过隐藏历史 warning 或把 unknown 当 terminal 制造一致。

## 9. T04 — Persisted Decimal And Account Capacity Claim

### 9.1 Task Packet

**Task ID:** `P0-ACH-T04`

**Goal:** 统一 Decimal canonicalization，并让 Claim hash、INSERT、reload、retry、Ticket 和 FinalGate 使用同一 payload。

**Why:** 合法 repeating Decimal 当前在 PG `Numeric(36,18)` roundtrip 后被误判为 drift。

**Allowed files:** 新增 `src/domain/persisted_decimal.py`、`src/domain/account_capacity_claim.py`、`src/domain/account_risk.py` 的 canonical 接入、`src/application/action_time/account_capacity_claim.py`、FinalGate/Ticket claim guard、focused tests。

**Forbidden files:** policy/sizing 数值、exchange gateway、通过 tolerance 忽略 mismatch。

**Requirements:**

1. 定义 exact、allowance、consumption、observation rounding。
2. hash 前 canonicalize；INSERT 只接受 frozen canonical payload。
3. reload 后比较 canonical payload。
4. 同值不同 raw scale retry 幂等；真实 drift 仍 conflict。
5. SQLSTATE/constraint name 精确分类。
6. FinalGate 复核 persisted canonical hash。
7. PG lock 内不得有 network I/O。
8. T01 未证明 schema gap 时不得新增 Numeric migration。

**Global Authority Model:** Claim 只保留容量，不创建 Ticket/submit authority。

**Chain Position:** `action_time_boundary`

**Live Enablement State Before:** 合法 Claim 被 roundtrip mismatch 阻止。

**Live Enablement State After:** canonical 同值可幂等持久化，真实差异 fail closed。

**Blocker Removed Or Reclassified:** `account_capacity_claim_roundtrip_mismatch:*` → exact canonical/constraint blocker 或 success。

**Per-Symbol / Per-Fact Acceptance:** BRF2 ETH short、SOR SOL long 生产数值，以及 price/qty/risk/margin 边界。

**Stop Condition:** 字段无法确定 semantic role，或 canonicalization 会扩大 Owner allowance。

**Capability Unlocked:** winner 可安全进入 Ticket。

**Next Engineering Bottleneck:** Signal conservation 和 arbitration。

**Rehearsal/Simulation Boundary:** real PG；gateway calls=0。

**Tests:** repeating Decimal、18/19 位边界、same/different payload race、hash/FinalGate parity。

**Done When:** T00 Decimal RED 全绿且无 float/tolerance path。

**Hard Stop:** 仅特判 `reserved_margin` 或让 DB 回读覆盖已 hash raw payload。

## 10. T05 — Signal Conservation、Invocation And Deterministic Arbitration

### 10.1 Task Packet

**Task ID:** `P0-ACH-T05`

**Goal:** 通过 T05A/T05B/T05C 三个顺序 checkpoint 保存每个 fresh Signal、确定性选择至多一个 winner，并以 typed coordinator 和真实 deadline 完成切换。

**Why:** 当前 35 个 Signal 缺 Invocation，24 个 Invocation 缺 process outcome；global single-row 语义在 arbitration 前丢失因果对象。

**Allowed files:** refresh sequence、`materialize_action_time_ticket_sequence.py`、Action-Time Invocation、Promotion/Lane、Ticket materialization、可替换关键 subprocess 的 typed application coordinator、focused tests。

**Forbidden files:** Strategy priority 值、Capital Allocation V1、exchange gateway、多个同时 real-submit lane。

**Requirements:**

1. 删除 global `LIMIT 1` 因果丢失语义，使用 bounded fresh Signal batch。
2. 每个 Signal 有 Invocation 和 process outcome。
3. 排序使用 policy priority、candidate priority、event time、observed time、signal ID。
4. 同 account/profile 事务内最多一个 winner。
5. loser 写 not-selected/arbitration evidence；expired/invalid 写 typed result。
6. 只有 winner 刷新 private facts、occupancy、Claim 和 Ticket。
7. partial write 回滚；retry 选择稳定。
8. Action-Time 内部改用 typed command/result，不依赖 stdout 最后一行 JSON。
9. coordinator 使用设计 §7.14 的 `global_deadline_ms`；新 Ticket/Fact 只能缩短 deadline，不能延长。
10. 每一步 timeout、PG lock timeout 和 statement timeout 都由 `remaining_budget_ms` 派生；预算不足必须在下一 authority boundary 前持久化 `action_time_deadline_insufficient:<next_stage>`。

**Global Authority Model:** arbitration 选择机会，不创建 FinalGate/Operation Layer authority。

**Chain Position:** `fresh_signal_promotion -> action_time_boundary`

**Live Enablement State Before:** 多 Signal 中部分没有 Invocation/result。

**Live Enablement State After:** 所有 Signal 有结果，同 domain 唯一 winner。

**Blocker Removed Or Reclassified:** `action_time_invocation_missing`、`runtime_process_outcome_missing`；正常 loser 变为 `arbitration_lost/not_selected`。

**Per-Symbol / Per-Fact Acceptance:** SOR BTC/SOL/ETH/AVAX 同 timestamp，在随机插入和两 worker 下选择一致。

**Stop Condition:** 出现两个 winner、partial terminalization 或需要修改 Owner priority。

**Capability Unlocked:** 真实多信号不丢失，仍保持一次一个新 Action-Time lane。

**Next Engineering Bottleneck:** multi-position occupancy/lifecycle。

**Rehearsal/Simulation Boundary:** private provider fake/read-only；gateway calls=0。

**Tests:** same timestamp、winner expiry、two workers、partial rollback、retry、process outcome conservation、signal/ticket/fact/systemd shortest deadline、deadline 前后 1ms、deadline 后零 Claim/Ticket/handoff side effect。

**Done When:** T05A/B/C 各自 RED→GREEN，且 67-signal production-shaped matrix 中每个 Signal 都有明确结果。

**Hard Stop:** DB implicit order、随机选择或多 lane 并行 submit。

### 10.2 顺序 Checkpoint、RED-GREEN 与回滚点

三个 checkpoint 共用 **Task ID `P0-ACH-T05`**，但必须分别 commit、验收和保留清晰回滚点。它们不得作为三套生产 writer 并存；Tokyo apply 只允许在 T05C、T10、T11 一起通过后发生。

#### T05A — Signal Intake And Invocation Conservation

```text
RED:
bounded same-timestamp Signal batch 中存在无 Invocation/outcome 的行，
duplicate delivery 或 process death 会遗漏或复制 causal context。

GREEN:
每个 fresh eligible Signal 先得到一个幂等 Invocation 和 process outcome；
本 checkpoint 的 private provider、Promotion winner、Claim、Ticket 调用数均为 0。

ROLLBACK:
部署前 code-only revert；已写 Invocation/outcome 是 append-only 非 submit 证据，
保留供审计，不需要 schema/policy rollback。
```

#### T05B — Deterministic Arbitration And Winner Claim

```text
RED:
random insert、two workers、winner expiry、serialization retry 可产生多个 winner、
无 winner evidence 或 loser partial terminalization。

GREEN:
同 account/profile allocation domain 至多一个 winner；
所有 loser 保存 winner_ref、rank、terminal result；只有 winner 可请求 private facts。

ROLLBACK:
部署前回退 arbitration commit，T05A 保留；不得在生产重新启用旧 global single-row writer。
```

#### T05C — Typed Coordinator And Global Deadline Cutover

```text
RED:
单个 child 可消耗 45 秒、stdout JSON 决定业务语义、过期 source 仍进入下一阶段。

GREEN:
typed command/result only；每一步接收 remaining_budget_ms；
deadline 不足保存 exact blocker 且后续 side effect=0；旧 stdout/global materializer 不可达。

ROLLBACK:
T13 前可回退 coordinator commit；Tokyo cutover 后保持 new-entry Writer Fence 并 forward-fix，
不得把已退休 stdout/global path 当生产 fallback。
```

## 11. T06 — Multi-Position Occupancy And Core Order Convergence

### 11.1 Task Packet

**Task ID:** `P0-ACH-T06`

**Goal:** 让 observation、Action-Time、FinalGate 和 next-entry gate 消费同一 occupancy，并证明两个仓位的 identity、保护和容量互不串线。

**Why:** core `orders` 与 ticket-bound truth、account current 和 watcher 曾给出不同冲突结论；2/2 state 尚未 whole-chain 认证。

**Allowed files:** lifecycle occupancy、account exposure/budget current、capacity hot-path repository、core Order terminal projection、ticket-bound finalizer/scheduler、readmodel接入、正式 repair projector、focused tests。

**Forbidden files:** `src/application/reconciliation.py` 未经重新审查不得修改；exchange placement、position cap、manual SQL。

**Requirements:**

1. Observation 在 2/2 时继续 detector；occupancy 只阻止 winner progression。
2. identity 绑定 account/profile/instrument/position mode/position bucket/netting domain/side/Ticket/exposure episode。
3. 同 instrument claim 精确阻止，不把不同受保护 instrument 当冲突。
4. terminal lifecycle exactly-once 释放 slot/risk/margin。
5. unknown outcome、active hold、missing protection 继续占用并 fail closed。
6. core Order 只由 exact terminal ticket-bound truth 投影终态。
7. runner、SL/TP1、reconciliation 和 settlement 按 Ticket 隔离。
8. one-time repair 只能调用正式 projector，且保留 dry-run/apply。
9. 建立一个 versioned `NettingDomainKey` builder；Exposure、Command、Hold、Protection 和 Reconciliation 不再自行拼接 key。
10. 验证 `brc_account_budget_current` 对一个 account/profile 只有一条 current；policy version 只能是属性，不能制造并行 current identity。

**Global Authority Model:** occupancy/projector 同步已证明事实，不创建或取消 exchange order。

**Chain Position:** `action_time_boundary`

**Live Enablement State Before:** 账户/Order/lifecycle current truth 可能分裂。

**Live Enablement State After:** 0/1/2 capacity 与每 Ticket lifecycle 唯一可解释。

**Blocker Removed Or Reclassified:** proven stale order conflict；真实同 instrument/2-of-2/unknown blocker 保留。

**Per-Symbol / Per-Fact Acceptance:** BTC/AVAX/ETH/SOL historical rows；两个不同 instrument 的 active protected Ticket；同 instrument negative。

**Stop Condition:** exact Ticket/exchange identity 不完整或 active risk 未知。

**Capability Unlocked:** 双仓位 pre-live matrix 的真实 occupancy 基础。

**Next Engineering Bottleneck:** detector current 和 projection ownership。

**Rehearsal/Simulation Boundary:** PG + fake exchange snapshots；exchange writes=0。

**Tests:** 0/1/2、same instrument、unknown outcome、runner isolation、release idempotency、core projector negatives。

**Done When:** watcher/direct/FinalGate/account owner state 对同一 snapshot 一致。

**Hard Stop:** 按 symbol 批量关 core order、删除历史、忽略 unknown outcome。

## 12. T07 — Detector Current And Projection Ownership

### 12.1 Task Packet

**Task ID:** `P0-ACH-T07`

**Goal:** 每 lane/event/candle 持久化一个 typed detector decision，并让 Signal 与 decision 在同一应用服务和明确事务边界中提交。

**Why:** 22/22 coverage 健康、Signal 可产生，但 Candidate Pool 仍报 22 个 detector missing。

**Allowed files:** observation monitor/watcher、runtime control repository、detector fact writer、Signal materializer、projection ownership contract、T01 批准的 conditional migration、focused tests。

**Forbidden files:** strategy threshold/event semantics、new detector table、runtime scope expansion、file output。

**Requirements:**

1. 决策绑定 typed full lane identity、event spec/version、detector、decision identity/closed candle、source watermark、producer runtime head/release generation。
2. satisfied 和 computed false 都持久化。
3. Signal 与 detector decision 原子或具备不可丢失 outbox/process outcome。
4. 同 candle 重复 tick no-op；payload drift 写 process blocker，禁止 `ON CONFLICT DO UPDATE` 改写历史 decision。
5. coverage/public fact 不得替代 detector decision。
6. batch transaction、复用 engine、每 candle 每 lane 最多一行。
7. 明确 Detector/Signal 唯一 writer，删除竞争 path。

**Global Authority Model:** detector decision 不创建 promotion 或 submit authority。

**Chain Position:** `pretrade_candidate_readiness`

**Live Enablement State Before:** Signal 与 detector current 可分裂。

**Live Enablement State After:** 22 lane 各有 computed result 或 exact technical blocker。

**Blocker Removed Or Reclassified:** `detector_not_attached` → `computed_not_satisfied`、fresh Signal 或 exact writer blocker。

**Per-Symbol / Per-Fact Acceptance:** 五个 StrategyGroup、22 lane、当前 Event Specs；unsupported side 不写 current。

**Stop Condition:** evaluator 缺完整 identity，或需要 generated file 作为输入。

**Capability Unlocked:** 可信 market-wait 和 current reducer。

**Next Engineering Bottleneck:** readmodel/ops/notification convergence。

**Rehearsal/Simulation Boundary:** live public/read-only facts allowed；exchange writes=0。

**Tests:** satisfied/false、repeat candle、identity drift、atomic rollback、row growth、writer ownership。

**Done When:** coverage healthy + Signal exists + detector current missing 不再可能。

**Hard Stop:** 通过 Signal presence 反推 detector computed。

## 13. T08 — Shared Readmodels、Ops、Forensics And Notification

### 13.1 Task Packet

**Task ID:** `P0-ACH-T08`

**Goal:** Candidate、Readiness、Tradeability、Daily Table、Goal、Monitor、Ops、Forensics 和 Owner notification 共用 Runtime Semantic Kernel 和同一 PG snapshot。

**Why:** 当前 historical warning、current risk、工程 blocker 和 capability recovery 被不同 consumer 分别解释。

**Allowed files:** 新 shared runtime-lane/current reducer、Candidate/Goal/Daily/Forensics readmodels、Ops health、Owner projection、server monitor、notification、focused tests；T01 批准的 conditional incident fields。

**Forbidden files:** 第二 health/notification table、local dedupe file、删除历史 Attempt、修改 Feishu secret。

**Requirements:**

1. reducer 输出 coverage/detector/signal/invocation/promotion/lane/occupancy/process/current relevance。
2. 所有 consumer 的 first blocker 和 watermark 一致。
3. current issues 与 historical warnings 分离。
4. `market_wait_validated` 满足完整合同。
5. event occurrence 与 capability incident fingerprint 分离。
6. engineering blocker 默认 Owner action=false。
7. recovery 只接受更晚同 process success 或 release certification。
8. signal expiry/top-lane change 不得 recovered。

**Global Authority Model:** readmodel/notification 不改变 runtime truth 或交易状态。

**Chain Position:** `daily_live_enablement_status`

**Live Enablement State Before:** 同一 snapshot 可产生 detector missing、processing、hard stopped 等冲突状态。

**Live Enablement State After:** 一个 current first blocker、一个 Owner product state、一个 incident truth。

**Blocker Removed Or Reclassified:** historical `submit_failed`/runner warnings 降级为 review-only；真实 current blocker 保留。

**Per-Symbol / Per-Fact Acceptance:** 22-lane golden matrix；BRF/SOR incident expiry/recovery；active unknown/protection negatives。

**Stop Condition:** 任一 consumer 必须绕过 Kernel 才能满足合同，或 lineage 不足以证明 terminal。

**Capability Unlocked:** 可信 pre-live status、monitor 和 Owner notification。

**Next Engineering Bottleneck:** runtime lifecycle、legacy path 和 retention。

**Rehearsal/Simulation Boundary:** typed PG fixtures、fake notifier；真实 Feishu 可留到 T13 no-write canary。

**Tests:** consumer parity、current/historical、market wait、incident dedupe/recovery、Owner action mapping。

**Done When:** 重复状态 SQL/list 被删除或委托给 Kernel，所有 views parity 通过。

**Hard Stop:** 隐藏 blocker、按年龄自动忽略 unknown，或模板变化重放历史通知。

## 14. T09 — Runtime Lifecycle、Legacy Retirement And Retention

### 14.1 Task Packet

**Task ID:** `P0-ACH-T09`

**Goal:** 对齐 active runtime 与 Candidate Universe，退休旧 Promotion/Order/current authority，并控制 PG、日志、report 和 release 增长。

**Why:** 52 active runtime / 22 current lane、旧 batch promotion、legacy Order reader 和 repair script 会继续制造噪声和双路径维护。

**Allowed files:** official runtime lifecycle/API、watcher selection、legacy path callers、deployment-scoped writer-fence/new-entry maintenance boundary、retention tooling、file-I/O audit tests、current docs authority updates。

**Forbidden files:** 删除 runtime/trading provenance、active-runtime fallback、新 report writer、全仓 monolith 重写。

**Requirements:**

1. active runtime 必须匹配 current candidate/event/runtime/policy binding。
2. out-of-universe row 只有在无 current signal/Ticket/lifecycle ownership 时 soft-retire/park。
3. 删除或不可达 legacy global promotion materializer。
4. legacy `orders` 退出 next-entry safety authority。
5. repair script 完成收敛后 archive/remove；不能长期 cadence 化。
6. detector 每 candle 一行；coverage current 每 lane 一行。
7. no-signal tick JSON/MD=0；日志不逐 tick 输出预期 exclusion noise。
8. retention 不删除 Signal/Ticket/Lifecycle/Outcome provenance。
9. 提供正式、可审计、可恢复的 new-entry maintenance/submit-disabled fence：阻止新真实 ENTRY，保持 observation 和已有仓位 lifecycle/reconciliation 运行；fence 不得成为未审计的 file-only runtime authority。
10. 建立 design §9.3 的 retention registry；每个数据族输出 `retained_rows/bytes`、`daily_growth_p95`、`capacity_budget`、`cleanup_lag_seconds`、`owner`、`next_cleanup_at` 和 `clear/warn/hard`。
11. cleanup 使用 advisory lock、最多 5,000 行短事务 chunk、总 timeout 10 分钟；不进入交易事务或生产热路径。
12. detector decision hard capacity 以 **228,096 行**为初始机器阈值；其他 cadence family 使用 `retention_days × frozen_daily_ceiling × 1.2` 计算 hard capacity。
13. `hard` retention 状态阻止 T11/T13；`warn` 不阻止交易，但不得宣称维护成本闭合。

**Global Authority Model:** hygiene 不改变 Owner scope/policy，也不创建 live authority。

**Chain Position:** `pretrade_candidate_readiness`

**Live Enablement State Before:** 新旧 path 并存、active runtime 语义漂移、增长成本上升。

**Live Enablement State After:** current path 唯一、历史路径有明确 removal proof、增长可预测。

**Blocker Removed Or Reclassified:** `runtime_excluded_by_candidate_universe` 从持续 warning 变为 bounded lifecycle event。

**Per-Symbol / Per-Fact Acceptance:** 22 current lane 全保留；有 current ownership 的 runtime 不 retire。

**Stop Condition:** 无法证明旧 path 不再被生产调用，或 retention 触及交易 provenance。

**Capability Unlocked:** 可维护的双仓位 pre-live whole-chain。

**Next Engineering Bottleneck:** Dual-position matrix。

**Rehearsal/Simulation Boundary:** dry-run first；exchange effect=0。

**Tests:** caller inventory、legacy path negative、runtime ownership、retention registry/dry-run/chunk/timeout/advisory-lock、protected provenance negative、file-I/O audit。

**Done When:** production critical path 只有一套 writer/reducer，audit performance risk clear。

**Hard Stop:** 通过兼容 adapter 永久同步两套 current authority。

## 15. T10 — Dual-Position Pre-Live Matrix

### 15.1 Task Packet

**Task ID:** `P0-ACH-T10`

**Goal:** 使用真实 PostgreSQL 和 fake/no-write gateway 证明当前 Owner policy 下两个仓位可以连续建立、独立运行、恢复并释放。

**Why:** 当前 2/2 账户状态不等于官方链已经证明完整双生命周期。

**Allowed files:** scoped integration/full-chain tests、account capacity/occupancy/lifecycle test harness、fake/no-write gateway、performance fixtures。

**Forbidden files:** position cap=3、policy/sizing 变化、真实 exchange write、synthetic production rows。

**Requirements:**

1. 0/2 + 两个不同 instrument Signal：全部保存，一次一个 winner。
2. 0/2 → 1/2，随后第二个不同 identity 的 production-shaped Signal 使 1/2 → 2/2。
3. 1/2 同 instrument 精确阻止。
4. 2/2 第三请求必须在 Claim/Ticket 前精确阻止。
5. 两 worker Claim 不突破 2。
6. 一个 `open_protected` ExposureEpisode + 一个不同 instrument 的 effective pending Claim/Reservation 必须计为 **2/2**；第三请求在 Account Budget/Claim 边界即被阻止，不得等待第二个 Ticket/position 出现。
7. pending Claim 转为同一 `exposure_episode_id` 的 working/open Exposure 时只发生 ownership replacement，slot、risk、cluster risk 和 margin 不得双计。
8. Claim/Ticket 原子事务 commit 前进程退出不得留下 durable Claim/Reservation/slot；commit 后退出则 pending Claim 继续占用，第三请求阻止，lease/process exit 本身不得释放容量。
9. official recovery 只有在证明无 external effect、无 unknown command、无 position/open order 后才能 exactly-once release；lease expiry 只能进入 recovery/reconciliation。
10. first position runner 与 second position protection/lifecycle 不串线。
11. 一个 terminal 只释放自己的 capacity；另一个保持占用。
12. release projector 与新 Claim 必须锁同一 `account_id + runtime_profile_id` Budget Current，并使用 monotonic `projection_version`/CAS；只允许“release 先 commit 后 Claim 成功”或“Claim 观察旧 2/2 后精确阻止/版本变化重试”。
13. simultaneous exchange close、Exposure terminalization、Reservation release、Budget reprojection 与新 Claim 并发时，Claim 必须绑定 commit 后的 `source_snapshot_id + projection_version`；禁止 lost update、negative slot、phantom free slot 和旧 snapshot 覆盖新 current。
14. unknown outcome、missing protection、orphan order 保持 hold。
15. 两 lifecycle 都能模拟到 settlement/review/closure。
16. risk policy version 切换后，一个 account/profile 仍只有一条 Budget Current，容量锁不会读取多行。
17. 一个 hold source resolved 不得清除同 netting domain 的其他 active source hold。
18. slot 尚有空余但 portfolio open risk 已耗尽时，精确返回 `portfolio_open_risk_capacity_exhausted`。
19. slot/portfolio 可用但目标 cluster 已耗尽时，精确返回 `risk_cluster_open_risk_capacity_exhausted`。
20. slot/risk/cluster 可用但 initial margin 已耗尽时，精确返回 `portfolio_initial_margin_capacity_exhausted`。
21. 多 cap 同时耗尽时 first blocker 顺序稳定，同时保留全部 cap diagnostics；释放一个 cap 后，其他未释放 cap 继续阻止。

**Global Authority Model:** fake gateway 结果不成为 production runtime authority。

**Chain Position:** `action_time_boundary`

**Live Enablement State Before:** 组件支持 2 positions，但未 whole-chain certified。

**Live Enablement State After:** bounded dual-position behavior 在全链和失败路径可重复证明。

**Blocker Removed Or Reclassified:** `dual_position_whole_chain_not_certified`。

**Per-Symbol / Per-Fact Acceptance:** 至少覆盖两个不同 canonical instruments、long/short、runner 与非-runner lifecycle；不依赖特定 crypto symbol patch。

**Stop Condition:** 任一 Ticket identity 串线、pending Claim 漏算/双算、release-vs-claim lost update、projection version 回退、重复 release、任一 position/risk/cluster/margin cap 被突破，或 fake gateway 被误认为 live。

**Capability Unlocked:** PostgreSQL exact-head final certification。

**Next Engineering Bottleneck:** schema/concurrency/restore certification。

**Rehearsal/Simulation Boundary:** disposable PG + fake gateway；exchange writes=0。

**Tests:** full positive/negative matrix、restart/crash-before-and-after-commit、three requesters、release-vs-claim、simultaneous close+claim、runner isolation、cap independence、pending→Exposure replacement、release exactly once。

**Done When:** `claimed_position_slots`、portfolio held risk、cluster held risk、exchange initial margin + unreflected pending margin 均从 active Exposure + effective pending Claim exactly once 得出；每个 cap 有独立正反例，两个 lifecycle 的每个对象都有 exact identity/result。

**Hard Stop:** 用同一 Ticket/position fixture 复制两次假装双仓位。

## 16. T11 — PostgreSQL Schema And Concurrency Certification

### 16.1 Task Packet

**Task ID:** `P0-ACH-T11`

**Goal:** 在 exact candidate SHA 上完成 clean/prod upgrade、schema fingerprint、并发、全链、性能和文件 I/O 认证。

**Why:** 当前问题正是局部测试通过但生产 Numeric、schema、同 tick 和历史 current state 未覆盖。

**Allowed files:** scoped integration/full-chain tests、schema/fingerprint tools、release verification assertions、test-only fake gateway。

**Forbidden files:** 为通过测试修改 policy/sizing、真实 exchange write、生成 repo report artifact。

**Requirements:**

1. fresh PostgreSQL `001→candidate head`。
2. production-shaped `140→candidate head`。
3. 两者 type/scale/null/default/index/unique/FK/CHECK fingerprint 相同。
4. managed-schema registry、Alembic-managed objects 与 PG model mappings diff clear；migration-only 表有显式规则。
5. 使用 barrier-controlled、非 sleep 猜序的至少三个独立 connection/process 认证 Claim/arbitration/capacity；覆盖 protected owner、pending Claim worker、third requester，以及 release/close worker 并发变体。
6. 22-lane detector/reducer/Goal/Monitor/Ops parity。
7. T10 dual-position whole-chain matrix。
8. active position、unknown outcome、missing protection、wrong account/instrument、stale facts negatives。
9. production-shaped `EXPLAIN ANALYZE`、20% watcher timeout headroom，并认证真实 deadline：Signal/Ticket/RequiredFacts/systemd 分别成为最短截止时间，30 秒 ceiling 前后 1ms，deadline 后零新 Claim/Ticket/FinalGate input/submit handoff。
10. file-I/O/output-scope audit clear。
11. 若存在 migration bundle，验证 Budget Current 单行 identity、Detector immutable decision identity 和 Netting Domain canonical key 的 expand/backfill/enforce 不变量。
12. 认证 T09 retention registry 全部非 `hard`、所有 production-cadence family 均有 owner/next cleanup，backup/release/journal threshold 可机器读取。
13. 冻结 previous-code compatibility matrix：Entry/Action-Time、Protection/Reconciliation、Current Projection、Monitor/Notification 四类 writer 分别定义 pass/fail 条件；即使 migration set 为 none 也必须执行。

**Global Authority Model:** test evidence 不授予 production exchange action。

**Chain Position:** `action_time_boundary`

**Live Enablement State Before:** 组件修复完成但未统一 exact-head 认证。

**Live Enablement State After:** exact SHA 成为 restore/deployment rehearsal candidate。

**Blocker Removed Or Reclassified:** 所有非-live工程 blocker 在 production-shaped 环境关闭。

**Per-Symbol / Per-Fact Acceptance:** 五个 StrategyGroup、22 lane、当前 Event Specs impact-covered；双仓位 asset-neutral matrix。

**Stop Condition:** schema fingerprint 不等、多个 winner、pending Claim 漏算/双算、release/Claim lost update、projection version 回退、任一 cap 被隐藏或绕过、deadline 后仍产生后续 side effect、readmodel drift、performance/file/retention risk 非 clear。

**Capability Unlocked:** shadow restore 和部署演练。

**Next Engineering Bottleneck:** backup/restore/rollback proof。

**Rehearsal/Simulation Boundary:** disposable PG + fake gateway；exchange writes=0。

**Tests:** focused → integration → full-chain → relevant regression → schema/performance audits。

**Done When:** exact SHA、test counts、fingerprints、plans、latency、file-I/O 结果写入 Completion Record。

**Hard Stop:** SQLite、mock SQL 或手工 schema 代替真实 migration chain。

## 17. T12 — Restore And Deployment Rehearsal

### 17.1 Task Packet

**Task ID:** `P0-ACH-T12`

**Goal:** 从 production-shaped backup 恢复 shadow PostgreSQL，验证 forward migration、data convergence、previous-application compatibility class 和失败恢复路径。

**Why:** 当前 deployment journal 没有形成已证明可用的数据库 backup/restore 闭环；forward-only migration 不能只靠理论 rollback。

**Allowed surfaces:** shadow DB、official backup/restore tooling、candidate migration bundle、data convergence services、previous release readonly/startup compatibility、previous writer compatibility test under shadow Writer Fence、deploy dry-run。

**Forbidden actions:** production mutation、manual SQL、丢弃新事件的整库 rollback、exchange write。

**Requirements:**

1. snapshot checksum 与 `pg_restore --list`/等价验证。
2. restore 到隔离 shadow DB。
3. apply candidate migration bundle if any。
4. run T11 full certification。
5. `previous_code_readonly_compatible` 必须证明 previous exact release 在 Writer Fence 下 startup/health/current-readmodel 正确且 DML=0、DDL=0、exchange write=0。
6. 按 Entry/Action-Time、Protection/Reconciliation、Current Projection、Monitor/Notification 四类分别执行 writer compatibility；只有四类全部通过才输出 `previous_code_write_compatible=true`。
7. data convergence service dry-run/apply 在 shadow 幂等。
8. migration failure 能恢复 pre-change shadow state。
9. 若只有 readonly compatible，rollback class 固定为 `code_rollback_readonly_only`：Writer Fence 保持、previous Entry/Current writer 禁用、Protection/Reconciliation 仅在该类别单独通过且保护已有仓位所需时运行、schema forward、fail closed + forward-fix。
10. candidate writer 产生新事实后，runbook 禁止整库 rollback 和 schema downgrade。
11. release manifest 包含 restore point、schema capability、四类 writer compatibility、compatibility floor 和 rollback class。

**Global Authority Model:** restore rehearsal 不改变 production truth 或 live policy。

**Chain Position:** `action_time_boundary`

**Live Enablement State Before:** code/schema certified，但恢复点未证明。

**Live Enablement State After:** candidate release 可恢复、可 forward-fix、previous-application compatibility class 已知。

**Blocker Removed Or Reclassified:** `schema_restore_not_certified`、`forward_migration_recovery_unknown`。

**Per-Symbol / Per-Fact Acceptance:** shadow 保留所有 Signal/Ticket/Lifecycle/Outcome provenance；current rows 收敛不丢失。

**Stop Condition:** restore checksum/fingerprint 不一致、数据 convergence 非幂等或 previous code 产生错误写入。

**Capability Unlocked:** Tokyo no-write canary。

**Next Engineering Bottleneck:** exact production generation acceptance。

**Rehearsal/Simulation Boundary:** shadow only；production/exchange writes=0。

**Tests:** restore、upgrade、previous-application compatibility、forward-fix runbook、data convergence twice；不执行生产 schema downgrade。

**Done When:** restore proof、四类 writer compatibility、`previous_code_readonly_compatible`、`previous_code_write_compatible` 和 rollback class 可机器重复；不执行生产 schema downgrade。

**Hard Stop:** 只创建 backup 文件但不 restore 验证。

## 18. T13 — Tokyo No-Exchange-Write Canary

### 18.1 Task Packet

**Task ID:** `P0-ACH-T13`

**Goal:** 部署 exact certified SHA 和必要 schema capability，在东京验证 current truth、服务、性能和历史收敛，同时禁止任何 exchange write。

**Why:** `multi_position_pre_live_certified` 必须证明生产机器与 shadow 结论一致，但不需要强制市场或第二仓位交易。

**Allowed surfaces:** official Tokyo deploy path、remote `pg_dump -Fc`/checksum/restore-list and isolated restore verification、approved migration bundle、official convergence services、systemd units、readonly PG/forensics/ops health、正式 deployment-scoped new-entry maintenance/submit-disabled fence、application-role grant audit/apply、fake/disabled submit canary。

**Forbidden actions:** forced Signal/Ticket、FinalGate/Operation Layer调用、exchange write、policy/profile/sizing mutation、manual SQL、destructive cleanup。

**Requirements:**

1. exact SHA、branch、source digest、migration head、graph checksum、schema fingerprint 一致。
2. 生产 migration 前创建远端 custom-format PG dump，记录 checksum、`pg_restore --list`/等价结果、可用磁盘、dump/restore/upgrade 耗时和保留位置。
3. 将该 exact dump 恢复到隔离 shadow DB，并复跑 candidate upgrade/fingerprint；`deploy_backup=false` 或仅有未验证 dump 直接停止。
4. 若 `role_topology_decision` 为 `credential_or_secret_change_required` 或 `role_topology_unknown`，在任何 production migration/grant 前以 `blocked_owner` 停止；不得在 T13 创建临时凭据。
5. 部署前启用正式、可审计、可恢复的 new-entry maintenance/submit-disabled fence；observation 和已有 position lifecycle/reconciliation 继续运行。
6. Writer Fence receipt 有效；lifecycle **entry mutation capability** 在 canary 内 disabled，已有仓位 protection/reconciliation capability 保持；canary 前后 mutation sentinel 不变。
7. fence 状态进入 release/PG audit lineage；任一异常保持 `failed_contained`，canary 结束后 fence 继续启用，等待后续 R1B 决策。
8. backend、watcher、monitor、lifecycle timer 正常。
9. application runtime 无 `create_all()` 能力；application identity 无 schema DDL、managed object ownership 或 membership/`SET ROLE`/default-privilege 绕过能力，且有恢复 grant/owner runbook。
10. 22/22 coverage 与 detector current/reducer 一致，或每 lane 有 exact technical blocker。
11. Account Current 对东京当前实际 occupancy 与 exchange/account/lifecycle truth 一致；完整 0/1/2 matrix 由 T10/T11 证明。
12. current occupancy 同时核对 active ExposureEpisode、effective pending Claim/Reservation、active hold/freeze、unresolved command/worker lease 和 exchange position/open-order truth；同一 exposure ownership 不得由 Claim + Exposure 双计。
13. 即使 first blocker 为 position cap，也必须分别输出并核验 portfolio held risk/limit、cluster held risk/limit、initial + pending margin/limit、position slots/limit。
14. historical Invocation/core Order/runtime rows 先 dry-run，再由正式 service 幂等收敛。
15. current issues 与 historical warnings 分离；notification 无假 Owner intervention/recovery。
16. no-signal file writes=0；Action-Time/Watcher/PG/log/disk/retention 在预算内。
17. canary exchange write count=0。
18. 生成 `multi_position_pre_live_certified` 或一个 exact blocker 结论。

**Global Authority Model:** deploy 不授予新 live scope；真实 action 仍等待自然事件、官方 gates，以及后续 R1B 对 new-entry fence 的明确释放。

**Chain Position:** `action_time_boundary`

**Live Enablement State Before:** local/shadow certified，Tokyo 仍运行旧 generation。

**Live Enablement State After:** Tokyo pre-live certified，new-entry fence 保持启用；下一步是独立 R1B natural live calibration 决策。

**Blocker Removed Or Reclassified:** 关闭 machine-generation、schema/current drift 和部署恢复不确定性。

**Per-Symbol / Per-Fact Acceptance:** 五 StrategyGroup、22 lane、真实 Account Current、current lifecycle/hold/position facts。

**Stop Condition:** migration/fingerprint drift、service unhealthy、current ownership unknown、DDL role不符、任何 exchange effect。

**Capability Unlocked:** 后续自然信号下的真实双仓位校准。

**Next Engineering Bottleneck:** R1B Natural Live Lifecycle Calibration。

**Rehearsal/Simulation Boundary:** Tokyo production machine、no-exchange-write canary。

**Tests:** postdeploy readonly verify、ops health、forensics、PG invariants、service journal、file/performance audit。

**Done When:** exact production acceptance matrix 全部通过，`forbidden_effects` 全 false，new-entry fence 仍可审计地保持启用。

**Hard Stop:** 需要真实订单才能证明工程正确，或 canary 产生任何 exchange write。

## 19. 测试分层与命令

实际文件名在 T00/T01 后冻结。最低分层：

```bash
pytest -q tests/unit/test_pg_migration_identifier_names.py \
  tests/unit/test_action_time_invocation.py \
  tests/unit/test_account_capacity_claim.py \
  tests/unit/test_account_capacity_claim_persistence.py

pytest -q tests/unit/test_server_product_state_refresh_sequence.py \
  tests/unit/test_pg_promotion_action_time_lane_materialization.py \
  tests/unit/test_lifecycle_occupancy.py \
  tests/unit/test_runtime_signal_forensics.py

pytest -q tests/unit/test_runtime_active_observation_monitor.py \
  tests/unit/test_strategy_live_candidate_pool.py \
  tests/unit/test_strategygroup_runtime_goal_status.py \
  tests/unit/test_tokyo_runtime_ops_health_lifecycle.py

pytest -q tests/integration/test_account_capacity_postgres.py \
  tests/integration/test_account_capacity_hot_path_scale.py \
  tests/integration/test_asset_neutral_account_risk_full_chain.py \
  tests/integration/test_dual_position_account_risk_remediation_full_chain.py

pytest -q tests/integration/test_action_time_multi_signal_postgres.py \
  tests/integration/test_multi_position_pre_live_postgres.py \
  tests/integration/test_runtime_schema_fingerprint_postgres.py

python3 scripts/audit_production_runtime_file_io.py --fail-on-risk
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
python3 scripts/validate_current_docs_authority.py
```

不存在的新增测试文件由对应 Task 创建。长全套回归只在 T11 exact-head gate 执行，不在早期 Task 反复运行。

## 20. 部署前验收矩阵

| Gate | 必须结果 |
| --- | --- |
| **Schema Truth** | Alembic sole owner；clean/prod fingerprint 等价；001–140 immutable |
| **Migration** | `none` 或最小 capability bundle；DDL/data/control 分离 |
| **Decimal/Claim** | canonical hash/insert/reload/retry/FinalGate 一致 |
| **Signal/Invocation** | 每 Signal 有 Invocation/result；无 handoff loss |
| **Arbitration** | 同 domain 唯一 winner；所有 loser 明确终态 |
| **Dual Position** | protected+pending=2/2、third requester pre-Ticket 阻止、claim-process exit 守恒、release-vs-claim 线性化、simultaneous close+claim、pending→Exposure 不双计、slot/portfolio/cluster/margin 独立 cap、exactly-once release 全通过 |
| **Lifecycle** | 两 Ticket 的 protection/runner/reconciliation/settlement 不串线 |
| **Detector** | 每 lane/candle 一个 decision；Signal 不脱离 decision |
| **Projection** | Candidate/Goal/Monitor/Ops/Forensics 同一 first blocker |
| **Legacy** | 旧 promotion/order/current authority 不再生产可达 |
| **Performance** | Action-Time `global_deadline` 强制执行；deadline 后零后续 authority side effect；watcher headroom ≥20%；hot path indexed |
| **File/Disk** | no-signal file writes=0；retention registry 无 hard；journald/release/backup 阈值与 prune owner 可机器验证 |
| **Recovery** | backup restore、forward migration、readonly/write compatibility class 通过；仅 readonly 时 Writer Fence + forward-fix |
| **Safety** | unknown outcome、missing protection、duplicate submit、wrong identity 全 fail closed |

## 21. Commit 与版本管理

| Task | 建议 commit subject |
| --- | --- |
| T00 | `test: freeze multi-position pre-live red evidence` |
| T01-T02 | `fix: establish single postgres schema authority` |
| T03 | `refactor: centralize runtime semantic invariants` |
| T04 | `fix: canonicalize persisted account capacity claims` |
| T05A | `fix: conserve every signal invocation outcome` |
| T05B | `fix: arbitrate one deterministic action-time winner` |
| T05C | `refactor: enforce typed action-time deadline coordinator` |
| T06 | `fix: converge multi-position lifecycle occupancy` |
| T07 | `fix: bind detector decisions and signals atomically` |
| T08 | `fix: unify current runtime health and incident truth` |
| T09 | `refactor: retire legacy runtime authority paths` |
| T10-T11 | `test: certify dual-position postgres full chain` |
| T12 | `test: classify postgres restore and previous-code compatibility` |
| T13 docs | `docs: certify tokyo multi-position pre-live canary` |

要求：

- 一个 migration writer；
- 核心 execution/current 文件串行 review；
- 每个 commit 可独立回退代码，schema forward-only；
- 不提交 `output/**`、runtime reports、`.agents/skills/skill-creator/`；
- 已部署 migration 文件不得改写。

## 22. Owner 确认点

实施本计划需要一次 Owner 确认，授权：

1. 在当前分支执行 T00-T12 工程和 shadow certification；
2. 根据 Schema Truth Gate 决定是否创建最小 migration bundle；
3. 通过官方路径执行 T13 东京 no-exchange-write canary；
4. 使用正式 projector/service 幂等收敛可证明的历史 current rows；
5. 停止在 `multi_position_pre_live_certified`，不在本 Program 强制真实第二仓位交易。

该确认不改变 policy/profile/sizing，也不授权 forced order、FinalGate/Operation Layer bypass、transfer、withdrawal、credential mutation 或 destructive cleanup。

若 T01 得出 `credential_or_secret_change_required`，上述一次确认不覆盖该变化；Program 状态必须保持 `blocked_owner`，直到获得单独的生产 credential/secret 授权。

## 23. Completion Record

当前状态：**T01–T02、T04、T06 的首批代码收敛与 T05C deadline fence 已完成本地验证；真实 PostgreSQL certification、shadow restore、Tokyo role topology 和 no-write canary 尚未执行。**

### 23.1 已完成的本地实现记录（部署前）

| 项目 | 结果 | 仍需的 Gate |
| --- | --- | --- |
| **Schema Authority** | Alembic 同时加载 `Base.metadata` 与 `PGCoreBase.metadata`；PG runtime `create_all()` 已移除，启动改为 head/capability fail-closed | disposable PostgreSQL `001 → 141` 与 `140 → 141` fingerprint 认证；Tokyo role topology readonly audit |
| **Capability Bundle** | **`141_schema_truth_capability_bundle`** 已作为最小候选：Budget Current account/profile 唯一性、immutable typed detector identity、Exposure/Command/Hold canonical NettingDomainKey backfill | 实际 PG upgrade；duplicate/current collision negative；production backup/shadow restore |
| **Decimal / Claim** | `Numeric(36,18)` canonicalization 已用于 hash、insert 与 reload compare；FinalGate 查询保持 policy version field | PostgreSQL roundtrip 和并发 Claim matrix |
| **Action-Time Deadline** | 以 monotonic elapsed 计算 30 秒及 source expiry 的最短 deadline；deadline 后不再启动 Ticket、FinalGate 或 handoff child step | child PG timeout/statement timeout 从 remaining budget 派生；真实 PG side-effect=0 matrix |
| **Detector Decision** | full typed identity 下重复 candle no-op，payload drift fail-closed；旧 `ON CONFLICT DO UPDATE` 已删除 | detector/Signal 同事务或 durable outbox，22-lane PG proof |
| **Netting Domain** | Exposure、Ticket Command、Hold 使用同一 `account|instrument|position_mode|bucket` identity；domain command mismatch fail-closed | production historical row dry-run 与 dual-position lifecycle matrix |

本地已通过的 focused tests：

```text
tests/unit/test_pg_migration_identifier_names.py
tests/unit/test_account_capacity_claim.py
tests/unit/test_account_capacity_claim_persistence.py
tests/unit/test_account_budget_current.py
tests/unit/test_account_exposure_current.py
tests/unit/test_ticket_bound_exchange_snapshot_provider.py
tests/unit/test_ticket_bound_exchange_command.py
tests/unit/test_runtime_active_observation_monitor.py
tests/unit/test_action_time_deadline.py
tests/unit/test_server_product_state_refresh_sequence.py
```

已在一次性本地 **PostgreSQL 16** 容器完成以下 disposable certification，容器已删除：

```text
tests/integration/test_account_truth_convergence_postgres.py  3 passed
tests/integration/test_account_capacity_postgres.py           3 passed
tests/integration/test_runtime_causal_integrity_postgres.py -k current_head  1 passed
```

其中完整认证 harness 使用官方 `001 → 106 → deterministic foundation seed → 141` 路径，并动态读取 Alembic current head；`init_pg_core_db()` capability startup 也已在 PostgreSQL 上通过。直接对绝对空库执行 `alembic upgrade head` 会在冻结历史 **revision 107** 停止，因为其错误地依赖 CPM authority seed；这是已知的 historical DDL/seed 混合债务，不修改 `001–140`。当前认证基线必须显式使用上述 deterministic seed path，P0-ACH 稳定后再生成认证 template/baseline。东京生产、migration apply、role/grant 变更和 Writer Fence 解除均未执行。

### 23.2 规划文档校验基线

| 校验 | 当前结果 |
| --- | --- |
| Current docs authority | `current_docs_authority_valid`，85 个 current docs |
| Output artifact scope | `output_artifact_scope_valid` |
| Production runtime file-I/O audit | `suspicious_runtime_file_authority=0`、`frequent_report_write=0` |
| Diff / whitespace | `git diff --check` 通过；两份新文档无 trailing whitespace |
| Migration identifier test | **RED retained**：3 项中 2 passed、1 failed；真实 head `140`，测试仍硬编码 `136` |

Migration identifier RED 属于 T00/T02 的明确工程输入，本轮只完成设计和执行计划，不通过顺手改测试掩盖 Schema Truth Gate。

实施后必须记录：

- commits 与 exact SHA；
- Schema Truth Gate 决策；
- migration capability bundle 或 `no_migration_required`；
- `001–140` checksum 与 candidate head；
- clean/prod schema fingerprint；
- focused/integration/full regression counts；
- dual-position 0/1/2 matrix；
- EXPLAIN/latency/row-growth/file-I/O 结果；
- restore、readonly/write compatibility class 与 forward-fix rollback class；
- Tokyo no-write canary、service/current truth 和 forbidden effects；
- final chain position 与下一 R1B action。
