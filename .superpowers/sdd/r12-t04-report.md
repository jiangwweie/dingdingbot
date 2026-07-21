# R12-T04 Implementation Report

## Outcome

- One lifecycle invocation now owns one immutable monotonic
  `absolute_deadline_at`; ENTRY, SL, and TP1 consume that exact value.
- Added a pure typed deadline budget and phase decision with production defaults:
  ENTRY `6s`, SL `6s`, TP1 `4s`, commit margin `5s`, ENTRY/SL result reserves
  `1s` each, and shutdown reserve `1s`.
- Protected-submit ENTRY requires the complete `15s` initial-protection reserve
  before its claim can commit.
- The effective gateway timeout is the minimum of role timeout, remaining
  deadline after commit margin, and the legacy timeout cap.
- Deadline and lease failures occur before gateway I/O. The claim transaction
  rolls back, leaving the command prepared and claimable.
- ENTRY result/projection truth always commits before a later SL/TP1 deadline
  decision. TP1 deadline exhaustion preserves confirmed SL truth.
- Real phase telemetry records request count, role/source identity, effective
  timeout, deadline remaining, result-transaction latency, result commit time,
  and accepted ENTRY-to-SL result-commit latency.
- CLI and systemd carry explicit production budgets while retaining the
  `28s < 36s < 45s` process timeout hierarchy.

## TDD Evidence

The three semantic corrections were observed RED before implementation:

```text
ENTRY-to-SL latency ended at SL dispatch start: expected 1000ms, got 0ms
post-claim deadline exhaustion still called the gateway: expected 0, got 1 call
result commit latency included lifecycle completion: expected 0ms, got 5000ms
```

After the worker correction:

```text
3 passed
```

CLI/systemd RED initially reported six missing defaults/helpers/inequalities;
the production wiring then passed all 27 selected checks. Legacy timeout
NaN/infinity tests were also RED before explicit finite validation and GREEN
afterwards.

## Deadline And Telemetry Matrix

| Case | Exchange requests | Durable result |
| --- | ---: | --- |
| ENTRY only | 1 | Same invocation deadline retained |
| ENTRY + SL | 2 | Exact-source Initial Stop remains complete |
| ENTRY + SL + TP1 | 3 | All phases share one deadline |
| Authoritative rejection | 1 | Confirmed rejection persisted |
| Dispatch timeout | 1 | `outcome_unknown` persisted |
| Pre-ENTRY reserve block | 0 | ENTRY remains `prepared`, attempt count `0` |
| SL/TP1 deadline block | 0 for blocked phase | Blocked command remains `prepared` |

Boundary evidence covers `margin-1ms`, exact margin, sufficient margin,
pre-ENTRY reserve below/exact threshold, deadline-capped lease equality, and
all non-finite typed/legacy float inputs.

## Regression Evidence

```text
deadline/domain/global/CLI/systemd telemetry: 82 passed
T03 exchange-command domain + worker: 57 passed
PostgreSQL RCI E1-E4 + process restart: 5 passed, 16 deselected
protected-submit attempt/API/global deadline: 75 passed
lifecycle maintenance/systemd/postdeploy compatibility: 36 passed
```

## Static And Production Gates

```text
alembic heads: 145 (head)
Ruff: All checks passed
git diff --check: passed
production runtime file-I/O audit:
  suspicious_runtime_file_authority=0
  frequent_report_write=0
output artifact scope: output_artifact_scope_valid
```

## Performance Assessment

- Cadence: one bounded decision per claimable exchange-command phase.
- PG: existing short claim and result transactions only; no transaction spans
  gateway I/O.
- Exchange: at most three worker writes for protected ENTRY -> SL -> TP1;
  actual calls, not CLI guesses, populate telemetry.
- File writes: zero JSON/Markdown/runtime artifact writes.
- CPU/disk: pure arithmetic and in-memory typed telemetry only.
- Timeout: every gateway phase is bounded by its role timeout and the same
  invocation deadline.

## Scope And Chain Position

```text
chain_position: durable_worker_protection_barrier
closed_engineering_problem: subphases could renew deadline and hide protection budget exhaustion
live_enablement_state_before: ENTRY could consume the timer budget before Initial Stop
live_enablement_state_after: ENTRY claim proves protection reserve and all phases consume one absolute deadline
blocker_removed_or_reclassified: initial_stop_timer_latency_gap removed; deadline exhaustion is explicit before I/O
capability_unlocked: bounded same-invocation ENTRY-to-Initial-Stop protection drain with real telemetry
next_engineering_bottleneck: R12-T05 reconciliation/recovery generation and incident/fence convergence
owner_action_required: no
```

R12-T05 incidents, recovery generation, capacity release, monitor language, and
new-entry fences remain intentionally out of scope.

## Self Review

- No second exchange authority, retry loop, long transaction, file-backed
  runtime authority, or recurring report writer was added.
- T03 exact source, Attempt, Ticket, netting-domain, phase-order, and quantity
  authority remain covered by the complete worker regression.
- No live profile, sizing, symbol/side, capital, credential, withdrawal, or
  transfer behavior changed.
- Self-review findings: no P0/P1/P2.
