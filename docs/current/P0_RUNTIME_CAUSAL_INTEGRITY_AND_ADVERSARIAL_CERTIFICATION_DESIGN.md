---
title: P0_RUNTIME_CAUSAL_INTEGRITY_AND_ADVERSARIAL_CERTIFICATION_DESIGN
status: CURRENT
authority: docs/current/P0_RUNTIME_CAUSAL_INTEGRITY_AND_ADVERSARIAL_CERTIFICATION_DESIGN.md
last_verified: 2026-07-13
---

# P0 Runtime Causal Integrity And Adversarial Certification

## 1. Decision

**P0-RCI** certifies that one production identity remains causally conserved
across PostgreSQL transaction, process death, retry, concurrency, exchange
ambiguity, lifecycle recovery, and Owner projection boundaries.

It is a bounded certification program over the deployed execution chain. It is
not a second execution path, a generic chaos platform, a new runtime profile, or
a substitute for natural live lifecycle calibration.

```text
existing invariant designs
-> real PostgreSQL and independent-process adversarial proof
-> classify the first escaped invariant
-> repair inside the existing boundary when possible
-> preserve R1B natural live calibration as the venue-only proof
```

## 2. Objective Facts

| Fact | Current evidence | Consequence |
| --- | --- | --- |
| **Action-Time identity** | Migration `119` binds fresh signal, invocation, facts, promotion, lane, Ticket, watcher coverage, and process outcome to one typed identity | Certification must preserve exact invocation and source watermark, not only lane labels |
| **Durable command protocol** | Exchange-command worker commits claim before exchange I/O and commits result afterward | Crash windows exist between the two commits and must be tested with independent processes |
| **Existing safety behavior** | Unit tests cover unknown outcome, expired lease, concurrent workers, rollback, repeated cleanup, and parent/child blocker conservation | Existing behavior is the oracle; P0-RCI must not invent a parallel state model |
| **Test database gap** | Core lifecycle fixtures build an in-memory SQLite database | SQLite proof does not certify PostgreSQL row locks, isolation, connection termination, or process death |
| **Natural-event boundary** | R1B requires a different-identity natural signal and real venue outcome | Fake exchange results cannot certify venue latency, fills, fees, funding, slippage, or protection acceptance |

Sources: `docs/current/P0_ACTION_TIME_INVOCATION_CONSISTENCY_AND_FAILURE_TRUTH_DESIGN.md`,
`docs/current/P0_LIFECYCLE_PRODUCTION_CERTIFICATION_AND_CLOSURE_DESIGN.md`,
`src/application/action_time/exchange_command_worker.py`,
`tests/unit/test_ticket_bound_exchange_command_worker.py`, and
`tests/unit/test_ticket_bound_runtime_safety_state_materialization.py`.

## 3. Analysis And Design Judgment

The remaining engineering uncertainty is not whether the happy path has more
steps. It is whether the same business identity and first blocker survive
failure boundaries that SQLite and one-process unit tests cannot reproduce.

Therefore the smallest sufficient high-level response is:

1. **Keep the deployed state machines and tables as the oracle.**
2. **Add production-shaped PostgreSQL/process certification outside production cadence.**
3. **Repair only demonstrated invariant violations.**
4. **Stop expansion when all bounded scenarios pass.**
5. **Let natural live events remain the only source of exchange-behavior calibration.**

## 4. Authority And Safety Boundary

| Surface | Allowed | Forbidden |
| --- | --- | --- |
| **Local PostgreSQL certification** | Temporary isolated database, production migrations, production repositories/services, test-local fake exchange ledger | Production PG mutation, copied production secrets, file-backed truth |
| **Process fault injection** | Kill a local child process at named committed boundaries | Production failpoints, Tokyo process killing, timing-based random chaos |
| **Exchange simulation** | Deterministic fake acceptance keyed by production `client_order_id` | Real exchange write, simulated result presented as live proof |
| **Implementation repair** | Minimal TDD fix preserving current state machine and authority | New runtime profile, capital/risk change, safety gate bypass |
| **Deployment** | Deploy only if runtime/schema/systemd behavior changes | Deploy merely because tests or documentation changed |

This program creates no production JSON/Markdown reports. Test state lives in a
temporary PostgreSQL database and process synchronization is in memory or in
test-only PostgreSQL tables.

## 5. Invariant Oracle

### 5.1 Signal To Ticket

1. One **`ActionTimeInvocation`** binds exactly one `signal_event_id`, lane,
   source watermark, and action-time fact set.
2. Ticket creation is atomic with promotion, reservation, lane, and required
   fact materialization.
3. An expired invocation cannot create a Ticket after restart.
4. A failed transaction leaves no partial Ticket authority.

### 5.2 Ticket To Exchange Command

1. One deterministic **`client_order_id`** identifies one external side effect.
2. Claim is committed before exchange I/O.
3. An expired dispatch lease becomes **`outcome_unknown`** and cannot dispatch
   again until reconciliation proves absence.
4. Two workers cannot produce two external side effects for one command.

### 5.3 Fill To Protection And Runner

1. Protection quantity is based on confirmed cumulative fill, not requested
   entry quantity.
2. Duplicate venue snapshots are idempotent.
3. Contradictory venue truth becomes a hard stop or reconciliation-required
   state, never a silent lifecycle regression.
4. TP1 recovery produces at most one runner mutation generation.

### 5.4 Truth To Owner Projection

1. A newer success may clear the current blocker while immutable history stays.
2. A no-signal tick cannot erase an unresolved engineering blocker.
3. **`market_wait_validated`** is valid only after all engineering readiness
   conditions are closed.

Sources: `docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md`,
`docs/current/PRE_TRADE_RUNTIME_CONTRACT.md`, and
`docs/current/P0_LIFECYCLE_PRODUCTION_CERTIFICATION_AND_CLOSURE_DESIGN.md`.

## 6. Coverage Matrix

| ID | Boundary | Adversarial scenario | Required proof |
| --- | --- | --- | --- |
| **RCI-S1** | Signal/Ticket | Signal A and B are simultaneously eligible | Ticket carries exactly the selected invocation identity; no cross-signal facts |
| **RCI-S2** | Signal/Ticket | Transaction rolls back before Ticket commit | Facts, promotion, reservation, lane, and Ticket are all absent or all committed |
| **RCI-S3** | Signal/Ticket | TTL expires and process restarts | No expired Ticket; exact typed blocker persists for the original lane |
| **RCI-E1** | Command/process | Process dies after committed claim and before exchange call | No exchange side effect; lease expiry persists unknown outcome; no redispatch |
| **RCI-E2** | Command/process | Exchange accepts and process dies before PG result commit | One fake exchange order exists; PG becomes unknown after lease; no second order |
| **RCI-E3** | Command/concurrency | Two independent workers race | One claim and one fake exchange side effect |
| **RCI-E4** | Command/network | Gateway times out after dispatch starts | Durable unknown outcome and active domain hold; later commands stay blocked |
| **RCI-L1** | Fill/protection | Entry is partially filled | Protection uses actual cumulative fill only |
| **RCI-L2** | Fill/protection | Duplicate then contradictory snapshots arrive | Duplicate is idempotent; contradiction cannot regress lifecycle truth |
| **RCI-L3** | TP1/runner | Restart after TP1 before runner completion | Exactly one runner command generation and one external mutation |
| **RCI-P1** | Projection | Newer same-lane success follows failure | Current blocker clears; failure history remains queryable |
| **RCI-P2** | Projection | No-signal refresh follows engineering failure | Owner/current projection keeps engineering blocker and rejects false market wait |

## 7. Test Architecture

```text
pytest controller process
-> create unique temporary PostgreSQL database
-> run Alembic production migrations through revision 119
-> seed only the minimum authoritative rows for the tested boundary
-> spawn independent worker process where process death matters
-> test-local fake exchange records unique client_order_id in PostgreSQL
-> assert production PG rows and fake external side effects
-> terminate connections and drop temporary database
```

### 7.1 Test Database

- Base connection comes from **`BRC_TEST_POSTGRES_ADMIN_URL`**.
- Default is the repository's local PostgreSQL 16 compose service.
- Every test session creates a randomly named database with no production data.
- Alembic applies the same migration chain as deployment.
- Cleanup terminates only sessions connected to the temporary database.

### 7.2 Fake Exchange

The fake exchange is not a runtime adapter. It is test-local infrastructure
with a unique constraint on `client_order_id`. It exposes whether one causal
command produced zero, one, or more external side effects even when the worker
process is killed.

### 7.3 Deterministic Fault Points

Faults occur only at named boundaries:

1. after claim transaction commit;
2. after fake exchange acceptance commit;
3. before command result transaction commit;
4. after TP1 truth commit and before runner mutation completion.

No random sleeps decide correctness. Synchronization uses process events or
test-only committed rows, and every wait is timeout-bounded.

## 8. Finding Classification Gate

| Finding | Meaning | Required response |
| --- | --- | --- |
| **coverage_gap** | Production behavior already satisfies the invariant; proof was missing | Keep the new certification test; no runtime change |
| **implementation_defect** | Code violates an already-authoritative invariant | Write/retain RED, apply minimal fix, run focused and full regression |
| **architecture_gap** | Existing states or ownership cannot express a safe result | Stop the affected implementation slice, amend current design, then continue |
| **live_only_unknown** | Result depends on real venue behavior | Keep it in R1B; do not fake a completion claim |

## 9. Cadence And Performance

**Production cadence impact is zero.** P0-RCI runs only as an explicit local or
CI certification suite. It adds no watcher tick, timer, subprocess, PG polling,
API call, runtime writer, or Owner notification. All process waits are bounded
and all test databases are disposable.

`scripts/audit_production_runtime_file_io.py` must report
`performance_risk.status=clear` before completion.

## 10. Deployment And Natural-Event Rule

1. Test/document-only changes do not trigger Tokyo deployment.
2. Runtime, schema, timer, or service changes trigger the normal exact-head
   deployment and read-only no-active acceptance.
3. No synthetic production signal, Ticket, command, or order is inserted.
4. A different natural `signal_event_id` or active safety incident preempts this
   program at the next committed transaction boundary.
5. Natural acceptance records the real Ticket chain and then P0-RCI resumes.

## 11. Done Definition

P0-RCI is complete when:

1. all **12 bounded scenarios** pass on real PostgreSQL;
2. crash, retry, and concurrency produce no duplicate Ticket, command, or fake
   exchange order;
3. ambiguous outcomes block retry until authoritative reconciliation;
4. partial fill protection and restart recovery preserve lifecycle monotonicity;
5. engineering blockers cannot be overwritten by no-signal projection;
6. every finding is classified and either fixed or retained as live-only;
7. no new runtime file authority or production cadence is introduced;
8. deployment is performed only if production behavior changed;
9. **R1B** remains explicitly pending when no natural live event occurs.
