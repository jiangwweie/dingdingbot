# L2 Intake Dry-Run

## Owner 摘要

- Status: `l2_intake_dry_run_no_candidates`
- Owner state: `waiting_for_opportunity`
- Candidate count: `0`
- Passed count: `0`
- Source enabled L2: `1`
- Source blocked rows: `1`
- No-candidate reason: `no_conditional_l2_review_candidates`
- Tier policy changed: `false`
- L4 scope changed: `false`
- Real order: `false`

## Rows

| StrategyGroup | Status | Next Step |
| --- | --- | --- |
| none | - | - |

## Source Readiness Rows

| StrategyGroup | Symbol | Side | Tier | L2 Readiness | Source State | Blocking gaps |
| --- | --- | --- | --- | --- | --- | --- |
| `RBR-001` | `ADA/USDT:USDT` | `short` | `L1` | `blocked_parked_negative_evidence` | `blocked` | `fixed_horizon_economic_result_negative, calm_range_m2m_failed, worst_90d_2x_reaches_negative_135_68_percent, trend_invalidation_and_range_quality_facts_missing` |
| `BTPC-001` | `None` | `None` | `L2` | `l2_shadow_candidate_observation_enabled` | `enabled_l2` | `historical_open_interest_window_missing, historical_global_long_short_ratio_window_missing, top_trader_position_ratio_window_missing, real_exchange_margin_liquidation_model_missing` |

## 下一步

- `continue_signal_coverage_monitoring`
