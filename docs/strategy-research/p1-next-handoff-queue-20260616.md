# P1 Next Handoff Queue

Status: ACTIVE_P1_QUEUE
Last updated: 2026-06-16

## Scope

This queue identifies which non-handoff candidates should be converted next
into main-control-reviewable handoff drafts.

P1 does not require a candidate to be promotion-ready. It requires the
candidate to have a stable semantic shape, explicit blockers, RequiredFacts,
sample packet expectations, and non-execution flags.

## Queue

| Rank | Candidate | Current Status | Handoff Target | Reason |
| ---: | --- | --- | --- | --- |
| 1 | `VCB-001` | `observe_only handoff draft plus signal-time boundary complete` | Observe-only true-breakout classifier handoff draft. | Completed in `strategy-group-handoffs/VCB-001/` and `vcb-signal-time-classifier-boundary-20260616.md`; broad breakout remains negative and armed observation remains blocked. |
| 2 | `RSR-001` | `observe_only scorer handoff draft plus standalone boundary complete` | TEQ support scorer packet or conditional scorer handoff draft. | Completed in `strategy-group-handoffs/RSR-001/` and `rsr-scorer-standalone-boundary-20260616.md`; it supports TEQ interpretation but remains blocked as standalone armed observation. |
| 3 | `NLPD-001` | `observe_only event-study handoff draft plus low-history boundary complete` | Low-history event-study observer draft. | Completed in `strategy-group-handoffs/NLPD-001/` and `nlpd-low-history-event-boundary-20260616.md`; event labels are useful but low-history, survivorship, spread/liquidity, and executable-side facts block armed observation. |
| 4 | `LCF-001` | `RequiredFacts design plus facts-pipeline boundary complete; facts still missing` | RequiredFacts design packet only. | Added `lcf-liquidation-cascade-requiredfacts-design-20260616.md` and `lcf-facts-pipeline-boundary-20260616.md`; still cannot be handoff-ready until force-order, OI, long-short, depth, ADL, and margin facts exist. |
| 5 | `MDS-001` | `overlay note complete; not standalone` | PMR-adjacent overlay note. | Added `mds-metals-dislocation-overlay-note-20260616.md`; useful for metals dislocation and session mismatch, but not yet a standalone strategy group. |

## VCB-001 Handoff Draft Scope

| Field | Draft Decision |
| --- | --- |
| Strategy role | `observe_only` true-breakout classifier lane. |
| Supported side | Long first; short/fade is negative or separate redesign evidence. |
| Positive evidence | `true_breakout_followthrough` has `908.444211%` full 1x and `440.884098%` best 90d 2x in offline label replay. |
| Negative evidence | Broad `all_breakouts` is `-77.092301%` full 1x; `false_breakout_reversal` is `-98.261028%` full 1x. |
| Main blocker | Pre-entry filters do not reproduce the post-entry true-breakout edge. |
| RequiredFacts | `compression_state`, `relative_volume_state`, `breakout_strength_state`, `false_breakout_state`, `cost_sensitivity_state`, `slot_m2m_equity_state`, `leverage_ruin_state`. |
| Handoff mode | `observe_only`; no armed observation until pre-entry classifier improves full-sequence behavior. |

P1 supplement:
`vcb-signal-time-classifier-boundary-20260616.md` separates signal-time
breakout facts from post-entry true/false labels. `true_breakout_followthrough`
is a research target only, not a fresh signal or candidate-preparation fact.

## RSR-001 Handoff Draft Scope

| Field | Draft Decision |
| --- | --- |
| Strategy role | TEQ support scorer / relative-strength context. |
| Supported side | Long only in current evidence. |
| Positive evidence | `teq_rsr_72h_strict_top2_hold72__index_confirmed` reaches full 2x `146.393744%` with best 30d 2x `330.020006%`. |
| Negative evidence | Second-half 2x remains `-27.303456%`; broader rows have severe drawdown. |
| Main blocker | Late-sample decay, session/fill, product risk, mark/funding, and real margin. |
| RequiredFacts | `relative_strength_rotation_state`, `reference_index_mapping_state`, `rotation_decay_disable_state`, `rank_priority_reslot_state`, `index_confirmed_rotation_state`, `equity_session_gap_state`, `exchange_margin_liquidation_state`. |
| Handoff mode | `observe_only_scorer`; it may support TEQ but should not be standalone armed observation yet. |

P1 supplement:
`rsr-scorer-standalone-boundary-20260616.md` separates TEQ support scoring,
Strategy Picker ranking language, decay-classifier research, and standalone
activation blockers.

## NLPD-001 Handoff Draft Scope

| Field | Draft Decision |
| --- | --- |
| Strategy role | Low-history new-listing / contract-event observer. |
| Supported side | Long continuation first; short/fade labels are analysis-only unless the venue supports execution. |
| Positive evidence | bStocks first-window dispersion and delayed label design are reproducible with closed 1h candles. |
| Negative evidence | Only 6 bStocks spot symbols and short refreshed histories; absolute payoff ceiling is still below right-tail promotion relevance. |
| Main blocker | Low-history, survivorship, spread/liquidity, product risk, and executable-side ambiguity. |
| RequiredFacts | `listing_event_time`, `first_trade_window_ohlcv`, `low_history_dataset_state`, `quote_volume_floor`, `spread_proxy_state`, `survivorship_control`, `short_executable_state`, `instrument_product_risk_state`. |
| Handoff mode | `observe_only`; event-study watcher only. |

P1 supplement:
`nlpd-low-history-event-boundary-20260616.md` separates listing-event
observation, first-session continuation labels, delayed fade labels, bStocks
low-history cohort facts, spot-short analysis-only labels, and PMR disable
overlay context.

## LCF-001 RequiredFacts Design Scope

| Field | Draft Decision |
| --- | --- |
| Strategy role | Liquidation-cascade follow-through RequiredFacts design task. |
| Supported side | Long and short remain research hypotheses only. |
| Positive evidence | Forced-flow cascade thesis is high-potential for small-capital right-tail windows; derivatives endpoint field shapes are capturable in current public snapshots. |
| Negative evidence | No local force-order stream, historical OI, historical long-short, top-trader, ADL, depth/slippage, or exchange-margin dataset is attached. |
| Main blocker | It cannot distinguish true liquidation cascade from ordinary price volatility without `force_order_event_stream`, `liquidation_cluster_state`, historical OI, positioning ratios, depth/slippage, ADL, and margin-model facts. |
| RequiredFacts | `force_order_event_stream`, `liquidation_cluster_state`, `historical_open_interest_window`, `global_long_short_ratio_window`, `top_trader_position_ratio_window`, `adl_quantile_state`, `orderbook_depth_slippage_state`, `real_exchange_margin_liquidation_model`. |
| Handoff mode | No handoff yet; keep as `facts_pipeline_required` until the data pipeline exists. |

P1 supplement:
`lcf-facts-pipeline-boundary-20260616.md` defines `lcf_facts_absent`,
`lcf_field_shape_observed`, `lcf_minimum_observable`, `lcf_replay_ready`, and
`lcf_handoff_candidate`. Missing facts must emit `facts_missing_no_signal`,
not weak signal or candidate preparation.

## MDS-001 Overlay Note Scope

| Field | Draft Decision |
| --- | --- |
| Strategy role | PMR-adjacent metals dislocation and session-mismatch overlay. |
| Supported side | `long_context` and `short_context`; not standalone long/short execution. |
| Positive evidence | `pmr_metal_relative_breakdown_short_72h` has full 2x `61.335549%`, best-30d 2x `74.904336%`, and best-90d 2x `52.642224%`; PMR regular-session short has right-tail windows but high drawdown. |
| Negative evidence | Broad metal long momentum fails; PMR has `0` 1x/2x right-tail gate rows in expanded-universe review; useful 5x rows are observation-only. |
| Main blocker | It is target-specific overlay vocabulary, not a stable activation/disable pair. |
| RequiredFacts | `instrument_type`, `metal_role_split_state`, `xag_dominance_state`, `commodity_session_gap_state`, `mark_deviation_bound_state`, `funding_rate_window`, `spread_fill_state`, `overlay_target_pairing_coverage_state`, `target_specific_overlay_effect_state`, `real_margin_model_state`. |
| Handoff mode | No handoff yet; keep as `overlay_candidate` until target-specific overlay coverage and activation/disable semantics improve. |

## P1 Next Actions

1. Keep `VCB-001` observe-only after
   `vcb-signal-time-classifier-boundary-20260616.md`; next evidence task is
   classifier redesign that improves full-sequence behavior without post-entry
   labels.
2. Keep `RSR-001` as observe-only scorer until second-half decay,
   session/fill, product-risk, mark/funding, and margin facts improve; current
   scorer/standalone boundary is
   `rsr-scorer-standalone-boundary-20260616.md`.
3. Keep `NLPD-001` as event-study observer until broader listing cohort,
   survivorship, spread/liquidity, product-risk, and executable-side facts
   improve; current low-history event boundary is
   `nlpd-low-history-event-boundary-20260616.md`.
4. Keep `LCF-001` as a RequiredFacts and facts-pipeline design task after
   `lcf-liquidation-cascade-requiredfacts-design-20260616.md` and
   `lcf-facts-pipeline-boundary-20260616.md`; do not create a handoff until
   force-order, liquidation-cluster, OI, ratio, depth, ADL, and margin facts
   exist in replay-aligned form.
5. Keep `MDS-001` as overlay research unless it develops a standalone
   activation/disable pair; current overlay note is
   `mds-metals-dislocation-overlay-note-20260616.md`.
