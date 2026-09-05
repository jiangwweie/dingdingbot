# Stage-3 Semantic Dynamic Selection Replay Protocol

## Status

```text
protocol_status = FROZEN_BEFORE_RESULT_INSPECTION
production_behavior = UNCHANGED
selector_implementation = NONE
production_authority = NONE
```

## Objective

Test one frozen, theory-driven pre-Detector Dynamic TradableUniverse for each
Crypto Strategy without optimizing parameters or requiring statistical
significance.

The Replay asks whether each Selector is operationally coherent and avoids
clear, persistent adverse selection. It does not prove alpha or authorize
production activation.

## Authority

```text
Stage-2.1 base commit:
337c5cd19e6837aa84d9eb49ed786beb2b156fce

Detector authority:
dev@2697f4b5943ed6a98f04a93e1b78d38e53780890

CandidateUniverse:
exact canonical 24-member Stage-2 panel
```

## Time windows

```text
warm-up start = 2026-06-15T00:00:00Z
evaluation    = [2026-07-31T00:00:00Z, 2026-08-31T00:00:00Z)
Discovery     = [2026-07-31T00:00:00Z, 2026-08-16T00:00:00Z)
Holdout       = [2026-08-16T00:00:00Z, 2026-08-31T00:00:00Z)
```

## Shared Universe contract

```text
CandidateUniverse = fixed 24
SELECTED           = ranks 1..16
NEAR_THRESHOLD     = ranks 17..20
NOT_SELECTED       = ranks 21..24
```

All Strategies rank higher feature values first. Exact ties use canonical
`exchange_instrument_id ASC`. No secondary alpha variable is permitted.

Any missing, duplicate, irregular or future Candidate input invalidates the
whole Selection Snapshot. V0 does not rank a partial panel.

## Temporal contract

A Selection Snapshot calculated at final 1h close `t` becomes effective at:

```text
t + 1h
```

The Detector evaluation at `t` therefore uses the previous eligible Snapshot.
This avoids using one close to select an Instrument and simultaneously claiming
that the already-closing Event was pre-selected.

```text
CPM cadence   = every UTC hour divisible by 4
BRF2 cadence  = every UTC hour divisible by 4
MPG cadence   = every final UTC 1h close
MI cadence    = every final UTC 1h close
```

The active Snapshot remains effective until the next Snapshot's
`effective_from_ms`.

## CPM V0

```text
selection_spec_id = CPM_SIGNED_TREND_EFFICIENCY_V0
feature = signed_trend_efficiency_24h

(close_t - close_t-24h)
---------------------------------
sum(abs(close_j - close_j-1), j=1..24)
```

The exact 25 contiguous final 1h closes ending at `t` are required. Zero path
distance invalidates the member.

## MPG V0

```text
selection_spec_id = MPG_LEADER_OCCUPANCY_V0
feature = leader_occupancy_6h
```

At each of the six final 1h boundaries:

```text
t-5h, t-4h, t-3h, t-2h, t-1h, t
```

calculate the exact production MPG comparative rank using:

```text
ComparisonUniverse = fixed 24
lookback = 8 final 1h bars
```

Then:

```text
leader_occupancy_6h
= count(rank <= 6) / 6
```

The Dynamic TradableUniverse never changes the ComparativeUniverse or rank.

## MI V0

```text
selection_spec_id = MI_POSITIVE_IMPULSE_RECENCY_V0
feature = positive_impulse_recency_12h
```

Use the 12 simple 1h returns ending at `t`, ordered oldest to newest. For
`j = 0..11`:

```text
p_j = max(simple_return_j, 0)
w_j = j / 11

positive_impulse_recency_12h
= sum(w_j * p_j) / sum(p_j)
```

If `sum(p_j) = 0`, the valid feature value is `0`. The Selector does not use
current MI rank or total 12h return.

## BRF2 V0

```text
selection_spec_id = BRF2_RESIDUAL_EXTENSION_V0
feature = residual_extension_z_24h
```

Use 72 contiguous final 1h log returns ending at `t`. For each hour, market
return is the equal-weight mean of the exact 24 Candidate log returns.

Estimate one OLS beta with intercept over 72 observations:

```text
beta_i = covariance(r_i, market) / variance(market)
alpha_i = mean(r_i) - beta_i * mean(market)
residual_i,j = r_i,j - alpha_i - beta_i * market_j
```

Then use the final 24 residuals:

```text
residual_extension_24h = sum(residual_i,j)
residual_rv_24h = sqrt(sum(residual_i,j ^ 2))

residual_extension_z_24h
= residual_extension_24h / residual_rv_24h
```

Zero market variance or zero residual RV invalidates the member.

## Numeric contract

- Source OHLC values enter from strings through `Decimal`.
- Feature formulas use deterministic `Decimal` where possible.
- Log returns and square root use frozen Python `math.log`, `math.sqrt` and
  `math.fsum` ordering.
- Rankings use full-precision in-memory values; exact tie-break is Instrument ID.
- No threshold, percentile or learned coefficient exists.

## Detector Replay contract

Two evidence views are required.

### Counterfactual membership view

Classify every Stage-2 all-24 Replay Event by the active pre-Detector Snapshot:

```text
SELECTED / NEAR_THRESHOLD / NOT_SELECTED
```

This measures Good-event capture and Bad-event rejection without changing Event
identity.

### Dynamic Detector view

Re-run the current Detector only for active SELECTED members. Rising-edge
ExposureEpisode state advances only when the Instrument is selected and
observed. Unselected time does not synthesize Detector state transitions.

MPG/MI comparative projections always use all 24 members even when only 16 are
Detector-eligible.

## Outcome contract

Use the unchanged Stage-2 Protocol V2 Signal-R path:

```text
signal anchor = trigger final close
stop = exact Detector protection_reference
path starts strictly after trigger close
horizon = 48h
15m -> 1m -> AMBIGUOUS
```

## Required diagnostics

For every Strategy and Discovery/Holdout/Full period report:

```text
ALL24 baseline Events
membership-classified Events
dynamic Detector Events

TP1_FIRST / STOP_FIRST / NEITHER / AMBIGUOUS
net_path_rate
MFE / MAE

baseline Good-event capture
baseline Bad-event rejection
Universe additions/removals
turnover
mean selected membership duration
Source failure / insufficient / empty Snapshot count
```

MPG/MI must report exact rank-parity mismatch count. Required result is zero.

## Frozen decision contract

For each Strategy:

```text
THEORY_COMPATIBLE_DYNAMIC_V0
REVISE_ONCE
SEMANTIC_SELECTOR_REJECTED
```

### Operational hard failures

Any of the following rejects or revises before outcome interpretation:

- CandidateUniverse drift;
- future leakage;
- partial-panel ranking;
- MPG/MI rank mismatch;
- Detector semantic duplication;
- no valid Snapshot coverage;
- persistent Ready < 16;
- missing deterministic rerun identity.

### Clear adverse-selection rejection

Reject only when both Discovery and Holdout satisfy all of:

```text
SELECTED resolved N >= 15
NOT_SELECTED resolved N >= 15
SELECTED minus NOT_SELECTED net_path_rate <= -0.20
SELECTED TP1_FIRST rate < NOT_SELECTED TP1_FIRST rate
SELECTED STOP_FIRST rate > NOT_SELECTED STOP_FIRST rate
```

If only one period meets the adverse condition, return `REVISE_ONCE`.
Otherwise, if operational hard gates pass, return
`THEORY_COMPATIBLE_DYNAMIC_V0`.

This is a semantic sanity gate, not an alpha significance test.

## Prohibitions

```text
NO parameter search
NO alternate Top-N
NO alternate cadence
NO alternate feature horizon
NO factor combination
NO PnL optimization
NO ticker whitelist
NO Detector change
NO production code or Schema change
NO production deployment or activation
```
