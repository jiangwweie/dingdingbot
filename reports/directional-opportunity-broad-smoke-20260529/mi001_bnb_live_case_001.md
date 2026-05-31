# MI-001 BNB Long Live Signal Case #001

Generated: 2026-05-31 15:28 CST

## 1. Summary

This is the first Owner-readable case review for a live read-only MI-001 BNB observation signal.

It is not a trial start, execution intent, order, execution permission, or runtime start. The source record is a PG observation row with all non-permission flags set. Forward reviews are now persisted in `brc_strategy_group_forward_reviews`.

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
| review_status | `1h_completed_remaining_windows_pending` |

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

## 5. Forward Review Table

Forward outcomes are recorded only when the required future closed bars are available. Pending windows are not inferred.

| window | status | review_due_at_utc | forward_return | MFE | MAE | source | notes |
| --- | --- | --- | ---: | ---: | ---: | --- | --- |
| 1h | `completed` | `2026-05-31T05:00:00Z` | `-0.7593%` | `0.3121%` | `-1.1483%` | `binance_usdm_public_klines_read_only` | calculated from 1 closed 1h public/read-only bar |
| 4h | `pending` | `2026-05-31T08:00:00Z` | n/a | n/a | n/a | `binance_usdm_public_klines_read_only` | review window has not reached due time |
| 12h | `pending` | `2026-05-31T16:00:00Z` | n/a | n/a | n/a | `binance_usdm_public_klines_read_only` | review window has not reached due time |
| 24h | `pending` | `2026-06-01T04:00:00Z` | n/a | n/a | n/a | `binance_usdm_public_klines_read_only` | review window has not reached due time |
| 72h | `pending` | `2026-06-03T04:00:00Z` | n/a | n/a | n/a | `binance_usdm_public_klines_read_only` | review window has not reached due time |

PG forward review ids:

- `MI-001-BNB-LONG:mi001-5bb8b1c1b14437d7bddbacab:1780196400000:1h`
- `MI-001-BNB-LONG:mi001-5bb8b1c1b14437d7bddbacab:1780196400000:4h`
- `MI-001-BNB-LONG:mi001-5bb8b1c1b14437d7bddbacab:1780196400000:12h`
- `MI-001-BNB-LONG:mi001-5bb8b1c1b14437d7bddbacab:1780196400000:24h`
- `MI-001-BNB-LONG:mi001-5bb8b1c1b14437d7bddbacab:1780196400000:72h`

## 6. Owner-readable Interpretation

This signal looks like the historical MI-001 BNB signal family in that the 12h impulse was well above the 3% trigger threshold, and BNB repaired-coverage historical evidence has stronger 72h/7d mean outcomes than SOL.

The persisted 1h review is adverse:

- 1h return: `-0.7593%`
- 1h MFE: `0.3121%`
- 1h MAE: `-1.1483%`

Interpretation:

- The 1h adverse move does not prove the strategy failed.
- It does strengthen the local exhaustion risk tag after a sharp 12h impulse.
- It supports adding a wait-for-confirmation or no-chase note to the BNB bounded trial design.
- It makes the 4h and 12h windows more important than a single 1h snapshot.

Initial conclusion remains: `pending`.

The case is valid as a live observation case, but not yet validated as a trade case.

## 7. What To Watch Next

- Whether 4h forward outcome recovers above the signal close or confirms exhaustion.
- Whether 12h/24h windows show follow-through consistent with historical MI-001 BNB winners.
- Whether MAE expands beyond historical path-risk expectations.
- Whether repeated BNB `would_enter` signals cluster too densely and need a dedup/no-chase rule.

## 8. Non-permissions

- no trial start
- no execution intent
- no order
- no order permission
- no execution permission
- no runtime start
- no automatic strategy routing
