# Task 9 Report — Shared Comparative Universe Projection

## Scope

Implemented only Task 9 from
`docs/superpowers/plans/2026-07-28-crypto-strategy-universe-implementation.md`.

- MPG and MI now build one typed comparative projection for one exact
  Universe closed bar.
- Every candidate Observation consumes the same persisted projection.
- The existing MPG/MI detectors and the existing Signal producer remain the
  only detector and Signal paths.
- No activation, Entry, Ticket, Exchange Command, deployment, Tokyo, systemd,
  production database, or exchange behavior was added.

## Projection Contract

The exact projection key is:

```text
event_spec_id
+ universe_version_id
+ closed_bar_time_ms
+ canonical member_set_digest
```

`ComparativeUniverseProjection` is frozen and extra-forbid. It contains:

- the exact key identities;
- one canonical-sorted `ComparativeMemberWindow` per Universe member;
- one complete existing `ComparativeStrengthSnapshot`;
- exact observation/validity times;
- the current PostgreSQL projection version.

Construction rejects missing or duplicate members, incomplete windows,
different latest close times, internal 1h gaps, future candles, digest drift,
strength-member drift, and invalid validity windows. The final
`lookback_bars + 1` closes must be anchored exactly one hour apart through the
requested closed bar.

## PostgreSQL Semantics

`brc_comparative_projection_current` remains one current outcome row per
Event/Universe version. The row is explicitly either `ready` or `unavailable`;
an unavailable outcome has a typed failure reason and can never be consumed as
a comparative market projection.

- First persistence inserts projection version 1.
- A newer closed bar atomically replaces the current payload and increments
  projection version.
- The same closed bar is idempotent and does not increment the version.
- An incomplete or temporarily unavailable exact-key build persists one
  unavailable outcome with a bounded 30-second retry window.
- Related scopes reuse that unavailable outcome without repeating member
  market reads before the retry boundary.
- A successful same-close bounded retry atomically replaces the unavailable
  outcome and increments projection version.
- An unavailable writer cannot replace a same-close ready projection.
- An older closed bar cannot replace newer current state.
- A newer closed bar increments the current projection version; a later stale
  writer is rejected.
- Reads require exact Event, Universe version, close time, and member digest.
- Persisted JSON is revalidated through the typed model; malformed payloads
  fail closed.

The same-process keyed lock only coalesces duplicate projector work. It is not
authority: PostgreSQL exact-key validation and atomic upsert remain the
cross-attempt authority. The official Observation service still claims at most
one scope per cadence.

## Observation And Transaction Boundary

Observation first resolves the exact PostgreSQL Universe and attempts an exact
projection read inside its short authority transaction.

On a miss:

```text
close authority transaction
-> acquire exact in-process projection key
-> recheck PostgreSQL in a short transaction
-> close transaction
-> fetch every member once through PublicMarketSource
-> build one typed ComparativeStrengthSnapshot
-> atomically persist current projection
-> each scope consumes the persisted projection
```

MPG then reads only that candidate's 4h window. MI needs no additional market
read. Direct Events do not read or write comparative projection state.

## RED Evidence

The initial disposable PostgreSQL counting test installed eight MPG scopes and
observed every scope at the same closed bar:

```text
test_eight_mpg_scopes_read_each_member_once_per_closed_bar

expected:
each of 8 members read once

actual:
each of 8 members read 8 times
64 total 1h member reads
```

The failure was the existing per-scope comparative fetch path, not fixture,
database, or environment failure.

The typed unit test initially failed at collection because
`project_comparative_universe` did not exist. The PostgreSQL integration test
initially lacked comparative projection repository methods.

## GREEN And Performance Evidence

Focused performance cases prove:

| Case | Scope count | 1h reads | Additional reads | Projection rows |
| --- | ---: | ---: | ---: | ---: |
| MPG | 8 | 8 total, one/member | 8 total 4h, one/member | 1 |
| MI | 10 | 10 total, one/member | 0 | 1 |
| Concurrent MPG scopes | 2 | 8 total, one/member | one 4h/scope | 1 |

The concurrent case also asserts `projection_version = 1`, proving the second
scope consumed the first exact projection instead of committing another
same-close generation.

Failure cases prove:

- one missing member makes every attempted related scope invalid;
- one member with a different latest close makes every attempted related scope
  invalid;
- one internal gap in the final comparative lookback makes every related scope
  invalid;
- sequential eight-scope and concurrent two-scope failures read each member
  exactly once, persist one unavailable outcome, and create zero Signal and
  zero warm readiness;
- repeated attempts before the 30-second retry boundary perform zero additional
  member reads;
- a successful same-close attempt at the retry boundary replaces unavailable
  with ready and advances projection version from 1 to 2;
- a persisted member digest different from the exact Universe digest is not
  consumed and is not overwritten at the same close;
- all failure cases create zero Signal and zero warm-ready scope;
- direct SOR Observation creates zero comparative projection rows.

## Focused Verification

Command:

```text
pytest -q \
  tests/trading_kernel/unit/test_project_comparative_universe.py \
  tests/trading_kernel/integration/test_comparative_universe_projection.py \
  tests/trading_kernel/integration/test_universe_market_call_bounds.py \
  tests/trading_kernel/integration/test_universe_warming.py \
  tests/trading_kernel/integration/test_observation_to_signal.py \
  tests/trading_kernel/integration/test_strategy_universe_repository.py \
  tests/trading_kernel/integration/test_schema_baseline.py
```

Result:

```text
66 passed in 39.50s
```

Static gate:

```text
Ruff E4/E7/E9/F/I: all checks passed
Mypy focused 5 source files with follow-imports skipped: success, no issues found
git diff --check: exit 0
```

Per parent scope, no broad full-suite, Tokyo, production, systemd, deployment,
or exchange action was run.
