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
| 5 | `MDS-001` | `overlay note plus target-pairing boundary complete; not standalone` | PMR-adjacent overlay note. | Added `mds-metals-dislocation-overlay-note-20260616.md` and `mds-target-pairing-boundary-20260616.md`; useful for target-specific disable/support tags, but not yet a standalone strategy group. |
| 6 | `DMI-001` | `observe_only handoff draft complete from P2 batch` | Equity ADX-rising directional-ignition observer draft. | Completed in `strategy-group-handoffs/DMI-001/`; converted from P2 cabinet extension after exit-horizon and cost-sensitivity evidence clarified a narrow long-only 24h semantic. |
| 7 | `SCF-001` | `observe_only handoff draft complete from P2 batch` | TEQ session-confluence structure-confirmation observer draft. | Completed in `strategy-group-handoffs/SCF-001/`; converted from P2 cabinet extension after exit-horizon evidence clarified a narrow TEQ long 12h semantic. |
| 8 | `MASS-001` | `observe_only handoff draft complete from P2 batch` | Mass Index bulge-reversal observer draft. | Completed in `strategy-group-handoffs/MASS-001/`; converted from P2 cabinet extension because its reversal-long branch is cleaner than EFI's current drawdown profile. |
| 9 | `EFI-001` | `right_tail candidate; drawdown/disable boundary complete; no handoff` | No handoff yet. Preserve negative-force exhaustion reversal as a review lane. | Added `efi-drawdown-disable-boundary-20260616.md`; branch-level right tail is strong, but candidate-level drawdown, high-leverage breakdown, short-side failure, product/session/fill, and margin facts block handoff. |
| 10 | `UO-001` | `observe_only handoff draft complete from P2 batch 2` | Ultimate Oscillator bullish-divergence observer draft. | Completed in `strategy-group-handoffs/UO-001/`; converted from P2 batch 2 because bullish divergence is cleaner than generic UO midline or short-side rows. |

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
| Main blocker | It is target-specific overlay vocabulary, not a stable activation/disable pair; BTPC/DCB/THR coverage is missing or too small for policy claims. |
| RequiredFacts | `instrument_type`, `metal_role_split_state`, `xag_dominance_state`, `commodity_session_gap_state`, `mark_deviation_bound_state`, `funding_rate_window`, `spread_fill_state`, `overlay_target_pairing_coverage_state`, `target_specific_overlay_effect_state`, `real_margin_model_state`. |
| Handoff mode | No handoff yet; keep as `overlay_candidate` until target-specific overlay coverage and activation/disable semantics improve. |

P1 supplement:
`mds-target-pairing-boundary-20260616.md` separates `NLPD-001` PMR disable
tags, `TEQ-001` PMR support tags, and historical coverage-missing policies for
`BTPC-001`, `DCB-001`, and `THR-001`. It also fixes the sample overlay packet
as `overlay_context_only` with `decision=no_candidate`.

## DMI-001 Observe-Only Handoff Draft Scope

| Field | Draft Decision |
| --- | --- |
| Strategy role | ADX/DMI equity-like directional ignition observer. |
| Supported side | Long only in current evidence. |
| Positive evidence | `dmi_long_equity_adx_rising` at `24h` has full 2x `481.350915%`, best 90d 2x `852.623789%`, second-half 2x `254.307331%`, and `0` 2x/5x proxy liquidation events. |
| Negative evidence | Generic DMI overreach, short-side rows, and precious-metal generalization fail current evidence. |
| Main blocker | Cost sensitivity, product/session/fill, live spread, and real exchange-margin facts. |
| RequiredFacts | `dmi_adx_trend_strength_state`, `dmi_directional_spread_state`, `dmi_asset_role_state`, `dmi_exit_horizon_state`, `dmi_fill_gap_slippage_sensitivity_state`, `fill_gap_slippage_state`, `real_exchange_margin_liquidation_model`. |
| Handoff mode | `observe_only`; no armed observation until live-like cost/fill/session/product and margin facts improve. |

## SCF-001 Observe-Only Handoff Draft Scope

| Field | Draft Decision |
| --- | --- |
| Strategy role | Session confluence / structure-confirmed TEQ observer. |
| Supported side | TEQ long first; PMR short remains support-only context. |
| Positive evidence | `teq_regular_strong_any_structure` at `12h` has full 2x `318.065867%`, best 90d 2x `216.167925%`, DD 2x `-22.978941%`, and `0` 2x/5x proxy liquidation events. |
| Negative evidence | 72h row has larger best-window but worse DD and 5x proxy liquidation; PMR confluence does not clear the right-tail gate. |
| Main blocker | Prefix-safe fact binding, fill/gap/session/product risk, time-stop tradeoff, and real margin. |
| RequiredFacts | `base_session_transfer_state`, `session_confluence_state`, `structure_confluence_count_state`, `confluence_prefix_state`, `teq_strong_momentum_state`, `scf_exit_horizon_state`, `scf_fill_gap_slippage_state`, `real_exchange_margin_liquidation_model`. |
| Handoff mode | `observe_only`; no armed observation until live-like fill/session/product and margin facts improve. |

P1 supplement:
`strategy-group-handoffs/SCF-001/handoff.md` separates prefix-safe confluence
facts, TEQ long lead semantics, PMR support-only context, 12h/72h time-stop
tradeoff, and high-leverage disable semantics.

## MASS-001 Observe-Only Handoff Draft Scope

| Field | Draft Decision |
| --- | --- |
| Strategy role | Mass Index range-expansion reversal observer. |
| Supported side | Long first; short and precious-metal rows are support-only or negative. |
| Positive evidence | `mass_bulge_reversal_long_48h` has full 2x `395.155223%`, best 90d 2x `338.952327%`, DD 2x `-10.652922%`, and `0` 2x/5x proxy liquidation events. |
| Negative evidence | Continuation long has larger best-window but DD 2x `-71.259030%`; short-side and precious-metal branches fail or support only. |
| Main blocker | Direction context, symbol concentration, monthly decay, product/session/fill, and real margin. |
| RequiredFacts | `mass_index_state`, `mass_bulge_trigger_state`, `mass_direction_context_state`, `mass_reversal_quality_state`, `mass_range_expansion_continuation_state`, `mass_window_decay_state`, `mass_symbol_concentration_state`, `fill_gap_slippage_state`, `real_exchange_margin_liquidation_model`. |
| Handoff mode | `observe_only`; no armed observation until direction-context, concentration/decay, fill/session/product, and margin facts improve. |

P1 supplement:
`strategy-group-handoffs/MASS-001/handoff.md` separates Mass Index as a
non-directional range-expansion indicator, long reversal lead semantics,
continuation drawdown support semantics, short-side failure facts, and
product/margin blockers.

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
   activation/disable pair; current boundaries are
   `mds-metals-dislocation-overlay-note-20260616.md` and
   `mds-target-pairing-boundary-20260616.md`.
6. Keep `DMI-001` as observe-only after
   `strategy-group-handoffs/DMI-001/handoff.md`; next evidence task is
   live-like spread/gap/session/product and real-margin fact attachment before
   any armed-observation discussion.
7. Keep `SCF-001` as observe-only after
   `strategy-group-handoffs/SCF-001/handoff.md`; next evidence task is
   live-like fill/gap/session/product, prefix-safe confluence fact binding, and
   real-margin review before any armed-observation discussion.
8. Keep `MASS-001` as observe-only after
   `strategy-group-handoffs/MASS-001/handoff.md`; next evidence task is
   direction-context hardening, symbol-concentration review, monthly decay
   disable, and fill/session/product/margin fact attachment.
9. Keep `EFI-001` out of handoff after
   `efi-drawdown-disable-boundary-20260616.md`; next evidence task is a
   signal-time disable classifier for `efi_negative_exhaustion_reversal_long_72h`
   plus product/session/fill and real-margin fact attachment.
10. Keep `UO-001` as observe-only after
    `strategy-group-handoffs/UO-001/handoff.md`; next evidence task is
    divergence-quality hardening, window-persistence review, product/session/fill
    fact attachment, and real-margin review before any armed-observation
    discussion.
