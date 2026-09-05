# Stage-3.1 Final Semantic Revision Report

## Status

```text
research_status = STAGE3_1_FINAL_SEMANTIC_REVISION_COMPLETE
generic_selection_implementation_authority = NONE
production_dynamic_activation_authority = NONE
```

## Strategy decision

| Strategy | Frozen Selector | Entry N | Retain N | Evidence Status | Dynamic Spec Eligible | Production Activation |
| --- | --- | ---: | ---: | --- | --- | --- |
| CPM-RO-001 | CPM_ABSOLUTE_DIRECTIONAL_EFFICIENCY_V1 | 16 | 16 | TOP16_FALLBACK_CAPTURE_BELOW_FLOOR | True | False |
| MPG-001 | MPG_PERSISTENT_LEADERSHIP_SCORE_V1 | 12 | 16 | MINIMUM_COMPATIBLE_CAPTURE_CARDINALITY | True | False |
| MI-001 | MI_POSITIVE_IMPULSE_RECENCY_V0 | 16 | 16 | MINIMUM_COMPATIBLE_CAPTURE_CARDINALITY | True | False |
| BRF2-001 | BRF2_RESIDUAL_EXTENSION_V0 | 16 | 16 | TOP16_FALLBACK_CAPTURE_BELOW_FLOOR | True | False |
| SOR-001 | EXISTING_SOR_DYNAMIC_SELECTION_V0 | 7 | 7 | EXISTING_GOLDEN_AUTHORITY | True | False |

## Cardinality sensitivity

| Strategy | Cardinality | Good Capture | Bad Rejection | Opportunity Retention | Dynamic Event Retention | Discovery Effect | Holdout Effect |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BRF2-001 | Top16 | 74.4% | 26.1% | 72.8% | 72.9% | +0.026 | +0.001 |
| BRF2-001 | Top12 | 58.5% | 43.6% | 55.8% | 55.1% | +0.084 | +0.004 |
| BRF2-001 | Top8 | 44.5% | 58.0% | 41.1% | 40.8% | +0.020 | +0.080 |
| CPM-RO-001 | Top16 | 62.6% | 38.1% | 65.0% | 66.8% | +0.124 | -0.108 |
| CPM-RO-001 | Top12 | 50.5% | 54.5% | 50.5% | 52.9% | +0.155 | -0.003 |
| CPM-RO-001 | Top8 | 31.3% | 71.4% | 32.1% | 35.5% | +0.072 | +0.019 |
| MI-001 | Top16 | 86.7% | 27.3% | 82.4% | 83.8% | +0.042 | +0.661 |
| MI-001 | Top12 | 73.3% | 45.5% | 66.2% | 73.0% | +0.057 | +0.615 |
| MI-001 | Top8 | 60.0% | 45.5% | 55.4% | 63.5% | -0.140 | +0.255 |
| MPG-001 | Top16 | 86.5% | 4.2% | 91.4% | 95.7% | -0.410 | -0.621 |
| MPG-001 | Top12 | 86.5% | 8.3% | 88.6% | 91.4% | -0.040 | -0.621 |
| MPG-001 | Top8 | 75.7% | 12.5% | 77.1% | 80.0% | -0.043 | -0.692 |

## CPM final revision

```text
removed_stage3_failure = True
verdict = CPM_THEORY_COMPATIBLE_DYNAMIC_V1
adverse_blocks = 1 / 5
```

## MPG final revision

```text
meaningful_discrimination = True
verdict = MPG_THEORY_COMPATIBLE_DYNAMIC_V1
```

## Claim boundary

This was the final authorized feature research. Cardinality was selected by the
pre-registered 80% Good Event Capture floor, not by maximizing net-path result.
Generic implementation remains separately gated and every Strategy may remain
Static independently.
