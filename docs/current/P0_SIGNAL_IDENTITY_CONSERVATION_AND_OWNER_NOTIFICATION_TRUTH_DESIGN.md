---
title: P0_SIGNAL_IDENTITY_CONSERVATION_AND_OWNER_NOTIFICATION_TRUTH_DESIGN
status: CURRENT_DESIGN
authority: docs/current/P0_SIGNAL_IDENTITY_CONSERVATION_AND_OWNER_NOTIFICATION_TRUTH_DESIGN.md
last_verified: 2026-07-13
---

# P0 Signal Identity Conservation And Owner Notification Truth

## Problem

The 2026-07-13 10:00 watcher tick reported one legacy runtime-ready signal but
persisted no `brc_live_signal_events` identity. The watcher nevertheless sent an
Owner message saying that an Action-Time Ticket should be materialized. The
message exposed internal vocabulary and could not name StrategyGroup, symbol,
side, event time, signal identity, or the first materialization blocker.

This is one systemic defect class:

```text
anonymous observation readiness
-> Owner opportunity notification
without
PG signal identity
```

It is not acceptable to fix only the message copy. The signal identity,
materialization outcome, monitor classification, and Owner notification must
share one authority boundary.

## Decision

PG current state is the only authority for an Owner claim that a trading
opportunity exists.

```text
production evaluator result
-> named PG live signal event
-> promotion / lane / Ticket
-> PG-backed Owner state
-> plain-language notification
```

A legacy `would_enter` or ready count without `signal_event_id` is diagnostic
input only. It must be classified as a signal-identity engineering gap, must
not be called a trading opportunity, and must never grant Ticket or submit
authority.

## Alternatives

| Option | Result | Decision |
| --- | --- | --- |
| Rewrite the existing English message only | Easier to read but preserves false opportunity claims | Reject |
| Suppress every anonymous-ready notification | Avoids noise but can hide a real producer-to-PG handoff defect | Reject |
| Bind opportunity language to PG identity and persist anonymous-ready failures in the existing process-outcome model | Preserves truth, makes the defect diagnosable, and adds no second authority | Adopt |

## Runtime Contract

### Named Signal

An Owner opportunity message requires all of:

```text
strategy_group_id
symbol
side
event_spec_id
event_time_ms
observed_at_ms
expires_at_ms
signal_event_id
```

The signal must be fresh, execution-eligible, and present in
`brc_live_signal_events`.

### Anonymous Ready

When the observation layer reports one or more ready rows but PG writes no
signal identity, the watcher must expose:

```text
status=runtime_signal_identity_gap
owner_state=temporarily_unavailable
order_created=false
exchange_write_called=false
```

The diagnostic must preserve the candidate StrategyGroup, symbol, side,
runtime instance, event-time reference, and exact first blocker whenever those
facts exist. Missing identity fields remain an explicit projection gap.

### Durable Failure Conservation

Use `brc_runtime_process_outcomes`; do not create another table or file.

```text
process_name=live_signal_materialization
scope_key=lane:<StrategyGroup>:<symbol>:<side>
source_watermark=<runtime instance + event time or signal identity>
first_blocker=<exact materialization blocker>
```

No-signal ticks write no process outcome. A later successful materialization
for the same lane replaces the current failed outcome. An expired repeated
event records a non-failure market/noop result rather than a persistent
engineering failure.

## Owner Notification Ownership

The production watcher must not send Owner Feishu messages directly. The
watcher's in-process dedupe state disappears on every systemd oneshot restart
and is not PG authority. Production notification ownership remains exclusively:

```text
watcher writes PG signal or process outcome
-> Tokyo server monitor reads PG current state
-> typed Owner notification intent
-> PG dedupe
-> Feishu
```

The watcher may emit structured stdout for developer diagnostics, but webhook
configuration does not make it an Owner notifier.

## Owner Notification Contract

The server-monitor message must be generated from the authoritative PG
post-observation state, not from `runtime_ready_signal_count` alone.

| Current fact | Owner message | Owner action |
| --- | --- | --- |
| Healthy and no PG signal | No message | None |
| Anonymous ready, no PG signal identity | `信号状态不一致，未下单。系统将继续处理，无需操作。` | None |
| Named fresh PG signal | `发现交易机会：<StrategyGroup> / <symbol> / <direction>。系统正在检查并处理，无需操作。` | None |
| Named pre-submit blocker | `该机会未执行：<plain reason>。系统未下单，无需操作。` | None unless policy/safety says otherwise |
| Submitted/protected lifecycle state | Use the existing typed Owner notification templates | According to lifecycle state |

Primary Owner text must not contain `runtime`, `operator`, `PG`, `Action-Time`,
`materialize`, evidence refs, routes, or raw blocker codes.

## Cadence And Performance

| Dimension | Contract |
| --- | --- |
| Cadence | One bounded evaluation per watcher tick; process outcomes only when a would-enter candidate exists |
| No-signal file writes | `0` JSON/MD files |
| PG writes | `0` for no-signal; at most one current process-outcome upsert per would-enter lane plus existing signal writes |
| CPU | No new replay or broad builder in watcher cadence |
| Timeout | Existing watcher and notification timeouts remain authoritative |
| Disk | No new files or report directories |
| Retention | Existing PG current/audit retention applies |

## Safety Boundary

This design does not change strategy semantics, candidate scope, capital,
leverage, sizing, live profile, FinalGate, Operation Layer, protection, or
exchange-write authority. Notification state is never trading authority.

## Acceptance

1. The captured `ready_count=1` and empty `signal_event_ids` shape produces a
   named identity-gap result; the watcher sends no direct Feishu message and
   the server monitor sends the plain Chinese notification.
2. A named PG signal produces an opportunity message containing StrategyGroup,
   symbol, and direction.
3. Expired, observe-only, and no-action rows never produce an opportunity
   message.
4. Materialization failure is queryable from PG by lane and exact blocker.
5. Same-lane success clears the current failed process outcome.
6. Duplicate ticks preserve event identity and notification dedupe.
7. All six current Event Specs retain producer-to-PG positive and negative
   coverage.
8. Production file-I/O audit reports `performance_risk.status=clear`.

## Chain Position

```text
chain_position: fresh_signal_promotion
strategy_group_id: current five StrategyGroups
symbol: current 22 candidate scopes
stage: anonymous_runtime_ready_not_conserved_to_pg
first_blocker: current_projection_gap
next_action: bind opportunity notification and durable failure evidence to named PG signal identity
stop_condition: every execution-grade observation creates a named PG signal or one durable lane-scoped blocker
owner_action_required: no
authority_boundary: observation readiness and notification never grant Ticket or exchange-write authority
```
