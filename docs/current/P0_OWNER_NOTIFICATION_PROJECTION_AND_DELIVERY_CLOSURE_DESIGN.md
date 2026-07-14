---
title: P0_OWNER_NOTIFICATION_PROJECTION_AND_DELIVERY_CLOSURE_DESIGN
status: LOCAL_IMPLEMENTATION_COMPLETE_DEPLOYMENT_PENDING
authority: docs/current/P0_OWNER_NOTIFICATION_PROJECTION_AND_DELIVERY_CLOSURE_DESIGN.md
last_verified: 2026-07-14
---

# P0 Owner Notification Projection And Delivery Closure Design

## Decision

The second release-risk closure package is:

```text
P0 Owner Notification Projection And Delivery Closure
```

It closes four defects inside the already deployed Owner-notification path:

1. lifecycle rows that are neither a stable positive milestone nor part of the
   old unsafe-status subset can fall through to a repeated `trade_submitted`
   card;
2. the five-intent cap is applied before PG delivery eligibility is known, so
   already-sent rows can consume the batch and starve new material intents;
3. the Feishu sender treats every HTTP 2xx response as success without checking
   the robot API business result;
4. the server monitor does not explicitly inspect the lifecycle scheduler
   timer and one-shot service that own continuous post-submit progression.

This package changes explanation, delivery correctness, and readonly health
coverage only. It does not change signal detection, StrategyGroup scope,
capital, leverage, sizing, FinalGate, Operation Layer, exchange-write
authority, lifecycle transition rules, or automatic exit policy.

## Release-Review Remediation — 2026-07-14

Local review found that the delivery ledger query combined exact stable keys and
legacy correlation compatibility under one global `LIMIT 1000`. That could omit
an already-sent exact row from a candidate set larger than 1,000, resend it,
and then collide with the ledger unique key.

The local correction is recorded in
`P0_RELEASE_REVIEW_FINDINGS_REMEDIATION_DESIGN.md`:

```text
exact stable-key batches without a global result limit
-> unresolved-only bounded legacy compatibility lookup
-> existing eligibility, five-attempt cap, send, and persistence path
```

The correction introduces no migration, outbox, timer, notification policy,
trading authority, or production file path. Its local acceptance includes the
1,001-sent-row suppression regression, the beyond-1,000 new-card delivery
regression, focused notification/monitor tests, full unit tests, and the
current production file-I/O audit. Tokyo remains unchanged pending a separate
release decision.

## Owner Decision Boundary

The current Tokyo release remains the running production version while this
design is reviewed and implemented locally after approval. New entries may
continue through the server's current official runtime path.

This document grants no authority to:

- deploy a new release;
- restart, stop, or reconfigure a Tokyo service;
- mutate production notification rows;
- suppress a current real order or lifecycle action;
- pause StrategyGroups or prevent new entry;
- add automatic emergency reduction or automatic policy-driven close.

A later deployment requires a separate release decision after local tests,
machine audits, and deploy evidence are complete.

## Authority And Source Boundaries

```text
PG/runtime facts decide what happened.
Lifecycle Safety Core decides typed lifecycle safety and Owner state.
OwnerNotificationIntent decides whether a material Owner message exists.
Delivery eligibility decides which unsent/retryable intents enter the batch.
Feishu acknowledgement decides whether one attempt is recorded as sent.
The renderer decides wording and presentation only.
```

The package reuses these current authority surfaces:

- `src/application/action_time/lifecycle_safety_core.py` for lifecycle status,
  control state, and Owner state;
- `src/application/readmodels/owner_projection.py` for lifecycle Owner
  feedback and explicit intervention rules;
- `src/application/owner_notification.py` for typed intents and static cards;
- `brc_server_monitor_notifications` for dedupe, retry, recovery, and delivery
  history;
- the existing server monitor timer for readonly production health checks.

No Markdown, JSON, YAML, local cache, or generated report becomes a runtime
source.

## Known Facts

### Current Projection Behavior

The current projector has explicit stable mappings for:

| Lifecycle status | Current material card | Intended result |
| --- | --- | --- |
| `entry_submit_sent`, `entry_fill_pending` | `trade_submitted` | Keep |
| `position_protected` | `position_protected` | Keep |
| `runner_protected` | `tp1_runner_active` | Keep |
| `lifecycle_closed` | `trade_closed` | Keep |

It also has a manually maintained unsafe-status set. Any other lifecycle status
returns no lifecycle-specific intent, after which a submitted Ticket can still
activate the generic `trade_submitted` fallback.

The following current lifecycle statuses reproduce that false fallback:

| Status family | Examples | Current visible defect |
| --- | --- | --- |
| Automated intermediate | `tp1_filled`, `runner_mutation_pending` | Repeats the old submit card during later processing |
| Recovery required | `protection_degraded`, `runner_mutation_failed`, `runner_reconciliation_mismatch` | Hides automatic recovery behind an old submit card |
| Hard stopped | `position_closed_protection_live`, `final_exit_unknown`, `settlement_blocked`, `review_blocked` | Can hide abnormal lifecycle state behind an informational submit card |

The typed lifecycle reducer already defines these states; the defect is that
the notification projector does not consume that complete typed decision.

### Current Delivery Behavior

`project_owner_notification_intents` sorts and truncates to five intents before
the delivery function reads existing ledger rows. The delivery loop later
suppresses already-sent or retry-exhausted rows.

Therefore this sequence is possible:

```text
project top five
-> all five are already sent
-> delivery suppresses all five
-> a sixth new critical intent is never considered in this run
```

The cap is a send-attempt budget, so it belongs after dedupe and retry
eligibility, not before them.

### Current Feishu Acknowledgement Behavior

Both Feishu send functions currently set `sent=true` for any HTTP status in the
2xx range. The response body is stored only as a preview.

For the current Feishu custom-robot response contract, transport success and
business success are separate facts. A response must not be marked sent when
its JSON body reports a non-zero business code.

### Current Monitor Unit Coverage

The monitor service explicitly checks the backend and runtime-signal watcher
timer/service. It does not include:

```text
brc-ticket-lifecycle-maintenance.timer
brc-ticket-lifecycle-maintenance.service
```

The lifecycle service is a one-shot unit, so `inactive` after a successful run
is valid. The lifecycle timer must remain active.

## Feishu Assessment Absorption And Architecture Choice

The Owner-provided Feishu assessment correctly identified the reproduced
fallback chain, broad HTTP success rule, pre-delivery five-item truncation, and
the difference between current-snapshot notification and immutable transition
delivery. Those findings are absorbed as defect evidence.

The current deployed notification contract remains authoritative for product
semantics: the Owner receives stable material states and abnormal intervention
states, not every internal lifecycle transition. Therefore this closure adopts
the diagnosis without turning the Owner into a lifecycle operator.

| Assessment proposal | Accepted fact or value | Current package decision | Reason |
| --- | --- | --- | --- |
| Complete lifecycle mapping | Yes | Classify every canonical status through Lifecycle Safety Core | Removes unknown fallback and taxonomy drift |
| TP1 pending and every transition get a card | Transition visibility matters | Keep automated intermediate states quiet; notify stable Runner protection or abnormal timeout/failure | Current Owner contract prefers stable material state over internal progress noise |
| Add many new notification kinds | More explicit event semantics are possible | Reuse the existing 9 product kinds | Typed safety state already determines positive, temporary-unavailable, or intervention outcome |
| Add transition/revision to dedupe identity | Same-kind escalation can otherwise dedupe | Preserve stable kind identity in this package | Temporary-unavailable to intervention changes kind and sends; repeated identical Owner action remains intentionally deduped |
| Add lifecycle notification outbox | Would preserve every transition | Do not add an outbox in this closure | It adds a second event authority and schema/cadence scope beyond the confirmed product model |
| Parse Feishu business result | Yes | Require HTTP and business-level success | Prevents false `sent` rows |
| Prevent five-item permanent loss | Yes | Apply cap after ledger eligibility | Preserves bounded cadence without starvation |

If a future Owner policy requires every funding-relevant transition to be
delivered, an immutable lifecycle-notification outbox becomes a separate
product decision. It is not necessary to close the current false fallback,
delivery starvation, acknowledgement, and monitor-coverage defects.

## Design Options

| Option | Projection correctness | Delivery correctness | Runtime change | Decision |
| --- | --- | --- | --- | --- |
| Add more statuses to the old unsafe set | Partial and drift-prone | None | Small | Reject |
| Add a second notification outbox or timer | Can be correct | Duplicates ledger and cadence | Large | Reject |
| Reuse typed lifecycle decision, move cap after eligibility, parse Feishu ACK, extend existing monitor units | Complete within current contract | Complete without schema change | Bounded | Adopt |

The adopted option removes duplicated lifecycle classification from the
notification layer and preserves one ledger, one monitor cadence, and one
delivery path.

## Lifecycle Projection Contract

### Typed Decision Input

For each latest lifecycle row, projection must obtain the existing typed Owner
feedback produced by `ticket_bound_lifecycle_owner_feedback`.

The notification projector uses only these fields:

```text
status
lifecycle_status
control_state
owner_action_required
reason
next_action
```

It must not recreate a second status taxonomy.

### Material State Rules

| Typed outcome | Material card | Owner action | Projection rule |
| --- | --- | --- | --- |
| Stable submit milestone | `trade_submitted` | No | Emit once for `entry_submit_sent` or `entry_fill_pending` |
| Stable protected milestone | `position_protected` | No | Emit once for `position_protected` |
| Stable Runner milestone | `tp1_runner_active` | No | Emit once for `runner_protected` |
| Completed | `trade_closed` | No | Emit once for `lifecycle_closed` |
| Automated intermediate | None | No | Stay quiet; do not fall back to Ticket submit |
| Recovery required, retry budget remains | None | No | Stay quiet while the system recovers; do not emit a false positive card |
| Hard stopped or unknown without explicit Owner action | `system_temporarily_unavailable` | No | Explain that automation cannot safely continue and the system is checking state |
| Retry exhausted or explicit intervention blocker | `intervention_required` | Yes | Name the bounded Owner action in plain language |

### Fallback Suppression Invariant

If a lifecycle row exists for a Ticket, its typed decision owns notification
classification. The Ticket-level `status=submitted` fallback may run only when
no lifecycle row exists.

Formally:

```text
lifecycle row exists
-> lifecycle decision returns a material intent or an intentional quiet result
-> never consult generic Ticket submitted fallback
```

This prevents later lifecycle states from replaying an earlier milestone.

### Incident Identity

Lifecycle abnormal states keep the existing stable correlation family:

```text
incident:lifecycle:<ticket_id>
```

A hard-stopped incident that later clears may generate one
`incident_recovered` card only if the original incident was actually sent.
Automated intermediate and recovery-required quiet states do not create an
incident row, so they cannot generate a false recovery card.

## Delivery Selection Contract

### Separation Of Concerns

The projector returns every unique material candidate in the bounded current
PG snapshot. The delivery layer then calculates eligibility and applies the
five-attempt cap.

```text
project candidates
-> merge current monitor fallback
-> normalize and dedupe identities
-> load current ledger state
-> suppress sent/exhausted identities and reopen active resolved incidents
-> severity/time ordering
-> select at most five delivery attempts
-> send and persist outcome
```

### Candidate Bound

The server monitor continues to consume the existing current-state repository
queries. Relevant history-like inputs are already query-bounded: fresh live
signals and current lifecycle rows are capped at **200**, while notification
ledger rows are capped at **1000**. This package adds no broader query and no
unbounded history scan.

The operational delivery cap remains **5 new or retryable cards per monitor
run**. Candidate projection does not add a second arbitrary fail gate; delivery
selection works inside the repository's existing bounded snapshot.

### Eligibility States

| Existing ledger state | Send eligible | Batch slot consumed | Result |
| --- | --- | --- | --- |
| No row | Yes | Yes | First attempt |
| `failed`, attempts below 3 | Yes | Yes | Retry |
| `sent` | No | No | Dedupe suppressed |
| `failed`, attempts at least 3 | No | No | Retry exhausted |
| `resolved` plus a currently active matching incident | Yes | Yes | Reopen a new incident episode and reset its three-attempt budget |

Suppressed and exhausted rows remain counted in the run summary, but they do
not occupy the five-attempt batch. Ledger rows are loaded in one bounded batch
query keyed by candidate dedupe keys; the implementation must not add one PG
query per candidate.

A resolved incident row is historical evidence that the prior episode closed,
not a permanent mute. When current PG facts project the same stable incident
again, delivery reopens the row, clears `resolved_at_ms`, and starts a new
three-attempt episode. This preserves the stable identity without suppressing a
real recurrence.

### Ranking

Eligible rows use the existing severity order:

```text
critical > warning > positive > info
```

Within one severity, older `occurred_at_ms` is delivered first so a sustained
stream cannot starve an already waiting card. Identity normalization and the
material-stage rules ensure this does not replay obsolete stages inside one
Ticket.

## Feishu Acknowledgement Contract

Create one pure response parser shared by text and interactive payload senders.

Its input is:

```text
HTTP status
raw response body
```

Its output contains:

```text
sent
status_code
business_code
business_message
response_body_preview
```

Success rules are:

1. HTTP status must be 2xx;
2. response body must be valid JSON object;
3. `code == 0` is success;
4. when `code` is absent, legacy `StatusCode == 0` is accepted;
5. non-zero code, invalid JSON, empty object, or missing recognized success
   field is failure.

The primary-versus-legacy field choice follows the official
[Feishu/Lark custom-bot guide](https://open.larksuite.com/document/uAjLw4CM/ukTMukTMukTM/bot-v3/use-custom-bots-in-a-group?lang=zh-CN),
which identifies `StatusCode` as a redundant compatibility field. Transport
2xx therefore cannot replace the business result.

Transport exceptions and HTTP errors remain failures. All bodies stay capped
to the existing 500-character preview, and no secret-bearing request data is
logged.

## Server Monitor Coverage

Add both lifecycle units to the monitor service command and default unit set:

```text
brc-ticket-lifecycle-maintenance.timer
brc-ticket-lifecycle-maintenance.service
```

Add only the service to `ONESHOT_INACTIVE_OK_UNITS`.

| Unit | Healthy states | Unhealthy condition | Owner projection |
| --- | --- | --- | --- |
| Lifecycle timer | active | failed, missing, or inactive | `system_temporarily_unavailable` |
| Lifecycle one-shot service | active, activating, or inactive after successful result | failed or unsuccessful result | `system_temporarily_unavailable` |
| Runtime monitor one-shot service | Existing behavior | Existing behavior | Existing behavior |

This is readonly inspection. It does not start, stop, restart, or repair any
unit.

## Schema And Migration Decision

No migration is required.

The existing `brc_server_monitor_notifications` columns already hold:

- stable kind and correlation identity;
- notification state and attempt count;
- Feishu response JSON;
- occurrence and resolution timestamps;
- Owner action requirement.

The richer Feishu acknowledgement fields are stored inside the existing
`feishu_response` JSON. A new table, outbox, status column, or dual-write path
would create authority duplication without adding required semantics.

## Cadence And Performance Impact

| Dimension | Current | After package | Impact |
| --- | --- | --- | --- |
| Monitor cadence | Every 10 minutes | Unchanged | None |
| Feishu attempt cap | 5 per run | 5 eligible attempts per run | Corrected semantics, no expansion |
| Feishu timeout | 10 seconds by runtime default | Unchanged | None |
| PG writes on quiet run | Zero notification delivery rows | Unchanged | None |
| Systemd reads | Backend plus watcher units | Adds 2 lifecycle-unit reads | Negligible bounded subprocess work |
| Runtime files | Zero new report files | Zero | Clear |

All subprocess work remains timeout-bounded. No production no-signal tick
creates JSON or Markdown output.

## Failure Semantics

| Failure | Fail behavior | Trading authority effect | Owner effect |
| --- | --- | --- | --- |
| Unknown lifecycle status | Typed reducer yields hard-stopped/unknown | No new exchange authority | Temporary-unavailable incident |
| Notification classification exception | Monitor run reports failure | None | Existing monitor incident path |
| Feishu HTTP 2xx with business error | Record failed attempt and retry within budget | None | Card remains undelivered and observable |
| Lifecycle timer unhealthy | Readonly monitor notifies | Does not start or stop lifecycle | Temporary-unavailable incident |

Notification failure must never become exchange-write authority, and it must
not block the lifecycle worker from protecting or reconciling a real position.

## File Boundary

### Files To Modify After Approval

```text
src/application/owner_notification.py
scripts/run_tokyo_runtime_server_monitor.py
deploy/systemd/brc-runtime-monitor.service
tests/unit/test_owner_notification_scenarios.py
tests/unit/test_owner_notification_delivery.py
tests/unit/test_runtime_monitor_frequency_policy.py
tests/unit/test_tokyo_runtime_server_monitor.py
tests/unit/test_tokyo_runtime_ops_health_lifecycle.py
```

### Files Not To Modify

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

No core execution file is required for this package.

## Acceptance Matrix

### Projection Acceptance

1. Every status in the typed lifecycle specification is classified by one
   parameterized test.
2. Automated intermediate and recovery-required states emit no false
   `trade_submitted` card.
3. Unknown or hard-stopped states emit temporary-unavailable unless explicit
   intervention rules apply.
4. Retry-exhausted and explicit Owner-intervention blockers emit
   `intervention_required`.
5. The four stable milestone cards remain unchanged.
6. Incident recovery appears only after an actually sent incident clears.

### Delivery Acceptance

1. Five already-sent high-ranked candidates do not starve a sixth new intent.
2. Five retry-exhausted candidates do not starve a new intent.
3. At most five actual sends or retries occur in one run.
4. A resolved incident that becomes active again sends once with a reset retry
   budget.
5. Dry-run creates zero delivery rows.
6. HTTP 200 with `code=0` succeeds.
7. HTTP 200 with non-zero `code` fails and consumes one retry attempt.
8. Invalid or unrecognized response JSON fails closed.

### Monitor Acceptance

1. The deployed unit declares the lifecycle timer and service explicitly.
2. Inactive successful one-shot lifecycle service is healthy.
3. Inactive lifecycle timer is unhealthy.
4. Failed lifecycle service is unhealthy.
5. Monitor tests prove no unit-control mutation command is introduced.

## Rollout And Stop Conditions

### Local Phase

After Owner approval:

1. implement on the focused `codex/*` branch;
2. run targeted projection, delivery, and systemd tests;
3. run the relevant notification and monitor regression suites;
4. run current-doc, output-scope, and production-file-I/O validators;
5. produce a deploy-readiness report without touching Tokyo.

### Deployment Phase

Deployment is a separate action. Before it, verify:

- the first work package and this package are both locally green;
- the exact release commit and pinned dependency set are recorded;
- the current live Ticket, position, and open-order state are read-only checked;
- deployment does not create a notification replay storm;
- rollback restores code and unit definitions without mutating PG lifecycle
  authority.

### Hard Stops

Stop without deployment if any of these occurs:

- lifecycle classification diverges from Lifecycle Safety Core;
- a sent or resolved event can be replayed;
- a business-error response can be persisted as sent;
- notification changes touch exchange-write authority;
- production file-I/O audit reports a new cadence path;
- implementation requires a migration or a second notification ledger.

## Chain Position

```text
Live Enablement State Before:
  real lifecycle may progress, but notification projection and delivery have
  classification, starvation, acknowledgement, and monitor-coverage gaps

Blocker Removed Or Reclassified:
  owner_notification_projection_delivery_certification_gap

Live Enablement State After Local Acceptance:
  notification behavior is implementation-complete and deploy-pending;
  current Tokyo runtime remains unchanged

Capability Unlocked:
  trustworthy material lifecycle cards, bounded fair delivery, business-level
  Feishu acknowledgement, and explicit lifecycle worker health observation

Next Engineering Bottleneck:
  combined release review and separately authorized Tokyo deployment
```

## Confirmation Gate

This design is a draft for Owner confirmation. No implementation, commit,
deployment, service change, production notification mutation, or server runtime
intervention is authorized by this document.
