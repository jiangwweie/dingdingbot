# BNB Trial Readiness Gap Check

Generated: 2026-05-31 15:13 CST

Scope: `MI-001 BNB/USDT:USDT long` readiness gap check.

This is a read-only gap check only. It does not start trial, create execution intents, create or cancel orders, grant execution permission, start runtime, or modify exchange/account state.

## 1. Summary

BNB now has live read-only observation evidence and a bounded trial design draft, but it is not trial-ready. The current state supports Owner review and continued observation only.

## 2. Gap Table

| item | status | source | blocker | notes |
| --- | --- | --- | --- | --- |
| account facts readable | available | existing Binance USDT futures read-only account facts path | no for review | Last verified in SOL readiness chain; BNB trial would need a fresh candidate-specific read before readiness. |
| Operation Layer cap | missing for BNB | repo/report search | yes | SOL cap exists; no BNB-specific cap/admission constraint is installed. |
| GKS | active=False | PG `global_kill_switch_state` | no for review | `active=False`; this does not grant execution permission. |
| startup guard | runtime-coupled blocker | startup guard reports/code | yes | Guard is process-local runtime-owned; no actual runtime guard is armed here. |
| execution permission | not order-capable | resolver config / task boundary | yes | Configured max observed as `intent_recording`, but this task grants no execution intent or order permission. |
| order path | frozen | task boundary + no order writes | yes for trial | No BNB order path enabled. |
| active BNB position | `0` | PG read-only repository check | no | No active BNB position found. |
| open BNB orders | `0` | PG read-only repository check | no | No open BNB orders found. |
| observation history | durable PG | `brc_strategy_group_observations` | no for review | BNB has live `would_enter` and latest `no_action` rows. |
| Owner BNB trial approval | missing | current artifacts | yes | Existing Owner metadata approval is for MI-001 SOL readiness, not BNB trial. |

## 3. What Blocks Testnet Owner-confirmed Rehearsal

- BNB-specific trial/admission metadata is not registered.
- BNB-specific Operation Layer cap is missing.
- Startup guard remains runtime-coupled.
- Rehearsal command path is not part of this task and must remain separate from observation.
- Owner must explicitly authorize any rehearsal step.

## 4. What Blocks Small Live Trial

- All testnet/rehearsal gaps above.
- Fresh account facts specific to the live trial moment.
- BNB-specific Owner final trial-start authorization.
- Confirmed Operation Layer cap and loss cap for BNB.
- Runtime-owned startup guard readiness action.
- Manual entry flow that preserves Owner-confirm-each-entry and does not auto-convert observation signals.

## 5. Current Allowed State

- live read-only public-market observation
- PG observation evidence persistence
- Owner review of BNB case #001
- bounded trial design drafting

## 6. Non-permissions

- no trial start
- no execution intent
- no order
- no execution permission
- no order permission
- no runtime start
- no automatic trading
