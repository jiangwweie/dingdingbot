## StrategyGroup Trial Candidate Pool v0

- Status: `trial_candidate_pool_ready`
- Candidate count: `5`
- Trial eligible count: `1`
- Actionable now count: `0`
- Live permission change count: `0`
- Output: `/Users/jiangwei/Documents/final/output/runtime-monitor/latest-strategygroup-trial-candidate-pool.md`

## Candidates

| StrategyGroup | Pool stage | Tier | Evidence stage | Trial eligible | Actionable now | Next system action |
| --- | --- | --- | --- | --- | --- | --- |
| `MPG-001` | `selected_live_lane_waiting_for_market` | `L4` | `trial_waiting` | 是 | 否 | `MPG-001_no_action_visibility_and_routing_audit` |
| `BRF-001` | `promote_review_candidate` | `L1` | `promote_review` | 否 | 否 | `BRF-001_forward_outcome_and_requiredfacts_review` |
| `LSR-001` | `rewrite_candidate_after_revision` | `L1` | `revise` | 否 | 否 | `LSR-001_classifier_fact_source_revision_review` |
| `MI-001` | `identity_candidate_review` | `unknown` | `identity_review` | 否 | 否 | `MI-001_registry_identity_review` |
| `CPM-RO-001` | `identity_candidate_review` | `unknown` | `identity_review` | 否 | 否 | `CPM-RO-001_registry_identity_review` |

## Boundary

Trial candidate pool is review-only. It does not authorize live execution, registry admission, tier change, live profile change, or order submission.
