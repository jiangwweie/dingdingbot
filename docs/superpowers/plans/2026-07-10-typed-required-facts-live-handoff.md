# P0-FH Typed RequiredFacts Live Handoff Implementation Plan

> Execute inline with strict red-green TDD. Synthetic inputs remain test-only
> and no test or deploy step may call a real exchange write.

**Goal:** Preserve evaluator-owned typed RequiredFacts through the watcher and
PG action-time chain, close two shared infrastructure gaps, and certify the five
current StrategyGroups at the ticket-bound disabled-smoke trading door.

**Architecture:** Reuse `StrategyFactObservation` and the existing PG live
signal payload; normalize PG DSNs through the shared adapter; make the deploy
plan own watcher quiescence and post-health restoration.

**Tech stack:** Python 3, Pydantic, SQLAlchemy, PostgreSQL/SQLite test fixtures,
systemd command planning, pytest, Alembic 112.

## File Map

### Modified files

- `scripts/runtime_active_observation_monitor.py`: preserve typed observations
  in the watcher signal summary.
- `src/application/action_time/fact_snapshots.py`: validate typed fact
  completeness, uniqueness, provenance, time bounds, and snapshot expiry.
- `src/application/action_time/full_chain_simulation_harness.py`: make the
  non-executing harness obey the same typed fact contract.
- `tests/unit/test_runtime_active_observation_monitor.py`: focused summary
  transport test.
- `tests/unit/test_action_time_full_chain_impact.py`: evaluator-to-PG-to-
  action-time and five-StrategyGroup certification tests.
- `tests/unit/test_pg_promotion_action_time_lane_materialization.py`: typed
  fact validation and fixture-contract tests.
- `scripts/build_strategygroup_tradeability_decision.py`: shared sync PG DSN
  normalization.
- `tests/unit/test_strategygroup_tradeability_decision.py`: asyncpg DSN
  normalization test.
- `scripts/plan_tokyo_runtime_governance_git_deploy.py`: watcher quiesce and
  post-health timer restore.
- `tests/unit/test_runtime_signal_watcher_systemd_units.py`: deploy ordering
  invariants.

## Task 1: Lock the typed-fact transport defect with failing tests

### Step 1: Add the focused projector test

Construct a real `RuntimeStrategySignalEvaluationResult` with typed facts,
embed its JSON form under the same API observation artifact shape used by the
watcher, and assert:

```python
summary = runtime_active_observation_monitor._signal_summary(artifact)
assert summary["fact_observations"] == expected_fact_rows
```

Run:

```bash
pytest -q tests/unit/test_runtime_active_observation_monitor.py \
  -k typed_fact_observations
```

Expected before implementation: `KeyError` or empty result because the summary
allow-list omits the field.

### Step 2: Add the real boundary integration test

For all twenty-two current candidate scopes across every StrategyGroup and both
SOR sides:

1. run the real runtime evaluator;
2. pass its serialized result through `_signal_summary`;
3. write the summary with `write_runtime_signal_summaries_to_pg`;
4. keep only non-strategy public facts such as `last_price` in the public fact
   snapshot;
5. materialize action-time facts;
6. assert every current Event Spec RequiredFact is satisfied from typed
   observations and no exchange effect occurred.

Expected before implementation: action-time blocks on missing event facts.

## Task 2: Implement the typed-fact handoff

### Step 1: Make the smallest producer fix

In `_signal_summary`, project `output.fact_observations` as a list containing
only dictionary rows. Do not derive or rename fact keys.

### Step 2: Run focused and full-chain tests

```bash
pytest -q \
  tests/unit/test_runtime_active_observation_monitor.py \
  tests/unit/test_runtime_strategy_signal_evaluation_service.py \
  tests/unit/test_action_time_full_chain_impact.py
```

Expected: all focused transport, six-Event-Spec, five-StrategyGroup, and
twenty-two-scope disabled-smoke tests pass.

### Step 3: Add negative assertions

Prove an absent typed observation remains missing and
`strong_uptrend_disable=true` blocks BRF2 before promotion. Prove stale,
future-dated, malformed, provenance-free, and duplicate observations cannot
satisfy RequiredFacts, and cap the action-time snapshot at the shortest typed
fact validity. For current execution-eligible Event Specs, prove every
promotion RequiredFact must exist in the valid typed set and that nested
evidence with the same key cannot become a fallback. Reuse existing fail-closed
materializer behavior rather than adding fallback inference.

## Task 3: Normalize the Tradeability PG DSN

### Step 1: Add a failing CLI unit test

Monkeypatch engine creation and the read-model builder, call `main` with:

```text
postgresql+asyncpg://user:pass@host/db
```

Assert engine creation receives:

```text
postgresql+psycopg://user:pass@host/db
```

Expected before implementation: CLI returns `2` before engine creation.

### Step 2: Use the shared adapter

Import `normalize_sync_postgres_dsn` and `is_sync_postgres_dsn` from
`scripts.pg_dsn`, normalize before validation, and preserve explicit SQLite
test-only behavior.

### Step 3: Run Tradeability tests

```bash
pytest -q tests/unit/test_strategygroup_tradeability_decision.py
```

## Task 4: Make Tokyo deploy watcher-safe

### Step 1: Add failing command-order tests

Assert phase 3 stops the watcher timer and running watcher service before the
backend. Apply the same quiesce invariant to runtime monitor and ticket
lifecycle maintenance timers/services. Assert phase 4 checks health before
restoring recurring consumers, then verifies the timers are active.

Expected before implementation: phase 3 contains no watcher quiesce and phase
4 contains no watcher timer start/active check.

### Step 2: Implement quiesce and restore

Add non-interactive bounded systemd commands to the existing deploy plan:

```text
systemctl stop brc-runtime-signal-watcher.timer
systemctl stop brc-runtime-monitor.timer
systemctl stop brc-ticket-lifecycle-maintenance.timer
systemctl stop brc-runtime-signal-watcher.service
systemctl stop brc-runtime-monitor.service
systemctl stop brc-ticket-lifecycle-maintenance.service
systemctl stop brc-owner-console-backend.service
...
curl health loop
...
systemctl start brc-runtime-signal-watcher.timer
systemctl is-active brc-runtime-signal-watcher.timer
```

The timer start must remain downstream of health success and current unit/drop-
in installation.

### Step 3: Run deploy/systemd tests

```bash
pytest -q \
  tests/unit/test_runtime_signal_watcher_systemd_units.py \
  tests/unit/test_tokyo_runtime_governance_release_prep.py \
  tests/unit/test_tokyo_runtime_governance_postdeploy_verify.py
```

## Task 5: Repository verification

### Step 1: Run the focused regression set

```bash
pytest -q \
  tests/unit/test_runtime_active_observation_monitor.py \
  tests/unit/test_runtime_strategy_signal_evaluation_service.py \
  tests/unit/test_action_time_full_chain_impact.py \
  tests/unit/test_strategygroup_tradeability_decision.py \
  tests/unit/test_runtime_signal_watcher_systemd_units.py \
  tests/unit/test_server_product_state_refresh_sequence.py \
  tests/unit/test_tokyo_runtime_governance_release_prep.py \
  tests/unit/test_tokyo_runtime_governance_postdeploy_verify.py
```

### Step 2: Run file-I/O and source-boundary audits

```bash
python3 scripts/audit_production_runtime_file_io.py --json
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
```

Require `performance_risk.status=clear`, zero frequent report writers, and no
new runtime JSON/MD authority.

### Step 3: Run the full suite

```bash
pytest -q
```

Require a clean pass. Inspect `git diff --check`, focused diff, and worktree
status before commit.

## Task 6: Commit, push, deploy, and accept Tokyo

### Step 1: Commit and push the focused branch

Commit only the design, plan, implementation, and tests in this worktree. Push
`codex/p0-fh-typed-required-facts` and verify the remote head equals the local
commit.

### Step 2: Run deployment preflight

Use the git-based Tokyo deployment planner/executor with:

- previous deployed head `f2a3fdd85a6c5873f98ca31b96ba514328404ecc`;
- expected remote and target migration count `112`;
- exact pushed target commit;
- active release path under `/home/ubuntu/brc-deploy/app/current`.

Stop on baseline drift, migration drift, health `live_ready=true`, unpushed
target head, file-I/O regression, or failed shadow rehearsal.

### Step 3: Apply and verify

Apply under standing authorization. Verify:

```text
manifest commit == pushed commit
alembic current == 112 (head)
backend active and /api/health HTTP 200
watcher timer active
runtime monitor timer active
ticket lifecycle timer active
one manually triggered watcher tick exits successfully
```

### Step 4: Prove the five-strategy trading-door state

Read PG/current projections and confirm:

- five current enabled StrategyGroups;
- six current executable Event Specs;
- twenty-two active candidate scopes with current watcher coverage;
- no strategy is blocked by missing typed-fact transport;
- current no-signal state is classified as market wait only when all non-market
  prerequisites are closed;
- no Owner intervention is required for normal waiting;
- no exchange write, order, profile, sizing, credential, withdrawal, or
  transfer mutation occurred during deployment or acceptance.

## Done When

The exact deployed commit preserves typed evaluator facts through PG action-
time materialization, all five StrategyGroups and twenty-two active scopes pass
the non-executing trading-door certification, the three infrastructure gaps are
closed by red-green tests, Tokyo services and timers are healthy, and the only
remaining condition for a real order is a future fresh live signal plus normal
action-time safety truth.

## Hard Stop

Do not deploy if tests or audits fail, if synthetic data can reach production
submit authority, if a strategy fact is inferred from its expected value, if
scope expands, if the release head cannot be proven, or if watcher restoration
would occur before backend health.
