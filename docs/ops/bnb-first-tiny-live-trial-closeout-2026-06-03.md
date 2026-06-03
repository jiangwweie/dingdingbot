# BNB First Tiny Live Trial Closeout - 2026-06-03

## Classification

This report closes the first real `MI-001-BNB-LONG` tiny live trial as an
execution-chain validation milestone. It does not prove strategy alpha,
profitability, drawdown behavior, or durable edge.

## Authorized Scope

- Authorization id: `auth-22c721595385495daf4457d06c4217ad`
- Carrier: `MI-001-BNB-LONG`
- Symbol: `BNB/USDT:USDT`
- Side: long
- Quantity: `0.01 BNB`
- Max notional: `20 USDT`
- Leverage: `1x`
- Protection: `single_tp_plus_sl`
- Mode: one-shot Owner-operated live trial

## Exchange Facts

- Entry order id: `91073270232`
- Entry local order id: `afc3ca42-835c-4878-ad89-5166085b24fd`
- Entry status: `FILLED`
- Entry filled quantity: `0.01 BNB`
- Entry average execution price: `642.81`

- Recovery close exchange order id: `91074094150`
- Recovery close local order id: `5b694d4c-816b-41af-81e9-ebebdccf61ac`
- Recovery close status: `FILLED`
- Recovery close filled quantity: `0.01 BNB`
- Recovery close average execution price: `644.27`

Final live exchange read-only verification after recovery:

- BNB active position count: `0`
- BNB normal open order count: `0`
- BNB conditional open order count: `0`

## Protection Attach Failure

The trial reached the phase:

`entry filled -> fill-based TP/SL plan created -> intent transition to PROTECTING`

The chain then failed before TP/SL order submission because
`PgExecutionIntentRepository.update()` was missing. This caused the protection
attach path to crash before `submit_take_profit` and `submit_stop_loss`.

No TP order and no SL order were created for this trial. The filled entry was
later recovered by an Owner-authorized bounded close.

## PG Records

Execution intents for this authorization:

- `intent-b053c8a8fdbf445da23da1e731b10a57`: `failed`, pre-order reject, no order id.
- `intent-e9acc0b6ca974bcb9355f43ea4906bac`: `failed`, pre-order reject, no order id.
- `intent-2149af97bcb9496696c7133d0a60e941`: `failed`, linked to entry order
  `afc3ca42-835c-4878-ad89-5166085b24fd` and exchange order `91073270232`.

Order records:

- ENTRY `afc3ca42-835c-4878-ad89-5166085b24fd`: exchange `91073270232`,
  `FILLED`, quantity `0.01`, average price `642.81`.
- EXIT `5b694d4c-816b-41af-81e9-ebebdccf61ac`: exchange `91074094150`,
  `FILLED`, quantity `0.01`, average price `644.27`,
  exit reason `authorized_recovery_close_hedge_mode_position_side_long_exact_size`.

Protection price plans:

- Pre-entry reference plan: reference `644.56`, TP `651.00`, SL `638.11`.
- Post-entry fill plan: fill `642.81`, TP `649.23`, SL `636.38`.

Execution result/review:

- Operation id: `review-auth-22c721595385495daf4457d06c4217ad-recovery-close`
- Status: `failed`
- Outcome: `completed_with_recovery_flat`
- Failure reason:
  `original_execution_chain_failed_before_protection_attach_recovered_by_authorized_close`

## Authorization Final State

- `consumed=true`
- `trial_final_state=completed_with_recovery_flat`
- `authorization_reuse_allowed=false`
- `next_trade_requires_new_owner_authorization=true`
- `next_executable=false`
- `live_ready=false`
- `order_permission_granted=false`
- `execution_permission_granted=false`
- `execution_intent_created=false`
- `order_created=false`
- `auto_execution_enabled=false`

## Validated

- Owner Web authorization can drive a real bounded live execution attempt.
- Final hard gate and scoped runtime safety can allow one bounded trial.
- Entry order path reached Binance and filled the exact authorized BNB size.
- PG can record entry order and recovery close facts.
- Live read-only exchange verification can confirm flat position and zero open orders.
- A consumed authorization can be closed so the next trade requires fresh Owner authorization.

## Not Validated

- Ideal TP/SL attach success path was not validated live.
- TP order acceptance, SL order acceptance, and exchange-side protection lifecycle were not validated live.
- OCO-style mutual exclusion, protection monitoring, and normal TP/SL exit review were not validated live.
- Strategy alpha was not validated.
- Long-run regime fit, drawdown, or repeatability were not validated.

## Closeout Outcome

Final outcome: `completed_with_recovery_flat`.

The first BNB tiny live trial is closed as an execution-chain validation
milestone with explicit protection-path failure and bounded recovery recorded.
