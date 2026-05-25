# TC-TINY-001D-1 ADR-0009 Authorization Request

Status: Executed on Binance testnet / pending review

Date: 2026-05-25

Runtime effect: executed after explicit Owner authorization

Trading permission effect: Binance testnet only / no real live trading

## Execution Result

Execution date: 2026-05-25

Owner authorization received: yes.

Outcome: controlled Binance testnet smoke completed through ENTRY,
exchange-native protection mounting, order-watch, external cleanup, and
reconciliation. GKS was restored, runtime was stopped, and the testnet account
was verified flat. Review follow-up remains for local stale protection-order
hygiene after the external cleanup path.

Evidence:

- Runtime started with `RUNTIME_PROFILE=sim1_eth_runtime` and
  `EXCHANGE_TESTNET=true`.
- Startup trading guard was armed only after authorization.
- GKS was disabled only for the controlled endpoint call and restored active
  immediately after the endpoint returned.
- Controlled endpoint result:
  - status: `completed`
  - intent id: `intent_f45649feb9fd`
  - signal id: `sig_fec09157c3cc`
  - amount: `0.01`
  - testnet: `true`
  - profile: `sim1_eth_runtime`
  - attempt locked: `true`
  - notional: `20.9347`
  - min notional: `20`
- Exchange testnet ENTRY was submitted and filled:
  - local order id: `ord_e1331c9f`
  - exchange order id: `8728148126`
- Exchange-native protection was mounted:
  - TP1 local order id: `ord_TP1_2730d882`,
    exchange order id: `8728148137`
  - TP2 local order id: `ord_TP2_9f28da89`,
    exchange order id: `8728148143`
  - SL local order id: `ord_sl_11671362`,
    exchange order id: `1000000084871663`
- Risk decision audit recorded startup guard allow, GKS allow, and
  `control.test_signal_injection` executed for the controlled intent.
- Direct testnet cleanup closed the residual `0.01 ETH` position with
  reduce-only market order `8728150129`.
- Direct Binance testnet verification after cleanup reported
  `positionAmt=0.000` and no target open protection orders.
- Runtime `/api/runtime/positions` was initially stale after direct cleanup, but
  periodic reconciliation later cleared it and recorded an external close
  marker.
- PG `positions` for `sig_fec09157c3cc` was marked closed with quantity `0`.
- PG `orders` still showed the local TP1, TP2, and SL rows as `OPEN` after
  direct exchange cleanup; reconciliation classified them as
  `stale_after_external_close` with `manual_data_hygiene_required`.
- Daily risk stats did not update for this test close because the external
  cleanup path had `pnl_status=unresolved_no_reliable_fill`.
- Runtime was stopped after verification; local port `8000` no longer listened.

Observations for follow-up:

- Periodic reconciliation after external cleanup reported
  `total=3825`, `severe=830`, and `warning=2995`; protection health set a
  critical block for `PROTECTION_LOCAL_SL_MISSING_ON_EXCHANGE` with count `829`.
  This is the main incomplete smoke finding.
- SL `fetch_order` confirmation reported a Binance testnet "Order does not
  exist" response immediately after STOP_MARKET submission, while order-watch
  later observed the SL as open. Treat this as a testnet confirmation-path
  observation for review, not a blocker for this smoke result.
- Direct exchange cleanup was necessary because the test endpoint validates
  entry/protection mounting, not a full strategy-managed exit.
- Local stale protection-order hygiene remains the main follow-up before
  treating this as a fully clean lifecycle smoke.

Follow-up status: `TC-TINY-001D-2` implemented local-only external-close order
hygiene and cleaned the historical stale ETH protection rows in PG. The original
001D-1 execution result remains recorded as partial because the issue was found
during that smoke and fixed afterward.

## Purpose

Request Owner authorization for one controlled Binance testnet order-lifecycle
smoke using the existing endpoint:

`POST /api/runtime/test/smoke/execute-controlled-entry`

This is a non-real-live execution request under
`docs/adr/0009-non-real-live-execution-authorization-boundary.md`.

## Requested Authorization

Authorize Codex to execute exactly one TC-TINY-001D-1 controlled testnet smoke
cycle:

1. start local runtime with the `sim1_eth_runtime` profile;
2. arm the startup trading guard;
3. temporarily disable GKS;
4. call the controlled test endpoint once;
5. observe ENTRY plus exchange-native SL/TP mounting on Binance testnet;
6. verify order-watch, position projection, daily stats, reconciliation, and
   audit trail;
7. restore GKS active and stop runtime;
8. if needed, clean residual Binance testnet open orders or positions for the
   controlled test only.

This authorization does not include real live trading, mainnet exchange access,
multiple cycles, strategy parameter changes, live profile changes, real-funds
deployment, transfer, withdrawal, or rebalancing.

## Intended Mode

- Mode: Binance testnet controlled runtime smoke.
- Runtime profile: `sim1_eth_runtime`.
- Exchange mode: `EXCHANGE_TESTNET=true`.
- Symbol: `ETH/USDT:USDT`.
- Direction: `LONG`.
- Maximum controlled endpoint calls: 1 per runtime session.
- Maximum controlled amount: `0.01 ETH`.
- Maximum planned testnet entry orders: 1.
- Expected protection orders: one stop-market SL and two reduce-only TP orders.

## Verification Already Completed

Local tests:

```bash
pytest -q tests/unit/test_tiny001d1a_controlled_signal_injection.py tests/unit/test_tiny001d4_once_per_session_guard.py
```

Expected current result: `33 passed`.

Extended boundary tests:

```bash
pytest -q tests/unit/test_tiny001d1a_controlled_signal_injection.py tests/unit/test_tiny001d4_once_per_session_guard.py tests/unit/test_personal_campaign_sandbox.py tests/unit/test_personal_campaign_schema_docs.py tests/unit/test_personal_campaign_schema_examples.py
```

Expected current result: `61 passed`.

The tests verify:

- test injection env flag is required;
- runtime control API flag is required;
- `EXCHANGE_TESTNET=true` is required;
- profile must be `sim1_eth_runtime`;
- request body overrides are rejected;
- endpoint is once-per-session;
- startup guard must be armed;
- GKS must be inactive;
- protection-health and circuit-breaker blocks stop execution;
- notional below min-notional blocks before `execute_signal`;
- endpoint calls only `ExecutionOrchestrator.execute_signal` directly and does
  not directly call order mutation APIs;
- trace is emitted best-effort;
- wrong live-like profiles are rejected.

## Exact Operational Steps

### 1. Start Runtime

```bash
RUNTIME_PROFILE=sim1_eth_runtime \
RUNTIME_CONTROL_API_ENABLED=true \
RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=true \
PROTECTION_HEALTH_EXTERNAL_ALERTS_ENABLED=false \
python3 -m src.main > /tmp/001d1_runtime.log 2>&1 &
echo "PID=$!"
```

Required checks before continuing:

- runtime log includes `SYSTEM READY`;
- resolved config reports `exchange_testnet=true`;
- profile is `sim1_eth_runtime`;
- startup guard is not armed until Step 2;
- GKS is active until Step 3;
- no live profile or mainnet mode is detected.

### 2. Arm Startup Guard

```bash
curl -s -X POST http://127.0.0.1:8000/api/runtime/control/startup-trading-guard/arm \
  -H "Content-Type: application/json" \
  -d '{"reason": "TC-TINY-001D-1 owner authorized testnet smoke", "updated_by": "owner"}'
```

### 3. Disable GKS Temporarily

```bash
curl -s -X POST http://127.0.0.1:8000/api/runtime/control/global-kill-switch \
  -H "Content-Type: application/json" \
  -d '{"active": false, "reason": "TC-TINY-001D-1 owner authorized testnet smoke", "updated_by": "owner"}'
```

### 4. Execute One Controlled Testnet Entry

```bash
curl -s -X POST http://127.0.0.1:8000/api/runtime/test/smoke/execute-controlled-entry \
  -H "Content-Type: application/json"
```

No request body is allowed. The endpoint derives all parameters server-side:

- symbol: `ETH/USDT:USDT`;
- direction: `LONG`;
- amount: `0.01`;
- SL: approximately 1 percent below fetched testnet ticker price;
- TP1: approximately 1 percent above fetched testnet ticker price;
- TP2: approximately 3.5 percent above fetched testnet ticker price.

### 5. Verify Runtime Evidence

Use local runtime endpoints and logs:

```bash
curl -s http://127.0.0.1:8000/api/runtime/execution/intents
curl -s http://127.0.0.1:8000/api/runtime/execution/orders
curl -s http://127.0.0.1:8000/api/runtime/positions
curl -s http://127.0.0.1:8000/api/runtime/events
```

Expected evidence:

- controlled endpoint response has `testnet=true`, `profile=sim1_eth_runtime`,
  `amount=0.01`, and `attempt_locked=true`;
- entry order receives a Binance testnet exchange order id;
- exchange-native SL and TP orders are mounted;
- order-watch receives updates;
- no unprotected position remains after entry fill;
- decision trace records the controlled test signal injection;
- daily stats update after close;
- reconciliation severe count remains zero.

Actual execution note: the daily-stats and zero-severe reconciliation
expectations were not met for the externally cleaned-up close. See
`Execution Result` above.

### 6. Restore Safe State

```bash
curl -s -X POST http://127.0.0.1:8000/api/runtime/control/global-kill-switch \
  -H "Content-Type: application/json" \
  -d '{"active": true, "reason": "TC-TINY-001D-1 complete - restore GKS", "updated_by": "owner"}'
```

Then stop runtime:

```bash
kill <PID>
```

## External Systems Touched

- Local runtime API on `127.0.0.1:8000`.
- Local or configured PG runtime database.
- Binance futures testnet REST/WebSocket endpoints through the existing
  exchange gateway.
- Local runtime logs under `/tmp/001d1_runtime.log` and project runtime logs.

## Credentials And Account State

- Uses existing Binance testnet credentials from local environment.
- Must not use live credentials.
- Must not configure or paste secrets into prompts, docs, or logs.
- Touches Binance testnet account state only.
- May create one testnet position and associated testnet SL/TP orders.
- May require testnet-only cleanup if the position or open orders remain.

## Stop Conditions

Immediately stop runtime, restore GKS active if reachable, and report to Owner
if any condition occurs:

- `EXCHANGE_TESTNET=false` or mainnet endpoint detected;
- profile is not `sim1_eth_runtime`;
- live key/profile/real-funds account detected;
- GKS inactive before the approved step;
- startup guard armed before the approved step;
- endpoint call count exceeds one;
- symbol differs from `ETH/USDT:USDT`;
- amount exceeds `0.01 ETH`;
- no SL is mounted after entry fill;
- protection-health block or circuit breaker appears;
- reconciliation severe count is greater than zero;
- any transfer, withdrawal, rebalancing, or non-testnet account action appears.

## Rollback And Cleanup

Mandatory cleanup:

1. re-enable GKS;
2. stop runtime;
3. verify testnet open orders and positions are flat or intentionally recorded;
4. preserve PG/runtime records as audit evidence.

If residual testnet orders or positions remain, cleanup is limited to the
controlled testnet symbol and amount. No live/mainnet cleanup action is allowed.

## Owner Authorization Phrase

To authorize execution, Owner should reply with a phrase equivalent to:

`Authorize TC-TINY-001D-1 under ADR-0009: one Binance testnet controlled entry cycle, max 0.01 ETH, sim1_eth_runtime only, restore GKS and stop runtime after verification.`
