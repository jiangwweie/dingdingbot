---
title: PROJECT_INFORMATION_ARCHITECTURE
status: CURRENT
authority: docs/current/PROJECT_INFORMATION_ARCHITECTURE.md
last_verified: 2026-07-01
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
| `strategy_registry` | StrategyGroup identity, edge thesis, trade logic, risk gaps, promotion gates, downshift and kill rules | `docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md` plus reviewed handoff packs | Defines strategy assets; not execution authority |
| `machine_config` | Structured policy or config consumed by scripts | `docs/current/**/*.json` where scripts read it | Must be schema-like, testable, and stable |
| `owner_policy` | Owner risk acceptance, tier switches, capital scope, pauses, parks, kills | Future runtime/policy store; during pilot only explicit Owner decisions and bounded docs | Dynamic authorization state; should not live as narrative Markdown long-term |
| `runtime_state` | Watcher state, live facts, candidate/auth state, orders, positions, protection, reconciliation | Runtime DB, Tokyo reports, generated watcher artifacts | Current operational truth, subject to freshness rules |
| `current_projection` | Single-owner current state over facts/events, such as Candidate Pool readiness, Goal Status, Runtime Safety State, and server monitor state | Target DB-backed current projection; transitional file-backed repository only | Runtime decision source after repository migration; exactly one owner projector |
| `generated_view` | Strategy Asset State evidence, Review Ledger, monitor summaries, Owner summaries | `output/**`, runtime report directories | Generated from sources; do not hand-edit as authority |
| `tracked_control_snapshot` | Small generated views that are allowed into routine Live Enablement commits | Paths listed in `config/output_control_snapshots.json` | Commit only with known source command, validator, and named task deliverable |
| `volatile_output_artifact` | Watcher ticks, public facts refreshes, dry-run chains, deploy snapshots, replay labs, and local runtime noise | `output/**` paths not listed as tracked control snapshots | Must remain untracked and ignored; regenerate or archive separately |
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

| Concern | Source |
| --- | --- |
| Product objective and Owner role | `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md` |
| Strategy experiment evaluation semantics | `docs/current/STRATEGY_EXPERIMENT_EVALUATION_CONTRACT.md` |
| Strategy engineering intake filter | `docs/current/STRATEGY_ENGINEERING_INTAKE_CONTRACT.md` |
| Tradeability Decision semantics | `docs/current/TRADEABILITY_DECISION_CONTRACT.md` |
| Blocker classification and Live Enablement completion rules | `docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md` |
| Daily Live Enablement management table | `docs/current/MAIN_CONTROL_DAILY_LIVE_ENABLEMENT_TABLE_CONTRACT.md` |
| Pre-Trade Runtime and Candidate Pool | `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md` |
| L1-L9 full-chain audit and optimization review | `docs/current/L1_L9_SYSTEM_REVIEW_AND_OPTIMIZATION_AUDIT.md` |
| Runtime terminology and Owner explanation governance | `docs/current/RUNTIME_TERMINOLOGY_OWNER_EXPLANATION_GOVERNANCE.md` |
| Owner Explanation Read Model contract | `docs/current/OWNER_EXPLANATION_READ_MODEL_CONTRACT.md` |
| Active StrategyGroup semantics review and optimization plan | `docs/current/ACTIVE_STRATEGYGROUP_SEMANTICS_REVIEW_AND_OPTIMIZATION_PLAN.md` |
| Multi-StrategyGroup multi-symbol multi-side action-time evolution | `docs/current/MULTI_STRATEGY_MULTI_SYMBOL_MULTI_SIDE_ACTION_TIME_EVOLUTION_DESIGN.md` |
| L1-L9 optimization execution plan | `docs/current/L1_L9_OPTIMIZATION_EXECUTION_PLAN.md` |
| Production runtime monitor ownership | `docs/current/SERVER_SIDE_RUNTIME_MONITOR_CONTRACT.md` |
| Tokyo runtime deployment boundary | `docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md` |
| Repo file source elimination governance | `docs/current/REPO_FILE_SOURCE_ELIMINATION_GOVERNANCE_PLAN.md` |
| Runtime control state DB architecture | `docs/current/RUNTIME_CONTROL_STATE_DB_ARCHITECTURE.md` |
| Runtime control state DB table design | `docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md` |
| Runtime control state mainline file I/O map | `docs/current/RUNTIME_CONTROL_STATE_MAINLINE_FILE_IO_MAP.md` |
| PG current projection authority closure | `docs/current/PG_CURRENT_PROJECTION_AUTHORITY_CLOSURE_DESIGN.md` |
| Strategy governance pipeline DB design | `docs/current/STRATEGY_GOVERNANCE_PIPELINE_DB_DESIGN.md` |
| WIP limit and stop rules | `docs/current/WIP_AND_STOP_RULE_CONTRACT.md` |
| Stage roadmap and current track plan | `docs/current/MAIN_CONTROL_ROADMAP.md` |
| Order-capable experiment profile | `docs/current/RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md` |
| Agent boundaries and goal-mode execution | `docs/current/AI_AGENT_CONSTRAINTS.md` |
| Owner-facing control board semantics | `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md` |
| Strategy asset registry contract | `docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md` |
| Strategy asset registry baseline | `docs/current/strategy-group-handoffs/strategygroup-registry-baseline.json` and `docs/current/strategy-group-handoffs/strategygroup-registry-baseline.md` |
| Current StrategyGroup tier review | `docs/current/strategy-group-handoffs/strategygroup-tier-review-current.json` and `docs/current/strategy-group-handoffs/strategygroup-tier-review-current.md` |
| Current StrategyGroup quality wave | `docs/current/strategy-group-handoffs/strategygroup-quality-wave-current.json` and `docs/current/strategy-group-handoffs/strategygroup-quality-wave-current.md` |
| Goal-mode task handoff contract | `docs/current/GOAL_MODE_TASK_PACKET_CONTRACT.md` |
| Runtime tier definitions | `docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.md` |
| Machine tier mapping | `docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json` |
| Output control snapshot whitelist | `config/output_control_snapshots.json` |
| RequiredFacts classes | `docs/current/strategy-group-handoffs/main-control-required-facts-map.md` |
| Strategy Asset State pre-live evidence compatibility path | `docs/current/STRATEGY_OPPORTUNITY_REVIEW_LEDGER.md` |
| Tradeability Decision generated view | `output/runtime-monitor/latest-strategygroup-tradeability-decision.json` and `output/runtime-monitor/latest-strategygroup-tradeability-decision.md` |
| Current goal audit | `docs/current/STRATEGYGROUP_RUNTIME_PILOT_GOAL_AUDIT.md` |
| Monitor baseline config | `docs/current/RUNTIME_MONITOR_BASELINE.json` |

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

During the pilot, `docs/current/**/*.json` can act as structured source input.
Long-term dynamic state should move to runtime or policy stores.

## Generated View Rules

Generated views include:

- `output/runtime-monitor/*.json`;
- `output/runtime-monitor/*.md`;
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
| `tracked_control_snapshot` | May be committed only when listed in `config/output_control_snapshots.json`, produced by the named source command, and accepted by its validator | Daily Live Enablement Table, Tradeability Decision, Replay/Live Parity Audit, Action-Time Boundary, Local Monitor Sequence, Single Lane Task Packet |
| `volatile_output_artifact` | Must not be committed by default; keep local, regenerate, or archive outside routine Live Enablement commits | public facts ticks, strategy runtime-signal facts, dry-run audit chains, deploy/session snapshots, replay labs |
| `historical_evidence_output` | Commit only when the task explicitly requires provenance capture and the artifact has a bounded retention reason | dated audits, one-off migration/deploy evidence, historical strategy-capture reports |

Git tracking under `output/**` is closed by default. `.gitignore` ignores the
whole output tree and re-admits only the exact control snapshot paths listed in
`config/output_control_snapshots.json`. Historical output files that are not
listed in the manifest are local compatibility evidence only and must be
removed from the git index with `git rm --cached`, not hand-promoted through a
routine commit.

Before accepting output changes, run:

```text
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
```

The validator checks the current output change set against
`config/output_control_snapshots.json`. Existing tracked output files remain
compatibility evidence, but their historical presence does not make them valid
routine commit candidates.

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

The repo file-source elimination plan is defined in
`docs/current/REPO_FILE_SOURCE_ELIMINATION_GOVERNANCE_PLAN.md`.

The target table design is defined in
`docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md`.

The strategy governance pipeline DB design is defined in
`docs/current/STRATEGY_GOVERNANCE_PIPELINE_DB_DESIGN.md`. It is a P1 design
for converting strategy research, handoff packs, and admission artifacts into
DB-backed strategy candidate and governance state after the P0 repository and
runtime-control DB source boundary is in place.

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
