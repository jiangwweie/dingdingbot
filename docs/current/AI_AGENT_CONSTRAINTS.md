---
title: AI_AGENT_CONSTRAINTS
status: CURRENT
authority: docs/current/AI_AGENT_CONSTRAINTS.md
last_verified: 2026-06-15
---

# AI Agent Constraints

This is the short current entry for agents working on the StrategyGroup runtime
pilot. If this file conflicts with historical archive material, this file wins.

## Objective

The project objective is:

```text
Owner enables a StrategyGroup
-> system observes market conditions
-> system runs all required checks inside official safety boundaries
-> system executes only through the official real-order path when allowed
-> system protects, reconciles, settles, notifies, and records
-> Owner supervises status and intervenes only on abnormal states
```

The Owner should not need to read raw evidence packets to operate the system.
Evidence packets are audit artifacts under the Owner-facing control board.

## Owner Supervisor Constraint

The Owner is a supervisor, not an execution operator.

Owner-facing product UI must answer:

- which StrategyGroups are enabled;
- which are running, waiting, processing, paused, or unavailable;
- whether funds, orders, positions, protection, and reconciliation are normal;
- whether the Owner needs to intervene;
- what one-line reason explains an unavailable or intervention state.

Owner-facing product UI must not make the Owner drive internal execution steps.
Do not turn these internal names into main UI labels, navigation, table columns,
primary cards, or action buttons:

```text
FinalGate
Operation Layer
RequiredFacts
candidate
authorization
preflight
proof
route
refId
blocker code
runtime grant
```

Allowed main UI language is deliberately small:

```text
未启用
运行中
等待机会
处理中
暂不可用
需要介入
已暂停
已完成
无需操作
资金正常
订单正常
持仓正常
保护正常
```

Internal gate names and evidence details may appear only in audit, detail, or
developer surfaces after the Owner asks to expand them.

## Standing Authorization

During this development-stage pilot, do not create new chat-confirmation
blockers for:

- focused `codex/*` branches;
- bounded local commits;
- Tokyo deploy apply inside the active stage;
- read-only Tokyo/live fact validation;
- watcher observation after StrategyGroup selection;
- StrategyGroup runtime bootstrap / attach through the official API path when
  it only creates admission, binding, and shadow runtime records;
- official in-boundary real order action after action-time FinalGate and
  Operation Layer pass.

This does not authorize FinalGate bypass, Operation Layer bypass, withdrawals,
transfers, credential changes, live-profile expansion, order-sizing default
expansion, stale-fact execution, missing protection, duplicate-submit risk, or
conflicting active position/open order execution.

## StrategyGroup Runtime Bootstrap

`scripts/bootstrap_strategygroup_runtime_pilot.py` is the current bounded bridge
from StrategyGroup picker state to observable runtime instances.

Default mode is plan-only. `--execute` may be used during this development
stage under standing authorization when the packet shows no inventory blocker.
The script may create StrategyFamily, StrategyFamilyVersion, Admission,
TrialBinding, risk acceptance, promotion confirmation, and shadow
StrategyRuntimeInstance records through official API surfaces.

It must not create candidate records, ExecutionIntents, orders, withdrawals,
transfers, exchange submit actions, or Operation Layer bypasses.

## Gate Behavior

Every blocker must classify itself as one of:

| Class | Meaning |
| --- | --- |
| `waiting_for_market` | No fresh signal exists |
| `missing_fact` | Required fact or evidence is absent or stale |
| `deployment_issue` | Tokyo or local deployment is behind current code |
| `active_position_resolution` | Position, open order, or protection state needs resolution |
| `hard_safety_stop` | Execution would violate the safety boundary |
| `review_only_warning` | Strategy evidence is weak but not a live-safety blocker |

Gates exist to preserve bounded real-funds safety. They must not become opaque
all-AND project blockers.

Gate classes are internal safety classifications. The main Owner UI should map
them to one terse product sentence, for example:

| Internal condition | Owner-facing sentence |
| --- | --- |
| stale or missing facts | 事实不可用，暂不能使用 |
| open order conflict | 有订单处理中，暂不能使用 |
| active position conflict | 有持仓处理中，暂不能使用 |
| missing protection | 保护未就绪，暂不能使用 |
| reconciliation mismatch | 订单结果不一致，等待系统处理 |
| `hard_safety_stop` | `需要介入` |
| `review_only_warning` | `运行中` (audit/detail available, not an Owner blocker) |

## Watch Branch Intake

Useful P0 content from `codex/runtime-signal-watcher-feishu` is carried
selectively. The broad docs reset has been completed on this branch through the
2026-06-15 docs-governance compression.

## Historical Docs

Historical docs are compressed into:

```text
docs/history-archive-2026-06-15-pre-governance.tar.gz
```

They are recovery material only. They must not be used as current product truth
or as a source of new chat-confirmation blockers.
