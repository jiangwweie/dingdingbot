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

# TE-004 - Pre-2021 ETH 1h/4h Data Coverage / QA Task Card

**Task ID:** TE-004
**Date:** 2026-05-07
**Status:** Proposed / Docs-only Plan
**Authorization Level:** Level 1 — data/evidence inspect + docs output; read-only DB queries allowed
**Affects Runtime Automatically:** No

---

## 0. Boundary

This task card authorizes **only** the creation of a docs-only data coverage
plan and QA specification for pre-2021 ETH/USDT:USDT 1h and 4h historical data.

It is not:

- data download authorization;
- data import authorization;
- database mutation authorization;
- Direction A execution authorization;
- Direction B-D1 execution authorization;
- extended backtest authorization;
- adapter authorization;
- strategy experiment authorization;
- strategy implementation approval;
- official validation approval;
- promotion review;
- small-live readiness review;
- live deployment advice;
- runtime/profile/risk/backtester-core change approval;
- parameter sweep authorization.

No data download, data import, database write, strategy experiment, extended
backtest, adapter, code change, migration, test run, or parameter sweep is
authorized by TE-004.

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

## 1. Goal

Verify or document the coverage status of pre-2021 ETH/USDT:USDT 1h and 4h
historical data and produce a docs-only data QA specification for potential
Direction A / B-D1 longer-window validation readiness.

This task does **not** produce any strategy conclusion. It answers only:

> Is it worth entering longer-window official validation readiness?

---

## 2. Why

TE-003 classified pre-2021 ETH 1h/4h readiness as `DATA_NOT_CONFIRMED`.

TE-003 confirmed:

- 2021-2025 is the current confirmed practical research window (five full
  years).
- Source-level Binance Vision docs suggest UM monthly klines may exist from
  2020-09 onward.
- No docs/reports/archive evidence confirms that pre-2021 ETH 1h/4h data is
  already imported locally, continuous, QA-checked, and ready for Direction A /
  B-D1 longer-window validation.

TE-004 is the recommended next step (TE-003 Option C) to resolve this gap.

---

## 3. Three-Layer Verification Model

Pre-2021 ETH 1h/4h data readiness must be assessed at three distinct layers.
Each layer must be independently confirmed before the next layer is considered.

### Layer 1 — Source-level Availability

Does the data exist at the upstream source?

- Confirm whether Binance Vision provides ETHUSDT UM monthly klines for 1h and
  4h before 2021-01-01.
- Record exact available months, source URL patterns, and file sizes if
  verifiable without downloading.
- Document contract launch date and earliest available month.
- This layer can be assessed via docs-only inspection of Binance Vision
  directory listings or published data availability docs.

### Layer 2 — Local Imported Availability

Has the data been imported into the local project database?

- Confirm whether pre-2021 ETH/USDT:USDT 1h and 4h rows exist in the current
  local database.
- If rows exist, record the exact start/end timestamps and row counts.
- If rows do not exist, document that import is required and stop — do not
  import without separate Owner authorization.
- This layer requires read-only database queries. No writes are authorized.

### Layer 3 — QA-passed Readiness

Has the imported data passed documented QA checks?

- Execute or define QA checks per Section 5 of this document.
- Record pass/fail for each check.
- If any check fails, document the failure and stop — do not fix data without
  separate Owner authorization.
- This layer requires read-only database queries and docs output. No writes
  are authorized.

**Layer progression rule:** A lower layer must be confirmed before the next
higher layer is assessed. If Layer 1 fails, there is no point checking Layer 2
or 3. If Layer 2 fails, Layer 3 cannot be assessed.

---

## 4. Authorization Scope

### 4.1 Allowed

- Read and inspect all files under `docs/ops/**`, `reports/**`, `archive/**`.
- Read-only database queries against local development database to check row
  existence, counts, and timestamps.
- Create and edit documents under `docs/ops/te-004-*`.
- Reference TE-003 findings and conclusions.
- Document Binance Vision source-level availability from public directory
  listings or published docs.
- Define QA specifications and checklists.
- Produce a coverage/QA report under `docs/ops/`.

### 4.2 Forbidden

- Data download (no `wget`, `curl`, `requests`, or script execution that
  downloads from Binance Vision or any external source).
- Data import (no execution of import scripts, no database inserts).
- Database mutation (no `INSERT`, `UPDATE`, `DELETE`, `CREATE TABLE`, `ALTER
  TABLE`, or any write operation).
- Direction A, Direction B-D1, or any extended backtest execution.
- Adapter implementation or modification.
- Strategy experiment execution.
- Parameter sweeps.
- Runtime/profile/risk/backtester-core modification.
- Promotion review or small-live readiness review.
- Live deployment advice.
- Any code change outside `docs/ops/te-004-*`.

### 4.3 Stop Conditions — Must Halt and Request Owner Authorization

TE-004 must stop immediately and request Owner authorization upgrade if any of
the following is needed:

1. **Downloading data** from Binance Vision or any external source.
2. **Importing data** into the local database.
3. **Writing to the database** for any reason (schema changes, data fixes,
   metadata updates).
4. **Running a backtest** of any kind, including research-only or diagnostic
   backtests.
5. **Executing any strategy logic** against pre-2021 data.
6. **Modifying source code** outside `docs/ops/te-004-*`.
7. **Creating or modifying** runtime profiles, risk rules, or backtester
   configuration.
8. **Making any promotion or validation readiness conclusion** that goes beyond
  "data is/is not available and QA-passed."

When a stop condition is hit, TE-004 must:

- Record the stop condition in the TE-004 report.
- State exactly what authorization upgrade is needed.
- State what the upgraded authorization would enable.
- Wait for Owner decision before proceeding.

---

## 5. Data QA Specification

If data reaches Layer 2 (local imported availability), the following QA checks
must be defined and, if Owner separately authorizes execution, performed.

### 5.1 Candle Count

| Check | Description |
| --- | --- |
| Expected candle count | Calculate expected count from start/end timestamps and interval (1h = 3600s, 4h = 14400s). Account for partial months. |
| Actual candle count | Count rows in local database for the pre-2021 window. |
| Delta | Report expected - actual. Any non-zero delta must be explained. |

### 5.2 Missing Timestamps

| Check | Description |
| --- | --- |
| Continuity scan | Generate expected timestamp sequence for 1h and 4h. Compare against actual timestamps. |
| Missing list | List all expected timestamps not found in data. |
| Gap classification | Classify gaps as: single-candle gap, multi-candle gap, exchange outage, or unknown. |

### 5.3 Duplicates

| Check | Description |
| --- | --- |
| Duplicate detection | Find rows with identical `(symbol, timeframe, timestamp)` tuples. |
| Duplicate count | Report count and list of duplicate timestamps. |
| Dedup rule | If duplicates exist, document deterministic dedup rule (e.g., keep earliest `inserted_at`). Do not execute dedup without Owner authorization. |

### 5.4 Unexpected Intervals

| Check | Description |
| --- | --- |
| Interval check | Verify consecutive timestamps differ by exactly the expected interval (3600s for 1h, 14400s for 4h). |
| Anomaly list | List any timestamp pairs with unexpected intervals. |

### 5.5 is_closed

| Check | Description |
| --- | --- |
| is_closed coverage | All historical rows must have `is_closed=True`. |
| Violation count | Count and list rows where `is_closed` is not `True`. |

### 5.6 OHLC Validity

| Check | Description |
| --- | --- |
| high >= low | Every candle must have `high >= low`. |
| open/close within range | `low <= open <= high` and `low <= close <= high`. |
| Positive prices | `open > 0`, `high > 0`, `low > 0`, `close > 0`. |
| Non-negative volume | `volume >= 0`. |
| Violation list | List all rows failing any OHLC check. |

### 5.7 Symbol Mapping

| Check | Description |
| --- | --- |
| Source symbol | `ETHUSDT` in Binance Vision files. |
| System symbol | `ETH/USDT:USDT` in local database. |
| Mapping consistency | Verify all imported rows use the correct system symbol. |

### 5.8 1h/4h Alignment

| Check | Description |
| --- | --- |
| Timestamp alignment | Every 4h timestamp must align to a 1h timestamp that is a multiple of 4h from UTC midnight. |
| Coverage alignment | For every 4h candle, the corresponding four 1h candles must exist. |
| No future-function | 4h candle must not use 1h data from a later 4h period. |

### 5.9 Indicator Warmup

| Check | Description |
| --- | --- |
| EMA60 warmup | At least 60 closed 4h candles must exist before the first evaluable Direction A signal. 60 × 4h = 10 days. |
| Donchian20 warmup | At least 20 closed 4h candles must exist before the first evaluable Direction A signal. 20 × 4h ≈ 3.3 days. |
| Combined warmup | EMA60 dominates: minimum 10 days of continuous 4h data before first signal. |
| Pre-2021 implication | If data starts 2020-09-01, first evaluable signal cannot appear before ~2020-09-11. Effective window is 2020-09-11 to 2020-12-31. |

---

## 6. Supplemental Window Classification

### 6.1 Default Classification

If the only pre-2021 data window is 2020-09 through 2020-12 (approximately four
months), it must be classified as:

> **Supplemental diagnostic window only.**

It cannot independently determine Direction A or B-D1 pass/fail.

### 6.2 Rationale

- Four months is too short to resolve sparse-trend fragility observed across
  2021-2025.
- Early-market behavior (2020 Binance USDT-M launch period) may differ
  structurally from 2021-2025 market microstructure.
- A supplemental window can provide additional stress-test context but not
  standalone validation evidence.

### 6.3 Upgrade Conditions

The supplemental classification can be upgraded only if:

- A longer pre-2021 data window is discovered (e.g., data from another
  exchange or earlier Binance spot/futures data with documented equivalence).
- Owner explicitly accepts partial-year evidence as sufficient for official
  validation.
- Both conditions require separate Owner decision, not TE-004 judgment.

---

## 7. Scope Guard — No Strategy Slide

TE-004 is a data coverage and QA task. It must not slide into strategy
validation.

Specific guards:

1. TE-004 does not authorize running Direction A or B-D1 logic against any
   data.
2. TE-004 does not authorize computing strategy metrics (win rate, PnL, Sharpe,
   drawdown, etc.) against pre-2021 data.
3. TE-004 does not authorize interpreting data coverage results as strategy
   validation evidence.
4. TE-004 output is a data coverage report, not a strategy report.
5. If data coverage results suggest a strategy experiment might be valuable,
   that is a separate task requiring separate Owner authorization.
6. TE-004 conclusions are limited to: data availability status, QA pass/fail,
   and a recommendation on whether to proceed to data acquisition or official
   validation readiness planning.

---

## 8. Deliverables

1. **TE-004 coverage/QA report** at `docs/ops/te-004-pre-2021-eth-data-coverage-report.md`
   containing:
   - Layer 1 assessment: source-level availability for pre-2021 ETHUSDT 1h/4h.
   - Layer 2 assessment: local imported availability (or confirmation that
     import is needed).
   - Layer 3 assessment: QA-passed readiness (or confirmation that QA cannot
     be assessed yet).
   - QA specification per Section 5 (ready for execution if Owner authorizes).
   - Supplemental window classification per Section 6.
   - Stop conditions encountered, if any.
   - Explicit statement: "This report does not authorize strategy experiments,
     extended backtests, data import, or promotion decisions."
   - Explicit statement: "There is no deployable small-live strategy candidate.
     Small-live readiness gate remains unmet."
   - Classification: one of `DATA_READY_FOR_READINESS_PLAN`,
     `DATA_AVAILABLE_BUT_NEEDS_QA`, `DATA_NOT_CONFIRMED`,
     `DATA_INSUFFICIENT`, or `DATA_SCOPE_TOO_RISKY`.
   - Recommendation: proceed to data acquisition, proceed to QA execution,
     proceed to official validation readiness planning, or pause longer-window
     validation.

---

## 9. Done When

- [ ] TE-004 coverage/QA report exists under `docs/ops/`.
- [ ] Report distinguishes source availability from local imported readiness
      from QA-passed readiness (three-layer model).
- [ ] Report defines QA checks per Section 5 or references them.
- [ ] Report classifies any 2020-09~2020-12 window as supplemental diagnostic
      only.
- [ ] Report states when to stop and request Owner authorization upgrade.
- [ ] Report explicitly says it is not experiment authorization.
- [ ] Report explicitly says there is no deployable small-live strategy
      candidate and small-live readiness gate remains unmet.
- [ ] No data was downloaded, imported, or mutated.
- [ ] No strategy experiment, backtest, or parameter sweep was run.
- [ ] No code outside `docs/ops/te-004-*` was modified.

---

## 10. Escalation Triggers

The following events require immediate stop and Owner notification:

| Trigger | Action |
| --- | --- |
| Pre-2021 data is found to exist locally but has never been QA-checked | Document finding; do not run QA without Owner authorization for Layer 3 |
| Pre-2021 data is found to not exist locally | Document finding; do not import without Owner authorization for Layer 2 |
| Binance Vision source is confirmed unavailable before 2021-01 | Document finding; recommend Option D (pause longer-window validation) |
| Any stop condition from Section 4.3 is encountered | Stop; document; request authorization upgrade |
| Any temptation to run strategy logic against pre-2021 data | Stop; document; this is a scope violation |

---

## 11. Relationship to TE-003

TE-004 is the recommended next step from TE-003 Option C.

TE-003 conclusions that remain binding:

- Current confirmed practical research window: 2021-2025.
- Pre-2021 ETH 1h/4h local data readiness: not confirmed.
- Binance Vision source-level availability: 2020-09 onward (medium confidence,
  source-doc claim only).
- Classification: `DATA_NOT_CONFIRMED`.

TE-004 does not re-litigate TE-003 findings. It builds on them.

---

## 12. Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-07 | Initial TE-004 task card created | Codex |
