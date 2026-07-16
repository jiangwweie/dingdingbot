# Active Ticket Exit Policy Adoption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reliably maintain the pre-deployment AVAX Ticket by optimizing the lifecycle oneshot, appending an immutable policy-adoption event, reconciling its TP1 to exact actual-entry 1R, and enabling the existing durable reduce-only mutation authority after exact-head certification.

**Architecture:** Keep the current Ticket immutable and derive one effective policy from either its frozen binding or one append-only adoption event. Keep the current durable exchange-command worker as the only writer. Optimize the oneshot with due-work selection, narrow exact-scope venue reads, stage telemetry, and a non-racing timeout hierarchy before enabling mutation.

**Tech Stack:** Python 3.10 production / Python 3.14 local unit tests, Pydantic v2, SQLAlchemy 2, PostgreSQL 16, Alembic-style migrations, CCXT 4.5.56 production, pytest, systemd.

## Global Constraints

- The existing AVAX Ticket, StrategyGroup, symbol, side, entry, capital, leverage, notional, and scope are immutable.
- TP1 is reduce-only LIMIT GTC with no market fallback.
- Every stop/TP1 mutation uses the existing durable command table and worker.
- Financial values use `decimal.Decimal`.
- No production runtime JSON/MD reads or recurring JSON/MD writes.
- No new entry, withdrawal, transfer, secret mutation, FinalGate bypass, or Operation Layer bypass.
- Program/data-path optimization precedes OS-resource relaxation.
- The unrelated `requirements-runtime.lock` worktree change is never staged.

---

### Task 1: Runner Stage Telemetry And Timeout Hierarchy

**Files:**
- Modify: `scripts/run_ticket_bound_lifecycle_maintenance_once.py`
- Modify: `deploy/systemd/brc-ticket-lifecycle-maintenance.service`
- Test: `tests/unit/test_ticket_bound_lifecycle_global_deadline.py`
- Test: `tests/unit/test_ticket_bound_lifecycle_runner_telemetry.py`

**Interfaces:**
- Produces: `LifecycleStageTelemetry` with `stage_durations_ms`, `exchange_request_count`, `pg_transaction_count`, `peak_rss_kib`, and `deadline_remaining_seconds`.
- Preserves: process JSON result status and `exchange_write_called` authority flags.

- [ ] **Step 1: Write RED tests** proving stage timing is emitted on success and structured deadline failure, peak RSS is a non-negative integer, and the service file uses application deadline 28s, outer timeout 36s, and `TimeoutStartSec=45s`.
- [ ] **Step 2: Run RED tests** with `python3 -m pytest tests/unit/test_ticket_bound_lifecycle_global_deadline.py tests/unit/test_ticket_bound_lifecycle_runner_telemetry.py -q`; expect failures for missing telemetry and the current outer 28s timeout.
- [ ] **Step 3: Implement telemetry** with a monotonic stage context and `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss`; include telemetry in every terminal payload without writing files.
- [ ] **Step 4: Correct timeout hierarchy** by changing only the outer process timeout to 36s and removing the broken `/usr/bin/time %M` dependency from lifecycle service execution.
- [ ] **Step 5: Run GREEN tests** and the existing deadline suite; expect all selected tests to pass.
- [ ] **Step 6: Commit** only Task 1 files with `fix: expose bounded lifecycle stage telemetry`.

### Task 2: Due-Work Selection And Narrow Venue Snapshot

**Files:**
- Modify: `src/application/action_time/lifecycle_maintenance_scheduler.py`
- Modify: `src/application/action_time/exchange_snapshot_provider.py`
- Modify: `src/infrastructure/exchange_gateway.py`
- Modify: `scripts/run_ticket_bound_lifecycle_maintenance_once.py`
- Test: `tests/unit/test_ticket_bound_lifecycle_due_work.py`
- Test: `tests/unit/test_ticket_bound_exchange_snapshot_provider.py`
- Test: `tests/performance/test_ticket_lifecycle_runner_production_shape.py`

**Interfaces:**
- Produces: `select_ticket_bound_lifecycle_due_work(conn, now_ms) -> LifecycleDueWork`.
- Produces: `ExchangeGateway.fetch_ticket_lifecycle_snapshot(scope, conditional_parent_order_ids, recent_fill_limit)`.
- Consumes: exact `TicketBoundExchangeScope` and PG instrument rule snapshot.

- [ ] **Step 1: Write RED due-work tests** for `no_work`, `exchange_truth_due`, `command_reconciliation_due`, `command_dispatch_due`, `policy_market_fact_due`, and `finalization_due`, including `legacy_unbound` policy short-circuit.
- [ ] **Step 2: Run RED due-work tests** and confirm missing selector failure.
- [ ] **Step 3: Implement indexed due-work selector** using exact rows and `EXISTS/LIMIT 1`; initialize the gateway only when selected work requires exchange access.
- [ ] **Step 4: Write RED narrow-adapter tests** proving one exact symbol/position side is queried and `load_markets()` is not called when a current PG instrument rule snapshot is present.
- [ ] **Step 5: Implement narrow snapshot adapter** under the existing exchange gateway boundary; missing/stale rules fail closed and never fall back to file data.
- [ ] **Step 6: Write and run production-shape performance test** for 1,000 unchanged ticks with zero duplicate business events and bounded request counts.
- [ ] **Step 7: Run GREEN suites** for scheduler, snapshot, command worker, lifecycle service, and performance shape.
- [ ] **Step 8: Commit** Task 2 files with `perf: narrow ticket lifecycle maintenance work`.

### Task 3: Append-Only Policy Adoption Schema And Domain

**Files:**
- Create: `migrations/versions/2026-07-16-125_add_active_ticket_exit_policy_adoption.py`
- Create: `src/domain/ticket_exit_policy_adoption.py`
- Modify: `tests/unit/lifecycle_test_schema.py`
- Create: `tests/unit/test_ticket_exit_policy_adoption_migration.py`
- Create: `tests/unit/test_ticket_exit_policy_adoption.py`

**Interfaces:**
- Produces: `TicketExitPolicyAdoptionEligibilitySnapshot` and canonical hash.
- Produces table: `brc_ticket_exit_policy_adoption_events`.
- Extends table: `brc_ticket_exit_policy_current(binding_source, adoption_event_id)`.

- [ ] **Step 1: Write migration RED tests** for columns, constraints, one accepted non-revoked adoption per Ticket, projection fields, and downgrade.
- [ ] **Step 2: Run migration RED tests** and confirm revision 125/module are absent.
- [ ] **Step 3: Implement migration 125** with bounded JSON/JSONB eligibility payload, canonical hash fields, indexes, and append-only application contract.
- [ ] **Step 4: Write domain RED tests** for exact identity, approval ordering, quantities, active protection, command safety, canonical hash, and invalid states.
- [ ] **Step 5: Implement frozen Pydantic domain models** using Decimal and explicit enums; no I/O imports.
- [ ] **Step 6: Run GREEN domain/migration tests** plus migrations 122–124 regressions.
- [ ] **Step 7: Commit** Task 3 files with `feat: add active ticket exit policy adoption authority`.

### Task 4: Eligibility, Adoption Apply, And Effective Binding

**Files:**
- Create: `src/application/action_time/ticket_exit_policy_adoption_service.py`
- Modify: `src/application/action_time/ticket_exit_policy_binding.py`
- Modify: `src/application/action_time/ticket_exit_execution_binding.py`
- Modify: `src/application/action_time/ticket_exit_policy_service.py`
- Create: `scripts/preview_ticket_exit_policy_adoption.py`
- Create: `scripts/apply_ticket_exit_policy_adoption.py`
- Create: `tests/unit/test_ticket_exit_policy_adoption_service.py`
- Modify: `tests/unit/test_ticket_exit_policy_binding.py`
- Modify: `tests/unit/test_ticket_exit_policy_service.py`

**Interfaces:**
- Produces: `evaluate_ticket_exit_policy_adoption_eligibility(conn, ticket_id, exchange_snapshot, owner_authorization_ref, runtime_head, now_ms) -> AdoptionEligibilityResult`.
- Produces: `apply_ticket_exit_policy_adoption(conn, eligibility, expected_eligibility_hash, now_ms) -> AdoptionApplyResult`.
- Produces: `resolve_effective_ticket_exit_policy_binding(conn, ticket_id, now_ms) -> TicketExitPolicyBinding`.

- [ ] **Step 1: Write RED eligibility tests** for exact AVAX-shaped success and every mismatch in the design failure matrix.
- [ ] **Step 2: Run RED tests** and confirm imports/functions are missing.
- [ ] **Step 3: Implement read-only eligibility** from exact Ticket/policy/lifecycle/protection/command/scope facts and caller-provided fresh exchange snapshot.
- [ ] **Step 4: Write RED apply tests** for append-only event, immutable Ticket, CAS projection initialization, idempotency, and conflicting digest rollback.
- [ ] **Step 5: Implement apply and effective resolver**; versioned Ticket binding wins, accepted adoption is second, legacy remains fail-closed.
- [ ] **Step 6: Implement preview/apply CLIs** with PG source only, typed stdout, no file artifacts, and explicit `exchange_write_called=false`.
- [ ] **Step 7: Run GREEN suites** for adoption, binding, execution snapshot, and policy service.
- [ ] **Step 8: Commit** Task 4 files with `feat: adopt approved exit policy for protected tickets`.

### Task 5: Durable TP1 Reprice Command

**Files:**
- Modify: `migrations/versions/2026-07-16-125_add_active_ticket_exit_policy_adoption.py`
- Modify: `src/domain/ticket_bound_exchange_command.py`
- Modify: `src/application/action_time/exchange_command_worker.py`
- Modify: `src/application/action_time/exchange_command_reconciliation.py`
- Modify: `src/application/action_time/ticket_exit_policy_service.py`
- Create: `tests/unit/test_ticket_exit_policy_tp1_reprice.py`
- Modify: `tests/unit/test_ticket_bound_exchange_command_worker.py`

**Interfaces:**
- Adds command source: `exit_policy_tp1_reprice`.
- Produces deterministic two-command sequence: cancel old TP1, then place exact reduce-only LIMIT GTC TP1 after confirmed cancellation and fresh-state revalidation.

- [ ] **Step 1: Write RED tests** for the current AVAX calculation: entry `6.658784615384615385`, stop `6.449`, tick `0.001`, expected TP1 `6.869`, existing TP1 `6.875`, difference six ticks.
- [ ] **Step 2: Write RED sequence tests** proving no replacement is prepared before cancel confirmation, unknown cancellation stops, partial/full fill changes branch, and SL remains untouched.
- [ ] **Step 3: Run RED tests** and confirm source/sequence are unsupported.
- [ ] **Step 4: Implement command-source validation and deterministic IDs** in the existing command authority.
- [ ] **Step 5: Implement cancel-confirm-reread-place state machine** with exact Ticket netting domain, reduce-only, position side, quantity, price, GTC, and no market fallback.
- [ ] **Step 6: Run GREEN tests** plus all command worker/reconciliation/runner mutation suites.
- [ ] **Step 7: Commit** Task 5 files with `feat: reconcile adopted ticket tp1 to actual entry r`.

### Task 6: Postdeploy Acceptance And Unit A/B Deployment

**Files:**
- Modify: `scripts/verify_tokyo_runtime_governance_postdeploy.py`
- Modify: `scripts/tokyo_runtime_deploy_remote_state_machine.py`
- Modify: `tests/unit/test_tokyo_runtime_governance_postdeploy.py`
- Modify: `tests/unit/test_tokyo_runtime_deploy_remote_state_machine.py`
- Modify: `docs/current/P0_ACTIVE_TICKET_EXIT_POLICY_ADOPTION_AND_RUNNER_RELIABILITY_DESIGN.md`

**Interfaces:**
- Postdeploy verifies migration 125, timeout hierarchy, adoption schema, lifecycle capability state, exact release, and performance telemetry.
- Units A/B leave lifecycle mutation disabled and execute zero exchange writes.

- [ ] **Step 1: Write RED postdeploy tests** for migration 125, service timeout hierarchy, adoption table shape, exact SHA, and disabled mutation during A/B.
- [ ] **Step 2: Run RED tests**, implement verifier/deployer checks, and rerun GREEN.
- [ ] **Step 3: Run targeted regression**, production file-I/O audit, full unit tests, deploy dry-run, and Tokyo read-only preflight.
- [ ] **Step 4: Commit** with `fix: certify active ticket adoption release`.
- [ ] **Step 5: Deploy exact head** with normal crash-safe Tokyo deploy while accepting the protected AVAX lifecycle.
- [ ] **Step 6: Observe 240 natural ticks** and require zero timeout/OOM/exchange write before Unit C.

### Task 7: Unit C Exact AVAX Adoption And Mutation Activation

**Files:**
- No new production code beyond Tasks 1–6.
- Runtime operations use the committed preview/apply/capability/deploy commands.

**Interfaces:**
- Consumes exact Ticket id, policy id/version/hash, owner authorization ref, fresh PG/exchange snapshot, exact runtime head, and lifecycle proof v2.
- Produces one accepted adoption event, current policy projection, optional TP1 reprice durable commands, and enabled lifecycle mutation capability.

- [ ] **Step 1: Quiesce lifecycle writer** and capture fresh read-only PG/exchange snapshot.
- [ ] **Step 2: Run exact adoption preview** and verify the expected six-tick TP1 mismatch with no other blocker.
- [ ] **Step 3: Apply adoption by eligibility CAS**; verify Ticket unchanged and exchange writes zero.
- [ ] **Step 4: Generate exact-head Action-Time/lifecycle proof v2** and enable `ticket_lifecycle_durable_mutation`.
- [ ] **Step 5: Resume lifecycle writer** and observe cancel-confirm-reprice or the fresh TP1 state branch.
- [ ] **Step 6: Verify PG/exchange order lineage, SL continuity, command outcomes, monitor, notification, memory, timeouts, and file-I/O audit.**
- [ ] **Step 7: Stop contained on any contradiction** by disabling mutation before any release rollback.

### Task 8: Final Verification And Release Handoff

**Files:**
- Update: `docs/current/P0_ACTIVE_TICKET_EXIT_POLICY_ADOPTION_AND_RUNNER_RELIABILITY_DESIGN.md` status/evidence only after real verification.

**Interfaces:**
- Produces a release-readiness and live-chain-position report grounded in exact commit, tests, server units, PG rows, and exchange orders.

- [ ] **Step 1: Run complete targeted tests and full unit suite**; report every failure or setup error exactly.
- [ ] **Step 2: Run production file-I/O audit** and require `performance_risk.status=clear`.
- [ ] **Step 3: Run postdeploy verifier and read-only exchange/PG reconciliation** against the exact deployed SHA.
- [ ] **Step 4: Re-read this plan and design acceptance criteria** and map each to evidence.
- [ ] **Step 5: Commit evidence/status documentation only if all required evidence exists**.
