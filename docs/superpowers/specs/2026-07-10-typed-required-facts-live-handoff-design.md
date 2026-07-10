# P0-FH Typed RequiredFacts Live Handoff Closure

Status: approved for implementation by standing Owner direction

Date: 2026-07-10

Scope: infrastructure closure plus five-StrategyGroup live-door certification

## Objective

Close the missing typed-fact handoff between the versioned runtime evaluators
and the PG-backed action-time materializer so every current StrategyGroup can
reach the official real-trading door when a fresh eligible signal exists:

```text
closed market data
-> versioned evaluator
-> typed StrategyFactObservation rows
-> watcher signal summary
-> PG live signal event payload
-> action-time RequiredFacts snapshot
-> promotion / single lane / ticket
-> FinalGate
-> Operation Layer
-> disabled-smoke protected submit boundary
```

The task also closes two infrastructure defects found while auditing the same
problem class: production DSN normalization and watcher-safe Tokyo deployment.

## Verified Starting State

- Tokyo runs release `f2a3fdd85a6c5873f98ca31b96ba514328404ecc`
  with Alembic migration `112`.
- Five current StrategyGroups own six current executable Event Specs and
  twenty-two active candidate scopes.
- The runtime evaluators already emit event-specific typed fact observations
  for `CPM-LONG`, `MPG-LONG`, `MI-LONG`, `SOR-LONG`, `SOR-SHORT`, and
  `BRF2-SHORT`.
- `src/application/action_time/fact_snapshots.py` already consumes
  `signal_summary.fact_observations`.
- `scripts/runtime_active_observation_monitor.py::_signal_summary` does not
  project `evaluation_result.output.fact_observations`, so production typed
  facts disappear before the PG live-signal payload.
- Existing PG writer tests inject `fact_observations` manually and existing
  full-chain tests put strategy facts into the public-fact snapshot. Those
  tests prove downstream mechanics but not the real evaluator-to-action-time
  transport boundary.
- The Tradeability CLI rejects the production `postgresql+asyncpg://` DSN even
  though other production scripts normalize it to the sync psycopg driver.
- The deploy plan waits for `/api/health`, but it leaves the watcher timer
  running while the backend is stopped for migration. The timer may therefore
  start a watcher tick against an unavailable API.

## Root Cause

This is a cross-component contract ownership failure, not five independent
strategy defects:

1. The evaluator output model gained a typed fact collection.
2. The action-time consumer was hardened to require observed strategy facts.
3. The intermediate watcher summary remained an older allow-list projection.
4. Tests validated each endpoint with hand-built payloads but did not certify
   the complete producer-to-consumer chain.

The same missing-boundary-test pattern allowed one script to bypass the shared
DSN adapter and allowed deploy health readiness to be checked without owning
the lifecycle of the watcher timer that consumes the backend.

## Architecture Decision

### 1. Extend the existing typed fact mainline

`StrategyFactObservation` remains the single typed evaluator fact contract.
The watcher summary must carry the serialized list without inventing,
recomputing, or flattening strategy semantics. The existing PG live-signal
payload remains the durable handoff; no new table, fact bus, JSON file, or
Markdown authority is introduced.

The summary projection accepts only dictionary rows. Evaluators own typed fact
creation, and Action-Time revalidates each serialized
`StrategyFactObservation` before using it. A fact is accepted only while
`observed_at_ms <= now_ms < valid_until_ms`. Missing provenance, malformed
rows, future observations, stale observations, and duplicate fact keys are
ignored so the corresponding RequiredFact fails closed. The materialized
action-time snapshot cannot outlive the shortest typed RequiredFact validity.
For an execution-eligible Event Spec, every promotion RequiredFact must be
present in this valid typed set. A same-named field buried in `evidence_payload`
or `signal_snapshot` cannot substitute for a missing typed observation.

### 2. Certify the real boundary, not hand-built endpoints

Add tests at three depths:

1. A focused projector test proves typed facts survive
   `evaluation_result.output -> _signal_summary`.
2. A five-StrategyGroup integration test uses real evaluator outputs, writes
   the resulting watcher summary to PG, and materializes action-time facts
   while the public fact snapshot contains no strategy-event facts.
3. The existing twenty-two-scope full-chain test continues to prove each
   active symbol/side can reach ticket-bound disabled smoke. The new test
   proves the facts that unlock that chain come from the actual evaluator
   contract rather than from a synthetic public-fact shortcut.

Negative coverage must prove missing observations and active disable facts
remain blocked. Synthetic inputs are test-only and must never become live
signals or exchange-write authority.

### 3. Use the shared PostgreSQL DSN adapter

The Tradeability CLI must call `normalize_sync_postgres_dsn` and validate with
`is_sync_postgres_dsn`, matching the rest of the PG-backed runtime scripts.
`postgresql+asyncpg://` therefore becomes `postgresql+psycopg://` before
SQLAlchemy engine creation. SQLite remains allowed only behind the explicit
test flag.

### 4. Quiesce and restore the watcher around deployment

The deploy lifecycle becomes:

```text
stop watcher, runtime-monitor, and lifecycle-maintenance timers
-> stop any running watcher, monitor, and lifecycle-maintenance services
-> stop backend
-> migrate and validate PG
-> switch release
-> start backend
-> wait boundedly for HTTP 200 health
-> install current watcher/systemd units and drop-ins
-> restore watcher, monitor, and lifecycle-maintenance timers/services
-> verify all recurring timers active
-> postdeploy read-only verification
```

The health loop and systemd stops are timeout-bounded. Recurring-service
restoration must occur only after health succeeds and the new units are
installed, so no runtime consumer can race backend or PG migration.

## Strategy And Scope Matrix

| StrategyGroup | Event Specs | Active scopes | Typed event facts owned by evaluator |
| --- | ---: | ---: | --- |
| `CPM-RO-001` | `CPM-LONG` | 4 | trend, reclaim, pullback-low reference |
| `MPG-001` | `MPG-LONG` | 4 | persistence, leader strength, momentum-floor reference |
| `MI-001` | `MI-LONG` | 3 | impulse, relative strength, impulse invalidation reference |
| `SOR-001` | `SOR-LONG`, `SOR-SHORT` | 8 | opening range, side trigger, side protection reference |
| `BRF2-001` | `BRF2-SHORT` | 3 | rally failure, short enabled, uptrend disable, rally-high reference |

## Error Handling And Fail-Closed Rules

- Missing or non-list `fact_observations`: project an empty list; action-time
  reports exact missing RequiredFacts.
- Non-dictionary observation row: ignore it; never infer a fact.
- Missing `observed_value`: it cannot satisfy action-time RequiredFacts.
- Stale, future-dated, provenance-free, malformed, or duplicate typed facts:
  ignore them and report the RequiredFact as missing.
- Missing typed RequiredFact on an execution-eligible Event Spec: fail closed
  even if an untyped evidence object contains a same-named value.
- Action-time snapshot expiry: cap it at the earliest validity of the signal,
  public fact snapshot, RequiredFacts freshness, and typed observations used.
- Active disable fact such as `strong_uptrend_disable=true`: block before lane
  creation.
- Unknown, null, malformed, or non-zero disable fact: fail closed; only an
  explicit false/zero observation is safe enough to continue.
- Unsupported symbol/side or ambiguous active Event Spec: preserve existing
  scope and identity hard stops.
- Async-driver DSN that cannot be normalized to the approved sync PG scheme:
  reject before connecting.
- Backend health timeout: do not restore/start the watcher timer and fail the
  deploy phase.

## Performance And Cadence

| Dimension | Decision |
| --- | --- |
| Cadence | Typed observations ride the existing per-signal watcher payload; no extra poller |
| No-signal file writes | `0` JSON/MD files |
| PG writes | No new tables or recurring rows; existing bounded signal/fact projections only |
| CPU | One small list copy per evaluated runtime; no report builder |
| Disk | No new sidecar, report, or archive output |
| Timeout | Existing API/subprocess timeouts plus bounded 30-second deploy health wait |
| Retention | Existing PG retention; design and plan are repository provenance only |

## Authority Boundary

This work does not change strategy parameters, Event Spec meaning, symbols,
sides, capital, leverage, notional, attempt caps, runtime profile, credentials,
or exchange permissions. It does not treat replay or synthetic facts as live.
It does not bypass FinalGate, Operation Layer, protection, duplicate-submit,
position/open-order, reconciliation, or settlement controls.

## Deployment And Acceptance

The deploy is stage-worthy because it repairs a production signal-to-action
boundary and deployment lifecycle. Acceptance requires:

1. focused red-green tests;
2. all related watcher, evaluator, action-time, Tradeability, deploy, and
   systemd tests;
3. full repository test suite;
4. production file-I/O audit with `performance_risk.status=clear` and zero
   frequent report writers;
5. clean commit and pushed focused branch;
6. Tokyo git-based release at the exact commit with migration `112`;
7. backend HTTP health, watcher/monitor/lifecycle timers active;
8. one production watcher tick exits successfully;
9. PG/read-model evidence confirms five StrategyGroups and twenty-two scopes
   are current, with no Owner action required when merely waiting for signal.

Natural market opportunity is not required for engineering acceptance. A real
order remains conditional on a future fresh live signal and all action-time
safety gates.

## Production Truth Cutover Extension

The first Tokyo acceptance run exposed two additional P0 truth defects after
the Typed RequiredFacts handoff itself was healthy:

1. Tradeability selected the most recently written Runtime Safety State without
   checking its validity window or current chain lineage, so an expired SOR
   snapshot could produce a false `tradable_now`;
2. the PG Tradeability adapter converted current rows back into legacy artifact
   shapes and re-ran historical schema guards, producing false
   `artifact_missing` / `schema_invalid` blockers for the other four groups.

The production design is therefore extended as follows:

```text
PG Candidate Pool per-symbol current truth
-> one strategy-level Tradeability aggregation per StrategyGroup
-> current Runtime Safety State payload validation
-> live_signal -> promotion -> lane -> ticket -> Operation Layer lineage proof
-> tradable_now only when both payload and lineage are valid
```

The following currentness rules are shared across read models:

| PG object | Currentness requirement | Authority consequence |
| --- | --- | --- |
| watcher coverage | current flag, bounded last tick, unexpired | may prove detector/watcher coverage only |
| pre-trade readiness | bounded compute time, unexpired | may classify the current per-symbol blocker |
| live signal / promotion / lane / ticket | not future-dated, legal open state, unexpired | may advance the L5-L7 chain only |
| Runtime Safety State | observed no later than now, unexpired, execution-eligible payload | still not enough for `tradable_now` |
| verified safety lineage | same StrategyGroup/symbol/side/profile across signal, promotion, lane, ticket, handoff, and safety snapshot | may support `tradable_now`; still no exchange-write authority by itself |

`Tradeability`, `Daily Live Enablement`, and `Goal Status` consume this shared
Runtime Safety truth. Expired snapshots are absent from current truth; orphan
or mismatched snapshots remain diagnostic evidence but cannot grant submit
readiness. Production Tradeability no longer invokes legacy artifact schema or
timestamp guards on PG current data.

## Rollback

No schema migration is required. Code rollback can atomically repoint
`app/current` to the previous release and restart the backend and watcher timer.
PG signal and fact history remains append-only. No destructive cleanup is part
of this task.

## Live Enablement Transition

```text
Before:
five evaluators emit correct facts
-> watcher summary drops them
-> future signal may stop at action-time missing facts

After:
five evaluators emit correct facts
-> watcher and PG preserve them
-> action-time materializes exact RequiredFacts
-> all 22 current scopes are certified to the disabled-smoke real-trading door
```

## Stop Conditions

Stop before deploy if any typed fact can be silently invented, any unsupported
side enters scope, file-I/O audit regresses, full tests fail, the target commit
is not the pushed remote branch head, Tokyo baseline differs from the expected
release, or production health cannot be restored without weakening safety.
