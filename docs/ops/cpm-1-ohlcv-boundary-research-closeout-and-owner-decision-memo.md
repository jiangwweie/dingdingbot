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

# CPM-1 OHLCV Boundary Research Closeout and Owner Decision Memo

**Date:** 2026-05-08
**Task ID:** CPM-1-OHLCV-BOUNDARY-RESEARCH-CLOSEOUT
**Classification:** CPM_OHLCV_BOUNDARY_ATTRIBUTION_PAUSED_RESEARCH_EVIDENCE_PRESERVED

---

## 1. Boundary

This is a docs-only closeout memo. It consolidates the full CPM-1 OHLCV boundary attribution chain, determines research status after the H5 macro-context robustness review (H5RA), and presents Owner decision options.

This memo does not authorize CPM-1 changes, CPM-MOD-003, CPM-2, gates, backtests, empirical diagnostics, parameter sweeps, runtime use, small-live, strategy rescue, lower-timeframe rescue, extra-data rescue, CVD/order-flow work, router/regime/portfolio work, or any empirical experiment execution.

---

## 2. Inputs

| ID | Document | Classification |
|----|----------|---------------|
| I1 | CPM-1 Favorable Regime Attribution Review | CONDITIONAL_EDGE_CANDIDATE / APPLICABILITY_RESEARCH_OBJECT |
| I2 | CPM-1 Artifact Normalization and Feature Context Audit | ARTIFACT_CONTEXT_PARTIAL |
| I3 | CPM-MOD-001 Dynamic Enablement Inspect | H0/H1/E1/E4 FAIL; RECOMMEND_LEVEL_3_INSPECT_RUN |
| I4 | CPM-MOD-002 Frozen Volatility Regime Gate Diagnostic | HYPOTHESIS_STRENGTHENED_REQUIRES_FURTHER_VALIDATION |
| I5 | CPM-ABI-001 Applicability Boundary Hypothesis Inspect | BOUNDARY_HYPOTHESIS_PARTIAL_NEEDS_ATTRIBUTION |
| I6 | CPM-FCX-001 Read-only Feature-Context Extraction | FEATURE_CONTEXT_SUPPORTS_BOUNDARY_HYPOTHESIS_INSPECT |
| I7 | CPM-CPA-001 Continuation Failure Pre-Observable Proxy Attribution | CONTINUATION_PROXY_POST_HOC_ONLY |
| I8 | CPM-CMC-001 Choppiness & Macro Context Attribution Closeout | BOUNDARY_ATTRIBUTION_PARTIAL_KEEP_RESEARCH_ONLY |
| I9 | CPM-H5RA-001 H5 Macro-Context Robustness Attribution | H5_PARTIAL_BUT_INCOMPLETE |
| I10 | SRR-002 Research Methodology and Applicability Boundary Upgrade | 7 standards accepted; no current module satisfies |
| I11 | SMA-001 Strategy Module Applicability Map | CPM-1: Paused; partially strengthened but incomplete |
| I12 | Live-safe v1 Task Board | Current operational state |

---

## 3. CPM-1 Evidence Chain Summary

| Step | ID | What | Outcome |
|------|----|------|---------|
| 1 | Original CPM-1 | ETH/USDT LONG-only 1h pullback-continuation, 4h EMA60 confirmation, Pinbar entry, TP1 1.0R / TP2 3.5R / SL -1.0R | Positive OOS 2024/2025; negative 2021/2022/2023 |
| 2 | Favorable Regime Review | 2024 +8501, 2025 +4490; 2021 -2154, 2022 -972, 2023 -3924; 10 open applicability questions | CONDITIONAL_EDGE_CANDIDATE / APPLICABILITY_RESEARCH_OBJECT |
| 3 | Artifact Audit | No per-position feature rows in MOD-002 artifacts; metric scale reconciliation needed | ARTIFACT_CONTEXT_PARTIAL |
| 4 | CPM-MOD-001 | E1 slope filter FAIL; E4 Donchian hard gate FAIL; H0 EMA250/200 gate FAIL; ATR percentile ecology 0.625 (2023) vs 0.531 (2024/25) | Dynamic enablement hypotheses failed |
| 5 | CPM-MOD-002 | Frozen ATR > 0.60 gate: 2021 improved +933; 2022–2025 unchanged; 2023 gate disabled 171 days but zero actual trades | ATR gate addresses 2021 only |
| 6 | CPM-ABI-001 | H1–H4 defined; 2023 continuation failure dominant; ATR gate addresses 2021 not 2023 | BOUNDARY_HYPOTHESIS_PARTIAL_NEEDS_ATTRIBUTION |
| 7 | CPM-FCX-001 | 329 positions, 47 features extracted; 2023 continuation-dominated (MFE 4.26 vs 406); 2025 fragility structural | FEATURE_CONTEXT_SUPPORTS_BOUNDARY_HYPOTHESIS_INSPECT |
| 8 | CPM-CPA-001 | 7 proxy candidates evaluated; no credible pre-observable continuation proxy; bar range POST_HOC; 2023 failure invisible before entry | CONTINUATION_PROXY_POST_HOC_ONLY |
| 9 | CPM-CMC-001 | CHOP POST_HOC_OR_REDUNDANT; H2 POST_HOC; H5 PLAUSIBLE (2022 macro downtrend 0% overlap); 2021 mod-ATR macro overextension; Hurst ~0.50 | BOUNDARY_ATTRIBUTION_PARTIAL_KEEP_RESEARCH_ONLY |
| 10 | SRR-002 | 7 methodology standards accepted; pre-observable boundary, independence, fragility, conditional module, extra-data, Level 3 admission, TE path | Methodology baseline set; no module satisfies |
| 11 | CPM-H5RA-001 | Multi-dimensional 2022 separation confirmed (1D); severe contradictions (2024/2025 top-5 hostile macro, 2023 non-hostile but loses); 3D EMA200 warmup-limited (20.2%) | H5_PARTIAL_BUT_INCOMPLETE |
| 12 | This Closeout | Consolidation of full chain; Owner decision required | OHLCV boundary attribution paused |

---

## 4. Current CPM-1 Status

**Primary classification:** CONDITIONAL_EDGE_CANDIDATE / APPLICABILITY_RESEARCH_OBJECT / OHLCV_BOUNDARY_ATTRIBUTION_PAUSED

CPM-1 has positive OOS performance in 2024 (+8501) and 2025 (+4490) but negative performance in 2021 (-2154), 2022 (-972), and 2023 (-3924). After 12 research steps, the failure modes are partially attributed but no pre-observable applicability boundary satisfies SRR-002 standards.

**SRR-002 compliance status:**

| Standard | Status | Detail |
|----------|--------|--------|
| Pre-observable applicability boundary | FAIL | No boundary computable before entry that explains all failure years |
| Independent alpha vs overlap echo | NOT TESTED | No independent signal set validated |
| Sparse trend fragility | PARTIAL | Top-winner concentration acknowledged but not deployment-grade |
| Conditional module evidence | FAIL | No validated pre-observable boundary for conditional enablement |
| Extra-data dependency | UNRESOLVED | Continuation failure may require non-OHLCV data |
| Level 3 admission gate | FAIL | Multiple requirements unmet |
| TE path framing | NOT REACHED | TE-007A blocked by foundational issues |

---

## 5. Failure Mode Map

| Year | Mode | Explanation | Confidence | Status |
|------|------|-------------|------------|--------|
| 2021 H1 | High-volatility whipsaw | ATR gate (CPM-MOD-002) filters 2021 high-ATR entries | Moderate | Addressed by MOD-002; not validated OOS |
| 2021 H2 | Moderate-volatility overextension | H5 macro: +38% above EMA200, +12% 30d return → mean-reversion pressure | Partial | H5 explains ~60% of 2021 mod-ATR losses |
| 2022 | Macro downtrend hostile to LONG | H5 macro: -17% below EMA200, 86% death cross, -4.68 EMA200 slope | Partial | Strong 2022 separation but post-hoc; 3D limited by warmup |
| 2023 | Continuation failure | MFE 4.26 vs 406 (2024); entries in non-hostile context; no continuation | None | **Unexplained under OHLCV.** No credible pre-observable proxy found (CPA-001). |
| 2024 | Favorable regime | Reference year; +8501 net; concentrated top-5 | N/A | Confirmed positive |
| 2025 | Fragile favorable | +4490 net; structural fragility; top-5 in hostile macro | N/A | Positive but fragile |

**Unexplained residual:** 2023 continuation failure remains invisible under OHLCV. This is the primary blocker for any applicability boundary.

---

## 6. Closed Lines

The following research lines are closed. They are not candidates for further empirical work unless new pre-observable hypotheses are proposed and approved separately.

| Line | Reason for Closure |
|------|-------------------|
| CPM-MOD-003 (new gate variants) | No pre-observable boundary exists to anchor a new gate |
| CPM-2 (direction extension) | CPM-1 boundary unresolved; extending premature |
| ATR threshold variants (sweep 0.50–0.70) | Post-hoc threshold fitting; MOD-002 addresses 2021 only |
| Bar range gate | POST_HOC (CPA-001); not pre-observable |
| CHOP gate | POST_HOC_OR_REDUNDANT (CMC-001); no separation |
| Hurst-based gating | ~0.50 everywhere; no separation |
| H3 composite threshold | POST_HOC (ABI-001) |
| 3D EMA200 hard gate | Warmup-limited (20.2% of 2022); 0% overlap headline based on 19/94 positions |
| 1D EMA200 hard gate | Would filter top-5 winners in 2024 and 2025 (severe contradiction) |
| H5 empirical diagnostic | Not justified: post-hoc, no validation period, does not explain 2023, threshold fitted to gap, top-5 in hostile context, 3D warmup-limited |
| E4 Donchian hard gate | FAIL (MOD-001) |
| Pinbar variant research | No hypothesis for variant improvement |
| TP/SL ratio variants | No hypothesis; changes risk profile without boundary insight |
| 15m timeframe rescue | ROLE_FROZEN per SRR-001 |
| Router/regime engine | CPM-1 boundary must resolve first |
| Portfolio overlay | CPM-1 boundary must resolve first |
| Extra-data/CVD rescue narrative | Post-hoc rescue rejected per SRR-002 Sec 6; requires named hypothesis |

**H5 is preserved as research evidence, not closed.** H5 provides partial attribution for 2022 and 2021 mod-ATR. It may inform future boundary work but cannot be converted to a gate or diagnostic.

---

## 7. Preserved Evidence Assets

The following artifacts constitute the CPM-1 boundary research evidence base. They are preserved for potential future use if new pre-observable hypotheses are proposed.

| Asset | Path | Content |
|-------|------|---------|
| Position context extraction | `reports/cpm-1-choppiness-macro-context-closeout/position_context_chop_macro.csv` | 329 positions, 47 features |
| Group summary | `reports/cpm-1-choppiness-macro-context-closeout/chop_macro_group_summary.json` | Per-group medians for CHOP, macro, Hurst |
| H5 robustness summary | `reports/cpm-1-h5-macro-context-robustness/h5_macro_robustness_summary.json` | Classifications, warmup audit, contradictions |
| H5 robustness summary (md) | `reports/cpm-1-h5-macro-context-robustness/h5_macro_robustness_summary.md` | Human-readable tables |
| Attribution chain documents | `docs/ops/cpm-1-*.md` (8 documents) | Full narrative and classification chain |

---

## 8. Why Frozen Diagnostic Is Not Justified

A "frozen diagnostic" would mean locking an H5-based macro context threshold as a CPM-1 runtime gate. This is not justified for the following reasons:

1. **Post-hoc origin.** H5 was formulated after observing 2022 failure patterns. Under SRR-002 Section 2, post-hoc hypotheses carry a penalty that prevents direct conversion to runtime rules.

2. **No validation period.** The only macro-downtrend year with full data is 2022. There is no independent validation period to test whether an H5 threshold would generalize.

3. **Does not explain 2023.** 2023 is the dominant failure mode (MFE 4.26 vs 406). 2023 entries occurred in non-hostile macro context (+10.66% above EMA200, 73.3% above). H5 cannot explain or filter 2023 failures.

4. **Threshold fitted to gap.** Any macro threshold (e.g., "price must be above EMA200" or "EMA50 must be above EMA200") would be fitted to the 2022-all vs 2024-winners gap (31.96 pp on d1_dist_ema200_pct). This is textbook overfitting without validation.

5. **Top-5 contradiction.** CPM-1's best trades (2024 top-5: -8.43% below EMA200, 60% death cross; 2025 top-5: -19.36% below EMA200, 60% death cross) enter in hostile macro context. Any macro gate would filter the strategy's most profitable entries.

6. **3D evidence warmup-limited.** The strongest separation headline (0% overlap on 3D EMA200) is based on 19 of 94 (20.2%) 2022 positions. The missing 79.8% includes the deepest bear-market phase.

---

## 9. Owner Decision Options

### Option A: Pause OHLCV Boundary Research (RECOMMENDED)

**Action:** Accept OHLCV boundary attribution as paused. Preserve evidence assets. Update task board. No further CPM-1 empirical work under OHLCV.

**Rationale:** The OHLCV attribution chain is exhausted under SRR-002. H5 provides one robust partial axis (2022 macro) but cannot be converted to a gate. 2023 remains unexplained. Further OHLCV-only work is diminishing returns.

**What this means:** CPM-1 remains non-runtime, non-small-live. Research evidence is preserved. Future boundary work can resume if a new pre-observable hypothesis emerges.

### Option B: Draft Docs-Only H5 Robustification Plan

**Action:** Draft a docs-only plan for further H5 robustification (e.g., expanding macro features, testing against additional failure subtypes, cross-validation framework design).

**Rationale:** H5 is the only partial explanation with coherent mechanism and multi-dimensional separation. Further development might yield a usable boundary.

**Risk:** High probability of diminishing returns. Post-hoc penalty remains. No validation period exists. Would delay other work.

### Option C: Extra-Data Inspect (RESERVED)

**Action:** Draft a docs-only inspect for whether non-OHLCV data (e.g., funding rate, open interest, order book depth) could provide a pre-observable proxy for continuation failure.

**Rationale:** 2023 continuation failure is invisible under OHLCV. SRR-002 Section 6 permits extra-data work with a named hypothesis addressing a specific OHLCV ambiguity. The named hypothesis would be: "continuation failure correlates with funding rate / OI divergence at entry time."

**Risk:** Requires extra data acquisition. Hypothesis is speculative. Must satisfy SRR-002 Section 6 before any empirical work.

**Status:** Reserved. Not recommended for immediate action but available if Owner wants to pursue.

### Option D: Stop CPM-1 Research Entirely

**Action:** Declare CPM-1 research closed. Archive all evidence. Remove from active consideration.

**Rationale:** Clean closure. Resource reallocation to other directions.

**Risk:** Discards positive 2024/2025 evidence and the H5 partial axis without exhausting extra-data avenue.

---

## 10. Recommendation

**Recommended: Option A with Option C reserved.**

- Accept OHLCV boundary attribution as paused.
- Preserve all evidence assets.
- Do not pursue Option B (diminishing returns on OHLCV-only H5 development).
- Reserve Option C for future Owner decision if extra-data avenue becomes attractive.
- Do not pursue Option D (premature closure given positive OOS evidence).

---

## 11. Task Board Update Recommendation

Add the following entries to the Strategy Candidate Inspect section of the Live-safe v1 Task Board:

| ID | Task | Status | Owner | Notes |
|----|------|--------|-------|-------|
| CPM-H5RA-001 | CPM-1 H5 Macro-Context Robustness Attribution | COMPLETE | Claude | H5_PARTIAL_BUT_INCOMPLETE. Multi-dimensional 2022 separation confirmed (1D); severe contradictions (top-5 hostile macro, 2023 non-hostile but loses); 3D warmup-limited. Recommendation D. |
| CPM-CLOSE-001 | CPM-1 OHLCV Boundary Research Closeout And Owner Decision Memo | COMPLETE | Claude | CPM_OHLCV_BOUNDARY_ATTRIBUTION_PAUSED_RESEARCH_EVIDENCE_PRESERVED. 12-step evidence chain consolidated. Owner decision required. Recommended Option A with C reserved. |

Update SMA-001 CPM-1 entry from "Paused; partially strengthened but incomplete applicability hypothesis" to "OHLCV boundary attribution paused; evidence preserved; no SRR-002-compliant boundary; Owner decision pending."

---

## 12. Final Classification

**CPM_OHLCV_BOUNDARY_ATTRIBUTION_PAUSED_RESEARCH_EVIDENCE_PRESERVED**

Sub-classifications preserved:
- CONDITIONAL_EDGE_CANDIDATE (original CPM-1)
- APPLICABILITY_RESEARCH_OBJECT (original CPM-1)
- H5_PARTIAL_BUT_INCOMPLETE (H5 macro-context)
- CONTINUATION_PROXY_POST_HOC_ONLY (2023 failure)
- POST_HOC_OR_REDUNDANT (CHOP, H2, H3 composite)
- CAVEATED_BY_WARMUP_OR_SAMPLE (3D EMA200)

---

## 13. Prohibitions

This memo does not authorize:
- CPM-1 changes (code, config, parameters)
- CPM-MOD-003 or any new gate variant
- CPM-2 or any direction extension
- Any new backtest, empirical diagnostic, or parameter sweep
- Threshold optimization or ATR sweep
- Runtime use or small-live
- Strategy rescue or lower-timeframe rescue
- Extra-data rescue without named hypothesis satisfying SRR-002 Sec 6
- CVD/order-flow data work
- Router/regime/portfolio work
- Automatic promotion from backlog
- Interpretation of paused status as deployment readiness

---

## 14. Owner Summary

CPM-1 has positive OOS evidence in 2024 (+8501) and 2025 (+4490) but negative in 2021 (-2154), 2022 (-972), and 2023 (-3924). After 12 research steps spanning hypothesis definition, feature extraction, proxy attribution, macro context analysis, and robustness review, no pre-observable applicability boundary satisfies SRR-002 standards.

H5-MACRO-LONG-BIAS-CONTEXT provides the strongest partial axis: multi-dimensional 2022 macro separation across 1D distance, cross-state, and slope features, with partial 2021 support. However, it is post-hoc, lacks a validation period, cannot explain the dominant 2023 continuation failure, and its strongest signal (3D EMA200) is warmup-limited. CPM-1's best trades enter in hostile macro context, meaning any macro gate would filter the strategy's most profitable entries.

OHLCV boundary attribution is paused. Research evidence is preserved. The recommended path is Option A (pause) with Option C (extra-data inspect) reserved for future Owner decision.

---

> CPM-1 remains non-runtime and non-small-live. CPM-1 OHLCV boundary attribution is paused with research evidence preserved. This closeout does not authorize CPM-1 changes, gates, empirical diagnostics, runtime use, strategy rescue, or any empirical experiment. Any future empirical work requires separate Owner approval and must satisfy SRR-002.
