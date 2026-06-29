## Trial-Grade Signal Gate Audit

- Status: `trial_grade_signal_gate_audit_ready`
- Generated: `2026-06-28T19:14:07.753679+00:00`
- Output JSON: `/Users/jiangwei/Documents/final-system-refactor-20260623/output/runtime-monitor/latest-strategygroup-trial-grade-signal-gate-audit.json`
- Scope: `30U bounded trial only`

## Summary

- StrategyGroups: `3`
- 30d trial-grade observations: `0`
- 30d action-time trial submits: `0`
- Hard safety gates relaxed: `否`

## Strategy Rows

| StrategyGroup | Current gate | 30d trial observations | Fixture trial cases | Max loss estimate | Tomorrow assessment |
| --- | --- | ---: | ---: | ---: | --- |
| `MPG-001` | `l4_production_path_with_trial_grade_warning_candidates` | 0 | 3 | 30 | `enter_trial_only_if_selected_scope_and_action_time_hard_gates_pass` |
| `BRF2-001` | `production_grade_strict_with_trial_grade_proxy_evidence` | 0 | 1 | 30 | `continue_armed_observation` |
| `SOR-001` | `conditional_armed_observation_with_trial_grade_replay_calibration` | 0 | 1 | 30 | `enter_non_executing_session_trial_review_then_action_time_gate` |

## Boundary

- Trial-grade risk is expressed as envelope: attempt cap, loss unit, pause rule, protection, and review.
- Replay, preview, and proxy rows do not satisfy action-time RequiredFacts.
- This artifact does not call FinalGate, Operation Layer, exchange write, or order creation.
