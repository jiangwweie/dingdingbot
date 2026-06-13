# Runtime Signal Watcher + Feishu Runbook - 2026-06-13

## Known Facts

- `scripts/runtime_signal_watcher_tick.py` is a one-shot watcher wrapper.
- It reuses the existing active runtime observation loop, status packet,
  operator packet, and wake-up packet builders.
- It writes JSON evidence every tick and only sends Feishu notifications when
  owner attention is required.
- Feishu custom bots receive messages through a group webhook. The text payload
  uses `msg_type=text` and `content.text`; signed bots add `timestamp` and
  `sign` fields according to Feishu custom bot webhook documentation.

## Safety Boundary

The watcher is not submit authority.

It must not:

- create executable `ExecutionIntent` records;
- place exchange orders;
- call `OrderLifecycle` submit;
- mutate runtime budget or attempt counters;
- create withdrawal or transfer instructions;
- bypass FinalGate or Operation Layer.

Every tick emits safety fields proving:

- `exchange_write_called=false`
- `order_created=false`
- `order_lifecycle_called=false`
- `execution_intent_created=false`
- `runtime_budget_mutated=false`
- `withdrawal_or_transfer_created=false`

## Evidence Paths

Default Tokyo paths:

```text
/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/latest-status.json
/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/status-packet.json
/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/operator-packet.json
/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/wakeup-packet.json
/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/watcher-tick.json
/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/notification-state.json
```

## Notification Policy

The watcher does not push every `waiting_for_signal` tick by default.

It pushes when one of these states appears:

| State | Meaning |
|---|---|
| `runtime_signal_ready_for_non_executing_prepare` | A runtime signal is ready for owner review. |
| `prepared_shadow_evidence_ready_for_owner_review` | Prepared shadow evidence exists and needs owner review. |
| `blocked_forbidden_effect` | The source packet reported a forbidden effect. |
| `operator_packet_needs_review` | The watcher cannot classify the operator packet safely. |
| `attention` / `blocked` / `stale` status packet | The status packet needs operator attention. |

Duplicate event keys are suppressed by `notification-state.json`.

## Feishu Environment

Do not commit webhook values.

Create this file on Tokyo:

```text
/home/ubuntu/brc-deploy/env/runtime-signal-watcher.env
```

Expected variables:

```bash
BRC_SIGNAL_WATCHER_FEISHU_WEBHOOK_URL='https://open.feishu.cn/open-apis/bot/v2/hook/...'
BRC_SIGNAL_WATCHER_FEISHU_WEBHOOK_SECRET='optional-signing-secret'
```

The script also supports fallback names:

```bash
FEISHU_WEBHOOK_URL='...'
FEISHU_WEBHOOK_SECRET='...'
```

## Manual Dry Run

```bash
cd /home/ubuntu/brc-deploy/current
/home/ubuntu/brc-deploy/venvs/brc-bnb-prelive-20260601/bin/python \
  scripts/runtime_signal_watcher_tick.py \
  --env-file /home/ubuntu/brc-deploy/env/live-readonly.env \
  --api-base http://127.0.0.1:18080 \
  --source live_market \
  --strategy-source live_market \
  --output-dir /home/ubuntu/brc-deploy/reports/runtime-signal-watcher \
  --notification-dry-run
```

## systemd Install

Copy the unit files from:

```text
deploy/systemd/brc-runtime-signal-watcher.service
deploy/systemd/brc-runtime-signal-watcher.timer
```

Install:

```bash
sudo cp deploy/systemd/brc-runtime-signal-watcher.service /etc/systemd/system/
sudo cp deploy/systemd/brc-runtime-signal-watcher.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now brc-runtime-signal-watcher.timer
```

Inspect:

```bash
systemctl status brc-runtime-signal-watcher.timer --no-pager
systemctl list-timers brc-runtime-signal-watcher.timer --no-pager
journalctl -u brc-runtime-signal-watcher.service -n 80 --no-pager
```

## Resume Path

When Feishu reports a ready signal:

1. Inspect `wakeup-packet.json`.
2. Inspect `operator-packet.json`.
3. Continue with fresh candidate / runtime grant / authorization evidence.
4. Run action-time FinalGate.
5. Execute a real gateway action only through official Operation Layer when
   FinalGate passes.

