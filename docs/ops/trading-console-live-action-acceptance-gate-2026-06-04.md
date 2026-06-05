# Trading Console Live Action Acceptance Gate

Date: 2026-06-04

Status: AUTHORIZED_DRY_RUN_BLOCKED_NOT_EXECUTED

Purpose: define the separate Owner approval and evidence requirements for live
action verification after the Trading Console reaches runtime-bound readiness.

The Owner later authorized one exact BNB bounded execute/protection acceptance
scope in-thread. The backend final hard gate remained blocked, so no live action
was executed.

## Prerequisites

Do not enter this gate unless all are true:

- runtime-bound transition runbook has passed through production switch;
- production `/api/health` proves `runtime_bound=true`;
- authenticated `/api/trading-console/*` GET validation passes;
- action endpoints, if present, are documented and intentionally enabled;
- current account/order/position/protection state has been captured;
- Owner approval is action-specific, not generic.

Required references:

- `docs/ops/trading-console-runtime-bound-transition-runbook-2026-06-04.md`
- `reports/trading-console-server-deploy-acceptance-2026-06-04/completion-audit.md`

## Approval Template

Each live action must have a separate approval record with:

- action name:
  - `execute`
  - `cancel`
  - `replace`
  - `flatten`
  - `retry_protection`
- symbol: exact exchange symbol
- side: exact side if applicable
- amount or notional: exact maximum
- leverage: exact maximum
- order type: exact type if applicable
- target order id / position id / protection plan id where applicable
- allowed time window
- maximum number of attempts
- required stop condition
- rollback or observation requirement
- evidence output path

Stop if any field is missing, ambiguous, or broader than the current BNB
prelive scope.

## Minimum Current BNB Scope Template

For the currently prepared prelive profile, the narrowest acceptable execute
authorization wording is:

```text
I authorize Trading Console live action acceptance for:
action: execute
symbol: BNB/USDT:USDT
side: LONG
max amount: 0.01 BNB
max notional: 20 USDT
max leverage: 1
max attempts: 1
required protection: enabled or explicit blocker recorded
time window: <exact time window>
stop condition: stop on any scope mismatch, unavailable pre-action read model,
conflicting position/order, missing authorization, missing protection readiness,
or action permission above approved scope.
```

Any cancel, replace, flatten, or retry-protection verification still requires a
separate action-specific approval.

## Shared Pre-Action Evidence

Before any action:

- capture `/api/health`;
- capture all `/api/trading-console/*` GET read models;
- capture exchange account facts through read-only API;
- capture open orders and positions;
- capture protection health;
- capture authorization state;
- capture audit chain baseline;
- record active runtime profile name and config hash.

Evidence must not include secrets or raw API keys.

## Action-Specific Gates

### Execute

Required approval fields:

- symbol
- side
- amount/notional
- leverage
- order type
- protection requirement

Pre-action checks:

- no conflicting open position unless explicitly approved;
- no conflicting open order unless explicitly approved;
- protection plan readiness is known;
- authorization is active and unexpired;
- hard gates are passing.

Post-action evidence:

- order id;
- order status;
- position delta;
- protection order creation or explicit protection blocker;
- audit event chain;
- review/recovery state.

### Cancel

Required approval fields:

- exact order id;
- cancel reason;
- whether protection orders are included or excluded.

Stop if the target order id is not present in the latest read model and
exchange read-only snapshot.

Post-action evidence:

- cancel response;
- order state transition;
- protection state after cancel;
- audit event.

### Replace

Required approval fields:

- exact order id;
- old parameters;
- new parameters;
- maximum slippage or price movement;
- whether replace is cancel+new or native replace.

Stop if replace could increase notional/leverage beyond approval.

Post-action evidence:

- old order state;
- new order id or updated exchange id;
- order ledger consistency;
- audit event.

### Flatten

Required approval fields:

- exact position symbol;
- side/quantity to close;
- maximum allowed close notional;
- whether reduce-only is mandatory.

Stop if flatten is not reduce-only or if it can open a reverse position.

Post-action evidence:

- position before/after;
- close order id;
- realized status if available;
- remaining protection cleanup status;
- audit event.

### Retry Protection

Required approval fields:

- exact position id or symbol/side;
- target protection plan id;
- protection order types;
- maximum number of retry attempts.

Stop if retry can create duplicate protection beyond approved coverage.

Post-action evidence:

- protection order ids;
- protection coverage state;
- orphan-protection state;
- recovery task state;
- audit event.

## Post-Action Acceptance Evidence

After each approved action:

- rerun authenticated browser validation;
- rerun `/api/trading-console/*` GET validation;
- capture order ledger;
- capture account risk;
- capture protection health;
- capture recovery exception state;
- capture review state;
- capture audit chain;
- record screenshots for affected pages.

## Stop Conditions

Stop immediately if:

- approval scope differs from active runtime profile scope;
- symbol is not `BNB/USDT:USDT` under current prelive profile;
- side is not approved;
- leverage exceeds approved maximum;
- notional/amount exceeds approved maximum;
- action endpoint tries to bypass Owner authorization;
- action endpoint tries to bypass Operation Layer;
- exchange or PG state cannot be read before action;
- any credential/API-key change would be required;
- any withdraw/transfer operation appears.

## Current Acceptance Status

Current status: BLOCKED_NOT_EXECUTED.

Owner-approved scope:

- action: execute + protection acceptance only
- symbol: `BNB/USDT:USDT`
- side: `LONG`
- amount: `0.01` BNB
- max notional: `20` USDT
- max leverage: `1`
- max attempts: `1`
- forbidden: any other symbol, side, leverage, or notional

Evidence:

- Active readonly runtime profile was seeded:
  `prelive_bnb_readonly_runtime`.
- Isolated runtime-bound probe passed on `127.0.0.1:18082` with
  `runtime_bound=true`, `live_ready=false`.
- Metadata-only bounded live authorization was created:
  `auth-91ac36ae4e6e46d8a87823811a81e103`.
- Final-gate dry-run after authorization returned:
  `final_preflight_result=blocked`.
- Execution endpoint was not called.
- No execution intent or order was created for
  `auth-91ac36ae4e6e46d8a87823811a81e103`.

Current hard blockers:

- GKS active:
  `global_kill_switch_state.active=true`,
  `reason=GKS_STATE_INITIALIZED_FAIL_CLOSED`.
- Production backend remains API-only, so startup guard final-gate source is
  `console_api_runtime_context_absent`.
- Reconciliation is not clean:
  PG has one BNB `STOP_MARKET` order with status `OPEN` and exchange order id
  `4000001470395922`; exchange read-only snapshot has zero BNB open orders.
- Runtime read-model schema gap:
  Tokyo `positions` table has `current_qty`, not `quantity`.

The current verdict remains `PASS_WITH_CONSTRAINT` until production runtime
binding, GKS/startup-guard safety state, and reconciliation are clean through an
approved workflow. No live order, cancel, replace, flatten, or retry protection
was executed during this acceptance run.
