---
title: P0_ACCOUNT_TRUTH_CONVERGENCE_AND_FAILED_SUBMIT_CAPACITY_CONSERVATION_IMPLEMENTATION_PLAN
status: DEPLOYED_COMPONENT_BASELINE
authority: docs/current/P0_ACCOUNT_TRUTH_CONVERGENCE_AND_FAILED_SUBMIT_CAPACITY_CONSERVATION_IMPLEMENTATION_PLAN.md
design: docs/current/P0_ACCOUNT_TRUTH_CONVERGENCE_AND_FAILED_SUBMIT_CAPACITY_CONSERVATION_DESIGN.md
baseline_branch: codex/budget-model-review-20260714
baseline_head: 386cc3d761f17231a6c35d2bc96b347153cbd907
production_head: 386cc3d761f17231a6c35d2bc96b347153cbd907
production_migration_head: 140
planned_migration_head: 140
owner_policy_change: none
exchange_write_authority: unchanged
---

# P0 Account Truth Convergence And Failed-Submit Capacity Conservation Implementation Plan

> **Current authority note:** T00-T11 are deployed component history at release
> `386cc3d7` / migration `140`. Any new schema、multi-signal、dual-position or runtime
> semantic work must follow P0-ACH rather than reopening this plan.

## 1. 执行目标

**目标是关闭“真实空仓但 PG 2/2、每个新 Ticket 又在本地订单注册失败”的完整问题类，并恢复可验证的真实交易技术能力。**

本计划不得以手工 SQL、删除历史、缩小仓位/杠杆、关闭策略、强制信号或绕过官方执行链作为完成方式。

## 2. 基线与完成状态

### 2.1 当前基线

| **项目** | **值** |
| --- | --- |
| 当前分支 | `codex/budget-model-review-20260714` |
| 当前 HEAD | `881f192b88e32610a6e27af0eb0e6df6cf1d1bcf` |
| 东京 HEAD | 同上 |
| 东京 migration | `139` |
| 下一 migration | `140` |
| 当前 exchange truth | 0 position / 0 regular order / 0 algo order |
| 当前错误容量 | 2 个 consumed Reservation / 2 个 reserved Exposure / 2/2 slots |
| 当前首阻塞 | `action_time_boundary_not_reproduced` |

### 2.2 完成定义

计划完成必须同时满足：

1. 生产长度 Ticket/Signal/Command identity 可注册本地 Order；
2. terminal pre-dispatch failure 可自动、安全、幂等释放容量；
3. active policy 账户在没有活跃 Ticket 时仍刷新 Current；
4. 账户事实事务与 candidate claim 事务分离；
5. Budget/Owner/monitor 语义一致；
6. PostgreSQL、并发、full-chain、文件 I/O 门禁通过；
7. 东京部署后当前两条错误占用通过正式服务收敛；
8. 下一次自然 eligible signal 不再被历史假槽位或本地 Order schema 阻止。

## 3. 任务顺序与依赖

| **顺序** | **任务** | **依赖** | **主要产物** |
| ---: | --- | --- | --- |
| **T00** | RED 生产因果证据 | 无 | 可重复失败测试 |
| **T01** | Local Order Lineage V2 | T00 | migration 140、typed builder、真实身份注册 |
| **T02** | Terminal pre-dispatch convergence | T00 | snapshot-aware release、completed lifecycle |
| **T03** | Independent Account Current owner | T02 | active-policy refresh、事务 A/B 分离 |
| **T04** | Budget 与 Owner 语义一致 | T03 | 2/2 正确状态 |
| **T05** | Coverage/monitor 统一 | T00 | shared health predicate |
| **T06** | 生产 repair 与 deploy 集成 | T01-T05 | 正式自动修复路径、部署断言 |
| **T07** | PostgreSQL 并发与负面测试 | T01-T06 | race/unknown/exposure safety proof |
| **T08** | Full-chain production-shaped certification | T07 | integrated no-exchange proof |
| **T09** | Tokyo deploy/canary | T08 | exact SHA + migration 140 |
| **T10** | Tokyo controlled convergence | T09 | 当前 2/2 -> 0/2 |
| **T11** | 自然信号后续验收 | T10 | live-path calibration，不阻塞工程闭环 |

核心执行、数据库 migration 和交易入口文件不得并行修改。T05 可在 T01-T03 之后独立实施，但必须在 T08 前合并到同一 exact HEAD。

## 4. 全局执行约束

### 4.1 Global Authority Model

```text
Owner controls policy.
System executes process.
Tradeability Decision answers can-trade.
Runtime Safety State answers live-submit safety.
Review updates strategy governance.
```

### 4.2 通用 Hard Stop

任一任务发现以下情况立即停止该任务：

- 需要扩大 live profile、symbol、side、leverage、notional 或并发上限；
- 需要 FinalGate 或 Operation Layer 绕过；
- 需要在未知 exchange outcome 下释放容量；
- 需要网络 I/O 持有 PG lock；
- 需要手工删除生产历史或破坏性 migration；
- 需要新增生产 JSON/Markdown/YAML/JSONL authority；
- 需要凭据变更、转账或提现；
- 需要修改本计划 Forbidden Files 之外的核心文件而未重新审查任务边界。

## 5. T00 — Freeze Production-shaped RED Evidence

### 5.1 Task Packet

**Task ID:** `ATC-FSC-T00`

**Goal:** 将当前生产故障冻结为真实 PostgreSQL、生产长度 identity 和完整状态组合的 RED 测试。

**Why:** 当前组件测试使用短 ID、fake repository 和拆散状态，无法证明生产因果链。

**Allowed files:**

- `tests/unit/test_ticket_bound_protected_submit_api.py`
- `tests/unit/test_budget_reservation_transition.py`
- `tests/unit/test_account_risk_lifecycle_reprojection.py`
- `tests/unit/test_account_budget_current.py`
- `tests/unit/test_ticket_bound_lifecycle_global_deadline.py`
- `tests/unit/test_tokyo_runtime_ops_health.py` 或现有对应 ops health 测试
- 新的 scoped PostgreSQL integration test

**Forbidden files:** `src/**`、`scripts/**`、migrations、deploy files。

**Requirements:**

1. 使用 148 字符 Ticket ID 和生产 `orders` schema 复现 SQLSTATE `22001`。
2. 先创建 consumed Reservation，再投影 reservation-only Exposure，再证明当前 reclaim 返回 0。
3. 证明 `prepared_scopes=[]` 时 active policy 不刷新。
4. 证明 2/2 Budget 当前仍 incorrectly allowed。
5. 证明 `covered/healthy/current` 被 ops SQL 误报。

**Chain Position:** `action_time_boundary`

**Live Enablement State Before:** fresh signal 可到 Ticket/submit prepare，但本地注册和容量收敛不可靠。

**Live Enablement State After:** blocker 被机器可重复证明，尚未移除。

**Blocker Removed Or Reclassified:** 将宽泛的容量阻塞精确化为 `action_time_boundary_not_reproduced` 下的 identity schema、terminal claim convergence 和 current refresh 缺陷。

**Per-Symbol / Per-Fact Acceptance:** BTCUSDT、SOLUSDT 历史状态组合与生产查询一致；长 ID 测试在 PostgreSQL 上失败。

**Stop Condition:** 所有 RED case 都因预期原因失败，而不是 fixture/schema 缺失。

**Capability Unlocked:** 为后续实现提供不可回退验收基线。

**Next Engineering Bottleneck:** Local Order Lineage V2。

**Rehearsal/Simulation Boundary:** disposable PostgreSQL；不调用 exchange gateway。

**Tests:** 只运行新增/修改的 RED tests，保存失败原因到测试输出，不写 repo 报告文件。

**Done When:** SQLSTATE、self-lock、no-scope refresh、2/2 flag、healthy coverage 五类失败均可重复。

**Hard Stop:** 使用 SQLite 代替 PostgreSQL 长度验证，或用人工 fixture 直接跳过生产 builder/repository。

## 6. T01 — Implement Ticket-bound Local Order Lineage V2

### 6.1 Task Packet

**Task ID:** `ATC-FSC-T01`

**Goal:** 消除 Ticket/Signal Evaluation 身份混用，保证 durable Command 在交易所 dispatch 前可注册唯一、可追溯的本地 Order。

**Why:** 当前每个生产长度 Ticket 都可能在 `orders.signal_evaluation_id` 溢出。

**Allowed files:**

- `src/domain/models.py`
- `src/infrastructure/pg_models.py`
- `src/infrastructure/pg_order_repository.py`
- 新的 `src/application/action_time/ticket_bound_local_order.py`
- `src/interfaces/api_trading_console.py`
- migration `140`
- focused order/protected-submit tests

**Forbidden files:** exchange gateway placement semantics、FinalGate、Operation Layer、policy/sizing、strategy detectors。

**Requirements:**

1. migration 140 增加 ticket-bound Order lineage columns、unique/check/FK contract。
2. ORM identity lengths 对齐 192；历史 rows 不重写语义。
3. typed builder 从 Command + Ticket 构造 Order。
4. `Order.signal_id=ticket.signal_event_id`。
5. `signal_evaluation_id=NULL`，除非存在真实 evaluation ID。
6. 删除两个 `ticket_id -> signal_evaluation_id` call site，不保留 fallback。
7. 注册后在 dispatch 前执行 repository round-trip identity assertion。
8. 捕获并分类 SQLSTATE/constraint，保持 secrets masked。

**Chain Position:** `action_time_boundary`

**Live Enablement State Before:** command prepared，local order registration schema invalid。

**Live Enablement State After:** production-length Ticket/Signal/Command/Order identity 可在 PG 注册，仍无 exchange write。

**Blocker Removed Or Reclassified:** 移除 `local_order_registration_schema_invalid`。

**Per-Symbol / Per-Fact Acceptance:** BTCUSDT 与 SOLUSDT 的 148 字符 Ticket fixture 均注册成功；Signal Event、Ticket、Command、instrument、episode 一致。

**Stop Condition:** 任一新 ticket-bound Order 缺少独立 lineage 或 repository round-trip 不一致。

**Capability Unlocked:** durable command 可安全到达 dispatch 边界。

**Next Engineering Bottleneck:** terminal pre-dispatch capacity convergence。

**Rehearsal/Simulation Boundary:** gateway 使用 fail-if-called fake；exchange call count 必须为 0。

**Tests:** unit + real PostgreSQL schema + migration upgrade/downgrade compatibility fixture。

**Done When:** T00 长 ID RED 转绿，且旧错绑路径 `rg` 为 0。

**Hard Stop:** 仅扩容 `signal_evaluation_id`，或把 Ticket ID 政名后继续写入 Signal Evaluation 字段。

## 7. T02 — Close Terminal Pre-dispatch Capacity Conservation

### 7.1 Task Packet

**Task ID:** `ATC-FSC-T02`

**Goal:** 使用新鲜完整账户快照安全释放 terminal pre-dispatch Claim，并原子关闭 Reservation/Exposure/Budget/Lifecycle。

**Why:** 当前 Reservation 与其派生 Exposure 形成自我锁死。

**Allowed files:**

- `src/application/action_time/budget_reservation_transition.py`
- `src/application/action_time/account_risk_reprojection.py`
- `src/application/action_time/account_exposure_current.py`
- `src/application/action_time/lifecycle_safety_core.py`
- `src/application/readmodels/owner_projection.py`
- focused unit/integration tests
- migration 140 的 lifecycle status constraint 部分

**Forbidden files:** post-submit force-close、protection cancellation、exchange mutation、直接生产 SQL repair。

**Requirements:**

1. 新增 snapshot-aware terminal reconciliation service/function。
2. 只接受 commands 全部 `reconciled_absent`；`prepared` 不足以释放。
3. 忽略 exact same Claim 派生的 reservation-only Exposure。
4. 对真实 position/open order/unknown identity/dispatch started/outcome unknown fail closed。
5. 同事务完成 Reservation released、Exposure flat、Budget refresh、Lifecycle `presubmit_reconciled_absent`。
6. repeated tick 不重复 event。
7. `submit_failed` 历史 attempt 与 Ticket 证据不删除。

**Chain Position:** `action_time_boundary`

**Live Enablement State Before:** terminal failed Ticket 永久占槽。

**Live Enablement State After:** 已证明 absent 的 pre-dispatch Ticket 自动完成并归还容量。

**Blocker Removed Or Reclassified:** 移除 `terminal_presubmit_capacity_not_converged`；unknown outcome 保持 `hard_safety_stop`。

**Per-Symbol / Per-Fact Acceptance:** BTC/SOL flat + reconciled_absent 释放；任一真实 exposure negative 保持 consumed。

**Stop Condition:** 释放判断仍依赖 reservation-only Current row，或 release 与 reprojection 可部分提交。

**Capability Unlocked:** 假槽位可自动恢复。

**Next Engineering Bottleneck:** active-policy independent refresh。

**Rehearsal/Simulation Boundary:** typed snapshot only；不执行 cancel/close/place。

**Tests:** self-lock RED、unknown outcome、real position、regular/algo order、idempotency、atomic rollback。

**Done When:** Claim -> reserved Exposure -> terminal absent -> released -> flat -> next Claim 的真实 PostgreSQL full-chain 通过。

**Hard Stop:** 以“交易所账户整体为空”替代 instrument/episode ownership 验证，或忽略 unknown orders。

## 8. T03 — Establish Independent Active-policy Account Current Owner

### 8.1 Task Packet

**Task ID:** `ATC-FSC-T03`

**Goal:** 让账户 Current 按 active policy 和新鲜快照刷新，不依赖 active Ticket、candidate 成功或 lifecycle 枚举变化。

**Why:** 当前空仓真相无法自动覆盖陈旧 2/2 Current。

**Allowed files:**

- `scripts/run_ticket_bound_lifecycle_maintenance_once.py`
- `src/application/action_time/account_risk_reprojection.py`
- `src/application/action_time/lifecycle_maintenance_scheduler.py`
- `src/application/action_time/ticket_materialization_sequence.py`
- `scripts/materialize_action_time_ticket_sequence.py`
- deploy service timeout only if measured need exists
- focused cadence/deadline tests

**Forbidden files:** 新 timer、第二 Current projector、网络 I/O under lock、runtime file output。

**Requirements:**

1. 从 active policy rows 选择 account/profile/exchange scope，即使 `prepared_scopes=[]`。
2. 每账户每 tick 只抓一个完整快照，ticket maintenance 复用。
3. 先提交 Account Truth transaction，再开始 candidate transaction。
4. 两事务统一 lock order：Policy Current -> Budget Current -> Reservation/Exposure。
5. post-submit tick 每个完整快照都可刷新 Current；semantic change 只控制 audit event。
6. snapshot 失败不写假 flat；Current 过期后 fail closed。
7. 维持 28 秒 global deadline、36 秒 command timeout、45 秒 systemd timeout，除非测量证明必须调整。

**Chain Position:** `action_time_boundary`

**Live Enablement State Before:** Current refresh 依赖 Ticket/lifecycle。

**Live Enablement State After:** active account policy 始终有新鲜 Current；candidate blocker 不回滚账户事实。

**Blocker Removed Or Reclassified:** 移除 `account_current_refresh_not_independent`。

**Per-Symbol / Per-Fact Acceptance:** 无活跃 Ticket 的空仓账户刷新到 0/2；candidate 被其他事实阻止后 source snapshot 仍是新值。

**Stop Condition:** 新 refresh 增加重复 timer、每 Ticket 重复 5 个 GET，或网络 I/O 位于事务内。

**Capability Unlocked:** 账户 Current 自愈与稳定容量仲裁。

**Next Engineering Bottleneck:** Budget/Owner semantics。

**Rehearsal/Simulation Boundary:** signed GET read-only；PG Current writes only。

**Tests:** no-scope refresh、snapshot dedupe、deadline、lock order、candidate rollback isolation、no-change event growth。

**Done When:** 每个完整快照更新 Current validity，且 steady-state 不新增 audit row/file。

**Hard Stop:** 通过延长 stale window 掩盖没有刷新，或把 monitor cache 当交易安全事实。

## 9. T04 — Align Budget Current And Owner Product Semantics

### 9.1 Task Packet

**Task ID:** `ATC-FSC-T04`

**Goal:** 统一 Budget、capacity decision 和 Owner readmodel 对满仓、技术不可用与需要介入的解释。

**Why:** 当前 `2/2 + new_entry_allowed=true` 违反字段语义；直接改 false 又会被旧 readmodel 误判为需介入。

**Allowed files:**

- `src/application/action_time/account_budget_current.py`
- `src/application/action_time/account_capacity_reservation.py`
- `src/application/readmodels/account_risk_owner_state.py`
- related tests

**Forbidden files:** policy values、candidate sizing math、Owner scope expansion。

**Requirements:**

1. 将 slots、portfolio risk、margin capacity 纳入账户级 blocker。
2. 2/2 时 `new_entry_allowed=false`、`first_blocker=max_concurrent_positions_reached`、`reconciliation_state=matched`。
3. Owner readmodel 先判断 reconciliation/unknown，再判断正常满仓。
4. candidate-specific cluster/instrument/quantity blocker 保持在 capacity decision。
5. projection version 只在 capacity semantics 变化时递增；source freshness 每次更新。

**Chain Position:** `action_time_boundary`

**Live Enablement State Before:** Current 与 decision 语义分裂。

**Live Enablement State After:** Current、Owner 与 capacity decision 一致。

**Blocker Removed Or Reclassified:** 移除 `account_budget_entry_semantics_inconsistent`。

**Per-Symbol / Per-Fact Acceptance:** 0/2 可接收、1/2 可接收、2/2 正常满仓、unknown exposure 暂不可用四类状态准确。

**Stop Condition:** 满仓被归类为 Owner intervention，或 unknown exposure 被归类为正常等待。

**Capability Unlocked:** 可信 Owner 产品状态和机器 capacity gate。

**Next Engineering Bottleneck:** monitor health consistency。

**Rehearsal/Simulation Boundary:** deterministic domain/readmodel tests only。

**Tests:** Budget projection、owner state、capacity reservation、dual-position release acceptance。

**Done When:** 删除/改写固定 `2/2 allowed=true` 的旧测试，并覆盖四类产品状态。

**Hard Stop:** 通过改字段名称但保留同一矛盾，或把正常满仓升级为 hard safety stop。

## 10. T05 — Unify Runtime Coverage And Historical Failure Monitoring

### 10.1 Task Packet

**Task ID:** `ATC-FSC-T05`

**Goal:** 让 Action-Time、candidate、forensics、ops health 与 Owner monitor 使用同一个 coverage/lifecycle current predicate。

**Why:** 当前 22/22 healthy coverage 被 ops 脚本统计为 0；历史 submit_failed 又污染当前状态。

**Allowed files:**

- shared domain/readmodel health predicate module
- `scripts/ops/check_tokyo_runtime_ops_health_once.py`
- `src/application/action_time/promotion_action_time_lane.py`
- `src/application/runtime_signal_forensics.py`
- `src/application/readmodels/strategy_live_candidate_pool.py`
- `src/application/readmodels/owner_projection.py`
- focused tests

**Forbidden files:** detector logic、watcher strategy parameters、new report artifacts。

**Requirements:**

1. coverage predicate 接受 `healthy/ok/active`，同时要求 covered/current/fresh。
2. 所有消费者复用，不复制 set literal。
3. `presubmit_reconciled_absent` 为 completed，不进入 lifecycle attention。
4. 历史 unresolved failure 仍保留审计，但不把全局系统永久标为 unavailable。
5. monitor 输出区分真实 position slots 与 stale reservation-only slots。

**Chain Position:** `action_time_boundary`

**Live Enablement State Before:** 实际 coverage 健康但监控误报。

**Live Enablement State After:** 22/22 coverage 在所有产品面一致。

**Blocker Removed Or Reclassified:** `detector_not_attached` 误报移除；真实 coverage failure 仍精确分类。

**Per-Symbol / Per-Fact Acceptance:** 22 个 current rows 全部一致 healthy；failed/degraded/stale negatives 仍阻止。

**Stop Condition:** ops 与 Action-Time 仍有不同 liveness 集合，或历史完成 failure 仍触发 current attention。

**Capability Unlocked:** 可信部署验收和 Owner 当前状态。

**Next Engineering Bottleneck:** deploy/repair integration。

**Rehearsal/Simulation Boundary:** PG/readmodel only；无 watcher parameter change。

**Tests:** shared predicate matrix、ops SQL、candidate pool、forensics、Owner projection。

**Done When:** 东京形态 fixture 得到 accepted coverage `22`，旧 ops `0` 断言被移除。

**Hard Stop:** 把 freshness/current 条件删除，只按字符串 healthy 放行。

## 11. T06 — Integrate Formal Production Repair And Deploy Assertions

### 11.1 Task Packet

**Task ID:** `ATC-FSC-T06`

**Goal:** 将 account truth convergence 纳入正式 runtime/deploy 路径，使生产两条错误占用由同一服务自动修复。

**Why:** 只修代码但没有受控生产收敛与验收，系统仍保持 2/2。

**Allowed files:**

- existing lifecycle/account maintenance runner
- `scripts/plan_tokyo_runtime_governance_git_deploy.py`
- `scripts/tokyo_runtime_deploy_remote_state_machine.py`
- `scripts/verify_tokyo_runtime_governance_postdeploy.py`
- deploy/systemd existing lifecycle service/timer only if needed
- deploy verifier tests

**Forbidden files:** one-off raw SQL repair script、new timer、credential files、release report files in repo。

**Requirements:**

1. deploy verifier 目标 revision 更新为 140。
2. writer fence 下 migration 后执行 no-exchange local-order identity canary。
3. 恢复 watcher 前执行一次 account-truth refresh 并断言 current consistency。
4. repair 必须调用正式 service/state machine，不允许 SQL shortcut。
5. 生产断言包含 Reservation、Exposure、Budget、Lifecycle、Command、Attempt 和 exchange snapshot。
6. repair 失败时保持 writer fence 或停止新 ENTRY，不影响保护/退出恢复。

**Chain Position:** `action_time_boundary`

**Live Enablement State Before:** 本地修复未进入东京。

**Live Enablement State After:** exact SHA 可安全部署并自动收敛当前两条假容量。

**Blocker Removed Or Reclassified:** deployment-side `action_time_boundary_not_reproduced` 可进入认证。

**Per-Symbol / Per-Fact Acceptance:** BTC/SOL 两条历史 Ticket 分别满足 absent guard 并各释放一次。

**Stop Condition:** deploy 需要人工 UPDATE/DELETE，或 watcher 在 account current 验证前恢复。

**Capability Unlocked:** Tokyo controlled repair。

**Next Engineering Bottleneck:** concurrency/full-chain certification。

**Rehearsal/Simulation Boundary:** deploy canary 禁止 gateway.place_order；exchange reads only。

**Tests:** deploy plan/state machine/postdeploy exact revision and repair assertions。

**Done When:** dry-run plan、candidate release canary、contained failure rollback 均通过。

**Hard Stop:** deploy success 被误解释为 exchange-write authority。

## 12. T07 — Certify PostgreSQL Concurrency And Safety Negatives

### 12.1 Task Packet

**Task ID:** `ATC-FSC-T07`

**Goal:** 证明 account refresh、candidate claim、terminal repair 并发时不丢 Claim、不超槽位、不错误释放。

**Why:** 新事务分离必须用真实 PostgreSQL 锁和隔离语义证明。

**Allowed files:** PostgreSQL integration tests、test support、必要的锁顺序修复文件。

**Forbidden files:** SQLite-only concurrency proof、生产 DB destructive fixture。

**Requirements:**

1. refresh 与两个 candidate 并发，最终 slots 不超过 2。
2. terminal repair 与新 Claim 并发，旧 release 与新 active Claim 各计一次。
3. snapshot older than current Claim 不得覆盖 post-claim projection。
4. deadlock 重试必须 bounded，不能静默放行。
5. unknown outcome 永不释放。

**Chain Position:** `action_time_boundary`

**Live Enablement State Before:** 单线程逻辑正确，竞态未证明。

**Live Enablement State After:** PostgreSQL concurrency safety certified。

**Blocker Removed Or Reclassified:** 移除 `account_capacity_concurrency_not_certified`。

**Per-Symbol / Per-Fact Acceptance:** BTC、SOL、ETH 三候选矩阵最多两槽；旧 absent Ticket 可释放后由一个新候选占用。

**Stop Condition:** 测试依赖 sleep 猜时序、缺少 lock observation，或出现不确定 flaky 结果。

**Capability Unlocked:** integrated full-chain certification。

**Next Engineering Bottleneck:** T08。

**Rehearsal/Simulation Boundary:** disposable loopback PostgreSQL；无 exchange。

**Tests:** 重复至少 20 轮的 bounded concurrency matrix；fail-on-skip/xfail。

**Done When:** 无 deadlock、无 oversubscription、无 false release、无 lost update。

**Hard Stop:** 通过全局串行锁掩盖错误事务边界，或把 max positions 改大使测试通过。

## 13. T08 — Run Full-chain Production-shaped Certification

### 13.1 Task Packet

**Task ID:** `ATC-FSC-T08`

**Goal:** 在同一 exact HEAD 证明长 identity、Claim、Ticket、Command、Order、failure closure、next Claim 的完整因果链。

**Why:** 本事故正是组件绿色但组合失败。

**Allowed files:** tests/certification scripts that use PG/current services and in-memory typed fixtures only。

**Forbidden files:** JSON/Markdown evidence output、fake success result、short identity substitute。

**Requirements:**

1. 使用设计文档第 11.2 节完整链路。
2. PostgreSQL migration 从 139 -> 140。
3. 本地 Order 注册后 gateway fail-if-called 或 disabled gateway。
4. pre-dispatch failure 收敛后 next Claim 成功。
5. 运行 runtime file I/O audit、output artifact scope validator、targeted + full regression。
6. 所有 required PostgreSQL tests fail-on-skip/xfail。

**Chain Position:** `action_time_boundary`

**Live Enablement State Before:** 各组件通过，组合链未认证。

**Live Enablement State After:** 非执行 production-shaped action-time boundary reproduced。

**Blocker Removed Or Reclassified:** `action_time_boundary_not_reproduced` 在工程面关闭。

**Per-Symbol / Per-Fact Acceptance:** production-length SOR BTC/SOL fixture 与第三个不同 instrument candidate 通过。

**Stop Condition:** 任一链路阶段由手工 DB seeding 跳过正式 producer，或 file artifact 成为权威输入。

**Capability Unlocked:** Tokyo deployment GO candidate。

**Next Engineering Bottleneck:** T09 deployment。

**Rehearsal/Simulation Boundary:** no real exchange writes；不授予 Runtime Safety submit authority。

**Tests:** targeted、PostgreSQL、migration、deploy、full regression、performance/file I/O。

**Done When:** exact SHA 的全部门禁通过且工作区只有预期 tracked changes。

**Hard Stop:** broad suite green 但 required PostgreSQL test skipped。

## 14. T09 — Deploy Exact SHA To Tokyo And Run Canary

### 14.1 Task Packet

**Task ID:** `ATC-FSC-T09`

**Goal:** 使用正式东京 state machine 部署已认证 exact SHA，并在恢复 writer 前验证 migration、identity 与 account refresh。

**Why:** 本地绿色不等于生产路径恢复。

**Allowed files/state:** approved git-based Tokyo deploy、systemd control、read-only exchange query、migration 140、PG current writes from official service。

**Forbidden files/state:** manual rsync mutable release、raw SQL data repair、credential mutation、forced order。

**Requirements:**

1. release manifest、Git tree digest、SHA、migration 140 一致。
2. backend import and schema smoke pass。
3. long ID local-order canary 不调用 exchange。
4. account truth snapshot ready，五个只读 surface 完整。
5. coverage 22/22 shared predicate pass。
6. timers/services 状态符合 deploy contract。

**Chain Position:** `action_time_boundary`

**Live Enablement State Before:** local certified。

**Live Enablement State After:** Tokyo exact SHA deployed，尚待当前数据收敛断言。

**Blocker Removed Or Reclassified:** deployment blocker 移除。

**Per-Symbol / Per-Fact Acceptance:** 当前 active StrategyGroup coverage 全矩阵健康；account snapshot flat。

**Stop Condition:** 任一 SHA/schema/service/canary 不一致，保持 contained/fenced。

**Capability Unlocked:** T10 controlled convergence。

**Next Engineering Bottleneck:** 当前两个 historical claims。

**Rehearsal/Simulation Boundary:** no forced live submit。

**Tests:** postdeploy verifier、journal、systemd、PG current、read-only exchange。

**Done When:** exact release active 且所有前置 canary 通过。

**Hard Stop:** 通过关闭安全 verifier 或恢复旧 release 绕过失败。

## 15. T10 — Converge Current Tokyo False Capacity

### 15.1 Task Packet

**Task ID:** `ATC-FSC-T10`

**Goal:** 由正式 account-truth service 把当前 BTC/SOL 两条 terminal absent Claim 收敛为 released/flat/0/2。

**Why:** 代码部署后必须恢复当前账户容量。

**Allowed state changes:** official Reservation/Lifecycle transitions、Exposure/Budget Current projection、append-only transition events。

**Forbidden state changes:** history deletion、manual SQL、exchange write、profile/sizing change。

**Requirements:**

1. repair 前再次证明 exchange 0 position/0 regular/0 algo。
2. 两个 attempts write=false；commands reconciled_absent/no dispatch/no exchange ID。
3. service 一次或多次幂等运行后精确释放两条。
4. Budget 0/2 matched/allowed；Exposure flat；Lifecycle completed。
5. 第二次 tick 转换计数为 0。

**Chain Position:** `action_time_boundary`

**Live Enablement State Before:** deployed but historical false slots remain。

**Live Enablement State After:** account capacity truth converged；系统等待自然 eligible signal。

**Blocker Removed Or Reclassified:** stale reservation `active_position_resolution` 假阻塞移除。

**Per-Symbol / Per-Fact Acceptance:** BTCUSDT/SOLUSDT 两条各释放一次，其他历史和真实 exposure 不变。

**Stop Condition:** 任一 exchange fact 非空、unknown 或身份不唯一，停止 release 并保持 fail closed。

**Capability Unlocked:** 下一 fresh eligible different-instrument candidate 可进入 Claim/Ticket。

**Next Engineering Bottleneck:** 自然市场信号后的真实链路校准。

**Rehearsal/Simulation Boundary:** exchange read-only；PG official state changes only。

**Tests:** before/after PG assertions、idempotency、monitor and service health。

**Done When:** 当前 Budget 0/2，服务无 blocker storm，Owner 状态为 running/waiting_for_opportunity。

**Hard Stop:** 为了得到 0/2 而删除 Ticket/Attempt/Command 历史。

## 16. T11 — Observe The Next Natural Eligible Signal

### 16.1 Task Packet

**Task ID:** `ATC-FSC-T11`

**Goal:** 在自然 eligible signal 到来时验证真实官方链路不再被本次工程缺陷阻止。

**Why:** 工程闭环可由 production-shaped certification 完成；自然市场事件用于实盘校准，不应由强制信号替代。

**Allowed actions:** standing authorization 内的 watcher、fresh signal、FinalGate、Operation Layer、真实 submit、protection、reconciliation、settlement、review。

**Forbidden actions:** synthetic live signal、forced order、扩大 scope/sizing、bypass。

**Requirements:**

1. signal -> promotion -> lane -> Ticket identity 完整。
2. pre-candidate account Current 新鲜且非历史假槽位。
3. local Order lineage 注册成功。
4. 真实 submit 仅在 FinalGate/Operation Layer pass 后发生。
5. exchange outcome、protection、reconciliation 按事实记录。
6. 如果市场没有 eligible signal，状态是 `market_wait_validated`，不是工程 blocked。

**Chain Position:** `daily_live_enablement_status`

**Live Enablement State Before:** engineering ready, waiting for natural opportunity。

**Live Enablement State After:** first natural live outcome calibrated，或继续 valid market wait。

**Blocker Removed Or Reclassified:** 工程 blocker 已关闭；无信号时归类 `market_wait_validated`。

**Per-Symbol / Per-Fact Acceptance:** 对实际触发的 StrategyGroup + symbol + side 保存完整 lineage。

**Stop Condition:** 出现 unknown outcome、missing protection、duplicate submit 或 wrong scope 时立即 hard stop。

**Capability Unlocked:** 恢复正常 live-profit experiment cadence。

**Next Engineering Bottleneck:** 由真实 outcome 决定，不预设策略优化。

**Rehearsal/Simulation Boundary:** 此任务允许官方真实 submit，但不扩大既有授权。

**Tests:** 生产事实审计、exchange/PG reconciliation、protection and review closure。

**Done When:** 自然事件完成官方链路，或所有非市场 blocker 关闭并明确 `market_wait_validated`。

**Hard Stop:** 把“没有自然信号”当成修复失败，或为验收人工制造交易。

## 17. 建议测试命令

具体文件可随实现调整，但门禁类别不得减少：

```bash
python3 -m pytest -q \
  tests/unit/test_ticket_bound_protected_submit_api.py \
  tests/unit/test_budget_reservation_transition.py \
  tests/unit/test_account_exposure_current.py \
  tests/unit/test_account_budget_current.py \
  tests/unit/test_account_risk_lifecycle_reprojection.py \
  tests/unit/test_ticket_bound_lifecycle_global_deadline.py \
  tests/unit/test_dual_position_account_risk_release_acceptance.py

python3 -m pytest -q \
  tests/integration/test_account_capacity_postgres.py \
  tests/integration/test_asset_neutral_account_risk_full_chain.py \
  tests/integration/test_account_capacity_hot_path_scale.py \
  <new production-shaped order/capacity convergence postgres test>

python3 scripts/audit_production_runtime_file_io.py
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
```

PostgreSQL required tests必须在 disposable loopback PG 运行，并启用 fail-on-skip/xfail。

## 18. 提交与版本管理建议

建议使用可审查的小提交，最终在同一 focused branch 集成：

| **提交** | **建议 subject** |
| --- | --- |
| T00 | `test: reproduce failed submit capacity deadlock` |
| T01 | `fix: conserve ticket bound local order identity` |
| T02 | `fix: close terminal presubmit capacity claims` |
| T03 | `fix: refresh account truth independently` |
| T04 | `fix: align account budget product semantics` |
| T05 | `fix: unify runtime coverage health semantics` |
| T06-T08 | `test: certify account truth convergence chain` |
| deploy docs/status | `docs: certify account truth convergence deployment` |

不得提交 `.agents/skills/skill-creator/` 或 `output/**`。

## 19. Owner 确认点

本计划唯一需要 Owner 确认的是：**同意按本设计实施 migration 140、正式部署东京，并让官方 account-truth service 在新鲜交易所空仓证据下自动释放当前两条 terminal pre-dispatch Reservation。**

该确认不改变现有风险政策，不授权强制交易，也不授权任何手工破坏性清理。

## 20. 本地实施与部署前认证记录（2026-07-20）

### 20.1 已完成范围

1. **T01 Order Lineage V2**：新增 migration **140**、独立 `Ticket/Command/Account/Instrument/Profile/Strategy/Episode` Order lineage；`Order.signal_id` 改为权威 Signal Event，`signal_evaluation_id` 保持真实 evaluation 或 `NULL`。
2. **T02 Terminal convergence**：仅在完整、新鲜、可交易账户快照证明 absence 后，自动将 terminal pre-dispatch Reservation 释放；reservation-only slot 不再自锁，unknown outcome、已 dispatch、真实仓位或同标的未归属订单继续 fail closed。
3. **T03 Independent Account Current**：active policy 账户即使没有 active Ticket 也会在既有 lifecycle cadence 内抓取一次账户快照并先独立提交 Current；Action-Time 候选事务不能回滚该事实。
4. **T04/T05 semantics**：`2/2` 时 `new_entry_allowed=false`、`reconciliation_state=matched`、Owner 显示正常满仓；ops health 与 Action-Time 统一接受 `covered + healthy/ok/active + current` coverage。

### 20.2 已验证事实

| **验证项** | **结果** | **证据** |
| --- | --- | --- |
| PostgreSQL 148 字符 Ticket Order | **通过** | migration 140 后写入真实长度 Ticket，Signal Evaluation 为 `NULL` |
| terminal reservation-only self-lock | **通过** | terminal absence 后 `consumed -> released`，lifecycle 变为 `presubmit_reconciled_absent`，重复 tick 不重复事件 |
| 定向单元回归 | **127 passed** | Action-Time、lifecycle、budget、Owner、ops、forensics 定向集合 |
| PostgreSQL integration | **2 passed** | disposable local PostgreSQL；无 exchange gateway 调用 |
| 文件 I/O 审计 | **clear** | `suspicious_runtime_file_authority=0`，`frequent_report_write=0` |

### 20.3 明确未执行的动作

- **未部署东京**、未运行 production migration、未写生产 PG、未调用交易所写接口。
- **T09/T10/T11** 仍待部署确认；部署后由正式 service 而非手工 SQL 收敛历史两条 Reservation。
