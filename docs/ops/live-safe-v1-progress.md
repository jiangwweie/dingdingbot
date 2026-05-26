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

## 2026-05-25 (BRC-R0/R1 Bounded Risk Campaign Implementation)

- Accepted ADR-0012 and reframed PLC from "Strategy Execution Platform" toward
  `Bounded Risk Campaign System`: isolated risk bucket, Owner-selected
  playbook, bounded attempts, hard risk envelope, profit-protect/loss-lock, and
  final outcome evidence.
- Implemented pure BRC domain objects and service logic for campaign creation,
  playbook switch decisions, ETH/BTC attempt sequence, mock PnL events,
  profit-protect, loss-lock, evidence packet, and final outcome.
- Added PG persistence and Alembic revision `012` for `brc_campaigns`,
  `brc_playbook_switch_decisions`, `brc_campaign_events`, and
  `brc_mock_pnl_events`.
- Added readonly inactive `brc_btc_eth_testnet_runtime` profile seed with fixed
  ETH/BTC caps, max attempts `2`, max simultaneous positions `1`, and program
  withdrawal disabled.
- Added local/internal BRC test endpoints under `/api/runtime/test/brc/*`.
  They require runtime control enabled, testnet, and the BRC profile; mutation
  endpoints also require test signal injection enabled. Request bodies cannot
  override controlled entry/close amount, side, leverage, SL, or TP.
- Mock PnL is BRC business-state evidence only. It does not mutate exchange
  fills, account balance, daily risk stats, or withdrawals.
- Targeted local tests were added for BRC service rules and BRC API acceptance
  flow. Binance testnet smoke remains the final acceptance gate.
- BRC-R0/R1 Binance testnet smoke passed after one repair cycle:
  - first BTC retry was blocked by account-level daily trade count because the
    same-day runtime trade count was already `10` and profile cap was `10`;
  - repaired BRC entry handling so blocked/failed execution intents do not
    record attempt entry;
  - set BRC testnet profile `daily_max_trades=20` while keeping BRC max attempts
    at `2`;
  - final retry completed ETH controlled entry/close, mock profit,
    BTC controlled entry/close, mock loss, third-attempt block, loss-locked
    switch block, evidence packet, and final outcome
    `ended_testnet_rehearsal_complete_loss_locked`;
  - GKS restored active, startup guard blocked, runtime state closed-safe,
    runtime stopped, and port `8001` released.

## 2026-05-26 (BRC-R2-001 Low-Friction Review Layer)

- Opened `BRC-R2-001` as the next BRC mainline step after the successful
  R0/R1 testnet rehearsal.
- Added the R2 plan in
  `docs/ops/brc-r2-low-friction-ops-review-plan.md`.
- Scope remains read-only for this slice: campaign review packet,
  next-campaign eligibility gate, local operator helper, and narrow
  text-to-read-action draft. No new order path, withdrawal/transfer endpoint,
  real-live authority, automatic sizing, strategy implementation, or
  natural-language auto-execution is introduced.

## 2026-05-26 (BRC-R2-002 Owner-Confirmed Read-Only Runner)

- Extended the BRC operator medium from draft-only to
  `draft -> plan -> confirmed read-only run`.
- The runner requires `CONFIRM_READ_ONLY_BRC`, executes only
  review/eligibility/evidence read actions, and marks run results with
  `mutation_executed=false`, `withdrawal_executed=false`, and
  `live_ready=false`.
- No new testnet order path, withdrawal/transfer endpoint, real-live
  authority, automatic sizing, strategy implementation, or natural-language
  auto-execution is introduced.

## 2026-05-26 (BRC-R2-003 Operator Action Ledger Persistence)

- Added the operator action ledger as the database fact source for
  `Owner text -> persisted plan -> action_id -> confirmed read-only run`.
- `/operator/plan` persists a ledger row and returns `action_id`; canonical
  run uses `/operator/actions/{action_id}/run`; compatibility `/operator/run`
  creates a ledger row internally.
- Confirmation failures and unknown text are persisted as `blocked`; executed
  rows preserve `mutation_executed=false`, `withdrawal_executed=false`, and
  `live_ready=false`.
- No new order path, withdrawal/transfer endpoint, real-live authority,
  automatic sizing, strategy implementation, or natural-language
  auto-execution is introduced.

## 2026-05-26 (BRC-R2-004 Review Decision Governance)

- Added persisted Owner review decisions as the final operation-governance
  ledger after read-only operator runs.
- Review decisions record campaign id, optional source action id, decision,
  reason, and next recommended task; they do not create campaigns or mutate
  runtime/exchange/account state.
- Review decision rows enforce `testnet_only=true`,
  `real_live_authorized=false`, `withdrawal_authorized=false`, and
  `strategy_execution_authorized=false`.

## 2026-05-26 (BRC-R3 LangGraph LLM Operator Gateway)

- Added a LangGraph-shaped BRC operator workflow:
  `Owner text -> normalized intent -> policy validation -> persisted workflow
  -> Owner confirmation -> allowed action -> persisted result`.
- Added `brc_llm_intents` and `brc_workflow_runs` as the durable fact source
  for LLM-normalized intents and workflow state. LangGraph checkpointing is
  orchestration-only and does not replace PG audit tables.
- Added OpenAI-compatible LLM provider configuration through environment
  variables only. API keys are not persisted or logged.
- Allowed actions are limited to read review packet, read next eligibility,
  read evidence, and the fixed BRC ETH -> BTC controlled testnet rehearsal.
  Forbidden live/mainnet, withdrawal/transfer, strategy execution, autonomous
  order, sizing/leverage/side override, and broader multi-symbol requests are
  blocked before execution.
- Added internal API and CLI wrappers for LLM workflow create/get/list/confirm.
  Read-only confirmation remains `CONFIRM_READ_ONLY_BRC`; controlled testnet
  rehearsal confirmation is `CONFIRM_BRC_TESTNET_REHEARSAL`.

## 2026-05-26 (BRC External Audit Backlog Alignment)

- External audit immediate fixes were completed in commit `bc7e2ad`:
  GKS constructor fail-closed, campaign transition owner-review/flat-proof
  enforcement, explicit trigger requirement for terminal runtime states,
  ended-campaign mock PnL guard, fixed testnet rehearsal result validation,
  loss-locked next-campaign creation gate, and LLM testnet intent upgrade
  guard.
- Recorded deferred audit/deployment items in
  `docs/ops/brc-pre-deploy-audit-backlog.md`.
- Deferred items are intentionally tied to later gates:
  Feishu callback integration, cloud deployment, Web mutation controls, and
  strategy-pool construction. They are not prerequisites for continuing the
  current local-only BRC operation-governance loop.
- Recommended next capability is `BRC-R4-001 Local Operator Console`: a
  local-only Web surface for current campaign state, review packet,
  next-campaign eligibility, LLM/operator plan, explicit confirmation,
  action/workflow ledger, review decision, and next gate.
- Boundary preserved: no real live/mainnet, no withdrawal/transfer endpoint,
  no autonomous strategy execution, no automatic sizing/leverage/side decision,
  no auto-filled confirmation phrase, and no new order path beyond existing
  fixed BRC testnet workflow.

## 2026-05-26 (BRC-R4 API Surface Cleanup Planning)

- Inspected the current backend API surface before Web implementation.
- Current route inventory:
  - `src/interfaces/api.py`: 79 legacy monolith routes;
  - `src/interfaces/api_console_runtime.py`: 47 runtime/BRC/test routes;
  - `src/interfaces/api_console_research.py`: 6 read-only research routes;
  - `src/interfaces/api_research_jobs.py`: 10 research job/candidate routes;
  - `src/interfaces/api_v1_config.py`: 42 broad config routes;
  - `src/interfaces/api_profile_endpoints.py`: 8 profile routes.
- Added `docs/ops/brc-r4-api-surface-cleanup-plan.md`.
- Planning conclusion: BRC Web should depend on a BRC-first API contract, not
  on the current legacy API surface. The target split is BRC campaign,
  BRC operator, BRC LLM workflows, runtime read, runtime control, dev-testnet
  BRC, and later research/strategy-pool routers.
- Recommended implementation order:
  contract freeze -> router split without behavior change -> dependency
  cleanup to `RuntimeContext` -> Web console implementation -> pre-deploy
  security gate.
- No API code, frontend code, runtime profile, exchange path, testnet action,
  real live action, withdrawal/transfer, strategy execution, or automatic
  sizing path was changed.

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

## 2026-05-25 (PLC Phased Upgrade Phase 3 Design)

- Added bounded testnet rehearsal design:
  `docs/ops/plc-phase3-testnet-rehearsal-design.md`.
- Added draft ADR-0009 authorization request:
  `docs/ops/plc-phase3-adr0009-authorization-request.md`.
- Phase 3 verdict:
  `phase3_design_ready / execution_blocked`.
- Execution blockers:
  - runtime-managed controlled close is not implemented yet;
  - campaign risk state machine remains TODO;
  - account risk/liquidation safety checks remain TODO;
  - no specific Owner authorization has been requested or granted for one PLC
    Phase 3 rehearsal cycle.
- The design prefers the installed Binance official plugin for read-only
  market/testnet state checks when available, but explicitly forbids using it
  to bypass the runtime lifecycle for order placement, cancellation, or cleanup.

## 2026-05-25 (PLC Phase 3 Blocker Closure)

- Implemented the runtime-managed controlled close path for `TC-TINY-001D-4`:
  - added explicit `OrderRole.EXIT` support and PG/ORM constraint migration;
  - added `ExecutionOrchestrator.execute_controlled_close()`;
  - added `POST /api/runtime/test/smoke/execute-controlled-close`;
  - keeps the close reduce-only, `sim1_eth_runtime` only, Binance testnet only,
    max `0.01 ETH`, local/internal only, empty-body only, and once per runtime
    session.
- Added controlled close tests covering:
  - reduce-only market close through the gateway;
  - exit projection and daily stats callback;
  - protection-order exchange cancel plus local terminalization;
  - endpoint once-per-session guard and orchestrator delegation.
- Added Phase 3 safety specs:
  - `docs/ops/plc-campaign-risk-state-machine-spec.md`;
  - `docs/ops/plc-account-risk-liquidation-safety-spec.md`.
- Updated Phase 3 verdict:
  `phase3_pre_execution_review / authorization_required`.
- Remaining before testnet execution:
  - exact ADR-0009 Owner authorization for one rehearsal cycle.
- Verification completed:
  - `pytest -q tests/unit/test_tiny001d4_controlled_close.py tests/unit/test_tiny001d4_once_per_session_guard.py tests/unit/test_tiny001d1a_controlled_signal_injection.py tests/unit/test_tiny001d1b_external_close_monitor.py tests/unit/test_ls003b_periodic_reconciliation.py tests/unit/test_order_lifecycle_service_pending_updates.py tests/unit/test_ls003a_reconciliation_read_model.py tests/unit/test_tiny001c_protection_health_monitor.py tests/unit/test_personal_campaign_paper_observation.py tests/unit/test_personal_campaign_runtime_adapter.py tests/unit/test_personal_campaign_sandbox.py tests/unit/test_personal_campaign_schema_docs.py tests/unit/test_personal_campaign_schema_examples.py`
    passed with 126 tests.
  - `python3 -m compileall -q ...` passed for touched modules.
  - `git diff --check` passed.
- PG preflight completed:
  - backed up 3706 historical active local order rows to
    `ops_backup_orders_plc_phase3_20260525`;
  - terminalized 3706 historical active local order rows locally with audit
    metadata and no exchange mutation;
  - local active orders are now `0`;
  - `orders.ck_orders_order_role` now allows `EXIT`.
- Binance preflight completed:
  - official Binance plugin public futures ticker check for `ETHUSDT` passed;
  - project read-only Binance testnet check for `ETH/USDT:USDT` returned no
    nonzero positions and open orders `0`.

## 2026-05-25 (PLC Phase 3 Attempt 1)

- Owner authorized one ADR-0009 Binance testnet controlled rehearsal cycle.
- Runtime start evidence:
  - commit: `14f4a2f`;
  - profile: `sim1_eth_runtime`;
  - `exchange_testnet=true`;
  - startup reconciliation candidates `0`;
  - startup guard manually armed;
  - GKS temporarily set inactive for the authorized cycle.
- Controlled entry succeeded:
  - intent id: `intent_b8b65ad0e745`;
  - signal id: `sig_c205e2c08e64`;
  - amount: `0.01`;
  - entry exchange order id: `8728367551`;
  - local ENTRY status: `FILLED`;
  - local protection orders mounted: SL `1000000084961186`, TP1
    `8728367554`, TP2 `8728367574`.
- Controlled close placed and filled the reduce-only `EXIT`:
  - local EXIT id: `exit_controlled_cbcef6060340`;
  - exchange order id: `8728368262`;
  - status: `FILLED`;
  - average execution price: `2102.72`;
  - realized PnL: `-0.0085`;
  - daily risk stats updated to cumulative PnL `0.9432`, trade count `3`.
- Attempt 1 did not fully pass acceptance because the close endpoint returned
  HTTP 500 after the EXIT fill. Root cause: Binance had already removed or
  expired at least one protection order after the reduce-only close, and
  `_cancel_remaining_protection_orders_after_controlled_close()` treated
  `OrderNotFoundError` during cleanup as fatal.
- Safety restoration:
  - read-only Binance testnet check after close returned no nonzero
    `ETH/USDT:USDT` position and open orders `0`;
  - GKS was restored active before cleanup review;
  - runtime process was stopped;
  - three local stale protection rows for `sig_c205e2c08e64` were terminalized
    locally with audit metadata and no exchange mutation;
  - local active orders are `0`.
- Follow-up patch:
  - controlled close cleanup now treats `OrderNotFoundError` for protection
    order cancellation as idempotent after the close is already confirmed;
  - other cancellation failures still fail the close path;
  - targeted verification passed: 65 tests, `compileall`, and
    `git diff --check`.
- Current verdict:
  `attempt1_safe_flat_but_not_acceptance_pass / retry_authorization_required`.

## 2026-05-25 (PLC Phase 3 Retry Completion)

- Owner authorized one additional bounded ADR-0009 Binance testnet retry.
- Preflight:
  - commit: `d8ade02`;
  - local active orders: `0`;
  - local active positions: `0`;
  - GKS active before start;
  - Binance testnet read-only check for `ETH/USDT:USDT`: no nonzero position,
    open orders `0`;
  - `tests/unit/test_tiny001d4_controlled_close.py` passed with 4 tests before
    retry.
- Runtime start evidence:
  - profile: `sim1_eth_runtime`;
  - `exchange_testnet=true`;
  - startup reconciliation candidates `0`, failures `0`;
  - startup guard manually armed for the retry;
  - GKS temporarily set inactive only for the authorized cycle.
- Controlled entry succeeded:
  - intent id: `intent_656a68bcc2c5`;
  - signal id: `sig_ab0a0a0b495c`;
  - amount: `0.01`;
  - entry exchange order id: `8728378151`;
  - local ENTRY status: `FILLED`;
  - protection orders mounted: SL `1000000084965165`, TP1 `8728378170`,
    TP2 `8728378187`.
- Patched controlled close succeeded:
  - response status: `FILLED`;
  - local EXIT id: `exit_controlled_4d0c9fe3059e`;
  - exchange order id: `8728378402`;
  - amount: `0.01`;
  - average execution price: `2101.62`;
  - terminalized protection orders: `3`;
  - endpoint returned success instead of HTTP 500.
- Projection and daily stats evidence:
  - local position `pos_sig_ab0a0a0b495c` is closed with quantity `0`;
  - realized PnL: `-0.0027`;
  - daily risk stats aggregate for `runtime:default` / `2026-05-25`:
    realized PnL `0.9405`, trade count `4`;
  - latest daily risk event key:
    `daily-risk:v1:runtime:default:2026-05-25:pos_sig_ab0a0a0b495c:exit_controlled_4d0c9fe3059e:0.01`.
- Final safety evidence:
  - GKS restored active with reason `PLC Phase 3 retry complete - restore GKS`;
  - local active orders: `0`;
  - local active positions: `0`;
  - Binance testnet final read-only check: no nonzero `ETH/USDT:USDT`
    position and open orders `0`;
  - manual bounded reconciliation read-model refresh persisted
    `1779690282549:ETH/USDT:USDT` with severe `0`, warning `0`, total `0`,
    consistent `true`;
  - runtime was stopped after verification.
- Current verdict:
  `phase3_complete_testnet_rehearsal_passed / phase4_still_blocked`.

## 2026-05-25 (PLC Phase 4 Readiness Review)

- Owner authorized Phase 4.
- Interpreted under the current PLC ladder as tiny-live-style readiness review
  only, not real-live trading authorization.
- Added `docs/ops/plc-phase4-tiny-live-style-readiness-review.md`.
- Phase 4 verdict:
  `phase4_review_complete / real_live_not_authorized / continue_non_real_live_hardening`.
- Blocking gaps before any real-live readiness can be reconsidered:
  - account risk and liquidation safety are still design-only;
  - campaign risk state machine is still design-only;
  - conditional SL visibility still creates temporary protection-health severe
    noise during active testnet exposure;
  - runtime control lifecycle needs explicit startup-guard reset and clean
    shutdown/port-release verification;
  - no strategy contract is promoted to real-live use.
- Added next non-real-live hardening tasks P4-001 through P4-005 to the task
  board.

## 2026-05-25 (PLC Phase 4 Local Hardening)

- Implemented P4-001 through P4-004 as non-real-live local hardening:
  - account risk/liquidation gate now blocks new entries fail-closed before
    CapitalProtection when account balance, positions, mark price, or
    liquidation distance are unavailable/degraded/critical;
  - campaign runtime state now persists in PG via `runtime_campaign_state`,
    exposes local/internal owner-control API, and allows new entries only in
    `armed`;
  - reconciliation now fetches normal open orders plus Binance conditional
    STOP_MARKET open-order views to reduce false protection-health severe
    noise when exchange-native SL exists;
  - startup guard now has explicit block/reset API and runtime shutdown paths
    reset it to `RUNTIME_SHUTDOWN_RESET`.
- Added migration `010_create_runtime_campaign_state`.
- Local PG verification:
  - attempted Alembic against the configured local PG and found the older
    migration chain is not clean-install safe because `002_create_orders_positions`
    references `signals` before the clean schema has `signals`;
  - cleared local PG historical schema under the previously approved
    disposable-data boundary;
  - restored runtime PG schema with `PGCoreBase.metadata.create_all()`;
  - verified `CampaignStateService` creates/restores `runtime:default` as
    `observe` from PG.
- Targeted verification:
  - `pytest -q tests/unit/test_p4_account_risk_service.py tests/unit/test_p4_campaign_state_service.py tests/unit/test_gks_v0_global_kill_switch.py tests/unit/test_ls003a_reconciliation_read_model.py tests/unit/test_tiny001d1b_sl_confirmation.py tests/unit/test_rtg002_ws_api_task_lifecycle.py`
    passed with 75 tests.
  - `python3 -m compileall -q ...` passed for touched runtime/API/infra/tests.
  - `git diff --check` passed.
- No real-live trading, real-funds operation, real runtime profile change, or
  real account mutation was performed.
- Current verdict:
  `phase4_hardening_local_complete / real_live_not_authorized / runtime_smoke_pending`.

## 2026-05-25 (PLC Phase 4 Runtime/Testnet Smoke Completion)

- Repaired the clean PG Alembic path after clearing disposable local PG data:
  - migration `002_create_orders_positions` no longer references `signals`
    before `signals` exists on a clean schema;
  - migration `009_add_exit_order_role` now drops either historical
    `ck_orders_order_role` or `check_orders_order_role` before recreating the
    order-role constraint;
  - clean local PG `alembic upgrade head` reached `010 (head)`.
- Restored runtime PG schema/profile state after the clean migration proof:
  - `PGCoreBase.metadata.create_all()` initialized the current runtime tables;
  - `sim1_eth_runtime` was reseeded as the active read-only runtime profile;
  - GKS was seeded active with reason
    `P4 lifecycle smoke default safe state`;
  - `CampaignStateService` restored `runtime:default` as `observe`.
- Fixed runtime lifecycle shutdown:
  - signal handlers now request shutdown only; cleanup is centralized in
    `run_application()`;
  - the embedded uvicorn server gets `should_exit=True` and a bounded await;
  - `SignalPipeline`, `ConfigManager`, runtime repositories, PG engines,
    SQLite pooled connections, and the event-loop default executor are closed;
  - startup guard is reset to `RUNTIME_SHUTDOWN_RESET` during shutdown.
- No-order testnet lifecycle smoke passed:
  - health check `ok`;
  - startup guard initial `armed=false`;
  - GKS `active=true`;
  - campaign state `observe`;
  - manual startup-guard arm then block worked;
  - runtime exited naturally after SIGTERM;
  - port `8001` released;
  - no `Runtime shutdown non-daemon threads` warning;
  - no `PROTECTION_ORPHAN_REDUCE_ONLY_ORDER` block.
- Active-position Binance testnet smoke passed after fixing conditional order
  cancellation:
  - controlled ENTRY succeeded: `intent_4e135118e8be`,
    `sig_5faab5666eeb`, amount `0.01`, notional `21.086`;
  - during active exposure, direct read-only testnet check showed position qty
    `0.01`, normal open orders `2`, conditional stop open orders `1`, and
    stop reduce-only count `1`;
  - periodic reconciliation reported `consistent` while the exchange-native SL
    was active;
  - no protection-health missing/orphan block appeared in the runtime log;
  - controlled close returned `FILLED` with EXIT
    `exit_controlled_f46d6fb36279`, exchange order `8728507418`, and
    terminalized protection orders `3`;
  - runtime close canceled the Binance conditional SL through the stop-order
    fallback path;
  - final direct read-only testnet check showed position qty `0`, normal open
    orders `0`, and conditional stop open orders `0`;
  - GKS was restored active, campaign state reset to `observe`, startup guard
    blocked, runtime exited naturally, and port `8001` released.
- Additional finding during smoke:
  - Binance testnet conditional SL cancellation can return not found through
    the normal cancel endpoint while the order is still visible under
    `fetch_open_orders(..., params={"stop": True})`;
  - `ExchangeGateway.cancel_order()` now falls back to the stop-order view and
    cancels with `params={"stop": True}` after matching the same exchange id;
  - Binance may return `status=None` for that cancel response, which is now
    treated as `canceled`.
- Final targeted verification:
  - `pytest -q tests/unit/test_p4_account_risk_service.py tests/unit/test_p4_campaign_state_service.py tests/unit/test_gks_v0_global_kill_switch.py tests/unit/test_ls003a_reconciliation_read_model.py tests/unit/test_tiny001d1b_sl_confirmation.py tests/unit/test_rtg002_ws_api_task_lifecycle.py tests/unit/test_tiny001d4_controlled_close.py`
    passed with 81 tests;
  - compileall passed for touched runtime/API/gateway/migration/test files;
  - `git diff --check` passed;
  - final Binance testnet read-only check for `ETH/USDT:USDT` showed position
    qty `0`, normal open orders `0`, and conditional stop open orders `0`.
- No real-live trading, real-funds operation, real runtime profile change, or
  real account mutation was performed.
- Current verdict:
  `phase4_p4_001_to_p4_004_non_real_live_smoke_complete / real_live_not_authorized / strategy_promotion_still_blocked`.

## 2026-05-25 (ARCH-P4-001 Runtime/API Composition Root Governance)

- Added ADR-0010 for runtime/API ownership:
  - `src/main.py` is the only execution-runtime composition root;
  - embedded API receives the main-owned runtime through `RuntimeContext` bound
    to `app.state.runtime`;
  - standalone `uvicorn src.interfaces.api:app` is degraded to
    HTTP/config/read-only mode and must not create exchange/orchestrator
    runtime wiring.
- Added `src/application/runtime_context.py` as the explicit runtime container
  for exchange, repositories, services, orchestrator, startup summary, runtime
  tasks, and embedded API handles, with `start()` / `shutdown()` owner-state
  methods.
- Updated API runtime control reads to prefer the bound context while retaining
  module-global compatibility for existing endpoints/tests.
- Acceptance repair closed two governance gaps before commit:
  - `RuntimeContext` now maps legacy `_signal_repo` / `_repository` reads to
    `signal_repository`, and `_account_getter` to `get_account_snapshot`;
  - `clear_runtime_context()` clears the compatibility globals populated by
    `bind_runtime_context()`, so a process without bound context no longer
    retains stale exchange/orchestrator/control handles.
- Verification after acceptance repair:
  - targeted architecture/API/control/Phase 4 regression tests passed with
    87 tests;
  - compileall and `git diff --check` passed;
  - no-order testnet lifecycle smoke started embedded API with the bound
    context, read startup guard successfully, exited naturally on SIGTERM,
    released port `8001`, and logged no non-daemon thread warning.
- No strategy logic, runtime profile, trading parameters, credentials, or
  real-live permissions were changed.

## 2026-05-25 (PLC Phase 5A Small-Scale Rehearsal Readiness)

- Owner approved the recommended 1/2/3 path and authorized bounded testnet.
- Kept `dev` as the current unpushed integration candidate; no remote push was
  performed.
- Added `docs/ops/plc-phase5-small-scale-rehearsal-design.md` and updated the
  PLC ladder/task board to show Phase 5A as the next non-real-live readiness
  step after Phase 4.
- Implemented first Phase 5A gates:
  - account-risk now prefers account-scope position fetches and can block a new
    entry because another symbol has critical liquidation distance;
  - account-risk computes total account exposure and blocks if exposure exceeds
    the configured balance multiple;
  - campaign state service exposes runtime-event transitions for
    `entry_filled`, `profit_protect_triggered`, `stop_loss_filled`,
    `position_closed`, and `risk_critical`;
  - Strategy Contract promotion gate accepts only reviewed paper-observation
    packets into the next non-order gate and preserves
    `promotion_review_no_order_authority`.
- Verification:
  - compileall passed for touched application/test modules;
  - new/local gate tests passed with 16 tests;
  - Phase 4/ARCH regression target passed with 95 tests;
  - PLC promotion/schema target passed with 28 tests.
- Bounded Binance testnet smoke passed:
  - controlled ENTRY succeeded: `intent_99fdcaa96287`,
    `sig_3d42cc1b8bf0`, amount `0.01`, notional `21.1324`;
  - mid-smoke runtime positions count was `1`;
  - controlled close returned `FILLED` with
    `exit_controlled_48409f3fc46a`, exchange order `8728597319`, and
    terminalized protection orders `3`;
  - final runtime positions `0`;
  - final local active orders `0`;
  - GKS restored active, campaign state restored `observe`, startup guard
    blocked/reset;
  - runtime exited naturally, port `8001` released, and no non-daemon thread
    warning appeared;
  - no `PROTECTION_ORPHAN_REDUCE_ONLY_ORDER` or `PROTECTION_MISSING_STOP_LOSS`
    block appeared in the smoke log.
- No real-live trading, real-funds operation, runtime profile change,
  credential change, strategy-parameter change, transfer, or withdrawal was
  performed.
- Current verdict:
  `phase5a_first_gates_smoked_on_testnet / real_live_not_authorized / repeated_rehearsal_still_separate_gate`.

## 2026-05-25 (PLC Phase 5B Repeated Testnet Rehearsal)

- Owner authorized Phase 5B.
- Added `docs/ops/plc-phase5b-repeated-testnet-rehearsal.md`.
- Started Phase 5B with a bounded scope:
  - repeated controlled Binance testnet cycles;
  - symbol-isolation hardening before any multi-symbol runtime discussion;
  - explicit continued block on real live and multi-symbol runtime.
- Implemented first symbol-isolation hardening:
  - `ExchangeGateway` keeps symbol-specific order-watch running state while
    preserving the legacy global shutdown flag for compatibility;
  - recent order-update evidence is now indexed by symbol before order
    confirmation, reducing same-id cross-symbol contamination risk;
  - added `runtime_symbol_isolation_audit` as a pure audit snapshot that marks
    order-watch/cache checks as pass, reconciliation/read-model checks as
    review, and multi-symbol runtime as blocked.
- Local verification:
  - compileall passed for touched exchange/audit/test modules;
  - symbol-isolation/order-watch/STOP_MARKET-adjacent tests passed with
    18 tests.
- Integration verification:
  - Phase 4/ARCH/PLC/Phase 5B target regression passed with 107 tests;
  - `git diff --check` passed.
- Repeated Binance testnet rehearsal passed:
  - Cycle 1 controlled ENTRY `intent_3c08be13f081`,
    `sig_0a7446591611`, amount `0.01`, notional `21.1515`;
  - Cycle 1 controlled close `FILLED`, `exit_controlled_67c1002181d4`,
    exchange order `8728615333`, terminalized protection orders `3`;
  - Cycle 2 controlled ENTRY `intent_a931c7dbf03b`,
    `sig_226d23b1c6d1`, amount `0.01`, notional `21.1607`;
  - Cycle 2 controlled close `FILLED`, `exit_controlled_7e1641a544ef`,
    exchange order `8728616546`, terminalized protection orders `3`;
  - both cycles started with pre positions `0`, observed mid positions `1`,
    ended with final positions `0` and final active local orders `0`;
  - both cycles restored GKS active, campaign state `observe`, and startup
    guard blocked/reset;
  - both cycles exited naturally, released port `8001`, and logged no
    non-daemon thread warning, missing-stop block, or orphan protection block.
- No real-live trading, real-funds operation, runtime profile change,
  credential change, strategy-parameter change, transfer, withdrawal, or
  multi-symbol runtime action was performed.
- Current verdict:
  `phase5b_repeated_testnet_passed / multi_symbol_runtime_blocked / real_live_not_authorized`.

## 2026-05-25 (PLC Phase 5C Two-Symbol Synthetic Fixture Proof)

- Continued from Phase 5B without changing runtime profile, credentials,
  strategy parameters, or real-live permissions.
- Added `docs/ops/plc-phase5c-two-symbol-synthetic-fixture-proof.md`.
- Implemented local BTC/ETH synthetic fixture proof:
  - reconciliation `build_read_model(ETH)` excludes BTC mismatches;
  - runtime orders read model filters by symbol;
  - runtime execution-intents read model now accepts a symbol filter;
  - runtime positions read model and `/api/runtime/positions` now accept a
    symbol filter;
  - `/api/runtime/execution/intents` now accepts a symbol filter;
  - portfolio remains account-level aggregation and includes both BTC and ETH.
- Updated `runtime_symbol_isolation_audit` with a Phase 5C verdict:
  `two_symbol_synthetic_fixture_passed / multi_symbol_runtime_still_blocked`.
- Verification:
  - compileall passed for touched read-model/API/audit/test modules;
  - local Phase 5B/5C symbol-isolation tests passed with 8 tests.
- No Binance testnet action was performed for Phase 5C because the task is a
  local synthetic proof. No real-live trading, real-funds operation, runtime
  profile change, credential change, transfer, withdrawal, or multi-symbol
  runtime action was performed.
- Current verdict:
  `phase5c_two_symbol_synthetic_fixture_passed / multi_symbol_runtime_still_blocked / real_live_not_authorized`.

## 2026-05-25 (PLC Phase 5D Two-Symbol Exchange Read-Only Rehearsal)

- Owner authorized the next step after Phase 5C.
- Added `docs/ops/plc-phase5d-two-symbol-exchange-readonly-rehearsal.md`.
- Added `src/application/two_symbol_exchange_rehearsal.py`:
  - read-only BTC/ETH ticker, positions, normal open orders, and conditional
    open-order probes;
  - explicit `exchange_connected_read_only_no_order_authority`;
  - fails if any symbol has nonzero position, normal open orders, or
    conditional open orders.
- Added tests for pass/fail read-only rehearsal behavior.
- Used the official Binance plugin for public USDS futures book ticker:
  `ETHUSDT` and `BTCUSDT` both returned bid/ask data.
- Initial project Binance testnet read-only rehearsal:
  - ETH position `0`, normal open orders `0`, conditional open orders `0`;
  - BTC position `0`, normal open orders `0`, conditional open orders `6`;
  - verdict `phase5d_two_symbol_exchange_readonly_needs_cleanup`.
- Bounded BTC testnet cleanup:
  - verified BTC position `0` and normal open orders `0`;
  - verified all 6 BTC conditional orders were reduce-only;
  - canceled exchange orders `1000000047775774`, `1000000047775957`,
    `1000000047779744`, `1000000047779975`, `1000000048741712`,
    `1000000048741904`;
  - final BTC position `0`, normal open orders `0`, conditional open orders
    `0`.
- Final project Binance testnet read-only rehearsal passed:
  - ETH ticker visible, position `0`, normal open orders `0`, conditional open
    orders `0`;
  - BTC ticker visible, position `0`, normal open orders `0`, conditional open
    orders `0`;
  - verdict `phase5d_two_symbol_exchange_readonly_passed`.
- Local verification:
  - Phase 5B/C/D local tests passed with 10 tests;
  - compileall and `git diff --check` passed before the final integration
    target.
- No real-live trading, real-funds operation, runtime profile change,
  credential change, strategy-parameter change, transfer, withdrawal, or
  multi-symbol runtime action was performed.
- Current verdict:
  `phase5d_two_symbol_exchange_readonly_passed / multi_symbol_runtime_still_blocked / real_live_not_authorized`.

## 2026-05-25 (PLC Phase 5E Design Start)

- Added `docs/ops/plc-phase5e-controlled-multi-symbol-testnet-runtime-rehearsal.md`
  as a design/Owner-review package only.
- Proposed a new readonly testnet runtime profile
  `phase5e_btc_eth_testnet_runtime`; `sim1_eth_runtime` must remain unchanged.
- Identified current blockers: runtime market scope is still single-symbol and
  controlled endpoints are hard-coded to ETH plus `sim1_eth_runtime`.
- Recommended first 5E rehearsal shape: one runtime process, BTC/ETH market
  scope, sequential ETH then BTC controlled testnet exposure, no simultaneous
  BTC+ETH position, and no portfolio/router expansion.
- Set proposed caps: ETH `0.01 ETH` / `25 USDT`, BTC exchange-minimum viable
  quantity with `130 USDT` ceiling, combined open exposure cap `130 USDT`
  because only one symbol may be open at a time, and max `5` order submissions
  per symbol.
- Recorded stop conditions and rollback path covering profile/config rollback,
  GKS/startup/campaign restoration, runtime shutdown, final BTC/ETH flat and
  open-orders `0`, and Owner-gated direct testnet cleanup only if runtime close
  fails.
- No implementation, profile/config mutation, runtime start, Binance testnet
  order, cleanup, cancellation, credential change, or real live action was
  executed.

## 2026-05-25 (PLC Phase 5E Implementation And Bounded Testnet)

- Owner authorized continuing PLC and bounded Phase 5E testnet.
- Implemented minimal multi-symbol runtime profile support:
  - optional `symbols` in `MarketRuntimeConfig`, defaulting to
    `[primary_symbol]` for legacy profiles;
  - validation that `primary_symbol` is included and symbols are unique;
  - subscribed pairs now cover every symbol/timeframe pair.
- Added dry-run-by-default `scripts/seed_phase5e_profile.py` and seeded
  readonly inactive profile `phase5e_btc_eth_testnet_runtime`.
- Added Phase 5E server-controlled ETH/BTC endpoints under
  `/api/runtime/test/phase5e/{eth|btc}/...`; legacy `sim1_eth_runtime`
  controlled endpoints remain intact.
- Local verification before runtime:
  - Phase 5E config/endpoint tests passed with 11 tests;
  - affected controlled endpoint / Phase 5C / Phase 5D / account-risk
    regression passed with 42 tests;
  - compileall and `git diff --check` passed.
- Read-only Binance testnet preflight passed: ETH/BTC positions `0`, normal
  open orders `0`, conditional open orders `0`.
- Runtime startup:
  - wrapper launch was required because `src.main` loads `.env.local` with
    override; direct shell `RUNTIME_PROFILE=...` was overwritten by
    `.env.local`;
  - 5E runtime resolved profile version `2`, hash `8c0f633708379804`;
  - BTC/ETH warmup loaded `4/4` pairs;
  - order-watch started for both symbols;
  - startup reconciliation candidates/failures were `0`.
- ETH leg passed:
  - controlled entry `intent_fca06be68891`, signal `sig_39cb35ab8b3e`,
    amount `0.01`, notional `21.1736`;
  - controlled close `exit_controlled_18ff201e1ec3`, exchange order
    `8728698638`, average execution price `2117.18`;
  - runtime terminalized 3 protection orders and daily risk stats trade count
    advanced from `7` to `8`.
- BTC leg was blocked before order placement:
  - fixed `0.001 BTC` notional was `77.5506`, below min_notional default
    `100`;
  - cap was not raised and no BTC order or position was opened.
- Final cleanup:
  - GKS active;
  - startup guard blocked;
  - campaign state `observe`;
  - direct Binance testnet read-only final state flat/no-open-orders for ETH
    and BTC;
  - PG active positions `[]`, PG ETH/BTC open orders `[]`;
  - runtime stopped naturally and port `8001` released.
- Observation: `/api/runtime/positions` briefly showed stale ETH exposure after
  close because account snapshot cache had not refreshed; direct exchange
  inventory and PG repositories were flat.
- Current verdict:
  `phase5e_eth_leg_passed / phase5e_btc_leg_blocked_by_min_notional_without_order / final_exchange_flat / real_live_not_authorized`.

## 2026-05-25 (PLC Phase 5E Feasibility Preflight Hardening)

- Continued PLC after Phase 5E without starting runtime or executing another
  testnet order.
- Added pure `src/application/phase5e_rehearsal_feasibility.py` for
  fixed-symbol cap/min-notional assessment.
- Added read-only API endpoint:
  `GET /api/runtime/test/phase5e/{eth|btc}/feasibility`.
- Changed Phase 5E controlled entry to reuse the same feasibility result before
  constructing the signal/order path.
- The endpoint can report the observed BTC blocker as
  `NOTIONAL_BELOW_MIN_NOTIONAL` before opening a GKS/startup/campaign entry
  window.
- Verification:
  - compileall passed for the new feasibility module and touched API/tests;
  - targeted tests passed with 43 tests;
  - `git diff --check` passed.
- No runtime start, exchange call, testnet order, profile cap increase, real
  live action, commit, or push was performed.

## 2026-05-25 (PLC Phase 5E Exchange MinNotional Metadata)

- Continued Phase 5E hardening without starting runtime or making exchange
  calls.
- Added `ExchangeGateway.get_min_notional(symbol)` as a synchronous read of
  already-loaded market metadata.
- The method reads `limits.cost.min` first, then Binance `MIN_NOTIONAL` /
  `NOTIONAL` filter values from market `info.filters`.
- Phase 5E feasibility now gets exchange metadata when available and falls back
  to conservative defaults only when metadata is unavailable.
- Verification:
  - compileall passed for touched exchange/test files;
  - targeted tests passed with 23 tests;
  - `git diff --check` passed.
- No runtime start, testnet order, cap increase, real live action, commit, or
  push was performed.

## 2026-05-25 (PLC Phase 5E BTC Blocker Decision Evidence)

- Continued Phase 5E BTC blocker handling without starting runtime or making
  exchange calls.
- Added next-viable BTC decision evidence to the pure feasibility model and
  read-only Phase 5E feasibility endpoint:
  - `next_viable_amount`;
  - `next_viable_notional`;
  - `cap_shortfall`.
- The Phase 5E BTC spec now supplies the controlled exchange-step assumption
  `amount_step=0.001` for decision evidence. It still keeps fixed order amount
  `0.001 BTC` and max notional `130 USDT`.
- For the observed blocked price `77550.6`, feasibility reports next viable
  amount `0.002 BTC`, estimated notional `155.1012 USDT`, and cap shortfall
  `25.1012 USDT`.
- This does not increase BTC cap, change live/runtime profile defaults, resize
  an order, start runtime, place a testnet order, or authorize real live.
- Verification:
  - `pytest -q tests/unit/test_phase5e_rehearsal_feasibility.py tests/unit/test_phase5e_controlled_multi_symbol_endpoints.py`
    passed with 14 tests.
  - broader Phase 5E/tiny controlled-close/Phase 5C/Phase 5D/account-risk
    targeted regression passed with 70 tests.
  - compileall and `git diff --check` passed for touched files.

## 2026-05-25 (PLC Phase 5E BTC Testnet Retry Authorization)

- Owner approved Binance testnet operations without the prior minimum-capital
  limitation.
- Interpreted scope: testnet-only permission to raise Phase 5E BTC controlled
  amount/cap enough to satisfy Binance testnet min-notional. This does not
  authorize real live, mainnet, real funds, withdrawal, transfer, or generic
  strategy sizing changes.
- Updated Phase 5E BTC controlled spec:
  - amount `0.002 BTC`;
  - max controlled notional `250 USDT`;
  - amount step remains `0.001 BTC`;
  - sequential one-symbol exposure remains required.
- Next action: run local verification, then one bounded BTC testnet retry with
  preflight, feasibility, controlled entry, runtime-managed close, final
  exchange/PG flatness checks, and restored controls.

## 2026-05-25 (PLC Phase 5E BTC Testnet Retry Passed)

- Local verification before retry:
  - compileall passed for touched runtime/config/API/readmodel/test files;
  - targeted Phase 5E/Phase 5C/Phase 5D/tiny/account-risk regression passed
    with 70 tests;
  - `git diff --check` passed.
- Read-only direct Binance testnet preflight:
  - ETH position `0`, normal open orders `0`, conditional open orders `0`;
  - BTC position `0`, normal open orders `0`, conditional open orders `0`;
  - BTC ticker `77403.4`, min_notional `50.0`.
- Started one runtime process on port `8001` with
  `RUNTIME_PROFILE=phase5e_btc_eth_testnet_runtime`, `EXCHANGE_TESTNET=true`,
  `RUNTIME_CONTROL_API_ENABLED=true`, and
  `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=true`.
- Runtime resolved profile version `2`, hash `8c0f633708379804`, and safe
  summary showed ETH/BTC symbols with testnet mode.
- BTC feasibility before entry:
  - amount `0.002`;
  - price `77392.5`;
  - notional `154.7850`;
  - min_notional `50.0`, source `get_min_notional`;
  - max_notional `250`;
  - reason `OK`.
- Controls for entry window:
  - startup guard armed;
  - GKS disabled only for the bounded entry window;
  - campaign state set to `armed`.
- Controlled BTC entry succeeded:
  - intent `intent_ed2c999769bd`;
  - signal `sig_929aabc7d2ce`;
  - amount `0.002`;
  - entry price `77391.8`;
  - notional `154.7836`;
  - status `completed`.
- After entry, BTC active exposure was `0.002` with three reduce-only
  protection orders (`TP1`, `TP2`, `SL`).
- Controlled BTC runtime close succeeded:
  - close order `exit_controlled_657fa92707ee`;
  - exchange order `13192655923`;
  - amount `0.002`;
  - average execution price `77396.67`;
  - terminalized protection orders `3`.
- Daily risk stats updated to trade_count `9` and cumulative realized PnL
  `-0.015260000000000000000`.
- Final state:
  - direct Binance testnet ETH/BTC positions `0`;
  - direct Binance testnet ETH/BTC normal open orders `0`;
  - direct Binance testnet ETH/BTC conditional open orders `0`;
  - PG active positions `[]`;
  - PG ETH/BTC open orders `[]`;
  - GKS active;
  - startup guard blocked;
  - campaign state `observe`;
  - runtime stopped via SIGTERM shutdown path and port `8001` released.
- Additional read-model fix from evidence review:
  - console order/execution-intent side mapping now handles enum directions
    such as `Direction.LONG`, avoiding a false `SELL` display fallback.
- No real live, mainnet, real-funds, withdrawal, transfer, commit, or push was
  performed.

## 2026-05-25 (PLC Phase 5E Positions Snapshot Freshness Hardening)

- Continued PLC after Phase 5E without starting runtime or making exchange
  calls.
- Hardened `/api/runtime/positions` read-model behavior after the Phase 5E
  stale snapshot observation.
- New behavior: when `position_repo.list_active(...)` succeeds, PG active
  positions are the source of truth for whether a position exists; account
  snapshot rows only enrich those active PG rows with mark price/PnL/leverage.
- This prevents a stale account snapshot from showing a snapshot-only position
  after runtime-managed close has already made PG active positions flat.
- Added regression coverage in the Phase 5C two-symbol read-model fixture.
- No runtime start, exchange call, testnet order, cap increase, real live
  action, commit, or push was performed.

## 2026-05-25 (PLC Daily Risk Scope Decision Lock)

- Continued PLC after Phase 5E without starting runtime or making exchange
  calls.
- Decision: daily risk stats remain account-level with fixed
  `scope_key="runtime:default"` across runtime profiles.
- Rationale: daily loss and daily trade count are account risk controls; making
  them profile-scoped or session-scoped would let repeated profiles bypass the
  account-level day budget.
- Phase rehearsal order/session isolation should remain in dedicated controls:
  endpoint once guards, fixed exposure caps, order-count caps, GKS/startup
  guard/campaign state, and explicit Owner authorization.
- Added `resolve_daily_risk_stats_scope_key(profile_name=...)` as a small code
  policy point and wired runtime startup through it.
- Added regression coverage proving `sim1_eth_runtime` and
  `phase5e_btc_eth_testnet_runtime` resolve to the same account-level scope.
- No runtime start, exchange call, testnet order, cap increase, real live
  action, commit, or push was performed.

## 2026-05-25 (PLC Phase 5E Inventory Preflight Read Model)

- Continued PLC after Phase 5E without starting runtime or making exchange
  calls.
- Added read-only Phase 5E inventory endpoint:
  `GET /api/runtime/test/phase5e/inventory`.
- The endpoint requires the Phase 5E runtime scope and testnet mode, then
  reports per-symbol counts for:
  - exchange nonzero positions;
  - exchange normal open orders;
  - exchange conditional open orders;
  - PG active positions;
  - PG open orders.
- The response includes per-symbol `flat` and account-level `all_flat`.
- This standardizes future preflight/final flatness evidence and remains
  read-only: no order placement, close, cancel, resize, or cleanup mutation.
- Verification:
  - `pytest -q tests/unit/test_phase5e_controlled_multi_symbol_endpoints.py`
    passed with 11 tests.
- No runtime start, exchange call, testnet order, cap increase, real live
  action, commit, or push was performed.

## 2026-05-25 (PLC Long-Term Capability Roadmap)

- Continued PLC in planning mode after Phase 5E without starting runtime or
  making exchange calls.
- Added `docs/ops/plc-long-term-capability-roadmap-v1.md` as the long-term
  capability roadmap for the Owner goal:
  `controlled testnet tool -> reliable personal strategy execution platform`.
- The roadmap separates the next durable capability tracks:
  - campaign risk state machine;
  - account-level risk state machine;
  - multi-symbol runtime foundation;
  - Strategy Contract promotion pipeline;
  - runtime evidence, stop, and rollback packet.
- Planning verdict: the next recommended task is local
  `PLC-STATE-001 - Campaign Risk State Machine transition table and replay
  proof` before more exchange-connected rehearsal.
- No runtime profile default, strategy parameter, order sizing, exchange call,
  testnet action, real live action, commit, or push was performed.

## 2026-05-25 (PLC-STATE-001 Campaign Transition Table And Replay Proof)

- Continued PLC after Phase 5E under Owner testnet authorization, but this task
  stayed local because the requested core capability does not require another
  exchange-connected rehearsal.
- Implemented table-driven campaign state transitions in
  `src/application/campaign_state_service.py`:
  - explicit `CampaignTransitionTrigger` values for Owner control, entry fill,
    profit-protect, stop-loss, position close, and risk-critical events;
  - `CampaignTransitionRule` rows with owner-review, flat-proof, and
    risk-reducing-close flags;
  - `CampaignTransitionRecord` audit records with sequence number, previous
    state, target/next state, trigger, reason, updated_by, strategy/session
    ids, and context metadata such as symbol/profile/position/signal/order;
  - `replay_campaign_transitions(...)` for deterministic local replay proof.
- Hardened runtime event semantics: `entry_filled` can confirm an already
  `armed` campaign, but cannot arm a campaign from `observe`; Owner arm remains
  the only table path from `observe` to `armed`.
- Added targeted unit coverage in `tests/unit/test_p4_campaign_state_service.py`
  for transition-table contents, accepted replay, rejected replay stop,
  invalid observe-entry runtime arming, and service audit metadata.
- Verification:
  - `pytest -q tests/unit/test_p4_campaign_state_service.py` passed with 11
    tests.
- No runtime start, exchange call, testnet order, migration, runtime profile
  default change, strategy parameter change, real live action, commit, or push
  was performed.

## 2026-05-25 (PLC-STATE-002/003/004 Durable Ledger, Runtime Wiring, Replay Evidence)

- Continued from PLC-STATE-001 to complete the next campaign state-machine
  capabilities.
- PLC-STATE-002:
  - added migration `011_create_runtime_campaign_state_transitions`;
  - added PG ORM/repository support for `runtime_campaign_state_transitions`;
  - successful state transitions now update snapshot and append ledger in one
    repository transaction when using PG;
  - rejected transitions are also appended to the ledger;
  - `CampaignStateService.build_replay_evidence()` replays the ledger and
    verifies replay final state against the durable snapshot.
- PLC-STATE-003:
  - wired `ExecutionOrchestrator` entry-fill callback to `entry_filled`;
  - wired TP fill/progress to `profit_protect_triggered`;
  - wired SL fill/progress to `stop_loss_filled`;
  - wired closed position projection to `position_closed`;
  - campaign event write failures are logged without blocking protection mount
    or risk-reducing close flow.
- PLC-STATE-004:
  - added read-only internal evidence endpoint
    `GET /api/runtime/control/campaign-state/replay-evidence`;
  - response reports replay final state, snapshot match, transition counts,
    rejected transition count, and transition records;
  - future bounded testnet rehearsals can collect this packet as audit
    evidence.
- Verification:
  - compileall passed for touched campaign/orchestrator/repository/API/test
    files;
  - `pytest -q tests/unit/test_p4_campaign_state_service.py
    tests/unit/test_plc_state_runtime_event_wiring.py
    tests/unit/test_gks_v0_global_kill_switch.py -k 'campaign_state or
    plc_state or runtime_event_wiring or CampaignState'` passed with 20
    selected tests.
  - `pytest -q tests/unit/test_tiny001d4_controlled_close.py
    tests/unit/test_phase5e_controlled_multi_symbol_endpoints.py
    tests/unit/test_phase5c_two_symbol_fixture.py` passed with 20 tests.
  - `alembic heads` reported `011 (head)`.
  - `git diff --check` passed.
- No runtime start, exchange call, testnet order, migration execution against
  live PG, runtime profile change, strategy parameter change, or real live
  action was performed.

## 2026-05-25 (Playbook Governance R0 Planning Alignment)

- Owner accepted the PLC roadmap review conclusion with amendments:
  Playbook Governance R0 should be inserted before Human Arm Gate and Strategy
  Contract/runtime work.
- Added ADR-0011:
  `docs/adr/0011-playbook-governance-before-strategy-contract.md`.
- Added R0 planning artifact:
  `docs/ops/playbook-governance-r0-plan.md`.
- Updated PLC SSOT docs so the current chain is now:
  `Mode Router -> Playbook Governance -> Human Arm Gate -> Strategy Contract`.
- Accepted R0 as paper-only/docs-governance only:
  playbook registry, switch decision log, switching gate rules, cooldown/review
  governance, CPV0_2 continuity, and dry-run review.
- Standardized the initial playbook catalog:
  - `PB-000-OBSERVE-ONLY` as default safe state;
  - `PB-001-DIRECTION-A-PAPER` as pause-fragile observe-only;
  - `PB-002-SQ02-DOWNSIDE-PAPER` as docs-only skeleton;
  - `PB-003-MANUAL-DISCRETIONARY` as highest-risk governed manual posture.
- Standardized the default switching constraints:
  loss cluster 48h hard-lock plus 24h override delay, profit-response risk
  increase 7-day hold plus review, 14-day minimum playbook hold, and max 3
  switches per rolling 90 days for narrative chasing.
- Deferred execution-oriented work: Tracks B-E runtime implementation,
  Phase 5H-8 runtime work, Strategy Contract v2 implementation,
  LifecycleStrategy/ExitMonitor runtime, and further paper/testnet runtime.
- No runtime start, exchange call, order path, strategy implementation, testnet
  action, real live action, commit, or push was performed.

## 2026-05-26 (BRC-R4 API Surface Cleanup + Local Operator Console)

- Implemented BRC-R4 as the current local operation-governance console slice.
- Backend:
  - slimmed `src/interfaces/api.py` into a BRC-first FastAPI app assembly;
  - added single-Owner operator auth with username, PBKDF2 password hash,
    Google Authenticator-compatible TOTP, and signed HttpOnly session cookie;
  - added helper script `scripts/brc_auth_setup.py`;
  - mounted only auth, BRC, operator, LLM workflow, runtime safety, and
    dev/testnet BRC routers in the main API app;
  - legacy research/config/runtime routes are no longer mounted by the main
    control-console API.
- Frontend:
  - rebuilt `gemimi-web-front` as `BRC Operator Console`;
  - kept the compact workbench visual style;
  - removed legacy runtime/research/config pages and unused dependencies;
  - added login, dashboard, operator, workflow, review, ledger, and runtime
    safety pages;
  - added human-readable chain explanations, blocked-state reasons, stage/next
    step/global planning panels, and expandable JSON/evidence details.
- Boundaries preserved:
  - no user table;
  - no real live/mainnet;
  - no withdrawal/transfer;
  - no automatic strategy execution;
  - no automatic sizing/leverage/side override;
  - no strategy pool implementation;
  - no testnet order was executed by this implementation update.
- Verification completed:
  - targeted backend auth/API/runtime-context tests passed;
  - frontend `npm run lint` passed;
  - frontend `npm run build` passed.

## 2026-05-26 (BRC-R4.1 Delivery Owner Guide)

- Upgraded the local console from engineering status pages toward a
  delivery-grade Owner operation guide.
- Added readonly `GET /api/brc/readiness` as the product-state translation
  layer. It summarizes current conclusion, reasons, account impact, next step,
  available actions, disabled actions, latest campaign, review summary,
  runtime summary, and developer details without mutating campaign/runtime/
  exchange state.
- Changed the frontend default route from dashboard to `/guide`. The Guide
  page is now the primary Owner story entry: current conclusion, why, account
  impact, next step, action cards, latest campaign/review summaries, and
  folded developer detail.
- Productized existing pages around readiness:
  - Runtime Safety translates Runtime/GKS/Startup Guard/Profile into Owner
    language and shows the overall conclusion.
  - Operator Plan disables plan creation when readiness says BRC read actions
    are unavailable and shows a confirmation card before read-only execution.
  - Workflow distinguishes read-only, controlled testnet, and forbidden
    intent; testnet confirmation is disabled until all readiness gates pass.
  - Review auto-binds the latest campaign and no longer asks Owner to hand-type
    Campaign ID by default.
  - Ledger shows operation summaries first and keeps JSON under developer
    detail.
- Boundaries preserved: no new order path, no new testnet authority, no real
  live/mainnet, no withdrawal/transfer, no automatic strategy execution, no
  automatic sizing/leverage/side override, and no strategy-pool execution.
- Verification completed:
  - `python3 -m py_compile src/interfaces/api_brc_console.py src/interfaces/api_runtime_safety.py`
  - `pytest -q tests/unit/test_brc_console_api_surface.py` -> 6 passed
  - `pytest -q tests/unit/test_brc_controlled_testnet_endpoints.py` -> 8 passed
  - `npm run lint`
  - `npm run build`
  - `git diff --check`
