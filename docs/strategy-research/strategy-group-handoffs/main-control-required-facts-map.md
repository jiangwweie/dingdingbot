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

P0 drawdown supplement:
`docs/strategy-research/mpg-member-drawdown-disable-addendum-20260616.md`.

| Drawdown Fact | Normalized Fact | Missing Behavior |
| --- | --- | --- |
| `mpg_member_drawdown_forensic_state` | Retrospective member/symbol/month attribution | `review_only_warning` |
| `mpg_member_disable_candidate_state` | Versioned prefix-safe member disable hypothesis | `do_not_member_filter` |
| `mpg_member_recent_loss_cluster_state` | Rolling member loss cluster from already-known outcomes | `no_member_downshift` |
| `mpg_signal_extension_state` | Signal-time body/prior-return impulse extension | `block_late_cycle_candidate_prepare` |
| `mpg_drawdown_phase_watch_state` | Realized observation drawdown watch state | `observe_only_or_pause_review` |
| `mpg_exit_horizon_tradeoff_state` | 12h tradeoff versus 72h revival selection | `block_candidate_prepare` |

### `FBS-001`

| RequiredFact | Normalized Fact | Missing Behavior |
| --- | --- | --- |
| `funding_rate_window` | `funding_rate_window` | `observe_only_or_block_fbs` |
| `basis_or_premium_window` | `basis_or_premium_window` | `observe_only_for_fbs` |
| `open_interest_value_change` | `open_interest_value_change` | `degrade_confidence_or_block_promotion` |
| `negative_funding_crowding_state` | Funding plus crowding composite | `no_signal` |
| `funding_settlement_timing_state` | Funding timing policy | `block_candidate_prepare` |
| `mark_deviation_state` | `mark_price_state` | `block_armed_observation_for_perps` |

P0 readiness supplement:
`docs/strategy-research/fbs-derivatives-facts-readiness-split-20260616.md`.

| Readiness State | Main-Control Meaning | Candidate Prepare |
| --- | --- | --- |
| `fbs_derivatives_facts_fresh` | Funding, mark, premium/basis, OI, global long-short, top-trader ratio, and symbol rules are current. | Can be considered after all main-control account, exchange, protection, runtime, and freshness gates pass. |
| `fbs_derivatives_facts_partial` | Funding and mark are current, but OI or crowding ratios are absent or field-shape-only. | Block from research semantics alone; keep observe-only context. |
| `fbs_derivatives_facts_stale` | Funding, mark, OI, or crowding facts are outside freshness policy. | Block and emit stale packet. |
| `fbs_derivatives_facts_missing` | Primary funding, mark, or exchange symbol facts are missing. | Block and emit no-signal or facts-missing packet. |
| `fbs_margin_model_missing` | Real exchange margin/liquidation model is absent. | Block leverage promotion. |

### `TEQ-001`

| RequiredFact | Normalized Fact | Missing Behavior |
| --- | --- | --- |
| `theme_momentum_state` | Closed-candle strategy evaluator state | `no_signal` |
| `basket_breadth_state` | Strategy concentration review | `degrade_confidence` |
| `symbol_concentration_state` | Strategy concentration review | `require_operator_review` |
| `session_gap_context` | `session_window_state` | `block_candidate_prepare` |
| `product_eligibility_state` | Exchange/product policy | `observe_only` |
| `mark_funding_review_state` | Mark and funding facts | `block_armed_observation_for_perps` |

P0 availability supplement:
`docs/strategy-research/teq-current-product-availability-refresh-20260616.md`.

| Availability State | Main-Control Meaning | Candidate Prepare |
| --- | --- | --- |
| `teq_current_product_visible` | Research symbol is visible in current exchangeInfo and exchange rules are present. | Can be considered after all other RequiredFacts pass. |
| `teq_cached_research_only` | Cached 2026 research symbol is not visible in current exchangeInfo. | Block candidate prepare; keep research/strategy-picker context only. |
| `teq_symbol_mapping_unclear` | Cached symbol may have changed or cannot be mapped to current symbol. | Block watcher binding until mapping review. |
| `teq_low_history_event_only` | bStocks or recent symbols have low history. | Observe event-study only; block promotion. |

### `PMR-001`

| RequiredFact | Normalized Fact | Missing Behavior |
| --- | --- | --- |
| `metal_role_split_state` | Strategy role classifier | `observe_only` |
| `xag_dominance_state` | Strategy concentration review | `require_operator_review` |
| `pmr_regular_breakdown_state` | Closed-candle strategy evaluator state | `no_signal` |
| `commodity_session_gap_state` | `session_window_state` | `observe_only` |
| `mark_deviation_bound_state` | `mark_price_state` | `block_armed_observation_for_perps` |
| `gold_token_context_state` | Product/context policy | `context_only` |

P0 role-split supplement:
`docs/strategy-research/pmr-overlay-role-split-20260616.md`.

| Role-Split Fact | Normalized Fact | Missing Behavior |
| --- | --- | --- |
| `pmr_role_branch_state` | Strategy role classifier branch | `observe_only_no_candidate` |
| `pmr_target_overlay_policy_state` | Target-strategy overlay mapping | `block_overlay_application` |
| `nlpd_pmr_disable_state` | NLPD-specific PMR disable/downshift condition | `no_disable_tag` |
| `teq_pmr_support_state` | TEQ-specific PMR support annotation | `no_support_tag` |
| `pmr_standalone_short_block_state` | Standalone PMR short block | `block_candidate_prepare` |
| `pmr_broad_long_negative_state` | Broad metal-long negative evidence | `block_long_claim` |
| `pmr_regular_xag_short_watch_state` | XAG-led regular-session short watchlist | `no_signal` |
| `stop_vs_right_tail_tradeoff_state` | Stop-risk versus right-tail tradeoff | `observe_only` |

### `SOR-001`

| RequiredFact | Normalized Fact | Missing Behavior |
| --- | --- | --- |
| `session_open_range_state` | Session policy plus closed candles | `block_signal_eval` |
| `session_breakout_trigger_state` | Closed trigger candle | `block_signal_eval` |
| `tradfi_session_mapping_state` | `session_window_state` | `block_candidate_prepare` |
| `time_stop_exit_horizon_state` | Strategy exit-plan state | `block_candidate_prepare` |
| `post_open_decay_disable_state` | Strategy disable state | `block_or_downshift` |
| `mark_funding_session_review_state` | Mark and funding facts | `block_armed_observation_for_perps` |

P0 branch supplement:
`docs/strategy-research/sor-branch-eligibility-time-stop-20260616.md`.

| Branch Fact | Normalized Fact | Missing Behavior |
| --- | --- | --- |
| `sor_branch_eligibility_state` | Branch-specific SOR classifier state | `block_candidate_prepare` |
| `sor_time_stop_72h_state` | Versioned 72h time-stop state | `block_candidate_prepare` |
| `sor_teq_short_decisive_breakdown_state` | TEQ short decisive-breakdown branch classifier | `no_signal` |
| `sor_teq_short_volume_downgrade_state` | TEQ short volume-confirmed downgrade after raw-pool reslot | `revival_only` |
| `sor_teq_long_revival_state` | TEQ long ORB revival-only state | `block_long_candidate_prepare` |
| `sor_pmr_short_decay_state` | PMR short second-half and post-open decay state | `conditional_observation_only` |
| `sor_broad_orb_block_state` | Broad ORB promotion block | `block_broad_sor_candidate` |
| `sor_5x_proxy_risk_state` | High-leverage proxy risk state | `block_leverage_promotion` |

### `VCB-001`

| RequiredFact | Normalized Fact | Missing Behavior |
| --- | --- | --- |
| `compression_state` | Closed-candle compression state | `no_signal` |
| `breakout_strength_state` | Closed-candle breakout strength over prior high | `no_signal` |
| `relative_volume_state` | Pre-entry participation state | `observe_only` |
| `pre_entry_classifier_state` | Signal-time classifier state | `observe_only` |
| `false_breakout_state` | False-breakout disable/downshift state | `block_armed_observation` |
| `cost_sensitivity_state` | Cost and event-slot M2M state | `block_promotion` |
| `slot_m2m_equity_state` | Event-slot realized equity state | `block_promotion` |
| `leverage_ruin_state` | High-leverage stress state | `block_leverage_promotion` |

P1 signal-time boundary supplement:
`docs/strategy-research/vcb-signal-time-classifier-boundary-20260616.md`.

| Boundary Fact | Normalized Fact | Missing Behavior |
| --- | --- | --- |
| `vcb_signal_time_fact_state` | Confirms only pre-entry closed-candle facts are used. | `no_signal` |
| `vcb_post_entry_label_boundary_state` | Confirms true/false labels are analysis-only. | `block_candidate_prepare` |
| `vcb_pre_entry_classifier_quality_state` | Current classifier quality and full-sequence result. | `observe_only` |
| `vcb_false_breakout_disable_state` | Bounded or unbounded false-breakout risk. | `block_armed_observation` |
| `vcb_cost_m2m_state` | Cost and event-slot equity evidence. | `block_promotion` |
| `vcb_spread_depth_state` | Live-like spread/depth fact availability. | `block_promotion` |
| `vcb_mark_index_state` | Futures mark/index interpretation. | `block_promotion` |
| `vcb_leverage_ruin_state` | 3x/5x promotion risk. | `block_leverage_promotion` |

### `RSR-001`

| RequiredFact | Normalized Fact | Missing Behavior |
| --- | --- | --- |
| `relative_strength_rotation_state` | Closed-candle relative-strength rank state | `no_score` |
| `reference_index_mapping_state` | QQQ/SPY reference mapping | `no_score` |
| `rank_priority_reslot_state` | Signal-time rank priority and slot competition | `observe_only` |
| `rotation_concentration_state` | Basket concentration and top-symbol share | `observe_only` |
| `rotation_decay_disable_state` | Second-half and post-window decay state | `block_candidate_prepare` |
| `index_confirmed_rotation_state` | QQQ/SPY non-negative confirmation state | `observe_only` |
| `equity_session_gap_state` | 24/7 Binance versus equity-session gap state | `block_promotion` |
| `exchange_margin_liquidation_state` | Real margin and liquidation interpretation | `block_leverage_promotion` |

P1 scorer boundary supplement:
`docs/strategy-research/rsr-scorer-standalone-boundary-20260616.md`.

| Boundary Fact | Normalized Fact | Missing Behavior |
| --- | --- | --- |
| `rsr_role_state` | Support scorer, picker rank hint, classifier candidate, or standalone blocked. | `observe_only` |
| `rsr_primary_strategy_binding_state` | Primary strategy RSR supports, usually `TEQ-001`. | `no_support_annotation` |
| `rsr_standalone_block_state` | Confirms RSR is not the primary activation source. | `block_candidate_prepare` |
| `rsr_decay_classifier_state` | Second-half decay and classifier quality. | `observe_only` |
| `rsr_index_reference_state` | QQQ/SPY reference freshness and mapping. | `no_score` |
| `rsr_rank_priority_state` | Signal-time rank and slot priority. | `no_score` |
| `rsr_longer_lookback_negative_state` | 120h broad rotation negative evidence. | `block_broad_rsr` |
| `rsr_high_leverage_block_state` | 3x/5x stress and disable boundary. | `block_leverage_promotion` |

### `NLPD-001`

| RequiredFact | Normalized Fact | Missing Behavior |
| --- | --- | --- |
| `listing_event_time` | Auditable listing or first-seen event time | `no_event_signal` |
| `first_trade_window_ohlcv` | First closed 1h window state | `no_event_signal` |
| `post_listing_delay_state` | Closed-candle delay before label formation | `block_candidate_prepare` |
| `low_history_dataset_state` | Low-history blocker state | `observe_only` |
| `quote_volume_floor` | Listing-window volume floor | `observe_only_or_block` |
| `spread_proxy_state` | Spread and liquidity proxy | `block_promotion` |
| `survivorship_control` | Failed/missing/renamed symbol control | `block_cohort_claim` |
| `instrument_product_risk_state` | bStocks, TradFi perps, metal tokens, or normal crypto class | `block_promotion` |
| `short_executable_state` | Whether short/fade labels are executable or analysis-only | `block_short_candidate` |

P1 low-history boundary supplement:
`docs/strategy-research/nlpd-low-history-event-boundary-20260616.md`.

| Boundary Fact | Normalized Fact | Missing Behavior |
| --- | --- | --- |
| `nlpd_event_source_state` | Official or auditable event source. | `no_event_signal` |
| `nlpd_first_window_completeness_state` | Required first-window candles are complete. | `no_event_signal` |
| `nlpd_low_history_block_state` | Low-history cohort is not promotion-grade. | `observe_only` |
| `nlpd_survivorship_control_state` | Missing, failed, or unavailable symbols are accounted for. | `block_cohort_claim` |
| `nlpd_product_class_state` | Product class is separated. | `block_promotion` |
| `nlpd_spread_liquidity_state` | Spread and liquidity facts are reproducible. | `block_promotion` |
| `nlpd_short_executable_state` | Short/fade labels are executable or analysis-only. | `block_short_candidate` |
| `nlpd_post_entry_label_boundary_state` | Event labels are research targets, not runtime entry facts. | `block_candidate_prepare` |
| `nlpd_pmr_disable_overlay_state` | PMR downshift/disable context for NLPD continuation labels. | `no_disable_annotation` |

### `DMI-001`

`DMI-001` is an observe-only handoff draft. This mapping exists to let main
control evaluate a directional-ignition watcher without treating generic ADX,
short-side DMI, or metal rows as executable evidence.

| RequiredFact | Normalized Fact | Missing Behavior |
| --- | --- | --- |
| `dmi_adx_trend_strength_state` | Closed-candle ADX >= 25 and rising trend-strength state. | `no_dmi_signal` |
| `dmi_directional_spread_state` | +DI / -DI direction and spread state. | `no_dmi_signal` |
| `dmi_di_cross_state` | Directional movement cross context. | `block_generic_dmi_claim` |
| `directional_decay_disable_state` | Late-window or post-ignition decay state. | `observe_only` |
| `dmi_asset_role_state` | Equity-like versus precious-metal role split. | `block_broad_asset_claim` |
| `dmi_raw_pool_classifier_state` | Signal-time classifier provenance. | `block_candidate_prepare` |
| `dmi_exit_horizon_state` | 24h time-stop state for the current lead row. | `block_candidate_prepare` |
| `dmi_fill_gap_slippage_sensitivity_state` | Deterministic extra-cost stress state. | `observe_only_or_block_promotion` |
| `dmi_extra_cost_tolerance_state` | Maximum tolerated extra round-trip cost. | `block_candidate_prepare` |
| `dmi_live_spread_proxy_state` | Live-like spread or bid/ask proxy. | `block_promotion` |
| `dmi_low_history_product_risk_state` | Product and short-history risk state for equity-like perps. | `observe_only` |
| `fill_gap_slippage_state` | Next-open and 24h exit fill/gap/slippage state. | `block_promotion` |
| `real_exchange_margin_liquidation_model` | Venue-specific margin and liquidation behavior. | `block_leverage_promotion` |

DMI handoff pack:
`docs/strategy-research/strategy-group-handoffs/DMI-001/handoff.md`.

### `SCF-001`

`SCF-001` is an observe-only handoff draft. This mapping exists to let main
control evaluate prefix-safe session-confluence watcher semantics without
treating later structure labels, PMR support rows, or high-leverage stress rows
as executable evidence.

| RequiredFact | Normalized Fact | Missing Behavior |
| --- | --- | --- |
| `base_session_transfer_state` | Existing session-transfer raw-pool signal state. | `no_scf_signal` |
| `session_confluence_state` | Same-symbol same-direction structure confirmation state. | `no_scf_signal` |
| `session_vwap_or_opening_range_state` | VWAP or SOR structure available before the base signal. | `observe_only_or_no_signal` |
| `session_imbalance_gap_state` | Session-gap or FVG structure available before the base signal. | `observe_only_or_no_signal` |
| `pmr_session_breakdown_structure_state` | PMR / XAG short-confluence context state. | `support_only_no_candidate` |
| `session_multi_structure_state` | Multiple structure sources are present and prefix-safe. | `observe_only` |
| `structure_confluence_count_state` | Count of prior confluence structures inside the 24h lookback. | `no_scf_signal` |
| `confluence_prefix_state` | Confirms confluence timestamp is not after the base signal. | `block_candidate_prepare` |
| `teq_strong_momentum_state` | TEQ prior 24h and 72h strength state for current lead. | `no_scf_signal` |
| `session_confluence_drawdown_state` | Drawdown and window-risk interpretation. | `observe_only` |
| `scf_exit_horizon_state` | 12h time-stop state for the current lead row. | `block_candidate_prepare` |
| `scf_time_stop_tradeoff_state` | 12h cleaner row versus 72h higher-window/higher-risk row. | `observe_only` |
| `scf_raw_pool_reslot_state` | Raw-pool and slot reslot provenance. | `block_promotion` |
| `high_leverage_confluence_disable_state` | 3x/5x stress and high-leverage disable state. | `block_leverage_promotion` |
| `scf_fill_gap_slippage_state` | Next-open and session fill/gap/slippage state. | `block_promotion` |
| `real_exchange_margin_liquidation_model` | Venue-specific margin and liquidation behavior. | `block_leverage_promotion` |

SCF handoff pack:
`docs/strategy-research/strategy-group-handoffs/SCF-001/handoff.md`.

### `LCF-001`

`LCF-001` is not a handoff pack. This mapping exists only to preserve the
facts-pipeline boundary for future main-control review.

| RequiredFact | Normalized Fact | Missing Behavior |
| --- | --- | --- |
| `force_order_event_stream` | Forced-liquidation event stream or archive. | `no_lcf_signal` |
| `liquidation_cluster_state` | Clustered liquidation pressure derived from force-order events. | `block_handoff` |
| `historical_open_interest_window` | Replay-aligned historical OI window. | `block_handoff` |
| `global_long_short_ratio_window` | Replay-aligned broad account-side positioning window. | `block_handoff` |
| `top_trader_position_ratio_window` | Replay-aligned top-trader positioning window. | `block_handoff` |
| `adl_quantile_state` | ADL or liquidation-engine stress proxy. | `observe_only_no_handoff` |
| `orderbook_depth_slippage_state` | Depth, spread, and slippage around cascade periods. | `block_promotion` |
| `real_exchange_margin_liquidation_model` | Venue-specific margin and liquidation behavior. | `block_leverage_promotion` |

P1 facts-pipeline supplement:
`docs/strategy-research/lcf-facts-pipeline-boundary-20260616.md`.

| Pipeline Fact | Main-Control Meaning | Missing Behavior |
| --- | --- | --- |
| `lcf_fact_pipeline_state` | Overall LCF fact-pipeline readiness state. | `no_lcf_signal` |
| `lcf_force_order_stream_state` | Force-order stream or archive is reproducibly captured. | `block_handoff` |
| `lcf_liquidation_cluster_state` | Clustered liquidation pressure is generated from force-order events. | `block_handoff` |
| `lcf_historical_oi_state` | Historical OI windows align to candidate candles. | `block_handoff` |
| `lcf_positioning_ratio_state` | Global and top-trader positioning windows align to candidate candles. | `block_handoff` |
| `lcf_adl_stress_state` | ADL or equivalent liquidation stress proxy exists. | `observe_only_no_handoff` |
| `lcf_depth_slippage_state` | Depth, spread, and slippage facts are present. | `block_promotion` |
| `lcf_margin_model_state` | Exchange margin and liquidation model is present. | `block_leverage_promotion` |
| `lcf_no_signal_when_facts_missing_state` | Missing facts emit no-signal rather than weak signal. | `block_handoff_if_absent` |

### `MDS-001`

`MDS-001` is not a handoff pack. This mapping exists only to preserve
target-specific overlay semantics for future main-control review.

| RequiredFact | Normalized Fact | Missing Behavior |
| --- | --- | --- |
| `instrument_type` | Metal perp, gold token, copper, or related product class. | `block_standalone_claim` |
| `metal_role_split_state` | Long context, short weakness, hedge, support, or disable role. | `observe_only_no_candidate` |
| `xag_dominance_state` | Whether the useful evidence is XAG-led rather than broad basket. | `block_broad_basket_claim` |
| `commodity_session_gap_state` | Commodity regular/off-hours/weekend mismatch state. | `observe_only` |
| `overlay_target_pairing_coverage_state` | Whether target strategy events overlap PMR/MDS evidence. | `no_overlay_policy` |
| `target_specific_overlay_effect_state` | Target-specific NLPD disable or TEQ support effect. | `no_overlay_policy` |
| `spread_fill_state` | Spread, depth, and next-open fill suitability. | `block_promotion` |
| `real_margin_model_state` | Metal-perp margin and liquidation interpretation. | `block_leverage_promotion` |

P1 target-pairing supplement:
`docs/strategy-research/mds-target-pairing-boundary-20260616.md`.

| Boundary Fact | Main-Control Meaning | Missing Behavior |
| --- | --- | --- |
| `mds_overlay_role_state` | Context, disable tag, support tag, or standalone blocked. | `observe_only_no_candidate` |
| `mds_target_pairing_state` | Direct PMR/MDS overlap exists for the target strategy. | `no_overlay_policy` |
| `mds_target_policy_state` | Target-specific policy is known. | `no_overlay_policy` |
| `historical_pmr_coverage_state` | Older 2024-2025 candidates have usable PMR/MDS coverage. | `coverage_missing_no_policy` |
| `mds_pmr_state_freshness` | PMR/MDS state is fresh enough for overlay tagging. | `no_overlay_tag` |
| `mds_session_mismatch_state` | Session mismatch is classified. | `observe_only` |
| `mds_xag_dominance_state` | XAG-led concentration is disclosed. | `block_broad_basket_claim` |
| `mds_spread_fill_state` | Spread, depth, and fill facts exist. | `block_promotion` |
| `mds_margin_model_state` | Real margin/liquidation model exists. | `block_leverage_promotion` |

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
