---
title: TRADING_KERNEL_OPERABILITY_REPAIR_DESIGN
status: CURRENT_DESIGN
program_id: TKR-OPERABILITY-REPAIR
last_verified: 2026-07-30
---

# Trading Kernel 可运行性修复设计

## 1. 文档定位

### 1.1 核心结论

本次修复不是继续给部署脚本增加例外，而是完成一次面向
**动态 StrategyUniverse、多仓容量、持续认证和受保护部署**的运行时收敛。
目标仍是一个 Trading Kernel、一个 PostgreSQL 权威和四个常驻 worker；
错误或过时的控制流、数据字段、测试与部署分支直接删除或重写，不保留兼容层。

本设计是待实施修复的稳定权威，不记录生产 SHA、标签、Ticket、测试数量或瞬时
服务状态。生产事实与当前关键路径仅由
`docs/current/MAIN_CONTROL_ROADMAP.md` 持有。

### 1.2 状态词

| 标记 | 含义 | 是否可作为当前生产事实 |
| --- | --- | --- |
| **已知事实** | 从当前跟踪代码、测试或既有权威合同直接验证 | 是，但瞬时事实仍只进入 Main Control Roadmap |
| **目标设计** | 本修复完成后必须成立的语义 | 否，完成实现与验收前不得宣称已部署 |
| **推荐决策** | 已有充分工程依据，但涉及 Owner 产品或资本政策 | 否，必须在对应执行卡前获得明确确认 |

### 1.3 适用范围

本设计只覆盖：

1. Reconciliation 调度与后台进度保证；
2. Instrument Certification、Signal Admission 与部署认证的一致性；
3. 活跃 protected Ticket 场景下的正式 ENTRY Promotion；
4. 常规发布和停机重建的显式状态机；
5. 多 Ticket 的止损风险与保证金容量语义；
6. 与上述语义冲突的代码、测试、文档和 schema 基线清理。

本设计不扩大交易所、账户、币种、策略 Event 或资金范围，不引入美股执行链，
不允许凭证修改、划转、提款、逐单人工批准或绕过 durable Exchange Command。

## 2. 重构目的

### 2.1 原 StrategyUniverse 重构的正确目的

**StrategyUniverse 重构**的业务目的不是在部署时逐个手工安装几十小时，而是：

1. 让每个 Strategy Event 使用版本化的 **1..10 个动态标的成员集合**；
2. 让 Warming 只读取市场与账户事实，产生 **零 StrategySignal**；
3. 让全部成员通过认证后由 PostgreSQL 原子切换 Active current pointer；
4. 让 Signal、CapacityClaim 与 Ticket 冻结 Universe 版本和 digest；
5. 让后续 Universe 替换不改变既有 exposure 的生命周期；
6. 让首批标的通过一次批量流程完成，不要求 Owner 操作内部 gate。

这些目的仍然正确。当前问题来自运行时调度、认证时间、ENTRY Promotion、容量政策
和部署状态机没有与该模型一起完成，而不是动态标的模型本身错误。
（来源：`P0_TRADING_KERNEL_REBUILD_DESIGN.md`、
`strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md`）

### 2.2 本次修复的产品结果

修复后，系统应满足：

```text
一次配置 approved manifest
-> 一次 Certification Batch
-> 六个 Event 的 Universe 串行安装但自动推进
-> Active pointer 原子完成
-> ENTRY 在 flat 或 exact protected 场景安全恢复
-> 正常运行持续刷新认证
-> 新 Signal 仅在认证新鲜时参与仲裁
```

部署耗时由真实外部读取和固定数量的本地阶段决定，不再由一个活跃 Ticket 对后台工作
造成无限饥饿，也不再要求七份 **60 秒**认证记录偶然同时新鲜。

## 3. 已知客观事实

### 3.1 缺陷清单

| ID | 等级 | 当前事实 | 直接证据 | 运行影响 |
| --- | --- | --- | --- | --- |
| **OR-P0-01** | P0 | Active Position Reconciliation 每次完成后按短间隔重新到期，且位于 Certification、Settlement、Review、Fee Monitor 之前 | `src/trading_kernel/interfaces/reconciliation_worker.py`；`deploy/systemd/brc-trading-kernel-reconciliation-worker.service` | 持续存在 active position 时，后台工作没有确定性进度保证 |
| **OR-P0-02** | P0 | protected handover 禁止同时 enable ENTRY，现有 Promotion 又要求全局 flat | `scripts/trading_kernel/deploy_tokyo_release.py`；`scripts/trading_kernel/promote_entry.py` | 活跃 protected Ticket 部署后无法通过官方路径恢复 ENTRY |
| **OR-P0-03** | P0 | 每个新 Ticket 用 wallet × `planned_stop_risk_fraction` 作为独立目标，并可使用全部剩余可执行保证金 | `src/trading_kernel/domain/capacity_sizing.py`；`src/trading_kernel/application/build_capacity_claim.py` | `max_concurrent_tickets=3` 可能名义存在、实际被首个 Ticket 长期耗尽 |
| **OR-P1-01** | P1 | 部署 Gate 要求全部标的认证 fresh，但 ready candidate 查询不连接认证表 | `scripts/trading_kernel/certify_readonly.py`；`src/trading_kernel/infrastructure/pg_signal_repository.py` | 部署语义与持续运行 admission 语义分裂 |
| **OR-P1-02** | P1 | 认证有效期、eligible 复查和最大等待均默认为 **60 秒**，每次 cadence 只推进一个标的 | `src/trading_kernel/interfaces/reconciliation_worker.py` | 七标的批量部署容易因时间窗口而抖动或超时 |
| **OR-P1-03** | P1 | 发布脚本以条件分支隐式组合阶段，异常后统一恢复全部 safety services | `scripts/trading_kernel/deploy_tokyo_release.py` | 恢复动作无法区分 schema 是否存在、identity 是否完成、Lifecycle 是否可安全启动 |
| **OR-P2-01** | P2 | runner 在请求 Fee Monitor 后，无论该 tick 是否真正执行监控都更新进程内时间戳 | `scripts/trading_kernel/run_reconciliation_worker_once.py` | 监控“已观察时间”可能是假进度 |

### 3.2 当前测试不能证明生产语义

下列测试目前可以通过，但没有构造生产中的 **5 秒 tick + 2 秒 active-position
重新到期**，或直接固化了错误发布语义：

| 测试 | 当前覆盖 | 缺失或错误语义 | 处理决定 |
| --- | --- | --- | --- |
| `test_reconciliation_worker_fairness.py` | Routine Work 连续存在 | 没有持续 Active Critical Position | 重写为 production-shaped virtual clock |
| `test_multi_ticket_closure_fairness.py` | 多 Ticket 顺序推进 | 每 tick 只推进 1ms，避开生产重新到期 | 重写为 5 秒 cadence 与真实 due-at |
| `test_strategy_universe_operability_architecture.py` | AST 调用次数 | 调用次数不能证明公平性或最大等待 | 删除 AST 计数断言，替换结构与行为测试 |
| `test_deploy_tokyo_release.py` protected 分支 | protected handover | 固化 protected 时永远不能恢复 ENTRY | 重写为 exact protected promotion |
| `test_deploy_tokyo_release.py` failure 分支 | 异常恢复 | 固化任意阶段都启动相同 services | 重写为 phase-aware failure matrix |

依据项目工程规则，以上测试不作为历史兼容合同；错误测试直接删除或整体重写。
（来源：`docs/current/AI_AGENT_CONSTRAINTS.md`）

## 4. 根因分析

### 4.1 控制流根因：优先级被实现成永久排他

当前 Reconciliation 一次调用返回一个结果。Critical Work 在 Routine Work 和
Certification 之前；Active Position 又会比常驻进程的下一次轮询更早重新到期。
因此“Safety 优先”在真实 cadence 下退化为“Housekeeping 永远没有机会”。

**设计修正**是把优先级和进度保证同时建模：Safety 仍先执行，但 Housekeeping 有
独立 cadence、独立 deadline 和最大等待上界，不依赖 Critical Work 暂时消失。

### 4.2 Gate 根因：部署、运行和动作时事实有三套含义

当前存在三套未对齐的认证语义：

1. 部署要求七个 current certification 同时 fresh；
2. Signal ready candidate 不要求 certification fresh；
3. CapacityClaim/dispatch 再读取动作时账户与 instrument facts。

正确分层应为：

```text
持续认证 = 参与仲裁的可用性门槛
动作时事实 = 最终安全门槛
部署 Certification Batch = 目标 release 的一次完整能力证明
```

三者用途不同，但必须共享同一 instrument identity、规则分类和 blocker vocabulary。

### 4.3 容量根因：并发上限不是并发可用性

`max_concurrent_tickets=3` 只限制数量；若一个 Ticket 可以使用全部剩余保证金，
“允许三个”并不等于“系统通常能容纳多个”。同时，现有
`CapacityUsage.gross_risk_at_stop` 已构造却未进入 sizing，导致账户级计划止损风险没有
成为 admission 输入。

**设计修正**是显式拆分单 Ticket 上限、账户总上限、单 Ticket 保证金上限和账户总
保证金上限；所有限制在同一纯 domain sizing 决策中计算，并在 Ticket 原子提交时重验。

### 4.4 时间根因：单条 TTL 被误用为批量完成窗口

**60 秒 TTL**可以表达一次短期事实的新鲜度，但不能同时承担七标的批量完成、六个
Universe 激活和发布 Promotion 的总窗口。批量部署需要一个带 manifest digest、目标
identity、成员结果和完成时间的 Certification Batch，而不是对独立 current rows 做
瞬时计数。

### 4.5 测试根因：fixture 消除了真实故障条件

测试使用 1ms 时间推进、Routine-only aggregate 或 AST 调用计数，均没有复现生产
轮询周期、重新调度时间和外部读取耗时。测试通过只能证明 fixture 内部自洽，不能证明
常驻 worker 在真实 cadence 下有界推进。

## 5. 目标运行时架构

### 5.1 保持四个常驻 Worker

生产仍只有 **Observation、Entry、Lifecycle、Reconciliation 四个 systemd service**。
不新增第五个认证 worker，不恢复 timer 冷启动，不让部署脚本代替正常 runtime 生产
认证事实。

```text
Observation Worker
  -> closed market facts / detectors / StrategySignal

Entry Worker
  -> certified candidate / action-time facts / Claim / Ticket / ENTRY

Lifecycle Worker
  -> Stop / TP1 / Runner / controlled EXIT

Reconciliation Worker
  -> Safety Lane
  -> Housekeeping Lane
```

### 5.2 Reconciliation 双 Lane

| Lane | 工作所有权 | 默认优先级 | 进度合同 | 每 cycle 上限 |
| --- | --- | --- | --- | --- |
| **Safety Lane** | Unknown outcome、post-fill risk、active position truth | 最高 | 每次到期优先执行；不得被 Housekeeping 推迟 | 1 个 action |
| **Housekeeping Lane** | Certification、Settlement、Review、Fee Monitor | 次高 | 每类工作有 next due 和 max wait；即使 Safety 连续存在也必须推进 | 1 个 action |

每个 process cycle 按以下确定性顺序执行：

1. 校验 runtime commit/schema fence；
2. claim 并执行至多一个 Safety action；
3. 再检查 Housekeeping deadline，执行至多一个到期 action；
4. 记录实际执行的 action 类型、耗时、下次 due 和结果；
5. 只有 Fee Monitor 真正完成读取并持久化后，才推进其 next due。

两个 action 顺序执行；任何 venue I/O 都在 PostgreSQL transaction 外。Safety action
失败只重排对应 exact work，不吞掉 Housekeeping 的 deadline。若 Unknown outcome 要求
全局 ENTRY fence，fence 立即生效，但只读认证、Settlement 和 Review 仍可按各自安全
语义推进。

### 5.3 Housekeeping 公平性

Housekeeping 选择器使用 **earliest-deadline-first + stable identity**，而不是固定 if/return
顺序。每个 kind 持有独立 due-at：

| Kind | 目标 cadence | 最大等待 | 超时行为 |
| --- | ---: | ---: | --- |
| Settlement | 立即或 30 秒重试 | **60 秒内至少尝试一次** | Owner 状态显示 closure delayed；ENTRY 不因 closure 被误启 |
| Review | 立即或 30 秒重试 | **60 秒内至少尝试一次** | 在 economics visibility grace 内重试，超时后精确记录 unavailable |
| Certification refresh | **5 分钟**刷新目标 | **2 分钟**调度等待 | 标的暂时不参与新 ENTRY；不终态拒绝 Signal |
| Fee Monitor | **5 分钟** | **10 分钟** | 记录 stale monitor；不伪造完成时间 |

这些值是工程默认值，可由受版本控制的 runtime 配置调整；生产部署必须在本地
production-shaped 测试中验证实际边界。

## 6. Certification、Signal 与 Admission

### 6.1 持续认证模型

`brc_instrument_certification_current` 继续持有每个 runtime profile + instrument 的当前
状态。目标默认值为：

1. eligible `valid_for = 10 分钟`；
2. eligible refresh target `= 5 分钟`；
3. transient retry `= 30 秒`；
4. owner-action recheck `= 5 分钟`；
5. scheduler max wait `= 2 分钟`。

认证 TTL 是 admission 的可用性证据，不替代 dispatch 前的动作时账户、盘口、position、
order rule、leverage 和 margin facts。

### 6.2 Certification Batch

部署新增正式的 **Certification Batch**：

| 数据对象 | 权威内容 | 生命周期 |
| --- | --- | --- |
| `brc_instrument_certification_batches` | batch id、target commit/schema/seed、runtime profile、manifest digest、状态、开始/完成/有效时间 | 一次部署或显式重认证一条 |
| `brc_instrument_certification_batch_members` | exact instrument、结果、facts digest、observed/valid time、blocker | 每个 batch 每个成员一条不可变结果 |
| `brc_instrument_certification_current` | 正常运行当前可用性 | 持续 upsert |

Batch 只能在 exact manifest 全部成员属于当前 approved scope、identity 一致、全部 eligible
且最早 valid-until 覆盖 promotion 最小窗口时完成。失败 batch 不自动缩小 manifest；修复
原因后创建新 batch，旧 batch 只保留审计事实。

Batch 在 ENTRY disabled 的 Owner Policy stage 下完成。Promotion 将该 policy 从 **v1**
原子推进到仅开放新 ENTRY authority 的直接 successor **v2** 时，postflight 允许同一 Batch
继续作为认证证据；只接受 `v1 -> v2` 且 `new_entry_submit_enabled=true` 的 exact stage
continuity。跳到 v3、跨版本、仍 disabled 或其他 policy drift 均使 Batch 失效。这样避免
“Batch 要求当前 v1、arm 后又要求当前 v2”的循环依赖，同时不放宽风险、scope、manifest、
commit、schema 或 seed identity。

### 6.3 Candidate Admission

`list_ready_candidates()` 必须按 exact runtime profile + instrument 连接 current
certification，并要求：

```text
status = eligible
blocker_code IS NULL
valid_until_ms > action_now_ms
```

认证过期时：

1. Signal 与 `candidate_ready` lineage 保留到自身 expiry；
2. Signal 暂不进入仲裁，不产生 terminal rejection；
3. 认证恢复后，未过期 Signal 可重新参与；
4. Signal 自身过期后由现有 stale closure 处理；
5. dispatch 继续以最新动作时事实作为最终 fail-closed 判断。

## 7. Protected ENTRY Promotion

### 7.1 目标语义

**Protected ENTRY Promotion**允许 exact protected exposure 在发布后继续被 Lifecycle
保护，同时恢复对其他 Netting Domain 的新 ENTRY。它不是绕过 flat gate，也不是一般
active-position 热迁移。

### 7.2 两种正式模式

| 模式 | 允许的内部状态 | 外部状态 | ENTRY Promotion |
| --- | --- | --- | --- |
| **Flat Promotion** | 零 active Ticket、Reservation、Command、Incident | 零 position、零 open order | 通过 batch 与 identity gate 后允许 |
| **Protected Promotion** | 全部 active Ticket 均为 exact protected，零 unknown/open Incident | 每个 Ticket 有 exact position 与完整 protection，且无未归属 position/order | 通过 exact protected snapshot 后允许 |

Protected 模式必须由程序从 PostgreSQL 自动枚举全部 active Tickets，禁止 Owner 手工拼接
Ticket 清单。程序逐 Ticket 验证：

1. Aggregate 状态仅为 `position_protected` 或 `runner_protected`；
2. Budget Reservation 和 Netting Domain hold 与 Ticket 一致；
3. internal position quantity、active Stop、TP1/Runner lineage 完整；
4. exchange position side/quantity 与内部 exact 相等；
5. active reduce-only protection 归属、数量和 purpose exact；
6. 零 unresolved Exchange Command、零 open Incident；
7. 零未归属 position、open order 或旧 writer；
8. runtime identity、schema、seed、policy、manifest 和 Certification Batch 一致。

其中 policy 一致性包含上节定义的 exact `v1 -> v2` ENTRY-arm stage continuity；它不是
任意旧 policy version 的兼容规则。

### 7.3 启动顺序

```text
ENTRY 保持 write fence
-> 原子写入/重验 new-entry authority
-> 启动 Entry service while fenced
-> 验证 worker identity、DB connectivity、无 mutation
-> 最终 postflight
-> 移除 fence
```

任一步失败都恢复 fence 并停止 Entry。既有 exposure 的 Lifecycle、Reconciliation、
Settlement 和 Review 权威不受 `new_entry_submit_enabled` 影响。

## 8. 容量与风险语义

### 8.1 Owner 已批准政策

Owner 已批准以下个人小资金、多机会并发政策。它是本 repair 的实施目标；在代码、schema、
seed、测试和 Tokyo cutover 完成前，不得把它描述为已生效的生产事实：

| 字段 | 推荐值 | 所有权 | 目的 |
| --- | ---: | --- | --- |
| `max_concurrent_tickets` | **3** | Owner Policy | 架构并发上限 |
| `max_ticket_stop_risk_fraction` | **0.03** | Owner Policy | 保留单 Ticket 的右尾收益弹性 |
| `max_gross_stop_risk_fraction` | **0.06** | Owner Policy | 通常容纳两个完整风险 Ticket，第三个使用剩余风险 |
| `max_ticket_initial_margin_fraction` | **0.45** | Owner Policy | 防止一个 Ticket 吞掉全部可用保证金，同时保留集中度 |
| `max_gross_initial_margin_utilization` | **0.90** | Owner Policy | 全账户初始保证金总上限 |
| `max_leverage` | **10** | Owner Policy | 绝对安全上限 |
| configured leverage | **5x** | Exchange readonly fact | 固定账户事实，Kernel 不修改 |

最不确定的不是公式，而是不同策略真实 stop distance 分布在 **45% 单 Ticket 保证金上限**
下的实际风险利用率、第三 Ticket 可用率、七个 instrument 最小下单量和 TP1/Runner
可执行性。该不确定性必须用历史 Replay 与当前 Binance readonly rules 在本地验证，
不能在服务器试错；Replay 不能静默改写 Owner 已批准参数。

### 8.2 纯 Domain 公式

```text
remaining_gross_stop_risk
= wallet_balance * max_gross_stop_risk_fraction
  - current_gross_risk_at_stop

ticket_stop_risk_budget
= min(
    wallet_balance * max_ticket_stop_risk_fraction,
    remaining_gross_stop_risk
  )

remaining_gross_margin
= margin_balance * max_gross_initial_margin_utilization
  - max(exchange_total_initial_margin, current_reserved_margin)

ticket_margin_budget
= min(
    margin_balance * max_ticket_initial_margin_fraction,
    available_margin,
    remaining_gross_margin
  )

selected_quantity
= min(risk_limited_quantity, margin_limited_quantity)
```

`planned_stop_risk_fraction` 的含义过于模糊，目标 schema 直接替换为上述显式字段；
旧字段、旧 fixture 和旧 seed 删除，不提供兼容读取或双写。

### 8.3 现有 Exposure 的处理

若修复部署时已有 protected Ticket 超过新的单 Ticket 上限：

1. 不取消其 protection，不撤销 Lifecycle 或 controlled exit 权威；
2. 账户总容量按实际 reservation/exposure 计算；
3. 在容量回落前，新的 Ticket 以明确 blocker 拒绝或暂缓；
4. 不伪造“仍有三个槽位”来绕过保证金或总止损风险。

## 9. 数据、事务与 Identity

### 9.1 Schema 目标

本修复改变 Owner Policy 和 capacity projection 字段，并新增 Certification Batch，因此
属于 **schema identity 变化**。实现时创建下一版单一 clean baseline，并删除旧 baseline；
生产只允许在 exchange flat、内部 closure 完成后执行 empty-schema rebuild，不做 in-place
兼容迁移。

### 9.2 原子边界

新 ENTRY 的原子提交继续包含：

```text
lock exact account exposure + netting domain
-> revalidate policy and current aggregate usage
-> commit Ticket + Reservation + Domain hold + Aggregate + Event + ENTRY Command
```

Certification Batch 的成员写入不跨外部读取持有 transaction。每个成员先完成 bounded
readonly I/O，再以 expected batch identity 与 lease 写入；最后一个成员只能在 transaction
内原子完成 batch。

### 9.3 Identity

以下 identity 必须一起匹配：

1. runtime commit；
2. schema revision；
3. seed identity；
4. runtime profile；
5. Owner Policy id/version；
6. manifest digest；
7. Certification Batch id；
8. 每个 protected Ticket 与 Netting Domain。

任一不一致均保留 ENTRY fence。Identity mismatch 不通过重试、默认值或旧 schema reader
自动修复。

## 10. 部署状态机

### 10.1 正式阶段

| 阶段 | 完成条件 | 允许运行的 Worker | 失败恢复 |
| --- | --- | --- | --- |
| **STAGED** | exact committed release 与 markers 已落盘 | 旧 release 按原状态 | 删除未激活 stage 或重新校验 |
| **QUIESCED** | Entry fenced，四个 writer 已停 | 无 | 若 schema 未改，可恢复旧 safety workers |
| **IDENTITY_ROTATED** | target runtime/schema/seed identity 原子完成 | 无 | 保持 fence，禁止旧 writer |
| **READONLY_WORKERS_STARTED** | Observation、Reconciliation 使用 target identity active | Observation、Reconciliation | 保持 fence，停止不匹配 worker |
| **TARGET_CERTIFIED** | exact Certification Batch complete | Observation、Reconciliation | 保持 fence，修复 blocker 后新建 batch |
| **LIFECYCLE_STARTED** | Lifecycle identity 与无副作用 smoke 通过 | 三个 safety workers | 保持 fence；Lifecycle 不安全则停止 |
| **ENTRY_STARTED_FENCED** | Entry active、fence present、零 mutation | 四个 workers | 停 Entry，保留 safety workers |
| **ENTRY_UNFENCED** | final postflight 与 authority atomic arm 成功 | 四个 workers | 立即 refence，停止 Entry，保护既有 exposure |

### 10.2 Phase-aware 恢复

部署控制器必须按 `cutover_tokyo.py` 已有 PostgreSQL ops journal 模式记录 exact operation
identity 和阶段。异常处理不得再无条件启动同一组 services：schema 被删除后不能恢复旧
worker；target identity 未完成时不能启动 Lifecycle；Entry 在任何不确定状态下必须
inactive/disabled/fenced。

### 10.3 Operation-owned rebuild 与 Batch-before-worker

`REBUILD_APPLICATION_SCHEMA` 是 **Cutover operation-owned effect**，不能仅因当前 schema
已经通过同 revision 的结构检查就判定本次阶段完成：

1. 新 `cutover_id` 的 journal 尚无该阶段记录时，必须执行一次 clean rebuild；
2. 同一 `cutover_id` 已进入该阶段后发生中断，才允许使用 schema postcondition 判断 effect
   是否已经完成并避免重复删除；
3. schema health 证明“当前结构可用”，不能替代“本次 operation 已执行 destructive effect”
   的 journal 事实。

Certification Batch 必须在 Reconciliation 启动前创建：

1. seed 完成后先安装第一个 exact Warming Universe，使 approved instruments 成为数据库
   事实；
2. 在 worker 尚未启动时创建 exact pending Batch；
3. Batch identity 必须绑定 target commit/schema/seed、Policy version 和 manifest；
4. 随后才启动 Observation、Reconciliation；
5. Reconciliation 第一轮成员认证必须直接写入该 Batch；
6. Universe bootstrap 复用第一个 Warming Universe 与 pending Batch，完成六个 Universe
   Active 与 Batch complete；
7. 禁止通过等待既有 certification 过期来补齐 Batch 成员。

## 11. Performance 与可观测性

### 11.1 必须观测的指标

1. 每个 lane 最近成功时间、oldest due age、执行耗时和结果；
2. 每个 Housekeeping kind 的 next due 与 max-wait breach；
3. Certification Batch 完成耗时、成员耗时和最早 valid-until；
4. ready Signal 因 certification stale 暂不可用的数量；
5. account gross stop risk、reserved margin、active Ticket count；
6. deployment phase、fence、service identity 和恢复动作；
7. Fee Monitor 真实完成时间，而不是调度尝试时间。

### 11.2 性能边界

正常 no-signal cadence 继续产生零 JSON/Markdown 文件。查询必须使用 exact key 或 bounded
selector；Certification Batch 最大成员数由 Universe 合同限制，不允许全历史扫描。
外部 I/O、SSH、subprocess 和 exchange reads 均有 timeout，且不在数据库 transaction 内。

## 12. 删除与替换清单

### 12.1 删除

1. 固化“一个 tick 只能做一种 Reconciliation 工作”的隐式返回结构；
2. `planned_stop_risk_fraction` 旧 policy/schema/fixture 语义；
3. protected handover 永久禁止后续 ENTRY 的测试和分支；
4. 异常后无条件启动全部 safety services 的恢复分支；
5. 以 AST 调用次数宣称调度公平的架构测试；
6. Fee Monitor 未执行却推进 observed-at 的状态；
7. 依赖七条独立认证记录偶然同时 fresh 的 Promotion 判定。

### 12.2 保留并强化

1. 四个 persistent worker；
2. PostgreSQL current + append-only lineage；
3. one Ticket per Exposure Episode；
4. global new ENTRY serialization；
5. Netting Domain isolation；
6. durable Exchange Command、unknown outcome 和 partial fill 语义；
7. fixed exchange leverage readonly adoption；
8. exact runtime fence；
9. flat-only destructive schema rebuild。

## 13. 决策登记

| 决策 | 状态 | 结论 | 生效条件 |
| --- | --- | --- | --- |
| **D-OR-01** | 已定 | 保持四个 persistent workers，Reconciliation 内部双 Lane | 本设计实施 |
| **D-OR-02** | 已定 | Certification stale 只暂停 admission，不终态拒绝未过期 Signal | 本设计实施 |
| **D-OR-03** | 已定 | 支持 exact protected ENTRY Promotion | exact facts 全通过 |
| **D-OR-04** | 已定 | schema 变化使用 flat-only clean rebuild，不做兼容迁移 | 本地 rehearsal 通过 |
| **D-CAP-01** | Owner 已批准 | 单 Ticket `3%`、账户总止损风险 `6%`、单 Ticket 保证金 `45%`、总保证金 `90%`、最多 `3` 个 Ticket | TC-05 按 exact 参数实现并验证 |

**D-CAP-01** 已关闭决策门，但批准不等于已部署。只有 TC-05、完整本地验证和 Tokyo
flat-only cutover 全部完成后，生产 seed 和 runtime 才能被描述为实施该政策。

## 14. 完成定义

本设计只有在以下条件全部成立时才算实现完成：

1. 持续 active position 下，Certification、Settlement、Review、Fee Monitor 均在最大等待
   上界内取得进度；
2. flat 和 protected 两种 Promotion 均通过 full-chain 测试；
3. stale certification 与恢复不会丢失仍有效的 Signal；
4. Capacity 使用单 Ticket 与账户总风险/保证金上限；
5. 部署每个阶段都有确定的 start、pass、fail 和 resume 语义；
6. disposable PostgreSQL 从空库完成下一版单一 baseline、seed、batch bootstrap、worker
   progression 和 Entry Promotion；
7. 完整 suite、Ruff、Mypy、architecture、runtime file-I/O、diff checks 全部通过；
8. Tokyo 只在本地证据完成后执行 readonly preflight 和受控 flat rebuild；
9. 错误旧代码、旧测试、旧 schema 和旧文档语义已删除；
10. 当前生产证据写回 `MAIN_CONTROL_ROADMAP.md`，本设计不复制瞬时状态。
