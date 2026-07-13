# Natural Signal Engineering Closure Implementation Plan

> **Execution mode:** Codex executes this plan inline in the isolated focused worktree. Repository policy forbids subagent delegation for this task.

**Goal:** Close the production engineering defects exposed by the latest natural signals, certify the fixes without exchange writes, deploy the exact tested commit to Tokyo, and leave the watcher ready for the next eligible signal.

**Architecture:** Preserve PG as the only current runtime truth. Fix capability propagation at the systemd process boundary, extend the existing public read-only market adapter, retain computed-false detector facts as first-class readiness evidence, and resolve durable action-time failure outcomes only through a newer bounded verification result rather than deleting history.

**Tech Stack:** Python, pytest, SQLAlchemy/PostgreSQL current projections, systemd, Tokyo git-export deployment, Binance USD-M public klines.

---

## Task 1: Backend Exchange Identity Process Propagation

**Files:**
- Create: `deploy/systemd/brc-owner-console-backend.service.d/30-runtime-order-capable-identity.conf`
- Modify: `scripts/plan_tokyo_runtime_governance_git_deploy.py`
- Test: `tests/unit/test_tokyo_lifecycle_phase_two_deploy.py`

1. Add a failing deploy-contract test proving the backend service consumes `runtime-order-capable.env` and the deploy installs the drop-in before backend startup.
2. Add a repository-owned systemd drop-in containing only the non-secret environment-file reference.
3. Install the drop-in during the code switch, reload systemd before backend startup, and verify the effective service environment-file configuration.
4. Keep identity values in the existing server env file; do not duplicate secrets or values in the repository.

## Task 2: SOR 15-Minute Public Market Support

**Files:**
- Modify: `src/infrastructure/binance_public_kline_market_source.py`
- Test: `tests/unit/test_strategy_group_live_readonly_observation.py`

1. Add a failing adapter test for a closed `15m` candle request and URL interval preservation.
2. Add `15m` to the bounded Binance public timeframe mapping.
3. Verify current open candles remain excluded and API calls retain their existing timeout.

## Task 3: Computed-False Fact Conservation And Cadence Alignment

**Files:**
- Modify: `deploy/systemd/brc-runtime-signal-watcher.timer`
- Test: `tests/unit/test_runtime_signal_watcher_systemd_units.py`
- Verify: `src/application/readmodels/strategy_live_candidate_pool.py`

1. Confirm from PG that MPG/OP repeatedly writes `computed=true`, `satisfied=false`, and `failed_facts=[public_facts_ready, spread_ok]`.
2. Prove the defect is a cadence gap: the public-fact validity window is five minutes while the watcher interval is ten minutes.
3. Move the watcher to a bounded three-minute interval with a 15-second accuracy window, preserving CPU quota, low-priority scheduling, timeout bounds, and non-persistent startup behavior.
4. Prove the existing candidate projection reports fresh computed-false facts as `computed_not_satisfied`; do not synthesize facts from runtime scope or extend action-time fact validity.

## Task 4: Durable Failure Resolution Without History Loss

**Files:**
- Modify only if required by a demonstrated gap: `src/application/action_time/process_outcome_relevance.py`
- Test: `tests/unit/test_process_outcome_relevance.py`
- Test: `tests/unit/test_tokyo_runtime_server_monitor.py`

1. Preserve unresolved engineering failures after signal expiry so defects cannot collapse into `waiting_for_market`.
2. Prove a newer successful outcome for the same process and lane supersedes an old legacy or typed failure in both candidate and monitor projections.
3. Use existing newer PG success outcomes to close historical monitor noise; never delete or rewrite historical outcomes.

## Task 5: Verification, Release, And Tokyo Acceptance

**Files:**
- Modify as needed: focused tests and deploy verification only.

1. Run focused RED/GREEN tests for all four defect classes.
2. Run relevant integration/release tiers and `scripts/audit_production_runtime_file_io.py`; production cadence must add zero JSON/MD writers and `performance_risk.status` must be `clear`.
3. Commit and push the focused branch, then execute the official Tokyo git-export deployment against the currently deployed head.
4. Verify backend process environment names include exchange account/exchange identity without printing values.
5. Verify all SOR observation cycles return business results rather than HTTP 400.
6. Verify MPG/OP reports `computed_not_satisfied` when spread is outside policy, not detector missing.
7. Verify current monitor state no longer reports the repaired action-time defect after bounded non-executing certification.
8. Confirm no exchange write, order, position, transfer, withdrawal, or profile/sizing expansion occurred during certification.

## Task 6: Deployment-Time Natural Signal Race Closure

**Files:**
- Modify: `scripts/plan_tokyo_runtime_governance_git_deploy.py`
- Test: `tests/unit/test_runtime_signal_watcher_systemd_units.py`
- Test: `tests/unit/test_tokyo_lifecycle_phase_two_deploy.py`

1. Reproduce the production timeline where phase 4 starts the watcher, a signal and Ticket are created, and phase 5/6 certification delays consumption beyond Ticket validity.
2. Prove phase 4 only installs/enables the watcher timer and never starts it.
3. Keep the watcher stopped through lifecycle and 22-scope certification; start it only after capability truth and current projections are committed.
4. Redeploy the exact fix and verify the first post-certification watcher tick cannot inherit a deployment-created stale Ticket.

## Task 7: Natural Live Order Lifecycle Truth And Protection Recovery

**Files:**
- Modify: `src/domain/order_state_machine.py`
- Modify: `src/application/order_lifecycle_service.py`
- Modify: `src/interfaces/api_trading_console.py`
- Modify: `src/application/action_time/exchange_snapshot_provider.py`
- Modify: `src/application/action_time/post_submit_reconciliation_tick.py`
- Modify: `src/application/action_time/exit_protection_materializer.py`
- Modify: `src/application/action_time/protection_recovery_command.py`
- Test: `tests/unit/test_order_lifecycle_service_pending_updates.py`
- Test: `tests/unit/test_ticket_bound_protected_submit_api.py`
- Test: `tests/unit/test_ticket_bound_post_submit_reconciliation_tick.py`

1. Preserve legal immediate market fills by accepting `SUBMITTED -> PARTIALLY_FILLED/FILLED` transitions and emitting the existing fill audit events.
2. Never fabricate fill quantity or average price from requested order fields when the venue reports `FILLED` without complete execution facts; persist exchange acceptance and require read-only reconciliation.
3. Conserve confirmed Entry fill quantity, average price, fee, and fill time from the official exchange snapshot into the protected-submit attempt and lifecycle projection.
4. Allow newer reconciled Entry facts to supersede stale aggregate attempt failure only for bounded recoverable protection states with complete Entry identity and positive execution facts.
5. Route missing SL/TP1 through the durable recovery command path and supersede only the original still-prepared protection commands after recovery is confirmed.
6. Certify the exact production failure shape: exchange accepted Entry, local lifecycle update failed, Entry facts recovered, SL/TP1 recovery commands prepared and confirmed, lifecycle protected, and old protection intents terminally reconciled without duplicate exchange submission.

## Performance And Safety Acceptance

- **Cadence:** no-signal watcher ticks create zero JSON/MD artifacts; PG/current projections remain the only runtime truth.
- **Latency:** public market and internal API calls remain timeout-bounded; no new subprocess is added to each symbol tick.
- **Authority:** deployment and rehearsal grant no FinalGate or Operation Layer bypass.
- **Natural acceptance:** the next fresh eligible signal remains the final proof for actual exchange dispatch; engineering closure is reported separately from natural-event acceptance.
