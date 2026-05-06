# Crypto Pullback Module v1 — Scope Note

**Date:** 2026-05-02 (updated 2026-05-06)
**Status:** Active (SSOT for strategy module identity; module paused for promotion — see OOS failure classification)
**Purpose:** Define the current strategy module's identity, assumptions, boundaries, and non-goals. This document is the single source of truth for what the module is and is not, preventing drift from ad-hoc parameter tuning or scope creep.

---

## 1. Module Identity

**Name:** Crypto Pullback Module v1 (CPM-1)

**Code reference:** `sim1_eth_runtime` runtime profile, `PinbarStrategy` trigger, `EmaTrendFilterDynamic` + `MtfFilterDynamic` filters

**What it is:** A trend-pullback continuation module that enters LONG positions when a pullback within an established uptrend shows signs of ending.

**What it is not:** It is not "the system strategy." It is not a general-purpose crypto trading module. It is not a mean-reversion module. It is not a volatility-breakout module.

**Pinbar is the entry trigger, not the module definition.** The module's identity is pullback-continuation-with-trend-confirmation. Pinbar is the geometric pattern used to detect the pullback-ending moment. A future CPM-2 could use a different trigger (e.g., inside bar, hammer, demand zone test) within the same structural framework.

---

## 2. Current Frozen Baseline

| Dimension | Value | Change Status |
|-----------|-------|---------------|
| Asset | ETH/USDT:USDT | Frozen |
| Primary timeframe | 1h | Frozen |
| MTF timeframe | 4h | Frozen |
| Direction | LONG-only | Frozen |
| Trigger | Pinbar (min_wick_ratio=0.6, max_body_ratio=0.3, body_position_tolerance=0.1) | Frozen |
| Filter 1 | EMA trend (period=50, min_distance_pct=0.005) | Frozen |
| Filter 2 | MTF confirmation (4h EMA60 rising) | Frozen |
| Filter 3 | ATR volatility | Disabled (frozen as disabled) |
| TP1 | 1.0R, close 50% | Frozen |
| TP2 | 3.5R, close 50% | Frozen |
| Initial SL | -1.0R (pinbar candle low) | Frozen |
| Breakeven | OFF | Frozen |
| Trailing stop | OFF | Frozen |
| OCO | ON | Frozen |

**All parameters above are frozen.** CPM-1 is paused for promotion after OOS gate failure (2021/2022 both negative). No parameter changes are in scope. Changes require owner decision and a separate task card.

---

## 3. Profit Hypothesis

The module earns when:

1. **An established uptrend exists** (price above EMA50, 4h EMA60 rising).
2. **Price pulls back within the trend** (creating the pinbar wick).
3. **The pullback ends and trend resumes** (the pinbar body confirms rejection of lower prices).
4. **Continuation carries price to TP1 (1R) and/or TP2 (3.5R)**.

The structural edge is: trend-following with a pullback-specific entry timing. The module does not earn from predicting trend starts or reversals — it earns from confirming that an existing trend is intact and entering at a discount.

**Historical evidence:**
- 2024: +8,501 USDT (WR=32.3%, Sharpe=1.91, MaxDD=17.39%)
- 2025 (partial): +4,490 USDT (WR=31.7%, Sharpe=2.01, MaxDD=11.56%)
- 2026 Q1 forward: +777 USDT (small sample, positive)

---

## 4. Failure Hypothesis

The module loses when:

1. **Pullback turns into reversal**: The pinbar is a trap, not a discount. The trend has actually ended, and the entry is at the start of a new downtrend.
2. **Overheating / high volatility**: Price has surged recently (high 72h return, high realized volatility). The pinbar is a pause in a parabolic move, not a pullback in a healthy trend.
3. **Near Donchian channel top**: Price is already at or near recent highs. The pullback is shallow and the upside is limited.
4. **Flat / sideways market**: EMA50 is flat, price oscillates around it. Pinbars fire but there is no trend to continue.

**M0 Strategy Ecology Map findings:**
- Top diagnostic features for loss prediction: `ema_4h_slope`, `recent_72h_return`, `realized_volatility_24h`, `distance_to_donchian_20_high`
- Pinbar is structurally counter-trend: it earns in low-slope, low-volatility environments and systematically loses in high-slope, high-volatility, recent-surge, and near-Donchian-top environments.

**2023 failure (regime mismatch):**
- 2023: -3,924 USDT (WR=16.1%, Sharpe=-2.63, MaxDD=49.19%)
- Five independent rescue experiments (H0 through H3a) exhausted all reasonable adjustment dimensions. All failed.
- **Classification: 2023 is the module's applicable-boundary cost, not a parameter problem.** Treat as regime mismatch / boundary cost. Do not re-open parameter search to "fix" 2023.

---

## 5. Applicable Market

The module is designed for and validated in:

- **Asset:** ETH/USDT:USDT perpetual contract
- **Timeframe:** 1h (primary), 4h (MTF confirmation)
- **Market state:** Established uptrend with moderate slope, moderate volatility, price below recent highs
- **Direction:** LONG only

**Cross-asset/cross-timeframe validation results:**
- BTC 1h: All configurations negative
- SOL 1h: All configurations negative
- ETH 4h: Too few trades (~17/year)
- ETH 15m: Too many trades (~140/year) with poor signal quality

**ETH 1h is the only validated path.** Expansion to other assets or timeframes requires new research and is not in scope.

---

## 6. Not-Applicable Market

The module is not designed for and is expected to lose in:

- **High-volatility regimes**: ATR percentile above ~0.6 (2023-like conditions)
- **Parabolic / surge regimes**: Recent 72h return above threshold (price has moved too far, too fast)
- **Near-Donchian-top regimes**: Price at or above recent channel highs (limited upside, high reversal risk)
- **Flat / sideways regimes**: EMA slope near zero (no trend to continue)
- **Downtrend regimes**: LONG-only by design; any downtrend is a structural non-fit
- **Non-ETH assets**: Not validated on BTC, SOL, or any other asset
- **Non-1h timeframes**: Not validated on 4h, 15m, or any other primary timeframe

---

## 7. 2023-Style Failure: Treatment

**Classification:** Regime mismatch / boundary cost. Not a parameter problem.

**Evidence:**
- H0 (EMA250/200 regime gate): Failed — coarse classification kills good-year trades
- H1 (SHORT-only mirror): Failed — only 2023 effective, 3yr far worse
- H2 (0.382 Fibonacci limit-entry): Failed — contradicts trend-following logic
- H3 (Dynamic risk geometry): Prerequisite (environment classification) fails
- H3a (Pre-entry feature prediction): Failed — absolute level overlap between 2023 and 2024/2025; no threshold separates them

**Current treatment:** Accept as boundary cost. Do not re-open parameter search.

**Future treatment candidates** (not now, require owner decision):
- E4 (donchian_distance) as risk-state label / position-weight-reduction factor (not hard filter)
- Regime identification layer (separate module, not CPM-1 scope)
- Portfolio diversification with a trend-following module (T1 research showed fragility; not viable yet)

---

## 8. Not-Now List

The following are explicitly out of scope for the current stabilization phase:

| Item | Why Not Now |
|------|------------|
| Parameter changes (EMA period, TP targets, SL, BE, trailing) | Baseline is frozen; changes require new research cycle |
| New entry triggers (inside bar, hammer, demand zone) | CPM-1 scope is pinbar; new triggers are CPM-2+ |
| SHORT direction | LONG-only validated; SHORT mirror (H1) failed |
| New asset expansion (BTC, SOL) | Cross-asset validation all negative |
| New timeframe expansion (4h, 15m) | Cross-timeframe validation all negative |
| ATR filter re-enablement | Frozen as disabled; was validated as redundant |
| E4 hard filter | P0 official validation showed over-filtering; FAIL |
| Regime identification layer | Separate module; prerequisite research not complete |
| Portfolio combination (T1 or other) | T1 fragility confirmed; not viable yet |
| Adaptive / dynamic parameter adjustment | No validated framework; H3 prerequisite fails |
| Limit-entry (Fibonacci 0.382) | H2 failed; contradicts trend-following logic |
| Multi-strategy routing | Single module only; routing requires portfolio engine |
| Frontend strategy control | Read-only display only; no runtime parameter modification |
| Backtester changes | Separate workstream |
| Risk rule changes | Live-safe non-goal |

---

## 9. Owner Decision Points

The following questions require owner input before any action:

1. **Should CPM-1 remain frozen through the observation period, or are there conditions that would justify unfreezing a specific parameter?** (Current default: frozen.)

2. **Should E4 (donchian_distance) be investigated as a risk-state label / position-weight-reduction factor?** (Current status: P0 official validation showed it is an effective risk factor but over-filters as a hard gate. Next step would be E4 threshold sensitivity analysis, not implementation.)

3. **Should additional OOS validation be pursued?** (Current status: 2021 and 2022 OOS have been run and both are negative. CPM-1 is paused. Any further OOS requires Owner decision on whether it would change the current Pause classification.)

4. **Should a second observation pass (longer duration, crossing UTC midnight) be scheduled before declaring the baseline stable?** (Current status: OBS-001 pass 1 completed with 5-minute window; gaps in order update, risk trace, and daily boundary evidence.)

5. **At what point would a CPM-2 (alternative trigger within same structural framework) become worth researching?** (Current status: no research planned. Trigger would need to address the same pullback-continuation hypothesis with different geometry.)

6. **Should the module's applicable-boundary cost (2023-style regime mismatch) be formally accepted as a portfolio-level risk, or should regime identification remain a research priority?** (Current status: accepted as boundary cost. Regime identification is a future capability, not a current task.)

7. **Is the current capital allocation (exposure=1.0, risk=0.5%) acceptable, or should the R1b feasible configurations be revisited?** (Current status: R1b showed MaxDD <= 35% constraint produces "not incentivizing" returns. Owner must decide if current allocation is acceptable or if the drawdown constraint should be relaxed.)

---

## 10. Relationship to Other Modules

| Module | Relationship |
|--------|-------------|
| Live-safe v1 | CPM-1 runs within live-safe guardrails. Live-safe does not modify strategy logic, risk rules, or runtime profile. |
| Decision Trace | Risk decisions from CPM-1's `pre_order_check` are recorded to `risk_decision.jsonl`. Trace schema is independent of CPM-1 parameters. |
| Reconciliation | Reconciliation detects local/exchange state mismatches. CPM-1's order flow produces the local state that reconciliation checks. |
| Runtime Task Governance | CPM-1's background tasks (order watch, snapshot update, reconciliation) are managed by the runtime task lifecycle system. |

---

## 11. Evidence Inventory

Key research documents supporting this scope note:

| ID | Document | Key Finding |
|----|----------|-------------|
| H0-H3a | `archive/.../2026-04-28-eth-baseline-2023-rescue-research-closure.md` | 2023 rescue exhausted; regime mismatch, not parameter problem |
| M0 | `archive/.../2026-04-28-strategy-ecology-map-m0.md` | Pinbar is counter-trend; top loss features identified |
| M1 | `archive/.../2026-04-28-pinbar-toxic-state-avoidance-m1.md` | 4 single-factor filters pass proxy PASS criteria |
| M1b | `archive/.../2026-04-28-pinbar-toxic-state-m1b-parity.md` | E1 FAIL, E4 PASS under official parity |
| P0 | `archive/.../2026-04-29-p0-pinbar-e4-official-validation.md` | E4 over-filters; FAIL as hard gate |
| R1b | `archive/.../2026-04-28-market-regime-experiment-assessment.md` | Capital allocation feasible but "not incentivizing" |
| C1/C2 | `archive/.../2026-04-28-c1-pinbar-t1-portfolio-proxy.md` | Portfolio combination fragile; T1 not viable |
| External review | `archive/.../2026-04-29-eth-baseline-strategy-research-review-for-external-quant.md` | Comprehensive strategy research review |
| OBS-001 | `docs/ops/live-safe-v1-observation-checklist.md` | First observation pass; runtime stable, no P0/P1 |

---

## 12. Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-05-02 | Initial scope note created | Claude Code (CPM-001) |
| 2026-05-06 | Updated status to reflect Pause after OOS gate failure; updated Owner decision point 3 for 2021/2022 OOS results | Claude Code (CPM-OOS-FAILURE-CLASSIFY-001) |