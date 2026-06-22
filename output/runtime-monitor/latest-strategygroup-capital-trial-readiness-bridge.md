## StrategyGroup Capital Trial Readiness Bridge

- Status: capital_trial_readiness_bridge_ready
- Generated: 2026-06-22T15:58:09.910172+00:00
- Output JSON: /Users/jiangwei/Documents/final/output/runtime-monitor/latest-strategygroup-capital-trial-readiness-bridge.json
- Trial Packet v0 JSON: /Users/jiangwei/Documents/final/output/runtime-monitor/latest-strategygroup-capital-trial-packet-v0.json
- Selected non-MPG candidate: BRF2-001
- Selected candidate status: short_candidate_trade_packet_pending_owner_policy
- Trial packet generated: 是
- Actionable now count: 0
- Live permission change count: 0
- Real order authority count: 0

## Selected Candidate

| Field | Value |
| --- | --- |
| StrategyGroup | BRF2-001 |
| Execution Tier | unknown |
| Evidence Stage | paper_observation_admission_candidate |
| Recent opportunities | 11 |
| Forward positive | 8 |
| Symbol scope | owner_policy_required |
| Side scope | short |
| Decision | promote |
| Reason | promote_to_tiny_live_intake_candidate_not_live_ready |
| Promotion scope | intake_only |
| Promotion target | paper_observation_or_candidate_trade_packet |
| Tiny live ready | 否 |
| Next checkpoint | BRF2-001_tiny_live_intake_candidate_packet |
| Recommendation | candidate_trade_prepare_pending_owner_policy |

## Ranking

| Rank | StrategyGroup | Recommendation | Score | Blockers |
| ---: | --- | --- | ---: | --- |
| 1 | BRF2-001 | candidate_trade_prepare_pending_owner_policy | 597 | 3_of_11_cap4_events_hit_5m_stop, strong_reclaim_proxy_catches_stop_hits_but_may_overfilter_positive_events, symbol/date filters that fully remove stop hits are high overfit risk, source_tiny_live_ready_false, owner_capital_scope_not_confirmed, owner_trial_identity_not_confirmed, fresh_signal_absent, action_time_finalgate_not_reached, official_operation_layer_not_reached |
| 2 | RBR2-001 | role_only_short_candidate_trade_watchlist | 390 | 5m_stop_hit_rate_is_high, time_stop_only_overstates_realistic_structural_stop_behavior, best role is filler not main right-tail engine, source_tiny_live_ready_false, owner_capital_scope_not_confirmed, owner_trial_identity_not_confirmed, fresh_signal_absent, action_time_finalgate_not_reached, official_operation_layer_not_reached |
| 3 | MI-001 | trial_prepare_after_owner_identity_and_capital_policy | 307 | registry_identity_or_registry_row_missing, execution_tier_not_in_policy_or_registry, formal_candidate_vs_sub_capability_vs_observe_asset_unresolved, owner_policy_scope_not_confirmed, registry_identity_unresolved, owner_capital_scope_not_confirmed, fresh_signal_absent, action_time_finalgate_not_reached, official_operation_layer_not_reached |
| 4 | CPM-RO-001 | defer_until_identity_or_merge_review_closed | 161 | registry_identity_or_registry_row_missing, execution_tier_not_in_policy_or_registry, would_enter_forward_outcome_pending:12h, would_enter_forward_outcome_pending:24h, formal_candidate_vs_sub_capability_vs_observe_asset_unresolved, owner_policy_scope_not_confirmed, registry_identity_unresolved, owner_capital_scope_not_confirmed, fresh_signal_absent, action_time_finalgate_not_reached, official_operation_layer_not_reached |
| 5 | LSR-001 | defer_until_rewrite_and_range_facts_closed | 44 | would_enter_forward_outcome_pending:24h, no_action_or_classifier_attribution_needs_closure, side_specific_rewrite_not_closed, range_context_required, owner_capital_scope_not_confirmed, fresh_signal_absent, action_time_finalgate_not_reached, official_operation_layer_not_reached |
| 6 | BRF-001 | defer_until_squeeze_requiredfacts_forward_completed | 13 | would_enter_forward_outcome_pending:12h, would_enter_forward_outcome_pending:24h, would_enter_forward_outcome_pending:4h, promote_review_forward_positive_not_completed, owner_policy_scope_not_confirmed, squeeze_classifier_required, requiredfacts_review_required, owner_capital_scope_not_confirmed, fresh_signal_absent, action_time_finalgate_not_reached, official_operation_layer_not_reached |
| 7 | BTPC-001 | defer_until_fact_source_classifier_closed | -90 | no_action_or_classifier_attribution_needs_closure, stale_fact_source_classifier_blocker_unclosed, no_recent_would_enter, owner_capital_scope_not_confirmed, fresh_signal_absent, action_time_finalgate_not_reached, official_operation_layer_not_reached |
