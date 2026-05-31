# MI-001 BNB Bounded Trial Design v0

Generated: 2026-05-31 16:25 CST

Status:

- `design_only`
- `not_trial_ready`
- `not_execution_ready`

## 1. Summary

This is a bounded trial design draft for `MI-001 BNB/USDT:USDT long`. It is prepared because live read-only observation produced a BNB `would_enter` case, but it does not authorize trial start, execution intent creation, order placement, runtime start, or execution permission.

Continuation update: BNB live case #001 has completed 1h and 4h forward reviews showing adverse early path. The 1h result was `-0.7593%` return, `0.3121%` MFE, `-1.1483%` MAE. The 4h result extended the adverse path with `-2.7020%` return, `0.3121%` MFE, `-3.1289%` MAE. This does not invalidate MI-001 BNB, but it strengthens local-exhaustion handling in the design draft.

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
| no-chase after adverse 1h path | true |
| no-chase after adverse 4h continuation | true |
| wait-for-confirmation before any future rehearsal consideration | true |
| max_total_loss_rule | current dedicated subaccount equity |
| max_notional_rule | `min(equity * 5, available_margin * 5, Operation Layer cap if exists)` |

## 4. Entry Handling Draft

1. Observation runner records `would_enter`.
2. Owner reviews the signal case, current account/safety facts, and forward review table.
3. If the first 1h path is adverse or MFE is thin, the case is tagged `local_exhaustion_watch`; no chase entry is allowed in design.
4. If the 4h path remains adverse, the case is tagged `adverse_continuation_watch`; a later 12h/24h recovery is required before any future rehearsal design step.
5. A future rehearsal design update should require confirmation, such as a later closed bar recovering above the signal close or a 12h/24h follow-through review.
6. If Owner wants a rehearsal/trial, a separate explicit readiness task must create BNB-specific trial metadata.
7. No code path may convert the observation signal into an execution intent automatically.

## 4.1 No-chase / Wait-for-confirmation Rules

| rule | status | rationale |
| --- | --- | --- |
| no-chase rule | added | BNB case #001 had adverse 1h and 4h returns after the impulse; do not chase the initial `would_enter` event. |
| wait-for-confirmation rule | added | A later 12h/24h follow-through or recovery above signal close should be reviewed before any future rehearsal design step. |
| local exhaustion handling | strengthened | A sharp 12h impulse followed by weak MFE and negative 1h/4h returns is treated as exhaustion risk, not as entry permission. |
| adverse-continuation handling | added | The 4h path extended the 1h adverse move, so the case remains observation-only pending later recovery evidence. |
| would_enter remains non-executable | unchanged | `would_enter` is still an observation signal only. |

## 5. Exit Draft

| exit type | draft behavior |
| --- | --- |
| time stop | review at 72h; force manual Owner decision by 7d |
| manual stop | Owner can stop outside this design draft |
| Operation Layer stop | any Operation Layer block overrides trial design |
| invalidation stop | sharp reversal / momentum exhaustion / excessive adverse path |
| no-chase invalidation | adverse early path without 12h/24h recovery keeps the case in observation-only state |

## 6. Review Windows

- `1h`
- `4h`
- `12h`
- `24h`
- `72h`
- `7d`

Current case #001 review state:

| window | status | interpretation |
| --- | --- | --- |
| 1h | completed adverse | strengthens local exhaustion risk tag |
| 4h | completed adverse | extends local exhaustion risk into adverse-continuation watch |
| 12h | pending | confirmation/recovery check |
| 24h | pending | early continuation check |
| 72h | pending | primary design review window |

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
