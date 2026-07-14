---
title: P0_OWNER_NOTIFICATION_PROJECTION_AND_DELIVERY_CLOSURE_IMPLEMENTATION_PLAN
status: LOCAL_IMPLEMENTATION_COMPLETE_DEPLOYMENT_PENDING
authority: docs/current/P0_OWNER_NOTIFICATION_PROJECTION_AND_DELIVERY_CLOSURE_IMPLEMENTATION_PLAN.md
last_verified: 2026-07-14
---

# P0 Owner Notification Projection And Delivery Closure Implementation Plan

> **Execution mode:** Codex executes this plan locally after Owner approval.
> Each task uses test-first implementation and an isolated focused branch.
> Tokyo deployment, service mutation, and production writes remain outside this
> plan until a separate release decision.

## Task ID

```text
P0-ON-PDC-20260714
```

## Goal

Close lifecycle notification misclassification, delivery-batch starvation,
Feishu business-acknowledgement ambiguity, and lifecycle-worker health coverage
without changing any trading authority or production cadence.

## Why

The current release can report an old `trade_submitted` milestone for later
lifecycle states, can spend its five-item candidate window on already-sent
rows, can mark an HTTP 2xx business error as sent, and does not explicitly
monitor the lifecycle timer/service.

These are Owner-feedback and runtime-observability defects. They do not justify
interrupting the currently running server release before the replacement has
passed local certification and a separate deployment decision.

## Global Authority Model

```text
Owner controls policy.
System executes process.
Lifecycle Safety Core owns lifecycle classification.
Owner notification projects material product language only.
Delivery ledger owns dedupe and retry only.
Feishu acknowledgement proves delivery only.
```

No task may grant signal, Ticket, order, exchange-write, capital, sizing,
leverage, position-close, or emergency-reduce authority.

## Chain Position

```text
Before:
  real lifecycle path exists; Owner feedback has projection and delivery gaps

After local completion:
  owner_notification_projection_delivery_certification_gap is closed locally
  and marked deployment_pending

After separately approved deployment and acceptance:
  notification and lifecycle-monitor closure can be marked production accepted
```

## Allowed Files

```text
src/application/owner_notification.py
scripts/run_tokyo_runtime_server_monitor.py
deploy/systemd/brc-runtime-monitor.service
tests/unit/test_owner_notification_scenarios.py
tests/unit/test_owner_notification_delivery.py
tests/unit/test_runtime_monitor_frequency_policy.py
tests/unit/test_tokyo_runtime_server_monitor.py
tests/unit/test_tokyo_runtime_ops_health_lifecycle.py
docs/current/P0_OWNER_NOTIFICATION_PROJECTION_AND_DELIVERY_CLOSURE_DESIGN.md
docs/current/P0_OWNER_NOTIFICATION_PROJECTION_AND_DELIVERY_CLOSURE_IMPLEMENTATION_PLAN.md
```

## Forbidden Files

```text
src/application/execution_orchestrator.py
src/application/order_lifecycle_service.py
src/application/position_projection_service.py
src/application/capital_protection.py
src/infrastructure/exchange_gateway.py
src/application/reconciliation.py
src/application/startup_reconciliation_service.py
migrations/versions/**
```

## Rehearsal And Simulation Boundary

All tests use in-memory typed rows, SQLite test schema, stub systemd results,
or stub Feishu responses. They do not create a real Webhook request, submit an
order, mutate a production unit, or grant Runtime Safety State authority.

## Stop Conditions

Stop implementation and report the exact conflict if:

1. correct projection requires changing Lifecycle Safety Core semantics;
2. a second table, outbox, scheduler, or migration appears necessary;
3. delivery correctness requires reading unbounded PG history;
4. any change enters an exchange-write or automatic position-close path;
5. current tests reveal that production authority differs from tracked code;
6. production file-I/O audit detects a new runtime reader or recurring writer.

## Task 1: Lock The Complete Lifecycle Notification Matrix

### Goal

Create a test matrix covering every status in the canonical lifecycle
specification before changing projection behavior.

### Files

```text
tests/unit/test_owner_notification_scenarios.py
src/application/owner_notification.py
```

### RED

Add parameterized tests that derive the status set from
`LIFECYCLE_STATUS_SPECIFICATIONS` and assert the notification outcome by typed
decision family.

The expected families are:

| Decision family | Expected notification |
| --- | --- |
| `entry_submit_sent`, `entry_fill_pending` | `trade_submitted` |
| `position_protected` | `position_protected` |
| `runner_protected` | `tp1_runner_active` |
| `lifecycle_closed` | `trade_closed` |
| Automated intermediate | No intent |
| Recovery required with retry budget | No intent |
| Hard stopped without explicit Owner action | `system_temporarily_unavailable` |
| Explicit Owner action or retry exhausted | `intervention_required` |

Add named regression tests for these reproduced false-submit statuses:

```text
tp1_filled
runner_mutation_pending
runner_mutation_failed
protection_degraded
runner_reconciliation_mismatch
position_closed_protection_live
final_exit_unknown
settlement_blocked
review_blocked
```

Each regression test provides a submitted Ticket and one lifecycle row. None
may return `trade_submitted`.

Run:

```bash
pytest -q tests/unit/test_owner_notification_scenarios.py
```

Expected RED evidence is at least one false `trade_submitted` assertion failure
from the reproduced status set.

### GREEN

In `src/application/owner_notification.py`:

1. import `ticket_bound_lifecycle_owner_feedback` from the existing Owner
   projection module;
2. replace the local unsafe-status subset with one helper that consumes the
   typed feedback;
3. return a material milestone intent, abnormal incident intent, or explicit
   quiet result;
4. consult submitted-Ticket fallback only when `lifecycle is None`;
5. keep stable milestone wording and correlation identities unchanged.

Introduce one internal result model or enum with these three outcomes:

```text
material_intent
intentional_quiet
no_lifecycle
```

This explicit tri-state is required because `None` alone cannot distinguish
"lifecycle exists and should remain quiet" from "no lifecycle exists, use the
Ticket fallback."

Run:

```bash
pytest -q tests/unit/test_owner_notification_scenarios.py
pytest -q tests/unit/test_ticket_bound_lifecycle_decision_reducer.py \
  tests/unit/test_ticket_bound_lifecycle_owner_projection.py
```

### Refactor

Remove the duplicated `unsafe_statuses` taxonomy. Keep notification wording in
the notification module and lifecycle semantics in Lifecycle Safety Core.

### Acceptance

- Every canonical lifecycle status is covered.
- No later status repeats `trade_submitted`.
- Automated recovery remains quiet while retry budget exists.
- Hard-stopped unknown state is visible without falsely requiring Owner action.
- Explicit intervention rules remain fail-closed.

### Commit Boundary

```bash
git add src/application/owner_notification.py \
  tests/unit/test_owner_notification_scenarios.py
git commit -m "fix: classify lifecycle owner notifications from typed state"
```

Do not create this commit until Task 1 tests are green.

## Task 2: Move The Five-Intent Cap Behind Delivery Eligibility

### Goal

Make the **5-card limit** apply to actual new or retryable delivery attempts,
not to pre-ledger projected candidates.

### Files

```text
src/application/owner_notification.py
scripts/run_tokyo_runtime_server_monitor.py
tests/unit/test_owner_notification_delivery.py
```

### RED

Add these delivery regressions:

1. five higher-ranked `sent` rows plus one new critical intent send the new
   intent in the same run;
2. five higher-ranked retry-exhausted rows plus one new intent send the new
   intent;
3. six eligible new intents perform exactly five sends;
4. two retryable failures and four new intents perform five attempts in the
   documented order;
5. dry-run still creates zero rows and performs zero network calls;
6. suppressed and exhausted counts remain visible even though those rows do
   not occupy attempt slots;
7. a resolved incident that becomes active again is eligible, clears
   `resolved_at_ms`, and starts a new three-attempt episode.

Run:

```bash
pytest -q tests/unit/test_owner_notification_delivery.py
```

Expected RED evidence is that the new sixth intent is starved by the current
projector truncation.

### GREEN

In `src/application/owner_notification.py`:

1. remove the final five-item slice from pure candidate projection;
2. retain deterministic dedupe and severity ordering;
3. rely on the current-state repository's existing bounded queries rather than
   adding an arbitrary projection failure threshold.

In `scripts/run_tokyo_runtime_server_monitor.py`:

1. merge the monitor fallback before delivery selection without slicing;
2. normalize and dedupe identities;
3. load existing ledger state for all bounded candidate dedupe keys in one PG
   query;
4. classify each candidate as new, retryable, sent, exhausted, or a resolved
   incident recurrence;
5. reset attempt count and resolution timestamp only for an active recurrence;
6. rank only new, retryable, and active-recurrence candidates;
7. select at most `MAX_INTENTS_PER_RUN` eligible candidates;
8. send only the selected batch;
9. include suppressed and exhausted counts for all inspected candidates in the
   summary.

Add one pure internal selection helper with the contract:

```python
def select_owner_notification_delivery_batch(
    candidates: list[OwnerNotificationIntent],
    ledger_rows: dict[str, dict[str, object]],
    *,
    limit: int,
) -> OwnerNotificationDeliverySelection:
```

The typed result contains selected candidates, sent-suppressed count,
retry-exhausted count, and reopened-incident count.

Run:

```bash
pytest -q tests/unit/test_owner_notification_delivery.py \
  tests/unit/test_owner_notification_scenarios.py
```

### Refactor

Keep PG writes inside the existing application function. The selection helper
must remain pure and must not open its own connection.

### Acceptance

- The batch limit is enforced after ledger eligibility.
- Already-sent and exhausted rows cannot starve new critical cards.
- At most five attempts occur per run.
- Existing stable dedupe identity is unchanged.
- A real incident recurrence is not permanently muted by the prior resolution.
- No second table, outbox, or timer exists.

### Commit Boundary

```bash
git add src/application/owner_notification.py \
  scripts/run_tokyo_runtime_server_monitor.py \
  tests/unit/test_owner_notification_delivery.py
git commit -m "fix: select owner notification batch after delivery eligibility"
```

Do not create this commit until Tasks 1 and 2 tests are green together.

## Task 3: Require Feishu Business-Level Acknowledgement

### Goal

Persist `sent` only when both HTTP transport and Feishu business result prove
success.

### Files

```text
scripts/run_tokyo_runtime_server_monitor.py
tests/unit/test_owner_notification_delivery.py
tests/unit/test_tokyo_runtime_server_monitor.py
```

### RED

Add pure acknowledgement tests for:

| HTTP/body case | Expected `sent` | Expected business code |
| --- | ---: | --- |
| 200 and `{"code": 0, "msg": "success"}` | true | 0 |
| 200 and `{"code": 19001, "msg": "invalid"}` | false | 19001 |
| 200 and `{"StatusCode": 0, "StatusMessage": "success"}` | true | 0 |
| 200 and `{"StatusCode": 1, "StatusMessage": "failed"}` | false | 1 |
| 200 and invalid JSON | false | null |
| 200 and `{}` | false | null |
| 500 and success-looking JSON | false | 0 |

Add an integration-level delivery assertion proving HTTP 200 plus non-zero
business code increments `send_attempts`, persists `failed`, and remains
retryable below three attempts.

Run:

```bash
pytest -q tests/unit/test_owner_notification_delivery.py \
  tests/unit/test_tokyo_runtime_server_monitor.py -k "feishu or notification"
```

Expected RED evidence is that the current 2xx-only sender marks the business
error as sent.

### GREEN

Add one pure parser shared by `send_feishu_text` and
`send_feishu_payload`:

```python
def parse_feishu_robot_ack(
    *,
    status_code: int,
    response_body: str,
) -> dict[str, object]:
```

Required output keys are:

```text
sent
status_code
business_code
business_message
response_body_preview
```

Rules:

1. reject non-2xx transport;
2. parse a JSON object;
3. prefer `code` when present;
4. accept `StatusCode` only when `code` is absent;
5. require the chosen business code to equal zero;
6. fail closed for invalid JSON or missing recognized code;
7. cap body preview at 500 characters.

Both senders must call this parser for successful HTTP responses. HTTP errors
and exceptions keep their current bounded failure shape. The existing
`feishu_response` JSON must persist `business_code` and the bounded
`business_message` together with transport status and body preview.

Run:

```bash
pytest -q tests/unit/test_owner_notification_delivery.py \
  tests/unit/test_tokyo_runtime_server_monitor.py -k "feishu or notification"
```

### Refactor

Do not log request bodies, signatures, Webhook URLs, or secrets. Do not create a
text fallback for a failed interactive-card send.

### Acceptance

- HTTP success alone cannot produce `sent`.
- Current and legacy Feishu success fields are supported explicitly.
- Business failure follows the existing bounded retry path.
- Delivery response evidence, including business code and bounded message,
  fits the existing JSON column.

### Commit Boundary

```bash
git add scripts/run_tokyo_runtime_server_monitor.py \
  tests/unit/test_owner_notification_delivery.py \
  tests/unit/test_tokyo_runtime_server_monitor.py
git commit -m "fix: verify feishu robot business acknowledgement"
```

Do not create this commit until Task 3 tests are green.

## Task 4: Add Lifecycle Scheduler Units To Readonly Health Coverage

### Goal

Make the existing server monitor explicitly observe the lifecycle timer and
one-shot service without controlling either unit.

### Files

```text
scripts/run_tokyo_runtime_server_monitor.py
deploy/systemd/brc-runtime-monitor.service
tests/unit/test_runtime_monitor_frequency_policy.py
tests/unit/test_tokyo_runtime_server_monitor.py
tests/unit/test_tokyo_runtime_ops_health_lifecycle.py
```

### RED

Add tests proving:

1. the monitor service command contains both
   `brc-ticket-lifecycle-maintenance.timer` and
   `brc-ticket-lifecycle-maintenance.service`;
2. the default Python unit tuple contains both;
3. the lifecycle one-shot service is in `ONESHOT_INACTIVE_OK_UNITS`;
4. inactive successful lifecycle service is healthy;
5. inactive lifecycle timer is unhealthy;
6. failed lifecycle service is unhealthy;
7. monitor source and unit files contain no `systemctl start`, `stop`,
   `restart`, `enable`, or `disable` action.

Run:

```bash
pytest -q tests/unit/test_runtime_monitor_frequency_policy.py \
  tests/unit/test_tokyo_runtime_server_monitor.py \
  tests/unit/test_tokyo_runtime_ops_health_lifecycle.py
```

Expected RED evidence is absence of the lifecycle units from the current
monitor configuration.

### GREEN

In `scripts/run_tokyo_runtime_server_monitor.py`:

1. append the lifecycle timer and service to `DEFAULT_SYSTEMD_UNITS`;
2. append only the lifecycle service to `ONESHOT_INACTIVE_OK_UNITS`;
3. reuse the current status/result evaluation without adding unit-specific
   branching elsewhere.

In `deploy/systemd/brc-runtime-monitor.service`, append:

```text
--systemd-unit brc-ticket-lifecycle-maintenance.timer
--systemd-unit brc-ticket-lifecycle-maintenance.service
```

Keep the existing timer cadence and environment files unchanged.

Run:

```bash
pytest -q tests/unit/test_runtime_monitor_frequency_policy.py \
  tests/unit/test_tokyo_runtime_server_monitor.py \
  tests/unit/test_tokyo_runtime_ops_health_lifecycle.py
```

### Refactor

Keep unit lists aligned between Python defaults and the deployed service. Do
not add a new monitor timer or a lifecycle-specific notification sender.

### Acceptance

- Both lifecycle units are observed.
- One-shot inactive semantics are correct.
- Timer inactivity remains an error.
- No service mutation command is introduced.
- Systemd inspection remains bounded readonly subprocess work.

### Commit Boundary

```bash
git add scripts/run_tokyo_runtime_server_monitor.py \
  deploy/systemd/brc-runtime-monitor.service \
  tests/unit/test_runtime_monitor_frequency_policy.py \
  tests/unit/test_tokyo_runtime_server_monitor.py \
  tests/unit/test_tokyo_runtime_ops_health_lifecycle.py
git commit -m "fix: monitor ticket lifecycle scheduler health"
```

Do not create this commit until Task 4 tests are green.

## Task 5: Run Package Regression And Negative-Authority Proof

### Goal

Prove the four changes compose without notification replay, runtime authority
expansion, cadence expansion, or file-backed production state.

### Files

No production file changes are allowed in this task. Test-only corrections may
touch only the allowed test files and must not weaken assertions.

### Targeted Regression

Run:

```bash
pytest -q \
  tests/unit/test_owner_notification.py \
  tests/unit/test_owner_notification_scenarios.py \
  tests/unit/test_owner_notification_delivery.py \
  tests/unit/test_owner_notification_migration.py \
  tests/unit/test_runtime_signal_forensics_repository.py \
  tests/unit/test_runtime_monitor_frequency_policy.py \
  tests/unit/test_tokyo_runtime_server_monitor.py \
  tests/unit/test_tokyo_runtime_ops_health_lifecycle.py
```

### Lifecycle Contract Regression

Run:

```bash
pytest -q \
  tests/unit/test_ticket_bound_lifecycle_decision_reducer.py \
  tests/unit/test_ticket_bound_lifecycle_owner_projection.py \
  tests/unit/test_ticket_bound_lifecycle_scheduler.py \
  tests/unit/test_ticket_bound_lifecycle_maintenance_service.py
```

### Static Negative Checks

Run:

```bash
rg -n "systemctl (start|stop|restart|enable|disable)" \
  scripts/run_tokyo_runtime_server_monitor.py \
  deploy/systemd/brc-runtime-monitor.service

rg -n "create_order|cancel_order|close_position|reduceOnly" \
  src/application/owner_notification.py \
  scripts/run_tokyo_runtime_server_monitor.py
```

Both searches must return no new authority-bearing implementation path.

### Repository Validators

Run:

```bash
python3 scripts/validate_current_docs_authority.py
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
python3 scripts/audit_production_runtime_file_io.py --fail-on-risk
git diff --check
```

Required outcomes:

- current-doc validation passes;
- no tracked `output/**` change exists;
- `performance_risk.status` is `clear`;
- no whitespace error exists.

### Broader Suite

Run the repository's standard complete unit suite:

```bash
pytest -q tests/unit
```

If the complete suite is too long for one command session, continue polling the
same process. Do not replace it with a smaller claim.

### Acceptance

- All targeted and lifecycle regressions pass.
- Full unit suite passes with no unexplained new skip or xfail.
- Static checks show no exchange or service-control authority expansion.
- Production file-I/O audit remains clear.

### Commit Boundary

If Task 5 requires no test correction, create no new commit. If an allowed test
file needed a legitimate strengthening change, commit only that exact file:

```bash
git add tests/unit/test_owner_notification_scenarios.py \
  tests/unit/test_owner_notification_delivery.py \
  tests/unit/test_runtime_monitor_frequency_policy.py \
  tests/unit/test_tokyo_runtime_server_monitor.py \
  tests/unit/test_tokyo_runtime_ops_health_lifecycle.py
git commit -m "test: certify owner notification delivery closure"
```

## Task 6: Prepare Deploy Evidence And Stop

### Goal

Produce a deploy-readiness conclusion without deploying or changing Tokyo.

### Required Evidence

Record in the final local handoff:

1. branch and exact commit SHA;
2. changed-file list;
3. targeted test counts;
4. full unit-suite result;
5. production file-I/O audit result;
6. notification matrix result;
7. delivery-starvation regression result;
8. Feishu business-acknowledgement result;
9. lifecycle systemd coverage result;
10. explicit statement that Tokyo remained untouched.

### Deploy Preflight For A Later Authorized Turn

The later deploy turn must perform readonly checks before mutation:

```text
current Tokyo release identity
active Ticket count and identities
current position and open-order state
notification ledger retry backlog
lifecycle timer and latest service result
runtime monitor timer and latest service result
```

Deploy acceptance must verify:

- no historical notification replay storm;
- one synthetic/stubbed business-error case remains failed locally, not against
  the real Webhook;
- both lifecycle units appear in monitor evidence;
- current real lifecycle continues without notification code granting or
  blocking exchange authority.

### Hard Stop

End the implementation turn with:

```text
local_implementation_complete
deployment_pending_owner_confirmation
tokyo_runtime_unchanged
```

Do not run SSH, deploy apply, systemctl mutation, production migration, real
Webhook test, or real exchange action in this plan.

## Done When

The work package is locally complete only when:

1. every canonical lifecycle status has a notification expectation;
2. no intermediate or recovery state repeats `trade_submitted`;
3. hard-stop versus explicit intervention behavior follows typed Owner state;
4. the five-card cap applies after delivery eligibility;
5. Feishu business errors cannot be persisted as sent;
6. lifecycle timer/service health is explicitly observed;
7. targeted and full unit suites pass;
8. current-doc, output-scope, and production-file-I/O validators pass;
9. no forbidden file changed;
10. Tokyo and its current live runtime remain untouched.

## Confirmation State

Owner approval authorized local implementation. The implementation and local
certification are complete; deployment, production notification, service
mutation, and trading intervention remain outside this package pending a
separate Owner release confirmation.
