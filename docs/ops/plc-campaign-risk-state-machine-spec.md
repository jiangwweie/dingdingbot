# PLC Campaign Risk State Machine Spec

Date: 2026-05-25
Status: DESIGN_REVIEW

Runtime effect: none

Trading permission effect: none

## Purpose

Define the minimum campaign risk state machine required before PLC Phase 3
testnet rehearsal. This is a design constraint, not runtime execution
authorization.

## States

| State | Meaning | Entry Trigger | Allowed Next States |
| --- | --- | --- | --- |
| `observe` | No armed campaign session. Review packets may be produced. | Default; owner reject; session expires. | `armed`, `paused` |
| `armed` | Owner has authorized one bounded session. | Matching `HumanArmDecision=arm`. | `paused`, `profit_protect`, `loss_locked`, `hard_locked`, `closed` |
| `paused` | No new intent may become an order plan. Existing risk-reducing close may continue. | Owner pause; failed review; soft operator stop. | `observe`, `armed`, `hard_locked` |
| `profit_protect` | Profit threshold reached; reduce/close requirement is active. | `total_pnl >= profit_protect_threshold`. | `closed`, `paused`, `hard_locked` |
| `loss_locked` | Campaign loss cap reached; no new entry allowed. | `total_pnl <= -max_campaign_loss`. | `hard_locked`, `closed` |
| `hard_locked` | Safety invariant breach; no new entry or re-arm. | Missing protection, failed reconciliation, account/liquidation critical, manual hard lock. | `closed` only after review |
| `closed` | Campaign session ended and no active position remains. | Runtime-managed close and reconciliation prove flat. | `observe` after owner review |

## Transition Rules

1. `observe -> armed` requires Owner arm, matching strategy contract id, session
   window, and frozen contract.
2. `armed -> profit_protect` requires a position lifecycle state with
   `reduce_or_close_required=true`.
3. `armed -> loss_locked` requires campaign loss cap breach.
4. Any state -> `hard_locked` on missing protection, account critical,
   liquidation critical, unresolved severe reconciliation, or manual hard lock.
5. `hard_locked` cannot return to `armed` directly.
6. `closed -> observe` requires no active position, no open exchange orders,
   no severe reconciliation mismatch, and Owner review.

## Phase 3 Enforcement

For PLC Phase 3, this state machine is used as an acceptance boundary:

- controlled entry may only run when campaign state is equivalent to `armed`;
- controlled close must be allowed in `armed`, `profit_protect`, `loss_locked`,
  or `hard_locked` because it is risk-reducing;
- after close, reconciliation must support `closed`;
- any invariant breach stops the rehearsal and preserves evidence.

## Required Evidence

- Campaign state before controlled entry.
- Campaign state before controlled close.
- Trigger reason for any transition.
- Final state after reconciliation.
- Operator/Owner review note if moving from `closed` back to `observe`.

## Non-Goals

- No real live trading.
- No automatic re-arm.
- No withdrawal instruction, amount, schedule, or automation.
- No LLM authority over state transitions.
