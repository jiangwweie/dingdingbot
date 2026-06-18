---
title: OWNER_RUNTIME_OPERATING_MODEL
status: CURRENT
authority: docs/current/OWNER_RUNTIME_OPERATING_MODEL.md
last_verified: 2026-06-18
---

# Owner Runtime Operating Model

The Owner operating model is simple:

```text
enable StrategyGroup
-> system runs automatically inside official boundaries
-> Owner supervises status
-> Owner intervenes only when intervention is requested
-> Owner reviews outcomes later
```

## Owner Decisions

The Owner decides:

- which StrategyGroup is enabled, paused, parked, or killed;
- the allocated subaccount risk budget and official runtime profile;
- whether to adjust risk or pause automation when an abnormal state appears;
- whether to keep, revise, promote, park, or kill a StrategyGroup after review;
- when the project moves from development-stage pilot to production operations.

The Owner-provided subaccount allocation is already the upstream risk-control
decision. Within that allocation and the selected official runtime profile, the
system should behave aggressively toward eligible right-tail opportunities. It
should not ask the Owner to re-confirm or re-risk-assess every in-boundary
opportunity, and it should not silently reduce leverage, notional, or exposure
because the opportunity is risky. A 100% loss of the allocated experiment
capital is within the project premise.

## System Responsibilities

The system handles:

- watcher observation;
- signed GET-only live fact precollection for account, position, open orders,
  budget coverage, protection templates, and next-attempt readiness;
- fresh signal detection;
- RequiredFacts readiness;
- candidate and authorization evidence;
- action-time FinalGate;
- official Operation Layer submission path;
- post-submit finalize, reconciliation, budget settlement, and review evidence.

Those are system responsibilities, not normal Owner workflow steps.

The system's hard stops are operational boundaries: wrong account, out-of-scope
StrategyGroup/symbol/side/profile, stale facts, duplicate submit risk, missing
protection, conflicting active position or open order, FinalGate bypass,
Operation Layer bypass, withdrawal, transfer, credential mutation, or
unauthorized live-profile/sizing mutation. They are not generic reasons to make
the system reduce leverage, shrink notional, slow eligible submits, or avoid
right-tail opportunities after the Owner has allocated loss-capable capital.

## Owner-Facing State

The Owner should see product states:

| State | Meaning |
| --- | --- |
| `not_enabled` | Owner has not enabled this StrategyGroup for runtime automation |
| `running` | StrategyGroup automation is enabled and healthy |
| `waiting_for_opportunity` | Automation is enabled and waiting for a usable market opportunity |
| `processing` | The system is handling signal, execution, protection, order, position, reconciliation, or settlement work |
| `temporarily_unavailable` | The StrategyGroup cannot be used right now; show one plain sentence |
| `needs_intervention` | Owner action is required, such as pause, risk adjustment, or recovery review |
| `paused` | Owner or system pause is active |
| `completed` | The latest run is settled and recorded |

Raw evidence packets remain available for audit but are not the Owner's daily
operating interface.

## Runtime Product State

During the StrategyGroup runtime pilot, the server should refresh Owner-readable
product state after each watcher tick:

```text
watcher tick
-> signed GET-only live facts
-> StrategyGroup readiness packet
-> runtime pilot product state
-> notification only when state materially changes
```

If live facts are ready but no fresh signal exists, the correct product state is
`waiting_for_opportunity`. This is not an Owner blocker and should not ask for
chat confirmation.

## Product Language Rule

Main Owner screens should avoid internal gate names. Use terse language:

| Internal wording | Owner wording |
| --- | --- |
| RequiredFacts missing/stale | 事实不可用 |
| FinalGate / Operation Layer not reached | 系统自动处理中 |
| preflight / proof / route | Details only |
| blocker code | Details only |
| reconciliation mismatch | 订单结果不一致，等待系统处理 |

If everything is healthy, the UI should say `运行中`, `等待机会`, or `无需操作`.
Do not show a next-step prompt for healthy automation.

## Document Authority

This file is the current Owner-operating SSOT. Historical docs compressed into
`docs/history-archive-2026-06-15-pre-governance.tar.gz` are recovery material
only and must not become current operating instructions.
