---
title: BRC_TARGET_SEMANTICS
status: CURRENT_CANON
authority: owner-semantic-audit + code-verification
last_verified: 2026-06-09
source_of_truth:
  - docs/canon/PROJECT_BASELINE_CURRENT.md
  - owner semantic audit 2026-06-09
  - tracked code verification
---

# BRC Target Semantics

This document defines the target semantic chain for BRC and maps each node to
its current code status.

---

## 1. Target Principle

BRC authorization object should be:

```text
bounded StrategyRuntimeInstance
```

Not:

```text
single trade order
```

The Owner should authorize a strategy running within risk boundaries, not one
immediate trade.

---

## 2. Target Chain

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

---

## 3. Current Status by Node

| Node | Current Status | Current Code Reality | Target Meaning |
| ---- | -------------- | -------------------- | -------------- |
| StrategyFamily | metadata only | Strategy family classification exists as metadata / admission | Strategy identity and risk profile |
| StrategyFamilyVersion | metadata only | Strategy specification document; not bound to executable strategy code | Versioned executable strategy definition |
| AdmissionDecision | partially implemented | Admission gate metadata operations (Phase 1-17) complete | Formal admission pass/fail with evidence |
| OwnerRiskAcceptance | partially implemented | OwnerRiskAcknowledgement exists for single-use authorization | Owner acceptance of strategy runtime risk |
| TrialBinding | metadata only | Audit binding record; not a running strategy instance | Binding between admitted strategy and runtime instance |
| StrategyRuntimeInstance | missing | Does not exist in current code | Running bounded strategy instance that generates evaluations |
| SignalEvaluation | missing | SignalPipeline exists as legacy real-time signal system; not connected to BRC StrategyFamily | Per-instance signal evaluation within risk boundaries |
| OrderCandidate | readmodel only | CandidateAction is readmodel / preview / policy evaluation | Executable order candidate from signal evaluation |
| FinalGate | implemented | FinalGate exists as hard execution gate | Pre-execution safety validation |
| ExecutionIntent | partially implemented | Execution permission system has 5 levels; intent recording exists | Bounded execution intent from order candidate |
| OrderLifecycle | implemented | Order lifecycle service handles order placement and tracking | Order lifecycle management with strategy semantic IDs |
| Order / Position | implemented | Order and position management through exchange gateway | Live order and position tracking |
| Reconciliation | implemented | Reconciliation service exists | PG / exchange consistency verification |
| Review | partially implemented | Review Ledger design exists; limited production review data | Full review with strategy semantic traceability |

Status legend:

- **implemented**: exists in tracked code and functional
- **partially implemented**: exists but incomplete or scoped
- **metadata only**: data model exists but no runtime behavior
- **readmodel only**: read-only projection, not executable
- **legacy path**: exists but not connected to target chain
- **missing**: does not exist in current code
- **target only**: defined as goal but no code artifact

---

## 4. One-shot Execution Is Historical Short Path

OwnerBoundedExecutionService is a valuable one-shot execution asset:

- It implements Owner authorization -> FinalGate -> Entry -> TP/SL ->
  Order -> Reconciliation -> Review.
- It is not the final target BRC architecture.
- It may remain as legacy / manual / safe trial path until the strategy
  runtime path is built.
- It does not generate signals or order candidates from a running strategy
  instance.

---

## 5. Strategy Semantics

- **EntryPolicy / ExitPolicy** should belong to strategy semantics, not be
  ad-hoc per-trade decisions.
- **ProtectionPolicy** (TP/SL) is minimum safety protection, not the whole
  exit strategy.
- **StrategyContractV2** (EntryPolicy / StopPolicy / TakeProfitPolicy /
  LifecycleExitPolicy / StrategySignalV2) is a candidate asset for future
  strategy semantic contracts.
- **SignalPipeline** is a candidate signal evaluation engine, not the final
  BRC runtime by itself.
- **BudgetedAutonomy** has multiple attempted boundary models, but current
  code is metadata_only / action_allowed=False.

---

## 6. Review Semantics

Future Review should be able to trace the full semantic chain:

```text
StrategyFamilyVersion
TrialBinding
StrategyRuntimeInstance
SignalEvaluation
OrderCandidate
ExecutionIntent
Order
Review
```

Current Review Ledger does not carry strategy semantic IDs through the chain.
This is a known gap (see `docs/canon/TECH_DEBT_BASELINE.md`).
