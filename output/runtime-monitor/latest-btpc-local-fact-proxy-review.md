# BTPC Local Fact Proxy Review

## Summary

- Status: `btpc_local_fact_proxy_review_ready`
- Proxy facts: `5/5`
- Replay samples: `5`
- Margin leverage cases: `4`
- Live RequiredFacts satisfied by proxy: `false`
- L2 promotion authority: `false`
- L4 scope change: `false`

## Proxy Rows

| Fact | Proxy | L2 review | Live fact | Operation layer |
| --- | --- | --- | --- | --- |
| `historical_open_interest_window` | `local_proxy_attached` | `can_review_crowding_direction_in_replay` | `False` | `False` |
| `historical_global_long_short_ratio_window` | `local_proxy_attached` | `can_review_positioning_bias_in_replay` | `False` | `False` |
| `top_trader_position_ratio_window` | `local_proxy_attached` | `can_review_top_trader_crowding_in_replay` | `False` | `False` |
| `real_exchange_margin_liquidation_model` | `local_review_model_attached` | `can_review_research_leverage_bands_without_live_authority` | `False` | `False` |
| `short_squeeze_risk` | `local_review_rule_attached` | `can_keep_short_squeeze_as_strategy_quality_review_input` | `False` | `False` |

## Next

- `run_btpc_l2_shadow_replay_with_local_fact_proxies_and_keep_live_scope_unchanged`
