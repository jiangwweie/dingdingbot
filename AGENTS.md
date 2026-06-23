# AGENTS.md - BRC Agent Operating Guide

Last updated: 2026-06-23
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
docs/current/PROJECT_INFORMATION_ARCHITECTURE.md
docs/current/OWNER_RUNTIME_OPERATING_MODEL.md
docs/current/AI_AGENT_CONSTRAINTS.md
docs/current/STRATEGY_EXPERIMENT_EVALUATION_CONTRACT.md
docs/current/TRADEABILITY_VERDICT_CONTRACT.md
docs/current/MAIN_CONTROL_ROADMAP.md
docs/current/RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md
docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md
docs/current/GOAL_MODE_TASK_PACKET_CONTRACT.md
docs/current/STRATEGY_OPPORTUNITY_REVIEW_LEDGER.md
docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md
docs/current/strategy-group-handoffs/main-control-handoff-index.md
```

Compressed historical docs live in:

```text
docs/history-archive-2026-06-15-pre-governance.tar.gz
```

The archive is recovery material only. It must not reintroduce per-deploy chat
confirmation, per-order chat confirmation inside the official runtime path, or
evidence-packet-as-Owner-interface workflows.

## Global Information Architecture

Current project truth must follow:

```text
Docs explain.
Registry defines strategy assets.
Policy records Owner-authorized control.
Runtime stores current system state.
Generated views summarize.
Archives preserve provenance.
```

`docs/current/PROJECT_INFORMATION_ARCHITECTURE.md` defines source classes and
authority order. `docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md`
defines the StrategyGroup asset layer. `docs/current/GOAL_MODE_TASK_PACKET_CONTRACT.md`
defines how architecture direction becomes bounded execution work.

Do not turn generated output, historical archive material, stale roadmap text,
or chat summaries into current authority when current code, machine config,
runtime state, or explicit Owner decisions disagree.

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

The project is a bounded-aggressive real-profit experiment. The Owner-provided
subaccount allocation is already the upstream risk-control decision and may be
treated as loss-capable experiment capital. Agents must not add hidden
conservatism by lowering leverage, shrinking notional, reducing exposure, or
slowing eligible submits merely because the trade is risky. Hard stops protect
operational authority and mechanical correctness; they are not generic reasons
to avoid in-boundary right-tail opportunities.

Strategy evaluation follows
`docs/current/STRATEGY_EXPERIMENT_EVALUATION_CONTRACT.md`: high-return numbers
such as `100%` are aspiration anchors, not hard intake gates; leverage values
such as `5x` are scenarios, not automatic disqualification or authorization.
Advance strategies by experiment value, known risk envelope, replay/paper
evidence, and main-control absorbability, not by perfect-profit proof.

Strategy tradeability follows
`docs/current/TRADEABILITY_VERDICT_CONTRACT.md`: every active or newly absorbed
StrategyGroup candidate must answer whether it can trade now. If it cannot, the
system must identify the first blocker, blocker owner, next action, and
post-action state. Do not compress asset-admission, Owner-policy, fact-mapping,
execution-gate, strategy-quality, or safety blockers into generic
`waiting_for_market`.

Current planning must use this operating loop:

```text
P0 live path stays ready
-> no-signal periods expand read-only opportunity discovery
-> no-action / would-enter observations enter replay-to-review
-> classifier, facts, freshness, cost, and tier gaps become decisions
-> StrategyGroups are kept, revised, promoted, parked, or killed
-> real allocated-subaccount outcomes later update the review ledger
```

The main bottleneck after the P0 runtime chain is StrategyGroup quality:
opportunity discovery, no-action diagnosis, replay coverage, fact/source
mapping, classifier repair, and tier governance. Reports and markdown are
mainline only when they feed this loop.

`StrategyGroup Decision Ledger` is the minimal pre-live strategy-learning
ledger. For compatibility, its active contract lives at
`docs/current/STRATEGY_OPPORTUNITY_REVIEW_LEDGER.md`, but it must not become a
large opportunity log. It records only high-priority observations that change a
StrategyGroup decision: keep observing, revise, promote, park, kill, go live,
do not go live, or block for safety. It complements the post-action Review
Ledger; it does not replace FinalGate, Operation Layer, live RequiredFacts, or
real lifecycle review.

Promotion language must be scoped. A research-side short candidate such as
`BRF2-001` may be promoted for `intake_only` or `trial_admission` without being
promoted to live readiness. Generic `promote` wording is invalid when it hides
whether the scope is intake, armed observation, tiny-live readiness, or L4
eligibility.

The Owner is not an operator. Owner-facing product surfaces must not turn
internal execution gates, evidence objects, API routes, proof chains, or blocker
codes into the main information architecture.

## Global Authority Model

Use this authority split across planning, implementation, review, and Owner
surfaces:

```text
Owner controls policy.
System executes process.
Runtime decides actionability.
Review updates strategy governance.
```

The Owner controls StrategyGroup policy: enable, pause, resume, promote,
downshift, park, kill, scoped risk acceptance, capital scope, runtime profile,
symbol/side scope, and production-stage transitions.

The system controls normal process execution after a bounded StrategyGroup and
runtime profile are selected:

```text
observation
-> RequiredFacts mapping
-> fresh signal detection
-> candidate / authorization evidence
-> action-time FinalGate
-> official Operation Layer
-> protection
-> reconciliation
-> settlement
-> review capture
```

Owner scoped risk acceptance may advance `trial_eligible`, observation, shadow,
armed-observation, or L4 eligibility. It must not set `actionable_now=true`,
bypass action-time RequiredFacts, bypass FinalGate, bypass Operation Layer,
ignore missing protection, ignore stale facts, or override account/exchange
safety facts.

Do not convert StrategyGroup governance into Owner manual operation. Do not ask
the Owner to manually judge raw no-action rows, replay samples, signal
freshness, RequiredFacts assembly, candidate/auth evidence, FinalGate, Operation
Layer, or ordinary in-boundary execution steps.

If the remaining gap is fact mapping, classifier repair, replay coverage,
monitor integration, runtime readiness, or a non-authority engineering defect,
continue engineering progress. Escalate to the Owner only for policy, tier,
capital/profile/scope, pause/resume, promote/downshift/park/kill, production
transition, or abnormal intervention.

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
| `asset_admission` | StrategyGroup is not yet a final-owned admitted trial/runtime asset |
| `owner_policy_required` | Owner capital, profile, risk, scope, promotion, pause, park, or kill decision is required |
| `missing_fact` | Required fact or evidence is absent or stale |
| `deployment_issue` | Tokyo or local deployment is behind current code |
| `monitor_refresh_needed` | Local monitor cache is missing, stale, schema-stale, or tied to an old runtime head |
| `active_position_resolution` | Position, open order, or protection state needs resolution |
| `hard_safety_stop` | Execution would violate the safety boundary |
| `review_only_warning` | Strategy evidence is weak but not a live-safety blocker |

Gates protect bounded real-funds safety. They must not become opaque all-AND
project blockers.

Gate checks must be scoped by execution surface:

| Surface | What gates may block | What gates must not block |
| --- | --- | --- |
| `rehearsal` | Unsafe or inconsistent local proof, missing test fixtures, broken lifecycle model | Non-executing dry-run, simulation, or packet generation merely because there is no live signal |
| `shadow` | Candidate/readiness evidence that would mislead tier or Owner state | Read-only observation, replay, classifier repair, RequiredFacts mapping, or monitor integration |
| `live_submit` | Real exchange write, stale facts, missing protection, duplicate submit, wrong scope, FinalGate/Operation Layer bypass | Engineering closure that remains non-executing and keeps `actionable_now=false` |
| `review` | Review claims unsupported by evidence | Recording negative evidence, rough cost estimates, or simulator outcomes as non-authority review input |

No live-only condition may block pre-live engineering closure. A missing fresh
signal, missing action-time live fact, or absent real exchange outcome blocks
real submit and live outcome calibration only. It does not block simulation,
dry-run, paper Operation Layer, post-submit lifecycle rehearsal, rough cost/PnL
calculation, or Review Ledger shape work.

Rehearsal and simulation may unlock the next engineering capability, but they
must never set `actionable_now=true`, pretend to be live RequiredFacts, or become
Operation Layer submit authority.

Monitor cache freshness is a reporting constraint, not a trading safety gate.
`runtime_progress_cache_stale`, `runtime_progress_cache_missing`,
`runtime_progress_cache_schema_stale`, and
`runtime_progress_cache_runtime_head_stale` must be classified as
`monitor_refresh_needed`. They may emit `NOTIFY` so automation refreshes the
local monitor artifact, but they must not enter `checks.blockers`, must not
become `hard_safety_stop`, and must not make P0 look blocked when the only
remaining real condition is a market fresh signal.

## StrategyGroup Runtime Path

Current target chain:

```text
StrategyGroup selection
-> trial asset admission when needed
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
Global Authority Model
Capability Unlocked
Next Engineering Bottleneck
Rehearsal/Simulation Boundary
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
