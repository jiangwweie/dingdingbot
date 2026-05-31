# MI-001 BNB Small Live Trial Readiness Draft

Generated: 2026-05-31

Status:

- `draft_only`
- `not_authorized`
- `not_started`
- `requires_owner_final_approval`

## 1. Summary

This is a readiness draft for a possible future small live `MI-001 BNB long` trial. It is not live authorization and does not start trial, create execution intent, create order, grant execution permission, or start runtime.

## 2. Required Preconditions

- BNB live case #001 forward review completed or replaced by a later confirmation case.
- BNB-specific Operation Layer notional/loss cap exists.
- Fresh read-only account facts available.
- GKS non-blocking state confirmed.
- Runtime-owned startup guard readiness confirmed.
- BNB active position and open orders checked as zero.
- Reconciliation clean.
- Evidence/audit logging packet ready.
- Owner final small-live approval recorded separately.

## 3. Capital And Risk Boundary

| item | rule |
| --- | --- |
| capital source | dedicated Binance USDT futures account |
| trial risk capital | current dedicated account equity |
| max total loss | current dedicated account equity, unless Owner selects smaller cap |
| max leverage | `5x` |
| max notional | `min(equity * 5, available_margin * 5, BNB Operation Layer cap)` |
| max simultaneous position | `1` |
| max attempts draft | `3` |

## 4. Allowed Scope

- symbol: `BNB/USDT:USDT`
- side: `long`
- Owner manual confirmation required for each entry
- no automatic entry
- no add-to-loser
- no symbol expansion
- no side expansion
- no leverage expansion above 5x

## 5. Stop Conditions

- Owner manual stop.
- Operation Layer block.
- Global Kill Switch active/blocking.
- Startup guard not armed or runtime safety unclear.
- Account/order/position reconciliation mismatch.
- Active BNB position/open order already exists.
- No-chase / wait-for-confirmation gate fails.
- Time stop / max holding time reached.

## 6. Review Obligations

- Record preflight evidence.
- Record Owner final approval.
- Record entry/exit evidence if a future live trial is separately authorized.
- Review 1h / 4h / 12h / 24h / 72h path.
- Produce post-trial packet before any second attempt.

## 7. Non-permissions

- no trial start
- no live authorization
- no execution intent
- no order
- no runtime start
- no leverage change
- no transfer / withdrawal
