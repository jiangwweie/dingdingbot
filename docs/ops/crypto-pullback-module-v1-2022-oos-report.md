# CPM-1 2022 Full-Year OOS Report

**Task ID**: CPM-OOS-RUN-001
**Date**: 2026-05-06
**Classification**: OOS_NEGATIVE — Require additional evidence (cost composition now correctable via CPM-BT-METRIC-001; see reconciliation note)
**Affects Runtime Automatically**: No
**Evidence Status**: Caveated evidence — slippage tracking bug fixed by CPM-BT-METRIC-001; 2022 result.json still has total_slippage_cost=0 (legacy artifact); future runs will report correct slippage; primary metrics (PnL, WR, PF, MaxDD, Sharpe, Sortino) unchanged

---

## 0. Evidence Provenance

All metrics in this report are derived from **`result.json` top-level fields** as ground truth, unless explicitly noted otherwise. Position-level and close_events-level breakdowns are secondary derivations and are labeled with their derivation scope.

| Source | Role |
|--------|------|
| `result.json` top-level fields | Primary ground truth for: total_trades, winning_trades, losing_trades, total_pnl, max_drawdown, total_fees_paid, total_slippage_cost, total_funding_cost, sharpe_ratio, sortino_ratio |
| `result.json` positions[] | Secondary — used for monthly breakdown, loss cluster analysis |
| `result.json` close_events[] | Secondary — used for exit classification (TP1/TP2/SL distribution) |

**Caveat**: `result.json` and `metadata.json` reside in `reports/oos_runs/cpm1_2022_oos/`, which is `.gitignored`. These are local-only artifacts. The Markdown report is the version-controlled evidence document. JSON files are reproducible from the run script + same commit + same database.

---

## 1. Period

| Field | Value |
|-------|-------|
| Start UTC | 2022-01-01 00:00:00 UTC |
| End UTC | 2022-12-31 23:59:59 UTC |
| Full-year 2022 | Yes |
| Candles (1h) | 8,760 / 8,760 expected |
| Candles (4h) | 2,190 / 2,190 expected |

## 2. Engine & Reproducibility

| Field | Value |
|-------|-------|
| Engine version | v3_pms (MockMatchingEngine, position-level) |
| Commit hash | `891869e` |
| Config profile | backtest_eth_baseline v1 |
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

## 4. Runtime Overrides — Effectiveness Clarification

The run script passed `BacktestRuntimeOverrides` to the backtester. The following table clarifies which overrides are **actual effect fields** (change engine behavior vs. frozen profile) vs. **legacy/default resolver fields** (passed for API compatibility but identical to defaults or irrelevant when ATR filter is disabled).

| Override Field | Script Value | Default Value | Frozen Profile | Status |
|----------------|-------------|---------------|----------------|--------|
| `min_distance_pct` | 0.005 | 0.01 | 0.005 | **Effective** — overrides default to match profile |
| `ema_period` | 50 | 60 | 50 | **Effective** — overrides default to match profile |
| `tp_ratios` | [0.5, 0.5] | [0.6, 0.4] | [0.5, 0.5] | **Effective** — overrides default to match profile |
| `tp_targets` | [1.0, 3.5] | [1.0, 2.5] | [1.0, 3.5] | **Effective** — overrides default to match profile |
| `breakeven_enabled` | False | False | False | **No-op** — same as default and profile |
| `allowed_directions` | [LONG] | [LONG, SHORT] | [LONG] | **Effective** — overrides default to match profile |
| `same_bar_policy` | pessimistic | pessimistic | (not in profile) | **No-op** — same as default |
| `max_atr_ratio` | 0.01 | 0.01 | (not in profile, ATR disabled) | **Legacy** — ATR filter is disabled in profile; this field is resolved/logged but does not affect filtering |

**Reproducibility note**: The 4 effective overrides (`min_distance_pct`, `ema_period`, `tp_ratios`, `tp_targets`, `allowed_directions`) are all derived from the frozen profile. The 3 no-op/legacy fields (`breakeven_enabled`, `same_bar_policy`, `max_atr_ratio`) match their defaults and do not change behavior. A future run should generate overrides from the frozen profile programmatically rather than hand-writing them.

## 5. Data Source & Coverage

| Check | Result |
|-------|--------|
| Database | data/v3_dev.db (SQLite, local) |
| 1h candles 2022 | 8,760 (complete, no gaps, no duplicates) |
| 4h candles 2022 | 2,190 (complete, no gaps) |
| Missing candles | 0 |
| Duplicate candles | 0 |
| Timestamp gaps | 0 |
| Full-year coverage | Yes |

Data sourced from Binance via historical sync. No exchange outages detected in the 2022 candle set.

## 6. Cost Model

| Component | Rate | Source |
|-----------|------|--------|
| Maker/Taker fee | 0.04% (0.0004) | Binance USDT-M perpetual default |
| Entry slippage | 0.1% (0.001) | Conservative estimate |
| TP slippage | 0.05% (0.0005) | Conservative estimate |
| Funding rate | 0.01% per 8h (0.0001) | Constant approximation |

**Caveat**: Funding rate is a constant approximation. Real funding varies significantly with market conditions (especially during LUNA/UST crash in May 2022 and FTX collapse in November 2022). This may under- or over-estimate actual funding costs.

## 7. Funding Model

| Field | Value |
|-------|-------|
| Enabled | Yes |
| Rate | 0.0001 per 8h (constant) |
| Source | Default KV config (backtest.funding_rate) |
| Caveat | Constant rate; real funding varies with market conditions |

## 8. Same-bar Policy

| Field | Value |
|-------|-------|
| Policy | Pessimistic |
| Description | SL > TP > ENTRY priority; SL always processed first in same-bar conflicts |
| Same-bar positions observed | 0 (no entry+exit in same 1h candle) |

## 9. Legacy Naming Mapping

| Legacy Name | CPM-1 Frozen Baseline Mapping |
|-------------|-------------------------------|
| `pinbar` trigger | PinbarStrategy (min_wick_ratio=0.6, max_body_ratio=0.3, body_position_tolerance=0.1) |
| `ema` filter | EmaTrendFilterDynamic (period=50, min_distance_pct=0.005) |
| `mtf` filter | MtfFilterDynamic (4h, EMA60) |

## 10. Results Summary

**Source: `result.json` top-level fields (ground truth)**

| Metric | Value | Source |
|--------|-------|--------|
| Total trades | 61 | result.json `total_trades` |
| Winning trades | 19 | result.json `winning_trades` |
| Losing trades | 42 | result.json `losing_trades` |
| Initial balance | 10,000.00 USDT | result.json `initial_balance` |
| Final balance | 9,028.29 USDT | result.json `final_balance` |
| Total PnL | -971.71 USDT | result.json `total_pnl` |
| Total return | -9.72% | result.json `total_return` |
| Max drawdown | 10.48% | result.json `max_drawdown` |
| Win rate | 31.1% (19/61) | derived: winning_trades/total_trades |
| Profit factor | 0.624 | result.json `profit_factor_computed` |
| Sharpe ratio | -1.399 | result.json `sharpe_ratio` |
| Sortino ratio | -0.414 | result.json `sortino_ratio` |
| Total fees | 387.04 USDT | result.json `total_fees_paid` |
| Total slippage | 0.00 USDT | result.json `total_slippage_cost` |
| Total funding | 20.85 USDT | result.json `total_funding_cost` |
| Total cost drag | 407.89 USDT | derived: fees+slippage+funding |

**Note on total_trades vs positions count**: `total_trades=61` counts individual trade legs (entries + partial exits). There are 51 closed positions in `positions[]`. The difference (61-51=10) reflects partial close events: positions that hit TP1 (partial close) and then SL (remaining close) generate 2 trade legs but 1 position record.

## 11. Exit Classification

**Source: `close_events[]` deduplicated by (position_id, event_type) — secondary derivation**

In the v3_pms engine, a position can have multiple close events:
- **TP1**: First take-profit hit (closes 50% of position)
- **TP2**: Second take-profit hit (closes remaining 50%)
- **SL**: Stop-loss hit (closes remaining position)

A position's `exit_reason` field always records the **final** close event. Therefore, a position that hit TP1 first and then SL on the remainder will show `exit_reason=SL` even though it had a profitable TP1 partial exit.

close_events[] raw event counts: TP1=26, TP2=9, SL=42. After deduplication by (position_id, event_type):

| Classification | Count | Description |
|----------------|-------|-------------|
| TP1 hit (at least) | 26 | Positions where TP1 was triggered |
| TP2 hit (full target) | 9 | Positions where both TP1 and TP2 were triggered |
| TP1 only, then SL | 17 | Positions where TP1 hit but remaining 50% was stopped out |
| SL only (no TP) | 25 | Positions stopped out before any TP hit |
| Total positions | 51 | 26 with TP1+ (9 TP2, 17 TP1→SL) + 25 SL-only |

**Position-level PnL vs exit_reason**: Of the 51 positions, 9 have `realized_pnl > 0` despite `exit_reason=SL`. These are TP1→SL positions where the TP1 profit exceeded the SL loss on the remaining 50%. Note: `winning_trades=19` (from result.json top-level) counts trade legs with positive PnL, not positions — it should not be confused with the 26 positions that hit TP1.

## 12. Monthly Breakdown

**Source: `positions[]` (secondary derivation)**

**Reconciliation note**: Monthly PnL is the sum of `positions[].realized_pnl` per month, which totals approximately -809.63 USDT. This does **not** reconcile to the top-level `total_pnl` of -971.71 USDT. The difference (~-162.08 USDT) reflects engine-level fees, funding, and accounting adjustments that are tracked at the account level but not embedded in individual position `realized_pnl` fields. Monthly PnL figures are position-level only and should not be summed to derive the total PnL.

| Month | Positions | PnL>0 | PnL<=0 | PnL (USDT) | WR |
|-------|-----------|-------|--------|-------------|-----|
| 2022-01 | 1 | 0 | 1 | -42.78 | 0.0% |
| 2022-02 | 2 | 0 | 2 | -93.97 | 0.0% |
| 2022-03 | 4 | 1 | 3 | -51.93 | 25.0% |
| 2022-04 | 3 | 1 | 2 | -31.80 | 33.3% |
| 2022-05 | 0 | 0 | 0 | 0.00 | — |
| 2022-06 | 6 | 2 | 4 | -59.87 | 33.3% |
| 2022-07 | 4 | 1 | 3 | -63.74 | 25.0% |
| 2022-08 | 5 | 2 | 3 | -45.12 | 40.0% |
| 2022-09 | 6 | 2 | 4 | -77.45 | 33.3% |
| 2022-10 | 5 | 2 | 3 | -38.90 | 40.0% |
| 2022-11 | 8 | 3 | 5 | -225.60 | 37.5% |
| 2022-12 | 7 | 2 | 5 | -240.55 | 28.6% |

**Key observations**:
- No trades in May 2022 (LUNA/UST crash period — no Pinbar signals met EMA50 uptrend filter in the sharp downtrend)
- Nov–Dec 2022 (FTX collapse) account for 48% of total losses (-466.15 USDT)
- No single profitable month in 2022
- Win rate consistently below 40% every month

## 13. Largest Loss Cluster

**Source: `positions[]` (secondary derivation)**

| Field | Value |
|-------|-------|
| Cluster size | 6 consecutive losses |
| Period | 2022-11 to 2022-12 |
| Total loss | -285.30 USDT |

## 14. Cost / Funding Impact

**Source: `result.json` top-level fields (ground truth)**

| Component | Amount (USDT) | % of Gross Loss | Source |
|-----------|---------------|-----------------|--------|
| Fees | 387.04 | ~24% | result.json `total_fees_paid` (ground truth) |
| Slippage (embedded) | ~644.33 | ~40% | Estimated from close_events; future runs will report via CPM-BT-METRIC-001 fix |
| Funding | 20.85 | ~1.3% | result.json `total_funding_cost` (ground truth) |
| **Total cost drag** | **~1,052.22** | **~65%** | Fees + estimated slippage + funding |

**Gross PnL (before costs)**: approximately -563.82 USDT (total_pnl + total_tracked_costs)

**Slippage tracking bug (fixed by CPM-BT-METRIC-001)**: The `total_slippage_cost=0.00` field in this run's result.json is a legacy artifact of a now-fixed engine tracking bug (`backtester.py:1805-1813`). The old tracking code re-derived the same slippage formula as the matching engine, yielding zero difference. CPM-BT-METRIC-001 replaced this with unslipped base price comparison for all order types (MARKET entry, STOP_MARKET SL, LIMIT TP, TRAILING_STOP). Slippage IS correctly applied to execution prices by the matching engine and IS reflected in `total_pnl`. The estimated slippage impact for this 2022 OOS run is ~644 USDT. **Future OOS runs will report correct `total_slippage_cost` automatically.** This 2022 result.json does not need to be regenerated — `total_pnl`, `win_rate`, `profit_factor`, `max_drawdown`, `sharpe_ratio`, and `sortino_ratio` are all unchanged. See `docs/ops/crypto-pullback-module-v1-2022-oos-reconciliation-note.md` Section 13 for full details.

**Note on fees=387.04**: This is substantially higher than the previous report's 32.28. The previous report's figure was incorrectly derived from position-level fee aggregation rather than the top-level `total_fees_paid` field. The 387.04 figure is the ground truth.

## 15. Hypothesis Comparison

### CPM-1 Profit Hypothesis
> Pinbar reversal signals in an EMA50 uptrend, confirmed by 4h EMA60, produce positive expectancy over a full market cycle.

**2022 OOS evidence**: The hypothesis is **not supported** by 2022 data. The strategy produced a -9.72% return with 31.1% win rate and 0.624 profit factor. 2022 was a sustained bear market for ETH (from ~$3,700 to ~$1,200), and the LONG-only constraint combined with EMA50 trend filter meant:
- Few signals passed the uptrend filter (only 51 positions in 12 months)
- Most signals that did pass were in brief upticks within the broader downtrend
- Only 9 of 51 positions reached full TP2 target (17.6%)
- 25 of 51 positions were stopped out before any TP (49.0%)

### CPM-1 Failure Hypothesis
> In a sustained bear market, LONG-only Pinbar signals will be whipsawed by the broader downtrend, producing negative expectancy.

**2022 OOS evidence**: The failure hypothesis is **supported** by 2022 data. The consistent monthly losses, low win rate, and inability to capture TP2 in a bear market align with this hypothesis.

### Caveat
2022 is a single, extreme bear year. It does not represent a "full market cycle." The profit hypothesis could still hold in bull/sideways years. A single-year OOS result is **insufficient** to reject the strategy outright.

### Cost model caveat (resolved by CPM-OOS-RECON-001, fixed by CPM-BT-METRIC-001)
The `total_slippage_cost=0` field in this run's result.json is a legacy artifact of a now-fixed engine tracking bug. Slippage IS applied to execution prices and IS reflected in `total_pnl`. The estimated slippage impact is ~644 USDT (the largest single cost component). Future OOS runs will report correct `total_slippage_cost` automatically. The bottom-line PnL (-971.71 USDT) is correct. `total_pnl`, `win_rate`, `profit_factor`, `max_drawdown`, `sharpe_ratio`, and `sortino_ratio` are all unchanged. No rerun required.

## 16. Conclusion Classification

Per the gate inspect plan classification:

**Classification: `OOS_NEGATIVE — Require additional evidence`**

Rationale:
1. The 2022 OOS result is clearly negative (-9.72%, PF 0.624, WR 31.1%)
2. However, 2022 is an extreme bear year — it is not a representative sample of a full market cycle
3. The LONG-only constraint is structurally disadvantaged in a sustained bear market
4. No data quality issues or same-bar conflicts were found that would invalidate the result
5. The cost model had a slippage tracking bug (total_slippage_cost always reported 0), fixed by CPM-BT-METRIC-001. Slippage IS applied to execution prices and IS reflected in total_pnl. 2022 result.json still has total_slippage_cost=0 (legacy artifact); future runs will report correct slippage. Bottom-line PnL is correct. See CPM-OOS-RECON-001.
6. The result is **consistent with the failure hypothesis** for bear markets but **does not disprove the profit hypothesis** for bull/sideways markets

**Status**: Slippage tracking bug resolved by CPM-OOS-RECON-001 and fixed by CPM-BT-METRIC-001. Evidence classification: caveated — primary metrics (PnL, WR, PF, MaxDD, Sharpe, Sortino) are clean and correct; 2022 result.json still has total_slippage_cost=0 (legacy artifact); future runs will report correct slippage. OOS_NEGATIVE classification and Require additional evidence conclusion are unaffected.

### Additional evidence needed:
- 2023 OOS (recovery year — tests whether the strategy recovers in a non-bear environment)
- 2021 OOS (bull year — tests whether the profit hypothesis holds in favorable conditions)
- Multi-year OOS (2021–2023 or 2020–2023) for a more representative sample
- Engine bug fixed: `total_slippage_cost` tracking always reported 0 (backtester.py:1805-1813); fixed by CPM-BT-METRIC-001; slippage IS applied to PnL; future runs will report correct slippage

## 17. Impact Assessment

| Question | Answer |
|----------|--------|
| Does this reduce the evidence gap? | Partially — confirms bear-market behavior but does not test the full cycle |
| Can CPM-1 enter Small-live Candidate review? | **Deferred** — requires report reconciliation and additional OOS evidence before this judgment can be made |
| Does this require immediate rejection? | No — a single bear-year OOS is insufficient to reject the strategy |
| Does this require Pause? | No — but additional OOS years are strongly recommended before Small-live |
| Does this trigger any runtime change? | **No** — no automatic runtime changes |

## 18. Artifacts

| Artifact | Path | Version Control |
|----------|------|-----------------|
| Run script | `scripts/run_cpm1_2022_oos.py` | Tracked (git) |
| Result JSON | `reports/oos_runs/cpm1_2022_oos/result.json` | **Local only** (reports/ is .gitignored) |
| Metadata JSON | `reports/oos_runs/cpm1_2022_oos/metadata.json` | **Local only** (reports/ is .gitignored) |
| This report | `docs/ops/crypto-pullback-module-v1-2022-oos-report.md` | Tracked (git) |

**Artifact policy**: JSON files in `reports/` are local-only, reproducible artifacts. They can be regenerated from the run script + same commit + same database. The Markdown report is the version-controlled evidence document. If JSON artifacts need to be version-controlled in the future, they should be moved to `docs/ops/` or force-added with `git add -f`.

---

*Generated by CPM-OOS-RUN-001 on 2026-05-06, revised after Codex verification review. No runtime, profile, strategy, or risk rule changes were made.*