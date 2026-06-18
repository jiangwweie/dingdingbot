---
title: RUNTIME_REPLAY_LAB
status: CURRENT
authority: docs/current/RUNTIME_REPLAY_LAB.md
last_verified: 2026-06-18
---

# Runtime Replay Lab

## Purpose

The Runtime Replay Lab is the local-only rehearsal layer for the
StrategyGroup Runtime Pilot.

Its job is to reduce dependence on rare live market signals by replaying
historical or synthetic StrategyGroup signal windows through the same runtime
semantics that later feed the official live chain:

```text
signal shape
-> RequiredFacts readiness shape
-> candidate / authorization shape
-> action-time FinalGate dry-run shape
-> Operation Layer evidence-prep shape
-> non-executing post-submit / protection / reconciliation shape
-> review recommendation
```

Replay exists to make the real live path faster to debug and more profitable
to iterate. It is not an execution authority.

## Current Scope

| Item | Current scope |
| --- | --- |
| First StrategyGroup | `MPG-001` |
| Runtime source | local domain contract and local fixture files |
| Report runner | `scripts/run_strategygroup_runtime_replay_lab.py` |
| Dry-run integration | `scripts/runtime_dry_run_audit_chain.py` includes replay-lab validation |
| Output intent | local audit packet and Owner-readable local progress note |
| Server deployment | out of scope for the first P0.5 checkpoint |
| Real order | out of scope |
| Exchange write | out of scope |

## Contract

Replay events must remain explicitly separated from live market signals.

| Field class | Requirement |
| --- | --- |
| Identity | Every event carries `schema`, `strategy_group_id`, `event_id`, `source`, and `kind` |
| Market shape | Events may include symbol, side, signal confidence, fact readiness, and boundary checks |
| Runtime shape | Events may describe whether dry-run prepare, FinalGate dry-run, and Operation Layer evidence-prep shape are reached |
| Review shape | Events may recommend `promote`, `keep_observing`, `revise`, `park`, or `kill` |
| Safety flags | Events must say `replay_only=true`, `not_live_market_signal=true`, and `not_execution_authority=true` |

Forbidden fields are rejected by the domain contract:

```text
exchange_write_allowed
real_order_allowed
real_submit_allowed
credential_mutation_allowed
withdrawal_allowed
transfer_allowed
live_profile_mutation_allowed
order_sizing_default_mutation_allowed
operation_layer_submit_allowed
```

These fields must remain false whenever present.

## Synthetic Fixture Set

The first local fixture set covers the minimum useful branches for the
bounded-aggressive live pilot:

| Case | Purpose |
| --- | --- |
| `no_signal` | Proves waiting state does not create candidate/auth/Operation Layer shape |
| `fresh_signal_pass` | Proves the happy path can reach non-executing prepare evidence shape |
| `stale_signal` | Proves freshness TTL still rejects expired signals |
| `missing_required_facts` | Proves missing facts stop before Operation Layer shape |
| `active_position_conflict` | Proves active exposure conflict blocks the path |
| `open_order_conflict` | Proves open-order conflict blocks the path |
| `protection_missing` | Proves missing protection blocks the path |
| `allocated_profile_boundary_mismatch` | Proves wrong profile/symbol/side/leverage boundary blocks the path |

## External Framework Policy

External replay frameworks such as Freqtrade may be useful later as sidecar
research adapters. They may produce:

```text
external_backtest_summary
signal_windows
entry_exit_samples
metric_summary
parameter_sensitivity
```

They must not provide:

```text
FinalGate authority
Operation Layer authority
real-submit permission
Owner state
live signal identity
```

The main runtime remains the authority for candidate/auth, FinalGate,
Operation Layer, protection, reconciliation, settlement, and review.

## Current Artifacts

| Artifact | Path |
| --- | --- |
| Domain contract | `src/domain/strategygroup_runtime_replay.py` |
| Local runner | `scripts/run_strategygroup_runtime_replay_lab.py` |
| Dry-run audit integration | `scripts/runtime_dry_run_audit_chain.py` |
| MPG replay sample | `docs/current/strategy-group-handoffs/MPG-001/replay/mpg-001-replay-sample.json` |
| MPG synthetic fixtures | `docs/current/strategy-group-handoffs/MPG-001/replay/synthetic-signal-fixtures.json` |
| Unit tests | `tests/unit/test_strategygroup_runtime_replay_lab.py` |
| Dry-run audit tests | `tests/unit/test_runtime_dry_run_audit_chain.py` |

## Acceptance

The current P0.5 checkpoint is accepted when:

1. `MPG-001` replay sample validates locally.
2. The synthetic fixture set covers no-signal, fresh-pass, stale, missing-fact,
   conflict, protection-missing, and profile-boundary branches.
3. Runtime dry-run audit exposes replay-lab checks in the unified packet.
4. All replay and dry-run paths prove:

```text
no Tokyo deploy
no FinalGate live call
no Operation Layer live submit
no exchange write
no real order
no withdrawal
no transfer
no secret or credential mutation
no live profile mutation
no order-sizing default mutation
```

## Next Expansion

The next useful expansion is not testnet. The next useful expansion is a
larger local replay corpus:

| Expansion | Why it matters |
| --- | --- |
| More MPG historical windows | Better entry/exit review before live signals arrive |
| Cost, slippage, and funding annotations | Better estimate of whether gross edge can survive execution friction |
| Cross-StrategyGroup replay after first live loop | Avoid expanding strategy count before the shared live path proves itself |
| Post-submit simulator linkage | Exercise fill, partial fill, reject, protection failure, recovery, reconciliation, and settlement branches |
