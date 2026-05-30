# MI-001 BNB/SOL Evidence Reviewability

## 1. Summary

This report rechecks local BNB/SOL historical OHLCV coverage and reruns MI-001 long evidence under one research-only local-data path. It does not start trial, create execution intent, place orders, start runtime, or grant execution permission.

BNB public Binance UM futures 1h monthly klines were downloaded for the missing 2023-2025 coverage and 2026 year-start gap, then imported into the local research SQLite store. BNB now has continuous 1h coverage for the same 2021-01-01 through 2026-05-20 review span used by SOL.

## 2. Path Chosen

Path A: direct public BNB data repair plus local research rerun. The task used downloaded public Binance UM futures kline archives and local SQLite only; it did not use exchange account APIs, PG writes, runtime, order, execution, or live runner paths.

## 3. Data Coverage

| symbol | range | bars | expected_bars | missing_bars | missing_periods | coverage_status | coverage_confidence |
| --- | --- | ---: | ---: | ---: | --- | --- | --- |
| BNB/USDT:USDT | 2021-01-01 00:00 -> 2026-05-20 23:00 | 47184 | 47184 | 0 | none | continuous_enough | high |
| SOL/USDT:USDT | 2021-01-01 00:00 -> 2026-05-20 23:00 | 47064 | 47184 | 120 | 2022-02-25 23:00 -> 2022-03-01 00:00 (72h missing); 2022-03-31 23:00 -> 2022-04-03 00:00 (48h missing) | coverage_gap | medium |

### Year Counts

| symbol | year | bars |
| --- | --- | ---: |
| BNB/USDT:USDT | 2021 | 8760 |
| BNB/USDT:USDT | 2022 | 8760 |
| BNB/USDT:USDT | 2023 | 8760 |
| BNB/USDT:USDT | 2024 | 8784 |
| BNB/USDT:USDT | 2025 | 8760 |
| BNB/USDT:USDT | 2026 | 3360 |
| SOL/USDT:USDT | 2021 | 8760 |
| SOL/USDT:USDT | 2022 | 8640 |
| SOL/USDT:USDT | 2023 | 8760 |
| SOL/USDT:USDT | 2024 | 8784 |
| SOL/USDT:USDT | 2025 | 8760 |
| SOL/USDT:USDT | 2026 | 3360 |

## 4. Rerun Scope

MI-001 is a 12h close-to-close momentum impulse. A long signal fires when current close is at least 3% above the close 12 bars earlier. This report evaluates long-only BNB and SOL candidates on 1h OHLCV.

Rerun scope: BNB/USDT:USDT long and SOL/USDT:USDT long only; windows 24h, 72h, and 7d; local SQLite `data/v3_dev.db`; no strategy parameter change; no broad smoke rerun for unrelated families.

## 5. Evidence Table

| symbol | window | signal_count | dedup_signal_count | mean | positive_rate | MFE | MAE | cost_adj_baseline | cost_adj_stress | funding_adj_baseline | random_mean | random_spread | top5_removed_mean | top5_impact | buy_hold | year/regime notes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| BNB/USDT:USDT | 24h | 4166 | 714 | 0.8087 | 0.4851 | 4.9494 | -3.7885 | 0.4387 | 0.2737 | 0.7187 | 0.2443 | 0.5644 | -0.4275 | 1.2363 | 1636.2725 | coverage repaired across 2021-2026 local review span |
| BNB/USDT:USDT | 72h | 4166 | 714 | 2.4074 | 0.5470 | 8.7626 | -5.9467 | 2.0374 | 1.8724 | 2.3174 | 0.7936 | 1.6138 | 0.4665 | 1.9409 | 1636.2725 | coverage repaired across 2021-2026 local review span |
| BNB/USDT:USDT | 7d | 4166 | 714 | 5.4482 | 0.5552 | 15.2098 | -8.6585 | 5.0782 | 4.9132 | 5.3582 | 1.9085 | 3.5397 | 1.5730 | 3.8752 | 1636.2725 | coverage repaired across 2021-2026 local review span |
| SOL/USDT:USDT | 24h | 8135 | 1271 | 0.6373 | 0.5019 | 5.9004 | -4.8789 | 0.2673 | 0.1023 | 0.5473 | 0.4413 | 0.1961 | -0.3112 | 0.9485 | 5498.8296 | continuous broad coverage with 120 missing 1h bars |
| SOL/USDT:USDT | 72h | 8135 | 1271 | 1.9531 | 0.5175 | 10.2580 | -7.8922 | 1.5831 | 1.4181 | 1.8631 | 1.1594 | 0.7937 | 0.3090 | 1.6441 | 5498.8296 | continuous broad coverage with 120 missing 1h bars |
| SOL/USDT:USDT | 7d | 8135 | 1271 | 4.7372 | 0.5398 | 17.1543 | -11.4288 | 4.3672 | 4.2022 | 4.6472 | 2.6259 | 2.1113 | 1.7938 | 2.9434 | 5498.8296 | continuous broad coverage with 120 missing 1h bars |

### 72h Year Split

| symbol | year | complete | mean | positive_rate | random_spread | note |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| BNB/USDT:USDT | 2021 | 1814 | 4.9294 | 0.5722 | 1.3203 | available after BNB coverage repair |
| BNB/USDT:USDT | 2022 | 822 | 0.7170 | 0.5474 | 1.0592 | available after BNB coverage repair |
| BNB/USDT:USDT | 2023 | 401 | 0.2208 | 0.5087 | 0.0096 | available after BNB coverage repair |
| BNB/USDT:USDT | 2024 | 605 | 1.3187 | 0.5736 | 0.5760 | available after BNB coverage repair |
| BNB/USDT:USDT | 2025 | 419 | -0.4310 | 0.5012 | -0.6280 | available after BNB coverage repair |
| BNB/USDT:USDT | 2026 | 105 | -1.9797 | 0.2857 | -1.4662 | available after BNB coverage repair |
| SOL/USDT:USDT | 2021 | 2566 | 4.8442 | 0.5931 | -0.1171 | available |
| SOL/USDT:USDT | 2022 | 1445 | -0.8496 | 0.4394 | 0.5144 | partial year due local gaps |
| SOL/USDT:USDT | 2023 | 1372 | 3.3278 | 0.5488 | 1.1298 | available |
| SOL/USDT:USDT | 2024 | 1303 | 1.1891 | 0.5334 | 0.4708 | available |
| SOL/USDT:USDT | 2025 | 1174 | -0.7494 | 0.4302 | -0.4766 | available |
| SOL/USDT:USDT | 2026 | 275 | -1.9987 | 0.3636 | -1.2961 | available |

## 6. Comparison / Reviewability

- BNB remains important because its repaired-coverage MI-001 72h/7d evidence remains stronger than SOL on mean forward return and random-spread checks, while showing weaker 24h positive rate and a negative 2025 year split.
- SOL remains the chain sample because its coverage is much broader and continuous enough across 2021-2026, and its PG/trial readiness chain is already built. SOL also carries visible high-MAE and signal-density/dedup risk tags.
- SOL and BNB can coexist inside MI. SOL is the operational chain sample; BNB is now a repaired-coverage strong observation candidate, not an automatic replacement and not a runtime-ready candidate.
- Owner-visible risk tags that require explicit review include high_MAE, top_tail_dependency, right_tail_dependency, signal_density_dedup, cost/funding/slippage sensitivity, and BNB 2025 weakness.
- Evidence still needed: true campaign replay, better funding history, event examples around top-tail contributors, and Owner review of BNB year-split fragility.

## 7. Strategy Group Status Update

| candidate | recommended_status | notes |
| --- | --- | --- |
| MI-001 BNB long | strong_smoke_candidate / reviewable_with_repaired_coverage | Keep in MI. Coverage blocker is repaired for 2021-2026 local OHLCV, but year-split/top-tail/cost risks remain. Not proven alpha, not runtime eligible, not order ready. |
| MI-001 SOL long | chain_sample / reviewable_with_risk_tags | Keep as current chain sample with high-MAE, top-tail, and dedup tags. Not proven alpha, not automatic order-ready. |

## 8. Safety Check

- 是否启动 trial？no
- 是否下单？no
- 是否创建 execution intent？no
- 是否授予 execution permission？no
- 是否修改 exchange_gateway？no
- 是否写 runtime/order/execution 表？no
- 是否调用真实账户 API？no
- 是否下载 Tier 1 数据？no

## 9. Tests / Validation

- `python3 scripts/research_directional_opportunity_smoke.py --variants MI-001 --symbols 'BNB/USDT:USDT' 'SOL/USDT:USDT' --sides long --windows 24h 72h 7d --sqlite-db data/v3_dev.db`
- `python3 scripts/analyze_mi001_bnb_sol_evidence_reviewability.py --sqlite-db data/v3_dev.db`
- `python3 -m compileall -q src scripts`
- `python3 -m pytest -q tests/unit/test_brc_console_api_surface.py tests/unit/test_execution_permission.py`
- `cd gemimi-web-front && npm run lint && npx vitest run && npm run build`

## 10. Remaining Work

- BNB local OHLCV coverage repair is complete for the 2021-01-01 through 2026-05-20 review span.
- BNB remains review-only until Owner reviews repaired coverage evidence, 2025 weakness, top-tail sensitivity, and campaign replay gaps.
- Live read-only observation still requires strategy-specific signal glue and observation sink wiring.
- No trial start, runtime start, execution permission, or order permission is implied.

## 11. Next Recommended Task

Owner review of BNB repaired evidence
