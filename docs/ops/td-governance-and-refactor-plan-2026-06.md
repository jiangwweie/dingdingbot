---
title: TD_GOVERNANCE_AND_REFACTOR_PLAN_2026_06
status: OPERATING_PLAN
authority: owner-task + docs/canon/*
created: 2026-06-09
scope: global technical debt governance and refactor planning
---

# Technical Debt Governance & Refactor Plan - 2026-06

This document is a global technical debt governance and refactor plan for BRC.
It is not a StrategyRuntimeInstance-only design document and does not authorize
implementation by itself.

This is a documentation-only plan. It does not authorize code, migration, API,
test, runtime, database, exchange, or external-service changes.

Authoritative baseline:

- `docs/canon/PROJECT_BASELINE_CURRENT.md`
- `docs/canon/BRC_TARGET_SEMANTICS.md`
- `docs/canon/TECH_DEBT_BASELINE.md`
- `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
- `docs/canon/AGENT_WORKSPACE_RULES.md`
- `docs/canon/DOCUMENT_GOVERNANCE.md`

---

## 1. Purpose

The purpose of this plan is to govern technical debt refactor work while BRC
evolves from:

```text
Owner authorizes one trade
```

to:

```text
Owner authorizes a bounded StrategyRuntimeInstance
```

The plan must advance that target without breaking the current one-shot live
path. The existing one-shot path is a valuable asset and remains the current
implemented execution reality until tracked code proves otherwise.

This plan covers all current technical debt classes:

- **S0 target semantic debt**: gaps between current code semantics and target
  strategy runtime governance.
- **S1 execution / audit semantic debt**: missing traceability, execution
  semantics, runtime IDs, and policy integration.
- **S2 maintainability / product interpretation debt**: confusing boundaries,
  oversized files, config/profile drift, console semantics, and naming debt.
- **S3 cleanup debt**: legacy scripts, sandbox remnants, stale physical docs
  organization, and duplicate support assets.

StrategyRuntimeInstance is the first mainline. It is not the whole technical
debt program. Config, Console, scripts, readmodels, API decomposition, legacy
cleanup, and document reorganization must remain visible and sequenced instead
of being forgotten behind the runtime backbone.

---

## 2. Current Code Reality

Current executable path is the one-shot OwnerBoundedExecution short chain:

```text
OwnerRiskAcknowledgement
-> AuthorizationDraft
-> BoundedLiveTrialAuthorization
-> FinalGate
-> OwnerBoundedExecutionService
-> Entry / TP / SL
-> Order / Reconciliation / Review
```

Current facts:

- Current implemented execution is one-shot `OwnerBoundedExecution`.
- `BoundedLiveTrialAuthorization` is single-use trade authorization.
- Current code does not contain a real `StrategyRuntimeInstance`.
- `AdmissionTrialBinding` is not currently a running strategy instance.
- `StrategyFamilyVersion` does not currently bind to a real
  StrategyImplementation.
- `CandidateAction` / `BudgetedAutonomy` are currently readmodel / preview /
  policy evaluation, not executable chains.
- `SignalPipeline` is a legacy real-time signal system. It can be considered a
  future SignalEvaluation engine candidate, but it is not currently connected
  to the BRC StrategyFamily runtime governance chain.
- The current one-shot path is valuable and must not be broken by refactor
  work.

The target semantic chain remains:

```text
StrategyFamily
-> StrategyFamilyVersion
-> AdmissionDecision
-> OwnerRiskAcceptance
-> TrialBinding
-> StrategyRuntimeInstance
-> SignalEvaluation
-> OrderCandidate
-> FinalGate
-> ExecutionIntent
-> OrderLifecycle
-> Order / Position
-> Reconciliation
-> Review
```

No sprint may describe a target node as implemented until tracked code and
Codex review verify that fact.

---

## 3. Refactor Strategy

The refactor strategy is:

```text
long sprint
+ strong boundary
+ additive-only
+ shadow path
```

### Long Sprint

Codex can run long tasks when the objective is coherent. The program does not
need to split every refactor into tiny tasks if doing so would lose semantic
continuity.

Each long sprint still needs one primary outcome, explicit boundaries, and a
clear review point before the next sprint begins.

### Strong Boundary

Every sprint must define:

- allowed files;
- forbidden files;
- whether migrations are allowed;
- whether APIs are allowed;
- whether execution/order code is allowed;
- whether runtime/project/test execution is allowed;
- whether the output is shadow-only or executable;
- exact stop conditions.

If the sprint needs to cross its boundary, the sprint stops and reports.

### Additive-only

Default mode is additive-only:

- add models, tables, nullable fields, repositories, services, readmodels, and
  tests where approved;
- preserve old data and old behavior;
- keep new runtime semantics optional until proven;
- avoid broad renames;
- avoid deletion until replacement behavior is stable and explicitly promoted.

Destructive migrations, irreversible cleanup, and broad replacement work
require separate approval after evidence exists.

### Shadow Path

New runtime governance must first exist as a shadow path:

- no order placement;
- no order cancel / close / replace;
- no exchange calls;
- no live/testnet connection;
- no automatic execution intent creation unless a later sprint explicitly
  allows it;
- no change to current one-shot execute API behavior;
- no FinalGate execute trigger from Sprint 1 runtime state.

Shadow artifacts should be inspectable, auditable, and comparable before any
controlled execution integration.

---

## 4. Non-negotiable Invariants

These invariants apply across all sprints:

1. Do not delete `OwnerBoundedExecutionService`.
2. Do not replace `BoundedLiveTrialAuthorization`.
3. Do not change current one-shot execute API behavior.
4. Do not change exchange order placement behavior.
5. Do not let `StrategyRuntimeInstance` place orders in Sprint 1.
6. Do not let `SignalPipeline` automatically trigger runtime execution.
7. Do not force old `ExecutionIntent` / `Order` / `Review` records to have
   runtime IDs.
8. Do not prematurely change frontend action APIs.
9. Do not run live or testnet.
10. Do not perform destructive migrations.
11. Do not bypass or weaken FinalGate.
12. Do not bypass the Operation Layer.
13. Do not output secrets or secret-adjacent values.
14. Do not optimize strategy returns or tune ETH Pinbar parameters as part of
    technical debt refactor.
15. Do not treat readmodel, preview, metadata, or design-only objects as
    executable authority.

---

## 5. Technical Debt Coverage Matrix

| Debt Class | Debt | Covered By | Timing | Notes |
| ---------- | ---- | ---------- | ------ | ----- |
| S0 | Owner authorizes trade vs Owner authorizes StrategyRuntimeInstance | Runtime backbone, shadow path, controlled integration | Sprint 1, Sprint 5 | Current one-shot path remains intact while target semantics are introduced. |
| S0 | StrategyRuntimeInstance missing | Domain model, repository, service, lifecycle, readmodel/API inspection | Sprint 1 | Shadow-only in Sprint 1; no execution. |
| S0 | TrialBinding is not runtime instance | Runtime draft from TrialBinding | Sprint 1 | TrialBinding remains binding/evidence, not itself runtime. |
| S0 | Admission pass does not produce StrategyRuntimeInstanceDraft | Runtime draft creation path | Sprint 1 | Additive path only; does not replace admission behavior. |
| S0 | StrategyFamilyVersion does not bind real StrategyImplementation | StrategyContractV2 / implementation adapter plan | Sprint 3, later promotion | Do not overclaim execution binding before implementation exists. |
| S1 | runtime_instance_id / trial_binding_id / strategy_family_version_id do not cross ExecutionIntent / Order / Review | Nullable audit ID spine | Sprint 2 | Additive, nullable, backward compatible. |
| S1 | signal_evaluation_id / order_candidate_id missing from audit chain | Audit ID spine and shadow candidate models | Sprint 2, Sprint 3 | Old records are not forced to backfill IDs. |
| S1 | SignalEvaluation missing | SignalEvaluation model and adapters | Sprint 3 | Shadow-only; no exchange call. |
| S1 | OrderCandidate missing | OrderCandidate model and candidate readmodel | Sprint 3 | Does not create ExecutionIntent in Sprint 3. |
| S1 | EntryPolicy / ExitPolicy not connected to BRC execution | StrategyContractV2 adapter and later runtime integration | Sprint 3, Sprint 5 | ProtectionPolicy remains minimum safety, not full exit semantics. |
| S1 | FinalGate lacks runtime mode | Runtime-aware FinalGate checks | Sprint 4 | Adds checks; does not replace existing FinalGate. |
| S1 | Review / Reconciliation cannot trace full strategy runtime chain | Audit ID spine through Review / Reconciliation | Sprint 2, Sprint 5 | Improves traceability without breaking existing reviews. |
| S1 | TP/SL exit projection may be incomplete | Protection and runtime execution review | Sprint 4, Sprint 5 | Audit before runtime execution promotion. |
| S2 | Runtime Profile / ConfigManager multi-track drift | Runtime/config/safety boundary consolidation | Sprint 7 | Deferred until runtime semantics are clearer. |
| S2 | ExecutionPermission / CapitalProtection coverage inconsistent | Coverage review and consolidation | Sprint 7 | Must preserve current safety boundaries. |
| S2 | scripts bypass risk | Script risk classification and containment | Sprint 7, Sprint 9 | Do not run scripts during governance planning. |
| S2 | Trading Console readmodel and action semantics are not unified | Console runtime productization and API truth-source cleanup | Sprint 6, Sprint 8 | Console must not overclaim unavailable capabilities. |
| S2 | API / readmodel files too large | API / readmodel decomposition | Sprint 8 | Decompose after semantic model stabilizes. |
| S2 | CandidateAction / BudgetedAutonomy naming is misleading | Product/readmodel semantics cleanup | Sprint 6, Sprint 8 | Keep them readmodel/preview until code changes prove otherwise. |
| S3 | legacy scripts / sandbox / dead paths | Legacy scripts / sandbox cleanup | Sprint 9 | Risk-grade before deleting. |
| S3 | old research engineering remnants | Sandbox and dead-path cleanup | Sprint 9 | Preserve useful evidence where needed. |
| S3 | docs/ops physical directory is crowded | Documentation/evidence reorganization | Sprint 10 | Non-blocking; last-phase cleanup. |
| S3 | duplicate agent / skill / support files | Documentation/support cleanup | Sprint 10 | Must respect current agent authority rules. |

---

## 6. Sprint Roadmap

### Sprint 1: StrategyRuntimeInstance Backbone + Shadow Path

Scope:

- domain model;
- additive-only migration;
- repository;
- service;
- runtime draft from TrialBinding;
- runtime lifecycle;
- readmodel / API inspection;
- tests;
- ADR / design note.

Required properties:

- StrategyRuntimeInstance is introduced as shadow runtime governance
  infrastructure.
- Runtime draft can be derived from TrialBinding without treating TrialBinding
  as the running instance.
- Lifecycle vocabulary distinguishes draft, active shadow, paused, completed,
  failed, revoked, and other states as appropriate.
- Current one-shot path remains unchanged.

Forbidden:

- no real execution connection;
- no FinalGate execute trigger;
- no order placement;
- no replacement of one-shot path.

### Sprint 2: Audit ID Spine

Scope:

- nullable runtime semantic IDs;
- `runtime_instance_id`;
- `trial_binding_id`;
- `strategy_family_version_id`;
- `signal_evaluation_id`;
- `order_candidate_id`.

Gradual propagation targets:

- `ExecutionIntent`;
- `Order`;
- `Review`;
- `Reconciliation`.

Principles:

- additive-only;
- nullable;
- backward compatible;
- old `ExecutionIntent` / `Order` / `Review` records are not forced to carry
  runtime IDs.

### Sprint 3: SignalEvaluation / OrderCandidate Shadow Path

Scope:

- SignalEvaluation model;
- OrderCandidate model;
- StrategyContractV2 adapter;
- SignalPipeline adapter;
- candidate readmodel.

Required properties:

- SignalPipeline can feed shadow evaluation only through an explicit adapter.
- CandidateAction / BudgetedAutonomy remain readmodel / preview / policy
  evaluation.
- OrderCandidate remains shadow-only in this sprint.

Forbidden:

- no order placement;
- no ExecutionIntent creation;
- no exchange call.

### Sprint 4: Runtime-aware FinalGate

Scope:

- runtime status check;
- attempts remaining;
- budget remaining;
- allowed symbol / side;
- max leverage;
- active positions;
- protection requirement.

Required properties:

- Runtime-aware FinalGate adds validation context.
- Existing one-shot FinalGate behavior remains unchanged.
- Passing FinalGate still does not automatically place orders.

Forbidden:

- no replacement of existing FinalGate;
- no automatic execution;
- no behavior change to one-shot FinalGate.

### Sprint 5: Controlled Runtime Execution Integration

Scope:

```text
StrategyRuntimeInstance
-> SignalEvaluation
-> OrderCandidate
-> FinalGate
-> ExecutionIntent
```

Required properties:

- Reuse existing safety boundaries.
- Execution is Owner-gated only.
- ExecutionIntent creation must occur through the approved path.
- Current one-shot OwnerBoundedExecution remains available.

Forbidden:

- no Operation Layer bypass;
- no real-funds or live-profile enablement by refactor;
- no runtime self-elevation;
- no unbounded symbol, side, leverage, notional, or attempt expansion.

### Sprint 6: Trading Console Runtime Productization

Scope:

- runtime shelf;
- runtime detail;
- signal evaluations;
- order candidates;
- attempts remaining;
- budget remaining;
- runtime review.

Required properties:

- Trading Console becomes an Owner operating surface for runtime governance.
- UI distinguishes readmodel, preview, shadow, candidate, authorized, gated,
  executable, active, paused, revoked, completed, and reviewed states where
  applicable.
- Product wording must not overclaim capabilities not implemented in tracked
  code.

### Sprint 7: Runtime / Config / Safety Boundary Consolidation

Scope:

- Runtime Profile / ConfigManager multi-track governance;
- ExecutionPermission coverage;
- CapitalProtection enforcement review;
- scripts bypass containment.

Required properties:

- Consolidate authority boundaries without changing live runtime profile or
  live trading config by default.
- Identify gaps between permission, capital protection, runtime profile, and
  script entry points.
- Contain bypass risk before broad cleanup.

### Sprint 8: API / ReadModel Decomposition

Scope:

- large API/readmodel file decomposition;
- Trading Console API truth-source cleanup;
- readmodel/action semantics layering.

Required properties:

- Split for maintainability after core semantic model is stable.
- Preserve frontend behavior unless an explicit UI/API task approves changes.
- Keep action APIs distinct from readmodel and preview APIs.

### Sprint 9: Legacy Scripts / Sandbox Cleanup

Scope:

- scripts risk grading;
- sandbox / research engineering downgrade;
- dead path cleanup.

Required properties:

- Grade scripts by exchange/database/runtime risk before cleanup.
- Preserve evidence needed for current canon or ADR traceability.
- Delete only after replacement or irrelevance is verified.

### Sprint 10: Documentation / Evidence Physical Reorganization

Scope:

- move appropriate docs/ops physical evidence to docs/evidence;
- organize archive structure;
- reduce docs/ops crowding.

Required properties:

- Non-blocking and last-phase.
- Canon remains the current fact source.
- Historical evidence remains available but cannot override canon.
- Agent instruction files are not re-authorized by physical movement.

---

## 7. Per-Sprint Review Checklist

Each sprint must review:

1. Was the sprint objective completed?
2. Were any forbidden changes violated?
3. Was the one-shot path broken or behaviorally changed?
4. Did the sprint produce any non-additive migration?
5. Did the sprint touch execution/order path?
6. Is a `docs/canon` update needed?
7. Were tests added where the sprint allowed implementation?
8. Were there any unstated API or DB behavior changes?
9. Can the program safely enter the next sprint?
10. Does the next sprint need a narrower scope?
11. Are metadata, readmodel, preview, shadow, and executable states still
    clearly separated?
12. Are secrets and secret-adjacent values masked?
13. Did agents stay inside allowed files?
14. Did the work preserve FinalGate and Operation Layer boundaries?

---

## 8. Stop Conditions

Stop and report if any sprint requires:

- modifying exchange order placement;
- replacing `OwnerBoundedExecutionService`;
- changing current one-shot execute behavior;
- destructive migration;
- live/testnet connection;
- allowing `StrategyRuntimeInstance` to place orders directly;
- allowing `SignalPipeline` to automatically enter execution;
- completing the sprint only by breaking the old one-shot chain;
- resolving a canon/code fact conflict without Codex/Owner review;
- outputting secrets;
- changing live runtime profile, live trading config, credentials, or
  real-funds order-sizing defaults;
- bypassing or weakening FinalGate;
- bypassing the Operation Layer.

---

## 9. What Is Explicitly Deferred

These items are intentionally deferred, not forgotten:

- Runtime Profile / ConfigManager consolidation.
- Script bypass cleanup.
- API/readmodel decomposition.
- Trading Console runtime productization.
- `docs/ops` physical reorganization.
- Legacy sandbox cleanup.
- Full runtime execution integration.

The reason for deferral is sequencing: the program must first establish the
runtime semantic backbone, audit ID spine, and shadow candidate path before
consolidating surrounding surfaces.

---

## 10. Codex Execution Report Format

Each sprint must end with:

```text
# Sprint Report

## 1. Summary
## 2. Branch / Commits
## 3. Files Changed
## 4. What Was Implemented
## 5. What Was Not Changed
## 6. Boundary Compliance
## 7. Tests / Validation
## 8. Migration Safety
## 9. Risks / Open Questions
## 10. Recommended Next Sprint
```

The report must explicitly state whether the sprint was shadow-only or touched
an executable path. It must also state whether canon updates are required.

---

## 11. Canon Update Rules

`docs/canon` is the current fact source and should not grow into a sprint log.

Rules:

- Sprint plans and execution records live in `docs/ops`.
- Sprint reports cannot override canon.
- Update `docs/canon` only when current facts or target semantics have changed
  in a stable way.
- Stable changes require tracked code verification, explicit Owner decision,
  accepted ADR, or a verified report that does not conflict with code.
- Do not update canon from proposals, unmerged work, shadow-only intentions, or
  historical docs.
- Do not mark `StrategyRuntimeInstance` as implemented until tracked code
  implements it and Codex verifies the behavior.
- Do not mark one-shot OwnerBoundedExecution as final architecture.
- If a sprint discovers conflict between canon and code fact, stop and report.

Likely canon files affected after future implementation sprints:

- `docs/canon/PROJECT_BASELINE_CURRENT.md`
- `docs/canon/BRC_TARGET_SEMANTICS.md`
- `docs/canon/TECH_DEBT_BASELINE.md`
- `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
- `docs/canon/AGENT_WORKSPACE_RULES.md`

Canon should remain short, factual, and free of implementation diaries.
