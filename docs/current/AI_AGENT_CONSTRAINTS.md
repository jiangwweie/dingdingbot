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
Owner selects a StrategyGroup
-> system admits or rejects it with clear reasons
-> watcher observes the market
-> fresh signal prepares candidate evidence
-> action-time FinalGate runs
-> official Operation Layer is the only real order path
-> post-submit finalize, reconciliation, budget settlement, and review close the loop
```

The Owner should not need to read raw evidence packets to operate the system.
Evidence packets are audit artifacts under the Owner-facing control board.

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
