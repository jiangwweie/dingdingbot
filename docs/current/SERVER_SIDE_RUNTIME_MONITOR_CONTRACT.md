---
title: SERVER_SIDE_RUNTIME_MONITOR_CONTRACT
status: CURRENT
authority: docs/current/SERVER_SIDE_RUNTIME_MONITOR_CONTRACT.md
last_verified: 2026-07-02
---

# Server-Side Runtime Monitor Contract

## Purpose

The production monitor owner is the Tokyo runtime environment, not a local
Codex heartbeat or local cache reader.

The target operating model is:

```text
Tokyo runtime
-> Tokyo server-side readonly monitor timer
-> classify quiet / notify
-> send Feishu notification only when useful
-> keep healthy waiting periods quiet
```

Local monitor artifacts remain useful for development diagnostics, postdeploy
verification, and replay-style investigation. They are not a production
fallback path, are not the production source of runtime truth, and must not
decide whether the Owner should be notified.

## Core Rule

```text
Server owns recurring production monitoring.
Local owns development diagnostics only.
FinalGate and Operation Layer remain action-time execution gates only.
```

After PG cutover, the server monitor reads Tokyo PG current state plus readonly
system/process/deploy health. It may classify the current state as quiet or
notify and may send a Feishu message. It must not create order authority or
call execution gates.

Generated runtime artifacts may be read only as diagnostics or export-health
checks. They must not decide production quiet/notify, fresh-signal state,
ticket state, or Owner intervention state when PG lineage exists.

## Current Problem

The local heartbeat / local cache monitor model is a development-stage
transition. It has these limitations:

| Concern | Local heartbeat model | Production target |
| --- | --- | --- |
| Monitor location | Local Codex session | Tokyo server timer |
| Runtime truth source | Local cache / output artifacts | Tokyo PG current state and readonly server facts |
| Cache freshness | Can become stale or schema-stale | Server reads current runtime facts directly |
| Owner notification | Local process decides from cached state | Server classifies quiet / notify and pushes Feishu |
| Trading safety | Must not depend on local monitor | Still protected by FinalGate and Operation Layer |

## Target Responsibilities

| Layer | Responsibility | Production role |
| --- | --- | --- |
| `tokyo_server_monitor` | Run recurring readonly status checks on Tokyo | Primary monitor path |
| `feishu_notifier` | Push only Owner-relevant events | Primary notification path |
| `local_monitor_sequence` | Manual diagnostic, postdeploy check, development artifact refresh | Development only |
| `codex_heartbeat` | Development automation and drift audit only | Not production monitor owner |
| `FinalGate` / `Operation Layer` | Official action-time execution gates | Unchanged, never monitor-owned |

## Allowed Effects

The server-side monitor may:

- read runtime status;
- read watcher status;
- read public facts and account-safe facts;
- read process, systemd, deploy, and artifact health;
- write PG server monitor run records and optional exports;
- send Feishu notifications;
- record notification dedupe state;
- retry failed notifications without changing trading authority.

## Forbidden Effects

The server-side monitor must not:

- bypass FinalGate;
- bypass Operation Layer;
- call exchange write paths;
- create orders;
- withdraw or transfer funds;
- mutate credentials or secrets;
- mutate live profiles;
- mutate order-sizing defaults;
- turn a replay, synthetic, local cache, or notification artifact into live
  RequiredFacts or submit authority.

## Notification Policy

Healthy waiting must stay quiet. Notifications exist to reduce missed
opportunities and surface real intervention needs, not to provide generic
heartbeat chatter.

| Scenario | Behavior |
| --- | --- |
| Healthy waiting for market | Do not notify |
| Fresh signal appears | Notify |
| Promotion candidate appears | Notify with dedupe when policy requires it |
| Action-Time Ticket is created | Notify |
| Candidate approaches action-time boundary | Notify |
| FinalGate passes or rejects | Notify |
| Real submit accepted | Notify |
| Protection fails or detaches | Must notify |
| Reconciliation mismatch appears | Must notify |
| Non-market blocker appears | Notify with blocker class |
| Watcher, systemd, deploy, or readiness chain fails | Notify |
| Server-side public facts or account-safe facts fail | Notify as runtime data gap |
| Pure JSON export stale | Export issue only; not production trading failure |
| Feishu send fails | Record failure and retry; do not change trading state |

Owner-facing messages should use product language such as:

```text
运行中
等待机会
处理中
暂不可用
需要介入
无需操作
```

Internal names such as `FinalGate`, `Operation Layer`, `RequiredFacts`,
`candidate`, and `authorization` may appear only in audit or developer detail,
not as the primary Owner message.

## Dedupe Requirement

The notifier must prevent repeated noise for the same condition.

Minimum dedupe identity:

| Field | Meaning |
| --- | --- |
| `automation_id` | Monitor automation identity |
| `strategy_group_id` | StrategyGroup when applicable |
| `symbol` | Candidate symbol when applicable |
| `blocker_class` | Current blocker class or runtime failure class |
| `checkpoint` | Monitor checkpoint or action-time boundary |
| `first_seen_at` | First time this condition was observed |
| `last_notified_at` | Last notification time for the same condition |

The dedupe state is notification state. It is not trading authority, strategy
policy, or runtime safety state. After PG cutover, dedupe state should live in
PG monitor/notification tables, not a local file that becomes production truth.

## Migration Plan

### Phase 1: Add Server Readonly Monitor

Create a Tokyo-side monitor entrypoint such as:

```text
scripts/run_tokyo_runtime_server_monitor.py
```

It should read PG current state, classify quiet / notify, write a server-side
monitor run record, optionally export an artifact, and call the Feishu notifier
only when the notification policy requires it.

### Phase 2: Add Systemd Timer

Add:

```text
brc-runtime-monitor.service
brc-runtime-monitor.timer
```

Default interval should be in the 5 to 15 minute range unless a current runtime
decision sets a different frequency. Fresh-signal or action-time windows may
use a shorter burst mode, but healthy waiting should remain quiet.

### Phase 3: Add Feishu Dedupe

Implement the dedupe identity in PG monitor notification tables or an equivalent
server-side runtime store that is not a repo/local-cache truth source. A failed
Feishu send should be retried and recorded without changing runtime safety or
order authority.

### Phase 4: Remove Local Heartbeat From Production

Local heartbeat and local monitor sequence become:

- manual diagnostic;
- postdeploy verification;
- drift audit against the server monitor contract.

They must not remain the production source for Owner notification decisions and
must not be used as a production fallback when server-side monitoring fails.

## Acceptance

The server-side monitor migration is accepted only when:

| Requirement | Done when |
| --- | --- |
| Server monitor ownership | Tokyo timer runs the readonly monitor without local Codex dependency |
| Quiet path | Healthy waiting produces no Feishu notification |
| Notify path | Fresh signal, action-time approach, non-market blocker, or runtime failure sends one deduped notification |
| Runtime source | Monitor reads Tokyo PG current state and readonly server facts, not local cache, generated JSON, or repo files as production truth |
| Safety boundary | Tests prove no FinalGate, Operation Layer, exchange write, order create, withdrawal, transfer, credential mutation, live-profile mutation, or sizing mutation |
| Local removal from production | Local monitor remains available for development diagnostics only and is not production notification owner or fallback |

## Chain Position

```text
chain_position: daily_live_enablement_status
strategy_group_id: active WIP StrategyGroups
symbol: active candidate pool
stage: monitor_runtime_ownership_boundary
first_blocker: monitor execution location is still local-development oriented
evidence: local heartbeat and cache-monitor artifacts are not Tokyo runtime truth
next_action: move recurring monitor ownership to Tokyo server-side readonly timer with Feishu notifier
stop_condition: server-side monitor proves quiet/no-signal without local cache dependency, or reports real runtime blocker
owner_action_required: no
authority_boundary: server-side monitor remains readonly and must not call FinalGate, Operation Layer, or exchange write
```
