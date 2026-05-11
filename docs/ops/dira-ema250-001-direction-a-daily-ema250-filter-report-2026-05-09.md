# DIRA-EMA250-001 — Direction A Daily EMA250 Filter Diagnostic

## 0. Boundary

This is a research-only frozen diagnostic.

- No runtime change.
- No production strategy change.
- No backtester core change.
- No parameter sweep.
- No short-side test.
- No paper/testnet/live approval.
- No strategy validation claim.
- No Claude task card.

## 1. Frozen Spec

Baseline Direction A:

- Assets: BTC/USDT:USDT and ETH/USDT:USDT for the main decision read.
- Timeframe: 4h.
- Direction: LONG-only.
- Entry: Donchian20 close breakout.
- Exit: fully closed 4h close below EMA60, executed next 4h open.
- Initial stop: previous 20 closed 4h low, signal bar excluded.
- Cost model: fee 0.0004, entry slippage 0.001, exit slippage 0.001, funding 0.0001 per 8h.
- Same-bar/execution semantics: same as existing Direction A report-local diagnostic.

Frozen new filter:

- Allow new long entries only when the latest fully closed 1D close is greater than the latest fully closed 1D EMA250.
- The daily candle must be fully closed before the 4h entry decision.
- If EMA250 warmup is unavailable, new entry is blocked.
- Exits for already open positions are not changed.
- No consecutive-loss pause.
- No short-side logic.
- No human-gating, LLM, news, funding, OI, or other filter.

## 2. Data / Reproducibility

- Script path: `reports/dira-ema250-001-direction-a-daily-ema250-filter/dira_ema250_001_diagnostic.py`
- Local DB: `data/v3_dev.db`
- Commit: `d742b56`
- ETH 4h coverage: 2020-01-01T00:00:00+00:00 to 2026-03-31T20:00:00+00:00; 1D coverage: 2021-01-01T00:00:00+00:00 to 2026-03-31T00:00:00+00:00; EMA250 first available: 2021-09-07T00:00:00+00:00
- BTC 4h coverage: 2021-01-01T00:00:00+00:00 to 2026-03-31T20:00:00+00:00; 1D coverage: 2021-01-01T00:00:00+00:00 to 2026-03-31T00:00:00+00:00; EMA250 first available: 2021-09-07T00:00:00+00:00
- SOL was run as appendix only.

## 3. Baseline vs EMA250 Filter Summary

| Asset | Variant | Trades | W/L | Net PnL | PF | Realized MaxDD | MTM MaxDD | Top-3 excl | Top-5 excl |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ETH | baseline | 173 | 34/139 | 3001.66 | 1.517 | 6.08% | n/a | -443.91 | -1493.33 |
| ETH | ema250 | 82 | 16/66 | 909.84 | 1.366 | 7.41% | 8.38% | -1309.99 | -1664.77 |
| BTC | baseline | 159 | 40/119 | 2517.17 | 1.477 | 9.95% | n/a | -687.93 | -1665.43 |
| BTC | ema250 | 82 | 28/54 | 2178.71 | 1.803 | 4.31% | 6.50% | -290.72 | -888.58 |
| BTC+ETH | baseline | 332 | 74/258 | 5518.83 | 1.498 | 6.64% | n/a | 1703.07 | -368.87 |
| BTC+ETH | ema250 | 164 | 44/120 | 3088.55 | 1.594 | 4.58% | n/a | -140.68 | -1379.44 |

BTC+ETH headline:

- Trades: 332 baseline -> 164 filtered.
- Net PnL: 5518.83 -> 3088.55, delta -2430.28.
- PF: 1.498 -> 1.594.
- Realized MaxDD: 6.64% -> 4.58%.
- Top-3 removal: 1703.07 -> -140.68.
- Top-5 removal: -368.87 -> -1379.44.

## 4. Year-by-Year Comparison

| Asset | Variant | Year | Trades | W/L | Net PnL | PF |
|---|---|---:|---:|---:|---:|---:|
| ETH | baseline | 2021 | 33 | 8/25 | 722.57 | 1.716 |
| ETH | baseline | 2022 | 36 | 5/31 | -76.80 | 0.923 |
| ETH | baseline | 2023 | 29 | 7/22 | 918.93 | 1.826 |
| ETH | baseline | 2024 | 34 | 9/25 | 1465.75 | 2.559 |
| ETH | baseline | 2025 | 41 | 5/36 | -28.79 | 0.984 |
| ETH | ema250 | 2021 | 10 | 2/8 | -62.97 | 0.772 |
| ETH | ema250 | 2022 | 1 | 1/0 | 71.13 | Infinity |
| ETH | ema250 | 2023 | 23 | 4/19 | -394.13 | 0.497 |
| ETH | ema250 | 2024 | 25 | 6/19 | 1025.80 | 2.578 |
| ETH | ema250 | 2025 | 23 | 3/20 | 270.01 | 1.350 |
| BTC | baseline | 2021 | 33 | 8/25 | 293.35 | 1.362 |
| BTC | baseline | 2022 | 31 | 5/26 | -821.76 | 0.217 |
| BTC | baseline | 2023 | 30 | 9/21 | 2407.94 | 3.211 |
| BTC | baseline | 2024 | 31 | 9/22 | 919.06 | 1.885 |
| BTC | baseline | 2025 | 34 | 9/25 | -281.43 | 0.782 |
| BTC | ema250 | 2021 | 5 | 3/2 | 107.37 | 2.188 |
| BTC | ema250 | 2022 | 1 | 0/1 | -56.33 | 0.000 |
| BTC | ema250 | 2023 | 22 | 7/15 | 1161.90 | 2.528 |
| BTC | ema250 | 2024 | 29 | 9/20 | 845.84 | 1.845 |
| BTC | ema250 | 2025 | 25 | 9/16 | 119.93 | 1.149 |
| BTC+ETH | baseline | 2021 | 66 | 16/50 | 1015.92 | 1.558 |
| BTC+ETH | baseline | 2022 | 67 | 10/57 | -898.56 | 0.560 |
| BTC+ETH | baseline | 2023 | 59 | 16/43 | 3326.86 | 2.511 |
| BTC+ETH | baseline | 2024 | 65 | 18/47 | 2384.81 | 2.206 |
| BTC+ETH | baseline | 2025 | 75 | 14/61 | -310.21 | 0.898 |
| BTC+ETH | ema250 | 2021 | 15 | 5/10 | 44.39 | 1.121 |
| BTC+ETH | ema250 | 2022 | 2 | 1/1 | 14.81 | 1.263 |
| BTC+ETH | ema250 | 2023 | 45 | 11/34 | 767.77 | 1.497 |
| BTC+ETH | ema250 | 2024 | 54 | 15/39 | 1871.64 | 2.134 |
| BTC+ETH | ema250 | 2025 | 48 | 12/36 | 389.94 | 1.247 |

Key bad-year impact:

- 2022 BTC+ETH: -898.56 baseline -> 14.81 filtered; improvement 913.36.
- 2025 BTC+ETH: -310.21 baseline -> 389.94 filtered; improvement 700.15.

Good-year preservation:

- 2021 BTC+ETH: 1015.92 baseline -> 44.39 filtered.
- 2023 BTC+ETH: 3326.86 baseline -> 767.77 filtered.
- 2024 BTC+ETH: 2384.81 baseline -> 1871.64 filtered.

## 5. Disabled Trade Review

Main BTC+ETH disabled trade summary:

- Disabled trades: 186.
- Disabled winners / losers: 37 / 149.
- Disabled baseline net PnL: 2070.96.
- Disabled winner PnL: 7914.89.
- Disabled loser PnL: -5843.92.

Disabled top-5 winners:

| Asset | Entry | Exit | Year | Baseline rank | Baseline PnL | Exit |
|---|---|---|---:|---:|---:|---|
| ETH | 2021-01-02 | 2021-01-11 | 2021 | 4 | 533.65 | ema60_close_break_next_open |
| ETH | 2023-01-02 | 2023-01-25 | 2023 | 3 | 1035.21 | ema60_close_break_next_open |
| ETH | 2023-10-20 | 2023-11-14 | 2023 | 5 | 515.77 | ema60_close_break_next_open |
| BTC | 2021-02-02 | 2021-02-23 | 2021 | 5 | 428.06 | ema60_close_break_next_open |
| BTC | 2023-01-09 | 2023-02-05 | 2023 | 2 | 1138.30 | ema60_close_break_next_open |

Disabled major losers:

| Asset | Entry | Exit | Year | Baseline rank | Baseline PnL | Exit |
|---|---|---|---:|---:|---:|---|
| ETH | 2025-06-09 | 2025-06-13 | 2025 | 173 | -133.30 | initial_stop |
| ETH | 2025-04-21 | 2025-04-21 | 2025 | 172 | -130.42 | initial_stop |
| ETH | 2021-08-30 | 2021-09-07 | 2021 | 171 | -115.12 | initial_stop |
| ETH | 2022-05-04 | 2022-05-05 | 2022 | 169 | -113.43 | initial_stop |
| ETH | 2022-06-06 | 2022-06-07 | 2022 | 167 | -111.72 | initial_stop |
| ETH | 2021-04-10 | 2021-04-18 | 2021 | 166 | -111.55 | initial_stop |
| ETH | 2025-02-21 | 2025-02-21 | 2025 | 165 | -107.93 | ema60_close_break_next_open |
| BTC | 2021-09-02 | 2021-09-07 | 2021 | 154 | -107.06 | initial_stop |
| BTC | 2025-11-26 | 2025-12-01 | 2025 | 153 | -106.88 | ema60_close_break_next_open |
| BTC | 2022-01-20 | 2022-01-20 | 2022 | 152 | -106.18 | initial_stop |

## 6. Fragility / Top-N Removal

- BTC+ETH top-1 removal: 4145.20 baseline -> 1857.89 filtered.
- BTC+ETH top-3 removal: 1703.07 baseline -> -140.68 filtered.
- BTC+ETH top-5 removal: -368.87 baseline -> -1379.44 filtered.

Read:

- Top-N fragility is not solved.
- The filter may improve or reduce net depending on disabled winners versus disabled losers, but sparse payoff-tail dependence remains the binding issue.
- If top-3/top-5 removal remains negative, the filter cannot be treated as validation.

## 7. Re-entry / False-Breakout Cluster Read

Known DIRA-FORENSIC-001 clusters were compared descriptively through the trade sequence before and after filtering.

Baseline largest loss clusters and filtered largest loss clusters are recorded in `summary.json`. The practical read:

| Asset | Variant | Start | End | Years | Losing trades | Cluster PnL |
|---|---|---|---|---|---:|---:|
| ETH | baseline | 2024-12-12 | 2025-04-21 | 2024,2025 | 14 | -682.25 |
| ETH | baseline | 2022-07-28 | 2022-10-14 | 2022 | 14 | -410.92 |
| ETH | baseline | 2024-03-25 | 2024-05-16 | 2024 | 9 | -400.19 |
| ETH | ema250 | 2024-12-12 | 2025-06-17 | 2024,2025 | 12 | -528.53 |
| ETH | ema250 | 2024-03-25 | 2024-05-16 | 2024 | 9 | -332.69 |
| ETH | ema250 | 2023-01-21 | 2023-04-09 | 2023 | 7 | -298.12 |
| BTC | baseline | 2023-07-10 | 2023-09-27 | 2023 | 11 | -606.48 |
| BTC | baseline | 2021-04-26 | 2021-07-12 | 2021 | 11 | -288.61 |
| BTC | baseline | 2025-10-21 | 2025-12-29 | 2025 | 10 | -563.75 |
| BTC | ema250 | 2023-07-10 | 2023-10-09 | 2023 | 6 | -343.99 |
| BTC | ema250 | 2025-02-20 | 2025-04-03 | 2025 | 5 | -309.74 |
| BTC | ema250 | 2025-08-22 | 2025-09-09 | 2025 | 5 | -219.27 |

- The EMA250 filter targets broad below-EMA250 regimes, so it can remove some 2022/2025 bear/chop entries.
- It does not address all clusters inside positive years because those clusters can occur while daily close remains above EMA250.
- It is therefore an objective coarse bull/bear gate, not a false-breakout detector.

## 8. Interpretation

Does EMA250 solve a real problem?

- It addresses a real problem only if it materially reduces 2022/2025 losses without disabling 2021/2023/2024 payoff tails. See the year-by-year and disabled-trade tables above.

Does it preserve the payoff engine?

- The key criterion is preservation of known top winners. If top-5 2021/2023/2024 winners are disabled, the filter damages the sparse payoff engine.

Does it create new problems?

- Yes if it blocks major winners, leaves top-N fragility unresolved, or creates asymmetric harm between BTC and ETH.

Does it support algorithmic gating as baseline?

- Human-gated thesis impact: **NO**.
- Verdict: **FILTER_REJECT**.

Does it still need human / LLM review?

- Yes. A daily EMA250 filter is a coarse objective ON/OFF baseline. It cannot read macro events, funding stress, news shocks, late-cycle distribution, or loss clusters inside positive regimes.

## 9. Verdict

Verdict: **FILTER_REJECT**.

Reason:

- EMA250 did not provide a favorable tradeoff between bad-year loss reduction and payoff-tail preservation.

## 10. What Not To Infer

- No live readiness.
- No paper/testnet approval.
- No runtime activation.
- No parameter approval.
- No short-side approval.
- No LLM implementation approval.
- No claim that this beats spot in a future bull cycle.
- No claim that Direction A is validated.
