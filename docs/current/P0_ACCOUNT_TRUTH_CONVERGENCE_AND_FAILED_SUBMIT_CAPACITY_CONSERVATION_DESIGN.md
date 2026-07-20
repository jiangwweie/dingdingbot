---
title: P0_ACCOUNT_TRUTH_CONVERGENCE_AND_FAILED_SUBMIT_CAPACITY_CONSERVATION_DESIGN
status: LOCAL_IMPLEMENTED_DEPLOYMENT_APPROVAL_REQUIRED
authority: docs/current/P0_ACCOUNT_TRUTH_CONVERGENCE_AND_FAILED_SUBMIT_CAPACITY_CONSERVATION_DESIGN.md
extends:
  - docs/current/DUAL_POSITION_HARD_CAP_ACCOUNT_RISK_MODEL_V0_DESIGN.md
  - docs/current/DUAL_POSITION_ACCOUNT_RISK_V0_RELEASE_BLOCKER_REMEDIATION_DESIGN.md
  - docs/current/TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md
scoped_correction_of:
  - ticket-bound local-order identity binding
  - terminal pre-dispatch reservation release
  - account current refresh ownership
  - account budget entry-capacity semantics
  - runtime coverage health classification
evidence_head: 881f192b88e32610a6e27af0eb0e6df6cf1d1bcf
production_head: 881f192b88e32610a6e27af0eb0e6df6cf1d1bcf
production_migration_head: 139
incident_date: 2026-07-20
exchange_write_during_analysis: 0
owner_policy_change: none
---

# P0 Account Truth Convergence And Failed-Submit Capacity Conservation Design

## 1. 决策摘要

### 1.1 核心结论

**当前东京交易所账户真实为空仓、无普通挂单、无 Algo 挂单，但 PostgreSQL 仍保留两个由失败 Ticket 派生的假占用槽位。** 这不是单纯的历史脏数据，而是以下五个缺陷组成的可重复生产故障：

1. **订单身份错绑**：完整 `ticket_id` 被写入 `orders.signal_evaluation_id`。
2. **本地订单注册失败**：148 字符 Ticket ID 超过生产列 `varchar(128)`，PostgreSQL 返回 **SQLSTATE `22001`**。
3. **Reservation 自锁**：失败 Ticket 的 `consumed` Reservation 被投影为 `reserved` Exposure；reclaim 又把这个派生槽位当作真实仓位证据，因此拒绝释放。
4. **账户 Current 无独立刷新所有者**：Action-Time 被阻止时会回滚刚写入的空仓 Current；没有活跃 lifecycle 时，30 秒 worker 也不会刷新；post-submit tick 又错误依赖 lifecycle 语义变化。
5. **产品状态语义分裂**：Budget Current 显示 `2/2`，同时仍写 `new_entry_allowed=true`；运维脚本又把真实的 `healthy` coverage 误报为未附着。

**当前分支与东京部署是同一个 exact HEAD，因此当前合并分支存在完全相同的问题。** 本设计只修复工程链路，不改变 Owner 已授权的并发仓位、风险、杠杆、名义金额、StrategyGroup、symbol、side 或 live profile。（来源：当前 Git `881f192b`、东京 systemd release identity、东京 PG revision `139`，2026-07-20）

### 1.2 设计选择

本设计选择 **“恢复既有已批准不变量，并补齐生产形态因果链认证”**，而不是创建第二套账户风险服务或直接清理两条 PG 数据。

目标链路为：

```text
完整只读账户快照
-> 短事务 A：锁定账户政策，收敛 terminal pre-dispatch claim
-> 投影 Exposure/Budget Current 并独立提交
-> 短事务 B：候选容量仲裁与 Claim
-> Ticket materialization
-> FinalGate
-> Operation Layer
-> 本地订单按真实 Signal/Ticket/Command 身份注册
-> 交易所 dispatch
```

候选被容量、事实或市场条件阻止时，**不得回滚事务 A 已提交的账户事实**。

## 2. 权威边界

### 2.1 保持不变的 Owner 决策

| **政策维度** | **当前值** | **本设计行为** |
| --- | ---: | --- |
| **最大并发仓位** | **2** | 保持 |
| **单次新 Action-Time Lane** | **1** | 保持 |
| **单 Ticket 计划止损风险** | **2.5%** | 保持 |
| **组合持有风险上限** | **6%** | 保持 |
| **主风险簇上限** | **4%** | 保持 |
| **初始保证金上限** | **90%** | 保持 |
| **最大杠杆** | **10x** | 保持 |
| **同 instrument 第二 Ticket** | **禁止** | 保持 |
| **未知 outcome / ownership** | **新 ENTRY fail closed** | 保持 |

本设计不授予 **FinalGate 绕过、Operation Layer 绕过、强制信号、强制下单、扩大资金或策略范围、转账、提现、凭据变更**。

### 2.2 当前文档关系

`DUAL_POSITION_ACCOUNT_RISK_V0_RELEASE_BLOCKER_REMEDIATION_DESIGN.md` 已经批准以下不变量：

- reservation-only Exposure 不能阻止自身释放；
- 每个完整新鲜账户快照都刷新 Current；
- release、Exposure flat、Budget refresh 同事务完成。

本设计不替换这些方向，而是记录 **当前实现偏离这些不变量的生产证据**，并定义可验收的闭环修复。

## 3. 已知客观事实

### 3.1 交易所与 PG 当前真相

| **事实面** | **当前值** | **结论** |
| --- | ---: | --- |
| **交易所非零仓位** | **0** | 账户真实为空仓 |
| **交易所普通挂单** | **0** | 无普通订单风险 |
| **交易所 Algo 挂单** | **0** | 无条件单残留 |
| **PG claimed slots** | **2 / 2** | 与交易所真相冲突 |
| **PG effective Reservation** | **2 个 consumed** | 两个假容量持有者 |
| **PG reservation-only Exposure** | **2 个 reserved，qty=0** | 派生槽位，不是真实仓位 |
| **保护提交 attempt** | **2 个 submit_failed** | 均在本地订单注册阶段失败 |
| **exchange_write_called** | **false / false** | 没有交易所写入 |
| **command dispatch_started** | **null / null** | 没有进入 dispatch |
| **command state** | **reconciled_absent** | durable command 已证明交易所不存在 |
| **Budget new_entry_allowed** | **true** | 与 2/2 容量状态自相矛盾 |

来源：东京 Binance USD-M 官方签名只读接口、东京生产 PG 只读查询，2026-07-20。

### 3.2 两个失败 Ticket

| **标的** | **Ticket 状态** | **Attempt 状态** | **Lifecycle 状态** | **Reservation** | **Exposure** |
| --- | --- | --- | --- | --- | --- |
| **SOLUSDT long** | `expired` | `submit_failed` | `submit_failed` | `consumed` | `reserved`, qty `0`, slot `true` |
| **BTCUSDT long** | `expired` | `submit_failed` | `submit_failed` | `consumed` | `reserved`, qty `0`, slot `true` |

来源：东京生产表 `brc_action_time_tickets`、`brc_ticket_bound_protected_submit_attempts`、`brc_ticket_bound_order_lifecycle_runs`、`brc_budget_reservations`、`brc_account_exposure_current`，2026-07-20。

### 3.3 DBAPIError 的精确数据库原因

两个 Ticket ID 长度均为 **148**。当前代码在本地订单构造时执行：

```python
signal_id=str(command["ticket_id"]),
signal_evaluation_id=str(command["ticket_id"]),
```

生产 `orders.signal_evaluation_id` 是 `varchar(128)`。在东京生产 PG 中使用相同类型赋值进行无持久化验证，PostgreSQL 返回：

```text
sqlstate=22001
message=value too long for type character varying(128)
```

因此 **`local_order_registration_failed:<local_order_id>:DBAPIError` 的确定根因是 Ticket ID 被错误绑定到 Signal Evaluation ID，并触发字段长度溢出**。（来源：`src/interfaces/api_trading_console.py:2912-2948`、`src/infrastructure/pg_models.py:86`、东京 PG `information_schema.columns` 与无表写入 `DO` 验证，2026-07-20）

### 3.4 当前分支仍满足失败条件

当前 HEAD `881f192b` 仍包含：

- `signal_evaluation_id=str(command["ticket_id"])`；
- terminal reclaim 对任何 `position_slot_claimed=true` 都拒绝；
- reservation-only projector 固定写 `position_slot_claimed=true`；
- lifecycle worker 在 `prepared_scopes` 为空时不获取账户快照；
- post-submit tick 仅在 `_tick_semantics_changed()` 时重投影；
- Budget `new_entry_allowed` 只看 Exposure blocker，不看并发槽位；
- ops health 只接受 `liveness_state='active'`。

所以这不是 release 分支的孤立问题，而是 **当前合并分支和当前东京部署的现行生产路径问题**。（来源：当前 tracked code，2026-07-20）

## 4. 基于事实的根因分析

### 4.1 正向调用链

```text
Watcher 发现 fresh eligible signal
-> Action-Time Invocation
-> account capacity claim
-> Ticket 创建
-> Reservation active -> consumed
-> FinalGate pass
-> Operation Layer handoff
-> protected submit attempt / durable exchange commands prepared
-> _execute_one_ticket_bound_exchange_command
-> 构造 Order
-> Ticket ID 错写 signal_evaluation_id
-> PgOrderRepository.session.merge()
-> PostgreSQL SQLSTATE 22001
-> local_order_registration_failed
-> exchange command 尚未 dispatch
-> attempt submit_failed
-> lifecycle submit_failed
-> Ticket 后续 expired
-> Reservation 仍 consumed
-> Exposure projector 将 Reservation 重建为 reserved slot
-> reclaim 将该 slot 误认作真实 exposure
-> Reservation 永久 consumed
-> Budget Current 永久 2/2
-> 新候选被 max_concurrent_positions_reached 阻止
```

### 4.2 逆向失败条件

| **失败点** | **精确条件** | **当前结果** |
| --- | --- | --- |
| **本地订单注册** | `len(ticket_id)=148` 且写入 `signal_evaluation_id varchar(128)` | SQLSTATE `22001` |
| **交易所 dispatch** | 只有本地订单注册成功后才调用 `mark_exchange_command_dispatching()` | 未执行 |
| **Reservation reclaim** | terminal Ticket 且无 exchange write，但同 Ticket Current slot=true | reclaim 拒绝 |
| **Exposure 投影** | effective Reservation 为 `active/consumed` 且无真实 position | 创建 `reserved`, slot=true |
| **Action-Time Current 刷新** | Current 投影位于同一个 sequence savepoint | 候选阻止时一并 rollback |
| **Lifecycle Current 刷新** | `prepared_scopes` 为空 | 不抓账户快照、不刷新 |
| **Post-submit Current 刷新** | lifecycle tick 语义没有变化 | 不刷新 |
| **Budget 入口语义** | Exposure 没有 first_blocker，即使 slots==max | `new_entry_allowed=true` |
| **运维 coverage** | 当前 coverage 为 `covered/healthy` | ops SQL 因只认 `active` 统计为 0 |

### 4.3 引入变更与组合缺陷

| **Commit** | **变更** | **单独意图** | **组合后问题** |
| --- | --- | --- | --- |
| `4bbfdcb2` | 初始 ticket-bound protected submit adapter | 注册本地订单后再下单 | 首次把 Ticket ID 同时写入 signal 字段 |
| `d257dc5b` | durable exchange command outcome | dispatch 前持久化 command | 保留错误身份绑定；异常仅保留类型名 |
| `e174ce9a` | terminal reservation reclaim | 安全释放未提交容量 | 把任何 Current slot 当成真实 exposure |
| `1afafe1c` | Account Exposure Current | reservation-only claim 占一个槽位 | 与上一 commit 形成自锁循环 |
| `9841f2bd` | Action-Time 前抓账户快照 | 在候选路径刷新账户容量 | 投影仍在 candidate savepoint 内，阻止即回滚 |
| `386d729b` | lifecycle 变化触发重投影 | 生命周期变化时更新账户 Current | 把 lifecycle 变化错误提升为 Current 刷新前提 |
| `2011eccc` | lifecycle worker 预取账户快照 | 复用活跃 Ticket scope | 没有活跃 Ticket 时不刷新 active policy 账户 |
| `591907db` | Budget 去重计数 | 风险、slot、margin 各计一次 | `new_entry_allowed` 未纳入 slot/risk/margin capacity |

来源：当前 Git history 与 `git blame`，2026-07-20。

### 4.4 预期模型与实际模型

| **维度** | **已批准预期** | **当前实际** | **差距** |
| --- | --- | --- | --- |
| **订单身份** | Signal、Ticket、Command、Order 独立保存并校验 | Ticket 被塞入 `signal_evaluation_id` | 身份维度混用 |
| **注册失败日志** | 有稳定错误码、SQLSTATE、约束或字段分类 | 只保留 `DBAPIError` 类型名 | 无法直接定位生产 schema 失败 |
| **Pre-dispatch release** | 忽略同 Claim 派生的 reservation-only slot | 任何 slot=true 都阻止 release | 自我锁死 |
| **账户 Current** | 每个完整新鲜快照都刷新 | 依赖候选成功或 lifecycle 变化 | 无独立事实所有者 |
| **事务边界** | 账户事实先独立提交，候选 claim 后执行 | 事实与 candidate 在同一 savepoint | candidate blocker 回滚事实 |
| **Budget 状态** | 2/2 时新 ENTRY 不允许，但 reconciliation 可 matched | 2/2 且 `new_entry_allowed=true` | 字段语义矛盾 |
| **Owner 状态** | 满仓是正常运行，不要求人工介入 | 直接改 flag 会被旧 readmodel 归类为需介入 | readmodel 判断顺序不完整 |
| **Coverage 健康** | `healthy/ok/active` 使用同一 typed predicate | ops 只认 `active` | 监控误报 |

### 4.5 认证为什么没有发现

**根因不只是代码错误，还包括生产形态认证被组件测试拆散。**

1. protected-submit 单元测试使用 `ticket-1` 等短 ID，并使用 fake lifecycle repository，没有触发 PostgreSQL `varchar(128)`。
2. SQLite 测试不执行 PostgreSQL varchar 长度语义，无法复现 SQLSTATE `22001`。
3. reclaim 测试证明“没有 Exposure 时可以释放”，但没有先投影 reservation-only Exposure。
4. Exposure 测试单独断言 reservation-only row 必须 `slot=true`，却没有与 terminal reclaim 联合。
5. lifecycle reprojection 测试明确断言“只有 lifecycle 语义变化才触发 reprojection”，与已批准设计相反。
6. Budget 测试明确断言 `claimed_position_slots=2` 时 `new_entry_allowed=true`，把产品语义矛盾固化为绿色测试。

因此原有组件测试可以全部通过，同时完整生产因果链仍然失败。新的认证必须使用 **真实 PostgreSQL + 生产长度身份 + 完整 Claim/Ticket/Command/Order/Current 因果链**。

## 5. 场景枚举与风险判断

| **场景** | **当前是否触发** | **原因** | **修复后要求** |
| --- | --- | --- | --- |
| **自然 fresh signal，账户真实空仓** | 是 | PG 2/2 先阻止容量 | 先刷新为 0/2，再仲裁候选 |
| **新 Ticket 进入本地订单注册** | 是 | Ticket ID 148 写入 varchar(128) | 使用真实 Signal ID；Ticket/Command 独立列 |
| **terminal pre-dispatch + reservation-only Exposure** | 是 | reclaim 自锁 | 忽略同 Claim 派生槽位并以快照证明无真实 exposure |
| **真实非零 position** | 不得释放 | 有真实资金 exposure | 始终保留 slot 和 reservation |
| **command outcome unknown / 已 dispatch** | 不得释放 | 可能存在外部订单 | 始终 fail closed，先 reconcile |
| **无活跃 Ticket，但政策 active** | Current 会过期 | worker 不选账户 scope | 30 秒独立刷新账户 Current |
| **candidate 因市场或容量被阻止** | Current 会 rollback | 同一 savepoint | 已提交账户事实不得回滚 |
| **2/2 真实仓位** | Budget flag 错误 | slot 未进入 flag | `new_entry_allowed=false`，Owner 状态仍为正常满仓 |
| **coverage covered/healthy** | ops 误报 | SQL 只认 active | 统一 typed predicate |

**风险结论：** 当前代码具备 fail-closed 特征，所以没有产生重复下单或未知交易所 outcome；但它不具备可靠的真实交易能力，因为每个新 Ticket 都可能在本地注册阶段重复失败，失败后又永久消耗容量。

## 6. 必须恢复的系统不变量

### 6.1 身份不变量

1. **Signal Event ID** 只能进入 `Order.signal_id` 或明确的 Signal Event 字段。
2. **Signal Evaluation ID** 只能保存真实 evaluation identity；没有时为 `NULL`。
3. **Ticket ID**、**Exchange Command ID**、**Account ID**、**Runtime Profile ID**、**Exchange Instrument ID**、**Exposure Episode ID** 在 ticket-bound 本地订单上必须独立保存。
4. 任何 ID 都必须使用其权威 schema 的长度；Ticket/Command/Event/Episode 为 `varchar(192)`。
5. 新 ticket-bound order 必须能从 PG 唯一反查 `Order -> Exchange Command -> Ticket -> Signal Event`。

### 6.2 容量守恒不变量

1. `active/consumed` Claim 在没有终态证据前持有一次风险、槽位和未反映保证金。
2. 同 Claim 派生的 reservation-only Exposure 是 **容量投影**，不是 **交易所 exposure 证据**。
3. terminal Ticket 只有同时满足以下条件才可释放：

   - `exchange_write_called=false`；
   - 所有 durable commands 均 `reconciled_absent`；
   - `dispatch_started_at_ms IS NULL`；
   - `exchange_order_id IS NULL`；
   - 完整新鲜账户快照证明该 Ticket/instrument/netting domain 无 position、无普通挂单、无 Algo 挂单；
   - 无未知 ownership 或冲突 episode。

4. release、Exposure flat、Budget refresh、lifecycle terminalization 必须同事务提交。
5. 真实 position、真实 open order、unknown command、dispatch 已开始、identity 不明时不得释放。

### 6.3 Current 不变量

1. active account-risk policy 是账户 Current 刷新的选择依据，不是 active Ticket。
2. 每个完整新鲜快照都更新 Current 的数量值、source snapshot、validity 和 `updated_at_ms`。
3. semantic fingerprint 只控制 append-only audit event，不控制 Current 刷新。
4. 网络请求和 subprocess 不得在 PG lock 内执行。
5. candidate claim 失败不得回滚已提交的账户事实。

### 6.4 产品语义不变量

1. `new_entry_allowed=false` 必须真实表示当前不允许新 ENTRY。
2. `reconciliation_state=matched` 可以与 `max_concurrent_positions_reached` 同时存在；满仓不是对账失败。
3. Owner readmodel 必须先区分正常满仓、技术不可用和需要介入，再生成产品状态。
4. coverage 健康判断必须由一个共享 predicate 管理。

## 7. 方案比较

| **方案** | **内容** | **优点** | **缺点** | **决定** |
| --- | --- | --- | --- | --- |
| **A. 手工 SQL 清两条 Reservation** | 直接改 `consumed -> released` | 快 | 下一次 Ticket 仍会 DBAPIError；无持续自愈；绕过正式状态机 | 拒绝 |
| **B. 仅扩容 signal_evaluation_id** | 把列改为 192 | 可消除本次长度错误 | 继续混用 Signal Evaluation 与 Ticket 身份；保留抽象错误 | 拒绝 |
| **C. 仅让 reclaim 忽略所有 reserved Exposure** | 放宽 slot 检查 | diff 小 | 可能错误释放真实 working/open exposure；安全不足 | 拒绝 |
| **D. 新建第二套账户刷新服务** | 独立 timer + 新 projection | 边界直观 | 增加第二 owner、重复交易所请求和竞态 | 拒绝 |
| **E. 恢复现有不变量并补齐身份与认证** | 修正 Order lineage、snapshot-aware reclaim、active-policy current owner、事务分离、语义统一 | 关闭完整问题类，不引入第二真源 | 需要 migration、PostgreSQL 测试和部署认证 | **采用** |

## 8. 选定架构

### 8.1 Ticket-bound Local Order Lineage V2

下一条 migration 在 `orders` 增加 ticket-bound execution lineage：

| **字段** | **类型** | **语义** |
| --- | --- | --- |
| `ticket_id` | `varchar(192)` | Action-Time Ticket |
| `exchange_command_id` | `varchar(192)` | 唯一 durable exchange command |
| `account_id` | `varchar(128)` | 交易账户 |
| `exchange_id` | `varchar(96)` | venue identity |
| `exchange_instrument_id` | `varchar(192)` | canonical instrument |
| `runtime_profile_id` | `varchar(128)` | runtime technical scope |
| `strategy_group_id` | `varchar(128)` | StrategyGroup identity |
| `exposure_episode_id` | `varchar(192)` | exposure episode |

同时将 ORM 的 `orders.id`、`orders.signal_id`、`orders.parent_order_id` 与当前 execution identity contract 对齐到 `192`。历史非 ticket-bound Order 允许新字段为 `NULL`；新 ticket-bound Order 必须满足条件约束：`exchange_command_id` 非空时，上述 lineage 全部非空，并且 `exchange_command_id` 唯一。

本地 Order 构造必须加载并校验：

```text
command.ticket_id == ticket.ticket_id
command.exchange_instrument_id == ticket.exchange_instrument_id
command.exposure_episode_id == ticket.exposure_episode_id
Order.signal_id = ticket.signal_event_id
Order.signal_evaluation_id = NULL
Order.ticket_id = ticket.ticket_id
Order.exchange_command_id = command.exchange_command_id
```

接口层不再手工拼装身份字典；使用一个 typed builder 生成 `Order`。旧的 `ticket_id -> signal_evaluation_id` 路径在同一任务中删除，不保留兼容分支。

### 8.2 注册失败分类与可观测性

本地注册失败必须保留安全、稳定、可搜索的内部原因：

```text
local_order_registration_schema_invalid
local_order_registration_constraint_violation
local_order_registration_connection_unavailable
local_order_registration_unknown
```

内部 audit/process outcome 至少记录：

- exception class；
- SQLSTATE；
- constraint name；
- local order ID；
- ticket ID hash 或受控 identity；
- `exchange_write_called=false`；
- `dispatch_started=false`。

不得记录 DSN、密码、API secret 或未掩码凭据。Owner 产品面只显示“订单准备阶段暂不可用，系统未向交易所提交”。

### 8.3 Account Truth Refresh Transaction

复用现有 **30 秒 lifecycle maintenance worker** 作为唯一调度所有者，但新增独立的 account-policy phase；不新增第二 timer。

```text
短 PG read：选择所有 activation_state=active 的 account/profile/exchange scope
-> 关闭事务
-> 每账户并发执行 5 个 Binance signed GET，总 timeout <= 8s
-> 短 PG write transaction：
   1. lock Account Risk Policy Current
   2. snapshot-aware terminal pre-dispatch reconciliation
   3. project Exposure Current
   4. project Budget Current
   5. terminalize resolved pre-dispatch lifecycle
   6. commit
-> 再运行 ticket-specific lifecycle maintenance
```

同一账户同一 tick 只抓一次完整快照，ticket-specific maintenance 复用该快照。

### 8.4 Snapshot-aware Terminal Pre-dispatch Reconciliation

新核心函数接收 typed `FullAccountRiskSnapshot`，而不是把 `brc_account_exposure_current` 当成外部真相。

对每个 terminal `consumed` Reservation：

1. `FOR UPDATE` 锁 Reservation、Ticket、Attempt、Lifecycle 和 commands。
2. 验证 Ticket 为 `expired/finalgate_rejected/invalidated/superseded`。
3. 验证 Attempt 从未 exchange write。
4. 要求所有 commands 已 `reconciled_absent`，而不是仅 `prepared`。
5. 使用 command client IDs、instrument、position bucket 和 episode 对完整快照分类。
6. 忽略 **同一个 Reservation 派生的 `reserved/qty=0` Current row**。
7. 发现真实 position、open order、unknown ownership 或另一 episode slot 时停止释放。
8. 原子执行：

```text
Reservation consumed -> released
reservation-only Exposure -> flat
Budget Current -> refreshed
Lifecycle submit_failed -> presubmit_reconciled_absent
append one reservation event + one lifecycle event
```

`presubmit_reconciled_absent` 是完成态：表示提交在 dispatch 前失败，交易所不存在订单或仓位，容量已经恢复。它不是成功交易，也不伪造 post-submit settlement/review。

### 8.5 事务分离

**事务 A：Account Truth Refresh**

- 输入：完整新鲜快照；
- 输出：已提交的 Exposure/Budget Current 与终态 claim 收敛；
- 不创建 signal、promotion、lane、Ticket 或 exchange command。

**事务 B：Candidate Claim And Ticket**

- 输入：事务 A 已提交的 Current snapshot lineage；
- 执行：capacity decision、Claim、post-claim projection、Ticket；
- candidate blocker 只回滚事务 B。

如果事务 A 与 B 并发，二者必须以相同顺序先锁 `Account Risk Policy Current`，再锁 `Account Budget Current`，防止陈旧 refresh 覆盖新 Claim。

### 8.6 Budget Current 一致语义

Budget projection 必须计算账户级入口 blocker：

```text
account_budget_current_stale
account_exposure_unknown
account_exposure_current_overflow
account_capacity_claim_current_overflow
max_concurrent_positions_reached
max_portfolio_open_risk_reached
max_portfolio_initial_margin_reached
```

`new_entry_allowed` 只有在这些账户级条件全部通过时才为 `true`。候选特定的 instrument/cluster/quantity blocker 仍由 capacity decision 计算。

Owner readmodel 判断顺序调整为：

1. Current stale / reconciliation mismatch / unknown exposure -> `temporarily_unavailable` 或 `needs_intervention`；
2. slots >= max 且 Current matched -> `running`，显示正常满仓；
3. capacity available -> `running`，显示仍可接收机会。

### 8.7 Coverage 健康统一

建立一个共享 typed predicate：

```text
coverage_state == covered
AND liveness_state IN {healthy, ok, active}
AND is_current == true
AND validity 未过期
```

Action-Time、candidate pool、forensics、ops health 和 server monitor 必须复用同一 predicate。东京当前 **22/22** coverage 为 `covered/healthy/current`，Action-Time 接受 22，旧 ops SQL 接受 0；修复后两者必须一致为 22。（来源：东京生产 PG `brc_watcher_runtime_coverage`，2026-07-20）

## 9. 数据修复设计

### 9.1 禁止项

- 禁止直接 `DELETE` Ticket、Reservation、Attempt、Lifecycle、Command 或 Exposure 历史；
- 禁止散落手写 SQL 把两条 Reservation 改为 released；
- 禁止把 `reconciled_absent` 改回 prepared；
- 禁止伪造 exchange order、fill、settlement 或 review；
- 禁止以当前 PG Exposure row 代替新的交易所快照。

### 9.2 正式修复路径

部署后，由同一 account-truth reconciliation service 在新鲜快照下处理当前两条记录。每条都必须再次满足：

```text
exchange position count for scope = 0
regular open order count for scope = 0
algo open order count for scope = 0
attempt.exchange_write_called = false
all commands = reconciled_absent
all dispatch_started_at_ms = null
all exchange_order_id = null
ticket terminal = true
```

修复后保留完整历史，只转换 Current/状态机：

| **对象** | **修复前** | **修复后** |
| --- | --- | --- |
| Reservation | `consumed` | `released` |
| Exposure | `reserved`, qty `0`, slot `true` | `flat`, qty `0`, slot `false` |
| Budget | `2/2`, allowed `true` | `0/2`, allowed `true` |
| Lifecycle | `submit_failed` | `presubmit_reconciled_absent` |
| Ticket | `expired` | 保持 `expired` |
| Command | `reconciled_absent` | 保持 |
| Attempt | `submit_failed`, write `false` | 保持历史事实 |

## 10. Cadence、性能与文件 I/O

### 10.1 生产 cadence

| **项目** | **目标** |
| --- | --- |
| Account refresh cadence | **30 秒**，沿用 lifecycle timer |
| 每账户 exchange reads | **5 个 signed GET / tick**，并发执行 |
| 总 snapshot timeout | **<= 8 秒** |
| PG write transaction | 目标 **< 250ms**，禁止网络 I/O |
| Current validity | **60 秒**；连续失败后自然 stale/fail closed |
| Candidate transaction | 独立短事务 |

一个 active account 的稳态请求量为约 **10 次 signed GET/分钟**。新增阶段必须复用同一 tick 的账户快照，不得为每个 Ticket 重复抓取。

### 10.2 PG 与磁盘增长

| **对象** | **无语义变化 tick 增长** | **语义变化时增长** |
| --- | ---: | ---: |
| `brc_account_exposure_current` | 0 新行，只 UPDATE current | 新 instrument current 才新增 |
| `brc_account_budget_current` | 0 新行，只 UPDATE current | 始终单行/account/profile |
| Reservation events | 0 | 每次真实状态转换 1 行 |
| Lifecycle events | 0 | 每次真实状态转换 1 行 |
| Runtime process outcome | 使用 current/upsert 或 journal；成功无变化不追加高频历史 | 失败或状态变化可追加受控事件 |
| JSON/MD/YAML/JSONL | **0 文件/tick** | 仅人工 archive，非 runtime authority |

生产 no-signal tick 必须保持 **0 个 JSON/Markdown 文件写入**。实现与部署验收必须运行 `scripts/audit_production_runtime_file_io.py`，`performance_risk.status` 必须为 `clear`。

## 11. 测试与认证设计

### 11.1 必须先失败的 RED 测试

1. 真实 PostgreSQL schema 下，148 字符 Ticket ID 走当前 order builder 得到 SQLSTATE `22001`。
2. 修复后同一 Ticket ID 可注册，且 `signal_evaluation_id IS NULL`、独立 lineage 完整。
3. terminal consumed Reservation 先投影为 reservation-only Exposure，再 reclaim，仍能释放。
4. 真实非零 position、真实 open order、unknown command、dispatch 已开始分别阻止 release。
5. `prepared_scopes=[]` 但 active policy 存在时，仍抓取并刷新账户 Current。
6. candidate capacity blocker 不回滚事务 A 的新 snapshot ID、validity 和 0/2 Current。
7. 2/2 Current 写 `new_entry_allowed=false`，Owner readmodel 显示正常满仓而非需介入。
8. `covered/healthy/current` 在 Action-Time 与 ops health 中均为健康。
9. 两个并发 candidate 与一个 account refresh 使用统一锁顺序，不超出 2 个槽位、不丢 Claim。

### 11.2 生产形态 full-chain

```text
long production-shaped signal_event_id
-> long action_time_invocation_id
-> 148-char ticket_id
-> capacity claim
-> Ticket
-> FinalGate rehearsal
-> Operation Layer paper/disabled exchange gateway
-> durable exchange command
-> local PG Order registration
-> forced pre-dispatch failure
-> command reconciled_absent
-> Ticket terminal
-> account snapshot flat
-> Reservation release
-> Exposure/Budget refresh 0/2
-> next different-instrument Claim succeeds
```

该认证必须使用 **真实 PostgreSQL**，不得由 SQLite、fake repository 或短 ID 替代。

### 11.3 负面矩阵

| **负面事实** | **必须结果** |
| --- | --- |
| command `outcome_unknown` | 不释放，`hard_safety_stop` |
| `dispatch_started_at_ms` 非空 | 不释放 |
| 任一 exchange order ID 存在 | 不释放 |
| 同 instrument 有未知 open order | 不释放 |
| 同 episode 有非零 position | 不释放 |
| snapshot 不完整或过期 | 不改变 Current 为 flat |
| policy scope 不匹配 | 不刷新、不 claim |
| refresh/claim 锁顺序相反 | 测试失败，禁止合并 |
| 第二次 repair tick | 0 重复 event，状态保持 |

## 12. 部署、Canary 与回滚

### 12.1 部署顺序

1. 本地定向、PostgreSQL、并发、full-chain、文件 I/O 门禁全部通过。
2. 使用当前东京 immutable release state machine 部署 exact SHA。
3. writer fence 下执行 migration **140**。
4. 启动 backend 只读/本地 PG 能力，运行长 ID local-order registration canary，不调用 exchange gateway。
5. 运行一次 account-truth refresh，重新抓取官方账户快照。
6. 正式 service 收敛两条 terminal pre-dispatch Reservation。
7. 断言 Budget `0/2`、Exposure flat、Lifecycle completed、22/22 coverage healthy。
8. 先恢复 account/lifecycle maintenance，再恢复 watcher 与 monitor。
9. 下一次自然 eligible signal 执行正常官方链路；缺少自然信号不阻塞工程闭环。

### 12.2 回滚边界

- migration 只做 additive schema 与约束升级；激活前可回滚 release pointer。
- 已经依据交易所空仓真相完成的 `consumed -> released` 是正确的不可逆历史转换，不自动伪造回 `consumed`。
- 如果部署后 Current 不一致，立即 fence 新 ENTRY，保留保护/退出能力，使用新鲜快照前向修复。
- 不使用 `git reset --hard`、破坏性 PG cleanup、Ticket 删除或历史重写。

## 13. 关联问题与处理范围

| **问题** | **是否同一 P0** | **处理** |
| --- | --- | --- |
| Ticket ID 错写 Signal Evaluation | 是 | Order Lineage V2 |
| terminal reservation 自锁 | 是 | snapshot-aware reconciliation |
| Current 刷新依赖 Ticket/lifecycle | 是 | active-policy account phase |
| Budget 2/2 仍 allowed | 是 | Budget/readmodel 语义统一 |
| coverage healthy 被 ops 误报 | 是，影响验收可信度 | shared predicate |
| 历史 `submit_failed` 污染 Owner 当前状态 | 是 | `presubmit_reconciled_absent` completed state |
| 旧 runner proof 告警 | 否，历史已关闭 Ticket | 保留为排除证据，不扩展本 P0 |
| 策略参数、止盈、移动止损 | 否 | 本设计不修改 |

## 14. 验收标准

### 14.1 工程完成

- 当前 HEAD 不再把 Ticket ID 写入 `signal_evaluation_id`；
- 生产长度 identity 的本地订单可在 PG 注册；
- terminal pre-dispatch Claim 在完整空仓快照下自动收敛；
- Current 每 30 秒按 active policy 刷新，与 active Ticket 无关；
- candidate rollback 不影响已经提交的账户 Current；
- Budget、Owner、Action-Time、ops monitor 使用一致状态语义；
- PostgreSQL 并发与负面测试通过；
- 文件 I/O 风险为 clear。

### 14.2 东京完成

- exact deployed SHA 与 migration `140` 一致；
- exchange position/order/algo order 仍为 0；
- 当前两个 Reservation 为 released；
- 当前两个 Exposure 为 flat/slot false；
- Budget 为 0/2、matched、new entry allowed；
- 两个 lifecycle 为 `presubmit_reconciled_absent`；
- 22/22 watcher coverage 在 Action-Time 与 ops health 中一致健康；
- timers/services 正常且无持续 blocker storm。

### 14.3 实盘能力边界

完成上述工程和东京认证后，可判定 **系统重新具备在下一次自然 eligible signal 到来时进入真实交易链路的技术能力**。真实成交、保护、止盈和结算仍由自然市场事件后的官方 FinalGate、Operation Layer 与 lifecycle 事实验证；不得用合成信号伪造实盘结果。

## 15. Chain Position

```text
chain_position: action_time_boundary
strategy_group_id: SOR-001
symbol: current fresh candidate scope
stage: fresh signal reaches account capacity and ticket-bound local order registration
first_blocker: action_time_boundary_not_reproduced
evidence: exchange truth is flat; two terminal submit_failed reservations remain consumed; current local-order builder writes a 148-character ticket_id into orders.signal_evaluation_id varchar(128), proven as PostgreSQL SQLSTATE 22001
next_action: implement Ticket/Command/Order identity conservation plus snapshot-aware terminal claim convergence and independent active-policy account-current refresh
stop_condition: a fresh flat-account snapshot commits 0/2 capacity before candidate arbitration, production-length local order identity registers successfully, and the next eligible natural signal can proceed without stale reservation blockage
owner_action_required: true_for_design_confirmation_only; false_for_ordinary_engineering_after_confirmation
signal_event_id: none for the currently capacity-blocked future event
promotion_candidate_id: none
action_time_lane_input_id: none
ticket_id: none for the next blocked event; two historical failed ticket IDs retained as incident evidence
authority_boundary: design and non-executing engineering only; no FinalGate bypass, Operation Layer bypass, forced signal, forced order, profile/sizing expansion, transfer, withdrawal, credential mutation, or destructive production cleanup
```
