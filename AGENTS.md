# AGENTS.md - BRC Agent Operating Guide

Last updated: 2026-06-15
Current phase: StrategyGroup runtime-governance pilot

## Current Document Authority

When project documents conflict, follow this order:

1. Owner explicit correction / decision.
2. Current tracked code + current git status.
3. `docs/current/*`.
4. Current verified runtime reports.
5. Historical archive material only when the task explicitly requires recovery.

Start from:

```text
docs/current/OWNER_RUNTIME_OPERATING_MODEL.md
docs/current/AI_AGENT_CONSTRAINTS.md
docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md
docs/current/strategy-group-handoffs/main-control-handoff-index.md
```

Compressed historical docs live in:

```text
docs/history-archive-2026-06-15-pre-governance.tar.gz
```

The archive is recovery material only. It must not reintroduce per-deploy chat
confirmation, per-order chat confirmation inside the official runtime path, or
evidence-packet-as-Owner-interface workflows.

## Product Objective

The Owner goal is:

```text
Owner enables a StrategyGroup.
The system observes, checks, executes inside official boundaries, protects,
reconciles, settles, and records.
The Owner supervises automation status and intervenes only when the product
surface says intervention is needed.
```

The system is not an institutional quant platform, a raw packet browser, or a
manual evidence-interpretation workflow.

The Owner is not an operator. Owner-facing product surfaces must not turn
internal execution gates, evidence objects, API routes, proof chains, or blocker
codes into the main information architecture.

## Standing Authorization

During the development-stage pilot, do not create new chat-confirmation
blockers for:

- focused `codex/*` branches;
- bounded local commits;
- Tokyo deploy apply inside the active stage;
- read-only Tokyo/live fact validation;
- watcher observation after StrategyGroup selection;
- StrategyGroup runtime bootstrap / attach through official API surfaces;
- fresh signal readiness checks;
- non-executing prepare records;
- shadow candidate, runtime grant, or authorization evidence inside boundary;
- official in-boundary real order action after action-time FinalGate and
  Operation Layer pass;
- post-submit finalize, reconciliation, budget settlement, and review capture;
- server historical report archival or compression.

This does not authorize:

- FinalGate bypass;
- Operation Layer bypass;
- withdrawal or transfer actions;
- credential or secret mutation;
- live profile expansion;
- order-sizing default expansion;
- stale-fact execution;
- missing protection;
- duplicate-submit risk;
- conflicting active position or open-order execution;
- destructive data migration or irreversible production cleanup.

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

Gates protect bounded real-funds safety. They must not become opaque all-AND
project blockers.

## StrategyGroup Runtime Path

Current target chain:

```text
StrategyGroup selection
-> runtime admission
-> armed observation
-> fresh strategy signal
-> RequiredFacts readiness
-> non-executing prepare records
-> shadow candidate / runtime grant / authorization evidence
-> action-time FinalGate
-> official Operation Layer gateway action
-> post-submit finalize / reconciliation / budget settlement
-> notification and review
```

## Owner Interface

The normal Owner-facing states are product states:

```text
not_enabled
running
waiting_for_opportunity
processing
temporarily_unavailable
needs_intervention
paused
completed
```

Evidence packets are audit artifacts. Do not ask the Owner to read raw watcher
packets, manually judge signal freshness, manually assemble RequiredFacts, or
hand-approve every in-boundary candidate after a bounded runtime is selected.

Main Owner UI must use terse Owner language:

```text
运行中
等待机会
处理中
暂不可用
需要介入
无需操作
资金正常
订单正常
保护正常
```

The main Owner UI must not expose these as primary labels, menus, cards, or
actions:

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

Those names may appear only in audit/detail/developer surfaces. If the system is
healthy, the UI should say the StrategyGroup is running or waiting and that no
Owner action is required. Only abnormal states should create Owner actions such
as pause, adjust risk, or review recovery.

## Strategy Research Boundary

Strategy research artifacts belong in:

```text
/Users/jiangwei/Documents/final-strategy-research
```

Main control accepts only StrategyGroup handoff packs, runtime admission facts,
RequiredFacts definitions, risk defaults, hard stops, sample packets, and review
outcomes.

## Codex / Claude Workflow

Codex owns requirements analysis, planning, architecture options, core
decisions, core implementation, code review, and merge readiness decisions.

Claude Code owns bounded implementation and tests from Codex-issued task cards.
Claude must not redefine scope, architecture, priorities, runtime profiles, or
strategy parameters.

Claude tasks must include:

```text
Task ID
Goal
Why
Allowed files
Forbidden files
Requirements
Tests
Done When
Hard Stop
```

## Core Files

Only Codex should modify these by default:

```text
src/application/execution_orchestrator.py
src/application/order_lifecycle_service.py
src/application/position_projection_service.py
src/application/capital_protection.py
src/infrastructure/exchange_gateway.py
src/application/reconciliation.py
src/application/startup_reconciliation_service.py
```

Claude can touch a core file only when the task card explicitly allows it.

## Engineering Constraints

- `domain/` must remain pure business logic and must not import I/O frameworks.
- Financial calculations must use `decimal.Decimal`, not `float`.
- Sensitive values must be masked in logs.
- Core parameters should use named Pydantic models instead of unstructured
  dictionaries.
- Execution, recovery, reconciliation, and circuit-breaker state should prefer
  the PG mainline unless explicitly documented as transitional.

## Git Discipline

- `dev` is integration, not a scratch branch.
- `program/live-safe-v1` is the older integration branch name and historical
  baseline.
- Current StrategyGroup runtime-governance pilot work proceeds on focused
  `codex/*` branches.
- Side-task output is not automatically integrated. The main controller must
  review, cherry-pick, replay, or merge the work.
- Do not revert user changes unless explicitly asked.
