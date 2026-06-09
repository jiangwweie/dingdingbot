---
name: project-core-memory
description: BRC project identity, code reality, target semantics, agent reading rules
type: project
---

# Project Core Memory

Updated: 2026-06-09

## Current Project Identity

This project is a personal quant BRC / Owner-controlled bounded-live research
and execution system.

Current target semantics: BRC is strategy runtime governance.

Owner authorization should ultimately authorize a bounded
StrategyRuntimeInstance, not one immediate trade.

## Current Code Reality

- Current executable path is one-shot Owner authorization:
  OwnerRiskAcknowledgement -> AuthorizationDraft ->
  BoundedLiveTrialAuthorization -> FinalGate ->
  OwnerBoundedExecutionService -> Entry / TP / SL ->
  Order / Reconciliation / Review.
- BoundedLiveTrialAuthorization is single-use trade authorization.
- Current code does not yet implement StrategyRuntimeInstance.
- StrategyFamily / Admission exists as metadata / admission / evidence chain.
- TrialBinding is not yet a running strategy instance.
- CandidateAction and BudgetedAutonomy are readmodel / preview / policy
  evaluation unless code proves otherwise.
- SignalPipeline is legacy real-time signal system and candidate future
  SignalEvaluation engine.
- OwnerBoundedExecutionService is a valuable one-shot execution asset, not the
  final target architecture.

## Target Direction

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

## Agent Reading Rule

- Always read AGENTS.md / CLAUDE.md and docs/canon/ first.
- Do not use docs/archive, docs/ops historical files, docs/gpt,
  docs/product/v2, or quarantined agent instructions as current truth.
- If memory conflicts with docs/canon, docs/canon wins.

## Do Not Misread

- Do not treat one-shot OwnerBoundedExecution as final architecture.
- Do not treat TrialBinding as currently running strategy instance.
- Do not treat StrategyFamilyVersion as executable strategy code.
- Do not treat CandidateAction as executable.
- Do not treat BudgetedAutonomy as auto trading.
- Do not infer current state from old "盯盘狗 v3.0" documents.
