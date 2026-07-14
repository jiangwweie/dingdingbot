# Ticket-Bound Exit Policy Program Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:executing-plans` for checkpointed execution. Core-file tasks are
> executed by the Codex primary agent. Do not spawn or delegate to subagents
> unless the Owner or then-current project instructions explicitly authorize
> it.

**Goal:** Repair runner/TP1 lifecycle safety, introduce a disabled versioned
Exit Policy Core, then replay and activate approved exit semantics for future
Tickets one Event Spec at a time.

**Architecture:** One immutable `TicketExitPolicySnapshot` is frozen into each
new Ticket. A pure evaluator consumes exact closed-market facts and current
protection state. All mutations use the existing ticket-bound lifecycle and
durable exchange-command authority. Release A, B, and C have separate schema,
deploy, rollback, and Owner gates.

**Tech Stack:** Python 3.12, Pydantic v2, `decimal.Decimal`, SQLAlchemy Core,
Alembic, PostgreSQL 16, pytest/pytest-asyncio, CCXT **4.5.56**, systemd timers,
Binance USD-M adapter, existing Tokyo git deployment tooling.

**Design authority:**
`docs/superpowers/specs/2026-07-14-ticket-bound-exit-policy-program-design.md`

## Execution Status And Stop Rule

This plan is **not authorized for implementation** until the Owner approves the
design package.

After approval:

1. Execute **Release A** completely, review it, deploy it through ordinary
   quiescence, and certify it before beginning Release B.
2. Execute and deploy **Release B** with the capability in
   `certified_disabled` state.
3. Execute Release C research and stop after the comparison package.
4. Do not execute Release C activation tasks C4-C5 until the Owner approves
   exact versioned policy values.

## Global Constraints

### Authority

- **Owner controls:** exact exit policy activation, policy parameters, capital,
  runtime profile, symbol/side scope, and abnormal intervention.
- **System controls:** observation, fact collection, pure evaluation, existing
  FinalGate/Operation Layer, protection, reconciliation, settlement, and review.
- No task may grant submit authority from a replay, test, policy row, or
  capability flag alone.

### Safety

- No FinalGate or Operation Layer bypass.
- No active-lifecycle deploy bypass.
- No duplicate exchange command after an unknown outcome.
- No runner replacement that cancels the old stop before confirming the new
  exact exchange order.
- No TP1 market fallback.
- No historical Ticket reinterpretation.
- No capital, notional, leverage, symbol, side, profile, or credential change.

### Data and performance

- PG/current services and exact exchange facts are the only production
  authority.
- Production cadence writes no JSON/Markdown reports.
- No new runtime file reader, dynamic-path evidence writer, or current
  report-directory interface.
- Public/signed exchange calls are timeout-bounded and occur outside long PG
  transactions.
- Every release must run `scripts/audit_production_runtime_file_io.py` and
  report `performance_risk.status = clear`.

### Git

- Work in an isolated `codex/*` worktree.
- Do not modify the dirty primary workspace.
- Do not commit `output/**`.
- Commit each task only after its task-local tests pass.
- Do not push or deploy until the release-level review is complete.

## Release Map

| Release | Migration | Production capability | Rollback boundary | Owner gate |
| --- | --- | --- | --- | --- |
| **A** | **121** | Runner maintenance, exact active generation, TP1 passive-limit contract and fee truth | Roll back only with zero active real lifecycle and no unknown command | No new policy decision |
| **B** | **122** | Typed Exit Policy Core deployed `certified_disabled` | App rollback allowed only before any active non-legacy policy Ticket | No new policy decision |
| **C** | **123**, created only after approval | One approved Event Spec at a time | Disable new Ticket creation; preserve frozen active Tickets | Exact parameters and activation required |

## Baseline Before Task A1

### Files

**Inspect only:**

- `AGENTS.md`
- `docs/current/P0_LIFECYCLE_PRODUCTION_CERTIFICATION_AND_CLOSURE_DESIGN.md`
- `docs/current/TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md`
- `docs/current/TICKET_BOUND_LIFECYCLE_SAFETY_CORE_IMPLEMENTATION_PLAN.md`
- `docs/current/PRODUCTION_RUNTIME_FILE_IO_ELIMINATION_DESIGN.md`
- `src/application/action_time/lifecycle_maintenance_scheduler.py`
- `src/application/action_time/protected_submit_attempt.py`
- `src/domain/ticket_bound_exchange_command.py`
- `src/infrastructure/exchange_gateway.py`
- migrations **091**, **105**, **114**, **120**

### Commands

Run:

```bash
git status --short --branch
git rev-parse --show-toplevel
git rev-parse --abbrev-ref HEAD
git worktree list --porcelain
python3 -m pytest -q \
  tests/unit/test_ticket_bound_lifecycle_scheduler.py \
  tests/unit/test_ticket_bound_protected_submit_attempt.py \
  tests/unit/test_ticket_bound_exchange_command.py \
  tests/unit/test_ticket_bound_exchange_command_worker.py \
  tests/unit/test_ticket_bound_runner_protection_adjuster.py \
  tests/unit/test_ticket_bound_runner_mutation_command.py \
  tests/unit/test_ticket_bound_post_submit_closure.py
```

Expected: baseline tests pass. If an existing baseline test fails, stop and
classify it before changing production code.

---

## Task A1: Restore `runner_protected` Maintenance Continuity

### Task card

- **Task ID:** `EXIT-A1`
- **Goal:** Make the production lifecycle timer continuously select and
  reconcile `runner_protected` Tickets.
- **Why:** The current state declares continued monitoring but is omitted from
  scheduler selection.
- **Allowed files:**
  - Modify `src/application/action_time/lifecycle_maintenance_scheduler.py`
  - Modify `tests/unit/test_ticket_bound_lifecycle_scheduler.py`
  - Modify `tests/unit/test_ticket_bound_post_submit_reconciliation_tick.py`
- **Forbidden files:** exchange gateway, policy/strategy registry, sizing,
  capital, credentials, deployment interlocks.
- **Global Authority Model:** read/reconcile only; a healthy runner creates no
  exchange write.
- **Chain Position:** post-TP1 lifecycle maintenance.
- **Live Enablement Before:** runner can be exchange-protected but unselected.
- **Live Enablement After:** runner is selected every due lifecycle tick.
- **Blocker Removed:** `runner_maintenance_status_omitted`.
- **Per-Symbol / Per-Fact Acceptance:** exact Ticket/instrument/side scope is
  passed to the existing snapshot provider.
- **Stop Condition:** selector admits terminal lifecycles or triggers a write
  for a healthy runner.
- **Capability Unlocked:** continuous runner reconciliation.
- **Next Bottleneck:** active protection identity is ambiguous across
  generations.
- **Rehearsal/Simulation Boundary:** tests may use in-memory exchange snapshots;
  they grant no live authority.
- **Hard Stop:** any change to submit eligibility or deploy quiescence.

### Step 1: Write the failing scheduler tests

Add tests equivalent to:

```python
def test_runner_protected_is_maintainable_and_snapshot_eligible():
    assert "runner_protected" in MAINTAINABLE_LIFECYCLE_STATUSES
    assert "runner_protected" in SNAPSHOT_STATUSES


@pytest.mark.asyncio
async def test_scheduler_selects_healthy_runner_without_exchange_write(...):
    result = await run_ticket_bound_lifecycle_maintenance_scheduler(...)
    assert result["selected_scope_count"] == 1
    assert result["exchange_read_called"] is True
    assert result["exchange_write_called"] is False
```

Run:

```bash
python3 -m pytest -q \
  tests/unit/test_ticket_bound_lifecycle_scheduler.py \
  tests/unit/test_ticket_bound_post_submit_reconciliation_tick.py
```

Expected: fail because `runner_protected` is omitted.

### Step 2: Apply the minimum production correction

Add `runner_protected` to both immutable status sets. Do not add branching,
special-case SOR logic, or a new timer.

### Step 3: Verify transition behavior

Add/retain cases for:

- healthy runner -> read-only continuation;
- runner fill -> existing terminal finalizer;
- exchange flat -> existing external-close attribution;
- missing runner -> existing protection degradation;
- snapshot timeout -> no exchange write.

Run the two task files again. Expected: pass.

### Step 4: Commit

```bash
git add \
  src/application/action_time/lifecycle_maintenance_scheduler.py \
  tests/unit/test_ticket_bound_lifecycle_scheduler.py \
  tests/unit/test_ticket_bound_post_submit_reconciliation_tick.py
git commit -m "fix(runtime): maintain protected runner lifecycles"
```

---

## Task A2: Centralize Active Exit-Protection Generation Resolution

### Task card

- **Task ID:** `EXIT-A2`
- **Goal:** Replace first-role lookup with one deterministic, lineage-aware
  active-protection resolver.
- **Why:** Multiple historical/replacement rows make a role name insufficient.
- **Allowed files:**
  - Create `src/domain/ticket_exit_protection.py`
  - Create `tests/unit/test_ticket_exit_protection.py`
  - Modify `src/application/action_time/runner_protection_adjuster.py`
  - Modify `src/application/action_time/runner_mutation_command.py`
  - Modify `src/application/action_time/lifecycle_maintenance_service.py`
  - Modify `src/application/action_time/protection_reconciler.py`
  - Modify `src/application/action_time/live_outcome_ledger.py`
  - Modify their existing targeted tests
- **Forbidden files:** schema, exchange gateway, strategy semantics, new
  repository/file authority.
- **Global Authority Model:** resolver identifies existing protection; it does
  not create or dispatch commands.
- **Chain Position:** protection reconciliation before mutation/finalization.
- **Live Enablement Before:** modules can choose different historical rows.
- **Live Enablement After:** all consumers share one exact resolution result.
- **Blocker Removed:** `active_exit_protection_identity_ambiguous`.
- **Per-Symbol / Per-Fact Acceptance:** rows must belong to the same exact
  `exit_protection_set_id`; cross-set rows fail validation.
- **Stop Condition:** resolver infers identity from creation order alone or
  silently accepts two unexplained active rows.
- **Capability Unlocked:** generation-safe Release A and replacement-ready B.
- **Next Bottleneck:** generation is not yet durable in PG.
- **Rehearsal/Simulation Boundary:** pure-domain fixtures only.
- **Hard Stop:** broad symbol-level order selection.

### Step 1: Add failing pure-domain tests

Define the expected API:

```python
result = resolve_active_exit_protection(
    exit_protection_set_id="set-1",
    role="RUNNER_SL",
    orders=orders,
    now_ms=1_720_000_000_000,
    replacement_grace_ms=90_000,
)

assert result.state is ActiveProtectionResolutionState.ACTIVE_ONE
assert result.active_order.local_order_id == "runner-g2"
```

Test at least:

- one active generation;
- old filled/cancelled row plus one active generation;
- linked new-open plus old-cancel-pending within grace;
- zero active rows while position open;
- two unexplained active rows;
- broken replacement lineage;
- cross-set row;
- terminal position.

Run:

```bash
python3 -m pytest -q tests/unit/test_ticket_exit_protection.py
```

Expected: import failure.

### Step 2: Implement the pure resolver

Create frozen typed models and this public function:

```python
def resolve_active_exit_protection(
    *,
    exit_protection_set_id: str,
    role: Literal["SL", "TP1", "RUNNER_SL"],
    orders: Sequence[ExitProtectionOrderView],
    position_is_open: bool,
    now_ms: int,
    replacement_grace_ms: int,
) -> ActiveProtectionResolution:
    ...
```

The domain module imports no SQLAlchemy, HTTP, exchange, or filesystem code.

### Step 3: Replace all duplicate lookup helpers

Delete local `_role_order`/first-match helpers and adapt row dictionaries into
the typed resolver at each application boundary. Every module must branch on
the typed resolution state.

Run:

```bash
python3 -m pytest -q \
  tests/unit/test_ticket_exit_protection.py \
  tests/unit/test_ticket_bound_runner_protection_adjuster.py \
  tests/unit/test_ticket_bound_runner_mutation_command.py \
  tests/unit/test_ticket_bound_lifecycle_maintenance_service.py \
  tests/unit/test_live_outcome_ledger.py
```

Expected: pass.

### Step 4: Prove duplicate helpers are gone

```bash
rg -n "def _role_order|next\(.*role|first.*RUNNER_SL" \
  src/application/action_time
```

Expected: no competing active-protection selector remains.

### Step 5: Commit

```bash
git add \
  src/domain/ticket_exit_protection.py \
  src/application/action_time/runner_protection_adjuster.py \
  src/application/action_time/runner_mutation_command.py \
  src/application/action_time/lifecycle_maintenance_service.py \
  src/application/action_time/protection_reconciler.py \
  src/application/action_time/live_outcome_ledger.py \
  tests/unit/test_ticket_exit_protection.py \
  tests/unit/test_ticket_bound_runner_protection_adjuster.py \
  tests/unit/test_ticket_bound_runner_mutation_command.py \
  tests/unit/test_ticket_bound_lifecycle_maintenance_service.py \
  tests/unit/test_live_outcome_ledger.py
git commit -m "refactor(runtime): resolve active exit protection exactly"
```

---

## Task A3: Add Migration 121 For Protection Generation And TP1 Execution Truth

### Task card

- **Task ID:** `EXIT-A3`
- **Goal:** Persist generation, TP1 execution style, and liquidity evidence.
- **Why:** The command must remain reconstructible after restart and auditable
  against actual fees.
- **Allowed files:**
  - Create
    `migrations/versions/2026-07-14-121_add_exit_execution_safety.py`
  - Create `tests/unit/test_exit_execution_safety_migration.py`
  - Modify `tests/support/runtime_control_state_schema.py`
  - Modify deploy migration-default tests and scripts only where required
- **Forbidden files:** policy tables, strategy activation rows, runtime JSON
  export.
- **Global Authority Model:** schema records facts; it grants no command or
  submit authority.
- **Chain Position:** durable command/protection state.
- **Live Enablement Before:** generation/TIF/post-only/liquidity role are not
  explicit columns.
- **Live Enablement After:** these values survive restart and reconciliation.
- **Blocker Removed:** `tp1_execution_truth_not_durable`.
- **Per-Symbol / Per-Fact Acceptance:** no symbol-specific default.
- **Stop Condition:** migration backfills a legacy row as post-only without
  evidence.
- **Capability Unlocked:** exact TP1 and runner generation reconciliation.
- **Next Bottleneck:** domain and gateway do not yet consume the fields.
- **Rehearsal/Simulation Boundary:** migration test only.
- **Hard Stop:** destructive table rewrite or non-null backfill without an
  explicit legacy value.

### Step 1: Write the failing migration test

Assert revision/down-revision and DDL text for:

```text
brc_ticket_bound_exit_protection_orders.generation INTEGER NOT NULL DEFAULT 1
brc_ticket_bound_exchange_commands.time_in_force VARCHAR(16) NULL
brc_ticket_bound_exchange_commands.post_only BOOLEAN NOT NULL DEFAULT false
brc_ticket_bound_exchange_commands.market_fallback_allowed BOOLEAN NOT NULL DEFAULT false
brc_live_outcome_ledger.tp1_liquidity_role VARCHAR(16) NULL
brc_live_outcome_ledger.tp1_fee NUMERIC(36,18) NULL
brc_live_outcome_ledger.tp1_fee_asset VARCHAR(32) NULL
```

Add the active-generation index with a PostgreSQL identifier shorter than 63
characters.

Run:

```bash
python3 -m pytest -q \
  tests/unit/test_exit_execution_safety_migration.py \
  tests/unit/test_pg_migration_identifier_names.py
```

Expected: fail because migration 121 is absent.

### Step 2: Implement migration 121

Use `server_default="1"` only for legacy generation. Leave legacy
`time_in_force` null; never claim it was GTC/GTX. `post_only=false` is factual
for rows without evidence and `market_fallback_allowed=false` is the fail-safe
default.

### Step 3: Update migration inventory and deploy defaults

Update:

- `tests/support/runtime_control_state_schema.py`;
- `scripts/plan_tokyo_runtime_governance_git_deploy.py` latest migration;
- `scripts/verify_tokyo_runtime_governance_postdeploy.py` latest migration;
- corresponding deploy-plan/postdeploy tests.

Run:

```bash
python3 -m pytest -q \
  tests/unit/test_exit_execution_safety_migration.py \
  tests/unit/test_pg_migration_identifier_names.py \
  tests/unit/test_tokyo_runtime_governance_migration_gap_audit.py \
  tests/unit/test_tokyo_runtime_governance_release_prep.py \
  tests/unit/test_tokyo_runtime_governance_postdeploy_verify.py
```

Expected: pass.

### Step 4: Commit

```bash
git add \
  migrations/versions/2026-07-14-121_add_exit_execution_safety.py \
  tests/unit/test_exit_execution_safety_migration.py \
  tests/support/runtime_control_state_schema.py \
  scripts/plan_tokyo_runtime_governance_git_deploy.py \
  scripts/verify_tokyo_runtime_governance_postdeploy.py \
  tests/unit/test_pg_migration_identifier_names.py \
  tests/unit/test_tokyo_runtime_governance_migration_gap_audit.py \
  tests/unit/test_tokyo_runtime_governance_release_prep.py \
  tests/unit/test_tokyo_runtime_governance_postdeploy_verify.py
git commit -m "feat(runtime): persist exit execution safety facts"
```

---

## Task A4: Enforce TP1 Passive-Limit Semantics End To End

### Task card

- **Task ID:** `EXIT-A4`
- **Goal:** Prove TP1 is limit, explicit-TIF, no-market-fallback, and reconcile
  maker/taker fee truth.
- **Why:** Ordinary `LIMIT` does not guarantee passive maker execution.
- **Allowed files:**
  - Modify `src/domain/ticket_bound_exchange_command.py`
  - Modify `src/application/action_time/protected_submit_attempt.py`
  - Modify `src/application/action_time/exchange_command.py`
  - Modify `src/interfaces/api_trading_console.py`
  - Modify `src/infrastructure/exchange_gateway.py` (**Codex core file**)
  - Modify `src/application/action_time/exchange_snapshot_provider.py`
  - Modify `src/application/action_time/ticket_bound_fill_projector.py`
  - Modify `src/application/action_time/live_outcome_ledger.py`
  - Modify targeted tests for these files
- **Forbidden files:** entry order type, TP1 price/fraction formula, sizing,
  leverage, strategy registry, direct raw venue keys outside the gateway.
- **Global Authority Model:** execution style cannot bypass existing command
  preparation/executor authority.
- **Chain Position:** protection preparation, gateway dispatch, fill truth.
- **Live Enablement Before:** TP1 is ordinary limit with implicit TIF and no
  liquidity-role evidence.
- **Live Enablement After:** TP1 is explicit passive limit with no market
  downgrade and exact fee evidence.
- **Blocker Removed:** `tp1_limit_maker_contract_incomplete`.
- **Per-Symbol / Per-Fact Acceptance:** price/quantity precision comes from the
  exact exchange instrument; best-book facts are exact symbol and bounded-age.
- **Stop Condition:** any path emits TP1 `MARKET`, uses a missing price, or
  retries without deterministic generation.
- **Capability Unlocked:** fee-sensitive TP1 production certification.
- **Next Bottleneck:** current manual-close lifecycle must close cleanly before
  deploy.
- **Rehearsal/Simulation Boundary:** mocked gateway only until Tokyo read-only
  capability verification; no test exchange write is authority.
- **Hard Stop:** market fallback or canceling SL to place TP1.

### Step 1: Add failing command-model tests

Expected model shape:

```python
class TicketBoundExchangeCommand(...):
    time_in_force: Literal["GTC", "GTX"] | None
    post_only: bool
    market_fallback_allowed: Literal[False]
```

Add validators:

```python
if self.order_role == "TP1":
    if self.order_type.lower() != "limit" or self.price is None:
        raise ValueError("tp1_requires_limit_price")
    if self.market_fallback_allowed:
        raise ValueError("tp1_market_fallback_forbidden")
    if self.post_only and self.time_in_force != "GTX":
        raise ValueError("tp1_post_only_requires_gtx")
```

Run:

```bash
python3 -m pytest -q \
  tests/unit/test_ticket_bound_exchange_command.py \
  tests/unit/test_ticket_bound_exchange_command_materialization.py \
  tests/unit/test_ticket_bound_protected_submit_attempt.py
```

Expected: fail until fields and validators exist.

### Step 2: Make protected submit explicit

For TP1 emit:

```python
{
    "gateway_order_type": "limit",
    "time_in_force": "GTX",
    "post_only": True,
    "market_fallback_allowed": False,
    "price": str(tp1_price),
    "reduce_only": True,
}
```

Entry and SL behavior remain unchanged. Add negative tests that monkeypatch any
TP1 type to `market` and assert fail-closed before gateway dispatch.

### Step 3: Extend the gateway adapter

Extend the core signature without exposing Binance-specific terms to callers:

```python
async def place_order(
    ...,
    time_in_force: str | None = None,
    post_only: bool = False,
) -> OrderPlacementResult:
    ...
```

At the Binance adapter boundary, map certified passive style to
`timeInForce=GTX`. CCXT's unified `PO` capability remains feature-detected and
version-tested; the adapter test asserts the actual params sent by CCXT
**4.5.56**. Do not assume `LIMIT` means maker.

Add gateway tests proving:

- limit + GTX sends the certified post-only param;
- market + GTX is rejected locally;
- post-only on an unsupported venue is rejected, not downgraded;
- hedge-mode position side remains exact;
- no secret value enters logs.

### Step 4: Add passive-rejection state

Treat authoritative post-only rejection as a typed recoverable result. The
existing SL remains. Prepare no market command. A fresh bounded BBO fact may
create the next deterministic TP1 generation only at a non-marketable price no
worse than the policy target.

Add tests for long and short price inequalities and retry idempotency.

### Step 5: Normalize liquidity role and fees

Extend fill normalization:

```python
"liquidity_role": normalize_liquidity_role(
    raw.get("takerOrMaker"),
    info.get("maker"),
    info.get("buyerMaker"),
),
```

Do not invent maker/taker when exchange evidence is absent. Propagate TP1 fee,
fee asset, submitted type/TIF, and liquidity role into the Live Outcome.

### Step 6: Run targeted tests

```bash
python3 -m pytest -q \
  tests/unit/test_ticket_bound_exchange_command.py \
  tests/unit/test_ticket_bound_exchange_command_materialization.py \
  tests/unit/test_ticket_bound_exchange_command_worker.py \
  tests/unit/test_ticket_bound_protected_submit_attempt.py \
  tests/unit/test_exchange_gateway_open_order_views.py \
  tests/unit/test_ticket_bound_post_submit_reconciliation_tick.py \
  tests/unit/test_live_outcome_ledger.py
```

Expected: pass.

### Step 7: Commit

```bash
git add \
  src/domain/ticket_bound_exchange_command.py \
  src/application/action_time/protected_submit_attempt.py \
  src/application/action_time/exchange_command.py \
  src/interfaces/api_trading_console.py \
  src/infrastructure/exchange_gateway.py \
  src/application/action_time/exchange_snapshot_provider.py \
  src/application/action_time/ticket_bound_fill_projector.py \
  src/application/action_time/live_outcome_ledger.py \
  tests/unit/test_ticket_bound_exchange_command.py \
  tests/unit/test_ticket_bound_exchange_command_materialization.py \
  tests/unit/test_ticket_bound_exchange_command_worker.py \
  tests/unit/test_ticket_bound_protected_submit_attempt.py \
  tests/unit/test_exchange_gateway_open_order_views.py \
  tests/unit/test_ticket_bound_post_submit_reconciliation_tick.py \
  tests/unit/test_live_outcome_ledger.py
git commit -m "fix(execution): enforce passive limit tp1 semantics"
```

---

## Task A5: Certify Strict Manual External-Close Recovery

### Task card

- **Task ID:** `EXIT-A5`
- **Goal:** Prove a manual reduce-only close settles the exact Ticket and cleans
  only its residual protection.
- **Why:** Release A cannot deploy around an ambiguous live lifecycle.
- **Allowed files:**
  - Modify the four targeted test files listed below
  - Modify `src/application/action_time/external_close_attribution.py` only if
    its exact attribution test fails
  - Modify
    `src/application/action_time/orphan_protection_cleanup_command.py` only if
    exact PG-linked cleanup fails
  - Modify `src/application/action_time/lifecycle_maintenance_service.py` only
    if lifecycle routing fails
  - Modify
    `src/application/action_time/ticket_bound_lifecycle_finalizer.py` only if
    terminal closure or single-outcome idempotency fails
  - Modify `src/application/action_time/ticket_bound_budget_settlement.py` only
    if one-time settlement fails
  - Modify existing lifecycle Owner notification code only if the terminal
    product state is incorrect
- **Forbidden files:** symbol-wide cancel, heuristic Ticket attribution, manual
  PG mutation scripts, deploy bypass.
- **Global Authority Model:** exchange facts determine closure; Owner manual
  action does not rewrite strategy semantics.
- **Chain Position:** external close -> orphan cleanup -> terminal settlement.
- **Live Enablement Before:** recovery path exists but must be certified against
  the current runner case.
- **Live Enablement After:** exact manual close produces one terminal outcome.
- **Blocker Removed:** `manual_close_recovery_not_certified`.
- **Per-Symbol / Per-Fact Acceptance:** exact account, venue, canonical
  instrument, position bucket, side, quantity, time, order identity, and unique
  Ticket.
- **Stop Condition:** residual open protection, duplicate outcome, or uncertain
  attribution.
- **Capability Unlocked:** ordinary zero-active-lifecycle deploy.
- **Next Bottleneck:** Release A release-level certification.
- **Rehearsal/Simulation Boundary:** production-shaped PG fixture only; real
  manual close remains Owner action.
- **Hard Stop:** direct production row edits.

### Step 1: Add the production-shaped regression

Extend:

- `tests/unit/test_tiny001d1b_external_close_monitor.py`;
- `tests/unit/test_ticket_bound_post_submit_closure.py`;
- `tests/unit/test_ticket_bound_lifecycle_finalizer.py`;
- `tests/integration/test_runtime_causal_integrity_postgres.py`.

Assert:

```python
assert lifecycle["final_exit_type"] == "EXTERNAL_CLOSE"
assert lifecycle["status"] == "completed"
assert residual_pg_linked_open_protection == []
assert live_outcome_count == 1
assert budget_settlement_count == 1
assert unrelated_symbol_orders_untouched is True
```

Add negative cases for wrong bucket, wrong side, quantity mismatch, two
candidate Tickets, and missing exchange order identity.

### Step 2: Run the tests before editing production code

```bash
python3 -m pytest -q \
  tests/unit/test_tiny001d1b_external_close_monitor.py \
  tests/unit/test_ticket_bound_post_submit_closure.py \
  tests/unit/test_ticket_bound_lifecycle_finalizer.py \
  tests/integration/test_runtime_causal_integrity_postgres.py
```

If all pass, this is a test-only certification task. If a test fails, implement
the smallest shared-invariant correction in the already existing modules and
rerun the full set.

### Step 3: Commit

Stage only the actual touched files and commit:

```bash
git commit -m "test(runtime): certify exact external close recovery"
```

---

## Task A6: Review, Certify, And Deploy Release A

### Pre-deploy acceptance

Run:

```bash
python3 -m pytest -q
python3 scripts/audit_production_runtime_file_io.py --fail-on-risk --json
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
git diff --check
git status --short
```

Required results:

- all tests pass;
- `performance_risk.status` is `clear`;
- no output artifact violation;
- no unstaged implementation file;
- code review has no P0/P1 finding;
- exchange is flat and active real lifecycle count is zero.

### Release A dry run

Collect current read-only deployment facts using the existing preflight script,
then invoke:

```bash
ssh tokyo /home/ubuntu/brc-deploy/venvs/brc-bnb-prelive-20260601/bin/python --version
python3 scripts/plan_tokyo_runtime_governance_git_deploy.py \
  --git-ref codex/release-risk-analysis-20260714 \
  --target-commit "$(git rev-parse HEAD)" \
  --expected-latest-migration 2026-07-14-121_add_exit_execution_safety.py \
  --venv-python /home/ubuntu/brc-deploy/venvs/brc-bnb-prelive-20260601/bin/python \
  --previous-release "$PREVIOUS_RELEASE" \
  --expected-deployed-head "$DEPLOYED_HEAD" \
  --expected-remote-migration-count "$REMOTE_MIGRATION_COUNT" \
  --expected-remote-latest-migration "$REMOTE_LATEST_MIGRATION"
```

The uppercase variables must be populated only from the same run's read-only
Tokyo preflight output, never from a stale note.

### Deploy and postdeploy

Use the existing apply executor only after its dry-run reports ready. Pass the
same explicit venv Python. After release switch:

```bash
python3 scripts/verify_tokyo_runtime_governance_postdeploy.py \
  --expected-current-head "$(git rev-parse HEAD)" \
  --expected-latest-migration 2026-07-14-121_add_exit_execution_safety.py \
  --venv-python /home/ubuntu/brc-deploy/venvs/brc-bnb-prelive-20260601/bin/python
```

Postdeploy acceptance:

- CCXT reports **4.5.56** from the explicit venv;
- migration head is 121;
- lifecycle timer is active;
- a read-only production-shaped `runner_protected` fixture/simulation is
  selectable;
- no exchange write occurs during certification;
- new TP1 command preview is `limit + GTX + no market fallback`.

Record the exact deployed commit and release identity in PG/current capability
state, not a recurring report file.

---

## Task B1: Implement The Pure Versioned Exit Policy Domain

### Task card

- **Task ID:** `EXIT-B1`
- **Goal:** Add typed policy models, canonical hashing, and pure evaluation.
- **Why:** Strategy exit semantics are currently named but not executable
  Ticket authority.
- **Allowed files:**
  - Create `src/domain/ticket_exit_policy.py`
  - Create `tests/unit/test_ticket_exit_policy.py`
- **Forbidden files:** all I/O, exchange calls, SQLAlchemy, current strategy
  activation.
- **Global Authority Model:** evaluator returns intent only.
- **Chain Position:** after fact/protection truth, before command preparation.
- **Live Enablement Before:** no shared executable exit-policy abstraction.
- **Live Enablement After:** deterministic typed decisions exist in pure code.
- **Blocker Removed:** `shared_exit_policy_domain_missing`.
- **Per-Symbol / Per-Fact Acceptance:** instrument identity is an input; no
  crypto-specific hidden constant.
- **Stop Condition:** unstructured parameter dictionaries or float arithmetic.
- **Capability Unlocked:** schema binding and application orchestration.
- **Next Bottleneck:** policy has no durable PG authority.
- **Rehearsal/Simulation Boundary:** pure tests only.
- **Hard Stop:** evaluator dispatches commands.

### Step 1: Write failing model tests

Test discriminated models for:

- `RIGHT_TAIL_RUNNER`, `FIXED_TARGETS`, `LIFECYCLE_ONLY`;
- `LIMIT_GTC`, `PASSIVE_LIMIT_GTX`;
- structural ATR, reference trail, no runner;
- invalidation and time-stop rules;
- canonical payload hash independent of mapping insertion order;
- invalid fraction totals, non-positive R, malformed side/timeframe;
- `market_fallback_allowed=True` rejected.

Run:

```bash
python3 -m pytest -q tests/unit/test_ticket_exit_policy.py
```

Expected: import failure.

### Step 2: Implement frozen typed models

Use `ConfigDict(frozen=True, extra="forbid")` and `Decimal` for every financial
number. Add one canonical serialization/hash function.

### Step 3: Add evaluator tests before evaluator code

Cover:

```python
assert evaluate_exit_policy(flat_input).kind is ExitDecisionKind.NOOP
assert evaluate_exit_policy(missing_protection).kind is ExitDecisionKind.BLOCKED
assert evaluate_exit_policy(invalidation_hit).kind is ExitDecisionKind.CLOSE_RUNNER
assert evaluate_exit_policy(time_stop_hit).kind is ExitDecisionKind.CLOSE_RUNNER
assert evaluate_exit_policy(long_improvement).proposed_stop > current_stop
assert evaluate_exit_policy(short_improvement).proposed_stop < current_stop
assert evaluate_exit_policy(non_improvement).kind is ExitDecisionKind.NOOP
```

Priority tests must prove invalidation wins over a simultaneous trail move.

### Step 4: Implement and verify

Run:

```bash
python3 -m pytest -q tests/unit/test_ticket_exit_policy.py
python3 -m compileall -q src/domain/ticket_exit_policy.py
```

Expected: pass.

### Step 5: Commit

```bash
git add src/domain/ticket_exit_policy.py tests/unit/test_ticket_exit_policy.py
git commit -m "feat(domain): add versioned ticket exit policy"
```

---

## Task B2: Add Migration 122 For Policy Authority And Current Projection

### Task card

- **Task ID:** `EXIT-B2`
- **Goal:** Create policy authority, immutable Ticket binding, and one current
  projection.
- **Why:** Runtime behavior must survive restart and cannot read registry files.
- **Allowed files:**
  - Create
    `migrations/versions/2026-07-14-122_add_ticket_exit_policy_core.py`
  - Create `tests/unit/test_ticket_exit_policy_migration.py`
  - Modify schema/deploy migration inventory files and tests
- **Forbidden files:** current policy seed rows, strategy parameter defaults,
  file-backed repositories.
- **Global Authority Model:** schema does not activate capability.
- **Chain Position:** policy registry -> Ticket -> lifecycle current projection.
- **Live Enablement Before:** no durable policy snapshot/current evaluator state.
- **Live Enablement After:** future-only typed authority can be persisted.
- **Blocker Removed:** `exit_policy_pg_authority_missing`.
- **Per-Symbol / Per-Fact Acceptance:** Event Spec and side are explicit;
  instrument remains Ticket-bound.
- **Stop Condition:** one policy row can silently affect historical Tickets.
- **Capability Unlocked:** materializer and service implementation.
- **Next Bottleneck:** no application binding.
- **Rehearsal/Simulation Boundary:** capability remains disabled.
- **Hard Stop:** seeding `status=current`.

### Step 1: Write the failing migration test

Assert:

```text
brc_strategy_exit_policies
brc_ticket_exit_policy_current
brc_action_time_tickets.exit_policy_id
brc_action_time_tickets.exit_policy_version
brc_action_time_tickets.exit_policy_snapshot
brc_action_time_tickets.exit_policy_hash
```

Require a partial unique index for one `current` exact policy scope and a
primary/unique owner boundary on `brc_ticket_exit_policy_current.ticket_id`.
The same migration extends the existing lifecycle exchange-command source
constraint with `exit_policy_runner` and `exit_policy_close`; it does not create
a new command table or dispatcher.

Run migration and identifier tests. Expected: fail.

### Step 2: Implement migration 122

Backfill historical Tickets with:

```json
{"binding_kind":"legacy_unbound","historical_semantics_not_synthesized":true}
```

Use an explicit legacy hash. Do not query current strategy rows during
backfill. Add capability `ticket_exit_policy_v1` as
`certified_disabled` only if the existing capability table contract supports
the row; otherwise the application must treat absence as disabled.

### Step 3: Update deploy defaults and verify

Run the same migration/deploy test set as A3 with expected latest migration
**122**.

### Step 4: Commit

```bash
git commit -m "feat(runtime): add ticket exit policy postgres core"
```

---

## Task B3: Bind Immutable Exit Policies Into Future Tickets

### Task card

- **Task ID:** `EXIT-B3`
- **Goal:** Query, validate, hash, and freeze the exact policy into Ticket
  identity.
- **Why:** Current registry changes must not reinterpret open positions.
- **Allowed files:**
  - Create `src/application/action_time/ticket_exit_policy_binding.py`
  - Create `tests/unit/test_ticket_exit_policy_binding.py`
  - Modify `src/application/action_time/action_time_ticket.py`
  - Modify `tests/unit/test_action_time_ticket_materialization.py`
- **Forbidden files:** default policy invention, historical row mutation,
  strategy activation.
- **Global Authority Model:** binding supplies semantics, not submit authority.
- **Chain Position:** Ticket materialization before action-time safety.
- **Live Enablement Before:** Ticket hash omits exit semantics.
- **Live Enablement After:** exact policy identity/hash is immutable.
- **Blocker Removed:** `ticket_exit_policy_not_frozen`.
- **Per-Symbol / Per-Fact Acceptance:** exact StrategyGroup/version/Event
  Spec/version/side match.
- **Stop Condition:** fallback to latest policy from a mismatched version.
- **Capability Unlocked:** restart-safe evaluation.
- **Next Bottleneck:** no due market fact/current projection service.
- **Rehearsal/Simulation Boundary:** capability remains disabled.
- **Hard Stop:** policy row upgrades Ticket authority.

### Step 1: Add failing binding tests

Cover exact match, missing policy, duplicate current policy, invalid payload,
hash mismatch, version mismatch, side mismatch, legacy Ticket, and identity
hash changes when policy version changes.

### Step 2: Implement the binding service

Public function:

```python
def load_ticket_exit_policy_binding(
    conn: sa.engine.Connection,
    *,
    strategy_group_id: str,
    strategy_version: str,
    event_spec_id: str,
    event_spec_version: str,
    side: str,
) -> TicketExitPolicyBinding:
    ...
```

Validate through `TicketExitPolicySnapshot` before returning.

### Step 3: Extend Ticket hashes

Add policy identity/hash to `TICKET_IDENTITY_HASH_FIELDS` and
`created_under_versions_hash`. Persist the complete immutable snapshot.

### Step 4: Verify and commit

```bash
python3 -m pytest -q \
  tests/unit/test_ticket_exit_policy_binding.py \
  tests/unit/test_action_time_ticket_materialization.py
git commit -m "feat(runtime): freeze exit policy into action-time tickets"
```

---

## Task B4: Build Due Closed-Market Facts And The Current Projection

### Task card

- **Task ID:** `EXIT-B4`
- **Goal:** Evaluate once per exact new closed policy candle with PG-backed
  watermark/state.
- **Why:** A trailing policy needs current facts without tick churn or files.
- **Allowed files:**
  - Create `src/application/action_time/ticket_exit_market_fact_service.py`
  - Create `src/application/action_time/ticket_exit_policy_projection.py`
  - Create `tests/unit/test_ticket_exit_market_fact_service.py`
  - Create `tests/unit/test_ticket_exit_policy_projection.py`
  - Reuse/extend the existing public closed-candle adapter
- **Forbidden files:** new timer, runtime report writer, repo config reader,
  network call inside a long transaction.
- **Global Authority Model:** facts cannot create submit authority.
- **Chain Position:** lifecycle due check -> exact fact -> pure decision.
- **Live Enablement Before:** no exit evaluation watermark/current owner.
- **Live Enablement After:** one projector and bounded due-fact service exist.
- **Blocker Removed:** `exit_market_fact_cadence_missing`.
- **Per-Symbol / Per-Fact Acceptance:** exact canonical instrument, venue,
  timeframe, final closed-candle timestamp, observed/valid times.
- **Stop Condition:** no-due tick calls public market API or writes a file.
- **Capability Unlocked:** application exit-policy orchestration.
- **Next Bottleneck:** decision cannot mutate runner yet.
- **Rehearsal/Simulation Boundary:** injected fake candle source.
- **Hard Stop:** using open/incomplete candle as exit authority.

### Step 1: Add failing cadence tests

Assert:

- before due time -> zero API calls;
- same watermark twice -> one evaluation;
- first new final candle -> one claim/fact row;
- stale or scope-mismatched candle -> blocker, no decision;
- two Tickets same instrument/timeframe -> coalesced source fetch;
- API timeout -> existing runner unchanged;
- zero JSON/MD writes.

### Step 2: Implement a typed port

```python
class ClosedCandleSource(Protocol):
    async def fetch_closed_candles(
        self,
        *,
        exchange_instrument_id: str,
        venue_id: str,
        timeframe: str,
        through_ms: int,
        limit: int,
        timeout_seconds: Decimal,
    ) -> Sequence[ClosedCandle]: ...
```

Use the existing Binance public source as the first adapter. Persist fact
snapshots under `fact_surface=ticket_exit_market`.

### Step 3: Implement one current projection owner

Use compare-and-set on `last_evaluated_watermark_ms` and
`next_evaluation_not_before_ms`. No other service writes the current projection.

### Step 4: Verify performance boundary

```bash
python3 -m pytest -q \
  tests/unit/test_ticket_exit_market_fact_service.py \
  tests/unit/test_ticket_exit_policy_projection.py
python3 scripts/audit_production_runtime_file_io.py --fail-on-risk --json
```

Expected: tests pass and performance risk is clear.

### Step 5: Commit

```bash
git commit -m "feat(runtime): add due exit market facts and projection"
```

---

## Task B5: Orchestrate Policy Decisions Through The Existing Command Authority

### Task card

- **Task ID:** `EXIT-B5`
- **Goal:** Convert typed decisions into generation-safe existing exchange
  commands and wire them into the existing scheduler.
- **Why:** Pure policy capability is not useful until it can safely maintain a
  runner.
- **Allowed files:**
  - Create `src/application/action_time/ticket_exit_policy_service.py`
  - Create `tests/unit/test_ticket_exit_policy_service.py`
  - Modify `src/application/action_time/lifecycle_maintenance_scheduler.py`
  - Modify `src/application/action_time/runner_mutation_command.py`
  - Modify `src/domain/ticket_bound_exchange_command.py`
  - Modify targeted lifecycle-event constraint tests without changing the
    already committed migration 122 contract
- **Forbidden files:** new command table, new dispatcher, cancel-old-first,
  direct exchange call from policy service.
- **Global Authority Model:** existing durable command worker remains the only
  write executor.
- **Chain Position:** typed decision -> durable command -> reconciliation.
- **Live Enablement Before:** decision is rehearsal-only.
- **Live Enablement After:** disabled capability can run full-chain simulation.
- **Blocker Removed:** `exit_policy_command_bridge_missing`.
- **Per-Symbol / Per-Fact Acceptance:** command inherits exact Ticket account,
  instrument, side, bucket, profile, policy hash, and market watermark.
- **Stop Condition:** command lacks deterministic generation or replacement
  lineage.
- **Capability Unlocked:** production-shaped Release B certification.
- **Next Bottleneck:** six-Event-Spec matrix.
- **Rehearsal/Simulation Boundary:** production capability remains disabled.
- **Hard Stop:** direct exchange mutation or activation row.

### Step 1: Add failing orchestration tests

Test:

- `NOOP` creates no command;
- `BLOCKED` creates no command and preserves SL;
- `MOVE_RUNNER_STOP` prepares generation N+1;
- new stop must be monotonic and tick-aligned;
- new place confirmed before old cancel command exists;
- unknown place outcome blocks cancellation;
- old fill during replacement terminates lifecycle and prevents duplicate close;
- exact cancel target is the PG-linked prior exchange order;
- `CLOSE_RUNNER` prepares one reduce-position exit command;
- restart at every state resumes idempotently.

### Step 2: Extend command-source enum without a second authority

Add exact sources such as `exit_policy_runner` and `exit_policy_close` to the
existing typed domain and check constraints. Preserve the existing unique
command identity of source/kind/role/generation.

### Step 3: Implement the service

```python
async def maintain_ticket_exit_policy(
    *,
    conn_factory: Callable[[], ContextManager[Connection]],
    ticket_id: str,
    now_ms: int,
    closed_candle_source: ClosedCandleSource,
) -> TicketExitPolicyMaintenanceResult:
    ...
```

The service performs short PG reads/claims, releases the transaction for market
I/O, persists exact fact/decision, and prepares a command. It never calls
`gateway.place_order` or `gateway.cancel_order`.

### Step 4: Wire the existing scheduler

After existing lifecycle reconciliation, call the service only for due,
capability-enabled runner states. A disabled capability returns a no-write
product state and preserves existing fixed runner behavior.

### Step 5: Verify and commit

```bash
python3 -m pytest -q \
  tests/unit/test_ticket_exit_policy_service.py \
  tests/unit/test_ticket_bound_lifecycle_scheduler.py \
  tests/unit/test_ticket_bound_runner_mutation_command.py \
  tests/unit/test_ticket_bound_runner_mutation_executor.py \
  tests/unit/test_ticket_bound_exchange_command_reconciliation.py
git commit -m "feat(runtime): route exit policies through durable commands"
```

---

## Task B6: Add Six-Event-Spec Production-Shaped Certification

### Task card

- **Task ID:** `EXIT-B6`
- **Goal:** Prove the core is strategy-agnostic across all active Event Specs
  while still disabled.
- **Why:** A SOR-only green path would not prove the shared abstraction.
- **Allowed files:**
  - Modify `src/application/action_time/full_chain_simulation_harness.py`
  - Create `tests/unit/test_ticket_exit_policy_full_chain.py`
  - Modify `tests/integration/test_runtime_causal_integrity_postgres.py`
- **Forbidden files:** production strategy activation, hard-coded symbol logic,
  test-only authority shortcuts.
- **Global Authority Model:** simulation cannot grant live submit.
- **Chain Position:** full lifecycle rehearsal.
- **Live Enablement Before:** component proof only.
- **Live Enablement After:** all active Event Specs pass the shared matrix.
- **Blocker Removed:** `exit_policy_production_shape_uncertified`.
- **Per-Symbol / Per-Fact Acceptance:** all six Event Specs; long/short; at least
  two canonical instruments; exact side/bucket.
- **Stop Condition:** a fixture bypasses FinalGate/Operation Layer or uses a
  privileged fake command outcome.
- **Capability Unlocked:** Release B deploy disabled.
- **Next Bottleneck:** strategy replay and Owner policy.
- **Rehearsal/Simulation Boundary:** explicit in every result.
- **Hard Stop:** certification changes capability to enabled.

### Step 1: Build the matrix

Parametrize:

```python
ACTIVE_EVENT_SPECS = (
    ("CPM-RO-001", "CPM-LONG", "long", "1h"),
    ("MPG-001", "MPG-LONG", "long", "1h"),
    ("MI-001", "MI-LONG", "long", "1h"),
    ("SOR-001", "SOR-LONG", "long", "15m"),
    ("SOR-001", "SOR-SHORT", "short", "15m"),
    ("BRF2-001", "BRF2-SHORT", "short", "1h"),
)
```

For each, prove Ticket snapshot, passive TP1, TP1 fill, runner creation,
evaluation, replacement/invalidation, terminal reconciliation, settlement,
fees, and one Live Outcome.

### Step 2: Add negative matrix

Cover stale/missing fact, wrong side, wrong Event Spec version, missing runner,
duplicate runner, partial TP1, post-only rejection, unknown place/cancel/close,
restart, manual external close, venue passive-limit absence, and non-improving
trail.

### Step 3: Run certification

```bash
python3 -m pytest -q \
  tests/unit/test_ticket_exit_policy_full_chain.py \
  tests/integration/test_runtime_causal_integrity_postgres.py
```

Expected: pass with capability still disabled.

### Step 4: Commit

```bash
git commit -m "test(runtime): certify exit policy full chain"
```

---

## Task B7: Review, Certify, And Deploy Release B Disabled

Run:

```bash
python3 -m pytest -q
python3 scripts/audit_production_runtime_file_io.py --fail-on-risk --json
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
git diff --check
git status --short
```

Review must prove:

- no second scheduler/command/order/event authority;
- no direct exchange call from domain/policy service;
- no current policy seed;
- capability is `certified_disabled` or absent/fail-disabled;
- historical Tickets are `legacy_unbound` without synthesized meaning;
- no production file I/O regression;
- no P0/P1 finding.

Use the Release A deploy commands with expected migration changed to:

```text
2026-07-14-122_add_ticket_exit_policy_core.py
```

Postdeploy read-only acceptance:

- migration head 122;
- explicit venv CCXT 4.5.56;
- policy tables/query work;
- current capability disabled;
- scheduler no-due tick performs no public candle call and no file write;
- existing live behavior remains the Release A behavior.

---

## Task C1: Create An Isolated Research Worktree And Shared Replay Harness

### Task card

- **Task ID:** `EXIT-C1`
- **Goal:** Implement one reusable exit-policy replay model outside production.
- **Why:** Exact parameters require evidence and must not be invented in the
  runtime repository.
- **Allowed repository:** `/Users/jiangwei/Documents/final-strategy-research`
  in a new isolated `codex/*` worktree.
- **Allowed files in that worktree:**
  - Create `src/domain/exit_policy_replay.py`
  - Create `scripts/run_active_strategy_exit_policy_replay.py`
  - Create `tests/test_exit_policy_replay.py`
  - Reuse logic from existing SOR/MPG exit-analysis scripts by importing or
    decisive refactor, not copy/paste drift
- **Forbidden files:** production main repo runtime, live PG, exchange-write
  credentials, generated artifacts in `/Users/jiangwei/Documents/final`.
- **Global Authority Model:** research evidence cannot activate a policy.
- **Chain Position:** strategy evidence before Owner activation.
- **Live Enablement Before:** parameters are unevaluated candidates.
- **Live Enablement After:** a shared reproducible comparison exists.
- **Blocker Removed:** `exit_policy_replay_harness_missing`.
- **Per-Symbol / Per-Fact Acceptance:** strategy, event, symbol, side, timeframe,
  fee, fill model, and split are explicit.
- **Stop Condition:** research reads live current files or emits runtime
  authority.
- **Capability Unlocked:** C2 parameter sweeps.
- **Next Bottleneck:** comparative results.
- **Rehearsal/Simulation Boundary:** all outputs labeled research-only.
- **Hard Stop:** modifying the existing dirty research worktree.

### Step 1: Create the isolated worktree

After verifying the research repository and current dirty worktree:

```bash
git -C /Users/jiangwei/Documents/final-strategy-research fetch origin
git -C /Users/jiangwei/Documents/final-strategy-research worktree add \
  /Users/jiangwei/Documents/final-strategy-research/.worktrees/exit-policy-replay-20260714 \
  -b codex/exit-policy-replay-20260714
```

Do not clean, reset, or reuse the dirty primary research worktree.

### Step 2: Write failing replay tests

Test bar ordering, TP1 partial fill, passive maker/taker model, ambiguous
same-bar TP1/SL touch, structural trail monotonicity, invalidation priority,
time stop, fee/funding, MFE/MAE, tail contribution, and no look-ahead.

### Step 3: Implement the shared harness

The harness accepts typed candidates and returns typed per-trade and aggregate
results. Runtime does not import this module.

### Step 4: Verify and commit in the research worktree

```bash
python3 -m pytest -q tests/test_exit_policy_replay.py
git diff --check
git add src/domain/exit_policy_replay.py \
  scripts/run_active_strategy_exit_policy_replay.py \
  tests/test_exit_policy_replay.py
git commit -m "feat(research): add shared exit policy replay"
```

---

## Task C2: Run Strategy-Specific Candidate Sweeps

### Task card

- **Task ID:** `EXIT-C2`
- **Goal:** Compare exit candidates for all six active Event Specs.
- **Why:** One universal trailing parameter set would overfit strategy semantics.
- **Allowed files:** research worktree scripts/tests and bounded research output
  under its documented research-results directory.
- **Forbidden files:** main runtime policy rows, current capability state,
  production deployment.
- **Global Authority Model:** evidence only.
- **Chain Position:** replay comparison.
- **Live Enablement Before:** candidate table only.
- **Live Enablement After:** recommended exact versions with sensitivity bounds.
- **Blocker Removed:** `exit_policy_parameter_evidence_missing`.
- **Per-Symbol / Per-Fact Acceptance:** symbol matrix, long/short separation,
  regime and out-of-sample splits.
- **Stop Condition:** result depends on a single symbol/window or optimistic
  ambiguous fill.
- **Capability Unlocked:** Owner decision package.
- **Next Bottleneck:** Owner activation decision.
- **Rehearsal/Simulation Boundary:** research-only labels.
- **Hard Stop:** declaring production-ready based only on in-sample net R.

### Candidate grid

For each Event Spec, compare:

1. current TP1 1R/50% baseline;
2. `LIMIT_GTC` and `PASSIVE_LIMIT_GTX` with conservative fill assumptions;
3. no hard TP2 and relevant fixed-target controls;
4. strategy-native invalidation;
5. time-stop candidates;
6. structural window and volatility buffer ranges;
7. minimum stop-improvement ticks and evaluation timeframe.

The old SOR `3 bars / ATR(14) / 0.5 ATR` values are one candidate, not a
default.

### Required metrics

Produce net R, mean/median R, tail contribution, profit giveback, MFE, MAE,
false-breakout loss, worst rolling windows, maker/taker fill rate, fee,
slippage, funding, stop-update count, rejection/retry count, time in trade, and
capital-slot occupancy.

### Verification

Run the research repository's complete test suite plus deterministic reruns
with a fixed data/version manifest. The two runs must produce identical policy
rankings and hashes.

Commit code and a bounded immutable research decision artifact in the research
repository. Do not copy generated replay data into the production repo.

---

## Task C3: Produce The Owner Decision Package And Stop

### Task card

- **Task ID:** `EXIT-C3`
- **Goal:** Translate research evidence into exact version candidates and one
  recommended canary.
- **Why:** Parameter selection and live activation are Owner policy.
- **Allowed files:** design/research decision document only; no runtime code or
  policy migration.
- **Forbidden files:** migration 123, current policy rows, live capability.
- **Global Authority Model:** Owner decides policy; system has not activated it.
- **Chain Position:** mandatory activation gate.
- **Live Enablement Before/After:** unchanged; Release B remains disabled.
- **Blocker Removed:** none until Owner decision.
- **Per-Symbol / Per-Fact Acceptance:** every recommendation references exact
  replay version/hash and scope.
- **Stop Condition:** any activation mutation.
- **Capability Unlocked:** only after Owner approval.
- **Next Bottleneck:** Owner decision.
- **Rehearsal/Simulation Boundary:** explicit.
- **Hard Stop:** do not continue to C4 automatically.

The package must contain, for each Event Spec:

- exact TP1 target/fraction/execution style;
- invalidation rule;
- time stop;
- runner structure/timeframe/window/buffer/minimum improvement;
- recommended version id/hash;
- maker/taker and fee results;
- tail/risk/operations/robustness comparison;
- rejected alternatives and sensitivity;
- recommended first canary and rollback rule.

End execution here and wait for explicit Owner approval.

---

## Task C4: Create Migration 123 Only After Owner Approval

### Authorization prerequisite

This task is **blocked by design** until the Owner approves exact Event Spec
policy values.

### Task card

- **Task ID:** `EXIT-C4`
- **Goal:** Persist the approved strategy/event/policy version for future
  Tickets only.
- **Allowed files after approval:**
  - Create a date-stamped migration 123 with approved version rows
  - Add migration tests and registry/current projection tests
  - Update deploy migration defaults
- **Forbidden files:** historical Ticket updates, unapproved Event Specs,
  symbol/scope/capital/profile expansion.
- **Chain Position:** Owner policy -> future Ticket authority.
- **Live Enablement Before:** Release B disabled.
- **Live Enablement After:** exact approved Event Spec eligible for one canary.
- **Hard Stop:** migration payload differs from the approved hash.

### TDD sequence after approval

1. Write a migration test containing the exact approved id/version/hash.
2. Assert no historical Ticket row changes.
3. Assert only one future-current policy exists for the exact Event Spec/side.
4. Implement migration 123.
5. Rerun migration, Ticket binding, policy service, and six-spec negative tests.
6. Commit:

```bash
git commit -m "feat(strategy): activate approved exit policy canary"
```

---

## Task C5: Deploy One-Event-Spec Canary And Certify Natural Production Behavior

### Preconditions

- Owner-approved migration 123 exists.
- Release A and B are deployed and green.
- Zero conflicting active position/open order exists at deploy.
- The exact Event Spec remains inside existing capital/profile/symbol/side
  authority.
- Full test, file-I/O audit, output scope, deploy plan, preflight, and postdeploy
  gates are green.

### Canary sequence

```text
activate one exact Event Spec version
-> create only future Ticket with frozen policy hash
-> prove passive TP1 command preview
-> wait for natural eligible opportunity
-> prove actual TP1 type/TIF/liquidity role/fee
-> prove runner creation and continuous monitoring
-> prove one trail/invalidation/time-stop decision if naturally reached
-> prove replacement or final close
-> prove settlement and one Live Outcome
```

No missing natural event blocks engineering closure, but it does block claims
about realized production economics.

### Canary rollback

If an invariant fails:

1. disable new Ticket creation for the policy version;
2. preserve the active Ticket's frozen semantics and exchange-native stop;
3. reconcile exact command outcomes;
4. forward-fix the active lifecycle;
5. do not roll back to code unable to read the active policy/generation;
6. do not cancel protective orders merely to switch releases.

## Final Program Verification

After the approved C canary completes, run:

```bash
python3 -m pytest -q
python3 scripts/audit_production_runtime_file_io.py --fail-on-risk --json
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
git diff --check
git status --short --branch
```

The program is complete only when all acceptance criteria in the design are
met, deployed release identity is exact, no P0/P1 review finding remains, and
the Owner-approved Event Spec has one fully reconciled future Ticket outcome.

## Implementation Handoff Summary

| Release | Code tasks | Review checkpoint | Deployment checkpoint | Mandatory stop |
| --- | --- | --- | --- | --- |
| **A** | A1-A5 | After A5 | A6 | Any active/ambiguous lifecycle |
| **B** | B1-B6 | After B6 | B7 disabled | Any accidental activation |
| **C** | C1-C2 | C3 decision package | C5 after C4 | **C3 Owner approval gate** |

The next executable action after document approval is **Task A1**, not Release
C research and not a live policy activation.
