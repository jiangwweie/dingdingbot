# Stage-2.1 Cluster Robustness Audit

## Status

```text
research_status = STAGE2_1_CLUSTER_ROBUSTNESS_COMPLETE
feature_selection_changed = FALSE
cutoff_changed = FALSE
selector_design_authority = NONE
implementation_authority = NONE
production_authority = NONE
```

## Audit contract

This audit uses only the four Stage-2 `SUPPORTED_FOR_SHADOW` rows, their frozen
LOW/HIGH buckets, resolved Signal-R first-passage labels, and the original
Discovery/Holdout boundary. It does not search thresholds, add features,
combine factors, or reclassify a hypothesis automatically.

Trigger-hour aggregation gives every unique Event trigger hour equal weight
within each bucket. Leave-one-out removes an entire UTC day or Monday-based UTC
week. Bootstrap intervals resample complete UTC-day or UTC-week clusters with
replacement, preserving all cross-sectional Events inside the sampled cluster.

## Holdout results

| Strategy | Feature | Event effect | Trigger-hour effect | LOW hours | HIGH hours | LODO sign | LOWO sign | Day bootstrap 95% CI | Week bootstrap 95% CI | Day valid | Week valid |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| BRF2-001 | avg_cross_asset_corr_24h | +0.318 | +0.276 | 10 | 94 | 100.0% | 100.0% | [-0.145, +0.728] | [+0.025, +0.556] | 88.8% | 92.6% |
| BRF2-001 | market_rv_24h | +0.559 | +0.445 | 21 | 74 | 100.0% | 66.7% | [+0.061, +1.144] | [-0.288, +0.798] | 99.3% | 96.3% |
| CPM-RO-001 | avg_cross_asset_corr_24h | -0.386 | -0.533 | 12 | 90 | 93.3% | 66.7% | [-0.787, +0.853] | [-0.673, +0.033] | 88.3% | 92.6% |
| CPM-RO-001 | directional_efficiency_24h | +0.466 | +0.280 | 40 | 77 | 100.0% | 100.0% | [-0.152, +0.807] | [+0.102, +0.492] | 100.0% | 96.4% |

The Holdout contains only three Monday-based UTC-week clusters, including one
partial week. Week-level leave-one-out and bootstrap results therefore measure
sensitivity to these observed blocks but must not be read as a precise
large-sample confidence interval.

## Evidence reading

- `CPM-RO-001 × directional_efficiency_24h` retains a positive trigger-hour
  effect and 100% day/week leave-one-out sign stability. Its UTC-week bootstrap
  interval remains positive, while its UTC-day interval still crosses zero.
- `BRF2-001 × market_rv_24h` retains a positive trigger-hour effect and 100%
  day leave-one-out stability. Its UTC-day bootstrap interval remains positive,
  but one of three leave-one-week-out runs reverses and the week interval
  crosses zero.
- `CPM-RO-001 × avg_cross_asset_corr_24h` retains the expected negative
  trigger-hour effect, but both cluster-bootstrap intervals touch or cross zero
  and one day/week exclusion can reverse the effect.
- `BRF2-001 × avg_cross_asset_corr_24h` retains positive leave-one-out signs,
  but the Holdout LOW bucket represents only 10 unique trigger hours and its
  UTC-day bootstrap interval crosses zero.

## Interpretation boundary

The audit measures sensitivity to observed time clustering. It does not create
independent market regimes, prove causal Context effects, or produce a
production Selector. The original Stage-2 classifications remain research
provenance; the cluster metrics are additional evidence for independent review.
