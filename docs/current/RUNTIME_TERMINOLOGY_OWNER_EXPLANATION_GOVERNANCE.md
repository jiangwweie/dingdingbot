---
title: RUNTIME_TERMINOLOGY_OWNER_EXPLANATION_GOVERNANCE
status: CURRENT_DESIGN
authority: docs/current/RUNTIME_TERMINOLOGY_OWNER_EXPLANATION_GOVERNANCE.md
last_verified: 2026-07-06
---

# Runtime Terminology Owner Explanation Governance

## Purpose

This document defines how the project should explain runtime, strategy, and
execution-chain terminology to the Owner.

The goal is:

```text
PG current state remains the source of truth.
Developer terms remain available for audit.
Owner-facing explanations use plain Chinese and concrete trade-chain meaning.
```

This document does not authorize FinalGate bypass, Operation Layer bypass,
exchange writes, live profile changes, sizing changes, or strategy-scope
expansion.

## Known Objective Facts

| Fact | Evidence |
| --- | --- |
| The Owner is a supervisor, not the execution operator | `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md` |
| Owner-facing states should use product language such as `running`, `waiting_for_opportunity`, `processing`, and `needs_intervention` | `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md` |
| Internal terms such as FinalGate, Operation Layer, RequiredFacts, candidate, and authorization must not be primary Owner UI labels | `AGENTS.md`, `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md` |
| PG current state and append-only lineage are the target authority for L2-L7 explanations | `docs/current/RUNTIME_CONTROL_STATE_DB_ARCHITECTURE.md`, `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md` |
| The temporary L2-L7 draft contains a starter glossary, but it is not a durable authority document | `docs/current/L2_L7_PRETRADE_CHAIN_RESET_TEMPORARY_DRAFT.md` |

## Analysis

The recurring communication problem is not that the Owner cannot understand the
system. The problem is that the system currently exposes internal engineering
terms before translating them into the Owner's question:

```text
昨天有没有机会？
哪条策略 / 哪个币 / 哪个方向？
推到哪一步？
为什么没有交易？
我是否需要做决定？
```

Therefore the system needs a **terminology explanation layer**. It must be a
read-model/export layer over PG truth, not another source of truth.

## Core Rule

Every runtime-facing status should be explainable in two layers:

| Layer | Audience | Example |
| --- | --- | --- |
| **Owner language** | Owner daily supervision | `SOR/ETH 做多机会已进入交易前检查，但还没有通过最终安全门。无需你操作。` |
| **Audit language** | Developers, reviewers, incident analysis | `action_time_lane_input exists; ticket missing; first_blocker=ticket_materialization_pending` |

The Owner explanation must never invent authority. It may explain a blocker,
but it must not grant live-submit permission.

## Required Explanation Fields

Every current projection that can appear in Owner or forensic explanations
should expose these fields or equivalents.

| Field | Meaning | Source |
| --- | --- | --- |
| `owner_state` | Owner product state such as `waiting_for_opportunity` or `processing` | Derived from PG current state |
| `plain_language_stage` | Plain Chinese stage reached | Glossary-backed projection |
| `plain_language_reason` | One sentence explaining why no trade or what is happening | Derived from first blocker and lineage |
| `plain_language_next_system_action` | What the system will do next | Derived from next action |
| `owner_action_required` | `true / false` | Policy/safety classification |
| `owner_action_reason` | If Owner action is required, the policy or abnormal intervention reason | PG policy/safety blocker |
| `technical_stage` | Developer stage such as `promotion_candidate` or `action_time_lane` | PG lineage |
| `first_blocker_class` | Contract blocker class | `BLOCKER_CLASSIFICATION_CONTRACT.md` |
| `lineage_refs` | Signal, promotion, lane, ticket, order refs | PG lineage |
| `authority_boundary` | Explicit no-bypass / no-exchange-write statement when relevant | Runtime contract |

## Glossary

### Strategy And Scope Terms

| Term | Chinese | Plain explanation | Owner-facing wording | Authority note |
| --- | --- | --- | --- | --- |
| **StrategyGroup** | 策略组 | 一套可被系统治理、观察、推进和复盘的策略资产 | 策略 | Registry/policy identity, not order authority |
| **Symbol** | 币种 / 标的 | 具体交易对象，例如 `ETHUSDT` | 币种 | Must map to exchange instrument before submit |
| **Side** | 交易方向 | `long` 是做多，`short` 是做空 | 方向 | Must come from strategy semantics, not mirroring |
| **Event Spec** | 事件规格 | 这个策略到底吃什么市场事件，例如 `MPG-LONG` | 机会类型 | Defines allowed strategy/symbol/side/event |
| **Candidate Universe** | 候选交易范围 | 哪些策略、币、方向、事件允许被观察和计算 | 候选范围 | Observation scope, not submit authority |
| **Owner Policy** | Owner 授权策略 | Owner 允许哪些策略、币种、方向、预算、配置进入哪一阶段 | 授权范围 | Stored as versioned policy, not chat memory |
| **Runtime Profile** | 运行配置 | 账户、环境、杠杆/名义金额边界、执行配置组合 | 运行配置 | Cannot be silently expanded |
| **Live Submit Scope** | 真实提交范围 | 哪些策略/币/方向允许进入真实下单前检查 | 真实提交范围 | Narrower than observation scope |
| **Version** | 版本 | 策略语义、事件、事实、政策、执行规则的固定版本 | 当前版本 | New versions affect future events only |

### Facts And Signal Terms

| Term | Chinese | Plain explanation | Owner-facing wording | Authority note |
| --- | --- | --- | --- | --- |
| **RequiredFacts** | 必需事实 | 策略事件成立前必须满足的机器条件 | 必要条件 | Must be machine-evaluable |
| **Fact Snapshot** | 事实快照 | 某一刻系统计算出来的市场/账户/安全事实 | 事实记录 | Must bind symbol, side, event, time |
| **Runtime Coverage** | 服务器运行覆盖 | 服务器确实在看某策略、币种、方向、事件 | 服务器正在看 | Symbol-only coverage is insufficient |
| **Watcher** | 观察器 | 服务端定时或常驻读取市场/账户状态的程序 | 监控程序 | Read-only unless official submit path is reached |
| **Live Signal Event** | 实时信号事件 | 当前真实市场发生了策略要吃的事件 | 市场机会 | Must use real market event time |
| **Fresh Signal** | 新鲜信号 | 事件刚发生且仍在有效窗口内 | 新机会 | `generated_at` cannot create freshness |
| **Event Time** | 事件时间 | 市场事件确认的时间，通常是触发 K 线收盘时间 | 市场确认时间 | Different from report generation time |
| **Generated At** | 生成时间 | 文件、报告或投影被生成的时间 | 报告生成时间 | Never signal freshness authority |
| **Computed Not Satisfied** | 已计算但不满足 | 系统算了条件，但市场事实没有达标 | 市场条件没到 | Market blocker, not engineering blocker |
| **Market Wait Validated** | 已验证市场等待 | 非市场问题都闭合，只差真实新机会 | 健康等待机会 | Requires full checklist |

### Promotion And Action-Time Terms

| Term | Chinese | Plain explanation | Owner-facing wording | Authority note |
| --- | --- | --- | --- | --- |
| **Candidate Pool** | 候选池 | 当前所有策略/币/方向的准备状态汇总 | 候选机会池 | Generated view over PG |
| **Promotion Candidate** | 可升级候选 | 新鲜机会满足条件，可以继续往交易前链路推进 | 可推进机会 | Not an order candidate |
| **Arbitration** | 仲裁 | 多个机会同时出现时，系统决定谁进入唯一窄通道 | 机会排序选择 | Deterministic and PG-backed |
| **Action-Time Lane** | 临近交易通道 | 被选中进入交易前检查的一条机会链路 | 交易前通道 | At most one real-submit lane |
| **Action-Time Ticket** | 交易前正式票据 | 唯一说明“这笔交易是谁”的机器记录 | 这笔候选交易 | Ticket is not order authority |
| **Ticket Hash** | 票据哈希 | 用关键字段锁住这笔候选交易身份 | 交易身份锁 | Prevents loose reconstruction |
| **Budget Reservation** | 预算预留 | 这笔候选交易临时占用的预算证明 | 预算检查 | Required before FinalGate |
| **Protection Reference** | 保护引用 | 止损/失效条件来自哪个策略事件事实 | 保护依据 | Operation Layer cannot guess stops |

### Gate And Submit Terms

| Term | Chinese | Plain explanation | Owner-facing wording | Authority note |
| --- | --- | --- | --- | --- |
| **FinalGate** | 最终安全门 | 对一张 Action-Time Ticket 做最后安全检查 | 最终安全检查 | Must consume `ticket_id` |
| **Operation Layer** | 官方执行层 | 真正执行官方下单路径的层 | 官方提交路径 | Must consume `ticket_id + finalgate_pass_id` |
| **Protected Submit** | 带保护的提交 | 主订单和保护/止损语义绑定的提交尝试 | 带保护下单 | No detached protection success |
| **Runtime Safety State** | 运行安全状态 | 判断当前是否允许真实提交的安全快照 | 交易安全状态 | Only source for `submit_allowed` |
| **Live Submit Allowed** | 允许真实提交 | 系统边界允许进入官方真实提交路径 | 真实提交允许 | Requires policy, facts, gates, protection |
| **Hard Safety Stop** | 硬安全停止 | 错账户、过期事实、无保护、重复提交等不可绕过问题 | 安全停止 | Owner cannot manually override execution safety |

### Post-Submit And Review Terms

| Term | Chinese | Plain explanation | Owner-facing wording | Authority note |
| --- | --- | --- | --- | --- |
| **Protection** | 保护 | 止损、失效、保护单或保护状态 | 保护正常/异常 | Required for complete submit success |
| **Reconciliation** | 对账 | PG、系统订单、交易所状态是否一致 | 订单/持仓对账 | Resolves stale local state |
| **Settlement** | 结算 | 预算、盈亏、保证金占用的后处理 | 结算 | Cannot rewrite strategy authority |
| **Review** | 复盘 | 这次信号/候选/订单给策略治理带来什么学习 | 复盘 | Recommends governance changes only |
| **Goal Status** | 目标状态 | 当前运行目标的汇总状态 | 当前运行状态 | Must summarize PG current projection |
| **Daily Table** | 每日推进表 | 主控每天看的单张推进面 | 今日推进面 | Management surface, not source truth |
| **Current Projection** | 当前投影 | PG 事实和事件投影出的当前状态 | 当前状态 | Exactly one owner projector |
| **Legacy Diagnostic** | 旧诊断 | 旧文件/旧链路留下的诊断信息 | 历史诊断 | Cannot set current blocker |

## Owner Explanation Templates

### No Fresh Signal

```text
当前没有可交易机会。
系统已覆盖 {strategy_count} 个策略和 {candidate_count} 个候选范围。
最近的阻断是：{plain_language_reason}。
Owner 无需操作。
```

### Computed Not Satisfied

```text
{strategy_group_id} / {symbol} / {side} 的市场条件已计算，但还没满足。
不交易的原因是：{failed_facts_plain_language}。
这属于市场没给机会，不是工程链路断了。
```

### Promotion Candidate Exists

```text
{strategy_group_id} / {symbol} / {side} 出现了新机会。
系统已把它升级为可推进机会，正在等待仲裁或进入交易前通道。
当前还没有真实下单。
```

### Action-Time Ticket Missing

```text
机会已经接近交易前检查，但系统还没有生成“这笔交易是谁”的正式票据。
缺少票据时，FinalGate 不能可靠检查同一笔候选交易，所以不会下单。
```

### FinalGate Or Operation Layer Blocked

```text
这笔候选交易已经有正式票据，但最终安全检查或官方提交路径没有通过。
系统停止在安全边界内，没有绕过下单。
Owner 只有在提示为“需要介入”时才需要处理。
```

## Projection Requirements

| Projection | Required plain-language fields |
| --- | --- |
| **Candidate Pool** | per candidate `plain_language_stage`, `plain_language_reason`, failed facts, whether ticket can be created |
| **Daily Table** | one-line daily conclusion, closest actionable candidate, first blocker in Owner language |
| **Goal Status** | current product state, whether Owner action is required, lineage refs |
| **Server Monitor** | quiet/notify reason, no local-cache wording, Feishu-ready message |
| **Runtime Forensics** | yesterday/recent signal story: detected signal, stage reached, why no trade, engineering vs market |
| **Future Frontend** | Owner product language first, developer/audit terms behind details |

## Implementation Plan

### Batch A - Glossary-Backed Mapping

Create a typed glossary map used by projectors and forensic tools.

| Item | Requirement |
| --- | --- |
| Inputs | Contract blocker class, chain stage, lineage refs |
| Output | Owner explanation fields and developer detail fields |
| Forbidden | Reading repo MD/JSON as runtime source |
| Tests | Every known blocker class has one Owner phrase and one technical detail phrase |

### Batch B - Projection Field Addition

Add plain-language fields to PG-backed projection exports.

| Projection | Acceptance |
| --- | --- |
| Candidate Pool | Every row with blocker has `plain_language_reason` |
| Daily Table | Top row and summary explain whether it is market wait, engineering gap, policy gap, or safety stop |
| Goal Status | `owner_action_required=false` is explicit for healthy waiting and ordinary processing |
| Server Monitor | Feishu notification text uses Owner terms |

### Batch C - Forensics Skill Update

Runtime signal forensics should answer in this order:

```text
detected signal
-> stage reached
-> lineage object that exists
-> first missing object
-> market / engineering / policy / safety classification
-> plain-language reason
```

### Batch D - Future Frontend Read Model

The future frontend should not render internal terms as primary labels. It
should consume an Owner explanation read model derived from PG current state.

## Acceptance Tests

| Test | Expected result |
| --- | --- |
| A candidate has `computed_not_satisfied` | Owner text says market facts failed, not generic error |
| A fresh signal has promotion but no ticket | Owner text says formal trade ticket is missing |
| An action-time ticket exists but FinalGate is not ready | Owner text says final safety check has not passed |
| A hard safety stop exists | Owner text says safety stop and whether Owner intervention is needed |
| PG lineage exists and JSON export differs | Explanation follows PG lineage, not JSON |

## Chain Position

```text
chain_position: owner_explanation_projection
strategy_group_id: active WIP StrategyGroups
symbol: active candidate universe
stage: terminology_governance_design
first_blocker: owner-readable explanation fields are not yet consistently projected from PG lineage
evidence: current docs and repeated Owner clarification requests
next_action: implement glossary-backed explanation mapping after design approval
stop_condition: Candidate Pool / Daily Table / Goal Status / Server Monitor / forensics all expose consistent plain-language reason fields
owner_action_required: no
authority_boundary: explanation only; no FinalGate, Operation Layer, exchange write, profile mutation, or sizing mutation
```
