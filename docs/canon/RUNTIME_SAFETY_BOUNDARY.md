---
title: RUNTIME_SAFETY_BOUNDARY
status: CURRENT_CANON
authority: owner-instruction + code-verification + ADR-0009 + ADR-0012
last_verified: 2026-06-09
source_of_truth:
  - docs/adr/0009-non-real-live-execution-authorization-boundary.md
  - docs/adr/0012-bounded-risk-campaign-system.md
  - docs/ops/knowledge-pack/CURRENT_FACT_REGISTRY.md
  - docs/canon/PROJECT_BASELINE_CURRENT.md
---

# Runtime Safety Boundary

This document defines the runtime safety boundaries for the BRC project.

---

## 1. Current Safety Principle

- Current code can reach the exchange order path through OwnerBoundedExecutionService.
- All execution work must respect Owner authorization and FinalGate.
- Documentation work must not run the project or call the exchange.
- Real live trading / real-funds order placement requires separate explicit
  Owner authorization for each action.

---

## 2. Execution Paths

| Path | Current Meaning | Status |
| ---- | --------------- | ------ |
| SignalPipeline -> ExecutionOrchestrator | Legacy real-time signal path | Legacy path; not connected to BRC StrategyFamily chain |
| OwnerTrialFlow -> OwnerBoundedExecution | One-shot Owner-authorized trade execution | Active; current primary execution path |
| Dev/test controlled paths | Testnet rehearsal and controlled testing | Active for scoped verification; no real funds |
| Scripts direct exchange paths | Research / admin scripts | Not integrated; untracked |
| Readmodel / preview paths | CandidateAction, BudgetedAutonomy, policy evaluation | Read-only; not executable |

---

## 3. Hard Red Lines

The following are prohibited unless Owner explicitly authorizes a specific task:

- Order placement (any exchange write)
- Order cancel / close / replace
- Exchange connection for live operations
- Database mutation (beyond what task card allows)
- Runtime server start
- Script execution against exchange
- Secret output (API keys, tokens, credentials, private keys, DB URLs)
- Withdrawal or transfer
- Strategy self-elevation
- Operation Layer bypass
- FinalGate bypass
- Unscoped symbol / side / leverage / notional expansion

---

## 4. Readmodel / Metadata / Execution Distinction

| Component | Classification | Basis |
| --------- | -------------- | ----- |
| CandidateAction | readmodel | No executable path in tracked code; display and policy evaluation only |
| BudgetedAutonomy | readmodel / design-only | `auto_within_budget_enabled=False`, `auto_execution_enabled=False` (hardcoded) |
| Operation Layer metadata steps | metadata | Not runtime execution unless code creates an executable object |
| TrialTradeIntent | non-executable evidence | Evidence record, not an execution trigger |
| StrategyFamilyVersion | metadata | Strategy specification document; not bound to executable code |
| AdmissionDecision | metadata | Classification and evidence; not an execution gate |

If code changes create executable paths for any of these, reclassify them.

---

## 5. FinalGate Meaning

- FinalGate is required before any execution.
- FinalGate preview / dry-run is not execution.
- Passing FinalGate does not automatically place orders; the Operation Layer
  must route the action.
- FinalGate should verify: Owner authorization, environment, account,
  symbol, side, quantity, leverage, budget, attempts, active exposure,
  open orders, fresh account facts, reconciliation, market rules,
  protection plan, GKS/runtime guard state, and Operation Layer path.
- Strategy evidence weakness is a warning, not a FinalGate hard blocker,
  after Owner acknowledgement.

---

## 6. Agent Documentation Safety

When doing documentation / analysis work:

- Do not run the project, tests, or scripts.
- Do not connect to exchange, database, Redis, WebSocket, or external services.
- Do not output any secrets or secret-adjacent information.
- Use only read-only commands (ls, find, grep, cat, git status, git diff).
- Changes must be limited to explicitly allowed files in the task card.
