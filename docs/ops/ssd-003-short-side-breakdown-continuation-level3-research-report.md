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

# SSD-003 - Short-side 4h Breakdown Continuation Level 3 Research Report

**Task ID:** SSD-003
**Date:** 2026-05-07
**Status:** Completed - single frozen Level 3 research-only run executed
**Authorization Level:** Owner-approved Level 3 research-only
**Scope:** One frozen short-only ETH 4h OHLCV breakdown-continuation run
**Affects Runtime Automatically:** No

---

## 0. Boundary

This is a research-only frozen run. It does not authorize runtime/profile/risk/
backtester-core changes, strategy promotion, small-live, canary-live, router,
portfolio, or regime-engine work.

No conclusion in this report may be interpreted as runtime candidate or
small-live readiness.

---

## 1. Frozen Spec - Written Before Execution

### 1.1 Scope

| Field | Frozen value |
| --- | --- |
| Asset | ETH/USDT:USDT |
| Direction | Short-only |
| Timeframe | 4h closed OHLCV |
| Window | 2021, 2022, 2023, 2024, 2025 |
| Lower timeframe | None |
| New data | None; no funding/OI/liquidation/orderbook/15m |
| Runtime/core changes | None |

### 1.2 Breakdown Structure Definition

Frozen structure:

> **Confirmed swing-low support.**

A confirmed swing low is a closed 4h candle whose low is strictly lower than
the lows of the two closed 4h candles immediately before it and the two closed
4h candles immediately after it. This uses only closed OHLCV. A support level
becomes usable only after the two right-side confirmation candles are closed.

Only the most recent confirmed swing-low support is active.

This is intentionally not Donchian20 and not an EMA/value-zone support.

### 1.3 Closed-bar Breakdown Rule

A breakdown event occurs when:

- there is an active confirmed swing-low support;
- the current 4h candle closes below that support low;
- the current candle is fully closed;
- there is no open position and no pending entry.

The breakdown bar is not itself an entry.

### 1.4 Continuation Confirmation Rule

Continuation is required to avoid one-bar failed breakdowns:

- the candle immediately after the breakdown bar must also fully close below
  the same broken support; and
- that confirmation candle must close below the breakdown bar close.

If this does not happen on the next candle, the breakdown setup is marked
`failed_breakdown_before_entry` and no trade is opened.

### 1.5 Late Capitulation Diagnostic

Late capitulation is diagnostic-only, not an entry filter:

- a setup is flagged `late_capitulation_diagnostic=true` if the breakdown bar's
  range is more than 2 times the average range of the prior 20 closed 4h bars.

This is not used to exclude trades. It is reported to assess whether winners or
losers cluster after extended downside movement.

### 1.6 Entry Timing Convention

Entry occurs at the next 4h candle open after continuation confirmation.

No entry is allowed on the signal close. No 1h or 15m timing is used.

### 1.7 Invalidation / Exit Lifecycle

This run uses two frozen exits:

1. **Squeeze / reclaim invalidation:** after entry, if a fully closed 4h candle
   closes back above the broken support, exit at the next 4h open.
2. **Protective stop:** if intrabar high reaches the initial stop, exit at the
   stop price.

Initial stop is frozen as the maximum high across the breakdown bar and the
continuation confirmation bar.

End-of-window open positions are force-closed at final close and reported.

### 1.8 Same-bar / Next-bar Policy

- Structure, breakdown, and continuation use fully closed 4h bars.
- Entry is next 4h open after continuation confirmation.
- Reclaim invalidation exits next 4h open after the reclaim close.
- Protective stop can trigger intrabar after entry; if stop and entry occur in
  the same bar, pessimistic handling is used and the stop is considered valid.
- Same-bar stop cases are counted.

### 1.9 Cost Model

Frozen cost model:

- initial balance: 10000 USDT;
- risk fraction: 1% of equity per trade;
- maximum notional exposure: 2x equity cap;
- fee rate: 0.04% per side;
- entry slippage: 0.10%;
- exit slippage: 0.10%;
- funding enabled using constant 0.01% per 8h approximation.

For short trades:

- entry execution price = raw entry open * (1 - entry slippage);
- exit execution price = raw exit price * (1 + exit slippage);
- gross short PnL before costs = (entry raw - exit raw) * quantity;
- net PnL subtracts execution slippage, fees, and funding approximation.

### 1.10 Funding Treatment Caveat

Funding is not used as a signal. No real funding, OI, liquidation, long/short,
or orderbook data is introduced.

Funding is reported as a constant approximation caveat. If results appear
funding-dependent, evidence must be downgraded or caveated.

### 1.11 Failure Closure

If this frozen run fails, it closes:

> ETH 4h OHLCV-only short-side breakdown continuation as a clean non-pullback
> standalone candidate under current constraints.

Failure must not generate alternate breakdown thresholds, support lookback
variants, Direction A mirror variants, bearish Direction C variants,
failed-rally value-zone entries, 1h/15m timing branches, funding/OI rescue, or
router/portfolio/regime proposals.

---

## 2. Execution Artifacts

The frozen rule was written before execution and was held fixed during the run.
The only post-first-run code change was a JSON serialization fix for `Decimal`
values in artifact output; no signal, entry, exit, cost, same-bar, or
diagnostic rule changed.

Artifacts:

- Research-only adapter:
  `reports/ssd-003-short-side-breakdown-continuation/ssd_003_short_breakdown_research_adapter.py`
- Summary:
  `reports/ssd-003-short-side-breakdown-continuation/summary.json`
- Signals:
  `reports/ssd-003-short-side-breakdown-continuation/signals.jsonl`
- Trades:
  `reports/ssd-003-short-side-breakdown-continuation/trades.jsonl`
- Failed breakdown diagnostics:
  `reports/ssd-003-short-side-breakdown-continuation/failed_breakdowns.jsonl`
- Equity curve:
  `reports/ssd-003-short-side-breakdown-continuation/equity_curve.jsonl`

Execution window:

- asset: `ETH/USDT:USDT`;
- timeframe: 4h closed OHLCV only;
- base years: 2021-2025;
- signals: 23;
- closed trades: 23.

---

## 3. Overall Results

| Metric | Result |
| --- | ---: |
| Net PnL | -1699.88 |
| Gross PnL before costs | -701.35 |
| Profit factor | 0.317 |
| Win rate | 4.35% |
| Closed trades | 23 |
| Winners | 1 |
| Losers | 22 |
| Realized MaxDD | 24.88% |
| MTM MaxDD | 26.98% |
| Fees | 40.93 |
| Slippage | 102.32 |
| Funding approximation | 855.28 |
| Total cost drag | 998.53 |

The frozen baseline is negative before and after costs, with PF far below 1,
one winner across the entire base window, and realized/MTM drawdown that is not
acceptable for a candidate module. Funding is a constant research
approximation, not real funding data and not a signal; it still exposes that
this lifecycle can hold low-quality shorts long enough for cost drag to
dominate.

---

## 4. Year-By-Year Results

| Year | Net PnL | PF | Trades | Winners | Win Rate | Realized MaxDD | MTM MaxDD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2021 | -2067.59 | 0.000 | 16 | 0 | 0.00% | 13.00% | 15.16% |
| 2022 | 0.00 | 0.000 | 0 | 0 | n/a | 13.00% | 13.89% |
| 2023 | 0.00 | 0.000 | 0 | 0 | n/a | 13.00% | 7.92% |
| 2024 | 0.00 | 0.000 | 0 | 0 | n/a | 13.00% | 14.81% |
| 2025 | 367.71 | 1.874 | 7 | 1 | 14.29% | 24.88% | 26.98% |

Notes:

- 2021 is a decisive negative window: 16 trades, zero winners, and -2067.59
  net PnL.
- 2022-2024 produce no closed trades, so the module has poor opportunity
  distribution across the full base window.
- 2025 is positive, but only from one winner. That is not a sufficient
  independent favorable-year base.
- Drawdown fields in no-trade years reflect account/equity context carried
  through the full curve rather than new yearly trade losses.

---

## 5. Fragility

| Fragility Check | Result |
| --- | ---: |
| Top-1 removal net PnL | -2488.50 |
| Top-3 removal net PnL | -2424.79 |
| Top-5 removal net PnL | -2314.07 |
| Top winner contribution to gross winners | 100.00% |

The fragility read is severe. There is only one winning trade, and even with
that trade included the module loses money. Top-3 and top-5 removal include the
single winner plus the next-best losing trades, so their excluded PnL can be
lower than top-1; the important point is unchanged: there is no robust winner
base.

---

## 6. Trade Quality

| Metric | Result |
| --- | ---: |
| Average MFE | 232.78 |
| Median MFE | 67.27 |
| Average MAE | -70.49 |
| Median MAE | -76.10 |
| Average giveback | 263.28 |
| Max giveback | 1439.95 |
| Average holding time | 1700.00 hours |
| Median holding time | 52.00 hours |

Trade quality is not acceptable. MFE exists, but giveback is larger than
average MFE and holding time is heavily skewed by a long 2025 force-close
lifecycle. This suggests the frozen exit lifecycle fails to reliably convert
downside movement into realized profit under the current constraints.

---

## 7. Breakdown, Squeeze, And Capitulation Diagnostics

| Diagnostic | Result |
| --- | ---: |
| Failed breakdowns before entry | 30 |
| Reclaim exits | 11 |
| Protective stop exits | 11 |
| Same-bar entry-stop trades | 1 |
| Late-capitulation flagged signals | 10 |
| Late-capitulation flagged trades | 10 |
| Late-capitulation net PnL | -738.42 |
| Non-late-capitulation net PnL | -961.46 |

Failed-breakdown and reclaim behavior is material. The rule sees more failed
breakdowns before entry than executed trades, and executed trades split heavily
between reclaim exits and protective stops. Late-capitulation diagnostics do
not rescue the thesis: both late-capitulation and non-late-capitulation groups
are negative. Any attempt to exclude one group after seeing this result would
become post-hoc filtering and is not permitted.

---

## 8. Overlap And Family Drift

Overlap was measured by matching SSD-003 entry timestamps against prior module
entry timestamps within +/- two 4h bars.

| Reference | Reference Signals | SSD Trades Matched | SSD Overlap | Reference Overlap |
| --- | ---: | ---: | ---: | ---: |
| Direction A | 173 | 0 | 0.00% | 0.00% |
| Direction C | 63 | 0 | 0.00% | 0.00% |
| CPM-1 | 207 | 1 | 4.35% | 0.48% |
| Direction D | 418 | 1 | 4.35% | 0.24% |

Family drift check:

- Direction A mirror drift: no. The rule is not a bearish Donchian-style mirror
  and observed overlap is 0%.
- Direction C drift: no. The rule does not use contraction/re-expansion and
  observed overlap is 0%.
- CPM / Direction D / 15m pullback drift: no. The rule does not use pullback,
  value-zone, Pinbar/wick rejection, lower-timeframe entry timing, or
  retracement-entry logic.
- New data dependency drift: no. The run used closed OHLCV only. Funding was
  handled as a constant cost caveat, not as a new data signal.

The mechanism stayed structurally distinct from the failed
pullback-continuation family. The rejection is therefore not because it drifted
into CPM/D; it is rejected on its own frozen baseline evidence.

---

## 9. Applicability Read

The frozen concept has a clear conceptual premise: downside continuation after
a confirmed closed-bar support breakdown. The run did not produce a usable
applicability boundary:

- 2021 shows repeated short breakdown failures and no winners.
- 2022-2024 produce no trades, so there is no evidence of broad applicability
  or independent favorable windows.
- 2025 has one winner, but this is too concentrated to support a module-level
  thesis.
- Late-capitulation diagnostics are negative both when flagged and when not
  flagged.
- Squeeze/reclaim risk is directly visible through reclaim exits and failed
  breakdowns.

Under the current constraints, this is not a promising standalone OHLCV-only
short-side breakdown continuation module.

---

## 10. Final Classification

Final classification: `REJECTED_FROZEN_BASELINE`.

Rationale:

- Net PnL is negative.
- PF is far below 1.
- Winner count is one.
- Top-winner fragility is extreme.
- 2021 is decisively negative.
- 2022-2024 have no opportunity base.
- 2025 is positive but single-winner concentrated.
- Realized and MTM drawdowns are not acceptable.
- No clean ex-ante applicability boundary was identified.

This is not `REJECT_AS_MIRROR_OR_UNCLEAR` because the rule was structurally
distinct and did not mirror Direction A. It is not `BACKLOG_DATA_DEPENDENT`
because the OHLCV-only premise was executable. It is not
`PAUSE_UNCLEAR_BOUNDARY` or `INSUFFICIENT_EVIDENCE` because the observed
evidence is already poor enough to reject the frozen baseline under the
pre-registered constraints.

---

## 11. Failure Closure

This failed run closes the following hypothesis:

> ETH 4h OHLCV-only short-side breakdown continuation as a clean non-pullback
> standalone candidate under current constraints.

This failure must not automatically generate:

- alternate breakdown thresholds;
- support/range lookback variants;
- bearish Direction A mirror variants;
- bearish Direction C variants;
- failed-rally value-zone entries;
- 1h or 15m timing branches;
- funding/OI rescue;
- router, portfolio, or regime proposals.

---

## 12. Owner Summary

- Frozen rule status: maintained. The run used the pre-written frozen rule; no
  parameter sweep, variant selection, or post-result rule adjustment occurred.
- Direction A mirror drift: no. Direction A overlap was 0%, and the mechanism
  was not a mechanical bearish mirror.
- Direction C / CPM / D / 15m drift: no. Direction C overlap was 0%; CPM-1 and
  Direction D overlap were each 4.35% of SSD trades; no
  pullback/value-zone/Pinbar/lower-timeframe entry logic was used.
- Performance: failed. Net PnL -1699.88, PF 0.317, win rate 4.35%, 23 trades,
  1 winner.
- Drawdown: failed. Realized MaxDD 24.88%, MTM MaxDD 26.98%.
- Fragility: failed. Top winner contributed 100% of gross winners; top-1
  removal net PnL was -2488.50.
- Applicability: failed to identify a clean ex-ante module boundary. 2021 was
  strongly negative, 2022-2024 had no trades, and 2025 depended on one winner.
- Final classification: `REJECTED_FROZEN_BASELINE`.
- Closed hypothesis: ETH 4h OHLCV-only short-side breakdown continuation as a
  clean non-pullback standalone candidate under current constraints.
- Recommendation: do not continue SSD-003 variants or rescue paths. Any future
  short-side work would require a new Owner-approved Level 1/2 direction
  refresh, not an automatic follow-up.
- Runtime / small-live: this is not a runtime candidate, not a small-live
  candidate, and the small-live readiness gate remains unmet.
