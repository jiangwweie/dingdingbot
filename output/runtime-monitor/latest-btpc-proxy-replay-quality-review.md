# BTPC Proxy Replay Quality Review

## Summary

- Status: `btpc_proxy_replay_quality_review_ready`
- Replay cases: `5`
- Proxy-reviewable would-enter: `2`
- Missing-derivatives cases resolved for L2 review only: `1`
- Live RequiredFacts satisfied by proxy replay: `false`
- L2 promotion authority: `false`
- L4 scope change: `false`

## Case Rows

| Case | Signal | Proxy status | Decision | Exchange write |
| --- | --- | --- | --- | --- |
| `bear_pullback_would_enter` | `would_enter_observe_only` | `proxy_context_sufficient_for_l2_shadow_review` | `keep_observing_l2_shadow_with_proxy_context` | `False` |
| `no_signal_bear_trend_not_ready` | `no_signal` | `proxy_context_not_required_for_no_action` | `keep_waiting_for_market_no_action_baseline` | `False` |
| `strong_uptrend_conflict` | `signal_conflict` | `proxy_context_available_but_conflict_rule_dominates` | `revise_conflict_disable_before_l2_promotion` | `False` |
| `missing_derivatives_context` | `would_enter_missing_required_facts` | `proxy_context_sufficient_for_l2_shadow_review` | `revise_live_fact_collection_but_l2_proxy_reviewable` | `False` |
| `stale_signal` | `stale_signal` | `proxy_context_available_but_freshness_rule_dominates` | `revise_freshness_or_classifier_before_l2_promotion` | `False` |

## Next

- `feed_btpc_proxy_replay_quality_into_l2_keep_revise_or_fact_source_review`
