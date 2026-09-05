# Stage-3 Semantic Dynamic Selection Replay

## Status

```text
research_status = STAGE3_SEMANTIC_DYNAMIC_SELECTION_REPLAY_COMPLETE
production_behavior = UNCHANGED
selector_implementation = NONE
production_authority = NONE
```

## Frozen selectors

| Strategy | Feature | Cadence | Universe |
| --- | --- | ---: | ---: |
| CPM | signed trend efficiency 24h | 4h | Top16 / Near4 / NotSelected4 |
| MPG | leader occupancy 6h | 1h | Top16 / Near4 / NotSelected4 |
| MI | positive impulse recency 12h | 1h | Top16 / Near4 / NotSelected4 |
| BRF2 | residual extension z 24h | 4h | Top16 / Near4 / NotSelected4 |

The Snapshot calculated at final close `t` becomes Detector-eligible at `t+1h`.
MPG/MI comparative ranks always use the complete fixed 24-member universe.

## Result boundary

CPM returned `REVISE_ONCE`. BRF2, MPG and MI did not show the frozen persistent
clear-adverse-selection condition, but MPG/MI have sparse NotSelected Event
coverage and therefore do not have evidence of quality improvement.

See `STAGE3_SEMANTIC_DYNAMIC_SELECTION_PROTOCOL.md` in the parent research
package and the machine-readable files under `artifacts/`.
