# FFC73899 And Dual-Position Account Risk V0 Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Repository and current session constraints prohibit subagent implementation for this merge.

**Goal:** Produce one locally certified two-parent merge of release commit `ffc73899` and budget commit `5b67181e` in an isolated sibling worktree without modifying, rebasing, deploying, or activating either source line.

**Architecture:** Start from the exact release commit, merge the exact budget commit with `--no-commit`, preserve release runtime/lifecycle behavior, and extend it with the budget branch's account-capacity invariants. Keep release migrations `121-125`, renumber budget migrations to `126-133`, preserve one Ticket/FinalGate/Operation Layer chain, and stop after local PostgreSQL and full-suite certification.

**Tech Stack:** Git worktrees, Python 3, Pydantic v2, `decimal.Decimal`, SQLAlchemy 2, Alembic, PostgreSQL 16, pytest, CCXT `4.5.56`, `ijson>=3.5.1,<4.0.0`, systemd release validation.

## Global Constraints

- Work only in `/Users/jiangwei/Documents/brc-merge-ffc73899-dual-position-risk-v0` on `codex/integrate-ffc73899-dual-position-risk-v0`.
- Release input is exactly `ffc73899f2749208074a06b9c7384e74911a400d`.
- Budget input is exactly `5b67181e2d287fb306bae953075c89e2c6be32ab`.
- The common ancestor is exactly `2001644581cccc968ba695d3ff129960db6a7e84`.
- Do not modify `/Users/jiangwei/Documents/final`, `/Users/jiangwei/Documents/final/.worktrees/release-risk-analysis-20260714`, or `/Users/jiangwei/Documents/brc-dual-position-account-risk-v0`.
- Do not stage or modify the release worktree's unrelated `requirements-runtime.lock` change.
- Do not absorb `faf49004`, `32cc84fd`, or `fdad0e93` in this merge; they form a later release-delta intake.
- Preserve release Alembic revisions `121-125`; integrated account-risk head is `133`.
- Restore historical migration `086` exactly from `ffc73899`; all new schema arrives through forward migrations.
- Preserve `ccxt==4.5.56`; add only `ijson>=3.5.1,<4.0.0` from the budget dependency delta.
- Keep one open real-submit Action-Time lane, one Ticket lifecycle owner, one durable exchange-command authority, ticket-only FinalGate identity, and ticket-plus-pass Operation Layer identity.
- PG/current remains the only production runtime authority; no JSON/Markdown/YAML/JSONL runtime fallback or recurring report writer is allowed.
- Financial values use `decimal.Decimal`; do not introduce float-based price, quantity, risk, margin, fee, or PnL calculations.
- No deploy, exchange write, policy activation, live-profile change, sizing-default change, withdrawal, transfer, credential mutation, or source-branch push occurs in this plan.
- No-signal cadence creates `0` JSON/MD files and `0` Claim/Ticket/ExposureEpisode rows.
- Capacity transactions perform `0` network calls and `0` subprocess calls.
- The complete test suite is announced before execution and runs only after focused and PostgreSQL gates pass.

## Program Control Block

**Global Authority Model:** Owner controls policy; system executes process; Tradeability Decision answers can-trade; Runtime Safety State answers live-submit safety; review updates strategy governance.

**Chain Position:** `release code integration -> migration lineage -> exact instrument/account facts -> capacity claim -> Ticket -> FinalGate -> lifecycle reprojection -> local release certification`.

**Live Enablement State Before:** release behavior exists at `ffc73899`; budget capability exists locally at `5b67181e`; no combined release exists.

**Live Enablement State After:** one local combined capability is certified; production state, live-submit scope, and Owner policy remain unchanged.

**Blocker Removed Or Reclassified:** duplicate Alembic revisions, split release/budget runtime semantics, and unverified cross-branch lifecycle interaction become one machine-tested local integration.

**Per-Symbol / Per-Fact Acceptance:** all six current Event Specs and all 22 registered lanes preserve release behavior; exact instrument, account snapshot, capacity, protection, policy, and lifecycle facts remain typed and fail closed.

**Stop Condition:** stop before deployment after clean merge history, migration head `133`, focused/PG/full-suite green, file-I/O audit clear, and local release preparation pass.

**Capability Unlocked:** a reviewable local release candidate combining release lifecycle fixes with asset-neutral two-position account-capacity enforcement.

**Next Engineering Bottleneck:** separate intake of `ffc73899..fdad0e93`, followed by shadow certification and an independent deployment/policy decision.

**Rehearsal/Simulation Boundary:** all work is local or disposable-PostgreSQL; no production signal, Ticket, order, exchange command, or policy row is created.

---

### Task 1: Re-Verify Isolation And Frozen Inputs

**Task ID:** `MERGE-DAR-01`

**Goal:** Prove the integration directory has no tracked changes, contains only the two approved untracked planning documents, and both source identities are unchanged before any merge mutation.

**Why:** A moving source ref or dirty integration worktree makes every later conflict and test result ambiguous.

**Allowed files:** None.

**Forbidden files:** Every tracked file; this task is read-only.

**Interfaces:**
- Consumes: local Git object database and worktree metadata.
- Produces: exact-ref and clean-baseline assertions on stdout only.

- [ ] **Step 1: Verify path, branch, HEAD, and clean status**

```bash
test "$(pwd -P)" = "/Users/jiangwei/Documents/brc-merge-ffc73899-dual-position-risk-v0"
test "$(git branch --show-current)" = "codex/integrate-ffc73899-dual-position-risk-v0"
test "$(git rev-parse HEAD)" = "ffc73899f2749208074a06b9c7384e74911a400d"
test -z "$(git status --porcelain --untracked-files=no)"
actual_untracked="$(git status --porcelain | LC_ALL=C sort)"
expected_untracked=$'?? docs/superpowers/plans/2026-07-17-ffc73899-dual-position-account-risk-v0-merge.md\n?? docs/superpowers/specs/2026-07-17-ffc73899-dual-position-account-risk-v0-integration-design.md'
test "$actual_untracked" = "$expected_untracked"
```

Expected: all commands exit `0` with no output. The two documents remain untracked until the final merge commit so its first parent stays exactly `ffc73899`.

- [ ] **Step 2: Verify the exact budget source and common ancestor**

```bash
test "$(git rev-parse codex/dual-position-account-risk-v0^{commit})" = "5b67181e2d287fb306bae953075c89e2c6be32ab"
test "$(git merge-base ffc73899 5b67181e2d287fb306bae953075c89e2c6be32ab)" = "2001644581cccc968ba695d3ff129960db6a7e84"
test "$(git rev-list --left-right --count ffc73899...5b67181e2d287fb306bae953075c89e2c6be32ab)" = $'88\t41'
```

Expected: all commands exit `0`.

- [ ] **Step 3: Verify source worktrees have not been repointed**

```bash
test "$(git -C /Users/jiangwei/Documents/brc-dual-position-account-risk-v0 rev-parse HEAD)" = "5b67181e2d287fb306bae953075c89e2c6be32ab"
test "$(git -C /Users/jiangwei/Documents/final rev-parse HEAD)" = "2001644581cccc968ba695d3ff129960db6a7e84"
git -C /Users/jiangwei/Documents/final/.worktrees/release-risk-analysis-20260714 status --short --branch
```

Expected: the budget source remains at `5b67181e`; the root release checkout remains at `2001644581`; the moving release worktree may show its pre-existing `requirements-runtime.lock` modification and must not be changed.

- [ ] **Step 4: Verify the known merge inventory without writing a merge tree**

```bash
base=2001644581cccc968ba695d3ff129960db6a7e84
test "$(comm -12 <(git diff --name-only "$base"..ffc73899 | LC_ALL=C sort) <(git diff --name-only "$base"..5b67181e | LC_ALL=C sort) | wc -l | tr -d ' ')" = "38"
test "$(git merge-tree --trivial-merge "$base" ffc73899 5b67181e | rg -c '^\+<<<<<<< ')" = "23"
```

Expected: `38` overlapping files and `23` conflict hunks.

**Tests:** exact Git assertions above.

**Done When:** all identities and counts match and no tracked file changed.

**Hard Stop:** any SHA, branch, path, or merge-base mismatch.

---

### Task 2: Establish The Isolated Python Baseline

**Task ID:** `MERGE-DAR-02`

**Goal:** Create an integration-local virtual environment and prove the frozen release base passes short structural tests.

**Why:** Reusing a source worktree's environment can hide dependency drift; the integration needs its own reproducible environment.

**Allowed files:** `.venv/**`, ignored pytest/cache files.

**Forbidden files:** tracked source, tests, migrations, docs, and both source worktrees.

**Interfaces:**
- Consumes: release `requirements.txt` at `ffc73899`.
- Produces: `.venv/bin/python` for all later commands.

- [ ] **Step 1: Create the local virtual environment**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

Expected: dependency installation exits `0`; `ccxt` resolves to `4.5.56`.

- [ ] **Step 2: Verify certified adapter and test runtime**

```bash
.venv/bin/python -c 'import ccxt; assert ccxt.__version__ == "4.5.56"'
.venv/bin/python -m pytest --version
```

Expected: both commands exit `0`.

- [ ] **Step 3: Run the short release baseline**

```bash
.venv/bin/python -m pytest -q \
  tests/unit/test_pg_migration_identifier_names.py \
  tests/unit/test_tokyo_runtime_governance_release_prep.py \
  tests/unit/test_ticket_bound_lifecycle_scheduler.py \
  tests/unit/test_ticket_bound_post_submit_reconciliation_tick.py \
  tests/unit/test_ticket_exit_policy_tp1_reprice.py
```

Expected: exit `0`, no skipped PostgreSQL claim, and no exchange write.

- [ ] **Step 4: Verify tracked status is still clean**

```bash
test -z "$(git status --porcelain --untracked-files=no)"
```

Expected: exit `0`.

**Tests:** five focused release test modules.

**Done When:** the release baseline is green in an integration-local environment.

**Hard Stop:** a baseline failure or any tracked environment output.

---

### Task 3: Start The Exact Two-Parent Merge And Freeze The Conflict Set

**Task ID:** `MERGE-DAR-03`

**Goal:** Enter a real merge state against the frozen budget commit without committing or resolving anything implicitly.

**Why:** The final result must preserve both source histories and expose every conflict for semantic review.

**Allowed files:** integration worktree and index only.

**Forbidden files:** both source worktrees and Git refs other than the integration branch.

**Interfaces:**
- Consumes: `ffc73899` as first parent and `5b67181e` as `MERGE_HEAD`.
- Produces: one unresolved merge state with the expected conflict inventory.

- [ ] **Step 1: Start the merge without auto-commit**

```bash
git merge --no-commit --no-ff 5b67181e2d287fb306bae953075c89e2c6be32ab
```

Expected: non-zero exit because conflicts exist; `MERGE_HEAD` is created and no commit is written.

- [ ] **Step 2: Verify merge parents**

```bash
test "$(git rev-parse HEAD)" = "ffc73899f2749208074a06b9c7384e74911a400d"
test "$(git rev-parse MERGE_HEAD)" = "5b67181e2d287fb306bae953075c89e2c6be32ab"
```

Expected: both assertions exit `0`.

- [ ] **Step 3: Verify the exact unresolved-file set**

```bash
git diff --name-only --diff-filter=U | LC_ALL=C sort
```

Expected set:

```text
scripts/prepare_tokyo_runtime_governance_release.py
scripts/run_ticket_bound_lifecycle_maintenance_once.py
scripts/runtime_active_observation_monitor.py
src/application/action_time/account_safe_facts.py
src/infrastructure/runtime_control_state_repository.py
tests/integration/test_runtime_causal_integrity_postgres.py
tests/support/runtime_control_state_schema.py
tests/unit/test_action_time_finalgate_preflight_materialization.py
tests/unit/test_action_time_full_chain_impact.py
tests/unit/test_action_time_operation_layer_handoff_materialization.py
tests/unit/test_pg_migration_identifier_names.py
tests/unit/test_pg_promotion_action_time_lane_materialization.py
tests/unit/test_runtime_control_state_repository.py
tests/unit/test_ticket_bound_lifecycle_scheduler.py
tests/unit/test_ticket_bound_post_submit_reconciliation_tick.py
tests/unit/test_ticket_bound_runtime_safety_state_materialization.py
tests/unit/test_tokyo_runtime_governance_release_prep.py
```

Expected: exactly the 17 paths above. `tests/unit/lifecycle_test_schema.py` is a
semantic auto-merge audit target in Task 4, but it is not one of the 17 textual
conflict files.

- [ ] **Step 4: Confirm no source ref moved**

```bash
test "$(git rev-parse codex/dual-position-account-risk-v0)" = "5b67181e2d287fb306bae953075c89e2c6be32ab"
```

Expected: exit `0`.

**Tests:** Git index and merge-parent assertions.

**Done When:** the integration worktree is in the expected unresolved merge state.

**Hard Stop:** unexpected merge parent, unexpected source SHA, or source-worktree mutation.

---

### Task 4: Replace The Duplicate Migration Lineage With Revisions 126-133

**Task ID:** `MERGE-DAR-04`

**Goal:** Produce one forward-only Alembic chain after release revision `125` without altering historical migration `086`.

**Why:** Duplicate revision IDs are the first release blocker and cannot be repaired by ordinary conflict resolution.

**Files:**
- Restore: `migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py`
- Rename/modify: eight budget migration files listed below
- Modify: `tests/unit/test_pg_migration_identifier_names.py`
- Modify: `tests/support/runtime_control_state_schema.py`
- Modify: `tests/unit/lifecycle_test_schema.py`
- Modify: `scripts/prepare_tokyo_runtime_governance_release.py`
- Modify: `tests/unit/test_tokyo_runtime_governance_release_prep.py`
- Test: all migration tests for revisions `121-133`

**Interfaces:**
- Produces: one Alembic chain `120 -> release 121-125 -> account-risk 126-133`.
- Preserves: release exit-policy tables and current production upgrade history.

- [ ] **Step 1: Restore migration 086 from the release parent**

```bash
git restore --source=ffc73899f2749208074a06b9c7384e74911a400d --staged --worktree -- \
  migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py
test "$(git hash-object migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py)" = \
  "$(git rev-parse ffc73899:migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py)"
```

Expected: byte identity with release migration `086`.

- [ ] **Step 2: Rename the eight budget migrations**

```bash
git mv migrations/versions/2026-07-14-121_create_account_risk_policy.py migrations/versions/2026-07-17-126_create_account_risk_policy.py
git mv migrations/versions/2026-07-14-122_create_account_risk_current_projections.py migrations/versions/2026-07-17-127_create_account_risk_current_projections.py
git mv migrations/versions/2026-07-14-123_repair_terminal_budget_reservations.py migrations/versions/2026-07-17-128_repair_terminal_budget_reservations.py
git mv migrations/versions/2026-07-14-124_add_account_capacity_reservation_scope.py migrations/versions/2026-07-17-129_add_account_capacity_reservation_scope.py
git mv migrations/versions/2026-07-14-125_add_account_capacity_claim_policy_event.py migrations/versions/2026-07-17-130_add_account_capacity_claim_policy_event.py
git mv migrations/versions/2026-07-15-126_expand_asset_neutral_account_risk_identity.py migrations/versions/2026-07-17-131_expand_asset_neutral_account_risk_identity.py
git mv migrations/versions/2026-07-15-127_backfill_asset_neutral_account_risk_identity.py migrations/versions/2026-07-17-132_backfill_asset_neutral_account_risk_identity.py
git mv migrations/versions/2026-07-15-128_enforce_asset_neutral_account_risk_identity.py migrations/versions/2026-07-17-133_enforce_asset_neutral_account_risk_identity.py
```

Expected: all eight `git mv` commands exit `0`.

- [ ] **Step 3: Apply the exact revision mapping with `apply_patch`**

Set each module header and Alembic variable to:

```text
126: Revision ID 126, Revises 125, revision="126", down_revision="125"
127: Revision ID 127, Revises 126, revision="127", down_revision="126"
128: Revision ID 128, Revises 127, revision="128", down_revision="127"
129: Revision ID 129, Revises 128, revision="129", down_revision="128"
130: Revision ID 130, Revises 129, revision="130", down_revision="129"
131: Revision ID 131, Revises 130, revision="131", down_revision="130"
132: Revision ID 132, Revises 131, revision="132", down_revision="131"
133: Revision ID 133, Revises 132, revision="133", down_revision="132"
```

Do not alter table, constraint, index, backfill, timeout, or downgrade semantics while renumbering.

- [ ] **Step 4: Update exact migration consumers**

Use `apply_patch` to make these exact changes:

```text
scripts/prepare_tokyo_runtime_governance_release.py latest migration -> 2026-07-17-133_enforce_asset_neutral_account_risk_identity.py
scripts/prepare_tokyo_runtime_governance_release.py expected minimum migrations -> 133
tests/unit/test_pg_migration_identifier_names.py expected account-risk revisions -> 126-133
tests/support/runtime_control_state_schema.py account-risk upgrade order -> 126-133
tests/unit/lifecycle_test_schema.py latest schema head -> 133
tests/unit/test_tokyo_runtime_governance_release_prep.py expected latest migration -> 2026-07-17-133_enforce_asset_neutral_account_risk_identity.py
```

- [ ] **Step 5: Prove no duplicate revision or stale filename remains**

```bash
rg -n 'Revision ID: 12[1-8]|revision: str = "12[1-8]"|down_revision: .*"12[0-8]"' \
  migrations/versions/2026-07-17-12*.py \
  migrations/versions/2026-07-17-13*.py
rg -n '2026-07-1[45]-12[1-8]_(create_account|repair_terminal|add_account|expand_asset|backfill_asset|enforce_asset)' \
  migrations scripts src tests docs/current
.venv/bin/python -m alembic heads
```

Expected: the first command shows only the intended new chain, the stale-filename search returns no matches, and Alembic prints exactly `133 (head)`.

- [ ] **Step 6: Run migration-focused tests**

```bash
.venv/bin/python -m pytest -q \
  tests/unit/test_exit_execution_safety_migration.py \
  tests/unit/test_ticket_exit_policy_migration.py \
  tests/unit/test_ticket_exit_policy_canary_migration.py \
  tests/unit/test_lifecycle_mutation_enablement_proof_migration.py \
  tests/unit/test_ticket_exit_policy_adoption_migration.py \
  tests/unit/test_account_risk_policy_migration.py \
  tests/unit/test_account_risk_current_migration.py \
  tests/unit/test_terminal_budget_reservation_repair_migration.py \
  tests/unit/test_asset_neutral_account_risk_migrations.py \
  tests/unit/test_pg_migration_identifier_names.py
```

Expected: exit `0` with no skipped test.

**Done When:** migration `086` matches release, Alembic has one head `133`, and all migration tests pass.

**Hard Stop:** duplicate head, historical migration drift, destructive backfill, or skipped PostgreSQL-required migration proof.

---

### Task 5: Resolve Dependencies And Accept Budget-Only Pure Boundaries

**Task ID:** `MERGE-DAR-05`

**Goal:** Import the budget branch's pure domain, streaming, and bounded-repository boundaries while preserving the release runtime dependency set.

**Why:** These files provide the new capability with the lowest overlap risk and establish interfaces consumed by later conflict resolutions.

**Files:**
- Modify: `requirements.txt`
- Add: `src/domain/account_capacity_claim.py`
- Add: `src/domain/account_risk.py`
- Add: `src/domain/instrument_risk_identity.py`
- Add: `src/infrastructure/account_capacity_hot_path_repository.py`
- Add: `src/infrastructure/streaming_http_json.py`
- Add: `src/infrastructure/binance_usdm_streaming_signed_reader.py`
- Add: `src/infrastructure/binance_usdm_account_risk_snapshot.py`
- Test: corresponding new unit tests

**Interfaces:**
- Produces: `InstrumentRiskIdentity`, `InstrumentRuleSnapshotRef`, `RiskClusterMembershipSnapshotRef`.
- Produces: `AccountCapacityClaimPayload`, `capacity_claim_hash`, `reservation_idempotency_key`, `revalidate_capacity_totals`.
- Produces: `decide_account_capacity` and `compute_directional_risk` using Decimal.
- Produces: bounded current-row loaders and `FullAccountRiskSnapshot`.

- [ ] **Step 1: Resolve `requirements.txt` to the exact dependency contract**

Use `apply_patch` so these exact lines are present once:

```text
ccxt==4.5.56
ijson>=3.5.1,<4.0.0
```

Remove the budget-side relaxed `ccxt>=4.2.24`, the duplicate FastAPI line introduced by the older branch, and any unreviewed Starlette cap not present in `ffc73899`.

- [ ] **Step 2: Install only the new dependency into the integration venv**

```bash
.venv/bin/python -m pip install 'ijson>=3.5.1,<4.0.0'
.venv/bin/python -c 'import ccxt, ijson; assert ccxt.__version__ == "4.5.56"'
```

Expected: exit `0`.

- [ ] **Step 3: Run pure-domain and streaming tests before changing overlap files**

```bash
.venv/bin/python -m pytest -q \
  tests/unit/test_instrument_risk_identity.py \
  tests/unit/test_account_capacity_claim.py \
  tests/unit/test_account_risk.py \
  tests/unit/test_account_capacity_hot_path_repository.py \
  tests/unit/test_streaming_http_json.py \
  tests/unit/test_binance_usdm_account_risk_snapshot.py
```

Expected: exit `0`.

- [ ] **Step 4: Run static purity and hot-path guards**

```bash
rg -n 'from (sqlalchemy|fastapi|aiohttp|ccxt)|import (sqlalchemy|fastapi|aiohttp|ccxt)' \
  src/domain/account_capacity_claim.py \
  src/domain/account_risk.py \
  src/domain/instrument_risk_identity.py
rg -n 'read_control_state\(|SELECT \*|autoload_with=|def _rows\(' \
  src/infrastructure/account_capacity_hot_path_repository.py
```

Expected: both searches return no matches.

**Done When:** dependency identity is exact and all new pure/streaming boundaries pass tests.

**Hard Stop:** CCXT is not `4.5.56`, a domain file imports I/O, or the hot-path repository scans generic state/history.

---

### Task 6: Integrate Exact Instrument, Runtime Lane, And Account Facts

**Task ID:** `MERGE-DAR-06`

**Goal:** Carry exact asset-neutral instrument identity and complete account facts through the release runtime lane without weakening release freshness or watcher behavior.

**Why:** Account capacity is invalid if identity is inferred from strings or if account facts are partial, stale, or obtained inside the capacity transaction.

**Files:**
- Modify: `src/domain/runtime_lane_identity.py`
- Modify: `src/application/runtime_lane_identity_service.py`
- Add: `src/application/action_time/instrument_risk_facts.py`
- Modify: `src/application/action_time/account_safe_facts.py`
- Modify: `src/infrastructure/runtime_control_state_repository.py`
- Modify: `scripts/runtime_active_observation_monitor.py`
- Modify: `scripts/run_server_product_state_refresh_sequence.py`
- Modify: `scripts/seed_runtime_control_state_foundation.py`
- Test: lane identity, account facts, repository, monitor, and refresh tests

**Interfaces:**
- Consumes: Candidate Scope exact `exchange_instrument_id`, versioned rule snapshot, policy/profile, and watcher lane identity.
- Produces: one immutable `RuntimeLaneIdentity` and one typed, fresh `FullAccountRiskSnapshot` reference.
- Preserves: release monitor-bounded repository reads and exact signal/Ticket lineage.

- [ ] **Step 1: Resolve runtime identity from the release version outward**

Keep every release identity/version/freshness field, then add the budget fields required by `InstrumentRiskIdentity`. Reject any implementation that constructs identity with `exchange_id + ':' + symbol` or parses `exchange_instrument_id` prefixes.

- [ ] **Step 2: Resolve `account_safe_facts.py`**

Preserve release account-mode freshness, lifecycle blocker semantics, and signed GET-only behavior. Add full-account positions, regular orders, conditional/algo orders, balances, account mode, and instrument-rule snapshot references through the typed snapshot provider. Keep network collection outside the short PG capacity transaction.

- [ ] **Step 3: Resolve `runtime_control_state_repository.py`**

Preserve release bounded read profiles and terminal exact-ID diagnostics. Add only the account-risk/current-projection rows consumed by Ticket and FinalGate. Do not route the budget hot path through `read_control_state()` and do not add file fallback.

- [ ] **Step 4: Resolve monitor and refresh entry points**

Preserve release cadence, timeout, writer-fence, and no-signal behavior. Account-risk facts may refresh only through the existing PG/current path; they must not create new report files or make a business blocker look like watcher failure.

- [ ] **Step 5: Run identity/account/repository tests**

```bash
.venv/bin/python -m pytest -q \
  tests/unit/test_runtime_lane_identity.py \
  tests/unit/test_runtime_lane_identity_api.py \
  tests/unit/test_runtime_lane_identity_service.py \
  tests/integration/test_runtime_lane_identity_certification.py \
  tests/unit/test_instrument_risk_facts.py \
  tests/unit/test_runtime_account_safe_facts.py \
  tests/unit/test_runtime_control_state_repository.py \
  tests/unit/test_runtime_active_observation_monitor.py \
  tests/unit/test_server_product_state_refresh_sequence.py
```

Expected: exit `0`; integration test runs only when its PG fixture is available and is rerun without skip in Task 11.

- [ ] **Step 6: Run exact-instrument static guard**

```bash
rg -n 'f"\{snapshot\.exchange_id\}:\{.*symbol|LIKE .binance_usdm:%|_exchange_instrument_id\(' \
  src/application src/domain src/infrastructure
```

Expected: no active runtime/account-risk identity construction or prefix parsing.

**Done When:** exact instrument and complete account facts reach the release lane through PG/current typed interfaces.

**Hard Stop:** symbol-derived identity, stale account facts accepted as clear, network inside capacity transaction, or monitor/file authority regression.

---

### Task 7: Integrate Account Capacity Claim Into Promotion, Ticket, And FinalGate

**Task ID:** `MERGE-DAR-07`

**Goal:** Extend the existing release Action-Time transaction so one Invocation creates at most one capacity Claim and one Ticket, with FinalGate semantic revalidation.

**Why:** This is the central correctness boundary of the dual-position model.

**Files:**
- Add: `src/application/action_time/account_capacity_claim.py`
- Add: `src/application/action_time/account_capacity_materialization.py`
- Add: `src/application/action_time/account_capacity_reservation.py`
- Add: `src/application/action_time/account_risk_policy.py`
- Add: `src/application/action_time/account_budget_current.py`
- Add: `src/application/action_time/account_exposure_current.py`
- Add: `src/application/action_time/account_exchange_ownership.py`
- Add: `src/application/action_time/budget_reservation_transition.py`
- Modify: `src/application/action_time/promotion_action_time_lane.py`
- Modify: `src/application/action_time/action_time_ticket.py`
- Modify: `src/application/action_time/ticket_materialization_sequence.py`
- Modify: `src/application/action_time/finalgate_preflight.py`
- Modify: `src/application/action_time/runtime_safety_state.py`
- Modify: `src/application/action_time/full_chain_simulation_harness.py`
- Modify: `src/application/action_time/exchange_scope.py`
- Modify: `src/application/action_time/exchange_command.py`
- Modify: `scripts/materialize_action_time_ticket_sequence.py`
- Test: capacity, Ticket, FinalGate, Operation Layer, and full-chain tests

**Interfaces:**
- Produces: `materialize_account_capacity_from_snapshot`.
- Produces: `insert_or_get_account_capacity_claim` and `load_account_capacity_claim_by_invocation`.
- Preserves: `materialize_action_time_invocation_promotion_action_time_lane` and `materialize_action_time_ticket_sequence` as the only promotion/Ticket path.
- Produces: `account_capacity_current_blockers` inside ticket-bound FinalGate preflight.

- [ ] **Step 1: Resolve promotion/lane from the release implementation**

Preserve release event identity, capability certification, exit-policy fields, lane reuse, expiry, and process-outcome conservation. Add the budget pre-generated reservation/Ticket/ExposureEpisode IDs and lock-first account-capacity bundle. A blocked capacity decision must conserve one exact lane blocker and must not become market wait.

- [ ] **Step 2: Resolve Ticket materialization**

Preserve every release Ticket hash/version/protection/execution/exit-policy field. Add exact Claim lineage and require the active reservation. The transaction must roll back promotion, reservation, lane, Claim, and Ticket together on any failure.

- [ ] **Step 3: Resolve FinalGate and Runtime Safety State**

FinalGate continues to consume `ticket_id`. Revalidate current policy event, instrument rule, cluster membership, account snapshot, projection version, own-claim exclusion/re-addition, margin, portfolio, cluster, slot, and same-instrument constraints. A failure blocks only new entry; existing protection and exit remain available.

- [ ] **Step 4: Preserve Operation Layer identity**

`tests/unit/test_action_time_operation_layer_handoff_materialization.py` must continue to prove `ticket_id + finalgate_pass_id` is mandatory and that no account-risk row can create submit authority.

- [ ] **Step 5: Run capacity/Ticket/FinalGate tests**

```bash
.venv/bin/python -m pytest -q \
  tests/unit/test_account_capacity_claim_persistence.py \
  tests/unit/test_account_capacity_reservation.py \
  tests/unit/test_account_capacity_materialization.py \
  tests/unit/test_account_exchange_ownership.py \
  tests/unit/test_account_exposure_current.py \
  tests/unit/test_account_budget_current.py \
  tests/unit/test_account_capacity_finalgate_guard.py \
  tests/unit/test_account_capacity_gate_replacement.py \
  tests/unit/test_action_time_ticket_materialization.py \
  tests/unit/test_action_time_ticket_materialization_sequence.py \
  tests/unit/test_pg_promotion_action_time_lane_materialization.py \
  tests/unit/test_action_time_finalgate_preflight_materialization.py \
  tests/unit/test_action_time_operation_layer_handoff_materialization.py \
  tests/unit/test_action_time_full_chain_impact.py \
  tests/unit/test_dual_position_account_risk_release_acceptance.py
```

Expected: exit `0`, no exchange write, and all registered release lanes remain covered.

- [ ] **Step 6: Run capacity transaction static guards**

```bash
rg -n 'read_control_state\(|SELECT \*|autoload_with=|def _rows\(' \
  src/application/action_time/account_budget_current.py \
  src/application/action_time/account_exchange_ownership.py \
  src/application/action_time/finalgate_preflight.py \
  src/infrastructure/account_capacity_hot_path_repository.py
rg -n 'requests\.|aiohttp|httpx|subprocess\.|os\.system' \
  src/application/action_time/account_capacity_claim.py \
  src/application/action_time/account_capacity_materialization.py \
  src/application/action_time/account_capacity_reservation.py
```

Expected: no matches.

**Done When:** one Invocation atomically owns one exact Claim/Ticket path and FinalGate revalidates it without authority expansion.

**Hard Stop:** duplicate Claim, loose FinalGate identity, hidden scope expansion, network under lock, or release Ticket field loss.

---

### Task 8: Integrate Lifecycle Reprojection Without Regressing Exit Protection

**Task ID:** `MERGE-DAR-08`

**Goal:** Reproject account exposure/budget from durable lifecycle facts while preserving all release TP1, runner, exit-protection, command, reconciliation, settlement, and outcome semantics.

**Why:** Multi-position capacity is unsafe if lifecycle changes do not release or conserve risk exactly; release behavior is unsafe if budget hooks replace its protection lineage.

**Files:**
- Add: `src/application/action_time/account_risk_reprojection.py`
- Modify: `src/application/action_time/lifecycle_exchange_command_materializer.py`
- Modify: `src/application/action_time/lifecycle_maintenance_scheduler.py`
- Modify: `src/application/action_time/post_submit_reconciliation_tick.py`
- Modify: `src/application/action_time/live_outcome_ledger.py`
- Modify: `src/application/action_time/ticket_bound_budget_settlement.py`
- Modify: `src/domain/ticket_bound_exchange_command.py`
- Modify: `scripts/run_ticket_bound_lifecycle_maintenance_once.py`
- Test: scheduler, reconciliation, command, settlement, outcome, and reprojection tests

**Interfaces:**
- Produces: `reproject_account_risk_current` after durable lifecycle truth.
- Preserves: release current-generation exit protection, repriced TP1 reconciliation, runner maintenance, command unknown-outcome handling, and terminal Outcome.

- [ ] **Step 1: Resolve the scheduler from release semantics**

Preserve release due-work selection, `runner_protected` continuity, gateway-init bounds, timeout hierarchy, telemetry, and disabled capability behavior. Add account-risk reprojection only after the selected lifecycle action commits durable facts.

- [ ] **Step 2: Resolve post-submit reconciliation from release semantics**

Preserve `ffc73899` repriced TP1 matching and exact exit-protection generation. Add exposure/budget reprojection as a downstream PG/current projection. It must not select exchange orders, mutate protection, or clear a NettingDomain hold independently.

- [ ] **Step 3: Resolve command and settlement semantics**

Preserve every release command source, deterministic identity, claim lease, unknown outcome, and reconciliation branch. Account capacity can consume command/lifecycle truth but cannot become a second exchange-command authority.

- [ ] **Step 4: Resolve Live Outcome semantics**

Preserve release fees, funding availability, TP1/runner/final-exit facts, exact order lineage, and terminal Ticket state. Add account-risk/release evidence only as typed nullable lineage; do not rewrite historical Outcome meaning.

- [ ] **Step 5: Run release-plus-budget lifecycle regression**

```bash
.venv/bin/python -m pytest -q \
  tests/unit/test_account_risk_lifecycle_reprojection.py \
  tests/unit/test_ticket_bound_lifecycle_scheduler.py \
  tests/unit/test_ticket_bound_lifecycle_global_deadline.py \
  tests/unit/test_ticket_bound_post_submit_reconciliation_tick.py \
  tests/unit/test_ticket_bound_exchange_command_materialization.py \
  tests/unit/test_ticket_bound_exchange_snapshot_provider.py \
  tests/unit/test_ticket_bound_budget_settlement.py \
  tests/unit/test_live_outcome_ledger.py \
  tests/unit/test_ticket_bound_protected_submit_attempt.py \
  tests/unit/test_ticket_bound_runtime_safety_state_materialization.py \
  tests/unit/test_ticket_exit_policy_tp1_reprice.py
```

Expected: exit `0`; release TP1/runner/exit-protection cases and budget release/conservation cases all pass.

- [ ] **Step 6: Verify one writer and no file cadence**

```bash
rg -n 'open\(|write_text\(|json\.dump|yaml\.dump|jsonlines|\.jsonl' \
  src/application/action_time/account_risk_reprojection.py \
  src/application/action_time/lifecycle_maintenance_scheduler.py \
  src/application/action_time/post_submit_reconciliation_tick.py
```

Expected: no production report or sidecar write path.

**Done When:** lifecycle facts conservatively update account capacity without altering release exchange/protection ownership.

**Hard Stop:** TP1/runner regression, duplicate command authority, premature budget release, or reprojection before durable lifecycle truth.

---

### Task 9: Integrate Read Models, Owner State, Operations, And Release Preparation

**Task ID:** `MERGE-DAR-09`

**Goal:** Expose account-risk capability through existing PG-backed read models and release checks without activating production policy.

**Why:** A merge is not releasable if monitoring, Owner state, schema checks, or deploy preparation disagree with the runtime chain.

**Files:**
- Add: `src/application/readmodels/account_risk_owner_state.py`
- Modify: `src/application/readmodels/strategy_live_candidate_pool.py`
- Modify: `src/application/readmodels/runtime_strategy_signal_input.py`
- Modify: `src/application/strategy_semantic_admission.py`
- Modify: `scripts/ops/check_tokyo_runtime_ops_health_once.py`
- Add: `scripts/ops/set_account_risk_policy.py`
- Modify: `scripts/prepare_tokyo_runtime_governance_release.py`
- Modify: `scripts/runtime_active_observation_monitor.py`
- Modify: `docs/current/P0_RUNTIME_STABILITY_AND_SIMPLIFIED_TOKYO_DEPLOYMENT_IMPLEMENTATION_PLAN.md`
- Test: readmodel, policy CLI, ops health, and release preparation tests

**Interfaces:**
- Produces: account-risk Owner status from PG current rows.
- Preserves: Candidate Pool/Tradeability/Goal Status first-blocker semantics and release deploy fencing.
- Keeps: policy CLI non-executing unless a later explicitly authorized operation invokes it.

- [ ] **Step 1: Resolve Candidate Pool and signal input**

Preserve release PG-only source priority, exact signal/lane/Ticket lineage, and blocker conservation. Add account-capacity blocker detail without converting it into generic market wait or Owner manual operation.

- [ ] **Step 2: Integrate Owner read model**

Map normal account-capacity state to terse product language. Keep internal Claim, projection version, rule snapshot, and cluster details in developer/audit detail only.

- [ ] **Step 3: Integrate policy CLI as a later-stage tool**

The script must use PG policy events/current projection, typed Decimal inputs, explicit plan/apply behavior, and zero exchange write. The merge and all local tests use plan/read-only paths only; no policy activation command runs.

- [ ] **Step 4: Repair the verified release-base documentation authority defect**

The file exists at `ffc73899` without YAML front matter and is absent from the
budget branch. Add exactly this front matter before its existing title:

```yaml
---
title: P0_RUNTIME_STABILITY_AND_SIMPLIFIED_TOKYO_DEPLOYMENT_IMPLEMENTATION_PLAN
status: CURRENT_IMPLEMENTATION_PLAN
authority: docs/current/P0_RUNTIME_STABILITY_AND_SIMPLIFIED_TOKYO_DEPLOYMENT_IMPLEMENTATION_PLAN.md
last_verified: 2026-07-17
---
```

Do not rewrite its release semantics. Verify the known baseline failure is
closed with:

```bash
.venv/bin/python scripts/validate_current_docs_authority.py
```

Expected: `current_docs_authority_valid`.

- [ ] **Step 5: Resolve release preparation**

Preserve release exact-head, immutable venv, writer fence, lifecycle capability, canary, and zero-exchange checks. Set local expected migration count to `133` and latest migration to `2026-07-17-133_enforce_asset_neutral_account_risk_identity.py`.

- [ ] **Step 6: Run readmodel/ops/release tests**

```bash
.venv/bin/python -m pytest -q \
  tests/unit/test_account_risk_owner_state.py \
  tests/unit/test_strategy_live_candidate_pool.py \
  tests/unit/test_runtime_strategy_signal_evaluation_service.py \
  tests/unit/test_runtime_strategy_signal_input_artifact_script.py \
  tests/unit/test_set_account_risk_policy.py \
  tests/unit/test_runtime_active_observation_monitor.py \
  tests/unit/test_tokyo_runtime_governance_release_prep.py
```

Expected: exit `0`; no policy activation and no exchange write.

**Done When:** all PG-backed read models and local release checks recognize schema `133` without changing production authority.

**Hard Stop:** generated-file authority, hidden policy activation, Owner-facing internal gate leakage, or release fence regression.

---

### Task 10: Resolve Test Schemas And Prove Every Conflict Is Closed

**Task ID:** `MERGE-DAR-10`

**Goal:** Resolve the remaining test/schema conflicts without weakening either branch's assertions.

**Why:** Test auto-resolution can silently remove release fields or budget invariants even when production code appears correct.

**Files:**
- Resolve: `tests/integration/test_runtime_causal_integrity_postgres.py`
- Resolve: `tests/support/runtime_control_state_schema.py`
- Resolve: `tests/unit/lifecycle_test_schema.py`
- Resolve: all remaining conflicted test files from Task 3
- Preserve/add: all budget-only account-risk tests
- Preserve: all release exit-policy/TP1/lifecycle tests

**Interfaces:**
- Produces: one integrated fixture schema matching migration head `133`.
- Preserves: release lifecycle proof v2, exit-policy adoption, current-generation TP1, and budget asset-neutral Claim fields.

- [ ] **Step 1: Resolve shared schemas by union of current columns and constraints**

Start from the release fixture schema and add the budget tables/columns exactly as revisions `126-133` create them. Do not edit release table/constraint names to match an older budget fixture.

- [ ] **Step 2: Resolve behavioral tests by preserving both assertion families**

Every conflicted test must retain:

```text
release: exact Ticket/exit-policy/lifecycle/current-generation behavior
budget: exact instrument/Claim/account snapshot/projection/capacity behavior
shared: zero exchange write, no loose identity, no file authority
```

- [ ] **Step 3: Verify no conflict marker or unmerged index entry remains**

```bash
test -z "$(git diff --name-only --diff-filter=U)"
! rg -n '^(<<<<<<<|=======|>>>>>>>)' . \
  -g '*.py' -g '*.md' -g '*.txt' -g '*.service'
```

Expected: both commands exit `0`.

- [ ] **Step 4: Run all conflict-adjacent tests together**

```bash
.venv/bin/python -m pytest -q \
  tests/integration/test_runtime_causal_integrity_postgres.py \
  tests/unit/test_action_time_finalgate_preflight_materialization.py \
  tests/unit/test_action_time_full_chain_impact.py \
  tests/unit/test_action_time_operation_layer_handoff_materialization.py \
  tests/unit/test_pg_migration_identifier_names.py \
  tests/unit/test_pg_promotion_action_time_lane_materialization.py \
  tests/unit/test_runtime_account_safe_facts.py \
  tests/unit/test_runtime_active_observation_monitor.py \
  tests/unit/test_runtime_control_state_repository.py \
  tests/unit/test_ticket_bound_lifecycle_scheduler.py \
  tests/unit/test_ticket_bound_post_submit_reconciliation_tick.py \
  tests/unit/test_ticket_bound_runtime_safety_state_materialization.py \
  tests/unit/test_tokyo_runtime_governance_release_prep.py
```

Expected: exit `0` when PostgreSQL is configured; if the integration module requires PG and reports a skip, Task 11 remains blocked.

- [ ] **Step 5: Run diff hygiene**

```bash
git diff --check
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
```

Expected: `git diff --check` exits `0`; output-scope validator reports valid.

**Done When:** no unmerged entry remains and the combined conflict-adjacent suite is green.

**Hard Stop:** resolving a test by deleting an assertion, weakening expected blockers, or skipping PG coverage.

---

### Task 11: Run Disposable PostgreSQL Concurrency, Migration, And Scale Certification

**Task ID:** `MERGE-DAR-11`

**Goal:** Prove the integrated chain against real PostgreSQL locking, migration, identity, and large-history behavior.

**Why:** SQLite and unit fixtures cannot establish account-wide concurrency or production migration safety.

**Allowed files:** ignored test caches and disposable external PostgreSQL schemas only.

**Forbidden files:** production PG, Tokyo server, source worktrees, tracked output artifacts.

**Interfaces:**
- Consumes: `BRC_LOCAL_TEST_POSTGRES_DSN` and `BRC_LOCAL_TEST_POSTGRES_SCHEMA` for a disposable PostgreSQL 16 schema.
- Produces: non-skipped concurrency, migration, full-chain, and 100000-row performance proof.

- [ ] **Step 1: Require explicit disposable PG configuration**

```bash
test -n "$BRC_LOCAL_TEST_POSTGRES_DSN"
test -n "$BRC_LOCAL_TEST_POSTGRES_SCHEMA"
```

Expected: both commands exit `0`. Missing values stop execution rather than falling back to SQLite.

- [ ] **Step 2: Run account-capacity PostgreSQL certification**

```bash
BRC_LOCAL_TEST_POSTGRES_DSN="$BRC_LOCAL_TEST_POSTGRES_DSN" \
BRC_LOCAL_TEST_POSTGRES_SCHEMA="$BRC_LOCAL_TEST_POSTGRES_SCHEMA" \
.venv/bin/python -m pytest -q \
  tests/integration/test_account_capacity_postgres.py \
  tests/integration/test_runtime_lane_identity_certification.py \
  tests/integration/test_asset_neutral_account_risk_full_chain.py \
  tests/integration/test_asset_neutral_account_risk_migration_scale.py \
  tests/integration/test_account_capacity_hot_path_scale.py
```

Expected: exit `0`, zero skips, the second concurrent transaction observes projection-version change, and 100000-row histories do not expand the current hot-path result.

- [ ] **Step 3: Run runtime causal integrity certification**

```bash
BRC_LOCAL_TEST_POSTGRES_DSN="$BRC_LOCAL_TEST_POSTGRES_DSN" \
BRC_LOCAL_TEST_POSTGRES_SCHEMA="$BRC_LOCAL_TEST_POSTGRES_SCHEMA" \
.venv/bin/python -m pytest -q tests/integration/test_runtime_causal_integrity_postgres.py
```

Expected: exit `0`, zero skips.

- [ ] **Step 4: Exercise fresh upgrade and release-like upgrade**

Use two disposable schemas:

```text
fresh schema: Alembic base -> 133
release-like schema: Alembic 125 -> 133
```

For each schema run:

```bash
.venv/bin/python -m alembic heads
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m alembic current
```

Expected: one head/current revision `133`. The release-like fixture must prove release exit-policy/adoption tables survive revisions `126-133` unchanged.

- [ ] **Step 5: Verify disposable downgrade/upgrade order**

On the fresh disposable schema only:

```bash
.venv/bin/python -m alembic downgrade 125
.venv/bin/python -m alembic upgrade 133
.venv/bin/python -m alembic current
```

Expected: exit `0`, current revision `133`, and downgrade removes only account-risk revisions `126-133`.

**Done When:** every PostgreSQL test runs without skip and both migration entry shapes reach head `133`.

**Hard Stop:** production DSN, skipped PG tests, lock timeout outside the designed fail-fast path, O(n) hot-path history reads, or release table loss.

---

### Task 12: Run Authority, Cadence, And Complete Regression Gates

**Task ID:** `MERGE-DAR-12`

**Goal:** Establish that the integrated tree is globally green and preserves production authority/performance rules.

**Why:** The budget branch's first full-suite run recorded 86 failures; the integration cannot be called merge-ready until the complete tree exits cleanly.

**Allowed files:** ignored test/cache files only.

**Forbidden files:** output artifacts, production state, source worktrees.

**Interfaces:**
- Produces: one complete local verification record on stdout.

- [ ] **Step 1: Run authority and file-I/O gates**

```bash
git diff --check
.venv/bin/python scripts/validate_current_docs_authority.py
.venv/bin/python scripts/validate_output_artifact_scope.py --git-status --git-tracked
.venv/bin/python scripts/audit_production_runtime_file_io.py
```

Required results:

```text
current_docs_authority_valid
output_artifact_scope_valid
suspicious_runtime_file_authority=0
frequent_report_write=0
performance_risk.status=clear
```

- [ ] **Step 2: Run the full focused account-risk regression**

```bash
.venv/bin/python -m pytest -q \
  tests/unit/test_account_capacity_hot_path_repository.py \
  tests/unit/test_streaming_http_json.py \
  tests/unit/test_binance_usdm_account_risk_snapshot.py \
  tests/unit/test_instrument_risk_identity.py \
  tests/unit/test_account_capacity_claim.py \
  tests/unit/test_runtime_lane_identity.py \
  tests/unit/test_runtime_lane_identity_service.py \
  tests/unit/test_account_risk.py \
  tests/unit/test_account_risk_policy.py \
  tests/unit/test_account_capacity_reservation.py \
  tests/unit/test_account_capacity_materialization.py \
  tests/unit/test_account_exchange_ownership.py \
  tests/unit/test_account_exposure_current.py \
  tests/unit/test_account_budget_current.py \
  tests/unit/test_account_capacity_finalgate_guard.py \
  tests/unit/test_action_time_ticket_materialization_sequence.py \
  tests/unit/test_dual_position_account_risk_release_acceptance.py
```

Expected: exit `0`.

- [ ] **Step 3: Run the full release lifecycle regression**

```bash
.venv/bin/python -m pytest -q \
  tests/unit/test_ticket_bound_lifecycle_scheduler.py \
  tests/unit/test_ticket_bound_post_submit_reconciliation_tick.py \
  tests/unit/test_ticket_bound_exchange_command_materialization.py \
  tests/unit/test_ticket_bound_exchange_snapshot_provider.py \
  tests/unit/test_ticket_bound_budget_settlement.py \
  tests/unit/test_live_outcome_ledger.py \
  tests/unit/test_ticket_exit_policy_adoption.py \
  tests/unit/test_ticket_exit_policy_tp1_reprice.py \
  tests/unit/test_tokyo_runtime_governance_release_prep.py
```

Expected: exit `0`.

- [ ] **Step 4: Announce and run the complete suite once**

```bash
.venv/bin/python -m pytest -q
```

Expected: exit code `0`, zero failures. Any failure keeps the merge uncommitted; do not mark unrelated failures green and do not weaken tests.

- [ ] **Step 5: Verify no generated artifacts entered Git status**

```bash
git status --short
.venv/bin/python scripts/validate_output_artifact_scope.py --git-status --git-tracked
```

Expected: only intended merge files are staged/modified; no `output/**` or runtime report artifact is present.

**Done When:** all focused, authority, file-I/O, and complete regression gates exit `0`.

**Hard Stop:** any full-suite failure, frequent report writer, runtime file authority, or tracked output artifact.

---

### Task 13: Update Integration Documentation And Create The Two-Parent Merge Commit

**Task ID:** `MERGE-DAR-13`

**Goal:** Record only observed local evidence and create the final local merge commit.

**Why:** The commit must preserve both histories and must not claim deployment or policy activation.

**Files:**
- Modify: `docs/current/DUAL_POSITION_HARD_CAP_ACCOUNT_RISK_MODEL_V0_DESIGN.md`
- Modify: `docs/current/DUAL_POSITION_HARD_CAP_ACCOUNT_RISK_MODEL_V0_IMPLEMENTATION_PLAN.md`
- Modify: `docs/current/DUAL_POSITION_ACCOUNT_RISK_V0_RELEASE_BLOCKER_REMEDIATION_DESIGN.md`
- Modify: `docs/current/DUAL_POSITION_ACCOUNT_RISK_V0_RELEASE_BLOCKER_REMEDIATION_IMPLEMENTATION_PLAN.md`
- Modify: `docs/current/DUAL_POSITION_ACCOUNT_RISK_V0_ASSET_NEUTRAL_IDENTITY_EXTENSION_DESIGN.md`
- Modify: `docs/current/DUAL_POSITION_ACCOUNT_RISK_V0_ASSET_NEUTRAL_IDENTITY_EXTENSION_IMPLEMENTATION_PLAN.md`
- Modify: `docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md`
- Preserve release-first: `docs/current/MAIN_CONTROL_ROADMAP.md`
- Preserve release-first: `docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md`
- Include: this design and plan

**Interfaces:**
- Produces: one local merge commit with parents `ffc73899` and `5b67181e`.

- [ ] **Step 1: Update status language from observed evidence only**

Use this exact boundary:

```text
integration_state: LOCAL_MERGE_CERTIFIED_NOT_DEPLOYED
production_state: UNCHANGED
policy_activation: NOT_PERFORMED
exchange_write: 0
migration_head: 133_LOCAL_ONLY
```

Do not change the current roadmap to imply Tokyo deployment, two-position policy activation, or live calibration.

- [ ] **Step 2: Run documentation and placeholder scans**

```bash
placeholder_pattern='T''BD|T''ODO|fill'' in|implement'' later|deployment'' complete|policy'' activated'
! rg -n "$placeholder_pattern" \
  docs/superpowers/specs/2026-07-17-ffc73899-dual-position-account-risk-v0-integration-design.md \
  docs/superpowers/plans/2026-07-17-ffc73899-dual-position-account-risk-v0-merge.md
.venv/bin/python scripts/validate_current_docs_authority.py
```

Expected: scan and validator exit `0`.

- [ ] **Step 3: Verify the merge is fully resolved and stage intended files**

```bash
test -z "$(git diff --name-only --diff-filter=U)"
git add -A
git diff --cached --check
```

Expected: no unmerged path and no whitespace error.

- [ ] **Step 4: Review staged scope before commit**

```bash
git diff --cached --stat
git diff --cached --name-only | rg '^output/' && exit 1 || true
git diff --cached --name-only | rg '^requirements-runtime\.lock$' && exit 1 || true
```

Expected: no output artifact or runtime lockfile.

- [ ] **Step 5: Create the two-parent merge commit**

```bash
git commit -m "merge: integrate dual-position account risk v0 onto ffc73899"
```

Expected: commit succeeds.

- [ ] **Step 6: Verify parents and clean status**

```bash
parents=$(git rev-list --parents -n 1 HEAD)
test "$(printf '%s\n' "$parents" | awk '{print $2}')" = "ffc73899f2749208074a06b9c7384e74911a400d"
test "$(printf '%s\n' "$parents" | awk '{print $3}')" = "5b67181e2d287fb306bae953075c89e2c6be32ab"
test -z "$(git status --porcelain --untracked-files=no)"
```

Expected: both parents match and tracked status is clean.

**Done When:** one clean local merge commit preserves both exact source parents.

**Hard Stop:** missing parent, extra parent, tracked output, runtime lockfile, or documentation claiming deploy/activation.

---

### Task 14: Run Post-Commit Release Preparation And Moving-Release Delta Audit

**Task ID:** `MERGE-DAR-14`

**Goal:** Prove the committed integration is locally release-preparable and identify, without merging, the later release delta.

**Why:** The source release continued moving during planning; the integration must remain reproducible before deciding whether to absorb those fixes.

**Allowed files:** None; this task is read-only after the merge commit.

**Forbidden files:** Tokyo, production PG, source worktrees, source branches.

**Interfaces:**
- Produces: local release-preparation report on stdout and a read-only delta inventory.

- [ ] **Step 1: Run local release preparation**

```bash
.venv/bin/python scripts/prepare_tokyo_runtime_governance_release.py \
  --json \
  --deployed-head ffc73899f2749208074a06b9c7384e74911a400d \
  --expected-min-migrations 133 \
  --expected-latest-migration 2026-07-17-133_enforce_asset_neutral_account_risk_identity.py
```

Expected: local preparation reports no migration, source, tracked-output, or authority blocker; it performs zero exchange write and writes no archive.

- [ ] **Step 2: Re-run short post-commit smoke**

```bash
.venv/bin/python -m pytest -q \
  tests/unit/test_pg_migration_identifier_names.py \
  tests/unit/test_dual_position_account_risk_release_acceptance.py \
  tests/unit/test_ticket_bound_post_submit_reconciliation_tick.py \
  tests/unit/test_tokyo_runtime_governance_release_prep.py
```

Expected: exit `0`.

- [ ] **Step 3: Inventory the excluded moving-release delta**

```bash
git log --oneline ffc73899f2749208074a06b9c7384e74911a400d..fdad0e9346203421319044d70e5e33d99925e485
git diff --stat HEAD...fdad0e9346203421319044d70e5e33d99925e485
git diff --name-only HEAD...fdad0e9346203421319044d70e5e33d99925e485 | LC_ALL=C sort
```

Expected: read-only output naming the three excluded release commits and their overlap with the now-green integration.

- [ ] **Step 4: Stop before intake, push, or deploy**

```bash
test -z "$(git status --porcelain --untracked-files=no)"
```

Expected: clean tracked status. No merge of `fdad0e93`, no push, no tag, and no Tokyo action occurs in this task.

**Done When:** local release preparation passes and the later release delta is explicitly inventoried but not absorbed.

**Hard Stop:** local release-prep blocker, dirty tracked status, accidental source-ref update, push, deploy, or policy action.

## Final Acceptance Matrix

| Gate | Required result |
| --- | --- |
| Isolation | Only the sibling integration worktree changed |
| Git lineage | Merge parents are exactly `ffc73899` and `5b67181e` |
| Migration | One Alembic head `133`; release `121-125` unchanged; `086` byte-identical to release |
| Dependency | `ccxt==4.5.56`; `ijson>=3.5.1,<4.0.0` |
| Identity | No symbol/prefix-derived instrument identity in active runtime |
| Capacity | One Invocation creates at most one Claim/Ticket; real PG locking proof passes |
| FinalGate | Ticket-only identity plus current semantic revalidation |
| Lifecycle | Release TP1, runner, protection, reconciliation, settlement, and Outcome tests remain green |
| Performance | 100000-row history does not expand current hot-path rows or memory beyond contract |
| Cadence | Zero no-signal JSON/MD and zero no-signal Claim/Ticket/ExposureEpisode rows |
| Authority | No deploy, policy activation, exchange write, scope/profile/sizing change |
| Regression | Focused, PostgreSQL, authority, file-I/O, and complete suites exit `0` |
| Release delta | `ffc73899..fdad0e93` inventoried separately and not absorbed |

## Plan Completion Boundary

Executing this plan ends with a **local, clean, two-parent, merge-ready integration branch**. It does not end with deployment, Tokyo migration apply, two-position policy activation, live-submit expansion, or source-branch integration.
