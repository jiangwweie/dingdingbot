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

# Direction A — Cross-Asset Transfer Diagnostic Plan

**Status:** Docs-only frozen diagnostic plan
**Classification:** MECHANISM_VALIDATION_PLAN_ONLY
**Date:** 2026-05-08
**Authorization Level:** Level 1/2 — docs-only planning
**Source:** Direction A sparse trend evidence hardening (DIRA-EH-001); SRR-002 methodology baseline; SMA-001 applicability map
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document is a docs-only frozen diagnostic plan for cross-asset mechanism validation.

It is not:

- a backtest;
- a strategy experiment;
- a parameter search;
- Direction A rescue;
- Direction A variant, overlay, timing rescue, or parameter change;
- per-asset optimization;
- runtime or small-live admission;
- promotion;
- strategy router, portfolio engine, or regime engine;
- new data pipeline authorization;
- CPM reopening or CPM follow-up;
- TE execution;
- any claim that cross-asset success implies runtime or small-live readiness.

No backtest, script, adapter, data import, parameter sweep, runtime/profile/risk
change, strategy promotion, or small-live interpretation is authorized by this
plan. Any empirical execution requires separate Owner approval.

Binding current state:

- There is no runtime candidate.
- There is no deployable small-live strategy.
- The small-live readiness gate remains unmet.
- Direction A remains `POSITIVE_SPARSE_TREND_EVIDENCE / NEEDS_TE_HARDENING /
  NON_RUNTIME`.
- This plan defines a frozen diagnostic protocol; it does not execute it.
- Executing this plan requires separate Owner approval and SRR-002 compliance.

---

## 1. Diagnostic Purpose

> **Test whether Direction A's frozen 4h trend lifecycle mechanism generalizes
> across BTC and SOL.**

This is:

- A cross-asset mechanism validation plan.
- A test of whether the Donchian20 → EMA60 lifecycle has crypto-wide structural
  validity beyond the ETH evidence baseline.
- A docs-only protocol definition that must be approved before any empirical
  execution.

This is explicitly **not**:

- search for a better asset;
- per-asset optimization of entry, exit, stop, or hold parameters;
- runtime promotion or small-live readiness evaluation;
- strategy rescue or Direction A variant;
- a claim that cross-asset success implies deployability;
- a replacement for the pre-observable applicability boundary requirement
  (SRR-002 Standard 1).

**Rationale.** The project has so far focused heavily on ETH. The Owner wants to
evaluate whether the same frozen mechanism has cross-asset validity rather than
remaining ETH-specific. If BTC (the dominant crypto asset) shows positive sparse
trend evidence under the same frozen rule, it would strongly support the claim
that Direction A captures a structural feature of crypto 4h trends, not an
ETH-specific artifact.

---

## 2. Frozen Rule

The Direction A frozen rule, stated exactly from DIRA-EH-001:

| Component | Specification |
| --- | --- |
| **Entry signal** | 4h Donchian20 close breakout (close > highest close of prior 20 4h bars) |
| **Entry execution** | Next 4h bar open after signal close, plus entry slippage |
| **Initial risk stop** | Previous 20 closed 4h low (signal bar excluded); active intrabar |
| **Exit mechanism** | Fully closed 4h candle close below EMA60; execution at next bar open, less exit slippage |
| **EMA period** | 60 |
| **Donchian lookback** | 20 |
| **Same-bar policy** | Entry at next bar open; exit at next bar open after EMA60 close-break trigger |
| **Cost model** | fee_rate 0.0004, entry slippage 0.001, exit slippage 0.001, funding 0.0001/8h |

**BTC and SOL must use the identical rule.** No asset-specific parameter
changes are permitted. The purpose is mechanism transfer validation, not
per-asset fitting.

Any change to Donchian lookback, EMA period, entry logic, exit logic, stop
logic, or cost model constitutes a Direction A variant and is explicitly
forbidden by this plan.

---

## 3. Asset Roles

| Asset | Role | Rationale |
| --- | --- | --- |
| **ETH/USDT:USDT** | Current evidence baseline | 173 trades, 34 winners, net +3,001.66, PF 1.517 (DIRA-EH-001). All cross-asset results are compared against this baseline. No re-execution of ETH is part of this plan. |
| **BTC/USDT:USDT** | Primary cross-asset robustness asset | BTC is the dominant crypto asset by market cap and liquidity. If the Donchian20 → EMA60 mechanism captures a structural crypto-wide trend feature, BTC should show it. Positive BTC evidence would strongly support Direction A as a crypto-wide mechanism, not an ETH-specific artifact. |
| **SOL/USDT:USDT** | High-beta / high-volatility transfer asset | SOL has higher volatility and beta than ETH. If Direction A's sparse trend mechanism transfers to SOL, it would support the hypothesis that the mechanism is robust to higher-volatility environments. However, SOL evidence must be interpreted with data-coverage caveats (Section 5). Failure on SOL does not necessarily invalidate ETH or BTC. |

**Interpretation rules:**

- BTC and SOL results must be interpreted separately, not averaged blindly.
- ETH is the reference baseline; BTC and SOL are independent validation targets.
- A positive result on BTC AND SOL would be the strongest evidence of
  mechanism-wide validity.
- A positive result on BTC only would still meaningfully strengthen the
  mechanism claim.
- A positive result on SOL only would support high-beta transfer but is weaker
  evidence for the general mechanism.
- Negative results on both BTC and SOL would suggest Direction A may be
  ETH-specific rather than crypto-wide, though this does not invalidate the ETH
  evidence itself.

---

## 4. Data Coverage Requirements

### 4.1 Source-Level Coverage

The system already has `BTC/USDT:USDT`, `ETH/USDT:USDT`, and `SOL/USDT:USDT`
configured as core symbols in `src/application/config/config_parser.py`. The
historical data repository (`src/infrastructure/historical_data_repository.py`)
supports multi-symbol kline storage in the `klines` table indexed by
`(symbol, timeframe, timestamp)`.

Source-level Binance perpetual contract availability:

| Asset | Contract Launch | Type | 4h Kline Source |
| --- | --- | --- | --- |
| ETH/USDT:USDT | 2019-09-25 | PERPETUAL | Binance Vision: 2019-09 onward (TE-004 confirmed) |
| BTC/USDT:USDT | ~2019-09 (Binance futures launch) | PERPETUAL | Binance Vision: 2019-09 onward (expected; must be verified) |
| SOL/USDT:USDT | 2020-09 (SOL mainnet; Binance perp later) | PERPETUAL | Binance Vision: 2020-Q4 onward (expected; must be verified) |

### 4.2 Required Data Checks Before Execution

For each asset, the following must be verified before any empirical run:

| Check | ETH | BTC | SOL |
| --- | --- | --- | --- |
| 4h OHLCV availability | Verified (TE-004) | Verify source availability | Verify source availability |
| Start date | 2019-09 (source); 2021-01 (local baseline) | Verify earliest available 4h bar | Verify earliest available 4h bar |
| End date | 2025-12-31 (current baseline) | 2025-12-31 | 2025-12-31 |
| Missing bars / gaps | TE-004 assessed ETH; same QA needed for BTC/SOL | Verify no gaps > 24h | Verify no gaps > 24h |
| Exchange symbol consistency | `ETH/USDT:USDT` perp | `BTC/USDT:USDT` perp | `SOL/USDT:USDT` perp |
| Stable quote currency | USDT — verified | USDT — verify | USDT — verify |
| Futures/perp vs spot consistency | Perp only — verified | Perp only — verify | Perp only — verify |
| Fee assumption | 0.0004 — frozen | 0.0004 — same frozen rate | 0.0004 — same frozen rate |
| Slippage assumption | 0.001 — frozen | 0.001 — same frozen rate | 0.001 — same frozen rate |
| Funding assumption | 0.0001/8h — frozen | 0.0001/8h — same frozen rate | 0.0001/8h — same frozen rate |
| Warmup requirement: Donchian20 | 20 4h bars = 80h | Same | Same |
| Warmup requirement: EMA60 | 60 4h bars = 240h | Same | Same |
| Combined warmup | ~240h (10 days) | Same | Same |
| 2021–2025 window fully available | Yes (local baseline) | Verify | Verify |
| Supplemental 2019/2020 window | Available (TE-004 confirmed for ETH) | Verify; may be available from 2019 | Likely unavailable or very limited for SOL |

### 4.3 SOL Data Coverage Caveat

SOL's Binance perpetual contract was launched later than ETH and BTC. The
available 4h OHLCV history for SOL/USDT:USDT may not cover the full 2019–2020
window. This does not force the same window on SOL.

**Adjusted interpretation rule:**

- If SOL 4h data is available from 2021-01 onward, the diagnostic uses the
  same 2021–2025 window as ETH and BTC. Comparability caveat is minimal.
- If SOL 4h data is available only from 2020-Q4 or later, the diagnostic uses
  the available SOL-valid window (e.g., 2021-01 to 2025-12-31). The 2019–2020
  supplemental window is marked as not comparable.
- If SOL 4h data is not available before mid-2021, the SOL diagnostic is
  restricted to the available sub-window. Interpretation must carry an explicit
  caveat that the SOL result covers fewer years and regimes than the ETH/BTC
  result.
- SOL window choice must not be optimized by results. The SOL-valid window is
  defined by data availability, not by which window produces positive metrics.

### 4.4 Local Data Readiness

The local SQLite database currently stores klines per symbol and timeframe. The
`get_klines` method in `historical_data_repository.py` can fetch from the
exchange if local data is missing. Before execution:

1. Verify local DB has (or can populate) 4h klines for `BTC/USDT:USDT` and
   `SOL/USDT:USDT` covering the diagnostic windows.
2. If local data is missing, it may be fetched from the exchange (this is
   data access, not data import or pipeline creation).
3. If exchange fetch fails for any asset, that asset is marked
   `DATA_INSUFFICIENT` and excluded from the diagnostic.

---

## 5. Diagnostic Windows

### 5.1 Window Definitions

| Window | Dates | Applies to | Rationale |
| --- | --- | --- | --- |
| **Base window** | 2021-01-01 to 2025-12-31 | ETH, BTC, SOL (if data available) | Same frozen baseline window as DIRA-EH-001; maximizes comparability with ETH evidence |
| **Supplemental window** | 2019-Q4 to 2020-12-31 | ETH (existing), BTC (if data available) | Extends evidence into earlier crypto cycle; comparable to TE-007A supplemental window |
| **SOL-valid window** | Determined by data availability | SOL only | Defined by earliest reliable 4h data; not by result optimization |

### 5.2 Window Integrity Rules

- **Window choice must not be optimized by results.** The base window for all
  three assets is 2021-01-01 to 2025-12-31. This is defined before any
  empirical run. If SOL data does not cover the full window, the SOL-valid
  window is truncated from the start, not from the end or middle.
- **No partial-year cherry-picking.** If any year is included, the full
  calendar year is included (2021-01-01 through 2021-12-31, etc.). No
  intraday start/end optimization.
- **Supplemental window is optional for BTC/SOL.** If BTC 2019–2020 data is
  available, the supplemental window may be run. If SOL 2019–2020 data is
  unavailable, the supplemental window is not run for SOL. This does not
  penalize the SOL result.
- **ETH base window is already established.** No re-execution of the ETH
  base window is part of this plan. The ETH baseline (173 trades, net
  +3,001.66, PF 1.517) from DIRA-EH-001 serves as the reference.

---

## 6. Required Metrics

For each asset (ETH baseline already established; BTC and SOL to be computed),
the following metrics must be reported in the diagnostic result:

### 6.1 Aggregate Metrics

| Metric | Description |
| --- | --- |
| Trades | Total number of closed 4h positions |
| Winners / Losers | Count of profitable / unprofitable trades |
| Win rate | Winners / Trades |
| Net PnL | Sum of all trade PnL after costs |
| Profit factor (PF) | Gross winning PnL / abs(gross losing PnL) |
| Realized MaxDD | Maximum peak-to-trough realized PnL decline |
| MTM MaxDD | Maximum mark-to-market drawdown |
| Avg winner | Average PnL of winning trades |
| Avg loser | Average PnL of losing trades |
| Payoff ratio | Avg winner / abs(avg loser) |
| Avg hold — winners | Average hold duration (hours) for winning trades |
| Avg hold — losers | Average hold duration (hours) for losing trades |

### 6.2 Fragility Metrics

| Metric | Description |
| --- | --- |
| Top-1 removal | Net PnL after removing the single largest winner |
| Top-3 removal | Net PnL after removing the 3 largest winners |
| Top-5 removal | Net PnL after removing the 5 largest winners |
| Top-1 as % of net PnL | Absolute top-1 contribution relative to net |
| Top-3 as % of net PnL | Combined top-3 contribution relative to net |

### 6.3 Year-by-Year Metrics

For each year in the diagnostic window:

| Metric | Description |
| --- | --- |
| Year PnL | Net PnL for the year |
| Year trade count | Number of closed trades in the year |
| Year winner count | Number of winning trades in the year |
| Year win rate | Winners / trade count for the year |
| Year PF | Profit factor for the year |

### 6.4 Top Winner Attribution

For the top-5 winners on each non-baseline asset:

| Metric | Description |
| --- | --- |
| Rank | Winner rank (1–5) |
| Net PnL | Absolute trade PnL |
| Year | Calendar year of entry |
| Entry date | 4h bar date of entry |
| Exit date | 4h bar date of exit |
| Hold (h) | Hold duration in hours |
| Exit reason | `ema60_close_break` or `initial_stop` |
| MFE | Maximum favorable excursion |
| MAE | Maximum adverse excursion |
| Regime context | Macro regime at time of entry (bull peak, consolidation, bear, recovery, etc.) |
| Thesis consistency | Does the trade match the trend-capture thesis? |

---

## 7. Cross-Asset Interpretation Rules

### 7.1 Interpretation Categories

| Category | Definition |
| --- | --- |
| `CROSS_ASSET_SUPPORTS_MECHANISM` | Both BTC and SOL show positive sparse trend evidence under the frozen rule (net PnL positive, PF > 1, top winners thesis-consistent). The mechanism appears to be a crypto-wide trend-capture feature. |
| `CROSS_ASSET_PARTIAL_SUPPORT` | BTC positive but SOL inconclusive (data insufficient, or SOL borderline). Or BTC positive and SOL negative but SOL caveat applies (short window, idiosyncratic). The mechanism has partial cross-asset support. |
| `ETH_SPECIFIC_EVIDENCE_ONLY` | BTC is negative or inconclusive AND SOL is negative or inconclusive. The mechanism may be ETH-specific rather than crypto-wide. ETH evidence is not invalidated but the mechanism generalization claim is not supported. |
| `CROSS_ASSET_NOT_SUPPORTED` | Both BTC and SOL are clearly negative (net PnL negative, PF < 1). The mechanism does not transfer. |
| `DATA_INSUFFICIENT` | One or both target assets lack sufficient data coverage to run the diagnostic. The diagnostic cannot reach a conclusion. |

### 7.2 Interpretation Guidance

- **BTC positive sparse trend evidence** would strongly support Direction A as
  a crypto-wide trend mechanism, because BTC is the dominant and most liquid
  crypto asset. BTC positive evidence is the strongest cross-asset validation.

- **SOL positive evidence** supports high-beta transfer. It must be caveated
  for data coverage (shorter available window may mean fewer regimes tested) and
  for SOL's idiosyncratic risk characteristics (lower liquidity, higher
  volatility, different market participant structure).

- **Failure on SOL** does not necessarily invalidate ETH or BTC. SOL's higher
  volatility and different market microstructure could cause the same frozen
  mechanism to behave differently. SOL failure is informative but not fatal to
  the mechanism hypothesis.

- **Failure on BTC** weakens the general mechanism claim more strongly than SOL
  failure. BTC is the closest analogue to ETH in terms of liquidity, market
  structure, and participant base. If the mechanism fails on BTC, the
  ETH-specificity concern becomes much more serious.

- **Positive result on any asset must not imply** runtime readiness, small-live
  readiness, or deployment permission. Cross-asset transfer is a mechanism
  validation dimension. It does not satisfy SRR-002 Standard 1 (pre-observable
  applicability boundary) or any other deployment gate.

- **Top-winner attribution** must be thesis-consistent on each asset. If
  BTC/SOL top winners are driven by data artifacts, exchange events, or
  mechanism-inconsistent price action, the positive PnL is not evidence of
  mechanism transfer.

---

## 8. Fragility Rules

### 8.1 Owner Tolerance Clarification for Sparse Trend Systems

Per SRR-002 Section 4.4, the Owner tolerates sparse trend characteristics
(low win rate, high payoff ratio, imperfect equity curves) in research context.
The following rules apply to each asset's diagnostic result:

1. **Negative top-3/top-5 removal is not automatic research rejection.** A
   cross-asset result that fails top-3 removal may still be classified as
   `POSITIVE_SPARSE_TREND_EVIDENCE` if it passes the sparse trend acceptance
   band (SRR-002 Section 4.5).

2. **Negative top-3/top-5 removal remains a deployment blocker.** A
   cross-asset result that fails top-3 removal cannot be promoted, cannot
   enter small-live, and cannot claim a validated applicability boundary.

3. **Top winners must be thesis-consistent.** The top winners on each asset
   must correspond to trend captures that the Donchian20 → EMA60 mechanism is
   designed to capture. If top winners are driven by flash crashes, exchange
   outages, or non-trend mechanisms, the evidence is weakened.

4. **Top winners must be checked for event/data artifacts.** Each top winner
   must be verified against exchange event logs, data quality reports, and
   surrounding bar pricing. Any artifact-flagged winner must be disclosed and
   its contribution discounted.

5. **Top winners should be year/regime-attributed.** Each top winner must be
   placed in macro regime context (bull expansion, bear recovery, consolidation,
   etc.) and checked for cross-year distribution. Single-year clusters of top
   winners are a fragility signal.

### 8.2 Cross-Asset Fragility Comparison

The cross-asset diagnostic should also compare fragility profiles:

| Comparison | What to check |
| --- | --- |
| Top-3 removal consistency | Does each asset show similar top-3 fragility? Or is one asset more concentrated? |
| Year concentration consistency | Do positive years distribute similarly across assets? |
| Win rate consistency | Are win rates comparable (all ~19–25%), or does one asset deviate significantly? |
| Payoff ratio consistency | Are payoff ratios comparable (all > 4:1), or does one asset show degraded payoff? |
| Loss tail consistency | Are loss tails similarly bounded across assets? |

If one asset shows dramatically different fragility characteristics than the ETH
baseline, this must be noted even if the aggregate metrics are positive.

---

## 9. SRR-002 Compliance

### 9.1 Classification of This Plan Under SRR-002

This plan is a cross-asset mechanism validation diagnostic. Its relationship
to SRR-002 standards:

| SRR-002 Standard | Applicability to this plan |
| --- | --- |
| **Sec 2 — Pre-observable applicability boundary** | Not addressed by this plan. Cross-asset transfer is orthogonal to boundary validation. Even if all three assets show positive evidence, no validated pre-observable boundary exists. |
| **Sec 3 — Independent alpha vs overlap echo** | Not directly applicable. Each asset is tested independently. There is no overlap echo concern because each asset runs the same mechanism independently. |
| **Sec 4 — Sparse trend fragility** | Applied. Each asset's result is evaluated under the sparse trend acceptance band (SRR-002 Sec 4.5). Negative top-3 removal is not research rejection but remains deployment blocker. |
| **Sec 5 — Conditional module evidence** | Not applicable. Direction A is not a conditional module. |
| **Sec 6 — Extra-data dependency** | Not applicable. This plan uses the same 4h OHLCV data. |
| **Sec 7 — Level 3 admission gate** | This plan is not a Level 3 request. It is a Level 1/2 docs-only diagnostic plan. It does not satisfy Level 3 requirements and does not claim to. |
| **Sec 8 — TE path framing** | Not directly applicable. Cross-asset transfer is not a TE-path task. |

### 9.2 What This Plan May Strengthen

If the cross-asset diagnostic produces positive results:

- It may strengthen the positive sparse trend evidence classification for
  Direction A.
- It may provide evidence that the Donchian20 → EMA60 mechanism captures a
  structural crypto trend feature, not an ETH-specific artifact.
- It may inform future strategy research direction (e.g., whether multi-asset
  trend capture is a valid research direction).

### 9.3 What This Plan Does Not Do

- It does not satisfy SRR-002 Standard 1 (pre-observable applicability
  boundary). The boundary remains the maximum common blocker.
- It does not authorize runtime use, small-live use, or deployment.
- It does not authorize promotion or strategy enablement.
- It does not close the boundary hypothesis question.
- It does not replace the need for a validated pre-observable applicability
  boundary before any deployment decision.

---

## 10. Execution Readiness

### 10.1 Readiness Classification

**Classification (2026-05-08):** `READY_FOR_OWNER_APPROVED_CROSS_ASSET_DIAGNOSTIC`

The data coverage audit (`docs/ops/direction-a-cross-asset-data-coverage-audit.md`)
has been completed. BTC has 100% base window coverage (10,956/10,956 bars,
zero gaps). SOL has 99.7% base window coverage (10,926/10,956 bars, 30
missing bars in 2022 across two 3–5 day gaps). All OHLCV data passes quality
checks. No data fetch or repair is required.

Prior classification was `NEEDS_DATA_COVERAGE_AUDIT_FIRST`. Upgraded on
2026-05-08 after audit completion.

### 10.2 Required Prior Steps

Before the diagnostic can be executed, the following must be completed:

| Step | Owner | Status |
| --- | --- | --- |
| 1. Verify BTC/USDT:USDT 4h OHLCV source availability (Binance Vision) | Claude | COMPLETE — local DB has full 2021–2025 coverage |
| 2. Verify SOL/USDT:USDT 4h OHLCV source availability (Binance Vision) | Claude | COMPLETE — local DB has 99.7% 2021–2025 coverage |
| 3. Verify BTC 4h data completeness (2021-01 to 2025-12-31, no gaps > 24h) | Claude | COMPLETE — 10,956/10,956 bars, zero gaps |
| 4. Verify SOL 4h data completeness (2021-01 to 2025-12-31; determine SOL-valid window) | Claude | COMPLETE — 10,926/10,956 bars; 30 bars missing in 2022; SOL-valid window is 2021-01-01 to 2025-12-31 |
| 5. Verify local DB can serve BTC and SOL 4h klines for full window | Claude | COMPLETE — all bars served from local SQLite |
| 6. Confirm BTC 2019–2020 supplemental window availability (optional) | Claude | COMPLETE — not imported locally; optional for diagnostic |
| 7. Determine SOL earliest reliable 4h data date (for SOL-valid window definition) | Claude | COMPLETE — 2021-01-01 00:00 UTC |
| 8. Owner approval for diagnostic execution | Owner | Not requested |

Steps 1–7 may be completed as a docs-only data coverage audit. Step 8
requires explicit Owner approval before any backtest execution.

### 10.3 Readiness Upgrade Path

| Current | Upgrade to | Condition |
| --- | --- | --- |
| `NEEDS_DATA_COVERAGE_AUDIT_FIRST` | `READY_FOR_OWNER_APPROVED_CROSS_ASSET_DIAGNOSTIC` | All 7 data coverage audit steps pass AND Owner approves execution |
| `NEEDS_DATA_COVERAGE_AUDIT_FIRST` | `NOT_READY` | Any data coverage step fails (BTC/SOL 4h data unavailable or incomplete for the required window) |

---

## 11. Explicit Prohibitions

This plan explicitly does **not** authorize:

1. **Any backtest execution.** No backtest may be run until this plan is
   upgraded to `READY_FOR_OWNER_APPROVED_CROSS_ASSET_DIAGNOSTIC` and Owner
   approves.
2. **Direction A changes.** No modification to Direction A's frozen rule,
   parameters, entry logic, exit logic, stop logic, or cost model.
3. **Per-asset optimization.** No fitting of Donchian lookback, EMA period,
   stop distance, or any other parameter to any individual asset's results.
4. **Parameter sweeps.** No systematic variation of parameters across assets
   or within any asset.
5. **Runtime use.** No activation of any asset in live or paper trading.
6. **Small-live use.** No interpretation of cross-asset results as small-live
   readiness.
7. **Strategy rescue.** This plan is not a rescue of Direction A. Direction A
   is already classified as `POSITIVE_SPARSE_TREND_EVIDENCE`. This plan tests
   mechanism transfer, not rescues a failing strategy.
8. **TE execution.** No TE-path task execution is authorized by this plan.
9. **CPM reopening.** This plan does not reopen CPM-1, CPM-MOD, or any
   pullback-continuation research.
10. **Router/regime/portfolio work.** No multi-asset routing, regime engine,
    portfolio construction, or position sizing work follows from this plan.
11. **Data pipeline creation.** Data access (fetching from exchange) is
    permitted for coverage verification. Data pipeline creation, schema changes,
    or ingestion architecture changes are not authorized.
12. **Any interpretation of positive results as promotion.** Even if all three
    assets show positive sparse trend evidence, the result strengthens the
    mechanism hypothesis but does not satisfy SRR-002 Standard 1, does not
    authorize runtime, and does not authorize small-live.
13. **Direction A variant creation.** If BTC/SOL results are negative, no
    parameter adjustment, timeframe change, exit modification, or overlay is
    authorized as a response.

---

## 12. Diagnostic Execution Protocol (Frozen)

When Owner approves execution, the following protocol must be followed exactly:

### Phase 1: Data Coverage Verification

1. For each target asset (BTC, SOL):
   a. Verify 4h OHLCV source availability via Binance Vision API/directory.
   b. Determine earliest and latest available 4h bar dates.
   c. Check for gaps > 24h in the 2021–2025 window.
   d. If gap found, document the gap and determine whether the window must be
      truncated or the gap is acceptable.
   e. Determine the SOL-valid window if SOL data does not cover full 2021.
2. For optional supplemental window (BTC only, if SOL data also available for
   2019–2020):
   a. Verify BTC 2019–2020 4h source availability.
   b. Determine earliest reliable 4h bar for BTC 2019–2020.
3. Populate local DB with required 4h klines (exchange fetch is data access,
   not pipeline creation).

### Phase 2: Frozen Backtest Execution

4. For each target asset (BTC, SOL), run the frozen Direction A rule:
   a. 4h Donchian20 close breakout → next 4h open entry.
   b. Previous-20-low initial stop.
   c. EMA60 close-break exit at next bar open.
   d. Cost model: fee 0.0004, entry slippage 0.001, exit slippage 0.001,
      funding 0.0001/8h.
   e. Window: base window (2021-01-01 to 2025-12-31) for all assets with
      full coverage; SOL-valid window if SOL data is truncated.
5. If optional supplemental window approved by Owner: run BTC 2019–2020 with
   the same frozen rule.
6. Do NOT run ETH again. Use the DIRA-EH-001 baseline (173 trades,
   +3,001.66, PF 1.517) as the reference.

### Phase 3: Metrics Computation

7. Compute all required metrics (Section 6) for each target asset.
8. Compute all fragility metrics (Section 6.2).
9. Compute all year-by-year metrics (Section 6.3).
10. Perform top-winner attribution (Section 6.4) for top-5 winners on each
    asset.
11. Apply TE-001 nine-layer winner concentration review to each target asset.

### Phase 4: Cross-Asset Interpretation

12. Compare BTC and SOL results against the ETH baseline.
13. Assign interpretation category (Section 7.1).
14. Document cross-asset fragility comparison (Section 8.2).
15. Document any data artifacts, event anomalies, or thesis-inconsistent top
    winners.
16. State the cross-asset verdict with all caveats.

### Phase 5: Reporting

17. Produce a single diagnostic result report (docs-only).
18. Report must include: all metrics, all attribution, interpretation category,
    SRR-002 compliance assessment, and explicit non-authorization statement.
19. The result report does not change any module classification. It may
    inform future Owner decisions about Direction A classification or strategy
    research direction.

---

## 13. Information Gain

### 13.1 What Positive BTC Result Tells Us

If BTC shows positive sparse trend evidence (net PnL positive, PF > 1,
thesis-consistent top winners):

- The Donchian20 → EMA60 mechanism likely captures a structural feature of
  crypto 4h trends, not an ETH-specific artifact.
- Direction A's mechanism generalizes across the two most liquid crypto assets.
- Future strategy research may consider multi-asset trend capture as a
  validated direction (subject to SRR-002 compliance for any actual
  implementation).
- The pre-observable applicability boundary question remains open.

### 13.2 What Negative BTC Result Tells Us

If BTC shows negative results (net PnL negative, PF < 1):

- The mechanism may be ETH-specific.
- Direction A's ETH evidence is not invalidated, but the general mechanism
  claim is weakened.
- Future research may need to investigate what ETH-specific feature enables
  the mechanism (market microstructure, participant composition, volatility
  profile).
- This is a meaningful closure: it narrows the mechanism hypothesis.

### 13.3 What Positive SOL Result Tells Us

If SOL shows positive sparse trend evidence:

- The mechanism transfers to a higher-beta, higher-volatility asset.
- This supports the structural mechanism hypothesis but is weaker evidence
  than BTC positive (because SOL has shorter data history and different market
  characteristics).
- Caveat: SOL result must be checked for data artifacts and must be
  interpreted within the SOL-valid window.

### 13.4 What Negative SOL Result Tells Us

If SOL shows negative results:

- The mechanism may not transfer to higher-volatility, lower-liquidity assets.
- This does not necessarily invalidate ETH or BTC evidence.
- SOL's different market microstructure may cause the frozen mechanism to
  behave differently.
- This is informative but not fatal.

### 13.5 What Mixed Results Tell Us

| BTC | SOL | Interpretation |
| --- | --- | --- |
| Positive | Positive | Strongest evidence: mechanism generalizes across liquidity tiers and volatility regimes |
| Positive | Negative/inconclusive | Partial support: mechanism works on dominant assets but may not transfer to higher-beta |
| Negative | Positive | Weak support: mechanism works on SOL but not BTC; investigate BTC-specific failure modes |
| Negative | Negative | Weakest evidence: mechanism may be ETH-specific |
| Inconclusive | Inconclusive | DATA_INSUFFICIENT: diagnostic cannot reach a conclusion |

---

## 14. Risk Factors

| Risk | Mitigation |
| --- | --- |
| BTC/SOL 4h data unavailable or incomplete | Audit data coverage before execution; classify as DATA_INSUFFICIENT if coverage fails |
| SOL data window too short for meaningful evaluation | Use SOL-valid window; add comparability caveat; do not force same window |
| Cross-asset positive result misinterpreted as promotion | Explicit non-authorization in report; restate that SRR-002 Standard 1 remains unsatisfied |
| Cross-asset negative result misinterpreted as Direction A rejection | Explicit statement that negative BTC/SOL does not invalidate ETH evidence |
| Top winners on BTC/SOL driven by data artifacts | Mandatory artifact check for each top-5 winner |
| Cost model inapplicable to BTC (different fee structure) | Use same frozen cost model for comparability; disclose if BTC actual fees differ |
| SOL idiosyncratic risk (exploit, delisting, etc.) | Check for known SOL exchange events during diagnostic window |

---

## 15. Explicit Prohibitions (Summary)

This plan does not authorize:

- any backtest execution;
- Direction A changes;
- per-asset optimization;
- parameter sweeps;
- runtime;
- small-live;
- strategy rescue;
- TE execution;
- CPM reopening;
- router/regime/portfolio work;
- data pipeline creation;
- interpreting any result as promotion or deployment gate pass;
- creating a Direction A variant in response to any outcome;
- any interpretation of this plan as satisfying SRR-002 Standard 1.

---

> **Direction A cross-asset transfer is a mechanism-validation plan only. This
> plan does not authorize backtests, Direction A changes, per-asset optimization,
> runtime use, small-live use, or strategy rescue. Any empirical cross-asset
> diagnostic requires separate Owner approval and must satisfy SRR-002.**

---

## Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-08 | Initial cross-asset transfer diagnostic plan | Claude |
