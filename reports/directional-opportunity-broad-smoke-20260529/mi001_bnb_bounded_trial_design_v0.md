# MI-001 BNB Bounded Trial Design v0

Generated: 2026-05-31 15:13 CST

Status:

- `design_only`
- `not_trial_ready`
- `not_execution_ready`

## 1. Summary

This is a bounded trial design draft for `MI-001 BNB/USDT:USDT long`. It is prepared because live read-only observation produced a BNB `would_enter` case, but it does not authorize trial start, execution intent creation, order placement, runtime start, or execution permission.

## 2. Trial Design Boundary

| field | value |
| --- | --- |
| strategy | `MI-001 BNB long` |
| symbol | `BNB/USDT:USDT` |
| side | `long` |
| mode | Owner confirms each entry |
| trigger source | live read-only observation signal |
| signal handling | `would_enter` -> Owner review, not order |
| capital model | dedicated subaccount equity |
| max leverage | `5x` |
| max simultaneous position | `1` |
| max attempts draft | `3` |
| max holding time draft | `72h` primary review, `7d` outer review |
| status | design-only, not trial-ready |

## 3. Risk Rules

| rule | value |
| --- | --- |
| no auto top-up | true |
| no transfer | true |
| no withdrawal | true |
| no symbol expansion | true |
| no side expansion | true |
| no leverage expansion above 5x | true |
| no add-to-loser | true |
| max_total_loss_rule | current dedicated subaccount equity |
| max_notional_rule | `min(equity * 5, available_margin * 5, Operation Layer cap if exists)` |

## 4. Entry Handling Draft

1. Observation runner records `would_enter`.
2. Owner reviews the signal case and current account/safety facts.
3. If Owner wants a rehearsal/trial, a separate explicit readiness task must create BNB-specific trial metadata.
4. No code path may convert the observation signal into an execution intent automatically.

## 5. Exit Draft

| exit type | draft behavior |
| --- | --- |
| time stop | review at 72h; force manual Owner decision by 7d |
| manual stop | Owner can stop outside this design draft |
| Operation Layer stop | any Operation Layer block overrides trial design |
| invalidation stop | sharp reversal / momentum exhaustion / excessive adverse path |

## 6. Review Windows

- `1h`
- `4h`
- `12h`
- `24h`
- `72h`
- `7d`

## 7. Required Before Any Trial Readiness Claim

- BNB-specific PG admission / trial registration.
- BNB-specific Operation Layer notional cap and loss cap metadata.
- Current account facts refresh.
- GKS and startup guard readiness facts.
- Active BNB position/order check.
- Owner final manual authorization for the BNB candidate.

## 8. Non-permissions

- no trial start
- no execution intent
- no order
- no runtime start
- no execution permission
- no order permission
- no leverage change
- no transfer or withdrawal
