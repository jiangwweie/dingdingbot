---
title: TECH_DEBT_BASELINE
status: CURRENT_CANON
authority: owner-semantic-audit + code-verification
last_verified: 2026-06-09
source_of_truth:
  - docs/canon/PROJECT_BASELINE_CURRENT.md
  - docs/canon/BRC_TARGET_SEMANTICS.md
  - owner semantic audit 2026-06-09
---

# Technical Debt Baseline

This document classifies known technical debt in the BRC project.

---

## 1. Debt Classification

| Level | Name | Meaning |
| ----- | ---- | ------- |
| S0 | Target semantic debt | Current code semantics diverge from target architecture |
| S1 | Audit / execution semantic debt | Gaps in audit trail, execution semantics, or strategy integration |
| S2 | Maintainability / product interpretation debt | Naming confusion, large files, agent instruction drift |
| S3 | Cleanup debt | Low-priority cleanup, dead code, documentation |

---

## 2. Current S0 Debt

| Debt | Current Code Reality | Target Semantics | Notes |
| ---- | -------------------- | ---------------- | ----- |
| Owner authorizes trade vs runtime instance | Owner authorizes single trade via BoundedLiveTrialAuthorization | Owner should authorize bounded StrategyRuntimeInstance | Core semantic gap |
| StrategyFamilyVersion not executable | Strategy specification document, not bound to strategy implementation | Should be versioned executable strategy definition | Requires strategy runtime infrastructure |
| Strategy semantics partially bound locally | CPM / BRF / RMR / FCO are now identified as initial reference/backlog candidates, and a local B0 pure model, context builder, trusted runtime fact overlay, promotion gate, shadow binding service, plus non-executing runtime planning bridge defines StrategyImplementationBinding, RequiredFacts, StrategyEvaluationContext, EntryPolicy, ProtectionPolicy, ExitPolicy, right-tail review metrics, and Owner/Codex promotion blockers; it can map StrategyFamilySignalInput / StrategyFamilySignalOutput / optional StrategyRuntimeInstance snapshots into RequiredFacts, replace caller-provided account/position allow facts with trusted read-only overlays when configured, create semantically bound shadow OrderCandidates, and reach RuntimeExecutionPlan / RuntimeExecutionIntentDraft; Trading Console has an internal non-endpoint service factory for the planner; concrete BRF/RMR evaluator details and runtime promotion confirmations remain incomplete | Controlled runtime execution should be gated by Strategy Semantics / Entry-Exit Policy Binding | B0 gate before real OrderLifecycle adapter or runtime submit |
| TrialBinding is not runtime instance | Audit binding record; shadow StrategyRuntimeInstance now exists separately | Should bind admitted strategy to running instance | Runtime identity exists, but executable integration is not complete |
| Admission does not create executable runtime | Admission pass can support shadow runtime draft/backbone work, but does not authorize execution | Admission should feed bounded StrategyRuntimeInstance governance | Runtime execution remains future work |

---

## 3. Current S1 Debt

| Debt | Impact | Notes |
| ---- | ------ | ----- |
| EntryPolicy / ExitPolicy not connected to BRC execution | Strategy exit decisions are ad-hoc, not part of strategy semantics | StrategyContractV2 is a candidate asset |
| RequiredFacts / freshness / missing-fact behavior need runtime source integration | Local B0 semantics declare and test missing/stale behavior, the local context builder maps existing signal/runtime snapshots into RequiredFacts, and the trusted runtime fact overlay can fail closed on unavailable account/position sources; Trading Console internal assembly can inject PG positions and cached account facts, but live scheduler/runtime evaluation binding plus funding/OI/crowding readers are not fully wired | Each StrategyImplementation must declare required_facts, optional_facts, freshness_requirement, and missing_fact_behavior |
| ProtectionPolicy and ExitPolicy are not yet integrated into execution binding | Local B0 semantics separates ProtectionPolicy and ExitPolicy, but real execution/protection handoff still needs controlled integration | ProtectionPolicy must bound loss; ExitPolicy must express profit-taking, runner, trailing, invalidation, time-stop, and lifecycle exits |
| Short-side BRF profile not yet fully confirmed | Doing short-side price action with long-side defaults would understate squeeze risk; the promotion gate blocks BRF promotion until a conservative short-side profile is confirmed | BRF must start with lower leverage, smaller notional, mandatory hard stop, strict max_active_positions, and Owner-confirm-each-entry |
| RMR classifier could become an over-strong filter | A broad hard regime filter could silently suppress strategies without reviewed confidence/freshness semantics | RMR starts as regime evidence / observe-only downgrade input, not execution authority |
| attempt / budget confirmation partially specified locally | Runtime reservation/mutation now prefers concrete max-loss evidence for `budget_reserved` and falls back to notional only when loss-budget evidence is missing; the promotion gate blocks runtime promotion and first-real-submit review until attempt, reservation, release/consume, duplicate-submit, protection-failure, account facts, and deployment confirmations are present | First real submit must confirm attempt consumption, budget reservation/release, protection failure handling, duplicate-submit blocking, account facts, and deployment readiness |
| Authorization is single-use | Cannot express multi-attempt strategy runtime | Current BoundedLiveTrialAuthorization is one-shot |
| runtime semantic IDs only partially propagated | Review cannot yet trace full runtime chain end-to-end | Nullable IDs and source-native recorded ExecutionIntent audit exist in the local working tree; order/review propagation is still incomplete |
| SignalPipeline and BRC StrategyFamily are dual-track | Legacy signal system not connected as an executable StrategyRuntimeInstance trigger | SignalPipeline is candidate for SignalEvaluation engine |
| Runtime-aware FinalGate has preview-only fact gaps | Runtime execution cannot safely rely on user-supplied active position counts; local signal-to-draft bridge and trusted fact overlay block when local active-position facts are unavailable, but live/runtime source orchestration is not yet productized | Active position facts must come from local projection/reconciliation or block when unavailable/stale |
| Recorded runtime ExecutionIntent is not live-submit integrated | In the local working tree, runtime candidate can become an audit intent, Owner submit authorization, controlled-submit plan, submit-time FinalGate preflight, preflight-gated disabled/blocked/not-implemented result, non-mutating attempt reservation preview, pending attempt reservation audit record, controlled runtime attempt mutation record, runtime-native protection plan preview/record, runtime OrderLifecycle handoff draft record, non-executing OrderLifecycle adapter preview gate, and non-executing submit adapter preview; it still cannot create/register local orders, submit an order, or call OrderLifecycle | This is intentional until the controlled submit adapter, OrderLifecycle adapter, submit adapter, and reconciliation closure are explicitly designed |
| BRC TP/SL exit projection may be incomplete | Protection logic exists but may not cover all edge cases | Needs audit when strategy runtime path is built |
| Review lacks right-tail and capital-base semantics | Stable-yield metrics can misclassify low-win-rate asymmetric strategies or Owner withdrawals | Review should track MFE/MAE, payoff asymmetry, tail wins, bounded max loss, manual withdrawals, and capital base adjustments |

---

## 4. Current S2 Debt

| Debt | Impact | Notes |
| ---- | ------ | ----- |
| Runtime Profile / TrialBinding / Authorization boundary sources unclear | Agent confusion about which authorization source applies | Need clear authority chain doc |
| CandidateAction / BudgetedAutonomy naming suggests execution | Agents may treat readmodel as executable | Naming is S2 debt; classification is in canon |
| Large API / readmodel files | Maintainability risk | Not blocking current work |
| Old docs / agent instructions can mislead agents | Stale instructions in docs/ops/ and .claude/ | Phase 3c will quarantine high-risk agent instructions |
| docs/ops/ ~155 files with mixed authority | Hard to determine which are current | Canon establishment (this phase) addresses this |

---

## 5. Non-goals

These are explicitly not current work:

- Do not delete one-shot execution path (OwnerBoundedExecutionService).
- Do not delete SignalPipeline.
- Do not delete Admission metadata chain.
- Do not large-refactor OrderLifecycle.
- Do not batch-delete historical docs.
- Do not promote shadow StrategyRuntimeInstance / SignalEvaluation /
  OrderCandidate records into execution authority without an explicit Codex
  task card and Owner-gated execution boundary.
- Do not design automatic withdrawal, transfer, or fund movement.

These items may become future work when Codex promotes them.
