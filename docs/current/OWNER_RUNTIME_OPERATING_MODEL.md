---
title: OWNER_RUNTIME_OPERATING_MODEL
status: CURRENT
authority: docs/canon/STRATEGYGROUP_RUNTIME_PILOT_OVERLAY.md
last_verified: 2026-06-15
---

# Owner Runtime Operating Model

The Owner operating model is simple:

```text
select StrategyGroup
-> observe
-> fresh signal
-> candidate
-> FinalGate
-> Operation Layer
-> reconcile
-> review
```

## Owner Decisions

The Owner decides:

- which StrategyGroup is selected;
- the small bounded risk profile;
- whether to pause, park, revise, promote, or kill a StrategyGroup after review;
- when the project moves from development-stage pilot to production operations.

## System Responsibilities

The system handles:

- watcher observation;
- fresh signal detection;
- RequiredFacts readiness;
- candidate and authorization evidence;
- action-time FinalGate;
- official Operation Layer submission path;
- post-submit finalize, reconciliation, budget settlement, and review evidence.

## Owner-Facing State

The Owner should see:

| State | Meaning |
| --- | --- |
| `observing` | Watcher is healthy and waiting for a fresh signal |
| `signal_ready` | Fresh signal exists and needs RequiredFacts/candidate checks |
| `blocked` | Missing fact, hard stop, conflict, or deployment issue exists |
| `candidate_ready` | Fresh candidate and authorization evidence are ready |
| `finalgate_ready` | Action-time FinalGate passed |
| `submitted` | Official Operation Layer submitted an auditable action |
| `settled` | Reconciliation and budget settlement are complete |

Raw evidence packets remain available for audit but are not the Owner's daily
operating interface.
