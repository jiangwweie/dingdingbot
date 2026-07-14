---
title: L1_L9_OPTIMIZATION_EXECUTION_PLAN
status: CURRENT_EXECUTION_PLAN
authority: docs/current/L1_L9_OPTIMIZATION_EXECUTION_PLAN.md
last_verified: 2026-07-06
---

# L1-L9 Optimization Execution Plan

## Purpose

This document converts the L1-L9 review into executable engineering batches.
It is written so that, after Owner confirmation, an implementation worker can
start from this plan without reopening architecture questions.

This plan is not a live-submit authorization and does not mutate runtime
profiles, sizing defaults, credentials, or exchange state.

## Evidence Basis

| Source | Role |
| --- | --- |
| `docs/current/L1_L9_SYSTEM_REVIEW_AND_OPTIMIZATION_AUDIT.md` | Full-chain audit and 5+ issues per layer |
| `docs/current/RUNTIME_TERMINOLOGY_OWNER_EXPLANATION_GOVERNANCE.md` | Terminology and Owner explanation design |
| `docs/current/ACTIVE_STRATEGYGROUP_SEMANTICS_REVIEW_AND_OPTIMIZATION_PLAN.md` | Strategy semantics review |
| `docs/current/MULTI_STRATEGY_MULTI_SYMBOL_MULTI_SIDE_ACTION_TIME_EVOLUTION_DESIGN.md` | Multi-signal arbitration design |
| `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md` | Runtime chain authority |
| `docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md` | PG table/constraint design |

## Execution Principles

| Principle | Required behavior |
| --- | --- |
| **Replace, not parallel** | Remove or rewrite old runtime decision paths instead of keeping fallbacks |
| **PG current state is truth** | L2-L7 decisions read PG lineage, not repo MD/JSON/output |
| **Event-driven semantics** | Fresh signal means real market event with event spec and event time |
| **One real-submit lane** | Multiple promotions allowed, one real-submit lane and ticket |
| **Owner explanation is derived** | Plain language explains PG state; it does not decide state |
| **Negative tests are required** | Invalid paths must be rejected, not merely ignored |

## Batch Overview

| Batch | Priority | Goal | Main capability unlocked |
| --- | --- | --- | --- |
| **B0** | P0 | Lock current review/design docs into source map | Implementation can use durable docs |
| **B1** | P0 | Split and enforce active StrategyGroup event semantics | Unsupported side/event rejected before signal |
| **B2** | P0 | Harden SOR-LONG / SOR-SHORT event path | SOR can be bidirectional without ambiguity |
| **B3** | P0 | Implement glossary-backed explanation projection | Owner can understand no-trade and stage reached |
| **B4** | P0 | Promote arbitration to first-class PG policy/run | Multiple fresh signals produce one winner |
| **B5** | P1 | Clean legacy naming/source semantics | New frontend/product surface does not inherit stale backend model |
| **B6** | P1 | Harden post-submit/reconciliation review proof | First real order can close learning loop cleanly |

## Shared Hard Stops

Every batch must stop if it would introduce:

```text
FinalGate bypass
Operation Layer bypass
exchange write outside official path
live profile expansion
order sizing expansion
credential mutation
withdrawal or transfer
repo MD/JSON/output as runtime source
unsupported side mirroring
generated_at as signal event time
replay event as fresh live signal
```

## B0 - Durable Document Registration

### Task Card

| Field | Content |
| --- | --- |
| **Task ID** | `B0-L1-L9-DURABLE-DOC-REGISTRY` |
| **Goal** | Register L1-L9 audit, terminology governance, strategy semantics review, multi-signal design, and execution plan in the information architecture source map |
| **Why** | New implementation work must not depend on temporary chat memory or an unindexed temporary draft |
| **Allowed files** | `docs/current/PROJECT_INFORMATION_ARCHITECTURE.md`, new `docs/current/*.md` design docs |
| **Forbidden files** | Runtime code, migrations, `frontend/`, output artifacts |
| **Requirements** | Source map names each durable design doc and clarifies that temporary L2-L7 draft is not long-term authority |
| **Tests** | `git diff --check`; `rg` source map entries |
| **Done When** | Durable docs are discoverable from `PROJECT_INFORMATION_ARCHITECTURE.md` |
| **Hard Stop** | Do not delete temporary draft until all confirmed decisions are landed in durable docs |

## B1 - Active Event Spec And RequiredFacts Enforcement

### Task Card

| Field | Content |
| --- | --- |
| **Task ID** | `B1-ACTIVE-EVENT-SPEC-REQUIREDFacts-CLOSURE` |
| **Goal** | Make the six active event specs and RequiredFacts the enforceable semantic source |
| **Why** | Strategy semantics must not come from old side constants, handoff JSON, or broad `supported_sides` lists |
| **Allowed files** | `migrations/versions/*`, `src/infrastructure/pg_models.py`, PG repository code, seed scripts, Candidate Pool materializers, focused tests |
| **Forbidden files** | Live profiles, sizing defaults, credentials, `frontend/`, unrelated strategy research |
| **Requirements** | Seed/validate `CPM-LONG`, `MPG-LONG`, `MI-LONG`, `SOR-LONG`, `SOR-SHORT`, `BRF2-SHORT`; bind symbols/sides/events; reject unsupported scope before signal |
| **Global Authority Model** | Owner controls policy; PG event/scope controls allowed semantics; code computes facts |
| **Chain Position** | `pretrade_candidate_readiness` |
| **Live Enablement State Before** | Some semantics still exist as code/docs conventions |
| **Live Enablement State After** | PG event/scope is the runtime semantic source |
| **Blocker Removed Or Reclassified** | `scope_not_attached` / semantic drift becomes DB-enforced scope |
| **Per-Symbol / Per-Fact Acceptance** | Every active candidate symbol binds one event spec and RequiredFacts version |
| **Stop Condition** | Unsupported side/symbol/event rejects before watcher/signal/promotion |
| **Capability Unlocked** | Event-backed L2 Candidate Universe |
| **Next Engineering Bottleneck** | SOR evaluator split and multi-signal arbitration |
| **Rehearsal/Simulation Boundary** | No exchange write; seed/validation only |
| **Tests** | Negative tests for CPM short, MPG short, MI short, BRF2 long, generic SOR signal, generated event time |
| **Done When** | Candidate Pool cannot create promotion from unsupported side/event |
| **Hard Stop** | No JSON fallback or long-term PG + file dual authority |

## B2 - SOR-LONG / SOR-SHORT Semantic Split

### Task Card

| Field | Content |
| --- | --- |
| **Task ID** | `B2-SOR-SIDE-EVENT-SPLIT-CLOSURE` |
| **Goal** | Convert SOR from broad side support into two explicit event paths |
| **Why** | Current SOR has the largest semantic ambiguity: both sides are declared, but reference logic is not fully split |
| **Allowed files** | SOR detector/evaluator code, strategy semantics code, PG event seed, Candidate Pool tests, runtime signal planning tests |
| **Forbidden files** | Operation Layer submit behavior, exchange gateway, live profile, sizing defaults |
| **Requirements** | `SOR-LONG` uses closed 15m breakout above opening range high; `SOR-SHORT` uses closed 15m breakdown below opening range low; both require side-specific protection refs |
| **Global Authority Model** | Strategy/event specs define allowed events; evaluator computes events; ticket fixes exact trade identity |
| **Chain Position** | `fresh_signal_promotion` |
| **Live Enablement State Before** | Generic SOR / short-oriented path can confuse side semantics |
| **Live Enablement State After** | SOR long and short are separate event-backed candidates |
| **Blocker Removed Or Reclassified** | `replay_live_rule_mismatch` / semantic ambiguity |
| **Per-Symbol / Per-Fact Acceptance** | ETH, SOL, AVAX, BTC have exact side/event facts |
| **Stop Condition** | Generic SOR signal cannot promote |
| **Capability Unlocked** | Bidirectional SOR without forced mirroring |
| **Next Engineering Bottleneck** | Arbitration conflict when both sides appear |
| **Tests** | SOR-LONG with short facts rejected; SOR-SHORT with long facts rejected; same-session conflict covered |
| **Done When** | SOR promotion rows always include exact event spec and side-specific fact refs |
| **Hard Stop** | Do not let one detector output satisfy both sides without two event rows |

## B3 - Owner Explanation Projection

### Task Card

| Field | Content |
| --- | --- |
| **Task ID** | `B3-OWNER-EXPLANATION-PROJECTION-CLOSURE` |
| **Goal** | Add plain-language explanation fields to runtime projections and forensics |
| **Why** | Owner repeatedly asks what terms mean and why no trade happened because internal terms are exposed too early |
| **Allowed files** | Projection builders, server monitor, runtime forensics skill, tests, docs |
| **Forbidden files** | FinalGate logic, Operation Layer submit logic, live profile, sizing defaults |
| **Requirements** | Emit `owner_state`, `plain_language_stage`, `plain_language_reason`, `plain_language_next_system_action`, `owner_action_required`, and lineage refs |
| **Global Authority Model** | Explanation derives from PG current state; it never decides trade authority |
| **Chain Position** | `daily_live_enablement_status` |
| **Live Enablement State Before** | Internal terms require manual interpretation |
| **Live Enablement State After** | Owner can see signal, stage reached, first missing object, and whether action is needed |
| **Blocker Removed Or Reclassified** | Explanation gap becomes machine-readable owner status |
| **Per-Symbol / Per-Fact Acceptance** | Computed-not-satisfied rows name failed facts in plain language |
| **Stop Condition** | Every no-trade status has market/engineering/policy/safety classification |
| **Capability Unlocked** | No-trade and recent-signal forensics become self-explanatory |
| **Next Engineering Bottleneck** | Future frontend can consume Owner language read model |
| **Tests** | Snapshot tests for market wait, computed-not-satisfied, promotion, ticket missing, hard safety stop |
| **Done When** | Forensics can answer "why no trade" without asking user to interpret FinalGate/Operation terms |
| **Hard Stop** | Do not read JSON exports when PG lineage exists |

## B4 - Multi-Candidate Arbitration

### Task Card

| Field | Content |
| --- | --- |
| **Task ID** | `B4-PG-MULTI-CANDIDATE-ARBITRATION-CLOSURE` |
| **Goal** | Make multi-signal winner selection a first-class PG-backed process |
| **Why** | Multiple strategies/symbols/sides can be fresh at once; V0 still needs one real-submit lane |
| **Allowed files** | PG schema/repository, promotion materializer, action-time lane materializer, tests, server monitor projection |
| **Forbidden files** | Exchange gateway, live profile, sizing defaults, broad strategy optimizer |
| **Requirements** | Multiple promotions may exist; exactly one `arbitration_won`; only winner creates real-submit lane; only lane creates ticket |
| **Global Authority Model** | Arbitration is process selection, not strategy-return optimization |
| **Chain Position** | `fresh_signal_promotion` / `action_time_boundary` |
| **Live Enablement State Before** | Multi-candidate behavior exists but not fully policy-visible |
| **Live Enablement State After** | Deterministic arbitration result exists with winner/loser reasons |
| **Blocker Removed Or Reclassified** | Ambiguous multi-signal handling becomes explicit process rule |
| **Per-Symbol / Per-Fact Acceptance** | Stale, unsupported, missing policy, missing budget, missing protection, active conflict eliminated before rank |
| **Stop Condition** | One open real-submit lane and one active ticket maximum |
| **Capability Unlocked** | Several fresh events can be handled without Owner manual selection |
| **Next Engineering Bottleneck** | Real order outcome calibration after first submit |
| **Tests** | Duplicate signals, stale vs fresh, same symbol opposite side, MPG vs SOR, BRF2 with active long conflict, concurrent worker lock |
| **Done When** | Projection explains winner and losers from PG arbitration |
| **Hard Stop** | Do not let Candidate Pool JSON select or override winner |

## B5 - Legacy Naming And Source Cleanup

### Task Card

| Field | Content |
| --- | --- |
| **Task ID** | `B5-LEGACY-RUNTIME-SOURCE-AND-NAMING-CLEANUP` |
| **Goal** | Remove or rewrite stale source names and runtime decision paths that can mislead new product/frontend work |
| **Why** | `owner_console` / `trading_console` names and historical source paths can pull the system back into old mental models |
| **Allowed files** | Readmodel/API naming wrappers, source map docs, deprecation/removal tests, imports |
| **Forbidden files** | Functional submit logic unless explicitly covered by tests; `frontend/` |
| **Requirements** | Inventory old names; classify as convert/delete/clean/archive; remove runtime authority from incompatible sources |
| **Global Authority Model** | Owner sees product state; developer APIs may remain only with explicit compatibility removal plan |
| **Chain Position** | `daily_live_enablement_status` |
| **Live Enablement State Before** | Old naming remains in backend/readmodels |
| **Live Enablement State After** | New product/readmodel naming can be built without stale console semantics |
| **Blocker Removed Or Reclassified** | Legacy semantic drift |
| **Tests** | Import compatibility, API route tests, no old source can set current blocker |
| **Done When** | Stale names are either removed, renamed, or documented as short-lived compatibility with tests |
| **Hard Stop** | Do not break current runtime endpoints without replacement acceptance |

## B6 - Post-Submit Closure And Review Hardening

### Task Card

| Field | Content |
| --- | --- |
| **Task ID** | `B6-TICKET-BOUND-POST-SUBMIT-REVIEW-CLOSURE` |
| **Goal** | Ensure first accepted real order can flow through protection, reconciliation, settlement, and review |
| **Why** | L9 is not fully proven until real order lineage closes |
| **Allowed files** | Post-submit closure materializer, reconciliation service boundaries, review outcome writer, tests |
| **Forbidden files** | Exchange write shortcuts, manual order mutation paths, live profile/sizing mutation |
| **Requirements** | Every accepted attempt binds ticket, finalgate pass, submit command, protection refs, reconciliation, settlement, review outcome |
| **Global Authority Model** | Review updates strategy governance; it does not grant current submit authority |
| **Chain Position** | `action_time_boundary` / post-submit closure |
| **Live Enablement State Before** | Simulator proof exists; real order closure is still live-outcome dependent |
| **Live Enablement State After** | First real submit can be closed and reviewed without ad hoc artifacts |
| **Blocker Removed Or Reclassified** | Post-submit lifecycle proof gap |
| **Tests** | accepted/protected, protection failed, partial fill, rejected, stale local order, exchange mismatch |
| **Done When** | Post-submit closure row can explain final state and review recommendation |
| **Hard Stop** | Do not delete or mutate historical order/position state destructively |

## Recommended First Implementation Order

| Order | Batch | Reason |
| --- | --- | --- |
| 1 | **B0** | Makes durable docs discoverable |
| 2 | **B1** | Locks StrategyGroup semantics before runtime projection work |
| 3 | **B2** | Fixes the highest-risk strategy-specific ambiguity |
| 4 | **B4** | Prepares for multiple simultaneous fresh signals |
| 5 | **B3** | Makes the resulting chain understandable to Owner/forensics/frontend |
| 6 | **B5** | Prevents stale product model from leaking into frontend |
| 7 | **B6** | Hardens after-submit proof before first real-order learning loop |

## Completion Audit Checklist

| Requirement | Proof |
| --- | --- |
| L1-L9 review exists with 5+ issues per layer | `L1_L9_SYSTEM_REVIEW_AND_OPTIMIZATION_AUDIT.md` |
| Terminology governance exists | `RUNTIME_TERMINOLOGY_OWNER_EXPLANATION_GOVERNANCE.md` |
| Strategy semantics review exists | `ACTIVE_STRATEGYGROUP_SEMANTICS_REVIEW_AND_OPTIMIZATION_PLAN.md` |
| Multi-strategy/multi-symbol/multi-side design exists | `MULTI_STRATEGY_MULTI_SYMBOL_MULTI_SIDE_ACTION_TIME_EVOLUTION_DESIGN.md` |
| Execution plan is detailed enough for task cards | This document |
| No frontend work included | Git status excludes `frontend/` from staged docs work |
| No runtime authority changed | Docs only unless later implementation task is accepted |

## Chain Position

```text
chain_position: l1_l9_optimization_execution_planning
strategy_group_id: active WIP StrategyGroups
symbol: active candidate universe
stage: execution_plan_ready_for_owner_confirmation
first_blocker: implementation has not yet been authorized against these task batches
evidence: durable design docs listed in Evidence Basis
next_action: after Owner confirmation, start B0 then B1 implementation
stop_condition: B1/B2/B4 negative tests prove event/scope/arbitration constraints
owner_action_required: yes_for_execution_confirmation_only
authority_boundary: planning only; no FinalGate, Operation Layer, exchange write, profile mutation, or sizing mutation
```
