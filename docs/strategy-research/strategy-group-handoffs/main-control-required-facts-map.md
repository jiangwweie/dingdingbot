# Main-Control RequiredFacts Map

Status: HANDOFF_SUPPLEMENT_READY
Last updated: 2026-06-14

## Purpose

This document maps StrategyGroup RequiredFacts to main-control runtime fact
categories. It is meant to reduce ambiguity when building the RequiredFacts
readiness matrix.

It does not implement fact collection, exchange gateway calls, account reads,
FinalGate checks, Operation Layer calls, or order sizing.

## Normalized Fact Map

| Normalized Fact | Strategy Meaning | Main-Control Possible Source | Missing Behavior |
| --- | --- | --- | --- |
| `closed_candle_state` | Signal must use completed 1h candles only. | Market data / candle store / strategy evaluator. | `block_candidate_prepare` |
| `latest_price` | Current reference price for observation context. | Market data source. | `block_armed_observation` |
| `recent_1h_candles` | Indicator and session calculations. | Candle store / historical OHLCV cache. | `block_signal_eval` |
| `quote_volume_state` | Liquidity and participation proxy. | Candle store / market fact source. | `downshift_or_block_by_strategy` |
| `mark_price_state` | Perp mark/last interpretation. | Exchange derivative market facts. | `block_armed_observation_for_perps` |
| `funding_rate_window` | Funding pressure and FBS signal source. | Exchange derivative facts / funding snapshot. | `observe_only_or_block_fbs` |
| `basis_or_premium_window` | Perp dislocation state. | Exchange derivative facts / premium index source. | `observe_only_for_fbs` |
| `open_interest_value_change` | Crowding, expansion, or deleveraging. | Derivatives facts / OI source. | `degrade_confidence_or_block_promotion` |
| `global_long_short_ratio` | Broad account-side crowding proxy. | Derivatives account ratio facts. | `block_fbs_candidate_prepare` |
| `top_trader_position_ratio` | Higher-margin account positioning proxy. | Derivatives top-trader facts. | `block_fbs_candidate_prepare` |
| `session_window_state` | SOR and TradFi session interpretation. | Session policy / calendar mapping. | `block_sor_candidate_prepare` |
| `same_symbol_position_state` | Prevent duplicate exposure. | Account / position read model. | `block_candidate_prepare` |
| `open_order_same_symbol_state` | Prevent duplicate pending orders. | Account / order read model. | `block_candidate_prepare` |
| `exchange_symbol_rules_state` | Current exchange availability, min notional, step, and tick. | ExchangeInfo / exchange rules cache. | `block_candidate_prepare` |
| `protection_plan_state` | Stop-loss and exit-plan hints exist. | Strategy signal packet plus main-control protection planner. | `block_candidate_prepare` |
| `real_margin_model_state` | Leverage interpretation beyond proxy. | Main-control margin model / exchange rule model. | `block_leverage_promotion` |
| `fill_gap_slippage_state` | Live-like cost and next-open fill risk. | Main-control cost/fill model. | `block_promotion_or_downshift` |

## Strategy-Specific Fact Mapping

### `MPG-001`

| RequiredFact | Normalized Fact | Missing Behavior |
| --- | --- | --- |
| `mpg_member_signal_state` | `closed_candle_state` plus strategy evaluator member state | `no_signal` |
| `mpg_group_pool_selection_state` | Strategy evaluator group selection state | `block_candidate_prepare` |
| `mpg_late_cycle_disable_state` | Strategy evaluator disable state | `block_candidate_prepare` |
| `mpg_exit_horizon_state` | Strategy exit-plan state | `block_candidate_prepare` |
| `mpg_high_leverage_disable_state` | Leverage readiness state | `block_leverage_promotion` |
| `tradfi_offhour_mark_index_state` | Session plus mark state | `downshift_or_block` |

### `FBS-001`

| RequiredFact | Normalized Fact | Missing Behavior |
| --- | --- | --- |
| `funding_rate_window` | `funding_rate_window` | `observe_only_or_block_fbs` |
| `basis_or_premium_window` | `basis_or_premium_window` | `observe_only_for_fbs` |
| `open_interest_value_change` | `open_interest_value_change` | `degrade_confidence_or_block_promotion` |
| `negative_funding_crowding_state` | Funding plus crowding composite | `no_signal` |
| `funding_settlement_timing_state` | Funding timing policy | `block_candidate_prepare` |
| `mark_deviation_state` | `mark_price_state` | `block_armed_observation_for_perps` |

### `TEQ-001`

| RequiredFact | Normalized Fact | Missing Behavior |
| --- | --- | --- |
| `theme_momentum_state` | Closed-candle strategy evaluator state | `no_signal` |
| `basket_breadth_state` | Strategy concentration review | `degrade_confidence` |
| `symbol_concentration_state` | Strategy concentration review | `require_operator_review` |
| `session_gap_context` | `session_window_state` | `block_candidate_prepare` |
| `product_eligibility_state` | Exchange/product policy | `observe_only` |
| `mark_funding_review_state` | Mark and funding facts | `block_armed_observation_for_perps` |

### `PMR-001`

| RequiredFact | Normalized Fact | Missing Behavior |
| --- | --- | --- |
| `metal_role_split_state` | Strategy role classifier | `observe_only` |
| `xag_dominance_state` | Strategy concentration review | `require_operator_review` |
| `pmr_regular_breakdown_state` | Closed-candle strategy evaluator state | `no_signal` |
| `commodity_session_gap_state` | `session_window_state` | `observe_only` |
| `mark_deviation_bound_state` | `mark_price_state` | `block_armed_observation_for_perps` |
| `gold_token_context_state` | Product/context policy | `context_only` |

### `SOR-001`

| RequiredFact | Normalized Fact | Missing Behavior |
| --- | --- | --- |
| `session_open_range_state` | Session policy plus closed candles | `block_signal_eval` |
| `session_breakout_trigger_state` | Closed trigger candle | `block_signal_eval` |
| `tradfi_session_mapping_state` | `session_window_state` | `block_candidate_prepare` |
| `time_stop_exit_horizon_state` | Strategy exit-plan state | `block_candidate_prepare` |
| `post_open_decay_disable_state` | Strategy disable state | `block_or_downshift` |
| `mark_funding_session_review_state` | Mark and funding facts | `block_armed_observation_for_perps` |

## Readiness Levels

| Readiness Level | Meaning |
| --- | --- |
| `signal_eval_ready` | Strategy can evaluate no-signal or signal state. |
| `observe_ready` | Strategy can enter observe-only mode. |
| `armed_observation_ready` | Strategy can prepare fresh candidate packets when a signal appears. |
| `candidate_prepare_ready` | Required market/account/exchange/protection facts are present. |
| `promotion_review_ready` | Margin, fill/gap, session, and concentration facts are strong enough for review. |

## Boundary

This map is a semantic bridge. Main-control still owns actual fact fetching,
runtime readiness, watcher wiring, FinalGate, Operation Layer, budget,
settlement, reconciliation, and review.
