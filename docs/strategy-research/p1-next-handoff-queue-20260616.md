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
| 1 | `VCB-001` | `observe_only handoff draft complete` | Observe-only true-breakout classifier handoff draft. | Completed in `strategy-group-handoffs/VCB-001/`; broad breakout remains negative and armed observation remains blocked. |
| 2 | `RSR-001` | `observe_only scorer handoff draft complete` | TEQ support scorer packet or conditional scorer handoff draft. | Completed in `strategy-group-handoffs/RSR-001/`; it supports TEQ interpretation but remains blocked as standalone armed observation. |
| 3 | `NLPD-001` | `research_candidate` | Low-history event-study observer draft. | Listing/event windows are interpretable and source-controlled, but sample breadth and survivorship facts block promotion. |
| 4 | `LCF-001` | `facts_pipeline_required` | RequiredFacts design packet first. | High-potential liquidation-cascade thesis cannot be handoff-ready until force-order, OI, long-short, depth, ADL, and margin facts exist. |
| 5 | `MDS-001` | `overlay_candidate` | PMR-adjacent overlay note. | Useful for metals dislocation and session mismatch, but not yet a standalone strategy group. |

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

## P1 Next Actions

1. Keep `VCB-001` observe-only until a signal-time classifier improves
   full-sequence behavior without post-entry labels.
2. Keep `RSR-001` as observe-only scorer until second-half decay,
   session/fill, product-risk, mark/funding, and margin facts improve.
3. Keep `NLPD-001` as event-study observer until a broader listing cohort
   exists.
4. Record `LCF-001` as a RequiredFacts design task, not a strategy handoff.
5. Keep `MDS-001` as overlay research unless it develops a standalone
   activation/disable pair.
