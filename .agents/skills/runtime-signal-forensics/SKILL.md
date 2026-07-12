---
name: runtime-signal-forensics
description: Use this skill whenever the user asks what signal the system detected yesterday/recently, why no trade happened, whether a theoretically tradable signal was missed, whether the reason was market-no-opportunity versus engineering/scope/safety blockage, why the Owner did not receive a Feishu/server-monitor notification, or asks for a plain-language market/strategy/action-time explanation. This skill should trigger even if the user does not use words like "forensics" or "no-trade"; phrases such as "昨天检测了什么", "有没有该交易没交易", "是不是市场没机会", "为什么没进交易链路", "推到哪一步", "为什么没收到通知", and "举个例子" require this workflow.
user-invocable: true
---

# Runtime Signal Forensics

## Purpose

Answer one Owner question:

```text
What did the system actually detect, did any theoretically tradable signal fail
to trade, and was no-trade caused by market conditions or by a system boundary?
```

This skill is deliberately narrower than architecture, planning, or broad
chain-position work. It turns runtime evidence into a plain explanation of:

- detected signals;
- strategy and symbol involved;
- market facts that were satisfied or not satisfied;
- how far the signal moved in the trading chain;
- the concrete reason it did not become a real order;
- whether server-side monitor and Feishu notification reflected the event;
- whether Owner authorization is required.

## Required Context

Read these first:

```text
AGENTS.md
docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md
docs/current/PRE_TRADE_RUNTIME_CONTRACT.md
docs/current/MAIN_CONTROL_DAILY_LIVE_ENABLEMENT_TABLE_CONTRACT.md
docs/current/WIP_AND_STOP_RULE_CONTRACT.md
docs/current/TRADEABILITY_DECISION_CONTRACT.md
docs/current/RUNTIME_CONTROL_STATE_DB_ARCHITECTURE.md
docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md
.agents/skills/chain-position/SKILL.md
```

If the user asks about a relative date such as "yesterday", convert it to an
absolute date using the current runtime timezone before reporting.

## Evidence Priority

Use **PG current state** and **audit lineage** for production questions.
Generated JSON/MD files are not a fallback source for current trading state.

Use this authority order:

1. Tokyo PG current state and audit lineage for signal, promotion, lane,
   ticket, policy, fact, FinalGate, Operation Layer, protection,
   reconciliation, and monitor state.
2. Tokyo DB-backed read models or API responses derived from PG projections.
3. Tokyo watcher, monitor, and deploy journals for runtime/process evidence.
4. Tokyo release metadata and deploy-health state from the official deploy path.
5. Archive-only historical evidence only when the user explicitly asks for
   provenance recovery.
6. Docs/contracts only to explain allowed meanings, not to invent facts.

Do not treat generated report files, task-packet exports, developer caches, old
watcher exports, or generated report timestamps as production truth. If
PG/current read models are unavailable, classify the answer as
`runtime_data_gap` and name the missing current projection instead of falling
back to files.

Never claim "market had no opportunity all day" unless the queried time window
has continuous watcher/monitor coverage or an explicit daily PG projection
proving no fresh eligible signal for that window.

Never claim "the system did not notify" as equivalent to "the system did not
detect a signal." Notification is a separate layer after detection and monitor
classification. Inspect the PG-backed monitor decision and notification state
before explaining missed notifications.

## Read-Only Collection

Use read-only commands only. Do not deploy, restart services, mutate files,
call FinalGate, call Operation Layer, or call exchange-write endpoints.

### Primary Forensics Command

Use the deployed bounded command before writing ad hoc PG or systemd queries:

```bash
ssh tokyo "cd /home/ubuntu/brc-deploy/app/current && set -a && source /home/ubuntu/brc-deploy/env/live-readonly.env && source /home/ubuntu/brc-deploy/env/runtime-monitor.env && set +a && timeout 25s /home/ubuntu/brc-deploy/venvs/brc-bnb-prelive-20260601/bin/python scripts/ops/query_runtime_signal_forensics.py --start '<ISO-8601 start with offset>' --end '<ISO-8601 end with offset>' --include-systemd"
```

Map optional Owner scope into `--strategy-group-id`, `--symbol`, and `--side`.
Use an absolute time window with an explicit offset. For Shanghai relative-date
questions, yesterday means `00:00:00+08:00` through the next
`00:00:00+08:00`; do not silently use server UTC day boundaries. Keep the
default row limit at 200 and never exceed `--limit 1000`.

The command is **stdout-only**, reads PG audit lineage directly, masks database
configuration, and reports all forbidden effects as false. It has no output,
apply, submit, policy, sizing, profile, callback, or exchange-write flags.

If the command itself fails, classify that failure first:

| Failure | Classification | Fallback |
| --- | --- | --- |
| PG unavailable or schema missing | `current_projection_gap` | Direct read-only PG table/column diagnosis |
| SSH or timeout failure | `runtime_data_gap` | Read-only SSH/systemd/network diagnosis |
| Invalid/reversed window | query error | Correct the absolute time window and rerun |
| Missing deployed command | deploy/readiness gap | Verify release head and deployed script path |

Only after recording that first failure may direct read-only PG and journal
commands be used as a diagnostic fallback. Generated JSON/MD files remain
forbidden as current-state fallback.

Collect current state from PG-backed read-only sources. Required current
objects are:

```text
live_signal_events
promotion_candidates
action_time_lane_inputs
action_time_tickets
runtime_fact_snapshots
watcher_coverage
runtime_safety_state_snapshots
monitor_decisions
notification_attempts
operation_submit_commands
protection_state
reconciliation_state
review_outcomes
```

If the operator only has historical files and no PG access, report
`runtime_data_gap:pg_current_projection_unavailable`. Do not reconstruct current
truth from generated JSON/MD.

For a date-window question, also collect:

```text
journalctl -u brc-runtime-signal-watcher.service --since <start> --until <end>
journalctl -u brc-runtime-monitor.service --since <start> --until <end>
systemctl status --no-pager brc-runtime-signal-watcher.service
systemctl status --no-pager brc-runtime-monitor.service
systemctl list-timers --all --no-pager brc-runtime-signal-watcher.timer brc-runtime-monitor.timer
```

For Feishu notification questions, verify only variable presence, not secret
values:

```text
/home/ubuntu/brc-deploy/env/runtime-monitor.env
/home/ubuntu/brc-deploy/env/live-readonly.env
```

Look only for these variable names and mask values:

```text
BRC_RUNTIME_MONITOR_FEISHU_WEBHOOK_URL
BRC_SIGNAL_WATCHER_FEISHU_WEBHOOK_URL
FEISHU_WEBHOOK_URL
BRC_RUNTIME_MONITOR_FEISHU_WEBHOOK_SECRET
BRC_SIGNAL_WATCHER_FEISHU_WEBHOOK_SECRET
FEISHU_WEBHOOK_SECRET
```

## Interpretation Rules

### Recursive Why Loop

Do not stop at a label such as "no authorization", "FinalGate not reached",
"no candidate", or "waiting for market". For every no-trade answer, keep asking
"why did the previous object not exist?" until the answer reaches one of these
terminal classes:

| Terminal class | Meaning | May stop? |
| --- | --- | --- |
| `objective_market_condition_not_satisfied` | The strategy/fact matrix says the required market condition is false, stale, or below threshold | yes |
| `engineering_handoff_gap` | A valid upstream signal existed, but the next machine object was not materialized | no; propose the repair |
| `scope_or_policy_gap` | The signal is outside selected StrategyGroup/symbol/side/profile policy | no; name the exact Owner decision |
| `runtime_safety_or_reconciliation_gap` | Position/order/protection/account state blocks next attempt | no; name the official recovery/reconciliation step |
| `current_projection_gap` | PG/readmodel state is unavailable, inconsistent, or insufficient to prove the chain | no; say which current projection must be repaired |

Use this drill-down order:

```text
detected signal?
-> is the PG-backed monitor decision newer than the relevant signal/lane state?
-> runtime lane or strategy-group preview?
-> if preview: does it have no_runtime_start / no_execution_permission?
-> if runtime lane: status waiting_for_signal, blocked, ready_for_prepare, or ready_for_final_gate_preflight?
-> signal input record present?
-> shadow_candidate_id or prepared_authorization_id present?
-> FinalGate reached?
-> Operation Layer reached?
-> protected submit attempted?
-> did server monitor classify quiet or notify?
-> if notify: was Feishu configured, attempted, sent, suppressed, or skipped?
```

For each missing object, name the previous object and the exact reason it did
not advance. Example:

```text
prepared_authorization_id is missing because the signal input record is missing.
The signal input record is missing because the runtime lane is blocked by
NEXT-ATTEMPT-POSITION-ORDER-CONFLICT. That is a reconciliation/safety gap, not
a market no-signal conclusion.
```

### Current Projection Freshness

Before using monitor or control state as evidence, compare current projection
timestamps across:

| Projection | What it proves |
| --- | --- |
| `live_signal_events` | whether a fresh signal existed |
| `promotion_candidates` | whether the signal was eligible to promote |
| `action_time_lane_inputs` | whether one lane narrowed to action-time |
| `action_time_tickets` | whether the formal machine ticket exists |
| `monitor_decisions` | whether the server classified quiet/notify/gap |
| `notification_attempts` | whether Feishu was configured, attempted, sent, or suppressed |

If monitor state is older than signal/lane state, do not use it to prove
"quiet", "no signal", or "no notification." Say the monitor projection is
stale relative to the current trading chain, then inspect the next read-only
monitor tick or report a monitor freshness gap.

If Server Monitor is newer and says `notify_required`, distinguish the reason:

| Reason class | Meaning |
| --- | --- |
| `action_time_boundary` | A fresh/action-time lane exists and Owner should be notified |
| `promotion_candidate` | A fresh candidate exists but has not narrowed to action-time |
| `runtime_data_gap` | Public/account/watcher facts are unavailable or stale |
| `watcher_or_service_failure` | Watcher status or systemd is truly unhealthy |
| `deploy_or_readiness_failure` | Deploy-health or readiness source is not healthy |

### Server Monitor And Feishu

Treat detection, monitor classification, and notification send as three
separate layers:

| Layer | Evidence | What it answers |
| --- | --- | --- |
| Detection | `live_signal_events`, `promotion_candidates`, `action_time_lane_inputs` | Did a fresh/action-time signal exist? |
| Monitor classification | `monitor_decisions` | Should the Owner be notified? |
| Notification send | `notification_attempts` and dedupe state | Was Feishu configured, attempted, sent, suppressed, or skipped? |

When explaining "why did I not receive a notification", report:

- `decision.notify`;
- `decision.blocker_class`;
- `decision.checkpoint`;
- `notification.configured`;
- `notification.attempted`;
- `notification.sent`;
- `notification.duplicate_suppressed`;
- `notification.skipped_reason`;
- whether `runtime-monitor.env` exists and contains a webhook variable name.

For typed Owner notifications also report `notification_kind`, `severity`,
`correlation_id`, `notification_state`, `send_attempts`, and
`resolved_at_ms`. Translate these into detection, trade progress, intervention,
or recovery before showing the exact audit fields.

Do not ask the Owner to judge raw monitor objects. Translate them into one
sentence such as:

```text
The system detected SOR-001 / SOLUSDT / long and the server monitor correctly
classified it as `notify_required`, but Feishu was not configured:
`notification.configured=false`, `skipped_reason=feishu_webhook_url_missing`.
```

### PG-Backed No-Trade Explanation

After PG cutover, explain every no-trade answer from this chain:

```text
live_signal_event
-> promotion_candidate
-> action_time_lane_input
-> action_time_ticket
-> finalgate_evidence
-> operation_submit_command
-> protection_state
-> reconciliation_state
-> review_outcome
```

Stop only when the first missing or rejected object resolves to one first
blocker. The answer must distinguish:

```text
market_not_satisfied
fresh_signal_absent
runtime_coverage_missing
fact_snapshot_missing
policy_scope_missing
runtime_profile_missing
sizing_scope_missing
protection_missing
arbitration_lost
ticket_missing
ticket_invalidated
finalgate_rejected
operation_blocked
reconciliation_blocked
```

If the system lacks PG lineage for the queried window after cutover, classify it
as an evidence/runtime gap rather than claiming market had no opportunity.

### Systemd OneShot Rules

The runtime watcher and server monitor services are systemd `oneshot` services.
Interpret them this way:

| systemd state | Meaning | Notify as failure? |
| --- | --- | --- |
| `active` while running | Service is currently executing | no |
| `activating` for watcher/monitor oneshot | Transient execution window | no, unless it stays stuck across repeated samples or journal shows failure |
| `inactive/dead` with latest `status=0/SUCCESS` | Normal completed oneshot run | no |
| `failed` or non-zero ExecStart/ExecStartPost | Real service failure | yes |

If an older monitor projection reports
`systemd_unit_not_active:brc-runtime-signal-watcher.service:activating`, check a
later watcher status/journal sample before calling it a real failure. If the
later watcher run ended successfully and the monitor script now reports
`systemd.ready=true`, classify the earlier item as a transient monitor race,
not as a trading-chain blocker.

### Signal Categories

Classify every detected item into one of these categories:

| Category | Meaning |
| --- | --- |
| `no_action` | Strategy explicitly did not see a tradable setup |
| `computed_not_satisfied` | Detector/facts ran, but required facts were false or incomplete |
| `would_enter` | Low-level strategy/runtime thought a setup might enter, but it is not yet a valid trade |
| `promotion_candidate` | A fresh satisfied candidate exists but is not yet the single action-time lane |
| `action_time_lane_input` | One candidate reached the narrowed pre-FinalGate lane |
| `candidate_authorization_ready` | The system has a concrete candidate/auth record |
| `finalgate_reached` | FinalGate was actually called or has a preflight result |
| `operation_layer_reached` | Official Operation Layer received a command plan or submit attempt |
| `real_order_attempted` | Exchange-write/order lifecycle action was attempted |

### Do Not Confuse These

- A `would_enter` signal is not automatically a trade.
- A strategy-group preview `would_enter` with `no_runtime_start=true` and
  `no_execution_permission=true` is review evidence only. It must not generate
  `shadow_candidate_id` or `prepared_authorization_id` unless it is promoted or
  matched to an active runtime lane through the official path.
- A price breakout is not automatically a strategy-confirmed signal.
- A candidate-pool row with `signal_state=absent` is stronger than a broad
  product-state phrase such as `fresh_signal_present=true` unless the latter
  names a concrete StrategyGroup, symbol, side, and candidate/auth record.
- A stale monitor `healthy_waiting_quiet` projection is weaker than a newer
  action-time lane projection with open `action_time_lane_inputs`.
- A missing Feishu send is not evidence that no signal existed. It may mean
  `notification.configured=false`, `duplicate_suppressed=true`, or a send
  failure.
- A runtime lane with `NEXT-ATTEMPT-POSITION-ORDER-CONFLICT` is not a market
  conclusion. It means PG/runtime/exchange position or order state must be
  reconciled before a new candidate can be trusted.
- Dry-run audit chain evidence never proves a real live trade opportunity.
- `FinalGate not_reached` means the safety gate did not receive a valid
  candidate; it is not the same as FinalGate rejecting a trade.
- `Operation Layer not_reached` means no executable command plan existed; it is
  not an exchange rejection.

### Market Opportunity Claim

Use this decision tree:

```text
continuous watcher coverage for the date?
  no -> cannot prove market had no opportunity for the whole window
  yes -> any fresh/live-submit-allowed satisfied candidate in PG current state?
    no -> market/no-signal for covered window
    yes -> did it reach action_time_lane_input?
      no -> engineering/scope/classification boundary
      yes -> did candidate_authorization exist?
        no -> candidate authorization materialization boundary
        yes -> did FinalGate pass?
          no -> safety/facts boundary
          yes -> did Operation Layer command plan exist?
            no -> operation-layer handoff boundary
            yes -> if no order, inspect protected submit result
monitor notification expected?
  no -> explain quiet/market wait
  yes -> inspect notification.configured / attempted / sent / skipped_reason
```

## Report Structure

Answer in Chinese. Use this exact high-level structure:

```text
## 结论
## 已知客观事实
## 昨天/当前检测到了什么
## 有没有理论可交易但没交易
## 为什么没有交易
## 通知为什么有/没有发出
## 具体例子
## 是否需要 Owner 授权
## 后续应记录成什么
## Chain Position
```

Keep the wording plain. Translate internal labels into human meaning and put
the exact field names in backticks after the plain explanation.

## Required Tables

When comparing strategies or signals, include a table with:

| StrategyGroup | Symbol | Side | Runtime status | Signal type | Chain step reached | Why no trade |
| --- | --- | --- | --- | --- | --- | --- |

When explaining three or more blockers, include:

| Blocker | Plain meaning | Exact missing field/evidence | Owner action required |
| --- | --- | --- | --- |

When explaining notification behavior, include:

| Layer | Status | Evidence | Meaning |
| --- | --- | --- | --- |

## Required Answer Checks

Before final response, verify:

- The answer says whether the date-window coverage is proven or incomplete.
- The answer names every detected `would_enter`, `promotion_candidate`, or
  `action_time_lane_input`.
- The answer compares PG current signal, promotion, action-time lane, ticket,
  monitor, and notification timestamps before making a no-signal or no-notify
  claim.
- The answer distinguishes market-not-satisfied from system-blocked.
- The answer distinguishes detection from server-monitor classification and
  Feishu delivery.
- The answer does not stop at "missing prepared_authorization_id"; it explains
  why that ID was not created.
- The answer says whether the signal was an active runtime lane or a
  strategy-group preview.
- If a preview signal is discussed, the answer reports `no_runtime_start`,
  `no_execution_permission`, `not_order`, and the next valid promotion/matching
  step.
- If a blocked runtime lane is discussed, the answer reports the concrete
  blocker such as position/order conflict, missing signal input record, or
  strategy fact failure.
- The answer names how far the signal moved: watcher, candidate pool,
  promotion, action-time, candidate/auth, FinalGate, Operation Layer, or submit.
- The answer says whether Owner authorization is needed.
- If notification is discussed, the answer reports `decision.notify`,
  `notification.configured`, `notification.attempted`, `notification.sent`,
  `notification.duplicate_suppressed`, and `notification.skipped_reason`.
- If systemd is discussed, the answer treats watcher/monitor `activating` or
  `inactive/dead` oneshot states as transient/success only after checking
  journal or latest status, and reports true `failed` states separately.
- The answer cites concrete PG row identifiers, current projection timestamps,
  or journal/process facts.
- The answer preserves authority boundaries:
  `no FinalGate bypass / no Operation Layer bypass / no exchange write`.

## Example Explanation Pattern

Use this pattern for a `would_enter` that did not trade:

```text
CPM-RO-001 / SOL / long had a low-level `would_enter` trace. That means one
runtime component saw a setup-like condition. It did not become a trade because
the system failed to materialize a valid candidate/auth record:
`prepared_authorization_id=null`, `shadow_candidate_id=null`, and the blocker
was `order_candidate_id_or_authorization_id_required`. In plain language: it
saw something worth attention, but it did not produce the machine-readable
"this exact trade" ticket required before FinalGate and Operation Layer.
```

Use this pattern for a strategy-group preview:

```text
CPM-RO-001 / ETH / long appeared as a strategy-group preview `would_enter`.
That object explicitly says `no_runtime_start=true`, `no_execution_permission=true`,
`no_order_permission=true`, and `not_order=true`. In plain language: it is a
review note saying "this setup resembles an entry", not a runtime trade
candidate. It cannot create `prepared_authorization_id` or `shadow_candidate_id`
until it is matched to an active runtime lane and passes the runtime candidate
materialization path.
```

Use this pattern for a runtime safety/reconciliation block:

```text
The active runtime lane did not create a candidate because it was blocked by
`NEXT-ATTEMPT-POSITION-ORDER-CONFLICT`: PG/runtime still reports an open order
while exchange/protection facts do not line up. In plain language: before
opening a new trade, the system must prove the old/order state is clean. This
is an engineering/reconciliation blocker, not an Owner authorization request
and not a market no-signal conclusion.
```

Use this pattern for a breakout without confirmation:

```text
SOR-001 / ETH moved above the opening-range level, but
`follow_through_confirmed=false`. In plain language: price poked through the
line, but the strategy did not confirm continuation. That is not a missed trade;
it is a strategy condition not satisfied.
```

## Hard Stops

Stop and report uncertainty when:

- the queried date has no watcher journal and no PG current/audit lineage;
- PG/current projections are unavailable and no archive-only provenance was
  explicitly requested;
- low-level watcher and PG promotion/action-time state disagree and no named candidate/auth
  record can reconcile them;
- a claim would require reading private exchange/account data that is not
  present in existing account-safe facts.

Do not fill gaps with market guesses.
