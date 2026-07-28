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
does not rewrite state.

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
25 passed in 11.72s
```

Universe regression verification covering repository install, warming,
certification, comparative projection, market-call bounds, and Signal
eligibility:

```text
43 passed in 37.48s
```

Static gates:

```text
Ruff: all new Task 10 files passed
Ruff: changed adapter and port passed after excluding unrelated pre-existing
      UP035/UP037/TRY004/FLY002 findings
Mypy: success, no issues found in 3 source files
git diff --check: exit 0
```

No broad full suite or production-adjacent operation was run.
