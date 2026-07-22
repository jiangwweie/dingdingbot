# Tokyo Production Cutover And Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the missing production adapters and deploy the rebuilt kernel to Tokyo through an isolated BRC-only destructive cutover and one terminal small real-funds Ticket.

**Architecture:** One production factory constructs the public market source and the authenticated Binance USD-M venue adapter. One idempotent runtime seed creates current authority in a new dedicated PostgreSQL database. One committed Tokyo cutover adapter owns only the exact BRC container, units, release, snapshot, and capability transitions.

**Tech Stack:** Python 3.11+, Pydantic 2, SQLAlchemy 2, asyncpg, Alembic, CCXT 4.5.56, PostgreSQL 16, Docker, systemd.

## Global Constraints

- One Exposure Episode owns exactly one Ticket and adding to a position is forbidden.
- New ENTRY is globally serialized; existing Ticket protection, exit, reconciliation, and Review remain concurrent.
- Acceptance policy is one Ticket, 20 USDT maximum notional, 10 USDT maximum stop risk, and 2x leverage.
- Full policy after acceptance is two Tickets, 40 USDT gross notional, 20 USDT gross stop risk, 10 USDT per-Ticket stop risk, and 2x leverage.
- New ENTRY disablement must not disable protection or controlled exit for an accepted Ticket.
- No credential mutation, withdrawal, transfer, stale-fact submit, unknown-outcome resend, or non-BRC mutation.
- Production no-signal cadence writes no JSON or Markdown files.
- Every exchange and subprocess call is timeout-bounded.

## File Structure

| File | Responsibility |
| --- | --- |
| `src/trading_kernel/infrastructure/production_runtime.py` | Parse exact production environment and construct CCXT market/venue adapters |
| `src/trading_kernel/infrastructure/runtime_authority_seed.py` | Idempotently seed runtime profile, policies, scopes, lane, capabilities, and metadata |
| `src/trading_kernel/infrastructure/tokyo_cutover_adapter.py` | Inspect and mutate only the explicit Tokyo BRC deployment allowlist |
| `scripts/trading_kernel/seed_runtime_authority.py` | Thin runtime authority seed CLI |
| `scripts/trading_kernel/probe_production_runtime.py` | Readonly factory/account/rule probe with masked output |
| `tests/trading_kernel/unit/test_production_runtime.py` | Factory identity, masking, symbol, and close behavior |
| `tests/trading_kernel/integration/test_runtime_authority_seed.py` | Exact idempotent 22-scope acceptance/full policy seed |
| `tests/trading_kernel/integration/test_production_cutover_adapter.py` | Explicit target allowlist, refusal gates, and phase postconditions |

---

### Task 1: Refresh Action-Time Instrument Rules And Preserve Lifecycle Authority

**Files:**
- Modify: `src/trading_kernel/application/runtime_facts.py`
- Modify: `src/trading_kernel/application/ports.py`
- Modify: `src/trading_kernel/interfaces/entry_worker.py`
- Modify: `src/trading_kernel/infrastructure/venue_adapter.py`
- Modify: `src/trading_kernel/infrastructure/pg_signal_repository.py`
- Modify: `scripts/trading_kernel/run_command_worker_once.py`
- Test: `tests/trading_kernel/integration/test_runtime_fact_workers.py`
- Test: `tests/trading_kernel/unit/test_venue_adapter.py`

**Interfaces:**
- Produces: `InstrumentRulesRequest` and `InstrumentRulesSource.read_instrument_rules(request) -> CapacityInstrumentRules`.
- Produces: `SignalRepository.upsert_instrument_rules(...) -> InstrumentRulesSnapshot`.
- Entry Worker persists live rules before `issue_ready_signal`.

- [x] **Step 1: Write failing tests**

```python
async def test_entry_worker_refreshes_live_instrument_rules_before_ticket() -> None:
    source = FakeActionFactsAndRulesSource()
    result = await run_entry_worker_once(factory, venue, source, request)
    assert result.status is EntryWorkerStatus.DISPATCHED
    assert state.persisted_rule.exchange_instrument_id == signal.exchange_instrument_id

async def test_disabling_new_entry_does_not_block_prepared_initial_stop() -> None:
    await disable_acceptance_policy(engine)
    result = await run_lifecycle_worker_once(factory, venue, facts, request)
    assert result.status is LifecycleWorkerStatus.DISPATCHED
```

- [x] **Step 2: Verify RED**

Run: `pytest -q tests/trading_kernel/integration/test_runtime_fact_workers.py -k 'instrument_rules or disabling_new_entry'`

Expected: FAIL because the rule-source protocol and persistence path do not exist.

- [x] **Step 3: Implement the minimal rule path**

```python
class InstrumentRulesSource(Protocol):
    async def read_instrument_rules(
        self,
        request: InstrumentRulesRequest,
    ) -> CapacityInstrumentRules: ...
```

`run_entry_worker_once` must gather action facts and rules outside a database
transaction, persist the exact rule projection in a short transaction, then
call `issue_ready_signal`. Owner Policy gates only new Ticket issuance;
lifecycle command dispatch remains available for an already accepted Ticket.

- [x] **Step 4: Verify GREEN**

Run: `pytest -q tests/trading_kernel/integration/test_runtime_fact_workers.py tests/trading_kernel/unit/test_venue_adapter.py`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/trading_kernel scripts/trading_kernel tests/trading_kernel
git commit -m "feat(kernel): refresh action-time instrument rules"
```

### Task 2: Production Binance Runtime Factories

**Files:**
- Create: `src/trading_kernel/infrastructure/production_runtime.py`
- Modify: `src/trading_kernel/infrastructure/venue_adapter.py`
- Modify: `src/trading_kernel/infrastructure/binance_public_market_source.py`
- Modify: `scripts/trading_kernel/run_command_worker_once.py`
- Modify: `scripts/trading_kernel/run_observation_worker_once.py`
- Modify: `scripts/trading_kernel/run_reconciliation_worker_once.py`
- Create: `scripts/trading_kernel/probe_production_runtime.py`
- Test: `tests/trading_kernel/unit/test_production_runtime.py`

**Interfaces:**
- Produces: `build_binance_usdm_market_source() -> CcxtBinancePublicMarketSource`.
- Produces: `build_binance_usdm_venue_adapter() -> CcxtVenueAdapter`.
- Consumes exact environment identities and canonical Registry instruments.

- [ ] **Step 1: Write failing factory tests**

```python
def test_factory_requires_exact_live_identity(monkeypatch) -> None:
    monkeypatch.setenv("TRADING_KERNEL_VENUE_ID", "wrong")
    with pytest.raises(ValueError, match="venue identity"):
        build_binance_usdm_venue_adapter()

@pytest.mark.asyncio
async def test_worker_closes_factory_resource(fake_factory) -> None:
    await command_cli_run(fake_args)
    assert fake_factory.adapter.closed is True
```

- [ ] **Step 2: Verify RED**

Run: `pytest -q tests/trading_kernel/unit/test_production_runtime.py`

Expected: FAIL because the production module does not exist.

- [ ] **Step 3: Implement exact environment construction**

```python
def build_binance_usdm_venue_adapter() -> CcxtVenueAdapter:
    settings = ProductionRuntimeSettings.from_environment()
    exchange = ccxt_async.binanceusdm({
        "apiKey": settings.api_key.get_secret_value(),
        "secret": settings.api_secret.get_secret_value(),
        "enableRateLimit": True,
        "options": {"defaultType": "future", "adjustForTimeDifference": True},
    })
    return CcxtVenueAdapter(...)
```

Worker CLIs must call a generic async `close()` in `finally`. Probe stdout may
contain only identities, counts, mode, and rule values.

- [ ] **Step 4: Verify GREEN**

Run: `pytest -q tests/trading_kernel/unit/test_production_runtime.py tests/trading_kernel/unit/test_binance_public_market_source.py tests/trading_kernel/unit/test_venue_adapter.py`

Expected: PASS with no unclosed-client warning.

- [ ] **Step 5: Commit**

```bash
git add src/trading_kernel/infrastructure scripts/trading_kernel tests/trading_kernel/unit
git commit -m "feat(kernel): add production Binance runtime factories"
```

### Task 3: Exact Runtime Authority Seed

**Files:**
- Create: `src/trading_kernel/infrastructure/runtime_authority_seed.py`
- Create: `scripts/trading_kernel/seed_runtime_authority.py`
- Test: `tests/trading_kernel/integration/test_runtime_authority_seed.py`
- Modify: `tests/trading_kernel/integration/test_schema_baseline.py`

**Interfaces:**
- Produces: `seed_runtime_authority(uow, request) -> RuntimeAuthoritySeedResult`.
- Produces: acceptance and full-policy transitions with monotonically increasing policy versions.

- [ ] **Step 1: Write failing exact-seed test**

```python
async def test_seed_creates_exact_acceptance_authority(engine) -> None:
    result = await seed_runtime_authority(uow, request)
    assert result.runtime_scope_count == 22
    assert result.real_submit_enabled is False
    assert result.max_concurrent_tickets == 1
    assert result.max_gross_notional == Decimal("20")
    assert result.target_leverage == Decimal("2")
```

- [ ] **Step 2: Verify RED**

Run: `pytest -q tests/trading_kernel/integration/test_runtime_authority_seed.py`

Expected: FAIL because the seed module does not exist.

- [ ] **Step 3: Implement idempotent seed and policy promotion**

Seed exactly one runtime profile, one policy, 22 runtime scopes, the global
lane, zero account exposure, `strategy_signal_ingest=true`,
`exchange_commands=false`, and exact schema metadata. `promote_full_policy`
requires a terminal reviewed acceptance Ticket and zero active exposure.

- [ ] **Step 4: Verify GREEN**

Run: `pytest -q tests/trading_kernel/integration/test_runtime_authority_seed.py tests/trading_kernel/integration/test_strategy_registry_seed.py`

Expected: PASS and second seed inserts or changes zero semantic rows.

- [ ] **Step 5: Commit**

```bash
git add src/trading_kernel/infrastructure/runtime_authority_seed.py scripts/trading_kernel/seed_runtime_authority.py tests/trading_kernel/integration
git commit -m "feat(kernel): seed exact Tokyo runtime authority"
```

### Task 4: Production Tokyo Cutover Adapter

**Files:**
- Create: `src/trading_kernel/infrastructure/tokyo_cutover_adapter.py`
- Modify: `scripts/trading_kernel/cutover_tokyo.py`
- Modify: `scripts/trading_kernel/verify_flat_cutover.py`
- Create: `deploy/docker/brc-trading-kernel-postgres.compose.yml`
- Test: `tests/trading_kernel/integration/test_production_cutover_adapter.py`

**Interfaces:**
- Produces: `build_tokyo_cutover_adapter() -> TokyoCutoverAdapter`.
- Implements: `inspect_preconditions`, `apply_phase`, `phase_satisfied`, and `close`.

- [ ] **Step 1: Write failing allowlist and refusal tests**

```python
def test_cutover_targets_only_exact_brc_allowlist(adapter) -> None:
    assert adapter.mutable_units == EXPECTED_OLD_BRC_UNITS | EXPECTED_NEW_BRC_UNITS
    assert "nginx.service" not in adapter.mutable_units
    assert "owner_ai_pg" not in adapter.mutable_containers

async def test_non_quant_baseline_drift_blocks_cleanup(adapter) -> None:
    adapter.system.non_quant_digest = "changed"
    facts = await adapter.inspect_preconditions(plan)
    assert facts.non_flat_positions == 0
    assert adapter.non_quant_baseline_matches() is False
```

- [ ] **Step 2: Verify RED**

Run: `pytest -q tests/trading_kernel/integration/test_production_cutover_adapter.py`

Expected: FAIL because no production adapter exists.

- [ ] **Step 3: Implement exact phases**

The adapter may mutate only:

```text
brc-owner-console-backend.service
brc-runtime-monitor.timer/service
brc-runtime-signal-watcher.timer/service
brc-ticket-lifecycle-maintenance.timer/service
brc-trading-kernel-*.timer/service
dingdingbot-pg
brc-trading-kernel-pg
/home/ubuntu/brc-deploy
/opt/brc
/etc/brc
```

`owner_ai_*`, nginx service state, Dingding Bot application state, and host
infrastructure are read-only baselines. The adapter creates the new DB container
before destructive phases, snapshots the old BRC DB, installs `0001_initial`,
seeds authority, switches the symlink, and leaves new ENTRY disabled.

- [ ] **Step 4: Verify GREEN**

Run: `pytest -q tests/trading_kernel/integration/test_production_cutover_adapter.py tests/trading_kernel/integration/test_cutover_state_machine.py`

Expected: PASS for every refusal, interruption, resume, and non-quant drift case.

- [ ] **Step 5: Commit**

```bash
git add src/trading_kernel/infrastructure/tokyo_cutover_adapter.py scripts/trading_kernel deploy/docker tests/trading_kernel/integration
git commit -m "ops(kernel): add production Tokyo cutover adapter"
```

### Task 5: Deployment Units And Readonly Certification

**Files:**
- Modify: `deploy/systemd/brc-trading-kernel-observation-worker.timer`
- Modify: `deploy/systemd/brc-trading-kernel-entry-worker.service`
- Modify: `deploy/systemd/brc-trading-kernel-reconciliation-worker.timer`
- Modify: `scripts/trading_kernel/certify_readonly.py`
- Test: `tests/trading_kernel/integration/test_cutover_state_machine.py`

**Interfaces:**
- Observation cadence: 5 seconds with bounded one-scope claims.
- Entry cadence: 2 seconds and explicit write-fence condition.
- Lifecycle cadence: 2 seconds.
- Reconciliation cadence: 5 seconds.

- [ ] **Step 1: Write failing unit and certification assertions**

```python
assert "OnUnitActiveSec=5s" in observation_timer
assert "ConditionPathExists=!/etc/brc/trading-kernel.write-fenced" in entry_service
assert "OnUnitActiveSec=5s" in reconciliation_timer
```

- [ ] **Step 2: Verify RED**

Run: `pytest -q tests/trading_kernel/integration/test_cutover_state_machine.py -k systemd`

- [ ] **Step 3: Implement units and certification output**

Readonly certification must report exact commit, revision, seed identity,
33-table allowlist, 22 scopes, capability states, active Tickets, commands,
positions, incidents, and Owner projection without printing secrets.

- [ ] **Step 4: Verify GREEN and static checks**

Run:

```bash
pytest -q tests/trading_kernel/integration/test_cutover_state_machine.py
uvx ruff check src/trading_kernel tests/trading_kernel scripts/trading_kernel migrations/trading_kernel
uv run --with-requirements requirements-dev.txt mypy src/trading_kernel scripts/trading_kernel
```

- [ ] **Step 5: Commit**

```bash
git add deploy/systemd scripts/trading_kernel/certify_readonly.py tests/trading_kernel/integration/test_cutover_state_machine.py
git commit -m "ops(kernel): harden production worker staging"
```

### Task 6: Tokyo Apply, Acceptance Ticket, Cleanup, And Hourly Automation

**Files:**
- Modify after evidence: `docs/current/MAIN_CONTROL_ROADMAP.md`
- Modify after evidence: `docs/current/P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN.md`

**Interfaces:**
- Consumes exact commit produced by Tasks 1-5.
- Produces direct Tokyo commit/schema/seed/service/Ticket/cleanup evidence.

- [ ] **Step 1: Run final local certification**

```bash
pytest -q tests/trading_kernel
python3 scripts/audit_production_runtime_file_io.py
git diff --check
```

Expected: all tests pass, runtime file readers/writers are zero, worktree clean.

- [ ] **Step 2: Upload exact release and run cutover plan**

Run `cutover_tokyo.py --plan` with the committed production adapter and exact
commit/seed identities. Expected: pass with exchange flat, old terminality, no
unknown outcome, and no new writer.

- [ ] **Step 3: Apply the cutover**

Run `cutover_tokyo.py --apply`. Expected: exact target DB, schema, seed,
release, and Observation capability; ENTRY remains fenced.

- [ ] **Step 4: Observe and arm one acceptance Ticket**

Wait for a fresh real signal. Atomically set acceptance policy
`real_submit_enabled=true`, remove only the new-ENTRY fence, and enable the
ENTRY timer. Do not inject a synthetic production signal.

- [ ] **Step 5: Prove terminal closure**

Require ENTRY, Initial Stop, TP1/runner or controlled EXIT, flat exchange,
zero residual orders, released budget, closed Incident, Settlement, Review
Economics, and Owner `completed`.

- [ ] **Step 6: Promote the prior approved full envelope**

Call the committed full-policy promotion only after Step 5. Verify two-Ticket
capacity and 40 USDT gross notional without creating a second order.

- [ ] **Step 7: Delete retired BRC assets**

Remove the exact old units, old DB container and volume, `/home/ubuntu/brc-deploy`,
old nginx BRC console site, all old BRC releases/reports/backups, and the
short-lived snapshot. Recheck the non-quant baseline digest.

- [ ] **Step 8: Create the hourly automation**

Use the product automation API with a one-hour cadence. It reads Tokyo Worker,
commit/schema/seed, PG, candidate, Ticket, command, position, incident, order,
resource, and non-quant baseline facts. Engineering blockers keep new ENTRY
fail-closed and authorize local fix, certification, commit, and redeployment.

- [ ] **Step 9: Update authority documents and commit**

```bash
git add docs/current
git commit -m "docs(kernel): record Tokyo production acceptance"
```

## Plan Self-Review

- **Spec coverage:** Runtime factories, rule freshness, acceptance/full policy,
  dedicated DB, committed cutover, exact deletion allowlist, non-quant baseline,
  real Ticket closure, and hourly repair automation each have one owning task.
- **Type consistency:** Factory, rule source, seed, and cutover adapter names are
  defined before later tasks consume them.
- **Authority consistency:** Only new Ticket issuance is fenced; protection and
  controlled exit remain available for accepted exposure.
- **No compatibility:** No old runtime import, old table reader in cadence,
  dual write, or fallback service is introduced.
