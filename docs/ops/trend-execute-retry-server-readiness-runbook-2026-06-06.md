> [!NOTE]
> **HISTORICAL_EVIDENCE** — This document is a historical operational, governance, sprint, product, or live-trial artifact from an earlier project phase.
>
> It may be useful for context, auditing, or traceability, but it does **not** represent current project state, constraints, product direction, or agent instructions.
>
> Current authoritative sources:
> - `docs/canon/PROJECT_BASELINE_CURRENT.md`
> - `docs/canon/BRC_TARGET_SEMANTICS.md`
> - `docs/canon/AGENT_WORKSPACE_RULES.md`
> - `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
> - `docs/canon/TECH_DEBT_BASELINE.md`
> - `docs/canon/DOCUMENT_GOVERNANCE.md`

# Trend Execute Retry Server Readiness Runbook - 2026-06-06

## Purpose

Prepare the server-side evidence chain for the exact Trend bounded live action:

- carrier: `TF-001-live-readonly-v0`
- symbol: `SOL/USDT:USDT`
- side: `long`
- quantity: `0.1`
- max notional: `20`
- leverage: `1`
- protection: `single_tp_plus_sl`

This runbook does not authorize unauditable trading. It defines the evidence
that must exist before the official execute endpoint can be used.

Local developer machines are not valid execution venues for this runbook. Local
work may compile, test, inspect, and dry-run the readiness code only. Credential
preflight with `run=true`, final-gate dry-run against live server facts, and the
official execute request must run through the server API environment that owns
the live exchange credentials and allowed source IP.

## Hard Boundaries

Do not paste, log, commit, or report API key or secret values.

Do not use `BINANCE_API_KEY` or `BINANCE_SECRET_KEY` as the mainline credential
source. The application credential names are:

- `EXCHANGE_API_KEY`
- `EXCHANGE_API_SECRET`

Do not reuse `auth-f43ecd5901c342deb4b2466c0548ebc4` blindly. That authorization
has prior failed intent/local order evidence and must remain blocked unless an
explicit audited failed-attempt resolution policy says otherwise.

Do not execute if any step below is blocked or returns stale/ambiguous evidence.

## Required Server Environment

The server environment used for the credential preflight must have:

- `TRADING_ENV=live`
- `EXCHANGE_TESTNET=false`
- `EXCHANGE_NAME=binance`
- `EXCHANGE_API_KEY` set
- `EXCHANGE_API_SECRET` set
- `RUNTIME_CONTROL_API_ENABLED=false`
- `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=false`

For the official execute route, the server-side permission mode must be
`BRC_EXECUTION_PERMISSION_MAX=order_allowed`. This is not a global auto-execute
grant; the action must still pass Owner authorization, final gate, PG evidence,
and exchange evidence.

## Server Evidence Sequence

The sequence can be run manually with the endpoints below or by using the
server-readiness probe:

```bash
TREND_EXECUTE_API_BASE="https://<server-api-host>" \
TREND_EXECUTE_SESSION_COOKIE="<operator-session-cookie-or-token>" \
TREND_EXECUTE_AUTHORIZATION_ID="auth-..." \
python3 scripts/probe_trend_execute_server_readiness.py
```

Default `TREND_EXECUTE_MODE=evidence` only calls GET endpoints. To execute, the
server operator must set both:

```bash
TREND_EXECUTE_MODE=execute
OWNER_APPROVED_TREND_BOUNDED_EXECUTION="TF-001-live-readonly-v0:SOL/USDT:USDT:LONG:0.1:20:1:max_attempts_1:single_tp_plus_sl"
```

The probe blocks execute unless credential preflight, execution-state retry
policy, execute-readiness, and final-gate dry-run all pass. It redacts cookies,
tokens, secrets, and authorization headers from output.

To create a fresh Owner authorization after credential preflight passes, use:

```bash
TREND_EXECUTE_MODE=prepare_authorization
OWNER_APPROVED_TREND_BOUNDED_EXECUTION="TF-001-live-readonly-v0:SOL/USDT:USDT:LONG:0.1:20:1:max_attempts_1:single_tp_plus_sl"
```

`prepare_authorization` first runs credential preflight and blocks if it does
not pass. If it passes, it uses the official metadata-only authorization path:
`current?carrier_id=TF-001-live-readonly-v0` -> risk acknowledgement ->
authorization draft -> live authorization activation. This mode does not run
final gate, create an ExecutionIntent, place an order, or call the execute
endpoint.

### 1. Credential Preflight

Call:

```text
GET /api/brc/owner-trial-flow/exchange-credential-preflight?run=true
```

Pass conditions:

- `result=passed`
- `env_blockers=[]`
- `hard_blockers=[]`
- `checks` include:
  - `load_usdt_m_futures_markets`
  - `binance_api_restrictions`
  - `usdt_m_futures_account_read`
  - `scoped_position_read`
  - `scoped_open_order_read`
  - `scoped_stop_order_read`
  - `scoped_market_metadata_read`
- Binance restriction summary proves:
  - `read_only_permission_present=true`
  - `futures_trade_permission_present=true`
  - `withdrawals_enabled=false`
- scoped SOL account facts are readable.

If blocked, record:

```yaml
stage: exchange_credential_preflight
severity: hard_blocker
retry_condition: fix server credential/IP/futures permissions and rerun credential preflight
```

### 2. Failed Authorization Evidence

For any candidate authorization, call:

```text
GET /api/brc/owner-trial-flow/authorizations/{authorization_id}/execution-state
```

Pass conditions:

- `retry_allowed=true`
- `retry_blockers=[]`
- no linked local order evidence
- no linked exchange order evidence
- execution result evidence is compatible with the retry policy.

If the authorization is `auth-f43ecd5901c342deb4b2466c0548ebc4`, expected result
is blocked because it has previous failed intent/local order evidence. Use a
fresh Owner authorization unless an explicit audited resolution policy is added.

Current implementation status: no audited failed-attempt resolution path exists
for an authorization that already has linked local order evidence. The accepted
path is a fresh Owner authorization after credential proof passes. Do not patch
PG to hide or detach the failed attempt.

### 3. Execute Readiness

Call:

```text
GET /api/brc/owner-trial-flow/authorizations/{authorization_id}/execute-readiness
```

Pass conditions:

- `ready=true`
- `blockers=[]`
- `supported=true`
- `creates_execution_intent_on_click=true`
- `creates_order_on_click=true`
- `order_permission_granted=false`

The last flag remains false because readiness does not grant permission. It only
states what the official execute endpoint would do if invoked.

### 4. Exact Trend FinalGate Dry Run

Call:

```text
GET /api/brc/owner-trial-flow/authorizations/{authorization_id}/final-gate-dry-run?run=true
```

Pass conditions:

- `result=passed`
- `final_gate.final_preflight_result=passed`
- `final_gate.hard_blockers=[]`
- `final_gate.carrier_id=TF-001-live-readonly-v0`
- `final_gate.symbol=SOL/USDT:USDT`
- `final_gate.side=long`
- `final_gate.non_permissions.execution_intent_created=false`
- `final_gate.non_permissions.order_created=false`
- `final_gate.non_permissions.exchange_write_api_called=false`

If blocked, record the hard blockers and do not execute.

### 5. Official Execute

Only after steps 1-4 pass with a fresh/resolved Owner authorization, call:

```text
POST /api/brc/owner-trial-flow/authorizations/{authorization_id}/execute
```

Expected post-execute evidence if successful:

- one ExecutionIntent linked to the authorization
- one entry order record
- TP and SL protection order records
- review/result envelope in `brc_execution_results`
- post-execute exchange read confirms the actual position/open-order state
- no action outside the exact Trend scope.

If the exchange rejects the entry, preserve the failed intent/order/review
evidence and do not retry the same authorization unless the retry policy says
the failure happened before any local or exchange order evidence existed.

## Minimum Report Fields

Every server run report should include:

- credential preflight result and sanitized blocker categories
- authorization id used
- execution-state retry verdict
- execute-readiness verdict
- final-gate dry-run verdict
- execute response if executed
- pre/post PG evidence counts
- pre/post exchange position/open-order counts
- safety proof: no secrets printed, no actions outside exact scope
- push status
