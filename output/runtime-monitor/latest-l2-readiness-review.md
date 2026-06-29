# L2 观察面准备度评审

## Owner 摘要

- Status: `l2_readiness_review_already_enabled`
- Owner state: `coverage_policy_current`
- Conditional L2 candidates: `0`
- Enabled L2 groups: `1`
- Blocked rows: `5`
- Tier policy change: `false`
- L4 scope change: `false`
- Shadow candidate now: `false`

## Readiness Rows

| StrategyGroup | Symbol | Side | Tier | Priority | L2 Readiness | Action | Blocking gaps |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `MI-001` | `SOL/USDT:USDT` | `long` | `unclassified` | `unknown` | `missing_policy` | `require_policy_before_l2_review` | `none` |
| `MI-001` | `BNB/USDT:USDT` | `long` | `unclassified` | `unknown` | `missing_policy` | `require_policy_before_l2_review` | `none` |
| `CPM-RO-001` | `ETH/USDT:USDT` | `long` | `unclassified` | `unknown` | `missing_policy` | `require_policy_before_l2_review` | `none` |
| `BRF-001` | `BTC/USDT:USDT` | `short` | `L1` | `P0_5` | `blocked_requiredfacts_and_squeeze_classifier_needed` | `keep_l1_observe_only_until_rally_failure_context_and_short_squeeze_classifier_are_attached` | `rally_high_and_rejection_context_not_attached_to_runtime_facts, short_squeeze_risk_classifier_missing_from_runtime, separate_brf_l2_intake_dry_run_missing, cost_fill_slot_m2m_and_leverage_boundary_missing` |
| `RBR-001` | `ADA/USDT:USDT` | `short` | `L1` | `P2` | `blocked_parked_negative_evidence` | `keep_l1_or_park_as_range_vocabulary_until_materially_new_classifier_exists` | `fixed_horizon_economic_result_negative, calm_range_m2m_failed, worst_90d_2x_reaches_negative_135_68_percent, trend_invalidation_and_range_quality_facts_missing` |
| `BTPC-001` | `None` | `None` | `L2` | `P0_5` | `l2_shadow_candidate_observation_enabled` | `continue_l2_shadow_candidate_observation_without_l4_scope_change` | `historical_open_interest_window_missing, historical_global_long_short_ratio_window_missing, top_trader_position_ratio_window_missing, real_exchange_margin_liquidation_model_missing` |

## 下一步

- `continue_l2_shadow_candidate_observation_without_l4_scope_change`
