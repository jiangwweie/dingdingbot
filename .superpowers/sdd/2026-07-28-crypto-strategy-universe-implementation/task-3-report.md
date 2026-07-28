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
