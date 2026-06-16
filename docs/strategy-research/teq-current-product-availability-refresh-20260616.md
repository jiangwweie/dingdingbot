# TEQ-001 Current Product Availability Refresh

Status: ACTIVE_P0_HANDOFF_HARDENING
Last updated: 2026-06-16

## Scope

This document hardens `TEQ-001` by separating historical cached research
evidence from current Binance USD-S product visibility.

It is research-only. It is not runtime admission, not a FinalGate input, not
an Operation Layer input, not a deploy request, not a credential change, not
an exchange write, not a live profile change, and not an order-sizing default.

## Refresh Source

| Field | Value |
| --- | --- |
| Script | `scripts/check_current_binance_tradfi_availability.py` |
| Public endpoint | `https://fapi.binance.com/fapi/v1/exchangeInfo` |
| Authentication | None |
| Exchange write | None |
| Binance `serverTime` | `1781596818787` |
| Generated at UTC | `2026-06-16T09:52:32.342685+00:00` |
| Local research symbols checked | `93` |
| Current visible rows | `1` |
| Replay-ready visible rows | `0` |

## Category Result

| Category | Local Rows | Current Visible | Current Missing | Interpretation |
| --- | ---: | ---: | ---: | --- |
| `tradfi_equity_or_etf_perpetual` | `87` | `0` | `87` | TEQ cached futures evidence is historical research only until current visibility is refreshed. |
| `tradfi_industrial_metal_context_perpetual` | `1` | `0` | `1` | Not TEQ core; remains unavailable for current futures observation. |
| `tradfi_precious_metal_perpetual` | `4` | `0` | `4` | PMR/FBS metal-perp observation needs separate current product check. |
| `tokenized_gold_perpetual_context` | `1` | `1` | `0` | `XAUTUSDT` is visible, but it is PMR context, not TEQ equity-like momentum. |

## TEQ Handoff Symbol Result

| Symbol | Current USD-S Visibility | Current Meaning |
| --- | --- | --- |
| `INTCUSDT` | `no` | Block current armed observation until symbol availability is refreshed. |
| `SNDKUSDT` | `no` | Block current armed observation until symbol availability is refreshed. |
| `MUUSDT` | `no` | Block current armed observation until symbol availability is refreshed. |
| `CRCLUSDT` | `no` | Block current armed observation until symbol availability is refreshed. |
| `MRVLUSDT` | `no` | Block current armed observation until symbol availability is refreshed. |
| `MSTRUSDT` | `no` | Block current armed observation until symbol availability is refreshed. |
| `HOODUSDT` | `no` | Block current armed observation until symbol availability is refreshed. |
| `COINUSDT` | `no` | Block current armed observation until symbol availability is refreshed. |
| `NVDAUSDT` | `no` | Block current armed observation until symbol availability is refreshed. |
| `TSLAUSDT` | `no` | Block current armed observation until symbol availability is refreshed. |

## Interpretation

`TEQ-001` still has useful research semantics: cached 2026 equity-like
momentum, relative-strength rotation, and session-transfer evidence remain
valid for historical discovery and strategy-cabinet reasoning.

The same evidence must not be interpreted as current runtime availability.
For main-control intake, `TEQ-001` needs a separate current product fact before
armed observation or candidate preparation.

## RequiredFacts Split

| RequiredFact | Fresh Behavior | Stale Behavior | Missing Behavior |
| --- | --- | --- | --- |
| `current_product_availability_state` | Symbol is visible in current public exchangeInfo and status is compatible with observation. | Degrade to observe-only and request refresh. | Block armed observation and candidate prepare. |
| `symbol_mapping_state` | Research symbol maps directly to current exchange symbol. | Degrade confidence and request mapping review. | Block candidate prepare. |
| `exchange_symbol_rules_state` | Min notional, tick, step, leverage limit, and status are available. | Block candidate prepare. | Block candidate prepare. |
| `low_history_dataset_state` | Low history is disclosed as discovery-only. | Keep observation but block promotion. | Block promotion. |
| `session_gap_context` | Session policy exists for regular/off-hours/weekend behavior. | Observe-only. | Block candidate prepare. |
| `mark_funding_review_state` | Mark/funding facts are current for visible futures symbols. | Observe-only. | Block armed observation for futures. |

## Main-Control Recommendation

`TEQ-001` should stay in the strategy cabinet and handoff batch, but current
product availability must gate runtime behavior:

1. Current symbol visible and exchange rules present: TEQ may enter
   `armed_observation` after all other RequiredFacts pass.
2. Cached research symbol not currently visible: keep TEQ as research and
   strategy-picker context, but block candidate preparation.
3. Symbol mapping unclear: require mapping review before watcher binding.
4. bStocks or low-history spot labels: keep event-study observation only.
5. Margin/funding/session facts missing: block promotion and downshift
   observation as needed.

This keeps the right-tail research alive while preventing stale product
availability from becoming accidental execution readiness.
