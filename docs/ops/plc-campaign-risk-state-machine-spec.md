> [!NOTE]
> **HISTORICAL_EVIDENCE** — This document is a historical operational, governance, sprint, product, or live-trial artifact from an earlier project phase.
>
> It may be useful for context, auditing, or traceability, but it does **not** represent current project state, constraints, product direction, or agent instructions.
>
> Current authoritative sources:
> - `docs/canon/PROJECT_BASELINE_CURRENT.md`
> - `docs/canon/BRC_TARGET_SEMANTICS.md`
> - `docs/canon/AGENT_WORKSPACE_RULES.md`
> - `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
> - `docs/canon/TECH_DEBT_BASELINE.md`
> - `docs/canon/DOCUMENT_GOVERNANCE.md`

# PLC Campaign Risk State Machine Spec

Date: 2026-05-25
Status: REVIEW

Runtime effect: application-layer campaign state validation hardened; no
runtime process started by this document

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

## PLC-STATE-001 Implementation Proof

`src/application/campaign_state_service.py` now exposes the campaign state
machine as a table-driven local core:

- `CampaignTransitionTrigger` names Owner and runtime triggers explicitly.
- `CampaignTransitionRule` records source state, target state, trigger,
  reason code, owner-review requirement, flat-proof requirement, and whether
  the path exists to allow risk-reducing close.
- `CampaignTransitionRecord` provides audit-ready transition records with
  sequence number, previous state, target/next state, trigger, reason,
  updated_by, active strategy/session ids, and context metadata.
- `replay_campaign_transitions(...)` replays a sequence deterministically and
  stops at the first invalid transition.

Accepted local proof path:

`observe --owner_arm--> armed --entry_filled--> armed --profit_protect_triggered--> profit_protect --position_closed--> closed --owner_review_reset--> observe`

Rejected local proof path:

`hard_locked --owner_arm--> armed`

Important semantic lock:

- `entry_filled` can confirm an already `armed` session, but it cannot move
  `observe` to `armed`; Owner arm remains the only accepted transition for
  arming a bounded campaign session.

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

## Verification

- `pytest -q tests/unit/test_p4_campaign_state_service.py` passed with 11
  tests on 2026-05-25.

No runtime start, exchange call, testnet order, migration, runtime profile
change, strategy parameter change, real live action, commit, or push was
performed for PLC-STATE-001.

## PLC-STATE-002 Durable Ledger

The campaign state machine now has a durable transition ledger:

- migration `011_create_runtime_campaign_state_transitions`;
- ORM table `runtime_campaign_state_transitions`;
- repository methods for append-only transition recording, state+transition
  transactional writes, and ordered ledger reads;
- rejected transitions are recorded with `accepted=false` and a rejection
  reason;
- successful transitions update `runtime_campaign_state` and append the ledger
  row in one repository transaction when the PG repository is available.

Replay proof:

- `CampaignStateService.build_replay_evidence()` reads the ledger, replays it
  from `observe`, and compares replay final state with the durable snapshot.
- `replay_campaign_transition_logs(...)` treats rejected transitions as audit
  facts that do not advance state.

## PLC-STATE-003 Runtime Event Wiring

The execution orchestrator now emits campaign runtime events from existing
runtime callbacks:

- ENTRY filled -> `entry_filled`;
- TP filled/progressed -> `profit_protect_triggered`;
- SL filled/progressed -> `stop_loss_filled`;
- position projection `just_closed=true` -> `position_closed`.

Campaign event write failures are logged and do not block protection mounting
or risk-reducing close handling. This preserves safety: close/protection paths
continue even if evidence recording has a local failure.

## PLC-STATE-004 Replay Evidence Packet

The internal runtime control surface now exposes read-only replay evidence:

`GET /api/runtime/control/campaign-state/replay-evidence`

The response includes:

- initial state;
- replay final state;
- current snapshot state;
- snapshot match flag;
- accepted flag;
- transition count;
- rejected transition count;
- transition records.

The endpoint does not place, cancel, close, resize, or mutate exchange orders.
It is designed for future bounded testnet rehearsal evidence collection.

## Non-Goals

- No real live trading.
- No automatic re-arm.
- No withdrawal instruction, amount, schedule, or automation.
- No LLM authority over state transitions.
