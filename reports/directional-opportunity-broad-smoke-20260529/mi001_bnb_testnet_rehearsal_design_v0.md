# MI-001 BNB Owner-confirmed Testnet Rehearsal Design v0

Generated: 2026-05-31

Status:

- `design_only`
- `not_started`
- `not_live_authorized`
- `not_execution_ready`

## 1. Summary

This design describes what a future Owner-confirmed `MI-001 BNB long` testnet rehearsal would need. It does not start a rehearsal, create an execution intent, create an order, grant execution permission, or authorize live trading.

## 2. Trigger And Mode

| field | value |
| --- | --- |
| strategy | `MI-001 BNB long` |
| symbol | `BNB/USDT:USDT` |
| side | `long` |
| trigger | BNB live observation `would_enter` plus Owner review |
| mode | Owner confirms each entry |
| signal handling | `would_enter -> Owner review`, not order |
| environment | Binance USDT futures testnet only, if separately authorized |
| current status | design only |

## 3. Allowed Testnet Scope

- BNB/USDT:USDT only.
- Long side only.
- Owner-confirmed entry only.
- Test order path may be exercised only in a separate testnet rehearsal task.
- No live account impact.
- No live authorization.

## 4. Risk Controls

- max leverage: `5x`
- max attempts draft: `3`
- max simultaneous position: `1`
- no add-to-loser
- no auto top-up
- no transfer
- no withdrawal
- no symbol expansion
- no side expansion
- no leverage expansion above 5x
- BNB-specific Operation Layer cap required before rehearsal

## 5. Exit / Stop Draft

- time stop
- manual Owner stop
- Operation Layer stop
- invalidation stop
- no-chase invalidation after adverse early path
- wait-for-confirmation before any rehearsal entry candidate

## 6. Recordkeeping Requirements

The rehearsal packet must record:

- Owner confirmation record
- testnet order id
- fill / reject
- position state
- PnL
- stop / exit event
- Operation Layer preflight/audit refs
- post-rehearsal review note

## 7. Current Blockers

- BNB-specific Operation Layer cap missing.
- Fresh account facts and BNB active position/order check required.
- GKS and startup guard state must be rechecked.
- Reconciliation precheck required.
- 12h / 24h / 72h BNB case #001 forward reviews remain pending.
- Owner testnet rehearsal authorization missing.

## 8. Non-permissions

- no trial start
- no live authorization
- no execution intent in this task
- no order in this task
- no runtime start in this task
- no leverage change
- no transfer / withdrawal
