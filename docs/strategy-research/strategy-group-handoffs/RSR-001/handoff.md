# RSR-001 Strategy Group Handoff Pack

Status: OBSERVE_ONLY_SCORER_HANDOFF_DRAFT_FOR_MAIN_CONTROL_REVIEW
Last updated: 2026-06-16

## Strategy

| Field | Value |
| --- | --- |
| Strategy Group | `RSR-001` |
| Name | Relative Strength Rotation |
| Family | Equity-like relative-strength rotation |
| Default Mode | `observe_only` |
| Execution Status | Research-only scorer; no runtime registration or order authority. |

`RSR-001` is a TEQ-support scorer and relative-strength observation lane. It
should help main control and future Strategy Picker surfaces understand which
equity-like symbols are leading a local theme. It should not be treated as a
standalone armed observation group until second-half decay, fill/session,
product-risk, mark/funding, and real margin facts improve.

## Supported Scope

| Field | Value |
| --- | --- |
| Timeframe | `1h` |
| Primary Side | `long` |
| Reference Symbols | `QQQUSDT`, `SPYUSDT` |
| Research Symbols | `MSTRUSDT`, `COINUSDT`, `CRCLUSDT`, `HOODUSDT`, `PLTRUSDT`, `MUUSDT`, `SNDKUSDT`, `TSLAUSDT`, `NVDAUSDT`, `METAUSDT`, `GOOGLUSDT`, `AVGOUSDT`, `SOXLUSDT` |
| Strategy Relation | Supports `TEQ-001`; separate from `NLPD-001` listing events. |

## Signal Ready Rule

The scorer is ready only when closed-candle relative-strength ranks can be
computed against the reference basket without future returns or post-entry
path fields.

The current research recommendation is observe-only. A fresh RSR packet may
rank candidates, explain TEQ context, or support review, but it must not by
itself prepare an execution candidate.

## RequiredFacts

| RequiredFact | Why |
| --- | --- |
| `relative_strength_rotation_state` | Required for any RSR score. |
| `reference_index_mapping_state` | Required because QQQ/SPY references anchor the score. |
| `rank_priority_reslot_state` | Required because simultaneous entries compete for slots. |
| `rotation_concentration_state` | Required before treating the score as diversified. |
| `rotation_decay_disable_state` | Required because second-half decay remains unresolved. |
| `index_confirmed_rotation_state` | Required for the cleaner strict-top2 classifier lane. |
| `equity_session_gap_state` | Required for Binance 24/7 equity-like perps. |
| `mark_funding_review_state` | Required for levered futures interpretation. |
| `exchange_margin_liquidation_state` | Required before leverage promotion. |
| `product_eligibility_state` | Required before current exchange availability can be trusted. |

## Risk Defaults

| Field | Value |
| --- | --- |
| Interpretation | Research proposal only, not live order-sizing defaults. |
| Risk Tier | `tiny` |
| Default Leverage | `1x` |
| Max Research Leverage | `2x` |
| Stress Only | `3x` |
| Disabled | `5x` |
| Protection | Requires TEQ-side protection plan before any future armed review. |

## Hard Stops

| Hard Stop | Reason |
| --- | --- |
| `standalone_execution_requested` | RSR is a scorer, not an action strategy. |
| `reference_index_mapping_missing` | Score cannot be interpreted without QQQ/SPY mapping. |
| `rank_priority_reslot_missing` | Capacity and simultaneous-symbol conflicts are unresolved. |
| `rotation_decay_unbounded` | Second-half decay remains a blocker. |
| `session_gap_policy_missing` | Equity-like perps require 24/7 versus U.S. session interpretation. |
| `mark_funding_missing` | Levered futures interpretation is blocked. |
| `real_margin_model_missing` | Leverage promotion is blocked. |
| `high_leverage_requested` | 3x is stress-only and 5x is disabled. |
| `same_symbol_active_position_or_open_order` | Prevents duplicate same-symbol exposure. |
| `stale_market_facts` | Blocks scorer interpretation. |
| `missing_exchange_rules` | Blocks runtime consumption. |
| `no_stop_loss_plan` | Blocks any future candidate preparation. |

## Evidence Summary

| Evidence | Result |
| --- | --- |
| Universe | `62` equity-like symbols including `QQQUSDT` and `SPYUSDT` references. |
| Raw signals | `6869` prefix-safe raw signals from closed 1h candles. |
| Baseline 72h top4 | Full 2x `95.623394%`; best 30d 2x `650.990499%`; 2x liquidation proxy `0`. |
| Rank-priority baseline | Full 2x `334.274599%`; best 30d 2x `892.836220%`; max DD 2x `-72.703589%`. |
| Cleaner classifier | `strict_top2__index_confirmed` full 2x `146.393744%`; best 30d 2x `330.020006%`; max DD 2x `-50.994691%`. |
| Main blocker | Cleaner classifier still has second-half 2x `-27.303456%`. |
| Negative rule | `120h_top4_hold120` full 2x `-80.027481%`; longer lookback is negative evidence. |
| Leverage warning | 5x rows include proxy wipeout; high leverage remains stress vocabulary. |

## Sample Packets

Canonical sample packets are in `handoff.json`.

## Main-Control Handoff

Recommendation: consume `RSR-001` as an observe-only scorer draft. It can
support TEQ interpretation, strategy comparison, and future Strategy Picker
ranking language, but it should not become standalone armed observation until
decay and product facts improve.
