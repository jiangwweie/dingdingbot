## StrategyGroup Trial Candidate Pool v0

- Status: `trial_candidate_pool_ready`
- Candidate count: `3`
- Trial eligible count: `1`
- Live permission change count: `0`
- Output: `/Users/jiangwei/Documents/final-system-refactor-20260623/output/runtime-monitor/latest-strategygroup-trial-candidate-pool.md`

## Candidates

| StrategyGroup | Pool stage | Tier | Evidence stage | Trial eligible | Strategy review checkpoint |
| --- | --- | --- | --- | --- | --- |
| `MPG-001` | `selected_live_lane_waiting_for_market` | `L4` | `trial_waiting` | 是 | `build_mpg_member_role_controls_v2_without_live_scope_expansion` |
| `BRF-001` | `promote_review_candidate` | `L1` | `promote_review` | 否 | `BRF-001_forward_outcome_and_requiredfacts_review` |
| `LSR-001` | `rewrite_candidate_after_revision` | `L1` | `revise` | 否 | `LSR-001_classifier_fact_source_revision_review` |

## Boundary

Trial candidate pool is review-only. It does not authorize live execution, registry admission, tier change, live profile change, or order submission.
