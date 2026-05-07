# TE-003 - Longer-window Data Availability Inspect

**Task ID:** TE-003
**Date:** 2026-05-07
**Status:** Accepted / Docs-only Inspect
**Scope:** Docs-only data availability inspect
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document inspects existing docs/reports/archive evidence for longer-window
ETH 1h / 4h data availability.

It is not:

- Direction A execution authorization;
- Direction B-D1 execution authorization;
- extended backtest authorization;
- data import authorization;
- data download script authorization;
- database mutation authorization;
- adapter authorization;
- strategy implementation approval;
- official validation approval;
- promotion review;
- small-live readiness review;
- live deployment advice;
- runtime/profile/risk/backtester-core change approval.

No strategy experiment, extended backtest, data import, database write, adapter,
code change, migration, test run, or parameter sweep was performed for TE-003.

Current project state remains:

| Field | State |
| --- | --- |
| Direction A | Positive-but-fragile research-only proxy evidence |
| Direction B-D1 | Positive-but-fragile / mixed-partial research-only proxy evidence |
| Deployable small-live strategy candidate | None |
| Small-live readiness gate | Remains unmet |
| Promotion conclusion | None |
| Runtime/profile/risk impact | None |

---

## 1. Inspected Materials

Primary inspected materials:

- `docs/ops/te-002-trend-edge-validation-window-readiness-inspect.md`
- `docs/ops/crypto-pullback-module-v1-2021-oos-gate-inspect-plan.md`
- `docs/ops/crypto-pullback-module-v1-2021-oos-report.md`
- `docs/ops/crypto-pullback-module-v1-2022-oos-gate-inspect-plan.md`
- `docs/ops/crypto-pullback-module-v1-2022-oos-report.md`
- `reports/oos_runs/cpm1_2021_oos/metadata.json`
- `reports/oos_runs/cpm1_2022_oos/metadata.json`
- `reports/nsc-014-direction-a-4h-main-trend-lifecycle-clean-baseline/experiment_report.md`
- `reports/nsc-014-direction-a-4h-main-trend-lifecycle-clean-baseline/summary.json`
- `reports/nsc-020-direction-b-d1-4h-trend-1h-follow-through-entry/experiment_report.md`
- `reports/nsc-020-direction-b-d1-4h-trend-1h-follow-through-entry/summary.json`
- `archive/2026-04-29-pre-live-safe-replan/scripts/etl/README.md`
- `archive/2026-04-29-pre-live-safe-replan/scripts/etl/import_all_klines.py`
- `archive/2026-04-29-pre-live-safe-replan/scripts/import_binance_klines.py`
- `archive/2026-04-29-pre-live-safe-replan/scripts/import_2021_data.py`
- `archive/2026-04-29-pre-live-safe-replan/scripts/import_2022_data.py`
- `archive/2026-04-29-pre-live-safe-replan/docs/planning/archive/phase7-validation-report.md`
- `archive/2026-04-29-pre-live-safe-replan/docs/archive/2026-04-14/phase7-etl-data-validation-fix.md`
- `archive/2026-04-29-pre-live-safe-replan/docs/diagnostic-reports/archive/2026-03-29-MTF 过滤 higher_tf_data_unavailable 问题修复.md`
- `archive/2026-04-29-pre-live-safe-replan/docs/archive/2026-04-14/test-report-backtest-data-integrity.md`
- `archive/2026-04-29-pre-live-safe-replan/docs/planning/2026-04-28-eth-baseline-oos-check.md`

This inspect used file reads and text search only. It did not query or mutate
the database.

---

## 2. Existing Confirmed Data Windows

### 2.1 Direction A / B-D1 Research Windows

Direction A and B-D1 summaries record these full-year windows:

| Year | UTC window | Direction A trades | B-D1 trades | Data status from current reports |
| --- | --- | ---: | ---: | --- |
| 2021 | 2021-01-01 to 2022-01-01 exclusive | 32 | 30 | Covered in research reports; separately QA-confirmed by CPM OOS docs |
| 2022 | 2022-01-01 to 2023-01-01 exclusive | 36 | 34 | Covered in research reports; separately QA-confirmed by CPM OOS docs |
| 2023 | 2023-01-01 to 2024-01-01 exclusive | 29 | 28 | Covered in research reports; Phase 7 local data report covers 2023-2026 |
| 2024 | 2024-01-01 to 2025-01-01 exclusive | 34 | 33 | Covered in research reports; Phase 7 local data report covers 2023-2026 |
| 2025 | 2025-01-01 to 2026-01-01 exclusive | 41 | 39 | Covered in research reports; Phase 7 local data report covers 2023-2026 |

Current confirmed practical research window remains:

> 2021-2025, five full years.

### 2.2 2021 / 2022 Confirmed ETH 1h / 4h Data

The CPM OOS planning and report documents confirm:

| Year | ETH 1h | ETH 4h | Quality evidence |
| --- | ---: | ---: | --- |
| 2021 | 8,760 / 8,760 candles | 2,190 / 2,190 candles | Full-year coverage, all 12 months complete, 0 missing, 0 duplicates, 0 timestamp gaps in 1h |
| 2022 | 8,760 / 8,760 candles | 2,190 / 2,190 candles | Full-year coverage, 0 missing, 0 duplicates, 0 timestamp gaps, no exchange outages detected in candle set |

Known caveats:

- 2021 exchange outage / May crash spread behavior is caveated.
- 2021 contract rule stability is assumed, not independently verified.
- Funding uses constant approximation, not real historical funding.
- The OOS metadata for 2021 records the database but does not repeat candle
  counts; the Markdown report carries the richer data QA details.

### 2.3 2023-2026 Local Data Evidence

The archived Phase 7 validation report confirms local `data/v3_dev.db` coverage:

| Symbol | Timeframe | Records | Range |
| --- | --- | ---: | --- |
| ETH/USDT:USDT | 1h | 27,720 | 2023-01-01 to 2026-03-01 |
| ETH/USDT:USDT | 4h | 6,930 | 2023-01-01 to 2026-03-01 |

The same report validates:

- OHLC numeric integrity after correcting the SQLite string-comparison false
  positive;
- local data repository read path;
- MTF alignment logic;
- no future-function issue in MTF alignment tests.

This supports current 2023-2025 research interpretation, but TE-003 treats it
as historical QA evidence rather than a fresh database verification.

---

## 3. Pre-2021 ETH 1h / 4h Data Availability

### 3.1 Source-level Availability

The archived ETL README states that Binance Vision futures UM monthly klines
are available at:

```text
https://data.binance.vision/data/futures/um/monthly/klines/{SYMBOL}/{TIMEFRAME}/{SYMBOL}-{TIMEFRAME}-{YEAR}-{MONTH}.zip
```

It also states:

> Binance provides data from 2020-09 to present.

This is useful source-level evidence. It means ETHUSDT 1h / 4h data may be
acquirable from Binance Vision for approximately 2020-09 onward.

### 3.2 Local Project Availability

TE-003 did not find a docs/reports/archive artifact confirming that pre-2021
ETH/USDT:USDT 1h or 4h data is already imported into the current local project
database.

Observed evidence:

- Dedicated import scripts exist for 2021 and 2022.
- Phase 7 local data validation covers 2023-2026.
- Generic ETL tooling can download/import Binance monthly kline ZIPs.
- Generic import tooling maps `ETHUSDT` to `ETH/USDT:USDT` and sets
  historical rows to `is_closed=True`.
- No inspected report confirms imported ETH 1h / 4h coverage for 2020-09
  through 2020-12.
- No inspected report confirms missing candle count, duplicate count, timestamp
  continuity, OHLC validity, or 4h/1h alignment for pre-2021 ETH data.

Therefore:

> Current project does not have confirmed pre-2021 ETH 1h / 4h data readiness.

### 3.3 Coverage Start / End

Based on source-level docs only:

| Layer | Earliest indicated start | Latest indicated end | Confidence |
| --- | --- | --- | --- |
| Binance Vision source availability | 2020-09 | Present | Medium, source-doc claim in archived ETL README |
| Local imported / QA-confirmed ETH 1h/4h | 2021-01 for OOS docs; 2023-01 for Phase 7 report | 2026-03 for Phase 7 report | High for documented windows |
| Local imported / QA-confirmed pre-2021 ETH 1h/4h | Not found | Not found | Not confirmed |

### 3.4 Continuity / Closed Candle / Symbol Issues

Known from tooling:

- Import scripts parse Binance CSV monthly ZIPs.
- Rows are inserted with local symbol format such as `ETH/USDT:USDT`.
- Historical rows are marked `is_closed=True`.
- Unique indexes / insert-or-ignore semantics are used to avoid duplicate
  `(symbol, timeframe, timestamp)` rows.

Not confirmed for pre-2021 ETH:

- whether rows exist locally;
- whether all expected months exist;
- whether 1h and 4h windows are continuous;
- whether there are missing or duplicate timestamps;
- whether OHLC numeric validation passes;
- whether `is_closed=True` is present for imported rows;
- whether 2020 contract specs, liquidity, tick size, lot size, or symbol
  semantics are comparable to 2021-2025;
- whether exchange outages or abnormal early-market behavior affect data;
- whether real funding data exists for the same period.

---

## 4. Suitability For Direction A / B-D1 Longer-window Validation

### 4.1 Direction A Requirements

Direction A requires:

- ETH 4h closed candles;
- previous 20 closed 4h high for Donchian breakout;
- previous 20 closed 4h low for initial stop;
- 4h EMA60 on closed candles;
- continuous 4h history across the validation window;
- enough warmup bars before the first evaluable signal;
- next-4h-open execution convention.

Pre-2021 data could support Direction A only if:

- 4h data is locally present and continuous;
- at least EMA60 and Donchian20 warmup are available before the validation
  start;
- OHLC numeric checks pass;
- gaps and duplicates are resolved by documented exclusion or rejection rules.

Current TE-003 judgment:

> Source-level data may be available, but local pre-2021 readiness for
> Direction A is not confirmed.

### 4.2 Direction B-D1 Requirements

B-D1 requires all Direction A data plus:

- ETH 1h closed candles;
- reliable 1h windows after each 4h signal close;
- 1h close > original 4h breakout level checks;
- next-1h-open execution convention;
- 1h/4h timestamp alignment without future-function leakage.

Current project has historical MTF alignment QA from Phase 7, but not
pre-2021 data-specific 1h/4h coverage QA.

Current TE-003 judgment:

> Source-level data may be available, but local pre-2021 readiness for B-D1 is
> not confirmed and carries higher QA burden than Direction A.

### 4.3 Cost / Funding / Slippage Suitability

Existing research uses:

- fee_rate = 0.0004;
- entry_slippage_rate = 0.001;
- stop_or_exit_slippage_rate = 0.001;
- funding_enabled = true;
- funding_rate_per_8h = 0.0001 constant approximation.

Risks for pre-2021 / 2020 data:

- Binance USDT-M perpetual market structure may differ from later years.
- Liquidity and spread may differ materially from 2021-2025.
- Contract rule stability requires confirmation.
- Constant funding approximation may be less credible for early market windows.
- A partial 2020 window may not support strong sparse-trend conclusions even
  if data exists.

Funding data:

- Real funding data is not currently confirmed in inspected docs for pre-2021.
- Real funding should not be required to start a docs-only data availability
  plan.
- Official validation should either keep constant funding explicitly caveated
  across all years or require a separate real-funding data decision.

---

## 5. Official Validation Data Requirements

Before Direction A / B-D1 official validation readiness, data requirements
should include:

### 5.1 Minimum Coverage

Recommended minimum:

- current confirmed 2021-2025 full years remain the base window;
- any longer-window extension must add at least a clearly defined contiguous
  period;
- partial 2020 data can be used only as a diagnostic / supplemental stress
  window unless Owner accepts partial-year evidence;
- official pass/fail should not rely on a short partial pre-2021 window.

If Binance Vision availability starts at 2020-09, then pre-2021 adds only about
four months. That can help inspect early-market behavior, but it is unlikely to
fully resolve sparse trend fragility by itself.

### 5.2 Data Quality Checks

Required per symbol/timeframe/year or partial window:

- source path or source URL pattern;
- local database path or immutable data snapshot path;
- start/end UTC timestamp;
- expected candle count;
- actual candle count;
- missing timestamp count and list;
- duplicate timestamp count and list;
- unexpected interval count;
- `is_closed` coverage;
- OHLC numeric validity: high >= low, open/close within high-low, positive
  prices and non-negative volume;
- monthly file presence for Binance Vision ZIP source;
- symbol mapping: `ETHUSDT` -> `ETH/USDT:USDT`;
- 1h/4h alignment coverage for B-D1;
- indicator warmup availability for Donchian20 and EMA60.

### 5.3 Gap Handling Principles

Recommended:

- no silent interpolation;
- no forward-filling OHLC;
- missing candles must be reported with timestamp list;
- a small gap can be accepted only if explicitly labeled and its effect on
  signal/exit windows is assessed;
- gaps overlapping candidate signal, stop, EMA exit, or 1h timing windows
  should invalidate affected trades or the affected window;
- duplicate timestamps should be rejected or deduplicated by a documented
  deterministic rule before any validation.

### 5.4 Symbol / Exchange Consistency

Required:

- exchange: Binance USDT-M futures / UM klines;
- source: Binance Vision monthly futures klines or an explicitly equivalent
  source;
- system symbol: `ETH/USDT:USDT`;
- source symbol: `ETHUSDT`;
- no exchange switching inside a validation window;
- contract launch / availability date documented;
- tick size / lot size / leverage / fee caveats documented where used for
  cost interpretation.

### 5.5 Same-bar / Next-bar Compatibility

Data must support:

- closed 4h signal bar;
- next 4h open for Direction A entry;
- next 4h open for EMA60 lifecycle exit;
- initial stop active after entry;
- closed 1h confirmation candle and next 1h open for B-D1;
- no use of unclosed higher timeframe candles;
- timestamp alignment compatible with MTF no-future-function rules.

### 5.6 Funding Data

Funding data is not strictly required for a data-availability inspect.

For official validation readiness:

- If constant funding is used, it must be applied consistently and labeled as
  an approximation.
- If real funding is required, real funding availability must be inspected and
  synchronized for all compared windows.
- Mixing real funding for some years with constant funding for others should
  be avoided unless reported side-by-side.

---

## 6. Conclusion Classification

Classification: **`DATA_NOT_CONFIRMED`**

Rationale:

- The project has documented ETH 1h/4h data coverage for 2021-2025.
- The project has source-level evidence that Binance Vision may provide UM
  monthly klines from 2020-09 onward.
- TE-003 did not find docs/reports/archive evidence that pre-2021 ETH 1h / 4h
  data is already imported locally, continuous, QA-checked, and ready for
  Direction A / B-D1 longer-window validation.
- Pre-2021 may add only a partial 2020 window, which is useful as supplemental
  context but unlikely to be decisive for sparse trend fragility.

Classification alternatives not selected:

| Classification | Why not selected |
| --- | --- |
| `DATA_READY_FOR_READINESS_PLAN` | Pre-2021 local coverage and QA are not confirmed. |
| `DATA_AVAILABLE_BUT_NEEDS_QA` | Source-level availability is indicated, but local data existence is not confirmed. |
| `DATA_INSUFFICIENT` | Source-level data may exist and current 2021-2025 data is sufficient for research review; insufficiency is not proven. |
| `DATA_SCOPE_TOO_RISKY` | Risks exist, but not enough evidence to declare the scope unusable. |

---

## 7. Next-step Options

### Option A - Enter Official Validation Readiness Plan

Proceed directly to an official validation readiness plan.

TE-003 judgment:

- Not recommended now.
- Pre-2021 local data readiness remains unconfirmed.
- Official validation readiness should not assume data that has not been
  verified.

### Option B - Data QA Docs-only Plan

Draft a docs-only QA plan for validating current 2021-2025 and any proposed
pre-2021 data.

TE-003 judgment:

- Useful if Owner wants to harden the already-known 2021-2025 dataset first.
- Insufficient if the goal is specifically to add pre-2021 data, because local
  pre-2021 existence remains unconfirmed.

### Option C - Data Acquisition / Coverage Task Card

Create a separate task card to verify or acquire pre-2021 ETH 1h/4h data,
record coverage, and produce a data QA report.

TE-003 judgment:

- Recommended.
- This is the correct next step if Owner wants to know whether longer-window
  validation can add anything beyond 2021-2025.
- Any acquisition/import/database mutation must be separately authorized and
  must not be bundled with strategy experiments.

### Option D - Pause Longer-window Validation And Return To Direction Map

Pause longer-window validation and return to `strategy-candidate-direction-map`
for inspect-only direction selection.

TE-003 judgment:

- Reasonable if Owner does not want to spend effort on a likely partial 2020
  extension.
- Keeps Direction A/B-D1 preserved as positive-but-fragile evidence without
  overworking the branch.

---

## 8. Recommendation

Recommended path:

1. Choose **Option C** if Owner wants to continue the longer-window question:
   create a separate data acquisition / coverage task card for pre-2021 ETH
   1h/4h.
2. Scope that task to data only: no strategy runs, no parameter sweeps, no
   official validation, no promotion conclusions.
3. Treat any 2020-09 to 2020-12 data as partial-window supplemental evidence
   unless a longer verified source is found.
4. If Owner does not want data acquisition/import work, choose **Option D** and
   return to the Strategy Candidate Direction Map.

Current hard conclusion:

> There is no deployable small-live strategy candidate. Small-live readiness
> gate remains unmet.

---

## 9. Recommended Next Task Card - Not Executed

```markdown
# Task ID
TE-004

## Goal
Verify or acquire pre-2021 ETH/USDT:USDT 1h and 4h historical data coverage
and produce a data QA report for potential Direction A / B-D1 longer-window
validation.

## Why
TE-003 classified pre-2021 ETH 1h / 4h readiness as `DATA_NOT_CONFIRMED`.
Source-level Binance Vision docs suggest UM monthly klines may exist from
2020-09 onward, but the project has no confirmed local pre-2021 ETH 1h/4h
coverage and QA report.

## Allowed files
- docs/ops/**
- reports/** inspect-only unless Owner separately authorizes output artifacts
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
- strategy reports or strategy experiment outputs

## Requirements
1. Do not run Direction A, Direction B-D1, or any extended backtest.
2. Do not do parameter sweeps or strategy-rule changes.
3. If data import/database mutation is needed, stop and request explicit Owner
   authorization before doing it.
4. Confirm whether ETHUSDT 1h and 4h Binance UM monthly klines exist before
   2021.
5. If data exists, record exact available months, expected candle counts, source
   URLs or file paths, and symbol mapping.
6. Define or execute only Owner-approved data QA checks: missing candles,
   duplicates, timestamp continuity, `is_closed`, OHLC numeric validity,
   monthly file presence, and 1h/4h alignment.
7. Document funding/cost-model caveats for early market data.
8. State whether the result is `DATA_READY_FOR_READINESS_PLAN`,
   `DATA_AVAILABLE_BUT_NEEDS_QA`, `DATA_NOT_CONFIRMED`, `DATA_INSUFFICIENT`,
   or `DATA_SCOPE_TOO_RISKY`.
9. State clearly that there is no deployable small-live strategy candidate and
   small-live readiness gate remains unmet.

## Tests
- Data QA only if separately approved; no strategy tests.

## Done When
- A docs-only data coverage/QA report exists under docs/ops/.
- The report distinguishes source availability from local imported readiness.
- The report recommends whether to proceed to official validation readiness,
  perform more data QA, acquire data, or pause longer-window validation.
- The report explicitly says it is not experiment authorization.
```

---

## 10. Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-07 | Initial longer-window data availability inspect | Codex |
