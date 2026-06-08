---
title: CURRENT_READINESS_BLOCKERS
status: CURRENT_CANON
authority: owner-correction + current-product-operating-model
last_verified: 2026-06-08
source_of_truth:
  - docs/ops/knowledge-pack/CURRENT_PRODUCT_OPERATING_MODEL.md
  - docs/ops/knowledge-pack/PROJECT_BASELINE_CURRENT.md
  - docs/ops/knowledge-pack/CURRENT_FACT_REGISTRY.md
  - docs/ops/trading-console-owner-action-flow-v1-deploy-governance-report-2026-06-07.md
  - docs/ops/mr-eth-review-ledger-budgeted-autonomy-v0-design-2026-06-08.md
---

# CURRENT_READINESS_BLOCKERS.md

This document tracks what blocks a new bounded live action or Owner operations
flow under the current productized BRC model.

It no longer frames the project as globally blocked on a pre-trial research
checklist. Older blocker names are preserved only when they still affect a
specific path.

---

## P0 Hard Blockers

### BLK-P0-01: Missing exact live-action authorization

- **What**: A new real live / real-funds action needs exact Owner authorization
  or an explicit `BudgetEnvelope` authorization.
- **Blocks**: Any live order, cancel, replace, flatten, retry protection, or
  other exchange write action.
- **Required clearance**: exact carrier/action, symbol, side, quantity or max
  notional, leverage, max attempts, protection requirement, review requirement,
  stop condition, and time/scope bounds.
- **Status**: Always hard-blocked until exact authorization exists for the
  action being attempted.

### BLK-P0-02: FinalGate blocked, stale, or unavailable

- **What**: `FinalGate` must pass for the exact action.
- **Blocks**: Official bounded live action.
- **Required clearance**: environment/account/symbol/side/quantity/notional/
  leverage, budget, attempts, active exposure, open orders, fresh account facts,
  fresh reconciliation, market rules, TP/SL plan, GKS/runtime guard, recording,
  and Operation Layer path all pass.
- **Status**: Hard blocker for execution; warnings remain warnings only when
  they do not affect live safety.

### BLK-P0-03: Exposure, protection, or reconciliation uncertainty

- **What**: New entry is blocked if PG/exchange exposure, open orders,
  protection, or reconciliation facts are stale, conflicting, or unknown.
- **Blocks**: New live entry and any action whose safety depends on those facts.
- **Required clearance**: fresh PG and exchange evidence; no conflicting active
  position or open order; active position protection is complete and known; PG
  and exchange agree or the disagreement is explicitly resolved.
- **Current note**: The MR/ETH Review Ledger note records protected-open ETH
  evidence with TP and SL present. While a position remains open, cleanup is not
  warranted, and any new action must pass fresh exposure/protection gates.

### BLK-P0-04: Operation Layer or FinalGate bypass

- **What**: Direct or custom per-strategy execution paths are forbidden.
- **Blocks**: Any action path outside `ActionSpec -> FinalGate -> Operation
  Layer -> official execute -> protection -> Review`.
- **Required clearance**: route the action through the official path and record
  audit/review evidence.

### BLK-P0-05: Environment, profile, credential, or runtime guard mismatch

- **What**: Any uncertainty in runtime profile, exchange account/subaccount,
  credential permissions, GKS, startup guard, or deployment/runtime version
  blocks live writes.
- **Blocks**: Live exchange writes and any action that can increase risk.
- **Required clearance**: fail-closed checks pass for the exact action scope.

---

## P1 Product / Architecture Blockers

### BLK-P1-01: Unsupported generic action bridge for a candidate

- **What**: Some candidates may be displayable or proposal-grade but not yet
  supported by the official action registry or generic `ActionSpec` bridge.
- **Blocks**: That candidate's execution path only.
- **Status**: Not a global product blocker. Render as unavailable/proposal with
  clear reason until the official bridge exists and `FinalGate` can evaluate it.

### BLK-P1-02: Recovery actions not fully productized

- **What**: Recovery visibility is product scope, but cancel/flatten/retry
  protection endpoints may not exist for every production scenario.
- **Blocks**: The specific recovery action in the console.
- **Required behavior**: show what is wrong, why it matters, whether new entry
  is blocked, what clears it, and whether Owner/system action exists. Do not
  show fake enabled buttons.

### BLK-P1-03: Budgeted Autonomy v0 is design-only

- **What**: Budgeted Autonomy v0 is a future authorization layer above
  `BudgetEnvelope` and below `FinalGate`.
- **Blocks**: Any no-confirmation or budgeted autonomous live execution.
- **Status**: Design-only until a separate Owner-approved implementation task
  enables an auditable official path.

### BLK-P1-04: 022-027 migrations not integrated

- **What**: 6 Alembic migrations and related research/domain/infra/app files
  remain untracked/not integrated.
- **Blocks**: Only paths that depend on those historical research tables or
  services.
- **Status**: Requires Owner decision if a current task needs them.

---

## P2 Review / Evidence Gaps

| Item | Current handling |
| --- | --- |
| Weak strategy evidence | Warning/risk disclosure after Owner acknowledgement, not a live-safety hard blocker by itself |
| Incomplete observation sample | Warning/risk disclosure unless it affects exact action safety |
| Missing fee/funding/slippage attribution | Show `not_available`; Review gap, not execution hard blocker by itself |
| Review analytics not sophisticated | Improve through Review Ledger; do not block product sprint on perfect attribution |
| UI/report incompleteness | Fix or record as acceptance gap; do not confuse with exchange safety blocker |

---

## Superseded Blanket Blockers

| Old blocker | Current status |
| --- | --- |
| old account-equity blanket blocker | Superseded. Account equity / wallet equity / available margin are available when cached AccountSnapshot exists; missing or stale facts remain preflight-specific blockers. |
| `3 trial candidates have no cost/baseline enrichment` | Superseded as global blocker. Enrichment completed for the initial broad-smoke candidates; outcomes are evidence/warnings and do not define current product readiness. |
| `signal-to-intent conversion not implemented` | Reframed. Uncontrolled generic signal-to-order remains unavailable, but official ActionCandidate/ActionSpec paths can proceed when implemented, scoped, authorized, and gated. |
| `blanket testnet authorization required` | Superseded. Testnet/dev/readiness/profile-scoped work proceeds via scoped verification and hard safety gates. |
| `production deployment unavailable` | Superseded. Tokyo Owner Console deployment exists with `runtime_bound=true` and `live_ready=false`; deployment is not generic live authorization. |

---

## Current Action Readiness Checklist

A new bounded live action requires all of these:

| # | Requirement | Status rule |
| --- | --- | --- |
| 1 | Exact Owner or BudgetEnvelope authorization | Required for the exact action |
| 2 | Official ActionCandidate / ActionSpec path | Required; no custom strategy execution |
| 3 | FinalGate pass | Required immediately before action |
| 4 | Fresh account and exposure facts | Required |
| 5 | No conflicting active position/open order unless explicitly in scope | Required |
| 6 | TP/SL or protection plan present for new live entry | Required |
| 7 | PG/exchange reconciliation acceptable | Required |
| 8 | GKS/startup guard/runtime profile/account checks pass | Required |
| 9 | Recording/audit/review path available | Required |
| 10 | Review Ledger requirement defined | Required |

If any required item is missing, the console should show the blocker and render
the action unavailable rather than hiding the reason or presenting a fake action.
