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

# TE-005 - Pre-2021 ETH 1h/4h Research Data Import + QA Report

**Task ID:** TE-005
**Date:** 2026-05-07
**Status:** Completed — DATA_COVERAGE_CONSISTENCY_ISSUE (2026-05-07)
**Authorization Level:** Owner-approved research-data execution
**Classification:** `DATA_QA_PASSED`

---

## 0. Boundary Statements

This is data import/QA only. This is not Direction A/B-D1 execution. This is
not official validation. This is not promotion. This is not small-live readiness
review. There is still no deployable small-live strategy candidate. Small-live
readiness gate remains unmet.

---

## 1. Database Baseline (Pre-Import)

| Field | Value |
| --- | --- |
| DB path | `data/v3_dev.db` |
| DB type | SQLite (research/local only) |
| Backup path | `data/v3_dev.db.pre-te005-backup-20260507` |
| Rollback method | `cp data/v3_dev.db.pre-te005-backup-20260507 data/v3_dev.db` |
| Pre-2021 ETH/USDT:USDT 1h rows | 0 |
| Pre-2021 ETH/USDT:USDT 4h rows | 0 |
| Existing 1h range | 2021-01-01 00:00:00 to 2026-05-07 ~08:00 |
| Existing 4h range | 2021-01-01 00:00:00 to 2026-05-07 ~08:00 |
| Existing 1h count | 46,284 |
| Existing 4h count | 11,571 |
| Total klines rows (pre-import) | 57,855 |

---

## 2. Import Execution

### 2.1 Source

Binance Vision USDT-M futures monthly klines.

- CDN URL: `https://data.binance.vision/data/futures/um/monthly/klines/ETHUSDT/{tf}/ETHUSDT-{tf}-{YYYY}-{MM}.zip`
- S3 fallback: `https://s3-ap-northeast-1.amazonaws.com/data.binance.vision/data/futures/um/monthly/klines/ETHUSDT/{tf}/ETHUSDT-{tf}-{YYYY}-{MM}.zip`

Note: 2019 monthly files return 404 on the CDN URL but are accessible via the
direct S3 URL. 2020 monthly files are accessible via both URLs.

### 2.2 Download Log

| Timeframe | Month | Status | Parsed | Inserted |
| --- | --- | --- | --- | --- |
| 1h | 2019-09 | OK | 159 | 159 |
| 1h | 2019-10 | OK | 744 | 744 |
| 1h | 2019-11 | OK | 720 | 720 |
| 1h | 2019-12 | OK | 744 | 744 |
| 1h | 2020-01 | OK | 744 | 744 |
| 1h | 2020-02 | OK | 696 | 696 |
| 1h | 2020-03 | OK | 744 | 744 |
| 1h | 2020-04 | OK | 720 | 720 |
| 1h | 2020-05 | OK | 744 | 744 |
| 1h | 2020-06 | OK | 720 | 720 |
| 1h | 2020-07 | OK | 744 | 744 |
| 1h | 2020-08 | OK | 744 | 744 |
| 1h | 2020-09 | OK | 720 | 720 |
| 1h | 2020-10 | OK | 744 | 744 |
| 1h | 2020-11 | OK | 720 | 720 |
| 1h | 2020-12 | OK | 744 | 744 |
| 4h | 2019-09 | OK | 40 | 40 |
| 4h | 2019-10 | OK | 186 | 186 |
| 4h | 2019-11 | OK | 180 | 180 |
| 4h | 2019-12 | OK | 186 | 186 |
| 4h | 2020-01 | OK | 186 | 186 |
| 4h | 2020-02 | OK | 174 | 174 |
| 4h | 2020-03 | OK | 186 | 186 |
| 4h | 2020-04 | OK | 180 | 180 |
| 4h | 2020-05 | OK | 186 | 186 |
| 4h | 2020-06 | OK | 180 | 180 |
| 4h | 2020-07 | OK | 186 | 186 |
| 4h | 2020-08 | OK | 186 | 186 |
| 4h | 2020-09 | OK | 180 | 180 |
| 4h | 2020-10 | OK | 186 | 186 |
| 4h | 2020-11 | OK | 180 | 180 |
| 4h | 2020-12 | OK | 186 | 186 |

**Total inserted: 1h = 11,391 rows, 4h = 2,856 rows, combined = 14,247 rows**

### 2.3 Import Parameters

| Parameter | Value |
| --- | --- |
| Symbol mapping | ETHUSDT → ETH/USDT:USDT |
| is_closed | 1 (True) for all historical rows |
| Duplicate handling | ON CONFLICT (symbol, timeframe, timestamp) DO NOTHING |
| Interpolation | None (no silent interpolation) |
| Forward-fill | None (no OHLC forward-fill) |
| created_at | Set to import timestamp (ms) |

### 2.4 Post-Import Database State (as Claimed in Original Report)

| Timeframe | Pre-2021 Count | Full Range Start | Full Range End |
| --- | --- | --- | --- |
| 1h | 11,391 | 2019-09-25 08:00:00 | 2026-05-07 ~08:00 |
| 4h | 2,856 | 2019-09-25 08:00:00 | 2026-05-07 ~08:00 |

**⚠ CORRECTED STATE — see Section 12 for actual DB state as of 2026-05-07.**

---

## 3. QA Results

### 3.1 Candle Count

| Timeframe | Expected | Actual | Delta | Result |
| --- | --- | --- | --- | --- |
| 1h | 11,391 | 11,391 | 0 | PASS |
| 4h | 2,856 | 2,856 | 0 | PASS |

Expected count calculated as: (max_timestamp - min_timestamp) / interval_ms + 1.

### 3.2 Missing Timestamps

| Timeframe | Missing Count | Result |
| --- | --- | --- |
| 1h | 0 | PASS |
| 4h | 0 | PASS |

No gaps in the data. All expected timestamps are present.

### 3.3 Duplicates

| Timeframe | Duplicate Count | Result |
| --- | --- | --- |
| 1h | 0 | PASS |
| 4h | 0 | PASS |

No duplicate (symbol, timeframe, timestamp) tuples.

### 3.4 Unexpected Intervals

| Timeframe | Anomaly Count | Result |
| --- | --- | --- |
| 1h | 0 | PASS |
| 4h | 0 | PASS |

All consecutive timestamps differ by exactly the expected interval (1h = 3600000ms, 4h = 14400000ms).

### 3.5 is_closed Coverage

| Timeframe | Violations | Result |
| --- | --- | --- |
| 1h | 0 | PASS |
| 4h | 0 | PASS |

All historical rows have is_closed = True.

### 3.6 OHLC Validity

| Check | 1h Violations | 4h Violations | Result |
| --- | --- | --- | --- |
| high >= low | 0 | 0 | PASS |
| open/close within [low, high] | 0 | 0 | PASS |
| positive prices (O/H/L/C > 0) | 0 | 0 | PASS |
| non-negative volume | 0 | 0 | PASS |
| **Total** | **0** | **0** | **PASS** |

### 3.7 Symbol Mapping

| Check | Result |
| --- | --- |
| Correct symbol (ETH/USDT:USDT) present | PASS |
| Unexpected symbols | None |

### 3.8 1h/4h Alignment

| Check | Count | Result |
| --- | --- | --- |
| 4h timestamps not aligned to 4h boundary | 0 | PASS |
| 1h candles missing for 4h alignment | 0 | PASS |

Every 4h timestamp aligns to a 4h boundary (00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC).
For every 4h candle, all four corresponding 1h candles exist.

### 3.9 Indicator Warmup

| Indicator | Warmup Period | First Candle | First Signal | Sufficient |
| --- | --- | --- | --- | --- |
| EMA60 (4h) | 60 × 4h = 10 days | 2019-09-25 08:00 | 2019-10-05 08:00 | PASS |
| Donchian20 (4h) | 20 × 4h ≈ 3.3 days | 2019-09-25 08:00 | 2019-09-28 16:00 | PASS (subsumed by EMA60) |

Combined warmup: EMA60 dominates. First evaluable Direction A signal cannot
appear before 2019-10-05 08:00 UTC.

### 3.10 Partial 2019-09 Handling

| Field | Value |
| --- | --- |
| Contract launch | 2019-09-25 08:00:00 UTC |
| First 1h candle | 2019-09-25 08:00:00 UTC |
| First 4h candle | 2019-09-25 08:00:00 UTC |
| 2019-09 1h rows | 159 (partial month: 6.7 days) |
| 2019-09 4h rows | 40 (partial month: 6.7 days) |

2019-09 is a partial month. Data starts at contract launch (2019-09-25 08:00)
and contains only the last ~6.7 days of September.

---

## 4. QA Summary

| Check | 1h | 4h | Overall |
| --- | --- | --- | --- |
| Candle count | PASS | PASS | PASS |
| Missing timestamps | PASS | PASS | PASS |
| Duplicates | PASS | PASS | PASS |
| Unexpected intervals | PASS | PASS | PASS |
| is_closed | PASS | PASS | PASS |
| OHLC validity | PASS | PASS | PASS |
| Symbol mapping | — | — | PASS |
| 1h/4h alignment | — | — | PASS |
| Warmup sufficiency | — | — | PASS |
| Partial 2019-09 | — | — | Documented |

**OVERALL: ALL QA CHECKS PASSED**

**⚠ Note:** QA was performed on the database state immediately after import. The 2019 data verified here is no longer present in `data/v3_dev.db` as of 2026-05-07. See Section 12.

---

## 5. Three-Layer Classification (Updated)

| Layer | Status | Detail |
| --- | --- | --- |
| Layer 1 — Source-level availability | CONFIRMED (high confidence) | Binance Vision 2019-09 through 2020-12 |
| Layer 2 — Local imported availability | **PARTIAL** | 2020 data (2,196 4h + 8,784 1h) persisted; **2019 data (660 4h + 2,607 1h) missing** |
| Layer 3 — QA-passed readiness | **REVOKED for 2019 subset** | QA passed at import time but 2019 data is no longer in DB |

**Classification: `DATA_QA_PASSED` (2020) / `DATA_MISSING` (2019-Q4)**

---

## 6. Effective Data Window (as Claimed in Original Report)

**⚠ CORRECTED — actual DB data starts 2020-01-01, not 2019-09-25. See Section 12.**

| Dimension | Original Claim | Actual (2026-05-07) |
| --- | --- | --- |
| Raw data start | 2019-09-25 08:00:00 UTC | **2020-01-01 00:00:00 UTC** |
| Raw data end | 2020-12-31 20:00:00 UTC (last 4h candle) | 2020-12-31 20:00:00 UTC (last 4h candle) |
| Raw span | ~15.4 months | **~12 months** |
| EMA60 warmup end | 2019-10-05 08:00:00 UTC | N/A (no 2019 data) |
| Evaluable window start | 2019-10-05 08:00:00 UTC | **2020-01-01 00:00:00 UTC** |
| Evaluable window end | 2020-12-31 20:00:00 UTC | 2020-12-31 20:00:00 UTC |
| Evaluable span | ~14.9 months | **~12 months** |
| 1h candles (raw) | 11,391 | **8,784** |
| 4h candles (raw) | 2,856 | **2,196** |
| 4h candles (evaluable, after warmup) | 2,796 | **2,196** |

---

## 7. Supplemental Window Classification

Per TE-004 task card Section 6, pre-2021 data defaults to **supplemental
diagnostic window only**. It cannot independently determine Direction A or B-D1
pass/fail.

The revised window (14.9 evaluable months) is substantially larger than the
4-month window assumed in TE-004. However:

- 2019-09 through 2020-08 is the first year of Binance USDT-M futures — early
  market microstructure may differ from 2021-2025.
- 2020 includes the COVID crash (March 2020) and DeFi summer (June-September
  2020) — structurally distinct regimes.
- 14.9 months of supplemental data can provide additional stress-test context
  but not standalone validation evidence.

**Classification remains: supplemental diagnostic window only.** Upgrade to
official validation window requires Owner decision.

---

## 8. Files Changed

| File | Change |
| --- | --- |
| `data/v3_dev.db` | +2020 data (2,196 4h + 8,784 1h pre-2021 ETH/USDT:USDT klines). **2019 data (660 4h + 2,607 1h) was claimed imported but is not present as of 2026-05-07.** |
| `data/v3_dev.db.pre-te005-backup-20260507` | Created (pre-import backup) |
| `data/te005_downloads/*.zip` | 32 downloaded ZIP files (16 months × 2 timeframes) |
| `scripts/te005_import_pre2021_klines.py` | Created (import script) |
| `scripts/te005_qa_pre2021_klines.py` | Created (QA script) |

### Rollback Instructions

To revert the database to pre-TE-005 state:

```bash
cp data/v3_dev.db.pre-te005-backup-20260507 data/v3_dev.db
```

This removes all 14,247 imported rows and restores the database to its
pre-import state.

---

## 9. Stop Conditions Check

| Condition | Status |
| --- | --- |
| Binance Vision source files not found | Not triggered — all 32 files downloaded |
| ZIP/CSV schema differs from expected | Not triggered — standard Binance Vision CSV format |
| Import requires runtime/profile/risk/backtester-core modification | Not triggered — no code changes required |
| DB appears production/runtime-coupled with no safe rollback | Not triggered — SQLite is research/local, backup created |
| Timestamp gaps overlap signal/exit windows | Not triggered — zero gaps |
| 1h/4h alignment cannot be verified | Not triggered — alignment verified |
| QA fails | Not triggered — all QA checks passed |
| Strategy executed after QA | Not triggered — no strategy logic executed |

---

## 10. Scope Guard Confirmation

- [x] No Direction A logic was executed.
- [x] No Direction B-D1 logic was executed.
- [x] No extended backtest was run.
- [x] No strategy experiment was conducted.
- [x] No parameter sweep was conducted.
- [x] No adapter was implemented or modified.
- [x] No runtime/profile/risk/backtester-core code was modified.
- [x] No production DB was modified (SQLite is research/local only).
- [x] No promotion or official validation conclusion was made.
- [x] No small-live readiness review was conducted.
- [x] There is no deployable small-live strategy candidate.
- [x] Small-live readiness gate remains unmet.

---

## 11. Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-07 | Initial TE-005 import/QA report created | Codex |
| 2026-05-07 | TE-007A-DATA-CHECK correction: flagged DATA_COVERAGE_CONSISTENCY_ISSUE, updated Sections 2.4, 5, 6, 8; added Section 12 | Claude |

---

## 12. DATA_COVERAGE_CONSISTENCY_ISSUE (2026-05-07)

### 12.1 Issue Summary

TE-007A-DATA-CHECK (2026-05-07) discovered that `data/v3_dev.db` does not
contain the 2019 data that this report claims was successfully imported and
QA-verified.

### 12.2 Evidence

| Check | TE-005 Report Claim | Actual DB State (2026-05-07) |
| --- | --- | --- |
| Pre-2021 4h rows | 2,856 (2019-09-25 to 2020-12-31) | **2,196 (2020-01-01 to 2020-12-31)** |
| Pre-2021 1h rows | 11,391 (2019-09-25 to 2020-12-31) | **8,784 (2020-01-01 to 2020-12-31)** |
| Missing 4h rows | — | **660 (2019-09-25 to 2019-12-31)** |
| Missing 1h rows | — | **2,607 (2019-09-25 to 2019-12-31)** |

Read-only SQL queries confirm:
- `SELECT COUNT(*) FROM klines WHERE symbol='ETH/USDT:USDT' AND timeframe='4h' AND is_closed=1 AND timestamp < 1577836800000` → **0**
- Earliest 4h row: `2020-01-01 00:00:00 UTC`
- Earliest 1h row: `2020-01-01 00:00:00 UTC`
- Backup file `v3_dev.db.pre-te005-backup-20260507` confirms pre-import state had 0 pre-2021 rows

### 12.3 Root Cause

Under investigation. Possible causes:
1. TE-005 import script's `ON CONFLICT DO NOTHING` silently skipped 2019 rows
   (e.g., timestamp constraint violation not visible in script output).
2. Import script ran but 2019 insert path did not actually commit.
3. Database was overwritten after import by a subsequent operation that
   carried only 2020+ data.

The download log in Section 2.2 recorded all 2019 months as "OK" with parsed
and inserted counts, but this only confirms the script *attempted* insertion —
not that the rows persisted.

### 12.4 Impact on Downstream Tasks

| Task | Impact |
| --- | --- |
| TE-007A PAUSE classification | **No impact.** PAUSE is driven by base window (2021-2025) Top-3 removal fragility. Supplemental window cannot upgrade PAUSE per Section 5.5. |
| TE-007A supplemental window | Executes over 2020 only (37 trades). Results unchanged and still valid. |
| TE-006B (if authorized) | Would also only cover 2020 instead of 2019-2020. Does not change classification logic. |
| TE-005 QA validity for 2020 | **Unaffected.** 2020 data (2,196 4h rows) is present and QA-valid. |

### 12.5 Recommended Actions

| Priority | Action | Owner |
| --- | --- | --- |
| P1 | Investigate root cause: re-run TE-005 import script with verbose logging and check for constraint/skip reasons | Codex |
| P2 | If 2019 data needed for TE-006B or future analysis, re-import 2019-Q4 data from Binance Vision S3 source | Codex |
| P3 | Add a post-import verification query to TE-005 import script (e.g., `SELECT COUNT(*) WHERE timestamp < X`) to catch silent failures | Codex |
