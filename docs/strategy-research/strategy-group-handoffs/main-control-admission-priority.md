# Main-Control Admission Priority

Status: HANDOFF_SUPPLEMENT_READY
Last updated: 2026-06-14

## Purpose

This document gives main-control a minimal admission order for the first
StrategyGroup handoff batch.

It is a research-side recommendation only. It is not runtime registration,
FinalGate input, Operation Layer input, exchange-write authority, deploy
authority, live-profile mutation, credential mutation, or order-sizing default.

## Admission Buckets

| Bucket | Strategy Groups | Main-Control Meaning |
| --- | --- | --- |
| `first_batch_default_visible` | `MPG-001`, `TEQ-001`, `FBS-001` | Show as first Strategy Picker candidates after exchange/rule validation. |
| `observe_only_default` | `PMR-001` | Show as observe-only until role/session/mark facts are present. |
| `conditional_session` | `SOR-001` | Show only with session-window readiness and branch selection. |

## Recommended Admission Order

| Rank | Strategy Group | Default Mode | Reason | Admission Notes |
| ---: | --- | --- | --- | --- |
| `1` | `MPG-001` | `armed_observation` | Broadest first handoff; simple long momentum-persistence semantics. | Admit first if closed-candle facts, exchange rules, and same-symbol account facts pass. |
| `2` | `TEQ-001` | `armed_observation` | Owner explicitly wants 2026 Binance equity-like instruments included. | Admit with concentration and session facts visible; do not treat as broad basket. |
| `3` | `FBS-001` | `armed_observation` with higher fact threshold | Best direct right-tail row, but depends on funding/mark/crowding facts. | Admit only when derivatives facts are available; otherwise observe-only overlay. |
| `4` | `SOR-001` | `conditional_armed_observation` | Useful session branches, but session timing is narrow. | Admit branch-by-branch near the session window. |
| `5` | `PMR-001` | `observe_only` | Useful metal short/overlay evidence, but role and session facts matter. | Upgrade only after explicit PMR role/session/mark readiness. |

## Strategy-Specific Defaults

### `MPG-001`

Default recommendation:

```text
show_in_strategy_picker: true
default_mode: armed_observation
default_side: long
first_batch_recommended: true
```

Admission gates:

1. Closed 1h candles present.
2. Exchange symbol rules present.
3. Same-symbol active position and open orders absent.
4. Late-cycle extension not triggered.
5. Stop-loss and exit-plan hints present.

### `TEQ-001`

Default recommendation:

```text
show_in_strategy_picker: true
default_mode: armed_observation
default_side: long
first_batch_recommended: true
```

Admission gates:

1. Symbol is in the TEQ research-supported set and currently exchange-visible.
2. Session context is known.
3. Mark/funding facts are available for perps.
4. Symbol concentration warning is visible in the UI.
5. Short side remains disabled except SOR-specific handoff lanes.

Relationship with `MPG-001`:

```text
same_symbol_same_direction: allow_observation_but_merge_candidate_review
same_symbol_duplicate_candidate: block_duplicate_candidate_prepare
different_symbol_same_direction: allow_parallel_observation
```

### `FBS-001`

Default recommendation:

```text
show_in_strategy_picker: true
default_mode: armed_observation_if_derivatives_facts_pass
default_side: long
first_batch_recommended: true
fact_threshold: high
```

Admission gates:

1. Funding-rate window present.
2. Mark-price window present.
3. Negative-funding crowding state present for the TEQ long lane.
4. Real-margin model is not required for observation, but missing real-margin
   facts must block leverage promotion.
5. Positive-funding short lanes remain negative/redesign evidence.

### `PMR-001`

Default recommendation:

```text
show_in_strategy_picker: true
default_mode: observe_only
default_side: short
upgrade_condition: explicit_role_session_mark_readiness
```

Upgrade to `armed_observation` only when:

1. `metal_role_split_state` is `short_weakness`.
2. `commodity_session_gap_state` is present.
3. `mark_deviation_bound_state` is present and bounded.
4. Same-symbol account conflicts are absent.
5. XAG dominance is visible as a limitation, not hidden as basket evidence.

### `SOR-001`

Default recommendation:

```text
show_in_strategy_picker: conditional
default_mode: armed_observation_near_session_window
default_side: branch_specific
```

Branch priority:

| Priority | Branch | Mode |
| ---: | --- | --- |
| `1` | `sor_pmr_us_open_short_72h` | `armed_observation` if PMR session facts pass. |
| `2` | `sorcls_pmr_short_prior_weakness` | `armed_observation` if decay warning is visible. |
| `3` | `sorcls_teq_short_decisive_breakdown_72h` | `armed_observation` with TEQ short exception label. |
| `4` | TEQ long SOR revival lanes | `observe_only` unless new disable classifier exists. |

## Minimal Main-Control Display Recommendation

| Strategy Group | Picker Default | Badge |
| --- | --- | --- |
| `MPG-001` | Visible | `first batch` |
| `TEQ-001` | Visible | `equity-like perp` |
| `FBS-001` | Visible | `high facts threshold` |
| `PMR-001` | Visible but observe-only | `overlay / role split` |
| `SOR-001` | Conditional visible | `session window` |

## Boundary

Admission priority does not authorize execution. It only helps main-control
decide how to display, observe, and review the first StrategyGroup batch.
