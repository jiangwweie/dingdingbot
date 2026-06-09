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

# BNB Second Tiny Live Trial Recovery Closeout - 2026-06-03

## Classification

This report closes the second real `MI-001-BNB-LONG` tiny live trial as a
protection-path failure plus bounded recovery milestone. It does not prove
strategy alpha, profitability, drawdown behavior, or durable edge.

## Authorized Scope

- Authorization id: `auth-291ded90949945f4b7251990b93c4bff`
- Carrier: `MI-001-BNB-LONG`
- Symbol: `BNB/USDT:USDT`
- Side: long
- Quantity: `0.01 BNB`
- Max notional: `20 USDT`
- Leverage: `1x`
- Protection: `single_tp_plus_sl`
- Mode: one-shot Owner-operated live trial with bounded recovery

## Exchange Facts

- Entry order id: `91080115011`
- Entry local order id: `f2b58504-c223-4dab-b5ea-fa24402efce7`
- Entry status: `FILLED`
- Entry filled quantity: `0.01 BNB`
- Entry average execution price: `643.54`

- TP local order id: `a54120e5-e0d8-4e3c-bd63-4478815162f6`
- TP status: `REJECTED`
- TP exchange order id: none

- SL local order id: `d88f40f1-033e-4247-ae5b-226d4667ad0c`
- SL status: `REJECTED`
- SL exchange order id: none

- Recovery close exchange order id: `91080406399`
- Recovery close local order id: `d5db2b79-9e24-422c-86f2-b93469aef867`
- Recovery close status: `FILLED`
- Recovery close filled quantity: `0.01 BNB`
- Recovery close average execution price: `643.79`
- Recovery close semantics:
  `authorized_recovery_close_hedge_mode_position_side_long_exact_size_after_tp_sl_reduceonly_reject`

Final live exchange read-only verification after recovery:

- BNB active position count: `0`
- BNB normal open order count: `0`
- BNB conditional open order count: `0`

## Protection Attach Failure

The trial reached:

`entry filled -> fill-based TP/SL plan persisted -> TP submit -> SL submit`

Both TP and SL were rejected by Binance with:

`-1106 Parameter 'reduceonly' sent when not required`

Root cause:

- The account is using Binance futures hedge-mode semantics.
- The protection payload included `positionSide=LONG`.
- The gateway also sent `reduceOnly=true`.
- Binance rejects `reduceOnly` when `positionSide` is supplied for this hedge-mode path.

Governance repair:

- Local reduce-only protection intent remains true.
- Exchange payload construction now omits the `reduceOnly` parameter for Binance
  when `positionSide` is present.
- Regression coverage proves ordinary reduce-only orders without `positionSide`
  still send `reduceOnly=true`.
- Regression coverage proves Binance hedge-mode protection orders send
  `positionSide=LONG` and omit exchange `reduceOnly`.

## PG Records

Execution intent:

- `intent-e7e7254d29ca4b4d8ce02ed538e8f69b`
- Final status: `failed`
- Failure reason:
  `protection_attach_rejected_binance_reduceonly_not_required_recovered_flat_by_authorized_close`

Order records:

- ENTRY `f2b58504-c223-4dab-b5ea-fa24402efce7`: exchange `91080115011`,
  `FILLED`, quantity `0.01`, average price `643.54`.
- TP `a54120e5-e0d8-4e3c-bd63-4478815162f6`: `REJECTED`.
- SL `d88f40f1-033e-4247-ae5b-226d4667ad0c`: `REJECTED`.
- EXIT `d5db2b79-9e24-422c-86f2-b93469aef867`: exchange `91080406399`,
  `FILLED`, quantity `0.01`, average price `643.79`.

Execution result/review:

- Operation id: `review-auth-291ded90949945f4b7251990b93c4bff-recovery-close`
- Outcome: `completed_with_recovery_flat`
- Final state snapshot: flat position, open orders zero, next trade requires
  fresh Owner authorization.

## Authorization Final State

- `consumed=true`
- `trial_final_state=completed_with_recovery_flat`
- `authorization_reuse_allowed=false`
- `next_trade_requires_new_owner_authorization=true`
- `next_executable=false`
- `live_ready=false`
- `order_permission_granted=false`
- `execution_permission_granted=false`
- `auto_execution_enabled=false`

## Closeout Outcome

Final outcome: `completed_with_recovery_flat`.

The second BNB tiny live trial is closed as a protection attach failure with
bounded recovery flat and an explicit hedge-mode protection payload repair.
