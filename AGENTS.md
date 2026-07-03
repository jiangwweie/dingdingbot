# AGENTS.md - BRC Agent Operating Guide

Last updated: 2026-07-02
Current phase: Pre-Trade Runtime V0

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
docs/current/STRATEGY_ENGINEERING_INTAKE_CONTRACT.md
docs/current/TRADEABILITY_DECISION_CONTRACT.md
docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md
docs/current/PRE_TRADE_RUNTIME_CONTRACT.md
docs/current/SERVER_SIDE_RUNTIME_MONITOR_CONTRACT.md
docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md
docs/current/REPO_FILE_SOURCE_ELIMINATION_GOVERNANCE_PLAN.md
docs/current/RUNTIME_CONTROL_STATE_DB_ARCHITECTURE.md
docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md
docs/current/RUNTIME_CONTROL_STATE_MAINLINE_FILE_IO_MAP.md
docs/current/MAIN_CONTROL_DAILY_LIVE_ENABLEMENT_TABLE_CONTRACT.md
docs/current/WIP_AND_STOP_RULE_CONTRACT.md
docs/current/MAIN_CONTROL_ROADMAP.md
docs/current/RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md
docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md
docs/current/GOAL_MODE_TASK_PACKET_CONTRACT.md
docs/current/STRATEGY_OPPORTUNITY_REVIEW_LEDGER.md
docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md
docs/current/strategy-group-handoffs/main-control-handoff-index.md
config/output_control_snapshots.json
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
defines the StrategyGroup asset layer.
`docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md` defines blocker classes and
Live Enablement completion rules.
`docs/current/PRE_TRADE_RUNTIME_CONTRACT.md` defines the current
multi-StrategyGroup, multi-symbol pre-trade runtime: wide observation, bounded
candidate readiness, fresh-signal promotion, single action-time lane narrowing,
and single-intent protected submit.
`docs/current/SERVER_SIDE_RUNTIME_MONITOR_CONTRACT.md` defines the production
monitor ownership boundary: Tokyo server-side readonly timer and Feishu
notification are the target production path; local heartbeat and local monitor
sequence are development diagnostic paths only, not production fallback and not
the source of production Owner notification decisions.
`docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md` defines the Tokyo runtime
deployment boundary: local SSH is the control plane, Tokyo code acquisition uses
approved git fetch/export or explicitly scoped archive upload paths, and deploy
success never grants live-submit or exchange-write authority.
`docs/current/REPO_FILE_SOURCE_ELIMINATION_GOVERNANCE_PLAN.md`,
`docs/current/RUNTIME_CONTROL_STATE_DB_ARCHITECTURE.md`,
`docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md`, and
`docs/current/RUNTIME_CONTROL_STATE_MAINLINE_FILE_IO_MAP.md` define the target
DB-backed current projection boundary: runtime/trading decisions must not
depend on repo MD/JSON, each current projection has one owner projector, and
generated JSON/MD is an export rather than a source of truth.
`docs/current/MAIN_CONTROL_DAILY_LIVE_ENABLEMENT_TABLE_CONTRACT.md` defines the
single daily management table.
`docs/current/WIP_AND_STOP_RULE_CONTRACT.md` defines active lane limits and stop
rules. `docs/current/GOAL_MODE_TASK_PACKET_CONTRACT.md` defines how architecture
direction becomes bounded execution work.

Do not turn generated output, historical archive material, stale roadmap text,
or chat summaries into current authority when current code, machine config,
runtime state, or explicit Owner decisions disagree.

`output/**` is not a single commit bucket. Routine StrategyGroup
live-enablement commits may include only tracked control snapshots listed in
`config/output_control_snapshots.json`, and only when they are the named task
deliverable, have a known source command, and pass their validator. Volatile
runtime facts, watcher refreshes, dry-run audit chains, deploy/session
snapshots, replay labs, and historical evidence directories must not enter
routine commits unless the task explicitly names them as deliverables and the
output-scope validator is updated first. Use
`python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked` before
accepting output changes.

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
`docs/current/TRADEABILITY_DECISION_CONTRACT.md`: every active or newly absorbed
StrategyGroup candidate must answer whether it can trade now. If it cannot, the
system must identify the first blocker, blocker owner, next action, and
post-action state. Blocker naming follows
`docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md`. Do not compress
asset-admission, Owner-policy, fact-mapping, detector, watcher, replay/live
rule, runtime-profile, execution-gate, strategy-quality, or safety blockers into
generic `waiting_for_market`.

Current planning must use this Live Enablement loop:

```text
maintain active StrategyGroup candidate symbol sets
-> compute per-symbol readiness and first blocker
-> promote fresh satisfied candidates without exchange-write authority
-> narrow at most one promoted candidate into an action-time lane input
-> refresh action-time facts
-> candidate / authorization evidence
-> FinalGate
-> Operation Layer
-> protection / reconciliation / settlement / review
```

Current WIP is limited by `docs/current/WIP_AND_STOP_RULE_CONTRACT.md`.
Daily status must collapse into
`docs/current/MAIN_CONTROL_DAILY_LIVE_ENABLEMENT_TABLE_CONTRACT.md`.
Before action-time, the pre-trade management unit is:

```text
StrategyGroup + symbol + readiness state + first blocker + evidence + next action + stop condition
```

The main bottleneck is no longer a general explanation of no-trade periods or a
single fixed daily lane. The main bottleneck is keeping the active
StrategyGroups in a multi-symbol pre-trade candidate pool, proving per-symbol
readiness, and allowing a fresh satisfied symbol to become the single
action-time lane. Reports, markdown, read-only watcher expansion, replay
outputs, and daily status reports are mainline only when they move a candidate
symbol forward or replace a broad blocker with a precise per-symbol / per-fact
blocker and next action.

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
Tradeability Decision answers can-trade; Runtime Safety State answers live-submit safety.
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
armed-observation, or L4 eligibility. It must not grant runtime trade/order
authority, bypass action-time RequiredFacts, bypass FinalGate, bypass Operation
Layer, ignore missing protection, ignore stale facts, or override
account/exchange safety facts.

Do not convert StrategyGroup governance into Owner manual operation. Do not ask
the Owner to manually judge raw no-action rows, replay samples, signal
freshness, RequiredFacts assembly, candidate/auth evidence, FinalGate, Operation
Layer, or ordinary in-boundary execution steps.

If the remaining gap is detector attachment, watcher input, fact mapping,
classifier repair, replay/live rule parity, action-time rehearsal, monitor
integration, runtime readiness, or another non-authority engineering defect,
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

Every blocker must classify itself through
`docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md`.

Current planning, task cards, code review, and generated summaries must map
legacy coarse labels into the contract classes before accepting completion.
`waiting_for_market`, `fresh_signal_absent`, `missing_fact`, and
`live_detector_artifact_missing` are not valid planning conclusions unless the
contract's stricter conditions are true.

Gates protect bounded real-funds safety. They must not become opaque all-AND
project blockers, and they must not let explanation artifacts replace Live
Enablement progress.

Gate checks must be scoped by execution surface:

| Surface | What gates may block | What gates must not block |
| --- | --- | --- |
| `rehearsal` | Unsafe or inconsistent local proof, missing test fixtures, broken lifecycle model | Non-executing dry-run, simulation, or packet generation merely because there is no live signal |
| `shadow` | Candidate/readiness evidence that would mislead tier or Owner state | Read-only observation, replay, classifier repair, RequiredFacts mapping, or monitor integration |
| `live_submit` | Real exchange write, stale facts, missing protection, duplicate submit, wrong scope, FinalGate/Operation Layer bypass | Engineering closure that remains non-executing and does not grant Runtime Safety State submit authority |
| `review` | Review claims unsupported by evidence | Recording negative evidence, rough cost estimates, or simulator outcomes as non-authority review input |

No live-only condition may block pre-live engineering closure. A missing fresh
signal, missing action-time live fact, or absent real exchange outcome blocks
real submit and live outcome calibration only. It does not block detector
attachment, watcher integration, per-symbol / per-fact classification,
simulation, dry-run, paper Operation Layer, post-submit lifecycle rehearsal,
rough cost/PnL calculation, or Review Ledger shape work.

Rehearsal and simulation may unlock the next engineering capability, but they
must never grant runtime trade/order authority, pretend to be live
RequiredFacts, or become Operation Layer submit authority.

Monitor cache freshness is a reporting constraint, not a trading safety gate.
`runtime_progress_cache_stale`, `runtime_progress_cache_missing`,
`runtime_progress_cache_schema_stale`, and
`runtime_progress_cache_runtime_head_stale` must be classified as
`monitor_refresh_needed`. They may emit `NOTIFY` so automation refreshes the
local monitor artifact, but they must not enter `checks.blockers`, must not
become `hard_safety_stop`, and must not make P0 look blocked when the only
remaining real condition is a market fresh signal.

`market_wait_validated` is allowed only after admission, scope, policy,
detector, watcher input, fact computation, blocker classification, and
action-time path readiness are closed for the lane. A detector artifact that
exists and reports computed false facts must be classified as
`computed_not_satisfied`, not as a missing detector.

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
