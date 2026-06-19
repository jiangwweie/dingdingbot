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
| First StrategyGroup | `MPG-001` remains the L4 live-order replay baseline |
| L2 observation expansion | `BTPC-001` has a shadow replay corpus for no-action / would-enter diagnostics |
| L1 observation expansion | `VCB-001` has an observe-only replay corpus for volatility-compression no-action / would-enter diagnostics; `LSR-001` has an observe-only replay corpus for liquidity-sweep and rewrite-gap diagnostics; `BRF-001` has an observe-only replay corpus for bear-rally-failure diagnostics |
| Runtime source | local domain contract and local fixture files |
| Report runner | `scripts/run_strategygroup_runtime_replay_lab.py` |
| Dry-run integration | `scripts/runtime_dry_run_audit_chain.py` includes replay-lab validation |
| Output intent | local audit packet and Owner-readable local progress note |
| Replay corpus | `MPG-001` has eight local replay windows; `BTPC-001` has five L2 shadow replay windows; `VCB-001`, `LSR-001`, and `BRF-001` each have five L1 observe-only replay windows |
| Post-submit simulator | local matrix covers accepted, failed-protection, partial-fill, reject, closed, and still-open shapes |
| Cost review | fee, slippage, funding, min-qty/step-size, and net-edge note fields are review inputs only |
| Server deployment | out of scope for the P0.5 replay/simulator checkpoint |
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

## MPG-001 Replay Corpus

The current local corpus covers eight window shapes:

| Case | Purpose |
| --- | --- |
| `trend_continuation` | Exercises the target right-tail continuation path |
| `false_breakout` | Keeps execution shape valid while review downgrades signal quality |
| `fast_reversal` | Exercises fast exit and review downgrade behavior |
| `choppy_no_trade` | Proves noisy regimes stay quiet and do not generate candidate/auth |
| `stale_signal` | Proves freshness rejection before submit authority |
| `missing_facts` | Proves RequiredFacts stop the path before execution-cost authority matters |
| `active_position_conflict` | Proves duplicate exposure is blocked |
| `protection_missing` | Proves missing protection remains a mechanical hard stop |

Every replay window carries a cost-review skeleton:

```text
fee_estimate_usdt
slippage_estimate_usdt
funding_impact_usdt
min_qty_step_size_impact
net_edge_note
not_submit_authority=true
```

These fields support review and profitability iteration. They do not authorize
submit.

## BTPC-001 L2 Shadow Replay Corpus

`BTPC-001` is not an L4 real-order StrategyGroup. Its replay corpus exists to
make broader opportunity discovery visible while the first bounded live-order
closure still waits on `MPG-001`.

The current local corpus covers five L2 shadow windows:

| Case | Purpose |
| --- | --- |
| `bear_pullback_would_enter` | Shows a short-side would-enter observation that may reach L2 review shape |
| `no_signal_bear_trend_not_ready` | Proves the strategy can stay visible without producing a candidate |
| `strong_uptrend_conflict` | Proves the short-side disable classifier blocks review promotion |
| `missing_derivatives_context` | Proves missing derivatives facts block L2 shadow evidence |
| `stale_signal` | Proves freshness rejection before promotion review |

The would-enter case may reach local prepare/review shape, but it must not reach
FinalGate, Operation Layer, exchange write, or real order authority.

## VCB-001 L1 Observe Replay Corpus

`VCB-001` remains an `L1 observe_only` StrategyGroup. Its replay corpus exists
to make volatility-compression breakout opportunities visible while classifier
quality, false-breakout disable state, and RequiredFacts shape remain under
review.

The current local corpus covers five L1 observe-only windows:

| Case | Purpose |
| --- | --- |
| `compression_breakout_would_enter` | Shows a long-side volatility-compression breakout observation for review |
| `no_signal_no_compression` | Proves no-compression windows stay visible but quiet |
| `false_breakout_disable_needed` | Proves false-breakout risk should revise the classifier before L2 promotion |
| `missing_compression_context` | Proves missing compression context blocks observation promotion review |
| `stale_signal` | Proves freshness rejection before promotion review |

The would-enter case must not reach prepare, FinalGate, Operation Layer,
exchange write, or real order authority. It is replay/review evidence only.

## LSR-001 L1 Observe Replay Corpus

`LSR-001` remains an `L1 observe_only` StrategyGroup. Its replay corpus exists
to keep liquidity-sweep observations visible while the side-specific rewrite
gap is still unresolved.

The current local corpus covers five L1 observe-only windows:

| Case | Purpose |
| --- | --- |
| `liquidity_sweep_long_would_enter_current_v0` | Shows the current-v0 long sweep observation for review |
| `short_revival_rewrite_needed` | Documents the stronger short-revival research lane and rewrite gap |
| `no_signal_no_sweep_reclaim` | Proves no-sweep windows stay visible but quiet |
| `missing_range_context` | Proves missing range/sweep context blocks observation promotion review |
| `stale_signal` | Proves freshness rejection before promotion review |

The would-enter and rewrite cases must not reach prepare, FinalGate, Operation
Layer, exchange write, or real order authority. They are replay/review evidence
only.

## BRF-001 L1 Observe Replay Corpus

`BRF-001` remains an `L1 observe_only` StrategyGroup. Its replay corpus exists
to make bear-rally-failure short observations visible while rally context,
short-squeeze-risk classification, and separate L2 intake remain unresolved.

The current local corpus covers five L1 observe-only windows:

| Case | Purpose |
| --- | --- |
| `bear_rally_failure_short_would_enter` | Shows a short-side rally-failure observation for review |
| `no_signal_rally_not_failed` | Proves rallies that have not failed stay visible but quiet |
| `short_squeeze_risk_revision_needed` | Proves squeeze-risk should revise the classifier before L2 promotion |
| `missing_rally_context` | Proves missing rally-high/rejection/squeeze context blocks promotion review |
| `stale_signal` | Proves freshness rejection before promotion review |

The would-enter and squeeze-risk cases must not reach prepare, FinalGate,
Operation Layer, exchange write, or real order authority. They are
replay/review evidence only.

## Owner Replay Review Summary

The Owner progress report must summarize replay coverage by StrategyGroup, not
only as aggregate sample counts. This lets the Owner see whether the system is
finding broader no-action / would-enter / revise evidence while P0 waits for a
real fresh signal.

The current table shape is:

| Field | Meaning |
| --- | --- |
| `StrategyGroup` | The replayed strategy group |
| `Layer` | `L4 replay baseline`, `L2 shadow`, or `L1 observe` |
| `Samples` | Local replay windows in the report |
| `Review signals` | Replay windows that would be reviewed as non-live signal evidence |
| `Quiet / no-action` | Replay windows that correctly stay quiet |
| `Revise` | Replay windows recommending classifier or facts revision |
| `Boundary` | Why the replay row cannot authorize live execution |

## Post-Submit Simulator Matrix

The local post-submit simulator matrix covers:

| Case | Purpose |
| --- | --- |
| `entry_accepted_protection_ok` | Normal accepted-entry close-loop shape |
| `entry_filled_sl_creation_failed` | Protection failure shape with reduce-only recovery reachable |
| `partial_fill` | Partial-fill reconciliation and budget shape |
| `submit_rejected_before_acceptance` | Rejected submit does not become active exposure |
| `position_closed_by_sl` | SL closure finalize/reconcile/settle/review shape |
| `position_closed_by_tp1` | TP1 closure and runner/remainder review shape |
| `active_position_remains_open` | Open protected position remains monitored, not falsely completed |

The simulator checks finalize, reconciliation, budget settlement, and review
shapes without calling live Operation Layer submit or exchange write.

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
| MPG replay corpus | `docs/current/strategy-group-handoffs/MPG-001/replay/mpg-001-replay-corpus.json` |
| MPG synthetic fixtures | `docs/current/strategy-group-handoffs/MPG-001/replay/synthetic-signal-fixtures.json` |
| BTPC L2 shadow replay corpus | `docs/current/strategy-group-handoffs/BTPC-001/replay/btpc-001-l2-replay-corpus.json` |
| VCB L1 observe replay corpus | `docs/current/strategy-group-handoffs/VCB-001/replay/vcb-001-l1-observe-replay-corpus.json` |
| LSR L1 observe replay corpus | `docs/current/strategy-group-handoffs/LSR-001/replay/lsr-001-l1-observe-replay-corpus.json` |
| BRF L1 observe replay corpus | `docs/current/strategy-group-handoffs/BRF-001/replay/brf-001-l1-observe-replay-corpus.json` |
| Post-submit simulator matrix | `docs/current/strategy-group-handoffs/MPG-001/replay/post-submit-simulator-matrix.json` |
| Unit tests | `tests/unit/test_strategygroup_runtime_replay_lab.py` |
| Dry-run audit tests | `tests/unit/test_runtime_dry_run_audit_chain.py` |

## Acceptance

The current P0.5 checkpoint is accepted when:

1. `MPG-001` replay corpus validates locally.
2. `BTPC-001` L2 shadow replay corpus validates locally without L4 authority.
3. `VCB-001` L1 observe replay corpus validates locally without L2 or L4
   authority.
4. `LSR-001` L1 observe replay corpus validates locally without L2 or L4
   authority.
5. `BRF-001` L1 observe replay corpus validates locally without L2 or L4
   authority.
6. The synthetic fixture set covers no-signal, fresh-pass, stale, missing-fact,
   conflict, protection-missing, and profile-boundary branches.
7. Post-submit simulator matrix covers accepted, failed-protection, partial-fill,
   reject, closed-by-SL, closed-by-TP1, and still-open shapes.
8. Cost-review fields are present as review inputs only.
9. Runtime dry-run audit exposes replay-lab checks in the unified packet.
10. All replay and dry-run paths prove:

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
larger local replay/review corpus:

| Expansion | Why it matters |
| --- | --- |
| More MPG historical windows | Better entry/exit review before live signals arrive |
| Better cost, slippage, and funding estimates | Better estimate of whether gross edge can survive execution friction |
| Cross-StrategyGroup replay at L2 only | Add no-action / would-enter diagnostics without expanding real-order scope |
| Simulator-to-review scoring | Turn fill/protection/reconciliation outcomes into promote/revise/park evidence |
