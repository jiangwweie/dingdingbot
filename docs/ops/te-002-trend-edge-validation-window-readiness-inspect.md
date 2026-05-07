# TE-002 - Trend Edge Validation Window & Official Evidence Readiness Inspect

**Task ID:** TE-002
**Date:** 2026-05-07
**Status:** Proposed / Inspect Only
**Scope:** Docs-only inspect report
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document is an inspect-only report based on existing `docs/ops`,
`reports`, and archived materials.

It is not:

- experiment authorization;
- extended backtest authorization;
- adapter authorization;
- code authorization;
- strategy implementation approval;
- official validation approval;
- promotion review;
- small-live readiness review;
- live deployment advice;
- runtime/profile/risk/backtester-core change approval.

No experiment was run for TE-002. No code, adapter, runtime profile, risk rule,
strategy implementation, migration, test, or backtester / research engine core
file was modified.

Current project state remains:

| Field | State |
| --- | --- |
| Direction A | Positive-but-fragile research-only evidence |
| Direction B-D1 | Positive-but-fragile / mixed-partial research-only evidence |
| Deployable small-live strategy candidate | None |
| Small-live readiness gate | Remains unmet |
| Promotion conclusion | None |
| Runtime/profile/risk impact | None |

---

## 1. Inspected Materials

Primary inspected materials:

- `docs/ops/te-001-sparse-trend-edge-evidence-review.md`
- `docs/ops/nsc-013-direction-a-4h-main-trend-lifecycle-clean-baseline-minimal-experiment-plan.md`
- `reports/nsc-014-direction-a-4h-main-trend-lifecycle-clean-baseline/experiment_report.md`
- `reports/nsc-014-direction-a-4h-main-trend-lifecycle-clean-baseline/summary.json`
- `docs/ops/nsc-019-direction-b-4h-trend-1h-entry-timing-minimal-experiment-plan.md`
- `reports/nsc-020-direction-b-d1-4h-trend-1h-follow-through-entry/experiment_report.md`
- `reports/nsc-020-direction-b-d1-4h-trend-1h-follow-through-entry/summary.json`
- `docs/ops/crypto-pullback-module-v1-2021-oos-gate-inspect-plan.md`
- `docs/ops/crypto-pullback-module-v1-2021-oos-report.md`
- `docs/ops/crypto-pullback-module-v1-2022-oos-gate-inspect-plan.md`
- `docs/ops/crypto-pullback-module-v1-2022-oos-report.md`
- `docs/ops/crypto-pullback-module-v1-2022-oos-reconciliation-note.md`
- `archive/2026-04-29-pre-live-safe-replan/docs/planning/2026-04-29-p0-pinbar-e4-official-validation.md`
- `archive/2026-04-29-pre-live-safe-replan/docs/planning/2026-04-29-p0-pinbar-e4-official-validation-script-fix-v3.md`
- `archive/2026-04-29-pre-live-safe-replan/scripts/import_2021_data.py`
- `archive/2026-04-29-pre-live-safe-replan/scripts/import_2022_data.py`
- `archive/2026-04-29-pre-live-safe-replan/scripts/validate_eth_oos_2025.py`

This inspect did not read or modify `src/**`, `configs/**`, `tests/**`,
`migrations/**`, runtime profiles, production strategy paths, risk rules, or
backtester / research engine core.

---

## 2. Current Evidence Status

TE-001 concluded:

- Direction A and Direction B-D1 should be retained as positive-but-fragile
  evidence.
- Top 3 / top 5 winner removal turning net negative should not mechanically
  equal reject for sparse trend strategies.
- The same fragility still blocks deployable / small-live pass.
- Direction A / B-D1 micro-tuning should pause before more rule variants are
  tested.

TE-002 confirms that state. The next question is not whether to run D2/D3/D4.
The next question is whether the existing evidence basis is ready for an
official validation readiness plan or whether data-window availability must be
inspected first.

---

## 3. Why Direction A / B-D1 Are Still Research-only Proxy Evidence

Direction A and Direction B-D1 reports both state `FEASIBLE_STANDALONE_ADAPTER`.
They were expressed as one-off research adapters under `reports/**`.

They are not official validation because:

1. They did not run through a registered production strategy module.
2. They did not use a committed official validation script with recorded
   engine version, commit hash, immutable config/profile hash, and output schema
   comparable to CPM OOS reports.
3. They did not pass through the official `v3_pms` dynamic strategy path
   confirmation standard used by the archived P0 Pinbar(E4) official validation
   report.
4. Their adapters live under `reports/**`, not as an official validation
   harness or production strategy implementation.
5. They use the CPM-1 OOS cost model as research SSOT, but their cost
   accounting remains report-adapter level and is not an official engine
   validation artifact.
6. They do not establish reproducible run metadata such as commit hash,
   config/profile hash, engine version, data snapshot hash, and owner-approved
   run gate.
7. They produce research classification only: `PAUSE_FRAGILE`; promotion,
   small-live, and live deployment conclusions remain `None`.

This does not make the evidence useless. It means the evidence can support
readiness planning, attribution design, and data-window inspection, but not
promotion or small-live readiness.

### 3.1 Official vs Proxy Evidence Boundary

| Dimension | Research-only standalone adapter | Official validation expectation |
| --- | --- | --- |
| Location | `reports/**` one-off adapter | Owner-approved validation script / official harness |
| Strategy path | Custom research logic | Confirmed official backtester / dynamic strategy path where applicable |
| Metadata | Report-dependent | Engine version, commit hash, config/profile hash, data source, run ID |
| Rule status | Frozen for experiment | Frozen and reproducible from immutable spec |
| Costs | Research SSOT applied by adapter | Engine-applied and reconciled cost model |
| Evidence use | Directional research / pause / reject | Official evidence readiness or validation review |
| Runtime effect | None | Still none unless separately approved |

Official validation is not promotion. It is only a cleaner evidence layer.

---

## 4. Current Historical Window Inventory

### 4.1 Windows Covered By Direction A / B-D1

Both Direction A and B-D1 summaries explicitly cover full-year windows:

| Year | UTC window | Direction A trades | B-D1 trades | Role in current interpretation |
| --- | --- | ---: | ---: | --- |
| 2021 | 2021-01-01 to 2022-01-01 exclusive | 32 | 30 | Bull / older stress-style reference |
| 2022 | 2022-01-01 to 2023-01-01 exclusive | 36 | 34 | Bear / whipsaw reference |
| 2023 | 2023-01-01 to 2024-01-01 exclusive | 29 | 28 | Positive recent reference |
| 2024 | 2024-01-01 to 2025-01-01 exclusive | 34 | 33 | Strong positive recent reference |
| 2025 | 2025-01-01 to 2026-01-01 exclusive | 41 | 39 | Recent weak/near-flat reference |

Current covered window: **2021-2025, five full calendar years**.

Direction A aggregate:

- 172 closed positions.
- Net +2332.51.
- PF 1.42270.
- MTM MaxDD 8.33%.
- Top 3 / top 5 net excluding remains negative.

B-D1 aggregate:

- 164 closed positions.
- Net +2440.63.
- PF 1.45473.
- MTM MaxDD 7.84%.
- Top 3 / top 5 net excluding remains negative.

### 4.2 Data Quality Records Currently Available

Confirmed from CPM OOS documents:

| Year | 1h data | 4h data | Quality notes |
| --- | --- | --- | --- |
| 2021 | 8,760 / 8,760 candles | 2,190 / 2,190 candles | Full year complete; 0 missing, 0 duplicates, 0 timestamp gaps in 1h; exchange outage and contract-rule assumptions caveated |
| 2022 | 8,760 / 8,760 candles | 2,190 / 2,190 candles | Full year complete; 0 missing, 0 duplicates, 0 timestamp gaps; no exchange outages detected in candle set |

From Direction A / B-D1 summaries:

- Data source recorded as `/Users/jiangwei/Documents/final/data/v3_dev.db`.
- Year windows for 2021-2025 are recorded.
- Cross-year indicators are computed over continuous series instead of
  resetting inside each year.

Current gap:

- TE-002 found explicit data-quality confirmations for 2021 and 2022.
- TE-002 did not find equally explicit docs-only data-quality confirmations
  for 2023, 2024, and 2025 comparable to the CPM 2021/2022 OOS reports.
- TE-002 did not find a confirmed pre-2021 ETH 1h/4h availability report.

### 4.3 Earlier ETH 4h / 1h Data Availability

Current inspect result:

- Archived import scripts explicitly cover 2021 and 2022.
- Direction A/B-D1 reports cover 2021-2025.
- The inspected docs mention possible multi-year OOS such as 2020-2023 for
  CPM-era thinking, but TE-002 did not find a verified local ETH 1h/4h
  data-quality report for 2020 or earlier.

Therefore, earlier data must be classified as:

> Unknown / not yet verified from allowed docs-only evidence.

This does not mean earlier ETH data is unavailable. It means TE-002 cannot
claim availability without a separate data-availability inspect.

### 4.4 OOS / Stress Window Sufficiency

Current evidence includes multiple regimes:

- 2021: bull year with correction.
- 2022: sustained bear / whipsaw year.
- 2023: recovery / positive trend reference.
- 2024: strong positive trend reference.
- 2025: recent weak / choppy reference.

This is enough for **research evidence review**, but not enough for
deployable or small-live readiness because:

- Direction A/B-D1 were not official validation runs.
- Winner attribution by year / signal context is incomplete.
- Top-winner concentration remains unresolved.
- 2023/2024 dominate net contribution.
- Funding is modeled as a constant approximation.
- 2023-2025 data quality is not documented at the same standard as 2021/2022
  OOS reports.

---

## 5. Would Longer-window Validation Help?

### 5.1 Why It Could Help

A longer window could help if it adds genuinely new regimes:

- pre-2021 trend / chop behavior;
- additional full bull-bear transitions;
- different funding and volatility regimes;
- more large-trend opportunities to test whether winners are cross-year and
  thesis-consistent;
- more stress periods to assess residual loss after removing top winners.

It could specifically reduce ambiguity around top-winner fragility:

- If additional large winners appear in distinct years and match the 4h main
  trend lifecycle thesis, the current top-winner concentration becomes more
  acceptable.
- If new windows are flat/negative but controlled, they may support
  `PAUSE_FRAGILE` or `PAUSE_NEEDS_LONGER_WINDOW` rather than reject.
- If earlier windows show no structural winners, or winners are event-spike
  artifacts, the evidence should move toward
  `REJECT_OVERFITTED_WINNER_DEPENDENCE` or `REJECT_NO_EDGE`.

### 5.2 Why It Might Not Help

Longer-window validation may not add much if:

- it only adds more samples from a highly similar regime;
- data before 2021 is thin, inconsistent, or not comparable for Binance
  USDT-M perpetuals;
- cost/funding assumptions become less reliable as the window moves further
  back;
- contract specs, liquidity, spread, or exchange behavior differ materially;
- the same top-winner cluster still dominates full-window net after adding
  earlier data.

### 5.3 Main Risk Of Longer Window

The main risk is false confidence:

- adding a year with questionable data quality can make fragility analysis look
  more robust while actually adding methodology noise;
- constant funding may become less credible across older regimes;
- official-vs-proxy gaps remain even if the window is longer;
- a longer proxy run still would not be official validation.

Conclusion:

> Longer-window validation is meaningful only after a data-availability and
> data-quality inspect. It should not be run immediately as an experiment.

---

## 6. Official Validation Readiness Checklist Draft

This checklist is a draft for future Owner review. It does not authorize a run.

### 6.1 Data Window Requirements

Required:

- exact UTC start/end for every validation window;
- full-year coverage unless a diagnostic window is explicitly labeled;
- per-year 1h and 4h candle counts;
- missing candle count and timestamps;
- duplicate timestamp count;
- unexpected timestamp gap count;
- exchange outage / abnormal market event notes;
- symbol and contract mapping: `ETH/USDT:USDT`;
- confirmation that indicators are computed over continuous data where needed;
- data snapshot path and reproducibility note;
- explicit statement whether pre-2021 data is available, unavailable, or
  caveated.

Minimum current readiness:

- 2021 and 2022 have documented 1h/4h completeness.
- 2023-2025 need comparable data-quality documentation before official
  validation readiness.
- Any pre-2021 extension requires a separate data availability task.

### 6.2 Cost / Funding / Slippage Requirements

Required:

- fee rate and source;
- entry slippage rate and source;
- stop/risk-exit slippage rate and source;
- EMA/lifecycle-exit slippage rate and source;
- whether end-of-window force closes are allowed and how they are costed;
- funding enabled/disabled state;
- funding rate source: constant approximation or real funding data;
- cost bridge from gross to net;
- per-year fee, slippage, and funding costs;
- known limitation if real funding is unavailable.

Current proposed baseline for comparability:

- fee_rate = 0.0004;
- entry_slippage_rate = 0.001;
- stop_or_lifecycle_exit_slippage_rate = 0.001;
- funding_enabled = true;
- funding_rate_per_8h = 0.0001 constant approximation.

Official readiness caveat:

- Constant funding is acceptable only as a clearly labeled approximation.
- If real funding data becomes available, all compared windows should use the
  same funding methodology or be reported side-by-side.

### 6.3 Same-bar / Next-bar Policy

Required:

- no same-bar entry from signal close;
- Direction A entry: signal on fully closed 4h bar N enters at 4h bar N+1 open;
- B-D1 entry: first eligible fully closed 1h confirmation enters at next 1h
  open;
- initial stop is active after entry;
- intrabar EMA60 touch does not trigger lifecycle exit;
- EMA60 close-break exits at next 4h open after the closed trigger bar;
- if stop and lifecycle exit conflict, use pessimistic documented ordering;
- same-bar conflict count and impact must be reported.

### 6.4 Anti-lookahead Proof

Required:

- Donchian high/low windows use only prior closed 4h bars;
- signal bar is excluded from prior-window calculations;
- original breakout level is fixed at signal time and not recomputed;
- 1h confirmation candles, if used, close strictly after the 4h signal close;
- EMA60 uses only closed 4h candles available at trigger time;
- cross-year calculations do not reset indicators in a way that creates
  artificial yearly artifacts;
- no future candle is used for entry, stop, exit, attribution, or filtering.

### 6.5 Official vs Proxy Adapter Requirements

Before official validation readiness, the project must decide whether official
validation means:

1. official backtester path with a dedicated validation script, or
2. a still-standalone but fully reproducible validation harness.

Minimum requirements either way:

- no production strategy implementation unless separately approved;
- no runtime/profile/risk changes;
- immutable frozen rule specification;
- recorded engine version;
- recorded commit hash;
- recorded config/profile hash or explicit "research-only no runtime profile"
  snapshot;
- recorded data source and data snapshot;
- deterministic output directory;
- smoke proof that the intended strategy path is actually used;
- no parameter changes after seeing results.

The archived P0 Pinbar(E4) official validation provides useful precedent:

- it confirmed `mode=v3_pms`;
- it confirmed dynamic strategy path use;
- it preserved attribution/filter evidence;
- it required smoke proof that the target filter was active;
- it still produced no runtime change.

Direction A/B-D1 do not yet meet this official validation standard.

### 6.6 Required Metrics

Future official validation readiness reports must include:

- closed positions count;
- gross PnL before costs;
- net PnL after costs;
- PF;
- win rate;
- average winner / average loser;
- realized MaxDD;
- MTM MaxDD;
- MFE distribution;
- MAE distribution;
- max and distributional giveback;
- hold duration distribution;
- funding intervals and funding cost by year;
- fee and slippage cost by year;
- year-by-year contribution;
- top 1 / top 3 / top 5 net excluding;
- worst 1 / worst 3 / worst 5 net excluding;
- top winner attribution by year / regime / signal context;
- whether winners match the main-trend lifecycle thesis;
- same-bar conflict count and impact;
- anti-lookahead proof;
- official/proxy evidence classification.

### 6.7 Sparse Trend Edge Evidence Gates

Use the TE-001 proposed gate set:

| Gate | Meaning |
| --- | --- |
| `PASS_TO_EVIDENCE_REVIEW` | Sufficient research evidence to justify official validation readiness review, not promotion |
| `PAUSE_FRAGILE` | Positive evidence exists, but fragility blocks pass |
| `PAUSE_NEEDS_LONGER_WINDOW` | Directionally interesting, but window/regime coverage is too narrow |
| `REJECT_OVERFITTED_WINNER_DEPENDENCE` | Edge is mostly accidental or overfit winner selection |
| `REJECT_NO_EDGE` | Gross/net structure does not show edge |
| `INSUFFICIENT_EVIDENCE` | Evidence volume, feasibility, or cleanliness is inadequate |

### 6.8 Rejection / Pause Conditions

Reject or pause if:

- gross expectancy is negative;
- net after realistic costs is negative;
- PF below 1.0 without compelling structural explanation;
- top winners are single-year or event-spike dependent;
- top winners do not match the main-trend lifecycle thesis;
- top 3 / top 5 removal is negative and residual losses are uncontrolled;
- yearly net depends almost entirely on one year;
- funding/slippage/cost assumptions are relaxed to pass;
- data quality is unknown for key years;
- official/proxy path cannot be reconciled;
- a rule requires post-result selection, parameter rescue, or extra overlays.

---

## 7. Current Direction A / B-D1 Readiness Judgment

### 7.1 Direction A

Judgment:

- Keep as positive-but-fragile research evidence.
- Not ready for official validation run.
- Potentially worth official validation readiness planning after data-quality
  checklist is completed.
- Longer-window inspect may be useful if pre-2021 ETH 1h/4h data can be
  verified cleanly.

Why:

- It has positive net, positive gross, PF above 1, moderate MTM DD, sufficient
  2021-2025 trade count, and a trend-like payoff shape.
- It remains blocked by top-winner concentration and 2023/2024 contribution
  dominance.
- It lacks winner attribution and official reproducibility metadata.

### 7.2 Direction B-D1

Judgment:

- Keep as positive-but-fragile / mixed-partial research evidence.
- Not ready for official validation run.
- Do not continue into D2/D3/D4 or a multi-rule 1h search.
- If official validation readiness proceeds, B-D1 should be treated as a
  comparator to Direction A, not as a new rule-search branch.

Why:

- It slightly improved net/PF/DD and preserved baseline top-5 winners.
- It did not clearly improve entry quality.
- It remains top-winner fragile.
- It adds 1h timing complexity and therefore needs stronger anti-lookahead and
  path-proof requirements than Direction A.

---

## 8. Explicit Non-authorization

The following are not authorized:

- extended backtest;
- Direction A rerun;
- Direction B-D1 rerun;
- D2 / D3 / D4;
- new 1h rule;
- new exit;
- new overlay;
- parameter sweep;
- CPM rescue;
- E-A reopen;
- Direction A parameter search;
- Direction B multi-rule search;
- portfolio / regime / multi-strategy work;
- multi-asset work;
- runtime/profile/risk changes;
- production strategy implementation;
- backtester / research engine core changes;
- promotion conclusion;
- small-live conclusion;
- live deployment conclusion.

---

## 9. Next-step Options

### Option A - Official Validation Readiness Plan

Draft a docs-only official validation readiness plan for Direction A and B-D1.

Use if Owner wants to define the official validation path, metadata standard,
report schema, and pass/pause/reject gates before deciding whether any run is
worth doing.

Pros:

- Clarifies official vs proxy evidence boundary.
- Reduces risk of accidental promotion-style interpretation.
- Keeps rule variants paused.

Cons:

- Still cannot answer whether pre-2021 data changes fragility.
- May be premature if data availability is unknown.

### Option B - Longer-window Data Availability Task

Inspect whether earlier ETH 1h/4h data exists, is clean, and is comparable.

Use if Owner wants to know whether a longer validation window is feasible
before drafting official validation execution details.

Pros:

- Directly addresses whether more years can help top-winner fragility.
- Prevents running or planning around data that may be unavailable or noisy.

Cons:

- May conclude no useful pre-2021 window exists.
- Does not by itself improve official validation readiness.

### Option C - Continue Pause And Return To Direction Map

Pause active strategy experiments and return to
`strategy-candidate-direction-map-v1` for inspect-only direction selection.

Use if Owner does not want to invest more in the current frozen variants.

Pros:

- Avoids overworking a fragile branch.
- Keeps research from drifting into rule rescue.

Cons:

- Leaves Direction A/B-D1 unresolved as positive-but-fragile evidence.

### Option D - Close Current Frozen Variants

Close Direction A clean baseline and Direction B-D1 current frozen variants,
while retaining 4h main-trend lifecycle capture as a long-term direction.

Use if Owner judges current winner concentration and 2023/2024 dominance too
fragile to justify more validation planning.

Pros:

- Clean closure.
- Prevents slow overfit drift.

Cons:

- May discard a plausible sparse trend payoff shape before attribution and
  longer-window questions are answered.

---

## 10. Recommendation

Recommended path:

1. Choose **Option B** first: longer-window data availability inspect.
2. Then choose **Option A** only if Option B confirms that data windows and
   data-quality evidence are sufficient or clearly bounded.
3. Keep Direction A and B-D1 paused as positive-but-fragile evidence.
4. Do not run Direction A/B-D1, D2/D3/D4, new entry/exit variants, overlays, or
   parameter sweeps.
5. If longer-window data is unavailable or too caveated, return to Option C or
   Option D.

Reasoning:

- The current five-year 2021-2025 window is useful but still leaves top-winner
  attribution and year-contribution questions unresolved.
- TE-002 cannot confirm pre-2021 ETH 1h/4h data availability from docs-only
  evidence.
- Official validation readiness should not be designed around assumed data.
- Longer-window availability is the least invasive next inspect task and keeps
  the research chain paused.

Current hard conclusion:

> There is no deployable small-live strategy candidate. Small-live readiness
> gate remains unmet.

---

## 11. Recommended Next Task Card - Not Executed

```markdown
# Task ID
TE-003

## Goal
Inspect whether a longer ETH 1h/4h historical validation window is available,
clean, and comparable for Direction A / Direction B-D1 Sparse Trend Edge
evidence.

## Why
TE-002 finds that Direction A / B-D1 currently cover 2021-2025 and remain
positive-but-fragile research-only evidence. Longer-window validation may help
interpret top-winner fragility, but pre-2021 ETH 1h/4h data availability and
quality were not confirmed from docs-only evidence.

## Allowed files
- docs/ops/**
- reports/** inspect-only
- archive/** inspect-only

## Forbidden files
- src/**
- configs/**
- tests/**
- migrations/**
- runtime profiles
- production strategy implementation
- risk rules
- backtester / research engine core

## Requirements
1. Do not run experiments or backtests.
2. Do not write code or create adapters.
3. Inspect existing documented data sources, import scripts, reports, and
   archived notes for ETH/USDT:USDT 1h and 4h availability before 2021.
4. Identify confirmed, unknown, and caveated years.
5. Define data-quality checks required before any future validation run:
   candle counts, gaps, duplicates, timestamp continuity, exchange outages,
   contract-spec caveats, funding availability, and cost-model comparability.
6. State whether longer-window validation is meaningful, unavailable, or too
   caveated.
7. Preserve research/runtime isolation.
8. State clearly that there is no deployable small-live strategy candidate and
   small-live readiness gate remains unmet.

## Tests
- Docs-only inspect; no tests.

## Done When
- A docs-only data availability report exists under docs/ops/.
- The report distinguishes confirmed windows from unverified windows.
- The report recommends whether to proceed to official validation readiness
  planning, continue pause, return to Strategy Candidate Direction Map, or close
  current frozen variants.
- The report explicitly says it is not experiment authorization.
```

---

## 12. Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-07 | Initial Trend Edge validation-window and readiness inspect | Codex |
