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

# NSC-010 — T1-A Thin-sample & Fragility Closure Review

**Date:** 2026-05-06
**Status:** Proposed / Owner Decision Review
**Scope:** Docs-only closure / evidence review
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document reviews NSC-009 evidence and proposes Owner decision options.

This is not:

- experiment authorization;
- runtime implementation authorization;
- official backtester integration approval;
- promotion approval;
- small-live candidate approval;
- live deployment advice.

This task did not run experiments, write code, modify runtime profiles, modify risk rules, change backtester / research engine core, or touch `src/`, `configs/`, `tests/`, or `migrations/`.

Inspected material:

- `docs/ops/nsc-007-next-strategy-candidate-direction-inspect.md`
- `docs/ops/nsc-008-t1-lite-4h-first-main-trend-capture-minimal-experiment-plan.md`
- `reports/nsc-009-t1a-4h-main-trend-capture/**`
- T1/T1-R/C1/C2 historical evidence under `archive/**`

---

## 1. Current State

| Field | State |
| --- | --- |
| CPM-1 | Remains paused; not a small-live candidate |
| CPM-2 Candidate A/B | Closed as research proxy insufficient |
| Candidate C | Reserve-only; not automatically started |
| T1-B | Reserve-only; not executed |
| T1-A frozen rule | Research-only evidence complete; did not pass minimum evidence gate |
| Deployable small-live strategy candidate | None |
| Small-live readiness gate | Remains unmet |

---

## 2. NSC-009 Result Summary

Primary NSC-009 report:

- `reports/nsc-009-t1a-4h-main-trend-capture/experiment_report.md`

NSC-009 result:

| Field | Value |
| --- | --- |
| Harness feasibility | `FEASIBLE_STANDALONE_ADAPTER` |
| Evidence type | Research-only standalone adapter |
| Candidate | T1-A |
| Frozen rule | 4h Donchian20 close breakout, next 4h open entry, previous-20 low initial stop, 1.5R activation, 3x ATR14 trailing |
| Closed positions | 85 |
| Net PnL | +368.18597 |
| Gross PnL before costs | +1015.05840 |
| PF | 1.07107 |
| Win rate | 42.35% |
| Realized MaxDD | 11.35% |
| MTM MaxDD | 12.25% |
| Classification | `INSUFFICIENT_EVIDENCE_THIN_SAMPLE` |

Year-by-year summary:

| Year | Trades | Net PnL | PF | MTM MaxDD |
| --- | ---: | ---: | ---: | ---: |
| 2021 | 16 | +230.84 | 1.27 | 4.30% |
| 2022 | 15 | -468.28 | 0.55 | 9.35% |
| 2023 | 19 | +393.92 | 1.37 | 12.25% |
| 2024 | 20 | +308.80 | 1.25 | 6.82% |
| 2025 | 15 | -97.09 | 0.90 | 8.98% |

Winner concentration:

| Concentration | Value |
| --- | --- |
| Top 1 PnL | +362.55 |
| Top 1 as abs total net | 98.47% |
| Net excluding top 1 | +5.64 |
| Top 3 PnL | +1031.55 |
| Top 3 as abs total net | 280.17% |
| Net excluding top 3 | -663.37 |
| Top 5 PnL | +1526.34 |
| Top 5 as abs total net | 414.56% |
| Net excluding top 5 | -1158.15 |

---

## 3. What The Result Means

T1-A is not completely signal-free.

Evidence in favor:

- standalone adapter was feasible without forbidden runtime/core changes;
- aggregate gross PnL was positive;
- aggregate net PnL was positive after the frozen cost model;
- PF was above 1.0;
- hold duration distribution shows the rule did hold beyond local intraday pops;
- 2023 and 2024 were positive, which is directionally relevant given CPM weakness.

But the current frozen rule did not pass the NSC-008 minimum evidence gate.

Blocking evidence:

- 2023+2024+2025 trade floor was not met: 54 closed positions versus required 60.
- Top-winner concentration failed the fragility gate.
- Net PnL excluding top 3 winners was negative.
- 2022 and 2025 were negative.
- Positive aggregate PnL was too thin to offset sample and fragility concerns.

Therefore:

- T1-A must not enter promotion.
- T1-A must not become a small-live candidate.
- T1-A must not enter runtime implementation.
- T1-A must not be integrated into the official backtester as current mainline.
- T1-A research-only standalone evidence must not be rewritten as official validation.

---

## 4. Recommended Classification

Recommended state for the current T1-A frozen rule:

> **Pause current T1-A frozen rule; allow redesign candidate only through a new docs-only plan.**

Reason:

- It is not a clean reject because there is some standalone signal: positive gross, positive net, PF above 1.0, and trend-like hold durations.
- It is not a pass because sample floor and fragility gate failed.
- It should not be rescued by parameter sweep.
- It should not continue as the current frozen mainline.

Classification:

| Field | Value |
| --- | --- |
| Current frozen rule | Pause |
| Candidate family | Redesign candidate, not current mainline |
| Promotion status | None |
| Small-live status | Not candidate |
| Runtime implementation | Not allowed |
| Evidence review status | Closure / Owner decision needed |

Retirement is also a valid Owner option if no longer worth investigating, but the evidence does not force immediate retirement because the hypothesis was not completely dead.

---

## 5. Primary Blocker — Thin Sample

NSC-008 set a lower trade floor for T1-lite than CPM because 4h trend-following is naturally lower-frequency:

- at least 20 closed positions across 2021+2022;
- at least 60 closed positions across 2023+2024+2025;
- at least 80 closed positions across 2021-2025.

NSC-009 result:

- 2021+2022 = 31 positions, floor met;
- 2023+2024+2025 = 54 positions, floor not met;
- 2021-2025 = 85 positions, floor met.

The failed reference-period floor matters because T1-A is rare-winner sensitive. A small number of missing trades can materially change whether the observed edge is real or just a handful of captured trends.

Future evidence-window extension may be legitimate only if:

- data exists before results are inspected;
- the new window is frozen in a docs-only plan;
- no parameters are changed;
- the same cost, next-bar, anti-lookahead, MTM, and fragility reporting applies;
- the extension is framed as evidence sufficiency, not rescue tuning.

It is not acceptable to fix thin sample by:

- lowering the prewritten floor after seeing results;
- adding only favorable years;
- dropping 2022 or 2025;
- increasing signal count through Donchian/ATR/trailing parameter sweeps.

---

## 6. Secondary Blocker — Fragility

T1-A failed the top-winner concentration gate.

The key issue is not merely that trend-following has large winners. Large winners are expected. The issue is that current net edge disappears after removing the top winners:

- top 1 accounts for 98.47% of absolute total net PnL;
- net excluding top 1 is only +5.64;
- top 3 accounts for 280.17% of absolute total net PnL;
- net excluding top 3 is -663.37;
- top 5 accounts for 414.56% of absolute total net PnL;
- net excluding top 5 is -1158.15.

Interpretation:

- This is partly a normal trend-following feature: rare large winners pay for many small losses.
- But under the current sample size, the concentration is too high for a standalone candidate evidence gate.
- The rule may be capturing main trend segments, but not with enough breadth to support confidence.

Conclusion:

The fragility is not automatically fatal to the whole T1-lite direction, but it is fatal to treating the current frozen T1-A rule as passed. The correct state is pause/redesign, not promotion.

---

## 7. Explicit Rescue Prohibitions

The following are not allowed as rescue work for the current T1-A frozen rule:

- Donchian lookback sweep;
- ATR multiplier sweep;
- trailing activation sweep;
- initial stop lookback sweep;
- EMA filter search after seeing results;
- cost-model relaxation;
- removing or downweighting failed years;
- adding only favorable years;
- retaining only large winners;
- changing the trade floor after seeing results;
- rewriting research-only standalone adapter evidence as official validation;
- direct runtime/profile/strategy implementation;
- portfolio engine;
- regime system;
- multi-strategy runtime;
- T1 + CPM-1 combination.

Any new hypothesis must be a new docs-only plan before execution.

---

## 8. Follow-up Direction Assessment

### 8.1 EMA60 Close-break Exit Variant

Potential status:

> Worth considering as a new docs-only experiment plan, not as a T1-A trailing-parameter rescue.

Rationale:

- Current T1-A uses ATR trailing. It can give back a large portion of open profit and still depends heavily on rare winners.
- A 4h EMA60 close-break exit is a different trend-lifecycle exit hypothesis: exit when the major trend closes below a structural trend line, not when an ATR trail is touched.
- It may address lifecycle invalidation more directly than ATR trailing.

Required boundary:

- fully closed 4h candle close below EMA60 only;
- no intrabar touch;
- record exit trigger bar, exit execution bar, and exit price convention;
- report MTM drawdown, maximum giveback, hold duration, and funding exposure;
- no EMA period sweep;
- no mixing EMA exit with several trailing variants;
- no entry-rule change in the same first pass.

This direction should be framed as:

> New trend-lifecycle exit hypothesis.

It must not be framed as:

> T1-A trailing parameter rescue.

### 8.2 T1-B 4h Trend + 1h Entry Refinement

Current status:

> Remains reserve.

Rationale:

- T1-B has higher rule freedom and higher drift risk.
- It could improve entry location, but it could also collapse back into CPM-style pullback repair.
- NSC-009 did not execute T1-B.

If started later, T1-B requires a separate docs-only experiment plan before any execution.

The plan must prove:

- 4h remains the profit source;
- 1h is entry timing only;
- exits remain trend-lifecycle oriented;
- no CPM-1 Pinbar rescue;
- no CPM-2 reclaim rescue;
- no multi-rule 1h search.

### 8.3 C1/C2 Portfolio Proxy

C1/C2 remain warning evidence only.

They may be used to remember:

- T1 can look useful in combination while remaining fragile standalone;
- accounting and compounding assumptions can make fragility worse;
- correlation evidence is not strategy validation.

They must not be used to:

- start portfolio engine;
- start T1 + CPM-1 combination;
- start multi-strategy runtime;
- revive CPM-1 as a portfolio base;
- treat T1-lite standalone as already validated.

---

## 9. Owner Decision Options

### Option A — Pause T1-A Frozen Rule And Open EMA60 Exit Inspect/Plan

Recommended if Owner wants to continue the 4h-first main-trend capture line while changing only the exit hypothesis.

Allowed next task:

- docs-only experiment plan for EMA60 close-break exit variant.

Not allowed:

- running the variant immediately;
- EMA period sweep;
- combining ATR and EMA exits after seeing results;
- changing entry rule in the same task.

### Option B — Pause T1-A And Open T1-B Docs-only Plan

Recommended if Owner believes the entry timing is the main weakness and wants to test 1h entry refinement inside a 4h-qualified trend.

Allowed next task:

- docs-only T1-B experiment plan.

Not allowed:

- running T1-B immediately;
- CPM-1 Pinbar rescue;
- CPM-2 reclaim rescue;
- 1h rule sweep.

### Option C — Retire T1-A And Return To Next Strategy Candidate Direction

Recommended if Owner judges that thin sample plus fragility makes the current trend-capture path unattractive.

Allowed next task:

- NSC next-direction inspect.

Not allowed:

- repackaging T1-A as passed;
- portfolio/regime expansion to rescue it.

### Option D — Extend Evidence Window Only If Data Availability Supports It

Recommended only if the Owner wants to answer whether the current frozen rule is thin because the window is too short, not because the rule is weak.

Allowed next task:

- docs-only evidence-window extension plan.

Requirements:

- freeze added windows before execution;
- no parameter changes;
- no cost relaxation;
- same anti-lookahead and MTM accounting;
- same fragility gates;
- no selective-year inclusion.

---

## 10. NSC-010 Closure

NSC-010 does not authorize a next experiment.

Closure summary:

- T1-A frozen rule has some signal but did not pass the minimum evidence gate.
- Positive net PnL does not offset thin sample and top-winner fragility.
- T1-A cannot enter promotion, small-live candidate status, runtime implementation, or official backtester integration.
- T1-B remains reserve.
- CPM-1 remains paused.
- CPM-2 A/B remain closed.
- Candidate C remains reserve-only.
- Current project still has no deployable small-live strategy candidate.
- Small-live readiness gate remains unmet.

Recommended next step:

1. Prefer **Option A** if Owner wants to continue the 4h-first trend-lifecycle line: create a docs-only EMA60 close-break exit experiment plan.
2. Use **Option B** only if Owner wants to study 1h entry refinement after resolving the current T1-A closure.
3. Use **Option C** if Owner wants to leave T1-lite and reopen broader candidate direction selection.
4. Use **Option D** only if additional historical data exists and Owner wants a pure evidence-sufficiency check without parameter sweep.
