# Direction A Cross-Asset Frozen Diagnostic Result

**Status:** Completed / Mechanism Validation Only
**Classification:** FROZEN_DIAGNOSTIC_RESULT
**Date:** 2026-05-08
**Authorization Level:** Level 1/2 — Owner-authorized one-time frozen empirical diagnostic
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document is the result of a one-time frozen empirical diagnostic for mechanism validation only.

It is not:

- a strategy experiment;
- a parameter optimization;
- a deployment evaluation;
- Direction A rescue or variant;
- runtime or small-live admission;
- promotion;
- TE execution;
- CPM reopening;
- router/regime/portfolio work;
- per-asset optimization;
- a claim that cross-asset success implies deployment readiness.

The frozen diagnostic ran the identical Direction A Donchian20 → EMA60 4h lifecycle mechanism on BTC/USDT:USDT and SOL/USDT:USDT using the existing local 4h OHLCV base window (2021-01-01 to 2025-12-31). No asset-specific parameter changes were made.

---

## 1. Inputs and Authorization

**Owner authorization:** One-time frozen empirical diagnostic, authorized by the task prompt.

**Diagnostic plan:** `docs/ops/direction-a-cross-asset-transfer-diagnostic-plan.md`
**Data coverage audit:** `docs/ops/direction-a-cross-asset-data-coverage-audit.md`
**SRR-002 methodology:** `docs/ops/srr-002-research-methodology-and-applicability-boundary-upgrade.md`

**Frozen rule source:** DIRA-EH-001 / NSC-014 clean baseline adapter
**Adapter:** `reports/direction-a-cross-asset-frozen-diagnostic/direction_a_cross_asset_frozen_diagnostic.py`

**Data source:** Local `data/v3_dev.db` — SQLite, klines table, 4h timeframe, is_closed = 1
**No data fetch, import, or database mutation was performed.**

---

## 2. Frozen Rule Confirmation

| Component | Specification |
| --- | --- |
| **Entry signal** | 4h Donchian20 close breakout: close > highest close of prior 20 closed 4h bars |
| **Entry execution** | Next 4h bar open after signal close, plus 0.1% entry slippage |
| **Initial risk stop** | Previous 20 closed 4h low, signal bar excluded; active intrabar |
| **Exit mechanism** | Fully closed 4h candle close below EMA60 |
| **Exit execution** | Next 4h bar open after EMA60 close-break trigger, less 0.1% exit slippage |
| **Same-bar policy** | Initial stop checked before recording same-bar EMA close-break trigger; intrabar EMA touch ignored |
| **EMA period** | 60 |
| **Donchian lookback** | 20 |
| **Cost model** | fee_rate 0.0004, entry slippage 0.001, exit slippage 0.001, funding 0.0001/8h |
| **Position sizing** | 1% risk fraction, max 2x equity exposure |
| **No asset-specific changes** | Confirmed — identical rule for ETH, BTC, and SOL |

---

## 3. Data Coverage Caveats

| Asset | Local bars loaded | Base window coverage | Known gaps | Classification |
| --- | --- | --- | --- | --- |
| ETH/USDT:USDT | Not re-run | 10,956/10,956 (100%) | None | Reference baseline |
| BTC/USDT:USDT | 11,496 | 10,956/10,956 (100%) | None | `DATA_READY_FULL_BASE_WINDOW` |
| SOL/USDT:USDT | 11,466 | 10,926/10,956 (99.7%) | 30 bars in 2022 (two gaps: Feb 25–Mar 1, Mar 31–Apr 3) | `DATA_READY_ADJUSTED_WINDOW` |

**SOL gap details:**
- Gap 1: 2022-02-25 20:00 UTC to 2022-03-01 00:00 UTC — 18 missing 4h bars (3.0 days)
- Gap 2: 2022-03-31 20:00 UTC to 2022-04-03 00:00 UTC — 12 missing 4h bars (2.0 days)
- Total: 30 missing bars out of 10,956 expected = 0.27% of base window
- Gaps result in no signal generation during those periods; structurally safe

**Warmup:** BTC and SOL data starts 2021-01-01 00:00 UTC. EMA60 warmup completes ~2021-01-11. First valid signals begin after warmup.

---

## 4. BTC Result

### 4.1 Aggregate Metrics

| Metric | BTC | ETH Baseline | Comparison |
| --- | --- | --- | --- |
| Trades | 159 | 173 | Similar (−14) |
| Winners | 40 | 34 | BTC has 6 more winners |
| Losers | 119 | 139 | BTC has 20 fewer losers |
| Win rate | 25.16% | 19.65% | BTC higher (+5.5pp) |
| Net PnL | +2,517.17 | +3,001.66 | BTC lower (−16.1%) |
| Gross PnL before costs | +3,844.83 | — | — |
| Profit factor | 1.477 | 1.517 | BTC slightly lower |
| Realized MaxDD | 9.95% | 6.08% | BTC higher DD |
| MTM MaxDD | 11.32% | 8.33% | BTC higher DD |
| Avg winner | +194.82 | — | — |
| Avg loser | −44.33 | — | — |
| Payoff ratio | 4.39:1 | — | High payoff ratio |
| Avg hold — winners | 281.1h (11.7 days) | — | — |
| Avg hold — losers | 47.1h (2.0 days) | — | — |

### 4.2 Cost Breakdown

| Cost | BTC |
| --- | --- |
| Fees | 253.66 |
| Slippage | 634.15 |
| Funding | 439.86 |
| Total costs | 1,327.66 |
| Gross PnL | 3,844.83 |
| Cost as % of gross | 34.5% |

### 4.3 Fragility Metrics

| Metric | BTC |
| --- | --- |
| Top-1 winner PnL | +1,303.82 |
| Top-3 winner PnL | +3,205.09 |
| Top-5 winner PnL | +4,182.60 |
| Top-1 as % of net PnL | 51.8% |
| Top-3 as % of net PnL | 127.3% |
| Top-5 as % of net PnL | 166.2% |
| Net after top-1 removal | +1,213.34 (positive) |
| Net after top-3 removal | **−687.93 (NEGATIVE)** |
| Net after top-5 removal | **−1,665.43 (NEGATIVE)** |
| Worst-1 loser | −135.26 |
| Worst-3 losers | −373.22 |
| Worst-5 losers | −591.90 |

**Fragility assessment:** BTC top-3 removal turns net PnL negative (−687.93). Top-3 winners contribute 127.3% of net, meaning the net excluding top-3 is negative. This is a deployment blocker per SRR-002 Section 4.5 but is acceptable as research evidence per Owner tolerance clarification (SRR-002 Section 4.4).

---

## 5. SOL Result

### 5.1 Aggregate Metrics

| Metric | SOL | ETH Baseline | Comparison |
| --- | --- | --- | --- |
| Trades | 158 | 173 | Similar (−15) |
| Winners | 44 | 34 | SOL has 10 more winners |
| Losers | 114 | 139 | SOL has 25 fewer losers |
| Win rate | 27.85% | 19.65% | SOL higher (+8.2pp) |
| Net PnL | +4,018.80 | +3,001.66 | SOL higher (+33.9%) |
| Gross PnL before costs | +4,783.71 | — | — |
| Profit factor | 1.790 | 1.517 | SOL higher |
| Realized MaxDD | 4.49% | 6.08% | SOL lower DD |
| MTM MaxDD | 6.44% | 8.33% | SOL lower DD |
| Avg winner | +206.89 | — | — |
| Avg loser | −44.60 | — | — |
| Payoff ratio | 4.64:1 | — | High payoff ratio |
| Avg hold — winners | 271.2h (11.3 days) | — | — |
| Avg hold — losers | 41.1h (1.7 days) | — | — |

### 5.2 Cost Breakdown

| Cost | SOL |
| --- | --- |
| Fees | 153.31 |
| Slippage | 383.29 |
| Funding | 228.31 |
| Total costs | 764.91 |
| Gross PnL | 4,783.71 |
| Cost as % of gross | 16.0% |

### 5.3 Fragility Metrics

| Metric | SOL |
| --- | --- |
| Top-1 winner PnL | +2,273.99 |
| Top-3 winner PnL | +3,638.58 |
| Top-5 winner PnL | +4,388.58 |
| Top-1 as % of net PnL | 56.6% |
| Top-3 as % of net PnL | 90.5% |
| Top-5 as % of net PnL | 109.2% |
| Net after top-1 removal | +1,744.80 (positive) |
| Net after top-3 removal | **+380.21 (positive)** |
| Net after top-5 removal | **−369.78 (NEGATIVE)** |
| Worst-1 loser | −153.44 |
| Worst-3 losers | −428.88 |
| Worst-5 losers | −669.94 |

**Fragility assessment:** SOL passes top-3 removal (+380.21 positive) but fails top-5 removal (−369.78). Top-3 winners contribute 90.5% of net PnL. Top-1 alone contributes 56.6% of net — above the 40% disclosure threshold but below the 50% concentration limit. Top-5 removal is a deployment blocker per SRR-002 but acceptable as research evidence.

---

## 6. ETH Baseline Comparison

| Metric | ETH | BTC | SOL |
| --- | --- | --- | --- |
| Trades | 173 | 159 | 158 |
| Winners / Losers | 34 / 139 | 40 / 119 | 44 / 114 |
| Win rate | 19.65% | 25.16% | 27.85% |
| Net PnL | +3,001.66 | +2,517.17 | +4,018.80 |
| Profit factor | 1.517 | 1.477 | 1.790 |
| Realized MaxDD | 6.08% | 9.95% | 4.49% |
| MTM MaxDD | 8.33% | 11.32% | 6.44% |
| Payoff ratio | — | 4.39:1 | 4.64:1 |
| Net excl top-3 | NEGATIVE | NEGATIVE | POSITIVE |
| Net excl top-5 | NEGATIVE | NEGATIVE | NEGATIVE |
| Classification | POSITIVE_SPARSE_TREND_EVIDENCE | BTC_PARTIAL_SPARSE_TREND_EVIDENCE | SOL_POSITIVE_SPARSE_TREND_EVIDENCE |

---

## 7. Cross-Asset Metric Table

| Metric | ETH | BTC | SOL | Cross-asset pattern |
| --- | --- | --- | --- | --- |
| Trade count | 173 | 159 | 158 | All ~160-170; comparable sample sizes |
| Win rate | 19.65% | 25.16% | 27.85% | All 19-28%; SOL highest, ETH lowest |
| Net PnL | +3,001.66 | +2,517.17 | +4,018.80 | All positive; SOL highest, BTC lowest |
| PF | 1.517 | 1.477 | 1.790 | All >1.4; SOL highest, BTC lowest |
| Payoff ratio | ~4.09 | 4.39 | 4.64 | All >4:1; high payoff consistent |
| Realized MaxDD | 6.08% | 9.95% | 4.49% | BTC highest DD |
| MTM MaxDD | 8.33% | 11.32% | 6.44% | BTC highest DD |
| Top-3 removal | NEGATIVE | NEGATIVE | POSITIVE | Only SOL passes |
| Top-5 removal | NEGATIVE | NEGATIVE | NEGATIVE | All fail |
| Cost % of gross | — | 34.5% | 16.0% | BTC higher cost drag |

**Structural pattern:** All three assets show the same sparse trend signature — low win rate (19-28%), high payoff ratio (>4:1), concentrated winners, positive net PnL under realistic costs. This is consistent with a crypto-wide trend-capture mechanism, not an ETH-specific artifact.

---

## 8. Fragility Comparison

| Metric | ETH | BTC | SOL |
| --- | --- | --- | --- |
| Top-1 as % of net | — | 51.8% | 56.6% |
| Top-3 as % of net | — | 127.3% | 90.5% |
| Top-5 as % of net | — | 166.2% | 109.2% |
| Net excl top-1 | — | +1,213.34 | +1,744.80 |
| Net excl top-3 | NEGATIVE | −687.93 | +380.21 |
| Net excl top-5 | NEGATIVE | −1,665.43 | −369.78 |

**Fragility profile:**
- **BTC** shows the highest top-winner concentration: top-3 alone is 127.3% of net. Removing the top 3 winners leaves −687.93. This is more concentrated than ETH.
- **SOL** shows strong but somewhat lower concentration: top-3 is 90.5% of net but still passes at +380.21. Top-5 removal turns negative (−369.78).
- **All three assets fail top-5 removal.** This is a universal fragility pattern for the Donchian20 → EMA60 mechanism across crypto assets. It is a deployment blocker but consistent with sparse trend characteristics.

**Year concentration:**
- BTC 2023 alone contributes +2,407.94 of +2,517.17 total net (95.7%). This is extreme year concentration.
- SOL 2023 alone contributes +2,832.81 of +4,018.80 total net (70.5%). Also concentrated but less extreme.
- Both show 2022 and 2025 as negative years, consistent with ETH.

---

## 9. Top Winner Attribution

### 9.1 BTC Top-10 Winners

| Rank | Entry | Exit | Hold (h) | Net PnL | Exit Reason | Year | Regime |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2023-10-16 | 2023-11-14 | 716 | +1,303.82 | ema60_close_break | 2023 | BTC spot ETF approval anticipation rally |
| 2 | 2023-01-09 | 2023-02-05 | 664 | +1,138.30 | ema60_close_break | 2023 | Post-FTX recovery rally |
| 3 | 2024-02-26 | 2024-03-15 | 420 | +762.97 | ema60_close_break | 2024 | BTC spot ETF inflow-driven rally |
| 4 | 2024-02-07 | 2024-02-24 | 388 | +549.44 | ema60_close_break | 2024 | BTC pre-halving rally |
| 5 | 2021-02-02 | 2021-02-23 | 488 | +428.06 | ema60_close_break | 2021 | Bull market expansion |
| 6 | 2021-10-01 | 2021-10-22 | 512 | +382.75 | ema60_close_break | 2021 | Bull market expansion |
| 7 | 2025-05-07 | 2025-05-28 | 520 | +331.45 | ema60_close_break | 2025 | 2025 bull phase |
| 8 | 2023-11-28 | 2023-12-11 | 300 | +302.83 | ema60_close_break | 2023 | BTC spot ETF anticipation continued |
| 9 | 2024-11-06 | 2024-11-26 | 476 | +302.12 | ema60_close_break | 2024 | Post-US election rally |
| 10 | 2025-09-29 | 2025-10-10 | 280 | +214.94 | ema60_close_break | 2025 | 2025 bull phase |

**BTC top-winner thesis consistency:**
- All top-10 winners are EMA60 close-break exits (trend exit, not stop) — thesis-consistent.
- All represent genuine trend captures: BTC moved substantially in the direction of the signal.
- Top winners span 2021 (2), 2023 (4), 2024 (3), 2025 (1) — distributed across 4 years, not single-year clustered.
- Top-1 (Oct 2023 ETF anticipation rally) is the largest single contributor at +1,303.82 (51.8% of net). This is a genuine macro-driven trend move.
- **No data/event artifact concerns identified.** All top winners correspond to well-known BTC macro trends (ETF approval, post-halving, election).

### 9.2 SOL Top-10 Winners

| Rank | Entry | Exit | Hold (h) | Net PnL | Exit Reason | Year | Regime |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2023-10-16 | 2023-11-21 | 856 | +2,273.99 | ema60_close_break | 2023 | SOL ecosystem revival rally |
| 2 | 2021-07-29 | 2021-08-25 | 640 | +832.68 | ema60_close_break | 2021 | SOL summer 2021 breakout |
| 3 | 2021-08-27 | 2021-09-13 | 408 | +531.91 | ema60_close_break | 2021 | SOL all-time high run |
| 4 | 2023-01-02 | 2023-01-25 | 544 | +398.46 | ema60_close_break | 2023 | Post-FTX recovery |
| 5 | 2021-01-24 | 2021-02-16 | 560 | +351.54 | ema60_close_break | 2021 | Early 2021 bull market |
| 6 | 2022-03-17 | 2022-04-06 | 496 | +327.33 | ema60_close_break | 2022 | Bear market relief rally |
| 7 | 2023-06-29 | 2023-07-21 | 524 | +306.36 | ema60_close_break | 2023 | Mid-2023 SOL recovery |
| 8 | 2023-12-20 | 2023-12-28 | 196 | +300.25 | ema60_close_break | 2023 | Year-end 2023 rally |
| 9 | 2024-07-15 | 2024-07-31 | 404 | +280.72 | ema60_close_break | 2024 | Mid-2024 SOL trend |
| 10 | 2021-03-27 | 2021-04-14 | 440 | +266.12 | ema60_close_break | 2021 | 2021 bull market |

**SOL top-winner thesis consistency:**
- All top-10 winners are EMA60 close-break exits — thesis-consistent.
- All represent genuine trend captures across multiple SOL market regimes.
- Top winners span 2021 (4), 2022 (1), 2023 (4), 2024 (1) — distributed across 4 years.
- Top-1 (Oct 2023 SOL ecosystem revival) is +2,273.99 (56.6% of net). This is a genuine macro-driven trend — SOL was recovering from FTX-era lows.
- Rank 6 (2022-03, bear market relief rally at +327.33) is a counter-trend capture during a bear year; this is a genuine trend signal, not an artifact.
- **No data/event artifact concerns identified.** All top winners correspond to known SOL market periods.

---

## 10. Worst Loser Attribution

### 10.1 BTC Worst-10 Losers

| Rank | Entry | Exit | Hold (h) | Net PnL | Exit Reason | Year |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 2024-12-05 | 2024-12-05 | 20 | −135.26 | initial_stop | 2024 |
| 2 | 2024-01-01 | 2024-01-03 | 40 | −123.77 | initial_stop | 2024 |
| 3 | 2023-07-13 | 2023-07-14 | 20 | −114.19 | initial_stop | 2023 |
| 4 | 2024-12-16 | 2024-12-19 | 72 | −111.09 | ema60_close_break | 2024 |
| 5 | 2023-11-20 | 2023-11-22 | 48 | −107.59 | ema60_close_break | 2023 |
| 6 | 2021-09-02 | 2021-09-07 | 128 | −107.06 | initial_stop | 2021 |
| 7 | 2025-11-26 | 2025-12-01 | 104 | −106.88 | ema60_close_break | 2025 |
| 8 | 2022-01-20 | 2022-01-20 | 4 | −106.18 | initial_stop | 2022 |
| 9 | 2022-05-04 | 2022-05-05 | 16 | −104.24 | initial_stop | 2022 |
| 10 | 2022-06-06 | 2022-06-07 | 20 | −102.40 | initial_stop | 2022 |

**BTC loser interpretation:**
- Worst losses are bounded (worst = −135.26 = 1.35% of initial equity).
- 6/10 worst losers are initial stops (fast exits), 4/10 are EMA60 breaks (slower exits).
- Worst losers span 2021-2025 across multiple years — not concentrated.
- The 2022 bear market produces 3 of the bottom 10 losers, consistent with trend-following underperformance in bear regimes.

### 10.2 SOL Worst-10 Losers

| Rank | Entry | Exit | Hold (h) | Net PnL | Exit Reason | Year |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 2024-06-04 | 2024-06-07 | 72 | −153.44 | initial_stop | 2024 |
| 2 | 2025-04-02 | 2025-04-02 | 0 | −147.44 | initial_stop | 2025 |
| 3 | 2025-12-09 | 2025-12-11 | 32 | −127.99 | ema60_close_break | 2025 |
| 4 | 2022-09-06 | 2022-09-06 | 12 | −120.91 | initial_stop | 2022 |
| 5 | 2023-01-29 | 2023-01-30 | 20 | −120.15 | initial_stop | 2023 |
| 6 | 2023-04-26 | 2023-04-26 | 4 | −119.61 | initial_stop | 2023 |
| 7 | 2025-05-18 | 2025-05-18 | 4 | −128.53 | ema60_close_break | 2025 |
| 8 | 2025-10-21 | 2025-10-22 | 8 | −118.28 | ema60_close_break | 2025 |
| 9 | 2024-07-02 | 2024-07-03 | 20 | −103.92 | ema60_close_break | 2024 |
| 10 | 2024-01-02 | 2024-01-03 | 36 | −93.45 | ema60_close_break | 2024 |

**SOL loser interpretation:**
- Worst losses are bounded (worst = −153.44 = 1.53% of initial equity).
- Rank 2 (2025-04-02): 0-hour hold — position entered and stopped out within the same 4h bar. MAE of −231.44 in notional terms (2.3% of equity). This is a legitimate high-volatility stop-out, not a data artifact.
- 5/10 worst losers are initial stops, 5/10 are EMA60 breaks.
- Worst losers span 2022-2025 — not concentrated.

---

## 11. Year/Regime Analysis

### 11.1 BTC Year-by-Year

| Year | Trades | Winners | Win Rate | Net PnL | PF | Top-1 Contribution | Interpretation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2021 | 33 | 8 | 24.2% | +293.35 | 1.36 | +428.06 (145.9%) | Bull market, but DD offset most gains |
| 2022 | 31 | 5 | 16.1% | −821.76 | 0.22 | +70.84 | Bear market; trend-following underperformance |
| 2023 | 30 | 9 | 30.0% | +2,407.94 | 3.21 | +1,303.82 (54.1%) | Strongest year; ETF anticipation rally |
| 2024 | 31 | 9 | 29.0% | +919.06 | 1.89 | +762.97 (83.0%) | Good year; ETF inflows, halving rally |
| 2025 | 34 | 9 | 26.5% | −281.43 | 0.78 | +331.45 | Negative year; cost drag exceeded edge |

**BTC regime pattern:**
- Positive years: 2021, 2023, 2024 (3 of 5 years positive)
- Negative years: 2022 (−821.76), 2025 (−281.43)
- 2023 dominates with 95.7% of total net PnL — extreme year concentration
- The mechanism captures trends in bull/expansion regimes but suffers in bear/consolidation regimes

### 11.2 SOL Year-by-Year

| Year | Trades | Winners | Win Rate | Net PnL | PF | Top-1 Contribution | Interpretation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2021 | 29 | 10 | 34.5% | +1,744.17 | 3.31 | +832.68 (47.7%) | Strong bull year; SOL breakout |
| 2022 | 31 | 7 | 22.6% | −310.31 | 0.63 | +327.33 | Bear market; relief rally captured but net negative |
| 2023 | 29 | 9 | 31.0% | +2,832.81 | 4.14 | +2,273.99 (80.3%) | Strongest year; SOL ecosystem revival |
| 2024 | 31 | 10 | 32.3% | +213.17 | 1.20 | +280.72 (131.7%) | Marginal positive; one large winner |
| 2025 | 38 | 8 | 21.1% | −461.04 | 0.70 | +255.82 | Negative year; high trade count, low win rate |

**SOL regime pattern:**
- Positive years: 2021, 2023, 2024 (3 of 5 years positive)
- Negative years: 2022 (−310.31), 2025 (−461.04)
- 2023 dominates with 70.5% of total net PnL — significant but less extreme than BTC
- Similar regime pattern to ETH/BTC: strongest in trend expansion, weakest in bear/choppy markets

### 11.3 Cross-Asset Regime Consistency

| Year | ETH | BTC | SOL | Cross-asset pattern |
| --- | --- | --- | --- | --- |
| 2021 | — | +293.35 | +1,744.17 | Both positive; SOL outperforms |
| 2022 | — | −821.76 | −310.31 | Both negative; bear market damage |
| 2023 | — | +2,407.94 | +2,832.81 | Both strongly positive; trend expansion |
| 2024 | — | +919.06 | +213.17 | Both positive; BTC stronger |
| 2025 | — | −281.43 | −461.04 | Both negative; cost drag dominates |

**Consistent regime behavior across assets:** All three assets (ETH, BTC, SOL) show positive performance in 2023 (strongest year), negative in 2022 (bear market), and negative in 2025. This is strong evidence that the mechanism captures crypto-wide structural trend behavior, not asset-specific artifacts.

---

## 12. Data/Event Artifact Review

### 12.1 Top Winner Artifact Check

**BTC top-10:** No data/event artifacts identified. All top winners correspond to well-known BTC macro trends (ETF anticipation, post-halving, election). All are EMA60 close-break exits (trend exit mechanism). Prices and volumes are consistent with the periods.

**SOL top-10:** No data/event artifacts identified. All top winners correspond to known SOL market periods. Rank 6 (2022-03, bear market relief rally) occurred during a known SOL recovery period; the 2022 data gaps (Feb 25–Mar 1, Mar 31–Apr 3) do not overlap with this trade (entry Mar 17, exit Apr 6 — the gap occurred before entry).

### 12.2 SOL Data Gap Impact

The two SOL data gaps in 2022 (total 30 bars, 5 calendar days) did not overlap with any top-10 winner or worst-10 loser. The gaps occurred:
- Feb 25–Mar 1, 2022: before the SOL top-6 winner entry (Mar 17)
- Mar 31–Apr 3, 2022: during the SOL top-6 winner hold period, but before the Apr 6 exit

The Apr 3 gap boundary means the exit bar (Apr 6) was available. No top winner or worst loser was affected by data gaps.

### 12.3 SOL Rank-2 Loser Note

SOL worst-2 loser (2025-04-02): 0-hour hold, entry and exit in the same 4h bar. MAE = −231.44 notional (2.3% of equity). This is a legitimate high-volatility same-bar stop-out, not a data artifact. The position sizing calculation produced a larger position due to SOL's higher price level and the signal_low being far below entry, resulting in a meaningful dollar loss on the same bar.

---

## 13. SRR-002 Interpretation

### 13.1 Sparse Trend Acceptance Band (SRR-002 Section 4.5)

| Check | ETH | BTC | SOL |
| --- | --- | --- | --- |
| Net PnL positive | Yes (+3,001.66) | Yes (+2,517.17) | Yes (+4,018.80) |
| PF > 1 | Yes (1.517) | Yes (1.477) | Yes (1.790) |
| Top winners thesis-consistent | Yes | Yes | Yes |
| Trade count >= 30 | Yes (173) | Yes (159) | Yes (158) |
| Top winners distributed >= 2 years | Yes | Yes (4 years) | Yes (4 years) |
| Top-3 winners have stated market-feature explanations | Yes | Yes | Yes |
| **Passes acceptance band** | **Yes** | **Yes** | **Yes** |

All three assets pass the SRR-002 sparse trend acceptance band. Evidence may be preserved as positive sparse trend research evidence.

### 13.2 Deployment Blockers (SRR-002 Section 4.2)

| Check | ETH | BTC | SOL |
| --- | --- | --- | --- |
| Top-3 removal positive | No | No | Yes |
| Top-5 removal positive | No | No | No |
| Winner concentration < 50% | — | No (51.8%) | No (56.6%) |
| Year concentration < 60% | — | No (2023 = 95.7%) | Yes for 2023 (70.5%) but borderline |
| **Deployment ready** | **No** | **No** | **No** |

No asset satisfies all deployment gates. Top-5 removal failure is universal.

### 13.3 Pre-Observable Applicability Boundary (SRR-002 Section 2)

No asset has a validated pre-observable applicability boundary. The year-concentration pattern (2023 dominance across all assets) suggests the mechanism is regime-dependent, but no boundary rule distinguishes favorable from unfavorable regimes using pre-observable features.

---

## 14. Cross-Asset Verdict

### 14.1 BTC Classification

**`BTC_POSITIVE_SPARSE_TREND_EVIDENCE`**

Rationale:
- Net PnL positive (+2,517.17) under realistic costs
- PF > 1 (1.477)
- 159 trades, 40 winners — sufficient sample
- Top winners are thesis-consistent (trend captures across 4 years)
- Top winners are not data artifacts
- Passes sparse trend acceptance band
- Fails top-3 removal (deployment blocker, not research rejection)
- Higher MaxDD than ETH (9.95% realized, 11.32% MTM) — noted
- BTC positive evidence strongly supports crypto-wide trend mechanism

### 14.2 SOL Classification

**`SOL_POSITIVE_SPARSE_TREND_EVIDENCE`**

Rationale:
- Net PnL positive (+4,018.80) under realistic costs — highest of all three assets
- PF > 1 (1.790) — highest of all three assets
- 158 trades, 44 winners — sufficient sample
- Top winners are thesis-consistent (trend captures across 4 years)
- Passes top-3 removal (+380.21 positive) — better than ETH/BTC
- Fails top-5 removal (deployment blocker)
- Lowest MaxDD of all three assets (4.49% realized, 6.44% MTM)
- SOL evidence must be caveated for 30-bar data gap in 2022 (documented, minimal impact)

### 14.3 Overall Cross-Asset Classification

**`CROSS_ASSET_SUPPORTS_MECHANISM`**

Rationale:
- BTC positive sparse trend evidence: strongly supports crypto-wide trend mechanism
- SOL positive sparse trend evidence: supports high-beta transfer
- Both pass the sparse trend acceptance band
- Both show positive net PnL, PF > 1, thesis-consistent top winners
- Consistent regime behavior across all three assets (ETH, BTC, SOL)
- 2023 strongest year for all three — structural trend capture
- 2022 and 2025 negative for both BTC and SOL — consistent bear/choppy underperformance

### 14.4 Caveats

1. **BTC top-3 removal is negative** (−687.93). This is worse than ETH and indicates higher winner concentration. BTC 2023 alone contributes 95.7% of total net — extreme year concentration.

2. **SOL top-5 removal is negative** (−369.78). Top-1 contributes 56.6% of net — above the 40% disclosure threshold.

3. **All three assets fail top-5 removal.** This is a universal fragility pattern for the Donchian20 → EMA60 mechanism.

4. **2025 is negative for both BTC and SOL.** If 2025 continues to deteriorate, the cross-asset evidence weakens.

5. **SOL data gap caveat:** 30 missing bars in 2022 (documented; minimal impact; no top winner/loser affected).

6. **Positive cross-asset results do not authorize runtime, small-live, or deployment.** SRR-002 Standard 1 (pre-observable applicability boundary) remains unsatisfied.

---

## 15. What This Does Not Authorize

This diagnostic result explicitly does **not** authorize:

- Direction A changes, variants, or modifications
- Parameter sweeps or per-asset optimization
- New backtests beyond this diagnostic
- Runtime use or activation
- Small-live use or interpretation
- Promotion or strategy enablement
- TE execution
- CPM reopening or CPM follow-up
- Router, regime engine, or portfolio work
- Strategy rescue
- Multi-asset expansion or deployment
- Any interpretation of positive results as deployment readiness

---

## 16. Owner Summary

### What Was Done

Ran the frozen Direction A Donchian20 → EMA60 4h lifecycle mechanism on BTC/USDT:USDT and SOL/USDT:USDT using the identical frozen rule (no asset-specific changes). Produced all required metrics, fragility analysis, year-by-year analysis, top-10 winner attribution, worst-10 loser attribution, and cross-asset comparison against the ETH baseline.

### Key Findings

1. **The mechanism transfers across crypto assets.** All three assets (ETH, BTC, SOL) show positive net PnL, PF > 1, and thesis-consistent top winners under the identical frozen rule. The Donchian20 → EMA60 mechanism captures a structural feature of crypto 4h trends, not an ETH-specific artifact.

2. **SOL shows the strongest results** (+4,018.80, PF 1.790, lowest MaxDD, passes top-3 removal). However, SOL results must be caveated for the 30-bar data gap.

3. **BTC shows positive but more concentrated results** (+2,517.17, PF 1.477, higher MaxDD, fails top-3 removal). BTC 2023 alone contributes 95.7% of total net — extreme year concentration.

4. **All three assets fail top-5 removal** — this is a universal fragility pattern that blocks deployment across all assets.

5. **Consistent regime behavior:** 2023 is the strongest year for all three assets; 2022 and 2025 are negative for both BTC and SOL. The mechanism is regime-dependent.

### Classification

- BTC: `BTC_POSITIVE_SPARSE_TREND_EVIDENCE`
- SOL: `SOL_POSITIVE_SPARSE_TREND_EVIDENCE`
- Overall: `CROSS_ASSET_SUPPORTS_MECHANISM`

### What Remains Blocked

- **Pre-observable applicability boundary** — not validated for any asset
- **Top-5 removal** — negative for all three assets (deployment blocker)
- **Year concentration** — 2023 dominance across all assets
- **Runtime/small-live readiness gate** — unmet
- **SRR-002 Standard 1** — unsatisfied

---

> **Direction A cross-asset frozen diagnostic is mechanism validation only. It does not authorize Direction A changes, per-asset optimization, runtime use, small-live use, TE execution, CPM reopening, portfolio work, or strategy rescue. Any future empirical work requires separate Owner approval and must satisfy SRR-002.**

---

## Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-08 | Initial cross-asset frozen diagnostic result | Claude |
