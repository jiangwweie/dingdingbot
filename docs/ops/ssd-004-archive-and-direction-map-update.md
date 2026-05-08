# SSD-004 - Archive SSD-003 Evidence And Update Strategy Direction Map

**Task ID:** SSD-004
**Date:** 2026-05-07
**Status:** Completed / Docs-only archive and direction map update
**Authorization Level:** Level 1/2 - docs-only
**Source:** SSD-003 completed frozen Level 3 research report
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document archives the SSD-003 frozen baseline result and writes the
conclusion back into the strategy module applicability map and non-pullback
direction map.

It is not:

- a new strategy experiment;
- backtest authorization;
- research script or adapter authorization;
- parameter search;
- runtime/profile/risk/backtester-core work;
- small-live readiness review;
- a new short-side research direction.

No runtime candidate, deployable small-live strategy, or strategy enablement
follows from this archive.

---

## 1. SSD-003 Frozen Concept

| Field | Value |
| --- | --- |
| Task | SSD-003 |
| Concept | Short-side 4h breakdown continuation |
| Mechanism | Confirmed swing-low support breakdown + continuation confirmation + squeeze/stop exit lifecycle |
| Asset | ETH/USDT:USDT |
| Timeframe | 4h closed OHLCV only |
| Direction | Short-only |
| Data | OHLCV only; no funding/OI/liquidation/orderbook/15m |

---

## 2. Final Classification

Classification: **`REJECTED_FROZEN_BASELINE`**

---

## 3. Failure Reasons

The frozen baseline failed on every primary metric:

| Metric | Result | Acceptable? |
| --- | --- | --- |
| Net PnL | -1699.88 | No |
| Profit factor | 0.317 | No; far below 1 |
| Closed trades | 23 | Low |
| Winners | 1 | Extreme fragility |
| Win rate | 4.35% | No |
| Realized MaxDD | 24.88% | No |
| MTM MaxDD | 26.98% | No |
| Top-1 removal net PnL | -2488.50 | No |
| Top winner contribution | 100% | No |

Year concentration:

- **2021**: strongly negative; 16 trades, zero winners, -2067.59 net PnL.
- **2022-2024**: no closed trades at all; no opportunity base.
- **2025**: positive (+367.71) but entirely dependent on one winner; not an
  independent favorable-year base.

No clean ex-ante applicability boundary was identified. The frozen exit
lifecycle failed to reliably convert downside movement into realized profit.
Funding approximation cost drag (855.28) was material, even as a constant
research caveat.

---

## 4. Non-Failure Reasons

SSD-003 was rejected on its own frozen baseline evidence. The rejection is **not** because:

| Drift concern | Finding |
| --- | --- |
| Direction A mirror drift | No. Direction A overlap was 0.00%. The rule was not a bearish Donchian-style mirror. |
| Direction C rescue drift | No. Direction C overlap was 0.00%. The rule did not use contraction/re-expansion. |
| CPM / Direction D / 15m pullback drift | No. CPM-1 overlap 4.35%, Direction D overlap 4.35%. No pullback, value-zone, Pinbar, wick-rejection, or lower-timeframe entry logic was used. |
| Data dependency unable to execute | No. The run was fully executable from closed OHLCV only. |

The mechanism stayed structurally distinct from the failed pullback-continuation
family. The rejection is therefore a pure evidence-quality rejection of the
specific frozen short-side breakdown continuation concept.

---

## 5. Closed Hypothesis

This failed run closes:

> ETH 4h OHLCV-only short-side breakdown continuation as a clean non-pullback
> standalone candidate under current constraints.

---

## 6. Explicit Prohibited Automatic Follow-Ups

No automatic follow-up is permitted from SSD-003:

| Prohibited path | Reason |
| --- | --- |
| SSD-003 variants | Frozen baseline rejected; no variant rescue |
| Alternate support / breakdown lookbacks | Would be post-hoc threshold fitting |
| Bearish Direction A mirror | Not a Direction A rescue path; Direction A overlap was 0% but the concept is independently rejected |
| Bearish Direction C rescue | Direction C is `INSUFFICIENT_EVIDENCE / PAUSE_THIN_FRAGILE`; not a rescue path |
| Failed-rally value-zone short | Would be pullback-continuation family rescue under a short label |
| 1h / 15m timing | LTF-002 freezes 15m as execution timing under a frozen 4h thesis; not a short-side rescue |
| Funding / OI rescue | Current scope has no funding/OI data pipeline; not a rescue path |
| Router / portfolio / regime | Not authorized under current scope |

---

## 7. Direction Map Updates

### 7.1 Short-Side Classification Change

Short-side breakdown continuation moves from **active immediate inspect** to
**rejected frozen baseline**.

Previous state (SRD-002):

> Short-side / two-sided directional lifecycle — Immediate Level 1/2 inspect

Current state (after SSD-003):

> Short-side 4h breakdown continuation — `REJECTED_FROZEN_BASELINE`; archived
> as SSD-003 frozen Level 3 result

### 7.2 Future Short-Side Work

Future short-side research is not permanently banned, but it cannot be
automatically derived from SSD-003. Any future short-side direction must:

1. be proposed through a new Owner-approved Level 1/2 direction refresh;
2. define a clearly different mechanism from SSD-003's confirmed-swing-low
   breakdown + continuation confirmation;
3. have a pre-observable applicability boundary stated before Level 3;
4. not reuse SSD-003's failure closure hypothesis as a starting point for
   parameter or threshold rescue.

### 7.3 Non-Pullback Direction Map Effect

SSD-003's rejection changes the non-pullback direction map first-rank
recommendation. Short-side / two-sided directional lifecycle was previously the
recommended first inspect target (SRD-002 rank 1). After SSD-003, the
4h-breakdown-continuation mechanism within that bucket is closed, and the bucket
must be re-evaluated or replaced by the next inspect candidate before any future
short-side work proceeds.

---

## 8. Current State After Archive

| Item | State |
| --- | --- |
| Short-side breakdown continuation | `REJECTED_FROZEN_BASELINE` |
| Direction A | `PAUSE_FRAGILE` |
| Direction C | `INSUFFICIENT_EVIDENCE / PAUSE_THIN_FRAGILE` |
| CPM-1 | Paused; partially strengthened but incomplete |
| Direction D | `REJECTED_FROZEN_BASELINE` |
| 15m / sub-1h auxiliary | Candidate - inspect-only execution layer |
| Non-pullback direction queue | Needs next-rank re-evaluation after short-side closure |
| Runtime candidate | None |
| Deployable small-live strategy | None |
| Small-live readiness gate | Unmet |

---

## 9. Explicit Non-Authorization

SSD-004 does not authorize:

- backtests;
- research scripts or adapters;
- parameter sweeps;
- runtime/profile/risk/backtester-core changes;
- small-live approval;
- strategy promotion;
- router / portfolio / regime engine;
- new data pipelines;
- SSD-003 variants or rescue;
- short-side breakdown continuation continuation;
- bearish Direction A mirror;
- bearish Direction C rescue;
- failed-rally value-zone short;
- 1h/15m timing rescue;
- funding/OI rescue;
- CPM rescue;
- Direction D rescue;
- treating the short-side bucket as permanently closed for all future work.

---

## 10. Owner Summary

SSD-003 produced a completed, clean, frozen Level 3 run for ETH 4h OHLCV-only
short-side breakdown continuation. The result is `REJECTED_FROZEN_BASELINE`:
net PnL -1699.88, PF 0.317, win rate 4.35%, 23 trades, 1 winner, realized
MaxDD 24.88%, MTM MaxDD 26.98%, extreme top-winner fragility. 2021 was
decisively negative, 2022-2024 had no trades, and 2025 depended on a single
winner.

The mechanism was structurally distinct from Direction A, Direction C, CPM-1,
and Direction D. The rejection is not because of family drift; it is rejected on
its own evidence.

The closed hypothesis is: ETH 4h OHLCV-only short-side breakdown continuation
as a clean non-pullback standalone candidate under current constraints.

No SSD-003 variants, alternate lookbacks, mirror variants, bearish C/D rescue,
failed-rally value-zone short, 1h/15m timing rescue, funding/OI rescue, or
router/portfolio/regime proposals are permitted as automatic follow-ups.

Future short-side work requires a new Owner-approved Level 1/2 direction refresh
with a clearly different mechanism.

Small-live readiness gate remains unmet. There is no runtime candidate and no
deployable small-live strategy.

---

## 11. Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-07 | Initial SSD-004 archive and direction map update | Claude |
