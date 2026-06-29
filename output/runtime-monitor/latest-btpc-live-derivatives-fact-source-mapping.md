# BTPC Live Derivatives Fact Source Mapping

## Summary

- Status: `btpc_live_derivatives_fact_source_mapping_ready_without_live_authority`
- Source mappings: `8/8`
- Source attachments pending: `8`
- Live RequiredFacts satisfied by mapping: `false`
- L2 promotion authority: `false`
- L4 scope change: `false`

## Source Rows

| Fact | Source route | Mapping | Live fact | Exchange write |
| --- | --- | --- | --- | --- |
| `funding_72h` | `perp_funding_rate_history_window` | `True` | `False` | `False` |
| `perp_spot_premium` | `perp_mark_index_or_spot_premium_window` | `True` | `False` | `False` |
| `open_interest_or_crowding_proxy` | `open_interest_snapshot_or_crowding_proxy` | `True` | `False` | `False` |
| `historical_open_interest_window` | `open_interest_history_window` | `True` | `False` | `False` |
| `historical_global_long_short_ratio_window` | `global_long_short_account_ratio_history_window` | `True` | `False` | `False` |
| `top_trader_position_ratio_window` | `top_trader_position_ratio_history_window` | `True` | `False` | `False` |
| `short_squeeze_risk` | `short_squeeze_disable_classifier_from_live_derivatives_features` | `True` | `False` | `False` |
| `real_exchange_margin_liquidation_model` | `exchange_leverage_bracket_margin_and_symbol_filter_model` | `True` | `False` | `False` |

## Next

- `review_btpc_conflict_and_freshness_classifier_rules_before_any_l2_promotion_review`
