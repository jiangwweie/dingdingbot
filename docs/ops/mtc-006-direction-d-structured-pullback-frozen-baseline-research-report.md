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

# MTC-006 - Direction D Structured Pullback / Value-Zone Frozen Baseline Research Report

**Task ID:** MTC-006
**Date:** 2026-05-07
**Authorization:** Level 3 research-only
**Status:** Completed; frozen spec was written before execution and was not changed after results
**Affects Runtime Automatically:** No

---

## 0. Scope Guard

This is a single frozen baseline research run for Direction D. It tests whether
a 4h structured pullback / value-zone mechanism has enough evidence to remain
research-relevant.

It is not parameter optimization, CPM rescue, runtime-candidate generation,
small-live readiness review, strategy-router design, portfolio allocation, or
regime-engine work.

Hard prohibitions:

- No parameter sweep.
- No multi-version value-zone comparison.
- No EMA period search.
- No confirmation-rule search.
- No trade-count rescue by relaxing conditions after results.
- No CPM-1 baseline change or CPM rescue.
- No Direction A / C parameter rescue.
- No 15m experiment.
- No runtime/profile/risk/backtester-core modification.
- No strategy router, portfolio, or regime engine.
- No new data pipeline.
- No runtime candidate or small-live candidate conclusion.

---

## 1. Frozen Spec

### 1.1 Asset / Timeframe / Window

| Dimension | Frozen value |
| --- | --- |
| Asset | ETH/USDT:USDT |
| Primary timeframe | 4h |
| Lower timeframe | None; no 15m, no 1h entry optimization |
| Base window | 2021-01-01 00:00 UTC through 2025-12-31 20:00 UTC closed 4h bars |
| Data source | Existing `data/v3_dev.db`, `klines`, read-only |

### 1.2 Trend Context

| Dimension | Frozen value |
| --- | --- |
| Parent trend indicator | 4h EMA60 |
| Parent trend condition | Closed 4h close > EMA60 |
| Direction | LONG-only |
| Donchian entry | Not used |

EMA60 is inherited from the MTC trend-lifecycle context. No other EMA period is
tested.

### 1.3 Value-Zone Definition

| Dimension | Frozen value |
| --- | --- |
| Zone type | EMA60 value zone |
| Zone touch | Closed 4h bar low <= EMA60 |
| Trend-active guard | Same bar close > EMA60, or at least one close > EMA60 within the prior 3 closed bars |
| Zone expiry | Pending zone state expires if the trend-active guard is no longer true before confirmation |

This uses the single MTC-005 EMA60 zone. No zone width, buffer, Fibonacci,
structure-level, or Donchian-zone variants are tested.

### 1.4 Resumption Confirmation

| Dimension | Frozen value |
| --- | --- |
| Confirmation indicator | 4h EMA20 |
| Confirmation condition | Closed 4h close > EMA20 after an eligible EMA60 zone touch |
| Same-bar zone touch + confirmation | Allowed, per MTC-005 Same-Bar Policy section |
| Candle-pattern trigger | Not used; no Pinbar / wick geometry |

The same-bar policy is explicit: the signal may occur on a fully closed 4h bar
whose low touches EMA60 and whose close reclaims EMA20. Entry still occurs only
on the next 4h open.

### 1.5 Entry / Stop / Exit

| Dimension | Frozen value |
| --- | --- |
| Entry timing | Next 4h bar open after fully closed confirmation bar |
| Entry slippage | Entry open * 0.001 |
| Initial stop | Lowest low of prior 6 closed 4h bars at signal time |
| Stop execution | Stop level with exit slippage |
| Lifecycle exit | Fully closed 4h close below EMA60 |
| Lifecycle execution | Next 4h bar open after EMA60 close-break, with exit slippage |
| Intrabar EMA exit | Not used |
| TP / BE / trailing | Not used |

Exit/lifecycle is inherited from Direction A/C to isolate the Direction D entry
mechanism.

### 1.6 Cost / Funding / Same-Bar

| Dimension | Frozen value |
| --- | --- |
| Fee rate | 0.0004 each side |
| Entry slippage | 0.001 |
| Stop / EMA exit slippage | 0.001 |
| Funding | Enabled, constant 0.0001 per 8h, matching MTC research convention |
| Same-bar order | Initial stop is checked before EMA close-break trigger; entry never occurs on the signal bar |

### 1.7 Position Sizing

| Dimension | Frozen value |
| --- | --- |
| Initial balance | 10,000 USDT |
| Risk fraction | 1% of current realized equity |
| Max exposure | 2.0x |

### 1.8 Required Drift / Overlap Checks

The run must include:

- CPM drift check: year profile, 2021 behavior, 2023 behavior, loss clusters,
  and confirmation mechanism check.
- Direction A signal overlap: Direction D signal timestamp within +/- 2 4h
  bars of Direction A signal timestamp.
- Direction C comparison: evidence difference on trade count, winner count,
  top-N fragility, and year concentration.

---

## 2. Pre-Registered Stop Conditions

Stop or downgrade if any of these are required or observed:

1. Parameter sweep.
2. Zone / EMA / confirmation-rule change.
3. Pinbar or CPM trigger dependency.
4. Too few trades or winners for evidence.
5. Top-3 / top-5 removal failure.
6. Clear CPM-like drift.
7. Clear Direction A/C variant behavior.
8. Need for 15m, funding/OI/orderbook new data.
9. Runtime/profile/risk/backtester-core modification.
10. Post-hoc no-trade gate explanation.

---

## 3. Pre-Registered Classification

Final classification must be one of:

- `REJECT`
- `INSUFFICIENT_EVIDENCE`
- `PAUSE_FRAGILE`
- `RESEARCH_PASS_REQUIRES_FURTHER_VALIDATION`

Runtime, deployable, promotion, and small-live classifications are prohibited.

---

## 4. Execution Results

Artifacts:

- Adapter: `reports/mtc-006-direction-d-structured-pullback/mtc_006_direction_d_research_adapter.py`
- Summary: `reports/mtc-006-direction-d-structured-pullback/summary.json`
- Signals: `reports/mtc-006-direction-d-structured-pullback/signals.jsonl`
- Trades: `reports/mtc-006-direction-d-structured-pullback/trades.jsonl`
- Equity curve: `reports/mtc-006-direction-d-structured-pullback/equity_curve.jsonl`

Execution notes:

- Standalone research adapter only; no runtime/profile/risk/backtester core
  file was modified.
- No parameter sweep, zone variant, EMA variant, confirmation variant, CPM
  trigger, 15m input, router, portfolio, or regime engine was used.
- Funding is included using the same constant 0.0001 per 8h convention used in
  prior MTC research adapters.

### 4.1 Overall Metrics

| Metric | Direction D result |
| --- | ---: |
| Signal count | 418 |
| Closed trades | 417 |
| Winner count | 66 |
| Loser count | 351 |
| Net PnL | -262.57 |
| Gross PnL before costs | 4,792.77 |
| PF | 0.985 |
| Win rate | 15.83% |
| Realized MaxDD | 26.22% |
| MTM MaxDD | 29.78% |
| Fees | 1,238.44 |
| Slippage | 3,096.10 |
| Funding | 720.80 |
| Average hold | 50.51h |
| Median hold | 12h |

Read:

- Trade count and winner count are more than sufficient.
- Gross edge exists before costs, but costs and weak loss distribution turn net
  negative.
- PF below 1 and MTM MaxDD near 30% trigger rejection conditions.

### 4.2 Year-by-Year

| Year | Net PnL | PF | Trades | Winners | Win rate | MTM MaxDD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2021 | 651.12 | 1.246 | 72 | 19 | 26.39% | 11.25% |
| 2022 | -1,373.18 | 0.500 | 79 | 10 | 12.66% | 22.69% |
| 2023 | 25.99 | 1.008 | 84 | 14 | 16.67% | 29.78% |
| 2024 | 2,896.84 | 1.973 | 75 | 11 | 14.67% | 22.69% |
| 2025 | -2,463.34 | 0.550 | 107 | 12 | 11.21% | 23.51% |

Year read:

- Positive years: 2021, 2023, 2024.
- 2024 is the only strong positive year.
- 2022 and 2025 are severe negative windows.
- 2023 is essentially flat after costs but carries the worst MTM drawdown.
- This does not show a clean applicability boundary; it shows high signal churn
  with year instability.

### 4.3 Fragility

| Fragility metric | Result |
| --- | ---: |
| Top-1 PnL | 2,759.31 |
| Net after top-1 removal | -3,021.88 |
| Top-3 PnL | 5,525.59 |
| Net after top-3 removal | -5,788.16 |
| Top-5 PnL | 7,068.50 |
| Net after top-5 removal | -7,331.08 |
| Top winner / gross winners | 16.31% |
| Top 3 / gross winners | 32.66% |
| Top 5 / gross winners | 41.78% |

Top winner attribution:

| Rank | Entry UTC | Year | Net PnL | Hold | Exit | Read |
| --- | --- | --- | ---: | ---: | --- | --- |
| 1 | 2024-02-06 04:00 | 2024 | 2,759.31 | 900h | EMA60 lifecycle | Major 2024 trend-lifecycle winner |
| 2 | 2025-07-06 16:00 | 2025 | 1,444.86 | 608h | EMA60 lifecycle | Isolated 2025 winner inside losing year |
| 3 | 2023-01-02 08:00 | 2023 | 1,321.42 | 544h | EMA60 lifecycle | Early 2023 trend-lifecycle winner |
| 4 | 2021-04-26 00:00 | 2021 | 844.90 | 428h | EMA60 lifecycle | 2021 trend continuation winner |
| 5 | 2021-02-01 20:00 | 2021 | 698.01 | 496h | EMA60 lifecycle | 2021 trend continuation winner |

Read:

- Winners are real trend-lifecycle trades, not pure one-bar accidents.
- However, the distribution is fragile: after removing the single largest
  winner the system is deeply negative.
- Top-3/top-5 removal is much worse than Direction A and Direction C.
- Direction D does not solve the MTC top-winner fragility problem.

### 4.4 Trade Quality

| Metric | Overall | Winners | Losers |
| --- | ---: | ---: | ---: |
| Avg MFE | 127.05 | 509.81 | 55.08 |
| Avg MAE | -48.07 | -21.87 | -52.99 |
| Avg giveback | 115.56 | 236.61 | 92.80 |
| Max MFE | 3,283.94 | - | - |
| Min MAE | -629.91 | - | - |

Additional observations:

- 262 of 417 trades held less than 1 day; median hold is only 12 hours.
- 392 of 418 signals were same-bar EMA60 touch + EMA20 reclaim. This is allowed
  by the frozen same-bar policy, but it shows that the EMA20 resumption
  confirmation often functions as immediate bounce confirmation, not a delayed
  structural recovery.
- Fee + slippage + funding totals 5,055.34, larger than gross PnL before costs
  of 4,792.77. Cost drag is decisive.
- Winners can become long trend-lifecycle trades, but the majority of signals
  churn out quickly.

### 4.5 Direction A Overlap

Overlap rule: Direction D signal within +/- 2 closed 4h bars of a Direction A
signal.

| Metric | Result |
| --- | ---: |
| Direction D signals | 417 executable signals |
| Direction A signals | 173 |
| D signals overlapping A | 123 |
| Overlap as % of D | 29.50% |
| A signals overlapping D | 109 |
| Overlap as % of A | 63.01% |
| Classification | Partial overlap |

Read:

- Direction D is not a Direction A variant by the >80% stop threshold.
- The overlap is asymmetric: Direction D produces many more signals, and many
  Direction A moments have nearby Direction D signals.
- Low-enough overlap does not help because Direction D has worse net, worse DD,
  and worse top-N fragility.

### 4.6 CPM Drift Check

| Check | Result | Read |
| --- | --- | --- |
| Rule dependency | No Pinbar / wick geometry | Pass; not a CPM trigger |
| 2021 behavior | +651.12 net, PF 1.246 | Different from CPM-1 2021 failure |
| 2023 behavior | +25.99 net, PF 1.008 | Different from CPM-1 2023 severe loss, but not strong |
| Positive-year profile | 2021, 2023, 2024 | Different from CPM-1's 2024/2025 concentration |
| CPM 2021 loss-cluster overlap | 19 losses, -998.74 in Feb-Mar / Aug-Oct-like clusters | Partial family risk |
| Drift classification | `NO_CLEAR_CPM_DRIFT` | Not a CPM clone, but family risk remains |

Read:

- Direction D does not clearly drift into CPM-1: it is 4h, structural, not
  Pinbar-based, and its year profile differs.
- But it still fails as a pullback-continuation module after costs and
  drawdown.
- The result is not "CPM-like success"; it is structurally different failure.

### 4.7 Direction C Comparison

| Metric | Direction C | Direction D |
| --- | ---: | ---: |
| Trade count | 63 | 417 |
| Winner count | 10 | 66 |
| Net PnL | 2,039.29 | -262.57 |
| PF | 1.405 | 0.985 |
| MTM MaxDD | 15.01% | 29.78% |
| Net after top-1 removal | 362.04 | -3,021.88 |
| Net after top-3 removal | -2,471.12 | -5,788.16 |
| Net after top-5 removal | -3,861.04 | -7,331.08 |

Read:

- Direction D solves Direction C's thin-sample problem.
- It does not solve evidence quality: more trades produced worse net,
  drawdown, and top-N fragility.
- Direction D is structurally different from Direction C, but its empirical
  evidence is worse.

### 4.8 Applicability Read

Supported:

- Direction D can capture real trend-lifecycle winners in 2021, 2023, 2024,
  and 2025.
- It is structurally distinct from CPM-1 and not merely Direction A overlap.

Not supported:

- No robust net edge after costs.
- No acceptable drawdown profile.
- No improved top-winner fragility.
- No clean pre-observable applicability boundary.
- 2022 and 2025 are severe failure windows; 2023 is flat but has the worst MTM
  drawdown.

Post-hoc gate risk:

- Any attempt to rescue Direction D would need to filter high-churn years or
  same-bar bounce signals after seeing results.
- That would violate MTC-006 and should not be done here.

### 4.9 Family-Level Impact

Direction D failing does not prove every possible pullback-continuation module
is impossible. It does materially reduce the priority of the current
pullback-continuation family:

- CPM-1 remains paused despite partial CPM-MOD-002 evidence.
- Direction D has enough sample and winners, but fails net/PF/DD/top-N.
- 15m pullback-entry should not be used to bypass this history.

Family implication:

> Pullback-continuation should be lowered in research priority unless a future
> idea has a clearly different mechanism and a pre-observable applicability
> boundary before any Level 3 request.

SMA-001 / SMA-002 should be updated if the Owner accepts MTC-006: Direction D
should move from candidate to rejected frozen baseline evidence, and
pullback-continuation family priority should decline.

### 4.10 Stop Condition Review

| Stop condition | Status |
| --- | --- |
| Parameter sweep required | Not triggered |
| Zone / EMA / confirmation change required | Not triggered |
| Pinbar / CPM trigger required | Not triggered |
| Trade count too low | Not triggered; 417 trades |
| Winner count too low | Not triggered; 66 winners |
| Top-3 / top-5 failure | Triggered |
| Clear CPM-like drift | Not triggered |
| Direction A variant >80% overlap | Not triggered |
| Direction C variant | Not triggered |
| Need 15m or new data | Not triggered |
| Runtime/profile/risk/backtester core change | Not triggered |
| Post-hoc no-trade gate needed | Would be required to rescue; not used |

---

## 5. Final Classification

**Final classification:** `REJECT`

Primary reasons:

- Net PnL is negative: -262.57.
- PF is below 1: 0.985.
- MTM MaxDD is high: 29.78%.
- Top-1/top-3/top-5 removal all fail sharply.
- The mechanism has enough trades and winners, so this is not a thin-sample
  excuse.

Direction D does not become a runtime candidate, small-live candidate, or
deployment candidate.

---

## 6. Owner Summary

**Frozen spec:** ETH/USDT:USDT 4h; EMA60 value-zone touch; EMA20 resumption
confirmation; next 4h open entry; prior-6-bar stop; EMA60 close-break lifecycle
exit; conservative fee/slippage/funding model; no 15m.

**Stop conditions:** no parameter/search/runtime stop was violated. Evidence
stop conditions triggered: net negative, PF < 1, MTM DD 29.78%, top-3/top-5
removal failure.

**Trade count / winner count:** 417 closed trades, 66 winners. Sample is large
enough; failure is not due to thin evidence.

**Core metrics:** net PnL -262.57, PF 0.985, win rate 15.83%, realized MaxDD
26.22%, MTM MaxDD 29.78%.

**Top-N fragility:** top-1 removal -3,021.88; top-3 removal -5,788.16; top-5
removal -7,331.08. Fragility is worse than Direction A and Direction C.

**Year-by-year:** 2021 +651.12; 2022 -1,373.18; 2023 +25.99; 2024 +2,896.84;
2025 -2,463.34. No stable applicability boundary.

**MFE / MAE / giveback:** avg MFE 127.05, avg MAE -48.07, avg giveback 115.56.
Winners have real MFE, but cost/churn and giveback dominate the full sample.

**Direction A overlap:** 29.50% of Direction D signals overlap Direction A
within +/- 2 bars; not an A variant by the 80% stop rule. However, evidence
quality is worse.

**CPM drift check:** no clear CPM drift. Direction D is not Pinbar/1h CPM and
has different 2021/2023 behavior, but it still fails as pullback-continuation
evidence after costs.

**Direction C comparison:** Direction D has far more trades and winners, but
worse net, worse DD, and worse top-N fragility.

**Module applicability read:** no clean ex-ante applicability boundary was
identified. Any rescue would require post-hoc filtering, which is prohibited.

**Family-level implication:** lower pullback-continuation family priority.
Direction D should be archived as rejected frozen-baseline evidence; 15m
pullback-entry should not be used to bypass CPM-1 / Direction D history.

**Final classification:** `REJECT`.

**Recommendation:** reject Direction D frozen baseline and update SMA-001 /
SMA-002 if Owner accepts. Do not continue with Direction D parameters, zone
variants, EMA variants, 15m entry timing, or CPM rescue.

**Runtime / small-live:** not a runtime candidate and small-live readiness
remains unmet.
