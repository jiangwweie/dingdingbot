---
title: OWNER_RUNTIME_OPERATING_MODEL
status: CURRENT
last_verified: 2026-10-12
---

# Owner Runtime Operating Model

## 首尔人工接管运行模型

**本分支默认全自动，人工干预后整笔永久转人工管理。**程序负责发现机会、首次开仓与初始止损；未干预时继续 TP1、Runner 和现有退出。
Owner 在**币安 App**进行有效的部分/全部减仓，或新增、修改、撤销相关退出挂单，不需要等待成交即可被识别为整笔接管。未提交或交易所拒绝的操作不构成接管证据。
（来源：[Owner 决策](../superpowers/specs/2026-11-06-app-manual-takeover-v1-owner-decisions.md)、[干预识别](../../src/trading_kernel/application/observe_trade_management.py)。）

### 管理权与职责

| 状态 | 系统可做 | 系统不可做 | Owner 操作 |
| --- | --- | --- | --- |
| **AUTO** | 依原规则保护、TP1、Runner、退出、对账 | 加仓、盲重发未知命令、重复消费信号 | 初始止损确认后可在 App 干预 |
| **REVIEW_REQUIRED** | 查询订单及完整历史，核实归属和已发请求 | 未查清前新的自动处置、把未知直接当人工 | 查看待核实状态，不必为了干预先暂停全局 ENTRY |
| **MANUAL** | 只读同步仓位/挂单/成交、核算占用、结算复盘 | 移止损、自动保本、TP1/Runner续管、自动平仓、撤残单、补仓 | 管理整笔余仓和已有 TP1/止损，清理残单 |

**MANUAL 不回 AUTO**：改回原价、原 TP1 成交、重启和升级都不会交还管理权。新独立 Ticket 默认 AUTO，仍须满足新机会、rearm 和风险门槛。
系统自然成交和自己的 durable Command 不算人工；事实缺失时进入待核实，只有完整证据允许解除 REVIEW_REQUIRED。
（来源：[管理权模型](../../src/trading_kernel/domain/trade_management.py)、[Reducer](../../src/trading_kernel/domain/reducer.py)、[派发写门](../../src/trading_kernel/application/dispatch_exchange_command.py)。）

### 控制台政策与 App 干预

Owner 在控制台管理全局 ENTRY、策略、Selection、方向与预算；这些操作不代替对某笔交易的 App 接管。
**暂停 ENTRY 只阻止新入场**，AUTO 旧仓继续保护；MANUAL 旧仓不会因暂停、恢复或受控全平被重新纳入自动退出。
首次入场必须来自程序；首版不允许人工加仓、重新开仓或反手，不增加每日亏损熔断。
保护事实缺失或人工风险不可核算时，系统限制新增自动开仓、继续核实，不擅自重挂止损或平掉人工仓。
（来源：[Owner控制](../../src/trading_kernel/application/owner_control.py)、[人工风险](../../src/trading_kernel/domain/manual_position.py)。）

### 归零、残单与账务

**余仓归零不等于交易结束**。未确认的残单、命令结果及账务仍须核实；Owner 清理相关挂单后，系统才能确认标的占用可释放并推进结算。
程序继续保留成交、手续费、资金费及原始入场身份；缺少可归属的经济事实时显式 unavailable，不伪造零收益。
本产品同一账户同标的跨多空只允许一个非终态 Ticket，交易所仍须为 independent sides；同标的双向禁入不是修改账户成单向模式。
（来源：[只读收尾](../../src/trading_kernel/application/reconcile_ticket.py)、[持久化模型](../../src/trading_kernel/infrastructure/pg_models.py)。）

## Runtime Process Topology

The four Kernel workers are four independent, persistent operating-system
processes managed by `systemd`. They share PostgreSQL authority and coordinate
through durable current rows, leases, Tickets, Events, and Exchange Commands;
they do not call one another as an in-memory pipeline.

| Process | Product responsibility | Exchange-write boundary |
| --- | --- | --- |
| Observation worker | Refresh market facts, evaluate StrategyGroups, and persist Signals or explicit no-signal outcomes | Read-only |
| Entry worker | Arbitrate eligible Signals, build CapacityClaims and Tickets, and dispatch the serialized ENTRY command | New ENTRY only |
| Lifecycle worker | Install/maintain AUTO protection, process TP1/Runner and authorized exits; MANUAL write guard stays closed | AUTO existing-Ticket protection and exit |
| Reconciliation worker | Management observation, readonly MANUAL accounting/closure, exact outcome recovery; isolated notification loop | AUTO recovery/cleanup only; no MANUAL exit or cancellation |

The static Owner Console is served by Nginx and is not a Kernel worker. The
Owner API is a separate service that reads product state and writes only
controlled PostgreSQL authority; it does not load exchange credentials or
dispatch orders. A worker can restart independently, while commit/schema
identity and PostgreSQL leases prevent a stale process from becoming a second
writer.

## Owner-Facing States

| State | Meaning |
| --- | --- |
| `not_enabled` | Policy does not enable the StrategyGroup |
| `running` | Observation and runtime are healthy |
| `waiting_for_opportunity` | All non-market readiness conditions pass and no fresh signal exists |
| `processing` | A signal, Ticket, command, position, or settlement is active |
| `temporarily_unavailable` | A current non-Owner condition blocks use |
| `needs_intervention` | A safety or policy action requires Owner attention |
| `paused` | Owner or system pause is active |
| `completed` | The latest Ticket is terminal and reviewed |

The primary Owner surface uses product language. Internal identities and
diagnostic fields remain available for audit without turning the Owner into an
execution operator.

## 独立飞书通知与 Transactional Outbox

首尔使用独立群和机器人，不能复用 Tokyo 出口。**管理权、实际余仓、入场均价、当前已核实止损/覆盖、策略短语义和北京时间**构成紧凑消息；不输出 Ticket/订单号，不借用旧自动止损声称当前完整保护。

| 业务变化 | 消息职责 | 不能推断的事实 |
| --- | --- | --- |
| 开仓且初始保护确认 | 已保护开仓，显示实际仓位与均价 | 接单回执不等于成交或 TP1 已挂 |
| 首次人工接管、归属待核实及解除 | 使用本事务最终事实，明确管理权 | 事实恢复不意味着 MANUAL 回 AUTO |
| TP1/可证实退出成交、平仓与残单 | 显示真实余量及需清理事项 | 仓位减少不证明成交价或全部收尾完成 |
| 保护/风险变化、运行异常及恢复 | 重要变化通知，不逐条刷普通改单 | 通知故障不变成交易故障或新增开仓熔断 |

**Transactional Outbox**随业务事务提交最终快照和正文，回滚则无消息；首次投递冻结发送正文，网络在事务外。
Reconciliation 的隔离异步循环使用租约/CAS、有限重试和过时抑制，不新增交易 Worker。
没有通道时消息保留待发且不扣尝试次数，失败保留可见状态；平台接受不代表已读，未知网络结果可能重复。
投递状态单独显示，不以通知心跳证明交易新鲜度。密钥仅在首尔受保护启动配置中加载。
（来源：[通知策略](../../src/trading_kernel/application/notice_policy.py)、[Outbox](../../src/trading_kernel/infrastructure/pg_notice_outbox.py)、[投递](../../src/trading_kernel/infrastructure/notice_delivery.py)、[通知方案](../superpowers/plans/2026-11-09-manual-notification-templates-v1.md)。）

## Multi-Position Meaning

Multi-position is the default kernel capability. Different Netting Domains can
hold protected positions concurrently, for different instruments. This manual product forbids overlapping long and
short exposure or nonterminal Tickets in the same account/instrument. New ENTRY admission remains globally serialized. Capacity is
controlled by current Owner budget policy, not by a hard-coded two-position
architecture.

Exact deployed Policy identity and values are production facts owned only by
`MAIN_CONTROL_ROADMAP.md`. Stable operating guidance defines Policy v4
semantics without becoming authority for whether that Policy is active.

Policy v4 defines three concurrent Tickets, explicit per-Ticket and gross risk
and margin limits, directional-risk and Exposure Family limits, a minimum
materialization ratio, maximum `10` leverage, and `cross` margin. Supported
instruments remain configured at fixed `5x`; the kernel adopts and revalidates
that account fact without mutating leverage.

Capacity is demand-based within the persisted policy's Ticket, gross,
directional, Family, strategy-side, Netting Domain and margin ceilings; three equal positions are not
promised. Disabling `new_entry_submit_enabled` stops only new ENTRY; it does not
remove protection or recovery authority from an AUTO Ticket with exchange
exposure. MANUAL remains readonly regardless of global ENTRY.

## Selection And Capacity Controls

Global ENTRY Resume and per-strategy Dynamic activation are separate TOTP
Owner operations. Activating Dynamic stages an exact future period; it is not
instant Universe takeover. Static can continue until the switching Vacuum;
existing Tickets retain their frozen lifecycle. CPM/MPG/MI/BRF2 have independent
Selection controls; Crypto SOR remains retired and must not be resumed.

Capacity B allows two distinct same-strategy/side opportunities under the
unchanged global three-Ticket, risk and Family ceilings. Selection controls
instruments, and Capacity bounds risk. No extra economic review or mandatory
Shadow waiting period is introduced.

## Owner Directional Risk V1 — approved target

Implementation and exact deployment/Owner activation posture are recorded only
in [MAIN_CONTROL_ROADMAP.md](MAIN_CONTROL_ROADMAP.md). Owner Directional
Risk V1 replaces the earlier eligibility-only planning boundary with an
explicit directional-risk preference: Owner selects bullish, neutral or
bearish; Capacity applies a tightening-only overlay to scoped Crypto new ENTRY.
The [experiment profile](RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md) owns the
exact approved matrix and risk denominator. The choice does not assert that
the account is already net long/short, reserve a strategy slot, or override a
maintenance pause. Signals and existing Ticket lifecycle retain their rules.

The Console shows requested/pending/effective state, effective time, direction
usage, over-limit existing exposure and a reminder after 24 hours. A saved
request is not yet effective when an old-authorized ENTRY is still in flight.
The Owner need not operate internal gates; Entry and Reconciliation resolve
the transition through the existing durable-command path. No automatic
neutral reset, flatten, historical Signal replay, or leverage change occurs.

See the [approved design](../superpowers/specs/2026-10-25-owner-directional-risk-v1-design.md)
and its implementation plan for concurrency proof and acceptance boundaries.
Software capability, authenticated Owner activation, and economic evidence
remain separate; current production facts belong only to `MAIN_CONTROL_ROADMAP.md`.
