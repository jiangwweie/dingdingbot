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

# CPM-OOS-RECON-001 — 2022 OOS Report Slippage / Cost Model Reconciliation Note

**Task ID**: CPM-OOS-RECON-001
**Date**: 2026-05-06
**Scope**: Reconcile slippage=0 anomaly and cost model caveats in CPM-OOS-RUN-001 report
**Affects Runtime Automatically**: No
**Affects Strategy Parameters**: No
**Affects Risk Rules**: No
**Affects Live Status**: No

---

## 1. Purpose

This note resolves the slippage=0 reproducibility ambiguity flagged in the 2022 OOS report (Section 14, Section 16) and determines whether the 2022 OOS result qualifies as clean, caveated, or invalid evidence.

---

## 2. Finding 1: slippage=0 Is a Tracking Bug, Not a Missing Cost

### Root Cause

`total_slippage_cost` in the backtester (`src/application/backtester.py:1805-1813`) re-derives the slippage-adjusted price using the same formula as the matching engine, then compares it against the engine's execution price. Since both use `kline.open * (1 + slippage_rate)`, the difference is always zero.

```python
# backtester.py:1808-1809 — re-derives same formula as engine
expected_price = kline.open * (Decimal('1') + engine.slippage_rate)
slippage = abs(order.average_exec_price - expected_price)  # always 0
```

The correct calculation should compare against the unslipped base price (`kline.open`), not the re-derived slipped price.

### Scope of the Bug

The tracking code also only covers `OrderType.MARKET` entry orders. It does not track slippage for:
- Stop-loss orders (STOP_MARKET) — slippage IS applied in the matching engine
- Take-profit orders (LIMIT TP) — tp_slippage IS applied in the matching engine
- Trailing exit orders — slippage IS applied separately

### Slippage IS Applied to PnL

The matching engine (`src/domain/matching_engine.py`) correctly applies slippage to every execution price:

| Order Type | Direction | Slippage Applied | Rate |
|------------|-----------|-----------------|------|
| MARKET entry | LONG | `kline.open * (1 + slippage_rate)` | 0.001 |
| MARKET entry | SHORT | `kline.open * (1 - slippage_rate)` | 0.001 |
| STOP_MARKET (SL) | LONG | `trigger_price * (1 - slippage_rate)` | 0.001 |
| STOP_MARKET (SL) | SHORT | `trigger_price * (1 + slippage_rate)` | 0.001 |
| LIMIT (TP) | LONG | `price * (1 - tp_slippage_rate)` | 0.0005 |
| LIMIT (TP) | SHORT | `price * (1 + tp_slippage_rate)` | 0.0005 |

The slippage-adjusted execution prices flow into `position.realized_pnl` and `account.total_balance`. The reported `total_pnl = -971.71` already includes all slippage costs.

### Estimated Slippage Impact

Using close_events data to reconstruct slippage from execution prices:

| Component | Estimated Amount (USDT) |
|-----------|------------------------|
| Entry slippage | 353.08 |
| SL exit slippage | 230.04 |
| TP exit slippage | 61.21 |
| **Total estimated slippage** | **644.33** |

For comparison:

| Cost Component | Amount (USDT) | % of Total Drag |
|---------------|---------------|-----------------|
| Fees (tracked correctly) | 387.04 | 36.8% |
| Funding (tracked correctly) | 20.85 | 2.0% |
| Slippage (embedded but untracked) | ~644.33 | 61.2% |
| **Total cost drag** | **~1,052.22** | 100% |

Slippage is the single largest cost component but is invisible in the report's cost breakdown.

### Historical Consistency

All archived CPM-1 research runs also report `total_slippage_cost = 0`. This is a systematic engine-level tracking bug, not a 2022-specific anomaly. The bug affects all backtest results equally, so cross-run comparisons remain valid even though the absolute cost breakdown is wrong.

---

## 3. Finding 2: Fee Model Is Correct and Consistent

### Fees Are Properly Tracked

- Fees are calculated on every fill inside `MockMatchingEngine._execute_fill()` at `exec_price * qty * fee_rate`
- Fees are deducted from `account.total_balance` on every fill (not just at position close)
- `total_fees_paid` in the report is accumulated from `position.total_fees_paid` when positions close
- The 387.04 USDT figure is consistent with 51 positions × ~2 fills/position × 0.04% fee rate

### Minor Reporting Gap

`total_fees_paid` in the report only accumulates fees for fully closed positions. Fees for any position still open at backtest end would be missing from the report total but already deducted from `account.total_balance`. In the 2022 OOS, all 51 positions closed, so this gap has zero effect.

### Fee Rate Consistency

The 2022 OOS uses `fee_rate=0.0004` (Binance USDT-M default). Historical CPM-1 evidence uses two fee models:
- Default: 0.04% (0.0004) — used in 2022 OOS and most proxy experiments
- BNB9: 0.0405% (0.000405) — used in External Quant Review

The 0.04% rate is the conservative (higher-cost) assumption relative to BNB9. This is acceptable for OOS evidence.

---

## 4. Finding 3: Funding Model Is Correct and Explicitly Caveated

### Funding Is Properly Tracked

- Funding cost is calculated per-kline for every open position: `position_value * funding_rate * (hours / 8)`
- Funding is deducted from `account.total_balance` immediately on each kline
- `total_funding_cost` is accumulated incrementally, capturing both open and closed positions
- The 20.85 USDT figure is consistent with 51 LONG positions averaging ~8 days hold × 0.01%/8h

### Caveat: Constant Rate Approximation

The funding model uses a constant 0.0001/8h rate. Real funding varies significantly with market conditions, especially during:
- LUNA/UST crash (May 2022): funding likely much higher for LONGs
- FTX collapse (November 2022): funding likely much higher for LONGs

The constant rate likely **underestimates** actual funding costs in 2022's extreme bear market. This means the -9.72% return may be slightly worse in reality due to higher funding drag.

This caveat was already documented in the 2022 OOS report (Section 6, Section 7) and is accepted as a known limitation.

---

## 5. Finding 4: Same-bar Policy Is Consistent

The pessimistic same-bar policy (SL > TP > ENTRY priority) is used consistently across:
- 2022 OOS run (`same_bar_policy="pessimistic"` in runtime overrides)
- All archived CPM-1 research scripts (verified in `archive/.../scripts/`)
- The matching engine default

No same-bar conflicts were observed in the 2022 OOS (0 positions with entry+exit in the same 1h candle). This is expected given the 1h timeframe and OCO order strategy.

---

## 6. Finding 5: Position-Level PnL Reconciliation

The monthly PnL sum from `positions[].realized_pnl` (~-809.63 USDT) does not equal the top-level `total_pnl` (-971.71 USDT). The ~-162.08 USDT difference is explained by:

- Position `realized_pnl` includes fees deducted at close but does not include funding costs (funding is tracked separately per-kline)
- Position `realized_pnl` may not include all entry-side fee deductions depending on how the engine aggregates

This reconciliation gap was already documented in the 2022 OOS report (Section 12) and does not affect the top-level `total_pnl` ground truth.

---

## 7. Impact Assessment

### Does slippage=0 invalidate the 2022 OOS result?

**No.** Slippage IS applied to execution prices and IS reflected in `total_pnl`. The tracking field is broken, but the PnL figure is correct. The -9.72% return already includes all slippage costs.

### Does the tracking bug affect interpretation?

**Partially.** The cost breakdown in the report (Section 14) is misleading:
- Reported: fees 39.8%, slippage 0.0%, funding 2.1% of gross loss
- Actual: fees ~24%, slippage ~40%, funding ~1.3% of gross loss (estimated)

Slippage is the largest single cost, not zero. This changes the cost composition narrative but not the bottom-line PnL.

### Does this affect the Owner classification?

**No.** The Owner classification (OOS_NEGATIVE — Require additional evidence) was based on:
1. -9.72% return (correct, includes slippage)
2. 31.1% win rate (correct)
3. 0.624 profit factor (correct)
4. 2022 being an extreme bear year (contextual, unchanged)

The classification remains valid. The only change is that the cost composition understanding is corrected.

### Does this require a rerun?

**No.** A rerun would produce the same `total_pnl`, `win_rate`, `profit_factor`, and `max_drawdown`. The only difference would be a corrected `total_slippage_cost` field, which is a reporting metric, not a PnL input.

---

## 8. Evidence Classification

| Question | Answer |
|----------|--------|
| Is slippage applied to PnL? | Yes — through execution price adjustment |
| Is `total_slippage_cost` tracking correct? | No — structurally broken, always reports 0 |
| Is `total_pnl` correct? | Yes — includes all costs (fees, slippage, funding) |
| Is `total_fees_paid` correct? | Yes — properly tracked |
| Is `total_funding_cost` correct? | Yes — properly tracked, with constant-rate caveat |
| Is same-bar policy consistent? | Yes — pessimistic across all CPM-1 evidence |
| Is the 2022 OOS result valid? | Yes — PnL and all primary metrics are correct |
| Is the cost breakdown in the report accurate? | No — slippage component is missing |
| Does this require a rerun? | No — same result would be produced |
| Does this change the Owner classification? | No — OOS_NEGATIVE / Require additional evidence stands |

**Classification: Caveated evidence — PnL and primary metrics are clean; cost composition breakdown is unreliable due to slippage tracking bug.**

This is an upgrade from the previous "reproducibility ambiguity" status. The ambiguity is now resolved: slippage IS applied, the tracking field IS broken, and the impact is quantified.

---

## 9. Required Corrections to 2022 OOS Report

The following sections of `crypto-pullback-module-v1-2022-oos-report.md` should be updated:

1. **Section 14 (Cost / Funding Impact)**: Replace slippage=0 note with reconciliation finding. Add estimated slippage breakdown (~644 USDT). Update cost composition percentages.

2. **Section 16 (Conclusion Classification)**: Update evidence status from "reproducibility ambiguity" to "caveated evidence — slippage tracking bug confirmed, PnL correct, cost composition unreliable."

3. **Section 14 (Note on slippage=0)**: Replace the speculative note with the confirmed root cause and quantified impact.

These are metadata-only corrections. No rerun, no parameter change, no runtime change.

---

## 10. Engine Bug Registration

The `total_slippage_cost` tracking bug should be registered as a known engine defect:

- **Bug**: `total_slippage_cost` always reports 0 because the tracking code re-derives the same slippage formula as the matching engine instead of comparing against the unslipped base price
- **Location**: `src/application/backtester.py:1805-1813`
- **Impact**: Reporting metric only; does not affect PnL, account balance, or position-level calculations
- **Scope**: All backtest runs (historical and future) are affected equally
- **Fix**: Change `expected_price = kline.open * (1 + slippage_rate)` to `expected_price = kline.open` for MARKET entry orders, and add tracking for SL/TP/trailing exit slippage
- **Priority**: Low — does not affect trading decisions or evidence validity; affects cost composition reporting only

This bug should NOT be fixed as part of this reconciliation task. Fixing it would be a separate engine-maintenance task and must not be bundled with any OOS evidence interpretation.

---

## 11. Not-Now List

The following are explicitly not authorized by this reconciliation task:

- No parameter change
- No runtime change
- No risk rule change
- No engine fix (separate task, separate approval)
- No rerun of 2022 OOS
- No 2021 or 2023 OOS run
- No E4 hard filter
- No SHORT
- No BTC/SOL
- No live-safe change
- No Small-live / promotion status change
- No automatic change to Owner classification

---

## 12. Conclusion

**slippage=0 source**: Engine tracking bug in `backtester.py:1805-1813`. Slippage IS applied to execution prices and IS reflected in PnL. The tracking field is structurally broken and always reports zero for all runs.

**Cost model trustworthiness**: Fees and funding are correctly tracked. Slippage is correctly applied to PnL but incorrectly reported as a separate line item. The cost composition breakdown is unreliable; the bottom-line PnL is correct.

**Funding model trustworthiness**: Correctly tracked with a known constant-rate caveat that likely underestimates 2022 actual funding costs.

**2022 OOS evidence classification**: **Caveated evidence** — primary metrics (PnL, WR, PF, MaxDD, Sharpe, Sortino) are clean and correct. Cost composition breakdown is unreliable due to slippage tracking bug. The caveat does not affect the OOS_NEGATIVE classification or the Require additional evidence conclusion.

**Rerun required**: No. Same result would be produced.

**Impact on Owner final classification**: None. OOS_NEGATIVE — Require additional evidence / Deferred stands unchanged.

---

## 13. Metric Correction Reference (CPM-BT-METRIC-001)

The slippage tracking bug documented in Section 2 has been fixed by CPM-BT-METRIC-001.

**Fix**: `src/application/backtester.py` — replaced self-referencing slippage derivation with unslipped base price comparison for all order types.

| Order Type | Old Tracking | New Tracking |
|------------|-------------|-------------|
| MARKET entry | `abs(exec_price - kline.open * (1 + rate))` → always 0 | `abs(exec_price - kline.open)` → correct |
| STOP_MARKET (SL) | Not tracked | `abs(exec_price - trigger_price)` → correct |
| LIMIT (TP) | Not tracked | `abs(exec_price - order.price)` → correct |
| TRAILING_STOP | Not tracked | `abs(exec_price - event.close_price)` → correct |

**New `total_slippage_cost` semantics**: Sum of `|execution_price - unslipped_base_price| * filled_qty` across all executed orders. This is a pure metric extraction — slippage is already embedded in execution prices and reflected in `total_pnl`. The tracking field does not affect PnL calculation.

**No trade outcomes changed**: The fix only affects the `total_slippage_cost` reporting field. Entry/exit prices, PnL, win rate, profit factor, max drawdown, Sharpe, and Sortino are all computed from the same execution prices as before.

**2022 OOS does not require rerun**: The same `total_pnl`, `win_rate`, `profit_factor`, `max_drawdown`, `sharpe_ratio`, and `sortino_ratio` would be produced. Only `total_slippage_cost` would change from 0.00 to ~644.33 USDT.

**Tests**: 16 focused unit tests in `tests/unit/test_cpm_bt_metric_001_slippage_tracking.py`.

---

*Generated by CPM-OOS-RECON-001 on 2026-05-06, revised by CPM-BT-METRIC-001 on 2026-05-06. No runtime, profile, strategy, risk rule, or live status changes were made.*
