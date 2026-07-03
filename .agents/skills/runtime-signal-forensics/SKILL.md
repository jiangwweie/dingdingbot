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
chain-position work. It turns runtime artifacts into a plain explanation of:

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
.agents/skills/chain-position/SKILL.md
```

If the user asks about a relative date such as "yesterday", convert it to an
absolute date using the current runtime timezone before reporting.

## Evidence Priority

Prefer Tokyo server-side runtime evidence over local caches for production
questions.

Use this authority order:

1. Tokyo `reports/runtime-signal-watcher/*` files and watcher journal.
2. Tokyo `app/current/output/runtime-monitor/*` generated views.
3. Tokyo server-side monitor reports and monitor journal.
4. Tokyo release manifest and deploy-health reports.
5. Local `output/runtime-monitor/*` only as fallback or comparison.
6. Docs/contracts only to explain allowed meanings, not to invent facts.

Never claim "market had no opportunity all day" unless the queried time window
has continuous watcher/monitor coverage or an explicit daily artifact proving
no fresh eligible signal for that window.

Never claim "the system did not notify" as equivalent to "the system did not
detect a signal." Notification is a separate layer after detection and monitor
classification. Always inspect the server monitor artifact and its
`notification` object before explaining missed notifications.

## Read-Only Collection

Use read-only commands only. Do not deploy, restart services, mutate files,
call FinalGate, call Operation Layer, or call exchange-write endpoints.

For Tokyo, collect:

```text
/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/latest-summary.json
/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/latest-status.json
/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/operator-evidence.json
/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/watcher-tick.json
/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/post-signal-resume-pack.json
/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/resume-dispatch-artifact.json
/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/strategygroup-runtime-goal-status.json
/home/ubuntu/brc-deploy/reports/runtime-monitor/latest-account-safe-facts.json
/home/ubuntu/brc-deploy/reports/runtime-monitor/latest-server-side-runtime-monitor.json
/home/ubuntu/brc-deploy/reports/runtime-monitor/latest-deploy-health.json
/home/ubuntu/brc-deploy/reports/runtime-monitor/server-monitor-dedupe-state.json
/home/ubuntu/brc-deploy/app/current/output/runtime-monitor/latest-strategy-live-candidate-pool.json
/home/ubuntu/brc-deploy/app/current/output/runtime-monitor/latest-daily-live-enablement-table.json
/home/ubuntu/brc-deploy/app/current/output/runtime-monitor/latest-single-lane-task-packet.json
/home/ubuntu/brc-deploy/app/current/output/runtime-monitor/latest-strategy-fresh-signal-action-time-boundary.json
/home/ubuntu/brc-deploy/app/current/.brc-release-manifest.json
```

For a date-window question, also collect:

```text
journalctl -u brc-runtime-signal-watcher.service --since <start> --until <end>
journalctl -u brc-runtime-monitor.service --since <start> --until <end>
systemctl status --no-pager brc-runtime-signal-watcher.service
systemctl status --no-pager brc-runtime-monitor.service
systemctl list-timers --all --no-pager brc-runtime-signal-watcher.timer brc-runtime-monitor.timer
find /home/ubuntu/brc-deploy/reports/runtime-signal-watcher -maxdepth 1 -type f -newermt <start> ! -newermt <end>
find /home/ubuntu/brc-deploy/reports/runtime-monitor -maxdepth 1 -type f -newermt <start> ! -newermt <end>
```

If the server lacks `jq`, use Python JSON parsing.

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
| `artifact_evidence_gap` | The artifacts are overwritten/missing/inconsistent and cannot prove the chain | no; say what evidence must be captured next |

Use this drill-down order:

```text
detected signal?
-> is Candidate Pool newer than Server Monitor?
-> runtime lane or strategy-group preview?
-> if preview: does it have no_runtime_start / no_execution_permission?
-> if runtime lane: status waiting_for_signal, blocked, ready_for_prepare, or ready_for_final_gate_preflight?
-> signal_input_json present?
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
prepared_authorization_id is missing because signal_input_json is missing.
signal_input_json is missing because the runtime lane is blocked by
NEXT-ATTEMPT-POSITION-ORDER-CONFLICT. That is a reconciliation/safety gap, not
a market no-signal conclusion.
```

### Artifact Freshness

Before using a monitor or control artifact as evidence, compare
`generated_at_utc` across:

| Artifact | Path |
| --- | --- |
| Candidate Pool | `/home/ubuntu/brc-deploy/app/current/output/runtime-monitor/latest-strategy-live-candidate-pool.json` |
| Daily Table | `/home/ubuntu/brc-deploy/app/current/output/runtime-monitor/latest-daily-live-enablement-table.json` |
| Server Monitor | `/home/ubuntu/brc-deploy/reports/runtime-monitor/latest-server-side-runtime-monitor.json` |
| Refresh Sequence | `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/server-product-state-refresh-sequence.json` |
| Goal Status | `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/strategygroup-runtime-goal-status.json` |

If Candidate Pool or Daily Table is newer than Server Monitor, do not use the
older Server Monitor artifact to prove "quiet", "no signal", or "no
notification." Say the monitor artifact is stale relative to the current
control state, then run or inspect the next server-monitor tick if the task
allows read-only validation.

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
| Detection | Candidate Pool, Daily Table, watcher artifacts | Did a fresh/action-time signal exist? |
| Monitor classification | `latest-server-side-runtime-monitor.json.decision` | Should the Owner be notified? |
| Notification send | `latest-server-side-runtime-monitor.json.notification` and dedupe state | Was Feishu configured, attempted, sent, suppressed, or skipped? |

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

Do not ask the Owner to judge raw monitor artifacts. Translate them into one
sentence such as:

```text
The system detected SOR-001 / SOLUSDT / long and the server monitor correctly
classified it as `notify_required`, but Feishu was not configured:
`notification.configured=false`, `skipped_reason=feishu_webhook_url_missing`.
```

### Systemd OneShot Rules

The runtime watcher and server monitor services are systemd `oneshot` services.
Interpret them this way:

| systemd state | Meaning | Notify as failure? |
| --- | --- | --- |
| `active` while running | Service is currently executing | no |
| `activating` for watcher/monitor oneshot | Transient execution window | no, unless it stays stuck across repeated samples or journal shows failure |
| `inactive/dead` with latest `status=0/SUCCESS` | Normal completed oneshot run | no |
| `failed` or non-zero ExecStart/ExecStartPost | Real service failure | yes |

If an old Server Monitor artifact reports
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
- A stale Server Monitor `healthy_waiting_quiet` artifact is weaker than a newer
  Candidate Pool with `action_time_lane_inputs`.
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
  yes -> any fresh/live-submit-allowed satisfied candidate in Candidate Pool?
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
- The answer compares Candidate Pool, Daily Table, Server Monitor, Refresh
  Sequence, and Goal Status freshness before making a no-signal or no-notify
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
  blocker such as position/order conflict, missing `signal_input_json`, or
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
- The answer cites concrete artifact paths or journal facts.
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

- the queried date has no watcher journal and no historical runtime artifacts;
- latest files were overwritten and no archival evidence exists;
- low-level watcher and candidate pool disagree and no named candidate/auth
  record can reconcile them;
- a claim would require reading private exchange/account data that is not
  present in existing account-safe facts.

Do not fill gaps with market guesses.
