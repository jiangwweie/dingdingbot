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
- Real order authority: `false`

## Scenarios

| Scenario | Status | Review shape | Real order |
| --- | --- | --- | --- |
| `submit_accepted` | `passed` | `True` | `False` |
| `submit_rejected` | `passed` | `True` | `False` |
| `partial_fill` | `passed` | `True` | `False` |
| `submit_timeout` | `passed` | `True` | `False` |
| `protection_failure` | `passed` | `True` | `False` |
| `reconciliation_shape` | `passed` | `True` | `False` |
| `rough_cost_pnl_review` | `passed` | `True` | `False` |

## Boundary

This rehearsal closes non-live lifecycle branches. Real exchange acceptance, fill behavior, protection acceptance, settlement, and realized PnL remain live-only calibration.
