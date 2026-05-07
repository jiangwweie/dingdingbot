# Crypto Pullback Module v1 — Evidence Interpretation Note

**Date:** 2026-05-06
**Status:** Active (evidence index only — no strategy conclusions)
**Purpose:** Index historical research evidence with explicit caveats so that future agents can reference findings without misreading old documents. This is a reference document, not a decision document. Intended as an appendix to the CPM-1 Stabilization Plan.

---

## 0. Terminology Note

Older archive documents use the term **"Pinbar baseline"** or **"ETH Pinbar baseline strategy."** This is a historical naming convention. The current module identity is **Crypto Pullback Module v1 (CPM-1)**, as defined in `crypto-pullback-module-v1-scope-note.md`. Pinbar is the entry trigger within CPM-1, not the module's total definition.

When reading archive documents, treat "Pinbar baseline" as synonymous with "CPM-1 frozen baseline parameters." Do not infer that the module is defined solely by its trigger pattern.

---

## 1. Evidence Matrix

### 1.1 Core Performance Evidence

| ID | Source Document | Source Date | Evidence Type | Official / Proxy | Cost Model | Data Window | Key Finding | Key Caveat | Affects Runtime Automatically |
|----|----------------|-------------|---------------|-----------------|------------|-------------|-------------|------------|-------------------------------|
| E-PERF-001 | External Quant Review §2 | 2026-04-29 | Backtest performance | Official | BNB9 where stated / mixed historical | 2023-01 to 2025-12 | 2024: +8,501 USDT (WR=32.3%); 2025: +4,490 USDT (WR=31.7%) | In-sample; no 2022 OOS validation run | No |
| E-PERF-002 | External Quant Review §2 | 2026-04-29 | Backtest performance | Official | BNB9 where stated / mixed historical | 2023-01 to 2023-12 | 2023: -3,924 USDT (WR=16.1%, MaxDD=49.19%) | Single-year loss; classified as regime mismatch not parameter error | No |
| E-PERF-003 | External Quant Review §2 | 2026-04-29 | Backtest performance | Official | BNB9 where stated / mixed historical | 2023-01 to 2025-12 | Aggregate 3yr: +9,067 USDT, WR=26.2%, Sharpe=0.31 | 2023 drag dominates aggregate; positive only because 2024+2025 offset 2023 | No |
| E-PERF-004 | External Quant Review §2 | 2026-04-29 | Forward performance | N/A (live/testnet) | Realized PnL | 2026 Q1 | +777 USDT | Small sample; not statistically significant; testnet environment | No |

**Caveat on all backtest evidence:** Cost model details vary across experiments. The External Quant Review uses BNB9 (0.0405% fee) as the stated cost model, but older proxy experiments (M0, M1, C1/C2) may use different or unspecified cost assumptions. Cross-experiment PnL comparisons should account for cost model differences, not assume uniformity. When a source document does not explicitly state its cost model, treat the PnL figures as directionally informative but not directly comparable with BNB9-stated results.

---

### 1.2 Strategy Ecology Evidence

| ID | Source Document | Source Date | Evidence Type | Official / Proxy | Cost Model | Data Window | Key Finding | Key Caveat | Affects Runtime Automatically |
|----|----------------|-------------|---------------|-----------------|------------|-------------|-------------|------------|-------------------------------|
| E-ECO-001 | M0 Strategy Ecology Map | 2026-04-28 | Feature importance (loss prediction) | Proxy (random forest classifier) | BNB9 where stated / mixed historical | 2023-01 to 2025-12 | Top loss-prediction features: ema_4h_slope, recent_72h_return, realized_volatility_24h, distance_to_donchian_20_high | Proxy model; feature importance ≠ causal mechanism; no out-of-sample validation on the ecology map itself | No |
| E-ECO-002 | M0 Strategy Ecology Map | 2026-04-28 | Regime characterization | Proxy | BNB9 where stated / mixed historical | 2023-01 to 2025-12 | CPM-1 earns in low-slope, low-volatility; systematically loses in high-slope, high-volatility, recent-surge, near-Donchian-top | "Low-slope" and "high-slope" are relative labels from proxy model; no hard thresholds defined | No |
| E-ECO-003 | M0 Strategy Ecology Map | 2026-04-28 | Structural classification | Proxy | BNB9 where stated / mixed historical | 2023-01 to 2025-12 | CPM-1 is structurally counter-trend: it earns when the trend is gentle and loses when the trend is aggressive | "Counter-trend" is a descriptive label from ecology analysis, not a formal regime definition | No |

**Caveat on proxy evidence:** M0 uses a random forest classifier as a proxy for understanding loss patterns. Feature importance from tree-based models can be unstable across seeds and hyperparameters. These findings identify candidate risk factors, not confirmed causal mechanisms.

---

### 1.3 Filter Validation Evidence

| ID | Source Document | Source Date | Evidence Type | Official / Proxy | Cost Model | Data Window | Key Finding | Key Caveat | Affects Runtime Automatically |
|----|----------------|-------------|---------------|-----------------|------------|-------------|-------------|------------|-------------------------------|
| E-FILT-001 | M1b Parity Report | 2026-04-28 | Single-factor filter test | Proxy (M1 parity) | BNB9 where stated / mixed historical | 2023-01 to 2025-12 | E1 (ema_4h_slope): FAIL — over-filters, kills 2024/2025 trades | Proxy parity criteria; not official validation | No |
| E-FILT-002 | M1b Parity Report | 2026-04-28 | Single-factor filter test | Proxy (M1 parity) | BNB9 where stated / mixed historical | 2023-01 to 2025-12 | E4 (donchian_distance): PASS under proxy parity — reduces 2023 loss while preserving 2024/2025 | Proxy parity criteria; P0 official validation overrides this result | No |
| E-FILT-003 | P0 Official Validation | 2026-04-29 | Single-factor filter test | Official | BNB9 where stated / mixed historical | 2023-01 to 2025-12 | E4 (donchian_distance): FAIL as hard gate — over-filters under official criteria; reduces trade count below acceptable threshold | Official criteria stricter than proxy; this result supersedes E-FILT-002 | No |
| E-FILT-004 | P0 Official Validation | 2026-04-29 | Risk factor assessment | Official | BNB9 where stated / mixed historical | 2023-01 to 2025-12 | E4 is an effective risk factor (correctly identifies high-loss regimes) but over-filters as a hard binary gate | E4's value as a risk-state label or position-weight factor is not ruled out; only hard-gate usage is rejected | No |

**Caveat on filter evidence:** M1/M1b proxy results and P0 official results use different acceptance criteria. When they conflict, P0 official takes precedence. Neither proxy nor official validation includes 2022 out-of-sample data.

---

### 1.4 2023 Rescue Evidence

| ID | Source Document | Source Date | Evidence Type | Official / Proxy | Cost Model | Data Window | Key Finding | Key Caveat | Affects Runtime Automatically |
|----|----------------|-------------|---------------|-----------------|------------|-------------|-------------|------------|-------------------------------|
| E-RES-001 | 2023 Rescue Closure | 2026-04-28 | Parameter adjustment | Official | BNB9 where stated / mixed historical | 2023-01 to 2025-12 | H0 (EMA250/200 regime gate): FAIL — coarse classification kills good-year trades | Regime gate concept is not rejected; only EMA250/200 implementation with tested thresholds | No |
| E-RES-002 | 2023 Rescue Closure | 2026-04-28 | Direction mirror | Official | BNB9 where stated / mixed historical | 2023-01 to 2025-12 | H1 (SHORT-only mirror): FAIL — only 2023 effective, 3yr aggregate far worse | SHORT direction is not validated as a standalone strategy | No |
| E-RES-003 | 2023 Rescue Closure | 2026-04-28 | Entry constraint | Official | BNB9 where stated / mixed historical | 2023-01 to 2025-12 | H2 (Fibonacci 0.382 limit-entry): FAIL — contradicts trend-following logic, reduces good-year trades | Limit-entry concept not rejected in all forms; only 0.382 Fibonacci tested | No |
| E-RES-004 | 2023 Rescue Closure | 2026-04-28 | Dynamic risk geometry | Official | BNB9 where stated / mixed historical | 2023-01 to 2025-12 | H3 (Dynamic risk geometry): FAIL — prerequisite (environment classification) does not separate 2023 from 2024/2025 | Dynamic risk geometry is not rejected in principle; only the tested classification approach fails | No |
| E-RES-005 | 2023 Rescue Closure | 2026-04-28 | Pre-entry feature prediction | Official | BNB9 where stated / mixed historical | 2023-01 to 2025-12 | H3a (Pre-entry feature prediction): FAIL — absolute feature level overlap between 2023 and 2024/2025; no threshold separates them | Feature overlap is a structural finding, not a methodology failure; suggests 2023 is not distinguishable ex-ante using these features | No |

**Caveat on rescue evidence:** Each H-experiment tests one specific implementation. Failure of H0 does not mean "regime gates never work" — it means "EMA250/200 with tested thresholds does not work." The closure document explicitly states this distinction. Do not over-generalize from individual experiment failures.

---

### 1.5 Same-Bar Evidence

| ID | Source Document | Source Date | Evidence Type | Official / Proxy | Cost Model | Data Window | Key Finding | Key Caveat | Affects Runtime Automatically |
|----|----------------|-------------|---------------|-----------------|------------|-------------|-------------|------------|-------------------------------|
| E-SB-001 | Same-Bar Verification Report | 2026-04-22 | Business verification | Official | BNB9 where stated / mixed historical | 2024-01 to 2025-12 | Same-bar policy impact is small under the tested 2024-2025 CPM-1 configuration (pessimistic vs random PnL diff +0.82%) | Only tested 2024-2025; not validated on 2023 or earlier years | No |
| E-SB-002 | Same-Bar Verification Report | 2026-04-22 | Business verification | Official | BNB9 where stated / mixed historical | 2024-01 to 2025-12 | Pessimistic same-bar policy (SL > TP) does not significantly understate results vs random policy | Same-bar conflict frequency and impact may differ under other parameter configurations or market regimes | No |

**Caveat on same-bar evidence:** This verification was prompted by a concern that same-bar trades might indicate a data look-ahead or timing error. The verification confirmed that same-bar policy impact is small under the tested 2024-2025 CPM-1 configuration. This finding applies only to the tested configuration and data window.

---

### 1.6 Capital Allocation Evidence

| ID | Source Document | Source Date | Evidence Type | Official / Proxy | Cost Model | Data Window | Key Finding | Key Caveat | Affects Runtime Automatically |
|----|----------------|-------------|---------------|-----------------|------------|-------------|-------------|------------|-------------------------------|
| E-CAP-001 | R1b Capital Allocation Audit v2 | 2026-04-29 | Feasibility analysis | Official | BNB9 where stated / mixed historical | 2023-01 to 2025-12 | MaxDD <= 35% constraint produces "not incentivizing" returns across all tested configurations | "Not incentivizing" is a qualitative assessment; owner may accept lower returns for lower drawdown | No |
| E-CAP-002 | R1b Capital Allocation Audit v2 | 2026-04-29 | Current allocation assessment | Official | BNB9 where stated / mixed historical | 2023-01 to 2025-12 | Current allocation (exposure=1.0, risk=0.5%) is within feasible range but does not meet MaxDD <= 35% in all years | Current allocation is owner-accepted; R1b findings are informational, not prescriptive | No |

**Caveat on capital allocation evidence:** R1b uses backtest-derived drawdown estimates. Actual live drawdown may differ due to slippage, funding, and execution gaps. Capital allocation is an owner decision, not a research output.

---

### 1.7 Portfolio Combination Evidence

| ID | Source Document | Source Date | Evidence Type | Official / Proxy | Cost Model | Data Window | Key Finding | Key Caveat | Affects Runtime Automatically |
|----|----------------|-------------|---------------|-----------------|------------|-------------|-------------|------------|-------------------------------|
| E-PORT-001 | C1/C2 Portfolio Proxy | 2026-04-28 | Portfolio proxy test | Proxy | BNB9 where stated / mixed historical | 2023-01 to 2025-12 | T1 (trend-following module) + CPM-1 portfolio: fragile — improvement only in narrow parameter bands | Proxy test; T1 module does not exist as implemented code | No |
| E-PORT-002 | C1/C2 Portfolio Proxy | 2026-04-28 | Portfolio assessment | Proxy | BNB9 where stated / mixed historical | 2023-01 to 2025-12 | Portfolio combination does not provide robust diversification benefit with available modules | Based on proxy T1; actual diversification may differ if a real trend-following module is built | No |

**Caveat on portfolio evidence:** C1/C2 uses a proxy implementation of T1. The portfolio fragility finding applies to the proxy, not to a hypothetical future T1 implementation. A real T1 module would need its own validation pipeline.

---

## 2. Evidence Hierarchy

When evidence conflicts, use this precedence:

1. **P0 Official validation** > M1/M1b Proxy parity
2. **Official experiments** (H0-H3a, P0, R1b) > Proxy experiments (M0, M1, C1/C2)
3. **Full-window results** (2023-2025) > Single-year results (2023 only or 2024 only)
4. **Same-bar verification** is configuration-specific; do not generalize beyond tested data window

---

## 3. Data Window Coverage

| Year | Coverage | Status |
|------|----------|--------|
| 2021 | Tested (OOS) | Negative: -2,153.76 USDT / -21.54%, PF 0.466, MaxDD 22.18%; favorable-regime signal-level failure |
| 2022 | Tested (OOS) | Negative: -971.71 USDT / -9.72%; bear-year failure hypothesis supported but no profit hypothesis support |
| 2023 | Tested (in-sample) | Worst year; regime mismatch |
| 2024 | Tested (in-sample) | Best year; +8,501 USDT |
| 2025 | Tested (in-sample) | Good year; +4,490 USDT |
| 2026 Q1 | Forward (testnet) | Small sample; +777 USDT |

**Current OOS status:** 2021 and 2022 have both been tested as OOS evidence and
both are negative. The 2021 bull-year failure is classified as signal-level
failure, not cost-dominated and not a May 2021 single-event artifact. CPM-1 is
therefore paused, the promotion path is stopped, and CPM-1 is not a Small-live
Candidate. No runtime, profile, strategy, or risk-rule change follows
automatically from this evidence.

---

## 4. Common Misreading Warnings

| Misreading | Correct Interpretation |
|------------|----------------------|
| "E4 was validated" | E4 passed proxy parity (M1b) but failed official validation (P0) as a hard gate. E4 is an effective risk factor but not a validated hard filter. |
| "2023 can be fixed" | Five rescue experiments (H0-H3a) exhausted reasonable adjustment dimensions. 2023 is classified as boundary cost, not a fixable parameter problem. |
| "Pinbar baseline is the strategy" | "Pinbar baseline" is a historical name. The module is CPM-1 (Crypto Pullback Module v1). Pinbar is the entry trigger. |
| "M0 proved that X causes losses" | M0 identified correlation patterns via proxy model. Feature importance ≠ causation. |
| "R1b says current allocation is wrong" | R1b says MaxDD <= 35% constraint produces unattractive returns. Current allocation is owner-accepted. R1b is informational. |
| "Same-bar trades are a bug" | Same-bar verification confirmed that same-bar policy impact is small under the tested 2024-2025 CPM-1 configuration. Not a bug, but the finding is configuration-specific. |
| "Portfolio combination works" | C1/C2 showed fragility in narrow parameter bands. Portfolio combination is not validated. |

---

## 5. Source Document Registry

| Document | Date | Archive Path | Key Content |
|----------|------|-------------|-------------|
| External Quant Review | 2026-04-29 | `archive/.../2026-04-29-eth-baseline-strategy-research-review-for-external-quant.md` | Comprehensive strategy research review; BNB9 cost model; 10-point executive summary; 12 methodology risks |
| 2023 Rescue Closure | 2026-04-28 | `archive/.../2026-04-28-eth-baseline-2023-rescue-research-closure.md` | H0-H3a full research chain closure; BNB9 cost model; 2023 classified as boundary cost |
| M0 Strategy Ecology Map | 2026-04-28 | `archive/.../2026-04-28-strategy-ecology-map-m0.md` | 10-feature tercile analysis; proxy model; counter-trend classification |
| M1b Parity Report | 2026-04-28 | `archive/.../2026-04-28-pinbar-toxic-state-m1b-parity.md` | E1/E4 parity check; proxy parity criteria; E4 PASS, E1 FAIL under parity |
| Same-Bar Verification Report | 2026-04-22 | `archive/.../same-bar-business-verification-report.md` | Pessimistic vs random same-bar policy; 2024-2025 only; +0.82% PnL diff |
| P0 Official Validation | 2026-04-29 | `archive/.../2026-04-29-p0-pinbar-e4-official-validation.md` | E4 official v3_pms validation; FAIL as hard gate; 3yr PnL -150.8% |
| R1b Capital Allocation Audit v2 | 2026-04-29 | `archive/.../2026-04-29-r1b-capital-allocation-audit-v2.md` | 56-config audit; 3 MaxDD metrics; 2 feasible configs under MaxDD <= 35% |

---

## 6. Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-05-06 | Initial evidence interpretation note created | Claude Code (CPM-DOC-EVIDENCE-001) |
| 2026-05-06 | Same-bar data window corrected (2023→2024); same-bar finding wording softened; cost model column unified to BNB9 where stated / mixed historical | Owner review feedback |
| 2026-05-06 | Restructured as stabilization planning appendix: added Source Date column, Affects Runtime Automatically column (all No), Source Document Registry section, renamed "Pinbar" references to CPM-1 where appropriate | Claude Code (CPM-STAB-EVIDENCE-MATRIX-001) |
