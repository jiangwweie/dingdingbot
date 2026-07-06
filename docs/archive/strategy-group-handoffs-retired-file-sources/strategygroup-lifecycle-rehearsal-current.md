---
title: STRATEGYGROUP_LIFECYCLE_REHEARSAL_CURRENT
status: CURRENT
authority: docs/current/strategy-group-handoffs/strategygroup-lifecycle-rehearsal-current.json
last_verified: 2026-06-20
---

# StrategyGroup Lifecycle Rehearsal Current

## Summary

- Status: `lifecycle_rehearsal_ready`
- Rehearsal mode: paper/simulator only
- Exchange write: `false`

## Scenarios

| Scenario | Status | Review shape |
| --- | --- | --- |
| `submit_accepted` | `passed` | `True` |
| `submit_rejected` | `passed` | `True` |
| `partial_fill` | `passed` | `True` |
| `submit_timeout` | `passed` | `True` |
| `protection_failure` | `passed` | `True` |
| `reconciliation_shape` | `passed` | `True` |
| `rough_cost_pnl_review` | `passed` | `True` |

## Boundary

This rehearsal closes non-live lifecycle branches. Real exchange acceptance, fill behavior, protection acceptance, settlement, and realized PnL remain live-only calibration.

## Runtime Safety State

- Source role: `lifecycle_rehearsal_evidence`
- Tradeability decision source: `False`
- Execution Attempt source: `False`
- Default next step: `feed_lifecycle_rehearsal_into_pre_live_readiness`
