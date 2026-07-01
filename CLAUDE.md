# CLAUDE.md - BRC Claude Worker Guide

Last updated: 2026-07-01
Current phase: StrategyGroup live-enablement pilot

## Role

Claude Code is a bounded implementation worker in this repository.

Codex owns requirements analysis, planning, architecture, core decisions, core
implementation, review, and merge readiness decisions.

Claude owns scoped implementation and tests from Codex-issued task cards.

## Required Context

Before starting work, read:

```text
AGENTS.md
docs/current/PROJECT_INFORMATION_ARCHITECTURE.md
docs/current/OWNER_RUNTIME_OPERATING_MODEL.md
docs/current/AI_AGENT_CONSTRAINTS.md
docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md
docs/current/MAIN_CONTROL_DAILY_LIVE_ENABLEMENT_TABLE_CONTRACT.md
docs/current/WIP_AND_STOP_RULE_CONTRACT.md
docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md
docs/current/GOAL_MODE_TASK_PACKET_CONTRACT.md
docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md
```

Then read only the task-specific files listed in the Codex task card.

Do not use compressed historical docs as active instructions unless the task
explicitly asks for recovery or provenance.

## Source Discipline

Claude must treat docs, registry rows, machine config, runtime state, generated
views, and archive material according to
`docs/current/PROJECT_INFORMATION_ARCHITECTURE.md`.

If a task reads generated output, treat it as checkpoint evidence, not a
hand-edited source of truth. If a task changes StrategyGroup semantics, tie the
change back to the StrategyGroup registry contract, handoff pack, runtime tier
policy, Decision Ledger, or an explicit Codex-issued task card.

## Current Product Direction

The current target is a StrategyGroup live-enablement pilot:

```text
select StrategyGroup + symbol lane
-> classify the earliest blocker precisely
-> remove detector / watcher / facts / scope / policy / runtime-profile blockers
-> reach market_wait_validated only after non-market blockers are closed
-> on fresh signal refresh action-time facts
-> candidate / authorization evidence
-> action-time FinalGate
-> official Operation Layer
-> post-submit finalize / reconciliation / budget settlement
-> review
```

Do not turn the Owner Console into a passive dashboard or a packet browser. It
is the Owner operating surface for state, blockers, candidate readiness,
FinalGate state, active position/protection, pause/revoke controls, and review
outcomes.

The project posture is bounded-aggressive. The Owner-provided subaccount
allocation is already the risk-control result and may be treated as
loss-capable experiment capital. Claude tasks must not reinterpret that budget
into lower leverage, lower exposure, smaller notional, or slower eligible
submits for caution. Stop only for explicit authority or mechanical boundaries
listed below.

Current mainline work is Live Enablement. Claude tasks must remove or precisely
reclassify the earliest blocker on a selected StrategyGroup + symbol lane.
Replay, synthetic fixtures, observe-only evidence, no-action rows, and read-only
watcher expansion are valid only when they produce per-symbol / per-fact blocker
evidence or a scoped live-enable proposal. They must not become live signals,
live RequiredFacts, FinalGate input, Operation Layer evidence, or real-order
authority.

## Authority Model For Worker Tasks

Claude must preserve this global split:

```text
Owner controls policy.
System executes process.
Runtime decides actionability.
Review updates strategy governance.
```

The Owner controls StrategyGroup enable/pause/resume, promote/downshift,
park/kill, scoped risk acceptance, capital/profile/scope changes, and
production-stage transition.

Claude task execution should keep engineering progress moving when the remaining
gap is detector attachment, watcher tick/input, fact mapping, classifier repair,
replay/live rule parity, action-time rehearsal, monitor integration, runtime
readiness, or another non-authority implementation defect.

Do not reinterpret those engineering gaps as a request for the Owner to manually
judge RequiredFacts, fresh signal validity, candidate/auth evidence, FinalGate,
Operation Layer, replay samples, no-action rows, or ordinary in-boundary
execution steps.

Owner scoped risk acceptance may advance `trial_eligible` or tier eligibility.
It must not set `actionable_now=true`, bypass FinalGate, bypass Operation Layer,
or override stale-fact, missing-protection, duplicate-submit, account, exchange,
or authority hard stops.

## Standing Authorization

During the development-stage pilot, do not block task progress on fresh chat
confirmation for bounded deploy apply, watcher operation, live read-only fact
checks, non-executing prepare records, or official in-boundary runtime actions
after FinalGate and Operation Layer pass.

Stop for boundary changes:

```text
FinalGate bypass
Operation Layer bypass
withdrawal or transfer
secret / credential / live profile mutation
order-sizing default expansion
unauthorized live profile, sizing default, selected StrategyGroup, symbol, side,
leverage, notional, or exposure expansion beyond the Owner-selected profile
stale account facts
missing protection
missing budget
duplicate-submit risk
conflicting active position or open order
destructive migration or irreversible production cleanup
```

## Task Card Requirement

Claude may implement only when the prompt includes:

```text
Task ID
Goal
Why
Allowed files
Forbidden files
Requirements
Global Authority Model
Chain Position
Live Enablement State Before
Live Enablement State After
Blocker Removed Or Reclassified
Per-Symbol / Per-Fact Acceptance
Stop Condition
Capability Unlocked
Next Engineering Bottleneck
Rehearsal/Simulation Boundary
Tests
Done When
Hard Stop
```

If a required change falls outside `Allowed files`, stop and report the blocker.

## Core File Rule

The following files are Codex-owned by default:

```text
src/application/execution_orchestrator.py
src/application/order_lifecycle_service.py
src/application/position_projection_service.py
src/application/capital_protection.py
src/infrastructure/exchange_gateway.py
src/application/reconciliation.py
src/application/startup_reconciliation_service.py
```

Do not edit these unless the task card explicitly allows it.

## Prohibitions

- Do not optimize strategy returns.
- Do not tune strategy parameters unless the task is explicitly a research task.
- Do not add multi-asset expansion outside the selected StrategyGroup boundary.
- Do not edit live trading profiles, credentials, or order-sizing defaults.
- Do not hard-code fixed return or drawdown targets into implementation, tests,
  runtime rules, or task interpretation.
- Do not create withdrawal or transfer actions.
