---
title: STRATEGY_CONTROL_BOARD_CONTRACT
status: CURRENT
authority: docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md
last_verified: 2026-06-15
---

# Strategy Control Board Contract

The Strategy Control Board is the Owner-facing operating surface. It must not become a packet browser, research-doc index, or manual gate assembly tool.

## Required Row Fields

| Field | Meaning |
| --- | --- |
| `strategy_group` | StrategyGroup id and display name |
| `runtime_state` | `observing`, `signal_ready`, `blocked`, `candidate_ready`, `submitted`, or `settled` |
| `signal_state` | `no_signal`, `fresh`, `stale`, or `conflict` |
| `required_facts` | `pass`, `missing`, `stale`, or `not_applicable` |
| `risk_profile` | Current bounded risk profile |
| `hard_stop` | Current hard-stop status and reason |
| `next_action` | `continue`, `prepare_candidate`, `run_finalgate`, `block`, or `review` |
| `review_outcome` | `promote`, `keep_observing`, `revise`, `park`, or `kill` |

## Notification Rule

Notify the Owner when deployment changes, watcher health regresses, a fresh
signal appears, a candidate becomes ready, FinalGate blocks or passes, Operation
Layer submits, post-submit reconciliation fails or settles, or review is needed.

Stay quiet when all selected runtimes remain observing with repeated
`no_signal` and no safety regression.
