# ADR 0014: StrategyRuntimeInstance Backbone Shadow Path

Date: 2026-06-09

Status: Accepted for TD-1 implementation

## Context

BRC is converging from one-shot Owner authorization toward strategy runtime
governance. Current executable code remains the one-shot path:

```text
OwnerRiskAcknowledgement
-> AuthorizationDraft
-> BoundedLiveTrialAuthorization
-> FinalGate
-> OwnerBoundedExecutionService
-> Entry / TP / SL
-> Order / Reconciliation / Review
```

The target chain introduces a bounded `StrategyRuntimeInstance` between
`TrialBinding` and future `SignalEvaluation` / `OrderCandidate` semantics.
Current code does not yet implement that runtime instance.

## Decision

Add `StrategyRuntimeInstance` as an additive shadow-path backbone.

`StrategyRuntimeInstance` is:

- a persisted bounded runtime governance record;
- derived from an admission / trial-binding context;
- linked to `StrategyFamilyVersion`, optional `OwnerRiskAcceptance`, and
  optional current carrier bridge data;
- governed by lifecycle status and explicit risk boundary fields;
- inspectable by Owner-facing readmodel / API surfaces.

`StrategyRuntimeInstance` is not:

- an execution permission;
- an order candidate;
- an execution intent;
- a FinalGate result;
- an order, position, or exchange command;
- proof that `StrategyFamilyVersion` is executable strategy code;
- a replacement for one-shot `BoundedLiveTrialAuthorization`.

This sprint is shadow-path only because the audit ID spine,
`SignalEvaluation`, `OrderCandidate`, runtime-aware FinalGate, and controlled
runtime execution path do not exist yet.

## Relationships

- `StrategyFamily`: strategy identity and risk lineage. Runtime instances refer
  to a family through the version record.
- `StrategyFamilyVersion`: version-pinned strategy specification metadata.
  This ADR does not make it executable strategy code.
- `AdmissionDecision`: source decision that admitted the strategy context.
- `OwnerRiskAcceptance`: optional Owner risk acceptance source. The runtime
  records the acceptance ID when present but does not create new acceptance.
- `AdmissionTrialBinding`: source binding evidence. It remains metadata /
  audit binding and is not itself the running runtime instance.
- `TrialTradeIntent`: non-executable evidence. Runtime creation does not turn
  trial trade intents into orders.
- `BoundedLiveTrialAuthorization`: remains single-use trade authorization for
  the existing one-shot path.
- `BudgetedAutonomyAuthorization`: remains preview / policy evaluation unless
  future tracked code promotes it through an official execution path.
- `StrategySignalV2`: future candidate signal contract input. This ADR does
  not route it into execution.
- `SignalPipeline`: legacy real-time signal system and possible future
  SignalEvaluation engine input. This ADR does not connect it to runtime
  execution.
- `ExecutionIntent`: not created by runtime activation in TD-1.
- `Order`: not created or mutated by runtime activation in TD-1.
- `Review`: future review should trace runtime IDs after the audit ID spine is
  implemented.

## Consequences

- One-shot `OwnerBoundedExecutionService` remains intact.
- `BoundedLiveTrialAuthorization` remains intact and single-use.
- Runtime activation is only a status transition.
- No exchange gateway, FinalGate execution, ExecutionIntent creation, or order
  placement is introduced by this ADR.
- Existing execution/order/review records are not required to have runtime IDs.

## Future Phases

1. Audit ID spine: nullable runtime semantic IDs across execution, order,
   reconciliation, and review surfaces.
2. `SignalEvaluation`: per-runtime shadow signal evaluation.
3. `OrderCandidate`: runtime-owned executable-candidate semantics, initially
   shadow-only.
4. Runtime-aware FinalGate: add runtime boundary checks without weakening the
   existing gate.
5. Controlled runtime execution: Owner-gated runtime candidate conversion into
   ExecutionIntent through the official path.
