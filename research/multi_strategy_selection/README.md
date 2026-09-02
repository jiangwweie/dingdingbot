# Multi-Strategy Selection Stage-2 Full Replay

Status: `RUNTIME_REFACTOR_REQUIRED / ENTRY_REFERENCE_DATA_GAP`

This research scope is intentionally separate from production code. R0-R2
froze current `dev`, the exact 24-member CandidateUniverse, current Detector
semantics, and the Detector-feature exclusion matrix. Execution stopped before
market-data acquisition because current production semantics do not expose a
Kline-reconstructible `entry_reference_price` for CPM/MPG/MI/BRF2 Events.

No Detector, Selector, ExitProfile, Capacity, leverage, risk, schema, runtime,
or production behavior was changed.

See:

- `stage2_replay_manifest.json`
- `DETECTOR_FEATURE_EXCLUSION_MATRIX.md`
- `STAGE2_EXECUTION_BLOCKER.md`

