# TE-006B — Direction A Longer-window Supplemental Validation Execution Plan

**Task ID:** TE-006B
**Date:** 2026-05-07
**Status:** Proposed / Execution Plan Only
**Authorization Level:** Level 2 — docs-only execution plan
**Parent:** TE-006 Official Validation Readiness Plan

---

## 0. Boundary Statements

This document is an execution plan only. It does not authorize running
backtests, executing Direction A validation, modifying runtime/profile/risk/
backtester-core, implementing strategies, making promotion conclusions, making
small-live readiness conclusions, or giving live deployment advice.

TE-006B execution requires separate Owner approval (Level 3).

There is no deployable small-live strategy candidate. Small-live readiness gate
remains unmet.

---

## 1. Purpose

TE-006B defines how to execute Direction A longer-window supplemental validation
by re-running the frozen NSC-014 Direction A clean baseline rule against the
2019-2020 supplemental diagnostic window and producing a combined evidence
report.

This is the concrete execution plan that TE-006 Section 8 Option A and
TE-007A Section 9 reference. It specifies:

- Exact frozen rule to reuse
- Data windows and their authority
- Reproducible commands
- Required output metrics and report structure
- Acceptance criteria
- Stop conditions
- Prohibited actions
- Rollback / cleanup

---

## 2. Frozen Direction A Baseline Definition

The frozen rule is inherited verbatim from NSC-014 / NSC-013 / TE-007A Section 2:

| Rule | Specification |
| --- | --- |
| Entry signal | 4h Donchian20 breakout — fully closed 4h candle close > previous 20 closed 4h high; signal bar excluded from window |
| Entry execution | Next 4h bar open after signal candle closes, plus entry slippage |
| Initial stop | Lowest low of previous 20 closed 4h candles at entry time; signal bar excluded; stop remains active throughout trade |
| Trend lifecycle exit | Fully closed 4h candle close below EMA60; intrabar EMA60 touch does not trigger exit |
| Exit execution | Next 4h bar open after exit signal candle closes, less exit slippage |
| Stop vs EMA same-bar | Pessimistic documented ordering: stop checked first |
| Direction E / E-A | NOT INCLUDED |
| 1h entry timing | NOT INCLUDED |
| Trailing stop | NOT INCLUDED |
| Parameter sweep | NOT PERMITTED |

Frozen parameters:

| Parameter | Value |
| --- | --- |
| Donchian channel period | 20 (closed 4h candles) |
| EMA period | 60 (closed 4h candles) |
| Timeframe | 4h |
| Symbol | ETH/USDT:USDT |
| Entry timing | Next 4h open |
| Exit timing | Next 4h open |
| Initial stop lookback | 20 closed 4h candles |

Cost model (frozen, from CPM-1 OOS SSOT):

| Parameter | Value |
| --- | --- |
| fee_rate | 0.0004 |
| entry_slippage_rate | 0.001 |
| stop_or_ema_exit_slippage_rate | 0.001 |
| funding_enabled | True |
| funding_rate_per_8h | 0.0001 |

---

## 3. Data Windows

### 3.1 Base Window (Primary Authority)

| Field | Value |
| --- | --- |
| Period | 2021-01-01 00:00:00 UTC to 2025-12-31 20:00:00 UTC |
| Span | 5 full years |
| Classification | Primary evidence source |
| Authority | Can independently support pass/pause/reject |
| Data QA status | MET (in use since project start) |
| NSC-014 result | PAUSE_FRAGILE (existing research-only proxy evidence) |

### 3.2 Supplemental Window (Diagnostic Only)

| Field | Value |
| --- | --- |
| Period | 2019-10-05 08:00:00 UTC to 2020-12-31 20:00:00 UTC |
| Span | ~14.9 months (after EMA60 warmup) |
| Classification | Supplemental diagnostic window only |
| Authority | Cannot independently determine pass/fail |
| Data QA status | MET (TE-005, DATA_QA_PASSED) |
| 1h/4h alignment | MET (TE-005 QA 5.8) |
| EMA60 warmup | 2019-09-25 to 2019-10-05 excluded |

### 3.3 Window Authority Rules

Per TE-006 Section 1.2:

1. Base window (2021-2025) is the primary decision authority.
2. Supplemental window (2019-2020) can only:
   - Strengthen a base-window pass (by showing consistent behavior pre-2021)
   - Expose hidden fragility (by showing inconsistent behavior pre-2021)
   - Provide additional stress-test context (COVID crash, early-market regime)
   - It **cannot** independently pass or fail Direction A.
3. Supplemental window can only downgrade or add caution, never upgrade.
4. 2019-2020 regime differences must be documented.

---

## 4. Reproducible Execution Commands

### 4.1 Prerequisite Checks

```bash
# 1. Verify database exists and has pre-2021 data
sqlite3 data/v3_dev.db \
  "SELECT timeframe, COUNT(*) FROM klines
   WHERE symbol='ETH/USDT:USDT' AND timestamp < 1609459200000
   GROUP BY timeframe;"
# Expected: 1h=8784, 4h=2196

# 2. Verify 2021-2025 data still present
sqlite3 data/v3_dev.db \
  "SELECT timeframe, COUNT(*) FROM klines
   WHERE symbol='ETH/USDT:USDT'
     AND timestamp >= 1609459200000 AND timestamp < 1767225600000
   GROUP BY timeframe;"

# 3. Verify TE-005 backup exists
ls -la data/v3_dev.db.pre-te005-backup-20260507
```

### 4.2 Execution Command

The NSC-014 adapter at
`reports/nsc-014-direction-a-4h-main-trend-lifecycle-clean-baseline/nsc_014_direction_a_research_adapter.py`
currently runs only the 2021-2025 window. TE-006B requires a modified copy that
adds the 2019-2020 supplemental window.

**Proposed approach:**

Create a new standalone research adapter at:
```
reports/te-006b-direction-a-longer-window-validation/te_006b_direction_a_longer_window_adapter.py
```

This adapter is a fork of the NSC-014 adapter with the following changes only:

1. Add supplemental window definition:
   ```python
   SUPPLEMENTAL_WINDOWS = {
       "2019-Q4": (1570257600000, 1577836800000),  # 2019-10-05 to 2020-01-01
       "2020": (1577836800000, 1609459200000),      # 2020-01-01 to 2021-01-01
   }
   ```

2. Run the same frozen Direction A rule against the supplemental window
   (2019-10-05 to 2020-12-31), starting from candle index 0 but only recording
   signals/trades after the EMA60 warmup date (2019-10-05 08:00 UTC).

3. Compute all metrics separately for:
   - Base window (2021-2025) — reuse NSC-014 results or recompute
   - Supplemental window (2019-2020) — new computation
   - Combined window (2019-2020 + 2021-2025) — aggregate only

4. Output to `reports/te-006b-direction-a-longer-window-validation/`

**Execution:**

```bash
cd /Users/jiangwei/Documents/final
python reports/te-006b-direction-a-longer-window-validation/te_006b_direction_a_longer_window_adapter.py
```

### 4.3 What Changes From NSC-014

| Aspect | NSC-014 | TE-006B |
| --- | --- | --- |
| Windows | 2021-2025 only | 2019-2020 + 2021-2025 |
| Rule logic | Frozen | Identical (frozen) |
| Cost model | Frozen | Identical (frozen) |
| Parameters | Frozen | Identical (frozen) |
| Output dir | `reports/nsc-014-*/` | `reports/te-006b-*/` |
| Classification | PAUSE_FRAGILE | Per TE-006 Section 5 |
| Supplemental regime breakdown | N/A | Required (Section 6.4) |
| 2019 partial-month handling | N/A | Required (Section 6.3) |

### 4.4 Files Modified

| File | Action |
| --- | --- |
| `reports/te-006b-direction-a-longer-window-validation/te_006b_direction_a_longer_window_adapter.py` | Created (new standalone adapter) |
| `reports/te-006b-direction-a-longer-window-validation/experiment_report.md` | Created (output) |
| `reports/te-006b-direction-a-longer-window-validation/summary.json` | Created (output) |
| `reports/te-006b-direction-a-longer-window-validation/trades.jsonl` | Created (output) |
| `reports/te-006b-direction-a-longer-window-validation/signals.jsonl` | Created (output) |
| `reports/te-006b-direction-a-longer-window-validation/equity_curve.jsonl` | Created (output) |
| `reports/te-006b-direction-a-longer-window-validation/mtm_equity_curve.jsonl` | Created (output) |
| `docs/ops/te-006b-direction-a-longer-window-validation-report.md` | Created (final validation report) |

No files under `src/`, `configs/`, `tests/`, `migrations/` are modified.
No runtime profiles, risk rules, or backtester core are modified.

---

## 5. Required Metrics

All metrics per TE-006 Section 3, computed separately for base window and
supplemental window.

### 5.1 Core Metrics (Per Window)

- Net PnL (after costs, including funding)
- Profit Factor (PF)
- Realized MaxDD
- MTM MaxDD
- Trade count
- Win rate
- Avg win / avg loss
- Funding exposure (absolute and as % of gross PnL)

### 5.2 Sparse Trend Fragility Metrics (Per Window)

- Top 1 / 3 / 5 removal (recompute net PnL and PF)
- Year-by-year contribution
- Winner attribution (fraction from top 1/3/5/10)
- Trade count floor
- MFE / MAE
- Giveback (MFE - realized PnL for winners)
- Funding exposure as % of gross PnL

### 5.3 Combined Window Metrics

- Aggregate net PnL, PF, MaxDD across both windows
- Year-by-year including 2019-Q4 and 2020
- Top-winner concentration across the full combined window

### 5.4 Supplemental Window Regime Breakdown

Required per TE-006 Section 3.4:

| Period | Regime | Must Document |
| --- | --- | --- |
| 2019-Q4 | Early Binance USDT-M futures | Low liquidity, wide spreads, thin order book |
| 2020-Q1 (pre-COVID) | Normal market | Baseline pre-pandemic behavior |
| 2020-03 | COVID crash | Extreme volatility, 50%+ ETH drawdown |
| 2020-Q2 | COVID recovery | V-shaped recovery, high volatility |
| 2020-Q3/Q4 | DeFi summer + consolidation | New market structure, increased retail |

### 5.5 2019 Partial-Month Treatment

Per TE-006 Section 3.3:

1. Do not include 2019-09 in year-by-year breakdown as a full month.
2. Either exclude 2019-09 entirely or combine with 2019-10 as "2019-Q4."
3. EMA60 warmup period (2019-09-25 to 2019-10-05) must not produce evaluable
   signals. Any signal before 2019-10-05 08:00 UTC is a warmup artifact.
4. Report 2019-09 row count and candle count separately.

---

## 6. Report Structure

The final validation report at
`docs/ops/te-006b-direction-a-longer-window-validation-report.md`
must contain:

1. **Boundary statements** — per Section 0 of this plan
2. **Frozen rule definition** — per Section 2
3. **Data window definitions** — per Section 3
4. **Cost model and execution policy** — per Section 2 cost model
5. **Anti-lookahead proof** — per NSC-014 report, re-confirmed for supplemental
6. **Base window results** — all metrics from Section 5.1 + 5.2
7. **Supplemental window results** — all metrics from Section 5.1 + 5.2
8. **Supplemental regime breakdown** — per Section 5.4
9. **2019 partial-month treatment** — per Section 5.5
10. **Combined window aggregate** — per Section 5.3
11. **Supplemental vs base consistency analysis** — compare regime patterns,
    PF, fragility across windows
12. **Classification** — per TE-006 Section 5
13. **Year-by-year table** — 2019-Q4, 2020, 2021, 2022, 2023, 2024, 2025
14. **Top-winner concentration analysis** — per window and combined
15. **MFE/MAE/giveback analysis** — per window
16. **Funding exposure analysis** — per window
17. **Stop conditions encountered** — if any
18. **Explicit statements:**
    - "This is official validation, not promotion authorization."
    - "There is no deployable small-live strategy candidate."
    - "Small-live readiness gate remains unmet."
    - "Research/runtime isolation is maintained."

---

## 7. Acceptance Criteria

TE-006B is accepted when:

- [ ] Adapter runs without error against both windows
- [ ] Base window results reproduce NSC-014 results within rounding tolerance
- [ ] Supplemental window produces a complete metrics set
- [ ] 2019 partial-month is handled per Section 5.5
- [ ] Supplemental regime breakdown is documented per Section 5.4
- [ ] Classification is assigned per TE-006 Section 5
- [ ] No files under `src/`, `configs/`, `tests/`, `migrations/` are modified
- [ ] No runtime/profile/risk/backtester-core changes are made
- [ ] Report structure matches Section 6
- [ ] Anti-lookahead proof is confirmed for supplemental window

---

## 8. Stop Conditions

Per TE-006 Section 7, extended for TE-006B:

| Condition | Action |
| --- | --- |
| Strategy logic is not code-frozen | Stop; do not validate against unfrozen logic |
| Entry/exit rules are ambiguous | Stop; clarify rules before validation |
| Data QA fails for either window | Stop; do not validate against un-QA'd data |
| 1h/4h alignment cannot be verified | Stop; alignment is prerequisite |
| Base window results diverge materially from NSC-014 | Stop; investigate divergence before proceeding |
| Supplemental window produces zero trades | Stop; investigate data or rule issue |
| Any metric computation error is discovered | Stop; recompute all metrics before proceeding |
| EMA60 warmup produces evaluable signals before 2019-10-05 | Stop; warmup leak detected |
| Owner revokes authorization | Stop immediately |

---

## 9. Prohibited Actions

The following are explicitly prohibited during TE-006B:

- Modifying `src/**`, `configs/**`, `tests/**`, `migrations/**`
- Modifying runtime profiles, risk rules, or backtester/research engine core
- Modifying the frozen Direction A rule (Donchian20, EMA60, cost model)
- Parameter sweep of any kind
- Enabling Direction E / E-A overlay
- Enabling 1h entry timing
- Cost / funding / slippage relaxation
- Selective year inclusion or exclusion after seeing results
- Rewriting results as promotion or small-live authorization
- Treating supplemental window as primary authority
- Combining windows into a monolithic proof
- Any live deployment conclusion

---

## 10. Rollback / Cleanup

### 10.1 Adapter Output Rollback

```bash
rm -rf reports/te-006b-direction-a-longer-window-validation/
rm -f docs/ops/te-006b-direction-a-longer-window-validation-report.md
```

### 10.2 Database Rollback

TE-006B does not modify the database. No database rollback is needed.

If the database was accidentally modified:
```bash
cp data/v3_dev.db.pre-te005-backup-20260507 data/v3_dev.db
```

### 10.3 NSC-014 Integrity Check

After TE-006B, verify NSC-014 results are unchanged:
```bash
# Re-run NSC-014 adapter and compare summary.json
cd reports/nsc-014-direction-a-4h-main-trend-lifecycle-clean-baseline/
python nsc_014_direction_a_research_adapter.py
# Compare output with git-committed version
```

---

## 11. Can TE-006B Execute Without Modifying Runtime/Strategy/Backtester Core?

**Yes.** The execution path is:

1. The NSC-014 adapter is a standalone Python script under `reports/` that:
   - Reads directly from `data/v3_dev.db` (SQLite)
   - Computes Donchian20, EMA60, and all trade logic inline
   - Writes output to `reports/` directory
   - Does not import anything from `src/`
   - Does not modify any runtime/profile/risk/backtester code

2. TE-006B adapter is a fork of NSC-014 with only:
   - Extended window definitions (adding 2019-2020)
   - Additional metrics computation for the supplemental window
   - Modified output directory

3. The 2019-2020 data is already in `v3_dev.db` (TE-005, DATA_QA_PASSED).

4. No code under `src/`, `configs/`, `tests/`, `migrations/` needs to change.

**Conclusion: TE-006B can execute as a pure research-only standalone adapter
without any runtime, strategy parameter, or backtester core modification.**

---

## 12. Supplemental Window Usage Rules

Per TE-006 Section 1.2 and project constraints:

1. **2019-2020 supplemental window can only:**
   - Strengthen a base-window pass (consistent behavior pre-2021)
   - Expose hidden fragility (inconsistent behavior pre-2021)
   - Provide additional stress-test context (COVID crash, early-market regime)

2. **2019-2020 supplemental window cannot:**
   - Independently pass or fail Direction A
   - Upgrade a PAUSE to a PASS
   - Override a base-window REJECT
   - Serve as standalone validation evidence

3. **Combined results must be interpreted as:**
   - "Base window result + supplemental window consistency check"
   - Not as a monolithic 6.2-year backtest proof

4. **If supplemental results diverge from base results:**
   - The divergence must be documented and explained
   - The supplemental result must not be given weight until explained
   - Possible explanations: regime difference (early Binance, COVID), liquidity,
     market microstructure

5. **2019-2020 cannot alone upgrade Direction A to official candidate.**
   Only the base window (2021-2025) can support a pass/pause/reject decision.

---

## 13. Expected Outcome Scenarios

### Scenario 1: Supplemental Consistent with Base

Supplemental window shows PF > 1.0 and similar regime pattern to base window.

- Base: PAUSE_FRAGILE → Final: PAUSE_FRAGILE (supplemental cannot upgrade)
- Supplemental adds confidence that Direction A behavior is not a 2021-2025 artifact
- Report notes: "Supplemental window is consistent; does not upgrade PAUSE_FRAGILE"

### Scenario 2: Supplemental Shows Additional Fragility

Supplemental window shows PF < 1.0 or very different behavior (e.g., COVID crash
destroys the strategy).

- Base: PAUSE_FRAGILE → Final: PAUSE_FRAGILE (reinforced)
- Report notes: "Supplemental window exposes additional fragility in 2019-2020 regime"
- This is valuable diagnostic information even though it doesn't change classification

### Scenario 3: Supplemental Shows Strong Performance

Supplemental window shows PF > 1.5 and strong trend capture, including through
COVID recovery.

- Base: PAUSE_FRAGILE → Final: PAUSE_FRAGILE (supplemental cannot upgrade)
- Report notes: "Supplemental window is consistent and strong; does not upgrade
  PAUSE_FRAGILE because base window fragility gates remain unmet"
- This may inform future Owner decision about whether to reconsider fragility gates

### Scenario 4: Supplemental Window Has Insufficient Trades

Fewer than 10 trades in the 14.9-month supplemental window.

- Report notes: "Supplemental window has insufficient trade count for
  interpretable evidence"
- Supplemental consistency check is marked as INCONCLUSIVE
- Base classification is unchanged

---

## 14. Relationship to TE-007A

TE-006B and TE-007A serve different purposes:

| Aspect | TE-006B | TE-007A |
| --- | --- | --- |
| Scope | Direction A longer-window supplemental validation | Direction A official validation |
| Windows | Base (2021-2025) + Supplemental (2019-2020) | Base (2021-2025) + Supplemental (2019-2020) |
| Classification | Per TE-006 Section 5 | Per TE-006 Section 5 |
| Authority | Research-only evidence with supplemental context | Official validation (if Owner authorizes) |
| Next step if PASS | Owner decides on small-live readiness | Owner decides on small-live readiness |
| Requires Owner MaxDD thresholds | No (uses research-only interpretation) | Yes (per TE-006 Section 2.4) |

TE-006B can be executed without TE-007A. TE-007A requires Owner-defined MaxDD
thresholds before execution. TE-006B does not require those thresholds because
it produces research-only evidence with supplemental context.

If TE-006B is executed first, its results can inform the Owner's decision on
whether to authorize TE-007A.

---

## 15. Owner Decision Required

**TE-006B execution requires Owner approval.**

This plan defines what execution would look like. It does not authorize that
execution.

To proceed, Owner must:

1. Review and approve this execution plan.
2. Confirm that the frozen Direction A rule (Section 2) is correct and complete.
3. Confirm that the supplemental window usage rules (Section 12) are acceptable.
4. Authorize Level 3 execution (backtest execution + metrics computation +
   docs output).

**This window is now stopped, awaiting Owner approval to execute TE-006B.**

---

## 16. Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-07 | Initial TE-006B execution plan created | Codex |
