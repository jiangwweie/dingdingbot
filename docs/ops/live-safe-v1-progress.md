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

## 2026-05-25 (PLC-001 Local Campaign Sandbox)

- Implemented the first Personal Leveraged Campaign local sandbox loop:
  `ModeAdvice -> HumanArmDecision -> StrategyContract -> TradeIntent -> RiskOrderPlan -> ExecutionReceipt -> PositionLifecycleState -> CampaignState`.
- Added disabled-by-default local domain contracts, deterministic sandbox functions, and an explicit `CampaignSandboxSettings(enabled=False)` runner guard only; no runtime profile, exchange gateway, execution orchestrator, real API, account, order, transfer, or withdrawal path is touched.
- Added targeted tests for allow/reject, pause, hard-lock, loss-lock, profit-protect reduce/close, default-disabled, no-side-effect, repeatable scenario-catalog cases, and trace invariant pass/fail checks.
- Recorded the docs/design boundary in `docs/ops/personal-leveraged-campaign-local-sandbox-v0.md`.

## 2026-05-25 (PLC-GOV-001 Branch And Document Governance)

- Added current branch/document governance note aligned to `docs/ops/project-roadmap-v2.md` and the accepted Personal Leveraged Campaign mainline.
- Classified local branches into active, protected, frozen research evidence, stale duplicate labels, and deletion candidates; no branch was deleted.
- Classified docs into current SSOT, active governance, active research context, runtime safety foundation, and historical evidence; no documents were physically moved.

## 2026-05-25 (PLC-SCHEMA-001 Schemas And Promotion Checklist)

- Added local JSON schemas for `ModeAdvice`, `HumanArmDecision`, `StrategyContract`, `TradeIntent`, `RiskOrderPlan`, `ExecutionReceipt`, `PositionLifecycleState`, and `CampaignState`.
- Added risk rule matrix covering order-plan, position-lifecycle, campaign, and profit-protection enforcement boundaries.
- Added promotion checklist confirming no runtime, paper, testnet, live, tiny-live, real account, real order, or real withdrawal candidate exists.
- Added schema-doc tests for parseability and disabled/local-only safety fields.

## 2026-05-25 (PLC-SQ02-001 SQ02 Contract Skeleton)

- Added docs-only `SQ02_DOWNSIDE_CONT_V0` StrategyContract skeleton.
- Added SQ02 schema examples for StrategyContract, ModeAdvice, HumanArmDecision, TradeIntent, RiskOrderPlan, and CampaignState.
- Added schema-example tests that parse examples through local campaign Pydantic models and verify default-disabled, no-exchange-side-effect, protection, and Owner-confirmation boundaries.

## 2026-05-25 (PLC-SCOPE-001 Withdrawal Out Of Scope)

- Owner clarified that withdrawals are handled manually by Owner and should not be modeled by the system.
- Removed active `WithdrawalInstruction` model, schema, example, sandbox generation path, and tests.
- Reframed the local chain endpoint as `CampaignState` with profit-protect reduce/close requirements only.

## 2026-05-25 (PLC-FEATURE-001 Feature Snapshot Boundary)

- Added local `FeatureSnapshot` model, JSON schema, and SQ02 example.
- Routed sandbox `StrategyContract` evaluation through `FeatureSnapshot` instead of a bare conditions dict.
- Added tests for closed/prior-only snapshot parsing, LLM decision rejection, and strategy-contract mismatch rejection.

## 2026-05-25 (PLC Local Chain Verification)

- Verified the local PLC mock/sandbox chain end to end through the repeatable scenario catalog:
  `allow_open_protected`, `reject_contract_invalidated`, `reject_order_caps`,
  `pause_blocks_session`, `hard_lock_missing_protection`, and
  `profit_protect_reduce`.
- Local smoke summary: all six scenarios produced invariant report `pass` with
  `runtime_effect=none`, `trading_permission_effect=none`, and no exchange,
  account, order, transfer, or withdrawal side effect.
- Targeted tests passed:
  `pytest -q tests/unit/test_personal_campaign_sandbox.py tests/unit/test_personal_campaign_schema_docs.py tests/unit/test_personal_campaign_schema_examples.py`
  -> 28 passed.
- Extended boundary tests passed:
  `pytest -q tests/unit/test_tiny001d1a_controlled_signal_injection.py tests/unit/test_tiny001d4_once_per_session_guard.py tests/unit/test_personal_campaign_sandbox.py tests/unit/test_personal_campaign_schema_docs.py tests/unit/test_personal_campaign_schema_examples.py`
  -> 61 passed.
- `python3 -m compileall -q src/domain/personal_campaign.py src/application/personal_campaign_sandbox.py`
  passed.
- `git diff --check` passed.
- No core execution files, runtime profiles, env files, exchange gateway, real
  account path, testnet order path, or credentials were modified.
- Testnet smoke was not executed in this PLC verification because, at that
  point, the PLC mainline was still treated as docs/design/sandbox only and
  `TC-TINY-001D-1` was still a separate Owner-approval boundary for first
  testnet ENTRY. ADR-0009 later clarified that non-real-live testnet work may
  be requested after scoped verification and explicit Owner authorization.

## 2026-05-25 (ADR-0009 Non-Real-Live Boundary Clarification)

- Owner clarified the execution boundary: except for real live trading, all
  development and research work may proceed after reasonable scoped testing and
  explicit Owner authorization for the specific action.
- Added ADR-0009 to distinguish non-real-live runtime/paper/testnet/
  tiny-live-style work from prohibited real live trading.
- Updated roadmap, Live-safe program, runtime safety boundary, promotion gate,
  PLC mainline, PLC checklist, PLC sandbox note, task board, and AGENTS.md to
  use the new action gate.
- No runtime code, runtime profile, env file, exchange gateway, credentials, or
  order path was changed by this boundary clarification.

## 2026-05-25 (TC-TINY-001D-1 Authorization Package)

- Prepared ADR-0009 action request for one controlled Binance testnet
  order-lifecycle smoke:
  `docs/ops/tc-tiny-001d-1-adr0009-authorization-request.md`.
- Updated the older `docs/ops/TC-TINY-001D-1-proposal.md` to mark it as
  superseded for execution authorization and to reflect that the controlled
  endpoint already exists.
- Verified current controlled endpoint tests:
  `pytest -q tests/unit/test_tiny001d1a_controlled_signal_injection.py tests/unit/test_tiny001d4_once_per_session_guard.py`
  -> 33 passed.
- Verified `python3 -m compileall -q src/interfaces/api_console_runtime.py` and
  `git diff --check` passed.
- No runtime, testnet, account, credential, or order action was executed. The
  next step is explicit Owner authorization for the exact ADR-0009 action.

## 2026-05-25 (TC-TINY-001D-1 Authorized Testnet Smoke)

- Owner authorized the ADR-0009 action for one Binance testnet controlled
  order-lifecycle smoke under `sim1_eth_runtime`, max `0.01 ETH`, with GKS
  restore and runtime stop required after verification.
- Preflight verified `.env` / `.env.local` effective safety fields without
  printing secrets: `EXCHANGE_TESTNET=true`, `RUNTIME_PROFILE=sim1_eth_runtime`,
  and Binance testnet API key/secret present but masked.
- Initial runtime start failed because local PG was not accepting connections;
  after Owner started PG in Docker, runtime started and reached `SYSTEM READY`.
- Executed exactly one controlled endpoint call:
  `POST /api/runtime/test/smoke/execute-controlled-entry`.
- Controlled endpoint completed with:
  `intent_f45649feb9fd`, `signal_id=sig_fec09157c3cc`, `amount=0.01`,
  `testnet=true`, `profile=sim1_eth_runtime`, `attempt_locked=true`,
  `notional=20.9347`, and `min_notional=20`.
- Exchange testnet ENTRY filled:
  local order `ord_e1331c9f`, exchange order `8728148126`.
- Exchange-native protection orders were mounted:
  TP1 `ord_TP1_2730d882` / `8728148137`,
  TP2 `ord_TP2_9f28da89` / `8728148143`,
  SL `ord_sl_11671362` / `1000000084871663`.
- Risk decision audit recorded startup guard allow, GKS allow, and
  `control.test_signal_injection` executed for the controlled intent.
- GKS was restored active immediately after the controlled endpoint returned.
- Direct Binance testnet cleanup closed the residual `0.01 ETH` position with
  reduce-only market order `8728150129`; direct exchange verification reported
  `positionAmt=0.000` and zero target open protection orders.
- Runtime `/api/runtime/positions` was initially stale after direct cleanup,
  then periodic reconciliation cleared positions and produced an external close
  marker.
- PG `positions` for `sig_fec09157c3cc` was marked closed with quantity `0`,
  but the local TP1, TP2, and SL order rows remained `OPEN` and were classified
  as `stale_after_external_close` / `manual_data_hygiene_required`.
- Daily risk stats did not update for this controlled close because the cleanup
  was an external reduce-only order with `pnl_status=unresolved_no_reliable_fill`.
- Runtime was stopped after verification; no `src.main` process remained and
  local port `8000` was no longer listening.
- Observations for review:
  - periodic reconciliation after external cleanup reported `total=3825`,
    `severe=830`, and `warning=2995`;
  - protection health set a critical
    `PROTECTION_LOCAL_SL_MISSING_ON_EXCHANGE` block with count `829`;
  - SL STOP_MARKET `fetch_order` confirmation returned a Binance testnet
    "Order does not exist" response immediately after submission, while
    order-watch later observed the SL as open;
  - local stale protection-order hygiene remains open before this can be treated
    as a fully clean lifecycle smoke.
- Added follow-up `TC-TINY-001D-2` for external-close local order hygiene design
  before any implementation. Existing code is intentionally conservative:
  external close projection marks positions closed unresolved, blocks new
  entries, and preserves stale protection-order evidence instead of silently
  rewriting local order state.

## 2026-05-25 (TC-TINY-001D-2 External-Close Local Order Hygiene)

- Owner authorized continuing the follow-up with minimal manual involvement and
  allowed direct cleanup of historical local data.
- Implemented local-only external-close hygiene:
  - after reconciliation proves exchange-flat and position projection marks a
    local position unresolved-closed, active local TP/SL rows for the same
    signal are terminalized to `CANCELED`;
  - terminalization is system-triggered, does not call the exchange, sets
    `exit_reason=EXTERNAL_CLOSE_LOCAL_HYGIENE`, and records audit metadata;
  - startup and periodic reconciliation refresh the read model after
    external-close state changes before protection-health evaluation.
- Cleaned historical local PG data for `ETH/USDT:USDT`:
  - before cleanup: 2174 active local protection rows without an active local
    position;
  - cleanup action: local PG-only status transition to `CANCELED` with
    `exit_reason=EXTERNAL_CLOSE_LOCAL_HYGIENE_HISTORICAL`;
  - audit rows written: 2174;
  - after cleanup: 0 active local protection rows without an active local
    position.
- Binance testnet read-only verification after cleanup:
  `positionAmt=0.000`, open orders `0`.
- Scoped verification passed:
  `pytest -q tests/unit/test_tiny001d1b_external_close_monitor.py tests/unit/test_ls003b_periodic_reconciliation.py tests/unit/test_order_lifecycle_service_pending_updates.py tests/unit/test_ls003a_reconciliation_read_model.py tests/unit/test_tiny001c_protection_health_monitor.py tests/unit/test_tiny001d1a_controlled_signal_injection.py tests/unit/test_tiny001d4_once_per_session_guard.py`
  -> 79 passed.
- Compile verification passed:
  `python3 -m compileall -q src/application/external_close_monitor.py src/application/order_lifecycle_service.py src/application/periodic_reconciliation.py src/main.py`.

## 2026-05-25 (TC-TINY-001D-2 Testnet Follow-up Verification)

- Executed a second authorized Binance testnet controlled smoke to validate the
  hygiene path after implementation:
  - runtime profile: `sim1_eth_runtime`;
  - exchange mode: `EXCHANGE_TESTNET=true`;
  - controlled endpoint call count: 1;
  - amount: `0.01 ETH`;
  - intent: `intent_55db456b02ac`;
  - signal: `sig_d191164ff9bc`;
  - controlled response: `status=completed`, `attempt_locked=true`,
    `notional=20.9779`, `min_notional=20`.
- ENTRY and protection evidence:
  - ENTRY local order `ord_3691e21f`, exchange order `8728201255`;
  - SL local order `ord_sl_78c9954c`, exchange order `1000000084892721`;
  - TP1 local order `ord_TP1_b582d57c`, exchange order `8728201272`;
  - TP2 local order `ord_TP2_3be90dae`, exchange order `8728201281`.
- GKS was restored active immediately after the endpoint returned.
- Direct Binance testnet cleanup closed the `0.01 ETH` position with reduce-only
  market order `8728202891`; read-only verification reported
  `positionAmt=0.000` and open orders `0`.
- Follow-up runtime startup reconciliation closed the local position,
  projected realized PnL `0.472000000000000000`, and updated daily risk stats
  to realized PnL `0.951700000000000000`, trade count `2`.
- Extended local hygiene terminalized the remaining local protection rows:
  `ord_sl_78c9954c`, `ord_TP1_b582d57c`, and `ord_TP2_3be90dae` ->
  `CANCELED` with `exit_reason=EXTERNAL_CLOSE_LOCAL_HYGIENE`.
- Added healed-read-model clearing for stale protection-health blocks.
- Periodic reconciliation after the fix reported `total=821`, `severe=0`,
  `warning=821`; warnings are historical `local_order_missing_on_exchange`
  noise, not protection-health critical blocks.
- Final state:
  - runtime stopped;
  - no `src.main` process and no local `8000` listener;
  - Binance testnet `positionAmt=0.000`, open orders `0`;
  - active local protection rows without active local position: `0`.
- Scoped verification passed:
  `pytest -q tests/unit/test_tiny001d1b_external_close_monitor.py tests/unit/test_ls003b_periodic_reconciliation.py tests/unit/test_order_lifecycle_service_pending_updates.py tests/unit/test_ls003a_reconciliation_read_model.py tests/unit/test_tiny001c_protection_health_monitor.py tests/unit/test_tiny001d1a_controlled_signal_injection.py tests/unit/test_tiny001d4_once_per_session_guard.py`
  -> 82 passed.
- `python3 -m compileall -q src/application/protection_health_monitor.py src/application/external_close_monitor.py src/application/order_lifecycle_service.py src/application/periodic_reconciliation.py src/main.py`
  passed.
- `git diff --check` passed.

## 2026-05-25 (Post-Smoke Planning Snapshot)

- Added a current planning snapshot to
  `docs/ops/live-safe-v1-task-board.md`.
- Short-term priorities:
  - clean remaining historical `local_order_missing_on_exchange` warning noise
    after query proof and without exchange mutation;
  - design a runtime-managed controlled close smoke to replace direct exchange
    cleanup;
  - harden STOP_MARKET confirmation fallback for Binance testnet timing quirks;
  - specify the first read-only PLC runtime adapter;
  - refresh the LS-003 structured-runtime-logs task card around the new
    reconciliation/protection-health events.
- Long-term priorities:
  - PLC promotion ladder from local sandbox to read-only runtime, paper,
    testnet, tiny-live-style rehearsal, and only later real-live review;
  - durable campaign risk state machine;
  - account risk state machine and liquidation/margin safety checks;
  - multi-symbol runtime readiness;
  - evidence-to-strategy-contract pipeline that keeps research output separate
    from runtime authority.
- Real live trading remains out of scope unless separately and explicitly
  authorized.

## 2026-05-25 (Short-Term Task Completion Pass)

- TC-TINY-001D-3: completed local PG-only historical warning cleanup.
  - Proof before cleanup: 821 `ETH/USDT:USDT` `OPEN` ENTRY rows and 0 active
    positions.
  - Backup table: `ops_backup_orders_tiny001d3_20260525` with 821 rows.
  - Mutation: terminalized 821 stale ENTRY rows to `CANCELED` with
    `HISTORICAL_LOCAL_ENTRY_WARNING_CLEANUP`.
  - Audit: inserted 821 `ORDER_CANCELED` rows with
    `historical_local_entry_warning_cleanup` metadata.
  - Proof after cleanup: no active `SUBMITTED` / `OPEN` /
    `PARTIALLY_FILLED` ETH orders and stale ENTRY count 0.
  - Scope: local PG only; no exchange mutation.
- TC-TINY-001D-5: hardened STOP_MARKET confirmation fallback in
  `ExchangeGateway.confirm_order_exists`.
  - Recent order-watch evidence is checked before REST confirmation.
  - After a `fetch_order` miss, conditional `fetch_open_orders` is retried
    with bounded delays before fail-closed.
  - Targeted tests:
    `pytest -q tests/unit/test_tiny001d1b_sl_confirmation.py tests/unit/test_tiny001d1b_sl_metadata_validation.py`
    passed with 9 tests.
- TC-TINY-001D-4: completed design document
  `docs/ops/tc-tiny-001d-4-runtime-managed-close-smoke-design.md`.
  No runtime close endpoint was added yet because lifecycle-close semantics
  should be Codex-owned before exchange-connected testnet execution.
- PLC-RUNTIME-001: completed read-only runtime adapter spec in
  `docs/ops/plc-runtime-001-read-only-runtime-adapter-spec.md`.
- LS-003: refreshed Claude task card in
  `docs/ops/ls-003-structured-runtime-logs-task-card.md`.
- Verification:
  - `pytest -q tests/unit/test_tiny001d1b_sl_confirmation.py tests/unit/test_tiny001d1b_sl_metadata_validation.py tests/unit/test_tiny001d1b_external_close_monitor.py tests/unit/test_ls003b_periodic_reconciliation.py tests/unit/test_order_lifecycle_service_pending_updates.py tests/unit/test_ls003a_reconciliation_read_model.py tests/unit/test_tiny001c_protection_health_monitor.py tests/unit/test_tiny001d1a_controlled_signal_injection.py tests/unit/test_tiny001d4_once_per_session_guard.py`
    passed with 91 tests.
  - `python3 -m compileall -q src/infrastructure/exchange_gateway.py src/interfaces/api_console_runtime.py src/application/external_close_monitor.py src/application/order_lifecycle_service.py src/application/protection_health_monitor.py`
    passed.
  - `git diff --check` passed.
  - Binance testnet read-only check for `ETH/USDT:USDT` returned active
    positions `[]` and open orders count `0`.

## 2026-05-25 (PLC Phased Upgrade Phase 1)

- Committed the prior short-term Live-safe follow-up batch:
  `28e97c8 chore: complete short-term live-safe followups`.
- Added PLC phased upgrade ladder:
  `docs/ops/plc-phased-upgrade-v0.md`.
- Implemented Phase 1 read-only runtime adapter:
  `src/application/personal_campaign_runtime_adapter.py`.
- Added `ReadOnlyRuntimeAdapterPreview` to the PLC domain contracts.
- Added read-only adapter schema and SQ02 example:
  - `docs/schemas/personal_campaign/read_only_runtime_adapter_preview.schema.json`
  - `docs/schemas/personal_campaign/examples/read_only_runtime_adapter_preview_sq02.example.json`
- Adapter behavior:
  - closed/prior snapshot plus frozen contract can produce an allowed
    read-only `TradeIntent` preview;
  - future/current snapshots are rejected;
  - non-frozen contracts are rejected;
  - contract/snapshot mismatches are rejected;
  - output carries `read_only_no_order_authority` and has no order/exchange id.
- Verification:
  `pytest -q tests/unit/test_personal_campaign_runtime_adapter.py tests/unit/test_personal_campaign_sandbox.py tests/unit/test_personal_campaign_schema_docs.py tests/unit/test_personal_campaign_schema_examples.py`
  passed with 35 tests.

## 2026-05-25 (PLC Phased Upgrade Phase 2)

- Implemented Phase 2 paper observation packet:
  `src/application/personal_campaign_paper_observation.py`.
- Added `PaperObservationPacket` and `PaperObservationReviewStatus` to the PLC
  domain contracts.
- Added paper observation packet schema and SQ02 example:
  - `docs/schemas/personal_campaign/paper_observation_packet.schema.json`
  - `docs/schemas/personal_campaign/examples/paper_observation_packet_sq02.example.json`
- Packet behavior:
  - wraps only read-only runtime previews;
  - carries `paper_observation_no_order_authority`;
  - stores review status, operator notes, and optional review provenance;
  - reviewed packets require `reviewed_by` and `reviewed_at_ms`;
  - exported packet dict is JSON-ready without writing files or calling
    services.
- Verification:
  `pytest -q tests/unit/test_personal_campaign_paper_observation.py tests/unit/test_personal_campaign_runtime_adapter.py tests/unit/test_personal_campaign_schema_docs.py tests/unit/test_personal_campaign_schema_examples.py`
  passed with 24 tests.
