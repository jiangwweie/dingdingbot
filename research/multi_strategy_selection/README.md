# Multi-Strategy Selection Stage-2 Full Replay

Status: `STAGE2_FULL_REPLAY_COMPLETE / PROTOCOL_V2`

This research scope is intentionally separate from production code. Protocol V1
stopped correctly at R2 because production action-time best bid/ask entry could
not be reconstructed from Klines. The retained Protocol V2 amendment separates
Signal-basis Event path quality from production execution quality and authorizes
trigger-close Signal-R as the primary estimand. R3-R16 are now complete.

No Detector, Selector, ExitProfile, Capacity, leverage, risk, schema, runtime,
or production behavior was changed.

See:

- `PROTOCOL_V2_AMENDMENT.md`
- `stage2_replay_manifest_v1_blocked.json`
- `stage2_replay_manifest.json`
- `DETECTOR_FEATURE_EXCLUSION_MATRIX.md`
- `STAGE2_EXECUTION_BLOCKER.md`
- `artifacts/STAGE2_FULL_REPLAY_REPORT.md`
- `artifacts/feature_screening.csv`

Stage-2.1 adds a research-only time-cluster robustness audit for the exact four
supported hypotheses. It freezes the Stage-2 buckets and labels, then reports
trigger-hour aggregation, leave-one-day/week-out stability, UTC-day/week
cluster bootstrap intervals, and per-block effects without changing any
classification or Selector authority.

- `artifacts/STAGE2_1_CLUSTER_ROBUSTNESS_REPORT.md`
- `artifacts/stage2_1_cluster_summary.csv`
- `artifacts/stage2_1_cluster_manifest.json`
