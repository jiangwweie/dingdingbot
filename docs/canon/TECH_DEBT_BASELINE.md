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
| TrialBinding is not runtime instance | Audit binding record | Should bind admitted strategy to running instance | Requires StrategyRuntimeInstance to exist |
| Admission does not create runtime draft | Admission pass creates metadata record | Admission pass should create StrategyRuntimeInstanceDraft | Requires new code path |

---

## 3. Current S1 Debt

| Debt | Impact | Notes |
| ---- | ------ | ----- |
| EntryPolicy / ExitPolicy not connected to BRC execution | Strategy exit decisions are ad-hoc, not part of strategy semantics | StrategyContractV2 is a candidate asset |
| Authorization is single-use | Cannot express multi-attempt strategy runtime | Current BoundedLiveTrialAuthorization is one-shot |
| strategy_family_id / trial_binding_id not propagated to Order / Review | Review cannot trace full semantic chain | Requires adding semantic IDs to order lifecycle |
| SignalPipeline and BRC StrategyFamily are dual-track | Legacy signal system not connected to BRC admission chain | SignalPipeline is candidate for SignalEvaluation engine |
| BRC TP/SL exit projection may be incomplete | Protection logic exists but may not cover all edge cases | Needs audit when strategy runtime path is built |

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
- Do not implement StrategyRuntimeInstance without a Codex task card.

These items may become future work when Codex promotes them.
