# Direction A — Cross-Asset Data Coverage Audit

**Status:** Docs/report-only data coverage audit
**Classification:** READINESS_AUDIT_ONLY
**Date:** 2026-05-08
**Authorization Level:** Level 1/2 — docs-only read-only DB queries
**Source:** Direction A cross-asset transfer diagnostic plan (Section 4, 10)
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document is a read-only data coverage audit for the Direction A
cross-asset transfer diagnostic plan.

It is not:

- a backtest;
- a strategy experiment;
- a data import or fetch;
- a data pipeline creation;
- a schema change;
- a database mutation;
- Direction A rescue or variant;
- runtime or small-live admission;
- promotion;
- any authorization for empirical execution.

This audit read-only-queries the local SQLite database (`data/v3_dev.db`) and
existing docs. It does not write to, fetch from, or modify any database.

---

## 1. Executive Summary

| Asset | Base Window (2021–2025) | Supplemental (2020) | Data Quality | Classification |
| --- | --- | --- | --- | --- |
| ETH/USDT:USDT | 10956/10956 bars (100.0%) | 2196/2196 bars (100%) | Clean | `DATA_READY_FULL_BASE_WINDOW` (reference) |
| BTC/USDT:USDT | 10956/10956 bars (100.0%) | 0/2196 bars (0%) | Clean | `DATA_READY_FULL_BASE_WINDOW` |
| SOL/USDT:USDT | 10926/10956 bars (99.7%) | 0/2196 bars (0%) | Clean; 30 bars missing in 2022 (2 gaps) | `DATA_READY_ADJUSTED_WINDOW` |

**Overall diagnostic readiness:** `READY_FOR_OWNER_APPROVED_CROSS_ASSET_DIAGNOSTIC`

**Key finding:** BTC has 100% base window coverage with no gaps. SOL has
99.7% base window coverage with 30 missing bars across two known gaps in
2022 (5 calendar days total). All data passes OHLCV quality checks. The
base window (2021-01-01 to 2025-12-31) is fully served by the local
database for both target assets. No data fetch or import is needed for the
base window diagnostic.

**This audit does not authorize the diagnostic execution.** The Owner must
separately approve the frozen cross-asset diagnostic.

---

## 2. Symbol Configuration

### 2.1 Config Source

Symbols are configured in:

- `src/application/config/config_parser.py` (default fallback):
  `core_symbols=["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"]`
- `data/config.db` → `symbols` table:
  All four symbols are `is_core=1, is_active=1`.

### 2.2 Configuration Verification

| Check | Result |
| --- | --- |
| BTC/USDT:USDT configured | Yes — core, active |
| ETH/USDT:USDT configured | Yes — core, active |
| SOL/USDT:USDT configured | Yes — core, active |
| BNB/USDT:USDT configured | Yes — core, active (not in scope) |
| 4h timeframe supported | Yes — `TIMEFRAME_MINUTES["4h"] = 240` in `historical_data_repository.py` |
| Perpetual futures consistent | Yes — all use `USDT:USDT` (USDT-margined perpetual) naming convention |
| No spot/perp mixing | Confirmed — all symbols use the `:USDT` perp suffix |

### 2.3 Symbol Naming Consistency

Local DB queries confirmed no symbol variants. Each asset has exactly one
symbol name in the klines table:

- `BTC/USDT:USDT` (no `BTCUSDT`, `BTC/USDT`, or other variants)
- `ETH/USDT:USDT`
- `SOL/USDT:USDT`

---

## 3. Local DB Coverage

### 3.1 Database Metadata

| Property | Value |
| --- | --- |
| Database file | `data/v3_dev.db` |
| Database size | 191.1 MB |
| Integrity check | `ok` (PRAGMA integrity_check passed) |
| Kline table | `klines` (indexed on `(symbol, timeframe, timestamp)`) |
| OHLC storage type | VARCHAR(32) — text; numeric comparison requires CAST |
| Backend routing | SQLite (default); PG used only if `PG_DATABASE_URL` env var is set |

### 3.2 ETH/USDT:USDT 4h Coverage (Reference)

| Property | Value |
| --- | --- |
| Earliest bar | 2020-01-01 00:00 UTC |
| Latest bar | 2026-03-31 20:00 UTC |
| Total bars | 13,692 |
| 2021–2025 base bars | 10,956 / 10,956 (100.0%) |
| 2020 supplemental bars | 2,196 / 2,196 (100%) |
| Post-2025 bars | 540 (2026-01-01 to 2026-03-31, outside base window) |

| Year | Bars | Expected | Status |
| --- | --- | --- | --- |
| 2021 | 2,190 | 2,190 | Full |
| 2022 | 2,190 | 2,190 | Full |
| 2023 | 2,190 | 2,190 | Full |
| 2024 | 2,196 | 2,196 | Full |
| 2025 | 2,190 | 2,190 | Full |

**ETH classification:** `DATA_READY_FULL_BASE_WINDOW` — complete base window
plus full 2020 supplemental window. No data fetch needed. Warmup bars
available from 2020-01-01 (12 months before base window start).

### 3.3 BTC/USDT:USDT 4h Coverage (Target 1)

| Property | Value |
| --- | --- |
| Earliest bar | 2021-01-01 00:00 UTC |
| Latest bar | 2026-03-31 20:00 UTC |
| Total bars | 11,496 |
| 2021–2025 base bars | 10,956 / 10,956 (100.0%) |
| 2020 supplemental bars | 0 / 2,196 (0%) |
| Post-2025 bars | 540 (2026-01-01 to 2026-03-31, outside base window) |

| Year | Bars | Expected | Status |
| --- | --- | --- | --- |
| 2021 | 2,190 | 2,190 | Full |
| 2022 | 2,190 | 2,190 | Full |
| 2023 | 2,190 | 2,190 | Full |
| 2024 | 2,196 | 2,196 | Full |
| 2025 | 2,190 | 2,190 | Full |

**BTC classification:** `DATA_READY_FULL_BASE_WINDOW` — complete base window
with zero gaps. No data fetch needed for base window.

**Supplemental note:** BTC has no 2020 data in the local database. The
BTCUSDT perpetual contract has been trading since ~2019-09 (Binance
futures launch), so source-level 2020 data is expected to be available
via Binance Vision. However, it was never imported locally. If the
Owner wants a BTC supplemental window, separate data import approval
would be required.

### 3.4 SOL/USDT:USDT 4h Coverage (Target 2)

| Property | Value |
| --- | --- |
| Earliest bar | 2021-01-01 00:00 UTC |
| Latest bar | 2026-03-31 20:00 UTC |
| Total bars | 11,466 |
| 2021–2025 base bars | 10,926 / 10,956 (99.7%) |
| 2020 supplemental bars | 0 / 2,196 (0%) |
| Post-2025 bars | 540 (2026-01-01 to 2026-03-31, outside base window) |
| Missing base bars | 30 (all in 2022) |

| Year | Bars | Expected | Status |
| --- | --- | --- | --- |
| 2021 | 2,190 | 2,190 | Full |
| 2022 | 2,160 | 2,190 | **Missing 30 bars** |
| 2023 | 2,190 | 2,190 | Full |
| 2024 | 2,196 | 2,196 | Full |
| 2025 | 2,190 | 2,190 | Full |

**SOL classification:** `DATA_READY_ADJUSTED_WINDOW` — base window is 99.7%
complete with known gaps. See gap analysis below.

---

## 4. SOL Gap Analysis

### 4.1 Gap Locations

| Gap # | Start | End | Missing Bars | Duration |
| --- | --- | --- | --- | --- |
| 1 | 2022-02-25 20:00 UTC | 2022-03-01 00:00 UTC | 18 bars | 3.0 days |
| 2 | 2022-03-31 20:00 UTC | 2022-04-03 00:00 UTC | 12 bars | 2.0 days |
| **Total** | | | **30 bars** | **5.0 days** |

### 4.2 Gap Characterization

- **Gap 1 (Feb 25 – Mar 1, 2022):** 18 missing 4h bars. This is a 3-day
  contiguous gap during a period of high SOL volatility (early 2022 market
  turbulence). Likely caused by Binance data unavailability or SOL perp
  contract maintenance.

- **Gap 2 (Mar 31 – Apr 3, 2022):** 12 missing 4h bars. This is a 2-day
  contiguous gap at the end of March / start of April 2022. Likely similar
  cause.

### 4.3 Gap Impact Assessment

- **Total gap: 30 bars out of 2,190 expected for 2022 = 1.4% of 2022.**
- **Total gap: 30 bars out of 10,956 expected for full base window = 0.27%.**
- The gaps are contiguous (not scattered), which means the backtest can run
  cleanly on the available data — it simply has 5 fewer calendar days of
  exposure in 2022.
- The Direction A frozen rule does not depend on continuous data for a
  specific date. Missing bars result in no signal being generated during the
  gap, not in incorrect signals. This is structurally safe.
- The gaps do not fall on known Direction A top-winner or top-loser trade
  dates (top winners span 2021-Q1, 2023-Q1, 2024-Q1, 2025-Q3 per
  DIRA-EH-001). However, SOL top winners are not yet known (not yet
  computed).
- **No data repair is required.** The diagnostic can proceed on 10,926
  bars. The SOL-valid window is 2021-01-01 to 2025-12-31 with 99.7%
  coverage.

---

## 5. Warmup Sufficiency

Direction A requires:

- Donchian20: 20 × 4h = 80h warmup
- EMA60: 60 × 4h = 240h warmup
- Combined: 60 × 4h = 240h (10 calendar days) from first available bar

| Asset | First Bar | Warmup Complete | Before 2021-01-01? | First Valid Signal |
| --- | --- | --- | --- | --- |
| ETH | 2020-01-01 | 2020-01-11 | Yes | 2021-01-01 (warmup fully before base window) |
| BTC | 2021-01-01 | 2021-01-11 | No | ~2021-01-11 (first 10 days have incomplete warmup) |
| SOL | 2021-01-01 | 2021-01-11 | No | ~2021-01-11 (first 10 days have incomplete warmup) |

**BTC/SOL warmup impact:** The first 10 days of 2021 (240h / 60 bars) will
have an incomplete EMA60. This affects at most 2–3 potential signals at the
very start of the base window. The directional impact is negligible: these
bars are only 0.09% of the 10,956-bar base window. The diagnostic should
start recording trades from the first bar where the EMA60 is fully warmed up
(~2021-01-11). This is standard practice and not a data defect.

---

## 6. Data Quality Checks

### 6.1 OHLCV Integrity

| Check | ETH | BTC | SOL |
| --- | --- | --- | --- |
| Duplicate timestamps | 0 | 0 | 0 |
| Zero/negative OHLC (numeric) | 0 | 0 | 0 |
| high < low (numeric) | 0 | 0 | 0 |
| open/close outside [low, high] (numeric) | 0 | 0 | 0 |
| Zero/null/negative volume | 0 | 0 | 0 |

Note: Initial text-based comparison flagged false positives due to OHLC
columns being stored as VARCHAR(32). Numeric CAST comparison confirms zero
actual anomalies.

### 6.2 Timezone Consistency

All timestamps are UTC milliseconds. The `HistoricalDataRepository` stores
timestamps as integer milliseconds from Unix epoch. No timezone conversion
ambiguity exists.

### 6.3 Data Source Consistency

All local data was imported from Binance kline API or Binance Vision
historical downloads. The ETH 2020 data was imported via TE-005 downloads
from `data.binance.vision`. BTC and SOL 2021+ data was imported via the
exchange gateway (`ExchangeGateway.fetch_historical_ohlcv`). All three
assets use the same USDT-margined perpetual contract feed.

---

## 7. Repository / Fetch Behavior

### 7.1 How HistoricalDataRepository Works

The `HistoricalDataRepository` (and its PG variant `PgHistoricalDataRepository`)
implements a local-first data access strategy:

1. Query local SQLite (or PG) for klines in the requested time range.
2. If local data is insufficient and an `ExchangeGateway` is configured,
   automatically fetch from the exchange to fill gaps.
3. Fetched data is saved to the local DB (idempotent INSERT OR IGNORE).

**Critical behavior for this audit:**

- When called with a specific time range and limit, the repository checks
  whether the returned count is less than the limit. If so, and an exchange
  gateway is present, it fetches from the exchange.
- This means that even if local data has gaps, the repository CAN fill them
  automatically during a backtest run — but only if an `ExchangeGateway`
  instance is provided to the repository constructor.

### 7.2 Implications for the Diagnostic

- **BTC base window:** 100% local coverage. No exchange fetch needed.
- **SOL base window:** 99.7% local coverage. The 30 missing bars in 2022
  could be auto-filled by the repository if an exchange gateway is provided
  during diagnostic execution. Alternatively, the diagnostic can simply run
  on the available 10,926 bars without repair.
- **No data fetch is authorized by this audit.** If the Owner wants the 30
  missing SOL bars filled, that requires separate approval. The diagnostic
  is valid either way (with or without the 30 bars).

### 7.3 Database Mutation Risk

The repository uses `INSERT OR IGNORE` (SQLite) or `ON CONFLICT DO NOTHING`
(PostgreSQL) for saves, making it idempotent. Any auto-fetch during a
backtest would write fetched bars to the local DB. This is a data mutation
and requires Owner awareness.

**Recommendation:** Run the SOL diagnostic on the existing 10,926 bars
without auto-fetch. The 30-bar gap is too small to materially affect the
diagnostic, and avoiding data mutation keeps this audit clean.

---

## 8. Readiness Classification

### 8.1 Per-Asset Classification

| Asset | Classification | Rationale |
| --- | --- | --- |
| ETH/USDT:USDT | `DATA_READY_FULL_BASE_WINDOW` | 100% base window + 100% supplemental. Reference only; no re-execution. |
| BTC/USDT:USDT | `DATA_READY_FULL_BASE_WINDOW` | 100% base window (10,956/10,956 bars). Zero gaps. No fetch needed. |
| SOL/USDT:USDT | `DATA_READY_ADJUSTED_WINDOW` | 99.7% base window (10,926/10,956 bars). Two gaps in 2022 totaling 30 bars / 5 days. Diagnostic valid on available data. |

### 8.2 Overall Diagnostic Readiness

**Classification: `READY_FOR_OWNER_APPROVED_CROSS_ASSET_DIAGNOSTIC`**

Rationale:

- BTC has 100% base window coverage with zero gaps — fully ready.
- SOL has 99.7% base window coverage — 30 missing bars in 2022 (5 calendar
  days, 1.4% of 2022) do not prevent a meaningful diagnostic. The diagnostic
  is valid on 10,926 bars.
- All OHLCV data passes quality checks (zero anomalies).
- Symbol configuration is correct for all three assets (core, active,
  perpetual, USDT-margined).
- Warmup requirements are satisfied (BTC/SOL first valid signal ~2021-01-11,
  which is 10 days into the base window — negligible impact).
- The local DB can serve all required 4h klines without exchange fetch.
- DB integrity check passes.

### 8.3 Supplemental Window Availability

| Asset | 2020 Supplemental | Available? | Notes |
| --- | --- | --- | --- |
| ETH | Full (2,196 bars) | Yes | Imported via TE-005 Binance Vision downloads |
| BTC | None (0 bars) | No | Source-level data expected to exist on Binance Vision but not imported locally |
| SOL | None (0 bars) | No | SOLUSDT perp launched ~2020-Q4; limited source-level availability for full 2020 |

The supplemental window is optional per the diagnostic plan. The base
window (2021–2025) is the primary diagnostic target. BTC supplemental
would require separate data import approval.

### 8.4 Upgrade Path

| Current Classification | Upgrade To | Condition |
| --- | --- | --- |
| `READY_FOR_OWNER_APPROVED_CROSS_ASSET_DIAGNOSTIC` | Diagnostic execution begins | Owner approves execution + SRR-002 compliance |

No data repair or fetch is required to reach readiness. The Owner may
optionally approve filling the 30 SOL bars for completeness, but this is
not a prerequisite.

---

## 9. Execution Gate

This audit establishes data readiness only. It explicitly does **not**
authorize:

1. **Direction A backtest execution.** The diagnostic must be separately
   approved by the Owner.
2. **Data fetch or import.** No exchange fetch, Binance Vision download,
   or data pipeline work is authorized by this audit.
3. **Database mutation.** No writes to `v3_dev.db`, PG, or any other
   database are authorized by this audit.
4. **Strategy execution or signal generation.** No trading signals,
   positions, or orders may be created.
5. **Runtime, small-live, or deployment use.** Data readiness does not
   imply strategy readiness.

Even if data is fully ready, the frozen cross-asset diagnostic requires
separate Owner approval and SRR-002 compliance before any empirical run.

---

## 10. Data Gap Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| SOL 2022 gaps miss a Direction A signal | Low (5 days out of 365) | Low (at most 1–2 signals lost) | Accept as-is; 99.7% coverage is sufficient for mechanism validation |
| BTC/SOL data has undetected quality issue | Very Low (all OHLCV checks pass) | Medium | Diagnostic report will include per-trade OHLCV inspection |
| Warmup period affects first signals | Negligible (10 days, 0.09% of window) | Negligible | Start recording trades from 2021-01-11 |
| Data source inconsistency between assets | Low (all Binance perp) | Medium | All use USDT-margined perpetual; same exchange, same data format |
| Future data revision changes results | Very Low | Low | Binance Vision historical data is immutable |

---

## 11. Summary

### 11.1 Data is ready for the base window diagnostic

- BTC: 10,956/10,956 bars (100%) — zero gaps — `DATA_READY_FULL_BASE_WINDOW`
- SOL: 10,926/10,956 bars (99.7%) — two gaps, 30 bars total —
  `DATA_READY_ADJUSTED_WINDOW`
- ETH reference: 10,956/10,956 bars (100%) — not re-executed

### 11.2 Supplemental window is not ready for BTC/SOL

- BTC 2020: source-level data likely available on Binance Vision; not
  imported locally; would require separate approval
- SOL 2020: limited source availability; not a priority

### 11.3 No data repair needed

The 30 missing SOL bars in 2022 (5 calendar days) are too small to
materially affect the diagnostic. The diagnostic is valid on available data.
Optional: Owner may approve filling the gaps for completeness.

### 11.4 Next step

Owner approval for frozen cross-asset diagnostic execution. No data work
required as a prerequisite.

---

> **Direction A cross-asset data coverage audit is readiness-only. This audit
> does not authorize Direction A backtests, strategy execution, data import,
> per-asset optimization, runtime use, small-live use, or strategy rescue. Any
> empirical cross-asset diagnostic requires separate Owner approval and must
> satisfy SRR-002.**

---

## Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-08 | Initial cross-asset data coverage audit | Claude |
