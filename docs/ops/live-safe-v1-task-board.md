# Live-safe v1 Task Board

Status values: `TODO`, `SPEC`, `IMPLEMENTING`, `TESTING`, `REVIEW`, `MERGED`, `BLOCKED`, `REJECTED`.

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
