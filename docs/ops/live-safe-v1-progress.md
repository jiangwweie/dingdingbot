# Live-safe v1 Progress

Use this file for session progress and handoff notes.

## 2026-04-29

- Archived pre-live-safe docs, tests, scripts, and generated artifacts.
- Established new program-scoped planning model under `docs/ops/`.
- Adopted Codex-led, Claude-bounded execution workflow.

## 2026-04-30

- Landed `Decision Trace Backbone v0` as a minimal, non-blocking trace backbone for risk decision JSONL output.
- Added `ADR-0002` to document Decision Trace Backbone v0 semantics, scope, and non-goals.
- Landed `LS-001` so the main runtime starts isolated order-watch tasks and exchange order updates can enter the local lifecycle path in real time.
- Landed `LS-002` so runtime daily risk limits now update from projected exit deltas and full position lifecycle closes.
- Kept scope tight: no `api.py` order-watch coverage, no trace expansion, no strategy/risk/profile changes.
- Deferred known follow-ups instead of expanding scope: duplicate `watch_orders` definition cleanup and re-evaluation of one-task-per-symbol if runtime symbol count grows.

## Next

- Keep the live-safe backbone thin; do not widen trace or order-watch into larger subsystems yet.
- Use the post-merge hardening ADR and task board entries as the backlog for the next iteration:
  - trace boundary cleanup
  - multi-symbol order-watch hardening
  - daily stats persistence before live expansion

## 2026-05-06

- Started LS-002b / LS-107 implementation after Owner approved the task card.
- Implemented direction: PG aggregate + event ledger, fixed `scope_key="runtime:default"`, no-new-entry fail-closed on daily stats persistence restore/write-through failure.
- Preserved LS-002 daily stats semantics and documented the accepted non-transactional crash/write window in ADR-0004.
- Targeted tests pass for LS-002b, LS-002 daily limits, and TM-002 exit projection observability.
- Alembic revision graph has single head `008` (LS-002b = 007, LS-003d = 008); local `alembic upgrade head` is blocked by existing SQLite schema/version drift at old revision `002`, before the LS-002b migration runs.
- Implemented LS-003d periodic reconciliation read model persistence as dedicated PG read-only report + mismatch tables. Consistent, mismatch, and fetch-failure reports persist best-effort; persistence failure remains report-only and does not affect runtime behavior. ADR-0007 accepted.
- Drafted CPM-CRITERIA-001 as a planning-only CPM-1 promotion/rejection/pause/observation criteria document; no code, experiment, runtime, risk, or strategy changes.

## 2026-05-06 (CPM-OOS)

- Ran CPM-OOS-RUN-001: 2022 full-year OOS backtest on frozen CPM-1 baseline.
- Result (from result.json ground truth): -971.71 USDT (-9.72%), 61 trades, WR 31.1%, PF 0.624, MaxDD 10.48%, Sharpe -1.399, Sortino -0.414.
- Classification: OOS_NEGATIVE — Require additional evidence (caveated: PnL clean, cost composition unreliable).
- 2022 is an extreme bear year; result is consistent with failure hypothesis but does not disprove profit hypothesis for bull/sideways markets.
- Codex verification found metric misalignment between report and result.json; report revised to use result.json top-level as ground truth. Exit classification now derived from close_events[] with explicit derivation scope labels. Runtime overrides clarified (5 effective, 3 legacy/no-op). Slippage=0 anomaly flagged as reproducibility ambiguity. Small-live Candidate judgment was deferred at this point; this was later superseded by CPM-OOS-FAILURE-CLASSIFY-001, which paused CPM-1 and blocked candidate review.
- CPM-OOS-RECON-001: Resolved slippage=0 anomaly. Root cause: backtester.py:1805-1813 re-derives same slippage formula as matching engine, yielding zero. Slippage IS applied to execution prices and IS reflected in total_pnl. Estimated slippage impact ~644 USDT (largest single cost component). Evidence classification upgraded from "reproducibility ambiguity" to "caveated evidence — PnL clean, cost composition unreliable." No rerun required. No change to OOS_NEGATIVE classification or Require additional evidence conclusion.
- CPM-BT-METRIC-001: Fixed slippage cost tracking metric in backtester.py. Replaced self-referencing derivation (always-zero) with unslipped base price comparison for all order types (MARKET entry, STOP_MARKET SL, LIMIT TP, TRAILING_STOP). Added trailing exit slippage tracking. 16 unit tests pass. No trade outcomes changed. No rerun of 2022 OOS required.
- No runtime, profile, strategy, or risk rule changes.
- Artifacts: reports/oos_runs/cpm1_2022_oos/ (local-only, .gitignored), docs/ops/crypto-pullback-module-v1-2022-oos-report.md (version-controlled), docs/ops/crypto-pullback-module-v1-2022-oos-reconciliation-note.md (version-controlled).

## 2026-05-06 (CPM-OOS-2021-PLAN)

- Created CPM-OOS-2021-PLAN-001: 2021 OOS gate inspect plan for CPM-1.
- 2021 is positioned as the complementary bull-year OOS candidate to 2022's bear-year evidence.
- Pre-run data check: ETH 1h 8,760 candles, 4h 2,190 candles — complete, no gaps, no duplicates.
- Open items: exchange outage verification during May 2021 crash, Binance contract rule stability, funding model choice.
- No 2021 OOS was run. No runtime, profile, strategy, or risk rule changes.
- Artifact: docs/ops/crypto-pullback-module-v1-2021-oos-gate-inspect-plan.md (version-controlled).
- CPM-OOS-2021-PLAN-001 finalized: fixed Section 6 Decision Matrix row 3 (broken Markdown table), added caveat to Section 5.1 (negative result classification before equating with module hypothesis failure).

## 2026-05-06 (CPM-OOS-2021-RUN)

- Ran CPM-OOS-2021-RUN-001: 2021 full-year OOS backtest on frozen CPM-1 baseline.
- Result: -21.54% return, 74 positions (88 trades), WR 29.5%, PF 0.466, MaxDD 22.18%, Sharpe -2.466, Sortino -0.759.
- Corrected total_slippage_cost: 1,040.85 USDT (CPM-BT-METRIC-001 fix active, non-zero).
- Classification: OOS_NEGATIVE — Pause CPM-1 for classification. 2021 (bull year) result is worse than 2022 (bear year), directly challenging the profit hypothesis.
- Fixed TP_ROLES NameError in backtester.py (CPM-BT-METRIC-001 leftover bug: undefined TP_ROLES constant replaced with inline [OrderRole.TP1..TP5] list). No trade outcomes changed.
- No runtime, profile, strategy, or risk rule changes.
- Artifacts: reports/oos_runs/cpm1_2021_oos/ (local-only, .gitignored), docs/ops/crypto-pullback-module-v1-2021-oos-report.md (version-controlled), scripts/run_cpm1_2021_oos.py (version-controlled).

## 2026-05-06 (CPM-OOS-FAILURE-CLASSIFY)

- Completed CPM-OOS-FAILURE-CLASSIFY-001: 2021 OOS failure classification / RCA.
- Primary classification: Favorable-regime profit hypothesis failure + loss-concentration issue.
- 2021 gross edge is negative (-573.84 USDT) — cost drag amplifies but does not cause the loss.
- 2021 and 2022 failures are not isomorphic: 2022 is cost-dominated in an unfavorable regime (consistent with failure hypothesis); 2021 is signal-level in a favorable regime (contradicts profit hypothesis).
- Final state: Pause CPM-1. Small-live Candidate review blocked. Baseline remains frozen. No runtime, profile, strategy, or risk rule changes. runtime_auto_change: No.
- Artifact: docs/ops/crypto-pullback-module-v1-oos-failure-classification.md (version-controlled).

## 2026-05-06 (Strategy Candidate Gate Status)

- Live-safe Foundation can continue as the system safety foundation: trusted order state, protection state, daily risk persistence, reconciliation read models, circuit-break behavior, and replayable observability remain valid system work.
- CPM-1 did not pass the OOS gate for strategy candidacy. The frozen baseline is paused, the promotion path is stopped, and CPM-1 is not a Small-live Candidate or canary-live candidate.
- Current strategy candidate inventory: none. The project does not currently have a deployable small-live strategy candidate.
- This gate status does not trigger runtime/profile/strategy/risk changes. runtime_auto_change: No.

## 2026-05-06 (NSC-001)

- Created NSC-001: CPM-2 Candidate Direction Inspect as a docs-only, inspect-only task.
- Scope inspected only `docs/ops/**`, `archive/**`, and `reports/**`.
- Drafted CPM-2 direction report focused on ETH 1h pullback-continuation with a different entry confirmation mechanism; no Pinbar parameter rescue path.
- Candidate families identified for later Owner-approved experiment planning: one-bar continuation reclaim, Donchian-location pullback confirmation, and a low-density two-candle pullback-end pattern.
- No backtests, strategy implementation, runtime/profile changes, risk rule changes, or promotion conclusions.
- Current state remains: no deployable small-live strategy candidate; small-live readiness gate unmet until a new candidate module passes a minimum evidence gate.

## 2026-05-06 (NSC-002)

- Created NSC-002: CPM-2 Minimal Experiment Plan Draft as Proposed / Experiment Plan Only.
- Drafted minimal experiment plans for Candidate A (One-Bar Continuation Reclaim) and Candidate B (Donchian-Location Pullback Confirmation).
- Candidate C remains reserve-only and does not enter the first experiment round unless A/B are rejected or paused and Owner approves a new plan.
- Plan defines frozen rules, one allowed sensitivity check per candidate, required windows, cost model, same-bar policy, required metrics, trade-count floors, pass/pause/reject gates, anti-overfit rules, and failure classification format.
- Explicitly constrained Candidate A away from reclaim-rule combination search and Candidate B away from E4 hard-filter revival / Donchian breakout interpretation.
- No backtests, strategy implementation, runtime/profile changes, risk rule changes, research-engine changes, or promotion conclusions.
- Current state remains: no deployable small-live strategy candidate; small-live readiness gate unmet until a new candidate module passes an Owner-approved minimum evidence gate.

## 2026-05-09 (Observation + Research Methodology Reset)

- Confirmed current phase label: `Observation + Research Methodology Reset`.
- Confirmed current mainline: Direction A BTC+ETH Phase 1 observation design only.
- Reaffirmed SRR-002 as the guiding methodology for future analysis; acceptance is docs-only and does not authorize experiments, parameter optimization, runtime, or small-live.
- Produced a docs-only roadmap reconciliation snapshot for Owner review.
- Local git state shows one untracked research doc, not 21 visible untracked research docs: `docs/ops/direction-a-btc-eth-phase1-observation-design-consolidation.md`.
- No strategy, experiment, execution, paper/testnet/live trading, portfolio/router, SOL Phase 2, CPM, or short-side action was started.
- Added the docs-only reconciliation snapshot and concise BTC+ETH Phase 1 Owner review brief. After creating those Owner-review artifacts, local visible untracked docs are three: BTC+ETH consolidation, reconciliation snapshot, and Owner review brief.
