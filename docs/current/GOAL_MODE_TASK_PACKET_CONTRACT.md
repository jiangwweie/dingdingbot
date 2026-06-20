---
title: GOAL_MODE_TASK_PACKET_CONTRACT
status: CURRENT
authority: docs/current/GOAL_MODE_TASK_PACKET_CONTRACT.md
last_verified: 2026-06-20
---

# Goal Mode Task Packet Contract

## Purpose

This file defines how the architecture window turns global direction into
bounded execution work for the main runtime window.

The contract exists to reduce repeated Owner intervention. It does not replace
current code, runtime gates, FinalGate, Operation Layer, live RequiredFacts, or
Owner policy.

## Operating Split

Use this split:

```text
architecture window
-> Goal Packet
-> main runtime window execution
-> Evidence Packet
-> architecture verdict
```

| Role | Responsibility |
| --- | --- |
| Architecture window | Define direction, scope, boundary, acceptance, and no-go rules |
| Main runtime window | Execute one bounded Goal Packet to checkpoint |
| Evidence Packet | Report facts, changed files, generated artifacts, tests, deploy state, and blockers |
| Architecture verdict | Accept, revise, park, split, or escalate the next stage |

## Goal Packet Required Shape

A Goal Packet must include:

| Field | Meaning |
| --- | --- |
| `Task ID` | Stable stage-level identifier |
| `Goal` | One outcome the execution window must produce |
| `Why` | Which project capability this advances |
| `Problem class` | The engineering problem class this task closes |
| `Capability unlocked` | The concrete system capability that must exist after the task |
| `Next engineering bottleneck` | The next problem class expected after this task completes |
| `Scope` | Included work and explicit non-goals |
| `Allowed files` | Files or directories the worker may touch |
| `Forbidden files` | Files or directories the worker must not touch |
| `Required inputs` | Current docs, generated packets, or code sources to read first |
| `Implementation requirements` | Behavioral requirements and integration rules |
| `Global authority model` | Owner-policy versus system-process rules the worker must preserve |
| `Rehearsal / simulation boundary` | Which branches can be closed without live signal and which remain live-only |
| `Validation` | Commands, generated evidence, or review checks required |
| `Done When` | Objective checkpoint criteria |
| `Deploy condition` | Whether deploy is forbidden, optional, or required |
| `Fresh signal interrupt` | What to do if a real fresh signal appears |
| `Safety boundary` | Conditions that stop the task |
| `Report format` | Required Evidence Packet contents |

## Evidence Packet Required Shape

The execution window must report:

| Field | Meaning |
| --- | --- |
| `Goal status` | completed, blocked, partial, or stopped by fresh-signal interrupt |
| `Changed files` | Exact files changed |
| `Generated artifacts` | Exact output paths created or refreshed |
| `Validation` | Commands run and pass/fail result |
| `Authority boundary` | Confirmation that no unauthorized live authority was introduced |
| `Deploy state` | not deployed, local only, deployed, or deploy blocked |
| `Decision impact` | Which StrategyGroup decision, runtime capability, or Owner surface changed |
| `Capability unlocked` | The concrete capability now available and how it was verified |
| `Closed engineering problem` | The engineering problem class closed by this task |
| `Next engineering bottleneck` | The next problem class surfaced by the completed work |
| `Rehearsal / simulation proof` | What was closed by dry-run, simulation, paper path, or local lifecycle tests |
| `Residual risk` | Remaining known risk or next evidence needed |

## Capability-First Goal Mode

Goal-mode work must be capability-first, not artifact-first.

Every non-trivial Goal Packet must close one engineering problem class and move
the system to the next problem class. A task that only explains why the project
cannot move forward is incomplete unless it proves the blocker is genuinely
market-dependent, live-outcome-dependent, or authority-dependent.

Use this progression shape:

```text
current bottleneck
-> engineering closure
-> capability unlocked
-> next engineering bottleneck
```

Examples:

| Current bottleneck | Capability unlocked | Next engineering bottleneck |
| --- | --- | --- |
| Strategy gap unclear | StrategyGroup gap matrix and decision impact are machine-checkable | RequiredFacts or classifier closure |
| RequiredFacts not mapped | Missing/present/stale facts are machine-classified | Candidate/auth preparation |
| Candidate/auth not reproducible | Candidate and authorization evidence are generated consistently | FinalGate action-time check |
| Submit lifecycle incomplete | Submit/reject/partial/timeout/protection branches are handled locally | Reconciliation and settlement |
| Reconciliation unclear | Position, order, protection, budget, and PnL are reviewable | Review Ledger decision feedback |

Do not use `waiting_for_market` as a generic answer for engineering gaps. Fresh
market signal, action-time facts, and live outcome calibration may remain
market-dependent, but fact mapping, classifier repair, replay coverage, monitor
integration, lifecycle handling, reconciliation shape, and review feedback are
engineering work.

Small-capital execution frictions such as fill probability, slippage, reject,
partial fill, protection acceptance, and PnL calculation should be handled as
coarse-estimate plus lifecycle/recovery branches first. Live trading calibrates
them; it is not the default reason to stop engineering progress.

## Rehearsal-Before-Live Rule

Goal-mode work must close all reasonable pre-live engineering branches before
declaring that live trading is required.

Use this split:

| Branch | Pre-live closure method | Live-only validation |
| --- | --- | --- |
| Submit accepted or rejected | Paper/simulator Operation Layer and local lifecycle tests | Real exchange acceptance or rejection |
| Partial fill | Simulated fill state and protection/reconciliation branch | Actual partial fill behavior |
| Protection accepted or failed | Exchange-rule precheck, simulator branch, hard-stop behavior | Real protection order acceptance |
| Slippage and fees | Coarse spread/fee/funding buffer | Real fill calibration |
| PnL and settlement | Local estimate, reconciliation shape, Review Ledger draft | Real account settlement |

Live-only validation cannot be used as a generic blocker for pre-live closure.
It should appear as the next engineering bottleneck only after the task proves
the rehearsal branch is complete, non-executing, and does not claim live
authority.

A Goal Packet that touches execution lifecycle must state which branches are
closed by dry-run/simulation and which remain live-calibration only.

## Required Authority Model Text

Every Goal Packet that touches StrategyGroup governance, runtime readiness,
Owner-facing state, Decision Ledger, tier review, or execution flow must include
this section:

```text
Global Authority Model:

Owner controls policy, tier, risk scope, capital scope, pause/resume,
promote/downshift/park/kill, and production-stage transition.

System controls normal process execution:
observation -> RequiredFacts mapping -> fresh signal detection -> candidate/auth
-> FinalGate -> Operation Layer -> protection -> reconciliation -> review.

Owner scoped risk acceptance may advance trial eligibility or tier eligibility.
It must not set actionable_now=true and must not bypass execution safety or
authority hard stops.

Do not convert StrategyGroup governance into Owner manual operation.
Do not ask Owner to manually judge RequiredFacts, fresh signal, candidate/auth,
FinalGate, Operation Layer, replay samples, no-action rows, or ordinary
in-boundary execution steps.

If the remaining gap is engineering work, fact mapping, classifier repair,
monitor integration, replay coverage, or runtime readiness, continue engineering.
Escalate to Owner only for policy, tier, capital/profile/scope, pause/resume,
promote/downshift/park/kill, production transition, or abnormal intervention.
```

## Accepted Work Types

| Work type | Accepted when |
| --- | --- |
| `P0 live-path work` | It advances fresh-signal closure, RequiredFacts, candidate/auth, FinalGate, Operation Layer, protection, reconciliation, settlement, or review |
| `P0.5 strategy-learning work` | It changes the StrategyGroup Decision Ledger, replay-to-review bridge, no-action attribution, or monitor sequence |
| `P1 governance work` | It clarifies tier movement, StrategyGroup registry state, Owner policy, or promotion/downshift/park/kill decisions |
| `docs work` | It changes a real decision, source authority, task boundary, or Owner interpretation burden |

Work that only adds reports, broad markdown, standalone scripts, or unconsumed
artifacts is not mainline unless it replaces and reduces an older surface.

Work that only identifies a missing capability without closing it or converting
it into a machine-checkable next bottleneck is `partial`, not `completed`.

## Fresh Signal Interrupt

Every non-P0 Goal Packet must include this rule:

```text
If a real fresh selected StrategyGroup signal appears, pause this task and
return to P0 live-path closure.
```

The interrupted task should leave an Evidence Packet describing the stopping
point and whether the work can resume without state loss.

## Architecture Verdict Vocabulary

Use this vocabulary after reading an Evidence Packet:

| Verdict | Meaning |
| --- | --- |
| `accept` | The checkpoint is complete and can become current baseline |
| `revise` | The result is useful but needs a bounded correction |
| `split` | The task uncovered more than one separable workstream |
| `park` | The result is not worth active continuation now |
| `escalate` | The result changes live authority, Owner policy, or core runtime safety and needs explicit Owner decision |

## Boundary

A Goal Packet cannot authorize:

- FinalGate bypass;
- Operation Layer bypass;
- exchange write outside official runtime path;
- real-order authority from replay, synthetic, or observe-only evidence;
- live-profile mutation;
- sizing-default expansion;
- withdrawal or transfer;
- credential mutation;
- destructive cleanup;
- strategy-parameter changes outside an explicit strategy/research task.
