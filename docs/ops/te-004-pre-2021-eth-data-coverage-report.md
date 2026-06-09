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

# TE-004 - Pre-2021 ETH 1h/4h Data Coverage / QA Report

**Task ID:** TE-004
**Date:** 2026-05-07
**Status:** Completed / Level 1 Inspect
**Authorization Level:** Level 1 — data/evidence inspect + docs output; read-only DB queries allowed
**Classification:** `DATA_AVAILABLE_BUT_NEEDS_IMPORT`

---

## 0. Boundary Reminder

This report does not authorize strategy experiments, extended backtests, data
import, data download, database mutation, or promotion decisions.

There is no deployable small-live strategy candidate. Small-live readiness gate
remains unmet.

---

## 1. Executive Summary

| Layer | Status | Finding |
| --- | --- | --- |
| Layer 1 — Source-level availability | **CONFIRMED** | Binance Vision provides ETHUSDT UM futures monthly klines for both 1h and 4h from 2019-09 through 2020-12 (and beyond). |
| Layer 2 — Local imported availability | **NOT CONFIRMED** | Local SQLite database contains zero pre-2021 rows for ETH/USDT:USDT 1h or 4h. |
| Layer 3 — QA-passed readiness | **NOT ASSESSABLE** | Cannot assess QA without local data. |

**Overall classification:** `DATA_AVAILABLE_BUT_NEEDS_IMPORT`

**Key correction to TE-003:** TE-003 stated "Binance Vision source-level availability: 2020-09 onward (medium confidence, source-doc claim only)." This report upgrades that finding to **high confidence** and extends the window: source-level data is available from **2019-09** (contract launch) through **2020-12**, not just 2020-09 through 2020-12.

---

## 2. Layer 1 — Source-level Availability

### 2.1 Contract Launch Date

Binance API `fapi/v1/exchangeInfo` confirms:

- **ETHUSDT perpetual contract onboardDate:** 2019-09-25 08:00:00 UTC
- **Contract type:** PERPETUAL
- **Status:** TRADING

This means ETHUSDT USDT-M perpetual has been trading since September 2019, not
November 2020 as the daily kline directory listing might suggest.

### 2.2 Binance Vision Monthly Kline Availability

Verified via S3 directory listing of `data.binance.vision`:

**1h timeframe — UM futures monthly klines:**

| Month | File | Size (bytes) |
| --- | --- | --- |
| 2019-09 | ETHUSDT-1h-2019-09.zip | 9,677 |
| 2019-10 | ETHUSDT-1h-2019-10.zip | 35,547 |
| 2019-11 | ETHUSDT-1h-2019-11.zip | 34,432 |
| 2019-12 | ETHUSDT-1h-2019-12.zip | 35,538 |
| 2020-01 | ETHUSDT-1h-2020-01.zip | 34,622 |
| 2020-02 | ETHUSDT-1h-2020-02.zip | 32,640 |
| 2020-03 | ETHUSDT-1h-2020-03.zip | 35,672 |
| 2020-04 | ETHUSDT-1h-2020-04.zip | 34,627 |
| 2020-05 | ETHUSDT-1h-2020-05.zip | 35,540 |
| 2020-06 | ETHUSDT-1h-2020-06.zip | 34,624 |
| 2020-07 | ETHUSDT-1h-2020-07.zip | 35,540 |
| 2020-08 | ETHUSDT-1h-2020-08.zip | 35,540 |
| 2020-09 | ETHUSDT-1h-2020-09.zip | 34,624 |
| 2020-10 | ETHUSDT-1h-2020-10.zip | 35,540 |
| 2020-11 | ETHUSDT-1h-2020-11.zip | 34,624 |
| 2020-12 | ETHUSDT-1h-2020-12.zip | 35,540 |

**4h timeframe — UM futures monthly klines:**

| Month | File | Size (bytes) |
| --- | --- | --- |
| 2019-09 | ETHUSDT-4h-2019-09.zip | 2,421 |
| 2019-10 | ETHUSDT-4h-2019-10.zip | 8,895 |
| 2019-11 | ETHUSDT-4h-2019-11.zip | 8,616 |
| 2019-12 | ETHUSDT-4h-2019-12.zip | 8,886 |
| 2020-01 | ETHUSDT-4h-2020-01.zip | 8,663 |
| 2020-02 | ETHUSDT-4h-2020-02.zip | 8,162 |
| 2020-03 | ETHUSDT-4h-2020-03.zip | 8,921 |
| 2020-04 | ETHUSDT-4h-2020-04.zip | 8,663 |
| 2020-05 | ETHUSDT-4h-2020-05.zip | 8,886 |
| 2020-06 | ETHUSDT-4h-2020-06.zip | 8,663 |
| 2020-07 | ETHUSDT-4h-2020-07.zip | 8,886 |
| 2020-08 | ETHUSDT-4h-2020-08.zip | 8,886 |
| 2020-09 | ETHUSDT-4h-2020-09.zip | 8,663 |
| 2020-10 | ETHUSDT-4h-2020-10.zip | 8,886 |
| 2020-11 | ETHUSDT-4h-2020-11.zip | 8,663 |
| 2020-12 | ETHUSDT-4h-2020-12.zip | 8,886 |

### 2.3 Source-level Observations

1. **File sizes are consistent and non-trivial.** 1h files range 9.6K–35.7K;
   4h files range 2.4K–8.9K. These sizes are consistent with real OHLCV data
   (not empty placeholders).

2. **2019-09 is a partial month** (contract launched 2019-09-25). The smaller
   file sizes for 2019-09 (9.7K for 1h, 2.4K for 4h) are consistent with
   approximately 5 days of data.

3. **Full months available for 2019-10 through 2020-12.** 16 full months plus
   one partial month = approximately 16.5 months of pre-2021 data.

4. **Size consistency across months.** 2020 monthly 1h files are 32.6K–35.7K,
   comparable to 2021 monthly files (~35–40K). This suggests similar data
   density and quality.

5. **Spot data also exists** on Binance Vision for the same period, but this
   report focuses on USDT-M futures data as that is what the system uses.

### 2.4 Layer 1 Conclusion

**Source-level availability is CONFIRMED with HIGH confidence.**

Binance Vision provides ETHUSDT UM futures monthly klines for 1h and 4h from
2019-09 (contract launch) through 2020-12. This is 16+ months of pre-2021 data,
significantly more than the 4-month window (2020-09~2020-12) assumed in TE-003.

---

## 3. Layer 2 — Local Imported Availability

### 3.1 Database Query Results

Local database: SQLite at `data/v3_dev.db`

**Pre-2021 data (timestamp < 1609459200000 = 2021-01-01 00:00:00 UTC):**

```
Result: ZERO rows for any symbol/timeframe combination.
```

No pre-2021 kline data exists in the local database for any symbol.

**Existing ETH/USDT:USDT data boundaries:**

| Timeframe | Count | First Timestamp | Last Timestamp | Span (days) |
| --- | --- | --- | --- | --- |
| 1h | 46,284 | 2021-01-01 00:00:00 | 2026-05-07 ~08:00 | ~1,953 |
| 4h | 11,571 | 2021-01-01 00:00:00 | 2026-05-07 ~08:00 | ~1,953 |

### 3.2 Layer 2 Conclusion

**Local imported availability is NOT CONFIRMED.**

No pre-2021 ETH/USDT:USDT 1h or 4h data exists in the local database. Import
is required before any QA or strategy work can proceed.

---

## 4. Layer 3 — QA-passed Readiness

**NOT ASSESSABLE.** Cannot execute QA checks without local data.

The QA specification defined in TE-004 Section 5 is ready for execution if
Owner separately authorizes data import and QA execution.

---

## 5. Revised Pre-2021 Data Window Assessment

### 5.1 TE-003 vs TE-004 Comparison

| Dimension | TE-003 Assessment | TE-004 Finding |
| --- | --- | --- |
| Source availability start | 2020-09 (medium confidence) | 2019-09 (high confidence) |
| Source availability end | 2020-12 | 2020-12 (unchanged) |
| Pre-2021 window size | ~4 months | ~16.5 months |
| Confidence | Medium | High (verified via S3 listing + Binance API) |
| Local data | Not confirmed | Confirmed absent |
| Contract launch | Not verified | 2019-09-25 (Binance API verified) |

### 5.2 Implications for Supplemental Window Classification

TE-004 task card Section 6 classified a 4-month window (2020-09~2020-12) as
"supplemental diagnostic window only." With the revised window of ~16.5 months
(2019-09~2020-12), the classification should be reconsidered:

- 16.5 months is substantially more than 4 months and could provide meaningful
  additional trend-cycle coverage.
- However, 2019-09 through 2020-08 is early-market behavior (first year of
  Binance USDT-M futures). Market microstructure may differ from 2021-2025.
- The 2020 period includes the COVID crash (March 2020) and the DeFi summer
  (June-September 2020), which are structurally distinct market regimes.

**Revised recommendation:** If imported and QA-passed, the 2019-09~2020-12
window should still default to **supplemental diagnostic window** per TE-004
Section 6, but the Owner may consider upgrading its classification given the
larger window size. This is an Owner decision, not a TE-004 conclusion.

---

## 6. Expected Data Volume (if Imported)

Based on source-level file sizes and contract launch date:

| Timeframe | Period | Estimated Candle Count | Notes |
| --- | --- | --- | --- |
| 1h | 2019-09-25 ~ 2020-12-31 | ~11,800 | ~490 days × 24 candles/day |
| 4h | 2019-09-25 ~ 2020-12-31 | ~2,940 | ~490 days × 6 candles/day |

These estimates assume 24/7 continuous trading with no gaps. Actual counts
may be lower due to exchange maintenance or early-market low liquidity periods.

---

## 7. Indicator Warmup Implications

Per TE-004 task card Section 5.9:

| Indicator | Warmup Period | Implication |
| --- | --- | --- |
| EMA60 (4h) | 60 × 4h = 10 days | First evaluable signal ~10 days after data start |
| Donchian20 (4h) | 20 × 4h ≈ 3.3 days | Subsumed by EMA60 warmup |
| Combined | 10 days | If data starts 2019-09-25, first signal ~2019-10-05 |

With the revised window starting 2019-09-25, the effective evaluable window
(after warmup) would be approximately:

- **Start:** ~2019-10-05
- **End:** 2020-12-31
- **Effective span:** ~15.2 months

---

## 8. Stop Conditions Encountered

| Condition | Status | Action |
| --- | --- | --- |
| Pre-2021 data not found locally | **TRIGGERED** | Documented in Section 3. Import requires Owner authorization. |
| Need to download data from Binance Vision | **WOULD BE NEEDED** | Not executed. Requires Owner authorization. |
| Need to import data into local DB | **WOULD BE NEEDED** | Not executed. Requires Owner authorization. |

TE-004 stops at Layer 2. Layer 3 (QA execution) requires Owner to separately
authorize data download, import, and QA execution.

---

## 9. Scope Guard Confirmation

- [x] No data was downloaded from Binance Vision or any external source.
- [x] No data was imported into the local database.
- [x] No database writes were executed.
- [x] No strategy logic was executed against any data.
- [x] No Direction A or B-D1 logic was run.
- [x] No extended backtest was run.
- [x] No parameter sweep was conducted.
- [x] No code outside `docs/ops/te-004-*` was modified.
- [x] No promotion or validation readiness conclusion was made beyond data
      availability status.
- [x] This report does not authorize strategy experiments, extended backtests,
      data import, or promotion decisions.
- [x] There is no deployable small-live strategy candidate. Small-live
      readiness gate remains unmet.

---

## 10. Recommendation

**Proceed to data acquisition planning.**

TE-004 confirms that 16+ months of pre-2021 ETHUSDT 1h/4h data is available at
the source level (Binance Vision). This is a significant upgrade from TE-003's
4-month estimate.

Next steps require Owner decision:

1. **Option A — Import and QA:** Authorize download of 2019-09~2020-12 monthly
   kline ZIP files from Binance Vision, import into local database, and execute
   QA checks per TE-004 task card Section 5. This requires Level 2+ authorization
   (data download + import + read-write DB queries).

2. **Option B — Defer:** Defer pre-2021 data acquisition. Continue with the
   current 2021-2025 confirmed window. Revisit if Direction A or B-D1 evidence
   strengthens to the point where longer-window validation becomes a priority.

3. **Option C — Partial import:** Import only 2020-06~2020-12 (post-COVID-crash
   period, 7 months) as a focused supplemental window. This avoids early-market
   microstructure concerns while still adding meaningful coverage.

**TE-004 does not recommend a specific option.** That is an Owner decision.

---

## 11. TE-003 Correction Note

TE-003 stated:

> "Binance Vision source-level availability: 2020-09 onward (medium confidence,
> source-doc claim only)"

TE-004 corrects this to:

> "Binance Vision source-level availability: 2019-09 onward (high confidence,
> verified via S3 directory listing + Binance API contract launch date)"

This correction does not change TE-003's conclusion that local data readiness
is `DATA_NOT_CONFIRMED`. It only upgrades the source-level availability
assessment.

---

## 12. Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-07 | Initial TE-004 coverage/QA report created | Codex |
