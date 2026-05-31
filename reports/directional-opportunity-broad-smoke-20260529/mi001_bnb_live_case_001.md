# MI-001 BNB Long Live Signal Case #001

Generated: 2026-05-31 15:13 CST

## 1. Summary

This is the first Owner-readable case review for a live read-only MI-001 BNB observation signal.

It is not a trial start, execution intent, order, execution permission, or runtime start. The source record is a PG observation row with all non-permission flags set.

## 2. Case Metadata

| field | value |
| --- | --- |
| case_id | `MI-001-BNB-LONG-live-case-001` |
| candidate_id | `MI-001-BNB-LONG` |
| strategy | `MI-001` momentum impulse |
| symbol | `BNB/USDT:USDT` |
| side | `long` |
| signal_type | `would_enter` |
| source | `live_market_read_only` |
| market_source | `binance_usdm_public_klines_read_only` |
| PG observation row | `MI-001-BNB-LONG:mi001-5bb8b1c1b14437d7bddbacab:1780196400000` |
| market_bar_timestamp_ms | `1780196400000` |
| market_bar_close | `740.200` |
| review_status | `pending_with_1h_outcome_available` |

## 3. Market Bar

Public Binance USD-M `BNBUSDT` 1h kline at `1780196400000`:

| open_time_ms | open | high | low | close | volume | close_time_ms |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `1780196400000` | `740.070` | `746.590` | `734.500` | `740.200` | `162113.58` | `1780199999999` |

## 4. Evaluator Evidence

| field | value |
| --- | --- |
| logic_version | `mi001-readonly-observation-v1` |
| lookback_bars | `12` |
| lookback_close | `694.990` |
| latest_close | `740.200` |
| impulse_return_pct | `6.5051` |
| return_threshold_pct | `3` |
| closed_candle_count | `30` |
| reason_codes | `mi001_12h_momentum_impulse`, `observe_only_review_required` |
| human_summary | MI-001 would-enter long observation: 12h close-to-close momentum impulse crossed threshold. |

## 5. Forward Tracking

Forward outcomes are only recorded when the required future closed bars are available. They are not inferred.

| window | status | close / outcome | MFE | MAE | notes |
| --- | --- | --- | --- | --- | --- |
| 1h | available | close `734.580`, return `-0.7593%` | `0.3121%` | `-1.1483%` | next closed 1h bar after signal |
| 4h | pending | n/a | n/a | n/a | full 4h forward close not yet available from latest closed-bar source |
| 12h | pending | n/a | n/a | n/a | future window not complete |
| 24h | pending | n/a | n/a | n/a | future window not complete |
| 72h | pending | n/a | n/a | n/a | future window not complete |

## 6. Owner-readable Interpretation

This signal looks like the historical MI-001 BNB signal family in that the 12h impulse is well above the 3% trigger threshold, and BNB repaired-coverage historical evidence has stronger 72h/7d mean outcomes than SOL.

Risk notes:

- The first available 1h forward result is negative, which is compatible with local exhaustion risk after a sharp impulse.
- Historical BNB evidence still has top-tail dependence and weak 2025/2026 year-split evidence.
- The signal is observation-only. It should enter Owner review, not order creation.

Initial conclusion: `pending`.

The case is valid as a live observation case, but not yet validated as a trade case.

## 7. Non-permissions

- no trial start
- no execution intent
- no order
- no order permission
- no execution permission
- no runtime start
- no automatic strategy routing
