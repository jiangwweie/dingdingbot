# Task 7 Report — Readonly Instrument Certification And PostgreSQL Monitor

## Scope

Implemented only **Task 7** from
`docs/superpowers/plans/2026-07-28-crypto-strategy-universe-implementation.md`.

- Reused the existing persistent Reconciliation worker after Ticket safety,
  unknown-outcome, Settlement, and Review work.
- Added one bounded PostgreSQL certification claim per cadence.
- Added authenticated readonly Binance USD-M product/account fact collection.
- Added pure certification classification orchestration and short-transaction
  persistence of product rules, certification current, instrument eligibility,
  and Monitor state changes.
- Did not add a fifth worker, activation, warming progression, Ticket creation,
  Exchange Command creation, exchange setting mutation, BNB purchase/transfer,
  Tokyo access, production database access, systemd changes, or deployment.

## Invariants Preserved

- Reconciliation safety work has strict precedence over certification.
- Claim and persistence use short PostgreSQL transactions; authenticated Venue
  I/O runs after the claim and ownership-read transactions are closed.
- Every cadence claims at most one due target using `FOR UPDATE SKIP LOCKED`.
- Lease owner plus exact lease expiry is the persistence token; a crash before
  persistence is recoverable after lease expiry, and stale persistence is
  rejected.
- Only `eligible` marks the canonical instrument `active`; owner-action and
  transient results restore `pending_certification`, preserving the Task 6
  Entry gate.
- Existing BRC-owned position domains subtract only the exact Kernel-projected
  quantity; any Venue excess remains unowned exposure, while a projection above
  Venue truth is a fail-closed contradiction. Exact owned exchange order IDs do
  not count as unowned orders.
- Account conditions needing human action project
  `OWNER_ACTION_REQUIRED` / `NEEDS_INTERVENTION`.
- Only explicit timeout, connection, and Venue-network failures schedule bounded
  retry and create no Owner intervention Monitor. Validation, identity, schema,
  and ownership contradictions fail closed without a transient-state write.
- Repeated identical blockers do not append duplicate Monitor events; blocker
  change and resolution each append exactly one state-change event.
- Certification leaves the Universe `warming`; activation remains outside
  Task 7.

## RED / GREEN Evidence

### Unit use case RED

```text
uv run pytest -q \
  tests/trading_kernel/unit/test_certify_universe_instrument.py
```

Initial result:

```text
ModuleNotFoundError:
No module named 'src.trading_kernel.application.certify_universe_instrument'
```

The first minimal implementation then exposed three behavior failures as valid
snapshots were classified transient. The fixture lacked the required
maintenance-bracket identity. After correcting the complete typed fixture and
implementing the use case, the file returned **5 passed**.

An additional RED proved account blockers with valid product rules were not
persisting those rules:

```text
1 failed, 3 deselected
assert len(state.rules) == 1
E assert 0 == 1
```

The minimal GREEN persists valid rules for both eligible and deterministic
account-blocker snapshots while keeping the instrument pending.

### PostgreSQL worker RED

After correcting the disposable fixture to use
`migrations/trading_kernel/alembic.ini`, migration, seed, and Universe install
succeeded. All three worker/Monitor cases then failed on the missing
Reconciliation request fields:

```text
certification_lease_ms: Extra inputs are not permitted
certification_valid_for_ms: Extra inputs are not permitted
certification_eligible_check_interval_ms: Extra inputs are not permitted
certification_owner_action_check_interval_ms: Extra inputs are not permitted
certification_transient_retry_interval_ms: Extra inputs are not permitted
```

This was the expected missing worker/repository integration.

## Implementation

- `application/certify_universe_instrument.py`
  - typed readonly request/snapshot/source models;
  - ownership read in a closed short transaction;
  - timeout-bounded external snapshot;
  - pure classifier invocation;
  - bounded eligible, Owner-action, and transient next-check intervals;
  - atomic short-UoW rules/certification/Monitor persistence.
- `infrastructure/pg_universe_repository.py`
  - bounded current/warming selector;
  - exact one-target claim and crash-recoverable lease;
  - stale-token guarded persistence;
  - certification-derived instrument status.
- `infrastructure/venue_adapter.py`
  - readonly market status, product rules, leverage brackets, hedge mode,
    exact Cross/leverage/position facts, and regular/conditional open orders;
  - exact BRC ownership subtraction;
  - no exchange mutation call.
- `interfaces/reconciliation_worker.py`
  - certification runs only after the core returns `NO_WORK`;
  - one claimed target and one result per cadence;
  - no activation call.
- `project_owner_state.py` and existing PostgreSQL Monitor repository
  - stable certification Monitor key;
  - intervention, blocker-change, duplicate suppression, and resolution.

## Final Verification

### Unit/classifier/use-case/adapter/safety

```text
uv run pytest -q \
  tests/trading_kernel/unit/test_instrument_certification.py \
  tests/trading_kernel/unit/test_certify_universe_instrument.py \
  tests/trading_kernel/unit/test_venue_adapter.py \
  -k 'instrument_certification or certification_is_readonly or \
  certification_reads_venue or owner_action or transient_read_failure or \
  eligible_recheck or ticket_safety'
```

Result: **15 passed, 35 deselected**.

### Disposable PostgreSQL worker/lease/Monitor

```text
uv run pytest -q \
  tests/trading_kernel/integration/test_universe_certification_worker.py \
  tests/trading_kernel/integration/test_universe_monitor.py
```

Result: **4 passed**.

The tests prove:

- one of two due members is processed per cadence;
- no PostgreSQL connection is `idle in transaction` during the fake
  authenticated readonly Venue call;
- timeout releases the lease and writes a 30-second retry;
- two crashed claims exclude all work until expiry and are reclaimable at
  expiry;
- Monitor event counts for first blocker, duplicate, changed blocker, and
  resolution are `1 -> 1 -> 2 -> 3`;
- no leverage, margin-mode, or position-mode mutation method is invoked;
- the Universe remains `warming`.

### Existing focused regressions

```text
uv run pytest -q \
  tests/trading_kernel/unit/test_reconciliation_worker_fairness.py
```

Result: **5 passed**.

```text
uv run pytest -q \
  tests/trading_kernel/integration/test_strategy_universe_repository.py \
  -k 'install_inserts_one_complete_warming_universe_and_reads_sorted'
```

Result: **1 passed, 12 deselected**.

### Ruff and diff

```text
uvx ruff check --select E4,E7,E9,F <Task-7 touched files>
```

Result: **All checks passed**.

`git diff --check` also passed.

## Review Fix Round 1/5

### Findings closed

1. **Exact projected BRC quantity**
   - `AdmissionOwnership` now requires one finite, nonnegative projected
     quantity for every owned Netting Domain.
   - PostgreSQL reads each active Ticket's canonical aggregate `position_qty`.
   - Certification subtracts only that projection per side. Venue `0.01`
     against Kernel `0.001` classifies the `0.009` excess as
     `unowned_position`.
   - Kernel projection above Venue quantity, missing projection, or mismatched
     projection identity fails closed as a snapshot contradiction.

2. **Deterministic rules and narrow retry**
   - The raw certification snapshot can retain missing or invalid order-rule
     fields as `None`; the pure classifier returns
     `owner_action_required/missing_order_rule`.
   - Complete positive rules are the only path that constructs and persists
     typed `InstrumentRulesFacts`.
   - The use case catches only `TimeoutError`, `ConnectionError`, and the
     explicit `InstrumentCertificationTransientFailure`.
   - The adapter maps CCXT `NetworkError` to that explicit transient type.
     Pydantic unknown fields, wrong snapshot identity, and other contradictions
     propagate without writing a transient certification.
   - Test fixtures use full model validation rather than `model_copy` to create
     invalid pseudo-facts.

### Review RED evidence

```text
3 failed:
- missing_order_rule was temporarily_unavailable
- unknown Pydantic field did not raise
- snapshot identity mismatch did not raise
```

The real adapter missing-`MIN_NOTIONAL` case also failed with:

```text
RuntimeError: venue minimum notional is missing or non-positive
```

### Review GREEN evidence

| Focused boundary | Result |
|---|---:|
| Pure classifier and certification use case | **17 passed** |
| Adapter exact/excess/contradiction/missing/invalid/network paths | **6 passed** |
| Ownership model projection invariant | **1 passed** |
| Entry-health ownership regression | **4 passed** |
| PostgreSQL ownership quantity projection | **1 passed** |
| PostgreSQL Task 7 worker/lease/Monitor | **4 passed** |
| Reconciliation fairness | **5 passed** |
| Ruff `E4,E7,E9,F` | **All checks passed** |

All checks were scoped to Task 7 and its directly affected ownership boundary;
no broad suite, Tokyo access, production mutation, activation, or exchange
write was performed.

## Remaining Boundary

Task 7 deliberately stops after updating readonly certification, canonical
instrument eligibility, product rules, retry/lease state, and Monitor. It does
not call `try_activate_universe()`, mark warm readiness, switch current
Universe pointers, enable Entry, mutate exchange settings, or perform any
Tokyo/production operation.
