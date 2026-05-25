# Live-safe v1 Task Board

Status values: `TODO`, `SPEC`, `IMPLEMENTING`, `TESTING`, `REVIEW`, `MERGED`, `BLOCKED`, `REJECTED`.

## Current Mainline Confirmation

2026-05-25 boundary update: ADR-0009 supersedes the older global docs-only
execution boundary. Real live trading remains prohibited unless separately and
explicitly authorized. Runtime, paper, testnet, tiny-live-style, read-only
exchange sync, and other non-real-live work may be executed after reasonable
scoped verification and explicit Owner authorization for the specific action.

As of 2026-05-09, the current phase label is `Observation + Research
Methodology Reset`.

The only current mainline strategy-research object recorded at that time was
BTC+ETH Phase 1 observation design for Direction A. That entry did not
authorize strategy runtime, paper/testnet/live trading, small-live execution,
portfolio/router work, SOL Phase 2, CPM reopening, short-side work, parameter
optimization, or runtime/profile/risk changes. Future non-real-live execution
can be requested under ADR-0009.

SRR-002 is accepted as the guiding methodology for future analysis. Acceptance
is docs-only and does not itself satisfy SRR-002 standards for any module.

## Milestones

- `Decision Trace Backbone v0` completed: minimal decision trace backbone added; risk decisions can be written to JSONL without affecting trading behavior on trace failure.
- `ADR-0002` completed: documented Decision Trace Backbone v0 semantics, scope, and non-goals.
- `LS-001` completed: main runtime order-watch enabled with isolated WS state; `api.py` out of scope; duplicate `watch_orders` definition remains as later cleanup.
- `LS-002` completed: runtime daily risk limits now update from projected exit deltas and full position closes; UTC reset and replay-safe accounting are active; v0 remains process-local in-memory state.

## Personal Leveraged Campaign Local Sandbox

These tasks are currently docs/design/sandbox/test only. They do not by
themselves authorize exchange access, paper/testnet/tiny-live-style execution,
real account data, runtime profile changes, order placement, order
cancellation, transfer, withdrawal, or direct research-to-order wiring. Such
non-real-live steps may be requested separately under ADR-0009.

| ID | Task | Status | Owner | Notes |
| --- | --- | --- | --- | --- |
| PLC-001 | Minimum local campaign chain sandbox | REVIEW | Codex | Adds disabled-by-default local objects, explicit `CampaignSandboxSettings(enabled=False)` guard, sandbox trace loop, repeatable scenario catalog, and trace invariant evaluator for `ModeAdvice -> HumanArmDecision -> StrategyContract -> TradeIntent -> RiskOrderPlan -> ExecutionReceipt -> PositionLifecycleState -> CampaignState`; targeted tests cover allow/reject, pause, hard-lock, profit-protect reduce/close, default-disabled, no-side-effect, catalog scenarios, and invariant pass/fail checks. Withdrawal is Owner-external and not modeled. |
| PLC-GOV-001 | Branch and document governance for current PLC mainline | REVIEW | Codex | Adds current branch/document governance note. Classifies active/protected/frozen/stale branches and current SSOT/active governance/runtime foundation/historical evidence docs without deleting branches or physically moving docs. |
| PLC-SCHEMA-001 | Local PLC schemas, risk matrix, and promotion checklist | REVIEW | Codex | Adds local JSON schemas for core PLC objects, rule matrix for order/position/campaign/profit-protection enforcement, and promotion checklist requiring scoped verification plus explicit Owner authorization before runtime/account stages. |
| PLC-SQ02-001 | SQ02 docs-only StrategyContract skeleton and examples | REVIEW | Codex | Adds SQ02 skeleton plus local schema examples parsed by unit tests against the local campaign Pydantic models. Scanner, alert, runtime, paper/testnet/tiny-live-style, account, leverage, sizing, or order-path use requires a separate ADR-0009 action request. |
| PLC-FEATURE-001 | Closed/prior FeatureSnapshot boundary for SQ02 local sandbox | REVIEW | Codex | Adds local `FeatureSnapshot` model/schema/example and routes sandbox contract evaluation through it. Feature snapshots forbid lookahead, LLM trade decisions, real account state, and exchange API state. |
| PLC-UPGRADE-001 | PLC phased upgrade ladder | REVIEW | Codex | Adds `docs/ops/plc-phased-upgrade-v0.md`. Phase 0 local sandbox is REVIEW; Phase 1 read-only runtime adapter is implemented for review; Phase 2 paper observation, Phase 3 testnet rehearsal, and Phase 4 tiny-live-style review remain gated. |
| PLC-RUNTIME-001 | PLC read-only runtime adapter implementation | REVIEW | Codex | Implements a pure read-only adapter from `FeatureSnapshot + StrategyContract` to `ReadOnlyRuntimeAdapterPreview` / `TradeIntent`. It rejects future snapshots, non-frozen contracts, and contract/snapshot mismatch; it has no order/exchange authority and imports no I/O frameworks. |
| PLC-PAPER-001 | PLC paper observation packet | REVIEW | Codex | Implements paper-only packets around read-only previews. Packets carry review status, operator notes, optional review provenance, `paper_observation_no_order_authority`, and explicit prohibited actions for order placement/cancellation, exchange mutation, real account read, and runtime profile changes. |
| PLC-TESTNET-001 | PLC Phase 3 testnet rehearsal package | REVIEW | Codex | Phase 3 retry completed under Owner ADR-0009 authorization on Binance testnet. One controlled ENTRY and one reduce-only controlled EXIT completed through runtime; protection cleanup terminalized 3 rows, daily stats updated, final Binance read-only state was flat with open orders `0`, local active orders/positions were `0`, latest reconciliation read model was consistent with severe `0` and warning `0`, and runtime was stopped. Phase 4 tiny-live-style review remains separately blocked. |
| PLC-PHASE4-001 | PLC Phase 4 tiny-live-style readiness review | REVIEW | Codex | Owner authorized Phase 4 review. P4-001 through P4-004 now have runtime code plus non-real-live testnet smoke evidence: account/campaign gates active, conditional SL visible during active exposure, runtime close cancels Binance conditional SL via stop-order fallback, and shutdown releases the API port naturally. Real live remains not authorized and still blocked by no promoted strategy contract. |
| ARCH-P4-001 | Runtime/API composition root governance | REVIEW | Codex | Adds ADR-0010 and `RuntimeContext`; embedded `main.py` is now the only execution-runtime composition root, API receives context via `app.state.runtime`, and standalone uvicorn is degraded to HTTP/config/read-only mode instead of creating exchange/orchestrator runtime wiring. Acceptance repair covers legacy context aliases and stale compatibility-global cleanup. Targeted 87-test regression and no-order lifecycle smoke passed. No runtime profile, strategy parameter, or trading-permission change. |
| PLC-PHASE5-001 | PLC Phase 5 small-scale rehearsal readiness | REVIEW | Codex | Owner approved the recommended 1/2/3 path and authorized bounded testnet. Adds Phase 5A design, treats `dev` as the current unpushed integration candidate, upgrades account-risk to account-scope position/exposure checks, adds runtime-event campaign transitions, and adds a Strategy Contract promotion gate that preserves no-order authority. Bounded Binance testnet smoke passed after these changes: one controlled entry, one runtime controlled close, final positions `0`, active local orders `0`, restored controls, clean shutdown. Real live remains not authorized. |
| PLC-PHASE5B-001 | PLC Phase 5B repeated testnet rehearsal | REVIEW | Codex | Owner authorized Phase 5B. Adds repeated testnet rehearsal design, symbol-scoped order-watch running state, symbol-indexed recent order-update evidence, and a pure symbol-isolation audit. Two Binance testnet cycles passed with controlled entry, runtime controlled close, final flat state, active local orders `0`, restored controls, clean shutdown, and port release. Multi-symbol runtime remains blocked. |
| PLC-PHASE5C-001 | PLC Phase 5C two-symbol synthetic fixture proof | REVIEW | Codex | Adds local BTC/ETH synthetic fixture proof for reconciliation and runtime read models. Positions, orders, and execution intents respect symbol filters; portfolio remains account-level aggregation. Multi-symbol runtime remains blocked; no testnet or real-live action is authorized by this proof. |

## Non-Real-Live Action Requests

These tasks require scoped verification and explicit Owner authorization before
execution under ADR-0009.

| ID | Task | Status | Owner | Notes |
| --- | --- | --- | --- | --- |
| TC-TINY-001D-1 | Controlled Binance testnet order-lifecycle smoke | REVIEW | Codex | Executed after Owner authorization under ADR-0009. One `sim1_eth_runtime` Binance testnet controlled endpoint call completed with `amount=0.01`, `attempt_locked=true`, ENTRY filled, exchange-native TP/SL mounted, GKS restored, direct testnet cleanup closed the residual position, reconciliation cleared runtime positions, and runtime was stopped. Follow-up observations: testnet SL `fetch_order` confirmation miss after STOP_MARKET submission, PG protection-order rows stale `OPEN` after external cleanup, periodic reconciliation `severe=830` / `warning=2995`, protection-health critical block `PROTECTION_LOCAL_SL_MISSING_ON_EXCHANGE` count `829`, and no daily-risk update for the unresolved external close. |
| TC-TINY-001D-2 | External-close local order hygiene follow-up | REVIEW | Codex | Implemented local-only hygiene for exchange-flat external close and closed-position stale protection rows. Active local TP/SL rows for the same signal are system-terminalized to `CANCELED` with audit metadata; startup/periodic reconciliation refreshes the read model before protection-health evaluation; healed read models clear stale protection-health blocks. Historical PG cleanup terminalized 2174 stale ETH protection rows and wrote 2174 audit rows. Follow-up testnet verification executed one more controlled endpoint (`intent_55db456b02ac`, `sig_d191164ff9bc`, amount `0.01`), cleaned exchange flat, then startup/periodic reconciliation terminalized the remaining 3 TP/SL rows, position closed with realized PnL, daily stats updated, periodic reconciliation reported `severe=0`, active stale protection rows without active position remained 0, and runtime stopped. Tests: targeted 82 passed; compileall and `git diff --check` passed; Binance testnet read-only verification: `positionAmt=0.000`, open orders 0. |

## Current Planning Snapshot

This snapshot reflects the state after `TC-TINY-001D-2`. It does not authorize
real live trading. Any runtime, testnet, paper, or exchange-connected action
still requires the ADR-0009 scoped action gate.

### Short-Term Tasks

| ID | Task | Status | Owner | Notes |
| --- | --- | --- | --- | --- |
| TC-TINY-001D-3 | Historical local open-order warning cleanup | REVIEW | Codex | Completed local PG-only cleanup after query proof: backed up 821 stale `ETH/USDT:USDT` `OPEN` ENTRY rows with no active position to `ops_backup_orders_tiny001d3_20260525`, terminalized them to `CANCELED`, and wrote 821 audit rows with `historical_local_entry_warning_cleanup` metadata. Post-check active stale ENTRY count is 0. No exchange mutation. |
| TC-TINY-001D-4 | Runtime-managed close smoke | REVIEW | Codex | Implements `OrderRole.EXIT`, `ExecutionOrchestrator.execute_controlled_close()`, and `POST /api/runtime/test/smoke/execute-controlled-close`. It persists a reduce-only EXIT order, places the market close through `ExchangeGateway`, projects the exit, updates daily stats, terminalizes protection orders, and enforces once-per-session execution. Targeted Phase 3 verification passed: 126 tests, compileall, and `git diff --check`. |
| TC-TINY-001D-5 | STOP_MARKET confirmation fallback hardening | REVIEW | Codex | Hardened `ExchangeGateway.confirm_order_exists` to accept recent order-watch evidence before REST, and to use bounded `fetch_open_orders` retry after a `fetch_order` miss. Targeted STOP_MARKET confirmation tests pass. |
| PLC-RUNTIME-001 | PLC local chain to read-only runtime adapter | REVIEW | Codex | Spec and implementation are ready. `src/application/personal_campaign_runtime_adapter.py` builds read-only `TradeIntent` previews only; schema/example/tests added. It explicitly forbids exchange/order authority and requires a separate ADR-0009 action before paper/testnet execution. |
| LS-003 | Structured runtime logs task card refresh | REVIEW | Codex | Refreshed Claude task card in `docs/ops/ls-003-structured-runtime-logs-task-card.md` for external-close hygiene, stale protection terminalization, protection-health healing, and secret-free structured event tests. |

### Long-Term Tasks

| ID | Task | Status | Owner | Notes |
| --- | --- | --- | --- | --- |
| PLC-LT-001 | Full PLC promotion ladder | REVIEW | Codex | Phase 0 local sandbox, Phase 1 read-only adapter, Phase 2 paper observation packet, Phase 3 Binance testnet rehearsal, and Phase 4 P4-001 through P4-004 non-real-live hardening/smoke are complete for review. Real live remains not authorized; next work is P4-005 rehearsal design and strategy-promotion governance only. |
| P4-001 | Runtime account risk gate | REVIEW | Codex | Implemented `AccountRiskService`, liquidation-price parsing, and fail-closed orchestrator gate before `CapitalProtection`. Targeted account-risk/orchestrator tests pass; active testnet controlled entry passed the runtime gate. |
| P4-002 | Durable campaign state machine | REVIEW | Codex | Implemented `runtime_campaign_state` PG migration, repository, service, owner-control API, and new-entry gate. Clean Alembic PG upgrade now reaches `010 (head)` after repairing older migration ordering/constraint drift; active testnet smoke armed campaign state for entry and reset it to `observe` after close. |
| P4-003 | Conditional protection visibility hardening | REVIEW | Codex | Reconciliation now fetches normal plus conditional STOP_MARKET open-order views and dedupes payloads before protection-health checks. Active testnet smoke observed position qty `0.01`, normal open orders `2`, stop open orders `1`, periodic reconciliation `consistent`, and no protection-health missing/orphan block. Runtime close now cancels conditional SL through a Binance stop-order fallback; final testnet state was flat with normal open `0` and stop open `0`. |
| P4-004 | Runtime control lifecycle reset | REVIEW | Codex | Added startup-guard block/reset control API, shutdown reset to `RUNTIME_SHUTDOWN_RESET`, centralized signal cleanup, resource closure, and event-loop default-executor shutdown. No-order and active-position testnet smokes both exited naturally, released port `8001`, and logged no non-daemon thread warning. |
| P4-005 | Phase 4 non-real-live rehearsal design | REVIEW | Codex | Superseded by Phase 5A small-scale rehearsal readiness design. `docs/ops/plc-phase5-small-scale-rehearsal-design.md` names exact commands, caps, stop conditions, rollback path, testnet-only boundary, and explicit real-live non-authorization. |
| P5-001 | Phase 5 small-scale rehearsal readiness | REVIEW | Codex | Phase 5A design added in `docs/ops/plc-phase5-small-scale-rehearsal-design.md`. First gates were smoked on bounded Binance testnet after implementation. Repeated/longer rehearsal remains a separate Owner gate. |
| P5-002 | Phase 5B repeated testnet rehearsal | REVIEW | Codex | Phase 5B design added in `docs/ops/plc-phase5b-repeated-testnet-rehearsal.md`. Local symbol-isolation tests passed and two repeated Binance testnet cycles passed. Longer/multi-symbol rehearsal remains a separate Owner gate. |
| P5-003 | Phase 5C two-symbol synthetic fixture proof | REVIEW | Codex | Phase 5C design added in `docs/ops/plc-phase5c-two-symbol-synthetic-fixture-proof.md`. Local BTC/ETH fixture passed for reconciliation, runtime read-model filters, and account-level portfolio aggregation. |
| PLC-LT-002 | Campaign risk state machine | REVIEW | Codex | Spec added in `docs/ops/plc-campaign-risk-state-machine-spec.md`. Runtime now has PG-backed state, entry gate, owner-control API, and runtime-event transitions for entry-filled, profit-protect, stop-loss lock, position close, and risk-critical. Full automatic wiring from every order lifecycle event remains future work. |
| LS-006 | Account risk state machine | REVIEW | Codex | Account risk now reads account-scope positions where available, blocks on unknown/degraded/critical liquidation state, and can block on total exposure cap. It remains an entry gate only; richer margin ratio and daily-loss cross-checks remain future work. |
| LS-007 | Liquidation distance and margin safety checks | REVIEW | Codex | Side-aware liquidation distance checks are implemented and unit-tested. Larger notional or multi-position rehearsal remains blocked until Phase 5 symbol/account isolation evidence is accepted. |
| RUNTIME-LT-001 | Multi-symbol runtime readiness | REVIEW | Codex | First hardening landed: order-watch running state is symbol-scoped and recent order-update evidence is symbol-indexed. Phase 5C local BTC/ETH fixture now proves reconciliation/read-model symbol filtering, but exchange-connected multi-symbol runtime remains blocked until separate Owner authorization, runtime profile/config review, and account-risk cap review. |
| RESEARCH-LT-001 | Opportunity evidence to strategy-contract pipeline | REVIEW | Codex | Adds pure Strategy Contract promotion gate for reviewed paper-observation packets. It can mark a contract eligible for the next non-order review gate, but it explicitly grants no order/exchange/account/profile or real-live authority. |

## P0

| ID | Task | Status | Owner | Notes |
| --- | --- | --- | --- | --- |
| LS-001 | Start `watch_orders` | MERGED | Codex | Main runtime order-watch enabled with isolated WS state; `api.py` out of scope; duplicate `watch_orders` definition remains as later cleanup. |
| LS-002 | Make daily max loss/trades effective | MERGED | Codex + Claude tests | Runtime projected daily PnL and full-close trade counts now drive daily limit rejects; persistence deferred to LS-002b. |
| LS-003 | Structured runtime logs | READY | Claude | Codex task card is ready in `docs/ops/ls-003-structured-runtime-logs-task-card.md`. |
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
