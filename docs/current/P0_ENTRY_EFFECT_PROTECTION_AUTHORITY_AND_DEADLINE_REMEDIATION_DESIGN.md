---
title: P0_ENTRY_EFFECT_PROTECTION_AUTHORITY_AND_DEADLINE_REMEDIATION_DESIGN
status: LOCAL_ENGINEERING_CERTIFIED_PENDING_TOKYO_DEPLOYMENT
authority: docs/current/P0_ENTRY_EFFECT_PROTECTION_AUTHORITY_AND_DEADLINE_REMEDIATION_DESIGN.md
program_id: P0-ACH-R12
parent_program: P0-ACH
corrects_program: P0-ACH-R11
corrects_commit: e51515501b8efecf3359917bc1da2702540fdabc
local_certified_commit: 4debdc00
local_schema_revision: 146
last_verified: 2026-07-22
owner_policy_change: none
exchange_write_authority: unchanged
production_deploy: separate_controlled_stage_not_yet_performed
---

# P0 Entry Effect、Protection Authority 与 Deadline 全链路修复设计

## 1. 文档定位

本设计记录 **P0-ACH-R12** 对 R11 发现的 Ticket 创建后保护链路缺陷的
纠偏，以及截至 `dev@4debdc00` 的本地认证结论。

它不把本地测试、`dev` 合并、Tokyo 部署和自然真实交易混为同一个状态：

```text
local engineering certification
-> controlled Tokyo deployment and current-state verification
-> deliberate new-entry fence release
-> distinct natural event acceptance
-> R1B venue and lifecycle calibration
```

### 1.1 当前状态

| 层级 | 已知事实 | 当前结论 |
| --- | --- | --- |
| **Local `dev`** | `4debdc00` 包含 EntryEffect、Protection Authority、absolute deadline、recovery/current-truth 修复；Alembic head 为 `146` | **本地工程已认证** |
| **Tokyo** | 最后留存运行快照是 `8c61a208062520a5c426e2151e4692e256fec5dd` / schema `143` | **尚未应用 R12，部署前必须重新读取** |
| **Natural live outcome** | 尚未以新的自然信号完成官方 `Ticket -> ENTRY -> same-source SL -> open_protected` 链路 | **事件驱动待验收** |

因此，本设计关闭的是原 R12 工程 `hard_safety_stop`，但不声称 Tokyo 已具备
已验证的交易能力，也不把未发生的自然事件写成真实订单结果。

## 2. 已修复的问题类

### 2.1 原始失败模式

R11 的确定性 RED 曾证明：ENTRY 在 Ticket TTL 内发起、结果却跨 TTL 返回时，
Ticket 可仍为 `finalgate_ready` 或被过期处理，而同一 source 的 Initial Stop 无法 claim。
这会把已可能存在的 exposure 错误地留在 pre-submit 语义中。

根因是把三类不同权限都绑定到 Ticket TTL：

| 权限 | 允许动作 | 终止条件 |
| --- | --- | --- |
| **Entry Authority** | 创建新风险敞口 | fresh facts、FinalGate、Operation Layer 或 Ticket TTL 失效 |
| **Protection Authority** | 对已存在或可能存在的敞口提交 reduce-only SL/TP1 或恢复保护 | 仅在 terminal absence/flat 被证明后终止 |
| **Lifecycle Authority** | 对账、恢复、结算和审查 | terminal closure 后终止 |

Ticket expiry 可以撤销新的 ENTRY 权限，不能撤销已经产生或可能产生 exposure 后的
减险与生命周期权限。

### 2.2 R12 架构决策

R12 保留单一业务与写入权威：

```text
Ticket = 交易业务生命周期身份
ProtectedSubmitAttempt = 一次受保护提交聚合
ExchangeCommand = 唯一 exchange side-effect authority
Lifecycle = exposure / protection / reconciliation / closure owner
```

不新增第二 submit worker、保护 grant 表、JSON/MD sidecar 或 Console direct-submit
fallback。修复在既有 Attempt、Command、Ticket、Lifecycle、incident 和 current projection
上表达。

## 3. 关键不变量

### 3.1 EntryEffect 原子投影

authoritative ENTRY result commit 在一个短 PG transaction 中必须同时完成：

1. 持久化 typed command result、执行数量、均价与观察时间。
2. 记录 Attempt 的 entry-effect 状态和 `exchange_write_called`。
3. 将 Ticket 从 `finalgate_ready` 转为 `submitted`。
4. 推进 Lifecycle 到 entry-submit、fill-pending 或 entry-filled 语义。
5. 保留 budget、capacity、ExposureEpisode 与 NettingDomain hold。
6. 投影 Initial Stop barrier；有 exposure 且未建立 SL 时写入 incident/new-entry fence。

`submitted` 表示 ENTRY exchange effect 已发生或可能发生；它不再等待 SL、TP1 或
整个 source aggregate 完成。

### 3.2 Exact-source 保护领取

ENTRY 和保护命令使用不同 claim predicate：

```text
ENTRY requires current fresh Ticket + FinalGate/Operation Layer identity.
SL/TP1/recovery requires exact Attempt/source/exposure identity + reduce-only legality.
```

ENTRY 已 effect 后，drain 只可完成相同 `protected_submit_attempt_id`、相同 source、
相同 exposure/netting domain 的 `SL`，之后才允许同 source 的 TP1。其他 source 的命令
不得被误记为当前 Ticket 的 Initial Stop。

### 3.3 一个绝对 deadline

每次 lifecycle invocation 只创建一次 `absolute_deadline_at`。claim、ENTRY、SL、TP1、
reconciliation、result commit 和 projection 都使用同一个剩余预算。新 ENTRY claim 前必须
预留 Entry result commit、Initial Stop I/O、Initial Stop commit 与 shutdown margin；不足则
在网络 I/O 前 fail closed。

ENTRY 已 effect 而预算意外耗尽时，系统先提交 ENTRY truth，然后创建保护 incident、保持
new-entry fence，并把 exact source 交给 recovery；不得重发 ENTRY、延长 Ticket TTL 或重置
deadline。

### 3.4 Recovery、current truth 与容量

zero fill、late fill、unknown outcome、SL rejected/unknown 与进程重启均通过 typed PG state
进入 reconciliation/recovery。只有 terminal absence/flat、无残留 order/effect、reconciliation
matched 且 lifecycle closure 完成后，capacity/hold 才可释放。

任何 active EntryEffect 不能被 Candidate Pool、Goal Status、Daily Table 或 monitor 压缩为
`waiting_for_opportunity`、`market_wait_validated` 或 `no_signal`。

## 4. 已完成的本地工程范围

| R12 任务 | 本地实现结果 | 主证据 |
| --- | --- | --- |
| **T01 RED 与状态建模** | expiry-during-entry、source competition、deadline 与 process recovery 边界被固定；typed EntryEffect 持久化 | `97218cd3`、`9d435add`、`16dd40cc` |
| **T02/T03 authority 与 source drain** | Entry/Protection claim 分离；Initial Stop 绑定 exact source/Attempt | `074830d7`、`cfdcad25` |
| **T04 absolute deadline** | 全调用链携带单一 deadline；deadline-blocked claim 安全释放 | `3c4f63ba`、`360e2c24` |
| **T05 recovery/current truth** | recovery generation、incident/fence、budget settlement、monitor/current projection 收敛 | `aa9f185b`、`af2a648d` |
| **T06 full-chain certification** | typed PG harness、worker/current truth/monitor 回归与 six Event-Spec impact coverage | `4debdc00` |

本地验收已覆盖：定向 unit 回归、23 个 PostgreSQL runtime-causal-integrity 场景、Alembic
single-head `146`、Ruff、output artifact scope 和 production file-I/O 审计。上述证据证明
代码与数据库契约；不构成 Tokyo runtime 或真实 exchange outcome 证据。

## 5. 剩余执行顺序

### 5.1 Controlled Tokyo deployment

部署前必须重新读取，不使用本文件中的历史快照代替实时事实：

1. `app/current` release manifest、实际 systemd runtime head 和 Alembic revision。
2. PG current positions、open orders、Tickets、Attempts、ExchangeCommands、incidents、holds。
3. 若有 active exposure、unknown outcome 或未保护状态，停止普通部署并转 recovery。
4. 建立 deployment-scoped new-entry fence，应用 `dev@4debdc00` 与 forward migration `146`。
5. 验证 exact SHA/schema、affected timers、no-write current-state canary、monitor/current truth。

部署成功只证明部署成功，不等于交易能力或自然真实订单验收。

### 5.2 Natural-event acceptance

在明确释放 fence 后，下一个不同 identity 的自然 eligible signal 必须走官方路径：

```text
fresh eligible signal
-> one Ticket
-> one ENTRY effect
-> exact fill truth
-> same-source Initial Stop within SLA
-> reconciliation/current truth consistent
-> open_protected or one exact visible hard blocker
```

若自然信号未出现，状态只能是 **`pre_live_certified`**，不能称为
`live_outcome_calibrated`。

## 6. Stop Conditions

出现任一条件，停止 deploy/fence release 或转入恢复：

- ENTRY effect 对应 Ticket 仍为 pre-submit 或 `expired`。
- SL claim 重新依赖 Ticket/signal/lane TTL。
- Initial Stop completion 不能证明 exact source、Attempt 与 exposure identity。
- absolute deadline 在子阶段重置，或 ENTRY 前未预留 Initial Stop 预算。
- active exposure 无 exact protection 或 current incident。
- restart 后可能重复 ENTRY，或 Ticket expiry 释放 capacity。
- monitor 把 active EntryEffect 压缩为 no-signal/waiting。
- runtime path 新增 JSON/MD/file authority、第二 exchange-write authority 或 direct submit fallback。

## 7. Chain Position

```text
chain_position: ticket_created_to_open_protected
program: P0-ACH-R12
local_state: multi_position_pre_live_certified_on_dev
tokyo_state: deployment_not_yet_performed; runtime truth must be refreshed before apply
first_blocker: controlled_tokyo_deployment_and_postdeploy_current_truth_verification
next_action: apply the Tokyo deployment contract to dev@4debdc00 with forward schema 146
postdeploy_action: deliberate fence release followed by natural-event acceptance
owner_action_required: none for ordinary in-boundary engineering; no policy/profile/sizing expansion is implied
authority_boundary: no FinalGate/Operation Layer bypass, credential change, withdrawal, transfer, or unscoped exchange write
```
