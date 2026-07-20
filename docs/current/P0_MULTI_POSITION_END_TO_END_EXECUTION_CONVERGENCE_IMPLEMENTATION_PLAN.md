---
title: P0_MULTI_POSITION_END_TO_END_EXECUTION_CONVERGENCE_IMPLEMENTATION_PLAN
status: IMPLEMENTATION_IN_PROGRESS
authority: docs/current/P0_MULTI_POSITION_END_TO_END_EXECUTION_CONVERGENCE_IMPLEMENTATION_PLAN.md
program_id: P0-ACH
design: docs/current/P0_MULTI_POSITION_END_TO_END_EXECUTION_CONVERGENCE_DESIGN.md
r7_design: docs/current/P0_R7_CURRENT_TRUTH_REDUCER_AND_LEGACY_RETIREMENT_DESIGN.md
r7_plan: docs/current/P0_R7_CURRENT_TRUTH_REDUCER_AND_LEGACY_RETIREMENT_IMPLEMENTATION_PLAN.md
baseline_commit: 60999176
current_certified_commit: 1fd49cc09efdb9653d5e1df4da8b8bb2b5fe86f1
target_stop: deployment_confirmation_gate
production_deploy: out_of_scope_until_owner_confirmation
---

# P0 多仓位端到端执行收敛执行计划

## 1. 执行目标

将当前系统推进到 **多仓位部署前认证完成**：每笔被选择的交易从 Signal 到 Ticket、真实订单准备、保护、runner、退出、对账和容量释放都具有独立、可恢复、可验证的链路。

本计划完成时停止在：

```text
exact certified commit
+ candidate migration head
+ disposable/shadow PostgreSQL certification
+ deployment package and rollback runbook
+ Writer Fence enabled
= deployment_confirmation_gate
```

不在本计划内执行东京部署、生产 migration、Writer Fence 解除或强制真实交易。

## 2. 当前基线

| 项目 | 基线 |
| --- | --- |
| Branch | `codex/budget-model-review-20260714` |
| Commit | **`60999176`** |
| Candidate migration head | **141** |
| Unit baseline | **138 focused tests passed** |
| Disposable PostgreSQL | migration、capacity concurrency、dynamic-head harness 已通过 |
| Remaining first blocker | global single-row trigger + fragmented per-trade lifecycle semantics |

## 3. 执行原则

1. **一个切片，一个权威替换，一个旧路径删除。**
2. 核心 entry、risk、lifecycle 文件串行修改。
3. 每个切片先写 RED，再实现，再执行 deletion/reachability test。
4. 不为兼容旧调用保留长期双路径。
5. 不因 live-only 条件阻止 rehearsal、PG、fake exchange 和 no-write 认证。
6. 不改变策略参数、风险预算、position cap、symbol/side scope。
7. 新 migration 必须重新通过 Schema Truth Gate，不允许顺手追加。

## 4. 依赖顺序

```mermaid
flowchart LR
    R0["R0 Baseline + deletion inventory"] --> R1["R1 Semantic Kernel"]
    R1 --> R2["R2 Signal intake + arbitration"]
    R2 --> R3["R3 Typed Action-Time coordinator"]
    R3 --> R4["R4 Capacity / occupancy linearization"]
    R4 --> R5["R5 Durable submit + protection barrier"]
    R5 --> R6["R6 Independent runner / exit"]
    R6 --> R7["R7 Current reducer + debt deletion"]
    R7 --> R8["R8 PostgreSQL full-chain / chaos certification"]
    R8 --> R9["R9 Predeploy package and shadow restore"]
```

R1 与 R0 结束前不得并行修改 execution core。R5、R6 涉及相同 lifecycle/command 表面，必须串行。

## 5. R0 — Baseline、RED 与删除清单冻结

### Task Packet

**Task ID:** `P0-MP-R0`

**Goal:** 固定所有剩余 failure classes、旧路径和当前测试基线。

**Why:** 没有删除清单和 RED，容易把旧路径保留成“临时兼容”。

**Allowed files:** focused tests、reachability audit、两份本文档 completion record。

**Forbidden files:** production implementation、policy、migration。

**Requirements:**

1. RED 覆盖 same-timestamp 8 Signals、random insertion、two workers。
2. RED 覆盖 0/2、1/2、2/2、third requester、same domain。
3. RED 覆盖两个 Ticket runner/exit isolation。
4. RED 覆盖 timeout、crash、outcome_unknown、partial fill、protection failure。
5. 生成机器可读的旧路径清单，但结果只写测试 stdout，不生成 repo report。
6. 冻结 141 graph checksum 和 commit baseline。

**Chain Position:** `action_time_boundary`

**State Before:** failure evidence 分散。

**State After:** 每类剩余问题都有稳定 RED 和删除目标。

**Tests:** new focused RED tests；migration graph test；file-I/O audit。

**Done When:** 每个后续 Task 都能引用 exact failing test 和 exact old path。

**Hard Stop:** 用文档描述替代 executable RED。

## 6. R1 — Runtime Semantic Kernel

### Task Packet

**Task ID:** `P0-MP-R1`

**Goal:** 统一 active、terminal、current、outcome_unknown 和 operational relevance。

**Allowed files:** 新纯 domain semantic module、Invocation、process outcome relevance、focused consumer adapters/tests。

**Forbidden files:** 数据库 I/O 进入 domain、万能 Aggregate、status reason migration。

**Requirements:**

1. 实现 stable phase/state/terminal_kind/reason_code。
2. 实现 legal transition 和 terminal irreversibility。
3. Invocation expiry/close、Ticket、Attempt、Command、Lifecycle 使用同一 predicate。
4. reason code 不进入频繁变化 CHECK enum。
5. 先接入 execution/current hot consumers，再删除其本地 status sets。

**Blocker Removed:** `runtime_state_semantics_diverged`。

**Acceptance:** 同一 fixture 在 Candidate、Goal、Ops、Forensics 中 active/terminal 结论一致。

**Tests:** transition table、expiry、unknown outcome、closed-but-relevant、historical warning negatives。

**Done When:** execution hot path 不再自行维护重复 terminal set。

**Hard Stop:** 把 unknown outcome 当作安全 terminal。

## 7. R2 — Signal Intake 与确定性仲裁

### Task Packet

**Task ID:** `P0-MP-R2`

**Goal:** 保存所有 fresh Signal，按稳定规则选择至多一个新 Ticket winner。

**Allowed files:** Action-Time Invocation、new typed intake/arbitration service、promotion/lane、runtime process outcome、focused PG tests。

**Forbidden files:** Owner priority 数值、Capital Allocation V1、exchange write、多个并行新 winner。

**Requirements:**

1. bounded batch max 64，删除 global latest-Signal selector 的业务职责。
2. 每 Signal exactly one Invocation。
3. 排序固定为 policy/candidate/event/observed/signal ID。
4. account/profile domain 使用 row/advisory lock。
5. candidate-specific pre-Claim failure 可在 deadline 内尝试下一候选。
6. global blocker 关闭整轮并写相同 root cause。
7. one winner 后 losers 写 `not_selected_this_round`、rank、winner_ref。
8. duplicate delivery、retry、worker death 不产生第二 Invocation/Claim/Ticket。

**Live Enablement Before:** Signal 可能无 Invocation 或被 LIMIT 1 隐式丢弃。

**Live Enablement After:** 每个 Signal 有结果，唯一 winner 可解释。

**Tests:** 8/32/64 Signals、random order、two workers、winner expiry、first candidate blocker fallback、global 2/2 stop。

**Done When:** `action_time_invocation_missing` 和无结果 Signal 在 production-shaped fixture 中为 0。

**Hard Stop:** 依赖数据库隐式顺序或提交两个 winner。

## 8. R3 — Typed Action-Time Coordinator

### Task Packet

**Task ID:** `P0-MP-R3`

**Goal:** 用 typed coordinator 替换 critical-path subprocess/stdout 协议，并完整执行 global deadline。

**Allowed files:** new application coordinator、refresh sequence、fact materialization、Ticket sequence、FinalGate/handoff typed calls、deadline tests。

**Forbidden files:** exchange gateway、45 秒扩容、stdout 作为业务真值。

**Requirements:**

1. coordinator 输入为 Invocation ID，不接受 global/no-Invocation production mode。
2. typed step result 包含 state、blocker、identity、deadline、side-effect counters。
3. `global_deadline=min(signal,ticket,fact,30s)`，只能缩短。
4. API/PG timeout 从 remaining budget 派生。
5. deadline 不足在下一 authority boundary 前持久化 typed outcome。
6. deadline 后 Claim/Ticket/handoff 新写入为 0。
7. 删除 `_structured_child_process_outcome` 等 critical-path stdout parser。
8. 删除 Ticket sequence 的 production global branch。

**Tests:** deadline 前后 1ms、fact expiry 缩短、timeout kill、transaction rollback、typed error parity。

**Done When:** production Action-Time critical path 无 subprocess/stdout business protocol。

**Hard Stop:** 保留旧路径作为 fallback。

## 9. R4 — Capacity 与 Occupancy 线性化

### Task Packet

**Task ID:** `P0-MP-R4`

**Goal:** 让 Claim、Exposure、Command、Hold 和 Budget Current 对 0/1/2 状态得出唯一答案。

**Allowed files:** capacity claim/reservation、Exposure/Budget projector、hot-path repository、Ticket/Command ownership、formal repair projector、PG tests。

**Forbidden files:** position cap 修改、symbol-only conflict、manual production SQL。

**Requirements:**

1. capacity owner 使用 Ticket/ExposureEpisode identity union。
2. pending Claim 转 Exposure 不双计。
3. same one-way NettingDomain 第二 Ticket fail-closed。
4. different instrument 可占两个独立 slot。
5. outcome_unknown、active hold、missing protection 保留容量。
6. lifecycle release 与新 Claim 并发时线性化。
7. formal projector 替代一次性 current mutator；旧 repair path 删除。
8. FinalGate、watcher、next-entry gate 读取相同 Account Current。

**Tests:** 0→1、1→2、2→3 blocked、same domain、different domain、close-vs-claim、crash-vs-claim、pending→Exposure、exact release。

**Done When:** 所有 consumer 的 claimed slots、held risk、pending margin 一致。

**Hard Stop:** 因进程消失或本地 Ticket 过期释放容量。

## 10. R5 — Durable Submit 与 Protection Barrier

### Task Packet

**Task ID:** `P0-MP-R5`

**Goal:** 证明每个 Ticket 的 entry command 和初始保护独立、幂等、可恢复。

**Allowed files:** Codex-owned execution core、Exchange Command、worker、protected submit、fill projector、protection materializer/reconciler、tests。

**Forbidden files:** FinalGate/Operation Layer bypass、credential、sizing/profile mutation。

**Requirements:**

1. durable command 必须先提交 PG，再进行 exchange write。
2. worker lease、client-order ID、request fingerprint 唯一。
3. network ambiguous 进入 outcome_unknown 并保留容量。
4. partial fill 按 exact quantity 创建/调整保护。
5. initial stop 和 required TP1 全部 matched 后才是 `open_protected`。
6. 两个 Ticket 的 command/protection generation 不互相覆盖。
7. retired direct submit/protection executor 删除或不可达。

**Tests:** before/after dispatch crash、duplicate worker、authoritative reject、unknown recovery、partial fill、protection reject、two-ticket isolation。

**Done When:** fake exchange ledger 证明每 command 至多一次外部 effect，且每 Ticket 独立保护。

**Hard Stop:** unknown outcome retry submit 或无保护释放容量。

## 11. R6 — 独立 Runner、终退与 Closure

### Task Packet

**Task ID:** `P0-MP-R6`

**Goal:** 两个仓位可使用各自 exit-policy cadence、保护 generation 和终退链路。

**Allowed files:** exit-policy binding/service、runner scheduler/command/adjuster、lifecycle command materializer、reconciliation、finalizer、settlement/review tests。

**Forbidden files:** global latest Ticket、symbol-only lookup、新 Ticket legacy_unbound。

**Requirements:**

1. runner queue key 为 Ticket + ExposureEpisode + next_due。
2. cadence 来自 exit-policy，不从 entry timeframe 猜测。
3. 新 Ticket 必须 version-bound；legacy_unbound 只允许历史只读解释。
4. 一个 Ticket 的 TP1/SL/runner mutation 不影响另一个 Ticket。
5. final exit 后先清保护、对账，再 terminal exposure。
6. settlement/review 后 exactly-once release。
7. 删除 retired direct runner/orphan executor 和不再使用的 import。

**Tests:** 15m + 1h concurrent policies、TP1 on A while B unchanged、runner mutation race、final exit unknown、position flat with live stop、double finalizer。

**Done When:** 两 Ticket lifecycle event streams 和 capacity release 完全隔离。

**Hard Stop:** global latest-row runner 或批量按 symbol 关闭订单。

## 12. R7 — Current Reducer 与历史债删除

本阶段的详细任务切片、Allowed/Forbidden files、CurrentTruthBundle、Incident、Monitor/Forensics cutover、continuation 收敛与 repair mutator 删除条件，以
`docs/current/P0_R7_CURRENT_TRUTH_REDUCER_AND_LEGACY_RETIREMENT_IMPLEMENTATION_PLAN.md`
为执行权威。

### Task Packet

**Task ID:** `P0-MP-R7`

**Goal:** 所有 Owner/ops/readmodel 使用同一 current truth，并删除替换完成的历史路径。

**Allowed files:** shared reducer、Candidate/Goal/Daily/Ops/Forensics、monitor/notification、reachability tests、删除清单文件。

**Forbidden files:** 新 health table、新 JSON cache、隐藏历史错误。

**Requirements:**

1. 所有 projection 使用相同 PG watermark/run ID。
2. current issue 与 historical warning 分离。
3. incident fingerprint、recovery 和 Owner action 唯一。
4. detector false 为 computed_not_satisfied，不是 missing。
5. 逐项删除 global selector、stdout parser、global Ticket path、duplicate status sets、retired executor、current mutator。
6. ripgrep/import/runtime reachability 必须为 0。

**Tests:** consumer parity、historical warning negatives、notification dedupe、recovery once、deleted import/reachability audit。

**Done When:** 同一 snapshot 的 first blocker 在所有 current surfaces 一致。

**Hard Stop:** 通过过滤历史行制造假健康。

## 13. R8 — PostgreSQL Full-Chain 与 Chaos Certification

### Task Packet

**Task ID:** `P0-MP-R8`

**Goal:** 使用真实 PostgreSQL 和 fake/no-write exchange 认证完整多仓位链。

**Allowed surfaces:** disposable PG、production-shaped seed/snapshot、fake exchange ledger、process crash harness、performance tools。

**Requirements:**

1. `001→106→seed→head` 和 production baseline→head 均通过。
2. schema fingerprint 等价。
3. raw detector input 走到两个 independent lifecycle closure，禁止手工构造完整下游对象。
4. two workers、random order、kill/restart、lock timeout、statement timeout 全覆盖。
5. 0/1/2、third requester、same domain、different domain、unknown outcome、missing protection 全覆盖。
6. Action-Time p95/p99、EXPLAIN、row growth、retention、file-I/O 全通过。
7. exchange write 使用 fake ledger，production credential 调用数为 0。

**Tests:** new multi-signal PG、multi-position PG、full-chain chaos、schema fingerprint、restore tests。

**Done When:** machine-readable matrix 全绿且 no forbidden effect。

**Hard Stop:** SQLite 替代 lock/Numeric/concurrency 认证。

## 14. R9 — Shadow Restore 与部署前包

### 14.1 当前执行状态

**R7** 的共享 Current Truth 与旧路径退役已完成，**R8** 的 disposable
PostgreSQL 全链与 chaos 认证已完成。R9 尚未改变东京、生产 schema、生产
role、Writer Fence 或交易所；它只允许生成 exact commit 的预部署证据，并将
缺失的 shadow/role/previous-writer 证据保持为明确 blocker，不能以本地测试
替代。

### 14.2 已获得的 R9 只读证据

| 证据项 | 结论 | 影响 | 来源 |
| --- | --- | --- | --- |
| Migration graph | 单 head **`142`**；checksum 由 `prepare_multi_position_predeploy_package.py` 计算 | 可作为 candidate release 的不可变输入 | 本地 Git，2026-07-20 |
| Local PostgreSQL | disposable certification DB 当前无业务表，不能冒充 production shadow | 必须从 production backup 恢复到新 shadow 后再 fingerprint | 本地 Docker readonly catalog，2026-07-20 |
| Tokyo role topology | 当前登录 runtime identity 为 `brc_dryrun`，且具有 superuser、`CREATEROLE` 与 `CREATEDB` | 不满足 application/migration identity 分离；不得进入部署前通过状态 | Tokyo `dingdingbot-pg` container readonly catalog，2026-07-20 |

因此 `role_topology_decision` 为
**`credential_or_secret_change_required`**：目标 application identity 必须无 schema
DDL、managed object ownership 或可通过 membership/`SET ROLE` 绕过的权限。当前没有
第二个可用 application identity；建立并分发该身份会涉及 credential/secret change，
本计划禁止自动执行。R9 保持 **`blocked_owner`**，直到该生产权限边界得到单独授权。

角色拓扑必须使用 `scripts/audit_postgres_role_topology.py` 的 stdout-only 审计结果
复核。该工具只在 read-only transaction 中读取 PostgreSQL catalog，并对连接身份
输出 hash reference；它不读取、输出或修改 credential，也不执行 role DDL。

### Task Packet

**Task ID:** `P0-MP-R9`

**Goal:** 准备 exact commit 的部署包，停止在 Owner 部署确认前。

**Allowed surfaces:** release manifest、deploy plan、PG backup/restore rehearsal、role topology readonly audit、Writer Fence plan、postdeploy readonly commands。

**Forbidden actions:** 东京 apply、生产 migration、grant/revoke apply、exchange write、Writer Fence 解除。

**Requirements:**

1. exact commit、source digest、migration head、graph checksum、schema fingerprint。
2. production backup restore 到 shadow 并执行 candidate upgrade/full-chain checks。
3. previous writer compatibility 分 Entry、Lifecycle、Projection、Monitor 四类。
4. role topology 输出 application/migration identity、owner、membership、DDL capability。
5. deployment 前 Writer Fence receipt 和恢复命令准备完整。
6. postdeploy no-write canary 命令、stop condition、rollback/forward-fix runbook 完整。
7. 产出 `ready_for_owner_deploy_confirmation` 或 exact blocker。

**Done When:** 部署所需命令和证据齐备，但没有改变东京状态。

**Hard Stop:** role topology unknown、backup restore 未验证、需要 secret 变化或 destructive migration。

## 15. 测试矩阵

| 维度 | 必须覆盖 |
| --- | --- |
| Signal | 1、8、32、64；同 timestamp；随机顺序；重复 delivery |
| Arbitration | first candidate fail then fallback；global blocker；two workers；winner expiry |
| Capacity | 0/2、1/2、2/2、third requester、same domain、different domain |
| Submit | before/after dispatch crash、reject、timeout、outcome_unknown、duplicate worker |
| Fill/protection | zero fill、partial fill、full fill、SL reject、TP1 reject、resize |
| Runner | 15m/1h 不同 cadence、TP1、stop movement、competing command |
| Exit | final exit accepted/rejected/unknown、flat + live protection、double finalizer |
| Recovery | restart、lease expiry、projector replay、release-vs-claim race |
| Projection | Candidate/Goal/Ops/Forensics/notification parity |
| Performance | deadline 30s、PG lock/statement timeout、EXPLAIN、row growth、retention |

## 16. Commit 与回滚点

| Slice | Commit subject | Rollback class |
| --- | --- | --- |
| R0 | `test: freeze multi-position execution red matrix` | code-only |
| R1 | `refactor: centralize runtime execution semantics` | code-only |
| R2 | `fix: conserve and arbitrate every live signal` | append-only Invocation facts retained |
| R3 | `refactor: replace action-time subprocess coordinator` | code-only before activation; forward-fix after facts |
| R4 | `fix: linearize multi-position capacity ownership` | schema forward; projector replay |
| R5 | `fix: isolate durable submit and protection per ticket` | Writer Fence + reconcile |
| R6 | `fix: isolate runner exit and release per ticket` | existing lifecycle remains active; forward-fix |
| R7 | `refactor: delete legacy runtime authority paths` | no old-path restoration after activation |
| R8 | `test: certify multi-position postgres full chain` | test-only |
| R9 | `chore: prepare multi-position predeploy package` | no production state change |

## 17. Deployment Confirmation Gate

最终交付必须明确：

```text
status: ready_for_owner_deploy_confirmation | blocked
exact_commit:
migration_head:
schema_fingerprint:
unit_test_count:
postgres_test_count:
full_chain_matrix:
deleted_path_count:
performance_risk.status: clear
file_io_risk.status: clear
role_topology_decision:
previous_code_compatibility:
writer_fence_plan:
backup_restore_status:
forbidden_effects: all_false
```

Owner 确认前停止，不执行部署。

## 18. Program Stop Conditions

以下任一存在即不得进入部署确认：

- fresh Signal 无 Invocation/result；
- 两 worker 可产生两个 winner；
- Claim 与 Exposure 双计；
- same one-way domain 可创建第二独立 Ticket；
- outcome_unknown 或 missing protection 释放容量；
- runner/exit 使用 global latest Ticket；
- 一个 Ticket 的保护或退出影响另一个 Ticket；
- current consumers first blocker 不一致；
- 删除清单存在 production reachability；
- 真实 PG、shadow restore、role topology、file-I/O 或 performance gate 未通过。

## 19. Chain Position

```text
chain_position: action_time_boundary
strategy_group_id: five active StrategyGroups
symbol: 22 active candidate lanes
stage: implementation_plan_ready
first_blocker: R1 Semantic Kernel and R2 bounded deterministic Signal arbitration are not implemented
evidence: design and current tracked code at 60999176
next_action: after Owner confirmation, execute R0 then R1 serially
stop_condition: ready_for_owner_deploy_confirmation with complete Signal-to-exit isolation and deleted legacy paths
owner_action_required: true_for_implementation_confirmation_only
authority_boundary: planning only; no production deployment, migration apply, exchange write, policy/profile/sizing change or Writer Fence release
```
