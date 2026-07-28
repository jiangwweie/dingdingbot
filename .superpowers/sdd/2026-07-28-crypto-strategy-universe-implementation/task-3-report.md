# Task 3 implementation report

## Scope

- Local/disposable PostgreSQL only.
- No Tokyo, systemd, production database, exchange, or network write.
- Forward-only `0001 -> 0002`; no compatibility reader, alias, view, dual-write,
  nullable lineage, or downgrade path.

## RED

Command:

```bash
python3 -m pytest -q \
  tests/trading_kernel/integration/test_schema_baseline.py \
  tests/trading_kernel/integration/test_schema_migration_postgres.py \
  tests/trading_kernel/integration/test_strategy_universe_schema.py
```

Actual result:

```text
collected 21 items
7 failed, 14 passed in 3.52s
exit code 1
```

Expected missing-behavior failures observed:

- five StrategyUniverse PostgreSQL tables were absent;
- `brc_strategy_candidate_scopes` was still present;
- Signal, CapacityClaim, and Ticket Universe lineage columns were absent;
- non-flat `0001 -> head` incorrectly returned success;
- real PostgreSQL raised `UndefinedTableError` for
  `brc_strategy_universe_versions`.

Production migration and SQLAlchemy metadata had not been modified before this
RED run.

## GREEN

Implemented:

- forward-only `0002_crypto_strategy_universe`;
- five canonical PostgreSQL authority tables;
- removal of `brc_strategy_candidate_scopes`;
- explicit Warming/Active/Retired runtime-scope permissions and warm lineage;
- non-null Universe lineage on Signal, CapacityClaim, and Ticket;
- event/version, current digest, global warming, member, current pointer, FK,
  lifecycle, readiness, and bounded operational index constraints;
- concurrency-serialized PostgreSQL trigger enforcing at most ten members;
- DDL-first precondition rejection when any pre-existing runtime/trade authority
  table contains rows;
- deliberate rejection of downgrade from `0002`.

Final targeted command:

```bash
python3 -m pytest -q \
  tests/trading_kernel/integration/test_schema_baseline.py \
  tests/trading_kernel/integration/test_schema_migration_postgres.py \
  tests/trading_kernel/integration/test_strategy_universe_schema.py
```

Actual result:

```text
collected 21 items
21 passed in 4.32s
exit code 0
```

The run used real disposable PostgreSQL databases against the local healthy
`dingdingbot-pg` container. Each test-created database was dropped in cleanup.

Focused Ruff command:

```bash
/Users/jiangwei/.local/bin/uv run --with 'ruff>=0.15.0' ruff check \
  --select E4,E7,E9,F \
  migrations/trading_kernel/versions/0002_crypto_strategy_universe.py \
  src/trading_kernel/infrastructure/pg_models.py \
  tests/trading_kernel/integration/test_schema_baseline.py \
  tests/trading_kernel/integration/test_schema_migration_postgres.py \
  tests/trading_kernel/integration/test_strategy_universe_schema.py
```

Actual result:

```text
All checks passed!
exit code 0
```

The first attempted `python3 -m ruff ...` could not run because the active
Python environment did not contain the Ruff module:

```text
/opt/homebrew/opt/python@3.14/bin/python3.14: No module named ruff
```

It was replaced by the repository-appropriate `uv run` invocation above.

Diff command:

```bash
git diff --check
```

Actual result: no output, exit code 0.

## Self-review

### Schema constraints

- Event/version and current-or-warming event/digest identities are unique.
- The partial unique warming index permits at most one global Warming Universe.
- Member identity is a composite primary key and references both Universe and
  instrument identity.
- A parent-row lock serializes member inserts before enforcing the ten-member
  limit, preventing concurrent inserts from bypassing cardinality.
- Current pointer event identity is a primary key.
- Runtime-scope lifecycle permission combinations and warm-readiness shape are
  check constrained.
- Signal, Claim, and Ticket Universe lineage is non-null and digest validated.

### Migration atomicity

- The first upgrade action is the populated-runtime/trade precondition.
- PostgreSQL transactional DDL plus the executable non-flat test proves failure
  leaves the five new tables absent and the old scope columns unchanged.
- Empty disposable `0001 -> 0002` succeeds.
- Downgrade raises a forward-only error and leaves `0002` intact.

### Test behavior

- Constraint tests execute real inserts and observe PostgreSQL unique, FK, and
  check violations.
- Metadata and PostgreSQL information-schema/index inspection independently
  verify the declared and migrated shapes.
- Valid pending-certification instruments and Warming/Active/Retired permission
  rows are accepted.

### No compatibility paths

- No candidate-scope table, view, alias, reader, dual-write, schema fallback, or
  nullable lineage path was added.
- No U.S.-equity identifier, seed, runtime profile, or product behavior was
  added.

## Deliberately deferred fallout

Tasks 4, 5, 8, and 11 must update Registry/seed/repository/application code
that still refers to `brc_strategy_candidate_scopes`,
`runtime_scopes_current.enabled`, old observation lease names, or pre-Universe
Signal/Claim/Ticket constructors. This task intentionally does not add
compatibility glue to keep those old paths operational.

## Fix round 1

### Reviewer findings addressed

- Universe current, scope, Signal, Claim, and Ticket identity/lifecycle
  relationships were bypassable.
- The flat migration preflight did not lock guarded tables.
- Member cardinality could be bypassed by updating `universe_version_id`.
- Crypto-only membership was not enforced by PostgreSQL.

### RED

Command:

```bash
python3 -m pytest -q \
  tests/trading_kernel/integration/test_schema_migration_postgres.py \
  tests/trading_kernel/integration/test_strategy_universe_schema.py
```

Initial result:

```text
collected 6 items
3 failed, 3 passed in 6.70s
exit code 1
```

Observed missing behavior:

- a concurrent `brc_entry_lane_current` insert completed after the migration
  emptiness check and before DDL;
- a non-USDT member was accepted;
- an Active scope referencing a Warming Universe was accepted.

After making all identity attempts independently observable, the focused
authority RED also recorded false rejection results for:

```text
member_update
warming_current
wrong_current_event
wrong_current_digest
wrong_signal_digest
active_scope_on_warming
retired_scope_on_warming
```

These were real PostgreSQL writes executed inside rolled-back test
transactions, not mock or source-text assertions.

### GREEN implementation

- Added version candidate keys for
  `(universe_version_id, event_spec_id, semantic_digest)` and the corresponding
  lifecycle tuple.
- Current pointer now carries a fixed `active` lifecycle identity and references
  the exact Active version through a deferred composite FK.
- Runtime scope now freezes `universe_semantic_digest` and references the exact
  version/event/digest/lifecycle tuple through a deferred composite FK.
- Signal, CapacityClaim, and Ticket reference exact version/event/digest
  identity through composite FKs.
- The preflight deterministically obtains `ACCESS EXCLUSIVE` locks on every
  guarded runtime/trade table before checking emptiness and holds them through
  the migration transaction.
- Universe members are immutable; UPDATE and DELETE are rejected.
- Member INSERT validates canonical Binance USD-M crypto USDT perpetual
  identity. Instrument identity columns are immutable while status remains
  mutable.
- The existing parent-version row lock continues to serialize parallel member
  inserts; the two-connection 10th/11th-member test proves the 11th is rejected
  after the 10th commits.

### Final PostgreSQL verification

Command:

```bash
python3 -m pytest -q \
  tests/trading_kernel/integration/test_schema_baseline.py \
  tests/trading_kernel/integration/test_schema_migration_postgres.py \
  tests/trading_kernel/integration/test_strategy_universe_schema.py
```

Actual result:

```text
collected 23 items
23 passed in 6.72s
exit code 0
```

Coverage includes:

- wrong Event, digest, lifecycle, and non-Active current pointer rejection;
- wrong scope digest and scope/version lifecycle rejection;
- wrong Signal digest plus Claim/Ticket composite FK schema inspection;
- non-Binance venue, non-crypto asset class, non-USDT quote, and non-perpetual
  membership rejection;
- instrument identity drift rejection;
- member UPDATE bypass rejection;
- two-connection parallel member cardinality enforcement;
- actual Alembic migration paused after preflight while a concurrent runtime
  insert is proven blocked;
- empty upgrade, non-flat atomic rejection, and forward-only downgrade refusal.

### Static verification

Focused Ruff:

```bash
/Users/jiangwei/.local/bin/uv run --with 'ruff>=0.15.0' ruff check \
  --select E4,E7,E9,F \
  migrations/trading_kernel/versions/0002_crypto_strategy_universe.py \
  src/trading_kernel/infrastructure/pg_models.py \
  tests/trading_kernel/integration/test_schema_baseline.py \
  tests/trading_kernel/integration/test_schema_migration_postgres.py \
  tests/trading_kernel/integration/test_strategy_universe_schema.py
```

Result:

```text
All checks passed!
exit code 0
```

`git diff --check` produced no output and exited 0.

### Fix-round self-review

- Composite lifecycle FKs are `DEFERRABLE INITIALLY DEFERRED`, allowing one
  atomic activation transaction to update version, scopes, and pointer without
  permitting an invalid committed state.
- Current pointers cannot reference Warming or Retired versions.
- Retired Tickets remain traceable because trade lineage excludes mutable
  lifecycle state while retaining exact version/event/digest identity.
- Runtime/trade preflight locks are acquired in sorted deterministic order
  before the first emptiness read.
- Member identity and instrument identity have no update compatibility path.
- No seed, repository, runtime worker, Tokyo, systemd, production database, or
  exchange behavior was added.
