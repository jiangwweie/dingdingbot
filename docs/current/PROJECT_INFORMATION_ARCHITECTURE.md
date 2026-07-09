---
title: PROJECT_INFORMATION_ARCHITECTURE
status: CURRENT
authority: docs/current/PROJECT_INFORMATION_ARCHITECTURE.md
last_verified: 2026-07-09
---

# Project Information Architecture

## Purpose

This file defines the global information-source contract for the StrategyGroup
live-enablement pilot.

It exists to prevent current project truth from being spread across narrative
documents, generated reports, local output files, and chat memory. It does not
authorize live trading, change runtime profiles, change strategy parameters, or
replace the official runtime chain.

## Core Rule

Use this split:

```text
Docs explain.
Registry defines strategy assets.
Policy records Owner-authorized control.
Runtime stores current system state.
Generated views summarize.
Archives preserve provenance.
```

Markdown may explain current intent and boundaries, but it must not become a
manual substitute for dynamic runtime state.

Dynamic current state must also obey this stricter rule:

```text
facts/events/diagnostics
-> one owner projector
-> current projection
-> generated JSON/MD export
```

Generated JSON/MD exports may summarize current projections, but they must not
become independent runtime truth or compete with another writer for the same
current state.

## Authority Model

This information architecture exists to support this authority split:

```text
Owner controls policy.
System executes process.
Tradeability Decision answers can-trade; Runtime Safety State answers live-submit safety.
Review updates strategy governance.
```

Owner policy belongs in explicit scoped decisions, policy events, or reviewed
governance documents. System process belongs in runtime code, machine config,
generated runtime state, and test-covered automation. Generated views summarize
the current state; they must not turn the Owner into the manual interpreter of
RequiredFacts, replay rows, no-action rows, FinalGate evidence, Operation Layer
evidence, or ordinary in-boundary execution steps.

`trial_eligible` is a strategy-governance and policy outcome.
`tradeability_decision` is a generated read model that explains whether a
StrategyGroup can trade now and, if not, names the first blocker.
`runtime_safety_state` is the generated read model that explains whether the
official live-submit path is currently safe enough to proceed. Other generated
views may summarize those models, but they must not recompute can-trade or
live-submit authority from documents or generated artifact metadata.
`blocker_classification` is the current blocker-language contract. Generated
views may report blocker classes, but planning and acceptance must interpret
them through `docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md`.

Tokyo runtime deployment follows `docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md`.
Deployment evidence is operational checkpoint evidence, not trading authority.
Deploy success must not be interpreted as live-submit readiness, FinalGate input,
Operation Layer evidence, or exchange-write permission.

## Information Classes

| Class | Purpose | Current location | Authority behavior |
| --- | --- | --- | --- |
| `governance_doc` | Product objective, Owner role, safety boundaries, AI constraints, architecture rules | `docs/current/*.md` | Human-readable authority for intent and constraints |
| `strategy_registry` | StrategyGroup identity, edge thesis, trade logic, risk gaps, promotion gates, downshift and kill rules | PG strategy registry/version/event/fact rows plus `docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md` | Defines strategy assets; not execution authority |
| `machine_config` | Structured policy or config represented by code schema or PG seed/import rows | PG current tables, migrations, typed code schemas | Repo JSON must not be runtime authority; reusable semantics must be seeded into PG or archived |
| `owner_policy` | Owner risk acceptance, tier switches, capital scope, pauses, parks, kills | Future runtime/policy store; during pilot only explicit Owner decisions and bounded docs | Dynamic authorization state; should not live as narrative Markdown long-term |
| `runtime_state` | Watcher state, live facts, candidate/auth state, orders, positions, protection, reconciliation | Runtime DB / PG current services | Current operational truth, subject to freshness rules |
| `current_projection` | Single-owner current state over facts/events, such as Candidate Pool readiness, Goal Status, Runtime Safety State, and server monitor state | Target DB-backed current projection; transitional file-backed repository only | Runtime decision source after repository migration; exactly one owner projector |
| `generated_view` | Strategy Asset State evidence, Review Ledger, monitor summaries, Owner summaries | `output/**`, runtime report directories | Generated from sources; do not hand-edit as authority |
| `generated_output_artifact` | Watcher ticks, public facts refreshes, dry-run chains, deploy snapshots, replay labs, local runtime noise, and generated control views | `output/**` | Must remain untracked and ignored; regenerate from PG/current services or archive separately |
| `archive` | Historical plans and obsolete evidence | `docs/history-archive-2026-06-15-pre-governance.tar.gz`, historical output | Recovery/provenance only |

## Authority Order

When artifacts conflict, use this order:

1. Explicit Owner correction or decision.
2. Current tracked code and runtime safety gates.
3. Runtime state with verified freshness.
4. Machine-readable current config.
5. Current governance docs.
6. Generated views, only as summaries of their source inputs.
7. Archives and old reports, only for recovery or provenance.

Generated output must not override current code, machine config, or explicit
Owner decisions.

## Current Source Map

`docs/current` contains only current authority contracts and active design
surfaces. Stage audits, old implementation packets, and absorbed review
material belong in `docs/archive/**` and must not be treated as current
authority.

| Concern | Current source |
| --- | --- |
| Product objective and Owner role | `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md` |
| Agent constraints and execution boundaries | `docs/current/AI_AGENT_CONSTRAINTS.md` |
| Stage roadmap and next execution order | `docs/current/MAIN_CONTROL_ROADMAP.md`, `docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md` |
| Strategy experiment evaluation semantics | `docs/current/STRATEGY_EXPERIMENT_EVALUATION_CONTRACT.md` |
| Strategy engineering intake filter | `docs/current/STRATEGY_ENGINEERING_INTAKE_CONTRACT.md` |
| Tradeability Decision semantics | `docs/current/TRADEABILITY_DECISION_CONTRACT.md` |
| Blocker classification and Live Enablement completion rules | `docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md` |
| Daily Live Enablement management table | `docs/current/MAIN_CONTROL_DAILY_LIVE_ENABLEMENT_TABLE_CONTRACT.md` |
| Pre-Trade Runtime and Candidate Pool | `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md` |
| Runtime terminology and Owner explanation governance | `docs/current/RUNTIME_TERMINOLOGY_OWNER_EXPLANATION_GOVERNANCE.md`, `docs/current/OWNER_EXPLANATION_READ_MODEL_CONTRACT.md` |
| Production runtime monitor ownership | `docs/current/SERVER_SIDE_RUNTIME_MONITOR_CONTRACT.md` |
| Tokyo runtime deployment boundary | `docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md` |
| Production runtime file I/O elimination | `docs/current/PRODUCTION_RUNTIME_FILE_IO_ELIMINATION_DESIGN.md` |
| Runtime control state DB architecture and tables | `docs/current/RUNTIME_CONTROL_STATE_DB_ARCHITECTURE.md`, `docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md` |
| Ticket-bound lifecycle and protection | `docs/current/TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md`, `docs/current/TICKET_BOUND_LIFECYCLE_SAFETY_CORE_IMPLEMENTATION_PLAN.md` |
| Post-submit reconciliation and recovery commands | `docs/current/POST_SUBMIT_RECONCILIATION_AND_RECOVERY_COMMAND_DESIGN.md` |
| Live outcome ledger contract | `docs/current/LIVE_OUTCOME_LEDGER_CONTRACT.md` |
| Trading quality capital/risk allocation | `docs/current/TRADING_QUALITY_CAPITAL_RISK_ALLOCATION_DESIGN.md` |
| Strategy governance pipeline DB design | `docs/current/STRATEGY_GOVERNANCE_PIPELINE_DB_DESIGN.md` |
| WIP limit and stop rules | `docs/current/WIP_AND_STOP_RULE_CONTRACT.md` |
| Owner-facing control board semantics | `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md` |
| Goal-mode task handoff contract | `docs/current/GOAL_MODE_TASK_PACKET_CONTRACT.md` |
| Strategy asset registry contract | `docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md` |
| Strategy asset registry current state | PG strategy registry / strategy version / RequiredFacts projections |
| StrategyGroup tier and quality current state | PG Owner policy, strategy review, and tradeability projections |
| Retired StrategyGroup file snapshots | `docs/archive/strategy-group-handoffs-retired-file-sources/` for provenance only |
| Runtime tier definitions | PG Owner policy / runtime profile projections plus explanatory Markdown |
| Machine tier mapping | PG Owner policy / runtime profile projections |
| RequiredFacts classes | PG RequiredFacts/version rows and typed code schema |
| Strategy Asset State pre-live evidence compatibility path | `docs/current/STRATEGY_OPPORTUNITY_REVIEW_LEDGER.md` |

## Markdown Rules

Markdown documents may:

- explain intent, ownership, safety boundaries, and acceptance rules;
- link to structured config and generated outputs;
- record durable architecture decisions;
- provide human-readable context for agents and the Owner.

Markdown documents must not:

- manually restate generated current state when a generated JSON is the source;
- act as a live runtime database;
- carry hidden Owner risk acceptance that is not explicit and scoped;
- convert Owner policy control into manual operation of runtime gates;
- imply real-order authority;
- override FinalGate, Operation Layer, RequiredFacts, protection, reconciliation,
  or budget-settlement gates.

If a Markdown roadmap cites current StrategyGroup decisions, it must identify
the generated source or use stable stage language instead of copying volatile
rows.

## Machine-Readable Config Rules

Machine-readable config under `docs/current` is allowed during the pilot when
it is stable, reviewed, and test-covered.

It must:

- be JSON or another structured format;
- have clear status, scope, and non-authority fields when relevant;
- be consumed by known scripts or tests;
- avoid embedding generated runtime state;
- keep real-order authority explicit and false unless the official runtime
  chain grants action-time authority.

Repo JSON must not act as structured runtime source input. Reusable semantics
belong in typed code schemas or PG seed/import rows; historical material belongs
in archive-only provenance.

## Generated View Rules

Generated views include:

- explicit diagnostic JSON exports;
- explicit diagnostic Markdown exports;
- deploy-session summaries;
- local monitor sequence artifacts;
- replay and audit reports generated by scripts.

They must be treated as:

```text
source inputs -> generated view -> checkpoint evidence
```

They must not become:

```text
generated view -> hand-edited source of truth
```

After the DB/repository migration, generated views must also not become:

```text
generated view A -> generated view B -> runtime decision
```

The allowed path is:

```text
DB/API/code facts
-> RuntimeControlStateRepository
-> current projection
-> generated view export
```

If a legacy artifact is still read for compatibility, it may produce
diagnostics only. It must not set the main current blocker when a fresher
current projection exists.

If a generated view and a roadmap disagree, regenerate or update the roadmap to
reference the generated source. Do not let the stale roadmap redefine current
state.

Routine commits must apply this stricter split:

| Output class | Commit rule | Examples |
| --- | --- | --- |
| `generated_output_artifact` | Must not be committed by default; keep local, regenerate from PG/current services, or archive outside routine Live Enablement commits | Daily Live Enablement Table exports, Candidate Pool exports, public facts ticks, strategy runtime-signal facts, dry-run audit chains, deploy/session snapshots, replay labs |
| `historical_evidence_output` | Commit only when the task explicitly requires provenance capture and the artifact has a bounded retention reason | dated audits, one-off migration/deploy evidence, historical strategy-capture reports |

Git tracking under `output/**` is closed by default. `.gitignore` ignores the
whole output tree. Historical output files are local compatibility evidence only
and must be removed from the git index, not hand-promoted through a routine
commit.

Before accepting output changes, run:

```text
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
```

The validator rejects routine output changes and tracked generated output.
Existing tracked output files are cleanup targets, not valid routine commit
candidates.

The Tradeability Decision generated view has one narrow role: it summarizes
registry, policy, runtime, research-intake, and ledger inputs into a current
answer for each candidate:

```text
can trade now
or
cannot trade because of first blocker X
```

It must not become an authority source for strategy semantics, Owner policy,
action-time facts, FinalGate, Operation Layer, or exchange writes. If the
Tradeability Decision reports `asset_admission`, the next source is the registry
or admission proposal. If it reports `policy`, the next source is an explicit
Owner decision. If it reports `execution_gate`, the next source is runtime state.

## Owner Policy Direction

The long-term system should record Owner policy as explicit, scoped events:

| Policy event | Meaning |
| --- | --- |
| `allow_l2_shadow` | Owner allows non-executing shadow candidate review |
| `allow_l3_armed_observation` | Owner allows armed observation without real-order authority |
| `allow_l4_live_trial` | Owner allows small-capital real-order eligibility inside official boundaries |
| `force_downshift` | Owner or system moves a StrategyGroup to a lower tier |
| `park_strategygroup` | Owner or system pauses strategy asset allocation |
| `kill_strategygroup` | Owner or system marks the StrategyGroup as no longer worth active work |

During the current pilot, these policy events may be represented by explicit
Owner decisions plus current docs. They should not be hidden in routine
Markdown summaries.

## DB-Backed Runtime Control State Direction

Dynamic StrategyGroup runtime-control state should migrate behind the
`RuntimeControlStateRepository` boundary defined in
`docs/current/RUNTIME_CONTROL_STATE_DB_ARCHITECTURE.md`.

The production repo/output/report file-authority elimination design is defined
in `docs/current/PRODUCTION_RUNTIME_FILE_IO_ELIMINATION_DESIGN.md`.

The target table design is defined in
`docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md`.

The strategy governance pipeline DB design is defined in
`docs/current/STRATEGY_GOVERNANCE_PIPELINE_DB_DESIGN.md`. It is a P1 design
for converting strategy research, archive-only handoff provenance, and
admission artifacts into DB-backed strategy candidate and governance state
after the P0 repository and runtime-control DB source boundary is in place.

This direction does not move governance Markdown, replay fixtures, deploy
configuration, or historical archives into DB. It moves dynamic registry
consumption, Owner policy, candidate universe, runtime scope, watcher coverage,
fact snapshots, pre-trade readiness, promotion candidates, action-time lane
inputs, runtime safety state, and server monitor notification state away from
raw JSON/file reads and into DB-backed control state. Generated JSON/MD files
remain exports and checkpoint evidence only.

## Architecture Boundary

This information architecture does not authorize:

- real-order submission;
- FinalGate bypass;
- Operation Layer bypass;
- stale-fact execution;
- missing protection;
- duplicate submit;
- conflicting active exposure;
- live-profile mutation;
- sizing-default expansion;
- withdrawal or transfer;
- credential mutation.

It only defines how project information is organized and how future agents
should choose sources.
