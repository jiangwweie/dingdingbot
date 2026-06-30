# BTPC L2 Shadow Fact Quality Review

## Summary

- Status: `btpc_l2_shadow_fact_quality_review_ready`
- Fact gaps: `5`
- Classified: `5`
- Promotion blockers: `5`
- Real-order blockers: `1`
- L2 promotion authority: `false`
- L4 scope change: `false`

## Fact Rows

| Gap | Fact | Class | Coverage | Effect | Next |
| --- | --- | --- | --- | --- | --- |
| `historical_open_interest_window_missing` | `historical_open_interest_window` | `derivatives` | `fact_source_pending` | `blocks_promotion_beyond_l2_review` | `attach_historical_open_interest_window_or_document_proxy` |
| `historical_global_long_short_ratio_window_missing` | `historical_global_long_short_ratio_window` | `derivatives` | `fact_source_pending` | `blocks_promotion_beyond_l2_review` | `attach_global_long_short_ratio_window_or_document_proxy` |
| `top_trader_position_ratio_window_missing` | `top_trader_position_ratio_window` | `derivatives` | `fact_source_pending` | `blocks_promotion_beyond_l2_review` | `attach_top_trader_position_ratio_window_or_document_proxy` |
| `real_exchange_margin_liquidation_model_missing` | `real_exchange_margin_liquidation_model` | `risk` | `fact_source_pending` | `blocks_any_btpc_real_order_eligibility` | `map_research_leverage_to_exchange_margin_liquidation_model` |
| `short_squeeze_risk_not_runtime_blocking` | `short_squeeze_risk` | `derivatives` | `strategy_review_pending` | `strategy_review_pending_not_runtime_blocking` | `record_short_squeeze_review_rule_before_promotion` |

## Next

- `attach_btpc_derivatives_fact_sources_and_margin_model_for_l2_quality_review`
