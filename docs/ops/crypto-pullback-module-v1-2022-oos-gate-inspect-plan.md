# Crypto Pullback Module v1 — 2022 OOS Gate Inspect Plan

**Task ID:** CPM-OOS-PLAN-001  
**Date:** 2026-05-06  
**Status:** Historical planning artifact; OOS run completed  
**Scope:** Baseline Strategy Module Stabilization governance

This document is an inspect plan and interpretation framework. It is not
experiment approval, not runtime promotion approval, not parameter tuning
approval, not live enablement approval, and not a backtest execution request.

**Current-state note (2026-05-06):** This plan is now a historical planning
artifact. The 2022 OOS run has been completed and was negative. After the later
2021 OOS run and CPM-OOS-FAILURE-CLASSIFY-001, CPM-1 is frozen and paused, is
not a Small-live Candidate, and its promotion path is stopped. No runtime,
profile, strategy, or risk-rule change follows automatically.

---

## 1. Status

Current status after run and failure classification:

- CPM-1 remains the current frozen baseline strategy module.
- The 2022 OOS run has been completed and was negative.
- The later 2021 OOS run was also negative and is classified as
  favorable-regime signal-level failure.
- CPM-1 is paused and is not a Small-live Candidate.
- CPM-1's promotion path is stopped.
- Current baseline parameters remain frozen.
- E4 / Donchian-distance may only be considered in future as a risk-state label
  research question, not as a hard filter.
- OOS results must not automatically modify strategy parameters, runtime
  profiles, risk rules, research engine behavior, or live promotion state.

This plan defines what must be checked before any future OOS run and how the
result should be interpreted after a run. It does not approve running 2022 OOS.

---

## 2. Purpose

2022 is the strongest current OOS candidate because CPM-1's main historical
evidence is concentrated in 2023-2025, and 2022 is outside that core evidence
window. The evidence interpretation note explicitly classifies 2022 as an
untested evidence gap.

This task is only an inspect plan because running OOS would create new research
evidence with promotion/rejection implications. That requires Owner approval,
fixed assumptions, and a pre-written interpretation framework before execution.

Within the promotion / rejection criteria, 2022 OOS sits between evidence
completeness and Small-live Candidate consideration:

1. CPM-1 can continue observation without OOS.
2. CPM-1 should not become Small-live Candidate unless Owner either waives or
   accepts the 2022 OOS gate.
3. Owner's current preliminary decision is that 2022 OOS should be a gate before
   Small-live Candidate status.
4. Passing the gate reduces an evidence gap; it does not approve live trading.

---

## 3. Baseline Freeze

Any future 2022 OOS run must use the current CPM-1 frozen baseline:

| Dimension | Frozen Baseline |
| --- | --- |
| Asset | `ETH/USDT:USDT` |
| Primary timeframe | `1h` |
| MTF timeframe | `4h` |
| Direction | `LONG-only` |
| Trigger | Pinbar, current CPM-1 trigger parameters |
| Trend filter | EMA50 + current `min_distance_pct` |
| MTF filter | 4h EMA60 confirmation |
| ATR filter | Disabled, frozen as disabled |
| Exit | TP1 1.0R 50%, TP2 3.5R 50%, current SL, BE off, trailing off |

Rules:

- Do not change parameters because of anticipated 2022 behavior.
- Do not change parameters after seeing the 2022 result within the same task.
- Do not turn OOS into a tuning loop.
- Do not add E4, SHORT, cross-asset, cross-timeframe, regime, or portfolio logic.
- If the frozen baseline cannot be reconstructed exactly, the correct state is
  Pause / Require additional evidence, not ad-hoc substitution.

---

## 4. Pre-run Checklist

Before Owner approves any actual 2022 OOS run, the following must be confirmed
and recorded.

| Check | Required Confirmation |
| --- | --- |
| Data source availability | ETH/USDT:USDT 1h and 4h data are available for the target window. |
| Data completeness | Missing candles, duplicate candles, timestamp gaps, and exchange outages are quantified. |
| Time window definition | Exact UTC start/end are specified; default candidate is full year 2022. |
| Full-year coverage | Confirm whether the run includes 2022-01-01 00:00:00 UTC through 2022-12-31 23:59:59 UTC, or document any deviation. |
| Same-bar policy | Same-bar conflict handling is explicitly stated and matches the comparable CPM-1 evidence policy. |
| Cost model | Fee model is specified, including whether BNB9-style assumptions apply. |
| Funding model | Funding inclusion/exclusion and data source are stated. |
| Backtest engine version | Engine implementation/version is recorded before execution. |
| Runtime/research profile mapping | The research profile is mapped to the current CPM-1 frozen baseline and legacy `pinbar` naming is resolved. |
| Commit hash | Repository commit hash is recorded for reproducibility. |
| Config/profile hash | Exact config/profile hash or immutable profile snapshot is recorded. |
| Data cleaning risk | Any cleaning, interpolation, exchange symbol migration, contract spec change, or candle-normalization step is listed. |
| Exchange rule difference risk | 2022 fee, precision, leverage, funding, contract, or symbol-rule differences are identified or explicitly caveated. |
| Output destination | Report path and required metadata schema are defined before running. |
| Owner approval | Owner explicitly approves running the OOS after reviewing this checklist. |

If any item is unknown, the run should not be treated as promotion-grade
evidence until the unknown is resolved or explicitly accepted as a caveat.

---

## 5. OOS Run Specification Draft

This section describes how to run the OOS only if Owner approves a future
execution task.

| Field | Draft Specification |
| --- | --- |
| Asset | `ETH/USDT:USDT` |
| Primary timeframe | `1h` |
| MTF timeframe | `4h` |
| Direction | `LONG-only` |
| Baseline | Current frozen CPM-1 baseline |
| Parameter changes | None |
| E4 / Donchian filter | Not included as hard filter |
| SHORT | Not included |
| Cross-asset / cross-timeframe | Not included |
| Target period | Full-year 2022 unless Owner approves a narrower diagnostic window |
| Run type | Out-of-sample validation, not optimization |
| Runtime impact | None |

Required output metrics:

- Trade count.
- Total PnL.
- Max drawdown.
- Win rate.
- Profit factor.
- Sharpe / Sortino, if already supported by the reporting path.
- Yearly and monthly breakdown.
- Largest loss cluster.
- Same-bar conflict count / impact, if available.
- Cost and funding impact, if available.
- Comparison to documented CPM-1 profit/failure hypothesis.

Required metadata:

- Period.
- Engine version.
- Commit hash.
- Config/profile hash.
- Data source and data coverage notes.
- Cost model.
- Funding model.
- Same-bar policy.
- Whether result affects runtime automatically: `No`.

---

## 6. Interpretation Rules

The 2022 OOS result must be interpreted under these rules:

1. OOS success does not equal Small-live approval.
2. OOS failure does not equal immediate rejection.
3. OOS must not trigger automatic parameter changes.
4. OOS must not trigger runtime profile, risk rule, research engine, or live
   enablement changes.
5. Do not rewrite the strategy based on a single-year result.
6. Do not run post-result parameter rescue inside the OOS task.
7. Interpret the result against the frozen CPM-1 profit/failure hypothesis and
   market-boundary definition.

Failure classification must come before action:

| Classification | Meaning | Default Follow-up |
| --- | --- | --- |
| Module hypothesis failure | Trend-pullback continuation hypothesis is not supported in 2022 and conflicts with the known CPM-1 story. | Pause or consider rejecting current baseline after Owner review. |
| Boundary cost similar to 2023 | 2022 fails in a way consistent with accepted non-applicable market behavior. | Continue Observation may remain possible if Owner accepts the cost. |
| Cost / funding assumption issue | Result changes materially because assumptions differ or are unreliable. | Require additional evidence before judging CPM-1. |
| Data quality issue | Missing, inconsistent, or transformed 2022 data makes the result unreliable. | Pause evidence judgment; repair evidence basis, not strategy. |
| Engine / same-bar semantic issue | Backtest behavior differs from prior evidence due to engine or same-bar semantics. | Reconcile methodology before using result. |
| Trade-count insufficiency | Too few trades for reliable interpretation. | Require additional evidence or classify as inconclusive. |

OOS success should also be classified. A positive result with low trade count,
large concentration, unclear funding, or strong assumption sensitivity may still
be inconclusive rather than promotion-supporting.

---

## 7. Decision Matrix

| OOS Outcome | Candidate State | Interpretation |
| --- | --- | --- |
| Clear positive result, sufficient trades, assumptions clean, hypothesis consistent | Small-live Candidate remains possible | Evidence gap reduced; still requires live-safe and Owner promotion review. |
| Positive result but thin trades or concentrated profits | Require additional evidence | Do not over-read a narrow single-year result. |
| Flat / mildly negative result matching accepted boundary cost | Continue Observation | Owner may still accept CPM-1 as boundary-cost module if broader evidence remains coherent. |
| Negative result inconsistent with known 2023-style boundary cost | Pause CPM-1 | Classify whether this is module/profile failure or methodology issue. |
| Severe negative result with clean assumptions and enough trades | Reject current baseline may be considered | Owner review required; no automatic rebuild. |
| Result dominated by cost/funding/data/same-bar uncertainty | Require additional evidence | Evidence is not promotion-grade until assumptions are settled. |
| Result suggests a specific non-runtime research question | Reopen Research | Only with bounded scope; no tuning loop or runtime effect. |
| Result cannot reproduce frozen baseline or profile mapping | Pause CPM-1 | Resolve reproducibility before interpretation. |

---

## 8. Required Output Format For Future Run

Any future approved OOS run must produce a report with at least these fields:

| Field | Required Content |
| --- | --- |
| `period` | Exact UTC start/end and whether it is full-year 2022. |
| `engine_version` | Backtest engine version or implementation identifier. |
| `commit_hash` | Git commit hash used for the run. |
| `config_profile_hash` | Frozen CPM-1 config/profile hash or immutable snapshot ID. |
| `cost_model` | Fee assumptions and source. |
| `funding_model` | Funding inclusion/exclusion, source, and caveats. |
| `same_bar_policy` | Same-bar conflict policy. |
| `trade_count` | Total trades and optional monthly count. |
| `total_pnl` | Total PnL in report currency. |
| `max_drawdown` | MaxDD with exact semantics. |
| `win_rate` | Win rate over the OOS period. |
| `profit_factor` | Profit factor if supported. |
| `sharpe_sortino` | Sharpe / Sortino if already supported. |
| `yearly_monthly_breakdown` | Full-year and monthly summary. |
| `largest_loss_cluster` | Largest drawdown/loss cluster with dates and trade count if available. |
| `hypothesis_mismatch` | Where result agrees or conflicts with existing CPM-1 hypothesis. |
| `conclusion_classification` | One of the failure/success classifications from this plan. |
| `affects_runtime_automatically` | Always `No`. |

The report should explicitly state: "This OOS result does not automatically
change runtime profile, strategy parameters, risk rules, or live status."

---

## 9. Owner Approval Gate

Before any actual 2022 OOS run, Owner must confirm:

1. Is running 2022 OOS approved?
2. Is the current frozen CPM-1 baseline the only test object?
3. Is the no-parameter-change rule accepted?
4. Is it accepted that OOS success does not automatically promote CPM-1?
5. Is it accepted that OOS failure is classified first and does not immediately
   trigger strategy rebuild or parameter rescue?
6. Is the selected cost/funding/same-bar policy acceptable for promotion-grade
   interpretation?
7. Is full-year 2022 required, or is any narrower window acceptable only as a
   diagnostic supplement?
8. Who reviews the output classification before CPM-1 state changes?

Without explicit Owner approval on these points, 2022 remains an evidence gap
and this document remains a plan only.

---

## 10. Not-now List

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
- No research engine or backtester change.
- No automatic research-to-runtime promotion.
- No automatic Small-live Candidate status.
- No live enablement.
- No frontend control.

---

## 11. Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-06 | Initial 2022 OOS gate inspect plan | Codex |
