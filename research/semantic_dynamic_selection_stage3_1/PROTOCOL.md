# Stage-3.1 Final Semantic Revision & Cardinality Sensitivity

## Frozen authority

```text
Stage-3 commit = 28b47e6d219acf2a008aacce92be1bd140b98964
Detector authority = dev@2697f4b5943ed6a98f04a93e1b78d38e53780890
production_behavior = UNCHANGED
implementation_authority = NONE
production_authority = NONE
```

## Unchanged contracts

- Exact fixed 24-member CandidateUniverse.
- Selection at `t`, effective at `t+1h`.
- CPM/BRF2 cadence 4h; MPG/MI cadence 1h.
- MPG/MI comparative rank always uses the full fixed 24.
- Stage-2 Protocol V2 48h Signal-R first passage remains unchanged.
- ExposureEpisode state is not reset during Universe absence/re-entry.

## Frozen feature revisions

### CPM V1

```text
CPM_ABSOLUTE_DIRECTIONAL_EFFICIENCY_V1
= abs(close_t - close_t-24h)
  / sum(abs(close_j - close_j-1), j=1..24)
```

### MPG V1

For the six all-24 production MPG ranks ending at `t`:

```text
rank_strength_j = (25 - rank_j) / 24
persistent_leadership_score_6h = mean(rank_strength_j)
```

### MI and BRF2

```text
MI_POSITIVE_IMPULSE_RECENCY_V0 = unchanged
BRF2_RESIDUAL_EXTENSION_V0 = unchanged
```

## Cardinalities

Only:

```text
Top16
Top12
Top8
```

For each N:

```text
SELECTED = rank <= N
EXCLUDED = rank > N
```

No other N may be calculated or reported.

## Recommendation rule

Evaluate N in ascending order `8, 12, 16`. Recommend the smallest N satisfying:

```text
Full Good Event Capture >= 80%
AND no persistent clear adverse selection in both Discovery and Holdout
```

Clear adverse selection uses the Stage-3 frozen condition:

```text
Selected and Excluded resolved N >= 15
operational_effect <= -0.20
Selected TP1 rate < Excluded TP1 rate
Selected Stop rate > Excluded Stop rate
```

## CPM terminal rule

The CPM revision verdict uses **Top16 continuity** to isolate the feature change
from cardinality change. Reject CPM V1 with no further revision when either:

```text
Discovery and Holdout effects are both <= -0.10 with sufficient comparison N
```

or:

```text
>= 60% of comparable 7-day blocks have operational_effect <= -0.10
```

## MPG discrimination rule

For each Snapshot and N record boundary ties. Tie-break selected members are the
members selected from a boundary feature-value group containing more than one
Instrument after all strictly higher values are admitted.

Return `MPG_SELECTOR_LOW_DISCRIMINATION` only when:

```text
baseline Event selected fraction > 95% at Top16, Top12 and Top8
AND mean boundary tie-break selected fraction > 5% at all three N
```

Otherwise, if there is no persistent clear adverse selection, return
`MPG_THEORY_COMPATIBLE_DYNAMIC_V1`.

## Hysteresis

For the recommended entry cardinality N:

```text
new admission = rank <= N
retention = rank <= 16
remove = rank > 16
```

No alternative retention rank may be tested.

## Prohibitions

```text
NO new feature
NO Top-N beyond 16/12/8
NO threshold or cadence search
NO Detector change
NO production code, DB, service or exchange mutation
NO third CPM revision
```
