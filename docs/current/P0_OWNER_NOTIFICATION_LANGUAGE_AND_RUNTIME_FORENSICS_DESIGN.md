---
title: P0_OWNER_NOTIFICATION_LANGUAGE_AND_RUNTIME_FORENSICS_DESIGN
status: OWNER_APPROVED_FOR_IMPLEMENTATION
authority: docs/current/P0_OWNER_NOTIFICATION_LANGUAGE_AND_RUNTIME_FORENSICS_DESIGN.md
last_verified: 2026-07-12
---

# P0 Owner Notification Language And Runtime Forensics Design

## Decision

The final proactive medium-scale engineering package before natural Live
calibration is:

```text
P0 Owner Notification Language And Runtime Forensics Closure
```

It turns PG/runtime events into plain Owner notifications, sends static Feishu
cards only for material transitions, and provides one read-only server
forensics command consumed by the existing `runtime-signal-forensics` Skill.

It does not add a frontend, MCP service, Feishu callback, policy mutation,
runtime authority, exchange write, new trading state machine, or file-backed
report path.

## Current Defect

The current server monitor directly renders internal fields:

```text
blocker_class
checkpoint
reasons
evidence_ref
```

Production history from 2026-07-05 through 2026-07-12 shows that detection is
broad but Owner feedback is unbalanced:

| Current event family | Monitor decisions | Existing notification behavior | Defect |
| --- | ---: | --- | --- |
| Healthy waiting | 833 quiet runs | No send | Correct |
| Watcher/service failure | 91 notify runs | Three dedupe rows, 21 send attempts | Transient/runtime jargon and excessive retries |
| Fresh signal | 5 notify runs | Signal/promotion checkpoints can notify separately | One opportunity can look like multiple unrelated alerts |
| TP1 reference missing | 151 notify runs | One deduped send | Failure is visible, but positive TP1/Runner progress is absent |
| Successful order lifecycle | Not projected as Owner events | No submit/fill/protection/TP1/Runner/close cards | Real trading feedback is incomplete |
| Incident recovery | Notification row becomes `resolved` | No recovery card | Owner sees the problem but not its resolution |

The defect is not insufficient logging. It is the absence of one typed Owner
language boundary and one material-transition identity.

## Authority Model

```text
PG/runtime facts decide what happened.
OwnerNotificationIntent decides how to explain it.
Feishu renderer decides presentation only.
Notification ledger decides dedupe/retry only.
Forensics reads and explains; it never mutates.
```

The notification layer must not decide Tradeability, Runtime Safety State,
FinalGate, Operation Layer, protection truth, reconciliation truth, policy, or
strategy review.

## Typed Owner Notification Intent

Create a pure typed application model with these fields:

```text
notification_kind
severity
correlation_id
strategy_group_id
symbol
side
occurred_at_ms
headline
current_state
result_summary
plain_reason
next_system_action
owner_action_required
owner_action
technical_refs
template_version
```

`technical_refs` remain available to PG audit and runtime forensics. They must
not appear in the primary Feishu card.

### Notification Kinds

| Kind | Correlation | Trigger | Owner meaning |
| --- | --- | --- | --- |
| `opportunity_detected` | `signal:<signal_event_id>` | Fresh validated Live signal | The system found a current opportunity |
| `opportunity_not_executed` | same signal | Signal becomes terminal with no submitted Ticket | The opportunity ended without an order and why |
| `trade_submitted` | `ticket:<ticket_id>` | Real exchange command is submitted/accepted | A real order entered venue processing |
| `position_protected` | same Ticket | Lifecycle reaches `position_protected` | Entry is confirmed and protection is active |
| `tp1_runner_active` | same Ticket | Lifecycle reaches `runner_protected` after TP1 | Partial profit is taken and the runner is protected |
| `trade_closed` | same Ticket | Lifecycle reaches `lifecycle_closed` | The trade is closed, settled, and reviewable |
| `intervention_required` | `incident:<stable identity>` | Hard safety, unknown exchange outcome, unprotected position, hard process failure | Owner attention is required or risk is abnormal |
| `system_temporarily_unavailable` | stable incident | Persistent infrastructure/data failure | Automation is temporarily unavailable |
| `incident_recovered` | same incident | Previously sent incident is no longer current | The reported problem has recovered |

`entry_filled`, `position_protected`, `tp1_filled`, and intermediate runner
mutation states remain audit events. The Owner receives the latest stable
material state rather than every internal transition.

## Scenario Projection

One pure projector consumes current and windowed PG facts and produces zero or
more `OwnerNotificationIntent` values.

Priority is:

```text
unprotected / unknown exchange result / hard stop
-> persistent system failure
-> closed trade
-> TP1 + protected runner
-> protected position
-> submitted trade
-> opportunity terminal without submit
-> fresh opportunity
```

The projector may produce multiple unrelated correlations, but the monitor may
send at most five new/retryable cards per run. Within one Ticket correlation,
only the newest material stage is emitted when several stages become visible
in the same monitor window.

## Dedupe, Retry, And Recovery

Extend `brc_server_monitor_notifications`; do not add a second notification
table.

Add current/audit fields:

```text
notification_kind
severity
correlation_id
template_version
owner_action_required
occurred_at_ms
resolved_at_ms
```

The stable dedupe identity is:

```text
automation_id + correlation_id + notification_kind
```

The template version is stored but is not part of the dedupe identity, so a
deployment must not replay historical events merely because wording changed.

Rules:

1. A sent material transition is never resent.
2. A failed delivery retries on later monitor runs up to three total attempts.
3. Exhausted delivery remains `failed` and is visible to health/forensics; it
   does not retry forever.
4. A resolved incident creates one `incident_recovered` intent only when the
   original incident was actually sent.
5. Healthy waiting resolves obsolete engineering notifications without sending
   a generic recovery card; recovery cards are reserved for material incidents.

## Static Feishu Card

Use the existing custom-robot Webhook and `msg_type=interactive` with a static
card JSON payload.

The card contains only:

```text
headline
strategy / symbol / side
current state
result
plain reason
next system action
whether Owner action is required
occurred time
diagnostic correlation id
```

Color mapping:

| Severity / kind | Header color |
| --- | --- |
| Opportunity / processing | blue |
| Protected / TP1 / closed profit / recovery | green |
| Not executed / informational close | grey |
| Temporarily unavailable | orange |
| Intervention required / unprotected / unknown outcome | red |

The card contains no callback component, button, selection control, URL action,
or write operation. Card send failure retries the same payload; it does not fall
back to text because that can duplicate one event through two formats.

## Plain-Language Rules

Primary cards must answer:

```text
What happened?
What is the current result?
Why did it stop or continue?
What will the system do next?
Does the Owner need to act?
```

These strings are forbidden in primary cards:

```text
FinalGate
Operation Layer
RequiredFacts
blocker_class
checkpoint
runtime_data_gap
evidence_ref
raw PG identifiers other than the short diagnostic correlation id
```

Templates are versioned Python code, not YAML/JSON/Markdown runtime files.

## Runtime Signal Forensics

Create one Tokyo-local, read-only command:

```text
scripts/ops/query_runtime_signal_forensics.py
```

Arguments:

```text
--database-url / PG_DATABASE_URL
--since <ISO-8601>
--until <ISO-8601>
--strategy-group-id <optional>
--symbol <optional>
--side <optional>
--limit <bounded; default 200; max 1000>
--include-systemd
--json
```

It reads PG signal, promotion, lane, Ticket, exchange command, lifecycle,
outcome, monitor, and notification rows for the requested window. Optional
systemd collection is local and timeout-bounded. It prints one structured
stdout response and creates zero files.

The response separates:

```text
coverage
signals
chain_progress
orders_and_lifecycle
notifications
system_health
first_blocker
owner_action_required
safety_invariants
```

The existing `.agents/skills/runtime-signal-forensics/SKILL.md` becomes the
natural-language interface. It invokes the command over the approved Tokyo SSH
control plane, converts relative dates to absolute Asia/Shanghai windows, and
explains the first missing/rejected object in Chinese.

No MCP server is added.

## Cadence And Performance

| Dimension | Boundary |
| --- | --- |
| Monitor cadence | Existing ten-minute timer plus existing deployment/manual invocations; no new recurring timer |
| Max cards | Five per monitor run |
| Network timeout | Existing bounded timeout per send; total monitor work remains bounded |
| Retry | Maximum three attempts per material notification |
| PG growth | One row per correlation + notification kind; no row per quiet tick |
| No-signal files | Zero JSON/MD/report files |
| Forensics | Explicit user/agent invocation only; bounded rows and subprocess timeouts |
| Disk | Zero new runtime artifacts; stdout only |
| Retention | Existing PG retention policy; no sidecar archive |

## Failure Handling

| Failure | Result |
| --- | --- |
| Unknown lifecycle status | Fail closed to one plain `system_temporarily_unavailable` intent; preserve technical ref |
| Missing correlation identity | Do not send; record monitor projection gap |
| Card payload invalid | Mark failed and retry up to cap |
| Webhook absent | Keep pending/configuration fact; do not expose secret values |
| PG unavailable | Existing runtime-data incident path; no file fallback |
| Forensics PG unavailable | Return `runtime_data_gap:pg_current_projection_unavailable` |
| systemd command timeout | Report incomplete system coverage; do not infer trading failure |

## Acceptance

1. Every notification is produced from `OwnerNotificationIntent`.
2. Fresh signal, no-order terminal result, submitted trade, protected position,
   TP1 runner, closed trade, intervention, temporary outage, and recovery have
   explicit tests.
3. One signal does not send separate signal/promotion/lane/Ticket jargon cards.
4. Positive lifecycle stages are visible without weakening safety alerts.
5. Delivery retries stop after three attempts.
6. Static cards contain no callbacks or technical vocabulary.
7. The forensics command reconstructs a bounded PG chain and notification
   outcome for an absolute time window.
8. The Skill answers recent-signal/no-trade/no-notification questions through
   the command rather than ad hoc report files.
9. No exchange write, FinalGate, Operation Layer, policy, strategy, sizing,
   profile, credential, withdrawal, or transfer authority is introduced.
10. Production no-signal cadence creates zero JSON/MD files and production
    file-I/O audit remains clear.

## Chain Position

```text
chain_position: action_time_boundary
strategy_group_id: CPM-RO-001 / MPG-001 / MI-001 / SOR-001 / BRF2-001
symbol: 22 active candidate scopes
stage: release_certified_waiting_for_natural_signal
first_blocker: market_wait_validated
evidence: production capability is certified; current Owner feedback is jargon-heavy and does not close successful/terminal notification lifecycle
next_action: implement typed Owner notification intents, static cards, bounded delivery ledger, and read-only runtime forensics
stop_condition: notification/forensics acceptance passes and proactive core engineering freezes until a natural signal or safety incident appears
owner_action_required: no
authority_boundary: no strategy/policy/risk/scope/FinalGate/Operation Layer/exchange-write expansion; no Feishu callbacks
```
