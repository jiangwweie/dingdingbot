# Stage-3 Semantic Dynamic Selection Replay Report

## Status

```text
research_status = STAGE3_SEMANTIC_DYNAMIC_SELECTION_REPLAY_COMPLETE
production_behavior = UNCHANGED
selector_implementation = NONE
production_authority = NONE
```

## Frozen protocol

- Exact fixed 24-member CandidateUniverse.
- Per-Strategy Top16 / Near4 / NotSelected4.
- CPM and BRF2 selection every 4h; MPG and MI every 1h.
- Snapshot calculated at `t` becomes Detector-eligible at `t+1h`.
- MPG/MI comparative rank always uses all 24 members.
- No parameter, cadence, Top-N, horizon or factor optimization occurred.

## Results

| Strategy | Classification | Comparison coverage | Discovery effect | Holdout effect | Baseline Events | Selected Events | Not Selected Events | Dynamic Detector Events | Good capture | Bad rejection | Positive blocks | Mean turnover | Mean membership |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| BRF2-001 | THEORY_COMPATIBLE_DYNAMIC_V0 | SUFFICIENT | +0.119 | -0.024 | 613 | 446 | 86 | 447 | 74.4% | 13.6% | 3/5 | 14.2% | 27.2h |
| CPM-RO-001 | REVISE_ONCE | SUFFICIENT | -0.191 | -0.265 | 719 | 570 | 71 | 585 | 74.8% | 7.4% | 1/5 | 13.9% | 27.8h |
| MI-001 | THEORY_COMPATIBLE_DYNAMIC_V0 | SPARSE_NOT_SELECTED_EVENTS | +0.842 | +0.361 | 74 | 61 | 6 | 62 | 86.7% | 12.1% | 2/3 | 15.0% | 6.6h |
| MPG-001 | THEORY_COMPATIBLE_DYNAMIC_V0 | SPARSE_NOT_SELECTED_EVENTS | +1.000 | N/A | 70 | 69 | 1 | 69 | 100.0% | 4.2% | 1/1 | 5.7% | 17.0h |

`SPARSE_NOT_SELECTED_EVENTS` means the frozen Top16 Selector removed too few
resolved Events to support a reliable Selected-vs-NotSelected comparison. It
does not convert operational compatibility into evidence of quality improvement.

## Runtime and semantic QC

```text
Selection Snapshots = 4,630
Member Decisions = 111,120
Dynamic Detector evaluations = 47,616
Dynamic Replay Events = 1,163
Dynamic invalid Detector evaluations = 0
MPG/MI rank parity mismatches = 0
Empty Snapshots = 0
Insufficient Snapshots = 0
```

## Claim boundary

`THEORY_COMPATIBLE_DYNAMIC_V0` means the frozen semantic Selector was
operationally coherent and did not show the pre-registered persistent clear
adverse-selection pattern. It does not mean profitable, statistically proven,
production ready or authorized for Dynamic Universe activation.
