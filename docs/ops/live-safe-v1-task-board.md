# Live-safe v1 Task Board

Status values: `TODO`, `SPEC`, `IMPLEMENTING`, `TESTING`, `REVIEW`, `MERGED`, `BLOCKED`, `REJECTED`.

## Current Mainline Confirmation

As of 2026-05-09, the current phase label is `Observation + Research
Methodology Reset`.

The only current mainline strategy-research object is BTC+ETH Phase 1
observation design for Direction A. This is docs-only and Owner-review focused.
It does not authorize strategy runtime, paper/testnet/live trading, small-live
execution, portfolio/router work, SOL Phase 2, CPM reopening, short-side work,
parameter optimization, or runtime/profile/risk changes.

SRR-002 is accepted as the guiding methodology for future analysis. Acceptance
is docs-only and does not itself satisfy SRR-002 standards for any module.

## Milestones

- `Decision Trace Backbone v0` completed: minimal decision trace backbone added; risk decisions can be written to JSONL without affecting trading behavior on trace failure.
- `ADR-0002` completed: documented Decision Trace Backbone v0 semantics, scope, and non-goals.
- `LS-001` completed: main runtime order-watch enabled with isolated WS state; `api.py` out of scope; duplicate `watch_orders` definition remains as later cleanup.
- `LS-002` completed: runtime daily risk limits now update from projected exit deltas and full position closes; UTC reset and replay-safe accounting are active; v0 remains process-local in-memory state.

## P0

| ID | Task | Status | Owner | Notes |
| --- | --- | --- | --- | --- |
| LS-001 | Start `watch_orders` | MERGED | Codex | Main runtime order-watch enabled with isolated WS state; `api.py` out of scope; duplicate `watch_orders` definition remains as later cleanup. |
| LS-002 | Make daily max loss/trades effective | MERGED | Codex + Claude tests | Runtime projected daily PnL and full-close trade counts now drive daily limit rejects; persistence deferred to LS-002b. |
| LS-003 | Structured runtime logs | TODO | Claude | Requires Codex task card first. |
| LS-004 | Daily equity snapshot | TODO | Claude | Requires Codex task card first. |
| LS-005 | Periodic reconciliation | TODO | Codex | Core execution safety. |
| LS-006 | Account risk state machine | TODO | Codex | ADR required before implementation. |
| LS-007 | Liquidation distance and margin safety checks | TODO | Codex | Best-effort exchange field handling. |

## P1

| ID | Task | Status | Owner | Notes |
| --- | --- | --- | --- | --- |
| LS-101 | Recovery retry worker | TODO | TBD | After P0 state foundations. |
| LS-102 | Orphan order detector | TODO | TBD | Likely part of reconciliation. |
| LS-103 | Protection order coverage checker | TODO | TBD | Likely part of reconciliation. |
| LS-104 | Runtime health dashboard updates | TODO | TBD | After backend signals are stable. |
| LS-105 | Trace backbone boundary cleanup | TODO | Codex | Fix `decision_trace.py` logger dependency direction; keep v0 semantics stable. |
| LS-106 | Order watch hardening for multi-symbol runtime | TODO | Codex | Remove duplicate `watch_orders` definition and replace shared order-watch running flag before multi-symbol expansion. |
| LS-107 | Daily stats persistence hardening | MERGED | Codex | LS-002b: PG aggregate + event ledger committed; 15 targeted tests pass. |
| LS-108 | Reconciliation read model persistence | MERGED | Claude | LS-003d: PG read-only report + mismatch tables; best-effort persistence; 15 targeted tests pass; migration clean-DB upgrade/downgrade/upgrade verified; ADR-0007. |

## P2

| ID | Task | Status | Owner | Notes |
| --- | --- | --- | --- | --- |
| LS-201 | Funding data ingestion | TODO | TBD | Not P0. |
| LS-202 | Open interest ingestion | TODO | TBD | Not P0. |
| LS-203 | Multi-asset universe manager | TODO | TBD | Not P0. |

## Strategy Candidate Inspect — Non-Runtime

These tasks are docs-only candidate-direction inspections. They do not authorize strategy implementation, backtests, runtime/profile changes, risk rule changes, or promotion decisions.

| ID | Task | Status | Owner | Notes |
| --- | --- | --- | --- | --- |
| NSC-001 | CPM-2 Candidate Direction Inspect | REVIEW | Codex | Docs-only inspect report drafted; CPM-1 remains paused and no small-live candidate exists. |
| NSC-002 | CPM-2 Minimal Experiment Plan Draft | REVIEW | Codex | Docs-only proposed experiment plan drafted for Candidate A/B; no experiment execution authorized. |
| MTC-001 | Main Trend Capture Fragility Evaluation Framework v0 | REVIEW | Claude | Docs-only framework defining top-winner concentration evaluation, classification gates (INSUFFICIENT / REJECT / PAUSE_FRAGILE / RESEARCH_PASS / RUNTIME_CANDIDATE), and application guidance for future direction inspections. |
| MTC-002 | Strategy Direction Map Refresh v2 | REVIEW | Claude | Docs-only direction map refresh. Adopts MTC-001 framework. Pauses Direction C. Closes Direction E overlay family. Recommends Direction C (volatility contraction) as next inspect priority. Supersedes SCDM-001. |
| MTC-003 | Direction C Volatility Contraction / Re-expansion Inspect v0 | REVIEW | Claude | Docs-only direction inspect + minimal experiment plan draft. Recommends Level 3 upgrade pending frozen threshold specification. Primary risk: signal count may fall below MTC-001 trade floor. |
| MTC-004 | Direction C Volatility Contraction / Re-expansion Frozen Baseline Research Run | REVIEW | Claude | Frozen baseline completed. 63 trades, net +2039, PF 1.405. Classification: INSUFFICIENT_EVIDENCE (2021+2022 floor missed by 1 trade, winner count 10 < 15). Top-1 = 82.25% of net. MTM DD 15.01%. 14.3% overlap with Direction A. Owner conclusion: PAUSE_THIN_FRAGILE; not upgraded, not rejected. |
| MTC-005 | Direction D Structured Pullback / Value-Zone Entry Inspect v0 | REVIEW | Claude | Docs-only inspect + minimal experiment plan draft. Analyzes CPM-1 boundary, Main Trend Capture membership, and relationship to Direction A/C. Recommends Level 3 experiment with mandatory CPM drift check. Key risk: pullback-continuation is CPM family territory. |
| MTC-006 | Direction D Structured Pullback / Value-Zone Frozen Baseline Research Run | REVIEW | Claude | Frozen baseline completed. 417 trades, 66 winners, net -262.57, PF 0.985, MTM DD 29.78%, top-1 removal -3021.88. Classification: REJECTED_FROZEN_BASELINE. Direction A overlap 29.50%; no clear CPM drift. Pullback-continuation family priority lowered. |
| SSD-003 | Short-side 4h Breakdown Continuation Level 3 Frozen Research Run | REVIEW | Claude | Frozen baseline completed. 23 trades, 1 winner, net -1699.88, PF 0.317, realized DD 24.88%, MTM DD 26.98%. 2021 strongly negative, 2022-2024 no trades, 2025 single-winner concentrated. 0% Direction A/C overlap. Classification: REJECTED_FROZEN_BASELINE. |
| SSD-004 | Archive SSD-003 Evidence And Update Strategy Direction Map | REVIEW | Claude | Docs-only archive. Wrote SSD-003 REJECTED_FROZEN_BASELINE into SMA-001 applicability map and SRD-002 non-pullback direction map. Short-side breakdown continuation moved to rejected frozen baseline. Next non-pullback inspect promoted to volatility expansion / impulse participation. |
| VEI-001 | Volatility Expansion / Impulse Participation Level 1/2 Inspect | COMPLETE | MARGINAL — conditional RECOMMEND_LEVEL_2_FROZEN_EXPERIMENT_PLAN | Claude | Docs-only concept inspect. VEI mechanism defined (bar-level range expansion + close-location + follow-through). Overlap risk MEDIUM-HIGH with Direction A. Long-only 4h OHLCV. |
| VEI-002 | Volatility Expansion / Impulse Participation Level 2 Frozen Experiment Plan | COMPLETE | RECOMMEND_OWNER_LEVEL_3_REQUEST_LATER | Claude | Docs-only frozen experiment plan. All entry/exit/stop/overlap/cost elements frozen. K=1.5, N=20, P=0.75, EMA60, 5-bar hold, 2×ATR14 stop. Overlap gates: A <50%, C <50%. |
| VEI-003 | Volatility Expansion / Impulse Participation Level 3 Research Run | COMPLETE | PAUSE_FRAGILE | Claude | Frozen baseline completed. 118 trades, net +630.49, PF 1.21. Overlap gates passed (A 27.1%, C 2.5%). Independent signals net -329.02 PF 0.86. All positive PnL from Direction A echo. Top-3 removal -286.85. |
| VEI-004 | Archive VEI-003 Evidence And Update Direction Maps | COMPLETE | — | Claude | Docs-only archive. VEI classified PAUSE_FRAGILE. SMA-001 and SRD-002 updated. Non-pullback immediate candidate queue exhausted. VEI-001 stale phrasing corrected. |
| SRR-001 | Strategy Research Reset / Evidence-State Review | COMPLETE | Codex | Docs-only evidence-state review. All directions classified (A PAUSE_FRAGILE, C INSUFFICIENT_EVIDENCE, CPM-1 paused, D REJECTED, SSD REJECTED, VEI PAUSE_FRAGILE, 15m ROLE_FROZEN). Maximum common blocker: no validated pre-observable applicability boundary. Recommended next step: SRR-002 methodology upgrade. |
| SRR-002 | Research Methodology and Applicability Boundary Upgrade | COMPLETE | Codex | Docs-only methodology upgrade. Defines 7 standards: pre-observable applicability boundary (Sec 2), independent alpha vs overlap echo (Sec 3), sparse trend fragility (Sec 4), conditional module evidence (Sec 5), extra-data dependency (Sec 6), Level 3 admission gate (Sec 7), TE path framing (Sec 8). Does not change any module classification. No current module satisfies SRR-002 standards. Future Level 3 requests must reference SRR-002 Section 7. |
| CPM-ABI-001 | CPM-1 Applicability Boundary Hypothesis Inspect | COMPLETE | Claude | Docs-only inspect. Hypotheses H1–H4 defined. 2023 continuation failure identified as dominant unexplained mode. ATR gate addresses 2021 but not 2023. Classification: BOUNDARY_HYPOTHESIS_PARTIAL_NEEDS_ATTRIBUTION. Recommendation D. |
| CPM-FCX-001 | CPM-1 Read-only Feature-Context Extraction | COMPLETE | Claude | Docs-only read-only feature extraction. 329 positions, 47 features. 2023 failure is continuation-dominated (MFE 4.26 vs 406). 2025 fragility structural. Classification: FEATURE_CONTEXT_SUPPORTS_BOUNDARY_HYPOTHESIS_INSPECT. |
| CPM-CPA-001 | CPM-1 Continuation Failure Pre-Observable Proxy Attribution | COMPLETE | Claude | Docs-only attribution. 7 proxy candidates evaluated. No credible pre-observable continuation proxy found. Bar range is POST_HOC. 2023 failure invisible before entry. Classification: CONTINUATION_PROXY_POST_HOC_ONLY. Recommendation D. |
| CPM-CMC-001 | CPM-1 Choppiness & Macro Context Attribution Closeout | COMPLETE | Claude | Docs-only closeout. CHOP adds nothing (POST_HOC_OR_REDUNDANT). H2 remains POST_HOC. H5-MACRO-LONG-BIAS-CONTEXT is PLAUSIBLE (2022 macro downtrend: 0% overlap d3_dist_EMA200). 2021 mod-ATR losses: macro overextension. Hurst ~0.50 everywhere. Classification: BOUNDARY_ATTRIBUTION_PARTIAL_KEEP_RESEARCH_ONLY. Recommendation D. |
| CPM-H5RA-001 | CPM-1 H5 Macro-Context Robustness Attribution | COMPLETE | Claude | Docs-only robustness review. H5_PARTIAL_BUT_INCOMPLETE. 1D macro context partially explains 2022 (multi-dimensional separation confirmed); 3D EMA200 finding is warmup/sample-caveated (20.2% coverage); 2023 remains unexplained; no frozen diagnostic authorized. Recommendation D. |
| CPM-CLOSE-001 | CPM-1 OHLCV Boundary Research Closeout And Owner Decision Memo | COMPLETE | Claude | Docs-only closeout. CPM_OHLCV_BOUNDARY_ATTRIBUTION_PAUSED_RESEARCH_EVIDENCE_PRESERVED. 12-step evidence chain consolidated. OHLCV boundary attribution paused; research evidence preserved; no runtime/small-live candidate. Option A recommended (pause), Option C reserved (extra-data inspect) for future Owner decision. |
| DIRA-EH-001 | Direction A Sparse Trend Evidence Hardening And Winner Attribution | COMPLETE | Claude | Docs-only evidence-hardening review. Classification: POSITIVE_SPARSE_TREND_EVIDENCE / NEEDS_TE_HARDENING. 173 trades, net +3001.66, PF 1.517. Top-3 removal net negative (-443.91). TE-001 9-layer review applied. Top winners thesis-consistent across 4 distinct macro regimes. Loss tail bounded (worst -133.30). No pre-observable applicability boundary. SRR-002 not met. Recommends Owner Option A (Preserve), B (TE-001 full review), or C (boundary hypothesis study). |
| DIRA-XA-001 | Direction A Cross-Asset Transfer Diagnostic Plan | COMPLETE | Claude | Docs-only frozen diagnostic plan. Defines frozen mechanism transfer test for BTC and SOL. Classification: MECHANISM_VALIDATION_PLAN_ONLY. Frozen rule: 4h Donchian20 → EMA60. 11 required sections: purpose, frozen rule, asset roles, data coverage, windows, metrics, interpretation rules, fragility, SRR-002 compliance, readiness, prohibitions. Readiness upgraded from NEEDS_DATA_COVERAGE_AUDIT_FIRST to READY_FOR_OWNER_APPROVED_CROSS_ASSET_DIAGNOSTIC after DIRA-XA-002 audit. |
| DIRA-XA-002 | Direction A Cross-Asset Data Coverage Audit | COMPLETE | Claude | Read-only data coverage audit. BTC: 10,956/10,956 bars (100%), zero gaps — DATA_READY_FULL_BASE_WINDOW. SOL: 10,926/10,956 bars (99.7%), 30 bars missing in 2022 (two 3–5 day gaps) — DATA_READY_ADJUSTED_WINDOW. All OHLCV quality checks pass. No data fetch or repair required. Overall: READY_FOR_OWNER_APPROVED_CROSS_ASSET_DIAGNOSTIC. Audit does not authorize diagnostic execution. |
| DIRA-XA-003 | Direction A Cross-Asset Frozen Diagnostic Result | COMPLETE | Claude | Frozen diagnostic completed. BTC: 159 trades, 40 winners, net +2,517.17, PF 1.477, payoff 4.39:1, top-3 removal NEGATIVE, 2023 = 95.7% of net. SOL: 158 trades, 44 winners, net +4,018.80, PF 1.790, payoff 4.64:1, top-3 removal POSITIVE (+380.21), top-5 removal NEGATIVE. Both pass sparse trend acceptance band. Classification: CROSS_ASSET_SUPPORTS_MECHANISM / NON_RUNTIME. No pre-observable applicability boundary. No runtime, small-live, or portfolio authorization. Direction A is archived as positive cross-asset sparse trend evidence, pause-fragile and non-runtime. This update does not authorize Direction A changes, further diagnostics, parameter optimization, portfolio work, runtime use, small-live use, TE execution, CPM reopening, or strategy rescue. |

## Direction A Mechanism Attribution Diagnostics

This section records a staged research roadmap after DIRA-XA-003 cross-asset
positive sparse trend evidence. It incorporates external quant feedback as
advisory diagnostic input only. It does not authorize Direction A changes,
parameter optimization, portfolio construction, runtime use, small-live use,
TE execution, CPM reopening, extra-data work, or strategy rescue.

Only P0 evidence-strength diagnostics are eligible for immediate
Owner-approved execution. P1 is blocked until P0 is complete. P2 is reserved as
risk-shape diagnosis only and must not be interpreted as deployment planning.

| ID | Task | Status | Priority | Notes |
| --- | --- | --- | --- | --- |
| DIRA-P0-PLAN | Direction A P0 Evidence Strength Diagnostics Plan | COMPLETE | P0 | Defines winner overlap and bootstrap PF CI as first diagnostic stage. Docs-only planning; no diagnostics executed by this entry. |
| DIRA-P0-001 | Direction A Cross-Asset Winner Timing Overlap | COMPLETE | P0 | Completed in `docs/ops/direction-a-p0-evidence-strength-diagnostics.md`. Classification: `WINNER_EVIDENCE_PARTIALLY_SHARED`. Top-5 raw winners 15; loose unique top-5 episodes 6; asset-adjusted loose effective observations 3.5. Evidence is materially less independent than raw winner count. |
| DIRA-P0-002 | Direction A Bootstrap PF Confidence Interval | COMPLETE | P0 | Completed in `docs/ops/direction-a-p0-evidence-strength-diagnostics.md`. Classification: `PF_CONFIDENCE_INCONCLUSIVE`. Trade-level PF p5: ETH 0.878, BTC 0.831, SOL 1.001. Combined P0 classification: `P0_EVIDENCE_STRENGTH_INCONCLUSIVE`; recommendation: Owner decision required. |
| DIRA-P1-001 | Direction A Random Entry + EMA60 Exit Control | COMPLETE | P1 | Completed in `docs/ops/direction-a-p1-edge-source-attribution.md` after separate Owner authorization. Per-asset classification: ETH/BTC/SOL all `ENTRY_ALPHA_PARTIAL`. Donchian20 entry contributes, but not decisively enough to isolate pure entry alpha. |
| DIRA-P1-002 | Direction A Buy-and-Hold / Time-in-Market Decomposition | COMPLETE | P1 | Completed in `docs/ops/direction-a-p1-edge-source-attribution.md` after separate Owner authorization. Per-asset classification: ETH/BTC/SOL all `SMART_BETA_TIMING`. Combined P1 classification: `P1_MIXED_EDGE_SOURCE`; recommendation: Owner decision required. |
| DIRA-P2-001 | Direction A Risk-Shape And Vol-Normalized Sizing Diagnostic | COMPLETE | P2 | Completed in `docs/ops/direction-a-p2-risk-shape-diagnostic.md` after separate Owner authorization. Classification: `P2_RISK_SHAPE_IMPROVES_BUT_NON_RUNTIME`; future path: `ELIGIBLE_FOR_SMALL_LIVE_DESIGN_PLAN`; recommendation: docs-only small-live design plan. This does not authorize Direction A changes, portfolio implementation, runtime, or small-live. |
| DIRA-P2-002 | Direction A MFE Distribution And Loser Characterization | RESERVED | P2 | Diagnose false breakout vs trend-death behavior. |

### Current Roadmap Interpretation

#### P0 - Evidence Strength

Immediate next stage after Owner approval.

Purpose:

- effective independent observation count;
- winner episode overlap;
- PF confidence / uncertainty.

Authorized after Owner approval:

- winner timing overlap;
- bootstrap PF CI.

#### P1 - Edge Source Attribution

Completed after separate Owner authorization.

Purpose:

- entry alpha vs exit management;
- alpha vs beta timing.

Interpretation:

- random entry controls show partial Donchian20 entry alpha across ETH/BTC/SOL;
- buy-and-hold decomposition classifies ETH/BTC/SOL as `SMART_BETA_TIMING`;
- combined result is `P1_MIXED_EDGE_SOURCE`;
- Direction A should no longer be framed as pure breakout alpha;
- Direction A remains non-runtime and non-small-live.

#### P2 - Risk Shape

Next eligible stage, subject to separate Owner approval.

Purpose:

- risk-shape diagnostic only;
- fixed-notional vs vol-normalized sizing;
- exposure caps and simultaneous signal risk;
- drawdown profile and top-winner dependence;
- no deployment implication;
- no portfolio/router implementation.

Completed roadmap stages:

- cross-asset frozen diagnostic;
- P0 evidence strength diagnostics;
- P1 edge-source attribution.

Still blocked:

- runtime;
- small-live;
- portfolio implementation;
- router/regime engine;
- parameter optimization;
- more assets;
- TE execution;
- CPM reopening.

This roadmap update does not authorize more assets, Direction A variants,
parameter optimization, regime gates, vol targeting implementation,
portfolio/router work, runtime, small-live, TE execution, CPM reopening, or
extra-data work.

## Strategy Research Methodology Baseline

**Current baseline:** SRR-002 (accepted 2026-05-08).

SRR-002 defines the methodology standards that any future strategy research must satisfy before Level 3 admission. Key standards:

1. **Pre-observable applicability boundary** (SRR-002 Sec 2): A boundary must be computable before the trade decision, not post-hoc selected, must survive realistic costs, trade/winner floors, top-3/top-5 removal, winner/year concentration checks, and must explain both valid and invalid states.

2. **Independent alpha vs overlap echo** (SRR-002 Sec 3): Signal-set distinctness is not enough. Non-overlapping signals must produce positive net PnL with PF >= 1.0, >= 10 winners, and >= 30% of total positive PnL attribution.

3. **Sparse trend fragility** (SRR-002 Sec 4): Top-3/top-5 removal failure is a deployment / small-live / validated-boundary blocker, not an automatic research rejection. For sparse trend systems, positive net PnL, PF > 1, thesis-consistent top winners, controlled risk relative to Owner tolerance, and enough trade count may justify preserving the module as `POSITIVE_SPARSE_TREND_EVIDENCE` / `PAUSE_FRAGILE` or `POSITIVE_CROSS_ASSET_SPARSE_TREND_EVIDENCE` / `PAUSE_FRAGILE`. Top-winner attribution (year/regime context, thesis consistency, event/artifact check, overlap echo check, non-overlap signal performance) remains mandatory. Direction A is now archived as `POSITIVE_CROSS_ASSET_SPARSE_TREND_EVIDENCE / PAUSE_FRAGILE / NON_RUNTIME` (DIRA-EH-001, DIRA-XA-003).

4. **Conditional module evidence** (SRR-002 Sec 5): A conditional module must have a validated pre-observable boundary, no post-hoc fitting penalty, valid-state fragility passage, and invalid-state explanation. Dynamic enablement discussion requires all prerequisites satisfied.

5. **Extra-data dependency** (SRR-002 Sec 6): Extra data is legitimate only with a named hypothesis addressing a specific OHLCV ambiguity. Rescue narrative (proposed after failure without named hypothesis) is rejected.

6. **Level 3 admission gate** (SRR-002 Sec 7): 10 requirements including frozen mechanism, clear information gain, failure closure statement, no variants if failed, no runtime interpretation, no automatic promotion, pre-observable applicability hypothesis, overlap/independence plan, pre-registered fragility gates, and declared data dependency.

7. **TE path framing** (SRR-002 Sec 8): TE-007A remains a separate evidence-hardening path. Must not be framed as promotion or small-live readiness. TE-005 2019-Q4 data inconsistency must be resolved or supplemental window adjusted before TE-007A execution.

**No current module satisfies SRR-002 standards.** Small-live readiness gate remains unmet. There is no runtime candidate and no deployable small-live strategy.

**This archive/update does not authorize:** new experiments, backtests, strategy scripts, adapters, parameter sweeps, data pipelines, runtime/profile/risk/backtester-core changes, strategy promotion, small-live interpretation, or automatic backlog promotion.
