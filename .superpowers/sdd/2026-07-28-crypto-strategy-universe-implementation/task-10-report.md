# Task 10 Report — Atomic StrategyUniverse Activation

## Scope

Implemented only Task 10 from
`docs/superpowers/plans/2026-07-28-crypto-strategy-universe-implementation.md`.

- Added one typed, database-only activation application boundary.
- Added one PostgreSQL transaction that validates the exact locked readiness
  snapshot and switches version, scope, and current-pointer authority.
- Added fail-closed, rollback, concurrency, idempotency, and side-effect
  integration evidence against disposable PostgreSQL.
- Preserved the Entry lane boundary: activation never reads or mutates Signal,
  Readiness, CapacityClaim, Ticket, Exchange Command, Trade Event, Aggregate,
  or Entry-lane state.
- Existing accepted Tickets retain their lifecycle authority; only new
  observation and new-entry scope authority moves to the newly active
  Universe.
- No Tokyo, production database, systemd, deployment, exchange read, or
  exchange write action was performed.

## Typed Decision Boundary

`UniverseActivationReadiness` is frozen and extra-forbid. The PostgreSQL
adapter converts one exact locked snapshot into this model; the pure
`activation_readiness_blocker` function owns stable blocker precedence.

| Locked fact | Fail-closed result | Mutation |
| --- | --- | --- |
| Target is not warming | `UNIVERSE_NOT_WARMING` | None |
| Current identity is incomplete | `CURRENT_UNIVERSE_IDENTITY_CONFLICT` | None |
| Event authority is inactive or unsupported | `EVENT_AUTHORITY_CONFLICT` | None |
| Member or warming-scope identity is incomplete | Exact identity blocker | None |
| Certification is missing, ineligible, or stale | Exact certification blocker | None |
| Warm readiness is missing or stale | Exact warm-readiness blocker | None |
| MPG/MI exact projection is absent or incomplete | `COMPARATIVE_PROJECTION_INCOMPLETE` | None |

The adapter uses bounded current-state reads. It requires exact member/scope
cardinality, active instruments, eligible action-time certification, matching
runtime profile and instrument identities, configured leverage 5, cross
margin, independent position sides, and unexpired warm readiness. MPG/MI also
requires one exact ready projection for the same Event, Universe, member-set
digest, and common warm closed bar.

## Atomic PostgreSQL Switch

One Unit of Work performs this sequence:

1. Lock the target Universe version.
2. Lock the Event current pointer and validate the complete current version and
   active scopes.
3. Lock and validate Event authority, target scopes, instruments,
   certifications, and the exact comparative projection when required.
4. Return `not_ready` without mutation when the pure readiness gate reports a
   blocker.
5. Retire old scopes, clear their leases and next due times, disable only new
   observation/new-entry authority, and advance scope/observation generations.
6. Activate new scopes, clear stale leases, and schedule the first observation
   strictly at the next closed Event bar.
7. Retire the old version, activate the new version, and CAS the current
   pointer to exactly one new activation generation.

Every step is in the same PostgreSQL transaction. A repeated call against the
exact active target returns `already_active` with the existing generation and
does not rewrite state only after the active version, scopes, five frozen
authority bindings, certifications, warm readiness, and exact comparative
projection have all been revalidated.

## Review Repair

The first Task 10 review found three closure gaps. The follow-up repair added
real PostgreSQL RED cases before changing production behavior.

### Exact Scope Authority

Both Warming activation and already-active revalidation now bind every exact
Scope to:

```text
strategy_group_id
+ strategy_version_id
+ runtime_profile_id
+ owner_policy_id
+ position_side
```

Registry group/version/Event rows, active Runtime Profile, enabled Owner
Policy, Policy scope, Universe identity, member identity, lifecycle
permissions, and those five Scope fields must agree. A wrong field returns the
scope/current identity blocker and leaves the old snapshot unchanged.

The initial five-variant RED showed four corrupted bindings activating and the
wrong Runtime Profile falling through to `CERTIFICATION_MISSING`. After the
repair, all five fail at the Scope identity boundary.

### Existing Worker Continuation

No fifth Worker was added.

- Reconciliation still prioritizes safety work, claims at most one
  certification target, closes the claim transaction, performs readonly venue
  I/O, persists certification/Monitor in a short transaction, and then opens a
  separate short DB-only activation Unit of Work.
- Observation still claims one Scope, closes the claim transaction, performs
  market I/O, persists warm facts, commits claim scheduling in its own short
  Unit of Work, and only then opens a separate DB-only activation Unit of Work.
- Expected `not_ready` results commit the newly persisted prerequisite and
  wait for the remaining prerequisite.
- Activation exceptions are not swallowed. Only the activation transaction
  rolls back; committed warm readiness and claim scheduling remain retryable,
  while the old Active Universe remains authoritative.

Two integration RED cases proved that `certification -> warming` and
`warming -> certification` both stopped without a current pointer. Both orders
now activate automatically when the final exact prerequisite becomes current;
the incomplete first step remains Warming with zero current pointer.

### Already-active Fail-closed Revalidation

The original fast path returned `already_active` immediately from pointer
identity. PostgreSQL RED cases then deleted an active Scope, changed its Owner
Policy binding, and deleted an MPG comparative projection; all three were
incorrectly accepted.

The fast path now executes the same bounded authority/readiness validation as a
new activation. Damage returns `not_ready`, does not advance the generation,
and does not mutate the corrupted snapshot.

### Deterministic Deadlock Repair

The second review identified a deterministic lock-order inversion:

```text
Observation scheduling transaction:
Scope row lock -> activation advisory lock

Concurrent DB-only activation:
activation advisory lock -> Scope row lock
```

A disposable PostgreSQL concurrency RED paused Observation immediately before
its activation call, let a concurrent activation acquire the advisory lock,
and then released Observation. PostgreSQL reported
`DeadlockDetectedError`: the Observation backend waited for the advisory lock
while the activation backend waited for the Observation transaction.

Observation now commits warm persistence and claim scheduling before opening
the activation Unit of Work. Every activation caller therefore starts at the
same global advisory lock and only then reaches version/current/Scope locks.
The concurrency regression proves:

- both attempts finish without deadlock;
- exactly one current pointer and activation generation are committed;
- all Scopes converge to complete active authority;
- Signal, Ticket, and Exchange Command counts remain zero.

A second PostgreSQL regression injects an activation trigger failure after the
final warm success. It proves warm readiness, released lease, and next
observation due time were already committed, the Universe remains wholly
Warming with no current pointer, and the next Reconciliation cadence activates
generation 1 after the injected fault is removed.

## RED And GREEN Evidence

The TDD sequence first established failures for the missing application
boundary and repository activation method. Subsequent RED cases demonstrated
that a partial implementation incorrectly activated from absent readiness,
absent comparative projection, and incomplete current authority. The
implementation was expanded only to satisfy those fail-closed cases.

| Evidence group | PostgreSQL behavior proved | Final result |
| --- | --- | ---: |
| Typed readiness and application boundary | Stable blocker precedence and extra-forbid inputs | 12 passed |
| Success and readiness blockers | Atomic switch; missing/ineligible/stale certification; missing/stale warm facts | 7 passed |
| Comparative and current identity | Exact projection required; incomplete old authority remains active | 2 passed |
| Concurrency and idempotency | Two workers produce one generation; retry returns already-active | 1 passed |
| Side-effect boundary | No chain or Entry-lane table is referenced by activation SQL | 1 passed |
| Fault injection | Failure at old scopes, new scopes, or pointer rolls back the exact snapshot | 3 passed |

The three fault cases install real PostgreSQL triggers that raise during
different activation stages. After each exception, the current pointer,
versions, scopes, generations, leases, scheduling fields, and execution-chain
row counts exactly equal the pre-attempt snapshot.

## Verification

Task 10 focused verification:

```text
61 passed in 40.57s
```

Initial Universe regression verification covering repository install, warming,
certification, comparative projection, market-call bounds, and Signal
eligibility:

```text
43 passed in 37.48s
```

Review-repair proportional verification covering activation, certification,
Monitor, warming, Observation-to-Signal, comparative projection, market-call
bounds, Signal eligibility, and Reconciliation fairness/Review:

```text
102 passed in 70.06s
```

P2 deadlock-repair proportional verification, including deterministic
PostgreSQL lock contention and next-cadence fault recovery:

```text
104 passed in 70.08s
```

Static gates:

```text
Ruff: all new Task 10 files passed
Ruff: changed adapter and port passed after excluding unrelated pre-existing
      UP035/UP037/TRY004/FLY002 findings
Ruff review repair: changed files passed after excluding only unrelated
                    pre-existing UP037/BLE001/TRY004/FLY002 findings
Mypy review repair: success, no issues found in 4 source files
git diff --check: exit 0
```

No broad full suite or production-adjacent operation was run.
