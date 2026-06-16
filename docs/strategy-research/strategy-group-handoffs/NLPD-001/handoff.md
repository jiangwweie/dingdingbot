# NLPD-001 Strategy Group Handoff Pack

Status: OBSERVE_ONLY_EVENT_STUDY_HANDOFF_DRAFT_FOR_MAIN_CONTROL_REVIEW
Last updated: 2026-06-16

## Strategy

| Field | Value |
| --- | --- |
| Strategy Group | `NLPD-001` |
| Name | New Listing Price Discovery |
| Family | New-listing / contract-event price discovery |
| Default Mode | `observe_only` |
| Execution Status | Research-only event observer; no runtime registration or order authority. |

`NLPD-001` is a low-history event-study observer for newly listed or newly
available Binance instruments. It is not an always-on listing strategy. Its
current purpose is to preserve short event-window semantics, first-session
continuation labels, delayed fade labels, and product-risk blockers for future
classifier work.

## Supported Scope

| Field | Value |
| --- | --- |
| Timeframe | `1h` |
| Primary Side | Long continuation first. |
| Analysis-Only Side | Short/fade labels are analysis-only unless executable venue facts exist. |
| Event Types | 2026 listing-hint symbols, bStocks spot symbols, TradFi equity perpetuals, tokenized metal / precious-metal contexts. |
| Current Example Symbols | `SNDKUSDT`, `MUUSDT`, `HOODUSDT`, `COINUSDT`, `MUBUSDT`, `SNDKBUSDT`, `TSLABUSDT`, `NVDABUSDT`, `CRCLBUSDT`, `SPCXBUSDT` |

## Signal Ready Rule

The observer is ready only when an event timestamp exists and the candidate
has enough closed 1h candles after listing to compute a delayed label without
using post-entry path information.

The current research recommendation is observe-only. A fresh NLPD packet may
record event-state, first-window behavior, and low-history labels, but it must
not by itself prepare an execution candidate.

## RequiredFacts

| RequiredFact | Why |
| --- | --- |
| `listing_event_time` | Required from official listing, exchangeInfo first-seen time, or an auditable event source. |
| `first_trade_window_ohlcv` | Required because labels depend on first closed 1h candles. |
| `post_listing_delay_state` | Required to prove signal formation uses only closed pre-entry candles. |
| `low_history_dataset_state` | Required blocker before promotion. |
| `quote_volume_floor` | Required before scoring event labels. |
| `spread_proxy_state` | Missing; required before promotion. |
| `survivorship_control` | Missing; required before cohort-level claims. |
| `instrument_product_risk_state` | Required to separate bStocks, TradFi perps, metal tokens, and normal crypto. |
| `short_executable_state` | Required before any short/fade label can be interpreted as executable. |
| `session_gap_policy` | Required for equity-like and commodity-like instruments. |

## Risk Defaults

| Field | Value |
| --- | --- |
| Interpretation | Research proposal only, not live order-sizing defaults. |
| Risk Tier | `tiny` |
| Default Leverage | `1x` |
| Stress Only | `2x`, `3x` |
| Disabled | `5x` |
| Protection | Requires product, liquidity, spread, and executable-side facts before any future armed review. |

## Hard Stops

| Hard Stop | Reason |
| --- | --- |
| `listing_event_time_missing` | Event study cannot form without auditable event time. |
| `first_trade_window_incomplete` | First closed candles are required before labels. |
| `low_history_dataset_unbounded` | Short-history evidence is discovery-only. |
| `survivorship_control_missing` | Cohort claims are blocked without failed/missing-symbol accounting. |
| `spread_liquidity_missing` | New-listing entries require liquidity and spread facts. |
| `spot_short_requested_without_executable_venue` | bStocks spot short/fade labels are analysis-only. |
| `product_risk_missing` | bStocks, TradFi perps, and tokenized metal products need separated interpretation. |
| `post_entry_label_used_as_signal` | Future path labels must not become entry facts. |
| `high_leverage_requested` | 2x/3x are stress-only and 5x is disabled. |
| `same_symbol_active_position_or_open_order` | Prevents duplicate same-symbol exposure. |
| `stale_market_facts` | Blocks event-state interpretation. |
| `missing_exchange_rules` | Blocks runtime consumption. |
| `no_stop_loss_plan` | Blocks any future candidate preparation. |

## Evidence Summary

| Evidence | Result |
| --- | --- |
| Manifest symbols | `31` symbols with 2026 listing hints. |
| bStocks spot symbols | `6` symbols. |
| TradFi futures symbols | `23` symbols. |
| Delayed labels | `575` rows. |
| bStocks refresh labels | `135` rows. |
| Best first-window bStock | `SNDKBUSDT` 24h first-window return `17.207059%`. |
| Best delayed continuation | `SNDKBUSDT` 12h delay / 36h hold, `6.846788%` net. |
| Best delayed fade | `CRCLBUSDT` 3h delay / 24h hold, `5.620422%` net. |
| Best TradFi continuation label | `SNDKUSDT` 12h delay / 48h hold, `13.7449%` net. |
| Best TradFi fade label | `SNDKUSDT` 6h delay / 48h hold, `20.1675%` net. |

## Negative Evidence

| Evidence | Interpretation |
| --- | --- |
| Only `6` bStocks spot symbols exist in the first event batch. | Cohort breadth is too small for promotion. |
| Refreshed bStocks histories are only `31` to `55` 1h bars. | Low-history blocker remains active. |
| Best bStocks delayed continuation is `6.846788%` net. | Useful event label, not right-tail promotion. |
| Short/fade bStocks labels are spot-analysis-only. | Cannot become executable without venue facts. |
| Best labels are concentrated in names such as `SNDK`, `MU`, and `HOOD`. | Symbol concentration and survivorship controls are required. |

## Sample Packets

Canonical sample packets are in `handoff.json`.

## Main-Control Handoff

Recommendation: consume `NLPD-001` as an observe-only event-study draft. It can
support future event watchers, first-session dashboards, and classifier
research, but it should not enter armed observation until cohort breadth,
survivorship, spread/liquidity, product-risk, and executable-side facts improve.
