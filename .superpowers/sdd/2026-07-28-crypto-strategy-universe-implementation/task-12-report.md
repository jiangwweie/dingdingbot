# Task 12 implementation report

## Status

Task 12 is implemented locally and is ready for independent review.

No Tokyo, production PostgreSQL, systemd, exchange, Universe production seed,
certification, warming cadence, activation, Signal, Ticket, or Entry action was
performed. All PostgreSQL evidence used disposable local databases.

The delivered boundary is:

- one configure CLI that accepts one exact Runtime Profile, one registered
  Event alias, and 1..10 unique uppercase USDT perpetual symbols;
- short symbols are normalized to canonical
  `binance-usdm:*USDT:perpetual` identities;
- PostgreSQL resolves the exact active Event and one enabled matching Owner
  Policy before the existing install use case installs a Warming Universe;
- the configure CLI never activates a Universe and creates no Signal, Claim,
  Ticket, or Exchange Command;
- one bounded readonly status CLI displays current/warming members,
  certification state, warm readiness, Monitor status/blocker, and exact
  current generation;
- terminal output is fixed text only and creates no JSON/Markdown or other
  files;
- status models cannot carry account identity, credentials, complete Venue
  payloads, rules payloads, or free-form Monitor summary/intervention text.

## TDD RED evidence

### Strict configure input

1. The initial missing-script RED was followed by the minimum argparse
   skeleton.
2. Command:
   `python3 -m pytest -q
   tests/trading_kernel/unit/test_configure_strategy_universe_script.py -x`
   - Result after the skeleton: **1 passed, 1 failed**.
   - Expected behavior failure: duplicate `BTCUSDT` reached database URL
     validation instead of returning `instruments must be unique`.
3. The completed input matrix proves:
   - zero members are rejected by required `--instrument`;
   - duplicate members are rejected, not silently deduplicated;
   - eleven members are rejected, not truncated;
   - non-USDT quote is rejected;
   - whitespace-drifted Runtime Profile/Event identity is rejected before
     database access and without traceback or DSN disclosure.

### Application use case and PostgreSQL install

1. The configure application test first failed because
   `configure_strategy_universe`, `UniverseConfigurationRequest`, and
   `UniverseInstallContext` did not exist.
2. PostgreSQL command:
   `python3 -m pytest -q
   tests/trading_kernel/integration/test_strategy_universe_scripts.py::test_configure_cli_installs_only_one_warming_universe
   -x`
   - RED result: the minimum script returned exit 0 with empty stdout and
     installed no Universe.
   - GREEN result: **1 passed**.
3. Unknown Event and Runtime Profile integration returned stable
   `EVENT_AUTHORITY_CONFLICT` and `RUNTIME_PROFILE_AUTHORITY_CONFLICT`, with
   zero Universe versions persisted.

### Readonly status and secret containment

1. The minimum status parser produced an empty stdout RED instead of the
   required bounded status.
2. After the first projection implementation, a corrupted Monitor
   `owner_status=credential=SECRET` produced a security RED: the CLI returned
   exit 0 and exposed the raw value.
3. GREEN uses a canonical typed Monitor display allowlist. Corrupted status
   returns only `error=operation_failed`; neither stdout nor stderr contains
   the corrupt value.
4. A non-exact status identity initially emitted a Pydantic traceback. The
   repaired CLI returns parser exit 2 with fixed text and no supplied DSN.

## Implementation

### Configure

- `UniverseConfigurationRequest` accepts canonical members only.
- `configure_strategy_universe` calls
  `resolve_install_context(runtime_profile_id, event_id)` and then the existing
  `install_strategy_universe` use case.
- `PostgresStrategyUniverseRepository.resolve_install_context` requires:
  - one active registered Event alias;
  - one active Binance USD-M Runtime Profile;
  - exactly one enabled Owner Policy whose typed scope allows the resolved
    canonical Event.
- The script contains no direct SQL, no file source, no report writer, and no
  activation call.

Successful terminal shape:

```text
status=installed
event_spec_id=event_spec:SOR-001:SOR-LONG:v2
universe_version_id=universe:<identity>:v1
semantic_digest=sha256:<digest>
lifecycle_state=warming
member_count=2
```

### Read status

The readonly query:

- first validates the exact active Runtime Profile and optional active Event;
- selects only active/warming Universe rows and their exact Profile scopes;
- uses one hard `70 + 1` row bound for six active ten-member Events plus one
  global ten-member Warming Universe;
- reads only certification status/blocker, warm readiness fields, canonical
  Monitor owner status, and current generation;
- never selects Runtime Profile account ID, certification raw facts,
  product-rule payload, Monitor summary/intervention, credential, or complete
  Venue payload.

## Verification evidence

### Task 12 focused

Command:

```text
python3 -m pytest -q
  tests/trading_kernel/unit/test_configure_strategy_universe_script.py
  tests/trading_kernel/integration/test_strategy_universe_scripts.py
```

Result: **12 passed in 10.56s**.

PostgreSQL assertions include:

- canonical sorted members;
- one Warming version and Warming permissions;
- zero current pointer after configure;
- zero Signal, Claim, Ticket, and Exchange Command;
- unknown Event/Profile atomic rejection;
- fixed terminal text;
- zero output files;
- readonly row counts unchanged before/after status;
- certification, warming, Monitor blocker, and active current generation 7;
- no account ID, DSN, credential, free-form Monitor summary, or complete Venue
  payload in output.

### Universe proportional regression

The 19-file unit/PostgreSQL group covering domain identity, install,
certification, warming, Monitor, comparative projection, activation,
activation failure rollback, market-call bounds, and Signal eligibility:

```text
131 passed in 80.00s
```

### Architecture and file authority

Command:

```text
python3 -m pytest -q tests/trading_kernel/architecture
```

Result: **28 passed in 0.94s**.

This includes the runtime file-I/O audit over
`src/trading_kernel` and `scripts/trading_kernel`.

Direct source checks over the two CLIs found no `execute`, SQL text, `open`,
file-write, JSON, YAML, or Markdown path.

### Static gates

- System `python3 -m ruff` was unavailable because Ruff is not installed in
  the default Python environment.
- Isolated command:
  `uvx --from 'ruff>=0.15.0' ruff check --select E4,E7,E9,F <Task 12 files>`
  - Result: **All checks passed**.
- Full source Mypy exposed the existing repository baseline of 35 errors in
  unrelated modules.
- Isolated changed-source command:
  `uv run --with-requirements requirements.txt --with 'mypy>=1.8.0' mypy
  --follow-imports=silent <four changed source files>`
  - Result: **Success: no issues found in 4 source files**.
- `python3 -m py_compile` for both CLIs and the new status application module:
  **passed**.
- `git diff --check`: **passed**.

## Full-chain baseline disclosure

The complete existing `tests/trading_kernel/full_chain` suite was run as
additional evidence:

```text
24 passed, 8 failed in 27.38s
```

These eight failures are outside the Task 12 execution path and were not
changed to manufacture a green total:

- six parametrized failures in
  `test_six_event_system_certification.py` are a tracked HEAD fixture drift;
  the test still inserts deleted `runtime_scopes_current.enabled` and fails
  with `CompileError: Unconsumed column names: enabled`;
- two failures in `test_multi_position_certification.py` are an existing
  dispatch-fixture expectation drift: ENTRY returns `SUPERSEDED` where the
  fixture expects `ACCEPTED`;
- neither failing file imports or invokes Strategy Universe configure/status
  code.

The Task 12 focused, Universe PostgreSQL, fault-recovery, architecture, and
static gates remain green. Repairing retired full-chain fixtures belongs to a
separate reviewed task.

## Stop boundary

Task 12 stops at local commit and independent review. It does not authorize
Tokyo deployment, production database mutation, Universe production
configuration, worker/systemd mutation, exchange readonly calls, or exchange
writes.
