---
title: PROJECT_INFORMATION_ARCHITECTURE
status: CURRENT
authority: docs/current/PROJECT_INFORMATION_ARCHITECTURE.md
last_verified: 2026-06-23
---

# Project Information Architecture

## Purpose

This file defines the global information-source contract for the StrategyGroup
runtime-governance pilot.

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

## Information Classes

| Class | Purpose | Current location | Authority behavior |
| --- | --- | --- | --- |
| `governance_doc` | Product objective, Owner role, safety boundaries, AI constraints, architecture rules | `docs/current/*.md` | Human-readable authority for intent and constraints |
| `strategy_registry` | StrategyGroup identity, edge thesis, trade logic, risk gaps, promotion gates, downshift and kill rules | `docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md` plus reviewed handoff packs | Defines strategy assets; not execution authority |
| `machine_config` | Structured policy or config consumed by scripts | `docs/current/**/*.json` where scripts read it | Must be schema-like, testable, and stable |
| `owner_policy` | Owner risk acceptance, tier switches, capital scope, pauses, parks, kills | Future runtime/policy store; during pilot only explicit Owner decisions and bounded docs | Dynamic authorization state; should not live as narrative Markdown long-term |
| `runtime_state` | Watcher state, live facts, candidate/auth state, orders, positions, protection, reconciliation | Runtime DB, Tokyo reports, generated watcher artifacts | Current operational truth, subject to freshness rules |
| `generated_view` | Strategy Asset State evidence, Review Ledger, monitor summaries, Owner summaries | `output/**`, runtime report directories | Generated from sources; do not hand-edit as authority |
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
| Tradeability Decision semantics | `docs/current/TRADEABILITY_DECISION_CONTRACT.md` |
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

If a generated view and a roadmap disagree, regenerate or update the roadmap to
reference the generated source. Do not let the stale roadmap redefine current
state.

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
| `force_downshift` | Owner or system downgrades a StrategyGroup tier |
| `park_strategygroup` | Owner or system pauses strategy asset allocation |
| `kill_strategygroup` | Owner or system marks the StrategyGroup as no longer worth active work |

During the current pilot, these policy events may be represented by explicit
Owner decisions plus current docs. They should not be hidden in routine
Markdown summaries.

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
