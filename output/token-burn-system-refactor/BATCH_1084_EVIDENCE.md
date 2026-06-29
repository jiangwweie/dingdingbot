# Batch 1084 Evidence - Monitor Refresh Sequence Status Helper

## Status

`in_progress`

This batch continues the long-running system refactor objective after the
directional Owner validation closeout. It does not claim strict objective
completion.

## Batch Acceptance

| Field | Value |
| --- | --- |
| closed_engineering_problem | Local Monitor Sequence still owned a small hand-rolled monitor-refresh status branch even though monitor-refresh classification already lives in `scripts/runtime_monitor_refresh.py`. |
| capability_unlocked | Monitor-refresh sequence status is now a shared helper, so daily/goal/local monitor projections can reuse one typed runtime-source rule instead of rebuilding `waiting_for_market_monitor_refresh_needed` locally. |
| next_engineering_bottleneck | Continue only with narrow current-boundary glue compression or validation. The previous merge-ready closeout must be revalidated after this new production-code batch before any merge claim. |
| files_changed | `scripts/runtime_monitor_refresh.py`; `scripts/run_strategygroup_runtime_local_monitor_sequence.py`; `tests/unit/test_strategygroup_runtime_local_monitor_sequence.py` |
| tests_run | `python3 -m pytest tests/unit/test_strategygroup_runtime_local_monitor_sequence.py -q` -> `47 passed`; `python3 -m pytest tests/unit/test_strategygroup_runtime_local_monitor_sequence.py tests/unit/test_strategygroup_runtime_daily_check.py tests/unit/test_strategygroup_runtime_goal_progress_audit.py -q` -> `161 passed`; `python3 -m compileall src scripts tests -q` -> passed; `git diff --check` -> passed; `python3 -m pytest tests/unit -q` -> `3124 passed, 1 skipped, 1 warning` |
| why_this_batch_enables_deeper_refactor | It removes one more local status-mapping decision from the Local Monitor Sequence and keeps monitor-refresh semantics centralized as a projection/helper concern rather than a parallel lifecycle layer. |

## Added / Retained / Deleted

| Category | Detail |
| --- | --- |
| added | `monitor_refresh_sequence_status(...)` in `scripts/runtime_monitor_refresh.py`; focused characterization coverage for typed runtime-source precedence. |
| retained | `monitor_refresh_needed` remains a reporting/refresh classification, not a blocker or hard safety stop. `waiting_for_market` is returned only when a typed runtime source declares waiting. |
| deleted_this_batch | The local inline monitor-refresh status branch in `_sequence_status(...)`. |
| planned_deletion_or_downgrade | Continue looking for local monitor/read-only projection glue that duplicates shared monitor helpers, but only in narrow current-boundary batches. |
| legacy_fallback_exit_condition | No legacy fallback was added. Existing artifact classification helpers remain the source for deployment issue and refresh semantics. |

## Boundary Classification

| Boundary | Status |
| --- | --- |
| FinalGate | untouched |
| Operation Layer | untouched |
| RequiredFacts | untouched |
| exchange write / real order | untouched |
| live profile / sizing / secrets | untouched |
| `/Users/jiangwei/Documents/final` | untouched |

## Revalidation

The batch is intentionally small and non-executing. It affects monitor/read-only
projection glue only.

```text
focused local monitor sequence: 47 passed
monitor refresh focused slice: 161 passed
compileall: passed
diff check: passed
full unit: 3124 passed, 1 skipped, 1 warning
```
