# Trend/SOL Full-Chain Closure Report

Date: 2026-06-06

## Verdict

PASS_WITH_CONSTRAINT

The existing Trend/SOL action lifecycle is closed to a clear operational state:

- SOL exchange position is flat.
- Entry order `218766349737` is filled.
- TP order `218766349863` is filled.
- Residual SL/algo `4000001500443218` is no longer visible in stop-order reads.
- PG local TP row is aligned to `FILLED`.
- PG local SL row is aligned to `CANCELED`.
- PG position projection is closed with `current_qty=0`.
- Post-live closure result envelope is recorded in `brc_execution_results`.
- Retry remains blocked by consumed authorization and prior completed intent.

Constraint: the first cleanup run successfully reached the Binance conditional
cancel fallback, but the script failed after the exchange cleanup while inserting
`order_audit_logs` because the first audit insert omitted the required `id`.
The later idempotent repair pass captured final exchange truth, repaired PG
state, and patched the result envelope to record that cleanup was attempted and
observably completed, but the original cancel response object was not preserved.

## Scope

- Carrier: `TF-001-live-readonly-v0`
- Symbol: `SOL/USDT:USDT`
- Side: `long`
- Quantity: `0.1`
- Max notional: `20`
- Leverage: `1`
- Protection: `single_tp_plus_sl`
- Authorization: `auth-8e591fb066af43578094c27064ede55f`
- Intent: `intent-e6ec405fa0fe4ba1bc82d3b246a6c9ef`

No new strategy action, new entry, broader symbol/side, leverage change,
Volatility/Mean-Reversion expansion, auto-execution, or broad action API was
introduced.

## Action Sequence

1. Fresh precheck confirmed exact scope, consumed authorization, completed
   intent, SOL flat state, and one matching residual stop/algo order.
2. Scoped cleanup called the existing exchange gateway cancel path for only
   `4000001500443218`.
3. `ExchangeGateway.cancel_order` first received ordinary order-not-found, then
   matched the conditional open order through its Binance stop-order fallback.
4. The script failed after the exchange cleanup during audit insert because
   `order_audit_logs.id` was not provided.
5. Follow-up read-only evidence confirmed `stop_order_count=0`.
6. Idempotent PG hygiene repaired TP/SL local order status and projected the
   local position closed.
7. `order_audit_logs` was populated with TP filled and SL canceled events.
8. `brc_execution_results` was updated with a post-live closure envelope.
9. A final read-only snapshot confirmed the closed state.

## Final Exchange Truth

From `readonly-final.json`:

- active SOL position count: 0
- ordinary open order count: 0
- stop order count: 0
- matching stop order count for `4000001500443218`: 0
- entry order `218766349737`: `FILLED`, filled quantity `0.1`, price `62.38`
- TP order `218766349863`: `FILLED`, filled quantity `0.1`, price `63.0`
- SL/algo `4000001500443218`: no longer found by ordinary order lookup and no
  longer visible in stop-order reads

## Final PG Truth

From `readonly-final.json`:

- authorization consumed: true
- intent status: `completed`
- entry local order `c51b913e-ab69-4233-82cf-9af8e1f43130`: `FILLED`
- TP local order `6426f4d0-7edc-4513-8020-71eb864338b1`: `FILLED`
- SL local order `1632dfa6-e968-4d27-8414-c89e30719c60`: `CANCELED`
- position `pos_owner-live-auth-8e591fb066af43578094c27064ede55f`:
  `current_qty=0`, `is_closed=1`
- realized PnL projection: `0.3720000000000000000000000000`
- post-live closure result:
  `post-live-closure-auth-8e591fb066af43578094c27064ede55f`

The post-live closure result records:

- `cleanup_attempted=true`
- `cleanup_executed=true`
- `cleanup_response_captured=false`
- `cleanup_target_exchange_order_id=4000001500443218`
- `cleanup_observed_effect=pre_cleanup_stop_order_count_1_to_post_cleanup_stop_order_count_0`
- `orphan_sl_remaining=false`

## Review And Audit

Review/audit state is now represented by:

- original execution review:
  `review-auth-8e591fb066af43578094c27064ede55f`
- post-live closure review/result:
  `post-live-closure-auth-8e591fb066af43578094c27064ede55f`
- order audit logs for:
  - TP status transition `OPEN -> FILLED`
  - SL status transition `OPEN -> CANCELED`

The final review is evidence-backed but has one caveat: the exact cancel response
payload from Binance was not preserved because the first run failed after the
exchange cleanup and before final evidence serialization. The observable
exchange effect and final read-only evidence are preserved.

## Retry Safety

Retry remains blocked by state, not by UI convention:

- authorization is consumed
- one completed execution intent exists for the authorization
- local execution/order/review state exists
- the previous intent status is `completed`

No duplicate execution occurred.

## Release State

Production service:

- service: `brc-owner-console-backend.service`
- health: `runtime_bound=true`, `live_ready=false`
- active port: `127.0.0.1:18080`
- `18081`: not listening
- `/home/ubuntu/brc-deploy/app/current` points to
  `/home/ubuntu/brc-deploy/releases/trend-sol-governance-8c6ddb9a-202606061415`
- active process PID `1123809` still runs the old long-lived process started on
  2026-06-04

No production restart was performed during this closure.

## Evidence Files

Server:

- `/home/ubuntu/brc-deploy/reports/trend-sol-full-closure-20260606/precheck.json`
- `/home/ubuntu/brc-deploy/reports/trend-sol-full-closure-20260606/post-exchange.json`
- `/home/ubuntu/brc-deploy/reports/trend-sol-full-closure-20260606/final.json`
- `/home/ubuntu/brc-deploy/reports/trend-sol-full-closure-20260606/readonly-final.json`

Local copies:

- `reports/trend-sol-full-closure-20260606/precheck.json`
- `reports/trend-sol-full-closure-20260606/post-exchange.json`
- `reports/trend-sol-full-closure-20260606/final.json`
- `reports/trend-sol-full-closure-20260606/readonly-final.json`

## Blocker Records

### BR-SOL-CLOSURE-CANCEL-RESPONSE-NOT-CAPTURED

- stage: residual protection cleanup
- path: one-shot closure script
- evidence: exchange gateway matched the conditional stop-order fallback, but
  the script then failed on `order_audit_logs.id` before preserving the cancel
  response object
- severity: medium
- bridge: final read-only exchange evidence confirms stop-order count 0; PG
  result envelope records response capture failure explicitly
- retry_condition: future cleanup scripts must serialize cancel result before
  any PG audit write and must generate audit IDs within the schema limit

### BR-SOL-RELEASE-PROCESS-DRIFT

- stage: release governance
- path: systemd active process vs `app/current`
- evidence: `app/current` points to the repaired real release, but active PID
  remains the older long-lived process
- severity: medium
- bridge: no restart in this closure; service remains healthy
- retry_condition: planned release restart verification window

## Safety Proof

- No new entry was submitted.
- No new strategy action was started.
- No Volatility Expansion or Mean Reversion action support was expanded.
- No auto-execution or broad action API was enabled.
- Only residual reduce-only SOL stop/algo cleanup was attempted.
- Cleanup was scoped to `SOL/USDT:USDT`, `LONG`, `0.1`, order/algo
  `4000001500443218`.
- Cleanup precheck required SOL flat state and exact PG/order scope.
- PG updates were limited to TP filled, SL canceled, position projection closed,
  order audit logs, and post-live closure result envelope.
- No credentials or secrets were printed.
- Production service was not restarted.
- No push was performed.
