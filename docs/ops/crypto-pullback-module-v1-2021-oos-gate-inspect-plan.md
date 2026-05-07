# Crypto Pullback Module v1 — 2021 OOS Gate Inspect Plan

**Task ID:** CPM-OOS-2021-PLAN-001
**Date:** 2026-05-06
**Status:** Historical planning artifact; OOS run completed
**Scope:** Baseline Strategy Module Stabilization governance

This document is an inspect plan and interpretation framework. It is not
experiment approval, not runtime promotion approval, not parameter tuning
approval, not live enablement approval, and not a backtest execution request.

**Current-state note (2026-05-06):** This plan is now a historical planning
artifact. The 2021 OOS run has been completed and was negative
(-2,153.76 USDT / -21.54%, PF 0.466, MaxDD 22.18%, slippage 1,040.85). After
CPM-OOS-FAILURE-CLASSIFY-001, CPM-1 is frozen and paused, is not a
Small-live Candidate, and its promotion path is stopped. No runtime, profile,
strategy, or risk-rule change follows automatically.

---

## 1. 2021 as OOS Candidate — Positioning

### 1.1 Market Characterization

2021 is a **strong bull year** for ETH with a mid-year correction:

| Period | Characterization |
|--------|-----------------|
| Jan–Apr 2021 | Sustained uptrend (ETH ~$730 → ~$2,500) |
| May 2021 | China ban crash (~$2,500 → ~$1,700, then recovery) |
| Jun–Aug 2021 | Recovery and consolidation (~$1,700 → ~$3,300) |
| Sep–Nov 2021 | Second leg up to ATH (~$3,300 → ~$4,878) |
| Dec 2021 | Post-ATH decline (~$4,878 → ~$3,700) |

ETH price range: $714.55 – $4,877.54 (full year).

### 1.2 Complementarity with 2022 OOS

| Dimension | 2022 OOS | 2021 OOS (candidate) |
|-----------|----------|----------------------|
| Market regime | Extreme bear (ETH $3,700 → $1,200) | Strong bull with correction (ETH $730 → $4,878) |
| LONG-only structural bias | Disadvantaged | Favored |
| EMA50 uptrend filter | Rarely active | Frequently active |
| Hypothesis tested | Failure hypothesis (bear) | Profit hypothesis (bull/sideways) |
| Evidence type | Stress test / boundary cost | Positive-expectancy validation |

2021 and 2022 are **complementary OOS candidates**: 2022 tests whether CPM-1 fails
as predicted in bear markets; 2021 tests whether CPM-1 profits as predicted in
favorable markets. Neither alone is sufficient; together they sample opposite
regimes.

### 1.3 Profit Hypothesis Test

2021 is the more direct test of the CPM-1 profit hypothesis:

> Pinbar reversal signals in an EMA50 uptrend, confirmed by 4h EMA60, produce
> positive expectancy over a full market cycle.

In 2021, the EMA50 uptrend filter should be active for most of the year, Pinbar
signals should be more frequent, and the LONG-only constraint is structurally
aligned with market direction. If CPM-1 does not produce positive results in
this environment, the profit hypothesis is directly challenged — not merely as
a boundary cost, but as a core mechanism failure.

This is distinct from 2022, which tests the failure hypothesis. 2021 tests
whether the mechanism works when conditions favor it.

---

## 2. Frozen Baseline

Any future 2021 OOS run must use the identical CPM-1 frozen baseline as the
2022 OOS run:

| Dimension | Frozen Baseline |
|-----------|----------------|
| Asset | `ETH/USDT:USDT` |
| Primary timeframe | `1h` |
| MTF timeframe | `4h` |
| Direction | `LONG-only` |
| Trigger | Pinbar (min_wick_ratio=0.6, max_body_ratio=0.3, body_position_tolerance=0.1) |
| Trend filter | EMA50 + min_distance_pct=0.005 |
| MTF filter | 4h EMA60 confirmation |
| ATR filter | Disabled, frozen as disabled |
| Exit | TP1 1.0R 50%, TP2 3.5R 50%, SL -1.0R, BE off, trailing off |
| Order strategy | OCO |

Rules:

- Do not change parameters because of anticipated 2021 behavior.
- Do not change parameters after seeing the 2021 result within the same task.
- Do not turn OOS into a tuning loop.
- Do not add E4, SHORT, cross-asset, cross-timeframe, regime, or portfolio logic.
- If the frozen baseline cannot be reconstructed exactly, the correct state is
  Pause / Require additional evidence, not ad-hoc substitution.

---

## 3. Pre-run Checklist

Before Owner approves any actual 2021 OOS run, the following must be confirmed
and recorded.

| # | Check | Required Confirmation | Current Status |
|---|-------|----------------------|----------------|
| 1 | ETH/USDT:USDT 1h data for 2021 | Data exists and is accessible | **Confirmed**: 8,760 candles in local DB |
| 2 | ETH/USDT:USDT 4h data for 2021 | Data exists and is accessible | **Confirmed**: 2,190 candles in local DB |
| 3 | Full-year coverage | 2021-01-01 00:00:00 UTC through 2021-12-31 23:59:59 UTC | **Confirmed**: Range 1609459200000–1640991600000, all 12 months complete |
| 4 | Missing candles | Count and location of any gaps | **Confirmed**: 0 gaps detected in 1h |
| 5 | Duplicate candles | Count of duplicate timestamps | **Confirmed**: 0 duplicates detected in 1h |
| 6 | Timestamp gaps | No unexpected inter-candle intervals | **Confirmed**: No gaps > 1h detected |
| 7 | Exchange outages | Any Binance outages affecting 2021 data | **Open**: May 2021 China ban crash — verify no exchange-side data gaps during high-volatility period |
| 8 | Binance futures symbol/contract differences | ETH/USDT:USDT perpetual contract specs in 2021 vs 2022 | **Open**: Binance USDT-M perpetual for ETH launched ~2020; verify tick size, lot size, and leverage rules were stable throughout 2021 |
| 9 | 2021 fee assumptions | Fee rate applicable to 2021 period | **Open**: Binance default taker fee was 0.04% in 2021; verify no BNB discount or VIP tier applies |
| 10 | Funding data availability | Whether real or constant-approximation funding is used | **Open**: Same constant 0.0001/8h approximation as 2022, or use real funding data if available |
| 11 | Slippage model compatibility | Slippage tracking uses CPM-BT-METRIC-001 corrected semantics | **Required**: Must use engine at commit >= 196bf2d (CPM-BT-METRIC-001 fix); future runs will report correct `total_slippage_cost` automatically |
| 12 | Same-bar policy | Matches 2022 OOS and CPM-1 evidence policy | **Required**: Pessimistic (SL > TP > ENTRY) |
| 13 | Backtest engine version | Recorded before execution | **Required**: v3_pms (MockMatchingEngine, position-level) |
| 14 | Commit hash | Repository commit hash for reproducibility | **Required**: Must be recorded at run time |
| 15 | Config/profile hash | Exact config/profile hash or immutable snapshot | **Required**: Must be recorded at run time |
| 16 | Legacy pinbar naming mapping | Resolved to CPM-1 frozen baseline | **Confirmed**: Same mapping as 2022 OOS (PinbarStrategy, EmaTrendFilterDynamic, MtfFilterDynamic) |
| 17 | Output report path | Defined before running | **Required**: `reports/oos_runs/cpm1_2021_oos/` (local-only, .gitignored) + version-controlled Markdown in `docs/ops/` |
| 18 | Owner approval gate | Owner explicitly approves running | **Required**: Not yet obtained |

Items marked **Open** must be resolved or explicitly caveated before the run
can be treated as promotion-grade evidence. Items marked **Required** must be
recorded at execution time.

### 3.1 Data Quality — Current Findings

As of 2026-05-06, the local SQLite database (`data/v3_dev.db`) contains:

- ETH/USDT:USDT 1h: 8,760 candles (complete, no gaps, no duplicates)
- ETH/USDT:USDT 4h: 2,190 candles (complete)
- Full 12-month coverage confirmed (Jan: 744, Feb: 672, Mar: 744, Apr: 720,
  May: 744, Jun: 720, Jul: 744, Aug: 744, Sep: 720, Oct: 744, Nov: 720,
  Dec: 744)
- ETH price range: $714.55 – $4,877.54

No hard data blockers found. Open items (exchange outages, contract rule
differences) are risk items to investigate, not current blockers.

---

## 4. Comparability with 2022 OOS

For 2021 results to be interpretable alongside 2022 results, the following
must be consistent:

| Dimension | 2022 OOS Value | 2021 OOS Requirement | Risk if Inconsistent |
|-----------|---------------|----------------------|---------------------|
| Cost model | fee_rate=0.0004, slippage_rate=0.001, tp_slippage_rate=0.0005 | **Must match** | Fee/slippage differences would make PnL non-comparable |
| Funding model | 0.0001/8h constant approximation | **Must match** | Different funding treatment would distort cost comparison |
| Same-bar policy | Pessimistic (SL > TP > ENTRY) | **Must match** | Different same-bar handling could change trade outcomes |
| Slippage tracking | 2022 run has total_slippage_cost=0 (legacy artifact of pre-fix engine) | **Must use CPM-BT-METRIC-001 fixed engine** (commit >= 196bf2d) | 2021 run will report correct slippage; 2022 result.json legacy artifact must not be misread |
| Engine version | v3_pms | **Must match** | Different engine semantics invalidate comparison |
| Frozen baseline | CPM-1 frozen parameters | **Must match** | Any parameter drift makes results non-comparable |
| Initial balance | 10,000 USDT | **Must match** | Different balance changes position sizing |

### 4.1 Slippage Tracking — Critical Comparability Note

The 2022 OOS was run on the pre-fix engine (commit 891869e). Its
`result.json` contains `total_slippage_cost=0` — a legacy artifact of the
now-fixed tracking bug (backtester.py:1805-1813). CPM-BT-METRIC-001 (commits
196bf2d, d1696e8, 3c3537b) fixed this by replacing self-referencing derivation
with unslipped base price comparison.

**Rules for 2021 run:**

1. The 2021 run **must** use the CPM-BT-METRIC-001 fixed engine. It will
   report correct `total_slippage_cost` automatically.
2. The 2022 `result.json` legacy `total_slippage=0` **must not** be misread as
   real zero slippage cost. The estimated 2022 slippage is ~644 USDT (from
   CPM-OOS-RECON-001).
3. When comparing 2021 and 2022 cost composition, the 2022 slippage figure
   must use the CPM-OOS-RECON-001 estimate (~644 USDT), not the legacy
   `total_slippage_cost=0` from result.json.
4. Bottom-line PnL, WR, PF, MaxDD, Sharpe, and Sortino are comparable across
   both runs because slippage IS applied to execution prices and IS reflected
   in `total_pnl` in both cases.

### 4.2 Funding Model — Comparability Caveat

Both runs use a constant 0.0001/8h funding approximation. Real funding varies
significantly:

- 2021 bull market: funding tends to be positive (longs pay shorts), which
  would increase costs for LONG-only positions.
- 2022 bear market: funding tends to be negative (shorts pay longs), which
  would reduce costs for LONG-only positions.

The constant approximation may **underestimate** 2021 funding costs and
**overestimate** 2022 funding costs relative to reality. This is a known
caveat that applies symmetrically. If real funding data becomes available,
both runs should be re-evaluated.

---

## 5. Interpretation Rules

The 2021 OOS result must be interpreted under these rules:

1. **2021 positive does not equal Small-live approval.** A single favorable
   year does not demonstrate robustness across market cycles.
2. **2021 negative does not equal immediate reject.** Even in a bull year,
   CPM-1 may underperform due to cost drag, thin signals, or specific
   sub-regime mismatch (e.g., May crash whipsaw).
3. **2021 thin trades / concentrated profits** should be classified as
   `Require additional evidence`. A few large wins in a bull market do not
   demonstrate repeatable edge.
4. **If data, cost, funding, same-bar, engine, or slippage semantics are not
   clean**, the result should be classified as `Caveated evidence` and must
   not be treated as promotion-grade.
5. **No post-result parameter rescue.** If 2021 is negative, do not tune
   parameters to improve it. Classify the failure first.
6. **No strategy rewrite based on a single-year result.** 2021 is one data
   point. It must be interpreted alongside 2022 and the 2023-2025 in-sample
   evidence.
7. **OOS must not trigger automatic parameter changes, runtime profile changes,
   risk rule changes, research engine changes, or live enablement changes.**
8. **Interpret the result against the frozen CPM-1 profit/failure hypothesis
   and market-boundary definition.**

### 5.1 2021-Specific Interpretation Context

2021 is a bull year. The EMA50 uptrend filter should be active for most of the
year, and LONG-only is structurally aligned. This creates specific
interpretation considerations:

- **If 2021 is positive**: This is the expected outcome under the profit
  hypothesis. It reduces the evidence gap but does not prove robustness
  — it only confirms the mechanism works when conditions favor it.
- **If 2021 is flat**: This is surprising in a bull year and suggests the
  strategy may not capture upside effectively, or that cost drag erodes
  gross profits. This would be a weaker signal than a positive result but
  not necessarily a failure — it depends on trade count and loss
  concentration.
- **If 2021 is negative**: This is a direct challenge to the profit
  hypothesis. If CPM-1 cannot profit in a favorable environment, the
  mechanism itself may be flawed, not just the market boundary. This is
  more serious than 2022 negative, which was consistent with the failure
  hypothesis. However, if the negative result is primarily driven by the
  May 2021 crash, a data/cost/funding caveat, or low trade count, the
  evidence should be classified first (as caveated evidence or
  Require additional evidence) rather than equated directly with module
  hypothesis failure.
- **May 2021 crash**: A sharp drawdown in May (China ban) is expected
  behavior for a LONG-only trend-following strategy. It should be
  interpreted as known boundary cost, not as mechanism failure, unless
  the drawdown is disproportionate relative to the recovery.

---

## 6. Decision Matrix

| # | OOS Outcome | Candidate State | Interpretation |
|---|-------------|----------------|----------------|
| 1 | Clear positive result, sufficient trades (≥40 positions), assumptions clean, hypothesis consistent | Evidence gap reduced; Small-live Candidate remains possible | 2021 confirms profit hypothesis in favorable conditions; still requires live-safe and Owner promotion review; does not automatically approve |
| 2 | Positive result but thin trades (<40 positions) or concentrated profits (top 3 trades > 50% of gross profit) | Require additional evidence | Do not over-read a narrow single-year result; bull market may produce few but large wins that are not repeatable |
| 3 | Flat / mildly negative result, absolute return < 5%, sufficient trades, assumptions clean | Continue Observation / Require additional evidence | In a favorable year this is weaker than expected; classify by trade count, cost drag, and loss concentration. Do not tune parameters inside the OOS task. |
| 4 | Severe negative result with clean assumptions and enough trades | Pause CPM-1 | If CPM-1 cannot profit in a favorable environment, the profit hypothesis is directly challenged; Owner review required; no automatic rebuild |
| 5 | Result dominated by data/cost/funding/slippage caveat | Caveated evidence — Require additional evidence | Evidence is not promotion-grade until assumptions are settled; resolve caveat before interpretation |
| 6 | Frozen baseline cannot be reproduced | Pause CPM-1 | Resolve reproducibility before interpretation; do not substitute parameters |
| 7 | Result conflicts with CPM-1 profit hypothesis (negative in favorable conditions, positive only via concentrated/unrepresentative wins) | Pause CPM-1 or Reopen Research | Owner review required; if mechanism is flawed, bounded research may be needed; no parameter rescue |

### 6.1 Trade Count Thresholds

| Threshold | Rationale |
|-----------|-----------|
| ≥40 positions | Minimum for meaningful WR/PF statistics in a single year |
| <40 positions | Result is thin; classify as Require additional evidence regardless of PnL sign |
| ≥60 positions | Comparable to 2022 (51 positions); allows direct regime comparison |

### 6.2 Concentration Thresholds

| Metric | Threshold | Action if Exceeded |
|--------|-----------|-------------------|
| Top 3 trades as % of gross profit | > 50% | Classify as concentrated; downgrade to Require additional evidence |
| Single-month PnL as % of total PnL | > 40% | Classify as concentrated; investigate sub-regime dependency |
| May 2021 drawdown as % of MaxDD | > 60% | Expected for China ban crash; do not over-penalize unless disproportionate |

---

## 7. Required Output Format for Future Approved Run

Any future approved 2021 OOS run must produce a report with at least these
fields:

| Field | Required Content |
|-------|-----------------|
| `period` | Exact UTC start/end and whether it is full-year 2021 |
| `engine_version` | Backtest engine version or implementation identifier |
| `commit_hash` | Git commit hash used for the run (must be ≥ 196bf2d for CPM-BT-METRIC-001 fix) |
| `config_profile_hash` | Frozen CPM-1 config/profile hash or immutable snapshot ID |
| `data_source` | Database path, data coverage notes, gap/duplicate audit results |
| `cost_model` | Fee assumptions, slippage rates, and source |
| `funding_model` | Funding inclusion/exclusion, rate, source, and caveats |
| `same_bar_policy` | Same-bar conflict policy |
| `corrected_total_slippage_cost` | Slippage cost from CPM-BT-METRIC-001 fixed engine (not legacy zero) |
| `trade_count` | Total trades and optional monthly/position count |
| `total_pnl` | Total PnL in report currency |
| `max_drawdown` | MaxDD with exact semantics |
| `win_rate` | Win rate over the OOS period |
| `profit_factor` | Profit factor if supported |
| `sharpe` | Sharpe ratio |
| `sortino` | Sortino ratio |
| `monthly_breakdown` | Full-year and monthly summary (positions, PnL, WR per month) |
| `largest_loss_cluster` | Largest drawdown/loss cluster with dates and trade count |
| `hypothesis_comparison` | Where result agrees or conflicts with CPM-1 profit/failure hypothesis |
| `conclusion_classification` | One of the classifications from Section 6 Decision Matrix |
| `affects_runtime_automatically` | Always `No` |

The report must explicitly state:

> "This OOS result does not automatically change runtime profile, strategy
> parameters, risk rules, or live status."

The report must also include a **comparability section** that:

1. States the 2021 cost model, funding model, same-bar policy, and slippage
   tracking version.
2. States the 2022 cost model, funding model, same-bar policy, and slippage
   tracking version (noting the legacy `total_slippage_cost=0` artifact).
3. Confirms or flags any differences that make the two results non-comparable.
4. Uses the CPM-OOS-RECON-001 estimated slippage (~644 USDT) for 2022 cost
   comparison, not the legacy `total_slippage_cost=0`.

---

## 8. Owner Approval Gate

Before any actual 2021 OOS run, Owner must confirm:

1. Is running 2021 OOS approved?
2. Is the current frozen CPM-1 baseline the only test object?
3. Is the no-parameter-change rule accepted?
4. Is it accepted that 2021 OOS success does not automatically promote CPM-1
   to Small-live Candidate?
5. Is it accepted that 2021 OOS failure is classified first (per Section 6)
   and does not immediately trigger strategy rebuild or parameter rescue?
6. Is the selected cost/funding/same-bar policy acceptable for promotion-grade
   interpretation?
7. Is full-year 2021 required, or is any narrower window acceptable only as a
   diagnostic supplement?
8. Is the CPM-BT-METRIC-001 fixed engine (commit ≥ 196bf2d) accepted as the
   required engine version?
9. Who reviews the output classification before CPM-1 state changes?
10. Is the 2021 result intended to be interpreted alongside 2022, or
    independently?

Without explicit Owner approval on these points, 2021 remains an unrun OOS
candidate and this document remains a plan only.

---

## 9. Not-now List

The following are explicitly not authorized by this inspect plan:

- No parameter change.
- No runtime change.
- No risk rule change.
- No E4 hard filter.
- No SHORT.
- No BTC/SOL expansion.
- No ETH 15m or 4h primary-timeframe expansion.
- No cross-asset or cross-timeframe expansion.
- No regime system.
- No portfolio.
- No multi-strategy.
- No live-safe change.
- No research engine or backtester change (beyond using the already-fixed
  CPM-BT-METRIC-001 engine).
- No automatic research-to-runtime promotion.
- No automatic Small-live Candidate status.
- No live enablement.
- No frontend control.
- No 2021 OOS run without Owner approval.
- No post-result parameter rescue.
- No strategy rewrite based on single-year result.

---

## 10. Relationship to Existing Governance

| Document | Relationship |
|----------|-------------|
| CPM-CRITERIA-001 (promotion/rejection criteria) | 2021 OOS is an evidence input to the criteria; this plan defines how the evidence is produced and interpreted |
| CPM-OOS-PLAN-001 (2022 OOS gate inspect plan) | 2021 is the complementary OOS candidate; results should be interpreted jointly |
| CPM-OOS-RUN-001 (2022 OOS report) | 2022 result provides the bear-market evidence point; 2021 provides the bull-market evidence point |
| CPM-OOS-RECON-001 (2022 reconciliation note) | Established that 2022 slippage=0 is a legacy artifact; 2021 must use fixed engine |
| CPM-BT-METRIC-001 (slippage fix) | Commits 196bf2d, d1696e8, 3c3537b; 2021 run must use engine at or after this fix |
| Live-safe v1 program | No live-safe code, runtime, or risk rule changes |

---

## 11. Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-05-06 | Initial 2021 OOS gate inspect plan | Claude (CPM-OOS-2021-PLAN-001) |
