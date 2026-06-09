---
title: PROJECT_BASELINE_CURRENT
status: CURRENT_CANON
authority: owner-correction + code-verification + semantic-audit
last_verified: 2026-06-09
supersedes:
  - docs/ops/knowledge-pack/PROJECT_BASELINE_CURRENT.md (for canon reading order)
source_of_truth:
  - docs/ops/knowledge-pack/PROJECT_BASELINE_CURRENT.md
  - docs/ops/knowledge-pack/CURRENT_PRODUCT_OPERATING_MODEL.md
  - docs/ops/knowledge-pack/CURRENT_FACT_REGISTRY.md
  - tracked code verification
  - owner semantic audit 2026-06-09
---

# Project Baseline Current

This is the authoritative project baseline for agent reading. It distills
verified facts from the knowledge-pack sources. For detailed evidence, consult
the source_of_truth files listed above.

---

## 1. Current Project Definition

BRC is a personal quantitative strategy runtime governance system.

Current code implements an Owner-controlled bounded-live research and execution
system. The current executable path is one-shot Owner-authorized single trade
execution.

Current governance direction is converging on Strategy Runtime Governance:
Owner should authorize a bounded StrategyRuntimeInstance, not one immediate
trade.

---

## 2. Current Code Reality

Current executable path is one-shot Owner authorization:

```text
OwnerRiskAcknowledgement
-> AuthorizationDraft
-> BoundedLiveTrialAuthorization
-> FinalGate
-> OwnerBoundedExecutionService
-> Entry / TP / SL
-> Order / Reconciliation / Review
```

Key facts:

- **BoundedLiveTrialAuthorization** is single-use trade authorization. It is
  not a strategy runtime authorization.
- **Current code does not implement StrategyRuntimeInstance.** There is no
  running strategy instance that generates signals or order candidates.
- **StrategyFamily / Admission** exists as metadata, admission classification,
  and evidence chain. It does not bind to executable strategy code.
- **CandidateAction / BudgetedAutonomy** are readmodel / preview / policy
  evaluation. They are not execution chains.
- **SignalPipeline** is the current legacy real-time signal system. It is a
  candidate asset for a future SignalEvaluation engine, but is not connected to
  the BRC StrategyFamily chain.
- **OwnerBoundedExecutionService** is a valuable one-shot real-closed-loop
  execution asset. It is not the final target BRC architecture.
- **Order / Reconciliation / Review** infrastructure is reusable but lacks
  strategy semantic IDs (strategy_family_id, trial_binding_id,
  strategy_runtime_instance_id) propagating through the chain.

---

## 3. Current Target Direction

BRC should become strategy runtime governance:

- Owner should authorize a bounded StrategyRuntimeInstance.
- StrategyRuntimeInstance should generate SignalEvaluation / OrderCandidate
  within risk boundaries.
- The target chain is defined in `docs/canon/BRC_TARGET_SEMANTICS.md`.

---

## 4. Do Not Misread

- Do not treat one-shot OwnerBoundedExecution as final architecture.
- Do not treat TrialBinding as an already-running strategy instance.
- Do not treat StrategyFamilyVersion as executable strategy code.
- Do not treat CandidateAction as executable.
- Do not treat BudgetedAutonomy as auto trading.
- Do not treat archived docs as current truth.
- Do not treat old read-only / research-only docs as current constraints.
- Do not treat docs/ops/ historical documents as current canon.

---

## 5. Authoritative Reading Order

For agents joining this project, read in this order:

1. `CLAUDE.md` / `AGENTS.md` — root entry points
2. `docs/canon/PROJECT_BASELINE_CURRENT.md` — this file
3. `docs/canon/BRC_TARGET_SEMANTICS.md` — target semantics and status map
4. `docs/canon/RUNTIME_SAFETY_BOUNDARY.md` — execution safety boundaries
5. `docs/canon/TECH_DEBT_BASELINE.md` — known debt classification
6. `docs/canon/DOCUMENT_GOVERNANCE.md` — how to read and trust documents

For detailed evidence and historical context, consult:

- `docs/ops/knowledge-pack/CURRENT_PRODUCT_OPERATING_MODEL.md`
- `docs/ops/knowledge-pack/PROJECT_BASELINE_CURRENT.md`
- `docs/ops/knowledge-pack/CURRENT_FACT_REGISTRY.md`
- `docs/ops/knowledge-pack/CURRENT_READINESS_BLOCKERS.md`
- `docs/ops/agent-current-brc-baseline.md`
- `docs/ops/agent-working-rules.md`
