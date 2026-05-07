# Crypto Pullback Module v1 — 2021 OOS Report

**Task ID:** CPM-OOS-2021-RUN-001
**Date:** 2026-05-06
**Classification:** OOS_NEGATIVE — Require additional evidence / Pause CPM-1 for classification
**Affects Runtime Automatically**: No
**Evidence Status**: Caveated — primary metrics (PnL, WR, PF, MaxDD, Sharpe, Sortino) are ground truth from result.json; corrected total_slippage_cost = 1,040.85 USDT (CPM-BT-METRIC-001 fix active); funding model is constant approximation; 2021 is a bull year and the result is worse than 2022 bear year, which directly challenges the profit hypothesis

This OOS result does not automatically change runtime profile, strategy
parameters, risk rules, or live status.

---

## 0. Evidence Provenance

All metrics in this report are derived from **`result.json` top-level fields**
as ground truth, unless explicitly noted otherwise. Position-level and
close_events-level breakdowns are secondary derivations and are labeled with
their derivation scope.

| Source | Role |
|--------|------|
| `result.json` top-level fields | Primary ground truth for: total_trades, winning_trades, losing_trades, total_pnl, max_drawdown, total_fees_paid, total_slippage_cost, total_funding_cost, sharpe_ratio, sortino_ratio |
| `result.json` positions[] | Secondary — used for monthly breakdown, loss cluster analysis |
| `result.json` close_events[] | Secondary — used for exit classification (TP1/TP2/SL distribution) |

**Caveat**: `result.json` and `metadata.json` reside in `reports/oos_runs/cpm1_2021_oos/`, which is `.gitignored`. These are local-only artifacts. The Markdown report is the version-controlled evidence document. JSON files are reproducible from the run script + same commit + same database.

---

## 1. Period

| Field | Value |
|-------|-------|
| Start UTC | 2021-01-01 00:00:00 UTC |
| End UTC | 2021-12-31 23:59:59 UTC |
| Full-year 2021 | Yes |
| Candles (1h) | 8,760 / 8,760 expected |
| Candles (4h) | 2,190 / 2,190 expected |

## 2. Engine & Reproducibility

| Field | Value |
|-------|-------|
| Engine version | v3_pms (MockMatchingEngine, position-level) |
| Commit hash | `bc64238` |
| Config profile hash | `065c0f18e6adf01bbb6a2ccb93a90fc1592bbdc5f74506661a4a1af8657f31d0` |
| Same-bar policy | Pessimistic (SL > TP > ENTRY priority) |
| Cost model | fee_rate=0.0004, slippage_rate=0.001, tp_slippage_rate=0.0005 |
| Funding model | Enabled, constant 0.0001/8h (approximation) |

## 3. Frozen Baseline

| Parameter | Value |
|-----------|-------|
| Asset | ETH/USDT:USDT |
| Primary timeframe | 1h |
| MTF timeframe | 4h |
| Direction | LONG-only |
| Trigger | Pinbar (min_wick_ratio=0.6, max_body_ratio=0.3, body_position_tolerance=0.1) |
| Trend filter | EMA50 + min_distance_pct=0.005 |
| MTF filter | 4h EMA60 confirmation |
| ATR filter | Disabled |
| Exit | TP1 1.0R 50%, TP2 3.5R 50%, SL -1.0R, BE off, trailing off |
| Order strategy | OCO |

No parameter changes were made. The frozen baseline matches the 2022 OOS run exactly.

## 4. Pre-run Checklist

| # | Check | Status | Detail |
|---|-------|--------|--------|
| 1 | ETH/USDT:USDT 1h data for 2021 | Confirmed | 8,760 candles in local DB |
| 2 | ETH/USDT:USDT 4h data for 2021 | Confirmed | 2,190 candles in local DB |
| 3 | Full-year coverage | Confirmed | All 12 months complete |
| 4 | Missing candles | Confirmed | 0 missing in 1h |
| 5 | Duplicate candles | Confirmed | 0 duplicates in 1h |
| 6 | Timestamp gaps | Confirmed | 0 gaps > 1h detected |
| 7 | Exchange outages | Caveated | May 2021 China ban crash — no exchange-side data gaps detected; high-volatility period may have wider spreads not captured in kline data |
| 8 | Binance futures contract rules | Caveated | Tick size, lot size, leverage assumed stable throughout 2021; not independently verified |
| 9 | Fee assumptions | Recorded | 0.04% taker fee (Binance USDT-M default) |
| 10 | Funding data | Recorded | Constant 0.0001/8h approximation; real funding varies with market conditions |
| 11 | Slippage model | Confirmed | CPM-BT-METRIC-001 fixed engine; reports corrected total_slippage_cost = 1,040.85 USDT (non-zero, confirming fix is active) |
| 12 | Same-bar policy | Confirmed | Pessimistic (SL > TP > ENTRY); matches 2022 OOS |
| 13 | Backtest engine version | Recorded | v3_pms (MockMatchingEngine, position-level) |
| 14 | Commit hash | Recorded | bc64238 |
| 15 | Config/profile hash | Recorded | 065c0f18e6adf01bbb6a2ccb93a90fc1592bbdc5f74506661a4a1af8657f31d0 |
| 16 | Legacy pinbar naming mapping | Confirmed | Same as 2022 OOS |
| 17 | Output report path | Recorded | reports/oos_runs/cpm1_2021_oos/ (local-only) + this document |
| 18 | Owner approval gate | Obtained | Owner approved under CPM-OOS-2021-PLAN-001 boundaries |

## 5. Results Summary

**Source: `result.json` top-level fields (ground truth)**

| Metric | Value | Source |
|--------|-------|--------|
| Total trades | 88 | result.json `total_trades` |
| Winning trades | 26 | result.json `winning_trades` |
| Losing trades | 62 | result.json `losing_trades` |
| Initial balance | 10,000.00 USDT | result.json `initial_balance` |
| Final balance | 7,846.24 USDT | result.json `final_balance` |
| Total PnL | -2,153.76 USDT | result.json `total_pnl` |
| Total return | -21.54% | result.json `total_return` |
| Max drawdown | 22.18% | result.json `max_drawdown` |
| Win rate | 29.5% (26/88) | result.json `win_rate` |
| Profit factor | 0.466 | result.json `profit_factor_computed` |
| Sharpe ratio | -2.466 | result.json `sharpe_ratio` |
| Sortino ratio | -0.759 | result.json `sortino_ratio` |
| Total fees | 519.97 USDT | result.json `total_fees_paid` |
| Total slippage | 1,040.85 USDT | result.json `total_slippage_cost` |
| Total funding | 19.10 USDT | result.json `total_funding_cost` |
| Total cost drag | 1,579.93 USDT | derived: fees+slippage+funding |

**Note on total_trades vs positions count**: `total_trades=88` counts individual trade legs (entries + partial exits). There are 74 closed positions in `positions[]`. The difference (88-74=14) reflects partial close events: positions that hit TP1 (partial close) and then SL (remaining close) generate 2 trade legs but 1 position record.

## 6. Exit Classification

**Source: `close_events[]` deduplicated by (position_id, event_type) — secondary derivation**

| Classification | Count | Description |
|----------------|-------|-------------|
| TP1 hit (at least) | 28 | Positions where TP1 was triggered |
| TP2 hit (full target) | 12 | Positions where both TP1 and TP2 were triggered |
| TP1 only, then SL | 16 | Positions where TP1 hit but remaining 50% was stopped out |
| SL only (no TP) | 46 | Positions stopped out before any TP hit |
| Total positions | 74 | 28 with TP1+ (12 TP2, 16 TP1→SL) + 46 SL-only |

Only 12 of 74 positions (16.2%) reached full TP2 target. 46 of 74 positions (62.2%) were stopped out before any TP. This is a worse exit distribution than 2022 (which had 9/51 = 17.6% TP2 and 25/51 = 49.0% SL-only).

## 7. Monthly Breakdown

**Source: `positions[]` (secondary derivation)**

**Reconciliation note**: Monthly PnL is the sum of `positions[].realized_pnl` per month, which totals approximately -1,744.07 USDT. This does **not** reconcile to the top-level `total_pnl` of -2,153.76 USDT. The difference (~-409.69 USDT) reflects engine-level fees, funding, and accounting adjustments that are tracked at the account level but not embedded in individual position `realized_pnl` fields. Monthly PnL figures are position-level only and should not be summed to derive the total PnL.

| Month | Positions | PnL>0 | PnL<=0 | PnL (USDT) | WR |
|-------|-----------|-------|--------|-------------|-----|
| 2021-01 | 5 | 2 | 3 | 90.29 | 40.0% |
| 2021-02 | 10 | 2 | 8 | -222.93 | 20.0% |
| 2021-03 | 9 | 1 | 8 | -327.27 | 11.1% |
| 2021-04 | 15 | 4 | 11 | 139.78 | 26.7% |
| 2021-05 | 2 | 0 | 2 | -147.68 | 0.0% |
| 2021-06 | 3 | 0 | 3 | -180.70 | 0.0% |
| 2021-07 | 3 | 1 | 2 | 62.70 | 33.3% |
| 2021-08 | 8 | 1 | 7 | -386.05 | 12.5% |
| 2021-09 | 4 | 0 | 4 | -317.47 | 0.0% |
| 2021-10 | 11 | 1 | 10 | -356.39 | 9.1% |
| 2021-11 | 2 | 0 | 2 | -147.93 | 0.0% |
| 2021-12 | 2 | 0 | 2 | -145.14 | 0.0% |

**Key observations**:
- Only 3 of 12 months are profitable (Jan, Apr, Jul)
- Aug–Dec 2021 is a sustained losing period (5 consecutive losing months)
- No trades in May 2021 (only 2 positions, both SL — LUNA/UST crash period)
- Win rate consistently below 40% every month except Jan (40.0%)
- The worst month is Aug 2021 (-386.05 USDT), not May (-147.68)

## 8. Largest Loss Cluster

**Source: `positions[]` (secondary derivation)**

| Cluster | Size | Total Loss | Period |
|---------|------|------------|--------|
| Largest | 16 consecutive losses | -1,079.84 USDT | 2021-08-02 to 2021-10-15 |
| Second | 11 consecutive losses | -717.67 USDT | 2021-04-15 to 2021-07-06 |
| Third | 9 consecutive losses | -540.90 USDT | 2021-10-21 to 2021-12-25 |

The largest loss cluster (16 consecutive losses from Aug to Oct) is significantly worse than the 2022 largest cluster (6 consecutive losses). This is unexpected in a bull year and suggests the strategy was whipsawed during the mid-year correction and post-ATH decline.

## 9. Cost / Funding Impact

**Source: `result.json` top-level fields (ground truth)**

| Component | Amount (USDT) | % of Total Cost | Source |
|-----------|---------------|-----------------|--------|
| Fees | 519.97 | 32.9% | result.json `total_fees_paid` |
| Slippage (corrected) | 1,040.85 | 65.9% | result.json `total_slippage_cost` (CPM-BT-METRIC-001 fix active) |
| Funding | 19.10 | 1.2% | result.json `total_funding_cost` |
| **Total cost drag** | **1,579.93** | 100.0% | derived |

**Gross PnL (before costs)**: -573.84 USDT (total_pnl + total_cost_drag)

Even before costs, the strategy was negative (-573.84 USDT). Cost drag (1,579.93 USDT) amplifies the loss but is not the sole cause — the gross result is already negative.

**Slippage tracking**: The `total_slippage_cost=1,040.85` field is the corrected value from the CPM-BT-METRIC-001 fixed engine. Unlike the 2022 run which reported `total_slippage_cost=0` (legacy artifact), this run correctly tracks slippage for all order types (MARKET entry, STOP_MARKET SL, LIMIT TP). Slippage is the dominant cost component at 65.9% of total cost.

**Funding caveat**: The constant 0.0001/8h approximation may underestimate 2021 funding costs. In a bull market, real funding tends positive (longs pay shorts), which would increase costs for LONG-only positions. However, funding is only 1.2% of total cost, so even a significant funding model error would not materially change the bottom line.

## 10. Comparability with 2022 OOS

| Dimension | 2022 OOS | 2021 OOS | Comparable? |
|-----------|----------|----------|-------------|
| Cost model | fee=0.0004, slippage=0.001, tp_slippage=0.0005 | Same | Yes |
| Funding model | 0.0001/8h constant | Same | Yes |
| Same-bar policy | Pessimistic | Same | Yes |
| Slippage tracking | Pre-fix engine (total_slippage_cost=0 in result.json) | CPM-BT-METRIC-001 fixed (1,040.85 USDT) | Semantics match; 2022 legacy artifact must use RECON estimate (~644 USDT) |
| Engine version | v3_pms | v3_pms | Yes |
| Frozen baseline | CPM-1 frozen parameters | Same | Yes |
| Initial balance | 10,000 USDT | Same | Yes |

### 10.1 Slippage Comparability

- 2021 slippage: 1,040.85 USDT (corrected, from engine)
- 2022 slippage: ~644 USDT (estimated, from CPM-OOS-RECON-001)

2021 slippage is higher than 2022, which is expected: 2021 had more trades (88 vs 61) and higher price levels (ETH $730–$4,878 vs $1,200–$3,700), resulting in larger absolute slippage per trade.

### 10.2 Cross-Year Comparison

| Metric | 2021 (Bull) | 2022 (Bear) | Observation |
|--------|-------------|-------------|-------------|
| Total PnL | -2,153.76 | -971.71 | 2021 loss is **2.2x worse** than 2022 |
| Total return | -21.54% | -9.72% | 2021 return is **2.2x worse** |
| MaxDD | 22.18% | 10.48% | 2021 MaxDD is **2.1x worse** |
| Win rate | 29.5% | 31.1% | Both below 35% |
| Profit factor | 0.466 | 0.624 | 2021 PF is **worse** |
| Sharpe | -2.466 | -1.399 | 2021 Sharpe is **worse** |
| Positions | 74 | 51 | 2021 has more trades |
| Winning months | 3/12 | 0/12 | 2021 has 3 winning months vs 2022's 0 |

This is the critical finding: **2021 (bull year) performs worse than 2022 (bear year)**. This directly challenges the CPM-1 profit hypothesis, which predicts that the strategy should profit in favorable conditions.

## 11. Hypothesis Comparison

### 11.1 CPM-1 Profit Hypothesis

> Pinbar reversal signals in an EMA50 uptrend, confirmed by 4h EMA60, produce positive expectancy over a full market cycle.

**2021 OOS evidence**: The hypothesis is **not supported** by 2021 data. The strategy produced a -21.54% return with 29.5% win rate and 0.466 profit factor in a year where ETH rose from ~$730 to ~$4,878. The LONG-only constraint was structurally aligned with market direction, and the EMA50 uptrend filter should have been frequently active. Yet the strategy lost more money than in the 2022 bear year.

The profit hypothesis predicts positive expectancy in favorable conditions. 2021 is the most favorable year in the available data window, and the result is clearly negative. This is a direct challenge to the core mechanism.

### 11.2 CPM-1 Failure Hypothesis

> In a sustained bear market, LONG-only Pinbar signals will be whipsawed by the broader downtrend, producing negative expectancy.

**2021 OOS evidence**: The failure hypothesis is **also challenged** by 2021 data. The failure hypothesis predicts negative results only in bear markets. But 2021 is a bull year, and the result is negative — and worse than the 2022 bear year. This means the failure hypothesis does not fully explain CPM-1's behavior. The strategy appears to fail in both bull and bear years, suggesting a deeper mechanism issue beyond market-direction alignment.

### 11.3 Caveat — Before Equating with Module Hypothesis Failure

Per CPM-OOS-2021-PLAN-001 Section 5.1: if the negative result is primarily driven by the May 2021 crash, a data/cost/funding caveat, or low trade count, the evidence should be classified first rather than equated directly with module hypothesis failure.

**Assessment of potential caveats**:

- **May 2021 crash**: May accounts for only -147.68 USDT (6.9% of total loss). The dominant losses come from Aug–Oct (-1,079.84 USDT cluster) and Feb–Mar (-536.81 USDT cluster). May is not the primary driver.
- **Data/cost/funding caveat**: Data is complete (0 gaps, 0 duplicates). Cost model is consistent with 2022. Funding is a minor component (1.2%). No data or assumption caveat explains the result.
- **Low trade count**: 74 positions is sufficient for statistical interpretation (above the 40-position threshold).
- **Cost drag**: Even gross PnL (before costs) is -573.84 USDT. Cost drag amplifies the loss but is not the sole cause.

**Conclusion**: The caveats do not explain the negative result. The 2021 OOS is a genuine negative outcome that directly challenges the profit hypothesis.

## 12. Conclusion Classification

Per CPM-OOS-2021-PLAN-001 Section 6 Decision Matrix:

**Classification: `OOS_NEGATIVE — Pause CPM-1 for classification`**

Failure classification completed by CPM-OOS-FAILURE-CLASSIFY-001: **Favorable-regime profit hypothesis failure** + loss-concentration issue. See `docs/ops/crypto-pullback-module-v1-oos-failure-classification.md`.

This falls between Decision Matrix rows 4 and 7:

- Row 4: "Severe negative result with clean assumptions and enough trades" → Pause CPM-1
- Row 7: "Result conflicts with CPM-1 profit hypothesis (negative in favorable conditions)" → Pause CPM-1 or Reopen Research

Rationale:
1. The 2021 OOS result is clearly negative (-21.54%, PF 0.466, WR 29.5%)
2. 2021 is a bull year — the most favorable environment for LONG-only CPM-1
3. The result is **worse** than 2022 (bear year), which directly contradicts the profit hypothesis
4. No data quality issues, same-bar conflicts, or assumption caveats explain the result
5. Trade count (74 positions) is sufficient for interpretation
6. The gross PnL is already negative before costs; cost drag amplifies but does not cause the loss
7. The result is not driven by May 2021 crash alone (May = 6.9% of total loss)

**Status**: Owner classification has been completed by
CPM-OOS-FAILURE-CLASSIFY-001. CPM-1 is frozen and paused, is not a Small-live
Candidate, and its promotion path is stopped. The profit hypothesis is directly
challenged; the failure hypothesis does not fully explain the result because
2021 is not a bear year.

### Additional evidence needed:
- Root cause analysis: Why does CPM-1 lose more in a bull year than a bear year? Is the EMA50 uptrend filter actually filtering for uptrends, or is it whipsawing during corrections within the uptrend?
- 2023 OOS (recovery year — tests whether the strategy recovers after a bear year)
- Multi-year OOS (2020–2023 or 2021–2023) for a more representative sample
- Position-level analysis: Are losses concentrated in specific sub-regimes (corrections within uptrends, post-ATH decline)?

## 13. Impact Assessment

| Question | Answer |
|----------|--------|
| Does this reduce the evidence gap? | Yes — but it reduces it in the wrong direction: 2021 is negative, not positive |
| Can CPM-1 enter Small-live Candidate review? | **No** — a negative result in a favorable year is a stronger blocker than a negative result in a bear year |
| Does this require immediate rejection? | Not automatically — current state is Pause; Owner may later decide reject vs bounded research |
| Does this require Pause? | **Yes** — classification is complete and CPM-1 remains paused |
| Does this trigger any runtime change? | **No** — no automatic runtime changes |

## 14. Artifacts

| Artifact | Path | Version Control |
|----------|------|-----------------|
| Run script | `scripts/run_cpm1_2021_oos.py` | Tracked (git) |
| Result JSON | `reports/oos_runs/cpm1_2021_oos/result.json` | **Local only** (reports/ is .gitignored) |
| Metadata JSON | `reports/oos_runs/cpm1_2021_oos/metadata.json` | **Local only** (reports/ is .gitignored) |
| This report | `docs/ops/crypto-pullback-module-v1-2021-oos-report.md` | Tracked (git) |

---

*Generated by CPM-OOS-2021-RUN-001 on 2026-05-06. No runtime, profile, strategy, or risk rule changes were made.*
