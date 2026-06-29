---
title: GOAL_MODE_TASK_PACKET_CONTRACT
status: DEPRECATED
authority: historical compatibility only
last_verified: 2026-06-29
---

# Goal Mode Task Packet Contract

## Deprecated

This file is no longer current execution authority.

Do not use Goal Packet, Task Card, Evidence Packet, `Done When`, `Allowed
files`, `Forbidden files`, or similar long markdown scaffolds as the default
main-control workflow.

Current execution coordination is defined by `AGENTS.md` and
`docs/current/AI_AGENT_CONSTRAINTS.md`:

```text
short execution brief
-> trading lifecycle capability or first blocker
-> validation
-> next checkpoint
```

The main control loop should stay centered on:

```text
fresh signal
-> Tradeability Decision
-> Runtime Safety State
-> Execution Attempt
-> Order Lifecycle
-> Review Outcome
-> StrategyGroup State Update
```

This compatibility file must not be used to add new packet, report, or
governance layers.
