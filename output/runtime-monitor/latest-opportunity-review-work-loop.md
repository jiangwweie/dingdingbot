# StrategyGroup Opportunity Review Work Loop

## Summary

- Status: `review_work_loop_ready`
- Observed opportunities: `6`
- Replay covered: `2`
- L4 scope change: `false`

## Opportunity Review Rows

| StrategyGroup | Tier | Replay | Gaps | Review Work |
| --- | --- | ---: | ---: | --- |
| `MI-001` | `unclassified` | 0 | 0 | `build_replay_corpus_before_l2` |
| `MI-001` | `unclassified` | 0 | 0 | `build_replay_corpus_before_l2` |
| `CPM-RO-001` | `unclassified` | 0 | 0 | `build_replay_corpus_before_l2` |
| `BRF-001` | `L1` | 5 | 4 | `repair_blocking_gaps_with_replay_or_facts` |
| `RBR-001` | `L1` | 0 | 4 | `park_or_vocabulary_only` |
| `BTPC-001` | `L2` | 5 | 5 | `continue_l2_shadow_quality_review` |

## Next

- `feed_btpc_proxy_replay_quality_into_l2_keep_revise_or_fact_source_review`

## Work Queue

| Priority | StrategyGroup | Work | Coverage | Next | Scheduled | Blocks L2 |
| --- | --- | --- | --- | --- | --- | --- |
| `signal-observation-grade-high` | `BRF-001` | `classifier_or_rule_work` | `needs_replay_or_spec` | `add_replay_or_spec_coverage_before_l2` | `true` | `true` |
| `signal-observation-grade-high` | `BRF-001` | `economic_replay_work` | `needs_replay_or_spec` | `add_replay_or_spec_coverage_before_l2` | `true` | `true` |
| `signal-observation-grade-high` | `BTPC-001` | `required_fact_or_market_data_work` | `fact_source_pending` | `attach_fact_source_before_l2_review` | `true` | `false` |
| `signal-observation-grade-high` | `BTPC-001` | `required_fact_or_market_data_work` | `fact_source_pending` | `attach_fact_source_before_l2_review` | `true` | `false` |
| `signal-observation-grade-high` | `BTPC-001` | `required_fact_or_market_data_work` | `fact_source_pending` | `attach_fact_source_before_l2_review` | `true` | `false` |
| `signal-observation-grade-high` | `BTPC-001` | `required_fact_or_market_data_work` | `fact_source_pending` | `attach_fact_source_before_l2_review` | `true` | `false` |
| `signal-observation-grade-high` | `BTPC-001` | `strategy_review_work` | `strategy_review_pending` | `continue_observe_only_review` | `true` | `false` |
| `signal-observation-grade-medium` | `BRF-001` | `required_fact_or_market_data_work` | `fact_source_pending` | `attach_fact_source_before_l2_review` | `true` | `true` |

## Strategy Asset Recommendations

| StrategyGroup | Tier | Decision | Next | Replay | Revise | Coverage Ready | Revision Tasks | Revision Ready | Revision Executed |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `MI-001` | `unclassified` | `needs_replay_before_asset_recommendation` | `add_replay_or_spec_coverage_before_l2` | 0 | 0 | 0 | 0 | 0 | 0 |
| `MI-001` | `unclassified` | `needs_replay_before_asset_recommendation` | `add_replay_or_spec_coverage_before_l2` | 0 | 0 | 0 | 0 | 0 | 0 |
| `CPM-RO-001` | `unclassified` | `needs_replay_before_asset_recommendation` | `add_replay_or_spec_coverage_before_l2` | 0 | 0 | 0 | 0 | 0 | 0 |
| `BRF-001` | `L1` | `continue_observe_only_review` | `continue_observe_only_review` | 5 | 3 | 0 | 0 | 0 | 0 |
| `RBR-001` | `L1` | `park_until_new_edge` | `park_until_new_evidence` | 0 | 0 | 0 | 0 | 0 | 0 |
| `BTPC-001` | `L2` | `keep_l2_shadow_and_revise_fact_classifier_inputs` | `feed_btpc_proxy_replay_quality_into_l2_keep_revise_or_fact_source_review` | 5 | 3 | 0 | 0 | 0 | 0 |
