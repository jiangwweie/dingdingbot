# BTPC L2 Keep / Revise / Fact Source Review

## Summary

- Status: `btpc_l2_keep_revise_fact_source_review_ready`
- Action items: `4`
- Live fact-source actions: `1`
- Classifier-rule actions: `2`
- L2 promotion authority: `false`
- L4 scope change: `false`

## Actions

| Area | Action | Evidence | Exchange write |
| --- | --- | --- | --- |
| `live_fact_source` | `attach_live_derivatives_fact_sources_before_btpc_live_eligibility` | `missing_derivatives_context` | `False` |
| `classifier_rule` | `review_btpc_strong_uptrend_conflict_disable_rule` | `strong_uptrend_conflict` | `False` |
| `classifier_rule` | `review_btpc_freshness_or_classifier_stale_signal_rule` | `stale_signal` | `False` |
| `observation` | `continue_btpc_l2_shadow_observation_with_proxy_context` | `bear_pullback_would_enter` | `False` |

## Next

- `execute_btpc_l2_fact_source_and_classifier_review_tasks_locally`
