# CPM-RO-001 Owner Special Observation Review Packet

Generated: 2026-05-31 16:43 CST

## 1. Summary

`CPM-RO-001` is an Owner special observation candidate for live read-only market validation. It is not proven alpha, not runtime eligible by default, not a trial start, not an execution intent, and not an order path.

Current task result:

- Historical warning and failure context reviewed.
- Current live read-only CPM snapshot generated through the existing observation path.
- Snapshot was persisted to PG as observe-only evidence.
- API / Console status was checked and already exposes CPM special-observation status, OOS warning, current signal, and non-permissions.

## 2. CPM Strategy Description

CPM is a pullback-continuation observation line. Its v0 evaluator checks 1h and 4h closed-candle context:

- 4h trend state via SMA20-style trend direction in the current read-only evaluator.
- 1h pullback / bounce depth over the recent lookback.
- reclaim or structure-loss confirmation.
- output contract: `no_action`, `would_enter`, or `invalid`.

Plain-language behavior:

| topic | CPM-RO-001 |
| --- | --- |
| it eats | low-slope, lower-volatility trend continuation after a controlled pullback or bounce |
| it hates | aggressive high-slope moves, violent corrections, regime breaks, and continuation failure |
| owner experience | calmer than MI when it works, but vulnerable to slow bleed and false continuation |
| role | Owner special observation for market validation and review |
| runtime status | not runtime eligible by default |

Evaluator contract source:

- `src/domain/cpm_historical_evaluator.py`
- `src/application/strategy_group_live_readonly_observation.py`

## 3. Historical Warning

CPM carries a mandatory OOS negative warning:

| period | source | positions | win rate | total PnL / return | note |
| --- | --- | ---: | ---: | --- | --- |
| 2021 OOS | `docs/ops/crypto-pullback-module-v1-oos-failure-classification.md` | 74 | 29.5% | `-2153.76 USDT`, `-21.54%` | negative in a bull year; direct challenge to the original profit hypothesis |
| 2022 OOS | same | 51 | 31.1% | `-971.71 USDT`, `-9.72%` | cost-dominated bear-year failure |
| 2021 baseline context | `docs/ops/cpm-1-readonly-feature-context-extraction-report.md` | 79 | 19.0% | `-1765.32` | feature extraction did not remove the warning |
| 2022 baseline context | same | 43 | 18.6% | `-763.72` | negative |

Failure context:

- 2021 failure is more serious than ordinary boundary cost because gross edge was already negative before cost drag.
- 2021 losses clustered in whipsaw / distribution phases even inside a bull year.
- 2023 context points to post-entry continuation failure: near-zero MFE versus 2024 winners.
- 2025 positive profile is structurally fragile and top-winner dependent.

This packet therefore does not present CPM as proven alpha.

## 4. Owner Rationale

Owner still allows special observation because:

- CPM is structurally different from MI and may be calmer.
- Current market structure may be more institutionalized and less purely right-tail than historical MI winners.
- The purpose is market validation and review optimization, not alpha proof.
- Live read-only observation can falsify or refine the hypothesis without creating execution risk.

Current hypothesis:

> CPM may be useful only in mild, low-slope continuation regimes where pullbacks repair without violent continuation failure.

## 5. Current Live Observation Snapshot

Snapshot command:

`python3 scripts/run_strategy_group_readonly_observation_once.py --source live_market --json`

PG observation row:

`CPM-RO-001:cpm-fb9e296ef9beebce7ba18cea:1780210800000`

| field | value |
| --- | --- |
| candidate_id | `CPM-RO-001` |
| symbol | `ETH/USDT:USDT` |
| signal_type | `no_action` |
| side | `none` |
| confidence | `0.25000000` |
| market_bar_timestamp | `2026-05-31T07:00:00Z` |
| market_bar_close | `2023.14` |
| source_type | `live_market_read_only` |
| market_source | `binance_usdm_public_klines_read_only` |
| sink_status | `recorded_pg` |
| reason_codes | `cpm_no_action_trend_ambiguous` |
| human_summary | `4h trend is ambiguous under CPM v0.` |

Key evidence payload:

| field | value |
| --- | --- |
| htf_trend | `neutral` |
| primary_trend | `down` |
| trend_alignment | `unknown` |
| regime | `transition` |
| entry_pattern | `bounce_loss` |
| pullback_depth_pct | `1.1372` |
| bounce_depth_pct | `1.1502` |
| long_pullback_depth_normal | `true` |
| long_reclaim_confirmed | `false` |
| short_bounce_depth_normal | `true` |
| short_loss_confirmed | `true` |
| sma20_1h | `2026.544` |
| sma20_4h | `2011.5295` |

Interpretation:

- Current CPM snapshot is reviewable and durable in PG.
- It is `no_action` because 4h trend is ambiguous under CPM v0.
- Some short-side structure markers exist, but the required higher-timeframe trend context is not aligned enough to produce a `would_enter` observation.
- No forward review is required for this `no_action` snapshot.

Non-permission flags on the PG row:

- `not_order = true`
- `not_execution_intent = true`
- `no_execution_permission = true`
- `no_order_permission = true`
- `no_runtime_start = true`

## 6. Review Metrics

CPM live read-only observation review should track:

| metric | review use |
| --- | --- |
| signal frequency | Detect whether CPM is too sparse, too noisy, or clustering in one regime |
| no_action ratio | Confirm the evaluator is selective in ambiguous states |
| would_enter count | Count actual review cases, not orders |
| invalid count | Detect market-source or context-quality failure |
| 24h / 72h / 7d forward return | Validate or falsify continuation quality |
| MFE / MAE | Compare mildness against MI and identify slow adverse paths |
| regime fit | Determine whether live cases occur in mild continuation regimes |
| failure mode | classify as trend failure, no reclaim, ambiguous trend, volatility damage, or continuation failure |
| Owner note | preserve qualitative judgment on market feel and setup readability |
| review verdict | one of `continue_observation`, `revise`, `park`, `owner_special_bounded_review_candidate` |

## 7. Invalidation Conditions

CPM should be revised or parked if:

- repeated `would_enter` cases have negative 24h/72h outcomes with low MFE;
- `would_enter` appears mostly in ambiguous or transition regimes;
- adverse paths are slow and persistent, making Owner experience worse than MI despite calmer entry logic;
- signal frequency is too low to review meaningfully;
- the evaluator repeatedly emits `invalid` due to missing 1h/4h context;
- any stakeholder attempts to present CPM as proven alpha or runtime eligible by default.

CPM may continue observation if:

- `no_action` avoids ambiguous trend states consistently;
- `would_enter` cases are rare but readable;
- MFE/MAE profile is materially milder than MI;
- follow-through appears in 24h/72h/7d windows without large early adverse path.

## 8. Owner Decision Options

| option | meaning |
| --- | --- |
| `continue_observation` | keep CPM in live read-only observation and collect more cases |
| `revise` | adjust the observation hypothesis or evaluator only after enough review cases |
| `park` | stop CPM observation if OOS failure modes repeat live |
| `owner_special_bounded_review_candidate` | consider bounded review design only after live observation evidence supports it |

## 9. Non-permissions

This packet does not grant:

- trial start
- execution intent
- order
- order permission
- execution permission
- runtime start
- automatic strategy routing
- leverage change
- transfer or withdrawal
- alpha proof
- runtime eligibility by default
