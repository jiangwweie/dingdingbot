# Tokyo Controlled Exit And Deployment Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Every production behavior follows test-first RED/GREEN/refactor.

**Goal:** Add a permanent, source-owned Controlled Exit capability and make Tokyo release deployment one resumable five-phase workflow: `orient -> optional drain -> flat cutover -> target verify -> seal`.

**Architecture:** The current deployed Trading Kernel remains the sole owner of every live Ticket. An explicit immutable deployment-drain authorization selects the complete bounded active Ticket set, calls the existing `request_exit()` application boundary, and lets the current Lifecycle and Reconciliation workers finish the durable reduce-only exit chain. The deployment orchestrator uses one state classification model and enters the existing flat compatible upgrade only after all source and exchange closure gates pass. Local certification is keyed by the exact Release Commit and is not repeated during fact-only wait/retry cycles.

**Tech Stack:** Python 3.12, frozen Pydantic v2 models, SQLAlchemy Core async, PostgreSQL/Alembic, pytest/pytest-asyncio, SSH stdin bridge, systemd, Ruff, Mypy.

## Global Constraints

- No production operation is authorized by this implementation task. Stop after local verification and creation of a new exact Release Commit.
- No DML lifecycle conversion, direct Binance close/cancel, venue client in the bridge, active-position handover, dual write, old-schema worker, downgrade, fallback, or old-schema reader after migration.
- The source release remains authoritative until every Ticket is terminal, external position is flat, owned order residue is absent, Reservation and Netting Domain are released, Commands and Incidents are resolved, and required Settlement/Review is complete.
- Entry remains stopped, disabled, and protected by `/etc/brc/trading-kernel.write-fenced` throughout drain and deployment.
- Drain is opt-in. The default deployment remains fail-closed and write-free when active Tickets exist.
- The operator may provide only the exact target commit and immutable drain authorization identity; account, venue, instrument, side, quantity, price, and Ticket list are derived from current authority.
- The hard active-Ticket bound is three and must also respect current Owner Policy capacity.
- Each eligible Ticket receives at most one `ExitRequested` generation. Unknown outcome is reconciled and never blindly resent.
- `0002_sor_v3_strategy_group_capacity -> 0003_portfolio_admission_observability` remains the only compatible schema transition.
- The same exact Release Commit receives one complete local certification. Later deployment waits or retries refresh only PostgreSQL, systemd, release-marker, and Binance facts unless code or certification inputs change.

---

### Task 1: Typed Controlled Exit authority and pure state classification

**Files:**
- Create: `src/trading_kernel/application/controlled_exit.py`
- Test: `tests/trading_kernel/unit/test_controlled_exit.py`

**Interfaces:**
- Add frozen `ControlledExitAuthorization` with exact `purpose`, immutable nonblank `authorization_id`, and lowercase 40-hex `target_commit`.
- Initially permit only `purpose="deployment_drain"`.
- Produce the canonical audit reason `deployment_drain:<authorization_id>:<target_commit>`.
- Add typed Ticket classifications: `eligible`, `in_progress`, `terminal`, and `blocked`.
- Eligible Aggregate states are exactly `position_protected` and `runner_protected`; progressing EXIT/Reconciliation/Settlement/Review states are resume-only.

- [ ] **Step 1: Write RED tests for authority validation and canonical reason**
- [ ] **Step 2: Run `pytest tests/trading_kernel/unit/test_controlled_exit.py -q` and confirm missing interfaces fail**
- [ ] **Step 3: Implement the minimal frozen authority and pure classifier**
- [ ] **Step 4: Re-run the unit file and confirm GREEN**

### Task 2: Bounded deterministic active Ticket selection

**Files:**
- Modify: `src/trading_kernel/application/ports.py`
- Modify: `src/trading_kernel/infrastructure/pg_repositories.py`
- Modify: `src/trading_kernel/infrastructure/pg_unit_of_work.py`
- Test: `tests/trading_kernel/integration/test_controlled_exit.py`

**Interfaces:**
- Add a repository method that returns the complete current nonterminal Ticket/Aggregate projection for one configured production runtime scope in stable Ticket identity order.
- Use bounded current-state predicates and reject more than the lesser of current Policy capacity and hard bound `3`.
- Include only fields required for classification and `request_exit()`; do not scan Event history.

- [ ] **Step 1: Write RED PostgreSQL tests for zero, one, multiple, deterministic ordering, and overflow**
- [ ] **Step 2: Run the integration file and confirm the repository boundary is absent**
- [ ] **Step 3: Implement the bounded repository query and UoW exposure**
- [ ] **Step 4: Re-run the integration file and confirm GREEN**

### Task 3: Idempotent Controlled Exit application service

**Files:**
- Modify: `src/trading_kernel/application/controlled_exit.py`
- Modify: `src/trading_kernel/application/reconcile_ticket.py`
- Test: `tests/trading_kernel/unit/test_controlled_exit.py`
- Test: `tests/trading_kernel/integration/test_controlled_exit.py`
- Test: `tests/trading_kernel/full_chain/test_ticket_lifecycle.py`

**Interfaces:**
- Add `request_controlled_exit(...)` that selects every bounded active Ticket, classifies it, and invokes the existing `request_exit()` only for eligible protected states.
- Use one short transaction per Ticket and preserve optimistic aggregate version checks.
- Return a typed summary containing requested, in-progress, terminal, and blocked Ticket identities without creating a second progress store.
- Do not cancel protection or dispatch venue writes in this service.

- [ ] **Step 1: Write RED tests for one request, multiple requests, resume, unsupported state, and crash-after-first-request**
- [ ] **Step 2: Confirm RED, including no duplicate EXIT Command on retry**
- [ ] **Step 3: Implement the minimal orchestration around existing `request_exit()`**
- [ ] **Step 4: Confirm GREEN and unchanged existing exit-chain tests**

### Task 4: Native current-release Controlled Exit CLI

**Files:**
- Create: `scripts/trading_kernel/request_controlled_exit.py`
- Test: `tests/trading_kernel/unit/test_request_controlled_exit.py`
- Test: `tests/trading_kernel/architecture/test_controlled_exit_architecture.py`

**Interfaces:**
- Accept exact `--purpose deployment_drain`, `--authorization-id`, and `--target-commit`.
- Load only current runtime environment and current-release infrastructure adapters.
- Print a bounded credential-free JSON result.
- Reject wrong runtime identity, schema, scope, open Incident, unresolved Command, exchange contradiction, missing protection, or unsupported Ticket state before the first lifecycle write.
- Contain no venue mutation and no SQL lifecycle update outside the application/UoW boundary.

- [ ] **Step 1: Write RED parser, validation, output, and architecture tests**
- [ ] **Step 2: Confirm RED**
- [ ] **Step 3: Implement the native CLI as a thin application adapter**
- [ ] **Step 4: Confirm GREEN and run a local disposable-PostgreSQL CLI rehearsal**

### Task 5: Bounded `0002` SSH-stdin bridge

**Files:**
- Create: `scripts/trading_kernel/request_controlled_exit_0002_bridge.py`
- Modify: `scripts/trading_kernel/deploy_tokyo_release.py`
- Test: `tests/trading_kernel/unit/test_request_controlled_exit_0002_bridge.py`
- Test: `tests/trading_kernel/architecture/test_controlled_exit_architecture.py`

**Interfaces:**
- Stream the committed bridge through SSH stdin to `/opt/brc/current/.venv/bin/python` without writing it into the release tree.
- Import the exact current `/opt/brc/current` package and call its existing `request_exit()` application use case.
- Require exact source commit, `0002_sor_v3_strategy_group_capacity`, runtime seed/scope/account identity, protection, command, Incident, and exchange facts before the first write.
- Include no reducer copy, SQL lifecycle DML, exchange client, target-release import, or post-migration path.

- [ ] **Step 1: Write RED tests for generated SSH command, stdin payload, identity refusal, and forbidden imports**
- [ ] **Step 2: Confirm RED**
- [ ] **Step 3: Implement the smallest bridge and backend invocation**
- [ ] **Step 4: Confirm GREEN and architecture boundaries**

### Task 6: One five-phase Tokyo deployment orchestrator

**Files:**
- Create: `scripts/trading_kernel/deployment_control.py`
- Modify: `scripts/trading_kernel/deploy_tokyo_release.py`
- Modify: `tests/trading_kernel/unit/test_deploy_tokyo_release.py`
- Create: `tests/trading_kernel/unit/test_deployment_control.py`

**Interfaces:**
- Extend `DeploymentPlan` with `drain_active_tickets`, `drain_authorization_id`, and positive `drain_timeout_seconds`.
- Reject Drain with `--enable-entry`; reject authorization without Drain and Drain without authorization.
- Implement one phase sequence: `orient`, optional `drain`, `flat_cutover`, `target_verify`, `seal`.
- Reuse one normalized source-state classification for no-op, eligible, progressing, blocked, and fully flat facts.
- During Drain, keep Observation/Lifecycle/Reconciliation active and Entry stopped/disabled/fenced.
- On timeout or blocked state, return without migration and retain source safety workers.
- Enter the unchanged compatible-upgrade migration only after a fresh final flat gate.

- [ ] **Step 1: Write RED plan-validation and phase-order tests**
- [ ] **Step 2: Add RED tests for zero-active no-op, successful drain, resume, timeout, rejected/unknown EXIT, residue, and contradiction**
- [ ] **Step 3: Confirm RED**
- [ ] **Step 4: Implement the dedicated state/phase module and reduce the release script to sequencing**
- [ ] **Step 5: Confirm GREEN and verify no alternate handover/migration branch exists**

### Task 7: Unified historical terminal classification

**Files:**
- Create or modify: `src/trading_kernel/infrastructure/terminal_classification.py`
- Modify: `scripts/trading_kernel/verify_schema.py`
- Modify: `src/trading_kernel/infrastructure/tokyo_cutover_adapter.py`
- Modify: `migrations/trading_kernel/versions/0003_portfolio_admission_observability.py`
- Modify: `tests/trading_kernel/integration/test_portfolio_admission_observability_migration.py`
- Modify: `tests/trading_kernel/integration/test_portfolio_admission_flat_compatible_deployment.py`

**Classification:**
- Exposure terminal: `terminal / terminal`, requiring Settlement and current effective Review.
- No-exposure terminal: exactly `leverage_rejected / leverage_rejected`, `entry_rejected / entry_rejected`, and `entry_reconciled_absent / entry_reconciled_absent`, requiring `terminal_at_ms` and zero exposure/authority/residue but no fabricated Settlement/Review.
- Every other nonterminal pair blocks migration.

- [ ] **Step 1: Write RED production-shaped `0002` fixtures for all allowed and blocked pairs**
- [ ] **Step 2: Confirm current verifier/migration incorrectly blocks no-exposure terminal rejection**
- [ ] **Step 3: Implement one explicit predicate shape in verifier, cutover inspection, and Alembic atomic guard**
- [ ] **Step 4: Confirm allowed lineage passes, residue fails, exposure history without Review fails, and preservation digest is unchanged**

### Task 8: SHA-keyed certification and non-overlapping test command

**Files:**
- Modify: `scripts/trading_kernel/deploy_tokyo_release.py`
- Modify or create: `scripts/trading_kernel/certify_release_candidate.py`
- Modify: `docs/superpowers/specs/2026-08-03-portfolio-admission-observability-test-cases.md`
- Test: `tests/trading_kernel/unit/test_deploy_tokyo_release.py`
- Test: `tests/trading_kernel/unit/test_release_certification.py`

**Contract:**
- One complete local certification manifest is bound to exact commit, clean tree, schema head, Registry digest, Policy/seed identity, and exact test command set.
- Deployment may consume that manifest only when every bound input matches.
- Wait/retry refreshes live facts only and never re-runs the full test suite for the same exact certified commit.
- Replace the duplicated `four directories + tests/trading_kernel` sequence with one non-overlapping command set.
- Do not add Template DB, broad pytest parallelism, or marker restructuring to this release.

- [ ] **Step 1: Write RED manifest identity/reuse/refusal tests**
- [ ] **Step 2: Confirm RED**
- [ ] **Step 3: Implement the minimal local certification manifest and deployment validation**
- [ ] **Step 4: Update the test specification to one non-overlapping suite and confirm repeat deployment performs fact refresh only**

### Task 9: Deployment contract and design status

**Files:**
- Modify: `docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md`
- Modify: `docs/superpowers/specs/2026-08-04-tokyo-deployment-drain-design.md`

- [ ] **Step 1: Document permanent Controlled Exit authority and the five phases**
- [ ] **Step 2: Document source-worker ownership, timeout/resume behavior, and post-migration fix-forward boundary**
- [ ] **Step 3: Document exposure-bearing versus no-exposure terminal evidence**
- [ ] **Step 4: Mark the design implemented only after verification passes**
- [ ] **Step 5: Do not copy volatile production counts, Ticket IDs, or current release identity into stable documents**

### Task 10: Local verification and production-shaped rehearsal

- [ ] **Step 1: Run targeted Controlled Exit and deployment unit tests**
- [ ] **Step 2: Run targeted PostgreSQL integration and exact `0002 -> 0003` migration tests**
- [ ] **Step 3: Run the non-overlapping full Trading Kernel suite exactly once**
- [ ] **Step 4: Run architecture tests, Ruff, and Mypy**
- [ ] **Step 5: Run production file-I/O audit and confirm no no-signal JSON/Markdown output path was introduced**
- [ ] **Step 6: Run a production-shaped disposable PostgreSQL rehearsal for orient -> drain request -> closure projection -> flat cutover preflight**
- [ ] **Step 7: Inspect `git diff --check`, complete diff, generated files, credential leakage, and forbidden compatibility patterns**
- [ ] **Step 8: Record exact commands, test counts, durations, and evidence in the implementation handoff**

### Task 11: New exact Release Commit

- [ ] **Step 1: Commit implementation in focused logical commits while preserving unrelated user work**
- [ ] **Step 2: After final verification, create one final candidate commit if documentation/evidence changed**
- [ ] **Step 3: Resolve and report the exact lowercase 40-hex Release Commit**
- [ ] **Step 4: Confirm the worktree is clean and the commit contains the complete implementation**

### Task 12: Stop at the production confirmation gate

- [ ] **Step 1: Do not update the heartbeat authorization automatically**
- [ ] **Step 2: Do not execute Tokyo Drain, Binance write, service mutation, migration, deployment, tag creation, or roadmap production-state update**
- [ ] **Step 3: Report the exact new Release Commit, local certification evidence, simplified production command, and remaining live gates**
- [ ] **Step 4: Wait for a new explicit Owner production-execution confirmation tied to the new exact Release Commit**

