# Stage-2 Full Replay — Protocol V2 Amendment

## Status transition

Protocol V1 stopped correctly after R2:

```text
previous_status = RUNTIME_REFACTOR_REQUIRED
blocker_code = ENTRY_REFERENCE_DATA_GAP
revised_status = RESEARCH_PROTOCOL_REVISION_REQUIRED
runtime_refactor_required = FALSE
```

`StrategySignal` is an immutable detected Event, not a sizing or order
instruction. Production entry geometry is created later by CapacityClaim from
the action-time best ask for LONG or best bid for SHORT. Stage-2 studies the
upper half of that chain: EventSpec occurrence, point-in-time Market Context,
and subsequent path quality.

## Primary estimand

```text
signal_anchor_price = trigger candle final close
signal_stop_reference = exact Detector protection_reference fact
forward_path_start = strictly after trigger close
execution_equivalence = FALSE
```

The resulting `signal_risk_per_unit`, `signal_tp1_price`, `mfe_signal_r`, and
`mae_signal_r` are research-only Signal-R values. They are not actual entry,
execution R, fee-adjusted return, or production profitability.

## First-passage contract

The primary path labels are:

```text
SIGNAL_TP1_FIRST
SIGNAL_STOP_FIRST
NEITHER
AMBIGUOUS
```

The trigger candle is excluded. The maximum forward window is 48 hours. Path
ordering uses 15-minute candles, drills into 1-minute candles only when one
15-minute candle touches both levels, and remains `AMBIGUOUS` if one 1-minute
candle still touches both.

## Secondary production validation

Matched production Tickets may compare Signal-basis and actual-entry-basis path
classification and normalized execution-anchor delta. This subset is
secondary robustness evidence only because Admission, Capacity, Netting, and
Budget have already selected it. It cannot train or freeze Context thresholds.

## Excluded work

Option A is out of scope. This task does not add historical book-ticker data,
order-book reconstruction, latency simulation, spread models, or an
execution-adjusted Replay. The frozen CandidateUniverse, Detector authority,
ComparisonUniverse semantics, features, Discovery/Holdout split, univariate
screening, LOSO, ambiguity handling, and classification gates remain unchanged.

## Claim boundary

The maximum positive classification is `SUPPORTED_FOR_SHADOW`. It means a
univariate Context feature showed stable incremental Signal-basis path
stratification for a current-dev EventSpec. It does not mean profitable,
execution validated, production ready, causal, or optimal.
